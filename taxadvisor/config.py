"""Runtime configuration, read from environment variables and an optional `.env` file in the repo root."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Domains the advisor may open with WebFetch. Search (WebSearch) is unrestricted; fetching is limited to
# official and well-known Slovak tax sources so that arbitrary pages can't be pulled into the conversation.
WEB_FETCH_DOMAINS = [
    "slov-lex.sk",
    "static.slov-lex.sk",
    "www.slov-lex.sk",
    "financnasprava.sk",
    "www.financnasprava.sk",
    "podpora.financnasprava.sk",
    "www.socpoist.sk",
    "www.employment.gov.sk",
    "www.mfsr.sk",
    "www.nrsr.sk",
    "www.slovensko.sk",
    "www.zakonypreludi.sk",
    "www.podnikajte.sk",
]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines). Real environment variables win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


@dataclass
class Settings:
    advisor_dir: Path
    data_dir: Path
    web_dir: Path
    claude_bin: str = "claude"
    model_quick: str = "sonnet"
    model_deep: str = "opus"
    model_law_analysis: str = "opus"
    claude_timeout_s: float = 600.0
    claude_extra_args: list[str] = field(default_factory=list)
    isolate_claude_config: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    token: str | None = None
    law_sync_interval_hours: float = 24.0
    law_sync_analyze: bool = True
    law_news_interval_days: float = 7.0
    law_analysis_max_per_run: int = 5
    stt_provider: str = "none"  # none | openai | local
    tts_provider: str = "none"  # none | openai | elevenlabs
    openai_api_key: str | None = None
    openai_stt_model: str = "gpt-4o-mini-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    elevenlabs_model: str = "eleven_multilingual_v2"
    local_whisper_model: str = "small"

    @property
    def laws_dir(self) -> Path:
        return self.advisor_dir / "laws"

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(REPO_ROOT / ".env")
        env = os.environ.get
        return cls(
            advisor_dir=Path(env("ADVISOR_DIR") or REPO_ROOT / "advisor").resolve(),
            data_dir=Path(env("DATA_DIR") or REPO_ROOT / "data").resolve(),
            web_dir=Path(env("WEB_DIR") or REPO_ROOT / "web").resolve(),
            claude_bin=env("CLAUDE_BIN") or "claude",
            model_quick=env("MODEL_QUICK") or "sonnet",
            model_deep=env("MODEL_DEEP") or "opus",
            model_law_analysis=env("MODEL_LAW_ANALYSIS") or "opus",
            claude_timeout_s=_float("CLAUDE_TIMEOUT_S", 600.0),
            claude_extra_args=shlex.split(env("CLAUDE_EXTRA_ARGS") or ""),
            isolate_claude_config=_bool("ISOLATE_CLAUDE_CONFIG", True),
            host=env("HOST") or "127.0.0.1",
            port=int(env("PORT") or 8765),
            token=env("ADVISOR_TOKEN") or None,
            law_sync_interval_hours=_float("LAW_SYNC_INTERVAL_HOURS", 24.0),
            law_sync_analyze=_bool("LAW_SYNC_ANALYZE", True),
            law_news_interval_days=_float("LAW_NEWS_INTERVAL_DAYS", 7.0),
            law_analysis_max_per_run=int(env("LAW_ANALYSIS_MAX_PER_RUN") or 5),
            stt_provider=(env("STT_PROVIDER") or "none").lower(),
            tts_provider=(env("TTS_PROVIDER") or "none").lower(),
            openai_api_key=env("OPENAI_API_KEY") or None,
            openai_stt_model=env("OPENAI_STT_MODEL") or "gpt-4o-mini-transcribe",
            openai_tts_model=env("OPENAI_TTS_MODEL") or "gpt-4o-mini-tts",
            openai_tts_voice=env("OPENAI_TTS_VOICE") or "alloy",
            elevenlabs_api_key=env("ELEVENLABS_API_KEY") or None,
            elevenlabs_voice_id=env("ELEVENLABS_VOICE_ID") or None,
            elevenlabs_model=env("ELEVENLABS_MODEL") or "eleven_multilingual_v2",
            local_whisper_model=env("LOCAL_WHISPER_MODEL") or "small",
        )
