"""Offline tests of the study tools (download pagination, trade simulation). No network, no orders."""
import os
import sys

import numpy as np

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "deploy", "scripts")
sys.path.insert(0, SCRIPTS)

import fetch_bitget_futures_history as F  # noqa: E402
import backtest_toro_long_mirror_15m as B  # noqa: E402

STEP = 900_000
NOW = 1_794_550_000_000 - 1_794_550_000_000 % STEP


def _fake_bitget(first_ts, last_ts):
    """Like the real endpoint: newest `limit` candles whose CLOSE time is <= endTime, ascending."""
    calls = []

    def get(path, params, tries=4):
        calls.append(dict(params))
        end, lim = int(params["endTime"]), int(params["limit"])
        ts = [t for t in range(first_ts, last_ts + 1, STEP) if t + STEP <= end][-lim:]
        return [[str(t), "1", "2", "0.5", "1.5", "10", "15"] for t in ts]
    return get, calls


def test_pagination_keeps_every_candle(monkeypatch):
    first = NOW - 1000 * STEP
    get, calls = _fake_bitget(first, NOW)
    monkeypatch.setattr(F, "_get", get)
    monkeypatch.setattr(F.time, "sleep", lambda s: None)
    rows, n = F.fetch_candles("BTCUSDT", "15m", first, NOW + STEP - 1)
    ts = [int(r[0]) for r in rows]
    assert ts == list(range(first, NOW, STEP))          # the candle still open at NOW is excluded
    assert n == len(calls) >= 5


def test_trade_enters_on_next_open_and_stop_gaps_fill_at_the_open():
    a = np.array([[0, 100, 100.5, 99.5, 100, 1],
                  [STEP, 100, 100.4, 99.8, 100.2, 1],
                  [2 * STEP, 97, 97.5, 96, 97, 1]], dtype=float)
    tr = B.trade(a, 1, 0.01, (0.0, 0.0, 0.0))
    assert tr["why"] == "stop" and tr["exit"] == 2
    assert abs(tr["net"] - (97 / 100 - 1)) < 1e-12           # gap below the stop: filled at the open, not the stop


def test_trade_stop_has_priority_when_stop_and_target_share_a_candle():
    a = np.array([[0, 100, 100, 100, 100, 1], [STEP, 100, 103, 98, 100, 1]], dtype=float)
    tr = B.trade(a, 1, 0.01, (6.0, 2.0, 1.0))
    assert tr["why"] == "stop" and tr["net"] < -0.01


def test_costs_are_charged_on_both_sides_plus_funding():
    a = np.array([[0, 100, 100, 100, 100, 1]] + [[i * STEP, 100, 100.1, 99.9, 100, 1] for i in range(1, 200)],
                 dtype=float)
    tr = B.trade(a, 1, 0.01, (6.0, 2.0, 1.0))
    assert tr["why"] == "tempo" and tr["hours"] == 24.0
    entry, exit_ = 100 * 1.0002, 100 * 0.9998
    expected = exit_ / entry - 1 - 6e-4 * (1 + exit_ / entry) - 1e-4 * 24 / 8
    assert abs(tr["net"] - expected) < 1e-12
