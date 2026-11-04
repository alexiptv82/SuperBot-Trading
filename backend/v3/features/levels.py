"""Session levels, supertrend, ATR percentile, opening range, swing pivots.

No I/O, network, clock, or randomness. Uses the same pinned Decimal context
as indicators.py. Values are not rounded. No look-ahead.

Known limits: partial sessions at the start of the series return None for
all bars of that session; volume-zero sessions return None until cumulative
volume becomes positive; swing pivots are confirmed only after `right` bars.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Optional

from backend.v3.features.indicators import _CTX, atr, check_bars


@dataclass(frozen=True)
class SupertrendSeries:
    line: tuple[Optional[Decimal], ...]
    direction: tuple[Optional[int], ...]


@dataclass(frozen=True)
class OpeningRangeSeries:
    high: tuple[Optional[Decimal], ...]
    low: tuple[Optional[Decimal], ...]


@dataclass(frozen=True)
class SwingSeries:
    high: tuple[Optional[Decimal], ...]
    low: tuple[Optional[Decimal], ...]
    high_time_ms: tuple[Optional[int], ...]
    low_time_ms: tuple[Optional[int], ...]


def _nz(d: Decimal) -> Decimal:
    return Decimal(0) if d == 0 else d


def _check_int(n, name="invalid_period"):
    if type(n) is not int or n < 1:
        raise ValueError(name)


def _check_session(period_ms, anchor_ms, candle_ms):
    if type(period_ms) is not int or period_ms < candle_ms or period_ms % candle_ms != 0:
        raise ValueError("invalid_period")
    if type(anchor_ms) is not int or anchor_ms < 0 or anchor_ms >= period_ms or anchor_ms % candle_ms != 0:
        raise ValueError("invalid_period")


def supertrend(bars, n, mult, *, candle_ms) -> SupertrendSeries:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    _check_int(n)
    if not isinstance(mult, Decimal) or not mult.is_finite() or mult <= 0:
        raise ValueError("invalid_period")
    check_bars(bars, candle_ms=candle_ms)
    try:
        with localcontext(_CTX):
            a = atr(bars, n, candle_ms=candle_ms)
            line = [None] * len(bars)
            direction = [None] * len(bars)
            if not bars:
                return SupertrendSeries(tuple(line), tuple(direction))
            i0 = n - 1
            if i0 >= len(bars):
                return SupertrendSeries(tuple(line), tuple(direction))
            hl2 = [(b.high + b.low) / 2 for b in bars]
            bu = [hl2[i] + mult * a[i] if a[i] is not None else None for i in range(len(bars))]
            bl = [hl2[i] - mult * a[i] if a[i] is not None else None for i in range(len(bars))]
            fu = [None] * len(bars)
            fl = [None] * len(bars)
            fu[i0] = bu[i0]
            fl[i0] = bl[i0]
            direction[i0] = -1
            line[i0] = fu[i0]
            for i in range(i0 + 1, len(bars)):
                fu[i] = bu[i] if bu[i] < fu[i - 1] or bars[i - 1].close > fu[i - 1] else fu[i - 1]
                fl[i] = bl[i] if bl[i] > fl[i - 1] or bars[i - 1].close < fl[i - 1] else fl[i - 1]
                if direction[i - 1] == -1:
                    direction[i] = 1 if bars[i].close > fu[i] else -1
                else:
                    direction[i] = -1 if bars[i].close < fl[i] else 1
                line[i] = fl[i] if direction[i] == 1 else fu[i]
            return SupertrendSeries(tuple(_nz(x) if x is not None else None for x in line), tuple(direction))
    except ArithmeticError:
        raise ValueError("numeric_out_of_range") from None


def atr_percentile(bars, n, window, *, candle_ms) -> tuple[Optional[Decimal], ...]:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    _check_int(n)
    _check_int(window)
    check_bars(bars, candle_ms=candle_ms)
    try:
        with localcontext(_CTX):
            a = atr(bars, n, candle_ms=candle_ms)
            out = [None] * len(bars)
            start = (n - 1) + (window - 1)
            for i in range(start, len(bars)):
                if a[i] is None:
                    continue
                cnt = sum(1 for j in range(i - window + 1, i + 1) if a[j] is not None and a[j] <= a[i])
                out[i] = _nz(Decimal(100) * Decimal(cnt) / Decimal(window))
            return tuple(out)
    except ArithmeticError:
        raise ValueError("numeric_out_of_range") from None


def vwap_session(bars, period_ms, anchor_ms, *, candle_ms) -> tuple[Optional[Decimal], ...]:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    _check_session(period_ms, anchor_ms, candle_ms)
    check_bars(bars, candle_ms=candle_ms)
    try:
        with localcontext(_CTX):
            out = [None] * len(bars)
            if not bars:
                return tuple(out)
            first_session = (bars[0].open_time_ms - anchor_ms) // period_ms
            first_session_start = anchor_ms + first_session * period_ms
            partial = bars[0].open_time_ms != first_session_start
            cum_tp_vol = Decimal(0)
            cum_vol = Decimal(0)
            cur_session = None
            for i, b in enumerate(bars):
                s = (b.open_time_ms - anchor_ms) // period_ms
                if s != cur_session:
                    cum_tp_vol = Decimal(0)
                    cum_vol = Decimal(0)
                    cur_session = s
                if partial and s == first_session:
                    continue
                tp = (b.high + b.low + b.close) / 3
                cum_tp_vol += tp * b.volume
                cum_vol += b.volume
                if cum_vol > 0:
                    out[i] = _nz(cum_tp_vol / cum_vol)
            return tuple(out)
    except ArithmeticError:
        raise ValueError("numeric_out_of_range") from None


def opening_range(bars, period_ms, anchor_ms, k, *, candle_ms) -> OpeningRangeSeries:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    _check_session(period_ms, anchor_ms, candle_ms)
    _check_int(k)
    if k * candle_ms > period_ms:
        raise ValueError("invalid_period")
    check_bars(bars, candle_ms=candle_ms)
    try:
        with localcontext(_CTX):
            hi = [None] * len(bars)
            lo = [None] * len(bars)
            if not bars:
                return OpeningRangeSeries(tuple(hi), tuple(lo))
            first_session = (bars[0].open_time_ms - anchor_ms) // period_ms
            first_session_start = anchor_ms + first_session * period_ms
            partial = bars[0].open_time_ms != first_session_start
            session_bars = {}
            for i, b in enumerate(bars):
                s = (b.open_time_ms - anchor_ms) // period_ms
                session_bars.setdefault(s, []).append((i, b))
            for s, items in session_bars.items():
                if partial and s == first_session:
                    continue
                if len(items) < k:
                    continue
                range_hi = max(b.high for _, b in items[:k])
                range_lo = min(b.low for _, b in items[:k])
                for idx, (i, _) in enumerate(items):
                    if idx >= k - 1:
                        hi[i] = _nz(range_hi)
                        lo[i] = _nz(range_lo)
            return OpeningRangeSeries(tuple(hi), tuple(lo))
    except ArithmeticError:
        raise ValueError("numeric_out_of_range") from None


def swing_levels(bars, left, right, *, candle_ms) -> SwingSeries:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    _check_int(left)
    _check_int(right)
    check_bars(bars, candle_ms=candle_ms)
    try:
        with localcontext(_CTX):
            hi = [None] * len(bars)
            lo = [None] * len(bars)
            hi_t = [None] * len(bars)
            lo_t = [None] * len(bars)
            cur_h = None
            cur_l = None
            for i in range(len(bars)):
                # il pivot candidato j e' valutato solo con barre <= i = j + right (nessun look-ahead)
                # e l'ultimo pivot confermato resta valido finche' non ne arriva un altro: una sola
                # passata, O(N * (left + right)), invece della scansione di tutti i pivot per ogni barra.
                j = i - right
                if j >= left:
                    left_max = max(bars[k].high for k in range(j - left, j))
                    right_max = max(bars[k].high for k in range(j + 1, j + right + 1))
                    if bars[j].high > left_max and bars[j].high >= right_max:
                        cur_h = j
                    left_min = min(bars[k].low for k in range(j - left, j))
                    right_min = min(bars[k].low for k in range(j + 1, j + right + 1))
                    if bars[j].low < left_min and bars[j].low <= right_min:
                        cur_l = j
                if cur_h is not None:
                    hi[i] = _nz(bars[cur_h].high)
                    hi_t[i] = bars[cur_h].open_time_ms
                if cur_l is not None:
                    lo[i] = _nz(bars[cur_l].low)
                    lo_t[i] = bars[cur_l].open_time_ms
            return SwingSeries(tuple(hi), tuple(lo), tuple(hi_t), tuple(lo_t))
    except ArithmeticError:
        raise ValueError("numeric_out_of_range") from None
