# Daňko – osobný daňový poradca pre tvoju s.r.o.

A personal tax advisor for a Slovak s.r.o. (service company) that you talk to by **chat or voice**, in
**Slovak or English**. Example: *"Som na obede s klientom, môžem platiť firemnou kartou?"*
The app gives a short spoken verdict, then details with § citations, VAT, what to do, risks and confidence.

The brain is **Claude Code in headless mode (`claude -p`)** running on your machine under **your Claude plan**,
with a dedicated workspace (`advisor/`) of a tax persona, specialist subagents, skills, curated knowledge, your
company profile and memory, and **full texts of the Slovak laws that sync automatically from Slov-Lex, with a
changelog**.

→ Design details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## What it does

* **Chat and voice UI**: tap 🎤, speak Slovak or English, and the answer's verdict is read aloud. It works on the
  phone too, and you can add it to the home screen.
* **Practical "real options" advice**: it shows the cheapest legal paths, not only the textbook one, and marks
  each by risk: 🟢 legal and safe · 🟡 legal only with conditions and evidence · 🔴 illegal. A 🔴 path comes with
  what realistically happens at an audit and the closest legal alternative. Examples: "TV via the company card →
  receivable + offset against dividend", "shareholder loan instead of equity at founding".
* **Knows your situation and remembers it**: `advisor/profile/company.md` + `memory.md` are always in context.
  When you agree on something ("no konateľ remuneration, dividends"), the advisor saves it (🧠) and uses it next time.
* **Connected to the laws**: 11 tracked laws (income tax, VAT, tax procedure, accounting, travel allowances,
  Labour Code, social and health insurance, transaction tax, motor vehicle tax, Commercial Code). The current
  consolidated texts are stored locally for exact § quotes, and upcoming versions that are already published are
  tracked too. Every change gets a diff, a changelog entry and an AI explanation of what it means for you, and the
  knowledge base is updated automatically.
* **Quick / Deep modes**: ⚡ Sonnet with skills for on-the-spot questions; 🔬 Opus with specialist subagents
  (DPH, daň z príjmov, mzdy a odvody, legislatívny výskumník) and web research for planning.

## Setup (localhost, Claude plan)

Requirements: Python ≥ 3.11 with [uv](https://docs.astral.sh/uv/), and
[Claude Code](https://docs.claude.com/en/docs/claude-code) installed and logged in with your plan (`claude` → `/login`).

```bash
git clone https://github.com/steboee/persona-tax-advisor && cd persona-tax-advisor
uv sync

# 1) tell the advisor about your company (edit the "?" lines)
$EDITOR advisor/profile/company.md

# 2) first law download + AI analysis of upcoming changes (a few minutes)
uv run taxadvisor laws sync --analyze

# 3) start the app → http://localhost:8765
uv run taxadvisor serve
```

Open **http://localhost:8765** in Chrome, Edge or Safari. These support Slovak speech recognition. Microphone access
works on `localhost` without HTTPS.

### From the terminal

```bash
uv run taxadvisor ask "Môžem si cez firmu kúpiť notebook?"
uv run taxadvisor ask --deep "Odmena konateľa alebo dividendy pri zisku 60 000 €?"
uv run taxadvisor laws status          # which versions are in force, what's coming
uv run taxadvisor laws changelog -n 10 # latest changes
cd advisor && claude                   # interactive Claude Code session with the advisor persona
```

### On the phone

The browser needs HTTPS for the microphone, so use [Tailscale](https://tailscale.com):

```bash
echo "ADVISOR_TOKEN=$(openssl rand -hex 24)" >> .env   # the UI asks for it once
uv run taxadvisor serve
tailscale serve --bg 8765                              # → https://<machine>.<tailnet>.ts.net
```

Open the URL on the phone, enter the token, and choose "Add to Home Screen".

## Law sync and changelog

* The server checks Slov-Lex every 24 h (`LAW_SYNC_INTERVAL_HOURS`), and once a week the AI also scans the web for
  news and Finančná správa guidance (`LAW_NEWS_INTERVAL_DAYS`). You can also start it manually with the
  **📜 Zákony → Skontrolovať teraz** button or `uv run taxadvisor laws sync --analyze --news`.
* Where to look:
  * **UI tab 📜 Zákony**: status of every law, upcoming versions, and a changelog with impact, action items and
    updated knowledge files.
  * `advisor/laws/CHANGELOG.md`: the same as Markdown. `changelog.json` is the machine-readable source.
  * `advisor/laws/<id>/current.md`: the full text in force today. `versions/` holds future versions and `diffs/` the
    exact changes.
* Commit `advisor/laws/` and `advisor/knowledge/` to git, and the git history becomes the audit trail of every law
  change and every AI edit to the knowledge base.
* To track another law, add it to `advisor/laws/registry.json` (year + number from Slov-Lex).

## Configuration

Copy `.env.example` to `.env`. Every setting is optional. The most useful ones:

| Variable | Default | Meaning |
|---|---|---|
| `MODEL_QUICK` / `MODEL_DEEP` | `sonnet` / `opus` | models for ⚡ / 🔬 modes |
| `ADVISOR_TOKEN` | – | required when exposing the server beyond localhost |
| `LAW_SYNC_INTERVAL_HOURS` | `24` | automatic law check (0 = off) |
| `LAW_SYNC_ANALYZE` | `true` | AI analysis of changes + knowledge updates |
| `LAW_NEWS_INTERVAL_DAYS` | `7` | AI web news watch (0 = off) |
| `STT_PROVIDER` / `TTS_PROVIDER` | `none` | optional server speech: `openai`, `elevenlabs`, `local` (faster-whisper) |

## How it's built

```
advisor/                 Claude Code workspace = the advisor (cwd of every `claude -p`)
  CLAUDE.md              persona, answer contract (spoken part --- details), sources, memory rules
  profile/               company.md + memory.md – your facts and agreed decisions (advisor writes here)
  knowledge/             curated 2026 rules: rates, representation, trips, car, setup, real options…
  laws/                  registry, synced statute texts, diffs, CHANGELOG.md, STATUS.md
  .claude/agents/        dph-specialista, dan-z-prijmov-specialista, mzdy-odvody-specialista,
                         legislativny-vyskumnik, analytik-zmien-zakonov
  .claude/skills/        firemny-vydavok, realne-moznosti, nastavenie-sro, vyber-penazi-z-firmy,
                         pracovna-cesta, firemne-auto, danovy-kalendar, citovanie-zakona, pamat,
                         analyza-zmeny-zakona
taxadvisor/              Python server (FastAPI) + CLI
  claude_runner.py       builds the claude command (scoped permissions), streams stream-json → UI events
  app.py                 /api/chat (SSE), conversations, memory, laws, optional STT/TTS, serves web/
  laws/                  Slov-Lex parser, sync + diff + changelog, AI analysis & news, scheduler
web/                     the UI (no build step): chat, voice, law changelog, memory
tests/                   pytest with a fake claude CLI and Slov-Lex fixtures
```

Security: the advisor process runs with `--permission-mode dontAsk` and an explicit allow-list. It can read the
workspace, search the web and fetch only official/known Slovak sources. Bash is never available. It can write only
to `profile/` in chat, and only to `knowledge/` during law analysis.

## Development

```bash
uv run pytest
```

## Disclaimer

Daňko is not a licensed daňový poradca. It states its confidence and sources, and it flags items marked ⚠️ in
`knowledge/` as unverified. For big decisions, confirm with your accountant or a tax advisor.
