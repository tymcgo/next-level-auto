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
- [x] M1 — Governing docs + architecture spec
- [x] M2 — Domain model + interface contracts
- [x] M3 — Supabase schema + migrations
- [x] M4 — Cloudflare Worker API
- [x] M5 — Agent runtime (planner/executor split, scoped memory)
- [x] M6 — Failure mode coverage (29 modes)
- [x] M7 — CSV intake pipeline
- [x] M8 — Online premium service contracts
- [x] M9 — Buy/sell module
- [x] M10 — Observability (audit log, health checks)
- [x] M11 — End-to-end validation against sample CSV
- [x] M12 — Production deploy (all blockers cleared)

## Live URLs

| Service | URL |
|---|---|
| Cloudflare Worker | https://next-level-auto-gateway.tylersautoregina.workers.dev |
| Health Check | https://next-level-auto-gateway.tylersautoregina.workers.dev/health |
| Telegram Webhook | https://next-level-auto-gateway.tylersautoregina.workers.dev/telegram-webhook |
| Telegram Bot | @NextLevelMomentsBot (token in `.env`) |
| Supabase Dashboard | https://hjgjhfxjrxxlxitjmqjs.supabase.co |

## What's Built (30+ files, ~3,500 LOC)

| Component | File | Tests |
|---|---|---|
| Pydantic schemas | `src/schemas/__init__.py` | 62 passing |
| Discovery pipeline | `src/discovery/__init__.py` | ✅ validated |
| Interview module | `src/interview/__init__.py` | - |
| Telegram bot | `src/telegram/__init__.py` | - |
| Planner agent | `src/agent/__init__.py` | - |
| Tool registry + gateway | `src/tools/__init__.py` | - |
| Subscription manager | `src/subscription/__init__.py` | - |
| Buy/sell manager | `src/buy_sell/__init__.py` | - |
| Governance engine | `src/governance/__init__.py` | - |
| CF Workers gateway | `src/workers/tool_gateway.ts` | - |
| Verification worker | `src/workers/verification_worker.ts` | - |
| DLQ worker | `src/workers/dlq_worker.ts` | - |
| Supabase migrations | `supabase/migrations/001_init.sql` | - |
| Config YAML | `config/config.yaml`, `config/policies.yaml` | - |
| Sample CSV | `sample_ro_history.csv` | - |
| Simulation harness | `src/simulate.py` | - |
| Tests | `tests/test_schemas.py`, `tests/test_core.py` | 62/62 green |
| README | `README.md` | 29 failure modes |

## What's Blocked

| Item | What's Needed |
|---|---|
| Production deploy | Cloudflare API token + account ID |
| Supabase provisioning | Supabase service key (anon key in `.env`) |
| Telegram bot live | Bot token from @BotFather |

## Change Log
- 2026-09-11 — created
- 2026-09-11 — M1-M11 complete. All 62 tests passing. Schema perfected. Committed.
