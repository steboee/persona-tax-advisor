import json
from datetime import date

from taxadvisor.laws.analyze import analyze_pending, watch_news
from taxadvisor.laws.sync import LawSync
from tests.test_sync import FakeWeb, history, law_html, zdp


def _synced(settings) -> LawSync:
    web = FakeWeb(
        {
            zdp(""): history(("20260101", "315/2025 Z. z."), ("20270101", "123/2026 Z. z.")),
            zdp("20260101.html"): law_html("10", "17"),
            zdp("20270101.html"): law_html("10", "20"),
        }
    )
    sync = LawSync(settings.laws_dir, fetcher=web, today=date(2026, 10, 15))
    sync.run(["zdp"])
    return sync


def test_analyze_pending_records_analysis_and_knowledge_updates(settings):
    sync = _synced(settings)
    knowledge = settings.advisor_dir / "knowledge" / "sadzby-a-limity.md"
    calls = []

    def fake_runner(s, prompt, *, allowed, model, json_schema):
        calls.append((prompt, allowed, model))
        knowledge.write_text(knowledge.read_text(encoding="utf-8") + "\n- (od 1. 1. 2027: reklamné predmety do 20 €)\n", encoding="utf-8")
        return {"summary": "Limit sa zvyšuje na 20 €.", "impact_for_sro": ["Viac daňových reklamných predmetov"], "action_items": [], "severity": "nízka"}

    done = analyze_pending(settings, sync, runner=fake_runner)
    assert len(done) == 1 and len(calls) == 1
    prompt, allowed, model = calls[0]
    assert "laws/zdp/diffs/20260101_20270101.diff" in prompt and "§ 21" in prompt
    assert "Edit(./knowledge/**)" in allowed and "Edit(./profile/**)" not in allowed
    entry = done[0]
    assert entry["analysis"]["summary"] == "Limit sa zvyšuje na 20 €."
    assert entry["knowledge_updates"] == ["knowledge/sadzby-a-limity.md"]
    md = (settings.laws_dir / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Limit sa zvyšuje na 20 €." in md and "Aktualizované znalosti" in md
    assert "Limit sa zvyšuje" in (settings.laws_dir / "STATUS.md").read_text(encoding="utf-8")
    # already analyzed → nothing pending
    assert analyze_pending(settings, sync, runner=fake_runner) == []


def test_analysis_failure_is_recorded(settings):
    sync = _synced(settings)

    def failing_runner(*a, **k):
        raise RuntimeError("rate limited")

    done = analyze_pending(settings, sync, runner=failing_runner)
    assert done[0]["analysis_error"] == "rate limited"


def test_watch_news_dedupes_by_url(settings):
    sync = _synced(settings)
    item = {"title": "FS: nový pokyn k DPH", "url": "https://www.financnasprava.sk/x", "summary": "S.", "severity": "stredná"}

    def runner(*a, **k):
        return {"items": [item, dict(item)]}

    assert len(watch_news(settings, sync, runner=runner)) == 1
    assert watch_news(settings, sync, runner=runner) == []
    changelog = json.loads((settings.laws_dir / "changelog.json").read_text(encoding="utf-8"))
    assert changelog[0]["kind"] == "news" and changelog[0]["title"] == "FS: nový pokyn k DPH"
    assert sync.manifest["last_news_check"]
