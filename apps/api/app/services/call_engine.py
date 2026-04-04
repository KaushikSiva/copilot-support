from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.config import Settings
from app.services.override_broker import OverrideBroker
from app.services.refund_agent import (
    build_closing_message,
    build_customer_ack,
    build_customer_confirmation,
    build_customer_refund_request,
    build_issue_briefing_message,
    build_opening_message,
    build_refund_message,
    build_refund_reference,
)


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()


class CallEngine:
    def __init__(self, repository: Any, settings: Settings, override_broker: OverrideBroker | None = None) -> None:
        self.repository = repository
        self.settings = settings
        self.override_broker = override_broker or OverrideBroker()
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start_outbound_refund_call(self, order_number: str, operator_name: str) -> dict[str, Any]:
        order = self.repository.get_order(order_number)
        if not order:
            raise KeyError(f"Unknown order_number {order_number}")

        call = self.repository.create_call_session(order, operator_name)
        task = asyncio.create_task(self._run_script(call["call_id"], order_number))
        self._tasks[call["call_id"]] = task
        task.add_done_callback(lambda _: self._tasks.pop(call["call_id"], None))
        return call

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _consume_override_with_grace(self, call_id: str) -> str | None:
        override = self.override_broker.consume(call_id)
        if override:
            self.repository.clear_next_turn_override(call_id)
            return override

        override = self.repository.consume_next_turn_override(call_id)
        if override:
            return override

        grace = max(self.settings.override_grace_sec, 0.0)
        deadline = asyncio.get_running_loop().time() + grace
        poll_interval = min(0.4, max(grace / 4, 0.05))
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(poll_interval)
            override = self.override_broker.consume(call_id)
            if override:
                self.repository.clear_next_turn_override(call_id)
                return override

            override = self.repository.consume_next_turn_override(call_id)
            if override:
                return override
        return None

    async def _run_script(self, call_id: str, order_number: str) -> None:
        try:
            order = self.repository.get_order(order_number)
            if not order:
                raise KeyError(f"Unknown order_number {order_number}")
            self.repository.update_call_session(
                call_id,
                {"status": "dialing", "started_at": _utc_now()},
            )
            await asyncio.sleep(self.settings.call_step_delay_sec)

            self.repository.update_call_session(call_id, {"status": "in_progress"})
            self.repository.append_transcript(call_id, order_number, "agent", build_opening_message(order))
            await asyncio.sleep(self.settings.call_step_delay_sec)

            self.repository.append_transcript(call_id, order_number, "customer", build_customer_confirmation(order))
            await asyncio.sleep(self.settings.call_step_delay_sec)

            briefing = await self._consume_override_with_grace(call_id) or build_issue_briefing_message(order)
            self.repository.append_transcript(call_id, order_number, "agent", briefing)
            await asyncio.sleep(self.settings.call_step_delay_sec)

            self.repository.append_transcript(call_id, order_number, "customer", build_customer_refund_request(order))
            await asyncio.sleep(self.settings.call_step_delay_sec)

            refund_reference = build_refund_reference(order_number)
            resolution = await self._consume_override_with_grace(call_id) or build_refund_message(order, refund_reference)
            self.repository.append_transcript(call_id, order_number, "agent", resolution)
            self.repository.mark_order_refunded(order_number, refund_reference, call_id)
            self.repository.update_call_session(call_id, {"refund_reference": refund_reference})
            order = self.repository.get_order(order_number) or order
            await asyncio.sleep(self.settings.call_step_delay_sec)

            self.repository.append_transcript(call_id, order_number, "customer", build_customer_ack(order))
            await asyncio.sleep(self.settings.call_step_delay_sec)

            closing = await self._consume_override_with_grace(call_id) or build_closing_message(order, refund_reference)
            self.repository.append_transcript(call_id, order_number, "agent", closing)
            self.repository.update_call_session(
                call_id,
                {"status": "completed", "ended_at": _utc_now()},
            )
        except asyncio.CancelledError:
            self.repository.update_call_session(call_id, {"status": "canceled", "ended_at": _utc_now()})
            raise
        except Exception as exc:
            self.repository.append_transcript(call_id, order_number, "system", f"Call failed: {exc}")
            self.repository.update_call_session(call_id, {"status": "failed", "ended_at": _utc_now()})
