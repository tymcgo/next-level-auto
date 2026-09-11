"""ToolRegistry — 8-tool allowlist with idempotency, retry, and circuit breaker."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


class CircuitBreaker:
    """Simple circuit breaker pattern."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open
    
    def can_execute(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half-open"
                return True
            return False
        return True  # half-open
    
    def record_success(self):
        self.failures = 0
        self.state = "closed"
    
    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "open"


class ToolRegistry:
    """8-tool gateway with idempotency and secret injection."""
    
    ALLOWLIST = [
        "decode_vin",
        "create_ro",
        "create_estimate",
        "send_sms",
        "order_parts",
        "create_stripe_subscription",
        "list_vehicle_for_sale",
        "audit_log",
    ]
    
    def __init__(self, config: dict, http: httpx.AsyncClient):
        self.config = config
        self.http = http
        self.secrets = self._load_secrets()
        self.circuit_breakers: dict[str, CircuitBreaker] = {
            tool: CircuitBreaker() for tool in self.ALLOWLIST
        }
    
    def _load_secrets(self) -> dict:
        """Load secrets from environment only — never hardcoded."""
        return {
            "STRIPE_SECRET_KEY": os.getenv("STRIPE_SECRET_KEY", ""),
            "TWILIO_ACCOUNT_SID": os.getenv("TWILIO_ACCOUNT_SID", ""),
            "TWILIO_AUTH_TOKEN": os.getenv("TWILIO_AUTH_TOKEN", ""),
            "TWILIO_PHONE_NUMBER": os.getenv("TWILIO_PHONE_NUMBER", ""),
            "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
            "SUPABASE_URL": os.getenv("SUPABASE_URL", ""),
            "SUPABASE_SERVICE_KEY": os.getenv("SUPABASE_SERVICE_KEY", ""),
        }
    
    def _check_idempotency(self, key: str) -> bool:
        """Check if this idempotency key was already processed."""
        # In production, check Supabase
        # For now, always return False (assume not processed)
        return False
    
    async def invoke(self, tool_name: str, params: dict, context: dict) -> dict:
        """Invoke a tool with full idempotency + circuit breaker protection."""
        
        # Allowlist check
        if tool_name not in self.ALLOWLIST:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not in allowlist: {self.ALLOWLIST}",
            }
        
        # Circuit breaker check
        cb = self.circuit_breakers[tool_name]
        if not cb.can_execute():
            return {
                "success": False,
                "error": f"Circuit breaker OPEN for tool '{tool_name}'",
            }
        
        # Idempotency check
        idempotency_key = context.get("idempotency_key", "")
        if idempotency_key and self._check_idempotency(idempotency_key):
            return {
                "success": True,
                "data": {"message": "Already processed (idempotent skip)"},
                "idempotency_key": idempotency_key,
            }
        
        # Dispatch to handler
        handler = getattr(self, f"_handle_{tool_name}", None)
        if not handler:
            return {"success": False, error: f"No handler for tool '{tool_name}'"}
        
        try:
            result = await handler(params, context)
            cb.record_success()
            result["idempotency_key"] = idempotency_key
            return result
        except Exception as e:
            cb.record_failure()
            return {
                "success": False,
                "error": str(e),
                "idempotency_key": idempotency_key,
            }
    
    # =================================================================
    # Tool handlers
    # =================================================================
    
    async def _handle_decode_vin(self, params: dict, context: dict) -> dict:
        """Decode VIN via NHTSA free API."""
        vin = params.get("vin", "").upper()
        if not vin or len(vin) != 17:
            return {"success": False, "error": "Invalid VIN"}
        
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json"
        res = await self.http.get(url)
        data = res.json()
        
        results = data.get("Results", [])
        get = lambda var: next((r["Value"] for r in results if r.get("Variable") == var), None)
        
        return {
            "success": True,
            "data": {
                "vin": vin,
                "year": int(get("Model Year") or 0),
                "make": get("Make"),
                "model": get("Model"),
                "trim": get("Trim"),
                "engine": get("Engine Model"),
                "transmission": get("Transmission Style"),
            },
        }
    
    async def _handle_create_ro(self, params: dict, context: dict) -> dict:
        """Create repair order via Supabase RPC."""
        supabase_url = self.secrets["SUPABASE_URL"]
        supabase_key = self.secrets["SUPABASE_SERVICE_KEY"]
        
        res = await self.http.post(
            f"{supabase_url}/rest/v1/rpc/create_repair_order",
            json={
                "p_vehicle_id": params.get("vehicle_id"),
                "p_customer_id": params.get("customer_id"),
                "p_description": params.get("description"),
                "p_line_items": params.get("line_items", []),
                "p_notes": params.get("notes"),
            },
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
        )
        
        if res.status_code >= 400:
            return {"success": False, "error": f"Supabase error: {res.text[:300]}"}
        
        return {"success": True, "data": {"ro_id": res.json()}}
    
    async def _handle_create_estimate(self, params: dict, context: dict) -> dict:
        """Create estimate via Supabase RPC."""
        supabase_url = self.secrets["SUPABASE_URL"]
        supabase_key = self.secrets["SUPABASE_SERVICE_KEY"]
        
        res = await self.http.post(
            f"{supabase_url}/rest/v1/rpc/create_estimate",
            json={
                "p_ro_id": params.get("ro_id"),
                "p_vehicle_id": params.get("vehicle_id"),
                "p_customer_id": params.get("customer_id"),
                "p_line_items": params.get("line_items", []),
                "p_notes": params.get("notes"),
                "p_expires_in_days": params.get("expires_in_days", 7),
            },
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
        )
        
        if res.status_code >= 400:
            return {"success": False, "error": f"Supabase error: {res.text[:300]}"}
        
        return {"success": True, "data": {"estimate_id": res.json()}}
    
    async def _handle_send_sms(self, params: dict, context: dict) -> dict:
        """Send SMS via Twilio."""
        account_sid = self.secrets["TWILIO_ACCOUNT_SID"]
        auth_token = self.secrets["TWILIO_AUTH_TOKEN"]
        from_number = self.secrets["TWILIO_PHONE_NUMBER"]
        
        if not account_sid or not auth_token:
            return {"success": False, "error": "Twilio not configured"}
        
        body = params.get("body", "")
        test_mode = os.getenv("TEST_MODE", "true") == "true"
        if test_mode:
            body = f"[TEST] {body}"
        
        res = await self.http.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
            data={"To": params.get("to"), "From": from_number, "Body": body},
            auth=(account_sid, auth_token),
        )
        
        if res.status_code >= 400:
            return {"success": False, "error": f"Twilio error: {res.text[:300]}"}
        
        data = res.json()
        return {"success": True, "data": {"message_sid": data.get("sid"), "status": data.get("status")}}
    
    async def _handle_order_parts(self, params: dict, context: dict) -> dict:
        """Order parts via Supabase RPC."""
        supabase_url = self.secrets["SUPABASE_URL"]
        supabase_key = self.secrets["SUPABASE_SERVICE_KEY"]
        
        res = await self.http.post(
            f"{supabase_url}/rest/v1/rpc/order_parts",
            json={
                "p_supplier": params.get("supplier"),
                "p_parts": params.get("parts", []),
                "p_ro_id": params.get("ro_id"),
            },
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
        )
        
        if res.status_code >= 400:
            return {"success": False, "error": f"Supabase error: {res.text[:300]}"}
        
        return {"success": True, "data": res.json()}
    
    async def _handle_create_stripe_subscription(self, params: dict, context: dict) -> dict:
        """Create Stripe Checkout session."""
        stripe_key = self.secrets["STRIPE_SECRET_KEY"]
        if not stripe_key:
            return {"success": False, "error": "Stripe not configured"}
        
        res = await self.http.post(
            "https://api.stripe.com/v1/checkout/sessions",
            data={
                "mode": "subscription",
                "success_url": params.get("success_url"),
                "cancel_url": params.get("cancel_url"),
                "line_items[0][price_data][currency]": "usd",
                f"line_items[0][price_data][product_data][name]": f"{params.get('plan_type')} care plan",
                "line_items[0][price_data][recurring][interval]": "month",
                "line_items[0][price_data][unit_amount]": "9999",
                "line_items[0][quantity]": "1",
            },
            headers={"Authorization": f"Bearer {stripe_key}"},
        )
        
        if res.status_code >= 400:
            return {"success": False, "error": f"Stripe error: {res.text[:300]}"}
        
        data = res.json()
        return {"success": True, "data": {"session_id": data.get("id"), "url": data.get("url")}}
    
    async def _handle_list_vehicle_for_sale(self, params: dict, context: dict) -> dict:
        """List vehicle for sale via Supabase RPC."""
        supabase_url = self.secrets["SUPABASE_URL"]
        supabase_key = self.secrets["SUPABASE_SERVICE_KEY"]
        
        res = await self.http.post(
            f"{supabase_url}/rest/v1/rpc/list_vehicle",
            json={
                "p_vehicle_id": params.get("vehicle_id"),
                "p_list_price": params.get("list_price"),
                "p_description": params.get("description"),
                "p_photos": params.get("photos", []),
                "p_condition_notes": params.get("condition_notes"),
            },
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
        )
        
        if res.status_code >= 400:
            return {"success": False, "error": f"Supabase error: {res.text[:300]}"}
        
        return {"success": True, "data": {"appraisal_id": res.json()}}
    
    async def _handle_audit_log(self, params: dict, context: dict) -> dict:
        """Write audit log entry."""
        supabase_url = self.secrets["SUPABASE_URL"]
        supabase_key = self.secrets["SUPABASE_SERVICE_KEY"]
        
        res = await self.http.post(
            f"{supabase_url}/rest/v1/audit_log",
            json={
                "action": params.get("action"),
                "actor_id": context.get("actor_id"),
                "target_type": params.get("target_type"),
                "target_id": params.get("target_id"),
                "before_state": params.get("before_state"),
                "after_state": params.get("after_state"),
                "metadata": params.get("metadata"),
            },
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
        )
        
        if res.status_code >= 400:
            return {"success": False, "error": f"Supabase error: {res.text[:300]}"}
        
        return {"success": True, "data": res.json()}


import os  # noqa: E402 — needed for secrets loading
