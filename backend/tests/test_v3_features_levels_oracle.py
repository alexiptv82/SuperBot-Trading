"""F7 / P7b - livelli e sessioni (supertrend, atr_percentile, vwap_session, opening_range, swing_levels):
verifica INDIPENDENTE (Claude) del modulo di Grok.

Il suo file ha 8 test (un valore comodo per funzione); mutanti, oracolo, troncamento completo, validazione,
scale estreme e prestazioni risultavano NON ESEGUITI. Qui:

* ORACOLO ``Fraction`` scritto dal contratto con algoritmi diversi dal modulo: ATR in forma chiusa, rango
  percentile con ordinamento (bisect), posizione nella sessione derivata dal TEMPO (non dall'enumerazione),
  pivot cercati all'indietro per ogni barra, supertrend come macchina a stati su un ATR esterno;
* vettori calcolati a parte (quelli del prompt) e dati casuali su griglia intera (cosi' ci sono pareggi di
  massimi/minimi), con guardie che dimostrano che i casi difficili ci sono davvero;
* invarianza al troncamento per OGNI serie di output, con meta-test su look-ahead veri;
* validazione esaustiva (codici esatti, ordine, ogni caso cattivo differisce dal buono solo per il difetto);
* scale estreme per invarianza di scala (corretto oppure ``numeric_out_of_range``, mai eccezione grezza ne'
  valore sbagliato), contesto Decimal ambientale, forma, purezza AST, prestazioni lineari.
"""
from __future__ import annotations

import ast
import copy
import dataclasses
import decimal
import inspect
import random
import time
from bisect import bisect_right
from decimal import ROUND_UP, Context, Decimal, getcontext, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from backend.v3.features import levels as lv
from backend.v3.features.indicators import Bar, check_bars
from backend.v3.features.levels import atr_percentile, opening_range, supertrend, swing_levels, vwap_session

D = Decimal
CMS = 60_000
TOL = Fraction(1, 10**40)


def F(x, y=1) -> Fraction:
    return Fraction(x, y) if y != 1 or isinstance(x, int) else Fraction(x)


# ============================================================ dati
def make_bars(rng: random.Random, length: int, mode: str, t0: int = 0):
    """Barre VALIDE su griglia intera (cosi' i massimi/minimi hanno pareggi), volumi anche 0."""
    out, price = [], 30
    for k in range(length):
        if mode == "flat":
            o = h = lo = c = price
        else:
            o = price
            if mode == "spiky" and rng.random() < 0.2:
                o = max(1, price + rng.randint(-6, 6))
            if mode == "up":
                c = o + rng.randint(1, 4)
            elif mode == "down":
                c = max(1, o - rng.randint(1, 4))
            else:
                c = max(1, o + rng.randint(-4, 4))
            h = max(o, c) + rng.randint(0, 3)
            lo = max(1, min(o, c) - rng.randint(0, 3))
        v = 0 if rng.random() < 0.3 else rng.randint(1, 6)
        out.append(Bar((t0 + k) * CMS, D(o), D(h), D(lo), D(c), D(v)))
        price = c
    return out


MODES = ("walk", "up", "down", "flat", "spiky")
LENGTHS = (1, 2, 3, 5, 8, 13, 25, 40, 70)
DATASETS = []
_rng = random.Random(20261104)
for _i, (_mode, _len) in enumerate(((m, n) for m in MODES for n in LENGTHS)):
    DATASETS.append((f"{_mode}-{_len}-{_i}", make_bars(_rng, _len, _mode, t0=(_i * 3) % 7)))
for _s in range(5):
    DATASETS.append((f"long-{_s}", make_bars(random.Random(700 + _s), 100, "walk" if _s % 2 else "spiky", t0=_s)))

ST_PARAMS = [(n, m) for n in (1, 2, 3, 5, 14) for m in (D(1), D("2.5"))]
PCT_PARAMS = [(n, w) for n in (1, 2, 3, 5) for w in (1, 2, 5, 20)]
SESSIONS = [(1, 0), (2, 0), (2, 1), (4, 0), (4, 3), (6, 2)]        # (periodo in barre, ancora in barre)
OR_K = (1, 2, 3)
SWING_PARAMS = [(1, 1), (2, 1), (1, 2), (3, 2), (2, 3)]


def closes(bars):
    return [b.close for b in bars]


def bars_from(highs, lows, closes_=None, vols=None, t0=0):
    out = []
    for k, (h, lo) in enumerate(zip(highs, lows)):
        c = lo if closes_ is None else closes_[k]
        out.append(Bar((t0 + k) * CMS, D(c), D(h), D(lo), D(c), D(1 if vols is None else vols[k])))
    return out


def test_generator_produces_valid_bars():
    for name, bars in DATASETS:
        check_bars(bars, candle_ms=CMS)


# ============================================================ oracolo (Fraction)
def closed_form(vals, alpha: Fraction):
    beta = 1 - alpha
    pw = [Fraction(1)]
    for _ in range(len(vals)):
        pw.append(pw[-1] * beta)
    return [alpha * sum((pw[j] * vals[i - j] for j in range(i)), Fraction(0)) + pw[i] * vals[0] for i in range(len(vals))]


def o_tr(bars):
    out = []
    for i, b in enumerate(bars):
        h, lo = F(b.high), F(b.low)
        out.append(h - lo if i == 0 else max(h - lo, abs(h - F(bars[i - 1].close)), abs(lo - F(bars[i - 1].close))))
    return out


_ATR_CACHE: dict = {}


