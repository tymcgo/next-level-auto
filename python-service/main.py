"""main.py — FastAPI service for Next Level Auto.
Three endpoints: /plan, /execute, /govern
Reuses Pydantic schemas from src/models/"""
import os
from contextlib import asynccontextmanager

import httpx
import structlog
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from starlette.middleware.cors import CORSMiddleware

from src.agent.planner import PlannerAgent
from src.governance.governance_engine import GovernanceEngine
from src.tools.tool_registry import ToolRegistry

load_dotenv()

logger = structlog.get_logger()

# =============================================================================
# App lifespan — load config, init clients
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load config
    with open("config.yaml") as f:
        app.state.config = yaml.safe_load(f)

    # HTTP client for external calls (Supabase, OpenRouter, etc.)
    app.state.http = httpx.AsyncClient(timeout=30.0)

    # Init components
    app.state.planner = PlannerAgent(app.state.config, app.state.http)
    app.state.tools = ToolRegistry(app.state.config, app.state.http)
    app.state.governance = GovernanceEngine(app.state.config, app.state.http)

    logger.info("service_started", config_loaded=True)
    yield
    await app.state.http.aclose()
    logger.info("service_stopped")

app = FastAPI(title="Next Level Auto Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Health check
# =============================================================================
@app.get("/health")
async def health():
    return {"status": "ok", "service": "nla-agent"}

# =============================================================================
# /plan — Generate a plan from an event
# =============================================================================
class PlanRequest:
    event: dict  # NextLevelEvent as dict
    customer_summary: str = ""
    recent_ros: list = []

@app.post("/plan")
async def plan(req: dict):
    """Given an event + context, return a PlanSchema JSON."""
    try:
        config = app.state.config
        planner: PlannerAgent = app.state.planner

        event = req.get("event", {})
        customer_summary = req.get("customer_summary", "")
        recent_ros = req.get("recent_ros", [])

        plan = await planner.generate(event, customer_summary, recent_ros)
        logger.info("plan_generated", event_type=event.get("event_type"))
        return {"success": True, "plan": plan}
    except Exception as e:
        logger.error("plan_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# /execute — Execute a plan step
# =============================================================================
@app.post("/execute")
async def execute(req: dict):
    """Execute a single tool step from a plan."""
    try:
        tool_name = req.get("tool")
        params = req.get("params", {})
        context = req.get("context", {})  # idempotency_key, correlation_id, actor_id

        if not tool_name:
            raise HTTPException(status_code=400, detail="Missing 'tool' field")

        tools: ToolRegistry = app.state.tools
        result = await tools.invoke(tool_name, params, context)

        logger.info("tool_executed", tool=tool_name, success=result.get("success"))
        return result
    except Exception as e:
        logger.error("execute_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# /govern — Governance: approval routing, notifications, SLA tracking
# =============================================================================
@app.post("/govern")
async def govern(req: dict):
    """Route approval/notification through governance engine."""
    try:
        action = req.get("action")  # "request_approval", "check_sla", "escalate"
        data = req.get("data", {})

        if not action:
            raise HTTPException(status_code=400, detail="Missing 'action' field")

        governance: GovernanceEngine = app.state.governance
        result = await governance.handle(action, data)

        logger.info("governance_handled", action=action)
        return result
    except Exception as e:
        logger.error("govern_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# Run: uvicorn main:app --host 0.0.0.0 --port 8000
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
