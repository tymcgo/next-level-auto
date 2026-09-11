# Next Level Auto — Custom Agentic Shop Management

**Tekmetric replacement.** Fully agentic. $0 to build and validate. Runs on free cloud tiers — your ThinkPad only needs a browser.

## Architecture

```
Telegram → Cloudflare Worker (serverless)
              ↓
         LLM Extraction (OpenRouter free models)
              ↓
         Supabase Cloud (Postgres + Auth, free tier)
              ↓
         Next.js Dashboard (Vercel free tier)
```

## Free Tiers Used

| Service | Free Tier | What We Use It For |
|---------|-----------|-------------------|
| **OpenRouter** | Free tier models (Gemma, Llama, Mistral) | Planner Agent LLM |
| **Supabase** | 500DB, 2M requests/month | DB, Auth, Queue |
| **Cloudflare Workers** | 100K req/day, 10M req/month | Telegram webhook, API |
| **Vercel** | 100GB bandwidth | Next.js dashboard |
| **Telegram Bot** | Free forever | Tech input, notifications |
| **Stripe Test Mode** | Free | Payment testing |
| **NHTSA VIN API** | Free public API | VIN decode |
| **GitHub** | Free | Repo, Actions CI |

**Total cost: $0/mo.** Only pay when you go live with real traffic.

## Quick Start

### 1. Get Free API Keys

```bash
# Sign up for free accounts:
# 1. OpenRouter: https://openrouter.ai (get API key)
# 2. Supabase: https://supabase.com (create free project)
# 3. Telegram: @BotFather → /newbot (get bot token)
# 4. Vercel: https://vercel.com (auto-deploy from GitHub)
# 5. Cloudflare: https://dash.cloudflare.com ( Workers & Pages)
```

### 2. Clone and Configure

```bash
git clone https://github.com/tymcgo/next-level-auto.git
cd next-level-auto
cp .env.example .env
# Fill in your free API keys
```

### 3. Deploy (no local servers needed)

```bash
# Deploy Cloudflare Worker (Telegram webhook)
npx wrangler deploy src/workers/telegram-webhook.ts

# Deploy Next.js dashboard to Vercel
vercel --prod

# Set Telegram webhook URL
curl -F "url=https://nla-telegram.your-subdomain.workers.dev" \
     https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook
```

### 4. Go

- Open your Vercel dashboard URL
- Send a voice note or VIN photo to your Telegram bot
- Watch events flow in real-time

## The 29-Failure Kill Matrix

Every failure mode from the original spec has a concrete mitigation built into the architecture:

| # | Failure | Mitigation |
|---|---------|-----------|
| 1 | Workarounds break | Declarative YAML workflows in `/workflows/` |
| 2 | Customizations break | Schema registry `/schemas/v1.json`, versioned events |
| 3 | Unexpected behaviors | Circuit breakers on all external calls |
| 4 | Context contamination | 1200 token output cap, scoped memory per VIN |
| 5 | Hallucinations | Zod validation, 8-tool allowlist, prompt firewall |
| 6 | Siloed info | Single events table, customer + last 2 ROs injected |
| 7 | Tech errors | Idempotency keys, exponential backoff + jitter, DLQ |
| 8 | Approval bottlenecks | Tiered approval >$750 → Tyler, 3h SLA escalation |
| 9 | Missed tool calls | Required outcomes + verification worker |
| 10 | Missed approvals | Escalation job every 15 min |
| 11 | No timely notifications | P0 Telegram immediate, P1 Slack, P2 daily digest |
| 12 | No governance | `policies.yaml`, `audit_log` append-only |
| 13 | Tool sprawl | Exactly 8 tools via gateway allowlist |
| 14 | Version drift | `schema_version` on all events, registry file |
| 15 | Race conditions | Idempotency keys, DB unique constraints |
| 16 | Silent failures | Verification worker, DLQ, transactional outbox |
| 17 | Retry storms | Backoff 200ms/1s/5s + jitter, max 5 retries |
| 18 | Security/injection | Prompt firewall strips overrides, Zod validation |
| 19 | Cost overruns | `cost_tokens` per event, $5/day budget cap |
| 20 | Inconsistent model behavior | PlanSchema JSON enforced, no free-text |
| 21 | No audit trail | `audit_log` append-only, OpenTelemetry traces |
| 22 | Brittle glue code | YAML state machines, declarative workflows |
| 23 | Manual reconciliation | Nightly reconciler (events vs Stripe vs shop) |
| 24 | Alert fatigue | Tiered notifications, batched P2 digest |
| 25 | SPOF | Stateless serverless functions, managed Supabase |
| 26 | Scope creep | `scope.md` enforced, features require inclusion |
| 27 | Vendor lock-in | Replaceable: Supabase→Postgres, CF→any Workers, LiteLLM→any LLM |
| 28 | Inconsistent schemas | Pydantic v2 + Zod + schema registry |

