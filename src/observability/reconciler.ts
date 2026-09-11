// reconciler.ts — Nightly reconciliation: events vs shop system vs Stripe
// Runs as a cron job at 2am CST

interface ReconciliationResult {
  date: string
  total_events: number
  total_ros: number
  total_estimates: number
  total_parts_orders: number
  total_subscriptions: number
  stripe_payments: number
  discrepancies: Discrepancy[]
  status: 'clean' | 'warnings' | 'critical'
}

interface Discrepancy {
  type: 'missing_payment' | 'orphan_event' | 'amount_mismatch' | 'duplicate_ro'
  severity: 'low' | 'medium' | 'high'
  description: string
  event_id?: string
  ro_id?: string
  expected?: any
  actual?: any
}

export async function runReconciliation(supabase: any, stripeKey: string): Promise<ReconciliationResult> {
  const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0]
  const startOfDay = `${yesterday}T00:00:00-06:00`
  const endOfDay = `${yesterday}T23:59:59-06:00`

  // Fetch all events from yesterday
  const { data: events } = await supabase
    .from('events')
    .select('*')
    .gte('timestamp', startOfDay)
    .lt('timestamp', endOfDay)

  // Fetch all ROs created yesterday
  const { data: ros } = await supabase
    .from('repair_orders')
    .select('*')
    .gte('created_at', startOfDay)
    .lt('created_at', endOfDay)

  // Fetch all estimates created yesterday
  const { data: estimates } = await supabase
    .from('estimates')
    .select('*')
    .gte('created_at', startOfDay)
    .lt('created_at', endOfDay)

  // Fetch all parts ordered yesterday
  const { data: partsOrders } = await supabase
    .from('parts')
    .select('*')
    .gte('ordered_at', startOfDay)
    .lt('ordered_at', endOfDay)

  // Fetch all subscriptions created yesterday
  const { data: subscriptions } = await supabase
    .from('subscriptions')
    .select('*')
    .gte('created_at', startOfDay)
    .lt('created_at', endOfDay)

  // Fetch Stripe payments from yesterday
  const stripePayments = await fetchStripePayments(stripeKey, yesterday)

  const discrepancies: Discrepancy[] = []

  // Check 1: Every payment_received event should have a matching Stripe payment
  const paymentEvents = events?.filter(e => e.event_type === 'payment_received') || []
  for (const event of paymentEvents) {
    const match = stripePayments.find((p: any) => 
      p.metadata?.event_id === event.id || p.amount === event.normalized?.amount
    )
    if (!match) {
      discrepancies.push({
        type: 'missing_payment',
        severity: 'high',
        description: `Payment event ${event.id} has no matching Stripe payment`,
        event_id: event.id,
        expected: event.normalized?.amount,
      })
    }
  }

  // Check 2: Every Stripe payment should have a matching event
  for (const payment of stripePayments) {
    const match = events?.find(e => 
      e.event_type === 'payment_received' && e.normalized?.stripe_payment_id === payment.id
    )
    if (!match) {
      discrepancies.push({
        type: 'orphan_event',
        severity: 'medium',
        description: `Stripe payment ${payment.id} has no matching event`,
        actual: payment.amount,
      })
    }
  }

  // Check 3: RO totals should match sum of line items
  for (const ro of ros || []) {
    const { data: lineItems } = await supabase
      .from('estimates')
      .select('line_items')
      .eq('ro_id', ro.id)
      .single()

    if (lineItems?.line_items) {
      const calculated = lineItems.line_items.reduce((sum: number, item: any) => {
        return sum + ((item.labor_hours || 0) * 125) + (item.parts_cost || 0)
      }, 0)
      if (Math.abs(calculated - (ro.total_amount || 0)) > 0.01) {
        discrepancies.push({
          type: 'amount_mismatch',
          severity: 'high',
          description: `RO ${ro.ro_number} total mismatch`,
          ro_id: ro.id,
          expected: calculated,
          actual: ro.total_amount,
        })
      }
    }
  }

  // Check 4: Duplicate ROs for same VIN on same day
  const vinRoMap: Record<string, number> = {}
  for (const ro of ros || []) {
    const { data: vehicle } = await supabase
      .from('vehicles')
      .select('vin')
      .eq('id', ro.vehicle_id)
      .single()
    
    if (vehicle) {
      const key = `${vehicle.vin}_${yesterday}`
      vinRoMap[key] = (vinRoMap[key] || 0) + 1
    }
  }
  for (const [key, count] of Object.entries(vinRoMap)) {
    if (count > 3) {
      discrepancies.push({
        type: 'duplicate_ro',
        severity: 'low',
        description: `VIN ${key} has ${count} ROs in one day`,
      })
    }
  }

  const criticalCount = discrepancies.filter(d => d.severity === 'high').length
  const status = criticalCount > 0 ? 'critical' : discrepancies.length > 0 ? 'warnings' : 'clean'

  return {
    date: yesterday,
    total_events: events?.length || 0,
    total_ros: ros?.length || 0,
    total_estimates: estimates?.length || 0,
    total_parts_orders: partsOrders?.length || 0,
    total_subscriptions: subscriptions?.length || 0,
    stripe_payments: stripePayments.length,
    discrepancies,
    status,
  }
}

async function fetchStripePayments(stripeKey: string, date: string): Promise<any[]> {
  if (!stripeKey) return []

  const startTs = Math.floor(new Date(`${date}T00:00:00-06:00`).getTime() / 1000)
  const endTs = Math.floor(new Date(`${date}T23:59:59-06:00`).getTime() / 1000)

  const res = await fetch(`https://api.stripe.com/v1/payment_intents?created[gte]=${startTs}&created[lte]=${endTs}&limit=100`, {
    headers: { Authorization: `Bearer ${stripeKey}` },
  })

  if (!res.ok) return []
  const data = await res.json()
  return data.data || []
}
