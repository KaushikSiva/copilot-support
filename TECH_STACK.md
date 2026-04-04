# Tech Stack

## Overview

`copilot-support` is a Python-based voice support system with a static operations frontend. It is organized as a monorepo and split into three runtime surfaces:

- a public web UI for operators
- a FastAPI backend for orders, calls, and transcripts
- a LiveKit worker for real-time voice handling

The product flow is:

1. The frontend loads problem orders and call state from the API.
2. The API reads and writes order/call data in Insforge.
3. For live calls, the API asks LiveKit to create a room and place a SIP call.
4. The worker joins that room, handles speech, and posts transcript and status updates back to the API.
5. When a customer explicitly asks for a refund, the API updates the order status to `refunded`.

## Monorepo Structure

```text
apps/
  api/      FastAPI application, Insforge adapter, tests
  web/      Static frontend assets
  worker/   LiveKit voice worker
scripts/    Utility scripts for probes and asset generation
```

## Frontend

Location:

- [apps/web/index.html](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/apps/web/index.html)
- [apps/web/cases.html](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/apps/web/cases.html)
- [apps/web/styles.css](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/apps/web/styles.css)
- [apps/web/app.js](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/apps/web/app.js)

Stack:

- HTML for structure
- CSS for the Newsprint-inspired visual system
- vanilla JavaScript for API access, routing, and live transcript updates

Key characteristics:

- no React, Next.js, or SPA framework
- static assets served directly by FastAPI in local mode
- deployable as a static frontend to Insforge Deployments
- runtime-configurable API base URL through `app-config.js`

The frontend is intentionally simple at the runtime level. Most of the complexity lives in the API and worker, not in the browser.

## Backend API

Location:

- [apps/api/app/main.py](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/apps/api/app/main.py)
- [apps/api/app/config.py](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/apps/api/app/config.py)

Stack:

- Python
- FastAPI
- Uvicorn
- `httpx` for outbound HTTP calls

Responsibilities:

- serve the frontend locally
- expose REST endpoints for summary, orders, calls, transcript, and override actions
- bootstrap demo data
- mediate all writes to Insforge
- trigger live outbound call setup

Important design choice:

- the API exposes both a public-facing URL path for browser traffic and an internal callback URL path for the worker
- this avoids forcing the worker to call back through ngrok just because the browser needs a public endpoint

## Voice Worker

Location:

- [apps/worker/worker_app.py](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/apps/worker/worker_app.py)
- [apps/worker/internal_client.py](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/apps/worker/internal_client.py)

Stack:

- Python
- LiveKit Agents
- LiveKit RTC / SIP

Responsibilities:

- join the LiveKit room for an outbound call
- listen to customer speech
- speak agent responses
- post transcript turns to the API
- post call status changes to the API
- mark refunds complete only after explicit customer intent

This worker is the real-time part of the system. It should be treated as a separate long-running process from the FastAPI app.

## Data Layer

Primary store:

- Insforge tables and record APIs

Fallback store:

- local JSON file for demo/offline mode

Key files:

- [apps/api/app/services/insforge.py](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/apps/api/app/services/insforge.py)
- [apps/api/app/services/local_store.py](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/apps/api/app/services/local_store.py)
- [apps/api/app/services/repository.py](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/apps/api/app/services/repository.py)

Current data model includes:

- `orders`
- `order_items`
- `products`
- `call_sessions`
- `transcript_turns`

Operational behavior:

- all seeded demo orders start as `problematic`
- refund flow updates them to `refunded`
- call records track transcript, status, override state, and refund reference

## Telephony and Realtime Voice

Stack:

- LiveKit Cloud
- LiveKit SIP
- Twilio PSTN number

How it is used:

- the API requests a LiveKit dispatch and outbound SIP participant
- LiveKit places the phone call
- the worker handles the voice session inside the room

Important product rule:

- live outbound is hard-pinned to `+12149098059`
- stored customer phone numbers are not used for real PSTN outbound in this demo

## AI Stack

Current live defaults:

- STT: OpenAI `gpt-4o-transcribe`
- LLM: OpenAI `gpt-5`
- TTS: OpenAI `gpt-4o-mini-tts`

Optional path:

- LM Studio
- PersonaPlex-7B as a separate turn-generation backend

Important design choice:

- refund authorization logic is not delegated blindly to the model
- the system classifies explicit refund intent and keeps the refund state transition in application logic
- PersonaPlex, when enabled, only shapes the wording of the agent response

Relevant files:

- [apps/api/app/services/refund_agent.py](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/apps/api/app/services/refund_agent.py)
- [apps/api/app/services/lm_studio_agent.py](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/apps/api/app/services/lm_studio_agent.py)

## Deployment Stack

Frontend deployment:

- Insforge Deployments

Backend exposure during development:

- FastAPI on local port `8787`
- ngrok reserved domain:
  `https://unmythological-addyson-follicular.ngrok-free.dev`

Local process model:

1. `make dev` or `make dev-public`
2. `make worker`
3. `make ngrok` when public browser access is needed

Important separation:

- the public site can call the API through ngrok
- the worker still calls back to the local API directly through `INTERNAL_API_BASE_URL`

## Tooling and DX

Stack:

- `make` for common commands
- Python `venv`
- `unittest` for backend tests
- ad hoc scripts in `scripts/` for probes and asset generation

Useful files:

- [Makefile](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/Makefile)
- [scripts/probe_personaplex_lmstudio.py](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/scripts/probe_personaplex_lmstudio.py)
- [scripts/generate_hero_video.py](/Users/kaushiksivakumar/workspace/voicecall-insforge-refunds/scripts/generate_hero_video.py)

## Why This Stack

This stack is optimized for a demo that needs real voice calls, mutable ecommerce records, and a deployable operator UI without standing up a full microservice platform.

The choices are pragmatic:

- static frontend keeps the UI lightweight
- FastAPI is enough for the control plane
- LiveKit handles the real-time voice path
- Insforge replaces Dockerized local databases
- ngrok bridges a deployed frontend to a local backend during development
