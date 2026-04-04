from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.config import Settings


class LiveKitClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _auth_token(self, room_name: str) -> str:
        import jwt

        now = int(time.time())
        payload = {
            "iss": self.settings.livekit_api_key,
            "sub": "refund-desk-api",
            "nbf": now,
            "exp": now + 3600,
            "video": {
                "room": room_name,
                "roomAdmin": True,
                "roomCreate": True,
                "canPublish": True,
                "canSubscribe": True,
            },
            "sip": {"admin": True, "call": True},
        }
        return jwt.encode(payload, self.settings.livekit_api_secret, algorithm="HS256")

    async def _post_twirp_with_fallback(
        self,
        client: Any,
        service_names: list[str],
        method: str,
        payload: dict[str, Any],
        token: str,
    ) -> Any:
        last_response: Any | None = None
        for service_name in service_names:
            url = f"{self.settings.livekit_url}/twirp/livekit.{service_name}/{method}"
            response = await client.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
            if response.status_code != 404:
                return response
            last_response = response
        assert last_response is not None
        return last_response

    async def create_agent_dispatch(self, room_name: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        import httpx

        token = self._auth_token(room_name)
        url = f"{self.settings.livekit_url}/twirp/livekit.AgentDispatchService/CreateDispatch"
        payload = {
            "room": room_name,
            "agent_name": self.settings.livekit_agent_name,
            "metadata": json.dumps(metadata or {}),
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        return response.json()

    async def create_outbound_sip_participant(
        self,
        room_name: str,
        to_number: str,
        from_number: str,
        participant_identity: str,
        metadata: dict[str, Any],
        participant_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        import httpx

        token = self._auth_token(room_name)
        payload = {
            "sip_trunk_id": self.settings.livekit_sip_trunk_id,
            "sip_call_to": to_number,
            "room_name": room_name,
            "participant_identity": participant_identity,
            "participant_name": "Refund Desk Customer",
            "participant_metadata": json.dumps(participant_metadata or {}),
            "krisp_enabled": False,
            "wait_until_answered": False,
            "headers": {"X-From-Number": from_number},
            "attributes": {key: str(value) for key, value in metadata.items()},
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await self._post_twirp_with_fallback(
                client=client,
                service_names=["SIP", "SIPService"],
                method="CreateSIPParticipant",
                payload=payload,
                token=token,
            )
        if response.is_error:
            raise RuntimeError(
                "LiveKit SIP CreateSIPParticipant failed "
                f"(status={response.status_code} body={response.text[:300]!r})"
            )
        return response.json()


def generate_room_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
