# copilot-support

Monorepo demo that keeps the useful `voicecall` concepts:

- outbound call sessions
- transcript history
- next-turn override for live support interjection
- order-context-driven agent responses

The difference is data persistence: instead of Dockerized database services, this project uses Insforge table and record APIs. If Insforge credentials are not set, it falls back to a local JSON store so the demo still runs.

## Repo Layout

```text
apps/
  api/   FastAPI app, call engine, Insforge adapter, tests
  web/   Static Newsprint-style operations dashboard
```

## Demo Flow

1. Bootstrap 144 ecommerce orders, all in `problematic` status.
2. Launch an outbound callback for any order.
3. In `livekit` mode, all outbound calls are hard-pinned to a single safe target number for testing.
4. The agent opens with the order number, item summary, and shipping city, then asks the customer to confirm the order.
5. After confirmation, the agent explains the issue and offers the refund, but does not process it yet.
6. The call stays multi-turn until the customer explicitly asks for the refund or declines it for now.
7. Support can arm a one-time next-turn override while the call is in progress.
8. Only after an explicit refund request does the system mark the order `refunded`.

## Running

```bash
cd /Users/kaushiksivakumar/workspace/voicecall-insforge-refunds
cp .env.example .env
make install
make install-worker
make dev
# in a second terminal
make worker
```

Open `http://127.0.0.1:8787`.

## Public Backend Via ngrok

The frontend deployment at `https://8xepxi2n.insforge.site` is currently configured to call the backend through:

- `https://unmythological-addyson-follicular.ngrok-free.dev`

To keep that working:

```bash
cd /Users/kaushiksivakumar/workspace/voicecall-insforge-refunds
make dev-public
# in a second terminal
make ngrok
# in a third terminal for live calls
make worker
```

This repo now separates the public browser URL from the worker callback URL:

- `PUBLIC_API_BASE_URL` and `API_BASE_URL` can point to the ngrok URL
- `INTERNAL_API_BASE_URL` stays `http://127.0.0.1:8787` so the LiveKit worker still talks to the local FastAPI process directly

The frontend also sends `ngrok-skip-browser-warning: true` automatically for requests to `*.ngrok-free.dev`, so browser fetches do not get the ngrok interstitial page instead of JSON.

## Real Call Checklist

For a real outbound call to work, all of these need to be true:

1. `.env` must contain valid values for:
   - `INSFORGE_BASE_URL`
   - `INSFORGE_ADMIN_TOKEN`
   - `CALL_TRANSPORT=livekit`
   - `LIVEKIT_URL`
   - `LIVEKIT_WS_URL`
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`
   - `LIVEKIT_SIP_TRUNK_ID`
   - `TWILIO_PHONE_NUMBER`
   - `OPENAI_API_KEY`
   - optionally `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` if you want ElevenLabs TTS
2. The FastAPI app must be running on the same `INTERNAL_API_BASE_URL` used by the worker. The default is `http://127.0.0.1:8787`.
3. The LiveKit worker must be running. `make worker` now starts the worker in `start` mode.
4. The outbound target is hard-pinned to `+12149098059`. The stored customer phone on the order is ignored for live outbound.
5. Your LiveKit SIP trunk and Twilio number must be provisioned and allowed to place outbound PSTN calls to `+12149098059`.

Then trigger a call with:

```bash
curl -X POST http://127.0.0.1:8787/api/calls/outbound \
  -H 'Content-Type: application/json' \
  -d '{"order_number":"ORD-02411","operator_name":"city-desk"}'
```

If the call is accepted, the API will create a LiveKit room, dispatch the `phone-ai-agent`, and ask LiveKit SIP to dial `+12149098059`.

## PersonaPlex Separate Path

The live worker now supports a separate experimental LM Studio path without replacing the current OpenAI-based speech pipeline.

- `WHISPER_MODEL` still controls STT. The current `.env` uses `gpt-4o-transcribe`.
- `AGENT_BACKEND=auto` means each agent turn tries LM Studio first and falls back to the deterministic refund copy if LM Studio is unavailable.
- `AGENT_BACKEND=lm_studio` forces the same path, but the code still falls back per-turn if LM Studio errors.
- `PERSONAPLEX_MODEL=PersonaPlex-7B` is the requested LM Studio model id.
- The worker keeps the refund decision logic outside the model. PersonaPlex only phrases the next agent turn for phases like `opening`, `issue_briefing`, `followup`, `refund_confirmation`, and `refund_closing`.
- Human support override still wins. If support arms a next-turn prompt, that text is spoken instead of the LM Studio response.

Once LM Studio finishes downloading and starts serving the model at `LM_STUDIO_BASE_URL`, the existing worker should start using it on the next generated turn without a code change.

You can probe the isolated path without touching live telephony:

```bash
cd /Users/kaushiksivakumar/workspace/voicecall-insforge-refunds
python3 scripts/probe_personaplex_lmstudio.py --list-only
python3 scripts/probe_personaplex_lmstudio.py --multi-turn-demo
```

The multi-turn demo exercises the same phases the worker uses:

1. Opening
2. Issue briefing
3. Follow-up while waiting for explicit refund approval
4. Refund confirmation after approval
5. Refund closing

## Insforge Configuration

Set these variables in `.env` or your shell:

- `INSFORGE_BASE_URL`
- `INSFORGE_ADMIN_TOKEN`
- `CALL_TRANSPORT`
- `LIVE_OUTBOUND_TARGET_NUMBER`

The checked-in `.env` uses `CALL_TRANSPORT=livekit` and hard-pins outbound telephony to `+12149098059`.

Expected API shapes are based on the Insforge docs:

- `GET /api/database/tables`
- `POST /api/database/tables`
- `POST /api/database/records/{tableName}`
- `PATCH /api/database/records/{tableName}`
- `GET /api/database/records/{tableName}`

If both Insforge variables are present, the API app creates missing tables and seeds them on startup when the `orders` table is empty.

## Notes

- The call execution is demo-first and deterministic; it mirrors the orchestration and override patterns from `voicecall` without pulling in Docker, Redis, or PSTN dependencies.
- The simulation mode still exists for local fallback, but the configured default now uses LiveKit SIP with a separate worker process.
- The frontend is intentionally editorial and high-contrast, following the Newsprint design direction you supplied.
