// verification_worker.ts — Verification Worker
// Checks required_outcomes for workflow instances within SLA
// Moves to DLQ on failure, triggers notifications

export interface VerificationResult {
  workflow_id: string
  instance_id: string
  status: 'verified' | 'failed' | 'timeout'
  missing_outcomes: string[]
  sla_breach: boolean
  error?: string
}

export async function verifyWorkflowOutcomes(
  instanceId: string,
  outcomes: string[],
  supabase: any
): Promise<VerificationResult> {
  // Check each required outcome against database state
  const missing: string[] = []

  for (const outcome of outcomes) {
    const [table, condition] = outcome.split(':')
    if (!table || !condition) {
      missing.push(outcome)
      continue
    }

    // Build query based on condition
    // Format: "status = 'approved'" or "count > 0"
    const query = supabase.from(table).select('id')

    if (condition.includes('=')) {
      const [col, val] = condition.split('=').map((s: string) => s.trim().replace(/'/g, ''))
      query.eq(col, val)
    } else if (condition.includes('>')) {
      const [col, val] = condition.split('>').map((s: string) => s.trim())
      query.gt(col, parseInt(val))
    }

    const { data, error } = await query.limit(1)

    if (error || !data || data.length === 0) {
      missing.push(outcome)
    }
  }

  return {
    workflow_id: 'unknown',
    instance_id: instanceId,
    status: missing.length === 0 ? 'verified' : 'failed',
    missing_outcomes: missing,
    sla_breach: false,
  }
}

// DLQ handler — moves failed events to DLQ and notifies
export async function moveToDLQ(
  eventId: string,
  originalEvent: any,
  errorMessage: string,
  supabase: any,
  notifyFn: (msg: string, priority: string) => Promise<void>
): Promise<void> {
  // Insert into DLQ
  await supabase.from('event_dlq').insert({
    event_id: eventId,
    original_event: originalEvent,
    error_message: errorMessage,
    failed_at: new Date().toISOString(),
  })

  // Update queue status
  await supabase
    .from('event_queue')
    .update({ status: 'dlq' })
    .eq('event_id', eventId)

  // Notify owner
  await notifyFn(`DLQ: Event ${eventId.slice(0, 8)} failed — ${errorMessage}`, 'P0')
}

// Escalation check — runs every 15 minutes via cron
export async function checkEscalations(supabase: any, notifyFn: (msg: string, priority: string) => Promise<void>): Promise<number> {
  const now = new Date().toISOString()
  const fifteenMinutesAgo = new Date(Date.now() - 15 * 60000).toISOString()

  // Find pending approvals that haven't been actioned
  const { data: pendingApprovals } = await supabase
    .from('approvals')
    .select('*')
    .eq('status', 'pending')
    .lt('requested_at', fifteenMinutesAgo)
    .lt('escalation_count', 3)

  if (!pendingApprovals || pendingApprovals.length === 0) return 0

  for (const approval of pendingApprovals) {
    // Escalate
    const newCount = (approval.escalation_count || 0) + 1
    await supabase
      .from('approvals')
      .update({
        escalation_count: newCount,
        status: newCount >= 3 ? 'escalated' : 'pending',
      })
      .eq('id', approval.id)

    // Send escalation notification
    await notifyFn(
      `ESCALATION (x${newCount}): Approval needed for ${approval.target_type} ${approval.target_id?.slice(0, 8)} — SLA ${approval.required_by}`,
      'P0'
    )
  }

  return pendingApprovals.length
}

// Daily digest — runs at 8am and 4pm
export async function sendDailyDigest(supabase: any, notifyFn: (msg: string) => Promise<void>): Promise<void> {
  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString()

  // Gather stats
  const [ros, parts, approvals, subscriptions, vehicles, events] = await Promise.all([
    supabase.from('repair_orders').select('id', { count: 'exact' }).in('status', ['draft', 'pending_approval', 'approved', 'in_progress']),
    supabase.from('parts').select('id', { count: 'exact' }).in('status', ['pending', 'ordered']),
    supabase.from('approvals').select('id', { count: 'exact' }).eq('status', 'pending'),
    supabase.from('subscriptions').select('monthly_amount').eq('status', 'active'),
    supabase.from('vehicle_appraisals').select('id', { count: 'exact' }).in('status', ['listed', 'sale_pending']),
    supabase.from('events').select('id', { count: 'exact' }).gte('timestamp', todayStart),
  ])

  const mrr = subscriptions.data?.reduce((sum: number, s: any) => sum + (s.monthly_amount || 0), 0) || 0

  const message = [
    `📊 Daily Digest — ${now.toLocaleDateString()}`,
    ``,
    `🔧 Open ROs: ${ros.count || 0}`,
    `📦 Parts waiting: ${parts.count || 0}`,
    `⏳ Pending approvals: ${approvals.count || 0}`,
    `💳 MRR: $${mrr.toFixed(2)}`,
    `🚗 Vehicles for sale: ${vehicles.count || 0}`,
    `📋 Events today: ${events.count || 0}`,
  ].join('\n')

  await notifyFn(message)
}
