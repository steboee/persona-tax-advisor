from pathlib import Path

from taxadvisor.laws.slovlex import Law, history_url, parse_history, version_url

FIXTURE = Path(__file__).parent / "fixtures" / "history_595.html"
ZDP = Law(id="zdp", year=2003, number=595, name="Zákon o dani z príjmov")


def test_urls():
    assert history_url(ZDP) == "https://static.slov-lex.sk/static/SK/ZZ/2003/595/"
    assert version_url(ZDP, "20260101") == "https://static.slov-lex.sk/static/SK/ZZ/2003/595/20260101.html"


def test_parse_history_finds_versions_and_amendments():
    versions = parse_history(FIXTURE.read_text(encoding="utf-8"), ZDP)
    assert [v.date for v in versions] == ["20250101", "20260101", "20270101"]  # script content and PDFs ignored
    by_date = {v.date: v for v in versions}
    assert by_date["20250101"].amendments == ["278/2024 Z. z."]
    assert by_date["20260101"].amendments == ["315/2025 Z. z."]
    assert by_date["20270101"].amendments == ["123/2026 Z. z."]
    assert by_date["20270101"].url.endswith("/SK/ZZ/2003/595/20270101.html")
    assert by_date["20270101"].iso == "2027-01-01"


def test_parse_history_without_table_rows_still_finds_versions():
    html = '<ul><li><a href="20240101.html">2024</a></li><li><a href="20250101.html">2025</a> 278/2024 Z. z.</li></ul>'
    versions = parse_history(html, ZDP)
    assert [v.date for v in versions] == ["20240101", "20250101"]
    assert all(v.amendments == [] for v in versions)  # can't attribute amendments without rows


def test_ignores_versions_of_other_laws():
    html = '<tr><td><a href="https://static.slov-lex.sk/static/SK/ZZ/2004/222/20250101.html">x</a></td></tr>'
    assert parse_history(html, ZDP) == []
