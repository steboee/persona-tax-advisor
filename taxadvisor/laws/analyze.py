"""AI steps of the law pipeline (run through `claude -p` in the advisor workspace).

* `analyze_pending` – for changelog entries with a diff: plain-language summary, impact on the user's s.r.o.,
  action items; the agent may update outdated files in knowledge/ (recorded in the entry).
* `watch_news` – web research for new guidance/legislation since the last check (Finančná správa, NR SR, …).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from taxadvisor.claude_runner import LAW_ANALYSIS_ALLOWED, READ_ONLY_ALLOWED, run_claude_json
from taxadvisor.config import Settings
from taxadvisor.laws.sync import LawSync, load_registry, now_iso, sk_date

log = logging.getLogger(__name__)

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "2–4 sentences in Slovak: what changes and from when"},
        "impact_for_sro": {"type": "array", "items": {"type": "string"}, "description": "concrete impacts on a small service s.r.o."},
        "action_items": {"type": "array", "items": {"type": "string"}},
        "severity": {"type": "string", "enum": ["vysoká", "stredná", "nízka"]},
        "affected_topics": {"type": "array", "items": {"type": "string"}},
        "knowledge_files_updated": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "impact_for_sro", "action_items", "severity"],
}

NEWS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "published": {"type": "string", "description": "YYYY-MM-DD if known"},
                    "url": {"type": "string"},
                    "summary": {"type": "string"},
                    "effective_from": {"type": "string", "description": "YYYY-MM-DD if known, else empty"},
                    "severity": {"type": "string", "enum": ["vysoká", "stredná", "nízka"]},
                    "status": {"type": "string", "description": "e.g. návrh, schválené NR SR, vyhlásené v Zbierke, metodický pokyn"},
                },
                "required": ["title", "url", "summary", "severity"],
            },
        }
    },
    "required": ["items"],
}

Runner = Callable[..., dict[str, Any]]


def _knowledge_hashes(advisor_dir: Path) -> dict[str, str]:
    root = advisor_dir / "knowledge"
    return {
        str(p.relative_to(advisor_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*.md"))
    }


def analysis_prompt(entry: dict[str, Any]) -> str:
    law_dir = f"laws/{entry['law_id']}"
    prev = (entry.get("previous_version") or "").replace("-", "")
    new = (entry.get("effective_from") or "").replace("-", "")
    sections = ", ".join(entry.get("changed_sections", [])[:60]) or "neurčené"
    return (
        "Si agent `analytik-zmien-zakonov`. Použi skill `analyza-zmeny-zakona`.\n\n"
        f"Zákon: {entry['law_name']} ({entry['law_ref']}), id `{entry['law_id']}`.\n"
        f"Typ zmeny: {entry['kind']} · nové znenie účinné od {sk_date(entry.get('effective_from'))}"
        f" · predchádzajúce znenie od {sk_date(entry.get('previous_version'))}.\n"
        f"Novely: {', '.join(entry.get('amendments') or []) or 'neuvedené'}.\n"
        f"Diff: `{entry['diff_path']}` (+{entry['stats']['added']} / −{entry['stats']['removed']} riadkov).\n"
        f"Staré znenie: `{law_dir}/versions/{prev}.md`, nové: `{law_dir}/versions/{new}.md`.\n"
        f"Zmenené ustanovenia: {sections}.\n\n"
        "Úlohy: (1) vysvetli podstatné zmeny po slovensky pre majiteľa malej s.r.o. poskytujúcej služby "
        "(pozri profile/company.md a profile/memory.md); (2) ak sú niektoré údaje v knowledge/ neaktuálne alebo sa "
        "od uvedeného dátumu zmenia, uprav ich (len súbory v knowledge/); (3) vráť JSON podľa schémy – "
        "v knowledge_files_updated uveď upravené súbory."
    )


def analyze_pending(
    settings: Settings,
    sync: LawSync,
    *,
    max_items: int | None = None,
    runner: Runner = run_claude_json,
) -> list[dict[str, Any]]:
    """Analyze changelog entries that have a diff but no analysis yet. Saves after each entry."""
    pending = [e for e in sync.changelog if e.get("diff_path") and not e.get("analysis") and not e.get("analysis_error")]
    pending = pending[: max_items if max_items is not None else settings.law_analysis_max_per_run]
    done = []
    for entry in pending:
        before = _knowledge_hashes(settings.advisor_dir)
        try:
            result = runner(
                settings,
                analysis_prompt(entry),
                allowed=LAW_ANALYSIS_ALLOWED,
                model=settings.model_law_analysis,
                json_schema=ANALYSIS_SCHEMA,
            )
            entry["analysis"] = {
                "summary": str(result.get("summary", "")).strip(),
                "impact_for_sro": [str(x) for x in result.get("impact_for_sro", [])],
                "action_items": [str(x) for x in result.get("action_items", [])],
                "severity": result.get("severity") if result.get("severity") in ("vysoká", "stredná", "nízka") else "stredná",
                "affected_topics": [str(x) for x in result.get("affected_topics", [])],
                "analyzed_at": now_iso(),
            }
        except Exception as exc:
            log.exception("analysis failed for %s", entry["id"])
            entry["analysis_error"] = str(exc)[:500]
        after = _knowledge_hashes(settings.advisor_dir)
        entry["knowledge_updates"] = sorted(k for k in after if before.get(k) != after[k])
        sync.save()
        done.append(entry)
    return done


def news_prompt(since: str | None, topics: list[str]) -> str:
    since_txt = since[:10] if since else "posledných 60 dní"
    return (
        "Si `legislativny-vyskumnik`. Nájdi na webe novinky v slovenskej daňovej a odvodovej legislatíve a v usmerneniach "
        f"Finančnej správy publikované od {since_txt}, ktoré môžu zaujímať majiteľa malej s.r.o. poskytujúcej služby "
        f"(témy: {', '.join(topics)}). Zdroje: financnasprava.sk (aktuality, metodické pokyny), nrsr.sk (schválené zákony), "
        "slov-lex.sk (vyhlásené predpisy), mfsr.sk, socpoist.sk, employment.gov.sk; sekundárne portály len na nájdenie primárneho zdroja. "
        "Zahrň aj návrhy, ktoré sú v legislatívnom procese, ale označ ich status. Nevymýšľaj; ak nič nové nie je, vráť prázdny zoznam. "
        "Vráť JSON podľa schémy, max. 8 položiek, summary po slovensky (1–3 vety, s dopadom na s.r.o.)."
    )


def watch_news(settings: Settings, sync: LawSync, *, runner: Runner = run_claude_json) -> list[dict[str, Any]]:
    laws, _ = load_registry(sync.laws_dir)
    topics = sorted({t for law in laws if law.enabled for t in law.topics} | {"minimálna mzda", "e-faktúry"})
    result = runner(
        settings,
        news_prompt(sync.manifest.get("last_news_check"), topics),
        allowed=READ_ONLY_ALLOWED + ["WebFetch"],
        model=settings.model_quick,
        json_schema=NEWS_SCHEMA,
    )
    known_urls = {e.get("url") for e in sync.changelog if e.get("kind") == "news"}
    added = []
    for item in result.get("items", [])[:8]:
        url = str(item.get("url", "")).strip()
        if not url or url in known_urls:
            continue
        entry = {
            "id": f"news-{hashlib.sha1(url.encode()).hexdigest()[:12]}",
            "detected_at": now_iso(),
            "law_id": None,
            "law_name": "Novinka",
            "law_ref": None,
            "kind": "news",
            "title": str(item.get("title", "")).strip(),
            "summary": str(item.get("summary", "")).strip(),
            "status": str(item.get("status", "")).strip(),
            "published": str(item.get("published", "")).strip() or None,
            "effective_from": str(item.get("effective_from", "")).strip() or None,
            "severity": item.get("severity") if item.get("severity") in ("vysoká", "stredná", "nízka") else "nízka",
            "url": url,
            "amendments": [],
            "changed_sections": [],
            "analysis": None,
            "analysis_error": None,
            "knowledge_updates": [],
        }
        sync.changelog.insert(0, entry)
        known_urls.add(url)
        added.append(entry)
    sync.manifest["last_news_check"] = now_iso()
    sync.save()
    return added
