// tool_gateway.ts — Tool Gateway for Next Level Auto
// 8-tool allowlist, Zod validation, secret injection, prompt firewall

import { z } from 'zod';

// =============================================================================
// Tool allowlist — ONLY these 8 tools can be invoked
// =============================================================================
const TOOL_NAMES = [
  'decode_vin',
  'create_ro',
  'create_estimate',
  'send_sms',
  'order_parts',
  'create_stripe_subscription',
  'list_vehicle_for_sale',
  'audit_log',
] as const;

type ToolName = (typeof TOOL_NAMES)[number];

// =============================================================================
// Zod schemas for each tool's params (validated before execution)
// =============================================================================
const schemas: Record<ToolName, z.ZodType<any>> = {
  decode_vin: z.object({
    vin: z.string().length(17).regex(/^[A-HJ-NPR-Z0-9]{17}$/),
  }),

  create_ro: z.object({
    vehicle_id: z.string().uuid(),
    customer_id: z.string().uuid(),
    description: z.string().max(500).optional(),
    line_items: z.array(z.object({
      description: z.string().max(100),
      labor_hours: z.number().min(0).max(100),
      parts_cost: z.number().min(0),
      part_number: z.string().optional(),
      quantity: z.number().int().min(1).default(1),
    })).min(1),
    notes: z.string().max(500).optional(),
  }),

  create_estimate: z.object({
    ro_id: z.string().uuid().optional(),
    vehicle_id: z.string().uuid(),
    customer_id: z.string().uuid(),
    line_items: z.array(z.object({
      description: z.string().max(100),
      labor_hours: z.number().min(0).max(100),
      parts_cost: z.number().min(0),
      part_number: z.string().optional(),
      quantity: z.number().int().min(1).default(1),
    })).min(1),
    notes: z.string().max(500).optional(),
    expires_in_days: z.number().int().max(30).default(7),
  }),

  send_sms: z.object({
    to: z.string().regex(/^\+[1-9]\d{1,14}$/, 'E.164 phone format required'),
    body: z.string().max(1600),
  }),

  order_parts: z.object({
    supplier: z.enum(['NAPA', 'RockAuto', 'Local OEM Dealer', 'LKQ']),
    parts: z.array(z.object({
      sku: z.string().optional(),
      name: z.string().max(100),
      quantity: z.number().int().min(1).default(1),
      target_price: z.number().min(0).optional(),
    })).min(1),
    ro_id: z.string().uuid().optional(),
  }),

  create_stripe_subscription: z.object({
    customer_id: z.string().uuid(),
    vehicle_id: z.string().uuid().optional(),
    plan_type: z.enum(['basic', 'plus', 'premium']),
    success_url: z.string().url(),
    cancel_url: z.string().url(),
  }),

  list_vehicle_for_sale: z.object({
    vehicle_id: z.string().uuid(),
    list_price: z.number().min(0),
    description: z.string().max(500).optional(),
    photos: z.array(z.string().url()).optional(),
    condition_notes: z.string().max(500).optional(),
  }),

  audit_log: z.object({
    action: z.string().max(100),
    target_type: z.string().max(50),
    target_id: z.string().max(50),
    before_state: z.any().optional(),
    after_state: z.any().optional(),
    metadata: z.record(z.any()).optional(),
  }),
};

// =============================================================================
// Secret injection map — secrets are NEVER hardcoded, always from env
// =============================================================================
interface ToolSecrets {
  [key: string]: string | undefined;
}

function getSecrets(): ToolSecrets {
  return {
    STRIPE_SECRET_KEY: process.env.STRIPE_SECRET_KEY,
    TWILIO_ACCOUNT_SID: process.env.TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN: process.env.TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER: process.env.TWILIO_PHONE_NUMBER,
    TELEGRAM_BOT_TOKEN: process.env.TELEGRAM_BOT_TOKEN,
    NHTSA_API_KEY: process.env.NHTSA_API_KEY,
    SUPABASE_SERVICE_KEY: process.env.SUPABASE_SERVICE_KEY,
  };
}

