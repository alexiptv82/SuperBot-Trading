"""Read-only state adapter tests; no exchange or VPS access."""
import unittest
try:
    from backend.desk.profit_manager_state_adapter import snapshots_from_state
except ModuleNotFoundError:
    from profit_manager_state_adapter import snapshots_from_state


class AdapterTests(unittest.TestCase):
    def state(self, **changes):
        p = dict(id=7, symbol="ETHUSDT", side=-1, entry=100, qty=10,
                 total_margin=50, open_ms=1000, fee_open=0.6, legs=1,
                 dca_count=0, dca_levels=[], pending_split=None)
        p.update(changes)
        return dict(main=dict(positions={"ETHUSDT": p}),
                    last_prices={"ETHUSDT": 99}, last_prices_ms=2000)

    def test_valid_paper_position(self):
        ticks, excluded = snapshots_from_state(self.state(), bot="hawk")
        self.assertEqual(len(ticks), 1)
        self.assertEqual(excluded, [])
        self.assertEqual(ticks[0].trade_id, "hawk:paper:7:1000:ETHUSDT")
        self.assertEqual(ticks[0].open_fee_usdt, 0.6)

    def test_dca_rejected(self):
        ticks, excluded = snapshots_from_state(self.state(dca_count=1), bot="bull")
        self.assertFalse(ticks)
        self.assertEqual(excluded[0]["reason"], "multi_leg_or_dca")

    def test_split_rejected(self):
        ticks, excluded = snapshots_from_state(self.state(legs=2), bot="hawk")
        self.assertFalse(ticks)
        self.assertEqual(excluded[0]["reason"], "multi_leg_or_dca")

    def test_missing_prices_rejected(self):
        s = self.state()
        s["last_prices"] = {}
        ticks, excluded = snapshots_from_state(s, bot="hawk")
        self.assertFalse(ticks)
        self.assertEqual(excluded[0]["reason"], "'ETHUSDT'")

    def test_no_paper_account_rejected(self):
        with self.assertRaises(ValueError):
            snapshots_from_state({}, bot="hawk")


if __name__ == "__main__":
    unittest.main()
