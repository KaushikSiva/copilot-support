from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pythonjsonlogger import jsonlogger

from app.config import get_settings
from app.services.lm_studio_agent import LmStudioAgent
from app.services.refund_agent import (
    build_closing_message,
    build_decline_hold_message,
    build_followup_message,
    build_issue_briefing_message,
    build_no_refund_close_message,
    build_opening_message,
    build_refund_message,
    build_refund_reference,
    classify_customer_intent,
)
from internal_client import consume_next_turn_override, mark_refund_complete, push_call_status, push_transcript_turn


logger = logging.getLogger("refund-worker")
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
logger.handlers = [handler]
logger.setLevel(logging.INFO)
settings = get_settings()

try:
    from livekit import rtc
    from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
    from livekit.agents.tts.stream_adapter import StreamAdapter
    from livekit.plugins import elevenlabs, openai, silero
except Exception as exc:
    logger.exception("Failed importing LiveKit packages: %s", exc)
    raise


def build_tts() -> object:
    provider = settings.tts_provider.strip().lower()
    if provider == "elevenlabs" and settings.elevenlabs_api_key and settings.elevenlabs_voice_id:
        return elevenlabs.TTS(
            api_key=settings.elevenlabs_api_key,
            voice_id=settings.elevenlabs_voice_id,
            model=settings.elevenlabs_tts_model,
        )
    return StreamAdapter(
        tts=openai.TTS(
            api_key=settings.openai_api_key,
            model=settings.openai_tts_model,
            voice=settings.openai_tts_voice,
            speed=settings.openai_tts_speed,
        ),
        text_pacing=True,
    )


def build_stt() -> object:
    params = {"model": settings.whisper_model, "api_key": settings.whisper_api_key}
    if settings.whisper_base_url:
        params["base_url"] = settings.whisper_base_url
    return openai.STT(**params)


async def _say_and_log(session: AgentSession, call_id: str, order_number: str, text: str) -> None:
    handle = session.say(text, add_to_chat_ctx=True)
    await handle.wait_for_playout()
    await push_transcript_turn(call_id, "agent", text)
    logger.info("Agent turn call_id=%s order_number=%s text=%s", call_id, order_number, text)


