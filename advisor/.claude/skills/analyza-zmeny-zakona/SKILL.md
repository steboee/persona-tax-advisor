---
name: analyza-zmeny-zakona
description: Analyze a detected change between two versions of a Slovak statute (diff from law sync), explain it in plain Slovak, assess the impact on a small s.r.o. owner, and update outdated knowledge files. Used by the law-sync pipeline; also usable manually ("what changed in the VAT act?").
---

# Analýza zmeny zákona – postup

Input (given in the prompt): law id + name, old version file, new version file, diff file, list of changed §§,
effective date, amending acts.

1. Read the diff file in chunks (it can be long). Focus on substantive changes; ignore renumbering, typography,
   footnotes and pure references unless they change meaning.
2. For each substantive change: what was before → what is now, which §, from which date.
3. Impact on the user: a small s.r.o. (see `profile/company.md`): rates, limits, deductibility, VAT deduction, deadlines,
   obligations, payroll/konateľ, dividends, car, cash/card payments. Rate severity:
   * `vysoká` – changes money or obligations for a typical small s.r.o. (rates, limits, new duties, deadlines)
   * `stredná` – affects some situations (specific expense types, sectors that may apply)
   * `nízka` – technical/administrative, unlikely to matter
4. Update knowledge: grep `knowledge/` for the affected topics/numbers. If a fact there is now wrong or will change
   on a known date, **edit the knowledge file**: fix the number/rule, add "(od D. M. RRRR: …)" for future changes,
   and update its "Posledné overenie" line to today's date. Only edit files under `knowledge/`. Keep edits minimal and
   factual; never delete warnings without a statute basis.
5. Return the structured result exactly as requested in the prompt (JSON). Write summaries in Slovak, concise,
   for a non-lawyer business owner.
