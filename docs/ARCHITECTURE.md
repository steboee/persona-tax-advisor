# Architecture — Persona Tax Advisor (SK s.r.o.)

A personal tax advisor for the owner/konateľ of a Slovak s.r.o. You ask by chat or by voice, in Slovak or English
("I'm at lunch with a client, can I pay with the company card?"). You get a short verdict you can hear, plus
details with § citations. The "brain" is **Claude Code in headless mode (`claude -p`)**, running on your machine under
your Claude plan. It works in a workspace that holds the tax persona, specialist subagents, skills, a curated knowledge
base and **full, auto-updated texts of the Slovak laws**.

## 1. Goals and constraints

| Goal | Consequence for the design |
|---|---|
| Ask "on the go" (lunch, car, shop) | Voice first. A spoken verdict comes before the details. Quick mode targets about 10 s per answer. |
| Slovak and English | Browser speech recognition `sk-SK` / `en-US`. The advisor answers in the user's language. |
| Correct and current law | Answers rest on the **statute text in force today**, synced from Slov-Lex. Curated knowledge sits on top for speed. Web search covers fresh guidance. |
| Know when laws change | A law-sync pipeline produces snapshots, diffs, a **changelog** and AI impact notes, and updates the knowledge base. |
| Runs on localhost with a Claude subscription | No API keys. The server shells out to the user's logged-in `claude` CLI. |
| Safe | The advisor is read-only (it cannot run commands or edit anything outside `knowledge/`). The server listens on localhost, with optional token auth. |
| It is not a licensed daňový poradca | Every answer states its confidence and sources, and flags when to ask your accountant. |

## 2. Component overview

```
 ┌────────────── Browser / phone (PWA) ──────────────┐
 │  Chat UI  ·  🎤 push-to-talk  ·  🔊 speak verdict   │
 │  Web Speech API (sk-SK/en-US) → text               │
 │  speechSynthesis (or server TTS) ← spoken part     │
 │  "📜 Zmeny zákonov" panel (law changelog)          │
 └───────────────┬───────────────────────────────────┘
                 │  HTTP + SSE (localhost, or Tailscale HTTPS for phone)
 ┌───────────────▼──────────── taxadvisor server (FastAPI) ─────────────────┐
 │  /api/chat (SSE) ─► ClaudeRunner ─► spawns `claude -p` (stream-json)       │
 │  /api/stt, /api/tts  (optional providers: OpenAI / ElevenLabs / local)    │
 │  /api/laws/*        ─► changelog, status, manual sync                      │
 │  SessionStore       conversation-id ↔ claude session-id (--resume)        │
 │  LawScheduler       daily background law sync (+ AI analysis)             │
 └───────────────┬──────────────────────────────────────────┬───────────────┘
                 │ cwd = advisor/                            │ HTTPS
 ┌───────────────▼─────────── advisor/ (Claude Code workspace) ──────────┐  │
 │ CLAUDE.md               persona, answer format, sources hierarchy     │  │
 │ profile/company.md      YOUR s.r.o. facts (VAT payer? employees? car?) │  │
 │ .claude/agents/         dph-specialista, dan-z-prijmov-specialista,   │  │
 │                         mzdy-odvody-specialista, legislativny-        │  │
 │                         vyskumnik, analytik-zmien-zakonov            │  │
 │ .claude/skills/         firemny-vydavok, pracovna-cesta, firemne-auto,│  │
 │                         vyber-penazi-z-firmy, danovy-kalendar,        │  │
 │                         citovanie-zakona, analyza-zmeny-zakona        │  │
 │ knowledge/              curated summaries, rates & limits (dated)     │  │
 │ laws/                   registry.json · <law>/current.md (full text)  │  │
 │                         versions/ · diffs/ · CHANGELOG.md · .json     │  │
 └───────────────────────────────────────────────────────────────────────┘  │
                                                    Slov-Lex, Finančná správa, web ◄┘
```

## 3. The brain: `claude -p` workspace

The server runs one `claude` process per user message:

```
claude -p "<message>" \
  --output-format stream-json --verbose --include-partial-messages \
  --model sonnet|opus \
  --session-id <uuid> | --resume <uuid>     # conversation memory
  --setting-sources project --strict-mcp-config  # isolation from your global config
  --permission-mode dontAsk --allowedTools "Read Grep Glob Skill Task WebSearch WebFetch(domain:…)"
  --append-system-prompt "<mode: voice|text, language, today's date>"
```

**Why `claude -p` rather than the raw API:** you get skills, subagents, tool use, file search over the law texts, web
search and session persistence without extra code, and it runs on your Claude plan.

### 3.1 Knowledge hierarchy (what the advisor trusts)

1. **`laws/<law>/current.md`**: the full consolidated statute text in force today, synced from Slov-Lex. This is the
   source of truth, and the advisor greps it for the exact § wording.
2. **`laws/CHANGELOG.md`**: upcoming changes that are already published. The advisor warns you, e.g. "from 1. 1. 2027
   this changes…".
3. **`knowledge/*.md`**: curated, practical summaries (rates, limits, interpretations), each with a `last verified`
   date. They are fast to read, and the law-sync analysis updates them.
4. **Web**: Finančná správa guidance (metodické pokyny), Slov-Lex, reputable portals. Used in deep mode or when (1)–(3)
   don't cover the question.
5. **`profile/company.md`**: your facts. They change the answer (VAT payer or not, konateľ employed or not, car
   ownership…).

### 3.2 Agents and skills

* **Main agent (persona):** handles 80 % of questions alone with skills. Skills load lazily: only the description sits
  in context until the skill is needed, which keeps quick mode fast.
