# Strategy — Next Level Auto Agentic Business OS

Updated: 2026-09-11

## Approach
Build a config-driven, failure-first business operating system. The system is composed of three planes (data, compute, intelligence) connected by YAML-defined behavior contracts. An autonomous agent runtime handles intake, inference, and execution with full observability. All 29 failure modes are handled by infrastructure, not by asking the owner.

## Why This Way
- **Zero-friction onboarding**: owner provides CSV + keys; system infers schema, builds tables, deploys endpoints, validates. No manual mapping.
- **YAML-driven behavior**: business rules (state machines, validation, pricing, escalation) live in config, not code. Owner can edit config to change behavior without redeploy.
- **Failure-first**: 29 failure modes (idempotency, DLQ, circuit breaker, audit, schema registry, scoped memory, planner/executor) are architected in from day one — not bolted on later.
- **Supabase**: gives Postgres + Auth + Storage + Realtime in one managed service. Row-level security, migrations, and edge functions.
- **Cloudflare Workers**: serverless edge compute with global distribution. No servers to manage, automatic scaling, Workers KV for config cache.
- **LiteLLM**: single routing layer for any LLM provider. Provider-agnostic, cost-tracking, fallbacks, rate-limit handling.
- **No LangChain**: keep it lean. Direct LLM calls via LiteLLM, custom orchestration logic. Avoid framework lock-in and excessive abstraction.

## Alternatives Considered
- **LangChain / LlamaIndex** — rejected: adds framework complexity, heavy dependency tree, opinionated patterns that conflict with YAML-driven design. Custom orchestration is simpler and more controllable.
- **Django / Rails monolith** — rejected: requires server management, migrations are heavier, not edge-native. Workers + Supabase is lighter and scales to zero.
- **Vercel / AWS Lambda** — rejected: Cloudflare Workers has better global latency, Workers KV for config caching, and a simpler pricing model at the edge.
- **Direct Supabase Edge Functions** — rejected: less portable than Cloudflare Workers, smaller ecosystem, weaker tooling. CF Workers are the more mature serverless edge platform.
- **Hard-coded business logic** — rejected: violates the "zero friction" requirement. Config-driven behavior lets the owner change rules without code changes or deploys.

## Change Log
- 2026-09-11 — created