## Project Structure

```
next-level-auto/
├── .env.example          # Environment template
├── config.yaml           # Shop config (labor, plans, suppliers)
├── plan.md               # Implementation plan + milestones
├── strategy.md           # Why this architecture
├── scope.md              # In/out of scope
├── architecture.md       # System design + kill matrix
├── schemas/
│   └── v1.json           # JSON Schema for NextLevelEvent
├── db/
│   └── schema.sql        # Postgres tables, queues, indexes
├── src/
│   ├── models/
│   │   ├── event.py      # Pydantic v2 NextLevelEvent
│   │   └── plan.py       # Pydantic PlanSchema
│   ├── workers/
│   │   └── telegram-webhook.ts  # Cloudflare Worker
│   ├── gateway/
│   │   └── tool_gateway.ts      # 8-tool gateway
│   ├── planner/
│   │   └── agent.yaml            # Planner Agent config
│   └── observability/
│       ├── cost_tracker.ts       # Token cost tracking
│       └── reconciler.ts         # Nightly reconciliation
├── workflows/
│   ├── estimate_approval.yaml
│   ├── parts_order.yaml
│   ├── subscription_signup.yaml
│   └── vehicle_appraisal.yaml
├── governance/
│   └── policies.yaml     # Approval, notification, retention policies
├── eval/
│   └── moments.yaml      # 30 shop Moments for validation
└── dashboard/            # Next.js 14 dashboard
    ├── app/
    │   ├── page.tsx         # Dashboard home
    │   ├── ro/page.tsx      # RO Kanban
    │   ├── estimates/       # Estimate builder (voice→draft)
    │   ├── inventory/       # Parts tracking
    │   ├── lot/             # Buy/Sell lot
    │   ├── subscriptions/   # MRR tracking
    │   ├── credits/         # Customer credits
    │   ├── build-package/   # 5-question form
    │   └── care-plans/      # Premium contracts
    └── components/
        └── Sidebar.tsx
```

## Tech Stack

| Layer | Tech | Why |
|-------|------|-----|
| LLM | OpenRouter free models | $0, no local compute needed |
| Backend | Cloudflare Workers | Serverless, $5/mo, 100K req/day free |
| DB | Supabase (Postgres + Auth) | Free tier 500MB, managed |
| Frontend | Next.js + Vercel | Free tier, zero-config deploy |
| Voice | Whisper via OpenRouter | No local install |
| OCR | OpenRouter vision models | No local install |
| Messaging | Telegram Bot | Free forever |
| Payments | Stripe (test mode) | Free testing |
| VIN Decode | NHTSA public API | Free |
| Monitoring | Cloudflare Workers telemetry + Supabase logs | Built-in |

## Running in TEST Mode

Default configuration:
- All SMS prefixed with `[TEST]`
- Stripe in test mode (no real charges)
- Cloudflare in dev mode
- LLM uses free OpenRouter models
- No real external calls unless explicitly enabled

## Going Live (Future)

When you're ready to go from $0 to production:

1. **Supabase**: Upgrade to Pro ($25/mo) for more storage/bandwidth
2. **LLM**: Switch to paid model (GPT-4o-mini or Claude Haiku) for better accuracy
3. **Stripe**: Flip to live mode (real charges)
4. **Vercel**: Pro ($20/mo) for custom domain + analytics
5. **Cloudflare**: $5/mo for 10M req
6. **Twilio**: For real SMS notifications

**Estimated production cost: $50-75/mo** — within spec.

## License

MIT — use freely, modify freely.

---

**Next Level Auto: Agentic shop management. Zero compute required.**
