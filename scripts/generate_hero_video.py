#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from textwrap import dedent
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "apps" / "web" / "assets" / "hero" / "refund-desk-hero.mp4"
DEFAULT_METADATA = DEFAULT_OUTPUT.with_suffix(".json")
DEFAULT_PROMPT_FILE = REPO_ROOT / "scripts" / "prompts" / "hero_video_call_center.txt"


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


def build_default_prompt() -> str:
    return dedent(
        """
        Photorealistic live-action promotional hero video for the homepage of a premium customer support app called Refund Desk.
        Real corporate call center environment, believable North American operations floor, one primary subject in focus:
        a calm customer support operator wearing a headset at a modern desk, with printed order sheets, a notebook, and a muted workstation.
        The operator is assisted by an AI calling platform that can place calls, resolve customer problems, and accept live speaking guidance from a human agent.
        Show the human operator quietly reviewing a customer issue, watching a call progress, and subtly typing one short intervention while the AI handles the conversation.
        The scene should imply AI-human collaboration without showing fake holograms, sci-fi effects, floating dashboards, or readable UI text.
        Use premium commercial cinematography, documentary realism, natural office lighting, shallow depth of field, restrained movement,
        35mm lens, smooth slow dolly or push-in, realistic skin texture, authentic hand motion, true-to-life proportions, understated wardrobe,
        crisp paper textures, quiet monitor glow, and soft ambient movement in the background.
        The subject should look competent, focused, and trustworthy, not theatrical.
        The final image must feel like footage from a high-end real startup brand film or enterprise commercial.
        No subtitles, no logos, no watermarks, no visible app interface text, no glitch effects, no cyberpunk palette,
        no surreal motion, no duplicated objects, no extra fingers, no warped hands, no porcelain skin, no exaggerated smiles,
        no CGI sheen, no AI-art look, no stock-footage cheesiness.
        """.strip()
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a realistic homepage hero video for Refund Desk using the MiniMax video API."
    )
    parser.add_argument("--token", default=os.getenv("MINIMAX_API_KEY", ""), help="MiniMax API key. Defaults to MINIMAX_API_KEY.")
    parser.add_argument("--api-base", default=os.getenv("MINIMAX_API_BASE", "https://api.minimax.io").rstrip("/"))
    parser.add_argument("--model", default="MiniMax-Hailuo-2.3")
    parser.add_argument("--duration", type=int, default=6)
    parser.add_argument("--resolution", default="1080P")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--prompt-file", default="")
    parser.add_argument("--first-frame-image", default="")
    parser.add_argument("--last-frame-image", default="")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--poll-interval", type=float, default=8.0)
    parser.add_argument("--timeout", type=float, default=900.0)
    return parser.parse_args()


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8").strip()
    if DEFAULT_PROMPT_FILE.exists():
        return DEFAULT_PROMPT_FILE.read_text(encoding="utf-8").strip()
    if args.prompt:
        return args.prompt.strip()
    return build_default_prompt()


def json_request(
    *,
    method: str,
    url: str,
    token: str,
    query: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    if query:
        url = f"{url}?{urlencode(query)}"

    headers = {"Authorization": f"Bearer {token}"}
    data: bytes | None = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    request = Request(url=url, method=method, headers=headers, data=data)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MiniMax request failed [{exc.code}] {method} {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"MiniMax request failed {method} {url}: {exc.reason}") from exc

    try:
        return json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"MiniMax returned non-JSON response for {method} {url}: {body[:300]}") from exc


def create_generation_task(args: argparse.Namespace, prompt: str) -> str:
    payload: dict[str, Any] = {
        "model": args.model,
        "prompt": prompt,
        "duration": args.duration,
        "resolution": args.resolution,
    }
    if args.first_frame_image:
        payload["first_frame_image"] = args.first_frame_image
    if args.last_frame_image:
        payload["last_frame_image"] = args.last_frame_image

    response = json_request(
        method="POST",
        url=f"{args.api_base}/v1/video_generation",
        token=args.token,
        payload=payload,
    )
    task_id = str(response.get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError(f"MiniMax did not return a task_id: {json.dumps(response, indent=2)}")
    return task_id


def poll_generation_task(args: argparse.Namespace, task_id: str) -> dict[str, Any]:
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        response = json_request(
            method="GET",
            url=f"{args.api_base}/v1/query/video_generation",
            token=args.token,
            query={"task_id": task_id},
        )
        status = str(response.get("status") or "")
        print(f"[MiniMax] task_id={task_id} status={status}", flush=True)
        if status == "Success":
            return response
        if status == "Fail":
            raise RuntimeError(f"MiniMax video generation failed: {json.dumps(response, indent=2)}")
        time.sleep(args.poll_interval)
    raise TimeoutError(f"Timed out waiting for MiniMax task {task_id} after {args.timeout:.0f}s")


def retrieve_file(args: argparse.Namespace, file_id: str) -> dict[str, Any]:
    response = json_request(
        method="GET",
        url=f"{args.api_base}/v1/files/retrieve",
        token=args.token,
        query={"file_id": file_id},
    )
    file_info = response.get("file") or {}
    if not isinstance(file_info, dict) or not file_info.get("download_url"):
        raise RuntimeError(f"MiniMax did not return a downloadable file: {json.dumps(response, indent=2)}")
    return file_info


def download_file(download_url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(download_url, method="GET")
    try:
        with urlopen(request, timeout=180.0) as response:
            data = response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Video download failed [{exc.code}] {download_url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Video download failed {download_url}: {exc.reason}") from exc

    output_path.write_bytes(data)


def write_metadata(
    metadata_path: Path,
    *,
    prompt: str,
    task_id: str,
    task_response: dict[str, Any],
    file_info: dict[str, Any],
    args: argparse.Namespace,
    output_path: Path,
) -> None:
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": "MiniMax",
        "model": args.model,
        "duration": args.duration,
        "resolution": args.resolution,
        "task_id": task_id,
        "file_id": file_info.get("file_id"),
        "output_path": str(output_path),
        "prompt": prompt,
        "download_url": file_info.get("download_url"),
        "video_width": task_response.get("video_width"),
        "video_height": task_response.get("video_height"),
        "first_frame_image": args.first_frame_image or None,
        "last_frame_image": args.last_frame_image or None,
        "created_at": int(time.time()),
    }
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    if not args.token.strip():
        print("Missing MiniMax API key. Set MINIMAX_API_KEY or pass --token.", file=sys.stderr)
        return 2

    prompt = read_prompt(args)
    output_path = Path(args.output).expanduser().resolve()
    metadata_path = Path(args.metadata).expanduser().resolve()

    print(f"[MiniMax] output={output_path}", flush=True)
    task_id = create_generation_task(args, prompt)
    print(f"[MiniMax] submitted task_id={task_id}", flush=True)

    task_response = poll_generation_task(args, task_id)
    file_id = str(task_response.get("file_id") or "").strip()
    if not file_id:
        raise RuntimeError(f"MiniMax task succeeded without file_id: {json.dumps(task_response, indent=2)}")

    file_info = retrieve_file(args, file_id)
    download_file(str(file_info["download_url"]), output_path)
    write_metadata(
        metadata_path,
        prompt=prompt,
        task_id=task_id,
        task_response=task_response,
        file_info=file_info,
        args=args,
        output_path=output_path,
    )

    print(f"[MiniMax] saved video to {output_path}", flush=True)
    print(f"[MiniMax] wrote metadata to {metadata_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