def o_atr(bars, n):
    key = (id(bars), n)
    if key not in _ATR_CACHE:
        e = closed_form(o_tr(bars), Fraction(1, n))
        _ATR_CACHE[key] = [None if i < n - 1 else e[i] for i in range(len(bars))]
    return _ATR_CACHE[key]


def o_supertrend(bars, a, mult):
    """Macchina a stati dalle formule L1, su una serie ATR data (cosi' si puo' provare anche con un ATR finto)."""
    line, dirn, state = [None] * len(bars), [None] * len(bars), None
    for i in range(len(bars)):
        if a[i] is None:
            continue
        hl2 = (F(bars[i].high) + F(bars[i].low)) / 2
        bu, bl = hl2 + F(mult) * a[i], hl2 - F(mult) * a[i]
        if state is None:
            fu, fl, d = bu, bl, -1
        else:
            pfu, pfl, pd = state
            pc, c = F(bars[i - 1].close), F(bars[i].close)
            fu = bu if (bu < pfu or pc > pfu) else pfu
            fl = bl if (bl > pfl or pc < pfl) else pfl
            d = (1 if c > fu else -1) if pd == -1 else (-1 if c < fl else 1)
        state = (fu, fl, d)
        dirn[i] = d
        line[i] = fl if d == 1 else fu
    return line, dirn


def o_atr_pct(bars, n, window):
    a = o_atr(bars, n)
    out = [None] * len(bars)
    for i in range((n - 1) + (window - 1), len(bars)):
        win = sorted(a[i - window + 1:i + 1])
        out[i] = 100 * Fraction(bisect_right(win, a[i]), window)
    return out


def _session_pos(bars, i, period_ms, anchor_ms):
    """(indice della prima barra della sessione di i, posizione di i nella sessione, sessione completa?)"""
    t = bars[i].open_time_ms
    s = (t - anchor_ms) // period_ms
    start_t = anchor_ms + s * period_ms
    pos = (t - start_t) // CMS
    return i - pos, pos, bars[0].open_time_ms <= start_t


def o_vwap(bars, period_ms, anchor_ms):
    out = [None] * len(bars)
    for i in range(len(bars)):
        j, _, complete = _session_pos(bars, i, period_ms, anchor_ms)
        if not complete:
            continue
        sv = sum((F(b.volume) for b in bars[j:i + 1]), Fraction(0))
        if sv > 0:
            out[i] = sum((F(b.volume) * (F(b.high) + F(b.low) + F(b.close)) / 3 for b in bars[j:i + 1]), Fraction(0)) / sv
    return out


def o_opening_range(bars, period_ms, anchor_ms, k):
    hi, lo = [None] * len(bars), [None] * len(bars)
    for i in range(len(bars)):
        j, pos, complete = _session_pos(bars, i, period_ms, anchor_ms)
        if complete and pos >= k - 1:
            hi[i] = max(F(b.high) for b in bars[j:j + k])
            lo[i] = min(F(b.low) for b in bars[j:j + k])
    return hi, lo


def o_swing(bars, left, right):
    """Per ogni barra i: cerca all'indietro il pivot piu' recente j <= i-right (valutato solo con barre <= j+right)."""
    n = len(bars)
    h, lo = [None] * n, [None] * n
    ht, lt = [None] * n, [None] * n
    for i in range(n):
        for j in range(i - right, left - 1, -1):
            hj = bars[j].high
            if hj > max(b.high for b in bars[j - left:j]) and hj >= max(b.high for b in bars[j + 1:j + right + 1]):
                h[i], ht[i] = F(hj), bars[j].open_time_ms
                break
        for j in range(i - right, left - 1, -1):
            lj = bars[j].low
            if lj < min(b.low for b in bars[j - left:j]) and lj <= min(b.low for b in bars[j + 1:j + right + 1]):
                lo[i], lt[i] = F(lj), bars[j].open_time_ms
                break
    return h, lo, ht, lt


def same(got, want, ctx, tol=TOL):
    assert len(got) == len(want), (ctx, len(got), len(want))
    for i, (g, w) in enumerate(zip(got, want)):
        if w is None:
            assert g is None, (ctx, i, "atteso None", g)
        elif isinstance(w, int) and not isinstance(w, bool):
            assert type(g) is int and g == w, (ctx, i, g, w)
        else:
            assert g is not None and type(g) is Decimal, (ctx, i, g)
            assert abs(Fraction(g) - w) <= tol * max(1, abs(w)), (ctx, i, g, float(w))


# ============================================================ vettori calcolati a parte (quelli del prompt)
HI12 = [10, 12, 13, 15, 16, 14, 12, 9, 8, 10, 13, 15]
LO12 = [8, 9, 11, 12, 14, 11, 9, 6, 5, 7, 10, 12]
HI8, LO8, CL8, VO8 = [10, 12, 11, 14, 13, 13, 12, 15], [8, 9, 7, 10, 9, 10, 6, 11], [9, 11, 8, 13, 12, 10, 7, 14], [2, 0, 3, 1, 4, 2, 0, 5]


