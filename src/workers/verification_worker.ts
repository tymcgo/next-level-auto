/**
 * verification_worker.ts — runs as a cron-triggered Worker.
 * Polls outbox for completed entries and verifies required outcomes.
 */
export interface Env {
  SUPABASE_URL: string;
  SUPABASE_SERVICE_KEY: string;
}

export default {
  async scheduled(controller: ScheduledController, env: Env): Promise<void> {
    // Query outbox for unverified completed entries
    const r = await fetch(`${env.SUPABASE_URL}/rest/v1/outbox?status=eq.completed&verified=eq.false&limit=100`, {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    });
    const entries = await r.json();
    for (const entry of entries) {
      // Verify: for create_ro, check RO exists in shop system
      let verified = true;
      let note = '';
      if (entry.tool === 'create_ro') {
        const result = JSON.parse(entry.result);
        // In real impl: poll shop API for ro_id
        if (!result.ro_id) { verified = false; note = 'ro_id missing'; }
      }
      // Update outbox
      await fetch(`${env.SUPABASE_URL}/rest/v1/outbox?id=eq.${entry.id}`, {
        method: 'PATCH',
        headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ verified, verification_note: note, verified_at: new Date().toISOString() }),
      });
    }
  },
};