async def _next_user_turn(queue: asyncio.Queue[str], timeout_sec: float) -> str | None:
    try:
        return await asyncio.wait_for(queue.get(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        return None


async def _next_agent_text(
    *,
    call_id: str,
    default_text: str,
    order: dict[str, Any],
    transcript: list[dict[str, str]],
    phase: str,
    refund_reference: str = "",
    lm_studio_agent: LmStudioAgent | None = None,
) -> str:
    override = await consume_next_turn_override(call_id)
    if override:
        return override

    if settings.agent_backend not in {"auto", "lm_studio"} or lm_studio_agent is None:
        return default_text

    try:
        text = await lm_studio_agent.generate_turn(
            order=order,
            transcript=transcript,
            phase=phase,
            refund_reference=refund_reference,
        )
        logger.info("LM Studio agent backend produced phase=%s call_id=%s", phase, call_id)
        return text
    except Exception as exc:
        logger.warning(
            "LM Studio agent backend failed for phase=%s call_id=%s; falling back to deterministic text: %s",
            phase,
            call_id,
            exc,
        )
        return default_text


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    attrs = participant.attributes or {}
    metadata_blob = getattr(participant, "metadata", "") or "{}"
    metadata = json.loads(metadata_blob) if isinstance(metadata_blob, str) else (metadata_blob or {})
    call_id = str(attrs.get("call_id") or metadata.get("call_id") or "")
    context_blob = attrs.get("context_json") or metadata.get("context_json") or {}
    context = json.loads(context_blob) if isinstance(context_blob, str) else dict(context_blob or {})
    order_number = str(context.get("order_number") or attrs.get("order_number") or "")
    lm_studio_agent = LmStudioAgent(settings) if settings.agent_backend in {"auto", "lm_studio"} else None

    agent = Agent(instructions="You are a concise refund support voice agent.")
    session = AgentSession(
        stt=build_stt(),
        vad=silero.VAD.load(),
        llm=openai.LLM(model=settings.openai_model, api_key=settings.openai_api_key),
        tts=build_tts(),
        allow_interruptions=True,
    )
    await session.start(room=ctx.room, agent=agent)
    await push_call_status(call_id, "in_progress")

    user_turns: asyncio.Queue[str] = asyncio.Queue()
    disconnect_event = asyncio.Event()
    transcript_context: list[dict[str, str]] = []

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event) -> None:  # type: ignore[no-untyped-def]
        if not bool(getattr(event, "is_final", False)):
            return
        text = str(getattr(event, "transcript", "") or "").strip()
        if not text:
            return
        transcript_context.append({"speaker": "customer", "text": text})
        user_turns.put_nowait(text)
        asyncio.create_task(push_transcript_turn(call_id, "customer", text))

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(disconnected_participant) -> None:  # type: ignore[no-untyped-def]
        if getattr(disconnected_participant, "identity", None) == participant.identity:
            disconnect_event.set()

    opening = await _next_agent_text(
        call_id=call_id,
        default_text=build_opening_message(context),
        order=context,
        transcript=transcript_context,
        phase="opening",
        lm_studio_agent=lm_studio_agent,
    )
    transcript_context.append({"speaker": "agent", "text": opening})
    await _say_and_log(session, call_id, order_number, opening)
    if disconnect_event.is_set():
        await push_call_status(call_id, "completed")
        ctx.shutdown(reason="participant_disconnected")
        return

    customer_turn = await _next_user_turn(user_turns, timeout_sec=20.0)
    if disconnect_event.is_set():
        await push_call_status(call_id, "completed")
        ctx.shutdown(reason="participant_disconnected")
        return

    refund_offer_made = False
    non_refund_turns = 0
    while True:
        if customer_turn is None:
            closing_text = await _next_agent_text(
                call_id=call_id,
                default_text=build_no_refund_close_message(context),
                order=context,
                transcript=transcript_context,
                phase="no_refund_closing",
                lm_studio_agent=lm_studio_agent,
            )
            transcript_context.append({"speaker": "agent", "text": closing_text})
            await _say_and_log(session, call_id, order_number, closing_text)
            await push_call_status(call_id, "completed")
            ctx.shutdown(reason="refund_not_requested")
            return

        intent = classify_customer_intent(customer_turn, refund_offer_made=refund_offer_made)
        if intent == "request_refund":
            refund_reference = build_refund_reference(order_number)
            await mark_refund_complete(call_id, order_number, refund_reference)
            refund_text = await _next_agent_text(
                call_id=call_id,
                default_text=build_refund_message(context, refund_reference),
                order=context,
                transcript=transcript_context,
                phase="refund_confirmation",
                refund_reference=refund_reference,
                lm_studio_agent=lm_studio_agent,
            )
            transcript_context.append({"speaker": "agent", "text": refund_text})
            await _say_and_log(session, call_id, order_number, refund_text)

            customer_turn = await _next_user_turn(user_turns, timeout_sec=12.0)
            if disconnect_event.is_set():
                await push_call_status(call_id, "completed")
                ctx.shutdown(reason="participant_disconnected")
                return

            closing_text = await _next_agent_text(
                call_id=call_id,
                default_text=build_closing_message(context, refund_reference),
                order=context,
                transcript=transcript_context,
                phase="refund_closing",
                refund_reference=refund_reference,
                lm_studio_agent=lm_studio_agent,
            )
            transcript_context.append({"speaker": "agent", "text": closing_text})
            await _say_and_log(session, call_id, order_number, closing_text)
            await push_call_status(call_id, "completed")
            ctx.shutdown(reason="call_flow_complete")
            return

        if intent == "decline_refund":
            next_text = await _next_agent_text(
                call_id=call_id,
                default_text=build_decline_hold_message(context),
                order=context,
                transcript=transcript_context,
                phase="decline_hold",
                lm_studio_agent=lm_studio_agent,
            )
            refund_offer_made = True
            non_refund_turns += 1
        elif not refund_offer_made:
            next_text = await _next_agent_text(
                call_id=call_id,
                default_text=build_issue_briefing_message(context),
                order=context,
                transcript=transcript_context,
                phase="issue_briefing",
                lm_studio_agent=lm_studio_agent,
            )
            refund_offer_made = True
        else:
            next_text = await _next_agent_text(
                call_id=call_id,
                default_text=build_followup_message(context),
                order=context,
                transcript=transcript_context,
                phase="followup",
                lm_studio_agent=lm_studio_agent,
            )
            non_refund_turns += 1

        transcript_context.append({"speaker": "agent", "text": next_text})
        await _say_and_log(session, call_id, order_number, next_text)
        if disconnect_event.is_set():
            await push_call_status(call_id, "completed")
            ctx.shutdown(reason="participant_disconnected")
            return

        if refund_offer_made and non_refund_turns >= 3:
            closing_text = await _next_agent_text(
                call_id=call_id,
                default_text=build_no_refund_close_message(context),
                order=context,
                transcript=transcript_context,
                phase="no_refund_closing",
                lm_studio_agent=lm_studio_agent,
            )
            transcript_context.append({"speaker": "agent", "text": closing_text})
            await _say_and_log(session, call_id, order_number, closing_text)
            await push_call_status(call_id, "completed")
            ctx.shutdown(reason="refund_not_requested")
            return

        customer_turn = await _next_user_turn(user_turns, timeout_sec=20.0)
        if disconnect_event.is_set():
            await push_call_status(call_id, "completed")
            ctx.shutdown(reason="participant_disconnected")
            return


def run_worker() -> None:
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            ws_url=settings.livekit_ws_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
            agent_name=settings.livekit_agent_name,
        )
    )


if __name__ == "__main__":
    run_worker()