class TestHandVectors:
    def test_swing(self):
        bars = bars_from([10, 12, 11, 14, 13, 13, 12, 15, 9], [8, 9, 7, 10, 9, 10, 6, 11, 5])
        s = swing_levels(bars, 2, 1, candle_ms=CMS)
        assert s.high == (None,) * 4 + (D(14),) * 4 + (D(15),)
        assert s.high_time_ms == (None,) * 4 + (180000,) * 4 + (420000,)
        assert s.low == (None,) * 3 + (D(7),) * 4 + (D(6), D(6))
        assert s.low_time_ms == (None,) * 3 + (120000,) * 4 + (360000, 360000)

    def test_vwap_and_opening_range(self):
        bars = bars_from(HI8, LO8, CL8, VO8)
        v = vwap_session(bars, 4 * CMS, 0, candle_ms=CMS)
        same(v, [F(9), F(9), F(44, 5), F(169, 18), F(34, 3), F(101, 9), F(101, 9), F(134, 11)], "vwap")
        r = opening_range(bars, 4 * CMS, 0, 2, candle_ms=CMS)
        assert r.high == (None, D(12), D(12), D(12), None, D(13), D(13), D(13))
        assert r.low == (None, D(8), D(8), D(8), None, D(9), D(9), D(9))

    def test_supertrend_and_atr_percentile(self):
        bars = bars_from(HI12, LO12)
        s = supertrend(bars, 2, D(1), candle_ms=CMS)
        assert s.direction == (None, -1, -1, -1, 1, -1, -1, -1, -1, -1, 1, 1)
        same(s.line, [None, F(27, 2), F(27, 2), F(27, 2), F(89, 8), F(255, 16), F(439, 32), F(679, 64), F(1223, 128),
                      F(1223, 128), F(3321, 512), F(8697, 1024)], "line")
        same(atr_percentile(bars, 2, 3, candle_ms=CMS),
             [None, None, None, F(100), F(100), F(100, 3), F(100, 3), F(100, 3), F(100, 3), F(100), F(100), F(200, 3)], "pct")

    def test_vectors_agree_with_oracle(self):
        """I vettori a mano coincidono con l'oracolo: se no, l'errore e' mio e non del modulo."""
        bars = bars_from(HI12, LO12)
        a = o_atr(bars, 2)
        assert a[1:4] == [F(3), F(7, 2), F(15, 4)]
        line, d = o_supertrend(bars, a, F(1))
        assert d == [None, -1, -1, -1, 1, -1, -1, -1, -1, -1, 1, 1] and line[1] == F(27, 2) and line[4] == F(89, 8)
        b8 = bars_from(HI8, LO8, CL8, VO8)
        assert o_vwap(b8, 4 * CMS, 0)[3] == F(169, 18)
        hi, lo = o_opening_range(b8, 4 * CMS, 0, 2)
        assert hi == [None, 12, 12, 12, None, 13, 13, 13] and lo[5] == 9


# ============================================================ contro l'oracolo
class TestAgainstOracle:
    def test_supertrend(self):
        flips = {"down_to_up": 0, "up_to_down": 0}
        for name, bars in DATASETS:
            for n, m in ST_PARAMS:
                got = supertrend(bars, n, m, candle_ms=CMS)
                line, dirn = o_supertrend(bars, o_atr(bars, n), m)
                same(got.line, line, (name, "line", n, m))
                same(got.direction, dirn, (name, "dir", n, m))
                for x, y in zip(dirn, dirn[1:]):
                    flips["down_to_up"] += (x, y) == (-1, 1)
                    flips["up_to_down"] += (x, y) == (1, -1)
        assert flips["down_to_up"] > 20 and flips["up_to_down"] > 20, flips          # guardia: cambi in ENTRAMBI i versi

    def test_atr_percentile(self):
        seen = {"hundred": 0, "min_rank": 0, "short": 0}
        for name, bars in DATASETS:
            for n, w in PCT_PARAMS:
                got = atr_percentile(bars, n, w, candle_ms=CMS)
                want = o_atr_pct(bars, n, w)
                same(got, want, (name, "pct", n, w))
                seen["hundred"] += sum(1 for x in want if x == 100)
                seen["min_rank"] += sum(1 for x in want if x is not None and w > 1 and x == Fraction(100, w))
                seen["short"] += (n - 1) + (w - 1) >= len(bars)
        assert seen["hundred"] > 100 and seen["min_rank"] > 20 and seen["short"] > 30, seen

    def test_vwap_session(self):
        seen = {"partial": 0, "zero_vol_session_start": 0, "values": 0}
        for name, bars in DATASETS:
            for pb, ab in SESSIONS:
                got = vwap_session(bars, pb * CMS, ab * CMS, candle_ms=CMS)
                want = o_vwap(bars, pb * CMS, ab * CMS)
                same(got, want, (name, "vwap", pb, ab))
                j, _, complete = _session_pos(bars, 0, pb * CMS, ab * CMS)
                seen["partial"] += not complete
                seen["values"] += sum(1 for x in want if x is not None)
                seen["zero_vol_session_start"] += sum(
                    1 for i in range(len(bars)) if _session_pos(bars, i, pb * CMS, ab * CMS)[2] and want[i] is None)
        assert seen["partial"] > 30 and seen["zero_vol_session_start"] > 30 and seen["values"] > 1000, seen

    def test_opening_range(self):
        seen = {"partial": 0, "incomplete_last": 0, "values": 0}
        for name, bars in DATASETS:
            for pb, ab in SESSIONS:
                for k in OR_K:
                    if k > pb:
                        continue
                    got = opening_range(bars, pb * CMS, ab * CMS, k, candle_ms=CMS)
                    hi, lo = o_opening_range(bars, pb * CMS, ab * CMS, k)
                    same(got.high, hi, (name, "or-high", pb, ab, k))
                    same(got.low, lo, (name, "or-low", pb, ab, k))
                    seen["partial"] += not _session_pos(bars, 0, pb * CMS, ab * CMS)[2]
                    seen["values"] += sum(1 for x in hi if x is not None)
                    last = len(bars) - 1
                    j, pos, complete = _session_pos(bars, last, pb * CMS, ab * CMS)
                    seen["incomplete_last"] += complete and pos < k - 1
        assert seen["partial"] > 30 and seen["incomplete_last"] > 20 and seen["values"] > 500, seen

    def test_swing_levels(self):
        seen = {"ties": 0, "no_pivot": 0, "pivots": 0, "short": 0}
        for name, bars in DATASETS:
            for left, right in SWING_PARAMS:
                got = swing_levels(bars, left, right, candle_ms=CMS)
                h, lo, ht, lt = o_swing(bars, left, right)
                ctx = (name, left, right)
                same(got.high, h, ctx + ("high",))
                same(got.low, lo, ctx + ("low",))
                same(got.high_time_ms, ht, ctx + ("high_t",))
                same(got.low_time_ms, lt, ctx + ("low_t",))
                seen["no_pivot"] += all(x is None for x in h) and all(x is None for x in lo)
                seen["pivots"] += sum(1 for x, y in zip(ht, ht[1:]) if y != x and y is not None)
                seen["short"] += len(bars) <= left + right
                for j in range(left, len(bars) - right):          # pareggi: massimo uguale a quello di una barra vicina
                    nb = bars[j - left:j] + bars[j + 1:j + right + 1]
                    seen["ties"] += any(b.high == bars[j].high for b in nb) and bars[j].high >= max(b.high for b in nb)
        assert seen["ties"] > 100 and seen["no_pivot"] > 10 and seen["pivots"] > 300 and seen["short"] > 20, seen

    def test_supertrend_uses_indicators_atr_not_its_own(self, monkeypatch):
        bars = DATASETS[40][1]                                    # serie "walk-70"
        n = 3
        fake = tuple([None] * (n - 1) + [D("1.5")] * (len(bars) - n + 1))
        calls = []

        def stub(b, nn, *, candle_ms):
            calls.append((nn, candle_ms))
            return fake
        monkeypatch.setattr(lv, "atr", stub)
        got = supertrend(bars, n, D(2), candle_ms=CMS)
        assert calls and calls[0] == (n, CMS)
        line, dirn = o_supertrend(bars, [None if x is None else F(x) for x in fake], F(2))
        same(got.line, line, "line-fake-atr")
        same(got.direction, dirn, "dir-fake-atr")
        calls.clear()
        monkeypatch.setattr(lv, "atr", stub)
        atr_percentile(bars, n, 4, candle_ms=CMS)
        assert calls and calls[0] == (n, CMS)


