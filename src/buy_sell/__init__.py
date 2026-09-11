"""Buy/Sell module — vehicle appraisals, Black Book lookup, website listing."""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BuySellManager:
    """Vehicle appraisal and listing flow."""

    def __init__(self, config_path: str):
        with open(config_path) as f:
            import yaml
            self.config = yaml.safe_load(f)

    async def appraise_vehicle(
        self,
        vin: str,
        mileage: int,
        condition: str,  # excellent, good, fair, poor
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Appraise a vehicle — Black Book lookup stub + condition adjustment."""
        # Black Book API stub — real implementation would call their API
        base_value_cents = await self._black_book_lookup(vin, mileage)

        # Condition multiplier
        multipliers = {"excellent": 1.0, "good": 0.85, "fair": 0.7, "poor": 0.5}
        multiplier = multipliers.get(condition.lower(), 0.7)

        offer_cents = int(base_value_cents * multiplier)

        # Cap at max_appraisal_cents from config
        max_cents = self.config.get("buy_sell", {}).get("max_appraisal_cents", 0)
        if max_cents > 0:
            offer_cents = min(offer_cents, max_cents)

        return {
            "vin": vin,
            "mileage": mileage,
            "condition": condition,
            "base_value_cents": base_value_cents,
            "offer_cents": offer_cents,
            "idempotency_key": idempotency_key,
            "status": "appraised",
        }

    async def _black_book_lookup(self, vin: str, mileage: int) -> int:
        """Stub for Black Book API. Returns base value in cents."""
        # Real: call Black Book API with VIN + mileage
        # For now, return a placeholder based on VIN hash for determinism
        import hashlib
        h = hashlib.md5(vin.encode()).hexdigest()
        # $5,000 - $35,000 range
        base = 500000 + (int(h[:8], 16) % 300000)
        return base

    async def list_vehicle(
        self,
        vin: str,
        mileage: int,
        asking_price_cents: int,
        photos: list[str],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """List vehicle for sale on website via webhook."""
        webhook_url = self.config.get("buy_sell", {}).get("website_webhook_url", "")
        if not webhook_url:
            logger.warning("No website webhook URL configured")
            return {"status": "no_webhook", "vin": vin}

        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                webhook_url,
                json={
                    "event": "vehicle_listed",
                    "vin": vin,
                    "mileage": mileage,
                    "asking_price_cents": asking_price_cents,
                    "photos": photos,
                    "idempotency_key": idempotency_key,
                },
                headers={
                    "Content-Type": "application/json",
                    "X-Idempotency-Key": idempotency_key,
                },
            )
            r.raise_for_status()
            return {"status": "listed", "vin": vin, "webhook_response": r.status_code}
