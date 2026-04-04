from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import random
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from app.config import Settings
from app.mock_data import CITIES, FIRST_NAMES, ISSUES, LAST_NAMES


ORDER_EXTRA_COLUMNS: list[dict[str, Any]] = [
    {"name": "order_number", "type": "string", "nullable": False, "unique": True},
    {"name": "customer_name", "type": "string", "nullable": False, "unique": False},
    {"name": "customer_phone", "type": "string", "nullable": False, "unique": False},
    {"name": "customer_email", "type": "string", "nullable": False, "unique": False},
    {"name": "shipping_city", "type": "string", "nullable": False, "unique": False},
    {"name": "shipping_state", "type": "string", "nullable": False, "unique": False},
    {"name": "shipping_postal_code", "type": "string", "nullable": False, "unique": False},
    {"name": "currency", "type": "string", "nullable": False, "unique": False, "defaultValue": "USD"},
    {"name": "fulfillment_status", "type": "string", "nullable": False, "unique": False, "defaultValue": "problematic"},
    {"name": "refund_amount", "type": "float", "nullable": False, "unique": False},
    {"name": "issue_reason", "type": "string", "nullable": False, "unique": False},
    {"name": "refund_reference", "type": "string", "nullable": True, "unique": False},
    {"name": "refunded_at", "type": "datetime", "nullable": True, "unique": False},
    {"name": "last_call_id", "type": "string", "nullable": True, "unique": False},
]

VOICE_TABLE_DEFINITIONS: dict[str, list[dict[str, Any]]] = {
    "call_sessions": [
        {"name": "call_id", "type": "string", "nullable": False, "unique": True},
        {
            "name": "order_id",
            "type": "uuid",
            "nullable": True,
            "unique": False,
            "foreignKey": {"table": "orders", "column": "id", "onDelete": "CASCADE"},
        },
        {"name": "order_number", "type": "string", "nullable": False, "unique": False},
        {"name": "customer_name", "type": "string", "nullable": False, "unique": False},
        {"name": "to_number", "type": "string", "nullable": False, "unique": False},
        {"name": "direction", "type": "string", "nullable": False, "unique": False},
        {"name": "status", "type": "string", "nullable": False, "unique": False},
        {"name": "support_operator", "type": "string", "nullable": False, "unique": False},
        {"name": "room_name", "type": "string", "nullable": False, "unique": False},
        {"name": "armed_override", "type": "string", "nullable": True, "unique": False},
        {"name": "refund_reference", "type": "string", "nullable": True, "unique": False},
        {"name": "created_at", "type": "datetime", "nullable": False, "unique": False},
        {"name": "updated_at", "type": "datetime", "nullable": False, "unique": False},
        {"name": "started_at", "type": "datetime", "nullable": True, "unique": False},
        {"name": "ended_at", "type": "datetime", "nullable": True, "unique": False},
    ],
    "transcript_turns": [
        {"name": "turn_id", "type": "string", "nullable": False, "unique": True},
        {"name": "call_id", "type": "string", "nullable": False, "unique": False},
        {"name": "order_number", "type": "string", "nullable": False, "unique": False},
        {"name": "sequence", "type": "integer", "nullable": False, "unique": False},
        {"name": "speaker", "type": "string", "nullable": False, "unique": False},
        {"name": "text", "type": "string", "nullable": False, "unique": False},
        {"name": "created_at", "type": "datetime", "nullable": False, "unique": False},
    ],
}


def updates_time() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()


class InsforgeDataStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._override_cache: dict[str, str] = {}

    def _request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        query: dict[str, str] | None = None,
        prefer_representation: bool = False,
    ) -> Any:
        query_string = f"?{urlencode(query)}" if query else ""
        url = f"{self.settings.insforge_base_url}{path}{query_string}"
        headers = {"Authorization": f"Bearer {self.settings.insforge_admin_token}"}
        data: bytes | None = None

        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if prefer_representation:
            headers["Prefer"] = "return=representation"

        request = Request(url=url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.settings.request_timeout_sec) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Insforge request failed [{exc.code}] {method} {path}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Insforge request failed {method} {path}: {exc.reason}") from exc

    def _query_records(self, table_name: str, query: dict[str, str] | None = None) -> list[dict[str, Any]]:
        result = self._request("GET", f"/api/database/records/{table_name}", query=query)
        return result if isinstance(result, list) else []

    def _create_records(self, table_name: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not records:
            return []
        result = self._request(
            "POST",
            f"/api/database/records/{table_name}",
            payload=records,
            prefer_representation=True,
        )
        return result if isinstance(result, list) else []

    def _update_records(
        self,
        table_name: str,
        filters: dict[str, str],
        updates: dict[str, Any],
    ) -> list[dict[str, Any]]:
        result = self._request(
            "PATCH",
            f"/api/database/records/{table_name}",
            payload=updates,
            query=filters,
            prefer_representation=True,
        )
        return result if isinstance(result, list) else []

    @staticmethod
    def _normalize_schema_columns(schema: dict[str, Any]) -> set[str]:
        return {
            str(column.get("columnName") or column.get("name") or "").strip()
            for column in (schema.get("columns") or [])
        }

    def _ensure_schema_columns(self, table_name: str, columns: list[dict[str, Any]]) -> None:
        schema = self._request("GET", f"/api/database/tables/{table_name}/schema")
        existing_columns = self._normalize_schema_columns(schema)
        missing_columns = [column for column in columns if column["name"] not in existing_columns]
        if not missing_columns:
            return

        add_columns = []
        for column in missing_columns:
            item = {
                "columnName": column["name"],
                "type": column["type"],
                "isNullable": column["nullable"],
                "isUnique": column["unique"],
            }
            if "defaultValue" in column and column.get("defaultValue") is not None:
                item["defaultValue"] = column["defaultValue"]
            add_columns.append(item)
        add_foreign_keys = [
            {
                "columnName": column["name"],
                "foreignKey": {
                    "referenceTable": column["foreignKey"]["table"],
                    "referenceColumn": column["foreignKey"]["column"],
                    "onDelete": column["foreignKey"].get("onDelete", "NO ACTION"),
                    "onUpdate": "NO ACTION",
                },
            }
            for column in missing_columns
            if column.get("foreignKey")
        ]
        self._request(
            "PATCH",
            f"/api/database/tables/{table_name}/schema",
            payload={
                "addColumns": add_columns,
                "dropColumns": [],
                "updateColumns": [],
                "addForeignKeys": add_foreign_keys,
                "dropForeignKeys": [],
            },
        )

    @staticmethod
    def _create_table_payload(table_name: str, columns: list[dict[str, Any]]) -> dict[str, Any]:
        mapped_columns = []
        for column in columns:
            item = {
                "columnName": column["name"],
                "type": column["type"],
                "isNullable": column["nullable"],
                "isUnique": column["unique"],
            }
            if "defaultValue" in column and column.get("defaultValue") is not None:
                item["defaultValue"] = column["defaultValue"]
            if column.get("foreignKey"):
                item["foreignKey"] = {
                    "referenceTable": column["foreignKey"]["table"],
                    "referenceColumn": column["foreignKey"]["column"],
                    "onDelete": column["foreignKey"].get("onDelete", "NO ACTION"),
                    "onUpdate": "NO ACTION",
                }
            mapped_columns.append(item)
        return {"tableName": table_name, "columns": mapped_columns}

    def ensure_tables(self) -> None:
        existing = set(self._request("GET", "/api/database/tables") or [])
        if "orders" not in existing or "order_items" not in existing or "products" not in existing:
            raise RuntimeError("Insforge ecommerce base tables are missing. Expected products, orders, and order_items.")

        self._ensure_schema_columns("orders", ORDER_EXTRA_COLUMNS)

        for table_name, columns in VOICE_TABLE_DEFINITIONS.items():
            if table_name in existing:
                self._ensure_schema_columns(table_name, columns)
                continue
            self._request(
                "POST",
                "/api/database/tables",
                payload=self._create_table_payload(table_name, columns),
            )

    @staticmethod
    def _batch(items: list[dict[str, Any]], size: int = 100) -> list[list[dict[str, Any]]]:
        return [items[index : index + size] for index in range(0, len(items), size)]

    def _active_products(self) -> list[dict[str, Any]]:
        products = self._query_records("products", {"is_active": "eq.true", "limit": "200", "order": "created_at.asc"})
        if not products:
            raise RuntimeError("No active products found in Insforge products table.")
        return products

    def bootstrap(self, order_count: int) -> dict[str, Any]:
        self.ensure_tables()
        existing_orders = self._query_records("orders", {"limit": "1"})
        if existing_orders:
            return self.get_summary()

        products = self._active_products()
        rng = random.Random(20260404)
        order_plans: list[dict[str, Any]] = []
        orders_payload: list[dict[str, Any]] = []

        for index in range(1, order_count + 1):
            first_name = rng.choice(FIRST_NAMES)
            last_name = rng.choice(LAST_NAMES)
            city, state, postal_code = rng.choice(CITIES)
            created_at = (
                datetime.now(tz=timezone.utc) - timedelta(days=rng.randint(1, 28), minutes=index)
            ).replace(microsecond=0).isoformat()
            order_number = f"ORD-{2400 + index:05d}"
            customer_name = f"{first_name} {last_name}"
            customer_email = f"{first_name.lower()}.{last_name.lower()}{index}@example.com"
            customer_phone = f"+1415555{index:04d}"
            shipping_address = f"{200 + index} Market Street Apt {rng.randint(2, 24)}"

            line_count = rng.randint(1, 3)
            selected_products = rng.sample(products, k=min(line_count, len(products)))
            lines: list[dict[str, Any]] = []
            total_amount = 0.0

            for product in selected_products:
                quantity = rng.randint(1, 2)
                unit_price = float(product["price"])
                total_amount += unit_price * quantity
                lines.append(
                    {
                        "product_id": product["id"],
                        "product_name": product["name"],
                        "sku": product["sku"],
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "created_at": created_at,
                    }
                )

            refund_amount = round(total_amount, 2)
            orders_payload.append(
                {
                    "customer_id": None,
                    "total_amount": refund_amount,
                    "shipping_address": shipping_address,
                    "created_at": created_at,
                    "updated_at": created_at,
                    "order_number": order_number,
                    "customer_name": customer_name,
                    "customer_phone": customer_phone,
                    "customer_email": customer_email,
                    "shipping_city": city,
                    "shipping_state": state,
                    "shipping_postal_code": postal_code,
                    "currency": "USD",
                    "fulfillment_status": "problematic",
                    "refund_amount": refund_amount,
                    "issue_reason": rng.choice(ISSUES),
                    "refund_reference": "",
                    "refunded_at": None,
                    "last_call_id": None,
                }
            )
            order_plans.append({"order_number": order_number, "created_at": created_at, "lines": lines})

        created_orders: list[dict[str, Any]] = []
        for chunk in self._batch(orders_payload):
            created_orders.extend(self._create_records("orders", chunk))

        order_ids = {row["order_number"]: row["id"] for row in created_orders}
        order_items_payload: list[dict[str, Any]] = []
        for plan in order_plans:
            order_id = order_ids.get(plan["order_number"])
            if not order_id:
                continue
            for line in plan["lines"]:
                order_items_payload.append(
                    {
                        "order_id": order_id,
                        "product_id": line["product_id"],
                        "quantity": line["quantity"],
                        "unit_price": line["unit_price"],
                        "created_at": line["created_at"],
                    }
                )

        for chunk in self._batch(order_items_payload):
            self._create_records("order_items", chunk)

        return self.get_summary()

    @staticmethod
    def _map_order_row(row: dict[str, Any]) -> dict[str, Any]:
        mapped = dict(row)
        mapped["fulfillment_status"] = str(row.get("fulfillment_status") or row.get("status") or "")
        mapped["refund_amount"] = float(row.get("refund_amount") or row.get("total_amount") or 0.0)
        mapped["refund_reference"] = str(row.get("refund_reference") or "")
        mapped["refunded_at"] = str(row.get("refunded_at") or "")
        mapped["issue_reason"] = str(row.get("issue_reason") or "")
        mapped["currency"] = str(row.get("currency") or "USD")
        mapped["customer_name"] = str(row.get("customer_name") or "")
        mapped["customer_phone"] = str(row.get("customer_phone") or "")
        mapped["customer_email"] = str(row.get("customer_email") or "")
        mapped["shipping_city"] = str(row.get("shipping_city") or "")
        mapped["shipping_state"] = str(row.get("shipping_state") or "")
        mapped["shipping_postal_code"] = str(row.get("shipping_postal_code") or "")
        return mapped

    def list_orders(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = {"limit": str(limit), "order": "created_at.desc"}
        if status:
            query["fulfillment_status"] = f"eq.{status}"
        rows = self._query_records("orders", query)
        return [self._map_order_row(row) for row in rows]

    def get_order(self, order_number: str) -> dict[str, Any] | None:
        rows = self._query_records("orders", {"order_number": f"eq.{order_number}", "limit": "1"})
        if not rows:
            return None

        order = self._map_order_row(rows[0])
        items = self._query_records("order_items", {"order_id": f"eq.{order['id']}", "order": "created_at.asc"})
        enriched_items: list[dict[str, Any]] = []
        for item in items:
            product_rows = self._query_records("products", {"id": f"eq.{item['product_id']}", "limit": "1"})
            product = product_rows[0] if product_rows else {}
            quantity = int(item.get("quantity") or 0)
            unit_price = float(item.get("unit_price") or 0.0)
            enriched_items.append(
                {
                    "item_external_id": item["id"],
                    "order_number": order["order_number"],
                    "sku": str(product.get("sku") or ""),
                    "product_name": str(product.get("name") or "Unknown Product"),
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": round(quantity * unit_price, 2),
                    "created_at": item.get("created_at"),
                }
            )

        order["items"] = enriched_items
        return order

    def list_calls(self, limit: int = 12) -> list[dict[str, Any]]:
        return self._query_records("call_sessions", {"limit": str(limit), "order": "created_at.desc"})

    def get_call(self, call_id: str) -> dict[str, Any] | None:
        rows = self._query_records("call_sessions", {"call_id": f"eq.{call_id}", "limit": "1"})
        return dict(rows[0]) if rows else None

    def create_call_session(
        self,
        order: dict[str, Any],
        operator_name: str,
        to_number: str | None = None,
        room_name: str | None = None,
    ) -> dict[str, Any]:
        now = updates_time()
        payload = {
            "call_id": str(uuid4()),
            "order_id": order.get("id"),
            "order_number": order["order_number"],
            "customer_name": order["customer_name"],
            "to_number": to_number or order["customer_phone"],
            "direction": "outbound",
            "status": "queued",
            "support_operator": operator_name,
            "room_name": room_name or f"refund-{order['order_number'].lower()}",
            "armed_override": "",
            "refund_reference": "",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "ended_at": None,
        }
        rows = self._create_records("call_sessions", [payload])
        return rows[0] if rows else payload

    def update_call_session(self, call_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        merged = dict(updates)
        merged["updated_at"] = updates_time()
        rows = self._update_records("call_sessions", {"call_id": f"eq.{call_id}"}, merged)
        if not rows:
            raise KeyError(f"Unknown call_id {call_id}")
        return dict(rows[0])

    def append_transcript(self, call_id: str, order_number: str, speaker: str, text: str) -> dict[str, Any]:
        latest = self._query_records(
            "transcript_turns",
            {"call_id": f"eq.{call_id}", "order": "sequence.desc", "limit": "1"},
        )
        next_sequence = int(latest[0]["sequence"]) + 1 if latest else 1
        now = updates_time()
        payload = {
            "turn_id": str(uuid4()),
            "call_id": call_id,
            "order_number": order_number,
            "sequence": next_sequence,
            "speaker": speaker,
            "text": text,
            "created_at": now,
        }
        rows = self._create_records("transcript_turns", [payload])
        self.update_call_session(call_id, {"updated_at": now})
        return rows[0] if rows else payload

    def list_transcript(self, call_id: str) -> list[dict[str, Any]]:
        return self._query_records("transcript_turns", {"call_id": f"eq.{call_id}", "order": "sequence.asc"})

    def set_next_turn_override(self, call_id: str, text: str) -> dict[str, Any]:
        self._override_cache[call_id] = text
        return self.update_call_session(call_id, {"armed_override": text})

    def get_next_turn_override(self, call_id: str) -> str | None:
        cached = self._override_cache.get(call_id)
        if cached:
            return cached
        call = self.get_call(call_id)
        if not call:
            return None
        value = str(call.get("armed_override") or "").strip()
        return value or None

    def consume_next_turn_override(self, call_id: str) -> str | None:
        cached = self._override_cache.pop(call_id, "").strip()
        if cached:
            self.update_call_session(call_id, {"armed_override": ""})
            return cached

        value = self.get_next_turn_override(call_id)
        self.update_call_session(call_id, {"armed_override": ""})
        return value

    def clear_next_turn_override(self, call_id: str) -> None:
        self._override_cache.pop(call_id, None)
        self.update_call_session(call_id, {"armed_override": ""})

    def mark_order_refunded(self, order_number: str, refund_reference: str, call_id: str) -> dict[str, Any]:
        now = updates_time()
        rows = self._update_records(
            "orders",
            {"order_number": f"eq.{order_number}"},
            {
                "fulfillment_status": "refunded",
                "refund_reference": refund_reference,
                "refunded_at": now,
                "updated_at": now,
                "last_call_id": call_id,
            },
        )
        if not rows:
            raise KeyError(f"Unknown order_number {order_number}")
        return self._map_order_row(rows[0])

    def get_summary(self) -> dict[str, Any]:
        orders = self._query_records("orders")
        calls = self._query_records("call_sessions")
        return {
            "mode": "insforge",
            "seeded_at": "",
            "orders": {
                "total": len(orders),
                "problematic": sum(1 for item in orders if item.get("fulfillment_status") == "problematic"),
                "refunded": sum(1 for item in orders if item.get("fulfillment_status") == "refunded"),
            },
            "calls": {
                "total": len(calls),
                "in_progress": sum(1 for item in calls if item.get("status") == "in_progress"),
                "completed": sum(1 for item in calls if item.get("status") == "completed"),
            },
        }
