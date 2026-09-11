"""PlannerAgent — converts events into structured plans using cloud LLM."""
from __future__ import annotations

import json
from typing import Any

import httpx
import yaml


class PlannerAgent:
    """Generates PlanSchema JSON from events using cloud LLM."""

    def __init__(self, config: dict, http: httpx.AsyncClient):
        self.config = config
        self.http = http
        planner_cfg = config.get("planner", {})
        self.max_tokens = planner_cfg.get("max_output_tokens", 1200)
        self.temperature = planner_cfg.get("temperature", 0.1)
        self.model = planner_cfg.get("litellm", {}).get("model", "openrouter/google/gemma-2-9b-it:free")
        self.api_base = planner_cfg.get("litellm", {}).get("api_base", "https://openrouter.ai/api/v1")
        self.api_key = planner_cfg.get("litellm", {}).get("api_key", "")

    async def generate(self, event: dict, customer_summary: str, recent_ros: list) -> dict:
        """Generate a plan from the event + context."""
        
        # Build the system + user prompt
        system = self._build_system_prompt()
        user = self._build_user_prompt(event, customer_summary, recent_ros)

        # Call LLM
        response = await self._call_llm(system, user)

        # Parse JSON from response
        plan = self._parse_response(response)
        return plan

    def _build_system_prompt(self) -> str:
        return """You are the Planner Agent for Next Level Auto.
Output ONLY valid JSON matching this schema:
{
  "customer_summary": "<2-8 words>",
  "vehicle_summary": "<year make model, or 'unknown'>",
  "diagnosis": "<brief tech diagnosis, or null>",
  "steps": [
    {"tool": "<tool_name>", "params": {...}, "description": "<1 sentence>"}
  ],
  "requires_approval": false,
  "approval_reason": "<why, or null>",
  "total_estimate": <number or null>,
  "notes": "<caveats, or null>"
}

Available tools: decode_vin, create_ro, create_estimate, send_sms, order_parts, create_stripe_subscription, list_vehicle_for_sale, audit_log
If total > 750, requires_approval=true. If VIN is unknown, first step must be decode_vin.
No text outside JSON. No markdown."""

    def _build_user_prompt(self, event: dict, customer_summary: str, recent_ros: list) -> str:
        event_type = event.get("event_type", "unknown")
        raw = event.get("raw", {})
        normalized = event.get("normalized", {})

        # Extract text content based on event type
        text_content = ""
        if event_type == "voice_note":
            text_content = normalized.get("transcription", raw.get("text", ""))
        elif event_type == "vin_photo":
            text_content = normalized.get("ocr_text", "")
        elif event_type == "sms_forward":
            text_content = raw.get("text", "")
        else:
            text_content = str(normalized) if normalized else str(raw)

        vin = normalized.get("vin", event.get("vin", "unknown"))

        return f"""Event: {event_type}
VIN: {vin}
Text: {text_content}
Customer: {customer_summary}
Recent ROs: {json.dumps(recent_ros) if recent_ros else "none"}"""

    async def _call_llm(self, system: str, user: str) -> str:
        """Call OpenRouter LLM."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        res = await self.http.post(
            f"{self.api_base}/chat/completions",
            json=payload,
            headers=headers,
        )

        if res.status_code != 200:
            raise Exception(f"LLM error {res.status_code}: {res.text[:500]}")

        data = res.json()
        return data["choices"][0]["message"]["content"]

    def _parse_response(self, response: str) -> dict:
        """Extract JSON from LLM response, handling markdown code blocks."""
        text = response.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            if lines[0].strip().startswith("```"):
                lines = lines[1:]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end+1])
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Could not parse JSON from response: {text[:200]}")
