from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.services.local_store import LocalDataStore


class LocalStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        settings = Settings(
            project_root=base,
            web_root=base,
            local_data_file=base / "local_store.json",
            insforge_base_url="",
            insforge_admin_token="",
            insforge_project_name="ecommerce",
            demo_order_count=24,
            call_step_delay_sec=0.2,
            override_grace_sec=0.05,
            default_support_operator="desk",
        )
        self.store = LocalDataStore(settings)
        self.store.bootstrap(24)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_bootstrap_seeds_problematic_orders(self) -> None:
        orders = self.store.list_orders(limit=30)
        self.assertEqual(len(orders), 24)
        self.assertTrue(all(item["fulfillment_status"] == "problematic" for item in orders))

    def test_override_is_consumed_once(self) -> None:
        order = self.store.list_orders(limit=1)[0]
        call = self.store.create_call_session(order, "desk")
        self.store.set_next_turn_override(call["call_id"], "Use this line.")

        self.assertEqual(self.store.get_next_turn_override(call["call_id"]), "Use this line.")
        self.assertEqual(self.store.consume_next_turn_override(call["call_id"]), "Use this line.")
        self.assertIsNone(self.store.get_next_turn_override(call["call_id"]))

    def test_mark_order_refunded_updates_status_and_reference(self) -> None:
        order = self.store.list_orders(limit=1)[0]
        updated = self.store.mark_order_refunded(order["order_number"], "RF-0001", "call-1")

        self.assertEqual(updated["fulfillment_status"], "refunded")
        self.assertEqual(updated["refund_reference"], "RF-0001")


if __name__ == "__main__":
    unittest.main()
