'use client'

import { useState, useEffect } from 'react'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL || '',
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''
)

export default function AuditPage() {
  const [entries, setEntries] = useState<any[]>([])
  const [filter, setFilter] = useState({ target_type: '', action: '', date_from: '', date_to: '' })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchAuditLog()
  }, [])

  async function fetchAuditLog() {
    let query = supabase
      .from('audit_log')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(200)

    if (filter.target_type) query = query.eq('target_type', filter.target_type)
    if (filter.action) query = query.ilike('action', `%${filter.action}%`)
    if (filter.date_from) query = query.gte('created_at', filter.date_from)
    if (filter.date_to) query = query.lte('created_at', filter.date_to)

    const { data } = await query
    setEntries(data || [])
    setLoading(false)
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Audit Log</h1>
      <p className="text-sm text-gray-500">Append-only. All system actions are recorded here.</p>

      {/* Filters */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <input
            type="text"
            placeholder="Target type..."
            value={filter.target_type}
            onChange={e => setFilter({ ...filter, target_type: e.target.value })}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
          />
          <input
            type="text"
            placeholder="Action..."
            value={filter.action}
            onChange={e => setFilter({ ...filter, action: e.target.value })}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
          />
          <input
            type="date"
            value={filter.date_from}
            onChange={e => setFilter({ ...filter, date_from: e.target.value })}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
          />
          <button
            onClick={fetchAuditLog}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm"
          >
            Apply Filters
          </button>
        </div>
      </div>

      {/* Audit Entries */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : entries.length === 0 ? (
          <p className="text-gray-500">No audit entries found</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-800">
                <th className="pb-2">Time</th>
                <th className="pb-2">Action</th>
                <th className="pb-2">Target</th>
                <th className="pb-2">Actor</th>
                <th className="pb-2">Before</th>
                <th className="pb-2">After</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(entry => (
                <tr key={entry.id} className="border-b border-gray-800">
                  <td className="py-2 text-xs text-gray-500">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td className="py-2">
                    <span className="px-2 py-1 bg-gray-800 rounded text-xs font-mono">
                      {entry.action}
                    </span>
                  </td>
                  <td className="py-2 text-gray-400 text-xs">
                    {entry.target_type}#{entry.target_id?.slice(0, 8)}
                  </td>
                  <td className="py-2 text-gray-400 text-xs">{entry.actor_id || 'system'}</td>
                  <td className="py-2 text-xs font-mono text-gray-500 max-w-[150px] truncate">
                    {entry.before_state ? JSON.stringify(entry.before_state).slice(0, 50) : '—'}
                  </td>
                  <td className="py-2 text-xs font-mono text-gray-500 max-w-[150px] truncate">
                    {entry.after_state ? JSON.stringify(entry.after_state).slice(0, 50) : '—'}
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