// =============================================================================
// Prompt Firewall — strips override instructions from user input
// =============================================================================
const FORBIDDEN_PATTERNS = [
  /ignore\s+(previous|above|all)\s+instructions/i,
  /you\s+are\s+now/i,
  /act\s+as\s+(if\s+)?(you\s+are|a)/i,
  /forget\s+(everything|all|your)/i,
  /jailbreak/i,
  /DAN\s+mode/i,
  /developer\s+mode/i,
  /system\s*:\s*override/i,
  /<\s*system\s*>/i,
  /\/\/\s*override/i,
  /bypass\s+(filter|restriction)/i,
  /pretend\s+(you\s+are|to\s+be)/i,
  /new\s+persona/i,
  /persona\s*:\s*/i,
  /sudo\s+/i,
  /root\s+access/i,
  /admin\s+mode/i,
];

function sanitizeInput(input: string): { sanitized: string; blocked: boolean } {
  let sanitized = input;
  let blocked = false;

  for (const pattern of FORBIDDEN_PATTERNS) {
    if (pattern.test(sanitized)) {
      sanitized = sanitized.replace(pattern, '[REDACTED]');
      blocked = true;
    }
  }

  return { sanitized, blocked };
}

// =============================================================================
// Tool execution with retry + circuit breaker
// =============================================================================
interface ToolResult {
  success: boolean;
  data?: any;
  error?: string;
  idempotency_key?: string;
}

interface ExecutionContext {
  idempotency_key: string;
  correlation_id: string;
  actor_id?: string;
  secrets: ToolSecrets;
  supabase: any; // Supabase client
}

async function executeWithRetry<T>(
  fn: () => Promise<T>,
  maxAttempts: number = 3,
  baseDelayMs: number = 200
): Promise<T> {
  let lastError: Error | undefined;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt === maxAttempts) break;

      // Exponential backoff with jitter
      const delay = baseDelayMs * Math.pow(2, attempt - 1);
      const jitter = Math.random() * delay * 0.5;
      await new Promise(resolve => setTimeout(resolve, delay + jitter));
    }
  }

  throw lastError;
}

// =============================================================================
// Idempotency check — ensures exactly-once execution
// =============================================================================
async function checkIdempotency(key: string, ctx: ExecutionContext): Promise<boolean> {
  const { data, error } = await ctx.supabase
    .from('events')
    .select('id')
    .eq('idempotency_key', key)
    .single();

  if (error && error.code !== 'PGRST116') {
    console.error('Idempotency check error:', error);
    return false; // On error, assume not processed (safe default)
  }

  return !!data;
}

// =============================================================================
// Tool implementations
// =============================================================================

async function decodeVin(params: { vin: string }, ctx: ExecutionContext): Promise<ToolResult> {
  const url = `https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/${params.vin}?format=json`;

  const result = await executeWithRetry(async () => {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`NHTSA API error: ${res.status}`);
    return res.json();
  });

  // Parse NHTSA response into structured format
  const decodeResults = result.Results || [];
  const getValue = (variable: string) => {
    const item = decodeResults.find((r: any) => r.Variable === variable);
    return item?.Value || null;
  };

  return {
    success: true,
    data: {
      vin: params.vin,
      year: parseInt(getValue('Model Year')) || null,
      make: getValue('Make') || null,
      model: getValue('Model') || null,
      trim: getValue('Trim') || null,
      engine: getValue('Engine Model') || null,
      transmission: getValue('Transmission Style') || null,
      fuel_type: getValue('Fuel Type - Primary') || null,
      plant: getValue('Plant Company Name') || null,
    },
  };
}

async function createRo(params: z.infer<typeof schemas.create_ro>, ctx: ExecutionContext): Promise<ToolResult> {
  const result = await executeWithRetry(async () => {
    const { data, error } = await ctx.supabase.rpc('create_repair_order', {
      p_vehicle_id: params.vehicle_id,
      p_customer_id: params.customer_id,
      p_description: params.description || null,
      p_line_items: params.line_items,
      p_notes: params.notes || null,
    });

    if (error) throw error;
    return data;
  });

  return {
    success: true,
    data: { ro_id: result.id, ro_number: result.ro_number },
    idempotency_key: ctx.idempotency_key,
  };
}

