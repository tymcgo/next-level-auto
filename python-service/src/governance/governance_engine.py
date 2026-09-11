"""GovernanceEngine — approval routing, notifications, SLA enforcement."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any

import httpx
import yaml


class GovernanceEngine:
    """Handles governance: approvals, notifications, SLA monitoring."""
    
    def __init__(self, config: dict, http: httpx.AsyncClient):
        self.config = config
        self.http = http
        self.secrets = self._load_secrets()
        governance_cfg = config.get("governance", {})
        self.estimator_approval_threshold = governance_cfg.get("approval_policies", [{}])[0].get("threshold", 750)
        self.approver = governance_cfg.get("approval_policies", [{}])[0].get("approver", "tyler")
        self.sla_hours = governance_cfg.get("approval_policies", [{}])[0].get("sla_hours", 3)
    
    def _load_secrets(self) -> dict:
        return {
            "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
            "TELEGRAM_ADMIN_CHAT_ID": os.getenv("TELEGRAM_ADMIN_CHAT_ID", ""),
            "SLACK_WEBHOOK_URL": os.getenv("SLACK_WEBHOOK_URL", ""),
            "SUPABASE_URL": os.getenv("SUPABASE_URL", ""),
            "SUPABASE_SERVICE_KEY": os.getenv("SUPABASE_SERVICE_KEY", ""),
        }
    
    async def handle(self, action: str, data: dict) -> dict:
        """Dispatch governance action."""
        handler = getattr(self, f"_handle_{action}", None)
        if not handler:
            return {"success": False, "error": f"Unknown action: {action}"}
        return await handler(data)
    
    async def _handle_request_approval(self, data: dict) -> dict:
        """Create approval request and notify approver."""
        target_type = data.get("target_type")
        target_id = data.get("target_id")
        requested_by = data.get("requested_by", "system")
        reason = data.get("reason", f"Approval required for {target_type}")
        
        # Create approval record
        supabase_url = self.secrets["SUPABASE_URL"]
        supabase_key = self.secrets["SUPABASE_SERVICE_KEY"]
        
        res = await self.http.post(
            f"{supabase_url}/rest/v1/approvals",
            json={
                "target_type": target_type,
                "target_id": target_id,
                "status": "pending",
                "requested_by": requested_by,
                "required_by": self.approver,
                "expires_at": (datetime.utcnow() + timedelta(hours=self.sla_hours)).isoformat(),
            },
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
        )
        
        if res.status_code >= 400:
            return {"success": False, "error": f"Failed to create approval: {res.text[:200]}"}
        
        approval_id = res.json().get("id")
        
        # Send Telegram notification to approver
        await self._notify_telegram(
            f"🔔 Approval Required\n"
            f"Type: {target_type}\n"
            f"ID: {target_id}\n"
            f"Reason: {reason}\n"
            f"SLA: {self.sla_hours}h\n"
            f"ID: {approval_id}",
            "P0"
        )
        
        return {"success": True, "approval_id": approval_id, "status": "pending"}
    
    async def _handle_check_sla(self, data: dict) -> dict:
        """Check for breached SLAs and escalate."""
        supabase_url = self.secrets["SUPABASE_URL"]
        supabase_key = self.secrets["SUPABASE_SERVICE_KEY"]
        
        # Find pending approvals past SLA
        res = await self.http.get(
            f"{supabase_url}/rest/v1/approvals?status=eq.pending&expires_at=lt.{datetime.utcnow().isoformat()}",
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
        )
        
        breached = res.json() if res.status_code == 0 else []
        
        for approval in breached:
            # Escalate
            await self._escalate(approval)
        
        return {"success": True, "breached_count": len(breached), "breached": breached}
    
    async def _handle_escalate(self, data: dict) -> dict:
        """Manually trigger escalation."""
        approval_id = data.get("approval_id")
        return await self._escalate({"id": approval_id})
    
    async def _escalate(self, approval: dict) -> dict:
        """Escalate a single approval."""
        supabase_url = self.secrets["SUPABASE_URL"]
        supabase_key = self.secrets["SUPABASE_SERVICE_KEY"]
        
        # Update escalation count
        await self.http.patch(
            f"{supabase_url}/rest/v1/approvals?id=eq.{approval['id']}",
            json={
                "escalation_count": approval.get("escalation_count", 0) + 1,
            },
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
        )
        
        # Notify
        await self._notify_telegram(
            f"⚠️ ESCALATION\n"
            f"Approval {approval.get('id', approval.get('id', 'unknown'))}\n"
            f"Breached SLA for {approval.get('target_type', 'unknown')}\n"
            f"Escalation #{approval.get('escalation_count', 0) + 1}",
            "P0"
        )
        
        return {"success": True, "action": "escalated"}
    
    async def _notify_telegram(self, message: str, priority: str = "P1"):
        """Send Telegram notification."""
        bot_token = self.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = self.secrets["TELEGRAM_ADMIN_CHAT_ID"]
        
        if not bot_token or not chat_id:
            return
        
        test_mode = os.getenv("TEST_MODE", "true") == "true"
        if test_mode:
            message = f"[TEST] {message}"
        
        await self.http.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            },
        )
    
    async def _notify_slack(self, message: str):
        """Send Slack notification."""
        webhook = self.secrets["SLACK_WEBHOOK_URL"]
        if not webhook:
            return
        
        test_mode = os.getenv("TEST_MODE", "true") == "true"
        if test_mode:
            message = f"[TEST] {message}"
        
        await self.http.post(webhook, json={"text": message})
    
    async def _handle_send_digest(self, data: dict) -> dict:
        """Send daily digest."""
        supabase_url = self.secrets["SUPABASE_URL"]
        supabase_key = self.secrets["SUPABASE_SERVICE_KEY"]
        
        # Gather stats
        stats = {}
        for table in ["repair_orders", "approvals", "parts"]:
            res = await self.http.get(
                f"{supabase_url}/rest/v1/{table}?select=id",
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                },
            )
            stats[table] = len(res.json()) if res.status_code == 200 else 0
        
        message = (
            f"📊 Daily Digest\n"
            f"Open ROs: {stats.get('repair_orders', 0)}\n"
            f"Pending Approvals: {stats.get('approvals', 0)}\n"
            f"Parts Waiting: {stats.get('parts', 0)}"
        )
        
        await self._notify_telegram(message, "P2")
        
        return {"success": True, "message": "Digest sent"}
