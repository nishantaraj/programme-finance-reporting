#!/usr/bin/env python3
"""
Per-programme profit and loss, with deferred revenue, from coded transactions.

An original illustration of a pattern: every transaction carries a programme
code, the code is the join key between finance, operations and the database,
and revenue is recognised over the programme's delivery dates instead of when
the cash arrives. All data in this repo is invented.

Rules, in short:
  * Money is integer minor units (assumed 2 decimals). Never floats.
  * Each row is converted to the base currency at the monthly rate for the
    month of the transaction, rounded half up to a minor unit.
  * Fees received in advance sit as a liability (deferred) and are recognised
    straight-line, per day, across start..end of the programme, up to --as-of.
  * Direct costs hit the programme they carry. Overhead rows carry the pool
    code OVH and are allocated to programmes pro rata to recognised revenue.
  * Anything that cannot be placed (no code, unknown code, missing FX rate...)
    is listed under Exceptions. Nothing is silently dropped.
  * Rows dated after --as-of are excluded and listed, not hidden.

Usage:
    python Src/programme_pnl.py --as-of 2026-11-15 --base SGD --out Reports
"""

import argparse
import csv
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

OVERHEAD_CODE = "OVH"
CODE_RE = re.compile(r"^(CMP|CMT|FEL)-[A-Z0-9]{2,6}-[A-Z0-9]{2,6}-\d{4}$")
TXN_TYPES = ("fee_received", "direct_cost", "overhead")


class MissingRate(Exception):
    pass


@dataclass(frozen=True)
class Programme:
    code: str
    name: str
    start: date
    end: date

    @property
    def total_days(self) -> int:
        return (self.end - self.start).days + 1


@dataclass(frozen=True)
class Txn:
    txn_id: str
    day: date
    code: str
    kind: str
    description: str
    currency: str
    amount_minor: int


@dataclass
class Row:
    code: str
    name: str
    fees: int = 0
    recognised: int = 0
    deferred: int = 0
    direct: int = 0
    overhead: int = 0

    @property
    def margin(self) -> int:
        return self.recognised - self.direct - self.overhead


@dataclass
class Report:
    as_of: date
    base: str
    rows: list = field(default_factory=list)
    exceptions: list = field(default_factory=list)  # (Txn or raw dict, reason)
    excluded: list = field(default_factory=list)  # Txn dated after as_of
    overhead_unallocated: int = 0


# ---------------------------------------------------------------- loading

def load_programmes(path: Path) -> dict:
    out = {}
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            out[r["programme_code"]] = Programme(
                r["programme_code"],
                r["programme_name"],
                date.fromisoformat(r["start_date"]),
                date.fromisoformat(r["end_date"]),
            )
    return out


def load_fx(path: Path) -> dict:
    out = {}
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            out[(r["month"], r["currency"])] = Decimal(r["rate_to_base"])
    return out


def load_transactions(path: Path):
    """Returns (valid_rows, unreadable_rows). Unreadable rows become exceptions."""
    good, bad = [], []
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            try:
                good.append(
                    Txn(
                        r["txn_id"],
                        date.fromisoformat(r["date"]),
                        (r["programme_code"] or "").strip(),
                        r["type"].strip(),
                        r["description"],
                        r["currency"].strip(),
                        int(r["amount_minor"]),
                    )
                )
            except (ValueError, KeyError, InvalidOperation):
                bad.append(r)
    return good, bad


# ------------------------------------------------------------------ maths

def round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_base(amount_minor: int, currency: str, day: date, base: str, fx: dict) -> int:
    """Convert integer minor units to the base currency at the monthly rate."""
    if currency == base:
        return amount_minor
    key = (day.strftime("%Y-%m"), currency)
    if key not in fx:
        raise MissingRate(f"no {currency} rate for {key[0]}")
    return round_half_up(Decimal(amount_minor) * fx[key])


