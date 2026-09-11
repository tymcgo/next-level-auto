"""Planner Agent — produces a Plan from a Moment + scoped customer context."""
from __future__ import annotations

import json
from typing import Any

import httpx
import yaml

from schemas import CustomerContext, NextLevelMoment, Plan, PlanStep

SYSTEM_PROMPT = """You are Next Level Auto estimator.
Input: a Moment (current shop event) + Customer last 2 ROs + config.yaml rules.
Output ONLY JSON matching PlanSchema: [{"tool": str, "args": {}}].
Rules:
- Each step calls one tool with its args.
- Use only tools from the tool registry.
- For estimates > threshold_cents, include a send_sms step requesting approval BEFORE any create_ro step.
- For subscription_signup, include create_stripe_subscription step.
- For vehicle_appraisal, include audit_log step with result.
- Never invent tools.
- Max 6 steps.
- Output raw JSON only, no markdown fences.
"""


class PlannerAgent:
    """Planner — pure reasoning, no side effects. Executor runs the steps."""

    def __init__(self, llm_base: str, llm_key: str, model: str, config_path: str):
        self.llm_base = llm_base
        self.llm_key = llm_key
        self.model = model
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

    def _build_user_prompt(
        self, moment: NextLevelMoment, ctx: CustomerContext
    ) -> str:
        return (
            f"Moment: {moment.model_dump_json(indent=2)}\n"
            f"CustomerContext: {ctx.model_dump_json(indent=2)}\n"
            f"Config rules: {json.dumps(self.config, indent=2)}"
        )

    async def plan(
        self, moment: NextLevelMoment, ctx: CustomerContext
    ) -> Plan:
        """Call LLM, parse Plan from JSON. Failures propagate as empty plan."""
        user_prompt = self._build_user_prompt(moment, ctx)
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(
                f"{self.llm_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.llm_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 1200,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            body = resp.json()
        raw = body["choices"][0]["message"]["content"]
        # Strip markdown fences if LLM ignores response_format
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        steps = [PlanStep(**s) for s in data.get("steps", [])]
        return Plan(steps=steps)
