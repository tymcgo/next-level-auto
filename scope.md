# Scope — Next Level Auto

## In Scope
1. **Canonical Event Schema** — NextLevelEvent with idempotency keys, append-only events table
2. **Capture Layer** — Cloudflare Worker accepting Telegram webhook (voice/SMS/VIN photo), normalize to NextLevelEvent
3. **Planner Agent** — Event + customer context + config.yaml → PlanSchema JSON (max 1200 tokens)
4. **Tool Gateway** — 8-tool allowlist (decode_vin, create_ro, create_estimate, send_sms, order_parts, create_stripe_subscription, list_vehicle_for_sale, audit_log)
5. **Workflows as YAML** — estimate_approval, parts_order, subscription_signup, vehicle_appraisal with state machines and policy gates
6. **Execution Layer** — Stateless workers with idempotency, exponential backoff + jitter, circuit breaker, DLQ, verification worker
7. **Governance** — policies.yaml, approvals table, escalation job, tiered notifications
8. **Dashboard** — Next.js with RO Kanban, Estimate builder (voice→draft), Inventory, Buy/Sell lot, MRR, Customer credits, Audit log
9. **Online Services** — /build-package form, /care-plans (3 premium contracts), Stripe Checkout, customer credits
10. **Buy/Sell** — vehicle_appraisals table, condition photos, profit calc, website webhook
11. **Observability** — audit_log, cost_tokens, OpenTelemetry, nightly reconciler
12. **Validation** — Eval suite (30 Moments), simulation report, TEST mode with SMS prefix

## Out of Scope
- Mobile app (PWA/dashboard covers this)
- Accounting integration (Stripe handles payments; QuickBooks can read events later)
- OEM dealer integrations
- Insurance claims
- Multi-location support (v2)

## Change Log
- 2026-08-25 — created
