"""Law sync: fetch versions of tracked laws, store snapshots, diff them and maintain the changelog.

Files (under advisor/laws/):
  registry.json             tracked laws (edit to add/remove)
  manifest.json             sync state (generated)
  <id>/versions/<date>.md   fetched consolidated texts (in force + already published future versions)
  <id>/current.md           copy of the version in force today (what the advisor greps)
  <id>/diffs/<a>_<b>.diff   unified diff between consecutive fetched versions
  changelog.json            machine-readable changelog (source of truth, newest first)
  CHANGELOG.md              human-readable changelog (rendered from changelog.json)
  STATUS.md                 short status, always loaded into the advisor's context
"""

from __future__ import annotations

import difflib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from taxadvisor.laws.htmltext import html_to_text
from taxadvisor.laws.slovlex import DEFAULT_BASE, Fetcher, Law, Version, history_url, http_fetch, parse_history

log = logging.getLogger(__name__)

HEADER_END = "\n---\n\n"
MIN_TEXT_CHARS = 400  # a real statute is far longer; less means the page didn't parse


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sk_date(d: str | None) -> str:
    """'20260101' or '2026-01-01' → '1. 1. 2026'."""
    if not d:
        return "?"
    digits = d.replace("-", "")
    if len(digits) != 8 or not digits.isdigit():
        return d
    return f"{int(digits[6:])}. {int(digits[4:6])}. {digits[:4]}"


# --------------------------------------------------------------------------- storage helpers


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("Corrupt JSON in %s – starting fresh", path)
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_registry(laws_dir: Path) -> tuple[list[Law], str]:
    data = load_json(laws_dir / "registry.json", {"laws": []})
    base = data.get("base_url") or DEFAULT_BASE
    laws = [
        Law(
            id=item["id"],
            year=int(item["year"]),
            number=int(item["number"]),
            name=item["name"],
            topics=item.get("topics", []),
            enabled=item.get("enabled", True),
        )
        for item in data.get("laws", [])
    ]
    return laws, base


def split_header(text: str) -> tuple[str, str]:
    if HEADER_END in text:
        head, body = text.split(HEADER_END, 1)
        return head, body
    return "", text


def render_version_file(law: Law, version: Version, body: str) -> str:
    amendments = ", ".join(version.amendments) or "–"
    head = (
        f"# {law.name} ({law.ref})\n\n"
        f"- Znenie účinné od: **{sk_date(version.date)}**\n"
        f"- Posledné novely v tomto znení: {amendments}\n"
        f"- Zdroj: {version.url}\n"
        f"- Stiahnuté: {now_iso()}"
    )
    return head + HEADER_END + body


# --------------------------------------------------------------------------- diff


@dataclass
class DiffResult:
    text: str
    added: int
    removed: int
    sections: list[str]

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


def _section_index(lines: list[str]) -> list[str]:
    current = ""
    index = []
    for line in lines:
        if line.startswith("### § "):
            current = line[4:].strip()
        elif line.startswith("## ") and ("Príloha" in line or "PRÍLOHA" in line):
            current = line[3:].strip()
        index.append(current)
    return index


def compute_diff(old_text: str, new_text: str, old_label: str, new_label: str, context: int = 3) -> DiffResult:
    old_lines = split_header(old_text)[1].splitlines()
    new_lines = split_header(new_text)[1].splitlines()
    old_sec, new_sec = _section_index(old_lines), _section_index(new_lines)
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    out = [f"--- {old_label}", f"+++ {new_label}"]
    added = removed = 0
    sections: list[str] = []
    for group in matcher.get_grouped_opcodes(context):
        i1, i2, j1, j2 = group[0][1], group[-1][2], group[0][3], group[-1][4]
        out.append(f"@@ -{i1 + 1},{i2 - i1} +{j1 + 1},{j2 - j1} @@")
        for tag, a1, a2, b1, b2 in group:
            if tag == "equal":
                out.extend(" " + line for line in old_lines[a1:a2])
                continue
            for k in range(a1, a2):
                out.append("-" + old_lines[k])
                removed += 1
            for k in range(b1, b2):
                out.append("+" + new_lines[k])
                added += 1
            for sec in ([new_sec[b1]] if b1 < len(new_sec) else []) + ([old_sec[a1]] if a1 < len(old_sec) else []):
                if sec and sec not in sections:
                    sections.append(sec)
    return DiffResult(text="\n".join(out) + "\n", added=added, removed=removed, sections=sections)


