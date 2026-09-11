"""PlanSchema — structured output for Planner Agent. Max 1200 tokens."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PlanAction(str, Enum):
    DECODE_VIN = "decode_vin"
    CREATE_RO = "create_ro"
    CREATE_ESTIMATE = "create_estimate"
    SEND_SMS = "send_sms"
    ORDER_PARTS = "order_parts"
    CREATE_STRIPE_SUBSCRIPTION = "create_stripe_subscription"
    LIST_VEHICLE_FOR_SALE = "list_vehicle_for_sale"
    AUDIT_LOG = "audit_log"


class EstimateLineItem(BaseModel):
    description: str = Field(max_length=100)
    labor_hours: float = Field(ge=0, le=100)
    parts_cost: float = Field(ge=0)
    part_number: Optional[str] = None
    quantity: int = Field(default=1, ge=1)


class PlanStep(BaseModel):
    tool: PlanAction
    params: dict = Field(default_factory=dict)
    description: Optional[str] = Field(default=None, max_length=200)


class PlanSchema(BaseModel):
    """Planner Agent output — must be valid JSON within 1200 tokens."""

    customer_summary: str = Field(max_length=300)
    vehicle_summary: Optional[str] = Field(default=None, max_length=200)
    diagnosis: Optional[str] = Field(default=None, max_length=500)
    steps: list[PlanStep] = Field(default_factory=list)
    requires_approval: bool = False
    approval_reason: Optional[str] = Field(default=None, max_length=100)
    total_estimate: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=300)

    class Config:
        json_schema_extra = {
            "example": {
                "customer_summary": "2018 Ford F-150, 120K km, regular customer",
                "diagnosis": "Brake pads worn, rotors scored",
                "steps": [
                    {"tool": "create_estimate", "params": {"labor_hours": 2.5, "parts": ["brake_pads", "rotors"]}},
                    {"tool": "order_parts", "params": {"supplier": "NAPA", "parts": ["BP-F150-2018", "ROT-F150-2018"]}}
                ],
                "requires_approval": True,
                "approval_reason": "Total $850 exceeds $750 threshold",
                "total_estimate": 850.00
            }
        }