# ============================================================ nessun look-ahead
CALLS = {
    "st.line": lambda b: supertrend(b, 3, D(2), candle_ms=CMS).line,
    "st.direction": lambda b: supertrend(b, 3, D(2), candle_ms=CMS).direction,
    "atr_pct": lambda b: atr_percentile(b, 3, 4, candle_ms=CMS),
    "vwap": lambda b: vwap_session(b, 4 * CMS, CMS, candle_ms=CMS),
    "or.high": lambda b: opening_range(b, 4 * CMS, CMS, 2, candle_ms=CMS).high,
    "or.low": lambda b: opening_range(b, 4 * CMS, CMS, 2, candle_ms=CMS).low,
    "swing.high": lambda b: swing_levels(b, 2, 2, candle_ms=CMS).high,
    "swing.low": lambda b: swing_levels(b, 2, 2, candle_ms=CMS).low,
    "swing.high_t": lambda b: swing_levels(b, 2, 2, candle_ms=CMS).high_time_ms,
    "swing.low_t": lambda b: swing_levels(b, 2, 2, candle_ms=CMS).low_time_ms,
}


def prefix_violations(fn, bars):
    full = tuple(fn(bars))
    return [m for m in range(len(bars) + 1) if tuple(fn(bars[:m])) != full[:m]]


class TestNoLookahead:
    @pytest.mark.parametrize("name", list(CALLS))
    def test_truncation_invariance(self, name):
        for ds, bars in DATASETS[::3] + DATASETS[-3:]:
            assert prefix_violations(CALLS[name], bars) == [], (name, ds)

    def test_the_check_can_see_real_lookahead(self):
        def pivot_without_waiting(bars):                     # conferma il pivot a j invece che a j+right
            h, _, _, _ = o_swing(bars, 2, 2)
            out = []
            for i in range(len(bars)):
                cand = [j for j in range(2, len(bars) - 2)
                        if j <= i and bars[j].high > max(b.high for b in bars[j - 2:j])
                        and bars[j].high >= max(b.high for b in bars[j + 1:j + 3])]
                out.append(bars[cand[-1]].high if cand else None)
            return tuple(out)

        def whole_session_range(bars):                       # range d'apertura visto prima di averlo (usa barre future)
            res = []
            for i in range(len(bars)):
                j, pos, complete = _session_pos(bars, i, 4 * CMS, CMS)
                res.append(max(b.high for b in bars[j:j + 2]) if complete and j + 1 < len(bars) else None)
            return tuple(res)

        def vwap_of_whole_session(bars):
            res = []
            for i in range(len(bars)):
                j, pos, complete = _session_pos(bars, i, 4 * CMS, CMS)
                seg = bars[j:j + 4]
                res.append(sum(b.close for b in seg) if complete else None)
            return tuple(res)
        bars = next(b for n, b in DATASETS if n.startswith("long-1"))
        assert len({b.high for b in bars}) > 5
        for bad in (pivot_without_waiting, whole_session_range, vwap_of_whole_session):
            assert prefix_violations(bad, bars) != [], bad.__name__

    def test_changing_the_future_does_not_change_the_past(self):
        _, bars = DATASETS[43]
        for cut in (5, 20, 50):
            tail = [dataclasses.replace(b, high=b.high + 7, volume=b.volume + 3) for b in bars[cut:]]
            altered = list(bars[:cut]) + tail
            for name, fn in CALLS.items():
                assert tuple(fn(altered))[:cut] == tuple(fn(bars))[:cut], (name, cut)


