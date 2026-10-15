import json
from datetime import date
from pathlib import Path

import pytest

from taxadvisor.laws.sync import LawSync, compute_diff, render_changelog_md

BASE = "https://static.slov-lex.sk/static/SK/ZZ"
FILLER = "".join(f"<p>Ustanovenie {i} bez zmeny, ktoré slúži ako výplň textu zákona.</p>" for i in range(20))


def law_html(rate: str, limit: str) -> str:
    return (
        "<html><body><div>PRVÁ ČASŤ</div>"
        f"<div>§ 15</div><p>(1) Sadzba dane je {rate} %.</p>{FILLER}"
        f"<div>§ 21</div><p>h) reklamné predmety v hodnote do {limit} eur.</p>{FILLER}"
        "</body></html>"
    )


def history(*rows: tuple[str, str]) -> str:
    body = "".join(f'<tr><td><a href="{d}.html">{d}</a></td><td>{amend}</td></tr>' for d, amend in rows)
    return f"<table>{body}</table>"


class FakeWeb:
    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        self.calls: list[str] = []

    def __call__(self, url: str) -> str:
        self.calls.append(url)
        if url not in self.pages:
            raise RuntimeError(f"404 {url}")
        return self.pages[url]


@pytest.fixture
def laws_dir(tmp_path: Path) -> Path:
    d = tmp_path / "advisor" / "laws"
    d.mkdir(parents=True)
    (d / "registry.json").write_text(
        json.dumps({"laws": [{"id": "zdp", "year": 2003, "number": 595, "name": "Zákon o dani z príjmov"}]}),
        encoding="utf-8",
    )
    return d


def zdp(path: str) -> str:
    return f"{BASE}/2003/595/{path}"


