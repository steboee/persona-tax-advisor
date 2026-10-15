"""Run law sync (+ analysis, + news) as a background job, on demand or on a schedule inside the server."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from taxadvisor.config import Settings
from taxadvisor.laws.analyze import analyze_pending, watch_news
from taxadvisor.laws.sync import LawSync, now_iso

log = logging.getLogger(__name__)


def run_pipeline(settings: Settings, *, analyze: bool, news: bool, law_ids: list[str] | None = None) -> dict[str, Any]:
    sync = LawSync(settings.laws_dir)
    report = sync.run(law_ids)
    result: dict[str, Any] = {
        "summary": report.summary(),
        "new_entries": len(report.new_entries),
        "errors": report.errors,
        "analyzed": 0,
        "news": 0,
    }
    if analyze:
        result["analyzed"] = len(analyze_pending(settings, sync))
    if news:
        try:
            result["news"] = len(watch_news(settings, sync))
        except Exception as exc:
            log.exception("news watch failed")
            result["errors"]["news"] = str(exc)[:300]
    return result


class LawJobs:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self.status: dict[str, Any] = {"running": False, "started": None, "finished": None, "result": None, "error": None}

    def start(self, *, analyze: bool, news: bool, law_ids: list[str] | None = None) -> bool:
        """Start in a background thread. Returns False if a job is already running."""
        with self._lock:
            if self.status["running"]:
                return False
            self.status = {"running": True, "started": now_iso(), "finished": None, "result": None, "error": None}
        threading.Thread(target=self._run, args=(analyze, news, law_ids), daemon=True, name="law-sync").start()
        return True

    def _run(self, analyze: bool, news: bool, law_ids: list[str] | None) -> None:
        try:
            result = run_pipeline(self.settings, analyze=analyze, news=news, law_ids=law_ids)
            error = None
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("law pipeline failed")
            result, error = None, str(exc)
        with self._lock:
            self.status.update({"running": False, "finished": now_iso(), "result": result, "error": error})

    def due(self) -> tuple[bool, bool]:
        """(sync due, news due) based on manifest timestamps and configured intervals."""
        manifest = LawSync(self.settings.laws_dir).manifest
        now = datetime.now(timezone.utc)

        def older_than(ts: str | None, delta: timedelta) -> bool:
            if not ts:
                return True
            try:
                return now - datetime.fromisoformat(ts) >= delta
            except ValueError:
                return True

        hours = self.settings.law_sync_interval_hours
        days = self.settings.law_news_interval_days
        sync_due = hours > 0 and older_than(manifest.get("updated"), timedelta(hours=hours))
        news_due = days > 0 and older_than(manifest.get("last_news_check"), timedelta(days=days))
        return sync_due, news_due

    async def scheduler(self, check_every_s: float = 3600) -> None:
        """Background loop for the server: start a job whenever sync or news is due."""
        await asyncio.sleep(15)  # let the server start first
        while True:
            try:
                sync_due, news_due = self.due()
                if sync_due or news_due:
                    log.info("scheduled law job (sync=%s, news=%s)", sync_due, news_due)
                    self.start(analyze=self.settings.law_sync_analyze, news=news_due)
            except Exception:  # pragma: no cover - defensive
                log.exception("law scheduler tick failed")
            await asyncio.sleep(check_every_s)