# ============================================================ validazione
def good_bars(n=12, t0=3):
    return make_bars(random.Random(5), n, "walk", t0=t0)


CALLERS = {
    "supertrend": lambda b, **k: supertrend(b, k.get("n", 3), k.get("mult", D(1)), candle_ms=k.get("candle_ms", CMS)),
    "atr_percentile": lambda b, **k: atr_percentile(b, k.get("n", 3), k.get("window", 3), candle_ms=k.get("candle_ms", CMS)),
    "vwap_session": lambda b, **k: vwap_session(b, k.get("period_ms", 4 * CMS), k.get("anchor_ms", 0), candle_ms=k.get("candle_ms", CMS)),
    "opening_range": lambda b, **k: opening_range(b, k.get("period_ms", 4 * CMS), k.get("anchor_ms", 0), k.get("k", 2),
                                                  candle_ms=k.get("candle_ms", CMS)),
    "swing_levels": lambda b, **k: swing_levels(b, k.get("left", 2), k.get("right", 1), candle_ms=k.get("candle_ms", CMS)),
}
# un parametro cattivo per funzione (per l'ordine degli errori)
ONE_BAD_PARAM = {"supertrend": {"n": 0}, "atr_percentile": {"n": 0}, "vwap_session": {"period_ms": 0},
                 "opening_range": {"k": 0}, "swing_levels": {"left": 0}}


def expect(code, fn, *a, **k):
    with pytest.raises(ValueError) as e:
        fn(*a, **k)
    assert str(e.value) == code, (str(e.value), code)


def with_bar(bars, pos, **over):
    out = list(bars)
    out[pos] = dataclasses.replace(out[pos], **over)
    return out


BAD_INT = [True, False, 0, -1, 1.0, 2.5, "3", None, D(3), [3]]


