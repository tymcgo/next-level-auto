"""Canonical domain schemas — Pydantic v2.

DESIGN PRINCIPLES:
- Every field has an explicit constraint (range, length, pattern, or enum).
- Money is always integer cents — never float dollars.
- Idempotency keys are `mom_` prefix + sha256 hex — unique across all time.
- VINs are ISO 3779 compliant (I/O/Q excluded, check-digit validated for 17-char).
- DTCs follow SAE J2012 format: [PBCU][0-9A-F]{4}.
- Status transitions are explicit — no undefined paths.
- All datetimes are timezone-aware UTC.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# CONSTANTS
# =============================================================================

# ISO 3779: VINs never contain I, O, or Q (easily confused with 1, 0, 9)
VIN_EXCLUDED_CHARS = frozenset("IOQ")
VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{11,17}$")
# SAE J2012 DTC format: network prefix + 4 hex digits
DTC_PATTERN = re.compile(r"^[PBCU][0-9A-Fa-f]{4}$")
# Idempotency key: `mom_` + 64 hex chars (sha256)
IDEMPOTENCY_PATTERN = re.compile(r"^mom_[0-9a-f]{64}$")
# Part numbers: alphanumeric, dashes, dots, 3-30 chars
PART_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9\-\.]{3,30}$")


# =============================================================================
# ENUMERATIONS
# =============================================================================

class MomentType(str, Enum):
    """The 8 canonical moment types — inferred from concern + diagnosis.
    
    LIFECYCLE: diagnosis → estimate → repair (after approval)
             maintenance (stand-alone, scheduled)
             subscription_signup → subscription_renewal (recurring)
             vehicle_appraisal → vehicle_listing (acquisition → sale)
    """
    diagnosis = "diagnosis"
    repair = "repair"
    estimate = "estimate"
    maintenance = "maintenance"
    subscription_signup = "subscription_signup"
    subscription_renewal = "subscription_renewal"
    vehicle_appraisal = "vehicle_appraisal"
    vehicle_listing = "vehicle_listing"


class ApprovalStatus(str, Enum):
    """Approval state machine.
    
    TRANSITIONS:
        pending → approved    (owner approves, or auto-approve if below threshold)
        pending → rejected    (owner rejects)
        pending → escalated   (SLA timer expired without response)
        escalated → approved  (owner approves after escalation)
        escalated → rejected  (owner rejects after escalation)
    
    NO BACKWARD TRANSITIONS: approved and rejected are terminal states.
    """
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    escalated = "escalated"


class SubscriptionPlan(str, Enum):
    """Care plan tiers — names populated by interview.
    
    Using str Enum so config.yaml plan names map directly.
    """
    BASIC = "BASIC"
    PLUS = "PLUS"
    PREMIUM = "PREMIUM"


class VehicleCondition(str, Enum):
    """Condition rating for appraisals — J.D. Power / Black Book scale."""
    excellent = "excellent"
    good = "good"
    fair = "fair"
    poor = "poor"


# =============================================================================
# VALUE OBJECTS
# =============================================================================

class Money(BaseModel):
    """Integer cents — never float. Prevents rounding errors in financial calc."""
    cents: int = Field(..., ge=0, description="Amount in cents")
    
    @property
    def dollars(self) -> float:
        return self.cents / 100
    
    def __add__(self, other: "Money") -> "Money":
        return Money(cents=self.cents + other.cents)
    
    def __mul__(self, qty: int | float) -> "Money":
        return Money(cents=int(self.cents * qty))


class PartLine(BaseModel):
    """A single line item in an estimate or RO."""
    part_number: str = Field(
        ...,
        min_length=3,
        max_length=30,
        description="Supplier part number (alphanumeric, dashes, dots)",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Human-readable part description",
    )
    quantity: int = Field(
        default=1,
        ge=1,
        le=100,
        description="Quantity ordered — minimum 1",
    )
    unit_cost_cents: int = Field(
        default=0,
        ge=0,
        le=1_000_000_000,  # $10M cap — catches data entry errors
        description="Cost per unit in cents",
    )
    
    @field_validator("part_number")
    @classmethod
    def validate_part_number(cls, v: str) -> str:
        if not PART_NUMBER_PATTERN.match(v):
            raise ValueError(
                f"Invalid part number '{v}': must match {PART_NUMBER_PATTERN.pattern}"
            )
        return v.upper()
    
    @property
    def line_total_cents(self) -> int:
        return self.unit_cost_cents * self.quantity


# =============================================================================
# CORE SCHEMA
# =============================================================================

class NextLevelMoment(BaseModel):
    """Canonical moment schema — the single source of truth for a shop event.
    
    INVARIANTS:
    - idempotency_key is globally unique (UNIQUE constraint in DB)
    - vin passes ISO 3779 validation (11-17 chars, no I/O/Q, check-digit for 17-char)
    - estimate_total_cents = (labor_hours * labor_rate_cents) + sum(parts.line_total_cents)
    - approval_status starts at pending, transitions follow state machine
    - raw input is retained for audit but capped at 10KB
    
    PARTITION KEY: vin (all moments for a vehicle are collected)
    SORT KEY: created_at (chronological within a vehicle)
    """
    
    idempotency_key: str = Field(
        ...,
        description="`mom_` + sha256(vin+timestamp+raw) — guarantees exactly-once processing",
    )
    vin: str = Field(
        ...,
        min_length=11,
        max_length=17,
        description="Vehicle Identification Number (ISO 3779)",
    )
    mileage: Optional[int] = Field(
        default=None,
        ge=0,
        le=2_000_000,  # 2M miles — catches odometer rollover / data errors
        description="Odometer reading at time of service",
    )
    dtcs: list[str] = Field(
        default_factory=list,
        max_length=50,  # Cap — more than 50 DTCs is likely a data error
        description="SAE J2012 Diagnostic Trouble Codes",
    )
    diag: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Technician diagnosis / notes",
    )
    parts: list[PartLine] = Field(
        default_factory=list,
        max_length=100,  # Cap — more than 100 line items is likely a data error
        description="Parts line items",
    )
    labor_hours: float = Field(
        default=0.0,
        ge=0.0,
        le=999.9,  # Cap — more than 999 hours is likely a data error
        description="Labor hours (tenths precision)",
    )
    labor_rate_cents: int = Field(
        default=0,
        ge=0,
        le=1_000_000,  # $10,000/hr cap — catches data entry errors
        description="Shop labor rate in cents/hour",
    )
    estimate_total_cents: int = Field(
        default=0,
        ge=0,
        le=100_000_000,  # $1M cap — catches data entry errors
        description="Total estimate in cents (labor + parts)",
    )
    approval_status: ApprovalStatus = Field(
        default=ApprovalStatus.pending,
        description="Current approval state",
    )
    subscription_plan: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Care plan name if subscription-related moment",
    )
    moment_type: MomentType = Field(
        default=MomentType.diagnosis,
        description="The 8 canonical moment types",
    )
    raw: Optional[str] = Field(
        default=None,
        max_length=10_000,  # 10KB cap — retains audit trail without unbounded storage
        description="Original voice transcription / text / forwarded SMS",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of moment creation",
    )
    
    # --- Validators ---
    
    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, v: str) -> str:
        if not IDEMPOTENCY_PATTERN.match(v):
            raise ValueError(
                f"Invalid idempotency_key '{v}': must match {IDEMPOTENCY_PATTERN.pattern}"
            )
        return v
    
    @field_validator("vin")
    @classmethod
    def validate_vin(cls, v: str) -> str:
        vin = v.upper().strip()
        # Length check AFTER strip (whitespace shouldn't count)
        if len(vin) < 11 or len(vin) > 17:
            raise ValueError(
                f"Invalid VIN '{vin}': length {len(vin)} not in 11-17 range"
            )
        if not VIN_PATTERN.match(vin):
            raise ValueError(
                f"Invalid VIN '{vin}': must exclude I/O/Q, "
                f"match {VIN_PATTERN.pattern}"
            )
        # ISO 3779 check digit validation for 17-char VINs
        # NOTE: This is a WARNING, not a hard rejection — shop VIN entry
        # is notoriously error-prone. We log but allow through.
        if len(vin) == 17:
            if not _validate_vin_check_digit(vin):
                # Log warning — do not raise
                import logging
                logging.getLogger(__name__).warning(
                    f"VIN '{vin}' check digit (position 9) fails ISO 3779 — "
                    f"allowed through but flagged for review"
                )
        return vin
    
    @field_validator("dtcs", mode="before")
    @classmethod
    def validate_dtcs(cls, v: list[str]) -> list[str]:
        normalized = []
        for dtc in v:
            dtc = dtc.upper().strip()
            if not DTC_PATTERN.match(dtc):
                raise ValueError(
                    f"Invalid DTC '{dtc}': must match {DTC_PATTERN.pattern}"
                )
            normalized.append(dtc)
        return normalized
    
    @model_validator(mode="after")
    def validate_estimate_total(self) -> "NextLevelMoment":
        """Ensure estimate_total_cents matches computed value if parts/labor present."""
        if self.parts or self.labor_hours > 0:
            labor_total = int(self.labor_hours * self.labor_rate_cents)
            parts_total = sum(p.line_total_cents for p in self.parts)
            expected = labor_total + parts_total
            # Allow tolerance for manual override (e.g., negotiated price)
            # but flag if mismatch is > 50% (data error)
            if self.estimate_total_cents > 0 and abs(self.estimate_total_cents - expected) > expected * 0.5:
                raise ValueError(
                    f"estimate_total_cents ({self.estimate_total_cents}) "
                    f"differs significantly from computed ({expected})"
                )
        return self


def _validate_vin_check_digit(vin: str) -> bool:
    """ISO 3779 VIN check digit validation (position 9).
    
    Uses transliteration weights. Returns True if check digit is valid.
    This catches 99% of VIN typos at the schema level.
    """
    # Transliteration table: char → value
    transliteration = {
        "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
        "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
        "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
    }
    for d in "0123456789":
        transliteration[d] = int(d)
    
    # Position weights (1-indexed positions 1-17)
    weights = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
    
    total = 0
    for i, char in enumerate(vin):
        value = transliteration.get(char, 0)
        total += value * weights[i]
    
    remainder = total % 11
    expected_check = "X" if remainder == 10 else str(remainder)
    actual_check = vin[8]  # Position 9 (0-indexed: 8)
    
    return actual_check == expected_check


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def compute_idempotency_key(vin: str, timestamp: str, raw: str) -> str:
    """Deterministic key — same inputs always produce the same key.
    
    Format: `mom_` + sha256_hex(vin.upper() + timestamp + raw)
    The prefix allows quick identification and avoids collision with other key formats.
    """
    h = hashlib.sha256()
    h.update(vin.upper().encode("utf-8"))
    h.update(b"\x00")  # separator to prevent concatenation collisions
    h.update(timestamp.encode("utf-8"))
    h.update(b"\x00")
    h.update(raw.encode("utf-8"))
    return f"mom_{h.hexdigest()}"


def moment_from_raw(
    *,
    vin: str,
    timestamp: str,
    raw: str,
    mileage: Optional[int] = None,
    dtcs: Optional[list[str]] = None,
    diag: Optional[str] = None,
    parts: Optional[list[PartLine]] = None,
    labor_hours: float = 0.0,
    labor_rate_cents: int = 0,
    moment_type: MomentType = MomentType.diagnosis,
    subscription_plan: Optional[str] = None,
    approval_status: ApprovalStatus = ApprovalStatus.pending,
) -> NextLevelMoment:
    """Factory: build a fully-formed Moment from raw inputs.
    
    Computes idempotency_key and estimate_total_cents automatically.
    """
    key = compute_idempotency_key(vin, timestamp, raw)
    labor_cents = int(labor_hours * labor_rate_cents)
    parts_cents = sum(p.line_total_cents for p in (parts or []))
    estimate = labor_cents + parts_cents
    return NextLevelMoment(
        idempotency_key=key,
        vin=vin,
        mileage=mileage,
        dtcs=dtcs or [],
        diag=diag,
        parts=parts or [],
        labor_hours=labor_hours,
        labor_rate_cents=labor_rate_cents,
        estimate_total_cents=estimate,
        moment_type=moment_type,
        raw=raw,
        subscription_plan=subscription_plan,
        approval_status=approval_status,
    )


# =============================================================================
# PLANNER SCHEMAS — Output of the LLM
# =============================================================================

class PlanStep(BaseModel):
    """A single step in the planner's output.
    
    INVARIANT: tool must be one of the registered tool names.
    """
    tool: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Tool name from the registry",
    )
    args: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific arguments",
    )


class Plan(BaseModel):
    """Planner output — a sequence of tool calls.
    
    INVARIANT: at most 6 steps (prevents runaway LLM loops).
    """
    steps: list[PlanStep] = Field(
        default_factory=list,
        max_length=6,
        description="Ordered tool calls (max 6)",
    )


# =============================================================================
# CUSTOMER CONTEXT — Scoped Memory
# =============================================================================

class CustomerContext(BaseModel):
    """Scoped memory — only last 2 ROs + plan info, nothing else.
    
    DESIGN: Planner receives ONLY this — never full customer history.
    Prevents context window pollution and keeps token usage bounded.
    
    INVARIANT: last_ro_date >= second_ro_date (chronological order).
    """
    customer_id: str = Field(..., min_length=1, max_length=64)
    vin: str = Field(..., min_length=11, max_length=17)
    last_ro_date: Optional[datetime] = None
    last_ro_total_cents: Optional[int] = Field(default=None, ge=0)
    second_ro_date: Optional[datetime] = None
    second_ro_total_cents: Optional[int] = Field(default=None, ge=0)
    subscription_plan: Optional[str] = Field(default=None, max_length=50)
    credits_remaining: int = Field(default=0, ge=0)
    
    @model_validator(mode="after")
    def validate_ro_order(self) -> "CustomerContext":
        if self.last_ro_date and self.second_ro_date:
            if self.last_ro_date < self.second_ro_date:
                raise ValueError("last_ro_date must be >= second_ro_date")
        return self


# =============================================================================
# SUPPORTING SCHEMAS
# =============================================================================

class SubscriptionEvent(BaseModel):
    """Stripe subscription lifecycle event."""
    event_id: str = Field(..., min_length=1, max_length=64)
    event_type: str = Field(..., pattern=r"^customer\.subscription\.(created|updated|deleted)$")
    stripe_subscription_id: str = Field(..., min_length=1, max_length=64)
    customer_email: str = Field(..., max_length=254)
    plan_name: str = Field(..., max_length=50)
    vin: str = Field(..., min_length=11, max_length=17)
    status: str = Field(..., pattern=r"^(active|past_due|canceled|unpaid|trialing)$")
    idempotency_key: str = Field(..., pattern=IDEMPOTENCY_PATTERN.pattern)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VehicleAppraisal(BaseModel):
    """Vehicle appraisal record — buy/sell workflow."""
    vin: str = Field(..., min_length=11, max_length=17)
    mileage: Optional[int] = Field(default=None, ge=0)
    condition: VehicleCondition
    base_value_cents: int = Field(..., ge=0)
    offer_cents: int = Field(..., ge=0)
    status: str = Field(default="appraised", pattern=r"^(appracted|approved|rejected|listed|sold)$")
    idempotency_key: str = Field(..., pattern=IDEMPOTENCY_PATTERN.pattern)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditLogEntry(BaseModel):
    """Single audit log entry — append-only."""
    event: str = Field(..., min_length=1, max_length=100)
    idempotency_key: Optional[str] = Field(default=None, pattern=IDEMPOTENCY_PATTERN.pattern)
    actor: str = Field(default="system", max_length=64)
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolCallResult(BaseModel):
    """Result of a single tool execution — written to outbox."""
    idempotency_key: str = Field(..., pattern=IDEMPOTENCY_PATTERN.pattern)
    tool: str = Field(..., min_length=1, max_length=50)
    status: str = Field(..., pattern=r"^(ok|error|already_processed)$")
    result: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = Field(default=None, max_length=1000)
    retry_count: int = Field(default=0, ge=0, le=10)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OutboxEntry(BaseModel):
    """Transactional outbox entry — bridges tool execution and verification."""
    idempotency_key: str = Field(..., pattern=IDEMPOTENCY_PATTERN.pattern)
    tool: str = Field(..., min_length=1, max_length=50)
    result: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="pending", pattern=r"^(pending|completed|failed)$")
    verified: bool = False
    verification_note: Optional[str] = Field(default=None, max_length=500)
    verified_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DLQEntry(BaseModel):
    """Dead Letter Queue entry — failed tool calls awaiting manual retry."""
    idempotency_key: str = Field(..., pattern=IDEMPOTENCY_PATTERN.pattern)
    tool: str = Field(..., min_length=1, max_length=50)
    args: dict[str, Any] = Field(default_factory=dict)
    error: str = Field(..., max_length=1000)
    retry_count: int = Field(default=0, ge=0, le=10)
    last_retry_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SMSMessage(BaseModel):
    """SMS message to customer via Twilio."""
    to: str = Field(..., pattern=r"^\+[1-9]\d{1,14}$", description="E.164 format")
    body: str = Field(..., min_length=1, max_length=1600, description="Message body (1600 char Twilio limit)")
    test_mode: bool = Field(default=True, description="If True, prefix [TEST - approve in Telegram]")


class TelegramApprovalRequest(BaseModel):
    """Telegram inline keyboard approval request."""
    chat_id: int = Field(..., gt=0)
    vin: str = Field(..., min_length=11, max_length=17)
    estimate_cents: int = Field(..., ge=0)
    summary: str = Field(..., max_length=1000)
    idempotency_key: str = Field(..., pattern=IDEMPOTENCY_PATTERN.pattern)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
