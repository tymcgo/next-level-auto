/**
 * dlq_worker.ts — reprocess failed moments from the DLQ.
 * Triggered manually or via cron. Attempts retry up to max_retries.
 */
export interface Env {
  SUPABASE_URL: string;
  SUPABASE_SERVICE_KEY: string;
  GATEWAY_URL: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('POST only', { status: 405 });
    const { idempotency_key } = await req.json();
    // Fetch from DLQ
    const r = await fetch(`${env.SUPABASE_URL}/rest/v1/failed_moments?idempotency_key=eq.${idempotency_key}&select=*`, {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    });
    const entries = await r.json();
    if (!entries.length) return Response.json({ error: 'not_found' }, { status: 404 });
    const entry = entries[0];
    if (entry.retry_count >= 3) return Response.json({ error: 'max_retries_exhausted' }, { status: 410 });
    // Re-post to gateway
    const res = await fetch(`${env.GATEWAY_URL}/tool`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool: entry.tool, args: JSON.parse(entry.args), idempotency_key }),
    });
    if (res.ok) {
      await fetch(`${env.SUPABASE_URL}/rest/v1/failed_moments?idempotency_key=eq.${idempotency_key}`, {
        method: 'PATCH',
        headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ retry_count: entry.retry_count + 1, last_retry_at: new Date().toISOString() }),
      });
      return Response.json({ status: 'retried' });
    }
    return Response.json({ status: 'retry_failed', http: res.status });
  },
};
