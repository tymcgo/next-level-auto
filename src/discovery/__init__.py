"""Discovery: parse RO history CSV, infer schema, build moment inventory."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from ..schemas import (
    MomentType,
    NextLevelMoment,
    PartLine,
    compute_idempotency_key,
)


# Common DTC regex
_DTC_RE = re.compile(r"[PBCU]\d{4}", re.IGNORECASE)


def _infer_moment_type(concern: str, diag: str) -> MomentType:
    """Infer moment type from concern + diagnosis text."""
    text = f"{concern} {diag}".lower()
    if any(w in text for w in ["appraisal", "buy my", "purchase vehicle", "trade"]):
        return MomentType.vehicle_appraisal
    if any(w in text for w in ["list", "sell", "consignment", "for sale"]):
        return MomentType.vehicle_listing
    if any(w in text for w in ["care plan", "subscription", "monthly plan", "maintenance plan"]):
        return MomentType.subscription_signup
    if any(w in text for w in ["renew", "auto-renew", "recurring"]):
        return MomentType.subscription_renewal
    if any(w in text for w in ["oil change", "tire rotation", "scheduled", "maintenance"]):
        return MomentType.maintenance
    if any(w in text for w in ["estimate", "quote", "how much", "price"]):
        return MomentType.estimate
    if any(w in text for w in ["diagnose", "check", "scan", "dtc", "light on", "noise"]):
        return MomentType.diagnosis
    return MomentType.repair


def parse_ro_csv(path: str | Path) -> list[NextLevelMoment]:
    """Parse RO history CSV into canonical moments."""
    path = Path(path)
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    moments = []
    # Try to identify columns flexibly
    cols = {c.lower().strip().replace(" ", "_"): c for c in rows[0].keys()} if rows else {}

    def pick(*names: str) -> str | None:
        for n in names:
            if n in cols:
                return cols[n]
        return None

    date_col = pick("date", "ro_date", "repair_order_date", "created")
    customer_col = pick("customer", "customer_name", "name")
    vin_col = pick("vin", "vehicle_id")
    concern_col = pick("concern", "concerns", "complaint", "reason")
    diag_col = pick("diag", "diagnosis", "technician_notes", "notes")
    total_col = pick("total", "total_cents", "amount", "ro_total")
    mileage_col = pick("mileage", "miles", "odometer")
    labor_col = pick("labor_hours", "hours", "labor_hrs")
    parts_col = pick("parts", "parts_cost", "parts_total")

    for row in rows:
        raw = json.dumps(row, sort_keys=True)
        vin = row.get(vin_col, "UNKNOWN") if vin_col else "UNKNOWN"
        date = row.get(date_col, datetime.utcnow().isoformat()) if date_col else datetime.utcnow().isoformat()
        key = compute_idempotency_key(vin, date, raw)
        concern = row.get(concern_col, "") if concern_col else ""
        diag = row.get(diag_col, "") if diag_col else ""
        dtcs = _DTC_RE.findall(f"{concern} {diag}")

        # Parse total — try cents, fallback to dollars
        total_cents = 0
        if total_col:
            raw_total = row[total_col].replace("$", "").replace(",", "").strip()
            try:
                val = float(raw_total)
                # If > 1000, assume cents already; otherwise dollars
                total_cents = int(val) if val > 1000 else int(val * 100)
            except ValueError:
                total_cents = 0

        mileage = None
        if mileage_col:
            try:
                mileage = int(row[mileage_col].replace(",", ""))
            except (ValueError, TypeError):
                pass

        labor_hours = 0.0
        if labor_col:
            try:
                labor_hours = float(row[labor_col])
            except (ValueError, TypeError):
                pass

        moment_type = _infer_moment_type(concern, diag)
        moments.append(
            NextLevelMoment(
                idempotency_key=key,
                vin=vin,
                mileage=mileage,
                dtcs=dtcs,
                diag=diag or concern,
                labor_hours=labor_hours,
                estimate_total_cents=total_cents,
                moment_type=moment_type,
                raw=raw,
            )
        )
    return moments


def build_moment_inventory(moments: list[NextLevelMoment]) -> dict[str, Any]:
    """Build aggregate analytics from moment list."""
    if not moments:
        return {}

    total = len(moments)
    type_counts: Counter[str] = Counter(m.moment_type.value for m in moments)
    all_dtcs: Counter[str] = Counter()
    for m in moments:
        all_dtcs.update(m.dtcs)

    totals = [m.estimate_total_cents for m in moments if m.estimate_total_cents > 0]
    avg_total = sum(totals) // len(totals) if totals else 0

    # Infer labor rate from moments with both labor_hours and total
    labor_rates = []
    for m in moments:
        if m.labor_hours > 0 and m.estimate_total_cents > 0:
            # rough: (total - assumed_parts) / hours, assume parts = 40% of total
            labor_portion = m.estimate_total_cents * 0.6
            rate = int(labor_portion / m.labor_hours)
            if 5000 < rate < 50000:  # $50-$500/hr in cents is reasonable
                labor_rates.append(rate)
    inferred_labor_rate = sum(labor_rates) // len(labor_rates) if labor_rates else 15000  # default $150/hr

    # Infer parts margin from part lines (if any)
    margins = []
    for m in moments:
        for p in m.parts:
            if p.unit_cost_cents > 0:
                # We don't have retail cost in CSV; default margin
                margins.append(1.3)
    inferred_margin = sum(margins) / len(margins) if margins else 1.3

    return {
        "total_moments": total,
        "moments_by_type": dict(type_counts),
        "top_dtcs": dict(all_dtcs.most_common(10)),
        "avg_estimate_cents": avg_total,
        "inferred_labor_rate_cents": inferred_labor_rate,
        "inferred_parts_margin": round(inferred_margin, 2),
        "vin_count": len({m.vin for m in moments}),
    }


def write_moment_inventory(moments: list[NextLevelMoment], out_path: str) -> dict[str, Any]:
    """Build inventory and write to JSON file."""
    inv = build_moment_inventory(moments)
    with open(out_path, "w") as f:
        json.dump(inv, f, indent=2)
    return inv
