'use client'

import { useState, useRef } from 'react'

export default function EstimatesPage() {
  const [isRecording, setIsRecording] = useState(false)
  const [transcription, setTranscription] = useState('')
  const [draft, setDraft] = useState<any>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)

  async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mediaRecorder = new MediaRecorder(stream)
    mediaRecorderRef.current = mediaRecorder
    const chunks: Blob[] = []

    mediaRecorder.ondataavailable = (e) => chunks.push(e.data)
    mediaRecorder.onstop = async () => {
      const blob = new Blob(chunks, { type: 'audio/webm' })
      // In production, send to /api/transcribe then /api/plan
      setTranscription('Voice note recorded. In production: Whisper → Planner Agent → draft estimate.')
      setDraft({
        line_items: [
          { description: 'Brake pad replacement', labor_hours: 1.5, parts_cost: 85 },
          { description: 'Rotor resurface', labor_hours: 0.5, parts_cost: 0 },
        ],
        subtotal: 272.50,
        tax: 13.63,
        total: 286.13,
      })
    }

    mediaRecorder.start()
    setIsRecording(true)
    setTimeout(() => {
      mediaRecorder.stop()
      setIsRecording(false)
    }, 5000)
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Estimate Builder</h1>

      {/* Voice Input */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <h2 className="text-lg font-semibold mb-4">Voice → Draft Estimate</h2>
        <div className="flex items-center gap-4">
          <button
            onClick={startRecording}
            disabled={isRecording}
            className={`px-6 py-3 rounded-lg font-medium transition-colors ${
              isRecording
                ? 'bg-red-600 text-white animate-pulse'
                : 'bg-blue-600 hover:bg-blue-700 text-white'
            }`}
          >
            {isRecording ? '● Recording...' : '🎤 Start Voice Note'}
          </button>
          <span className="text-sm text-gray-500">Max 5 seconds (demo)</span>
        </div>
        {transcription && (
          <div className="mt-4 p-3 bg-gray-800 rounded-lg">
            <p className="text-sm text-gray-300">{transcription}</p>
          </div>
        )}
      </div>

      {/* Draft Preview */}
      {draft && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          <h2 className="text-lg font-semibold mb-4">Draft Estimate</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-800">
                <th className="pb-2">Description</th>
                <th className="pb-2 text-right">Labor</th>
                <th className="pb-2 text-right">Parts</th>
                <th className="pb-2 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {draft.line_items.map((item: any, i: number) => (
                <tr key={i} className="border-b border-gray-800">
                  <td className="py-2">{item.description}</td>
                  <td className="py-2 text-right">{item.labor_hours}h</td>
                  <td className="py-2 text-right">${item.parts_cost.toFixed(2)}</td>
                  <td className="py-2 text-right font-mono">
                    ${((item.labor_hours * 125) + item.parts_cost).toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={3} className="pt-2 text-right text-gray-400">Subtotal</td>
                <td className="pt-2 text-right font-mono">${draft.subtotal.toFixed(2)}</td>
              </tr>
              <tr>
                <td colSpan={3} className="text-right text-gray-400">Tax</td>
                <td className="text-right font-mono">${draft.tax.toFixed(2)}</td>
              </tr>
              <tr className="text-lg font-bold">
                <td colSpan={3} className="pt-2 text-right">Total</td>
                <td className="pt-2 text-right font-mono text-blue-400">${draft.total.toFixed(2)}</td>
              </tr>
            </tfoot>
          </table>
          <div className="mt-4 flex gap-3">
            <button className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg text-sm">Send to Customer</button>
            <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Edit</button>
            <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm">Discard</button>
          </div>
        </div>
      )}
    </div>
  )
}