def test_full_lifecycle(laws_dir: Path):
    web = FakeWeb(
        {
            zdp(""): history(("20250101", "278/2024 Z. z."), ("20260101", "315/2025 Z. z."), ("20270101", "123/2026 Z. z.")),
            zdp("20250101.html"): law_html("15", "17"),
            zdp("20260101.html"): law_html("10", "17"),
            zdp("20270101.html"): law_html("10", "20"),
        }
    )

    # 1) first sync: baseline for the version in force + diff for the published future version
    report = LawSync(laws_dir, fetcher=web, today=date(2026, 10, 15)).run()
    assert report.errors == {}
    kinds = [e["kind"] for e in report.new_entries]
    assert kinds == ["baseline", "upcoming"]
    upcoming = report.new_entries[1]
    assert upcoming["effective_from"] == "2027-01-01"
    assert upcoming["previous_version"] == "2026-01-01"
    assert upcoming["amendments"] == ["123/2026 Z. z."]
    assert upcoming["changed_sections"] == ["§ 21"]
    assert upcoming["stats"] == {"added": 1, "removed": 1}
    diff = (laws_dir.parent / upcoming["diff_path"]).read_text(encoding="utf-8")
    assert "-h) reklamné predmety v hodnote do 17 eur." in diff
    assert "+h) reklamné predmety v hodnote do 20 eur." in diff
    assert zdp("20250101.html") not in web.calls  # old versions are not downloaded
    current = (laws_dir / "zdp" / "current.md").read_text(encoding="utf-8")
    assert "Sadzba dane je 10 %" in current and "do 17 eur" in current
    status = (laws_dir / "STATUS.md").read_text(encoding="utf-8")
    assert "| `zdp` |" in status and "od 1. 1. 2027 (123/2026 Z. z.)" in status
    changelog_md = (laws_dir / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Pripravovaná zmena" in changelog_md and "§ 21" in changelog_md

    # 2) nothing new → no entries, no downloads of known versions
    web.calls.clear()
    report = LawSync(laws_dir, fetcher=web, today=date(2026, 10, 16)).run()
    assert report.new_entries == []
    assert web.calls == [zdp("")]

    # 3) the future version gets amended again before it takes effect
    web.pages[zdp("")] = history(
        ("20250101", "278/2024 Z. z."), ("20260101", "315/2025 Z. z."), ("20270101", "123/2026 Z. z. 200/2026 Z. z.")
    )
    web.pages[zdp("20270101.html")] = law_html("12", "20")
    report = LawSync(laws_dir, fetcher=web, today=date(2026, 11, 1)).run()
    assert [e["kind"] for e in report.new_entries] == ["upcoming_revised"]
    assert report.new_entries[0]["changed_sections"] == ["§ 15"]

    # 4) the date passes → "effective" entry and current.md switches to the new version
    report = LawSync(laws_dir, fetcher=web, today=date(2027, 1, 2)).run()
    assert [e["kind"] for e in report.new_entries] == ["effective"]
    current = (laws_dir / "zdp" / "current.md").read_text(encoding="utf-8")
    assert "Sadzba dane je 12 %" in current and "do 20 eur" in current
    changelog = json.loads((laws_dir / "changelog.json").read_text(encoding="utf-8"))
    assert [e["kind"] for e in changelog] == ["effective", "upcoming_revised", "upcoming", "baseline"]


def test_fetch_error_is_recorded_and_previous_snapshot_kept(laws_dir: Path):
    web = FakeWeb({zdp(""): history(("20260101", "")), zdp("20260101.html"): law_html("10", "17")})
    LawSync(laws_dir, fetcher=web, today=date(2026, 10, 15)).run()
    web.pages.pop(zdp(""))
    report = LawSync(laws_dir, fetcher=web, today=date(2026, 10, 16)).run()
    assert "zdp" in report.errors
    assert (laws_dir / "zdp" / "current.md").is_file()
    assert "Chyby posledného sync" in (laws_dir / "STATUS.md").read_text(encoding="utf-8")


def test_empty_page_is_rejected(laws_dir: Path):
    web = FakeWeb({zdp(""): history(("20260101", "")), zdp("20260101.html"): "<html><body>Maintenance</body></html>"})
    report = LawSync(laws_dir, fetcher=web, today=date(2026, 10, 15)).run()
    assert "looks empty" in report.errors["zdp"]


def test_compute_diff_ignores_header_and_tracks_sections():
    old = "# Hlavička\n- Stiahnuté: 1\n---\n\n### § 1\n\na\nb\n\n### § 2\n\nc\n"
    new = "# Hlavička\n- Stiahnuté: 2\n---\n\n### § 1\n\na\nb\n\n### § 2\n\nC\n"
    result = compute_diff(old, new, "old", "new")
    assert (result.added, result.removed) == (1, 1)
    assert result.sections == ["§ 2"]
    assert "Stiahnuté" not in result.text


def test_render_changelog_with_analysis_and_news():
    md = render_changelog_md(
        [
            {
                "detected_at": "2026-10-15T00:00:00+00:00", "law_name": "Novinka", "law_ref": None, "kind": "news",
                "title": "Nový metodický pokyn", "summary": "Zhrnutie.", "effective_from": None, "url": "https://x.sk",
            },
            {
                "detected_at": "2026-10-15T00:00:00+00:00", "law_name": "Zákon o DPH", "law_ref": "222/2004 Z. z.",
                "kind": "upcoming", "effective_from": "2027-01-01", "previous_version": "2026-01-01",
                "amendments": ["1/2026 Z. z."], "changed_sections": ["§ 49"], "stats": {"added": 3, "removed": 1},
                "diff_path": "laws/dph/diffs/a.diff", "url": "https://slov-lex",
                "analysis": {"summary": "Mení sa odpočet.", "impact_for_sro": ["Dopad"], "action_items": ["Urob X"], "severity": "vysoká"},
                "knowledge_updates": ["knowledge/sadzby-a-limity.md"],
            },
        ]
    )
    assert "📰 Novinka (web)" in md and "Nový metodický pokyn" in md
    assert "🔴 (vysoká)" in md and "- [ ] Urob X" in md and "`knowledge/sadzby-a-limity.md`" in md
    assert "**Účinné od:** 1. 1. 2027" in md
