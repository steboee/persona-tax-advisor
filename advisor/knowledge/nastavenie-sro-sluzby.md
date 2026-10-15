# Nastavenie novej s.r.o., ktorá predáva služby (konateľ = jediný spoločník)

Posledné overenie: 2026-10-15 · ⚠️ = over v zákone / u účtovníka pred rozhodnutím.
Toto sú **odporúčania pre typický prípad** (1 človek robí služby – IT, konzulting, dizajn… – cez vlastnú s.r.o.).
Vždy ich prispôsob faktom v `profile/company.md` a `profile/memory.md`.

## 1. Pri zakladaní (checklist)
- [ ] Spoločenská zmluva / zakladateľská listina, konateľ, sídlo, predmet podnikania (voľné živnosti na služby).
- [ ] Základné imanie ⚠️ (doteraz min. 5 000 €; over aktuálny stav Obchodného zákonníka – grep v `laws/obchodny-zakonnik/current.md`).
- [ ] Zápis do obchodného registra → DIČ pridelí finančná správa (registrácia na daň z príjmov prebieha automaticky ⚠️).
- [ ] **Elektronická schránka** na slovensko.sk – aktivovať (povinná komunikácia s FS).
- [ ] Podnikateľský bankový účet + firemná karta (transakčná daň: karta 2 €/rok, prevody 0,4 % max 40 €).
- [ ] Účtovník (s.r.o. = podvojné účtovníctvo) – dohodnúť pred prvou faktúrou.
- [ ] **DPH pri službách do/z EÚ – § 7a** (pozri bod 3) – vybaviť **pred** prvou takou službou.
- [ ] Ak bude firma vyplácať odmenu/mzdu → registrácia zamestnávateľa v Sociálnej poisťovni a zdravotnej poisťovni.
- [ ] e-kasa len ak budeš prijímať hotovosť/kartu od fyzických osôb (B2B faktúry na účet ju nepotrebujú).
- [ ] Prvé zdaňovacie obdobie: **minimálna daň (daňová licencia) sa neplatí** za obdobie, v ktorom firma vznikla (§ 46b ⚠️).

## 2. Odmena konateľa – 3 modely
| Model | Odvody | Daň | Kedy dáva zmysel |
|---|---|---|---|
| **A. Konateľ bez odmeny + dividendy** | sociálne žiadne; zdravotné ako **samoplatiteľ**, ak nemáš iný príjem (min. ~121,92 €/mes. v 2026 ⚠️) | zisk: DPPO 10 % (výnosy ≤ 100 000 €) + dividenda 7 % → **~16,3 %** | najnižšie celkové zaťaženie; nevýhoda: žiadne nemocenské, dôchodok len minimálny |
| **B. Pravidelná mesačná odmena** (zmluva o výkone funkcie) | konateľ 9,4 % soc. + 5 % zdrav.; firma 24,15 % soc. + 11 % zdrav. ⚠️ | 19 % (25 %…) po odpočítaní nezdaniteľnej časti (497,23 €/mes. v 2026 ⚠️) | chceš nemocenské/dôchodok/hypotéku (príjem pre banku), alebo zisk > pásmo 10 % |
| **C. Pracovná zmluva** na inú činnosť (napr. programátor) | ako bežný zamestnanec (firma 36,2 %, ty 13,4 %) ⚠️ | ako mzda | keď potrebuješ plnohodnotného zamestnanca (materské, PN, nárok na stravovanie) |

- Konateľ vykonáva funkciu v **obchodnoprávnom** vzťahu (zmluva o výkone funkcie), nie v pracovnom pomere.
- **Nepravidelná** odmena (napr. raz ročne) → nižšie sociálne sadzby (konateľ 7 %, firma 21,75 % ⚠️).
- Odmena = daňový výdavok firmy (zníži DPPO 10 %/21 %), ale odvody + daň zo mzdy sú zvyčajne vyššie než dividenda.

### Odporúčanie pre začínajúcu servisnú s.r.o. (typický prípad)
1. Na začiatku: **model A** (bez odmeny), peniaze von cez **dividendy** po schválení závierky + **cestovné náhrady** pri cestách.
2. Ak potrebuješ pravidelný príjem pre banku, nemocenské alebo materské/otcovské → zvážiť **malú pravidelnú odmenu** (model B)
   a zvyšok dividendy. Konkrétnu sumu prepočítať (deep mode, `mzdy-odvody-specialista`).
3. Sleduj **výnosy 100 000 €** – nad ňou DPPO 21 %; potom sa mení optimum (odmena znižuje základ dane z 21 %).
4. Nezabudni: dividendy až po roku (zo schváleného zisku). V prvom roku žiješ z úspor alebo z odmeny.