# --------------------------------------------------------------------------- sync


@dataclass
class SyncReport:
    checked: list[str] = field(default_factory=list)
    new_entries: list[dict[str, Any]] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        parts = [f"skontrolované zákony: {len(self.checked)}", f"nové záznamy: {len(self.new_entries)}"]
        if self.errors:
            parts.append(f"chyby: {len(self.errors)} ({', '.join(self.errors)})")
        return " · ".join(parts)


class LawSync:
    def __init__(self, laws_dir: Path, fetcher: Fetcher | None = None, today: date | None = None):
        self.laws_dir = laws_dir
        self.fetch = fetcher or http_fetch
        self.today = today or date.today()
        self.manifest = load_json(laws_dir / "manifest.json", {"laws": {}})
        self.changelog: list[dict[str, Any]] = load_json(laws_dir / "changelog.json", [])

    # ---- public

    def run(self, law_ids: list[str] | None = None) -> SyncReport:
        laws, base = load_registry(self.laws_dir)
        report = SyncReport()
        for law in laws:
            if not law.enabled or (law_ids and law.id not in law_ids):
                continue
            report.checked.append(law.id)
            state = self.manifest["laws"].setdefault(law.id, {})
            state.update({"name": law.name, "ref": law.ref, "history_url": history_url(law, base)})
            try:
                entries = self._sync_law(law, base, state)
                state["last_error"] = None
                report.new_entries.extend(entries)
            except Exception as exc:  # keep going with other laws; previous snapshot stays
                log.exception("law sync failed for %s", law.id)
                state["last_error"] = f"{type(exc).__name__}: {exc}"
                report.errors[law.id] = state["last_error"]
            state["last_checked"] = now_iso()
        self.manifest["updated"] = now_iso()
        self.save()
        return report

    def save(self) -> None:
        save_json(self.laws_dir / "manifest.json", self.manifest)
        save_json(self.laws_dir / "changelog.json", self.changelog)
        (self.laws_dir / "CHANGELOG.md").write_text(render_changelog_md(self.changelog), encoding="utf-8")
        (self.laws_dir / "STATUS.md").write_text(render_status_md(self.manifest, self.changelog, self.today), encoding="utf-8")

    # ---- internals

    def _law_dir(self, law: Law) -> Path:
        return self.laws_dir / law.id

    def _version_path(self, law: Law, d: str) -> Path:
        return self._law_dir(law) / "versions" / f"{d}.md"

    def _download(self, law: Law, version: Version) -> str:
        body = html_to_text(self.fetch(version.url))
        if len(body) < MIN_TEXT_CHARS:
            raise RuntimeError(f"text of {version.url} looks empty ({len(body)} chars) – page layout changed?")
        text = render_version_file(law, version, body)
        path = self._version_path(law, version.date)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return text

    def _diff_entry(self, law: Law, kind: str, old_date: str, new: Version, old_text: str, new_text: str) -> dict | None:
        diff = compute_diff(old_text, new_text, f"{law.id}/{old_date}", f"{law.id}/{new.date}")
        if not diff.changed:
            return None
        rel = f"laws/{law.id}/diffs/{old_date}_{new.date}.diff"
        diff_path = self.laws_dir.parent / rel
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_path.write_text(diff.text, encoding="utf-8")
        return self._entry(
            law,
            kind,
            new,
            previous_version=old_date,
            diff_path=rel,
            stats={"added": diff.added, "removed": diff.removed},
            changed_sections=diff.sections,
        )

    def _entry(self, law: Law, kind: str, version: Version, **extra: Any) -> dict[str, Any]:
        entry = {
            "id": f"{law.id}-{kind}-{version.date}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "detected_at": now_iso(),
            "law_id": law.id,
            "law_name": law.name,
            "law_ref": law.ref,
            "kind": kind,
            "effective_from": version.iso,
            "previous_version": None,
            "amendments": version.amendments,
            "url": version.url,
            "diff_path": None,
            "stats": None,
            "changed_sections": [],
            "analysis": None,
            "analysis_error": None,
            "knowledge_updates": [],
        }
        entry.update(extra)
        if entry["previous_version"]:
            entry["previous_version"] = f"{entry['previous_version'][:4]}-{entry['previous_version'][4:6]}-{entry['previous_version'][6:]}"
        self.changelog.insert(0, entry)
        return entry

    def _sync_law(self, law: Law, base: str, state: dict[str, Any]) -> list[dict[str, Any]]:
        versions = parse_history(self.fetch(history_url(law, base)), law, base)
        if not versions:
            raise RuntimeError("no versions found on the Slov-Lex history page")
        today = self.today.strftime("%Y%m%d")
        old_versions = {v["date"]: v for v in state.get("versions", [])}
        fetched: set[str] = set(state.get("fetched", []))
        first_time = not fetched
        current = next((v for v in reversed(versions) if v.date <= today), None)
        upcoming = [v for v in versions if v.date > today]
        entries: list[dict[str, Any]] = []

        newly: list[Version] = []
        for v in ([current] if current else []) + upcoming:
            if v.date not in fetched or not self._version_path(law, v.date).is_file():
                self._download(law, v)
                newly.append(v)
            elif v.date > today and set(v.amendments) != set(old_versions.get(v.date, {}).get("amendments", [])):
                # A published future version was amended again before taking effect.
                old_text = self._version_path(law, v.date).read_text(encoding="utf-8")
                new_text = self._download(law, v)
                entry = self._diff_entry(law, "upcoming_revised", v.date, v, old_text, new_text)
                if entry:
                    entries.append(entry)

        known = sorted(fetched | {v.date for v in newly})
        for v in sorted(newly, key=lambda x: x.date):
            older = [d for d in known if d < v.date and self._version_path(law, d).is_file()]
            if first_time and current and v.date == current.date:
                entries.append(self._entry(law, "baseline", v))
                continue
            if not older:
                entries.append(self._entry(law, "baseline", v))
                continue
            prev = older[-1]
            old_text = self._version_path(law, prev).read_text(encoding="utf-8")
            new_text = self._version_path(law, v.date).read_text(encoding="utf-8")
            kind = "upcoming" if v.date > today else "in_force"
            entry = self._diff_entry(law, kind, prev, v, old_text, new_text)
            if entry:
                entries.append(entry)

        old_current = state.get("current")
        if current and old_current and current.date != old_current and current.date not in {v.date for v in newly}:
            entries.append(self._entry(law, "effective", current, previous_version=old_current))

        if current:
            text = self._version_path(law, current.date).read_text(encoding="utf-8")
            (self._law_dir(law) / "current.md").write_text(text, encoding="utf-8")

        state["versions"] = [{"date": v.date, "url": v.url, "amendments": v.amendments} for v in versions]
        state["fetched"] = known
        state["current"] = current.date if current else None
        state["upcoming"] = [v.date for v in upcoming]
        return entries


