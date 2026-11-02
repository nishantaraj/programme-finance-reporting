# Programme finance reporting

A small, runnable illustration of how I produce a per-programme profit and loss when cash arrives long before the work is delivered. It is an original illustration of the pattern, written for this repo. It is not company code and it uses no company data: every programme, partner, code, amount and exchange rate in here is invented.

## The problem

A programme collects fees in advance, in more than one currency, from several sources. Finance wants to know which programmes make money, and the answer is wrong if cash is treated as revenue the day it lands. It is also wrong if costs, overhead and currency conversion are handled differently by each person who touches the spreadsheet.

## The approach

1. **One programme code on every row.** The code (`CMP-NRTH-LEAD-2609`: type, partner, programme, cohort) is the join key for finance, operations and the database. See [Docs/Programme-Code-Convention.md](Docs/Programme-Code-Convention.md).
2. **Money as integer minor units.** No floats anywhere. Conversion to the base currency uses a monthly rate table and rounds half up.
3. **Advance fees are a liability first.** They are recognised per day across the programme's delivery dates, up to the as-of date, and the rest stays deferred.
4. **Overhead has a pool code.** It is allocated to programmes pro rata to recognised revenue, using largest remainder so the parts sum exactly to the pool.
5. **Nothing disappears.** Rows with no code, an unknown code, or a missing exchange rate go to an Exceptions section. Rows dated after the as-of date are listed as excluded.

## Run it

```bash
python Src/programme_pnl.py --as-of 2026-11-15 --base SGD --out Reports
python -m unittest discover -s Tests -v
```

Only the Python standard library is used (3.9 or newer). The report is written to `Reports/Programme-Pnl.md`, which is gitignored. A committed example from the sample data is in [Sample-Output/Programme-Pnl.md](Sample-Output/Programme-Pnl.md), and a test fails if it drifts from what the script produces.

## Layout

| Folder | What is in it |
|---|---|
| `Src/` | `programme_pnl.py`, the whole calculation |
| `Sample-Data/` | Invented programme register, transactions and monthly FX rates |
| `Sample-Output/` | The committed example report |
| `Reports/` | Where generated reports go (ignored by git) |
| `Docs/` | The programme code convention |
| `Tests/` | Deferral maths, FX conversion, exceptions, determinism, one hand-checked programme |

## What the sample shows

The sample has four programmes and 18 transactions. Three rows are deliberately broken: one has no code, one has a well-formed code that is not in the register, and one is in a currency with no rate. All three appear under Exceptions and none of them touch the totals. One row is dated after the as-of date and is listed as excluded.

One programme is worth checking by hand, because it is the one I use in the tests. The fellowship received fees worth 3,852.00 SGD after conversion, and 42 of its 70 delivery days had passed on 2026-11-15, so 3,852.00 x 42 / 70 = 2,311.20 is recognised and 1,540.80 is still deferred.

## Limits

- Every currency is assumed to have two decimal places.
- Recognition is straight-line by day. Real programmes sometimes need milestones instead.
- Costs are recognised when incurred, with no accruals or prepayments.
- Overhead allocation by revenue is one choice among several, and a different basis changes every margin.
- This is a reporting calculation. It does not post to, or read from, any accounting system.
