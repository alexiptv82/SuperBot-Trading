"""No-I/O invariants of three separate 2k PAPER Brain trials."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import TestCase, main

from backend.v3.arena.trial_plan import build_trial_plan


class TestTrialPlan(TestCase):
    def test_three_wallets_are_independent_and_disabled(self):
        plans = build_trial_plan(date(2026, 11, 18))
        self.assertEqual([p.provider for p in plans], ["deepseek", "qwen", "minimax"])
        self.assertEqual(len({p.journal for p in plans}), 3)
        self.assertEqual(len({p.budget for p in plans}), 3)
        self.assertEqual(len({p.run_id for p in plans}), 3)
        self.assertEqual(sum((p.capital_usdt for p in plans), Decimal(0)),
                         Decimal("6000"))
        self.assertTrue(all(p.capital_usdt == Decimal("2000") for p in plans))
        self.assertTrue(all(p.internal_portfolio_id == "brain" for p in plans))
        self.assertTrue(all(not p.enabled and not p.approved for p in plans))
        self.assertEqual(plans[1].model, "qwen/qwen3.7-plus")
        self.assertEqual(plans[2].model, "minimax/minimax-m3.1-flash")
        self.assertEqual(plans[0].run_id, "brain-deepseek-paper20261118")

    def test_plan_has_no_side_effects(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "arena"
            plans = build_trial_plan(date(2026, 11, 18), root=root)
            self.assertEqual(len(plans), 3)
            self.assertFalse(root.exists())

    def test_invalid_date_and_root_fail_closed(self):
        for day in ("2026-11-18", None):
            with self.assertRaises(ValueError):
                build_trial_plan(day)
        for root in (Path("relative"), Path("/"), Path("/tmp/../arena")):
            with self.assertRaises(ValueError):
                build_trial_plan(date(2026, 11, 18), root=root)


if __name__ == "__main__":
    main()
