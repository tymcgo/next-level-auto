'use client'

import { useState } from 'react'

const CARE_PLANS = [
  {
    id: 'basic',
    name: 'Basic Care',
    price: 49.99,
    interval: 'month',
    description: 'Essential maintenance to keep your vehicle running smoothly.',
    features: [
      'Synthetic oil change (up to 5L)',
      'Tire rotation & balance',
      '21-point vehicle inspection',
      'Fluid top-up (all fluids)',
      'Battery health check (1x/contract)',
    ],
    max_vehicles: 1,
    contract_months: 12,
    color: 'gray',
  },
  {
    id: 'plus',
    name: 'Plus Care',
    price: 89.99,
    interval: 'month',
    description: 'Enhanced coverage for drivers who want peace of mind.',
    features: [
      'Everything in Basic Care',
      'Brake inspection & service',
      'Battery health test (2x/contract)',
      'Alignment check (1x/contract)',
      '24/7 Roadside assistance',
      'Loaner car (1x per contract year)',
      'Priority scheduling',
    ],
    max_vehicles: 2,
    contract_months: 12,
    color: 'blue',
  },
  {
    id: 'premium',
    name: 'Premium Care',
    price: 149.99,
    interval: 'month',
    description: 'Complete coverage for total peace of mind.',
    features: [
      'Everything in Plus Care',
      'Unlimited scheduled maintenance',
      'Brake pad/rotor replacement (1 set/contract)',
      'Priority scheduling (same-day when possible)',
      'Free diagnostic on repairs over $500',
      'Annual detailing (interior + exterior)',
      'Unlimited loaner cars',
      'Tire repair (road hazard)',
    ],
    max_vehicles: 3,
    contract_months: 24,
    color: 'purple',
  },
]

export default function CarePlansPage() {
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null)
  const [showCheckout, setShowCheckout] = useState(false)

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <div className="text-center">
        <h1 className="text-3xl font-bold">Premium Care Plans</h1>
        <p className="text-gray-400 mt-2">
          Fixed monthly cost. No surprise maintenance bills.
        </p>
      </div>

      {/* Plan Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {CARE_PLANS.map(plan => (
          <div
            key={plan.id}
            className={`bg-gray-900 rounded-2xl border p-6 relative overflow-hidden ${
              selectedPlan === plan.id ? 'border-blue-500 ring-2 ring-blue-500/30' : 'border-gray-800'
            } ${plan.color === 'purple' ? 'md:scale-105 md:-my-2' : ''}`}
          >
            {plan.color === 'purple' && (
              <div className="absolute top-0 right-0 bg-purple-600 text-xs px-3 py-1 rounded-bl-lg">
                Most Popular
              </div>
            )}
            <div className="mb-4">
              <h3 className="text-xl font-bold">{plan.name}</h3>
              <div className="mt-2">
                <span className="text-4xl font-bold">${plan.price}</span>
                <span className="text-gray-500">/{plan.interval}</span>
              </div>
              <p className="text-sm text-gray-400 mt-2">{plan.description}</p>
            </div>
            <ul className="space-y-2 mb-6">
              {plan.features.map((feature, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <span className="text-green-400 mt-0.5">✓</span>
                  <span className="text-gray-300">{feature}</span>
                </li>
              ))}
            </ul>
            <button
              onClick={() => {
                setSelectedPlan(plan.id)
                setShowCheckout(true)
              }}
              className={`w-full py-3 rounded-lg font-medium transition-colors ${
                plan.color === 'purple'
                  ? 'bg-purple-600 hover:bg-purple-700'
                  : plan.color === 'blue'
                  ? 'bg-blue-600 hover:bg-blue-700'
                  : 'bg-gray-700 hover:bg-gray-600'
              }`}
            >
              Choose {plan.name}
            </button>
          </div>
        ))}
      </div>

      {/* Checkout Modal */}
      {showCheckout && selectedPlan && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-2xl border border-gray-700 p-8 max-w-md w-full">
            <h2 className="text-xl font-bold mb-4">Subscribe to {CARE_PLANS.find(p => p.id === selectedPlan)?.name}</h2>
            <p className="text-gray-400 mb-6">
              You'll be redirected to Stripe to complete payment. Your subscription activates immediately.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowCheckout(false)}
                className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg"
              >
                Cancel
              </button>
              <button className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg font-medium">
                Proceed to Checkout
              </button>
            </div>
          </div>
        </div>
      )}

      {/* FAQ */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <h2 className="text-xl font-bold mb-4">Frequently Asked Questions</h2>
        <div className="space-y-4">
          <div>
            <h3 className="font-medium">Can I cancel anytime?</h3>
            <p className="text-sm text-gray-400">Cancel within 30 days for a full refund. After that, no penalties.</p>
          </div>
          <div>
            <h3 className="font-medium">Can I upgrade my plan?</h3>
            <p className="text-sm text-gray-400">Yes — upgrade anytime, price difference prorated.</p>
          </div>
          <div>
            <h3 className="font-medium">What's not covered?</h3>
            <p className="text-sm text-gray-400">Collision damage, insurance items, and non-maintenance repairs.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
