"""Bridge to Claude Code headless mode (`claude -p`).

* `build_chat_command` assembles the CLI invocation for a chat turn (permissions, model, session handling).
* `stream_claude` runs it and yields the raw stream-json events.
* `StreamTranslator` turns raw events into small UI events: text deltas, tool/status updates, memory saves, final.
* `run_claude_json` is the blocking variant used by the law-sync analysis (single JSON result).
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import PurePath
from typing import Any

from taxadvisor.config import WEB_FETCH_DOMAINS, Settings

log = logging.getLogger(__name__)

# Built-in tools the advisor process gets at all. Everything else (Bash, notebooks, …) doesn't exist for it.
ADVISOR_TOOLS = ["Read", "Grep", "Glob", "Skill", "Task", "Agent", "WebSearch", "WebFetch", "Edit", "Write"]

READ_ONLY_ALLOWED = ["Read", "Grep", "Glob", "Skill", "Task", "Agent", "WebSearch"] + [
    f"WebFetch(domain:{d})" for d in WEB_FETCH_DOMAINS
]
# Chat may additionally write its memory (profile/), law analysis may update knowledge/.
CHAT_ALLOWED = READ_ONLY_ALLOWED + ["Edit(./profile/**)", "Write(./profile/**)"]
LAW_ANALYSIS_ALLOWED = READ_ONLY_ALLOWED + ["Edit(./knowledge/**)", "Write(./knowledge/**)"]
DISALLOWED = ["Bash", "NotebookEdit"]

STREAM_LINE_LIMIT = 32 * 1024 * 1024  # tool results can make single stream-json lines large


def base_command(settings: Settings, *, model: str, allowed: list[str]) -> list[str]:
    cmd = [
        settings.claude_bin,
        "-p",
        "--model",
        model,
        "--tools",
        ",".join(ADVISOR_TOOLS),
        "--permission-mode",
        "dontAsk",
        "--allowedTools",
        " ".join(allowed),
        "--disallowedTools",
        " ".join(DISALLOWED),
    ]
    if settings.isolate_claude_config:
        # Only the advisor workspace config; ignore the user's global plugins/MCP servers.
        cmd += ["--setting-sources", "project", "--strict-mcp-config"]
    return cmd + list(settings.claude_extra_args)


def turn_context(*, mode: str, voice: bool, lang: str, today: date | None = None) -> str:
    """Per-turn context prepended to the user message.

    Kept in the message (not the system prompt) because Claude Code may snapshot the system prompt for the whole
    session, while mode, input type and date can change between turns.
    """
    today = today or date.today()
    mode_txt = "dôkladný (môžeš použiť subagentov a webový výskum)" if mode == "deep" else "rýchly (stručne, bez subagentov)"
    input_txt = "hlas (voice mode: hovorená časť max. 2 vety)" if voice else "text"
    lang_txt = "English" if lang == "en" else "slovenčina"
    return f"[Kontext: dnes {today.isoformat()} · režim: {mode_txt} · vstup: {input_txt} · jazyk odpovede: {lang_txt}]"


def build_chat_command(
    settings: Settings,
    message: str,
    *,
    mode: str = "quick",
    voice: bool = False,
    lang: str = "sk",
    session_id: str,
    resume: bool,
    today: date | None = None,
) -> list[str]:
    model = settings.model_deep if mode == "deep" else settings.model_quick
    cmd = base_command(settings, model=model, allowed=CHAT_ALLOWED)
    cmd += ["--output-format", "stream-json", "--verbose", "--include-partial-messages"]
    cmd += ["--resume", session_id] if resume else ["--session-id", session_id]
    prompt = f"{turn_context(mode=mode, voice=voice, lang=lang, today=today)}\n\n{message}"
    # "--" ends option parsing so a message starting with "-" is never taken for a flag.
    return cmd + ["--", prompt]


async def stream_claude(cmd: list[str], *, cwd: str, timeout_s: float) -> AsyncIterator[dict[str, Any]]:
    """Run claude and yield parsed stream-json events. Non-JSON stdout lines are ignored.

    Raises RuntimeError if the process can't start or exits with an error without producing a result.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=STREAM_LINE_LIMIT,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Claude CLI '{cmd[0]}' not found. Install Claude Code and log in (`claude`), or set CLAUDE_BIN."
        ) from exc

    stderr_chunks: list[bytes] = []

    async def drain_stderr() -> None:
        assert proc.stderr is not None
        while chunk := await proc.stderr.read(65536):
            stderr_chunks.append(chunk)

    stderr_task = asyncio.create_task(drain_stderr())
    saw_result = False
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    try:
        assert proc.stdout is not None
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text.startswith("{"):
                continue
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                log.debug("non-JSON line from claude: %s", text[:200])
                continue
            if event.get("type") == "result":
                saw_result = True
            yield event
        await proc.wait()
    except asyncio.TimeoutError:
        raise RuntimeError(f"Claude did not finish within {int(timeout_s)} s") from None
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        await stderr_task
    if proc.returncode not in (0, None) and not saw_result:
        err = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Claude exited with code {proc.returncode}: {err[-2000:] or 'no output'}")


def _short(text: str, n: int = 80) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _rel(path: str) -> str:
    parts = PurePath(path).parts
    for anchor in ("profile", "knowledge", "laws", ".claude"):
        if anchor in parts:
            return "/".join(parts[parts.index(anchor):])
    return PurePath(path).name