* **Skills** encode decision procedures, e.g. `firemny-vydavok` is the "can the company pay for this?" decision tree
  covering business purpose (§ 2 písm. i), non-deductible items (§ 21), representation, VAT deduction (§ 49), the
  required document and how to book it.
* **Subagents** (deep mode, or complex cross-domain questions) get their own context and tools:
  * `dph-specialista`: VAT (222/2004)
  * `dan-z-prijmov-specialista`: income tax (595/2003)
  * `mzdy-odvody-specialista`: payroll, contributions, konateľ remuneration, dividends
  * `legislativny-vyskumnik`: verifies against current law text and the web, returns citations
  * `analytik-zmien-zakonov`: used by law sync; explains a diff and updates `knowledge/`

### 3.3 Modes

| Mode | Model | Tools | Use |
|---|---|---|---|
| **Rýchly (quick)** | `sonnet` | skills, local files, law grep | lunch / shop questions. Short answer. |
| **Dôkladný (deep)** | `opus` | + subagents, web research | planning (dividends vs. salary, buying a car, year-end). |

### 3.4 Answer contract

Every answer starts with a **spoken part** (1–3 sentences: verdict and the one thing to do), then a line `---`,
then the details: why (§ citations), DPH, what to do (document, how to book it), risks, confidence and sources. The UI
speaks only the part before `---`.

## 4. Voice pipeline

```
🎤 hold button → Web Speech API (sk-SK) → interim text in input → release → POST /api/chat {voice:true}
     └─ fallback (Firefox / no Web Speech): MediaRecorder → /api/stt (OpenAI | local faster-whisper)
SSE text deltas → bubble → on "done": spoken part → speechSynthesis(sk-SK) or /api/tts (OpenAI | ElevenLabs)
```

* The default needs **no keys**. Chrome, Edge and Safari support Slovak recognition, and Slovak TTS voices ship with
  macOS/iOS ("Laura") and Android/Chrome.
* For better voices, set `TTS_PROVIDER=elevenlabs|openai` and a key. Server STT is optional too.
* The microphone needs a secure context: `http://localhost` works. For the phone, use `tailscale serve` (HTTPS) and set
  `ADVISOR_TOKEN`.

## 5. Law sync and changelog ("connected to laws")

```
 registry.json ──► for each law:
   1. GET static.slov-lex.sk/static/SK/ZZ/<year>/<no>/          (history page: all versions)
   2. parse versions [effective_from, amending acts]; pick the version in force today and future ones
   3. new version?  GET …/<YYYYMMDD>.html → HTML→text → laws/<id>/versions/<date>.md
   4. diff vs previous snapshot → laws/<id>/diffs/<old>_<new>.diff (+ list of changed §§)
   5. update current.md (in force today), manifest.json
   6. append entry to laws/CHANGELOG.md + changelog.json   ◄── shown in UI "📜 Zmeny zákonov"
   7. (--analyze) claude -p with the analytik-zmien-zakonov agent:
        reads the diff → plain-language summary, impact on your s.r.o., action items,
        edits knowledge/*.md where they are out of date → recorded in the changelog entry
   8. (--news) claude -p web watch: Finančná správa guidance and news since the last check → changelog "news"
```

* **Triggers:** the server scheduler (default every 24 h, `LAW_SYNC_INTERVAL_HOURS`), the CLI
  (`uv run taxadvisor laws sync --analyze --news`), or cron/launchd.
* **Upcoming versions:** Slov-Lex publishes future versions once an amendment is promulgated, so the changelog warns
  you *before* a change takes effect.
* **Auditability:** snapshots and diffs are plain files, so commit them to git and the git history becomes the audit
  trail. AI edits to `knowledge/` are listed in each changelog entry.
* **Robustness:** the parser discovers versions by URL pattern (`…/<no>/YYYYMMDD.html`), not by page layout. When a
  fetch fails, the run logs it and the previous snapshot is kept.

## 6. Data and state

| Path | What | Who writes |
|---|---|---|
| `advisor/profile/company.md` | your company facts | you |
| `advisor/knowledge/` | curated summaries | you, law-sync analysis |
| `advisor/laws/` | statute snapshots, diffs, changelog | law sync |
| `data/sessions.json` | conversation ↔ claude session ids, titles | server |
| `~/.claude/projects/…` | full conversation transcripts | Claude Code |

## 7. Security and privacy

* The server binds `127.0.0.1` by default. Exposing it requires `ADVISOR_TOKEN`, sent as a bearer token by the UI.
* The advisor process runs with `--permission-mode dontAsk` and an allow-list: read-only tools, web limited to a set of
  domains, no Bash. Law analysis is allowed to edit `knowledge/` and nothing else. Untrusted web content therefore can't
  change your system.
* Questions are processed by Claude under your plan. Company facts stay in local files, so keep personal IDs out of
  `profile/`.

## 8. Roadmap

| Phase | Scope |
|---|---|
| **MVP (this repo)** | Web chat + voice, quick/deep modes, persona, 5 agents, 7 skills, knowledge base, law sync + changelog + AI analysis, CLI. |
| 2 | Telegram bot (voice notes; no HTTPS setup needed for the phone). Receipt photo: "is this deductible?" (vision), with a note written on the receipt. |
| 3 | Expense log: every answered "can I pay?" becomes a row (date, amount, deductible?, VAT), exportable for the accountant. |
| 4 | Proactive: deadlines (DPPO 31. 3., DPH 25th), "dividends vs. salary" year-end planner, notifications on law changes. |
| 5 | Realtime voice (streaming STT/TTS, barge-in), CarPlay/Android Auto via a messaging app. |