class TestValidation:
    @pytest.mark.parametrize("name", list(CALLERS))
    def test_control_valid_and_empty(self, name):
        assert CALLERS[name](good_bars()) is not None
        r = CALLERS[name]([])
        vals = [getattr(r, f.name) for f in dataclasses.fields(r)] if dataclasses.is_dataclass(r) else [r]
        assert all(v == () for v in vals)
        CALLERS[name](good_bars(1))

    @pytest.mark.parametrize("name", list(CALLERS))
    @pytest.mark.parametrize("bad", [None, "abc", b"abc", 5, {1}, {"a": 1}, (x for x in range(3)), iter([]),
                                     set(good_bars(3)), frozenset(good_bars(3)), dict.fromkeys(good_bars(3))])
    def test_bars_container(self, name, bad):
        expect("invalid_bars", CALLERS[name], bad)

    @pytest.mark.parametrize("name", list(CALLERS))
    def test_bar_defects_each_alone_at_three_positions(self, name):
        base = good_bars()
        cases = {
            "not a Bar": lambda b, p: [None if i == p else x for i, x in enumerate(b)],
            "dict instead of Bar": lambda b, p: [dataclasses.asdict(x) if i == p else x for i, x in enumerate(b)],
            "price float": lambda b, p: with_bar(b, p, close=100.5),
            "price nan": lambda b, p: with_bar(b, p, open=D("NaN")),
            "price zero": lambda b, p: with_bar(b, p, low=D(0)),
            "volume negative": lambda b, p: with_bar(b, p, volume=D("-1")),
            "volume float": lambda b, p: with_bar(b, p, volume=1.5),
            "low above high": lambda b, p: with_bar(b, p, low=b[p].high + 1),
            "close above high": lambda b, p: with_bar(b, p, close=b[p].high + 1),
            "open below low": lambda b, p: with_bar(b, p, open=b[p].low - D("0.5")),
            "time not aligned": lambda b, p: with_bar(b, p, open_time_ms=b[p].open_time_ms + 1),
        }
        for label, make in cases.items():
            for pos in (0, len(base) // 2, len(base) - 1):
                expect("invalid_bars", CALLERS[name], make(base, pos))

    @pytest.mark.parametrize("name", list(CALLERS))
    def test_gaps_duplicates_ordering(self, name):
        base = good_bars(10)
        for k in (1, 5, 8):                                  # buco in prima/centrale/penultima posizione (togliere l'ultima non fa buco)
            expect("invalid_bars", CALLERS[name], base[:k] + base[k + 1:])
        for k in (1, 5, 9):
            dup = list(base)
            dup[k] = dataclasses.replace(dup[k], open_time_ms=dup[k - 1].open_time_ms)
            expect("invalid_bars", CALLERS[name], dup)
            back = list(base)
            back[k], back[k - 1] = back[k - 1], back[k]
            expect("invalid_bars", CALLERS[name], back)

    @pytest.mark.parametrize("name", list(CALLERS))
    @pytest.mark.parametrize("bad", [True, False, 0, -1, 60000.0, "60000", None, D(60000), [1]])
    def test_candle_ms(self, name, bad):
        expect("invalid_candle_ms", CALLERS[name], good_bars(), candle_ms=bad)

    @pytest.mark.parametrize("name", list(CALLERS))
    def test_error_order(self, name):
        bad_param = ONE_BAD_PARAM[name]
        for bad_ms in (True, 0, -1, 60000.0, None):
            expect("invalid_candle_ms", CALLERS[name], [None], candle_ms=bad_ms, **bad_param)
        expect("invalid_period", CALLERS[name], [None], **bad_param)          # periodo prima delle barre
        expect("invalid_period", CALLERS[name], good_bars(), **bad_param)
        expect("invalid_bars", CALLERS[name], [None])

    @pytest.mark.parametrize("name,param", [("supertrend", "n"), ("atr_percentile", "n"), ("atr_percentile", "window"),
                                            ("swing_levels", "left"), ("swing_levels", "right"), ("opening_range", "k")])
    @pytest.mark.parametrize("bad", BAD_INT)
    def test_integer_parameters(self, name, param, bad):
        expect("invalid_period", CALLERS[name], good_bars(), **{param: bad})

    @pytest.mark.parametrize("bad", [D(0), D("-1"), 2.0, 1, "1", None, D("NaN"), D("Infinity"), D("-Infinity"), True])
    def test_supertrend_mult(self, bad):
        expect("invalid_period", CALLERS["supertrend"], good_bars(), mult=bad)
        CALLERS["supertrend"](good_bars(), mult=D("0.0001"))

    @pytest.mark.parametrize("name", ["vwap_session", "opening_range"])
    def test_session_parameters(self, name):
        for bad in (True, False, 0, -CMS, 4 * CMS + 1, CMS // 2, 4.0 * CMS, "x", None, D(4 * CMS)):
            expect("invalid_period", CALLERS[name], good_bars(), period_ms=bad)
        for bad in (True, -CMS, 4 * CMS, 5 * CMS, 7, 0.0, "0", None, D(0)):
            expect("invalid_period", CALLERS[name], good_bars(), anchor_ms=bad)
        CALLERS[name](good_bars(), period_ms=CMS, anchor_ms=0, k=1)     # periodo = 1 barra ammesso (k=1 per opening_range)
        CALLERS[name](good_bars(), period_ms=4 * CMS, anchor_ms=3 * CMS)

    def test_session_bool_values_are_refused_even_when_numerically_valid(self):
        """Con candle_ms=1, True e False sono valori numericamente BUONI (1 e 0): solo il controllo di tipo li rifiuta."""
        bars = [Bar(k, D(10), D(11), D(9), D(10), D(1)) for k in range(8)]
        vwap_session(bars, 2, 0, candle_ms=1)
        opening_range(bars, 2, 0, 1, candle_ms=1)
        vwap_session(bars, 1, 0, candle_ms=1)                                            # periodo di una barra: ammesso
        expect("invalid_period", vwap_session, bars, True, 0, candle_ms=1)               # True == 1
        expect("invalid_period", vwap_session, bars, 2, False, candle_ms=1)              # False == 0
        expect("invalid_period", opening_range, bars, True, 0, 1, candle_ms=1)
        expect("invalid_period", opening_range, bars, 2, False, 1, candle_ms=1)
        expect("invalid_period", opening_range, bars, 2, 0, True, candle_ms=1)           # k = True == 1
        for name, param in (("supertrend", "n"), ("atr_percentile", "n"), ("atr_percentile", "window"),
                            ("swing_levels", "left"), ("swing_levels", "right")):
            expect("invalid_period", CALLERS[name], bars, candle_ms=1, **{param: True})

    def test_session_parameters_are_checked_against_candle_ms(self):
        bars = [Bar(k * 5, D(10), D(11), D(9), D(10), D(1)) for k in range(12)]       # candle_ms = 5
        vwap_session(bars, 20, 5, candle_ms=5)
        expect("invalid_period", vwap_session, bars, 22, 0, candle_ms=5)               # 22 non multiplo di 5
        expect("invalid_period", vwap_session, bars, 20, 3, candle_ms=5)               # ancora non multipla
        expect("invalid_period", vwap_session, bars, 4, 0, candle_ms=5)                # periodo < candle_ms

    def test_opening_range_k_must_fit_the_period(self):
        opening_range(good_bars(), 4 * CMS, 0, 4, candle_ms=CMS)                       # k*candle == periodo: ammesso
        expect("invalid_period", opening_range, good_bars(), 4 * CMS, 0, 5, candle_ms=CMS)

    def test_open_time_bool_and_negative_are_refused(self):
        def series(times):
            return [Bar(t, D(10), D(11), D(9), D(10), D(1)) for t in times]
        for name in CALLERS:
            CALLERS[name](series([0, 1, 2, 3]), candle_ms=1, period_ms=2, anchor_ms=0)
            for times in ([False, 1, 2, 3], [0, True, 2, 3], [0, 1, True]):
                expect("invalid_bars", CALLERS[name], series(times), candle_ms=1, period_ms=2, anchor_ms=0)
            for k0 in (-6, -3, -1):
                expect("invalid_bars", CALLERS[name], [Bar((k0 + k) * CMS, D(10), D(11), D(9), D(10), D(1)) for k in range(6)])


# ============================================================ scale estreme (invarianza di scala)
BIGCTX = Context(prec=120, Emax=decimal.MAX_EMAX, Emin=decimal.MIN_EMIN)
BASE = bars_from(HI12, LO12, vols=[2, 0, 3, 1, 4, 2, 0, 5, 1, 1, 3, 2])


def rescale(bars, e):
    with localcontext(BIGCTX):
        return [Bar(b.open_time_ms, b.open.scaleb(e), b.high.scaleb(e), b.low.scaleb(e), b.close.scaleb(e), b.volume)
                for b in bars]


def _series(r):
    return tuple(getattr(r, f.name) for f in dataclasses.fields(r)) if dataclasses.is_dataclass(r) else (r,)


_a2 = o_atr(BASE, 2)
_st = o_supertrend(BASE, _a2, F(1))
_hi, _lo = o_opening_range(BASE, 4 * CMS, 0, 2)
_sw = o_swing(BASE, 2, 1)
# nome -> (calcolo, serie attese a scala 1, grado: 1 = scala col prezzo, 0 = indipendente dalla scala)
SCALE_CASES = {
    "supertrend": (lambda b: supertrend(b, 2, D(1), candle_ms=CMS), _st, (1, 0)),
    "atr_percentile": (lambda b: atr_percentile(b, 2, 3, candle_ms=CMS), (o_atr_pct(BASE, 2, 3),), (0,)),
    "vwap_session": (lambda b: vwap_session(b, 4 * CMS, 0, candle_ms=CMS), (o_vwap(BASE, 4 * CMS, 0),), (1,)),
    "opening_range": (lambda b: opening_range(b, 4 * CMS, 0, 2, candle_ms=CMS), (_hi, _lo), (1, 1)),
    "swing_levels": (lambda b: swing_levels(b, 2, 1, candle_ms=CMS), _sw, (1, 1, 0, 0)),
}
MUST_WORK = (-100_000, -300, 300, 100_000)
MAY_REFUSE = (-10**9, -1_000_100, -1_000_020, -999_990, -600_000, 600_000, 999_990, 999_999, 1_000_010, 1_000_100, 10**9)


def assert_scaled(got_series, want_series, degrees, e, ctx):
    for si, (gs, ws, deg) in enumerate(zip(got_series, want_series, degrees)):
        assert len(gs) == len(ws), (ctx, si)
        for i, (g, w) in enumerate(zip(gs, ws)):
            if w is None:
                assert g is None, (ctx, si, i)
            elif deg == 0 and isinstance(w, int):
                assert type(g) is int and g == w, (ctx, si, i, g)
            else:
                assert g is not None and type(g) is Decimal, (ctx, si, i, g)
                with localcontext(BIGCTX):
                    unscaled = Fraction(g.scaleb(-e * deg))
                assert abs(unscaled - w) <= Fraction(1, 10**30) * max(abs(w), Fraction(1, 10**20)), (ctx, si, i, g)


class TestExtremeScales:
    @pytest.mark.parametrize("name", list(SCALE_CASES))
    @pytest.mark.parametrize("e", MUST_WORK)
    def test_supported_range_is_correct(self, name, e):
        fn, want, deg = SCALE_CASES[name]
        assert_scaled(_series(fn(rescale(BASE, e))), want, deg, e, (name, e))

    @pytest.mark.parametrize("name", list(SCALE_CASES))
    @pytest.mark.parametrize("e", MAY_REFUSE)
    def test_beyond_range_correct_or_typed(self, name, e):
        fn, want, deg = SCALE_CASES[name]
        try:
            got = _series(fn(rescale(BASE, e)))
        except ValueError as exc:
            assert str(exc) == "numeric_out_of_range", (name, e, str(exc))
            return
        assert_scaled(got, want, deg, e, (name, e))

    @pytest.mark.parametrize("name", ["supertrend", "atr_percentile", "vwap_session"])
    def test_refusal_really_happens_and_is_clean(self, name):
        fn = SCALE_CASES[name][0]
        refused = 0
        for e in MAY_REFUSE:
            try:
                fn(rescale(BASE, e))
            except ValueError as exc:
                refused += 1
                assert str(exc) == "numeric_out_of_range"
                assert exc.__cause__ is None and exc.__suppress_context__ is True
        assert refused >= 3, (name, refused)

    def test_ambient_traps_of_the_caller_do_not_matter(self):
        with localcontext() as c:
            c.traps[decimal.Overflow] = False
            c.traps[decimal.Underflow] = False
            c.Emax, c.Emin = decimal.MAX_EMAX, decimal.MIN_EMIN
            expect("numeric_out_of_range", vwap_session, rescale(BASE, 10**9), 4 * CMS, 0, candle_ms=CMS)
            expect("numeric_out_of_range", vwap_session, rescale(BASE, -1_000_100), 4 * CMS, 0, candle_ms=CMS)


# ============================================================ contesto, forma, immutabilita'
def _everything(bars):
    return (supertrend(bars, 3, D("2.5"), candle_ms=CMS), atr_percentile(bars, 3, 4, candle_ms=CMS),
            vwap_session(bars, 4 * CMS, CMS, candle_ms=CMS), opening_range(bars, 4 * CMS, CMS, 2, candle_ms=CMS),
            swing_levels(bars, 2, 2, candle_ms=CMS))


class TestContextShapeImmutability:
    def test_decimal_context_independence(self):
        bars = next(b for n, b in DATASETS if n == "long-3")
        base = _everything(bars)
        with localcontext() as c:
            c.prec = 5
            c.rounding = ROUND_UP
            assert _everything(bars) == base
        with localcontext() as c:
            c.prec = 200
            c.traps[decimal.InvalidOperation] = False
            assert _everything(bars) == base
        assert getcontext().prec == 28

    def test_inputs_not_mutated_deterministic_tuple_equals_list(self):
        bars = next(b for n, b in DATASETS if n == "long-2")
        lst = list(bars)
        snap = copy.deepcopy(lst)
        a = _everything(lst)
        assert lst == snap and _everything(lst) == a and _everything(tuple(lst)) == a

    def test_shapes(self):
        bars = good_bars(30)
        assert type(atr_percentile(bars, 3, 3, candle_ms=CMS)) is tuple and type(vwap_session(bars, 4 * CMS, 0, candle_ms=CMS)) is tuple
        results = {
            lv.SupertrendSeries: (supertrend(bars, 3, D(1), candle_ms=CMS), ("line", "direction")),
            lv.OpeningRangeSeries: (opening_range(bars, 4 * CMS, 0, 2, candle_ms=CMS), ("high", "low")),
            lv.SwingSeries: (swing_levels(bars, 2, 1, candle_ms=CMS), ("high", "low", "high_time_ms", "low_time_ms")),
        }
        for cls, (r, names) in results.items():
            assert type(r) is cls and tuple(f.name for f in dataclasses.fields(cls)) == names
            for nme in names:
                assert type(getattr(r, nme)) is tuple and len(getattr(r, nme)) == 30
            with pytest.raises(dataclasses.FrozenInstanceError):
                setattr(r, names[0], ())

    def test_signatures(self):
        for fn in (supertrend, atr_percentile, vwap_session, opening_range, swing_levels):
            params = inspect.signature(fn).parameters
            assert params["candle_ms"].kind is inspect.Parameter.KEYWORD_ONLY, fn.__name__
            assert all(p.default is inspect.Parameter.empty for p in params.values()), fn.__name__
        with pytest.raises(TypeError):
            swing_levels(good_bars(), 2, 1, CMS)
        with pytest.raises(TypeError):
            vwap_session(good_bars(), 4 * CMS, 0)

    def test_series_types(self):
        bars = good_bars(40)
        st = supertrend(bars, 2, D(1), candle_ms=CMS)
        assert all(d is None or (type(d) is int and d in (-1, 1)) for d in st.direction)
        sw = swing_levels(bars, 1, 1, candle_ms=CMS)
        assert all(t is None or type(t) is int for t in sw.high_time_ms + sw.low_time_ms)
        for s in (st.line, sw.high, sw.low):
            assert all(x is None or (type(x) is Decimal and not (x == 0 and x.is_signed())) for x in s)


# ============================================================ purezza e prestazioni
class TestPurityAndSpeed:
    src = Path(lv.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    def test_imports(self):
        mods = set()
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Import):
                mods |= {a.name for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                mods.add(n.module or "")
        assert mods <= {"__future__", "dataclasses", "decimal", "typing", "backend.v3.features.indicators"}, mods
        for n in ast.walk(self.tree):                          # solo nomi che indicators esporta davvero come API
            if isinstance(n, ast.ImportFrom) and n.module == "backend.v3.features.indicators":
                assert {a.name for a in n.names} <= {"Bar", "check_bars", "atr", "true_range", "_CTX"}, [a.name for a in n.names]

    def test_no_float_clock_random_io_numeric_defaults(self):
        names = {n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        attrs = {n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute)}
        assert not names & {"float", "open", "print", "eval", "exec", "compile", "__import__", "input"}
        assert not attrs & {"now", "today", "time", "random", "uniform", "urlopen", "system", "popen", "read_text", "environ"}
        assert [n for n in ast.walk(self.tree) if isinstance(n, ast.Constant) and type(n.value) is float] == []
        assert "float(" not in self.src
        for fn in ast.walk(self.tree):
            if isinstance(fn, ast.FunctionDef):
                for d in list(fn.args.defaults) + [x for x in fn.args.kw_defaults if x is not None]:
                    assert not (isinstance(d, ast.Constant) and isinstance(d.value, (int, float)) and not isinstance(d.value, bool)), fn.name

    def test_every_public_function_uses_the_pinned_context(self):
        for fn in ast.walk(self.tree):
            if isinstance(fn, ast.FunctionDef) and fn.name in {"supertrend", "atr_percentile", "vwap_session", "opening_range", "swing_levels"}:
                assert any(isinstance(n, ast.Name) and n.id == "_CTX" for n in ast.walk(fn)), fn.name

    def test_linear_time(self):
        bars = make_bars(random.Random(1), 4000, "walk")
        t = time.perf_counter()
        supertrend(bars, 14, D(3), candle_ms=CMS)
        atr_percentile(bars, 14, 100, candle_ms=CMS)
        vwap_session(bars, 96 * CMS, 0, candle_ms=CMS)
        opening_range(bars, 96 * CMS, 0, 4, candle_ms=CMS)
        swing_levels(bars, 3, 3, candle_ms=CMS)
        assert time.perf_counter() - t < 5.0
        # storico previsto: ~245 000 barre a 15m su 7 anni. Misurato sul modulo di Grok: 5000 barre 0,12 s, 10000 0,5 s,
        # 20000 1,75 s, 40000 6,7 s (x4 a ogni raddoppio: O(N*P)). Lineare: 60000 barre in ~0,2 s.
        big = make_bars(random.Random(2), 60000, "spiky")
        t = time.perf_counter()
        swing_levels(big, 2, 2, candle_ms=CMS)
        assert time.perf_counter() - t < 4.0, "swing_levels non lineare: scansione dei pivot futuri per ogni barra?"
        t = time.perf_counter()
        for fn in (lambda b: supertrend(b, 14, D(3), candle_ms=CMS), lambda b: vwap_session(b, 96 * CMS, 0, candle_ms=CMS),
                   lambda b: opening_range(b, 96 * CMS, 0, 4, candle_ms=CMS), lambda b: atr_percentile(b, 14, 50, candle_ms=CMS)):
            fn(big)
        assert time.perf_counter() - t < 20.0
