from __future__ import annotations

from threading import RLock


class OverrideBroker:
    def __init__(self) -> None:
        self._lock = RLock()
        self._values: dict[str, str] = {}

    def set(self, call_id: str, text: str) -> None:
        with self._lock:
            self._values[call_id] = text

    def get(self, call_id: str) -> str | None:
        with self._lock:
            value = self._values.get(call_id, "").strip()
            return value or None

    def consume(self, call_id: str) -> str | None:
        with self._lock:
            value = self._values.pop(call_id, "").strip()
            return value or None

    def clear(self, call_id: str) -> None:
        with self._lock:
            self._values.pop(call_id, None)