def describe_tool(name: str, tool_input: dict[str, Any]) -> tuple[str, str]:
    """Human-friendly (Slovak) label for a tool call → (label, kind)."""
    inp = tool_input or {}
    if name in ("Edit", "Write", "MultiEdit"):
        path = _rel(inp.get("file_path", ""))
        if path.startswith("profile/"):
            return f"🧠 Ukladám do pamäte ({path})", "memory"
        return f"✏️ Upravujem {path}", "edit"
    if name == "Skill":
        return f"📘 Postup: {inp.get('skill') or inp.get('command') or '?'}", "skill"
    if name in ("Task", "Agent"):
        who = inp.get("subagent_type") or inp.get("description") or "špecialista"
        return f"🧑‍💼 Konzultujem: {who}", "agent"
    if name == "Read":
        return f"📄 Čítam {_rel(inp.get('file_path', ''))}", "read"
    if name == "Grep":
        where = _rel(inp.get("path", "")) if inp.get("path") else "všade"
        return f"🔎 Hľadám „{_short(inp.get('pattern', ''), 40)}“ v {where}", "search"
    if name == "Glob":
        return f"🗂️ Prehľadávam súbory {inp.get('pattern', '')}", "search"
    if name == "WebSearch":
        return f"🌐 Hľadám na webe: {_short(inp.get('query', ''), 60)}", "web"
    if name == "WebFetch":
        url = inp.get("url", "")
        host = url.split("/")[2] if "://" in url else url
        return f"🌐 Otváram {host}", "web"
    return f"🔧 {name}", "tool"


@dataclass
class StreamTranslator:
    """Converts raw stream-json events into UI events.

    UI events:
      {"type": "session", "session_id"}
      {"type": "text", "text"}                    – delta of the top-level answer
      {"type": "tool", "label", "kind", "nested"}  – status line (kind "memory" when the advisor saves memory)
      {"type": "done", "text", "session_id", "cost_usd", "duration_ms", "is_error", "memory_saved"}
    """

    session_id: str | None = None
    final_text: str = ""
    memory_saved: bool = False
    _streamed_current: bool = False
    _segments: list[str] = field(default_factory=list)

    def feed(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        etype = event.get("type")
        top_level = event.get("parent_tool_use_id") is None
        out: list[dict[str, Any]] = []

        if etype == "system" and event.get("subtype") == "init":
            self.session_id = event.get("session_id") or self.session_id
            out.append({"type": "session", "session_id": self.session_id})

        elif etype == "stream_event" and top_level:
            ev = event.get("event") or {}
            if ev.get("type") == "message_start":
                self._streamed_current = False
            elif ev.get("type") == "content_block_delta":
                delta = ev.get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    self._streamed_current = True
                    self._append(delta["text"])
                    out.append({"type": "text", "text": delta["text"]})

        elif etype == "assistant":
            content = (event.get("message") or {}).get("content") or []
            for block in content:
                btype = block.get("type")
                if btype == "text" and top_level and not self._streamed_current and block.get("text"):
                    # No partial messages were streamed for this message → emit the whole block.
                    self._append(block["text"])
                    out.append({"type": "text", "text": block["text"]})
                elif btype == "tool_use":
                    label, kind = describe_tool(block.get("name", ""), block.get("input") or {})
                    if kind == "memory":
                        self.memory_saved = True
                    if top_level:
                        self._segments.append("")  # text after a tool call starts a new segment
                    out.append({"type": "tool", "label": label, "kind": kind, "nested": not top_level})

        elif etype == "result":
            self.session_id = event.get("session_id") or self.session_id
            result_text = event.get("result")
            if not isinstance(result_text, str) or not result_text.strip():
                result_text = self._last_segment()
            self.final_text = result_text
            out.append(
                {
                    "type": "done",
                    "text": result_text,
                    "session_id": self.session_id,
                    "cost_usd": event.get("total_cost_usd"),
                    "duration_ms": event.get("duration_ms"),
                    "is_error": bool(event.get("is_error")) or event.get("subtype") not in (None, "success"),
                    "memory_saved": self.memory_saved,
                }
            )
        return out

    def _append(self, text: str) -> None:
        if not self._segments:
            self._segments.append("")
        self._segments[-1] += text

    def _last_segment(self) -> str:
        for seg in reversed(self._segments):
            if seg.strip():
                return seg
        return ""


def run_claude_json(
    settings: Settings,
    prompt: str,
    *,
    allowed: list[str],
    model: str,
    json_schema: dict[str, Any] | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Blocking one-shot run with `--output-format json`; returns the parsed structured output.

    Prefers `structured_output` (when --json-schema is supported), falls back to the first JSON object in the result.
    """
    cmd = base_command(settings, model=model, allowed=allowed) + ["--output-format", "json", "--no-session-persistence"]
    if json_schema is not None:
        cmd += ["--json-schema", json.dumps(json_schema, ensure_ascii=False)]
    cmd += ["--", prompt]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(settings.advisor_dir),
            capture_output=True,
            text=True,
            timeout=timeout_s or settings.claude_timeout_s,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Claude CLI '{settings.claude_bin}' not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Claude analysis timed out") from exc
    payload = _last_json_object(proc.stdout)
    if payload is None:
        raise RuntimeError(f"Claude returned no JSON (exit {proc.returncode}): {proc.stderr[-1500:]}")
    if payload.get("is_error"):
        raise RuntimeError(f"Claude error: {payload.get('result') or payload.get('subtype')}")
    structured = payload.get("structured_output")
    if isinstance(structured, dict):
        return structured
    extracted = extract_json_object(payload.get("result") or "")
    if extracted is None:
        raise RuntimeError("Claude result did not contain a JSON object")
    return extracted


def _last_json_object(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Find the first top-level JSON object in free text (handles ```json fences and prose around it)."""
    decoder = json.JSONDecoder()
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        try:
            obj, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None
