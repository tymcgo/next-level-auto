"""Interview: ask owner 10 questions, write answers into config.yaml."""
from __future__ import annotations

from typing import Any

import yaml


QUESTIONS = [
    {
        "key": "labor_rate",
        "question": "What is your shop's hourly labor rate? (e.g., 150 for $150/hr)",
        "type": "int",
        "target": ("labor_rate_ccents",),
        "transform": lambda v: int(v) * 100,  # dollars -> cents
    },
    {
        "key": "plan_a",
        "question": "Name your BASIC care plan (e.g., 'Essentials')",
        "type": "str",
        "target": ("plans", 0, "name"),
    },
    {
        "key": "plan_a_price",
        "question": "Monthly price for BASIC plan? (e.g., 49.99)",
        "type": "float",
        "target": ("plans", 0, "price_cents"),
        "transform": lambda v: int(float(v) * 100),
    },
    {
        "key": "plan_a_benefits",
        "question": "Benefits for BASIC plan (comma-separated, e.g., 'Oil change, Tire rotation, Inspection')",
        "type": "str",
        "target": ("plans", 0, "benefits"),
        "transform": lambda v: [b.strip() for b in v.split(",") if b.strip()],
    },
    {
        "key": "plan_b",
        "question": "Name your PLUS care plan (e.g., 'Preferred')",
        "type": "str",
        "target": ("plans", 1, "name"),
    },
    {
        "key": "plan_b_price",
        "question": "Monthly price for PLUS plan?",
        "type": "float",
        "target": ("plans", 1, "price_cents"),
        "transform": lambda v: int(float(v) * 100),
    },
    {
        "key": "plan_b_benefits",
        "question": "Benefits for PLUS plan (comma-separated)",
        "type": "str",
        "target": ("plans", 1, "benefits"),
        "transform": lambda v: [b.strip() for b in v.split(",") if b.strip()],
    },
    {
        "key": "plan_c",
        "question": "Name your PREMIUM care plan (e.g., 'VIP')",
        "type": "str",
        "target": ("plans", 2, "name"),
    },
    {
        "key": "plan_c_price",
        "question": "Monthly price for PREMIUM plan?",
        "type": "float",
        "target": ("plans", 2, "price_cents"),
        "transform": lambda v: int(float(v) * 100),
    },
    {
        "key": "plan_c_benefits",
        "question": "Benefits for PREMIUM plan (comma-separated)",
        "type": "str",
        "target": ("plans", 2, "benefits"),
        "transform": lambda v: [b.strip() for b in v.split(",") if b.strip()],
    },
    {
        "key": "parts_supplier",
        "question": "Preferred parts supplier name + email for orders",
        "type": "str",
        "target": ("parts_supplier_email",),
    },
    {
        "key": "approval_threshold",
        "question": "Estimate approval threshold in dollars — above this requires your approval (e.g., 500)",
        "type": "float",
        "target": ("approval_threshold_cents",),
        "transform": lambda v: int(float(v) * 100),
    },
    {
        "key": "sms_sender",
        "question": "SMS sender name (what customers see, e.g., 'NextLevel Auto')",
        "type": "str",
        "target": ("sms_sender_name",),
    },
]


def run_interview(answers: dict[str, Any], config_path: str) -> dict[str, Any]:
    """Given a dict of answers from the owner, update config.yaml."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Ensure plans list has 3 slots
    if "plans" not in config or not isinstance(config["plans"], list):
        config["plans"] = []
    while len(config["plans"]) < 3:
        config["plans"].append({"name": "", "price_cents": 0, "benefits": []})

    for q in QUESTIONS:
        val = answers.get(q["key"])
        if val is None:
            continue
        if "transform" in q:
            val = q["transform"](val)
        # Navigate target path
        obj = config
        for step in q["target"][:-1]:
            obj = obj[step]
        obj[q["target"][-1]] = val

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    return config


def interview_questions() -> list[dict[str, Any]]:
    """Return list of question dicts for external caller (Telegram bot, CLI)."""
    return [{"key": q["key"], "question": q["question"], "type": q["type"]} for q in QUESTIONS]