def recognised_revenue(total: int, programme: Programme, as_of: date) -> int:
    """Straight-line per day across start..end, inclusive, capped at the total."""
    elapsed = (as_of - programme.start).days + 1
    elapsed = max(0, min(elapsed, programme.total_days))
    return round_half_up(Decimal(total) * elapsed / programme.total_days)


def allocate(total: int, weights: dict) -> dict:
    """Largest-remainder split of an integer total. Ties break on key order,
    so the same input always gives the same output and the parts sum exactly."""
    weight_sum = sum(weights.values())
    if weight_sum == 0:
        return {k: 0 for k in weights}
    shares = {k: (total * w) // weight_sum for k, w in weights.items()}
    remainders = {k: (total * w) % weight_sum for k, w in weights.items()}
    left = total - sum(shares.values())
    for k in sorted(weights, key=lambda k: (-remainders[k], k))[:left]:
        shares[k] += 1
    return shares


# ----------------------------------------------------------------- report

def classify(t: Txn, programmes: dict):
    """Return a reason string if the row cannot be placed, else None."""
    if t.kind not in TXN_TYPES:
        return f"unknown type '{t.kind}'"
    if not t.code:
        return "uncoded: no programme code"
    if t.code == OVERHEAD_CODE:
        return None if t.kind == "overhead" else "OVH code is only for overhead rows"
    if t.kind == "overhead":
        return "overhead rows must use the OVH pool code"
    if not CODE_RE.match(t.code):
        return f"malformed code '{t.code}'"
    if t.code not in programmes:
        return f"unknown code '{t.code}' (not in the programme register)"
    return None


def build_report(programmes, txns, unreadable, fx, base, as_of) -> Report:
    rep = Report(as_of=as_of, base=base)
    rep.exceptions.extend((r, "unreadable row (bad date, amount or columns)") for r in unreadable)
    rows = {c: Row(c, p.name) for c, p in programmes.items()}
    overhead_pool = 0

    for t in sorted(txns, key=lambda t: (t.day, t.txn_id)):
        if t.day > as_of:
            rep.excluded.append(t)
            continue
        reason = classify(t, programmes)
        if reason is None:
            try:
                value = to_base(t.amount_minor, t.currency, t.day, base, fx)
            except MissingRate as e:
                reason = str(e)
        if reason is not None:
            rep.exceptions.append((t, reason))
            continue
        if t.kind == "fee_received":
            rows[t.code].fees += value
        elif t.kind == "direct_cost":
            rows[t.code].direct += value
        else:
            overhead_pool += value

    for code, row in rows.items():
        row.recognised = recognised_revenue(row.fees, programmes[code], as_of)
        row.deferred = row.fees - row.recognised

    weights = {c: r.recognised for c, r in rows.items() if r.recognised > 0}
    if overhead_pool and weights:
        for code, amount in allocate(overhead_pool, weights).items():
            rows[code].overhead = amount
    else:
        rep.overhead_unallocated = overhead_pool

    rep.rows = [rows[c] for c in sorted(rows)]
    return rep


# -------------------------------------------------------------- rendering

def money(minor: int) -> str:
    sign = "-" if minor < 0 else ""
    whole, cents = divmod(abs(minor), 100)
    return f"{sign}{whole:,}.{cents:02d}"


def pct(margin: int, revenue: int) -> str:
    if revenue == 0:
        return "n/a"
    value = (Decimal(margin) * 100 / Decimal(revenue)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{value}%"


def render_markdown(rep: Report) -> str:
    out = []
    out.append("# Programme P&L")
    out.append("")
    out.append(f"As of {rep.as_of.isoformat()}. Base currency {rep.base}. Amounts are in {rep.base} with two decimals.")
    out.append("Invented data, generated by `Src/programme_pnl.py`.")
    out.append("")
    out.append("| Programme code | Programme | Fees received | Revenue recognised | Deferred (liability) | Direct costs | Overhead allocated | Margin | Margin % |")
    out.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    tot = Row("Total", "")
    for r in rep.rows:
        out.append(
            f"| {r.code} | {r.name} | {money(r.fees)} | {money(r.recognised)} | {money(r.deferred)} | "
            f"{money(r.direct)} | {money(r.overhead)} | {money(r.margin)} | {pct(r.margin, r.recognised)} |"
        )
        tot.fees += r.fees
        tot.recognised += r.recognised
        tot.deferred += r.deferred
        tot.direct += r.direct
        tot.overhead += r.overhead
    out.append(
        f"| **Total** |  | **{money(tot.fees)}** | **{money(tot.recognised)}** | **{money(tot.deferred)}** | "
        f"**{money(tot.direct)}** | **{money(tot.overhead)}** | **{money(tot.margin)}** | **{pct(tot.margin, tot.recognised)}** |"
    )
    out.append("")
    if rep.overhead_unallocated:
        out.append(
            f"Overhead not allocated (no recognised revenue to allocate against): {money(rep.overhead_unallocated)} {rep.base}."
        )
        out.append("")

    out.append("## Exceptions")
    out.append("")
    out.append("Rows that could not be placed. They are not in the table above, and they need a person to fix the source.")
    out.append("")
    if rep.exceptions:
        out.append("| Txn | Date | Code | Type | Amount | Reason |")
        out.append("|---|---|---|---|---:|---|")
        for item, reason in sorted(rep.exceptions, key=lambda x: _exc_id(x[0])):
            if isinstance(item, Txn):
                out.append(
                    f"| {item.txn_id} | {item.day.isoformat()} | {item.code or '(blank)'} | {item.kind} | "
                    f"{item.currency} {money(item.amount_minor)} | {reason} |"
                )
            else:
                out.append(f"| {item.get('txn_id', '?')} | {item.get('date', '?')} | {item.get('programme_code') or '(blank)'} | "
                           f"{item.get('type', '?')} | {item.get('currency', '?')} {item.get('amount_minor', '?')} | {reason} |")
    else:
        out.append("None.")
    out.append("")

    out.append("## Excluded: dated after the as-of date")
    out.append("")
    if rep.excluded:
        out.append(", ".join(f"{t.txn_id} ({t.day.isoformat()})" for t in rep.excluded) + ".")
    else:
        out.append("None.")
    out.append("")

    out.append("## Method")
    out.append("")
    out.append("- Each row is converted at the monthly rate for the month of the transaction, rounded half up to a minor unit.")
    out.append("- Fees received are held as a liability and recognised per day across the programme's start and end dates, up to the as-of date.")
    out.append("- Overhead (code OVH) is allocated to programmes pro rata to recognised revenue, largest remainder, so the parts sum exactly.")
    out.append("- Margin is recognised revenue minus direct costs minus allocated overhead.")
    out.append("")
    return "\n".join(out)


def _exc_id(item):
    return item.txn_id if isinstance(item, Txn) else str(item.get("txn_id", ""))


# -------------------------------------------------------------------- cli

def run(data_dir: Path, base: str, as_of: date) -> Report:
    programmes = load_programmes(data_dir / "Programmes.csv")
    fx = load_fx(data_dir / "Fx-Rates.csv")
    txns, unreadable = load_transactions(data_dir / "Transactions.csv")
    return build_report(programmes, txns, unreadable, fx, base, as_of)


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Per-programme P&L with deferred revenue.")
    ap.add_argument("--as-of", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
    ap.add_argument("--base", default="SGD", help="base currency code (default SGD)")
    ap.add_argument("--out", default="Reports", help="output folder (default Reports)")
    ap.add_argument("--data", default=str(root / "Sample-Data"), help="folder with the three CSV files")
    args = ap.parse_args()

    rep = run(Path(args.data), args.base, args.as_of)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "Programme-Pnl.md"
    target.write_text(render_markdown(rep))
    print(f"Wrote {target}")
    print(f"Exceptions: {len(rep.exceptions)}  Excluded after as-of: {len(rep.excluded)}")


if __name__ == "__main__":
    main()
