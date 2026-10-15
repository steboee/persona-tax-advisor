# Zdroje (kam siahať pri overovaní)

## Primárne (zákony) – lokálne synchronizované
- `laws/registry.json` – zoznam sledovaných zákonov a ich ID.
- `laws/<id>/current.md` – úplné znenie účinné dnes (zo Slov-Lex). Grep podľa „§ 21“, „ods.“, kľúčových slov.
- `laws/<id>/versions/<YYYYMMDD>.md` – ďalšie stiahnuté znenia (aj budúce, už vyhlásené).
- `laws/CHANGELOG.md` – čo sa zmenilo, kedy, a čo to znamená.
- Slov-Lex online: `https://static.slov-lex.sk/static/SK/ZZ/<rok>/<číslo>/` (história znení),
  `https://static.slov-lex.sk/static/SK/ZZ/<rok>/<číslo>/<YYYYMMDD>.html` (konkrétne znenie), `https://www.slov-lex.sk`.

## Oficiálne usmernenia
- Finančná správa – metodické pokyny a usmernenia: https://www.financnasprava.sk/sk/podnikatelia/dane
- Finančná správa – znalostná báza (FAQ): https://podpora.financnasprava.sk
- Finančná správa – daňový kalendár: https://www.financnasprava.sk/sk/podnikatelia/danovy-kalendar
- Sociálna poisťovňa: https://www.socpoist.sk
- MPSVR (stravné, minimálna mzda, cestovné náhrady): https://www.employment.gov.sk
- Ministerstvo financií (návrhy zákonov, konsolidácia): https://www.mfsr.sk
- NR SR – legislatívny proces (schvaľované novely): https://www.nrsr.sk

## Sekundárne (dobré na orientáciu, nie ako jediný zdroj)
- podnikajte.sk, pravnenoviny.sk, aksamec.sk, kros.sk (akadémia), zakonypreludi.sk (zrkadlo znení zákonov)

## Pravidlo
Ak sekundárny zdroj odporuje znení zákona v `laws/`, platí zákon. Ak si nie si istý, povedz to a uveď oboje.
