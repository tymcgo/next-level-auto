// telegram-webhook.ts — Updated for Python service integration
// Field names aligned with Python: NextLevelMoment, CustomerContext, Plan

export interface Env {
  SUPABASE_URL: string
  SUPABASE_SERVICE_KEY: string
  TELEGRAM_BOT_TOKEN: string
  TELEGRAM_WEBHOOK_SECRET: string
  OPENROUTER_API_KEY: string
  PYTHON_SERVICE_URL: string  // Fly.io URL
  TEST_MODE: string
}

interface TelegramUpdate {
  update_id: number
  message?: TelegramMessage
}

interface TelegramMessage {
  message_id: number
  from: { id: number; first_name: string; username?: string }
  chat: { id: number; type: string }
  date: number
  text?: string
  voice?: { file_id: string; duration: number; mime_type?: string }
  photo?: Array<{ file_id: string; width: number; height: number; file_size?: number }>
  caption?: string
  forward_from?: { id: number; first_name: string }
  forward_date?: number
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 })
    }

    const secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if (secret !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response("Unauthorized", { status: 401 })
    }

    const update: TelegramUpdate = await request.json()

    try {
      await handleUpdate(update, env)
    } catch (err) {
      console.error("Failed to process update:", err)
    }

    return new Response("OK", { status: 200 })
  },
}

async function handleUpdate(update: TelegramUpdate, env: Env): Promise<void> {
  const msg = update.message
  if (!msg) return

  let extracted: { text: string; vin: string | null }

  if (msg.voice) {
    extracted = await handleVoiceNote(msg, env)
  } else if (msg.photo && msg.photo.length > 0) {
    extracted = await handlePhoto(msg, env)
  } else if (msg.text) {
    extracted = { text: msg.text, vin: extractVIN(msg.text) }
  } else {
    return
  }

  // Build event matching Python schema: NextLevelMoment
  const event = buildEvent(msg, extracted, env)

  // Check idempotency (KV or Supabase)
  const idempotencyKey = await computeIdempotencyKey(event)
  if (await isDuplicate(idempotencyKey, env)) {
    console.log(`Duplicate event skipped: ${idempotencyKey}`)
    return
  }

  // Write to Supabase
  const eventId = await writeEventToSupabase(event, env)

  // Get customer summary and recent ROs
  const customerSummary = await getCustomerSummary(event.vin, env)
  const recentROs = await getRecentROs(event.vin, env)

  // Call Python /plan
  const planResponse = await fetch(`${env.PYTHON_SERVICE_URL}/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event: { ...event, id: eventId },
      customer_summary: customerSummary,
      recent_ros: recentROs,
    }),
  })

  if (!planResponse.ok) {
    console.error("Python /plan failed:", await planResponse.text())
    return
  }

  const { plan } = await planResponse.json()

  // Execute each step
  for (const step of plan.steps || []) {
    await executeStep(step, event, eventId, env)
  }

  // If approval needed, call Python /govern
  if (plan.requires_approval) {
    await fetch(`${env.PYTHON_SERVICE_URL}/govern`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "request_approval",
        data: {
          target_type: "estimate",
          target_id: eventId,
          reason: plan.approval_reason,
          requested_by: "telegram_bot",
        },
      }),
    })
  }
}

// =============================================================================
// Execute a plan step — mix of direct calls and Python /execute
// =============================================================================
async function executeStep(
  step: { tool: string; params: dict; description?: string },
  event: any,
  eventId: string,
  env: Env
): Promise<void> {
  const context = {
    idempotency_key: `${eventId}-${step.tool}`,
    correlation_id: eventId,
    actor_id: event.actor_id,
  }

  // Tools that can be called directly from Worker (external APIs)
  const directTools = ["decode_vin", "send_sms"]
  if (directTools.includes(step.tool)) {
    await invokeDirectTool(step.tool, step.params, env)
    return
  }

  // DB operations go through Python /execute
  await fetch(`${env.PYTHON_SERVICE_URL}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tool: step.tool,
      params: step.params,
      context,
    }),
  })
}

