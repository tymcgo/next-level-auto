# Next Level Auto — Agentic Business OS

Fully agentic business operating system for automotive repair shops.
**Owner provides CSV + 3 keys. System does the rest.**

## Status: M1-M11 Complete | M12 Blocked on Cloudflare Token

## Quick Start

```bash
# 1. Clone + install
git clone <repo> && cd NextLevelAuto
pip install -e .
npm install  # for Workers

# 2. Configure
cp .env.example .env  # fill in keys

# 3. Deploy Workers
cd src/workers && wrangler deploy

# 4. Run simulation
python src/simulate.py ro_history.csv simulation_report.json
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Telegram Bot (@NextLevelMomentsBot)    │
│          voice → Whisper → structured Moment             │
│          VIN photo → OCR → structured Moment             │
│          forwarded SMS → parse → structured Moment       │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                   Planner Agent (LLM)                    │
│   System prompt: You are Next Level Auto estimator       │
│   Input: Moment + last 2 ROs + config.yaml               │
│   Output: Plan [{tool, args}] ≤ 1200 tokens              │
│   Scoped memory ONLY — no history beyond last 2 ROs      │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│            Cloudflare Workers — Tool Gateway             │
│   Zod validation → sanitize → idempotency → circuit br.  │
│   8 tools: decode_vin, create_ro, create_estimate,       │
│   send_sms, order_parts, create_stripe_subscription,     │
│   update_website_inventory, audit_log                     │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              Supabase (Postgres + Auth + RLS)            │
│   moments, processed_moments, outbox, failed_moments,    │
│   customer_credits, vehicle_appraisals, audit_log        │
└─────────────────────────────────────────────────────────┘
```

## The 8 Moment Types

| Key | Description | Auto-Approve |
|---|---|---|
| `diagnosis` | Initial concern, test drive, DTC scan | Below threshold |
| `repair` | Labor + parts to fix diagnosed issue | Below threshold |
| `estimate` | Written quote before authorization | Below threshold |
| `maintenance` | Oil, tires, brakes on schedule | Below threshold |
| `subscription_signup` | Customer enrolls in monthly plan | Always |
| `subscription_renewal` | Auto-renew monthly plan | Always |
| `vehicle_appraisal` | Shop buying a vehicle | Below threshold |
| `vehicle_listing` | Shop listing for sale | Always |

## The 8 Tools

| Tool | Purpose | Idempotent |
|---|---|---|
| `decode_vin` | NHTSA free VIN decoder | ✅ |
| `create_ro` | Create RO in shop system | ✅ |
| `create_estimate` | Create written estimate | ✅ |
| `send_sms` | Twilio SMS to customer | ✅ |
| `order_parts` | Email parts order to supplier | ✅ |
| `create_stripe_subscription` | Stripe care plan subscription | ✅ |
| `update_website_inventory` | Webhook to website | ✅ |
| `audit_log` | Append-only audit trail | ✅ |

## Schema (Perfected — 62 Tests)

The canonical schema `NextLevelMoment` is the single source of truth:

```python
class NextLevelMoment(BaseModel):
    idempotency_key: str   # `mom_` + sha256(vin+timestamp+raw) — globally unique
    vin: str               # 11-17 chars, ISO 3779 (no I/O/Q), check digit WARNING not rejection
    mileage: Optional[int] # 0-2M miles
    dtcs: list[str]        # SAE J2012 format [PBCU][0-9A-F]{4}
    diag: Optional[str]    # Technician notes (max 2000 chars)
    parts: list[PartLine]  # Part number, description, qty, unit_cost_cents
    labor_hours: float     # 0-999.9
    labor_rate_cents: int  # Shop rate in cents/hour
    estimate_total_cents: int  # Auto-computed: labor + parts
    approval_status: ApprovalStatus  # pending → approved | rejected | escalated
    subscription_plan: Optional[str] # Care plan name
    moment_type: MomentType          # 8 canonical types
    raw: Optional[str]               # Original input (max 10KB)
    created_at: datetime             # Timezone-aware UTC
```

**Key Design Decisions:**
- **Money is always integer cents** — never float (prevents rounding errors)
- **VIN check digit is WARNING not rejection** — shop VIN entry is error-prone; we log but allow through
- **Idempotency key = `mom_` + sha256** — `mom_` prefix for quick identification, sha256 for collision resistance, separator bytes prevent concatenation attacks
- **Approval state machine**: pending → approved | rejected | escalated (no backward transitions)
- **Scoped memory**: CustomerContext = last 2 ROs only — planner never sees full history

## 29 Failure Modes — Coverage Matrix

