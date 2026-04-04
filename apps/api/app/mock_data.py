from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
from typing import Any


FIRST_NAMES = [
    "Ava",
    "Noah",
    "Mia",
    "Ethan",
    "Isla",
    "Liam",
    "Nora",
    "Owen",
    "Ella",
    "Mason",
    "Leah",
    "Lucas",
]

LAST_NAMES = [
    "Carter",
    "Nguyen",
    "Patel",
    "Brooks",
    "Diaz",
    "Foster",
    "Kim",
    "Singh",
    "Price",
    "Lopez",
    "Turner",
    "Reed",
]

CITIES = [
    ("San Francisco", "CA", "94103"),
    ("Seattle", "WA", "98104"),
    ("Austin", "TX", "78701"),
    ("Chicago", "IL", "60607"),
    ("Brooklyn", "NY", "11201"),
    ("Portland", "OR", "97205"),
    ("Denver", "CO", "80202"),
    ("Boston", "MA", "02110"),
]

PRODUCTS = [
    {"sku": "ARC-101", "name": "Arc Runner Sneaker", "price": 128.0},
    {"sku": "LMN-204", "name": "Lumen Carry Tote", "price": 92.0},
    {"sku": "NVY-318", "name": "Navy Studio Jacket", "price": 164.0},
    {"sku": "GLS-443", "name": "Glass Pour-Over Set", "price": 56.0},
    {"sku": "MTR-552", "name": "Metro Wireless Earbuds", "price": 148.0},
    {"sku": "BRM-611", "name": "Bramble Linen Sheet Set", "price": 184.0},
    {"sku": "PLR-705", "name": "Polar Travel Mug", "price": 34.0},
    {"sku": "HZN-884", "name": "Horizon Desk Lamp", "price": 78.0},
]

ISSUES = [
    "duplicate fulfillment scan",
    "carrier damage review",
    "warehouse hold anomaly",
    "payment capture mismatch",
    "inventory sync fault",
    "delivery exception dispute",
]

LOYALTY_TIERS = ["editorial", "standard", "plus", "priority"]


def _iso_now(offset_days: int = 0, offset_minutes: int = 0) -> str:
    return (
        datetime.now(tz=timezone.utc)
        + timedelta(days=offset_days, minutes=offset_minutes)
    ).replace(microsecond=0).isoformat()


def _phone_for(index: int) -> str:
    return f"+1415555{index:04d}"


def build_demo_dataset(order_count: int = 144) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(20260404)
    customers: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    order_items: list[dict[str, Any]] = []

    for index in range(1, order_count + 1):
        first_name = rng.choice(FIRST_NAMES)
        last_name = rng.choice(LAST_NAMES)
        city, state, postal_code = rng.choice(CITIES)
        created_at = _iso_now(offset_days=-rng.randint(1, 28), offset_minutes=index)
        customer_external_id = f"CUST-{index:04d}"
        order_number = f"ORD-{2400 + index:05d}"
        address_line = f"{200 + index} Market Street Apt {rng.randint(2, 24)}"
        item_count = rng.randint(1, 3)
        items_preview: list[dict[str, Any]] = []
        total_amount = 0.0

        for line_index in range(1, item_count + 1):
            product = rng.choice(PRODUCTS)
            quantity = rng.randint(1, 2)
            line_total = round(product["price"] * quantity, 2)
            total_amount += line_total
            items_preview.append(
                {
                    "sku": product["sku"],
                    "product_name": product["name"],
                    "quantity": quantity,
                }
            )
            order_items.append(
                {
                    "item_external_id": f"ITEM-{index:04d}-{line_index}",
                    "order_number": order_number,
                    "sku": product["sku"],
                    "product_name": product["name"],
                    "quantity": quantity,
                    "unit_price": product["price"],
                    "line_total": line_total,
                    "created_at": created_at,
                }
            )

        customer_name = f"{first_name} {last_name}"
        customers.append(
            {
                "customer_external_id": customer_external_id,
                "first_name": first_name,
                "last_name": last_name,
                "customer_name": customer_name,
                "email": f"{first_name.lower()}.{last_name.lower()}{index}@example.com",
                "phone": _phone_for(index),
                "city": city,
                "state": state,
                "postal_code": postal_code,
                "shipping_address": address_line,
                "loyalty_tier": rng.choice(LOYALTY_TIERS),
                "created_at": created_at,
                "updated_at": created_at,
            }
        )

        orders.append(
            {
                "order_number": order_number,
                "customer_external_id": customer_external_id,
                "customer_name": customer_name,
                "customer_phone": _phone_for(index),
                "customer_email": f"{first_name.lower()}.{last_name.lower()}{index}@example.com",
                "shipping_address": address_line,
                "shipping_city": city,
                "shipping_state": state,
                "shipping_postal_code": postal_code,
                "currency": "USD",
                "total_amount": round(total_amount, 2),
                "refund_amount": round(total_amount, 2),
                "issue_reason": rng.choice(ISSUES),
                "fulfillment_status": "problematic",
                "refund_reference": "",
                "refunded_at": "",
                "items_preview": items_preview,
                "created_at": created_at,
                "updated_at": created_at,
            }
        )

    return {
        "customers": customers,
        "orders": orders,
        "order_items": order_items,
    }

