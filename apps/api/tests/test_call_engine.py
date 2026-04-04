from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.services.call_engine import CallEngine
from app.services.local_store import LocalDataStore


class CallEngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        settings = Settings(
            project_root=base,
            web_root=base,
            local_data_file=base / "local_store.json",
            insforge_base_url="",
            insforge_admin_token="",
            insforge_project_name="ecommerce",
            demo_order_count=12,
            call_step_delay_sec=0.01,
            override_grace_sec=0.05,
            default_support_operator="desk",
        )
        self.store = LocalDataStore(settings)
        self.store.bootstrap(12)
        self.engine = CallEngine(self.store, settings)

    async def asyncTearDown(self) -> None:
        await self.engine.shutdown()
        self.temp_dir.cleanup()

    async def test_outbound_refund_call_updates_order_and_transcript(self) -> None:
        order = self.store.list_orders(limit=1)[0]
        call = await self.engine.start_outbound_refund_call(order["order_number"], "desk")
        await asyncio.sleep(0.45)

        updated_order = self.store.get_order(order["order_number"])
        updated_call = self.store.get_call(call["call_id"])
        transcript = self.store.list_transcript(call["call_id"])

        self.assertIsNotNone(updated_order)
        self.assertEqual(updated_order["fulfillment_status"], "refunded")
        self.assertIsNotNone(updated_call)
        self.assertEqual(updated_call["status"], "completed")
        self.assertGreaterEqual(len(transcript), 7)
        self.assertTrue(any(turn["speaker"] == "agent" for turn in transcript))
        customer_refund_turn = next(
            (turn for turn in transcript if turn["speaker"] == "customer" and "refund" in turn["text"].lower()),
            None,
        )
        agent_refund_turn = next(
            (turn for turn in transcript if turn["speaker"] == "agent" and "issued a full refund" in turn["text"].lower()),
            None,
        )
        self.assertIsNotNone(customer_refund_turn)
        self.assertIsNotNone(agent_refund_turn)
        assert customer_refund_turn is not None
        assert agent_refund_turn is not None
        self.assertLess(customer_refund_turn["sequence"], agent_refund_turn["sequence"])


if __name__ == "__main__":
    unittest.main()
