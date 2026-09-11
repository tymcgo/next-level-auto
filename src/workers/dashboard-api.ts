// dashboard-api.ts — Cloudflare Worker for Next.js Dashboard API
// Serves data to the frontend from Supabase

export interface Env {
  SUPABASE_URL: string
  SUPABASE_SERVICE_KEY: string
}

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS_HEADERS })
    }

    const url = new URL(request.url)
    const path = url.pathname

    try {
      let result: any

      switch (path) {
        case '/api/stats':
          result = await getDashboardStats(env)
          break
        case '/api/events':
          result = await getRecentEvents(url.searchParams, env)
          break
        case '/api/ros':
          result = await getRepairOrders(url.searchParams, env)
          break
        case '/api/inventory':
          result = await getInventory(env)
          break
        case '/api/subscriptions':
          result = await getSubscriptions(env)
          break
        case '/api/lot':
          result = await getLotListings(env)
          break
        case '/api/credits':
          result = await getCustomerCredits(env)
          break
        case '/api/audit':
          result = await getAuditLog(url.searchParams, env)
          break
        default:
          return new Response('Not found', { status: 404, headers: CORS_HEADERS })
      }

      return new Response(JSON.stringify(result), {
        headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
      })
    } catch (err) {
      console.error('API error:', err)
      return new Response(JSON.stringify({ error: 'Internal server error' }), {
        status: 500,
        headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
      })
    }
  },
}

async function getDashboardStats(env: Env) {
  const [ros, approvals, parts, subs, vehicles, events] = await Promise.all([
    fetch(`${env.SUPABASE_URL}/rest/v1/repair_orders?status=neq.closed&select=id`, {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    }).then(r => r.json()),
    fetch(`${env.SUPABASE_URL}/rest/v1/approvals?status=eq.pending&select=id`, {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    }).then(r => r.json()),
    fetch(`${env.SUPABASE_URL}/rest/v1/parts?status=in.(pending,ordered)&select=id`, {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    }).then(r => r.json()),
    fetch(`${env.SUPABASE_URL}/rest/v1/subscriptions?status=eq.active&select=monthly_amount`, {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    }).then(r => r.json()),
    fetch(`${env.SUPABASE_URL}/rest/v1/vehicle_appraisals?status=in.(listed,sale_pending)&select=id`, {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    }).then(r => r.json()),
    fetch(`${env.SUPABASE_URL}/rest/v1/events?timestamp=gte.${new Date(Date.now() - 86400000).toISOString()}&select=id`, {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    }).then(r => r.json()),
  ])

  return {
    openROs: ros.length,
    pendingApprovals: approvals.length,
    partsWaiting: parts.length,
    mrr: subs.reduce((sum: number, s: any) => sum + (s.monthly_amount || 0), 0),
    vehiclesForSale: vehicles.length,
    todayEvents: events.length,
  }
}

async function getRecentEvents(params: URLSearchParams, env: Env) {
  const limit = params.get('limit') || '20'
  const res = await fetch(
    `${env.SUPABASE_URL}/rest/v1/events?order=timestamp.desc&limit=${limit}`,
    {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    }
  )
  return res.json()
}

async function getRepairOrders(params: URLSearchParams, env: Env) {
  const status = params.get('status') || 'neq.closed'
  const res = await fetch(
    `${env.SUPABASE_URL}/rest/v1/repair_orders?status=${status}&select=*,vehicle:vehicles(vin,year,make,model),customer:customers(name)&order=created_at.desc&limit=50`,
    {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    }
  )
  return res.json()
}

async function getInventory(env: Env) {
  const res = await fetch(
    `${env.SUPABASE_URL}/rest/v1/parts?select=*,ro:repair_orders(ro_number)&order=status.asc&limit=100`,
    {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    }
  )
  return res.json()
}

async function getSubscriptions(env: Env) {
  const res = await fetch(
    `${env.SUPABASE_URL}/rest/v1/subscriptions?select=*,customer:customers(name),vehicle:vehicles(vin)&order=created_at.desc`,
    {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    }
  )
  return res.json()
}

async function getLotListings(env: Env) {
  const res = await fetch(
    `${env.SUPABASE_URL}/rest/v1/vehicle_appraisals?status=in.(listed,sale_pending)&select=*,vehicle:vehicles(vin,year,make,model,mileage)&order=created_at.desc`,
    {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    }
  )
  return res.json()
}

async function getCustomerCredits(env: Env) {
  const res = await fetch(
    `${env.SUPABASE_URL}/rest/v1/customer_credits?select=*,customer:customers(name),vehicle:vehicles(vin)&order=created_at.desc`,
    {
      headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
    }
  )
  return res.json()
}

async function getAuditLog(params: URLSearchParams, env: Env) {
  const target = params.get('target') || ''
  const action = params.get('action') || ''
  let query = `${env.SUPABASE_URL}/rest/v1/audit_log?order=created_at.desc&limit=200`

  if (target) query += `&target_type=eq.${target}`
  if (action) query += `=action=ilike.*${action}*`

  const res = await fetch(query, {
    headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` },
  })
  return res.json()
}
