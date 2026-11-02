# Programme code convention

One short code identifies every programme run. The same string is used in the accounting system's tracking category, in the application and payment records, in the response sheets, and in the database. Because it is identical everywhere, a payment, a cost, an application and a report row can all be joined without a lookup table or a person's memory.

## Format

```
TYPE-PARTNER-PROGRAMME-COHORT
CMP-NRTH-LEAD-2609
```

| Part | Rule | Example |
|---|---|---|
| TYPE | Three letters. `CMP` camp, `CMT` competition, `FEL` fellowship | `CMP` |
| PARTNER | 2 to 6 upper-case letters or digits, the organisation the run is delivered with | `NRTH` |
| PROGRAMME | 2 to 6 upper-case letters or digits, the programme family | `LEAD` |
| COHORT | Four digits, year and month the cohort starts (`YYMM`) | `2609` |

The pattern is `^(CMP|CMT|FEL)-[A-Z0-9]{2,6}-[A-Z0-9]{2,6}-\d{4}$`. All codes in this repo are invented.

## Reserved code

`OVH` is the pool for shared overhead. It is valid only on overhead rows, and it is allocated to programmes at report time.

## Rules

1. A code is created once, in the programme register, before the first transaction uses it.
2. A code is never reused and never edited. A cohort that moves gets a new code and the old one is closed.
3. Every transaction carries exactly one code. A row without one is an exception, not a default bucket.
4. A well-formed code that is not in the register is also an exception. The usual cause is a typo or a run that was never registered.
5. The register holds the start and end dates, which are what revenue recognition uses.

## Why bother

Without a shared key, each team keeps its own list of names for a programme, and reconciling them is a recurring manual job. With one, the report in this repo is a straight group-by.
