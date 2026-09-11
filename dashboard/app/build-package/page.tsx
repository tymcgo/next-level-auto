'use client'

import { useState } from 'react'

const QUESTIONS = [
  { id: 'mileage', label: 'Current vehicle mileage', type: 'number', placeholder: 'e.g. 85000' },
  { id: 'year', label: 'Vehicle year', type: 'number', placeholder: 'e.g. 2020' },
  { id: 'make', label: 'Vehicle make', type: 'text', placeholder: 'e.g. Toyota' },
  { id: 'model', label: 'Vehicle model', type: 'text', placeholder: 'e.g. Camry' },
  { id: 'driving', label: 'Average km per year', type: 'select', options: ['Under 10,000', '10,000-20,000', '20,000-30,000', 'Over 30,000'] },
]

const CARE_PLANS = [
  { id: 'basic', name: 'Basic Care', price: 49.99, includes: ['Oil change (synthetic)', 'Tire rotation', '21-point inspection', 'Fluid top-up'] },
  { id: 'plus', name: 'Plus Care', price: 89.99, includes: ['Everything in Basic', 'Brake service', 'Battery test', 'Alignment check', 'Roadside assistance'] },
  { id: 'premium', name: 'Premium Care', price: 149.99, includes: ['Everything in Plus', 'Unlimited maintenance', 'Brake replacement', 'Priority scheduling', 'Annual detailing'] },
]

export default function BuildPackagePage() {
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [quote, setQuote] = useState<any>(null)
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null)

  function handleAnswer(id: string, value: string) {
    setAnswers(prev => ({ ...prev, [id]: value }))
  }

  function calculateQuote() {
    const mileage = parseInt(answers.mileage) || 0
    const kmPerYear = answers.driving === 'Under 10,000' ? 8000 :
                      answers.driving === '10,000-20,000' ? 15000 :
                      answers.driving === '20,000-30,000' ? 25000 : 35000
    
    const oilChanges = Math.ceil((kmPerYear * 12) / 8000)  // Every 8,000 km for 1 year
    const tireRotations = Math.ceil((kmPerYear * 12) / 10000)
    const inspections = 2  // Every 6 months
    
    setQuote({
      oil_changes: oilChanges,
      tire_rotations: tireRotations,
      inspections: inspections,
      monthly_price: 79.99,
      annual_price: 79.99 * 12,
      savings_vs_paygo: 240,
    })
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Build Your Maintenance Package</h1>
      <p className="text-gray-400">Answer 5 questions and get a custom maintenance plan with pricing.</p>

      {step < QUESTIONS.length ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          <div className="text-sm text-gray-500 mb-2">Question {step + 1} of {QUESTIONS.length}</div>
          <label className="block text-lg font-medium mb-4">{QUESTIONS[step].label}</label>
          
          {QUESTIONS[step].type === 'select' ? (
            <div className="space-y-2">
              {QUESTIONS[step].options?.map(opt => (
                <button
                  key={opt}
                  onClick={() => {
                    handleAnswer(QUESTIONS[step].id, opt)
                    setStep(step + 1)
                  }}
                  className="w-full text-left px-4 py-3 rounded-lg bg-gray-800 hover:bg-gray-700 border border-gray-700"
                >
                  {opt}
                </button>
              ))}
            </div>
          ) : (
            <input
              type={QUESTIONS[step].type}
              placeholder={QUESTIONS[step].placeholder}
              onChange={e => handleAnswer(QUESTIONS[step].id, e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3"
            />
          )}
          
          {QUESTIONS[step].type !== 'select' && (
            <button
              onClick={() => setStep(step + 1)}
              disabled={!answers[QUESTIONS[step].id]}
              className="mt-4 px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg"
            >
              Next →
            </button>
          )}
        </div>
      ) : !quote ? (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 space-y-4">
          <h2 className="text-lg font-semibold">Your Vehicle</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><span className="text-gray-500">Mileage:</span> {answers.mileage}</div>
            <div><span className="text-gray-500">Year:</span> {answers.year}</div>
            <div><span className="text-gray-500">Make:</span> {answers.make}</div>
            <div><span className="text-gray-500">Model:</span> {answers.model}</div>
            <div><span className="text-gray-500">Driving:</span> {answers.driving}</div>
          </div>
          <button
            onClick={calculateQuote}
            className="px-6 py-3 bg-green-600 hover:bg-green-700 rounded-lg font-medium"
          >
            Calculate My Quote
          </button>
        </div>
      ) : !selectedPlan ? (
        <div className="space-y-4">
          <div className="bg-blue-900/20 rounded-xl border border-blue-600/30 p-6">
            <h2 className="text-lg font-semibold mb-4">Your Custom Package</h2>
            <div className="grid grid-cols-2 gap-4 text-sm mb-4">
              <div><span className="text-gray-400">Oil changes/yr:</span> {quote.oil_changes}</div>
              <div><span className="text-gray-400">Tire rotations/yr:</span> {quote.tire_rotations}</div>
              <div><span className="text-gray-400">Inspections/yr:</span> {quote.inspections}</div>
              <div><span className="text-gray-400">Est. savings:</span> ${quote.savings_vs_paygo}/yr</div>
            </div>
            <div className="text-3xl font-bold text-green-400">${quote.monthly_price}/mo</div>
            <div className="text-sm text-gray-500">${quote.annual_price.toFixed(2)}/yr</div>
          </div>

          <h3 className="text-lg font-semibold">Or choose a care plan:</h3>
          <div className="grid gap-4">
            {CARE_PLANS.map(plan => (
              <button
                key={plan.id}
                onClick={() => setSelectedPlan(plan.id)}
                className="text-left bg-gray-900 rounded-xl border border-gray-800 p-4 hover:border-blue-600"
              >
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-medium">{plan.name}</div>
                    <div className="text-sm text-gray-400 mt-1">
                      {plan.includes.slice(0, 2).join(' • ')}...
                    </div>
                  </div>
                  <div className="text-xl font-bold">${plan.price}/mo</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="bg-green-900/20 rounded-xl border border-green-600/30 p-6 text-center">
          <div className="text-5xl mb-4">✓</div>
          <h2 className="text-xl font-semibold mb-2">Ready to subscribe!</h2>
          <p className="text-gray-400 mb-4">
            {CARE_PLANS.find(p => p.id === selectedPlan)?.name} plan selected.
            You'll be redirected to Stripe Checkout.
          </p>
          <button className="px-6 py-3 bg-green-600 hover:bg-green-700 rounded-lg font-medium">
            Proceed to Checkout →
          </button>
        </div>
      )}
    </div>
  )
}
