"""Conversation store: maps UI conversations to Claude Code session ids and keeps a short message history.

Claude Code keeps the full transcript itself (resumed with --resume); this file only lets the UI list and
re-display conversations.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_MESSAGES = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ConversationStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = {}
        if path.is_file():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                backup = path.with_suffix(".corrupt.json")
                path.replace(backup)
                self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def create(self, title: str) -> dict[str, Any]:
        with self._lock:
            conv = {
                "id": str(uuid.uuid4()),
                "title": title[:80] or "Nový rozhovor",
                "created": _now(),
                "updated": _now(),
                # Session id we ask Claude to use for the first turn; replaced by the id Claude reports.
                "claude_session_id": str(uuid.uuid4()),
                "started": False,
                "messages": [],
            }
            self._data[conv["id"]] = conv
            self._save()
            return dict(conv)

    def get(self, conv_id: str) -> dict[str, Any] | None:
        with self._lock:
            conv = self._data.get(conv_id)
            return json.loads(json.dumps(conv)) if conv else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            items = [
                {k: c[k] for k in ("id", "title", "created", "updated")} | {"messages": len(c["messages"])}
                for c in self._data.values()
            ]
        return sorted(items, key=lambda c: c["updated"], reverse=True)

    def delete(self, conv_id: str) -> bool:
        with self._lock:
            existed = self._data.pop(conv_id, None) is not None
            if existed:
                self._save()
            return existed

    def add_message(self, conv_id: str, role: str, text: str, **meta: Any) -> None:
        with self._lock:
            conv = self._data[conv_id]
            conv["messages"].append({"role": role, "text": text, "ts": _now(), **meta})
            conv["messages"] = conv["messages"][-MAX_MESSAGES:]
            conv["updated"] = _now()
            self._save()

    def mark_started(self, conv_id: str, claude_session_id: str | None) -> None:
        with self._lock:
            conv = self._data[conv_id]
            conv["started"] = True
            if claude_session_id:
                conv["claude_session_id"] = claude_session_id
            self._save()

    def reset_session(self, conv_id: str) -> None:
        """Pick a fresh Claude session id when the first turn failed before Claude started the session."""
        with self._lock:
            conv = self._data[conv_id]
            if not conv["started"]:
                conv["claude_session_id"] = str(uuid.uuid4())
                self._save()
