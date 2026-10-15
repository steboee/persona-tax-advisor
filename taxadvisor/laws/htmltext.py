"""Convert a statute HTML page (Slov-Lex) into greppable plain text with Markdown-ish headings.

Layout-agnostic on purpose: block elements become lines, then lines are classified by their text
("§ 21" → `### § 21`, "PRVÁ ČASŤ" → `## PRVÁ ČASŤ`), so a redesign of the HTML doesn't break the output.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

BLOCK_TAGS = {
    "p", "div", "section", "article", "li", "ul", "ol", "table", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "dd", "dt", "dl", "header", "footer", "main", "aside", "figure", "caption", "hr",
}
SKIP_TAGS = {"script", "style", "head", "noscript", "nav", "button", "select", "option", "form", "svg", "iframe"}
CELL_TAGS = {"td", "th"}

PARAGRAPH_RE = re.compile(r"^§\s*\d+[a-z]*$")
PART_RE = re.compile(
    r"^((PRVÁ|DRUHÁ|TRETIA|ŠTVRTÁ|PIATA|ŠIESTA|SIEDMA|ÔSMA|DEVIATA|DESIATA|JEDENÁSTA|DVANÁSTA)\s+ČASŤ"
    r"|ČASŤ\s+[IVXLC\d]+|[IVXLC]+\.\s*ČASŤ|PRÍLOHA.*|Príloha\s+č\.\s*\d+.*)$"
)
HEAD_RE = re.compile(r"^(PRVÁ|DRUHÁ|TRETIA|ŠTVRTÁ|PIATA|ŠIESTA|SIEDMA)\s+HLAVA$|^HLAVA\s+[IVXLC\d]+$")
ARTICLE_RE = re.compile(r"^Čl\.\s*[IVXLC\d]+$")


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.current: list[str] = []
        self.skip_depth = 0

    def _flush(self) -> None:
        text = " ".join("".join(self.current).split())
        if text:
            self.lines.append(text)
        self.current = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "br" or tag in BLOCK_TAGS:
            self._flush()
        elif tag in CELL_TAGS and self.current:
            self.current.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.current.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def html_to_text(html: str) -> str:
    parser = _Extractor()
    parser.feed(html)
    parser.close()
    out: list[str] = []
    for line in parser.lines:
        line = line.replace(" ", " ").strip()
        if not line:
            continue
        if PARAGRAPH_RE.match(line):
            line = "### " + re.sub(r"^§\s*", "§ ", line)
        elif PART_RE.match(line) or HEAD_RE.match(line) or ARTICLE_RE.match(line):
            line = "## " + line
        if out and out[-1] == line:
            continue  # drop exact consecutive duplicates (repeated navigation, etc.)
        if line.startswith("#") and out and out[-1] != "":
            out.append("")
        out.append(line)
        if line.startswith("#"):
            out.append("")
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
