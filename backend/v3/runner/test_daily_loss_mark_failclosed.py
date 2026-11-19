"""Synthetic regression tests for Brain PAPER daily loss fail-closed pricing.

Does not contact an exchange, run a Brain, or read operational journals.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.v3.runner import daily_loss as loss_mod
from backend.v3.runner.runner import Runner


D = Decimal
NOW_MS = 1_800_000_000_000


def _summary(*, positions=()):
    return SimpleNamespace(open_positions=list(positions), closed_trades=[])


def _position(symbol, fill="100", qty="1", side=1):
    return SimpleNamespace(symbol=symbol, fill_price=D(fill), quantity=D(qty), side=side)


def _eval(*, positions, price_of):
    with patch.object(loss_mod, "build_summary", return_value=_summary(positions=positions)):
        return loss_mod.evaluate_daily_loss(
            journal=object(), portfolio_id="brain", run_id="brain-paper",
            initial_equity=D("2000"), now_ms=NOW_MS, price_of=price_of,
            warn_fraction=D("0.35"), halt_fraction=D("0.50"),
        )


class DailyLossMarkFailClosedTests(unittest.TestCase):
    def test_missing_second_quote_never_returns_partial_ok(self):
        positions = [_position("BTCUSDT"), _position("ETHUSDT")]
        seen = []

        def price_of(symbol, _ms):
            seen.append(symbol)
            if symbol == "BTCUSDT":
                return D("105")
            raise TimeoutError("private provider details must not leak")

        with self.assertRaisesRegex(ValueError, "^daily_loss_price_unavailable$"):
            _eval(positions=positions, price_of=price_of)
        self.assertEqual(seen, ["BTCUSDT", "ETHUSDT"])

    def test_non_finite_non_positive_and_non_decimal_marks_are_rejected(self):
        for bad in (None, 0, 100, D("NaN"), D("Infinity"), D("0"), D("-1")):
            with self.subTest(mark=repr(bad)):
                with self.assertRaisesRegex(ValueError, "^daily_loss_price_invalid$"):
                    _eval(positions=[_position("BTCUSDT")], price_of=lambda _s, _t: bad)

    def test_valid_quotes_preserve_existing_pnl_formula(self):
        quotes = {"BTCUSDT": D("90"), "ETHUSDT": D("110")}
        result = _eval(
            positions=[_position("BTCUSDT"), _position("ETHUSDT")],
            price_of=lambda s, _ms: quotes[s],
        )
        self.assertEqual(result.level, "ok")
        self.assertEqual(result.loss_usd, D("0"))
        self.assertEqual(result.loss_fraction, D("0"))

    def test_flat_wallet_does_not_require_prices(self):
        result = _eval(
            positions=[],
            price_of=lambda _s, _t: self.fail("no mark should be requested without open positions"),
        )
        self.assertEqual(result.level, "ok")

    def test_runner_halts_new_entries_on_missing_quote_without_stopping_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitored = []
            opened = []
            runner = Runner(
                run_id="brain-paper", data_dir=Path(tmp),
                run_monitor=lambda now: (monitored.append(now) or SimpleNamespace(errors=[])),
                run_cycle=lambda now, slot: opened.append((now, slot)),
                cycle_delay_ms=0,
                daily_loss=lambda _now: _eval(
                    positions=[_position("BTCUSDT")],
                    price_of=lambda _s, _t: (_ for _ in ()).throw(TimeoutError("no quote")),
                ),
            )
            result = runner.tick(NOW_MS)
            self.assertEqual(result.state, "halted")
            self.assertIn("halted:daily_loss_check_failed", result.last_error)
            self.assertEqual(monitored, [NOW_MS])  # exit monitoring still runs
            self.assertEqual(opened, [])          # no new entry cycles
            beat = json.loads((Path(tmp) / "heartbeat.json").read_text())
            self.assertEqual(beat["daily_loss_level"], "unknown")
            self.assertEqual(beat["state"], "halted")


    def test_stale_one_minute_quote_denies_complete_daily_loss_check(self):
        # The real feed's last_minute_close raises this code for a stale candle.
        with self.assertRaisesRegex(ValueError, "^daily_loss_price_unavailable$"):
            _eval(
                positions=[_position("BTCUSDT")],
                price_of=lambda _s, _t: (_ for _ in ()).throw(ValueError("stale_minute_bar")),
            )

    def test_daily_loss_warn_and_halt_boundaries_unchanged(self):
        position = _position("BTCUSDT", fill="1100")
        warn = _eval(positions=[position], price_of=lambda _s, _t: D("400"))
        halt = _eval(positions=[position], price_of=lambda _s, _t: D("100"))
        self.assertEqual((warn.level, warn.loss_fraction), ("warn", D("0.35")))
        self.assertEqual((halt.level, halt.loss_fraction), ("halt", D("0.50")))

    def test_sidecar_exit_owner_is_not_called_or_stopped_by_failed_daily_loss(self):
        # In sidecar mode exits belong to a separate process: runner must only
        # fail closed for entries, without taking ownership of exit monitoring.
        with tempfile.TemporaryDirectory() as tmp:
            opened, health_checks = [], []
            def exit_healthy(now):
                health_checks.append(now)
                return True

            runner = Runner(
                run_id="brain-paper", data_dir=Path(tmp), run_monitor=None,
                run_cycle=lambda now, slot: opened.append((now, slot)),
                cycle_delay_ms=0, exit_mode="sidecar",
                exit_healthy=exit_healthy, fresh_clock_ms=lambda: NOW_MS + 1_000,
                daily_loss=lambda _now: _eval(
                    positions=[_position("BTCUSDT")],
                    price_of=lambda _s, _t: (_ for _ in ()).throw(TimeoutError("no quote")),
                ),
            )
            result = runner.tick(NOW_MS)
            self.assertEqual(result.state, "halted")
            self.assertIn("halted:daily_loss_check_failed", result.last_error)
            self.assertEqual(health_checks, [NOW_MS])
            self.assertEqual(opened, [])
            self.assertIsNone(result.monitor)
            beat = json.loads((Path(tmp) / "heartbeat.json").read_text())
            self.assertEqual(beat["daily_loss_level"], "unknown")
            self.assertEqual(beat["state"], "halted")


if __name__ == "__main__":
    unittest.main()
