"""Monitor guardrail tests; all inputs are synthetic temporary copies."""
import json
import tempfile
import unittest
from pathlib import Path
try:
    from backend.desk.profit_manager_monitor import check_output, run_once
    from backend.desk.profit_manager_replay import ShadowReplay
except ModuleNotFoundError:
    from profit_manager_monitor import check_output, run_once
    from profit_manager_replay import ShadowReplay


class MonitorTests(unittest.TestCase):
    def test_refuse_bot_data_output(self):
        with self.assertRaises(ValueError):
            check_output("/opt/superbot-desk-data/hawk", ["/tmp/hawk-copy.json"])

    def test_refuse_original_state_name(self):
        with self.assertRaises(ValueError):
            check_output("/tmp/monitor-output", ["/tmp/state_v2.json"])

    def test_fresh_copy_observed_once(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            copy = root / "hawk-copy.json"
            out = root / "output"
            out.mkdir()
            state = dict(main=dict(positions={"ETHUSDT": dict(
                id=1, symbol="ETHUSDT", side=1, entry=100, qty=10,
                total_margin=40, open_ms=1000, fee_open=0.6,
                legs=1, dca_count=0, dca_levels=[], pending_split=None)}),
                last_prices={"ETHUSDT": 101}, last_prices_ms=2000)
            copy.write_text(json.dumps(state))
            seen, replay = {}, ShadowReplay()
            first = run_once({"hawk": copy}, replay, seen, out, now_ms=2500)
            second = run_once({"hawk": copy}, replay, seen, out, now_ms=3000)
            self.assertEqual(first["observations"], 1)
            self.assertEqual(second["observations"], 0)
            self.assertEqual(len((out / "observations.jsonl").read_text().splitlines()), 1)

    def test_stale_price_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            copy = root / "hawk-copy.json"
            out = root / "output"
            out.mkdir()
            copy.write_text(json.dumps(dict(main=dict(positions={}),
                last_prices={}, last_prices_ms=1000)))
            result = run_once({"hawk": copy}, ShadowReplay(), {}, out, now_ms=999999)
            self.assertEqual(result["observations"], 0)


if __name__ == "__main__":
    unittest.main()
