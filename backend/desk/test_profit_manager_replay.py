"""Safety and counterfactual tests for offline shadow replay."""
import unittest
try:
    from backend.desk.profit_manager_shadow import ProfitConfig
    from backend.desk.profit_manager_replay import Snapshot, ShadowReplay
except ModuleNotFoundError:
    from profit_manager_shadow import ProfitConfig
    from profit_manager_replay import Snapshot, ShadowReplay


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.replay = ShadowReplay(ProfitConfig(activation_roi_pct=20, lock_roi_pct=5,
            trail_drawdown_pct=12, fee_rate_side=0, slip_rate_side=0, min_hold_seconds=0))

    def tick(self, ms, mark, **changes):
        fields = dict(trade_id="hawk:paper:1", timestamp_ms=ms, open_ms=0,
                      side=1, entry=100, mark=mark, qty=10, allocated_margin=40)
        fields.update(changes)
        return Snapshot(**fields)

    def test_exit_remains_terminal(self):
        self.assertEqual(self.replay.observe(self.tick(1000, 101)).action, "HOLD")
        exit_event = self.replay.observe(self.tick(2000, 100.5))
        self.assertEqual(exit_event.action, "SHADOW_EXIT")
        later = self.replay.observe(self.tick(3000, 105))
        self.assertEqual(later, exit_event)

    def test_out_of_order_or_duplicate_rejected(self):
        self.replay.observe(self.tick(1000, 101))
        for ms in (1000, 999):
            with self.assertRaises(ValueError):
                self.replay.observe(self.tick(ms, 100.8))

    def test_partial_or_dca_rejected_until_accounting_supported(self):
        self.replay.observe(self.tick(1000, 101))
        for change in (dict(qty=5), dict(entry=99), dict(allocated_margin=30)):
            with self.assertRaises(ValueError):
                self.replay.observe(self.tick(2000, 100.9, **change))

    def test_same_trade_id_other_bot_must_be_separate(self):
        self.replay.observe(self.tick(1000, 101))
        other = self.replay.observe(self.tick(1000, 99, trade_id="bull:paper:1", side=-1))
        self.assertEqual(other.action, "HOLD")

    def test_snapshot_before_open_rejected(self):
        with self.assertRaises(ValueError):
            self.replay.observe(self.tick(1000, 101, open_ms=2000))


if __name__ == "__main__":
    unittest.main()
