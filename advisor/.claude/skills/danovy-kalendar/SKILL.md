---
name: danovy-kalendar
description: Tax and filing deadlines for the s.r.o. – corporate income tax return, VAT return and control statement, EC sales list, payroll levies, dividend withholding tax, motor vehicle tax, extensions. Use for "when do I have to file/pay…", "what's due this month", "can I postpone the tax return".
---

# Daňový kalendár – postup

1. Read `knowledge/danovy-kalendar.md`.
2. Use today's date (given in the system prompt) to answer "what's next / what's due this month".
   Consider the company profile (VAT payer? monthly/quarterly? employees? car?) and list only what applies.
3. Weekend/holiday shifts to the next working day (daňový poriadok). For exact dates in the current year, or anything
   marked ⚠️, verify on financnasprava.sk (Daňový kalendár) with WebFetch/WebSearch when allowed, otherwise say it's
   unverified.
4. Extension of the DPPO return: notification to the tax office by the original deadline → +3 months (+6 with foreign
   income); tax is then also paid by the extended deadline.
