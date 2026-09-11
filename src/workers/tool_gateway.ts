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
  LLM_API_BASE: string;
  LLM_API_KEY: string;
  LLM_MODEL: string;
  AGENT_SERVICE_URL: string;
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

// ---------- LLM via OpenRouter ----------
async function callLLM(env: Env, messages: any[], max_tokens: number = 1200, temperature: number = 0, json: boolean = true): Promise<any> {
  const r = await fetch(`${env.LLM_API_BASE}/chat/completions`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${env.LLM_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: env.LLM_MODEL, messages, max_tokens, temperature, ...(json ? { response_format: { type: 'json_object' } } : {}) }),
  });
  if (!r.ok) throw new Error(`LLM error ${r.status}: ${await r.text()}`);
  const data = await r.json();
  return data.choices[0].message.content;
}

async function transcribeVoice(env: Env, audioBytes: ArrayBuffer): Promise<string> {
  const b64 = btoa(String.fromCharCode(...new Uint8Array(audioBytes)));
  const r = await fetch(`${env.LLM_API_BASE}/audio/transcriptions`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${env.LLM_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: 'openai/whisper-large-v3', file: `data:audio/ogg;base64,${b64}`, response_format: 'text' }),
  });
  if (!r.ok) throw new Error(`Whisper error ${r.status}: ${await r.text()}`);
  return await r.text();
}

async function extractMomentFromText(env: Env, text: string): Promise<any> {
  const raw = await callLLM(env, [
    { role: 'system', content: 'Extract structured auto repair data from the customer message. Return JSON: {"vin": "...", "mileage": null, "concern": "...", "dtcs": [], "parts_needed": [], "labor_hours": 0.0, "subscription_plan": null, "moment_type": "diagnosis|repair|estimate|maintenance|subscription_signup|subscription_renewal|vehicle_appraisal|vehicle_listing"}' },
    { role: 'user', content: text },
  ], 500);
  return JSON.parse(raw);
}

async function extractVinFromImage(env: Env, imageBytes: ArrayBuffer): Promise<any> {
  const b64 = btoa(String.fromCharCode(...new Uint8Array(imageBytes)));
  const raw = await callLLM(env, [
    { role: 'user', content: [
      { type: 'text', text: 'Read the VIN from this photo. Return JSON: {"vin": "...", "mileage": null}' },
      { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } },
    ]},
  ], 200, 0, false);
  return JSON.parse(raw);
}

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