# --------------------------------------------------------------------------- rendering

KIND_LABELS = {
    "baseline": "🆕 Začiatok sledovania",
    "upcoming": "⏳ Pripravovaná zmena (už vyhlásená)",
    "upcoming_revised": "✏️ Pripravovaná zmena upravená",
    "in_force": "✅ Nové znenie účinné",
    "effective": "📅 Ohlásená zmena nadobudla účinnosť",
    "news": "📰 Novinka (web)",
}
SEVERITY_ICON = {"vysoká": "🔴", "stredná": "🟠", "nízka": "🟢"}


def render_changelog_md(changelog: list[dict[str, Any]]) -> str:
    lines = [
        "# Zmeny v sledovaných zákonoch",
        "",
        "Generuje law sync (`uv run taxadvisor laws sync`). Najnovšie hore. Zdroj znení: Slov-Lex.",
        "Záznamy „📰 Novinka (web)“ pochádzajú z webového prieskumu – over ich v zákone.",
        "",
    ]
    if not changelog:
        lines.append("_Zatiaľ žiadne záznamy – sync ešte nebežal._")
    for e in changelog:
        title = f"{e['law_name']} ({e['law_ref']})" if e.get("law_ref") else e.get("law_name", "Novinka")
        lines += [f"## {e['detected_at'][:10]} · {KIND_LABELS.get(e['kind'], e['kind'])} · {title}", ""]
        if e.get("title"):
            lines.append(f"**{e['title']}**  ")
        if e.get("effective_from"):
            lines.append(f"- **Účinné od:** {sk_date(e['effective_from'])}")
        if e.get("previous_version"):
            lines.append(f"- **Predchádzajúce znenie:** od {sk_date(e['previous_version'])}")
        if e.get("amendments"):
            lines.append(f"- **Novely:** {', '.join(e['amendments'])}")
        if e.get("changed_sections"):
            secs = e["changed_sections"]
            more = f" … (+{len(secs) - 25})" if len(secs) > 25 else ""
            lines.append(f"- **Zmenené ustanovenia:** {', '.join(secs[:25])}{more}")
        if e.get("stats"):
            lines.append(f"- **Rozsah:** +{e['stats']['added']} / −{e['stats']['removed']} riadkov · diff: `{e['diff_path']}`")
        if e.get("url"):
            lines.append(f"- **Zdroj:** {e['url']}")
        a = e.get("analysis")
        if a:
            sev = a.get("severity", "")
            lines += ["", f"**Čo to znamená pre teba** {SEVERITY_ICON.get(sev, '')} ({sev or '?'})", "", a.get("summary", "")]
            for item in a.get("impact_for_sro", []) or []:
                lines.append(f"- {item}")
            if a.get("action_items"):
                lines += ["", "**Čo urobiť:**"] + [f"- [ ] {x}" for x in a["action_items"]]
        elif e.get("summary"):
            lines += ["", e["summary"]]
        if e.get("analysis_error"):
            lines.append(f"- _Analýza zlyhala: {e['analysis_error']}_")
        if e.get("knowledge_updates"):
            lines += ["", "**Aktualizované znalosti:** " + ", ".join(f"`{p}`" for p in e["knowledge_updates"])]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_status_md(manifest: dict[str, Any], changelog: list[dict[str, Any]], today: date) -> str:
    laws = manifest.get("laws", {})
    lines = [
        f"# Stav sledovaných zákonov (law sync: {(manifest.get('updated') or '?')[:16].replace('T', ' ')} UTC)",
        "",
        "Úplné znenia: `laws/<id>/current.md` (účinné dnes), budúce: `laws/<id>/versions/<YYYYMMDD>.md`. Detaily zmien: `laws/CHANGELOG.md`.",
        "",
        "| ID | Zákon | Účinné znenie od | Pripravované zmeny (účinnosť) |",
        "|---|---|---|---|",
    ]
    errors = []
    for law_id, st in laws.items():
        upcoming = st.get("upcoming") or []
        versions = {v["date"]: v for v in st.get("versions", [])}
        up_txt = "; ".join(
            f"od {sk_date(d)}" + (f" ({', '.join(versions[d]['amendments'][:2])})" if versions.get(d, {}).get("amendments") else "")
            for d in upcoming
        ) or "–"
        cur = sk_date(st.get("current")) if st.get("current") else "nestiahnuté"
        lines.append(f"| `{law_id}` | {st.get('name', '')} ({st.get('ref', '')}) | {cur} | {up_txt} |")
        if st.get("last_error"):
            errors.append(f"- `{law_id}`: {st['last_error']}")
    recent = [e for e in changelog if e.get("kind") not in ("baseline",)][:8]
    if recent:
        lines += ["", "## Posledné zmeny a novinky", ""]
        for e in recent:
            sev = (e.get("analysis") or {}).get("severity") or e.get("severity") or ""
            what = (e.get("analysis") or {}).get("summary") or e.get("summary") or e.get("title") or ""
            what = " ".join(what.split())[:220]
            eff = f" · účinné od {sk_date(e['effective_from'])}" if e.get("effective_from") else ""
            lines.append(f"- {SEVERITY_ICON.get(sev, '•')} **{e.get('law_name', 'Novinka')}**{eff}: {what}")
    if errors:
        lines += ["", "## Chyby posledného sync (použi web / knowledge)", ""] + errors
    return "\n".join(lines) + "\n"
