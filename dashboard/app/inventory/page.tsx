'use client'

import { useState, useEffect } from 'react'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL || '',
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''
)

export default function InventoryPage() {
  const [parts, setParts] = useState<any[]>([])
  const [orders, setOrders] = useState<any[]>([])

  useEffect(() => {
    fetchInventory()
    fetchOrders()
  }, [])

  async function fetchInventory() {
    const { data } = await supabase
      .from('parts')
      .select('*, ro:repair_orders(ro_number)')
      .order('status', { ascending: true })
      .limit(100)
    setParts(data || [])
  }

  async function fetchOrders() {
    const { data } = await supabase
      .from('parts')
      .select('*')
      .eq('status', 'ordered')
      .order('created_at', { ascending: false })
    setOrders(data || [])
  }

  const statusColors: Record<string, string> = {
    pending: 'bg-gray-600/20 text-gray-400',
    ordered: 'bg-blue-600/20 text-blue-400',
    received: 'bg-green-600/20 text-green-400',
    installed: 'bg-purple-600/20 text-purple-400',
    returned: 'bg-red-600/20 text-red-400',
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Inventory</h1>

      {/* Parts on Order */}
      {orders.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <h2 className="text-lg font-semibold mb-4">Parts on Order ({orders.length})</h2>
          <div className="space-y-2">
            {orders.map(order => (
              <div key={order.id} className="flex items-center justify-between py-2 border-b border-gray-800">
                <div>
                  <span className="text-sm font-medium">{order.name}</span>
                  <span className="text-xs text-gray-500 ml-2">{order.supplier}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm">{order.quantity}x</span>
                  <span className="text-sm font-mono">${order.unit_cost?.toFixed(2)}</span>
                  <span className={`text-xs px-2 py-1 rounded ${statusColors[order.status]}`}>
                    {order.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* All Parts */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-lg font-semibold mb-4">All Parts</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-800">
              <th className="pb-2">Part</th>
              <th className="pb-2">RO</th>
              <th className="pb-2 text-right">Qty</th>
              <th className="pb-2 text-right">Cost</th>
              <th className="pb-2 text-right">Price</th>
              <th className="pb-2 text-center">Status</th>
            </tr>
          </thead>
          <tbody>
            {parts.map(part => (
              <tr key={part.id} className="border-b border-gray-800">
                <td className="py-2">
                  <div className="font-medium">{part.name}</div>
                  <div className="text-xs text-gray-500">{part.sku || '—'}</div>
                </td>
                <td className="py-2 text-gray-400 font-mono text-xs">
                  {part.ro?.ro_number || '—'}
                </td>
                <td className="py-2 text-right">{part.quantity}</td>
                <td className="py-2 text-right font-mono">${part.unit_cost?.toFixed(2)}</td>
                <td className="py-2 text-right font-mono">${part.unit_price?.toFixed(2)}</td>
                <td className="py-2 text-center">
                  <span className={`text-xs px-2 py-1 rounded ${statusColors[part.status] || 'bg-gray-800 text-gray-400'}`}>
                    {part.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
