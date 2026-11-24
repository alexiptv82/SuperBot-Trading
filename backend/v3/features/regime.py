"""Deterministic regime classifier for Brain V3.

No I/O, network, clock, or randomness. Uses the same pinned Decimal context
as indicators.py. Labels are closed-bar, no look-ahead, no hidden thresholds.

Known limits: early bars are UNCERTAIN until all input series are defined;
no hysteresis; no memory between bars.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Optional

from backend.v3.features.indicators import _CTX, adx, atr, check_bars, true_range
from backend.v3.features.levels import atr_percentile

REGIME_LABELS = ("TREND_UP", "TREND_DOWN", "RANGE", "EXPANSION", "SHOCK", "UNCERTAIN")


@dataclass(frozen=True)
class RegimeParams:
    shock_tr_mult: Decimal
    expansion_pct_min: Decimal
    adx_trend_min: Decimal
    adx_range_max: Decimal


def _check_int(n):
    if type(n) is not int or n < 1:
        raise ValueError("invalid_period")


def regime_labels(bars, atr_n, pct_window, adx_n, params, *, candle_ms) -> tuple[str, ...]:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    _check_int(atr_n)
    _check_int(pct_window)
    _check_int(adx_n)
    if type(params) is not RegimeParams:
        raise ValueError("invalid_threshold")
    for f in (params.shock_tr_mult, params.expansion_pct_min, params.adx_trend_min, params.adx_range_max):
        if not isinstance(f, Decimal) or not f.is_finite():
            raise ValueError("invalid_threshold")
    if params.shock_tr_mult <= 0:
        raise ValueError("invalid_threshold")
    if not (Decimal(0) <= params.expansion_pct_min <= Decimal(100)):
        raise ValueError("invalid_threshold")
    if params.adx_trend_min <= 0:
        raise ValueError("invalid_threshold")
    if params.adx_range_max < 0:
        raise ValueError("invalid_threshold")
    if params.adx_range_max >= params.adx_trend_min:
        raise ValueError("invalid_threshold")
    check_bars(bars, candle_ms=candle_ms)
    try:
        with localcontext(_CTX):
            tr = true_range(bars, candle_ms=candle_ms)
            a = atr(bars, atr_n, candle_ms=candle_ms)
            p = atr_percentile(bars, atr_n, pct_window, candle_ms=candle_ms)
            ad = adx(bars, adx_n, candle_ms=candle_ms)
            out = []
            for i in range(len(bars)):
                if a[i] is None or p[i] is None or ad.plus_di[i] is None or ad.minus_di[i] is None or ad.adx[i] is None:
                    out.append("UNCERTAIN")
                    continue
                if tr[i] > params.shock_tr_mult * a[i]:
                    out.append("SHOCK")
                    continue
                if p[i] >= params.expansion_pct_min:
                    out.append("EXPANSION")
                    continue
                if ad.adx[i] >= params.adx_trend_min:
                    if ad.plus_di[i] > ad.minus_di[i]:
                        out.append("TREND_UP")
                        continue
                    if ad.minus_di[i] > ad.plus_di[i]:
                        out.append("TREND_DOWN")
                        continue
                if ad.adx[i] <= params.adx_range_max:
                    out.append("RANGE")
                    continue
                out.append("UNCERTAIN")
            return tuple(out)
    except ArithmeticError:
        raise ValueError("numeric_out_of_range") from None
