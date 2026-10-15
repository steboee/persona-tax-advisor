---
name: pamat
description: Persistent memory – save facts about the user and their company, and decisions you agreed on, into profile/memory.md and profile/company.md so future conversations use them. Use whenever the user states a lasting fact (founding status, VAT status, revenue, clients, car, employees, partner, konateľ remuneration) or confirms a decision/plan, or asks you to remember/forget something.
---

# Pamäť – postup

Memory files (always loaded in context via CLAUDE.md): `profile/company.md` (structured facts) and
`profile/memory.md` (log of facts, decisions, tasks, open questions).

**Save when:**
* the user states a lasting fact about themselves or the company ("I'm founding an s.r.o.", "I'm not a VAT payer",
  "my clients are in Germany", "I bought a car for 30 000 €");
* you and the user **agree on a decision** ("OK, I'll take no remuneration and pay dividends");
* there is a concrete follow-up task with a date (register § 7a before the first invoice to a German client);
* the user explicitly asks to remember or forget something.

**Don't save:** one-off questions, hypotheticals ("what if…") unless the user adopts them, your own advice that the
user didn't accept, sensitive data (birth numbers, passwords, IBAN, health details).

**How:**
1. Update the matching line in `profile/company.md` (replace `?` with the fact) using Edit.
2. Add one line at the top of "## Záznamy" in `profile/memory.md`:
   `- RRRR-MM-DD · [fakt|rozhodnutie|úloha|otázka] short text` (today's date from the system prompt).
   Update "## Aktuálny stav" if the phase changed. Mark completed tasks `✅` instead of deleting them.
3. If a new fact contradicts an older one, update it and note the change ("zmena: …").
4. At the end of your answer add one short line: `🧠 Uložené: …` so the user knows what you remembered.
