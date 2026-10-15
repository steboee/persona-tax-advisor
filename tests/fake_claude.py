#!/usr/bin/env python3
"""Stand-in for the `claude` CLI in tests. Records argv and prints canned stream-json / json output."""
import json
import os
import sys

argv = sys.argv[1:]
log_path = os.environ.get("FAKE_CLAUDE_LOG")
if log_path:
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(argv) + "\n")


def arg(name):
    return argv[argv.index(name) + 1] if name in argv else None


if os.environ.get("FAKE_CLAUDE_FAIL"):
    print("boom: not logged in", file=sys.stderr)
    sys.exit(3)

fmt = arg("--output-format")
if fmt == "json":
    structured = json.loads(os.environ.get("FAKE_CLAUDE_JSON", "{}"))
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "ok", "structured_output": structured}))
    sys.exit(0)

session = arg("--session-id") or arg("--resume") or "fake-session"
prompt = argv[-1]


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False), flush=True)


emit({"type": "system", "subtype": "init", "session_id": session, "tools": ["Read"], "model": arg("--model")})
emit({"type": "stream_event", "parent_tool_use_id": None, "event": {"type": "message_start", "message": {"id": "m1"}}})
emit({"type": "stream_event", "parent_tool_use_id": None, "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Pozriem sa. "}}})
emit({"type": "assistant", "parent_tool_use_id": None, "message": {"id": "m1", "content": [{"type": "text", "text": "Pozriem sa. "}]}})
emit({"type": "assistant", "parent_tool_use_id": None, "message": {"id": "m1", "content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "firemny-vydavok"}}]}})
emit({"type": "assistant", "parent_tool_use_id": "t1", "message": {"id": "s1", "content": [{"type": "tool_use", "name": "WebSearch", "input": {"query": "reprezentácia"}}]}})
emit({"type": "assistant", "parent_tool_use_id": None, "message": {"id": "m1", "content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/x/advisor/profile/memory.md"}}]}})
emit({"type": "stream_event", "parent_tool_use_id": None, "event": {"type": "message_start", "message": {"id": "m2"}}})
answer = "Áno, môžeš.\n---\n**Verdikt:** ✅"
for chunk in (answer[:5], answer[5:]):
    emit({"type": "stream_event", "parent_tool_use_id": None, "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": chunk}}})
emit({"type": "assistant", "parent_tool_use_id": None, "message": {"id": "m2", "content": [{"type": "text", "text": answer}]}})
emit({"type": "result", "subtype": "success", "is_error": False, "result": answer, "session_id": session, "total_cost_usd": 0.01, "duration_ms": 1234, "echo_prompt": prompt})
