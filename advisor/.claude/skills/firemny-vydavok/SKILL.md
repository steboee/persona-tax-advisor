---
name: firemny-vydavok
description: Decide whether the s.r.o. can pay for something and whether it is a tax-deductible expense (daňový výdavok) with VAT deduction. Use for any "can I pay this with the company card / can the company buy / is this deductible" question — lunches, dinners, coffee with clients, gifts, electronics, clothes, phone, software, education, fitness, home office, fines, parking, taxi, groceries, etc.
---

# Môže to zaplatiť firma? – rozhodovací postup

Work through these steps quickly (most answers need only steps 1–4). Facts: `knowledge/bezne-vydavky.md`,
`knowledge/reprezentacia.md`, `knowledge/sadzby-a-limity.md` (already in context).

1. **Business purpose (§ 2 písm. i) ZDP).** Does the expense serve the company's business (earning, securing,
   maintaining taxable income)? Purely private → ❌ not a company expense at all; if paid by the company it must be
   repaid by the konateľ or becomes their taxable income / hidden profit distribution. Say this clearly.
2. **Explicitly non-deductible (§ 21 ZDP)?** Typical: representation (§ 21 ods. 1 písm. h) – meals/drinks with clients,
   hospitality, gifts; fines and penalties from the state; personal consumption. Representation → ❌ deductible,
   but the company **may still pay** it (booked as non-deductible, 513).
   Exception: promotional items (reklamné predmety) ≤ 17 € per piece (not alcohol/tobacco) → ✅.
3. **Limited deductibility (§ 19 ZDP)?** Travel allowances only up to statutory amounts (`pracovna-cesta` skill),
   car costs with logbook and private-use split (`firemne-auto` skill), mixed-use phone/internet proportionally,
   employee benefits with conditions.
4. **Asset or expense?** Tangible > 1 700 € (and useful life > 1 year) → depreciate; intangible > 2 400 € → amortize.
5. **VAT (only if the company is a VAT payer – check profile).** Deduction only for goods/services used for taxable
   supplies (§ 49). No deduction for hospitality/entertainment (§ 49 ods. 7) except promo items ≤ 17 € excl. VAT.
   Passenger car M1 acquired 1. 1. 2026 – 30. 6. 2028 → 50 % (§ 85n). Non-deductible VAT increases the cost; for
   representation the whole amount incl. VAT is non-deductible.
6. **Who benefits?** If the konateľ/employee personally benefits (fitness, clothes, private trips), it is usually
   their taxable non-cash income (nepeňažný príjem, § 5 ods. 3) → payroll tax + contributions.
7. **Documents & booking.** e-kasa receipt or invoice for the company (IČO/DIČ), note who/why for client meetings,
   cestovný príkaz for trips, logbook for car. Name the account type when helpful (513 reprezentácia,
   501 spotreba materiálu, 518 služby, 512 cestovné).

## Verify before citing
Grep the statute when you cite a §: e.g. `Grep pattern="reprezentáci" path="laws/zdp/current.md"` (see
`citovanie-zakona` skill). If `laws/zdp/current.md` doesn't exist, cite from knowledge and say the local statute text
wasn't available.

## Output
Answer in the format from CLAUDE.md. The spoken part must answer the literal question first, e.g.:
"Áno, firemnou kartou to zaplatiť môžeš, ale obed s klientom je reprezentácia, takže to nie je daňový výdavok a DPH
si neodpočítaš. Pýtaj bloček a poznač si, s kým si bol a prečo."