## 3. DPH pri službách (dôležité pre IT/konzulting)
- **Klient firma v inom štáte EÚ** (B2B služby, miesto dodania podľa § 15 ods. 1): neplatiteľ sa musí **registrovať podľa § 7a
  pred dodaním služby** (bez ohľadu na sumu). Faktúra bez DPH s „prenesenie daňovej povinnosti“ + IČ DPH oboch strán;
  **súhrnný výkaz** do 25. dňa po štvrťroku. Registrácia § 7a = nie si plnohodnotný platiteľ (žiadny odpočet).
- **Nákup služieb z EÚ/mimo EÚ** (Google Ads, AWS, SaaS, Upwork…): tiež § 7a a **samozdanenie** (zaplatíš DPH 23 % v SR bez odpočtu, ak nie si platiteľ).
- **Klienti na Slovensku:** platiteľom DPH sa staneš povinne pri obrate > 50 000 €/rok (od 1. 1. nasl. roka) alebo > 62 500 € v priebehu roka (okamžite).
- **Dobrovoľná registrácia** sa oplatí, ak máš veľa nákupov s DPH a klientov-platiteľov (pre nich je DPH neutrálna);
  neoplatí sa, ak predávaš ľuďom/neplatiteľom.

## 4. Zamestnať partnerku/partnera alebo člena rodiny?
**Áno, legálne to ide – ale len ak je to skutočná práca za primeranú mzdu.** Partner(ka) je pre firmu bežný zamestnanec.
- **Podmienky, aby to obstálo pri kontrole:** reálna, preukázateľná práca, ktorú firma potrebuje (administratíva, fakturácia,
  marketing, sociálne siete, zákaznícka podpora, účtovné podklady…); mzda zodpovedá práci a trhu (nie 3 000 € za 2 hodiny týždenne);
  pracovná zmluva/dohoda, pracovná náplň, výkazy, výstupy (e-maily, dokumenty), dochádzka pri pracovnom pomere.
- **Riziko:** fiktívne zamestnanie alebo nadhodnotená mzda → správca dane neuzná mzdu ako daňový výdavok (doplatok DPPO + pokuta),
  Sociálna poisťovňa môže preskúmať účelové zamestnanie pred materskou (nemocenské dávky). ⚠️
- **Čo to reálne prinesie:** rozdelenie príjmu na dve osoby (každá s vlastnou nezdaniteľnou časťou a nižším pásmom dane),
  partnerka má sociálne a zdravotné poistenie (nemocenské, dôchodok, **materské** – ak plánujete deti, materská sa počíta
  z jej vymeriavacieho základu ⚠️ podmienky a rozhodné obdobie over), mzda je daňový výdavok firmy.
- **Čo to stojí:** odvody spolu ~49 % nad čistou mzdou pri pracovnom pomere (firma ~36,2 %, zamestnanec 13,4 %) ⚠️ – pri malej
  sume a ak partnerka nemá iné poistenie sa to môže oplatiť (inak by platila zdravotné ako samoplatiteľ).
- **Formy:** pracovná zmluva na kratší úväzok (aspoň minimálna mzda pomerne – 915 €/mes. pri plnom úväzku v 2026);
  **dohoda o pracovnej činnosti** (max. 10 h/týždeň ⚠️) – lacnejšie administratívne, odvody podobné; **dohoda o brigádnickej práci
  študentov** – odvodová úľava do limitu ⚠️ (len študent).
- **Manželka vs. priateľka:** daňovo pre firmu rovnaké. Nezdaniteľná časť „na manželku“ (u teba, nie vo firme) existuje len pre manželstvo.
- **Odporúčanie:** zamestnať len ak partnerka naozaj pre firmu pracuje (alebo bude). Začať dohodou alebo menším úväzkom,
  mzda v trhovej výške za danú prácu, viesť dôkazy o práci. Pred rozhodnutím prepočítať (deep mode).

## 5. Čo si ešte nastaviť hneď
- Cestovné príkazy pri cestách ku klientom (stravné je pre konateľa daňové a nezdaňuje sa).
- Domáca kancelária: nájomná zmluva firma ↔ konateľ (nájomné je výdavok firmy, u teba príjem z prenájmu § 6 ods. 3) ⚠️ alebo coworking.
- Notebook/telefón kupovať na firmu (ak primárne na prácu); pri súkromnom používaní pomer.
- Auto: od 2026 len 50 % odpočet DPH pri osobnom aute (ak budeš platiteľ) – pred kúpou poradiť (`firemne-auto`).