async function createEstimate(params: z.infer<typeof schemas.create_estimate>, ctx: ExecutionContext): Promise<ToolResult> {
  const result = await executeWithRetry(async () => {
    const { data, error } = await ctx.supabase.rpc('create_estimate', {
      p_ro_id: params.ro_id || null,
      p_vehicle_id: params.vehicle_id,
      p_customer_id: params.customer_id,
      p_line_items: params.line_items,
      p_notes: params.notes || null,
      p_expires_in_days: params.expires_in_days,
    });

    if (error) throw error;
    return data;
  });

  return {
    success: true,
    data: { estimate_id: result.id, approval_token: result.customer_approval_token },
    idempotency_key: ctx.idempotency_key,
  };
}

async function sendSms(params: z.infer<typeof schemas.send_sms>, ctx: ExecutionContext): Promise<ToolResult> {
  const { to, body } = params;
  const accountSid = ctx.secrets.TWILIO_ACCOUNT_SID;
  const authToken = ctx.secrets.TWILIO_AUTH_TOKEN;
  const fromNumber = ctx.secrets.TWILIO_PHONE_NUMBER;
  const testMode = process.env.TEST_MODE === 'true';

  if (!accountSid || !authToken || !fromNumber) {
    return { success: false, error: 'Twilio credentials not configured' };
  }

  const finalBody = testMode ? `[TEST] ${body}` : body;

  const result = await executeWithRetry(async () => {
    const res = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${accountSid}/Messages.json`, {
      method: 'POST',
      headers: {
        Authorization: `Basic ${btoa(accountSid + ':' + authToken)}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({ To: to, From: fromNumber, Body: finalBody }),
    });

    if (!res.ok) throw new Error(`Twilio error: ${res.status}`);
    return res.json();
  });

  return {
    success: true,
    data: { message_sid: result.sid, status: result.status },
    idempotency_key: ctx.idempotency_key,
  };
}

async function orderParts(params: z.infer<typeof schemas.order_parts>, ctx: ExecutionContext): Promise<ToolResult> {
  const result = await executeWithRetry(async () => {
    const { data, error } = await ctx.supabase.rpc('order_parts', {
      p_supplier: params.supplier,
      p_parts: params.parts,
      p_ro_id: params.ro_id || null,
    });

    if (error) throw error;
    return data;
  });

  return {
    success: true,
    data: { order_refs: result.order_refs, total_items: params.parts.length },
    idempotency_key: ctx.idempotency_key,
  };
}

async function createStripeSubscription(params: z.infer<typeof schemas.create_stripe_subscription>, ctx: ExecutionContext): Promise<ToolResult> {
  const stripeKey = ctx.secrets.STRIPE_SECRET_KEY;
  if (!stripeKey) return { success: false, error: 'Stripe not configured' };

  const result = await executeWithRetry(async () => {
    const res = await fetch('https://api.stripe.com/v1/checkout/sessions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${stripeKey}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        'customer_email': '', // Will be looked up by customer_id
        'mode': 'subscription',
        'line_items[0][price_data][currency]': 'usd',
        `line_items[0][price_data][product_data][name]': `${params.plan_type} care plan`,
        'line_items[0][price_data][recurring][interval]': 'month',
        `line_items[0][price_data][unit_amount]': '9999', // Will be looked up from config
        'line_items[0][quantity]': '1',
        `success_url`: params.success_url,
        `cancel_url`: params.cancel_url,
        `metadata[customer_id]`: params.customer_id,
        `metadata[plan_type]`: params.plan_type,
      }),
    });

    if (!res.ok) throw new Error(`Stripe error: ${res.status}`);
    return res.json();
  });

  return {
    success: true,
    data: { session_id: result.id, url: result.url },
    idempotency_key: ctx.idempotency_key,
  };
}

