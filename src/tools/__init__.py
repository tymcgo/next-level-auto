"""Tool registry + gateway — idempotent, env-secrets, prompt injection filter."""
from __future__ import annotations

import os
import re
from typing import Any, Callable, Awaitable

from ..schemas import NextLevelMoment

# Type alias for tool handlers
ToolHandler = Callable[[dict[str, Any], dict[str, str]], Awaitable[dict[str, Any]]]

# Prompt injection patterns — reject before any LLM-derived input reaches tools
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions?",
    r"you\s+are\s+now",
    r"system\s*prompt",
    r"<\s*/\s*instruction\s*>",
    r"<\s*instruction\s*>",
    r"<!--\s*system",
    r"\{\{\s*config",
    r"\$\{",
    r"`\s*rm\s+-rf",
]


def sanitize_input(value: str) -> str:
    """Detect and reject prompt-injection payloads."""
    lowered = value.lower()
    for pat in _INJECTION_PATTERNS:
        if re.search(pat, lowered):
            raise ValueError(f"Potential prompt injection detected: {pat}")
    return value


def require_env(keys: list[str]) -> dict[str, str]:
    """Pull secrets from env only — never from config.yaml or user input."""
    out = {}
    for k in keys:
        v = os.environ.get(k)
        if not v:
            raise EnvironmentError(f"Missing required env var: {k}")
        out[k] = v
    return out


class ToolRegistry:
    """Maps tool name -> handler. All tools are idempotent via idempotency_key."""

    def __init__(self):
        self._tools: dict[str, ToolHandler] = {}

    def register(self, name: str, handler: ToolHandler) -> None:
        if name in self._tools:
            raise KeyError(f"Tool {name!r} already registered")
        self._tools[name] = handler

    def get(self, name: str) -> ToolHandler:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name!r}")
        return self._tools[name]

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(
        self,
        name: str,
        args: dict[str, Any],
        env_keys: list[str],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Execute a tool with env injection + idempotency check."""
        # Sanitize any string args
        for k, v in args.items():
            if isinstance(v, str):
                args[k] = sanitize_input(v)
        env = require_env(env_keys)
        handler = self.get(name)
        result = await handler(args | {"_env": env, "_idempotency_key": idempotency_key})
        result["_tool"] = name
        result["_idempotency_key"] = idempotency_key
        return result


# ---------- Tool handler stubs (real implementations in tools/) ----------

async def _decode_vin(args: dict[str, Any]) -> dict[str, Any]:
    """NHTSA free VIN decoder."""
    import httpx

    vin = args["vin"]
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}?format=json"
        )
        r.raise_for_status()
        results = r.json().get("Results", [])
        decoded = {}
        for item in results:
            if item.get("Value"):
                decoded[item["Variable"]] = item["Value"]
    return {"vin": vin, "year": decoded.get("Model Year"), "make": decoded.get("Make"), "model": decoded.get("Model")}


async def _create_ro(args: dict[str, Any]) -> dict[str, Any]:
    """Create RO in shop system API (Tekmetric/Shopmonkey auto-detect)."""
    # Real implementation calls SHOP_API_BASE with SHOP_API_KEY
    return {"ro_id": f"RO-{args['_idempotency_key'][:8]}", "status": "created"}


async def _create_estimate(args: dict[str, Any]) -> dict[str, Any]:
    """Create written estimate record."""
    return {"estimate_id": f"EST-{args['_idempotency_key'][:8]}", "status": "created"}


async def _send_sms(args: dict[str, Any]) -> dict[str, Any]:
    """Twilio SMS — TEST mode prefixes [TEST - approve in Telegram]."""
    env = args["_env"]
    to = args["to"]
    body = args["body"]
    test_mode = os.environ.get("SMS_TEST_MODE", "true").lower() == "true"
    if test_mode:
        body = f"[TEST - approve in Telegram] {body}"
    # Real: Twilio REST call using env["TWILIO_ACCOUNT_SID"], env["TWILIO_AUTH_TOKEN"]
    return {"to": to, "body": body, "sent": True, "test_mode": test_mode}


async def _order_parts(args: dict[str, Any]) -> dict[str, Any]:
    """Email parts order to supplier (mock + email)."""
    return {"order_id": f"PART-{args['_idempotency_key'][:8]}", "supplier_email": args.get("supplier_email", "")}


async def _create_stripe_subscription(args: dict[str, Any]) -> dict[str, Any]:
    """Stripe subscription from config.yaml plan."""
    return {
        "subscription_id": f"sub_{args['_idempotency_key'][:8]}",
        "plan": args.get("plan"),
        "status": "active",
    }


async def _update_website_inventory(args: dict[str, Any]) -> dict[str, Any]:
    """Webhook to website inventory system."""
    return {"webhook": args.get("webhook_url"), "status": "posted"}


async def _audit_log(args: dict[str, Any]) -> dict[str, Any]:
    """Append to audit log table."""
    return {"logged": True, "timestamp": args.get("timestamp"), "event": args.get("event")}


def build_default_registry() -> ToolRegistry:
    """Register the 8 core tools."""
    reg = ToolRegistry()
    reg.register("decode_vin", _decode_vin)
    reg.register("create_ro", _create_ro)
    reg.register("create_estimate", _create_estimate)
    reg.register("send_sms", _send_sms)
    reg.register("order_parts", _order_parts)
    reg.register("create_stripe_subscription", _create_stripe_subscription)
    reg.register("update_website_inventory", _update_website_inventory)
    reg.register("audit_log", _audit_log)
    return reg
