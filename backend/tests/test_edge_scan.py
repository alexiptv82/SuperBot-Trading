"""Test delle parti pure di edge_scan (nessuna rete, nessun exchange)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import edge_scan as es  # noqa: E402


def flat_candles(n, price=100.0):
    return [[i * 60_000, price, price, price, price, 1.0] for i in range(n)]


def sig(side="long", i=10, price=100.0, atr=1.0, kind="scalp", strength=80, ts=0, symbol="BTC/USDT:USDT"):
    return {"symbol": symbol, "i": i, "ts": ts, "price": price, "atr": atr,
            "side": side, "trade_type": kind, "strength": strength}


def test_horizon_flat_market_costs_only_slippage():
    candles = flat_candles(200)
    j, gross = es.evaluate_signal(candles, sig(), "H30", slip=0.0002)
    assert j == 40
    # entrata +2 bp, uscita -2 bp su prezzo piatto: ~ -4 bp
    assert -4.2 < gross < -3.8


def test_horizon_long_and_short_are_symmetric():
    up = flat_candles(200)
    for k in range(11, 200):
        up[k] = [k * 60_000, 101, 101, 101, 101, 1.0]
    _, g_long = es.evaluate_signal(up, sig("long"), "H30", slip=0.0)
    _, g_short = es.evaluate_signal(up, sig("short"), "H30", slip=0.0)
    assert g_long > 99 and g_short < -99


def test_profile_take_profit_long():
    candles = flat_candles(200)
    # scalp P8: stop 8 x ATR = 8, TP = 12 sopra -> 112
    candles[15] = [15 * 60_000, 100, 113, 100, 112, 1.0]
    j, gross = es.evaluate_signal(candles, sig(), "P8", slip=0.0)
    assert j == 15
    assert abs(gross - 1200.0) < 1e-6   # +12% = 1200 bp


def test_profile_stop_short_has_negative_gross():
    candles = flat_candles(200)
    candles[20] = [20 * 60_000, 100, 109, 100, 108, 1.0]   # sale oltre lo stop (108)
    j, gross = es.evaluate_signal(candles, sig("short"), "P8", slip=0.0)
    assert j == 20
    assert gross < -700


def test_deoverlap_keeps_one_per_symbol_at_a_time():
    rows = [("A", 1, 10, 5.0), ("A", 3, 12, 6.0), ("A", 11, 15, 7.0), ("B", 2, 6, 8.0)]
    kept = es.deoverlap(rows)
    assert [(r[0], r[1]) for r in kept] == [("A", 1), ("A", 11), ("B", 2)]


def test_summarize_basic():
    rows = [("A", 1, 2, 20.0), ("A", 5, 6, 0.0), ("A", 9, 10, 10.0)]
    s = es.summarize(rows, 12.0)
    assert s["n"] == 3 and abs(s["mean"] - 10.0) < 1e-9
    assert abs(s["net"] + 2.0) < 1e-9
    assert abs(s["win_net"] - 100 / 3) < 1e-6
    assert es.summarize([], 12.0)["n"] == 0


def test_slices_cover_single_and_pair_dimensions():
    signals = [sig(strength=75, ts=5 * 3_600_000), sig("short", strength=95, kind="medium", ts=13 * 3_600_000,
                                                      symbol="XAU/USDT:USDT")]
    sl = es.build_slices(signals)
    assert sl[("tipo=scalp",)] == [0]
    assert sl[("simbolo=XAU",)] == [1]
    assert sl[("forza=f>=70",)] == [0, 1] and sl[("forza=f>=90",)] == [1]
    assert sl[("ora=h04-07",)] == [0] and sl[("ora=h12-15",)] == [1]
    assert sl[("tipo=medium", "lato=short")] == [1]
    assert ("tipo=scalp", "lato=short") not in sl


def test_gate_oos_selects_on_a_and_checks_on_b():
    # A: la fetta tipo=scalp ha media 30 bp (>= 12) con n sufficiente; B: -20 bp
    fee = 12.0
    a_stats = {("tipo=scalp",): {"n": 50, "mean": 30.0}, ("tipo=medium",): {"n": 50, "mean": 5.0}}
    b_rows = [("S", 1, 2, -20.0), ("S", 5, 6, -20.0)]
    b_slices = {("tipo=scalp",): [0, 1], ("tipo=medium",): []}
    g = es.gate_oos(a_stats, b_rows, b_slices, fee, k=1.0, min_n=40)
    assert g["chosen"] == 1 and g["confirmed"] == 0
    assert g["pooled"]["n"] == 2 and abs(g["pooled"]["mean"] + 20.0) < 1e-9
