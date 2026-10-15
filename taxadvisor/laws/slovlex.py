"""Slov-Lex source: discover versions of a law and fetch a version's text.

History page:  https://static.slov-lex.sk/static/SK/ZZ/<year>/<number>/
Version text:  https://static.slov-lex.sk/static/SK/ZZ/<year>/<number>/<YYYYMMDD>.html

Versions are discovered by URL pattern (links ending in /<YYYYMMDD>.html), not by page layout. Amending acts are
taken from links to other acts (/SK/ZZ/<y>/<n>/) and "n/yyyy Z. z." mentions on the same table row.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx

DEFAULT_BASE = "https://static.slov-lex.sk/static/SK/ZZ"
USER_AGENT = "persona-tax-advisor/0.1 (+law sync; personal use)"

Fetcher = Callable[[str], str]


@dataclass
class Law:
    id: str
    year: int
    number: int
    name: str
    topics: list[str] = field(default_factory=list)
    enabled: bool = True

    @property
    def ref(self) -> str:
        return f"{self.number}/{self.year} Z. z."


@dataclass
class Version:
    date: str  # YYYYMMDD – effective from
    url: str
    amendments: list[str] = field(default_factory=list)

    @property
    def iso(self) -> str:
        return f"{self.date[:4]}-{self.date[4:6]}-{self.date[6:]}"


def history_url(law: Law, base: str = DEFAULT_BASE) -> str:
    return f"{base}/{law.year}/{law.number}/"


def version_url(law: Law, date: str, base: str = DEFAULT_BASE) -> str:
    return f"{base}/{law.year}/{law.number}/{date}.html"


_ROW_RE = re.compile(r"<tr\b.*?</tr>", re.S | re.I)
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_ACT_LINK_RE = re.compile(r"/SK/ZZ/(\d{4})/(\d+)(?:/|$)")
_ACT_TEXT_RE = re.compile(r"(\d{1,4})\s*/\s*(\d{4})\s*Z\.\s*z\.")
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)


def _valid_date(d: str) -> bool:
    y, m, day = int(d[:4]), int(d[4:6]), int(d[6:])
    return 1918 <= y <= 2100 and 1 <= m <= 12 and 1 <= day <= 31


def parse_history(html: str, law: Law, base: str = DEFAULT_BASE) -> list[Version]:
    html = _SCRIPT_RE.sub(" ", html)
    own = f"/SK/ZZ/{law.year}/{law.number}/"
    # "20260101.html", "./20260101.html", ".../SK/ZZ/2003/595/20260101.html" or ".../SK/ZZ/2003/595/20260101"
    version_re = re.compile(rf"(?:^|/SK/ZZ/{law.year}/{law.number}/|^\./)(\d{{8}})(?:\.html)?/?(?:[?#].*)?$")
    chunks = _ROW_RE.findall(html) or [html]
    found: dict[str, Version] = {}
    for chunk in chunks:
        dates: list[str] = []
        amendments: list[str] = []
        for href in _HREF_RE.findall(chunk):
            m = version_re.search(href)
            if m and (own in href or "/" not in href.lstrip("./")):
                if _valid_date(m.group(1)):
                    dates.append(m.group(1))
                continue
            act = _ACT_LINK_RE.search(href)
            if act and (int(act.group(1)), int(act.group(2))) != (law.year, law.number):
                amendments.append(f"{int(act.group(2))}/{act.group(1)} Z. z.")
        text = _TAG_RE.sub(" ", chunk)
        for num, year in _ACT_TEXT_RE.findall(text):
            ref = f"{int(num)}/{year} Z. z."
            if (int(year), int(num)) != (law.year, law.number):
                amendments.append(ref)
        if len(chunks) == 1:
            amendments = []  # without table rows we can't tell which amendment belongs to which version
        for d in dict.fromkeys(dates):
            version = found.setdefault(d, Version(date=d, url=version_url(law, d, base)))
            for a in dict.fromkeys(amendments):
                if a not in version.amendments:
                    version.amendments.append(a)
    return sorted(found.values(), key=lambda v: v.date)


def http_fetch(url: str, *, retries: int = 2, timeout: float = 60.0) -> str:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            resp.encoding = resp.encoding or "utf-8"
            return resp.text
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last = exc
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last}")
