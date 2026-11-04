"""F7 / P7 — indicatori a barre chiuse: verifica INDIPENDENTE (Claude) del modulo di Grok.

Perche' un secondo file di test: i test di Grok sono 8 controlli (un solo valore noto per
indicatore, troncamento provato solo su ``ema``, validazione di due codici, purezza che guarda solo
gli ``ImportFrom``) e il suo rapporto dichiara mutanti, oracolo e confronto col laboratorio NON
eseguiti. Qui:

* un ORACOLO scritto dal testo del contratto con algoritmi DIVERSI da quelli del modulo
  (forma chiusa con somme pesate invece della ricorsione, somme cumulative, ``math.isqrt`` per la
  radice, ``Fraction`` esatta) confronta OGNI valore di OGNI serie su dataset casuali validi, con
  guardie che dimostrano che i casi difficili (barre piatte, soli rialzi, soli ribassi, serie piatta,
  gap, serie piu' corta del periodo) ci sono davvero;
* vettori calcolati a parte con una ricorsione ``Fraction`` semplice (terza implementazione);
* invarianza al troncamento (nessun look-ahead) per TUTTE le funzioni, con un meta-test che prova
  che il controllo sa vedere un look-ahead vero;
* codici d'errore esatti e in ordine per ogni funzione, ogni caso cattivo differisce dal buono SOLO
  per il difetto provato e in piu' posizioni (non solo la prima barra); buchi in prima, centrale e
  ultima posizione;
* scale estreme (``numeric_out_of_range``), contesto Decimal ambientale, assenza di ``-0``,
  non-mutazione, proprieta' (RSI in [0,100], ADX in [0,100], ...), purezza (AST);
* confronto numerico col laboratorio del 9 ottobre (``backend/strategy_lab.py``) e con le formule
  pandas equivalenti, se numpy/pandas sono installati.
"""
from __future__ import annotations

import ast
import copy
import dataclasses
import decimal
import itertools
import math
import random
from decimal import ROUND_UP, Context, Decimal, InvalidOperation, getcontext, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from backend.v3.features import indicators as ind
from backend.v3.features.indicators import (
    Bar, adx, atr, bollinger, check_bars, donchian, ema, macd, rma, rsi, sma, true_range,
)

D = Decimal
CMS = 60_000
TOL = Fraction(1, 10**40)


# ============================================================ dati di prova
def _d(x) -> Decimal:
    return Decimal(str(x))


def make_bars(rng: random.Random, length: int, mode: str, t0: int = 0):
    """Barre VALIDE (low <= open,close <= high, prezzi > 0, contigue)."""
    bars = []
    prev_close = _d("100.00")
    for k in range(length):
        t = (t0 + k) * CMS
        if mode == "flat" or (mode == "flat_then_walk" and k < 4) or (mode == "walk_flats" and rng.random() < 0.3):
            o = h = lo = c = prev_close
        else:
            o = prev_close
            if mode in ("walk", "walk_flats", "flat_then_walk") and rng.random() < 0.3:
                o = max(_d("1.00"), prev_close + _d(rng.randint(-200, 200)) / 100)       # gap
            step = _d(rng.randint(1, 300)) / 100
            if mode == "up":
                c = o + step
            elif mode == "down":
                c = max(_d("0.50"), o - min(step, o - _d("0.50")))
            else:
                c = max(_d("0.50"), o + (step if rng.random() < 0.5 else -step))
            top, bot = max(o, c), min(o, c)
            h = top + _d(rng.randint(0, 150)) / 100
            lo = max(_d("0.01"), bot - _d(rng.randint(0, 150)) / 100)
            if mode == "up":
                lo = min(lo, bot)
        v = _d(rng.randint(0, 5000)) / 10
        bars.append(Bar(t, o, h, lo, c, v))
        prev_close = c
    return bars


MODES = ("walk", "up", "down", "flat", "flat_then_walk", "walk_flats")
LENGTHS = (1, 2, 3, 5, 8, 14, 25, 40, 60)
DATASETS = []
_rng = random.Random(20261104)
for _i, (_mode, _len) in enumerate(itertools.product(MODES, LENGTHS)):
    DATASETS.append((f"{_mode}-{_len}-{_i}", make_bars(_rng, _len, _mode, t0=_i)))
for _s in range(6):
    DATASETS.append((f"long-{_s}", make_bars(random.Random(900 + _s), 130, "walk_flats", t0=_s)))
PERIODS = (1, 2, 3, 5, 14, 20)
BB_K = (D("1"), D("2.5"))
MACD_SETS = ((2, 3, 2), (3, 5, 2), (5, 10, 4), (12, 26, 9))


def closes(bars):
    return [b.close for b in bars]


def test_generator_produces_valid_bars():
    """Lezione di P5: i dati casuali devono essere VALIDI secondo il contratto del modulo."""
    for name, bars in DATASETS:
        check_bars(bars, candle_ms=CMS)
        assert len(bars) >= 1, name


# ============================================================ oracolo (Fraction, algoritmi diversi)
def F(x, y=1) -> Fraction:
    return Fraction(x, y) if y != 1 else Fraction(x)


def closed_form(vals, alpha: Fraction):
    """e[0]=v0; e[i]=e[i-1]+alpha(v[i]-e[i-1])  ==  alpha*sum_{j<i}(1-alpha)^j v[i-j] + (1-alpha)^i v[0]."""
    beta = 1 - alpha
    pw = [Fraction(1)]
    for _ in range(len(vals)):
        pw.append(pw[-1] * beta)
    out = []
    for i in range(len(vals)):
        s = sum((pw[j] * vals[i - j] for j in range(i)), Fraction(0))
        out.append(alpha * s + pw[i] * vals[0])
    return out


def o_sma(vals, n):
    pre = [Fraction(0)]
    for v in vals:
        pre.append(pre[-1] + v)
    return [None if i < n - 1 else (pre[i + 1] - pre[i + 1 - n]) / n for i in range(len(vals))]


def o_ema(vals, n):
    e = closed_form(vals, Fraction(2, n + 1))
    return [None if i < n - 1 else e[i] for i in range(len(vals))]


def o_rma(vals, n):
    e = closed_form(vals, Fraction(1, n))
    return [None if i < n - 1 else e[i] for i in range(len(vals))]


def o_tr(bars):
    out = []
    for i, b in enumerate(bars):
        h, lo = F(b.high), F(b.low)
        if i == 0:
            out.append(h - lo)
        else:
            pc = F(bars[i - 1].close)
            out.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    return out


def o_atr(bars, n):
    return o_rma(o_tr(bars), n)


def o_rsi(bars, n):
    c = [F(b.close) for b in bars]
    out = [None] * len(bars)
    if len(bars) < 2:
        return out
    g = [max(c[i] - c[i - 1], 0) for i in range(1, len(c))]          # g[k] <-> indice k+1
    l = [max(c[i - 1] - c[i], 0) for i in range(1, len(c))]
    ag = closed_form([Fraction(x) for x in g], Fraction(1, n))
    al = closed_form([Fraction(x) for x in l], Fraction(1, n))
    for i in range(n, len(bars)):
        a, b = ag[i - 1], al[i - 1]
        if b == 0:
            out[i] = Fraction(50) if a == 0 else Fraction(100)
        else:
            out[i] = 100 - 100 / (1 + a / b)
    return out


