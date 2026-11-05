"""S02: EMA cross from equality allowed, ADX minimum inclusive."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from backend.v3.features.indicators import Bar, adx, check_bars, ema
from backend.v3.detectors.common import RiskSpec, build_candidates, check_candle_ms, check_risk, check_symbol


@dataclass(frozen=True)
class EmaCrossParams:
    fast_n: int
    slow_n: int
    adx_n: int
    adx_min: Decimal


def detect_ema_cross_adx(symbol: str, bars: Sequence[Bar], params: EmaCrossParams,
                         risk: RiskSpec, *, candle_ms: int):
    check_candle_ms(candle_ms)
    check_symbol(symbol)
    if type(params) is not EmaCrossParams:
        raise ValueError("invalid_params")
    for n in (params.fast_n, params.slow_n, params.adx_n):
        if type(n) is not int or n < 1:
            raise ValueError("invalid_params")
    if not params.fast_n < params.slow_n:
        raise ValueError("invalid_params")
    if not isinstance(params.adx_min, Decimal) or not params.adx_min.is_finite() or params.adx_min < 0:
        raise ValueError("invalid_params")
    check_risk(risk)
    check_bars(bars, candle_ms=candle_ms)
    closes = [b.close for b in bars]
    ef = ema(closes, params.fast_n)
    es = ema(closes, params.slow_n)
    ax = adx(bars, params.adx_n, candle_ms=candle_ms)
    sides = [0] * len(bars)
    for i in range(1, len(bars)):
        if any(v is None for v in (ef[i - 1], es[i - 1], ef[i], es[i], ax.adx[i])):
            continue
        if ef[i - 1] <= es[i - 1] and ef[i] > es[i] and ax.adx[i] >= params.adx_min:
            sides[i] = 1
        elif ef[i - 1] >= es[i - 1] and ef[i] < es[i] and ax.adx[i] >= params.adx_min:
            sides[i] = -1
    return build_candidates(symbol, bars, sides, strategy_id="S02", risk=risk, candle_ms=candle_ms)
