"""FastAPI server: chat (SSE) over `claude -p`, optional voice endpoints, memory and law changelog APIs, web UI."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from taxadvisor import __version__
from taxadvisor.claude_runner import StreamTranslator, build_chat_command, stream_claude
from taxadvisor.config import Settings
from taxadvisor.laws.jobs import LawJobs
from taxadvisor.laws.sync import load_json
from taxadvisor.sessions import ConversationStore
from taxadvisor import voice

log = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    mode: str = Field(default="quick", pattern="^(quick|deep)$")
    voice: bool = False
    lang: str = Field(default="sk", pattern="^(sk|en)$")


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    lang: str = Field(default="sk", pattern="^(sk|en)$")


class SyncRequest(BaseModel):
    analyze: bool = True
    news: bool = False
    law_ids: list[str] | None = None


def create_app(settings: Settings | None = None, *, run_scheduler: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()
    store = ConversationStore(settings.data_dir / "conversations.json")
    jobs = LawJobs(settings)
    locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = None
        if run_scheduler and (settings.law_sync_interval_hours > 0 or settings.law_news_interval_days > 0):
            task = asyncio.create_task(jobs.scheduler())
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Persona Tax Advisor", version=__version__, lifespan=lifespan)

    def require_token(request: Request) -> None:
        if not settings.token:
            return
        header = request.headers.get("authorization", "")
        supplied = header[7:] if header.lower().startswith("bearer ") else request.query_params.get("token")
        if supplied != settings.token:
            raise HTTPException(status_code=401, detail="Missing or invalid token")

    auth = [Depends(require_token)]

    # ------------------------------------------------------------------ meta

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "version": __version__,
            "claude_found": shutil.which(settings.claude_bin) is not None,
            "advisor_dir": str(settings.advisor_dir),
        }

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        return {
            "auth_required": bool(settings.token),
            "stt_server": voice.stt_available(settings),
            "tts_server": voice.tts_available(settings),
            "models": {"quick": settings.model_quick, "deep": settings.model_deep},
        }

    # ------------------------------------------------------------------ chat

    @app.post("/api/chat", dependencies=auth)
    async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
        conv = store.get(req.conversation_id) if req.conversation_id else None
        if req.conversation_id and conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conv is None:
            conv = store.create(title=" ".join(req.message.split())[:60])
        conv_id = conv["id"]
        lock = locks.setdefault(conv_id, asyncio.Lock())

        async def events():
            def sse(payload: dict[str, Any]) -> str:
                return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            yield sse({"type": "conversation", "id": conv_id, "title": conv["title"]})
            if lock.locked():
                yield sse({"type": "error", "message": "Predchádzajúca odpoveď v tomto rozhovore ešte beží."})
                return
            async with lock:
                current = store.get(conv_id) or conv
                store.add_message(conv_id, "user", req.message, mode=req.mode, voice=req.voice)
                cmd = build_chat_command(
                    settings,
                    req.message,
                    mode=req.mode,
                    voice=req.voice,
                    lang=req.lang,
                    session_id=current["claude_session_id"],
                    resume=current["started"],
                )
                translator = StreamTranslator()
                done: dict[str, Any] | None = None
                stream = stream_claude(cmd, cwd=str(settings.advisor_dir), timeout_s=settings.claude_timeout_s)
                try:
                    async for raw in stream:
                        for ev in translator.feed(raw):
                            if ev["type"] == "session":
                                store.mark_started(conv_id, ev["session_id"])
                            if ev["type"] == "done":
                                done = ev
                            yield sse(ev)
                        if await request.is_disconnected():
                            log.info("client disconnected, stopping claude for %s", conv_id)
                            break
                except RuntimeError as exc:
                    store.reset_session(conv_id)
                    yield sse({"type": "error", "message": str(exc)})
                    return
                finally:
                    await stream.aclose()  # kills the claude process if it is still running
                if done is None:
                    yield sse({"type": "error", "message": "Claude skončil bez odpovede."})
                    return
                store.mark_started(conv_id, done.get("session_id"))
                store.add_message(
                    conv_id,
                    "assistant",
                    done["text"],
                    cost_usd=done.get("cost_usd"),
                    duration_ms=done.get("duration_ms"),
                    memory_saved=done.get("memory_saved"),
                )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/conversations", dependencies=auth)
    def conversations() -> list[dict[str, Any]]:
        return store.list()

    @app.get("/api/conversations/{conv_id}", dependencies=auth)
    def conversation(conv_id: str) -> dict[str, Any]:
        conv = store.get(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conv

    @app.delete("/api/conversations/{conv_id}", dependencies=auth)
    def delete_conversation(conv_id: str) -> dict[str, bool]:
        return {"deleted": store.delete(conv_id)}

    # ------------------------------------------------------------------ memory (profile)

    @app.get("/api/memory", dependencies=auth)
    def memory() -> dict[str, str]:
        profile = settings.advisor_dir / "profile"

        def read(name: str) -> str:
            path = profile / name
            return path.read_text(encoding="utf-8") if path.is_file() else ""

        return {"company": read("company.md"), "memory": read("memory.md")}

    # ------------------------------------------------------------------ laws

    @app.get("/api/laws/changelog", dependencies=auth)
    def law_changelog(limit: int = 100) -> list[dict[str, Any]]:
        return load_json(settings.laws_dir / "changelog.json", [])[:limit]

    @app.get("/api/laws/status", dependencies=auth)
    def law_status() -> dict[str, Any]:
        manifest = load_json(settings.laws_dir / "manifest.json", {"laws": {}})
        registry = load_json(settings.laws_dir / "registry.json", {"laws": []})
        laws = []
        for item in registry.get("laws", []):
            st = manifest.get("laws", {}).get(item["id"], {})
            laws.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "ref": f"{item['number']}/{item['year']} Z. z.",
                    "enabled": item.get("enabled", True),
                    "current": st.get("current"),
                    "upcoming": st.get("upcoming", []),
                    "last_checked": st.get("last_checked"),
                    "last_error": st.get("last_error"),
                }
            )
        return {
            "updated": manifest.get("updated"),
            "last_news_check": manifest.get("last_news_check"),
            "laws": laws,
            "job": jobs.status,
        }

    @app.post("/api/laws/sync", dependencies=auth)
    def law_sync(req: SyncRequest) -> JSONResponse:
        started = jobs.start(analyze=req.analyze, news=req.news, law_ids=req.law_ids)
        return JSONResponse({"started": started, "job": jobs.status}, status_code=202 if started else 409)

    # ------------------------------------------------------------------ voice (optional server providers)

    @app.post("/api/stt", dependencies=auth)
    async def stt(audio: UploadFile = File(...), lang: str = Form("sk")) -> dict[str, str]:
        data = await audio.read()
        try:
            text = await voice.transcribe(settings, data, audio.filename or "audio.webm", lang)
        except voice.VoiceNotConfigured as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        return {"text": text}

    @app.post("/api/tts", dependencies=auth)
    async def tts(req: TTSRequest) -> Response:
        try:
            audio, media_type = await voice.synthesize(settings, req.text, req.lang)
        except voice.VoiceNotConfigured as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        return Response(content=audio, media_type=media_type)

    # ------------------------------------------------------------------ web UI

    if settings.web_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")

    return app
