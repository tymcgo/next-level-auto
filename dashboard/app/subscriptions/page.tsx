'use client'

import { useState, useEffect } from 'react'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL || '',
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''
)

export default function SubscriptionsPage() {
  const [subs, setSubs] = useState<any[]>([])
  const [stats, setStats] = useState({ total: 0, mrr: 0, active: 0, cancelled: 0 })

  useEffect(() => {
    fetchSubscriptions()
  }, [])

  async function fetchSubscriptions() {
    const { data } = await supabase
      .from('subscriptions')
      .select('*, customer:customers(name), vehicle:vehicles(vin, year, make, model)')
      .order('created_at', { ascending: false })

    const allSubs = data || []
    setSubs(allSubs)
    setStats({
      total: allSubs.length,
      mrr: allSubs.filter(s => s.status === 'active').reduce((sum, s) => sum + (s.monthly_amount || 0), 0),
      active: allSubs.filter(s => s.status === 'active').length,
      cancelled: allSubs.filter(s => s.status === 'cancelled').length,
    })
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Subscriptions</h1>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <div className="text-2xl font-bold text-green-400">${stats.mrr.toFixed(0)}</div>
          <div className="text-sm text-gray-400">Monthly Revenue</div>
        </div>
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <div className="text-2xl font-bold text-blue-400">{stats.active}</div>
          <div className="text-sm text-gray-400">Active</div>
        </div>
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <div className="text-2xl font-bold text-yellow-400">{stats.total}</div>
          <div className="text-sm text-gray-400">Total</div>
        </div>
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <div className="text-2xl font-bold text-red-400">{stats.cancelled}</div>
          <div className="text-sm text-gray-400">Cancelled</div>
        </div>
      </div>

      {/* MRR Chart Placeholder */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-lg font-semibold mb-4">MRR Over Time</h2>
        <div className="h-48 flex items-center justify-center text-gray-500">
          📈 Chart placeholder — connect recharts in production
        </div>
      </div>

      {/* Subscriptions Table */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-lg font-semibold mb-4">All Subscriptions</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-800">
              <th className="pb-2">Customer</th>
              <th className="pb-2">Vehicle</th>
              <th className="pb-2">Plan</th>
              <th className="pb-2 text-right">Monthly</th>
              <th className="pb-2 text-center">Status</th>
              <th className="pb-2">Started</th>
            </tr>
          </thead>
          <tbody>
            {subs.map(sub => (
              <tr key={sub.id} className="border-b border-gray-800">
                <td className="py-2">{sub.customer?.name || '—'}</td>
                <td className="py-2 text-gray-400">
                  {sub.vehicle ? `${sub.vehicle.year} ${sub.vehicle.make}` : '—'}
                </td>
                <td className="py-2">
                  <span className={`px-2 py-1 rounded text-xs ${
                    sub.plan_type === 'premium' ? 'bg-purple-600/20 text-purple-400' :
                    sub.plan_type === 'plus' ? 'bg-blue-600/20 text-blue-400' :
                    'bg-gray-600/20 text-gray-400'
                  }`}>
                    {sub.plan_type}
                  </span>
                </td>
                <td className="py-2 text-right font-mono">${sub.monthly_amount?.toFixed(2)}</td>
                <td className="py-2 text-center">
                  <span className={`text-xs px-2 py-1 rounded ${
                    sub.status === 'active' ? 'bg-green-600/20 text-green-400' :
                    sub.status === 'cancelled' ? 'bg-red-600/20 text-red-400' :
                    'bg-gray-600/20 text-gray-400'
                  }`}>
                    {sub.status}
                  </span>
                </td>
                <td className="py-2 text-gray-500 text-xs">
                  {sub.started_at ? new Date(sub.started_at).toLocaleDateString() : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
