from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings
from app.services.refund_agent import summarize_items


logger = logging.getLogger(__name__)


def _phase_instructions(phase: str) -> str:
    instructions = {
        "opening": (
            "Open the call. Mention the order number, a brief item summary, and the shipping city. "
            "Ask the customer to confirm it is the correct order."
        ),
        "issue_briefing": (
            "The customer has confirmed the order. Explain the problem briefly, mention the refund amount, "
            "and ask whether they want the refund processed now."
        ),
        "followup": (
            "The customer has not asked for a refund yet. Keep the refund unprocessed, answer naturally, "
            "and ask one concise question that moves toward a decision."
        ),
        "decline_hold": (
            "Acknowledge that no refund will be processed now. Keep the case open and invite the customer to "
            "ask for the refund later or request more review."
        ),
        "refund_confirmation": (
            "The customer explicitly requested a refund and the refund has already been processed by the system. "
            "Confirm the refund amount and provide the refund reference."
        ),
        "refund_closing": (
            "Close the call after a completed refund. Say clearly that the order is now refunded, mention email "
            "confirmation and the refund reference, thank the customer, and wish them a good day."
        ),
        "no_refund_closing": (
            "Close the call without processing a refund. State clearly that no refund has been processed."
        ),
    }
    return instructions.get(phase, "Reply naturally as a concise customer support voice agent.")


def _format_transcript(transcript: list[dict[str, str]], limit: int = 10) -> str:
    excerpt = transcript[-limit:]
    if not excerpt:
        return "(no transcript yet)"
    return "\n".join(f"{turn['speaker']}: {turn['text']}" for turn in excerpt)


def _extract_completion_text(body: dict[str, Any]) -> str:
    content = (
        body.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
        return " ".join(part.strip() for part in parts if part.strip()).strip()
    return ""


def build_chat_messages(
    order: dict[str, Any],
    transcript: list[dict[str, str]],
    phase: str,
    refund_reference: str = "",
) -> list[dict[str, str]]:
    order_number = str(order.get("order_number") or "")
    refund_amount = float(order.get("refund_amount") or 0.0)
    order_summary = summarize_items(order)
    shipping_city = str(order.get("shipping_city") or "")
    issue_reason = str(order.get("issue_reason") or "")
    refund_reference_text = refund_reference or "(not available)"

    system = (
        "You are Avery, a concise customer support voice agent for Refund Desk. "
        "Sound natural, professional, and spoken, not written. "
        "Do not mention being AI, a language model, or a prompt. "
        "Do not use markdown, bullets, labels, stage directions, emojis, or quotes. "
        "Keep each answer to one short paragraph, usually one or two sentences. "
        "Never say a refund was processed unless the phase explicitly says it has already been processed."
    )
    user = (
        f"Phase: {phase}\n"
        f"Phase instructions: {_phase_instructions(phase)}\n"
        f"Order number: {order_number}\n"
        f"Customer name: {order.get('customer_name')}\n"
        f"Order summary: {order_summary}\n"
        f"Shipping city: {shipping_city}\n"
        f"Issue reason: {issue_reason}\n"
        f"Refund amount: ${refund_amount:.2f}\n"
        f"Refund reference: {refund_reference_text}\n"
        "Recent transcript:\n"
        f"{_format_transcript(transcript)}\n"
        "Write only the next assistant turn."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


class LmStudioAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._resolved_model: str | None = None

    async def _list_models(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.settings.lm_studio_timeout_sec) as client:
            response = await client.get(
                f"{self.settings.lm_studio_base_url}/models",
                headers={"Authorization": f"Bearer {self.settings.lm_studio_api_key}"},
            )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        return data if isinstance(data, list) else []

    async def resolve_model(self) -> str:
        if self._resolved_model:
            return self._resolved_model

        models = await self._list_models()
        requested = self.settings.personaplex_model.strip()
        ids = [str(item.get("id") or "").strip() for item in models]
        if requested and requested in ids:
            self._resolved_model = requested
            return requested

        requested_lower = requested.lower()
        for model_id in ids:
            lowered = model_id.lower()
            if requested_lower and requested_lower in lowered:
                self._resolved_model = model_id
                return model_id
            if "persona" in lowered or "plex" in lowered:
                self._resolved_model = model_id
                return model_id

        if requested:
            logger.warning(
                "LM Studio did not list requested model %s; using it optimistically without caching",
                requested,
            )
            return requested
        raise RuntimeError("No PersonaPlex-capable model was found in LM Studio.")

    async def generate_turn(
        self,
        *,
        order: dict[str, Any],
        transcript: list[dict[str, str]],
        phase: str,
        refund_reference: str = "",
    ) -> str:
        model = await self.resolve_model()
        payload = {
            "model": model,
            "temperature": self.settings.lm_studio_temperature,
            "messages": build_chat_messages(order, transcript, phase, refund_reference=refund_reference),
        }
        async with httpx.AsyncClient(timeout=self.settings.lm_studio_timeout_sec) as client:
            response = await client.post(
                f"{self.settings.lm_studio_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.lm_studio_api_key}"},
                json=payload,
            )
        response.raise_for_status()
        body = response.json()
        clean = _extract_completion_text(body)
        if not clean:
            raise RuntimeError(f"LM Studio returned an empty completion: {body}")
        return clean
