"""P9a — verifica indipendente (Claude): regole riscritte dal contratto con altre formule e altri parametri,
non-lookahead con indicatori VERI, compatibilita' con label_candidates (P5).

Gli indicatori (ATR, ADX) sono presi da `indicators` (gia' verificati in P7); le EMA, MACD, Bollinger, canale di
Donchian, i lati, il cooldown e le barriere sono ricalcolati qui da zero con `Fraction`/`Decimal` a 80 cifre.
"""
from __future__ import annotations

import random
from decimal import Decimal as D, localcontext
from fractions import Fraction as F

import pytest

from backend.v3.detectors import breakout as B
from backend.v3.detectors import common as C
from backend.v3.detectors import reversal as R
from backend.v3.detectors import trend as T
from backend.v3.features import indicators as I
from backend.v3.learning.opportunity import Candle, label_candidates

MS = 60_000
RISK = C.RiskSpec(9, D("1.2"), D("1.8"), 2)
BP = B.DonchianParams(13, 30)
BP_OFF = B.DonchianParams(8, None)
RP = R.BbMacdParams(17, D("1.7"), D("0.25"), D("0.75"), 8, 21, 5)
TP = T.EmaCrossParams(6, 15, 10, D("18"))
CASES = [
    ("S07", B.detect_donchian_breakout, BP),
    ("S07", B.detect_donchian_breakout, BP_OFF),
    ("S05", R.detect_bollinger_macd_reversal, RP),
    ("S02", T.detect_ema_cross_adx, TP),
]
IDS = ["S07-trend", "S07-plain", "S05", "S02"]
SEEDS = (3, 11, 2026)
N = 1200


def random_bars(seed, n=N):
    r = random.Random(seed)
    price, out = F(100), []
    for i in range(n):
        o = price
        c = price * (1 + F(r.randint(-60, 60), 10_000))
        hi = max(o, c) * (1 + F(r.randint(0, 40), 10_000))
        lo = min(o, c) * (1 - F(r.randint(0, 40), 10_000))
        with localcontext() as ctx:
            ctx.prec = 12
            ob, hb, lb, cb = (+(D(v.numerator) / D(v.denominator)) for v in (o, hi, lo, c))
        hb, lb = max(hb, ob, cb), min(lb, ob, cb)
        out.append(I.Bar(i * MS, ob, hb, lb, cb, D(1)))
        price = F(cb)
    return out


def ema_raw(values, n):
    """EMA con seme = primo valore (come indicators), in Fraction, senza i None iniziali."""
    alpha = F(2, n + 1)
    e, out = None, []
    for v in values:
        e = v if e is None else e + alpha * (v - e)
        out.append(e)
    return out


def ema_f(values, n):
    return [v if i >= n - 1 else None for i, v in enumerate(ema_raw(values, n))]


def sides_s07(bars, p):
    c = [F(b.close) for b in bars]
    te = None if p.trend_ema_n is None else ema_f(c, p.trend_ema_n)
    s = [0] * len(bars)
    for i in range(p.n, len(bars)):                       # canale delle n barre PRECEDENTI (i esclusa)
        hi = max(F(b.high) for b in bars[i - p.n:i])
        lo = min(F(b.low) for b in bars[i - p.n:i])
        side = 1 if c[i] > hi else (-1 if c[i] < lo else 0)
        if side and te is not None:
            if te[i] is None or (side == 1 and not c[i] > te[i]) or (side == -1 and not c[i] < te[i]):
                side = 0
        s[i] = side
    return s


def sides_s05(bars, p):
    c = [b.close for b in bars]
    cf = [F(x) for x in c]
    line_full = [a - b for a, b in zip(ema_raw(cf, p.macd_fast), ema_raw(cf, p.macd_slow))]
    sig_full = ema_raw(line_full, p.macd_signal)
    s = [0] * len(bars)
    with localcontext() as ctx:
        ctx.prec = 80
        for i in range(len(bars)):
            if i < p.bb_n - 1 or i < p.macd_slow + p.macd_signal - 2:
                continue
            w = c[i - p.bb_n + 1:i + 1]
            m = sum(w) / D(p.bb_n)
            sd = (sum((x - m) ** 2 for x in w) / D(p.bb_n)).sqrt()
            if sd == 0:
                continue
            pb = (c[i] - (m - p.bb_k * sd)) / (2 * p.bb_k * sd)
            line, hist = line_full[i], line_full[i] - sig_full[i]
            if pb < p.pb_low and hist > 0 and line < 0:
                s[i] = 1
            elif pb > p.pb_high and hist < 0 and line > 0:
                s[i] = -1
    return s


def sides_s02(bars, p):
    c = [F(b.close) for b in bars]
    ef, es = ema_f(c, p.fast_n), ema_f(c, p.slow_n)
    ax = I.adx(bars, p.adx_n, candle_ms=MS).adx
    s = [0] * len(bars)
    for i in range(1, len(bars)):
        if None in (ef[i - 1], es[i - 1], ef[i], es[i]) or ax[i] is None:
            continue
        if ef[i - 1] <= es[i - 1] and ef[i] > es[i] and ax[i] >= p.adx_min:
            s[i] = 1
        elif ef[i - 1] >= es[i - 1] and ef[i] < es[i] and ax[i] >= p.adx_min:
            s[i] = -1
    return s