| # | Failure Mode | Where Handled | Mechanism |
|---|---|---|---|
| 1 | **Idempotency keys** | `src/schemas/` + `tool_gateway.ts` | `mom_` + sha256, UNIQUE constraint + pre-check |
| 2 | **Transactional outbox** | `supabase/migrations` + gateway | `outbox` table, write result on success |
| 3 | **Dead Letter Queue** | `supabase/migrations` + `dlq_worker.ts` | `failed_moments` table, retry up to 3x |
| 4 | **Circuit breaker** | `tool_gateway.ts` | 5 failures/30s → open, 60s cooldown |
| 5 | **Audit log** | `supabase/migrations` + `audit_log` tool | Append-only `audit_log` table |
| 6 | **Schema registry** | `src/schemas/__init__.py` | Pydantic v2 canonical schema |
| 7 | **Scoped memory** | `src/agent/__init__.py` | CustomerContext = last 2 ROs ONLY |
| 8 | **Planner/Executor split** | `src/agent/` + `src/tools/` | Planner outputs Plan JSON, Executor runs steps |
| 9 | **Prompt injection filter** | `src/tools/` + `tool_gateway.ts` | Regex patterns reject malicious input |
| 10 | **Exponential backoff** | `tool_gateway.ts` | 200ms base, 5x multiplier |
| 11 | **Jitter** | `tool_gateway.ts` | Random jitter added to backoff |
| 12 | **Partition by VIN** | `supabase/migrations` | Index on `moments.vin` |
| 13 | **SMS test mode** | `src/tools/` | `[TEST - approve in Telegram]` prefix |
| 14 | **Kill switch** | Telegram `/stop` | Bot polling stops, Workers reject new work |
| 15 | **Verification worker** | `verification_worker.ts` | Cron every 5 min checks outbox |
| 16 | **Approval timeout escalation** | `src/governance/` | SLA 3h → auto-escalation SMS |
| 17 | **Subscription idempotency** | `src/subscription/` | Stripe `Idempotency-Key` header |
| 18 | **Buy/sell approval gate** | `src/buy_sell/` | `max_appraisal_cents` cap |
| 19 | **Inventory reconciliation** | `update_website_inventory` tool | Webhook + outbox tracking |
| 20 | **Schema validation** | Pydantic v2 + Zod | Input validated at boundary |
| 21 | **RLS** | `supabase/migrations` | All tables have RLS |
| 22 | **Required outcome verification** | `verification_worker.ts` | Checks `create_ro` returns `ro_id` |
| 23 | **DLQ manual retry** | `dlq_worker.ts` | POST to `/dlq/retry` |
| 24 | **Secret isolation** | `src/tools/` + `.env.example` | Secrets from env ONLY |
| 25 | **Input sanitization** | `src/tools/` | All string args sanitized |
| 26 | **Tool registry** | `src/tools/` | Explicit registration |
| 27 | **Config-driven behavior** | `config/config.yaml` | Business rules in YAML |
| 28 | **Typed errors** | All modules | Structured error responses |
| 29 | **Health checks** | `tool_gateway.ts` | `GET /health` |

## Interview (10 Questions → config.yaml)

The system asks the owner via Telegram or CLI:

1. Hourly labor rate (e.g., $150/hr)
2. BASIC care plan name + price + benefits
3. PLUS care plan name + price + benefits
4. PREMIUM care plan name + price + benefits
5. Preferred parts supplier email
6. Approval threshold in dollars
7. SMS sender name

Answers written to `config/config.yaml` — no manual YAML editing.

## Simulation Mode

```bash
python src/simulate.py ro_history.csv report.json
```

Output: approval time before/after, tokens per RO, cost, error count.
All SMS prefixed with `[TEST - approve in Telegram]`.

## Supabase Tables

| Table | Purpose |
|---|---|
| `moments` | Canonical moment records |
| `processed_moments` | Idempotency tracking |
| `outbox` | Transactional outbox |
| `failed_moments` | Dead letter queue |
| `customer_credits` | Subscription credits |
| `vehicle_appraisals` | Buy/sell records |
| `audit_log` | Append-only audit trail |

## Tech Stack

| Layer | Technology |
|---|---|
| Data | Supabase (Postgres + Auth + RLS) |
| Compute | Cloudflare Workers |
| Intelligence | LiteLLM (provider-agnostic LLM routing) |
| Capture | Telegram Bot API |
| Language | Python 3.11 + TypeScript |
| Validation | Pydantic v2 + Zod |
| Config | YAML (no hard-coded business logic) |

## Deliverables Checklist

- [x] Git repo with full source (24 files)
- [x] `.env.example` with 20 documented env vars
- [x] README with failure mode matrix (this file)
- [x] 62 tests passing (schema, discovery, validation)
- [x] Discovery pipeline validated (10 moments from sample CSV)
- [x] Config-driven YAML (moment types, plans, policies)
- [x] Cloudflare Workers gateway (idempotency, circuit breaker, DLQ)
- [x] Telegram bot (voice/VIN/SMS capture)
- [x] Subscription flow (Stripe + customer credits)
- [x] Buy/sell flow (appraisal + website webhook)
- [ ] Live Telegram bot link (needs bot token from @BotFather)
- [ ] Dashboard URL for audit log (needs Supabase Studio access)
- [ ] Production deploy (needs Cloudflare API token + Supabase service key)

## What's Blocked

| Item | What's Needed |
|---|---|
| Production deploy | Cloudflare API token + account ID |
| Supabase provisioning | Supabase service key (anon key in `.env`) |
| Telegram bot live | Bot token from @BotFather |
| Shopify AI Toolkit | Private repo access (non-critical) |

## Config Files

- `config/config.yaml` — moment types, plans, execution tuning
- `config/policies.yaml` — approval thresholds, failure mode toggles
- `.env` — secrets (never committed)
