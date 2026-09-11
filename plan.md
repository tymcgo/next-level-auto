# Plan — Next Level Auto Agentic Business OS

Updated: 2026-09-11

## Goal
Build a fully agentic business operating system for an automotive repair shop (diagnosis, repair, buy/sell, online premium service contracts) with zero friction for the owner — owner supplies a CSV of ROs and 3 API keys; the system infers, builds, deploys, and validates everything else.

## Stack
- **Supabase** — Postgres + Auth + Storage + Realtime (data plane)
- **Cloudflare Workers** — serverless API edge (compute plane)
- **LiteLLM** — LLM routing / cost control (intelligence plane)
- **YAML config** — ALL behavior is config, no hard-coded business logic

## Milestones
- [x] M1 — Governing docs + architecture spec (plan.md, strategy.md)
- [x] M2 — Domain model + interface contracts (Pydantic schemas, tool registry)
- [x] M3 — Supabase schema + migrations
- [x] M4 — Cloudflare Worker API (CRUD, idempotency, auth, audit)
- [x] M5 — Agent runtime (planner/executor split, scoped memory)
- [x] M6 — Failure mode coverage (29 modes)
- [x] M7 — CSV intake pipeline (infer schema, validate, ingest)
- [x] M8 — Online premium service contracts (Stripe subscription flow)
- [x] M9 — Buy/sell module (vehicle appraisal, website listing)
- [x] M10 — Observability (structured logs, audit log, health checks)
- [x] M11 — End-to-end validation against sample CSV
- [ ] M12 — Production deploy + owner handoff (requires real API keys)

## Current Step
M12 — Cloudflare onboarding + production deploy prep.

## What's Built
| Component | File | Status |
|---|---|---|
| Pydantic schemas | `src/schemas/__init__.py` | ✅ tested |
| Discovery pipeline | `src/discovery/__init__.py` | ✅ validated |
| Interview module | `src/interview/__init__.py` | ✅ |
| Telegram bot | `src/telegram/__init__.py` | ✅ |
| Planner agent | `src/agent/__init__.py` | ✅ |
| Tool registry + gateway | `src/tools/__init__.py` | ✅ |
| Subscription manager | `src/subscription/__init__.py` | ✅ |
| Buy/sell manager | `src/buy_sell/__init__.py` | ✅ |
| Governance engine | `src/governance/__init__.py` | ✅ |
| CF Workers gateway | `src/workers/tool_gateway.ts` | ✅ |
| Verification worker | `src/workers/verification_worker.ts` | ✅ |
| DLQ worker | `src/workers/dlq_worker.ts` | ✅ |
| Supabase migrations | `supabase/migrations/001_init.sql` | ✅ |
| Config YAML | `config/config.yaml`, `config/policies.yaml` | ✅ |
| Sample CSV | `sample_ro_history.csv` | ✅ |
| Simulation harness | `src/simulate.py` | ✅ |
| Tests | `tests/test_schemas.py`, `tests/test_core.py` | ✅ 61/61 passing |
| README | `README.md` | ✅ with 29 failure modes |

## Risks / Open Questions
- Owner has not yet provided real CSV of ROs — M12 requires delivery.
- Cloudflare account setup needed (API token + account ID).
- Supabase service key needed for production.

## Change Log
- 2026-09-11 — created
- 2026-09-11 — M1-M11 complete. All 61 tests passing. Schema perfected.
- 2026-09-11 — M12 in progress. Cloudflare onboarding started.
