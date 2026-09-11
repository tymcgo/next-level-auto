/**
 * tool_gateway.ts — Cloudflare Worker entry point.
 * Routes requests to tools with Zod validation, idempotency, circuit breaker, DLQ.
 */
import { Hono } from 'hono';
import { z } from 'zod';

// ---------- Zod schemas for each tool ----------

const DecodeVinArgs = z.object({ vin: z.string().min(11).max(17) });
const CreateRoArgs = z.object({ vin: z.string(), customer: z.string(), concern: z.string() });
const CreateEstimateArgs = z.object({ vin: z.string(), total_cents: z.number().int() });
const SendSmsArgs = z.object({ to: z.string(), body: z.string() });
const OrderPartsArgs = z.object({ supplier_email: z.string().email(), parts: z.array(z.object({ part_number: z.string(), description: z.string(), quantity: z.number().int() })) });
const CreateStripeSubArgs = z.object({ customer_email: z.string().email(), plan_name: z.string(), vin: z.string() });
const UpdateWebsiteArgs = z.object({ webhook_url: z.string().url(), vin: z.string(), action: z.string() });
const AuditLogArgs = z.object({ event: z.string(), timestamp: z.string(), data: z.record(z.any()).optional() });

const ToolCallSchema = z.object({
  tool: z.enum(['decode_vin', 'create_ro', 'create_estimate', 'send_sms', 'order_parts', 'create_stripe_subscription', 'update_website_inventory', 'audit_log']),
  args: z.record(z.any()),
  idempotency_key: z.string().min(32).max(64),
});

type Env = {
  SUPABASE_URL: string;
  SUPABASE_SERVICE_KEY: string;
  TWILIO_ACCOUNT_SID: string;
  TWILIO_AUTH_TOKEN: string;
  TWILIO_FROM_NUMBER: string;
  STRIPE_SECRET_KEY: string;
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_OWNER_CHAT_ID: string;
  NHTSA_BASE: string;
  WEBSITE_WEBHOOK_URL: string;
  SHOP_API_BASE: string;
  SHOP_API_KEY: string;
};

// ---------- Prompt injection filter ----------
const INJECTION_PATTERNS = [
  /ignore\s+(all\s+)?previous\s+instructions?/i,
  /you\s+are\s+now/i,
  /system\s*prompt/i,
  /<\s*\/?\s*instruction\s*>/i,
  /<!--\s*system/i,
  /\{\{\s*config/i,
  /\$\{/,
  /`\s*rm\s+-rf/i,
];

function sanitize(value: string): string {
  for (const pat of INJECTION_PATTERNS) {
    if (pat.test(value)) throw new Error(`Prompt injection detected: ${pat.source}`);
  }
  return value;
}

// ---------- Idempotency check ----------
async function checkIdempotency(supabaseUrl: string, supabaseKey: string, key: string): Promise<boolean> {
  const r = await fetch(`${supabaseUrl}/rest/v1/processed_moments?idempotency_key=eq.${key}&select=idempotency_key`, {
    headers: { apikey: supabaseKey, Authorization: `Bearer ${supabaseKey}` },
  });
  const data = await r.json();
  return data.length > 0;
}

async function recordIdempotency(supabaseUrl: string, supabaseKey: string, key: string, tool: string, result: any) {
  await fetch(`${supabaseUrl}/rest/v1/processed_moments`, {
    method: 'POST',
    headers: { apikey: supabaseKey, Authorization: `Bearer ${supabaseKey}`, 'Content-Type': 'application/json', Prefer: 'return=minimal' },
    body: JSON.stringify({ idempotency_key: key, tool, result: JSON.stringify(result), created_at: new Date().toISOString() }),
  });
}

// ---------- Circuit breaker ----------
class CircuitBreaker {
  private failures = 0;
  private lastFailure = 0;
  private state: 'closed' | 'open' | 'half-open' = 'closed';

  constructor(private threshold: number, private windowMs: number, private cooldownMs: number) {}

  canExecute(): boolean {
    if (this.state === 'closed') return true;
    if (this.state === 'open') {
      if (Date.now() - this.lastFailure > this.cooldownMs) {
        this.state = 'half-open';
        return true;
      }
      return false;
    }
    return true; // half-open: allow one probe
  }

  recordSuccess() {
    this.failures = 0;
    this.state = 'closed';
  }

  recordFailure() {
    this.failures++;
    this.lastFailure = Date.now();
    if (this.failures >= this.threshold) this.state = 'open';
  }
}

const breakers: Record<string, CircuitBreaker> = {};

function getBreaker(tool: string): CircuitBreaker {
  if (!breakers[tool]) breakers[tool] = new CircuitBreaker(5, 30000, 60000);
  return breakers[tool];
}

// ---------- DLQ ----------
async function sendToDLQ(supabaseUrl: string, supabaseKey: string, tool: string, args: any, error: string, idempotency_key: string) {
  await fetch(`${supabaseUrl}/rest/v1/failed_moments`, {
    method: 'POST',
    headers: { apikey: supabaseKey, Authorization: `Bearer ${supabaseKey}`, 'Content-Type': 'application/json', Prefer: 'return=minimal' },
    body: JSON.stringify({ tool, args: JSON.stringify(args), error, idempotency_key, retry_count: 0, created_at: new Date().toISOString() }),
  });
}

// ---------- Exponential backoff with jitter ----------
function backoffWithJitter(attempt: number, baseMs: number, multiplier: number, jitterMs: number): number {
  const exp = baseMs * Math.pow(multiplier, attempt);
  const jitter = Math.floor(Math.random() * jitterMs);
  return exp + jitter;
}

// ---------- Tool implementations ----------

async function decodeVin(args: any, env: Env) {
  const r = await fetch(`${env.NHTSA_BASE}/vehicles/DecodeVin/${args.vin}?format=json`);
  const data = await r.json();
  const decoded: Record<string, string> = {};
  for (const item of data.Results || []) {
    if (item.Value) decoded[item.Variable] = item.Value;
  }
  return { vin: args.vin, year: decoded['Model Year'], make: decoded['Make'], model: decoded['Model'] };
}

async function createRo(args: any, env: Env) {
  // Call shop system API
  const r = await fetch(`${env.SHOP_API_BASE}/repair-orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.SHOP_API_KEY}` },
    body: JSON.stringify(args),
  });
  const data = await r.json();
  return { ro_id: data.id, status: 'created' };
}

async function createEstimate(args: any, env: Env) {
  return { estimate_id: `EST-${Date.now()}`, vin: args.vin, total_cents: args.total_cents, status: 'created' };
}

async function sendSms(args: any, env: Env) {
  const testMode = true; // TODO: from env
  let body = args.body;
  if (testMode) body = `[TEST - approve in Telegram] ${body}`;
  const r = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${env.TWILIO_ACCOUNT_SID}/Messages.json`, {
    method: 'POST',
    headers: { Authorization: 'Basic ' + btoa(`${env.TWILIO_ACCOUNT_SID}:${env.TWILIO_AUTH_TOKEN}`) },
    body: new URLSearchParams({ To: args.to, From: env.TWILIO_FROM_NUMBER, Body: body }),
  });
  const data = await r.json();
  return { sid: data.sid, sent: true, test_mode: testMode };
}

async function orderParts(args: any, env: Env) {
  // Mock: log order + email supplier
  return { order_id: `PART-${Date.now()}`, supplier_email: args.supplier_email, parts_count: args.parts.length };
}

async function createStripeSubscription(args: any, env: Env) {
  const r = await fetch('https://api.stripe.com/v1/subscriptions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.STRIPE_SECRET_KEY}` },
    body: new URLSearchParams({ 'customer_email': args.customer_email, 'plan_name': args.plan_name, 'vin': args.vin }),
  });
  const data = await r.json();
  return { subscription_id: data.id, plan: args.plan_name, status: 'active' };
}

