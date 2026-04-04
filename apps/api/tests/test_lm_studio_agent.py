from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.services.lm_studio_agent import LmStudioAgent, _extract_completion_text, build_chat_messages


class FakeLmStudioAgent(LmStudioAgent):
    def __init__(self, settings: Settings, models: list[dict[str, str]]) -> None:
        super().__init__(settings)
        self._models = models

    async def _list_models(self) -> list[dict[str, str]]:
        return self._models


class LmStudioAgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.settings = Settings(
            project_root=base,
            web_root=base,
            local_data_file=base / "local_store.json",
            personaplex_model="PersonaPlex-7B",
        )
        self.order = {
            "order_number": "ORD-02541",
            "customer_name": "Jordan Lee",
            "shipping_city": "Dallas",
            "issue_reason": "carrier damage claim",
            "refund_amount": 264.95,
            "items_preview": [
                {"quantity": 1, "product_name": "Ashwood Standing Lamp"},
                {"quantity": 2, "product_name": "Glass Shade Kit"},
            ],
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_chat_messages_includes_phase_and_transcript(self) -> None:
        messages = build_chat_messages(
            self.order,
            [
                {"speaker": "agent", "text": "Hello, I am calling about your order."},
                {"speaker": "customer", "text": "Yes, that is my order."},
            ],
            phase="issue_briefing",
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Phase: issue_briefing", messages[1]["content"])
        self.assertIn("ORD-02541", messages[1]["content"])
        self.assertIn("customer: Yes, that is my order.", messages[1]["content"])

    async def test_resolve_model_prefers_exact_match(self) -> None:
        agent = FakeLmStudioAgent(
            self.settings,
            models=[{"id": "qwen"}, {"id": "PersonaPlex-7B"}],
        )

        resolved = await agent.resolve_model()
        self.assertEqual(resolved, "PersonaPlex-7B")

    async def test_resolve_model_falls_back_to_persona_like_id(self) -> None:
        agent = FakeLmStudioAgent(
            Settings(
                project_root=self.settings.project_root,
                web_root=self.settings.web_root,
                local_data_file=self.settings.local_data_file,
                personaplex_model="",
            ),
            models=[{"id": "llama-3.2"}, {"id": "PersonaPlex-7B-GGUF"}],
        )

        resolved = await agent.resolve_model()
        self.assertEqual(resolved, "PersonaPlex-7B-GGUF")

    async def test_resolve_model_does_not_cache_optimistic_requested_name(self) -> None:
        agent = FakeLmStudioAgent(
            self.settings,
            models=[{"id": "llama-3.2"}],
        )

        resolved = await agent.resolve_model()
        self.assertEqual(resolved, "PersonaPlex-7B")
        self.assertIsNone(agent._resolved_model)

    def test_extract_completion_text_handles_string_and_parts(self) -> None:
        as_text = _extract_completion_text({"choices": [{"message": {"content": "hello there"}}]})
        as_parts = _extract_completion_text(
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": "hello"},
                                {"type": "text", "text": "there"},
                            ]
                        }
                    }
                ]
            }
        )

        self.assertEqual(as_text, "hello there")
        self.assertEqual(as_parts, "hello there")


if __name__ == "__main__":
    unittest.main()
