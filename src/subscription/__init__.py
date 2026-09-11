"""Subscription flow — Stripe integration for care plans."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """Create Stripe subscriptions from config.yaml plans."""

    def __init__(self, stripe_key: str, config_path: str):
        self.stripe_key = stripe_key
        self.base = "https://api.stripe.com/v1"
        with open(config_path) as f:
            import yaml
            self.config = yaml.safe_load(f)

    def _plans(self) -> list[dict[str, Any]]:
        return self.config.get("plans", [])

    def get_plan(self, name: str) -> dict[str, Any] | None:
        for p in self._plans():
            if p.get("name", "").lower() == name.lower():
                return p
        return None

    async def create_subscription(
        self,
        customer_email: str,
        plan_name: str,
        vin: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Create Stripe subscription. Idempotent via idempotency_key."""
        plan = self.get_plan(plan_name)
        if not plan:
            raise ValueError(f"Unknown plan: {plan_name}")

        # 1. Get or create Stripe customer
        customer = await self._get_or_create_customer(customer_email)

        # 2. Create subscription
        sub = await self._create_stripe_subscription(
            customer["id"], plan["price_cents"], vin, idempotency_key
        )

        # 3. Provision credits in customer_credits table (via Supabase)
        await self._provision_credits(customer_email, plan_name, vin)

        return {
            "subscription_id": sub["id"],
            "customer_id": customer["id"],
            "plan": plan_name,
            "status": sub["status"],
            "idempotency_key": idempotency_key,
        }

    async def _get_or_create_customer(self, email: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as c:
            # Search for existing
            r = await c.get(
                f"{self.base}/customers",
                params={"email": email, "limit": 1},
                headers={"Authorization": f"Bearer {self.stripe_key}"},
            )
            r.raise_for_status()
            data = r.json().get("data", [])
            if data:
                return data[0]
            # Create new
            r = await c.post(
                f"{self.base}/customers",
                data={"email": email},
                headers={"Authorization": f"Bearer {self.stripe_key}"},
            )
            r.raise_for_status()
            return r.json()

    async def _create_stripe_subscription(
        self, customer_id: str, price_cents: int, vin: str, idempotency_key: str
    ) -> dict[str, Any]:
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"{self.base}/subscriptions",
                data={
                    "customer": customer_id,
                    "items[0][price_data][currency]": "usd",
                    "items[0][price_data][unit_amount]": price_cents,
                    "items[0][price_data][recurring][interval]": "month",
                    "items[0][price_data][product_data][name]": f"Care Plan - {vin}",
                    "metadata[vin]": vin,
                    "metadata[idempotency_key]": idempotency_key,
                },
                headers={
                    "Authorization": f"Bearer {self.stripe_key}",
                    "Idempotency-Key": idempotency_key,
                },
            )
            r.raise_for_status()
            return r.json()

    async def _provision_credits(self, email: str, plan_name: str, vin: str) -> None:
        """Provision credits in customer_credits table via Supabase."""
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not supabase_url or not supabase_key:
            logger.warning("Supabase not configured — skipping credit provisioning")
            return
        async with httpx.AsyncClient() as c:
            await c.post(
                f"{supabase_url}/rest/v1/customer_credits",
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={
                    "customer_email": email,
                    "vin": vin,
                    "plan": plan_name,
                    "credits_remaining": 1,  # 1 service per month
                },
            )
