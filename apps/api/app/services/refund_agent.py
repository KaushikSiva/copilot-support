from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any


def _first_name(order: dict[str, Any]) -> str:
    customer_name = str(order.get("customer_name", "") or "").strip()
    return customer_name.split(" ")[0] if customer_name else "there"


def summarize_items(order: dict[str, Any]) -> str:
    items = order.get("items") or order.get("items_preview") or []
    if not isinstance(items, list) or not items:
        return "your order"

    labels: list[str] = []
    for item in items[:2]:
        quantity = int(item.get("quantity", 1) or 1)
        product_name = str(item.get("product_name", "item")).strip()
        labels.append(f"{quantity} {product_name}")

    summary = ", ".join(labels)
    if len(items) > 2:
        summary += ", and the remaining items"
    return summary


def build_refund_reference(order_number: str) -> str:
    stamp = datetime.now(tz=timezone.utc).strftime("%m%d%H%M")
    suffix = order_number.split("-")[-1][-4:]
    return f"RF-{suffix}-{stamp}"


def build_opening_message(order: dict[str, Any]) -> str:
    return (
        f"Hello {_first_name(order)}, this is Avery with Northline Commerce support. "
        f"I'm calling about order {order['order_number']} for {summarize_items(order)} "
        f"shipping to {order['shipping_city']}. Can you confirm that's the correct order?"
    )


def build_issue_briefing_message(order: dict[str, Any]) -> str:
    return (
        f"I can confirm we flagged a {order['issue_reason']} on order {order['order_number']}. "
        f"The order is eligible for a full refund of ${float(order['refund_amount']):.2f} "
        f"to the original payment method. If you'd like me to process the refund now, "
        "say refund this order, or tell me what you'd like me to check first."
    )


def build_followup_message(order: dict[str, Any]) -> str:
    return (
        f"I have not processed the refund yet for order {order['order_number']}. "
        f"It is still eligible for ${float(order['refund_amount']):.2f} back to the original payment method. "
        "If you want me to proceed, say please refund it now. Otherwise tell me what else you want reviewed."
    )


def build_decline_hold_message(order: dict[str, Any]) -> str:
    return (
        f"Understood. I have not processed a refund for order {order['order_number']}. "
        "If you change your mind, say refund this order. Otherwise I can stay with you and review the case."
    )


def build_customer_confirmation(order: dict[str, Any]) -> str:
    return (
        f"Yes, that sounds right. The order ending in {str(order['order_number'])[-4:]} "
        f"was headed to {order['shipping_city']}."
    )


def build_customer_refund_request(order: dict[str, Any]) -> str:
    return f"Yes, please refund order {order['order_number']}."


def build_refund_message(order: dict[str, Any], refund_reference: str) -> str:
    return (
        f"Thanks for confirming. We reviewed a {order['issue_reason']} on order {order['order_number']} "
        f"and I've issued a full refund of ${float(order['refund_amount']):.2f} "
        f"to the original payment method. Your refund reference is {refund_reference}."
    )


def build_customer_ack(order: dict[str, Any]) -> str:
    return "Okay, thanks for taking care of that. I appreciate the update."


def build_closing_message(order: dict[str, Any], refund_reference: str) -> str:
    return (
        f"Your order is now refunded, and you'll receive an email confirmation shortly. "
        f"If you need anything else, mention reference {refund_reference}. Thank you for your time today, and have a good day."
    )


def build_no_refund_close_message(order: dict[str, Any]) -> str:
    return (
        f"I have not processed a refund for order {order['order_number']}. "
        "The case will stay open until you request it. If you want the refund later, "
        "contact support and reference the order number. Goodbye."
    )


def _normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def classify_customer_intent(text: str, refund_offer_made: bool = False) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return "other"

    decline_phrases = (
        "do not refund",
        "dont refund",
        "don't refund",
        "no refund",
        "not a refund",
        "not now",
        "not yet",
        "keep the order",
        "do not process it",
        "dont process it",
        "don't process it",
    )
    if any(phrase in normalized for phrase in decline_phrases):
        return "decline_refund"

    request_phrases = (
        "refund this order",
        "refund the order",
        "please refund",
        "issue the refund",
        "process the refund",
        "go ahead and refund",
        "i want a refund",
        "i would like a refund",
        "id like a refund",
        "money back",
        "credit it back",
        "reimburse me",
        "refund it",
    )
    if any(phrase in normalized for phrase in request_phrases):
        return "request_refund"

    if "refund" in normalized and "no" not in normalized and "not" not in normalized:
        return "request_refund"

    if refund_offer_made:
        affirmative_phrases = (
            "yes",
            "yes please",
            "please do",
            "go ahead",
            "do it",
            "do that",
            "okay",
            "ok",
            "sure",
            "sounds good",
            "that works",
            "please proceed",
            "proceed",
        )
        if normalized in affirmative_phrases:
            return "request_refund"

    return "other"