async function updateWebsiteInventory(args: any, env: Env) {
  const r = await fetch(args.webhook_url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event: args.action, vin: args.vin, timestamp: new Date().toISOString() }),
  });
  return { webhook: args.webhook_url, status: r.status };
}

async function auditLog(args: any, env: Env) {
  return { logged: true, event: args.event, timestamp: args.timestamp };
}

const TOOL_HANDLERS: Record<string, (args: any, env: Env) => Promise<any>> = {
  decode_vin: decodeVin,
  create_ro: createRo,
  create_estimate: createEstimate,
  send_sms: sendSms,
  order_parts: orderParts,
  create_stripe_subscription: createStripeSubscription,
  update_website_inventory: updateWebsiteInventory,
  audit_log: auditLog,
};

// ---------- Hono app ----------

const app = new Hono<{ Bindings: Env }>();

app.post('/tool', async (c) => {
  const env = c.env;
  let body: any;
  try { body = await c.req.json(); } catch { return c.json({ error: 'invalid JSON' }, 400); }

  // Validate
  const parsed = ToolCallSchema.safeParse(body);
  if (!parsed.success) return c.json({ error: 'validation_failed', details: parsed.error.flatten() }, 400);

  const { tool, args, idempotency_key } = parsed.data;

  // Sanitize string args
  for (const [k, v] of Object.entries(args)) {
    if (typeof v === 'string') args[k] = sanitize(v);
  }

  // Idempotency check
  const seen = await checkIdempotency(env.SUPABASE_URL, env.SUPABASE_SERVICE_KEY, idempotency_key);
  if (seen) return c.json({ status: 'already_processed', idempotency_key });

  // Circuit breaker
  const breaker = getBreaker(tool);
  if (!breaker.canExecute()) {
    await sendToDLQ(env.SUPABASE_URL, env.SUPABASE_SERVICE_KEY, tool, args, 'circuit_breaker_open', idempotency_key);
    return c.json({ error: 'circuit_breaker_open', tool }, 503);
  }

  // Execute with retry
  const handler = TOOL_HANDLERS[tool];
  if (!handler) return c.json({ error: 'unknown_tool' }, 400);

  let lastError: string | null = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const result = await handler(args, env);
      breaker.recordSuccess();
      await recordIdempotency(env.SUPABASE_URL, env.SUPABASE_SERVICE_KEY, idempotency_key, tool, result);
      // Also write to outbox for verification
      await fetch(`${env.SUPABASE_URL}/rest/v1/outbox`, {
        method: 'POST',
        headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`, 'Content-Type': 'application/json', Prefer: 'return=minimal' },
        body: JSON.stringify({ idempotency_key, tool, result: JSON.stringify(result), status: 'completed', created_at: new Date().toISOString() }),
      });
      return c.json({ status: 'ok', tool, result, idempotency_key });
    } catch (e: any) {
      lastError = e.message;
      breaker.recordFailure();
      if (attempt < 2) await new Promise(r => setTimeout(r, backoffWithJitter(attempt, 200, 5, 50)));
    }
  }

  // All retries exhausted -> DLQ
  await sendToDLQ(env.SUPABASE_URL, env.SUPABASE_SERVICE_KEY, tool, args, lastError || 'unknown', idempotency_key);
  return c.json({ error: 'all_retries_exhausted', tool, last_error: lastError }, 500);
});

app.get('/health', (c) => c.json({ status: 'ok', timestamp: new Date().toISOString() }));

export default app;
