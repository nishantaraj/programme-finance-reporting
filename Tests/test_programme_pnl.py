import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Src"))

import programme_pnl as p  # noqa: E402

DATA = ROOT / "Sample-Data"


def sample_report(as_of=date(2026, 11, 15)):
    return p.run(DATA, "SGD", as_of)


class DeferralMaths(unittest.TestCase):
    prog = p.Programme("FEL-DEMO-DATA-2610", "Test", date(2026, 10, 5), date(2026, 12, 13))  # 70 days

    def test_straight_line_mid_programme(self):
        # 42 of 70 days elapsed on 2026-11-15: 385200 * 42 / 70 = 231120 exactly
        self.assertEqual(p.recognised_revenue(385200, self.prog, date(2026, 11, 15)), 231120)

    def test_before_start_is_zero(self):
        self.assertEqual(p.recognised_revenue(385200, self.prog, date(2026, 10, 4)), 0)

    def test_first_day_counts(self):
        self.assertEqual(p.recognised_revenue(7000, self.prog, date(2026, 10, 5)), 100)

    def test_after_end_is_capped_at_total(self):
        self.assertEqual(p.recognised_revenue(385200, self.prog, date(2027, 6, 1)), 385200)

    def test_recognised_plus_deferred_equals_fees(self):
        for row in sample_report().rows:
            self.assertEqual(row.recognised + row.deferred, row.fees)

    def test_allocation_sums_exactly_and_is_stable(self):
        weights = {"A": 1, "B": 1, "C": 1}
        first = p.allocate(100, weights)
        self.assertEqual(sum(first.values()), 100)
        self.assertEqual(first, p.allocate(100, weights))
        self.assertEqual(first, {"A": 34, "B": 33, "C": 33})


class FxConversion(unittest.TestCase):
    fx = {("2026-08", "INR"): Decimal("0.0156"), ("2026-11", "USD"): Decimal("1.2900")}

    def test_base_currency_is_identity(self):
        self.assertEqual(p.to_base(12345, "SGD", date(2026, 8, 1), "SGD", self.fx), 12345)

    def test_monthly_rate_applied(self):
        # INR 45,000.00 at 0.0156 = SGD 702.00
        self.assertEqual(p.to_base(4500000, "INR", date(2026, 8, 20), "SGD", self.fx), 70200)

    def test_rounds_half_up(self):
        # 1 minor unit * 1.29 = 1.29 -> 1 ; 50 * 1.29 = 64.5 -> 65
        self.assertEqual(p.to_base(1, "USD", date(2026, 11, 1), "SGD", self.fx), 1)
        self.assertEqual(p.to_base(50, "USD", date(2026, 11, 1), "SGD", self.fx), 65)

    def test_missing_rate_raises(self):
        with self.assertRaises(p.MissingRate):
            p.to_base(100, "AED", date(2026, 11, 1), "SGD", self.fx)


class Exceptions(unittest.TestCase):
    def test_bad_rows_are_listed_not_dropped(self):
        rep = sample_report()
        reasons = {t.txn_id: why for t, why in rep.exceptions}
        self.assertEqual(sorted(reasons), ["T016", "T017", "T018"])
        self.assertIn("uncoded", reasons["T016"])
        self.assertIn("unknown code", reasons["T017"])
        self.assertIn("AED", reasons["T018"])

    def test_exceptions_do_not_reach_the_totals(self):
        rep = sample_report()
        direct = {r.code: r.direct for r in rep.rows}
        # T018 (AED, no rate) must not be in the Riverside figure: 40000 + 22950
        self.assertEqual(direct["CMT-RVRS-SAT-2611"], 62950)

    def test_rows_after_as_of_are_excluded_and_listed(self):
        rep = sample_report()
        self.assertEqual([t.txn_id for t in rep.excluded], ["T012"])

    def test_every_row_is_accounted_for(self):
        txns, unreadable = p.load_transactions(DATA / "Transactions.csv")
        rep = sample_report()
        placed_or_flagged = len(rep.exceptions) + len(rep.excluded)
        self.assertEqual(len(txns) + len(unreadable) - placed_or_flagged, 14)  # 18 rows, 4 flagged or excluded, 14 placed


class HandChecked(unittest.TestCase):
    def test_example_fellowship(self):
        row = {r.code: r for r in sample_report().rows}["FEL-DEMO-DATA-2610"]
        # fees: USD 2,000.00 @1.31 = 2,620.00 ; INR 80,000.00 @0.0154 = 1,232.00
        self.assertEqual(row.fees, 385200)
        self.assertEqual(row.recognised, 231120)
        self.assertEqual(row.deferred, 154080)
        # costs: SGD 250.00 + USD 200.00 @1.29 = 258.00
        self.assertEqual(row.direct, 50800)

    def test_overhead_pool_fully_allocated(self):
        rep = sample_report()
        self.assertEqual(sum(r.overhead for r in rep.rows), 112900)  # 600 + 400 + USD 100 @1.29


class Determinism(unittest.TestCase):
    def test_rerun_gives_identical_output(self):
        self.assertEqual(p.render_markdown(sample_report()), p.render_markdown(sample_report()))

    def test_committed_sample_output_is_current(self):
        committed = (ROOT / "Sample-Output" / "Programme-Pnl.md").read_text()
        self.assertEqual(p.render_markdown(sample_report()), committed)


if __name__ == "__main__":
    unittest.main()
