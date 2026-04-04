from __future__ import annotations

import unittest

from app.mock_data import build_demo_dataset
from app.services.refund_agent import (
    build_closing_message,
    build_issue_briefing_message,
    build_opening_message,
    build_refund_message,
    build_refund_reference,
    classify_customer_intent,
)


class RefundAgentTests(unittest.TestCase):
    def test_opening_message_mentions_order_and_city(self) -> None:
        order = build_demo_dataset(1)["orders"][0]
        message = build_opening_message(order)

        self.assertIn(order["order_number"], message)
        self.assertIn(order["shipping_city"], message)

    def test_refund_reference_uses_order_suffix(self) -> None:
        value = build_refund_reference("ORD-02477")
        self.assertTrue(value.startswith("RF-2477-"))

    def test_refund_message_mentions_amount_and_reference(self) -> None:
        order = build_demo_dataset(1)["orders"][0]
        message = build_refund_message(order, "RF-0009")

        self.assertIn("RF-0009", message)
        self.assertIn(f"${order['refund_amount']:.2f}", message)

    def test_issue_briefing_mentions_refund_offer(self) -> None:
        order = build_demo_dataset(1)["orders"][0]
        message = build_issue_briefing_message(order)

        self.assertIn(order["issue_reason"], message)
        self.assertIn("refund this order", message.lower())

    def test_closing_message_thanks_customer_and_ends_naturally(self) -> None:
        order = build_demo_dataset(1)["orders"][0]
        message = build_closing_message(order, "RF-0009")

        self.assertIn("refunded", message.lower())
        self.assertIn("thank you", message.lower())
        self.assertIn("good day", message.lower())

    def test_refund_intent_requires_request_or_offer_context(self) -> None:
        self.assertEqual(classify_customer_intent("Yes, that is the right order."), "other")
        self.assertEqual(classify_customer_intent("Please refund it."), "request_refund")
        self.assertEqual(classify_customer_intent("Yes please", refund_offer_made=True), "request_refund")
        self.assertEqual(classify_customer_intent("No, do not refund it."), "decline_refund")


if __name__ == "__main__":
    unittest.main()
