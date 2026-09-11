# Plan — Next Level Auto (Custom Agentic Tekmetric)
Updated: 2026-08-25

## Goal
Build a fully agentic shop management system that replaces Tekmetric for Next Level Auto: auto repair shop handling diagnosis, maintenance, repair, buy/sell vehicles, online premium service contracts, and custom maintenance package builders. Kill all 29 failure modes.

## Architecture
**Cloud-native, zero local compute.** ThinkPad W540 only needs a browser.
- Telegram → Cloudflare Worker (serverless) → OpenRouter free LLM → Supabase Cloud (free tier) → Vercel dashboard (free tier)

## Milestones
- [x] M1 — Canonical Schema + DB schema + events table + idempotency ✅
- [x] M2 — Cloudflare Worker Telegram webhook + Whisper/VIN/OCR normalization ✅
- [x] M3 — Planner Agent (1200-token JSON output) + tool_gateway.ts (8 tools, Zod, secret injection, prompt firewall) ✅
- [x] M4 — YAML workflows (estimate_approval, parts_order, subscription_signup, vehicle_appraisal) ✅
- [x] M5 — Governance: policies.yaml, approvals, escalation, tiered notifications ✅
- [x] M6 — Next.js Dashboard (8 pages): RO Kanban, Estimate builder, Inventory, Buy/Sell, MRR, Credits, Audit, Build Package ✅
- [x] M7 — Online services: /build-package (5-question form), /care-plans (3 premium), Stripe Checkout ✅
- [x] M8 — Observability: cost_tracker, reconciler, verification worker ✅
- [x] M9 — Eval suite: 30 shop Moments + simulation report ✅
- [x] M10 — Deliverables: docker-compose, .env.example, README, CI/CD, setup scripts ✅

## Current Step
ALL MILESTONES COMPLETE. Full system scaffolded. Awaiting Python service from nla-agentic-builder for integration.

## Deliverables Built
| File | Purpose |
|------|---------|
| `schemas/v1.json` | JSON Schema for NextLevelEvent |
| `src/models/event.py` | Pydantic v2 canonical event |
| `src/models/plan.py` | PlanSchema for Planner Agent |
| `db/schema.sql` | Postgres tables, queues, indexes, triggers |
| `db/functions.sql` | Supabase stored procedures |
| `src/workers/telegram-webhook.ts` | Cloudflare Worker Telegram webhook |
| `src/workers/workflow-state.ts` | Durable Object for workflow state |
| `src/workers/verification_worker.ts` | SLA verification, DLQ, escalation |
| `src/workers/dashboard-api.ts` | Cloudflare Worker dashboard API |
| `src/gateway/tool_gateway.ts` | 8-tool gateway with Zod, prompt firewall |
| `python-service/` | FastAPI + PlannerAgent + ToolRegistry + GovernanceEngine |
| `workflows/*.yaml` | 4 YAML state machine workflows |
| `governance/policies.yaml` | Approval, notification, retention policies |
| `dashboard/` | Next.js 14 with 8 pages |
| `eval/moments.yaml` | 30 shop Moments + simulation config |
| `config.yaml` | Shop config (cloud-native LLM, plans, suppliers) |
| `.env.example` | Environment template |
| `docker-compose.yml` | Optional local Supabase |
| `wrangler.toml` | Cloudflare Worker config |
| `setup.sh` / `setup.bat` | One-time setup scripts |
| `.github/workflows/ci.yml` | CI/CD pipeline |
| `README.md` | Full documentation + kill matrix |

## Integration with nla-agentic-builder
- Message sent with updated scope (no local LLM, use OpenRouter)
- Python service (`python-service/`) built as integration point
- Endpoints: `/plan`, `/execute`, `/govern`
- CF Worker POSTs to Python for plan/govern, direct calls for tools

## Change Log
- 2026-08-25 — created, all milestones built, cloud-native pivot for ThinkPad W540
