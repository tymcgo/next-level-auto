"""Comprehensive tests for perfected schemas — every field, constraint, and validator."""
import pytest
from pydantic import ValidationError

from src.schemas import (
    NextLevelMoment,
    PartLine,
    Money,
    Plan,
    PlanStep,
    CustomerContext,
    SubscriptionEvent,
    VehicleAppraisal,
    AuditLogEntry,
    OutboxEntry,
    DLQEntry,
    SMSMessage,
    TelegramApprovalRequest,
    MomentType,
    ApprovalStatus,
    VehicleCondition,
    compute_idempotency_key,
    moment_from_raw,
)


# =============================================================================
# MONEY
# =============================================================================

class TestMoney:
    def test_positive_amount(self):
        m = Money(cents=15000)
        assert m.dollars == 150.0
    
    def test_zero_amount(self):
        m = Money(cents=0)
        assert m.dollars == 0.0
    
    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            Money(cents=-1)
    
    def test_addition(self):
        m1 = Money(cents=100)
        m2 = Money(cents=200)
        assert (m1 + m2).cents == 300
    
    def test_multiplication(self):
        m = Money(cents=100)
        assert (m * 3).cents == 300
        assert (m * 1.5).cents == 150


# =============================================================================
# PART LINE
# =============================================================================

class TestPartLine:
    def test_valid_part(self):
        p = PartLine(part_number="PAD-001", description="Brake Pads", quantity=2, unit_cost_cents=8000)
        assert p.line_total_cents == 16000
    
    def test_default_quantity(self):
        p = PartLine(part_number="PAD001", description="Pads")
        assert p.quantity == 1
    
    def test_part_number_uppercased(self):
        p = PartLine(part_number="pad-001", description="Pads")
        assert p.part_number == "PAD-001"
    
    def test_invalid_part_number_too_short(self):
        with pytest.raises(ValidationError):
            PartLine(part_number="P", description="Pads")
    
    def test_invalid_part_number_special_chars(self):
        with pytest.raises(ValidationError):
            PartLine(part_number="PAD@001", description="Pads")
    
    def test_negative_cost_rejected(self):
        with pytest.raises(ValidationError):
            PartLine(part_number="PAD001", description="Pads", unit_cost_cents=-1)
    
    def test_quantity_too_high(self):
        with pytest.raises(ValidationError):
            PartLine(part_number="PAD001", description="Pads", quantity=101)


# =============================================================================
# IDEMPOTENCY KEY
# =============================================================================

class TestIdempotencyKey:
    def test_deterministic(self):
        k1 = compute_idempotency_key("WBA3A5C55CF2", "2024-01-01T00:00:00", "raw")
        k2 = compute_idempotency_key("WBA3A5C55CF2", "2024-01-01T00:00:00", "raw")
        assert k1 == k2
    
    def test_unique_per_input(self):
        k1 = compute_idempotency_key("WBA3A5C55CF2", "2024-01-01T00:00:00", "raw1")
        k2 = compute_idempotency_key("WBA3A5C55CF2", "2024-01-01T00:00:01", "raw2")
        assert k1 != k2
    
    def test_mom_prefix(self):
        k = compute_idempotency_key("WBA3A5C55CF2", "ts", "raw")
        assert k.startswith("mom_")
    
    def test_sha256_length(self):
        k = compute_idempotency_key("WBA3A5C55CF2", "ts", "raw")
        assert len(k) == 68  # "mom_" + 64 hex chars
    
    def test_collision_resistance(self):
        """Ensure separator prevents concatenation collisions."""
        k1 = compute_idempotency_key("ABC", "12", "3")
        k2 = compute_idempotency_key("AB", "C12", "3")
        k3 = compute_idempotency_key("A", "BC12", "3")
        assert len({k1, k2, k3}) == 3


# =============================================================================
# VIN VALIDATION
# =============================================================================

