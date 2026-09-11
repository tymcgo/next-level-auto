'use client'

import { useState, useEffect } from 'react'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL || '',
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''
)

const RO_STATUSES = ['draft', 'pending_approval', 'approved', 'in_progress', 'completed', 'closed']

interface RepairOrder {
  id: string
  ro_number: string
  status: string
  total_amount: number
  description: string
  created_at: string
  vehicle: { vin: string; year: number; make: string; model: string }
  customer: { name: string }
}

export default function ROPage() {
  const [ros, setRos] = useState<RepairOrder[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchROs()
  }, [])

  async function fetchROs() {
    const { data } = await supabase
      .from('repair_orders')
      .select('*, vehicle:vehicles(vin, year, make, model), customer:customers(name)')
      .order('created_at', { ascending: false })
      .limit(50)
    setRos(data || [])
    setLoading(false)
  }

  function groupByStatus(ros: RepairOrder[]) {
    const groups: Record<string, RepairOrder[]> = {}
    RO_STATUSES.forEach(s => { groups[s] = [] })
    ros.forEach(ro => {
      if (groups[ro.status]) groups[ro.status].push(ro)
    })
    return groups
  }

  const grouped = groupByStatus(ros)

  if (loading) return <div className="text-gray-500">Loading...</div>

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Repair Orders — Kanban</h1>
      <div className="flex gap-4 overflow-x-auto pb-4">
        {RO_STATUSES.map(status => (
          <div key={status} className="min-w-[280px] flex-1 bg-gray-900 rounded-xl border border-gray-800 p-3">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-300 uppercase">{status.replace('_', ' ')}</h3>
              <span className="text-xs bg-gray-800 px-2 py-1 rounded text-gray-400">
                {grouped[status].length}
              </span>
            </div>
            <div className="space-y-2">
              {grouped[status].map(ro => (
                <div key={ro.id} className="bg-gray-800 rounded-lg p-3 border border-gray-700 hover:border-blue-600 transition-colors cursor-pointer">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-mono text-blue-400">{ro.ro_number}</span>
                    <span className="text-sm font-semibold">${ro.total_amount?.toFixed(0)}</span>
                  </div>
                  <p className="text-xs text-gray-400">
                    {ro.vehicle?.year} {ro.vehicle?.make} {ro.vehicle?.model}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">{ro.customer?.name}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
