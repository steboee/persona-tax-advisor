import json
import os

from fastapi.testclient import TestClient

from taxadvisor.app import create_app


def sse_events(response) -> list[dict]:
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def claude_calls() -> list[list[str]]:
    with open(os.environ["FAKE_CLAUDE_LOG"], encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def test_chat_streams_and_resumes_conversation(settings):
    client = TestClient(create_app(settings, run_scheduler=False))
    r = client.post("/api/chat", json={"message": "Obed s klientom – môžem platiť kartou?", "voice": True})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = sse_events(r)
    assert events[0]["type"] == "conversation"
    conv_id = events[0]["id"]
    types = [e["type"] for e in events]
    assert "session" in types and "text" in types and types[-1] == "done"
    done = events[-1]
    assert done["text"].startswith("Áno, môžeš.") and done["memory_saved"] is True
    assert any(e["type"] == "tool" and e["kind"] == "memory" for e in events)

    r2 = client.post("/api/chat", json={"message": "A DPH?", "conversation_id": conv_id})
    assert sse_events(r2)[-1]["type"] == "done"
    first, second = claude_calls()
    session = first[first.index("--session-id") + 1]
    assert second[second.index("--resume") + 1] == session
    assert "voice mode" in first[-1] and "voice mode" not in second[-1]

    conv = client.get(f"/api/conversations/{conv_id}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant", "user", "assistant"]
    assert client.get("/api/conversations").json()[0]["id"] == conv_id
    assert client.delete(f"/api/conversations/{conv_id}").json() == {"deleted": True}


def test_chat_error_from_cli_is_reported(settings, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FAIL", "1")
    client = TestClient(create_app(settings, run_scheduler=False))
    events = sse_events(client.post("/api/chat", json={"message": "x"}))
    assert events[-1]["type"] == "error" and "not logged in" in events[-1]["message"]


def test_unknown_conversation_404(settings):
    client = TestClient(create_app(settings, run_scheduler=False))
    assert client.post("/api/chat", json={"message": "x", "conversation_id": "nope"}).status_code == 404


def test_token_auth(settings):
    settings.token = "s3cret"
    client = TestClient(create_app(settings, run_scheduler=False))
    assert client.get("/api/config").json()["auth_required"] is True
    assert client.get("/api/conversations").status_code == 401
    assert client.get("/api/conversations", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/api/memory?token=s3cret").status_code == 200


def test_memory_laws_and_voice_endpoints(settings):
    client = TestClient(create_app(settings, run_scheduler=False))
    mem = client.get("/api/memory").json()
    assert "zakladá s.r.o." in mem["memory"] and "Profil firmy" in mem["company"]
    status = client.get("/api/laws/status").json()
    assert {law["id"] for law in status["laws"]} >= {"zdp", "dph", "transakcna-dan"}
    assert client.get("/api/laws/changelog").json() == []
    assert client.post("/api/tts", json={"text": "ahoj"}).status_code == 501
    assert client.post("/api/stt", files={"audio": ("a.webm", b"x")}).status_code == 501
    cfg = client.get("/api/config").json()
    assert cfg["stt_server"] is False and cfg["tts_server"] is False


def test_serves_web_ui(settings):
    client = TestClient(create_app(settings, run_scheduler=False))
    r = client.get("/")
    assert r.status_code == 200 and "Daňko" in r.text
