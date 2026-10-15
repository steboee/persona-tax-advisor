"""Command line: `taxadvisor serve | ask | laws …`."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid

from taxadvisor.config import Settings


def _cmd_serve(args: argparse.Namespace, settings: Settings) -> int:
    import uvicorn

    from taxadvisor.app import create_app

    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port
    if settings.host not in ("127.0.0.1", "localhost", "::1") and not settings.token:
        print("⚠️  Listening on a non-local address without ADVISOR_TOKEN – anyone on the network can use it.", file=sys.stderr)
    app = create_app(settings, run_scheduler=not args.no_scheduler)
    print(f"Daňko beží na http://{settings.host}:{settings.port}")
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    return 0


async def _ask(settings: Settings, question: str, mode: str, session: str | None) -> int:
    from taxadvisor.claude_runner import StreamTranslator, build_chat_command, stream_claude

    session_id = session or str(uuid.uuid4())
    cmd = build_chat_command(settings, question, mode=mode, session_id=session_id, resume=bool(session))
    translator = StreamTranslator()
    try:
        async for raw in stream_claude(cmd, cwd=str(settings.advisor_dir), timeout_s=settings.claude_timeout_s):
            for ev in translator.feed(raw):
                if ev["type"] == "text":
                    print(ev["text"], end="", flush=True)
                elif ev["type"] == "tool":
                    print(f"\n  [{ev['label']}]", file=sys.stderr, flush=True)
                elif ev["type"] == "done":
                    print()
                    print(f"\n(session: {ev['session_id']} – pokračuj: taxadvisor ask --session {ev['session_id']} \"…\")", file=sys.stderr)
    except RuntimeError as exc:
        print(f"Chyba: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_laws(args: argparse.Namespace, settings: Settings) -> int:
    from taxadvisor.laws.analyze import analyze_pending, watch_news
    from taxadvisor.laws.sync import LawSync, load_json

    if args.laws_cmd == "sync":
        sync = LawSync(settings.laws_dir)
        report = sync.run(args.law or None)
        print(report.summary())
        for entry in report.new_entries:
            print(f"  • {entry['law_id']}: {entry['kind']} (účinné od {entry.get('effective_from')})")
        for law_id, err in report.errors.items():
            print(f"  ✗ {law_id}: {err}", file=sys.stderr)
        if args.analyze:
            done = analyze_pending(settings, sync, max_items=args.max_analyses)
            print(f"analyzované zmeny: {len(done)}")
            for entry in done:
                a = entry.get("analysis") or {}
                print(f"  • {entry['law_id']}: {a.get('severity', '?')} – {a.get('summary') or entry.get('analysis_error')}")
                if entry.get("knowledge_updates"):
                    print(f"    upravené znalosti: {', '.join(entry['knowledge_updates'])}")
        if args.news:
            added = watch_news(settings, sync)
            print(f"novinky z webu: {len(added)}")
            for item in added:
                print(f"  • {item['title']} – {item['url']}")
        print(f"changelog: {settings.laws_dir / 'CHANGELOG.md'}")
        return 1 if report.errors and not report.checked else 0

    if args.laws_cmd == "status":
        print((settings.laws_dir / "STATUS.md").read_text(encoding="utf-8"))
        return 0

    if args.laws_cmd == "changelog":
        entries = load_json(settings.laws_dir / "changelog.json", [])[: args.n]
        if args.json:
            print(json.dumps(entries, ensure_ascii=False, indent=2))
        else:
            for e in entries:
                summary = (e.get("analysis") or {}).get("summary") or e.get("summary") or ""
                print(f"{e['detected_at'][:10]}  {e['kind']:<16} {e.get('law_name', '')} – účinné od {e.get('effective_from') or '?'}")
                if summary:
                    print(f"    {summary}")
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="taxadvisor", description="Osobný daňový poradca pre s.r.o. (Claude Code)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_serve = sub.add_parser("serve", help="spusti web server (chat + hlas)")
    p_serve.add_argument("--host")
    p_serve.add_argument("--port", type=int)
    p_serve.add_argument("--no-scheduler", action="store_true", help="nespúšťaj automatický law sync")

    p_ask = sub.add_parser("ask", help="opýtaj sa z terminálu")
    p_ask.add_argument("question")
    p_ask.add_argument("--deep", action="store_true", help="dôkladný režim (opus, subagenti, web)")
    p_ask.add_argument("--session", help="pokračuj v rozhovore (session id)")

    p_laws = sub.add_parser("laws", help="synchronizácia zákonov a changelog")
    laws_sub = p_laws.add_subparsers(dest="laws_cmd", required=True)
    p_sync = laws_sub.add_parser("sync", help="stiahni aktuálne znenia, porovnaj, zapíš changelog")
    p_sync.add_argument("--law", action="append", help="len vybraný zákon (id z registry.json), opakovateľné")
    p_sync.add_argument("--analyze", action="store_true", help="AI analýza zmien + úprava knowledge/")
    p_sync.add_argument("--max-analyses", type=int, default=None)
    p_sync.add_argument("--news", action="store_true", help="AI prieskum noviniek na webe")
    laws_sub.add_parser("status", help="stav zákonov")
    p_cl = laws_sub.add_parser("changelog", help="posledné zmeny")
    p_cl.add_argument("-n", type=int, default=20)
    p_cl.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()

    if args.cmd == "serve":
        return _cmd_serve(args, settings)
    if args.cmd == "ask":
        return asyncio.run(_ask(settings, args.question, "deep" if args.deep else "quick", args.session))
    if args.cmd == "laws":
        return _cmd_laws(args, settings)
    return 2