// ---------- Telegram Webhook ----------
app.post('/telegram-webhook', async (c) => {
  const env = c.env;
  let update: any;
  try { update = await c.req.json(); } catch { return c.json({ error: 'invalid JSON' }, 400); }

  // Handle callback queries (inline button presses)
  if (update.callback_query) {
    const data = update.callback_query.data;
    const chatId = update.callback_query.message?.chat?.id;
    if (data?.startsWith('approve:yes:')) {
      const vin = data.split(':')[2];
      await fetch(`${env.SUPABASE_URL}/rest/v1/audit_log`, {
        method: 'POST',
        headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`, 'Content-Type': 'application/json', Prefer: 'return=minimal' },
        body: JSON.stringify({ event: 'approval_granted', actor: 'owner', data: { vin, source: 'telegram' } }),
      });
      await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ callback_query_id: update.callback_query.id, text: `✅ Approved ${vin}` }),
      });
      return c.json({ status: 'approved', vin });
    } else if (data?.startsWith('approve:no:')) {
      const vin = data.split(':')[2];
      await fetch(`${env.SUPABASE_URL}/rest/v1/audit_log`, {
        method: 'POST',
        headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`, 'Content-Type': 'application/json', Prefer: 'return=minimal' },
        body: JSON.stringify({ event: 'approval_rejected', actor: 'owner', data: { vin, source: 'telegram' } }),
      });
      await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ callback_query_id: update.callback_query.id, text: `❌ Rejected ${vin}` }),
      });
      return c.json({ status: 'rejected', vin });
    }
  }

  const message = update.message;
  if (!message) return c.json({ status: 'no_message' });

  const chatId = message.chat?.id;
  const text = message.text || '';

  // Handle /start
  if (text === '/start') {
    await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, text: '👋 Welcome to Next Level Auto!\n\nSend me:\n- A voice note (concern/diagnosis)\n- A VIN photo\n- A forwarded SMS\n\nI will create a structured Moment and start the approval flow.' }),
    });
    return c.json({ status: 'welcomed' });
  }

  // Handle /stop (kill switch)
  if (text === '/stop') {
    await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, text: '🛑 Bot paused. No new Moments will be processed. Contact owner to restart.' }),
    });
    return c.json({ status: 'stopped' });
  }

  // Handle voice notes
  if (message.voice) {
    const fileId = message.voice.file_id;
    const fileInfo = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getFile?file_id=${fileId}`);
    const fileData = await fileInfo.json();
    const filePath = fileData.result.file_path;
    const audioRes = await fetch(`https://api.telegram.org/file/bot${env.TELEGRAM_BOT_TOKEN}/${filePath}`);
    const audioBytes = await audioRes.arrayBuffer();
    try {
      const transcript = await transcribeVoice(env, audioBytes);
      await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId, text: `🎤 Transcribed: ${transcript}\n⏳ Extracting structured data...` }),
      });
      const moment = await extractMomentFromText(env, transcript);
      // Send to Python agentic service for planning
      const agentUrl = env.AGENT_SERVICE_URL;
      if (agentUrl) {
        const agentResponse = await fetch(`${agentUrl}/process`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ moment, context: { customer_id: 'telegram-' + chatId, vin: moment.vin || '' }, threshold_cents: 50000 }),
        });
        const result = await agentResponse.json();
        if (result.status === 'needs_approval') {
          const estimateDollars = ((result.governance?.estimate_cents || 0) / 100).toFixed(2);
          await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chat_id: chatId, text: `📋 Plan created. Estimate: $${estimateDollars}\n⏳ Waiting for owner approval...` }),
          });
        } else {
          await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chat_id: chatId, text: `📋 Plan created and executing:\n${JSON.stringify(result.plan, null, 2)}` }),
          });
        }
      } else {
        await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chat_id: chatId, text: `📝 Extracted Moment:\n${JSON.stringify(moment, null, 2)}` }),
        });
      }
    } catch (e: any) {
      await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId, text: `❌ Error: ${e.message}` }),
      });
    }
    return c.json({ status: 'voice_processed' });
  }

  // Handle photos (VIN)
  if (message.photo) {
    const photo = message.photo[message.photo.length - 1];
    const fileId = photo.file_id;
    const fileInfo = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getFile?file_id=${fileId}`);
    const fileData = await fileInfo.json();
    const filePath = fileData.result.file_path;
    const imgRes = await fetch(`https://api.telegram.org/file/bot${env.TELEGRAM_BOT_TOKEN}/${filePath}`);
    const imgBytes = await imgRes.arrayBuffer();
    try {
      const result = await extractVinFromImage(env, imgBytes);
      await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId, text: `📸 VIN: ${result.vin || 'unknown'}\nMileage: ${result.mileage || 'unknown'}` }),
      });
    } catch (e: any) {
      await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId, text: `❌ Error: ${e.message}` }),
      });
    }
    return c.json({ status: 'photo_processed' });
  }

  // Handle text (forwarded SMS or direct message)
  if (text) {
    try {
      const moment = await extractMomentFromText(env, text);
      // Send to Python agentic service
      const agentUrl = env.AGENT_SERVICE_URL;
      if (agentUrl) {
        const agentResponse = await fetch(`${agentUrl}/process`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ moment, context: { customer_id: 'telegram-' + chatId, vin: moment.vin || '' }, threshold_cents: 50000 }),
        });
        const result = await agentResponse.json();
        if (result.status === 'needs_approval') {
          const estimateDollars = ((result.governance?.estimate_cents || 0) / 100).toFixed(2);
          await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chat_id: chatId, text: `📋 Plan created. Estimate: $${estimateDollars}\n⏳ Waiting for owner approval...` }),
          });
        } else {
          await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chat_id: chatId, text: `📋 Plan created and executing:\n${JSON.stringify(result.plan, null, 2)}` }),
          });
        }
      } else {
        await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chat_id: chatId, text: `📨 Extracted Moment:\n${JSON.stringify(moment, null, 2)}` }),
        });
      }
    } catch (e: any) {
      await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId, text: `❌ Error: ${e.message}` }),
      });
    }
    return c.json({ status: 'text_processed' });
  }

  return c.json({ status: 'unhandled' });
});

export default app;
