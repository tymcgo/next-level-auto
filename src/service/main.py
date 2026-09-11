"""FastAPI Python service — exposes the agentic pipeline to the Cloudflare Worker.

Endpoints:
- POST /plan    → PlannerAgent.plan() returns Plan
- POST /execute → ToolRegistry.execute() runs each step
- POST /govern  → GovernanceEngine + NotificationRouter handle approval flows
- POST /process → Full pipeline: plan → govern → (execute or request approval)
"""
from __future__ import annotations

import os
import sys
from typing import Any

# Ensure src is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from src.schemas import CustomerContext, NextLevelMoment, Plan, PlanStep
from src.agent import PlannerAgent
from src.tools import build_default_registry, sanitize_input
from src.governance import GovernanceEngine, NotificationRouter, SLAMonitor

app = FastAPI(title="Next Level Auto — Agentic Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Initialize components ----------
planner = PlannerAgent(
    llm_base=os.environ.get("LLM_API_BASE", "https://openrouter.ai/api/v1"),
    llm_key=os.environ.get("LLM_API_KEY", ""),
    model=os.environ.get("LLM_MODEL", "openai/gpt-4o-mini"),
    config_path=os.environ.get("CONFIG_PATH", "config/config.yaml"),
)

registry = build_default_registry()

governance = GovernanceEngine(
    config_path=os.environ.get("CONFIG_PATH", "config/config.yaml"),
    policies_path=os.environ.get("POLICIES_PATH", "config/policies.yaml"),
)

# Telegram bot token for sending approval requests
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_CHAT_ID = int(os.environ.get("TELEGRAM_OWNER_CHAT_ID", "0"))

notifier = NotificationRouter(
    bot_token=TELEGRAM_BOT_TOKEN,
    owner_chat_id=TELEGRAM_OWNER_CHAT_ID,
    digest_chat_id=TELEGRAM_OWNER_CHAT_ID,
)

sla_monitor = SLAMonitor(
    sla_seconds=governance.sla_seconds(),
    escalation_sms=governance.policies.get("approval", {}).get("escalation_sms", True),
)


# ---------- Request/Response models ----------
class MomentRequest(BaseModel):
    idempotency_key: str
    vin: str
    mileage: int | None = None
    dtcs: list[str] = []
    diag: str | None = None
    parts: list[dict[str, Any]] = []
    labor_hours: float = 0.0
    labor_rate_cents: int = 0
    estimate_total_cents: int = 0
    moment_type: str = "diagnosis"
    raw: str | None = None
    subscription_plan: str | None = None


class PlanRequest(BaseModel):
    moment: MomentRequest
    context: dict[str, Any]


class ExecuteRequest(BaseModel):
    plan: dict[str, Any]
    env: dict[str, str] = {}


class GovernRequest(BaseModel):
    moment: MomentRequest
    threshold_cents: int = 50000


class ProcessRequest(BaseModel):
    moment: MomentRequest
    context: dict[str, Any]
    threshold_cents: int = 50000


# ---------- Helpers ----------
def _to_next_level_moment(req: MomentRequest) -> NextLevelMoment:
    return NextLevelMoment(
        idempotency_key=req.idempotency_key,
        vin=req.vin,
        mileage=req.mileage,
        dtcs=req.dtcs,
        diag=req.diag,
        parts=req.parts,  # type: ignore
        labor_hours=req.labor_hours,
        labor_rate_cents=req.labor_rate_cents,
        estimate_total_cents=req.estimate_total_cents,
        moment_type=MomentType(req.moment_type),
        raw=req.raw,
        subscription_plan=req.subscription_plan,
    )


# ---------- Endpoints ----------
@app.get("/health")
async def health():
    return {"status": "ok", "service": "nla-agentic-service"}


@app.post("/plan")
async def plan(req: PlanRequest):
    """Get a plan from the Planner agent."""
    try:
        moment = _to_next_level_moment(req.moment)
        context = CustomerContext(**req.context) if req.context else CustomerContext(customer_id="unknown", vin=req.moment.vin)
        plan = await planner.plan(moment, context)
        return plan.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plan failed: {str(e)}")


@app.post("/execute")
async def execute(req: ExecuteRequest):
    """Execute a plan by running each tool step."""
    try:
        results = []
        for step in req.plan.get("steps", []):
            tool_name = step.get("tool", "")
            tool_args = step.get("args", {})
            idempotency_key = tool_args.pop("_idempotency_key", f"exec-{tool_name}-{id(step)}")
            # Sanitize args
            for k, v in tool_args.items():
                if isinstance(v, str):
                    tool_args[k] = sanitize_input(v)
            try:
                result = await registry.execute(
                    name=tool_name,
                    args=tool_args,
                    env_keys=[],  # Worker provides env via req.env
                    idempotency_key=idempotency_key,
                )
                results.append({"tool": tool_name, "status": "ok", "result": result})
            except Exception as e:
                results.append({"tool": tool_name, "status": "error", "error": str(e)})
        return {"status": "ok", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execute failed: {str(e)}")


@app.post("/govern")
async def govern(req: GovernRequest):
    """Check if moment requires approval and send Telegram request if needed."""
    try:
        moment = _to_next_level_moment(req.moment)
        needs_approval = governance.requires_approval(moment.estimate_total_cents)
        
        result = {
            "needs_approval": needs_approval,
            "estimate_cents": moment.estimate_total_cents,
            "threshold_cents": req.threshold_cents,
            "vin": moment.vin,
            "summary": moment.diag or moment.moment_type,
        }
        
        if needs_approval and TELEGRAM_BOT_TOKEN:
            await notifier.send_approval_request(
                estimate_cents=moment.estimate_total_cents,
                vin=moment.vin,
                summary=moment.diag or "",
            )
            sla_monitor.track(moment.idempotency_key)
            result["approval_sent"] = True
        else:
            result["approval_sent"] = False
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Govern failed: {str(e)}")


@app.post("/process")
async def process(req: ProcessRequest):
    """Full pipeline: plan → govern → return result."""
    try:
        moment = _to_next_level_moment(req.moment)
        context = CustomerContext(**req.context) if req.context else CustomerContext(customer_id="unknown", vin=req.moment.vin)
        
        # 1. Plan
        plan = await planner.plan(moment, context)
        
        # 2. Govern
        needs_approval = governance.requires_approval(moment.estimate_total_cents)
        
        if needs_approval:
            # Send approval request via Telegram
            if TELEGRAM_BOT_TOKEN:
                await notifier.send_approval_request(
                    estimate_cents=moment.estimate_total_cents,
                    vin=moment.vin,
                    summary=moment.diag or "",
                )
                sla_monitor.track(moment.idempotency_key)
            return {
                "status": "needs_approval",
                "plan": plan.model_dump(),
                "governance": {
                    "needs_approval": True,
                    "estimate_cents": moment.estimate_total_cents,
                    "threshold_cents": req.threshold_cents,
                    "vin": moment.vin,
                    "summary": moment.diag or "",
                    "approval_sent": True,
                },
            }
        
        # 3. No approval needed — return plan for Worker to execute
        return {
            "status": "ok",
            "plan": plan.model_dump(),
            "governance": {
                "needs_approval": False,
                "estimate_cents": moment.estimate_total_cents,
                "threshold_cents": req.threshold_cents,
                "vin": moment.vin,
                "summary": moment.diag or "",
                "approval_sent": False,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Process failed: {str(e)}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
