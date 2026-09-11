'use client'

import { useState, useEffect } from 'react'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL || '',
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''
)

interface DashboardStats {
  openROs: number
  pendingApprovals: number
  partsWaiting: number
  mrr: number
  vehiclesForSale: number
  todayEvents: number
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats>({
    openROs: 0,
    pendingApprovals: 0,
    partsWaiting: 0,
    mrr: 0,
    vehiclesForSale: 0,
    todayEvents: 0,
  })
  const [recentEvents, setRecentEvents] = useState<any[]>([])

  useEffect(() => {
    fetchStats()
    fetchRecentEvents()
  }, [])

  async function fetchStats() {
    const [ros, approvals, parts, subs, vehicles, events] = await Promise.all([
      supabase.from('repair_orders').select('id', { count: 'exact' }).neq('status', 'closed'),
      supabase.from('approvals').select('id', { count: 'exact' }).eq('status', 'pending'),
      supabase.from('parts').select('id', { count: 'exact' }).eq('status', 'ordered'),
      supabase.from('subscriptions').select('monthly_amount').eq('status', 'active'),
      supabase.from('vehicles').select('id', { count: 'exact' }).eq('status', 'for_sale'),
      supabase.from('events').select('id', { count: 'exact' }).gte('timestamp', new Date(Date.now() - 86400000).toISOString()),
    ])

    setStats({
      openROs: ros.count || 0,
      pendingApprovals: approvals.count || 0,
      partsWaiting: parts.count || 0,
      mrr: subs.data?.reduce((sum, s) => sum + (s.monthly_amount || 0), 0) || 0,
      vehiclesForSale: vehicles.count || 0,
      todayEvents: events.count || 0,
    })
  }

  async function fetchRecentEvents() {
    const { data } = await supabase
      .from('events')
      .select('*')
      .order('timestamp', { ascending: false })
      .limit(10)
    setRecentEvents(data || [])
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <span className="px-3 py-1 bg-yellow-600/20 text-yellow-400 text-xs rounded-full border border-yellow-600/30">
          TEST MODE
        </span>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard title="Open ROs" value={stats.openROs} icon="🔧" color="blue" />
        <StatCard title="Pending Approvals" value={stats.pendingApprovals} icon="⏳" color="yellow" />
        <StatCard title="Parts Waiting" value={stats.partsWaiting} icon="📦" color="orange" />
        <StatCard title="Monthly Recurring" value={`$${stats.mrr.toFixed(2)}`} icon="💳" color="green" />
        <StatCard title="Vehicles for Sale" value={stats.vehiclesForSale} icon="🚗" color="purple" />
        <StatCard title="Events Today" value={stats.todayEvents} icon="📊" color="cyan" />
      </div>

      {/* Recent Events */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-lg font-semibold mb-4">Recent Events</h2>
        <div className="space-y-2">
          {recentEvents.length === 0 ? (
            <p className="text-gray-500 text-sm">No events yet</p>
          ) : (
            recentEvents.map((event) => (
              <div key={event.id} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
                <div className="flex items-center gap-3">
                  <span className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-400">
                    {event.event_type}
                  </span>
                  <span className="text-sm text-gray-300">
                    {event.vin_last6}
                  </span>
                </div>
                <span className="text-xs text-gray-500">
                  {new Date(event.timestamp).toLocaleString()}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

function StatCard({ title, value, icon, color }: { title: string; value: string | number; icon: string; color: string }) {
  const colorMap: Record<string, string> = {
    blue: 'from-blue-600/20 to-blue-600/5 border-blue-600/30',
    yellow: 'from-yellow-600/20 to-yellow-600/5 border-yellow-600/30',
    orange: 'from-orange-600/20 to-orange-600/5 border-orange-600/30',
    green: 'from-green-600/20 to-green-600/5 border-green-600/30',
    purple: 'from-purple-600/20 to-purple-600/5 border-purple-600/30',
    cyan: 'from-cyan-600/20 to-cyan-600/5 border-cyan-600/30',
  }

  return (
    <div className={`bg-gradient-to-br ${colorMap[color]} border rounded-xl p-4`}>
      <div className="flex items-center justify-between">
        <span className="text-2xl">{icon}</span>
        <span className="text-2xl font-bold">{value}</span>
      </div>
      <p className="text-sm text-gray-400 mt-2">{title}</p>
    </div>
  )
}
