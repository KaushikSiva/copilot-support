from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _load_dotenv(project_root: Path) -> None:
    candidate_files = [
        project_root / ".env",
        project_root / ".env.local",
        project_root.parent / "voicecall" / ".env",
    ]
    for env_file in candidate_files:
        if not env_file.exists():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    project_root: Path
    web_root: Path
    local_data_file: Path
    insforge_base_url: str = ""
    insforge_admin_token: str = ""
    insforge_project_name: str = "ecommerce"
    call_transport: str = "simulation"
    live_outbound_target_number: str = "+12149098059"
    api_base_url: str = "http://127.0.0.1:8787"
    public_api_base_url: str = "http://127.0.0.1:8787"
    internal_api_base_url: str = "http://127.0.0.1:8787"
    livekit_url: str = ""
    livekit_ws_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_sip_trunk_id: str = ""
    livekit_agent_name: str = "phone-ai-agent"
    livekit_default_room_prefix: str = "refund"
    twilio_phone_number: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    agent_backend: str = "auto"
    lm_studio_base_url: str = "http://127.0.0.1:1234/v1"
    lm_studio_api_key: str = "lm-studio"
    personaplex_model: str = "PersonaPlex-7B"
    lm_studio_timeout_sec: float = 8.0
    lm_studio_temperature: float = 0.2
    tts_provider: str = "openai"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "ash"
    openai_tts_speed: float = 1.0
    whisper_base_url: str = ""
    whisper_api_key: str = "local-whisper"
    whisper_model: str = "whisper-1"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_tts_model: str = "eleven_turbo_v2_5"
    demo_order_count: int = 144
    call_step_delay_sec: float = 1.4
    override_grace_sec: float = 2.4
    default_support_operator: str = "city-desk"
    request_timeout_sec: float = 20.0

    @property
    def data_mode(self) -> str:
        if self.insforge_base_url and self.insforge_admin_token:
            return "insforge"
        return "local"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[3]
    _load_dotenv(project_root)
    web_root = project_root / "apps" / "web"
    local_data_file = project_root / "apps" / "api" / "data" / "local_store.json"

    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8787").strip().rstrip("/")
    public_api_base_url = os.getenv("PUBLIC_API_BASE_URL", api_base_url).strip().rstrip("/") or api_base_url
    internal_api_base_url = os.getenv("INTERNAL_API_BASE_URL", api_base_url).strip().rstrip("/") or api_base_url

    return Settings(
        project_root=project_root,
        web_root=web_root,
        local_data_file=local_data_file,
        insforge_base_url=os.getenv("INSFORGE_BASE_URL", "").strip().rstrip("/"),
        insforge_admin_token=os.getenv("INSFORGE_ADMIN_TOKEN", "").strip(),
        insforge_project_name=os.getenv("INSFORGE_PROJECT_NAME", "ecommerce").strip() or "ecommerce",
        call_transport=os.getenv("CALL_TRANSPORT", "simulation").strip().lower() or "simulation",
        live_outbound_target_number=os.getenv("LIVE_OUTBOUND_TARGET_NUMBER", "+12149098059").strip(),
        api_base_url=api_base_url,
        public_api_base_url=public_api_base_url,
        internal_api_base_url=internal_api_base_url,
        livekit_url=os.getenv("LIVEKIT_URL", "").strip().rstrip("/"),
        livekit_ws_url=os.getenv("LIVEKIT_WS_URL", "").strip(),
        livekit_api_key=os.getenv("LIVEKIT_API_KEY", "").strip(),
        livekit_api_secret=os.getenv("LIVEKIT_API_SECRET", "").strip(),
        livekit_sip_trunk_id=os.getenv("LIVEKIT_SIP_TRUNK_ID", "").strip(),
        livekit_agent_name=os.getenv("LIVEKIT_AGENT_NAME", "phone-ai-agent").strip() or "phone-ai-agent",
        livekit_default_room_prefix=os.getenv("LIVEKIT_DEFAULT_ROOM_PREFIX", "refund").strip() or "refund",
        twilio_phone_number=os.getenv("TWILIO_PHONE_NUMBER", "").strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        agent_backend=os.getenv("AGENT_BACKEND", "auto").strip().lower() or "auto",
        lm_studio_base_url=os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1").strip().rstrip("/"),
        lm_studio_api_key=os.getenv("LM_STUDIO_API_KEY", "lm-studio").strip() or "lm-studio",
        personaplex_model=os.getenv("PERSONAPLEX_MODEL", "PersonaPlex-7B").strip() or "PersonaPlex-7B",
        lm_studio_timeout_sec=max(float(os.getenv("LM_STUDIO_TIMEOUT_SEC", "8.0")), 1.0),
        lm_studio_temperature=float(os.getenv("LM_STUDIO_TEMPERATURE", "0.2")),
        tts_provider=os.getenv("TTS_PROVIDER", "openai").strip() or "openai",
        openai_tts_model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts").strip() or "gpt-4o-mini-tts",
        openai_tts_voice=os.getenv("OPENAI_TTS_VOICE", "ash").strip() or "ash",
        openai_tts_speed=float(os.getenv("OPENAI_TTS_SPEED", "1.0")),
        whisper_base_url=os.getenv("WHISPER_BASE_URL", "").strip(),
        whisper_api_key=os.getenv("WHISPER_API_KEY", "local-whisper").strip() or "local-whisper",
        whisper_model=os.getenv("WHISPER_MODEL", "whisper-1").strip() or "whisper-1",
        elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", "").strip(),
        elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", "").strip(),
        elevenlabs_tts_model=os.getenv("ELEVENLABS_TTS_MODEL", "eleven_turbo_v2_5").strip() or "eleven_turbo_v2_5",
        demo_order_count=max(int(os.getenv("DEMO_ORDER_COUNT", "144")), 12),
        call_step_delay_sec=max(float(os.getenv("CALL_STEP_DELAY_SEC", "1.4")), 0.2),
        override_grace_sec=max(float(os.getenv("OVERRIDE_GRACE_SEC", "2.4")), 0.0),
        default_support_operator=os.getenv("DEFAULT_SUPPORT_OPERATOR", "city-desk").strip() or "city-desk",
    )