class TestVinValidation:
    def test_valid_11_char_vin(self):
        # 11-char VINs skip ISO 3779 check digit validation
        m = moment_from_raw(vin="WBA3A5C55CF2", timestamp="2024-01-01", raw="test")
        assert m.vin == "WBA3A5C55CF2"

    def test_vin_check_digit_warning_not_rejection(self):
        """17-char VIN with invalid check digit should be allowed through with warning."""
        m = moment_from_raw(vin="5YJSA1DG5DFP12345", timestamp="2024-01-01", raw="test")
        assert m.vin == "5YJSA1DG5DFP12345"
    
    def test_vin_uppercased(self):
        m = moment_from_raw(vin="wba3a5c55cf2", timestamp="2024-01-01", raw="test")
        assert m.vin == "WBA3A5C55CF2"

    def test_vin_stripped(self):
        m = moment_from_raw(vin=" WBA3A5C55CF2 ", timestamp="2024-01-01", raw="test")
        assert m.vin == "WBA3A5C55CF2"

    def test_vin_with_i_rejected(self):
        with pytest.raises(ValidationError):
            moment_from_raw(vin="WBA3A5C5ICF2", timestamp="2024-01-01", raw="test")

    def test_vin_with_o_rejected(self):
        with pytest.raises(ValidationError):
            moment_from_raw(vin="WBA3A5C5OCF2", timestamp="2024-01-01", raw="test")

    def test_vin_with_q_rejected(self):
        with pytest.raises(ValidationError):
            moment_from_raw(vin="WBA3A5C5QCF2", timestamp="2024-01-01", raw="test")

    def test_vin_too_short(self):
        with pytest.raises(ValidationError):
            moment_from_raw(vin="WBA3A5C55C", timestamp="2024-01-01", raw="test")

    def test_vin_too_long(self):
        with pytest.raises(ValidationError):
            moment_from_raw(vin="WBA3A5C55CF2012345", timestamp="2024-01-01", raw="test")


# =============================================================================
# DTC VALIDATION
# =============================================================================

class TestDtcValidation:
    def test_valid_dtc(self):
        m = moment_from_raw(vin="WBA3A5C55CF2", timestamp="2024-01-01", raw="test", dtcs=["P0300", "P0420"])
        assert m.dtcs == ["P0300", "P0420"]
    
    def test_dtc_uppercased(self):
        m = moment_from_raw(vin="WBA3A5C55CF2", timestamp="2024-01-01", raw="test", dtcs=["p0300"])
        assert m.dtcs == ["P0300"]
    
    def test_dtc_stripped(self):
        m = moment_from_raw(vin="WBA3A5C55CF2", timestamp="2024-01-01", raw="test", dtcs=[" P0300 "])
        assert m.dtcs == ["P0300"]
    
    def test_invalid_dtc_prefix(self):
        with pytest.raises(ValidationError):
            moment_from_raw(vin="WBA3A5C55CF2", timestamp="2024-01-01", raw="test", dtcs=["X0300"])
    
    def test_invalid_dtc_length(self):
        with pytest.raises(ValidationError):
            moment_from_raw(vin="WBA3A5C55CF2", timestamp="2024-01-01", raw="test", dtcs=["P030"])
    
    def test_too_many_dtcs(self):
        with pytest.raises(ValidationError):
            moment_from_raw(vin="WBA3A5C55CF2", timestamp="2024-01-01", raw="test", dtcs=[f"P{i:04d}" for i in range(51)])


# =============================================================================
# ESTIMATE TOTAL VALIDATION
# =============================================================================

