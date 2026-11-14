"""Falco PAPER SHORT-only: isolated regression tests (no network, no bot startup)."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from desk.engine import PaperAccount


class FalcoShortOnlyTest(unittest.TestCase):
    def _open(self, side: int):
        acc = PaperAccount()
        stop = 98.0 if side == 1 else 102.0
        tp = 104.0 if side == 1 else 96.0
        return acc, acc.open("BTCUSDT", side, 100.0, 20, 100.0,
                             stop, tp, 1_000, {"BTCUSDT": 100.0},
                             source="claude", trade_type="medio")

    def test_falco_rejects_all_long_sources_at_account(self):
        with patch.dict(os.environ, {"DESK_PORTFOLIO": "hawk", "DESK_MODE": "paper"}):
            acc, (pos, reason) = self._open(1)
            self.assertIsNone(pos)
            self.assertEqual(reason, "falco_short_only")
            self.assertFalse(acc.positions)

    def test_falco_short_still_allowed(self):
        with patch.dict(os.environ, {"DESK_PORTFOLIO": "hawk", "DESK_MODE": "paper"}):
            acc, (pos, reason) = self._open(-1)
            self.assertIsNotNone(pos, reason)
            self.assertEqual(pos.side, -1)
            self.assertEqual(len(acc.positions), 1)

    def test_toro_long_unaffected(self):
        with patch.dict(os.environ, {"DESK_PORTFOLIO": "bull", "DESK_MODE": "paper"}):
            acc, (pos, reason) = self._open(1)
            self.assertIsNotNone(pos, reason)
            self.assertEqual(pos.side, 1)

    def test_s25_direct_long_path_blocked_for_falco(self):
        text = (Path(__file__).resolve().parents[1] / "desk" / "cli.py").read_text()
        check = 'PORTFOLIO.name != "hawk" and os.environ.get("DESK_LONG_S25") == "1"'
        self.assertEqual(text.count(check), 2)
        self.assertIn('base_act == "open_long"', text)
        self.assertIn('_candidate("falco_short_only"', text)


if __name__ == "__main__":
    unittest.main()
