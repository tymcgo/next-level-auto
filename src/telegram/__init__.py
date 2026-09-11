"""Telegram bot — captures voice notes, VIN photos, forwarded SMS into Moments."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TelegramBot:
    """Minimal Telegram bot — no external deps beyond httpx.

    Accepts:
    - Voice note -> Whisper transcription -> structured Moment
    - VIN photo -> OCR (or manual entry prompt) -> structured Moment
    - Forwarded SMS -> parse -> structured Moment
    """

    def __init__(self, token: str, llm_base: str, llm_key: str, model: str):
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}"
        self.llm_base = llm_base
        self.llm_key = llm_key
        self.model = model
        self._offset = 0

    async def _api(self, method: str, **kwargs: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{self.base}/{method}", json=kwargs)
            r.raise_for_status()
            return r.json()

    async def get_updates(self) -> list[dict[str, Any]]:
        data = await self._api("getUpdates", offset=self._offset, timeout=30)
        updates = data.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> dict[str, Any]:
        return await self._api("sendMessage", chat_id=chat_id, text=text, **kwargs)

    async def send_inline_buttons(
        self, chat_id: int, text: str, buttons: list[dict[str, str]]
    ) -> dict[str, Any]:
        """Send message with YES/NO inline buttons for approval."""
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ YES", "callback_data": "approve:yes"},
                    {"text": "❌ NO", "callback_data": "approve:no"},
                ]
            ]
        }
        return await self._api(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            reply_markup=json.dumps(keyboard),
        )

    async def download_file(self, file_id: str) -> bytes:
        info = await self._api("getFile", file_id=file_id)
        file_path = info["result"]["file_path"]
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get(
                f"https://api.telegram.org/file/bot{self.token}/{file_path}"
            )
            r.raise_for_status()
            return r.content

    async def transcribe_voice(self, audio_bytes: bytes) -> str:
        """Send voice to Whisper via LiteLLM proxy."""
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                f"{self.llm_base}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.llm_key}"},
                files={"file": ("voice.ogg", audio_bytes, "audio/ogg")},
                data={"model": "whisper-1", "response_format": "text"},
            )
            r.raise_for_status()
            return r.text.strip()

    async def extract_moment_from_text(self, text: str) -> dict[str, Any]:
        """Use LLM to extract structured Moment fields from free text."""
        prompt = f"""Extract structured data from this customer message. Return JSON only:
{{"vin": "...", "mileage": null, "concern": "...", "dtcs": [], "parts_needed": [], "labor_hours": 0.0, "subscription_plan": null, "moment_type": "diagnosis|repair|estimate|maintenance|subscription_signup|subscription_renewal|vehicle_appraisal|vehicle_listing"}}

Message: {text}"""
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{self.llm_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.llm_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "Extract structured auto repair data. JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 500,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"]
            return json.loads(raw)

    async def handle_update(self, update: dict[str, Any]) -> dict[str, Any]:
        """Process a single Telegram update. Returns extracted moment data."""
        # Handle callback queries (inline button presses)
        if "callback_query" in update:
            return await self._handle_callback(update["callback_query"])

        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        if not chat_id:
            return {"status": "no_chat"}

        # Voice note
        if "voice" in message:
            voice = message["voice"]
            audio = await self.download_file(voice["file_id"])
            text = await self.transcribe_voice(audio)
            moment_data = await self.extract_moment_from_text(text)
            moment_data["raw"] = text
            moment_data["source"] = "voice"
            await self.send_message(chat_id, f"📝 Transcribed: {text}\n⏳ Processing...")
            return moment_data

        # Photo (VIN)
        if "photo" in message:
            # Telegram returns multiple sizes; largest is last
            photo = message["photo"][-1]
            img_bytes = await self.download_file(photo["file_id"])
            # For VIN: send to LLM vision model or OCR
            moment_data = await self._extract_vin_from_image(img_bytes)
            moment_data["source"] = "vin_photo"
            await self.send_message(chat_id, f"📸 VIN detected: {moment_data.get('vin', 'unknown')}")
            return moment_data

        # Forwarded SMS / text
        text = message.get("text", "")
        if text:
            moment_data = await self.extract_moment_from_text(text)
            moment_data["raw"] = text
            moment_data["source"] = "text"
            await self.send_message(chat_id, f"📨 Received. Processing...")
            return moment_data

        return {"status": "unhandled"}

    async def _extract_vin_from_image(self, img_bytes: bytes) -> dict[str, Any]:
        """Use vision LLM to read VIN from photo."""
        import base64

        b64 = base64.b64encode(img_bytes).decode()
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{self.llm_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.llm_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Read the VIN from this photo. Return JSON: {\"vin\": \"...\", \"mileage\": null}"},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                            ],
                        }
                    ],
                    "max_tokens": 200,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
            r.raise_for_status()
            return json.loads(r.json()["choices"][0]["message"]["content"])

    async def _handle_callback(self, callback: dict[str, Any]) -> dict[str, Any]:
        """Handle inline button press (YES/NO approval)."""
        data = callback.get("data", "")
        chat_id = callback.get("message", {}).get("chat", {}).get("id")
        if data == "approve:yes":
            await self._api("answerCallbackQuery", callback_query_id=callback["id"], text="✅ Approved")
            return {"action": "approved", "chat_id": chat_id}
        elif data == "approve:no":
            await self._api("answerCallbackQuery", callback_query_id=callback["id"], text="❌ Rejected")
            return {"action": "rejected", "chat_id": chat_id}
        return {"action": "unknown"}
