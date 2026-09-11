'use client'

import { useState, useEffect } from 'react'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL || '',
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || ''
)

export default function LotPage() {
  const [listings, setListings] = useState<any[]>([])
  const [appraisals, setAppraisals] = useState<any[]>([])

  useEffect(() => {
    fetchListings()
    fetchAppraisals()
  }, [])

  async function fetchListings() {
    const { data } = await supabase
      .from('vehicle_appraisals')
      .select('*, vehicle:vehicles(vin, year, make, model, mileage)')
      .in('status', ['listed', 'sale_pending'])
      .order('created_at', { ascending: false })
    setListings(data || [])
  }

  async function fetchAppraisals() {
    const { data } = await supabase
      .from('vehicle_appraisals')
      .select('*')
      .eq('status', 'pending')
      .order('created_at', { ascending: false })
    setAppraisals(data || [])
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Buy/Sell Lot</h1>
        <button className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg text-sm">
          + New Appraisal
        </button>
      </div>

      {/* Pending Appraisals */}
      {appraisals.length > 0 && (
        <div className="bg-yellow-900/20 rounded-xl border border-yellow-600/30 p-4">
          <h2 className="text-lg font-semibold mb-4 text-yellow-400">Pending Appraisals ({appraisals.length})</h2>
          <div className="space-y-3">
            {appraisals.map(app => (
              <div key={app.id} className="flex items-center justify-between bg-gray-900 rounded-lg p-3">
                <div>
                  <span className="font-medium">{app.vin}</span>
                  <span className="text-xs text-gray-500 ml-2">{app.condition_rating}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-sm">Est: ${app.estimated_value?.toLocaleString()}</span>
                  <span className="text-sm">Ask: ${app.list_price?.toLocaleString()}</span>
                  <button className="px-3 py-1 bg-blue-600 rounded text-xs">Approve</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Listed Vehicles */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h2 className="text-lg font-semibold mb-4">Listed Vehicles ({listings.length})</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {listings.map(listing => (
            <div key={listing.id} className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
              {/* Photo placeholder */}
              <div className="h-32 bg-gray-700 flex items-center justify-center text-gray-500">
                {listing.photos?.[0] ? (
                  <img src={listing.photos[0]} className="w-full h-full object-cover" />
                ) : (
                  <span>📷 No photos</span>
                )}
              </div>
              <div className="p-3">
                <div className="font-medium">
                  {listing.vehicle?.year} {listing.vehicle?.make} {listing.vehicle?.model}
                </div>
                <div className="text-sm text-gray-400">
                  {listing.vehicle?.mileage?.toLocaleString()} km
                </div>
                <div className="flex items-center justify-between mt-2">
                  <span className="text-lg font-bold text-green-400">
                    ${listing.list_price?.toLocaleString()}
                  </span>
                  <span className={`text-xs px-2 py-1 rounded ${
                    listing.status === 'sale_pending' ? 'bg-orange-600/20 text-orange-400' : 'bg-blue-600/20 text-blue-400'
                  }`}>
                    {listing.status}
                  </span>
                </div>
                {listing.profit && (
                  <div className="text-xs text-gray-500 mt-1">
                    Est. profit: ${listing.profit.toLocaleString()}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
