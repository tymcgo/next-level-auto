"""Simulation runner — replay last N ROs through the pipeline and generate report."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from src.discovery import parse_ro_csv, write_moment_inventory
from src.schemas import CustomerContext, NextLevelMoment
from src.agent import PlannerAgent
from src.tools import build_default_registry, sanitize_input


class Simulator:
    """Replay ROs through planner + executor, measure outcomes."""

    def __init__(self, config_path: str, llm_base: str, llm_key: str, model: str):
        self.planner = PlannerAgent(llm_base, llm_key, model, config_path)
        self.registry = build_default_registry()
        self.results: list[dict[str, Any]] = []

    async def replay(self, moments: list[NextLevelMoment], max_count: int = 20) -> dict[str, Any]:
        """Replay moments, return report."""
        subset = moments[-max_count:]
        total_tokens = 0
        total_cost_cents = 0
        start_time = time.time()

        for moment in subset:
            ctx = CustomerContext(customer_id="sim", vin=moment.vin)
            try:
                plan = await self.planner.plan(moment, ctx)
                # Count tokens (rough: 1 token per 4 chars)
                total_tokens += len(json.dumps(plan.model_dump())) // 4
                for step in plan.steps:
                    # Execute tool (mock — don't actually call external APIs in sim)
                    result = {"tool": step.tool, "mock": True}
                    self.results.append({"moment_id": moment.idempotency_key, "tool": step.tool, "result": result})
            except Exception as e:
                self.results.append({"moment_id": moment.idempotency_key, "error": str(e)})

        elapsed = time.time() - start_time
        # Cost: ~$0.0002 per 1K tokens for gpt-4o-mini
        total_cost_cents = (total_tokens / 1000) * 0.02

        return {
            "moments_replayed": len(subset),
            "total_tokens": total_tokens,
            "estimated_cost_cents": round(total_cost_cents, 2),
            "elapsed_seconds": round(elapsed, 2),
            "tokens_per_ro": round(total_tokens / len(subset), 1) if subset else 0,
            "errors": len([r for r in self.results if "error" in r]),
        }


async def run_simulation(csv_path: str, config_path: str, out_path: str) -> dict[str, Any]:
    """Full simulation pipeline."""
    moments = parse_ro_csv(csv_path)
    inventory = write_moment_inventory(moments, out_path.replace(".json", "_inventory.json"))

    sim = Simulator(
        config_path=config_path,
        llm_base="http://localhost:4000/v1",
        llm_key="sk-sim",
        model="gpt-4o-mini",
    )
    report = await sim.replay(moments, max_count=20)
    report["inventory"] = inventory

    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    return report


if __name__ == "__main__":
    import sys
    csv = sys.argv[1] if len(sys.argv) > 1 else "ro_history.csv"
    out = sys.argv[2] if len(sys.argv) > 2 else "simulation_report.json"
    report = asyncio.run(run_simulation(csv, "config/config.yaml", out))
    print(json.dumps(report, indent=2))
