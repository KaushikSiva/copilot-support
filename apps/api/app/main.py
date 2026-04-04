from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.services.call_engine import CallEngine
from app.services.live_outbound import LiveOutboundService
from app.services.override_broker import OverrideBroker
from app.services.repository import build_repository


logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    repository = build_repository(settings)
    repository.bootstrap(settings.demo_order_count)
    override_broker = OverrideBroker()
    app.state.repository = repository
    app.state.override_broker = override_broker
    app.state.call_engine = CallEngine(repository, settings, override_broker=override_broker)
    app.state.live_outbound = LiveOutboundService(repository, settings)
    yield
    await app.state.call_engine.shutdown()


app = FastAPI(title="VoiceCall Insforge Refund Desk", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def allow_private_network_access(request: Request, call_next):
    response = await call_next(request)
    if request.headers.get("access-control-request-private-network", "").lower() == "true":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


def repo(request: Request):
    return request.app.state.repository


def engine(request: Request) -> CallEngine:
    return request.app.state.call_engine


def overrides(request: Request) -> OverrideBroker:
    return request.app.state.override_broker


def live_outbound(request: Request) -> LiveOutboundService:
    return request.app.state.live_outbound


@app.exception_handler(KeyError)
async def handle_key_error(_: Request, exc: KeyError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "mode": settings.data_mode,
        "project_name": settings.insforge_project_name,
        "public_api_base_url": settings.public_api_base_url,
        "internal_api_base_url": settings.internal_api_base_url,
        "call_transport": settings.call_transport,
        "live_outbound_target_number": settings.live_outbound_target_number,
        "agent_backend": settings.agent_backend,
        "personaplex_model": settings.personaplex_model,
        "lm_studio_base_url": settings.lm_studio_base_url,
        "whisper_model": settings.whisper_model,
        "tts_provider": settings.tts_provider,
    }


@app.post("/api/admin/bootstrap")
def bootstrap_demo(request: Request) -> dict[str, Any]:
    return repo(request).bootstrap(settings.demo_order_count)


@app.get("/api/summary")
def summary(request: Request) -> dict[str, Any]:
    return repo(request).get_summary()


@app.get("/api/orders")
def list_orders(request: Request, status: str | None = None, limit: int = 50) -> dict[str, Any]:
    items = repo(request).list_orders(status=status, limit=limit)
    return {"items": items, "total": len(items)}


@app.get("/api/orders/{order_number}")
def get_order(order_number: str, request: Request) -> dict[str, Any]:
    item = repo(request).get_order(order_number)
    if not item:
        raise HTTPException(status_code=404, detail="Order not found")
    return item


@app.get("/api/calls")
def list_calls(request: Request, limit: int = 12) -> dict[str, Any]:
    items = repo(request).list_calls(limit=limit)
    return {"items": items, "total": len(items)}


@app.post("/api/calls/outbound")
async def create_outbound_call(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    order_number = str(payload.get("order_number", "") or "").strip()
    operator_name = str(payload.get("operator_name", "") or settings.default_support_operator).strip()
    if not order_number:
        raise HTTPException(status_code=422, detail="order_number is required")
    if settings.call_transport == "livekit":
        call = await live_outbound(request).start_outbound_refund_call(order_number, operator_name)
    else:
        call = await engine(request).start_outbound_refund_call(order_number, operator_name)
    return call


@app.get("/api/calls/{call_id}")
def get_call(call_id: str, request: Request) -> dict[str, Any]:
    item = repo(request).get_call(call_id)
    if not item:
        raise HTTPException(status_code=404, detail="Call not found")
    return item


@app.get("/api/calls/{call_id}/transcript")
def get_transcript(call_id: str, request: Request) -> dict[str, Any]:
    if not repo(request).get_call(call_id):
        raise HTTPException(status_code=404, detail="Call not found")
    items = repo(request).list_transcript(call_id)
    return {"items": items, "total": len(items)}


@app.get("/api/calls/{call_id}/next-turn")
def get_next_turn(call_id: str, request: Request) -> dict[str, Any]:
    if not repo(request).get_call(call_id):
        raise HTTPException(status_code=404, detail="Call not found")
    return {"text": overrides(request).get(call_id) or repo(request).get_next_turn_override(call_id)}


@app.post("/api/calls/{call_id}/next-turn")
def set_next_turn(call_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    text = str(payload.get("text", "") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Missing override text")
    overrides(request).set(call_id, text)
    repo(request).set_next_turn_override(call_id, text)
    return {"ok": True}


@app.delete("/api/calls/{call_id}/next-turn")
def clear_next_turn(call_id: str, request: Request) -> dict[str, Any]:
    overrides(request).clear(call_id)
    repo(request).clear_next_turn_override(call_id)
    return {"ok": True}


@app.post("/api/calls/{call_id}/next-turn/consume")
def consume_next_turn(call_id: str, request: Request) -> dict[str, Any]:
    if not repo(request).get_call(call_id):
        raise HTTPException(status_code=404, detail="Call not found")
    text = overrides(request).consume(call_id) or repo(request).consume_next_turn_override(call_id)
    if text:
        repo(request).clear_next_turn_override(call_id)
    return {"text": text}


@app.post("/api/internal/transcript")
def internal_add_transcript(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    call_id = str(payload.get("call_id", "") or "").strip()
    speaker = str(payload.get("speaker", "") or "").strip()
    text = str(payload.get("text", "") or "").strip()
    if not call_id or not speaker or not text:
        raise HTTPException(status_code=422, detail="Invalid payload")
    call = repo(request).get_call(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    turn = repo(request).append_transcript(call_id, call["order_number"], speaker, text)
    return {"ok": True, "turn_id": turn.get("turn_id") or turn.get("id")}


@app.post("/api/internal/call-status")
def internal_update_call_status(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    call_id = str(payload.get("call_id", "") or "").strip()
    status = str(payload.get("status", "") or "").strip()
    if not call_id or not status:
        raise HTTPException(status_code=422, detail="Invalid payload")
    call = repo(request).update_call_session(call_id, {"status": status})
    return {"ok": True, "status": call["status"]}


@app.post("/api/internal/refund-complete")
def internal_refund_complete(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    call_id = str(payload.get("call_id", "") or "").strip()
    order_number = str(payload.get("order_number", "") or "").strip()
    refund_reference = str(payload.get("refund_reference", "") or "").strip()
    if not call_id or not order_number or not refund_reference:
        raise HTTPException(status_code=422, detail="Invalid payload")
    order = repo(request).mark_order_refunded(order_number, refund_reference, call_id)
    repo(request).update_call_session(call_id, {"refund_reference": refund_reference})
    return {"ok": True, "order_number": order["order_number"], "refund_reference": refund_reference}


app.mount("/", StaticFiles(directory=settings.web_root, html=True), name="web")
