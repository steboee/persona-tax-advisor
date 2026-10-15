"""Optional server-side speech providers.

The default setup needs none of this: the browser does speech recognition (Web Speech API, sk-SK) and speech
synthesis. These providers are for better voices or browsers without speech recognition (e.g. Firefox).
"""

from __future__ import annotations

import io
from functools import lru_cache

import httpx

from taxadvisor.config import Settings


class VoiceNotConfigured(RuntimeError):
    pass


def stt_available(settings: Settings) -> bool:
    if settings.stt_provider == "openai":
        return bool(settings.openai_api_key)
    if settings.stt_provider == "local":
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True
    return False


def tts_available(settings: Settings) -> bool:
    if settings.tts_provider == "openai":
        return bool(settings.openai_api_key)
    if settings.tts_provider == "elevenlabs":
        return bool(settings.elevenlabs_api_key and settings.elevenlabs_voice_id)
    return False


async def transcribe(settings: Settings, audio: bytes, filename: str, lang: str) -> str:
    if not stt_available(settings):
        raise VoiceNotConfigured("Server speech recognition is not configured (STT_PROVIDER).")
    if settings.stt_provider == "openai":
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                data={"model": settings.openai_stt_model, "language": lang},
                files={"file": (filename, audio)},
            )
            resp.raise_for_status()
            return resp.json().get("text", "").strip()
    model = _local_whisper(settings.local_whisper_model)
    segments, _ = model.transcribe(io.BytesIO(audio), language=lang)
    return " ".join(seg.text.strip() for seg in segments).strip()


@lru_cache(maxsize=1)
def _local_whisper(size: str):  # pragma: no cover - optional heavy dependency
    from faster_whisper import WhisperModel

    return WhisperModel(size, compute_type="int8")


async def synthesize(settings: Settings, text: str, lang: str) -> tuple[bytes, str]:
    """Returns (audio bytes, media type)."""
    if not tts_available(settings):
        raise VoiceNotConfigured("Server speech synthesis is not configured (TTS_PROVIDER).")
    async with httpx.AsyncClient(timeout=120) as client:
        if settings.tts_provider == "openai":
            resp = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_tts_model,
                    "voice": settings.openai_tts_voice,
                    "input": text,
                    "instructions": "Speak Slovak naturally." if lang == "sk" else "Speak naturally.",
                    "response_format": "mp3",
                },
            )
        else:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}",
                headers={"xi-api-key": settings.elevenlabs_api_key or "", "accept": "audio/mpeg"},
                json={"text": text, "model_id": settings.elevenlabs_model, "language_code": lang},
            )
        resp.raise_for_status()
        return resp.content, "audio/mpeg"
