# Architecture — Next Level Auto

## System Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Telegram Bot   │────▶│  Cloudflare      │────▶│  Supabase           │
│  (voice/SMS/    │     │  Worker          │     │  (Postgres+pgmq)    │
│   VIN photo)    │     │  - Normalize     │     │  - events (append)  │
└─────────────────┘     │  - Idempotency   │     │  - RO table         │
                        │  - Enqueue       │     │  - Queue            │
                        └──────────────────┘     └─────────┬───────────┘
                                                           │
                        ┌──────────────────┐               │
                        │  Planner Agent   │◀──────────────┘
                        │  (LiteLLM)       │
                        │  - Event + ctx   │
                        │  - 1200 tok out  │
                        └────────┬─────────┘
                                 │
                        ┌────────▼─────────┐
                        │  tool_gateway.ts │
                        │  - 8 tools       │
                        │  - Zod validate  │
                        │  - Secret inject │
                        │  - Prompt FW     │
                        └────────┬─────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
     ┌────────▼────────┐ ┌──────▼───────┐ ┌───────▼────────┐
     │  Workflow       │ │  External    │ │  Governance    │
     │  Workers        │ │  APIs        │ │  Workers       │
     │  (YAML-driven)  │ │  - NHTSA VIN │ │  - Escalation  │
     │                  │ │  - Stripe    │ │  - Notifications│
     │                  │ │  - Twilio    │ │  - Approvals   │
     └─────────────────┘ └──────────────┘ └────────────────┘
```

## Data Flow

1. **Ingest**: Telegram → Worker → Whisper (voice) / OCR (VIN photo) / SMS parse → NextLevelEvent
2. **Enqueue**: Event written to `events` (append-only), enqueued to `pgmq` partitioned by `vin_last6`
3. **Plan**: Worker dequeues → Planner Agent receives Event + customer summary + last 2 ROs + config.yaml → PlanSchema JSON
4. **Execute**: Each plan step dispatched through `tool_gateway.ts` → Zod validation → secret injection → idempotency check → tool invocation
5. **Verify**: Verification worker checks `required_outcomes` within SLA; DLQ on failure
6. **Notify**: Tiered notifications based on policy severity

## Failure Mode Kill Matrix (29 failures → mitigations)

| # | Failure | Mitigation |
|---|---------|-----------|
| 1 | Workarounds break | Declarative YAML workflows, versioned schemas, schema registry |
| 2 | Customizations break | Schema validation on all inputs, backward-compatible migrations |
| 3 | Unexpected behaviors | Circuit breakers on all external calls, graceful degradation |
| 4 | Context contamination/bloat | Scoped memory per VIN, max 1200 token output, stateless workers |
| 5 | Hallucinations | Zod schema enforcement, tool allowlist, prompt firewall stripping overrides |
| 6 | Siloed info | Single events table, customer summary + last 2 ROs always injected |
| 7 | Tech errors | Idempotency keys, exponential backoff + jitter, DLQ with retry |
| 8 | Approval bottlenecks | Tiered approval (>$750 → Tyler), 3h SLA escalation |
| 9 | Missed tool/skill calls | Tool allowlist with required outcomes, verification worker |
| 10 | Missed approvals | policies.yaml enforcement, escalation job every 15 min |
| 11 | No timely notifications | P0 Telegram immediate, P1 Slack, P2 daily digest 8am/4pm |
| 12 | No governance | policies.yaml, audit_log append-only, approvals table |
| 13 | Tool sprawl | Exactly 8 tools, gateway allows only those 8 |
| 14 | Version/state drift | Schema registry /schemas/v1.json, schema_version on all events |
| 15 | Race conditions | Idempotency keys, DB unique constraints, single-writer per VIN partition |
| 16 | Silent failures | Verification worker, DLQ alerting, transactional outbox |
| 17 | Retry storms | Exponential backoff 200ms/1s/5s + jitter, max 5 retries |
| 18 | Security/injection gaps | Prompt firewall strips override instructions, secret injection (no hardcoded secrets), Zod input validation |
| 19 | Cost overruns | cost_tokens per event tracked, LiteLLM cost routing, 1200 token cap |
| 20 | Inconsistent behavior across models | Planner output constrained to PlanSchema JSON, no free-text |
| 21 | No audit trail/observability | audit_log append-only, OpenTelemetry, correlation IDs |
| 22 | Brittle glue code | YAML workflows, declarative state machines, no custom routing logic |
| 23 | Manual reconciliation | Nightly reconciler comparing events vs shop system vs Stripe |
| 24 | Alert fatigue | Tiered notifications, deduplication, 8am/4pm digest batching |
| 25 | SPOF | Stateless workers, Supabase managed failover, Cloudflare global edge |
| 26 | Scope creep | scope.md enforced, features require explicit inclusion |
| 27 | Vendor lock-in | Replaceable: Supabase→Postgres, Cloudflare→any Worker platform, LiteLLM→any LLM |
| 28 | Inconsistent schemas | Pydantic v2 on input, Zod on gateway, schema registry, schema_version |
| 29 | N/A (placeholder) | Covered by above |

## Change Log
- 2026-08-25 — created
