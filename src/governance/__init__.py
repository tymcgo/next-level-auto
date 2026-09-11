"""Governance — approval gate, SLA enforcement, notification routing."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
import yaml

logger = logging.getLogger(__name__)


class GovernanceEngine:
    """Evaluate moments against policies.yaml rules."""

    def __init__(self, config_path: str, policies_path: str):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        with open(policies_path) as f:
            self.policies = yaml.safe_load(f)

    def requires_approval(self, estimate_total_cents: int) -> bool:
        """Check if estimate exceeds threshold."""
        threshold = self.policies.get("approval", {}).get("threshold_cents", 0)
        return estimate_total_cents > threshold

    def sla_seconds(self) -> int:
        return self.policies.get("approval", {}).get("sla_seconds", 10800)

    def auto_approve(self, moment_type: str, estimate_cents: int) -> bool:
        """Check if this moment type is below auto-approve threshold."""
        for m in self.config.get("moments", []):
            if m.get("key") == moment_type:
                below = m.get("auto_approve_below", 0)
                return estimate_cents <= below
        return False


class NotificationRouter:
    """Route notifications by priority: P0 -> Telegram immediate, P1 -> digest."""

    def __init__(self, bot_token: str, owner_chat_id: int, digest_chat_id: int):
        self.bot_token = bot_token
        self.owner_chat_id = owner_chat_id
        self.digest_chat_id = digest_chat_id
        self.base = f"https://api.telegram.org/bot{bot_token}"
        self._digest_buffer: list[str] = []

    async def _api(self, method: str, **kwargs: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{self.base}/{method}", json=kwargs)
            r.raise_for_status()
            return r.json()

    async def send_p0(self, text: str) -> dict[str, Any]:
        """Immediate P0 notification to owner."""
        return await self._api("sendMessage", chat_id=self.owner_chat_id, text=f"🚨 P0: {text}")

    async def send_p1(self, text: str) -> dict[str, Any]:
        """P1 — daily digest entry."""
        self._digest_buffer.append(text)
        return {"status": "buffered", "count": len(self._digest_buffer)}

    async def send_approval_request(self, estimate_cents: int, vin: str, summary: str) -> dict[str, Any]:
        """Send inline YES/NO approval buttons to owner."""
        text = (
            f"💰 Approval Required\n"
            f"VIN: {vin}\n"
            f"Estimate: ${estimate_cents / 100:.2f}\n"
            f"{summary}"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": f"approve:yes:{vin}"},
                    {"text": "❌ Reject", "callback_data": f"approve:no:{vin}"},
                ]
            ]
        }
        return await self._api(
            "sendMessage",
            chat_id=self.owner_chat_id,
            text=text,
            reply_markup=json.dumps(keyboard),
        )

    async def flush_digest(self) -> dict[str, Any] | None:
        """Send accumulated P1 digest to digest chat."""
        if not self._digest_buffer:
            return None
        text = "📊 Daily Digest\n\n" + "\n".join(self._digest_buffer)
        self._digest_buffer = []
        return await self._api("sendMessage", chat_id=self.digest_chat_id, text=text)


class SLAMonitor:
    """Watch pending approvals and escalate after SLA breach."""

    def __init__(self, sla_seconds: int, escalation_sms: bool):
        self.sla_seconds = sla_seconds
        self.escalation_sms = escalation_sms
        self._pending: dict[str, float] = {}  # idempotency_key -> timestamp

    def track(self, idempotency_key: str) -> None:
        self._pending[idempotency_key] = time.time()

    def resolve(self, idempotency_key: str) -> None:
        self._pending.pop(idempotency_key, None)

    def get_breached(self) -> list[str]:
        """Return list of keys that have exceeded SLA."""
        now = time.time()
        return [k for k, ts in self._pending.items() if now - ts > self.sla_seconds]
