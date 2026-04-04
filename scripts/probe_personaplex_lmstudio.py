#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_repo_dotenv() -> None:
    for env_path in (REPO_ROOT / ".env", REPO_ROOT / ".env.local"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_repo_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe a separate LM Studio PersonaPlex path without changing the main worker stack."
    )
    parser.add_argument("--base-url", default=os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/"))
    parser.add_argument("--api-key", default=os.getenv("LM_STUDIO_API_KEY", "lm-studio"))
    parser.add_argument("--model", default=os.getenv("PERSONAPLEX_MODEL", ""))
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument(
        "--prompt",
        default=(
            "You are a concise customer support voice agent. "
            "A customer confirms order ORD-02541 is correct, but has not yet asked for a refund. "
            "Briefly explain the problem, offer the refund, and wait for explicit approval before processing it."
        ),
    )
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--multi-turn-demo", action="store_true")
    return parser.parse_args()


def json_request(method: str, url: str, api_key: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    data: bytes | None = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = Request(url=url, method=method, headers=headers, data=data)
    try:
        with urlopen(request, timeout=60.0) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LM Studio request failed [{exc.code}] {method} {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"LM Studio request failed {method} {url}: {exc.reason}") from exc
    return json.loads(body) if body else {}


def list_models(base_url: str, api_key: str) -> list[dict[str, Any]]:
    payload = json_request("GET", f"{base_url}/models", api_key)
    data = payload.get("data")
    return data if isinstance(data, list) else []


def choose_model(models: list[dict[str, Any]], requested: str) -> str:
    if requested:
        return requested
    ids = [str(item.get("id") or "") for item in models]
    for candidate in ids:
        lowered = candidate.lower()
        if "persona" in lowered or "plex" in lowered:
            return candidate
    raise RuntimeError(
        "No PersonaPlex-like model id was found. Pass --model explicitly or set PERSONAPLEX_MODEL in .env."
    )


def run_chat(base_url: str, api_key: str, model: str, prompt: str, temperature: float) -> dict[str, Any]:
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are testing a separate experimental PersonaPlex path for a voice support product. "
                    "Reply with natural spoken language only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    return json_request("POST", f"{base_url}/chat/completions", api_key, payload)


def multi_turn_demo(order_number: str = "ORD-02541") -> list[dict[str, str]]:
    order = {
        "order_number": order_number,
        "customer_name": "Jordan Lee",
        "shipping_city": "Dallas",
        "issue_reason": "carrier damage claim",
        "refund_amount": 264.95,
        "items_preview": [
            {"quantity": 1, "product_name": "Ashwood Standing Lamp"},
            {"quantity": 2, "product_name": "Glass Shade Kit"},
        ],
    }
    return [
        {
            "phase": "opening",
            "speaker": "customer",
            "text": f"Yes, order {order_number} going to Dallas is mine.",
            "order": order,
        },
        {
            "phase": "issue_briefing",
            "speaker": "customer",
            "text": "What exactly went wrong with the shipment?",
            "order": order,
        },
        {
            "phase": "followup",
            "speaker": "customer",
            "text": "If the full amount is coming back, go ahead and refund it.",
            "order": order,
        },
        {
            "phase": "refund_confirmation",
            "speaker": "customer",
            "text": "Okay, thanks for handling it.",
            "order": {**order, "refund_reference": "RF-2541-04042015"},
        },
        {
            "phase": "refund_closing",
            "speaker": "customer",
            "text": "",
            "order": {**order, "refund_reference": "RF-2541-04042015"},
        },
    ]


def build_phase_prompt(
    phase: str,
    order: dict[str, Any],
    transcript: list[dict[str, str]],
    refund_reference: str = "",
) -> str:
    refund_amount = float(order.get("refund_amount") or 0.0)
    items_preview = order.get("items_preview") or []
    item_summary = ", ".join(
        f"{int(item.get('quantity', 1) or 1)} {str(item.get('product_name', 'item')).strip()}"
        for item in items_preview[:2]
    ) or "the order items"
    phase_instructions = {
        "opening": "Open the call, mention the order number and item summary, then ask the customer to confirm the order.",
        "issue_briefing": "The customer confirmed the order. Explain the problem, mention the refund amount, and ask if they want the refund processed now.",
        "followup": "The customer has not explicitly approved the refund yet. Keep the refund unprocessed, answer naturally, and ask one concise question that moves toward a decision.",
        "refund_confirmation": "The customer explicitly requested the refund and the system already processed it. Confirm the amount and give the refund reference.",
        "refund_closing": "Close the call after a completed refund. Mention email confirmation and the refund reference.",
    }
    transcript_excerpt = "\n".join(f"{turn['speaker']}: {turn['text']}" for turn in transcript[-8:]) or "(no transcript yet)"
    return (
        "You are a concise customer support voice agent for Refund Desk. "
        "Sound natural and spoken, not written. Do not mention being AI.\n"
        f"Phase: {phase}\n"
        f"Instructions: {phase_instructions.get(phase, 'Reply naturally as a support agent.')}\n"
        f"Order number: {order['order_number']}\n"
        f"Customer name: {order['customer_name']}\n"
        f"Shipping city: {order['shipping_city']}\n"
        f"Issue reason: {order['issue_reason']}\n"
        f"Order summary: {item_summary}\n"
        f"Refund amount: ${refund_amount:.2f}\n"
        f"Refund reference: {refund_reference or '(not processed yet)'}\n"
        "Recent transcript:\n"
        f"{transcript_excerpt}\n"
        "Write only the next agent turn."
    )


def main() -> int:
    args = parse_args()
    models = list_models(args.base_url, args.api_key)
    print(json.dumps({"base_url": args.base_url, "models": models}, indent=2), flush=True)
    if args.list_only:
        return 0

    model = choose_model(models, args.model)
    if args.multi_turn_demo:
        transcript: list[dict[str, str]] = []
        outputs: list[dict[str, Any]] = []
        for step in multi_turn_demo():
            refund_reference = str(step["order"].get("refund_reference") or "")
            prompt = build_phase_prompt(step["phase"], step["order"], transcript, refund_reference=refund_reference)
            response = run_chat(args.base_url, args.api_key, model, prompt, args.temperature)
            text = (
                response.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            agent_text = str(text or "").strip()
            transcript.append({"speaker": "agent", "text": agent_text})
            customer_text = str(step["text"] or "").strip()
            if customer_text:
                transcript.append({"speaker": step["speaker"], "text": customer_text})
            outputs.append(
                {
                    "phase": step["phase"],
                    "agent_text": agent_text,
                    "next_customer_text": customer_text,
                }
            )
        print(json.dumps({"selected_model": model, "multi_turn_demo": outputs}, indent=2), flush=True)
        return 0

    response = run_chat(args.base_url, args.api_key, model, args.prompt, args.temperature)
    message = (
        response.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    print(json.dumps({"selected_model": model, "response": response, "text": message}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
