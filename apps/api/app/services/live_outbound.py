from __future__ import annotations

from typing import Any

from app.config import Settings
from app.services.livekit_client import LiveKitClient, generate_room_name
from app.services.phone import normalize_e164
from app.services.refund_agent import summarize_items


def build_call_context(order: dict[str, Any], operator_name: str) -> dict[str, Any]:
    return {
        "order_id": order.get("id"),
        "order_number": order["order_number"],
        "customer_name": order["customer_name"],
        "customer_phone": order["customer_phone"],
        "customer_email": order["customer_email"],
        "shipping_address": order["shipping_address"],
        "shipping_city": order["shipping_city"],
        "shipping_state": order["shipping_state"],
        "shipping_postal_code": order["shipping_postal_code"],
        "issue_reason": order["issue_reason"],
        "refund_amount": order["refund_amount"],
        "currency": order["currency"],
        "items": order.get("items", []),
        "items_summary": summarize_items(order),
        "operator_name": operator_name,
    }


class LiveOutboundService:
    def __init__(self, repository: Any, settings: Settings, client: LiveKitClient | None = None) -> None:
        self.repository = repository
        self.settings = settings
        self.client = client or LiveKitClient(settings)

    async def start_outbound_refund_call(self, order_number: str, operator_name: str) -> dict[str, Any]:
        order = self.repository.get_order(order_number)
        if not order:
            raise KeyError(f"Unknown order_number {order_number}")

        target_number = normalize_e164(self.settings.live_outbound_target_number)
        from_number = normalize_e164(self.settings.twilio_phone_number)
        room_name = generate_room_name(self.settings.livekit_default_room_prefix)
        call = self.repository.create_call_session(
            order,
            operator_name,
            to_number=target_number,
            room_name=room_name,
        )

        self.repository.update_call_session(call["call_id"], {"status": "dialing", "room_name": room_name})
        participant_identity = f"pstn-{call['call_id'][:8]}"
        context = build_call_context(order, operator_name)

        try:
            await self.client.create_agent_dispatch(
                room_name=room_name,
                metadata={"call_id": call["call_id"], "order_number": order_number},
            )
            await self.client.create_outbound_sip_participant(
                room_name=room_name,
                to_number=target_number,
                from_number=from_number,
                participant_identity=participant_identity,
                metadata={"call_id": call["call_id"], "order_number": order_number},
                participant_metadata={"call_id": call["call_id"], "context_json": context},
            )
        except Exception:
            self.repository.update_call_session(call["call_id"], {"status": "failed"})
            raise

        latest = self.repository.get_call(call["call_id"])
        return latest or call

