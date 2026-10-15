import asyncio
import json
from datetime import date

import pytest

from taxadvisor.claude_runner import (
    StreamTranslator,
    build_chat_command,
    describe_tool,
    extract_json_object,
    run_claude_json,
    stream_claude,
)


def test_build_chat_command_first_turn_and_resume(settings):
    first = build_chat_command(settings, "-obed?", mode="quick", session_id="abc", resume=False, today=date(2026, 10, 15))
    assert first[0] == settings.claude_bin and "-p" in first
    assert first[first.index("--model") + 1] == "sonnet"
    assert first[first.index("--session-id") + 1] == "abc" and "--resume" not in first
    assert first[first.index("--permission-mode") + 1] == "dontAsk"
    allowed = first[first.index("--allowedTools") + 1]
    assert "Edit(./profile/**)" in allowed and "Edit(./knowledge/**)" not in allowed and "Bash" not in allowed
    assert "WebFetch(domain:static.slov-lex.sk)" in allowed
    assert "Bash" in first[first.index("--disallowedTools") + 1]
    assert first[-2] == "--"  # message can never be parsed as a flag
    assert first[-1].startswith("[Kontext: dnes 2026-10-15") and first[-1].endswith("-obed?")

    deep = build_chat_command(settings, "x", mode="deep", voice=True, lang="en", session_id="abc", resume=True)
    assert deep[deep.index("--model") + 1] == "opus"
    assert deep[deep.index("--resume") + 1] == "abc" and "--session-id" not in deep
    assert "voice mode" in deep[-1] and "English" in deep[-1]


def test_translator_streams_top_level_text_and_tools():
    events = [
        {"type": "system", "subtype": "init", "session_id": "s1"},
        {"type": "stream_event", "parent_tool_use_id": None, "event": {"type": "message_start"}},
        {"type": "stream_event", "parent_tool_use_id": None, "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hľadám. "}}},
        {"type": "assistant", "parent_tool_use_id": None, "message": {"content": [{"type": "text", "text": "Hľadám. "}]}},
        {"type": "assistant", "parent_tool_use_id": None, "message": {"content": [{"type": "tool_use", "name": "Grep", "input": {"pattern": "§ 21", "path": "/a/advisor/laws/zdp/current.md"}}]}},
        {"type": "stream_event", "parent_tool_use_id": "t1", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "SUBAGENT"}}},
        {"type": "assistant", "parent_tool_use_id": "t1", "message": {"content": [{"type": "tool_use", "name": "Write", "input": {"file_path": "/a/advisor/profile/memory.md"}}]}},
        {"type": "stream_event", "parent_tool_use_id": None, "event": {"type": "message_start"}},
        {"type": "assistant", "parent_tool_use_id": None, "message": {"content": [{"type": "text", "text": "Nie.\n---\nDetail"}]}},
        {"type": "result", "subtype": "success", "result": "", "session_id": "s1", "total_cost_usd": 0.1},
    ]
    t = StreamTranslator()
    out = [ev for e in events for ev in t.feed(e)]
    texts = [e["text"] for e in out if e["type"] == "text"]
    assert texts == ["Hľadám. ", "Nie.\n---\nDetail"]  # no duplicate of streamed text, no subagent text
    tools = [e for e in out if e["type"] == "tool"]
    assert tools[0]["label"].startswith("🔎") and "laws/zdp/current.md" in tools[0]["label"] and not tools[0]["nested"]
    assert tools[1]["kind"] == "memory" and tools[1]["nested"]
    done = out[-1]
    assert done["type"] == "done" and done["text"] == "Nie.\n---\nDetail"  # falls back to last segment
    assert done["memory_saved"] is True and done["session_id"] == "s1" and done["is_error"] is False


def test_describe_tool_labels():
    assert describe_tool("Skill", {"skill": "firemny-vydavok"})[0] == "📘 Postup: firemny-vydavok"
    assert describe_tool("Task", {"subagent_type": "dph-specialista"})[1] == "agent"
    assert describe_tool("WebFetch", {"url": "https://www.financnasprava.sk/sk/x"})[0] == "🌐 Otváram www.financnasprava.sk"
    assert describe_tool("Edit", {"file_path": "/r/advisor/knowledge/a.md"}) == ("✏️ Upravujem knowledge/a.md", "edit")


def test_stream_claude_with_fake_cli(settings):
    cmd = build_chat_command(settings, "test", session_id="sess-1", resume=False)

    async def collect():
        return [e async for e in stream_claude(cmd, cwd=str(settings.advisor_dir), timeout_s=30)]

    events = asyncio.run(collect())
    assert events[0]["session_id"] == "sess-1"
    assert events[-1]["type"] == "result"


def test_stream_claude_reports_cli_failure(settings, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FAIL", "1")
    cmd = build_chat_command(settings, "test", session_id="s", resume=False)

    async def collect():
        return [e async for e in stream_claude(cmd, cwd=str(settings.advisor_dir), timeout_s=30)]

    with pytest.raises(RuntimeError, match="not logged in"):
        asyncio.run(collect())


def test_stream_claude_missing_binary(settings):
    settings.claude_bin = "/nonexistent/claude"
    cmd = build_chat_command(settings, "x", session_id="s", resume=False)

    async def collect():
        return [e async for e in stream_claude(cmd, cwd=str(settings.advisor_dir), timeout_s=5)]

    with pytest.raises(RuntimeError, match="not found"):
        asyncio.run(collect())


def test_run_claude_json_structured_output(settings, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_JSON", json.dumps({"summary": "ok", "severity": "nízka"}))
    out = run_claude_json(settings, "prompt", allowed=["Read"], model="opus", json_schema={"type": "object"})
    assert out == {"summary": "ok", "severity": "nízka"}


def test_extract_json_object():
    assert extract_json_object('Tu je výsledok:\n```json\n{"a": {"b": 1}}\n```') == {"a": {"b": 1}}
    assert extract_json_object("bez json") is None
