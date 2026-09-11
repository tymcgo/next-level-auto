"""NextLevelEvent — Pydantic v2 canonical schema for Next Level Auto."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    VOICE_NOTE = "voice_note"
    VIN_PHOTO = "vin_photo"
    SMS_FORWARD = "sms_forward"
    WEBHOOK_IN = "webhook_in"
    RO_CREATED = "ro_created"
    ESTIMATE_CREATED = "estimate_created"
    ESTIMATE_APPROVED = "estimate_approved"
    PARTS_ORDERED = "parts_ordered"
    PARTS_RECEIVED = "parts_received"
    SUBSCRIPTION_SIGNED = "subscription_signed"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    VEHICLE_LISTED = "vehicle_listed"
    VEHICLE_SOLD = "vehicle_sold"
    VEHICLE_APPRAISED = "vehicle_appraised"
    PACKAGE_PURCHASED = "package_purchased"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_FAILED = "payment_failed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    AUDIT_LOG = "audit_log"


class EventSource(str, Enum):
    TELEGRAM_VOICE = "telegram_voice"
    TELEGRAM_PHOTO = "telegram_photo"
    TELEGRAM_SMS = "telegram_sms"
    WEBHOOK = "webhook"
    DASHBOARD = "dashboard"
    SYSTEM = "system"


class CostTokens(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    model: str = "unknown"
    estimated_cost_usd: float = Field(default=0.0, ge=0)


class NextLevelEvent(BaseModel):
    """Append-only, idempotent canonical event for all shop operations."""

    id: str = Field(default_factory=lambda: str(uuid.uuid7()))
    schema_version: str = "1.0.0"
    idempotency_key: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    event_type: EventType
    vin: str = Field(..., pattern=r"^[A-HJ-NPR-Z0-9]{17}$")
    vin_last6: str = Field(..., pattern=r"^[A-HJ-NPR-Z0-9]{6}$")
    timestamp: datetime
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict[str, Any]
    normalized: dict[str, Any] = Field(default_factory=dict)
    source: EventSource
    correlation_id: Optional[str] = None
    actor_id: Optional[str] = None
    cost_tokens: Optional[CostTokens] = None

    @field_validator("vin")
    @classmethod
    def validate_vin(cls, v: str) -> str:
        return v.upper()

    @field_validator("vin_last6")
    @classmethod
    def validate_vin_last6(cls, v: str, info) -> str:
        return v.upper()

    def model_post_init(self, __context: Any) -> None:
        """Ensure vin_last6 matches last 6 of vin if not provided correctly."""
        if self.vin and len(self.vin) >= 6:
            object.__setattr__(self, "vin_last6", self.vin[-6:])

    @staticmethod
    def compute_idempotency_key(vin: str, timestamp: str, raw: dict) -> str:
        """SHA-256(vin + timestamp + raw_json) for exactly-once processing."""
        payload = json.dumps(
            {"vin": vin.upper(), "timestamp": timestamp, "raw": raw},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