class TestEstimateTotal:
    def test_correct_total_auto_computed(self):
        m = moment_from_raw(
            vin="WBA3A5C55CF2",
            timestamp="2024-01-01",
            raw="test",
            labor_hours=2.0,
            labor_rate_cents=15000,
            parts=[PartLine(part_number="PAD001", description="Pads", quantity=1, unit_cost_cents=8000)],
        )
        # 2.0 * 15000 + 8000 = 38000
        assert m.estimate_total_cents == 38000
    
    def test_mismatch_too_large_rejected(self):
        """If estimate differs from computed by >50%, reject."""
        with pytest.raises(ValidationError):
            NextLevelMoment(
                idempotency_key=compute_idempotency_key("WBA3A5C55CF2", "ts", "raw"),
                vin="WBA3A5C55CF2",
                labor_hours=1.0,
                labor_rate_cents=10000,
                estimate_total_cents=500000,  # Way off from 10000
            )


# =============================================================================
# MOMENT TYPE
# =============================================================================

class TestMomentType:
    def test_all_types_valid(self):
        for t in MomentType:
            m = moment_from_raw(vin="WBA3A5C55CF2", timestamp="2024-01-01", raw="test", moment_type=t)
            assert m.moment_type == t
    
    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            moment_from_raw(vin="WBA3A5C55CF2", timestamp="2024-01-01", raw="test", moment_type="invalid")


# =============================================================================
# APPROVAL STATUS
# =============================================================================

class TestApprovalStatus:
    def test_default_pending(self):
        m = moment_from_raw(vin="WBA3A5C55CF2", timestamp="2024-01-01", raw="test")
        assert m.approval_status == ApprovalStatus.pending
    
    def test_all_statuses_valid(self):
        for s in ApprovalStatus:
            m = moment_from_raw(vin="WBA3A5C55CF2", timestamp="2024-01-01", raw="test", approval_status=s)
            assert m.approval_status == s


# =============================================================================
# CUSTOMER CONTEXT
# =============================================================================

class TestCustomerContext:
    def test_valid_context(self):
        from datetime import datetime
        ctx = CustomerContext(
            customer_id="cust_123",
            vin="WBA3A5C55CF2",
            last_ro_date=datetime(2024, 1, 1),
            last_ro_total_cents=45000,
            second_ro_date=datetime(2023, 12, 1),
            second_ro_total_cents=30000,
        )
        assert ctx.customer_id == "cust_123"
    
    def test_ro_order_validated(self):
        from datetime import datetime
        with pytest.raises(ValidationError):
            CustomerContext(
                customer_id="cust_123",
                vin="WBA3A5C55CF2",
                last_ro_date=datetime(2023, 1, 1),  # Earlier than second
                second_ro_date=datetime(2024, 1, 1),
            )


# =============================================================================
# SUBSCRIPTION EVENT
# =============================================================================

class TestSubscriptionEvent:
    def test_valid_event(self):
        e = SubscriptionEvent(
            event_id="evt_123",
            event_type="customer.subscription.created",
            stripe_subscription_id="sub_123",
            customer_email="test@example.com",
            plan_name="BASIC",
            vin="WBA3A5C55CF2",
            status="active",
            idempotency_key=compute_idempotency_key("WBA3A5C55CF2", "ts", "raw"),
        )
        assert e.event_type == "customer.subscription.created"
    
    def test_invalid_event_type(self):
        with pytest.raises(ValidationError):
            SubscriptionEvent(
                event_id="evt_123",
                event_type="invalid.event",
                stripe_subscription_id="sub_123",
                customer_email="test@example.com",
                plan_name="BASIC",
                vin="WBA3A5C55CF2",
                status="active",
                idempotency_key=compute_idempotency_key("WBA3A5C55CF2", "ts", "raw"),
            )
    
    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            SubscriptionEvent(
                event_id="evt_123",
                event_type="customer.subscription.created",
                stripe_subscription_id="sub_123",
                customer_email="test@example.com",
                plan_name="BASIC",
                vin="WBA3A5C55CF2",
                status="invalid",
                idempotency_key=compute_idempotency_key("WBA3A5C55CF2", "ts", "raw"),
            )


# =============================================================================
# VEHICLE APPRAISAL
# =============================================================================

