"""Offline report smoke tests. No external services."""
import json
import unittest
try:
    from backend.desk.profit_manager_report import analyze_lines
except ModuleNotFoundError:
    from profit_manager_report import analyze_lines


class ReportTests(unittest.TestCase):
    def test_empty_stream(self):
        r = analyze_lines([])
        self.assertEqual(r["snapshots_seen"], 0)
        self.assertFalse(r["profit_improvement_verified"])

    def test_bad_line_is_reported_without_fake_profit(self):
        r = analyze_lines(["not json"])
        self.assertEqual(r["snapshots_rejected"], 1)
        self.assertEqual(r["hypothetical_exits"], [])

    def test_valid_snapshots_counted(self):
        base = dict(trade_id="hawk:paper:100", open_ms=0, side=1,
                    entry=100, qty=10, allocated_margin=40)
        lines = [json.dumps(dict(base, timestamp_ms=1000, mark=102)),
                 json.dumps(dict(base, timestamp_ms=2000, mark=101))]
        r = analyze_lines(lines)
        self.assertEqual(r["snapshots_accepted"], 2)
        self.assertFalse(r["profit_improvement_verified"])


if __name__ == "__main__":
    unittest.main()
