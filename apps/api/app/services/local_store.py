from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.mock_data import build_demo_dataset


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()


class LocalDataStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path: Path = settings.local_data_file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        if not self.path.exists():
            self._write(self._empty())

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "seeded_at": "",
            "customers": [],
            "orders": [],
            "order_items": [],
            "call_sessions": [],
            "transcript_turns": [],
        }

    def _read(self) -> dict[str, Any]:
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, payload: dict[str, Any]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _find_call(self, data: dict[str, Any], call_id: str) -> dict[str, Any] | None:
        return next((item for item in data["call_sessions"] if item["call_id"] == call_id), None)

    def bootstrap(self, order_count: int) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            if not data["orders"]:
                seeded = build_demo_dataset(order_count)
                data.update(seeded)
                data["seeded_at"] = _utc_now()
                self._write(data)
            return self.get_summary()

    def list_orders(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read()
            items = list(data["orders"])
        if status:
            items = [item for item in items if item["fulfillment_status"] == status]
        items.sort(key=lambda item: item["created_at"], reverse=True)
        return items[:limit]

    def get_order(self, order_number: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._read()
            order = next((item for item in data["orders"] if item["order_number"] == order_number), None)
            if not order:
                return None
            items = [item for item in data["order_items"] if item["order_number"] == order_number]
        enriched = dict(order)
        enriched["items"] = sorted(items, key=lambda item: item["item_external_id"])
        return enriched

    def list_calls(self, limit: int = 12) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read()
            items = list(data["call_sessions"])
        items.sort(key=lambda item: item["created_at"], reverse=True)
        return items[:limit]

    def get_call(self, call_id: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._read()
            call = self._find_call(data, call_id)
            return dict(call) if call else None

    def create_call_session(
        self,
        order: dict[str, Any],
        operator_name: str,
        to_number: str | None = None,
        room_name: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            timestamp = _utc_now()
            payload = {
                "call_id": str(uuid4()),
                "order_number": order["order_number"],
                "customer_name": order["customer_name"],
                "to_number": to_number or order["customer_phone"],
                "direction": "outbound",
                "status": "queued",
                "support_operator": operator_name,
                "room_name": room_name or f"refund-{order['order_number'].lower()}",
                "armed_override": "",
                "refund_reference": "",
                "created_at": timestamp,
                "updated_at": timestamp,
                "started_at": "",
                "ended_at": "",
            }
            data["call_sessions"].append(payload)
            self._write(data)
            return payload

    def update_call_session(self, call_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            call = self._find_call(data, call_id)
            if not call:
                raise KeyError(f"Unknown call_id {call_id}")
            call.update(updates)
            call["updated_at"] = _utc_now()
            self._write(data)
            return dict(call)

    def append_transcript(self, call_id: str, order_number: str, speaker: str, text: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            sequence = 1 + sum(1 for item in data["transcript_turns"] if item["call_id"] == call_id)
            turn = {
                "turn_id": str(uuid4()),
                "call_id": call_id,
                "order_number": order_number,
                "sequence": sequence,
                "speaker": speaker,
                "text": text,
                "created_at": _utc_now(),
            }
            data["transcript_turns"].append(turn)
            call = self._find_call(data, call_id)
            if call:
                call["updated_at"] = turn["created_at"]
            self._write(data)
            return turn

    def list_transcript(self, call_id: str) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read()
            items = [item for item in data["transcript_turns"] if item["call_id"] == call_id]
        items.sort(key=lambda item: item["sequence"])
        return items

    def set_next_turn_override(self, call_id: str, text: str) -> dict[str, Any]:
        return self.update_call_session(call_id, {"armed_override": text})

    def get_next_turn_override(self, call_id: str) -> str | None:
        call = self.get_call(call_id)
        if not call:
            return None
        value = str(call.get("armed_override", "") or "").strip()
        return value or None

    def consume_next_turn_override(self, call_id: str) -> str | None:
        with self._lock:
            data = self._read()
            call = self._find_call(data, call_id)
            if not call:
                raise KeyError(f"Unknown call_id {call_id}")
            value = str(call.get("armed_override", "") or "").strip()
            call["armed_override"] = ""
            call["updated_at"] = _utc_now()
            self._write(data)
        return value or None

    def clear_next_turn_override(self, call_id: str) -> None:
        self.update_call_session(call_id, {"armed_override": ""})

    def mark_order_refunded(self, order_number: str, refund_reference: str, call_id: str) -> dict[str, Any]:
        with self._lock:
            data = self._read()
            order = next((item for item in data["orders"] if item["order_number"] == order_number), None)
            if not order:
                raise KeyError(f"Unknown order_number {order_number}")
            order["fulfillment_status"] = "refunded"
            order["refund_reference"] = refund_reference
            order["refunded_at"] = _utc_now()
            order["updated_at"] = order["refunded_at"]
            order["last_call_id"] = call_id
            self._write(data)
            return dict(order)

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            data = self._read()
        orders = data["orders"]
        calls = data["call_sessions"]
        problematic = sum(1 for item in orders if item["fulfillment_status"] == "problematic")
        refunded = sum(1 for item in orders if item["fulfillment_status"] == "refunded")
        in_progress = sum(1 for item in calls if item["status"] == "in_progress")
        return {
            "mode": "local",
            "seeded_at": data["seeded_at"],
            "orders": {
                "total": len(orders),
                "problematic": problematic,
                "refunded": refunded,
            },
            "calls": {
                "total": len(calls),
                "in_progress": in_progress,
                "completed": sum(1 for item in calls if item["status"] == "completed"),
            },
        }
