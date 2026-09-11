'use client'

import { useState, useEffect } from 'react'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL || '',
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''
)

export default function CreditsPage() {
  const [credits, setCredits] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchCredits()
  }, [])

  async function fetchCredits() {
    const { data } = await supabase
      .from('customer_credits')
      .select('*, customer:customers(name), vehicle:vehicles(vin)')
      .order('created_at', { ascending: false })
    setCredits(data || [])
    setLoading(false)
  }

  const totalRemaining = credits.reduce((sum, c) => sum + (c.amount_remaining || 0), 0)
  const totalOriginal = credits.reduce((sum, c) => sum + (c.amount_original || 0), 0)

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Customer Credits</h1>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <div className="text-2xl font-bold text-blue-400">${totalOriginal.toFixed(2)}</div>
          <div className="text-sm text-gray-400">Total Issued</div>
        </div>
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <div className="text-2xl font-bold text-green-400">${totalRemaining.toFixed(2)}</div>
          <div className="text-sm text-gray-400">Remaining</div>
        </div>
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <div className="text-2xl font-bold text-purple-400">{((totalRemaining / totalOriginal) * 100 || 0).toFixed(1)}%</div>
          <div className="text-sm text-gray-400">Utilization</div>
        </div>
      </div>

      {/* Credits Table */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-lg font-semibold mb-4">All Credits</h2>
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : credits.length === 0 ? (
          <p className="text-gray-500">No credits issued yet</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-800">
                <th className="pb-2">Customer</th>
                <th className="pb-2">Vehicle</th>
                <th className="pb-2">Type</th>
                <th className="pb-2 text-right">Original</th>
                <th className="pb-2 text-right">Remaining</th>
                <th className="pb-2">Expires</th>
              </tr>
            </thead>
            <tbody>
              {credits.map(credit => (
                <tr key={credit.id} className="border-b border-gray-800">
                  <td className="py-2">{credit.customer?.name || '—'}</td>
                  <td className="py-2 text-gray-400 font-mono text-xs">{credit.vehicle?.vin || '—'}</td>
                  <td className="py-2">
                    <span className={`px-2 py-1 rounded text-xs ${
                      credit.credit_type === 'package' ? 'bg-blue-600/20 text-blue-400' :
                      credit.credit_type === 'labor' ? 'bg-green-600/20 text-green-400' :
                      'bg-gray-600/20 text-gray-400'
                    }`}>
                      {credit.credit_type}
                    </span>
                  </td>
                  <td className="py-2 text-right font-mono">${credit.amount_original?.toFixed(2)}</td>
                  <td className="py-2 text-right font-mono">${credit.amount_remaining?.toFixed(2)}</td>
                  <td className="py-2 text-gray-500 text-xs">
                    {credit.expires_at ? new Date(credit.expires_at).toLocaleDateString() : 'Never'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