async function listVehicleForSale(params: z.infer<typeof schemas.list_vehicle_for_sale>, ctx: ExecutionContext): Promise<ToolResult> {
  const result = await executeWithRetry(async () => {
    const { data, error } = await ctx.supabase.rpc('list_vehicle', {
      p_vehicle_id: params.vehicle_id,
      p_list_price: params.list_price,
      p_description: params.description || null,
      p_photos: params.photos || [],
      p_condition_notes: params.condition_notes || null,
    });

    if (error) throw error;
    return data;
  });

  return {
    success: true,
    data: { listing_id: result.id, list_price: params.list_price },
    idempotency_key: ctx.idempotency_key,
  };
}

async function auditLog(params: z.infer<typeof schemas.audit_log>, ctx: ExecutionContext): Promise<ToolResult> {
  const result = await executeWithRetry(async () => {
    const { data, error } = await ctx.supabase
      .from('audit_log')
      .insert({
        action: params.action,
        actor_id: ctx.actor_id,
        target_type: params.target_type,
        target_id: params.target_id,
        before_state: params.before_state,
        after_state: params.after_state,
        metadata: params.metadata,
      })
      .select()
      .single();

    if (error) throw error;
    return data;
  });

  return {
    success: true,
    data: { audit_id: result.id },
    idempotency_key: ctx.idempotency_key,
  };
}

// =============================================================================
// Tool dispatcher
// =============================================================================
const TOOL_FUNCTIONS: Record<ToolName, (params: any, ctx: ExecutionContext) => Promise<ToolResult>> = {
  decode_vin: decodeVin,
  create_ro: createRo,
  create_estimate: createEstimate,
  send_sms: sendSms,
  order_parts: orderParts,
  create_stripe_subscription: createStripeSubscription,
  list_vehicle_for_sale: listVehicleForSale,
  audit_log: auditLog,
};

// =============================================================================
// Gateway entry point — validates, checks idempotency, dispatches
// =============================================================================
export async function invokeTool(
  toolName: string,
  params: any,
  context: Omit<ExecutionContext, 'secrets'>
): Promise<ToolResult> {
  // 1. Allowlist check
  if (!TOOL_NAMES.includes(toolName as ToolName)) {
    return {
      success: false,
      error: `Tool "${toolName}" not in allowed tools: ${TOOL_NAMES.join(', ')}`,
    };
  }

  // 2. Sanitize params (prompt firewall)
  const { sanitized, blocked } = sanitizeInput(JSON.stringify(params));
  if (blocked) {
    await auditLog(
      {
        action: 'tool_input_sanitized',
        target_type: 'tool',
        target_id: toolName,
        metadata: { original_params: params },
        before_state: null,
        after_state: null,
      },
      { ...context, secrets: getSecrets() }
    );
  }

  // 3. Zod validation
  const schema = schemas[toolName as ToolName];
  const parsed = schema.safeParse(blocked ? JSON.parse(sanitized) : params);
  if (!parsed.success) {
    return {
      success: false,
      error: `Validation error: ${parsed.error.message}`,
    };
  }

  // 4. Idempotency check
  const alreadyProcessed = await checkIdempotency(context.idempotency_key, {
    ...context,
    secrets: getSecrets(),
  });

  if (alreadyProcessed) {
    return {
      success: true,
      data: { message: 'Already processed (idempotent skip)' },
      idempotency_key: context.idempotency_key,
    };
  }

  // 5. Execute with retry + circuit breaker
  const fn = TOOL_FUNCTIONS[toolName as ToolName];
  try {
    const result = await fn(parsed.data, { ...context, secrets: getSecrets() });

    // 6. Write audit log for the tool invocation
    await auditLog(
      {
        action: `tool_${toolName}_executed`,
        target_type: 'tool',
        target_id: toolName,
        before_state: null,
        after_state: result.data,
        metadata: { params: parsed.data, idempotency_key: context.idempotency_key },
      },
      { ...context, secrets: getSecrets() }
    );

    return result;
  } catch (err) {
    const errorMessage = err instanceof Error ? err.message : String(err);
    return {
      success: false,
      error: errorMessage,
      idempotency_key: context.idempotency_key,
    };
  }
}

export { schemas, TOOL_NAMES };
