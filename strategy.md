# Strategy — Next Level Auto (Custom Agentic Tekmetric)
Updated: 2026-08-25

## Approach
Declarative YAML-driven workflow state machines + idempotent stateless workers + append-only event sourcing. Every operation has an idempotency key, schema validation at the boundary, circuit breakers on all external calls, and a transactional outbox for reliable delivery.

## Why This Way
- Supabase gives us Postgres + Auth + pgmq in one managed service at $25/mo
- Cloudflare Workers: zero server maintenance, $5/mo for 10M req
- LiteLLM gateway: model-agnostic, cost-optimized routing
- Telegram: techs already use it, no new app to learn
- YAML workflows: non-devs can edit business logic without touching TypeScript

## Alternatives Considered
- **Tekmetric API integration** — rejected: vendor lock-in, their API is brittle, doesn't support custom workflows
- **Custom monolith app** — rejected: requires ongoing maintenance, doesn't scale down to $50/mo
- **n8n/Zapier automation** — rejected: not agentic, no idempotency guarantees, no audit trail
- **LangChain/AutoGen agents** — rejected: over-abstraction, unpredictable costs, hallucination amplification

## Change Log
- 2026-08-25 — created
