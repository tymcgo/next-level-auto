"""Tests for core schemas and discovery."""
import pytest
from src.schemas import (
    NextLevelMoment,
    PartLine,
    compute_idempotency_key,
    moment_from_raw,
)
from src.discovery import parse_ro_csv, build_moment_inventory, _infer_moment_type


def test_idempotency_key_deterministic():
    k1 = compute_idempotency_key("WBA3A5C55CF2", "2024-01-01T00:00:00", "raw text")
    k2 = compute_idempotency_key("WBA3A5C55CF2", "2024-01-01T00:00:00", "raw text")
    assert k1 == k2
    assert len(k1) == 68  # sha256 hex


def test_idempotency_key_unique():
    k1 = compute_idempotency_key("WBA3A5C55CF2", "2024-01-01T00:00:00", "raw text")
    k2 = compute_idempotency_key("WBA3A5C55CF2", "2024-01-01T00:00:01", "raw text")
    assert k1 != k2


def test_moment_from_raw():
    m = moment_from_raw(
        vin="WBA3A5C55CF2",
        timestamp="2024-01-01T00:00:00",
        raw="test",
        labor_hours=2.0,
        labor_rate_cents=15000,
        parts=[PartLine(part_number="PAD1", description="Brake Pads", quantity=1, unit_cost_cents=8000)],
    )
    assert m.vin == "WBA3A5C55CF2"
    assert m.estimate_total_cents == 2 * 15000 + 8000  # 38000
    assert m.idempotency_key == compute_idempotency_key("WBA3A5C55CF2", "2024-01-01T00:00:00", "test")


def test_infer_moment_type():
    assert _infer_moment_type("check engine light on", "scan DTCs") == "diagnosis"
    assert _infer_moment_type("oil change", "scheduled maintenance") == "maintenance"
    assert _infer_moment_type("buy my car", "appraisal") == "vehicle_appraisal"
    assert _infer_moment_type("list my vehicle", "consignment") == "vehicle_listing"
    assert _infer_moment_type("care plan signup", "subscription") == "subscription_signup"


def test_parse_csv(tmp_path):
    csv_content = """date,customer,vin,concern,diag,total,mileage
2024-01-01,John,WBA3A5C55CF2,check engine light,scan DTCs,450.00,65000
2024-01-02,Jane,1HGBH41JXMN109186,oil change,scheduled maintenance,89.99,30000"""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(csv_content)
    moments = parse_ro_csv(csv_path)
    assert len(moments) == 2
    assert moments[0].vin == "WBA3A5C55CF2"
    assert moments[0].estimate_total_cents == 45000
    assert moments[1].estimate_total_cents == 8999


def test_build_inventory():
    moments = [
        moment_from_raw(vin="WBA3A5C55CF2", timestamp="2024-01-01", raw="r1", labor_hours=1, labor_rate_cents=10000),
        moment_from_raw(vin="1HGBH41JXMN109186", timestamp="2024-01-02", raw="r2", labor_hours=2, labor_rate_cents=10000),
    ]
    inv = build_moment_inventory(moments)
    assert inv["total_moments"] == 2
    assert inv["vin_count"] == 2
    assert "inferred_labor_rate_cents" in inv
