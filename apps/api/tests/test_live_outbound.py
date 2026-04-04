from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.services.live_outbound import LiveOutboundService
from app.services.local_store import LocalDataStore


class FakeLiveKitClient:
    def __init__(self) -> None:
        self.dispatches: list[dict] = []
        self.calls: list[dict] = []

    async def create_agent_dispatch(self, room_name: str, metadata: dict | None = None) -> dict:
        self.dispatches.append({"room_name": room_name, "metadata": metadata})
        return {"ok": True}

    async def create_outbound_sip_participant(
        self,
        room_name: str,
        to_number: str,
        from_number: str,
        participant_identity: str,
        metadata: dict,
        participant_metadata: dict | None = None,
    ) -> dict:
        self.calls.append(
            {
                "room_name": room_name,
                "to_number": to_number,
                "from_number": from_number,
                "participant_identity": participant_identity,
                "metadata": metadata,
                "participant_metadata": participant_metadata,
            }
        )
        return {"participant_id": "sip-demo"}


class LiveOutboundTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_outbound_uses_fixed_target_number(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        base = Path(temp_dir.name)
        settings = Settings(
            project_root=base,
            web_root=base,
            local_data_file=base / "local_store.json",
            insforge_base_url="",
            insforge_admin_token="",
            insforge_project_name="ecommerce",
            call_transport="livekit",
            live_outbound_target_number="+12149098059",
            api_base_url="http://127.0.0.1:8787",
            livekit_url="https://example.livekit.test",
            livekit_ws_url="wss://example.livekit.test",
            livekit_api_key="key",
            livekit_api_secret="secret",
            livekit_sip_trunk_id="trunk",
            livekit_agent_name="phone-ai-agent",
            livekit_default_room_prefix="refund",
            twilio_phone_number="+15555550123",
            openai_api_key="k",
            openai_model="gpt-4o-mini",
            tts_provider="openai",
            openai_tts_model="gpt-4o-mini-tts",
            openai_tts_voice="ash",
            openai_tts_speed=1.0,
            whisper_base_url="",
            whisper_api_key="local-whisper",
            whisper_model="whisper-1",
            elevenlabs_api_key="",
            elevenlabs_voice_id="",
            elevenlabs_tts_model="eleven_turbo_v2_5",
            demo_order_count=12,
            call_step_delay_sec=0.01,
            override_grace_sec=0.05,
            default_support_operator="desk",
        )
        store = LocalDataStore(settings)
        store.bootstrap(12)
        fake_client = FakeLiveKitClient()
        service = LiveOutboundService(store, settings, client=fake_client)

        order = store.list_orders(limit=1)[0]
        call = await service.start_outbound_refund_call(order["order_number"], "desk")

        self.assertEqual(call["to_number"], "+12149098059")
        self.assertEqual(fake_client.calls[0]["to_number"], "+12149098059")
        self.assertEqual(fake_client.calls[0]["from_number"], "+15555550123")
        temp_dir.cleanup()
