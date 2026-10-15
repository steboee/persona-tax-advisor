---
name: citovanie-zakona
description: Find and quote the exact wording of a Slovak statute provision from the locally synced law texts (laws/<id>/current.md), check which version is in force and whether an amendment is coming. Use whenever you cite a §, need exact statutory wording, a limit/rate from the law, or must verify a ⚠️ item.
---

# Citovanie zákona – postup

1. Find the law id in `laws/registry.json` (e.g. `zdp` = 595/2003 daň z príjmov, `dph` = 222/2004, `cestovne-nahrady`
   = 283/2002, `socialne-poistenie` = 461/2003, `zdravotne-poistenie` = 580/2004, `transakcna-dan` = 279/2024,
   `uctovnictvo` = 431/2002, `danovy-poriadok` = 563/2009, `zakonnik-prace` = 311/2001,
   `dan-z-motorovych-vozidiel` = 361/2014, `obchodny-zakonnik` = 513/1991).
2. Check `laws/STATUS.md` (in context) for the version in force and upcoming versions.
3. Locate the provision in `laws/<id>/current.md`:
   * Section heading lines look like `### § 21` (paragraphs) – grep `^### § 21$` with `-A` context, or grep a keyword
     (e.g. `reprezentáci`, `17 eur`, `stravné`, `48 000`) with `-n` and then Read around that line with offset/limit.
   * Odseky are `(1)`, `(2)`…; písmená `a)`, `b)`…
   * The files are large – never Read a whole law file; always grep first, then Read a window (e.g. 80 lines).
4. Quote briefly (one sentence or the relevant písmeno), then cite as
   "§ 21 ods. 1 písm. h) zákona č. 595/2003 Z. z. (znenie účinné od D. M. RRRR)".
5. If an upcoming version exists (`laws/<id>/versions/<future date>.md`), grep the same provision there; if it differs,
   tell the user what changes and from when.
6. If the law file is missing, say "lokálne znenie zákona nie je stiahnuté (spusti law sync)" and fall back to
   knowledge files or the web (static.slov-lex.sk).