async function invokeDirectTool(tool: string, params: any, env: Env): Promise<void> {
  if (tool === "decode_vin") {
    // Call NHTSA directly
    await fetch(`https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/${params.vin}?format=json`)
  }
  // Add other direct tools as needed
}

// =============================================================================
// Event builder — aligned with Python NextLevelMoment
// =============================================================================
function buildEvent(msg: TelegramMessage, extracted: { text: string; vin: string | null }, env: Env): any {
  const source = msg.voice ? "telegram_voice" : msg.photo ? "telegram_photo" : "telegram_text"
  const eventType = msg.voice ? "voice_note" : msg.photo ? "vin_photo" : msg.forward_from ? "sms_forward" : "webhook_in"

  return {
    moment_type: eventType,
    vin: extracted.vin || "UNKNOWNVIN0000000",
    vin_last6: (extracted.vin || "000000").slice(-6),
    timestamp: new Date().toISOString(),
    raw_data: {
      message_id: msg.message_id,
      chat_id: msg.chat.id,
      voice_duration: msg.voice?.duration,
      transcription: extracted.text,
    },
    extracted_data: {
      text: extracted.text,
      vin: extracted.vin,
    },
    source,
    actor_id: String(msg.from.id),
    correlation_id: crypto.randomUUID(),
  }
}

// =============================================================================
// Customer summary lookup (from Supabase)
// =============================================================================
async function getCustomerSummary(vin: string, env: Env): Promise<string> {
  if (vin === "UNKNOWNVIN0000000") return "Unknown customer"

  const res = await fetch(
    `${env.SUPABASE_URL}/rest/v1/vehicles?vin=eq.${vin}&select=customers(name,phone)&limit=1`,
    {
      headers: {
        apikey: env.SUPABASE_SERVICE_KEY,
        Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      },
    }
  )
  const data = await res.json()
  if (data && data.length > 0) {
    const customer = data[0].customers
    return customer?.name || "Unknown"
  }
  return "Unknown customer"
}

// =============================================================================
// Recent ROs for this VIN
// =============================================================================
async function getRecentROs(vin: string, env: Env): Promise<any[]> {
  if (vin === "UNKNOWNVIN0000000") return []

  const res = await fetch(
    `${env.SUPABASE_URL}/rest/v1/repair_orders?vehicle_id=in.(select id from vehicles where vin='${vin}')&select=ro_number,status,total_amount,created_at&order=created_at.desc&limit=2`,
    {
      headers: {
        apikey: env.SUPABASE_SERVICE_KEY,
        Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      },
    }
  )
  return await res.json() || []
}

// =============================================================================
// Idempotency — check via KV or Supabase
// =============================================================================
async function computeIdempotencyKey(event: any): Promise<string> {
  const data = JSON.stringify({
    vin: event.vin,
    timestamp: event.timestamp,
    raw: event.raw_data,
  }, Object.keys(event.raw_data).sort())

  const encoder = new TextEncoder()
  const hash = await crypto.subtle.digest("SHA-256", encoder.encode(data))
  return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, "0")).join("")
}

async function isDuplicate(key: string, env: Env): Promise<boolean> {
  const res = await fetch(
    `${env.SUPABASE_URL}/rest/v1/events?idempotency_key=eq.${key}&select=id&limit=1`,
    {
      headers: {
        apikey: env.SUPABASE_SERVICE_KEY,
        Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      },
    }
  )
  const data = await res.json()
  return data && data.length > 0
}

