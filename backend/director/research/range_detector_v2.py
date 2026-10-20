"""Causal fixed-level candidate range detector for Phase 0 prereg v2.

Not a trading strategy. Two distinct steps:
(1) freeze reference bounds using *prior* closed bars only;
(2) look for FOUR alternating, separately confirmed rejections in later
    closed bars. Activation only after the final confirmation is closed.

This intentionally does not use future highs/lows to create trade levels.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from typing import Optional, Sequence
from director.contracts.outcomes import OHLC


@dataclass(frozen=True)
class FrozenRange:
    support: float
    resistance: float
    tolerance: float
    formed_by_ms: int
    bar_ms: int
    adx_1h: float


@dataclass(frozen=True)
class RangeActivation:
    activation_open_ms: int
    support: float
    resistance: float
    touch_sides: tuple[str, ...]
    touch_open_ms: tuple[int, ...]
    confirmation_ms: int


def _quantile(xs: list[float], p: float) -> float:
    ys = sorted(xs)
    u = (len(ys) - 1) * p
    i = int(u)
    return ys[i] * (1 - (u - i)) + ys[min(len(ys) - 1, i + 1)] * (u - i)


def freeze_levels(reference: Sequence[OHLC], *, bar_ms: int,
                  adx_1h: float, adx_asof_ms: int) -> Optional[FrozenRange]:
    """Reference must end with a fully closed bar; 96x5m or 32x15m."""
    lookback = {300_000: 96, 900_000: 32}.get(bar_ms)
    if lookback is None or len(reference) != lookback:
        raise ValueError("reference length/timeframe must be 8h of completed bars")
    if not all(isinstance(x, OHLC) for x in reference):
        raise TypeError("OHLC required")
    if any(b.open_ms - a.open_ms != bar_ms for a, b in zip(reference, reference[1:])):
        raise ValueError("reference has missing or reordered bars")
    last_closed_ms = reference[-1].open_ms + bar_ms
    if type(adx_asof_ms) is not int or adx_asof_ms > last_closed_ms or adx_asof_ms <= 0:
        raise ValueError("ADX lookahead or unavailable")
    if type(adx_1h) not in (int, float) or not isfinite(adx_1h) or adx_1h < 0:
        raise ValueError("invalid ADX")
    low = _quantile([b.low for b in reference], .10)
    high = _quantile([b.high for b in reference], .90)
    width = high - low
    if width <= 0 or width / reference[-1].close * 1e4 < 60:
        return None
    true_ranges = [max(b.high - b.low, abs(b.high - reference[i-1].close),
                       abs(b.low - reference[i-1].close))
                   for i, b in enumerate(reference) if i > 0]
    atr14 = sum(true_ranges[-14:]) / 14
    tol = max(2 * reference[-1].close / 10000, 0.1 * atr14)
    # A flat ADX AND reference displacement filter: neither alone is sufficient.
    if adx_1h >= 20 or abs(reference[-1].close - reference[0].close) > 0.5 * width:
        return None
    return FrozenRange(low, high, tol, last_closed_ms, bar_ms, float(adx_1h))


def detect_confirmation(levels: FrozenRange, observation: Sequence[OHLC]) -> Optional[RangeActivation]:
    """Use at most the NEXT 48 5m / 16 15m bars for qualification.

    A touch is confirmed only after a subsequent (1st or 2nd) CLOSED candle
    rejects the boundary toward the center by 2 tolerance units. Touches must
    alternate S/R/S/R or R/S/R/S; >=3 bars separation on each same edge.
    Any CLOSE beyond a frozen level +/- tolerance invalidates the attempt.
    """
    max_bars = 48 if levels.bar_ms == 300_000 else 16
    bars = list(observation[:max_bars])
    if not bars:
        return None
    if bars[0].open_ms != levels.formed_by_ms:
        raise ValueError("qualification starts after reference; no skipped bar")
    if any(b.open_ms - a.open_ms != levels.bar_ms for a, b in zip(bars, bars[1:])):
        raise ValueError("qualification has missing bars")
    active: list[tuple[str,int,int]] = []   # side, touch_index, confirmation_index
    pend: list[tuple[str,int]] = []
    last_touch: dict[str,int] = {}
    for i, bar in enumerate(bars):
        if bar.close < levels.support - levels.tolerance or bar.close > levels.resistance + levels.tolerance:
            return None
        accepted=[]
        for side, first_i in pend:
            if i - first_i > 2:
                continue
            if i <= first_i:
                accepted.append((side,first_i));continue
            passed=(bar.close >= levels.support + 2*levels.tolerance if side == "S"
                    else bar.close <= levels.resistance - 2*levels.tolerance)
            if passed:
                # Do not allow multiple nearly identical touches of same edge.
                if i - last_touch.get(side, -100) >= 3 and (not active or active[-1][0] != side):
                    active.append((side,first_i,i))
                    last_touch[side]=i
                    if len(active)==4:
                        if {s for s,_,_ in active} == {"S","R"}:
                            return RangeActivation(bar.open_ms+levels.bar_ms, levels.support,
                                                   levels.resistance,
                                                   tuple(s for s,_,_ in active),
                                                   tuple(bars[j].open_ms for _,j,_ in active),
                                                   bar.open_ms+levels.bar_ms)
                        return None
            else:
                accepted.append((side,first_i))
        pend=accepted
        if bar.low <= levels.support + levels.tolerance and bar.close >= levels.support:
            if i-last_touch.get("S",-100) >= 3 and (not active or active[-1][0]!="S"):
                pend.append(("S",i))
        if bar.high >= levels.resistance - levels.tolerance and bar.close <= levels.resistance:
            if i-last_touch.get("R",-100) >= 3 and (not active or active[-1][0]!="R"):
                pend.append(("R",i))
    return None
