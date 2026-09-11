// cost_tracker.ts — Track LLM token usage and cost per event
// Runs as a Cloudflare Worker cron every hour

interface CostEntry {
  event_id: string
  model: string
  input_tokens: number
  output_tokens: number
  estimated_cost_usd: number
  timestamp: string
}

// Model pricing (USD per 1M tokens)
const MODEL_PRICING: Record<string, { input: number; output: number }> = {
  'ollama/llama3.2:latest': { input: 0, output: 0 },  // Free local
  'ollama/llama3.1:8b': { input: 0, output: 0 },
  'ollama/mistral:7b': { input: 0, output: 0 },
  'gpt-4o-mini': { input: 0.15, output: 0.60 },
  'gpt-4o': { input: 2.50, output: 10.00 },
  'claude-3-5-sonnet': { input: 3.00, output: 15.00 },
  'claude-3-haiku': { input: 0.25, output: 1.25 },
}

export function estimateCost(model: string, inputTokens: number, outputTokens: number): number {
  const pricing = MODEL_PRICING[model] || { input: 0, output: 0 }
  return ((inputTokens * pricing.input) + (outputTokens * pricing.output)) / 1_000_000
}

export async function trackCost(entry: CostEntry, supabase: any): Promise<void> {
  await supabase.from('events').update({
    cost_tokens: {
      input_tokens: entry.input_tokens,
      output_tokens: entry.output_tokens,
      model: entry.model,
      estimated_cost_usd: entry.estimated_cost_usd,
    },
  }).eq('id', entry.event_id)
}

// Daily cost summary
export async function getDailyCostSummary(supabase: any, date: string): Promise<{
  total_cost: number
  total_events: number
  by_model: Record<string, { tokens: number; cost: number }>
}> {
  const { data } = await supabase
    .from('events')
    .select('cost_tokens')
    .gte('timestamp', `${date}T00:00:00`)
    .lt('timestamp', `${date}T23:59:59`)

  let totalCost = 0
  const byModel: Record<string, { tokens: number; cost: number }> = {}

  for (const event of data || []) {
    const ct = event.cost_tokens
    if (!ct) continue

    totalCost += ct.estimated_cost_usd || 0

    if (!byModel[ct.model]) {
      byModel[ct.model] = { tokens: 0, cost: 0 }
    }
    byModel[ct.model].tokens += (ct.input_tokens || 0) + (ct.output_tokens || 0)
    byModel[ct.model].cost += ct.estimated_cost_usd || 0
  }

  return {
    total_cost: totalCost,
    total_events: data?.length || 0,
    by_model: byModel,
  }
}
