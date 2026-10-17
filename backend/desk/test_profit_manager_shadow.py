"""Isolated unit tests for the pure shadow decision function.

Run: python -m unittest discover -s backend/desk -p 'test_profit_manager_shadow.py'
No bot, exchange, network, or persistent state is touched.
"""
import math
import unittest

try:
    from backend.desk.profit_manager_shadow import assess, ProfitConfig
except ModuleNotFoundError:
    from profit_manager_shadow import assess, ProfitConfig


class ShadowProfitMathTests(unittest.TestCase):
    def setUp(self):
        self.no_cost = ProfitConfig(
            activation_roi_pct=20, lock_roi_pct=5, trail_drawdown_pct=12,
            fee_rate_side=0, slip_rate_side=0, min_hold_seconds=0,
        )

    def calc(self, side=1, mark=101, peak=0, **kwargs):
        return assess(side=side, entry=100, mark=mark, qty=10, margin=40,
                      peak_roi_net_pct=peak, held_seconds=120,
                      config=self.no_cost, **kwargs)

    def test_long_and_short_symmetric_before_costs(self):
        long = self.calc(side=1, mark=101)
        short = self.calc(side=-1, mark=99)
        self.assertEqual(long.estimated_net_usdt, 10)
        self.assertEqual(short.estimated_net_usdt, 10)
        self.assertEqual(long.roi_net_pct, 25)
        self.assertEqual(short.roi_net_pct, 25)

    def test_activation_and_trailing_exit(self):
        self.assertEqual(self.calc(mark=100.4).reason, "not_activated")
        armed = self.calc(mark=101)
        self.assertEqual(armed.action, "HOLD")
        self.assertEqual(armed.protected_roi_pct, 13)
        reversal = self.calc(mark=100.5, peak=25)
        self.assertEqual(reversal.action, "SHADOW_EXIT")
        self.assertEqual(reversal.protected_roi_pct, 13)

    def test_positive_funding_paid_reduces_net(self):
        base = self.calc()
        paid = self.calc(funding_usdt=2)
        self.assertEqual(base.estimated_net_usdt - paid.estimated_net_usdt, 2)

    def test_negative_funding_received_increases_net(self):
        base = self.calc()
        received = self.calc(funding_usdt=-2)
        self.assertEqual(received.estimated_net_usdt - base.estimated_net_usdt, 2)

    def test_actual_open_fee_used_instead_of_assumption(self):
        cfg = ProfitConfig(fee_rate_side=0.001, slip_rate_side=0,
                           min_hold_seconds=0)
        d = assess(side=1, entry=100, mark=101, qty=10, margin=40,
                   peak_roi_net_pct=0, held_seconds=120, config=cfg,
                   open_fee_usdt=3)
        self.assertAlmostEqual(d.estimated_net_usdt, 5.99, places=4)

    def test_slippage_is_adverse_for_both_sides(self):
        cfg = ProfitConfig(fee_rate_side=0, slip_rate_side=0.001,
                           min_hold_seconds=0)
        for side, mark in ((1, 101), (-1, 99)):
            d = assess(side=side, entry=100, mark=mark, qty=10, margin=40,
                       peak_roi_net_pct=0, held_seconds=120, config=cfg)
            self.assertLess(d.estimated_net_usdt, 10)

    def test_minimum_hold_does_not_propose_exit(self):
        cfg = ProfitConfig(fee_rate_side=0, slip_rate_side=0,
                           min_hold_seconds=60)
        d = assess(side=1, entry=100, mark=100, qty=10, margin=40,
                   peak_roi_net_pct=40, held_seconds=59, config=cfg)
        self.assertEqual(d.action, "HOLD")
        self.assertEqual(d.reason, "minimum_hold")

    def test_invalid_data_and_config_rejected(self):
        cases = [
            dict(side=0), dict(margin=0), dict(mark=float("nan")),
            dict(funding_usdt=float("inf")), dict(open_fee_usdt=-1),
            dict(config=ProfitConfig(trail_drawdown_pct=float("nan"))),
            dict(config=ProfitConfig(fee_rate_side=float("inf"))),
        ]
        for changes in cases:
            params = dict(side=1, entry=100, mark=101, qty=10, margin=40,
                          peak_roi_net_pct=0, held_seconds=120)
            params.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                assess(**params)

    def test_decision_is_pure_and_does_not_change_peak_input(self):
        first = self.calc(mark=101, peak=0)
        second = self.calc(mark=100.9, peak=first.peak_roi_net_pct)
        self.assertEqual(first.peak_roi_net_pct, 25)
        self.assertEqual(second.peak_roi_net_pct, 25)


if __name__ == "__main__":
    unittest.main()
