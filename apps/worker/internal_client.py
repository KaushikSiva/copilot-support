from __future__ import annotations

import httpx

from app.config import get_settings


def _base_url() -> str:
    settings = get_settings()
    return settings.internal_api_base_url or settings.api_base_url


async def push_call_status(call_id: str, status: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(f"{_base_url()}/api/internal/call-status", json={"call_id": call_id, "status": status})


async def push_transcript_turn(call_id: str, speaker: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"{_base_url()}/api/internal/transcript",
            json={"call_id": call_id, "speaker": speaker, "text": text},
        )


async def consume_next_turn_override(call_id: str) -> str | None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(f"{_base_url()}/api/calls/{call_id}/next-turn/consume")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        text = payload.get("text")
        return text.strip() if isinstance(text, str) and text.strip() else None


async def mark_refund_complete(call_id: str, order_number: str, refund_reference: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"{_base_url()}/api/internal/refund-complete",
            json={
                "call_id": call_id,
                "order_number": order_number,
                "refund_reference": refund_reference,
            },
        )