def o_macd(bars, fast, slow, signal):
    c = [F(b.close) for b in bars]
    ef, es = closed_form(c, Fraction(2, fast + 1)), closed_form(c, Fraction(2, slow + 1))
    line = [a - b for a, b in zip(ef, es)]
    sig = closed_form(line, Fraction(2, signal + 1))
    hist = [a - b for a, b in zip(line, sig)]
    n = len(c)
    return (
        [None if i < slow - 1 else line[i] for i in range(n)],
        [None if i < slow + signal - 2 else sig[i] for i in range(n)],
        [None if i < slow + signal - 2 else hist[i] for i in range(n)],
    )


def o_sqrt(x: Fraction) -> Fraction:
    """sqrt con math.isqrt a scala RELATIVA: parte intera del risultato >= 10**40 (errore relativo <= 1e-40)."""
    if x == 0:
        return Fraction(0)
    d = len(str(x.numerator)) - len(str(x.denominator))            # ~ log10(x) entro +-1
    m = max(0, (82 - d + 1) // 2 + 1)
    return Fraction(math.isqrt(x.numerator * 10 ** (2 * m) // x.denominator), 10 ** m)


def o_boll(bars, n, k):
    c = [F(b.close) for b in bars]
    mid = o_sma(c, n)
    up, lo, pb, bw = [], [], [], []
    for i in range(len(c)):
        if mid[i] is None:
            up.append(None); lo.append(None); pb.append(None); bw.append(None)
            continue
        w = c[i - n + 1:i + 1]
        var = sum(((x - mid[i]) ** 2 for x in w), Fraction(0)) / n
        sd = o_sqrt(var)
        u, l_ = mid[i] + F(k) * sd, mid[i] - F(k) * sd
        up.append(u); lo.append(l_)
        pb.append(None if var == 0 else (c[i] - l_) / (u - l_))
        bw.append((u - l_) / mid[i])
    return mid, up, lo, pb, bw


def o_donchian(bars, n):
    hi = [None if i < n - 1 else max(F(b.high) for b in bars[i - n + 1:i + 1]) for i in range(len(bars))]
    lo = [None if i < n - 1 else min(F(b.low) for b in bars[i - n + 1:i + 1]) for i in range(len(bars))]
    return hi, lo


def o_adx(bars, n):
    N = len(bars)
    H, L = [F(b.high) for b in bars], [F(b.low) for b in bars]
    pdm, mdm = [Fraction(0)], [Fraction(0)]
    for i in range(1, N):
        up, dn = H[i] - H[i - 1], L[i - 1] - L[i]
        pdm.append(up if (up > dn and up > 0) else Fraction(0))
        mdm.append(dn if (dn > up and dn > 0) else Fraction(0))
    a = closed_form(o_tr(bars), Fraction(1, n))
    ps, ms = closed_form(pdm, Fraction(1, n)), closed_form(mdm, Fraction(1, n))
    pdi = [100 * ps[i] / a[i] if a[i] != 0 else Fraction(0) for i in range(N)]
    mdi = [100 * ms[i] / a[i] if a[i] != 0 else Fraction(0) for i in range(N)]
    dx = [100 * abs(pdi[i] - mdi[i]) / (pdi[i] + mdi[i]) if pdi[i] + mdi[i] > 0 else Fraction(0) for i in range(N)]
    ad = closed_form(dx, Fraction(1, n))
    return (
        [None if i < n - 1 else pdi[i] for i in range(N)],
        [None if i < n - 1 else mdi[i] for i in range(N)],
        [None if i < 2 * n - 2 else ad[i] for i in range(N)],
    )


# ============================================================ confronto
def assert_same(got, want, ctx, tol=TOL):
    assert len(got) == len(want), (ctx, len(got), len(want))
    for i, (g, w) in enumerate(zip(got, want)):
        if w is None:
            assert g is None, (ctx, i, "atteso None", g)
        else:
            assert g is not None, (ctx, i, "atteso valore", w)
            assert type(g) is Decimal, (ctx, i, type(g))
            assert abs(Fraction(g) - w) <= tol * max(1, abs(w)), (ctx, i, g, float(w))


def no_negative_zero(series, ctx):
    for i, v in enumerate(series):
        if v is not None:
            assert not (v == 0 and v.is_signed()), (ctx, i, "zero negativo")


# ============================================================ vettori calcolati a parte
def bars_from_ohlc(rows, t0=0):
    return [Bar((t0 + k) * CMS, _d(o), _d(h), _d(l), _d(c), D(1)) for k, (o, h, l, c) in enumerate(rows)]


class TestHandVectors:
    def test_sma_ema_rma_anchors(self):
        v = [D(10), D(12), D(11), D(15)]
        assert sma(v, 2) == (None, D(11), D("11.5"), D(13))
        assert ema(v, 3) == (None, None, D(11), D(13))
        assert rma(v, 2) == (None, D(11), D(11), D(13))
        assert ema(v, 1) == tuple(v)                                   # alpha = 1
        assert rma(v, 1) == tuple(v)
        assert sma(v, 5) == (None,) * 4 and ema(v, 5) == (None,) * 4   # serie piu' corta del periodo
        assert sma([], 3) == () and ema([], 3) == () and rma([], 3) == ()
        assert ema([D(8)], 1) == (D(8),)
        assert ema([D(10), D(20)], 4) == (None, None)

    def test_ema_n4_exact(self):
        # e0=10; e1=10+0.4*10=14 ; e2=14+0.4*16=20.4 ; e3=20.4+0.4*19.6=28.24
        assert ema([D(10), D(20), D(30), D(40)], 4) == (None, None, None, D("28.24"))
        # n=9, alpha=0.2 : 10 -> 10+0.2*(20-10)=12 -> 12+0.2*(30-12)=15.6
        # n=9, alpha=1/5, serie costante 30 dopo 10,20: e0=10 e1=12 e2=15.6 e3=18.48 ...
        got = ema([D(10), D(20), D(30)] + [D(30)] * 6, 9)
        e = [F(10)]
        for v in [20, 30] + [30] * 6:
            e.append(e[-1] + F(1, 5) * (v - e[-1]))
        assert got[:8] == (None,) * 8 and abs(Fraction(got[8]) - e[8]) <= TOL * 100

    def test_true_range(self):
        bars = bars_from_ohlc([(10, 12, 9, 11), (15, 16, 14, 15), (15, 15, 15, 15), (13, 14, 12, 13)])
        # tr0 = 3 ; tr1 = max(2, |16-11|, |14-11|) = 5 ; tr2 = max(0, |15-15|, |15-15|) = 0 ; tr3 = max(2, |14-15|, |12-15|) = 3
        assert true_range(bars, candle_ms=CMS) == (D(3), D(5), D(0), D(3))
        assert all(type(x) is Decimal for x in true_range(bars, candle_ms=CMS))

    def test_atr_is_rma_of_tr(self):
        bars = bars_from_ohlc([(10, 12, 9, 11), (15, 16, 14, 15), (15, 15, 15, 15), (13, 14, 12, 13)])
        # n=2: alpha 1/2 : r0=3, r1=4, r2=2, r3=2.5
        assert atr(bars, 2, candle_ms=CMS) == (None, D(4), D(2), D("2.5"))

    def test_rsi_vectors(self):
        bars = bars_from_ohlc([(10, 11, 9, 10), (10, 12, 10, 11), (11, 12, 9, 10), (10, 13, 10, 12)])
        r = rsi(bars, 2, candle_ms=CMS)
        assert r[:2] == (None, None) and r[2] == D(50)
        assert abs(Fraction(r[3]) - Fraction(250, 3)) <= TOL * 100
        up = bars_from_ohlc([(1, 2, 1, 2), (2, 3, 2, 3), (3, 4, 3, 4), (4, 5, 4, 5)])
        assert rsi(up, 2, candle_ms=CMS) == (None, None, D(100), D(100))     # avg_loss = 0, avg_gain > 0
        down = bars_from_ohlc([(5, 5, 4, 4), (4, 4, 3, 3), (3, 3, 2, 2), (2, 2, 1, 1)])
        assert rsi(down, 2, candle_ms=CMS) == (None, None, D(0), D(0))
        flat = bars_from_ohlc([(5, 5, 5, 5)] * 4)
        assert rsi(flat, 2, candle_ms=CMS) == (None, None, D(50), D(50))      # avg_loss = 0 e avg_gain = 0
        assert rsi(flat[:2], 2, candle_ms=CMS) == (None, None)
        assert rsi(flat[:1], 1, candle_ms=CMS) == (None,)
        assert rsi(flat, 1, candle_ms=CMS) == (None, D(50), D(50), D(50))

    def test_macd_vectors(self):
        bars = bars_from_ohlc([(c, c, c, c) for c in (10, 12, 11, 15, 14, 18, 16)])
        m = macd(bars, 2, 3, 2, candle_ms=CMS)
        want_line = [None, None, F(1, 9), F(19, 27), F(65, 162), F(859, 972), F(1961, 5832)]
        want_sig = [None, None, None, F(14, 27), F(107, 243), F(1073, 1458), F(1369, 2916)]
        want_hist = [None, None, None, F(5, 27), F(-19, 486), F(431, 2916), F(-259, 1944)]
        assert_same(m.line, want_line, "line")
        assert_same(m.signal, want_sig, "signal")
        assert_same(m.hist, want_hist, "hist")
        assert type(m) is ind.MacdSeries

    def test_bollinger_vectors(self):
        bars = bars_from_ohlc([(1, 1, 1, 1), (3, 3, 3, 3)])
        b = bollinger(bars, 2, D(1), candle_ms=CMS)
        assert b.mid == (None, D(2)) and b.upper == (None, D(3)) and b.lower == (None, D(1))
        assert b.percent_b == (None, D(1)) and b.bandwidth == (None, D(1))
        flat = bars_from_ohlc([(5, 5, 5, 5)] * 3)
        f = bollinger(flat, 2, D("2.5"), candle_ms=CMS)
        assert f.percent_b == (None, None, None) and f.bandwidth == (None, D(0), D(0))
        assert f.upper == (None, D(5), D(5)) and f.lower == (None, D(5), D(5))
        # popolazione, non campione: [2, 4, 6, 4] n=4 -> mid 4, var = (4+0+4+0)/4 = 2
        pop = bars_from_ohlc([(c, c, c, c) for c in (2, 4, 6, 4)])
        p = bollinger(pop, 4, D(1), candle_ms=CMS)
        sd = (Fraction(p.upper[3]) - 4)
        assert abs(sd * sd - 2) <= Fraction(1, 10**50)

    def test_donchian_vectors(self):
        bars = bars_from_ohlc([(10, 12, 9, 11), (11, 15, 10, 14), (14, 14, 8, 9), (9, 11, 9, 10)])
        d = donchian(bars, 2, candle_ms=CMS)
        assert d.high == (None, D(15), D(15), D(14)) and d.low == (None, D(9), D(8), D(8))
        d1 = donchian(bars, 1, candle_ms=CMS)
        assert d1.high == (D(12), D(15), D(14), D(11)) and d1.low == (D(9), D(10), D(8), D(9))
        assert donchian(bars, 5, candle_ms=CMS).high == (None,) * 4

    def test_adx_vectors(self):
        bars = bars_from_ohlc([(10, 12, 9, 11), (11, 13, 10, 12), (12, 12, 8, 9), (9, 10, 9, 10),
                               (10, 10, 10, 10), (10, 14, 10, 14)])
        a = adx(bars, 2, candle_ms=CMS)
        assert_same(a.plus_di, [None, F(50, 3), F(50, 7), F(50, 9), F(50, 9), F(3250, 41)], "pdi")
        assert_same(a.minus_di, [None, F(0), F(200, 7), F(200, 9), F(200, 9), F(200, 41)], "mdi")
        assert_same(a.adx, [None, None, F(55), F(115, 2), F(235, 4), F(40615, 552)], "adx")
        assert type(a) is ind.AdxSeries

    def test_adx_flat_start_division_by_zero_branch(self):
        bars = bars_from_ohlc([(10, 10, 10, 10)] * 3 + [(10, 11, 10, 11), (11, 13, 11, 12)])
        a = adx(bars, 2, candle_ms=CMS)
        assert_same(a.plus_di, [None, F(0), F(0), F(100), F(100)], "pdi")
        assert_same(a.adx, [None, None, F(0), F(50), F(75)], "adx")


# ============================================================ contro l'oracolo
class TestAgainstOracle:
    def test_sma_ema_rma(self):
        seen_short = 0
        for name, bars in DATASETS:
            vals = closes(bars)
            fv = [F(v) for v in vals]
            for n in PERIODS:
                seen_short += n > len(vals)
                assert_same(sma(vals, n), o_sma(fv, n), (name, "sma", n))
                assert_same(ema(vals, n), o_ema(fv, n), (name, "ema", n))
                assert_same(rma(vals, n), o_rma(fv, n), (name, "rma", n))
                for fn in (sma, ema, rma):
                    no_negative_zero(fn(vals, n), (name, fn.__name__, n))
        assert seen_short > 20                                     # guardia: serie piu' corta del periodo

    def test_negative_and_mixed_sign_values(self):
        rng = random.Random(7)
        vals = [D(rng.randint(-5000, 5000)) / 100 for _ in range(40)]
        fv = [F(v) for v in vals]
        for n in PERIODS:
            assert_same(sma(vals, n), o_sma(fv, n), ("sma-neg", n))
            assert_same(ema(vals, n), o_ema(fv, n), ("ema-neg", n))
            assert_same(rma(vals, n), o_rma(fv, n), ("rma-neg", n))

    def test_true_range_and_atr(self):
        for name, bars in DATASETS:
            tr = true_range(bars, candle_ms=CMS)
            assert tuple(tr) == tuple(tr) and len(tr) == len(bars)
            assert_same(tr, o_tr(bars), (name, "tr"))
            for n in PERIODS:
                assert_same(atr(bars, n, candle_ms=CMS), o_atr(bars, n), (name, "atr", n))

    def test_rsi(self):
        stats = {"r100": 0, "r50": 0, "r0": 0, "short": 0}
        for name, bars in DATASETS:
            for n in PERIODS:
                got = rsi(bars, n, candle_ms=CMS)
                want = o_rsi(bars, n)
                assert_same(got, want, (name, "rsi", n))
                no_negative_zero(got, (name, "rsi", n))
                for w in want:
                    if w is not None:
                        stats["r100"] += w == 100
                        stats["r50"] += w == 50
                        stats["r0"] += w == 0
                stats["short"] += n >= len(bars)
        assert stats["r100"] > 10 and stats["r50"] > 10 and stats["r0"] > 10 and stats["short"] > 10, stats

    def test_macd(self):
        for name, bars in DATASETS:
            for fast, slow, signal in MACD_SETS:
                got = macd(bars, fast, slow, signal, candle_ms=CMS)
                line, sig, hist = o_macd(bars, fast, slow, signal)
                ctx = (name, "macd", fast, slow, signal)
                assert_same(got.line, line, ctx + ("line",))
                assert_same(got.signal, sig, ctx + ("signal",))
                assert_same(got.hist, hist, ctx + ("hist",))
                for i in range(len(bars)):                         # hist = line - signal (nelle posizioni definite)
                    if got.hist[i] is not None:
                        diff = Fraction(got.line[i]) - Fraction(got.signal[i])
                        assert abs(Fraction(got.hist[i]) - diff) <= Fraction(1, 10**55), ctx

    def test_bollinger(self):
        stats = {"pb_none": 0, "pb_val": 0}
        for name, bars in DATASETS:
            for n in (2, 3, 5, 14, 20):
                for k in BB_K:
                    got = bollinger(bars, n, k, candle_ms=CMS)
                    mid, up, lo, pb, bw = o_boll(bars, n, k)
                    ctx = (name, "boll", n, k)
                    tol = Fraction(1, 10**30)
                    assert_same(got.mid, mid, ctx + ("mid",), tol)
                    assert_same(got.upper, up, ctx + ("upper",), tol)
                    assert_same(got.lower, lo, ctx + ("lower",), tol)
                    assert_same(got.percent_b, pb, ctx + ("%B",), tol)
                    assert_same(got.bandwidth, bw, ctx + ("bw",), tol)
                    for w in pb:
                        stats["pb_none"] += w is None
                        stats["pb_val"] += w is not None
        assert stats["pb_none"] > 50 and stats["pb_val"] > 500, stats    # guardia: %B None (serie piatte) e valori

    def test_donchian(self):
        for name, bars in DATASETS:
            for n in PERIODS:
                got = donchian(bars, n, candle_ms=CMS)
                hi, lo = o_donchian(bars, n)
                assert_same(got.high, hi, (name, "don-high", n))
                assert_same(got.low, lo, (name, "don-low", n))
                for h, l in zip(got.high, got.low):
                    if h is not None:
                        assert l <= h

    def test_adx(self):
        stats = {"a0": 0}
        for name, bars in DATASETS:
            for n in PERIODS:
                got = adx(bars, n, candle_ms=CMS)
                pdi, mdi, ad = o_adx(bars, n)
                ctx = (name, "adx", n)
                assert_same(got.plus_di, pdi, ctx + ("pdi",))
                assert_same(got.minus_di, mdi, ctx + ("mdi",))
                assert_same(got.adx, ad, ctx + ("adx",))
                stats["a0"] += sum(1 for a in ad if a == 0)
        assert stats["a0"] > 20, stats                              # guardia: ramo a==0 / dx==0 esercitato

    def test_dataset_guards(self):
        """I dataset contengono davvero i casi difficili."""
        flat_bars = sum(1 for _, bs in DATASETS for b in bs if b.high == b.low == b.open == b.close)
        gaps = sum(1 for _, bs in DATASETS for i in range(1, len(bs)) if bs[i].open != bs[i - 1].close)
        assert flat_bars > 100 and gaps > 100
        assert any(all(bs[i].close > bs[i - 1].close for i in range(1, len(bs))) and len(bs) > 5 for _, bs in DATASETS)
        assert any(all(bs[i].close < bs[i - 1].close for i in range(1, len(bs))) and len(bs) > 5 for _, bs in DATASETS)
        assert any(len(bs) < 3 for _, bs in DATASETS)


# ============================================================ proprieta'
class TestProperties:
    def test_ranges_and_lengths(self):
        for name, bars in DATASETS:
            n = 5
            for series in (ema(closes(bars), n), rma(closes(bars), n), sma(closes(bars), n),
                           atr(bars, n, candle_ms=CMS), rsi(bars, n, candle_ms=CMS)):
                assert len(series) == len(bars)
            for v in rsi(bars, n, candle_ms=CMS):
                assert v is None or 0 <= v <= 100
            a = adx(bars, n, candle_ms=CMS)
            for i in range(len(bars)):
                p, m, x = a.plus_di[i], a.minus_di[i], a.adx[i]
                if p is not None:
                    assert 0 <= p and 0 <= m and p + m <= 100 + D("1E-40"), (name, i)
                if x is not None:
                    assert 0 <= x <= 100 + D("1E-40"), (name, i)
            b = bollinger(bars, 3, D(2), candle_ms=CMS)
            for i in range(len(bars)):
                if b.mid[i] is not None:
                    assert b.lower[i] <= b.mid[i] <= b.upper[i]
            assert len(true_range(bars, candle_ms=CMS)) == len(bars)
            assert all(x >= 0 for x in true_range(bars, candle_ms=CMS))

    def test_no_negative_zero_anywhere(self):
        for name, bars in DATASETS:
            for n in (2, 5):
                for s in (*macd(bars, 2, 3, n, candle_ms=CMS).__dict__.values(),
                          *bollinger(bars, n, D(2), candle_ms=CMS).__dict__.values(),
                          *donchian(bars, n, candle_ms=CMS).__dict__.values(),
                          *adx(bars, n, candle_ms=CMS).__dict__.values(),
                          true_range(bars, candle_ms=CMS), atr(bars, n, candle_ms=CMS)):
                    no_negative_zero(s, (name, n))

    def test_inputs_are_not_mutated_and_deterministic(self):
        name, bars = DATASETS[40]
        lst = list(bars)
        snap = copy.deepcopy(lst)
        vals = closes(bars)
        vsnap = list(vals)
        a = (adx(lst, 3, candle_ms=CMS), rsi(lst, 3, candle_ms=CMS), ema(vals, 3))
        assert lst == snap and vals == vsnap
        assert (adx(lst, 3, candle_ms=CMS), rsi(lst, 3, candle_ms=CMS), ema(vals, 3)) == a
        assert (adx(tuple(lst), 3, candle_ms=CMS), rsi(tuple(lst), 3, candle_ms=CMS), ema(tuple(vals), 3)) == a   # tuple = lista

    def test_context_independence(self):
        name, bars = DATASETS[-1]
        vals = closes(bars)

        def everything():
            return (
                sma(vals, 5), ema(vals, 5), rma(vals, 5), true_range(bars, candle_ms=CMS),
                atr(bars, 5, candle_ms=CMS), rsi(bars, 5, candle_ms=CMS),
                macd(bars, 5, 10, 4, candle_ms=CMS), bollinger(bars, 5, D("2.5"), candle_ms=CMS),
                donchian(bars, 5, candle_ms=CMS), adx(bars, 5, candle_ms=CMS),
            )
        base = everything()
        with localcontext() as c:
            c.prec = 5
            c.rounding = ROUND_UP
            assert everything() == base
        with localcontext() as c:
            c.prec = 200
            c.traps[InvalidOperation] = False
            assert everything() == base
        assert getcontext().prec == 28                              # il contesto del chiamante non e' toccato


# ============================================================ troncamento (nessun look-ahead)
CALLS = {
    "sma": lambda bars: sma(closes(bars), 5),
    "ema": lambda bars: ema(closes(bars), 5),
    "rma": lambda bars: rma(closes(bars), 5),
    "true_range": lambda bars: true_range(bars, candle_ms=CMS),
    "atr": lambda bars: atr(bars, 5, candle_ms=CMS),
    "rsi": lambda bars: rsi(bars, 5, candle_ms=CMS),
    "macd.line": lambda bars: macd(bars, 3, 6, 3, candle_ms=CMS).line,
    "macd.signal": lambda bars: macd(bars, 3, 6, 3, candle_ms=CMS).signal,
    "macd.hist": lambda bars: macd(bars, 3, 6, 3, candle_ms=CMS).hist,
    "boll.mid": lambda bars: bollinger(bars, 5, D(2), candle_ms=CMS).mid,
    "boll.upper": lambda bars: bollinger(bars, 5, D(2), candle_ms=CMS).upper,
    "boll.lower": lambda bars: bollinger(bars, 5, D(2), candle_ms=CMS).lower,
    "boll.percent_b": lambda bars: bollinger(bars, 5, D(2), candle_ms=CMS).percent_b,
    "boll.bandwidth": lambda bars: bollinger(bars, 5, D(2), candle_ms=CMS).bandwidth,
    "don.high": lambda bars: donchian(bars, 5, candle_ms=CMS).high,
    "don.low": lambda bars: donchian(bars, 5, candle_ms=CMS).low,
    "adx.plus_di": lambda bars: adx(bars, 5, candle_ms=CMS).plus_di,
    "adx.minus_di": lambda bars: adx(bars, 5, candle_ms=CMS).minus_di,
    "adx.adx": lambda bars: adx(bars, 5, candle_ms=CMS).adx,
}


def prefix_violations(fn, bars):
    """Posizioni m per cui fn(bars[:m]) != fn(bars)[:m] (uguaglianza esatta, None compresi)."""
    full = tuple(fn(bars))
    return [m for m in range(len(bars) + 1) if tuple(fn(bars[:m])) != full[:m]]


class TestNoLookahead:
    @pytest.mark.parametrize("name", list(CALLS))
    def test_truncation_invariance(self, name):
        for ds_name, bars in DATASETS[::4] + DATASETS[-3:]:
            assert prefix_violations(CALLS[name], bars) == [], (name, ds_name)

    def test_the_check_can_see_a_real_lookahead(self):
        """Meta-test: lo stesso controllo DEVE vedere una media centrata e un massimo che guarda avanti."""
        def centered_sma(bars):
            v = closes(bars)
            return tuple(None if i < 1 or i + 1 >= len(v) else (v[i - 1] + v[i] + v[i + 1]) / 3 for i in range(len(v)))

        def peeking_max(bars):
            return tuple(bars[min(i + 1, len(bars) - 1)].high for i in range(len(bars)))

        def last_value_normalised(bars):               # dipende dall'ultimo dato della serie intera
            v = closes(bars)
            return tuple(x / v[-1] for x in v) if v else ()
        bars = next(b for n, b in DATASETS if n.startswith("walk-60"))
        assert len({x.high for x in bars}) > 20 and len({x.close for x in bars}) > 20     # guardia: non piatto
        assert prefix_violations(centered_sma, bars) != []
        assert prefix_violations(peeking_max, bars) != []
        assert prefix_violations(last_value_normalised, bars) != []

    def test_changing_the_future_does_not_change_the_past(self):
        _, bars = DATASETS[50]
        for cut in (5, 20, 35):
            altered = list(bars[:cut]) + make_bars(random.Random(cut), len(bars) - cut, "walk", t0=0)[:0]
            tail = [dataclasses.replace(b, close=b.close, high=b.high + 5) for b in bars[cut:]]
            altered = list(bars[:cut]) + tail
            for name, fn in CALLS.items():
                assert tuple(fn(altered))[:cut] == tuple(fn(bars))[:cut], (name, cut)


# ============================================================ validazione
def good_bars(n=8, t0=3):
    return make_bars(random.Random(5), n, "walk", t0=t0)


def with_bar(bars, pos, **over):
    out = list(bars)
    out[pos] = dataclasses.replace(out[pos], **over)
    return out


def positions(n):
    return (0, n // 2, n - 1)


BAR_CALLERS = {
    "check_bars": lambda b, **kw: check_bars(b, candle_ms=kw.get("candle_ms", CMS)),
    "true_range": lambda b, **kw: true_range(b, candle_ms=kw.get("candle_ms", CMS)),
    "atr": lambda b, **kw: atr(b, kw.get("n", 3), candle_ms=kw.get("candle_ms", CMS)),
    "rsi": lambda b, **kw: rsi(b, kw.get("n", 3), candle_ms=kw.get("candle_ms", CMS)),
    "macd": lambda b, **kw: macd(b, kw.get("fast", 2), kw.get("slow", 4), kw.get("signal", 2), candle_ms=kw.get("candle_ms", CMS)),
    "bollinger": lambda b, **kw: bollinger(b, kw.get("n", 3), kw.get("k", D(2)), candle_ms=kw.get("candle_ms", CMS)),
    "donchian": lambda b, **kw: donchian(b, kw.get("n", 3), candle_ms=kw.get("candle_ms", CMS)),
    "adx": lambda b, **kw: adx(b, kw.get("n", 3), candle_ms=kw.get("candle_ms", CMS)),
}


def expect(code, fn, *a, **k):
    with pytest.raises(ValueError) as e:
        fn(*a, **k)
    assert str(e.value) == code, (str(e.value), code)


class TestValidationBars:
    @pytest.mark.parametrize("name", list(BAR_CALLERS))
    def test_control_is_valid(self, name):
        BAR_CALLERS[name](good_bars())
        BAR_CALLERS[name]([])                                         # vuota: ammessa
        BAR_CALLERS[name](good_bars(1))

    @pytest.mark.parametrize("name", list(BAR_CALLERS))
    def test_empty_returns_empty_series(self, name):
        r = BAR_CALLERS[name]([])
        if r is not None:
            vals = list(r.__dict__.values()) if dataclasses.is_dataclass(r) else [r]
            assert all(v == () for v in vals)

    @pytest.mark.parametrize("name", list(BAR_CALLERS))
    @pytest.mark.parametrize("bad", [None, "abc", b"abc", 5, {1}, {"a": 1}, (x for x in range(3)), iter([])])
    def test_bars_must_be_a_real_sequence(self, name, bad):
        expect("invalid_bars", BAR_CALLERS[name], bad)

    def test_generator_of_valid_bars_is_refused_not_consumed(self):
        gen = (b for b in good_bars())
        expect("invalid_bars", true_range, gen, candle_ms=CMS)
        assert next(gen) is not None                                  # non consumato dalla validazione

    @pytest.mark.parametrize("name", list(BAR_CALLERS))
    def test_element_must_be_exactly_a_bar(self, name):
        class SubBar(Bar):
            pass
        base = good_bars()
        for pos in positions(len(base)):
            for bad in (None, 5, "x", (0, 1, 2, 3, 4, 5), dataclasses.asdict(base[pos]), SubBar(**base[pos].__dict__)):
                b = list(base); b[pos] = bad
                expect("invalid_bars", BAR_CALLERS[name], b)

    @pytest.mark.parametrize("name", list(BAR_CALLERS))
    def test_field_defects_each_alone_at_three_positions(self, name):
        base = good_bars()
        ref = base[0]
        cases = {
            "open_time bool": {"open_time_ms": True},
            "open_time float": {"open_time_ms": 60000.0},
            "open_time negative": {"open_time_ms": -CMS},
            "open_time not multiple": None,                                  # costruito per posizione
            "open float": {"open": 100.5},
            "high float": {"high": 100.5},
            "low float": {"low": 100.5},
            "close float": {"close": 100.5},
            "volume float": {"volume": 1.5},
            "volume str": {"volume": "1"},
            "open nan": {"open": D("NaN")},
            "close inf": {"close": D("Infinity")},
            "high -inf": {"high": D("-Infinity")},
            "low snan": {"low": D("sNaN")},
            "volume nan": {"volume": D("NaN")},
            "open zero": {"open": D(0)},
            "close negative": {"close": D("-1")},
            "low zero": {"low": D(0)},
            "volume negative": {"volume": D("-0.1")},
            "low above high": {"low": ref.high + 1},
            "open above high": {"open": ref.high + 1},
            "open below low": {"open": ref.low - D("0.001")},
            "close above high": {"close": ref.high + D("0.001")},
            "close below low": {"close": ref.low - D("0.001")},
            "open None": {"open": None},
            "volume None": {"volume": None},
        }
        for label, over in cases.items():
            for pos in positions(len(base)):
                if label == "open_time not multiple":
                    over_p = {"open_time_ms": base[pos].open_time_ms + 1}
                else:
                    over_p = over
                if "open" in over_p and isinstance(over_p["open"], Decimal) and over_p["open"] == ref.high + 1:
                    over_p = {"open": base[pos].high + 1}
                if label == "low above high":
                    over_p = {"low": base[pos].high + 1}
                if label == "open below low":
                    over_p = {"open": base[pos].low - D("0.001")}
                if label == "close above high":
                    over_p = {"close": base[pos].high + D("0.001")}
                if label == "close below low":
                    over_p = {"close": base[pos].low - D("0.001")}
                b = list(base)
                b[pos] = Bar(**{**base[pos].__dict__, **over_p})
                expect("invalid_bars", BAR_CALLERS[name], b)

    @pytest.mark.parametrize("name", list(BAR_CALLERS))
    def test_gaps_and_ordering_defects(self, name):
        base = good_bars(9)
        for k in (1, 4, 7):                                           # prima, centrale, ultima giuntura
            gap = base[:k] + base[k + 1:]
            expect("invalid_bars", BAR_CALLERS[name], gap)            # barra mancante = buco
            dup = list(base); dup[k] = dataclasses.replace(dup[k], open_time_ms=dup[k - 1].open_time_ms)
            expect("invalid_bars", BAR_CALLERS[name], dup)            # tempo ripetuto
            back = list(base); back[k], back[k - 1] = back[k - 1], back[k]
            expect("invalid_bars", BAR_CALLERS[name], back)           # non crescente
        shifted = [dataclasses.replace(b, open_time_ms=b.open_time_ms + 1) for b in base]
        expect("invalid_bars", BAR_CALLERS[name], shifted)            # tutte non allineate
        # una serie che parte da un orario qualsiasi (multiplo) e' valida
        BAR_CALLERS[name](good_bars(9, t0=12345))

    @pytest.mark.parametrize("name", list(BAR_CALLERS))
    @pytest.mark.parametrize("bad", [True, False, 0, -1, 1.0, 60000.5, "60000", None, D(60000), [1]])
    def test_candle_ms(self, name, bad):
        expect("invalid_candle_ms", BAR_CALLERS[name], good_bars(), candle_ms=bad)

    def test_candle_ms_one_is_valid_when_aligned(self):
        bars = [Bar(i, D(1), D(2), D(1), D(2), D(0)) for i in range(5)]
        assert len(true_range(bars, candle_ms=1)) == 5
        expect("invalid_bars", true_range, bars, candle_ms=2)          # 1 non e' multiplo di 2

    @pytest.mark.parametrize("name", [n for n in BAR_CALLERS if n not in ("check_bars", "true_range")])
    def test_error_order_candle_ms_then_period_then_bars(self, name):
        badbars = [None]
        param_bad = {"atr": {"n": 0}, "rsi": {"n": 0}, "macd": {"fast": 4, "slow": 2}, "bollinger": {"n": 1},
                     "donchian": {"n": 0}, "adx": {"n": 0}}[name]
        expect("invalid_candle_ms", BAR_CALLERS[name], badbars, candle_ms=True, **param_bad)
        expect("invalid_period", BAR_CALLERS[name], badbars, **param_bad)
        expect("invalid_bars", BAR_CALLERS[name], badbars)
        # periodo cattivo con barre valide: sempre invalid_period
        expect("invalid_period", BAR_CALLERS[name], good_bars(), **param_bad)

    def test_true_range_order_candle_ms_then_bars(self):
        expect("invalid_candle_ms", true_range, None, candle_ms=0)
        expect("invalid_bars", true_range, None, candle_ms=CMS)

    @pytest.mark.parametrize("name,pname", [("atr", "n"), ("rsi", "n"), ("donchian", "n"), ("adx", "n"),
                                            ("bollinger", "n")])
    @pytest.mark.parametrize("bad", [True, False, 0, -1, 1.0, 2.5, "3", None, D(3), [3]])
    def test_period_types(self, name, pname, bad):
        expect("invalid_period", BAR_CALLERS[name], good_bars(), **{pname: bad})

    @pytest.mark.parametrize("which", ["fast", "slow", "signal"])
    @pytest.mark.parametrize("bad", [True, 0, -2, 2.0, "2", None, D(2)])
    def test_macd_period_types(self, which, bad):
        kw = {"fast": 2, "slow": 4, "signal": 2}
        kw[which] = bad
        expect("invalid_period", BAR_CALLERS["macd"], good_bars(), **kw)

    def test_macd_fast_must_be_below_slow(self):
        for fast, slow in ((4, 4), (5, 4), (3, 2)):
            expect("invalid_period", BAR_CALLERS["macd"], good_bars(), fast=fast, slow=slow)
        BAR_CALLERS["macd"](good_bars(), fast=1, slow=2)

    def test_bollinger_n_and_k(self):
        expect("invalid_period", BAR_CALLERS["bollinger"], good_bars(), n=1)
        BAR_CALLERS["bollinger"](good_bars(), n=2)
        for bad in (D(0), D("-1"), 2.0, 2, "2", None, D("NaN"), D("Infinity"), D("-Infinity"), True):
            expect("invalid_period", BAR_CALLERS["bollinger"], good_bars(), k=bad)
        BAR_CALLERS["bollinger"](good_bars(), k=D("0.0001"))

    def test_donchian_and_others_accept_period_one(self):
        for name in ("atr", "rsi", "donchian", "adx"):
            BAR_CALLERS[name](good_bars(), n=1)


class TestValidationValues:
    FN = {"sma": sma, "ema": ema, "rma": rma}

    @pytest.mark.parametrize("name", list(FN))
    def test_control(self, name):
        assert len(self.FN[name]([D(1), D(2), D(3)], 2)) == 3
        assert self.FN[name]((D(1), D(2)), 1) is not None

    @pytest.mark.parametrize("name", list(FN))
    @pytest.mark.parametrize("bad", [None, "123", b"12", 5, {D(1)}, {1: D(1)}, (x for x in [D(1)]), iter([D(1)])])
    def test_values_container(self, name, bad):
        expect("invalid_values", self.FN[name], bad, 2)

    @pytest.mark.parametrize("name", list(FN))
    def test_value_elements_each_alone_at_three_positions(self, name):
        for bad in (1.5, 1, True, "1", None, D("NaN"), D("Infinity"), D("-Infinity"), D("sNaN"), [D(1)]):
            for pos in (0, 3, 6):
                vals = [D(i) for i in range(7)]
                vals[pos] = bad
                expect("invalid_values", self.FN[name], vals, 2)

    @pytest.mark.parametrize("name", list(FN))
    @pytest.mark.parametrize("bad", [True, False, 0, -1, 1.0, "2", None, D(2), [2]])
    def test_period(self, name, bad):
        expect("invalid_period", self.FN[name], [D(1), D(2)], bad)

    @pytest.mark.parametrize("name", list(FN))
    def test_period_checked_before_values(self, name):
        expect("invalid_period", self.FN[name], None, 0)
        expect("invalid_values", self.FN[name], None, 1)


# ============================================================ scale estreme
BIGCTX = Context(prec=120, Emax=decimal.MAX_EMAX, Emin=decimal.MIN_EMIN)
CTX_FIELDS = (("prec", 60), ("Emin", -999999), ("Emax", 999999), ("clamp", 0))


def base_bars(n=8):
    """Serie a scala 1; le altre scale sono la stessa mantissa con esponente spostato (invarianza di scala)."""
    out, p = [], D(1)
    for k in range(n):
        o, c = p, p * (D("1.01") if k % 2 else D("0.99"))
        out.append(Bar(k * CMS, o, max(o, c) * D("1.001"), min(o, c) / D("1.001"), c, D(1)))
        p = c
    return out


def rescale(bars, e):
    with localcontext(BIGCTX):
        return [Bar(b.open_time_ms, b.open.scaleb(e), b.high.scaleb(e), b.low.scaleb(e), b.close.scaleb(e), b.volume)
                for b in bars]


def _series(r):
    return tuple(r.__dict__.values()) if dataclasses.is_dataclass(r) else (r,)


# nome -> (calcolo sulle barre, oracolo sulle barre a scala 1, grado di omogeneita' di ogni serie)
# grado 1: la serie scala con il prezzo (livelli); grado 0: indipendente dalla scala (rapporti)
SCALE_CASES = {
    "true_range": (lambda b: true_range(b, candle_ms=CMS), lambda b: (o_tr(b),), (1,)),
    "atr": (lambda b: atr(b, 3, candle_ms=CMS), lambda b: (o_atr(b, 3),), (1,)),
    "rsi": (lambda b: rsi(b, 3, candle_ms=CMS), lambda b: (o_rsi(b, 3),), (0,)),
    "macd": (lambda b: macd(b, 2, 3, 2, candle_ms=CMS), lambda b: o_macd(b, 2, 3, 2), (1, 1, 1)),
    "bollinger": (lambda b: bollinger(b, 3, D(2), candle_ms=CMS), lambda b: o_boll(b, 3, D(2)), (1, 1, 1, 0, 0)),
    "donchian": (lambda b: donchian(b, 3, candle_ms=CMS), lambda b: o_donchian(b, 3), (1, 1)),
    "adx": (lambda b: adx(b, 3, candle_ms=CMS), lambda b: o_adx(b, 3), (0, 0, 0)),
    "sma": (lambda b: sma(closes(b), 3), lambda b: (o_sma([F(x) for x in closes(b)], 3),), (1,)),
    "ema": (lambda b: ema(closes(b), 3), lambda b: (o_ema([F(x) for x in closes(b)], 3),), (1,)),
    "rma": (lambda b: rma(closes(b), 3), lambda b: (o_rma([F(x) for x in closes(b)], 3),), (1,)),
}
BASE = base_bars()
BASE_WANT = {name: case[1](BASE) for name, case in SCALE_CASES.items()}
MUST_WORK = (-100_000, -300, 300, 100_000)
MAY_REFUSE = (-10**9, -1_000_100, -1_000_020, -999_990, -600_000, 600_000, 999_990, 999_999, 1_000_010,
              1_000_100, 10**9)
REL = Fraction(1, 10**30)


def assert_scaled_correct(got_series, want_series, degrees, e, ctx):
    assert len(got_series) == len(want_series) == len(degrees), ctx
    for si, (gs, ws, deg) in enumerate(zip(got_series, want_series, degrees)):
        assert len(gs) == len(ws), (ctx, si)
        for i, (g, w) in enumerate(zip(gs, ws)):
            if w is None:
                assert g is None, (ctx, si, i)
                continue
            assert g is not None and type(g) is Decimal, (ctx, si, i, g)
            with localcontext(BIGCTX):
                unscaled = Fraction(g.scaleb(-e * deg))
            assert abs(unscaled - w) <= REL * max(abs(w), Fraction(1, 10**20)), (ctx, si, i, g)


class TestExtremeScales:
    def test_base_series_is_valid_and_oracle_is_nontrivial(self):
        check_bars(BASE, candle_ms=CMS)
        for name, want in BASE_WANT.items():
            assert any(v is not None and v != 0 for ws in want for v in ws), name

    @pytest.mark.parametrize("name", list(SCALE_CASES))
    @pytest.mark.parametrize("e", MUST_WORK)
    def test_supported_range_is_correct_not_refused(self, name, e):
        fn, _, degrees = SCALE_CASES[name]
        got = _series(fn(rescale(BASE, e)))
        assert_scaled_correct(got, BASE_WANT[name], degrees, e, (name, e))

    @pytest.mark.parametrize("name", list(SCALE_CASES))
    @pytest.mark.parametrize("e", MAY_REFUSE)
    def test_beyond_range_correct_or_typed_never_raw_never_silently_wrong(self, name, e):
        fn, _, degrees = SCALE_CASES[name]
        try:
            got = _series(fn(rescale(BASE, e)))
        except ValueError as exc:
            assert str(exc) == "numeric_out_of_range", (name, e, str(exc))
            return
        assert_scaled_correct(got, BASE_WANT[name], degrees, e, (name, e))      # se risponde, risponde giusto

    @pytest.mark.parametrize("name", list(SCALE_CASES))
    def test_the_refusal_actually_happens_somewhere(self, name):
        """Guardia: l'insieme di scale oltre il range contiene casi che il modulo rifiuta davvero (sono 'ValueError'
        e non risposte): altrimenti il test precedente non proverebbe nulla sul ramo dell'errore."""
        fn = SCALE_CASES[name][0]
        refused = 0
        for e in MAY_REFUSE:
            try:
                fn(rescale(BASE, e))
            except ValueError:
                refused += 1
        if name != "donchian":                       # donchian non fa aritmetica: risponde a ogni scala
            assert refused >= 3, (name, refused)

    def test_error_has_no_decimal_cause_attached(self):
        with pytest.raises(ValueError) as ex:
            bollinger(rescale(BASE, 600_000), 3, D(2), candle_ms=CMS)
        assert str(ex.value) == "numeric_out_of_range"
        assert ex.value.__cause__ is None and ex.value.__suppress_context__ is True

    def test_context_is_pinned_not_inherited(self):
        c = ind._CTX
        for attr, want in CTX_FIELDS:
            assert getattr(c, attr) == want, attr
        assert c.rounding == decimal.ROUND_HALF_EVEN
        for trap in (decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow, decimal.Underflow):
            assert c.traps[trap], trap

    def test_the_ambient_trap_settings_of_the_caller_do_not_matter(self):
        with localcontext() as c:
            c.traps[decimal.Overflow] = False
            c.traps[decimal.Underflow] = False
            c.Emax = decimal.MAX_EMAX
            c.Emin = decimal.MIN_EMIN
            with pytest.raises(ValueError) as ex:
                bollinger(rescale(BASE, 600_000), 3, D(2), candle_ms=CMS)
            assert str(ex.value) == "numeric_out_of_range"
            with pytest.raises(ValueError) as ex:
                ema(closes(rescale(BASE, -1_000_100)), 3)
            assert str(ex.value) == "numeric_out_of_range"


# ============================================================ purezza
class TestPurity:
    src = Path(ind.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    def test_imports(self):
        mods = set()
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Import):
                mods |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                mods.add((n.module or "").split(".")[0])
        assert mods <= {"__future__", "dataclasses", "decimal", "typing", "collections", "math"}, mods

    def test_no_float_clock_random_io(self):
        names = {n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        attrs = {n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute)}
        assert not names & {"float", "open", "print", "eval", "exec", "compile", "__import__", "input", "globals"}
        assert not attrs & {"now", "today", "time", "random", "uniform", "urlopen", "system", "popen",
                            "read_text", "write_text", "environ", "getenv"}
        floats = [n for n in ast.walk(self.tree) if isinstance(n, ast.Constant) and type(n.value) is float]
        assert floats == []
        assert "float(" not in self.src

    def test_no_numeric_defaults_in_signatures(self):
        for fn in ast.walk(self.tree):
            if isinstance(fn, ast.FunctionDef):
                defaults = list(fn.args.defaults) + [d for d in fn.args.kw_defaults if d is not None]
                for d in defaults:
                    assert not (isinstance(d, ast.Constant) and isinstance(d.value, (int, float)) and
                                not isinstance(d.value, bool)), fn.name

    def test_local_context_is_used_by_every_public_function(self):
        public = {"sma", "ema", "rma", "true_range", "atr", "rsi", "macd", "bollinger", "donchian", "adx"}
        for fn in ast.walk(self.tree):
            if isinstance(fn, ast.FunctionDef) and fn.name in public:
                uses = any(isinstance(n, ast.Name) and n.id == "localcontext" for n in ast.walk(fn)) or \
                    any(isinstance(n, ast.Call) and getattr(n.func, "id", "") in public - {fn.name} for n in ast.walk(fn))
                assert uses, fn.name

    def test_module_has_no_import_time_side_effects(self):
        assert getcontext().prec == 28


# ============================================================ prestazioni (nessun O(n^2) nascosto)
class TestScaling:
    def test_adx_and_friends_scale_linearly_enough(self):
        import time as _t
        bars = make_bars(random.Random(1), 3000, "walk_flats")
        t = _t.perf_counter()
        adx(bars, 14, candle_ms=CMS); rsi(bars, 14, candle_ms=CMS); atr(bars, 14, candle_ms=CMS)
        bollinger(bars, 20, D(2), candle_ms=CMS); macd(bars, 12, 26, 9, candle_ms=CMS); donchian(bars, 20, candle_ms=CMS)
        elapsed = _t.perf_counter() - t
        assert elapsed < 5.0, f"{elapsed:.1f}s per 3000 barre: ricalcolo ripetuto?"


# ============================================================ laboratorio del 9 ottobre e pandas
np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")


class TestAgainstLabAndPandas:
    @staticmethod
    def arrays(bars):
        f = lambda xs: np.array([float(x) for x in xs])  # noqa: E731
        return f([b.high for b in bars]), f([b.low for b in bars]), f([b.close for b in bars])

    def rel(self, got, want, ctx, rtol=1e-9):
        for i, (g, w) in enumerate(zip(got, want)):
            if g is None:
                continue
            assert abs(float(g) - w) <= rtol * max(1.0, abs(w)), (ctx, i, float(g), w)

    def test_against_strategy_lab(self):
        lab = pytest.importorskip("backend.strategy_lab")
        bars = make_bars(random.Random(3), 500, "walk", t0=0)
        h, l, c = self.arrays(bars)
        for n in (3, 14, 20):
            self.rel(ema([b.close for b in bars], n), lab.ema(c, n), ("ema", n))
            self.rel(rma([b.close for b in bars], n), lab.rma(c, n), ("rma", n))
            self.rel(atr(bars, n, candle_ms=CMS), lab.atr(h, l, c, n), ("atr", n))
            a = adx(bars, n, candle_ms=CMS)
            self.rel(a.adx, lab.adx(h, l, c, n), ("adx", n))
            mid, up, lo = lab.bollinger(c, n, 2.0)
            b = bollinger(bars, n, D("2.0"), candle_ms=CMS) if n >= 2 else None
            self.rel(b.mid, mid, ("bb-mid", n)); self.rel(b.upper, up, ("bb-up", n)); self.rel(b.lower, lo, ("bb-lo", n))

    def test_rsi_and_macd_against_pandas_formulas(self):
        bars = make_bars(random.Random(4), 400, "walk_flats", t0=0)
        c = pd.Series([float(b.close) for b in bars])
        for n in (2, 14):
            d = c.diff()
            ag = d.clip(lower=0).ewm(alpha=1.0 / n, adjust=False).mean()
            al = (-d.clip(upper=0)).ewm(alpha=1.0 / n, adjust=False).mean()
            rs = ag / al
            want = (100 - 100 / (1 + rs)).tolist()
            got = rsi(bars, n, candle_ms=CMS)
            for i, (g, w) in enumerate(zip(got, want)):
                if g is None:
                    continue
                if math.isnan(w) or math.isinf(w):      # 0/0 e x/0: casi limite definiti dal contratto (50 e 100)
                    continue
                assert abs(float(g) - w) <= 1e-9 * max(1.0, abs(w)), (n, i, float(g), w)
        fast, slow, signal = 12, 26, 9
        ef, es = c.ewm(span=fast, adjust=False).mean(), c.ewm(span=slow, adjust=False).mean()
        line = ef - es
        sig = line.ewm(span=signal, adjust=False).mean()
        m = macd(bars, fast, slow, signal, candle_ms=CMS)
        self.rel(m.line, line.tolist(), "macd.line")
        self.rel(m.signal, sig.tolist(), "macd.signal")
        self.rel(m.hist, (line - sig).tolist(), "macd.hist")