// =============================================================================
// Write event to Supabase
// =============================================================================
async function writeEventToSupabase(event: any, env: Env): Promise<string> {
  const idempotencyKey = await computeIdempotencyKey(event)
  
  const res = await fetch(`${env.SUPABASE_URL}/rest/v1/events`, {
    method: "POST",
    headers: {
      apikey: env.SUPABASE_SERVICE_KEY,
      Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      "Content-Type": "application/json",
      Prefer: "return=representation",
    },
    body: JSON.stringify({
      schema_version: "1.0.0",
      idempotency_key: idempotencyKey,
      event_type: event.moment_type,
      vin: event.vin,
      vin_last6: event.vin_last6,
      timestamp: event.timestamp,
      received_at: new Date().toISOString(),
      raw: event.raw_data,
      normalized: event.extracted_data,
      source: event.source,
      actor_id: event.actor_id,
      correlation_id: event.correlation_id,
    }),
  })

  const data = await res.json()
  return data[0]?.id
}

// =============================================================================
// Voice note → Whisper via OpenRouter
// =============================================================================
async function handleVoiceNote(msg: TelegramMessage, env: Env): Promise<{ text: string; vin: string | null }> {
  const voice = msg.voice!
  const fileUrl = await getFileUrl(voice.file_id, env.TELEGRAM_BOT_TOKEN)
  if (!fileUrl) throw new Error("Failed to get voice file URL")

  const audioRes = await fetch(fileUrl)
  const audioBlob = await audioRes.blob()

  // Use OpenRouter for Whisper (no local compute)
  const formData = new FormData()
  formData.append("file", audioBlob, "audio.ogg")

  const res = await fetch("https://openrouter.ai/api/v1/audio/transcriptions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.OPENROUTER_API_KEY}`,
    },
    body: formData,
  })

  if (!res.ok) throw new Error(`Whisper error: ${res.status}`)
  const transcription = await res.text()

  return { text: transcription.trim(), vin: extractVIN(transcription) }
}

// =============================================================================
// VIN photo → OCR via OpenRouter
// =============================================================================
async function handlePhoto(msg: TelegramMessage, env: Env): Promise<{ text: string; vin: string | null }> {
  const photos = msg.photo!
  const bestPhoto = photos[photos.length - 1]

  const fileUrl = await getFileUrl(bestPhoto.file_id, env.TELEGRAM_BOT_TOKEN)
  if (!fileUrl) throw new Error("Failed to get photo file URL")

  const imageRes = await fetch(fileUrl)
  const imageBlob = await imageRes.blob()

  // Use OpenRouter vision for OCR
  const base64 = await blobToBase64(imageBlob)

  const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.OPENROUTER_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "google/gemma-2-9b-it:free",
      messages: [
        {
          role: "user",
          content: [
            { type: "text", text: "Extract the VIN number and any other text from this image. Return JSON: {vin: string|null, text: string}" },
            { type: "image_url", image_url: { url: `data:image/jpeg;base64,${base64}` } },
          ],
        },
      ],
    }),
  })

  if (!res.ok) throw new Error(`OCR error: ${res.status}`)
  const data = await res.json()
  const text = data.choices?.[0]?.message?.content || ""

  return { text, vin: extractVIN(text) }
}

// =============================================================================
// Helpers
// =============================================================================
async function getFileUrl(fileId: string, botToken: string): Promise<string | null> {
  const res = await fetch(
    `https://api.telegram.org/bot${botToken}/getFile?file_id=${fileId}`
  )
  const data = await res.json()
  if (!data.ok) return null
  return `https://api.telegram.org/file/bot${botToken}/${data.result.file_path}`
}

async function blobToBase64(blob: Blob): Promise<string> {
  const buffer = await blob.arrayBuffer()
  const bytes = new Uint8Array(buffer)
  let binary = ""
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

function extractVIN(text: string): string | null {
  const vinRegex = /\b[A-HJ-NPR-Z0-9]{17}\b/gi
  const matches = text.match(vinRegex)
  if (matches) {
    const vin = matches[0].toUpperCase()
    if (!/[IOQ]/.test(vin)) return vin
  }
  return null
}