SIDES = {B.DonchianParams: sides_s07, R.BbMacdParams: sides_s05, T.EmaCrossParams: sides_s02}


def expected(sid, symbol, bars, sides, risk):
    a = I.atr(bars, risk.atr_n, candle_ms=MS)
    out, last = [], None
    for i, side in enumerate(sides):
        if side == 0 or a[i] is None:
            continue
        if last is not None and i - last <= risk.cooldown_bars:
            continue
        entry, d = F(bars[i].close), F(risk.stop_atr_mult) * F(a[i])
        stop = entry - side * d
        target = entry + side * F(risk.target_r_mult) * d
        ok = (0 < stop < entry < target) if side == 1 else (0 < target < entry < stop)
        if not ok:
            continue
        t = bars[i].open_time_ms + MS
        out.append((f"{sid}:{symbol}:{t}:{'L' if side == 1 else 'S'}", side, t, entry, stop, target))
        last = i
    return out


def close_enough(x: D, y: F) -> bool:
    return abs(F(x) - y) <= F(1, 10 ** 45) * abs(y)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", range(len(CASES)), ids=IDS)
def test_rules_rewritten_from_the_contract_give_identical_candidates(case, seed):
    sid, fn, p = CASES[case]
    bars = random_bars(seed)
    got = fn("BTCUSDT", bars, p, RISK, candle_ms=MS)
    sides = SIDES[type(p)](bars, p)
    exp = expected(sid, "BTCUSDT", bars, sides, RISK)
    assert len(got) == len(exp)
    for g, e in zip(got, exp):
        assert (g.candidate_id, g.side, g.signal_time_ms) == e[:3]
        assert g.symbol == "BTCUSDT"
        assert close_enough(g.entry_price, e[3]) and close_enough(g.stop_price, e[4]) and close_enough(g.target_price, e[5])
    # guardie: il confronto non e' vuoto, copre entrambi i lati e il cooldown sopprime qualcosa
    assert sum(c.side == 1 for c in got) >= 3 and sum(c.side == -1 for c in got) >= 3, (sid, seed, len(got))
    nocool = expected(sid, "BTCUSDT", bars, sides, C.RiskSpec(9, D("1.2"), D("1.8"), 0))
    assert len(nocool) > len(exp)


@pytest.mark.parametrize("seed", SEEDS[:2])
@pytest.mark.parametrize("case", range(len(CASES)), ids=IDS)
def test_no_lookahead_with_real_indicators_truncation_invariance(case, seed):
    sid, fn, p = CASES[case]
    bars = random_bars(seed)
    full = fn("BTCUSDT", bars, p, RISK, candle_ms=MS)
    assert len(full) >= 6
    for m in (60, 137, 400, 777, 1013, N - 1):
        part = fn("BTCUSDT", bars[:m], p, RISK, candle_ms=MS)
        limit = bars[m - 1].open_time_ms + MS
        assert part == tuple(c for c in full if c.signal_time_ms <= limit), (sid, seed, m)


def test_truncation_test_would_catch_a_detector_that_looks_one_bar_ahead():
    """Meta-test: un rilevatore che per segnalare sulla barra i legge la barra i+1 NON e' invariante al troncamento."""
    bars = random_bars(3)

    def leaky_sides(prefix):
        s = sides_s07(prefix, BP_OFF)
        return [v if i + 1 < len(prefix) and prefix[i + 1].close != prefix[i].close else 0 for i, v in enumerate(s)]

    def honest_sides(prefix):
        return sides_s07(prefix, BP_OFF)

    for sides_fn, must_differ in ((leaky_sides, True), (honest_sides, False)):
        full = expected("S07", "BTCUSDT", bars, sides_fn(bars), RISK)
        assert len(full) >= 6
        m = full[3][2] // MS            # prefisso che termina esattamente sulla barra del 4o segnale
        part = expected("S07", "BTCUSDT", bars[:m], sides_fn(bars[:m]), RISK)
        keep = [e for e in full if e[2] <= bars[m - 1].open_time_ms + MS]
        assert (part != keep) is must_differ


@pytest.mark.parametrize("case", range(len(CASES)), ids=IDS)
def test_candidates_are_accepted_and_labelled_by_p5(case):
    sid, fn, p = CASES[case]
    bars = random_bars(11)
    cands = fn("BTCUSDT", bars, p, RISK, candle_ms=MS)
    assert cands
    candles = [Candle(b.open_time_ms, b.open, b.high, b.low, b.close) for b in bars]
    labels = label_candidates(cands, {"BTCUSDT": candles}, candle_ms=MS, horizons_ms=[5 * MS, 30 * MS],
                              cost_bp=D(5), ambiguous_policy="stop_first")
    assert len(labels) == len(cands)
    flat = [h for lab in labels for h in lab.horizons]
    assert any(h.status == "complete" for h in flat)
    assert any(h.barrier in ("target", "stop") for h in flat)


def test_symbols_with_dot_dash_underscore_and_max_length_make_valid_ids():
    bars = random_bars(3, 300)
    for sym in ("BTC_USDT.P", "A-B", "a" * 40):
        out = B.detect_donchian_breakout(sym, bars, BP_OFF, RISK, candle_ms=MS)
        assert out
        for c in out:
            assert c.symbol == sym and len(c.candidate_id) <= 128