class TestVehicleAppraisal:
    def test_valid_appraisal(self):
        a = VehicleAppraisal(
            vin="WBA3A5C55CF2",
            mileage=65000,
            condition=VehicleCondition.good,
            base_value_cents=2500000,
            offer_cents=2125000,
            idempotency_key=compute_idempotency_key("WBA3A5C55CF2", "ts", "raw"),
        )
        assert a.condition == VehicleCondition.good
    
    def test_invalid_condition(self):
        with pytest.raises(ValidationError):
            VehicleAppraisal(
                vin="WBA3A5C55CF2",
                mileage=65000,
                condition="amazing",  # Not in enum
                base_value_cents=2500000,
                offer_cents=2125000,
                idempotency_key=compute_idempotency_key("WBA3A5C55CF2", "ts", "raw"),
            )


# =============================================================================
# OUTBOX ENTRY
# =============================================================================

class TestOutboxEntry:
    def test_default_pending(self):
        e = OutboxEntry(
            idempotency_key=compute_idempotency_key("WBA3A5C55CF2", "ts", "raw"),
            tool="create_ro",
        )
        assert e.status == "pending"
        assert e.verified is False
    
    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            OutboxEntry(
                idempotency_key=compute_idempotency_key("WBA3A5C55CF2", "ts", "raw"),
                tool="create_ro",
                status="unknown",
            )


# =============================================================================
# DLQ ENTRY
# =============================================================================

class TestDLQEntry:
    def test_default_retry_count(self):
        e = DLQEntry(
            idempotency_key=compute_idempotency_key("WBA3A5C55CF2", "ts", "raw"),
            tool="create_ro",
            error="timeout",
        )
        assert e.retry_count == 0
    
    def test_retry_count_capped(self):
        with pytest.raises(ValidationError):
            DLQEntry(
                idempotency_key=compute_idempotency_key("WBA3A5C55CF2", "ts", "raw"),
                tool="create_ro",
                error="timeout",
                retry_count=11,
            )


# =============================================================================
# SMS MESSAGE
# =============================================================================

class TestSMSMessage:
    def test_valid_e164(self):
        m = SMSMessage(to="+14155552671", body="Your estimate is ready")
        assert m.to == "+14155552671"
    
    def test_invalid_phone_format(self):
        with pytest.raises(ValidationError):
            SMSMessage(to="4155552671", body="test")  # Missing +
    
    def test_body_too_long(self):
        with pytest.raises(ValidationError):
            SMSMessage(to="+14155552671", body="A" * 1601)


# =============================================================================
# TELEGRAM APPROVAL REQUEST
# =============================================================================

class TestTelegramApprovalRequest:
    def test_valid_request(self):
        r = TelegramApprovalRequest(
            chat_id=123456789,
            vin="WBA3A5C55CF2",
            estimate_cents=50000,
            summary="Brake service",
            idempotency_key=compute_idempotency_key("WBA3A5C55CF2", "ts", "raw"),
        )
        assert r.chat_id == 123456789
    
    def test_invalid_chat_id(self):
        with pytest.raises(ValidationError):
            TelegramApprovalRequest(
                chat_id=-1,
                vin="WBA3A5C55CF2",
                estimate_cents=50000,
                summary="Test",
                idempotency_key=compute_idempotency_key("WBA3A5C55CF2", "ts", "raw"),
            )


# =============================================================================
# PLAN / PLAN STEP
# =============================================================================

class TestPlan:
    def test_max_6_steps(self):
        with pytest.raises(ValidationError):
            Plan(steps=[PlanStep(name=f"step_{i}") for i in range(7)])


# =============================================================================
# RAW TRUNCATION
# =============================================================================

class TestRawTruncation:
    def test_raw_capped(self):
        with pytest.raises(ValidationError):
            moment_from_raw(
                vin="WBA3A5C55CF2",
                timestamp="2024-01-01",
                raw="A" * 10001,  # Just over 10KB cap
            )
