"""S07: strict breakout of the previous Donchian channel, optional EMA filter."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

from backend.v3.features.indicators import Bar, check_bars, donchian, ema
from backend.v3.detectors.common import RiskSpec, build_candidates, check_candle_ms, check_risk, check_symbol


@dataclass(frozen=True)
class DonchianParams:
    n: int
    trend_ema_n: Optional[int]


def detect_donchian_breakout(symbol: str, bars: Sequence[Bar], params: DonchianParams,
                             risk: RiskSpec, *, candle_ms: int):
    check_candle_ms(candle_ms)
    check_symbol(symbol)
    if type(params) is not DonchianParams:
        raise ValueError("invalid_params")
    if type(params.n) is not int or params.n < 1:
        raise ValueError("invalid_params")
    if params.trend_ema_n is not None and (type(params.trend_ema_n) is not int or params.trend_ema_n < 1):
        raise ValueError("invalid_params")
    check_risk(risk)
    check_bars(bars, candle_ms=candle_ms)
    dc = donchian(bars, params.n, candle_ms=candle_ms)
    te = None if params.trend_ema_n is None else ema([b.close for b in bars], params.trend_ema_n)
    sides = [0] * len(bars)
    for i in range(1, len(bars)):
        high, low = dc.high[i - 1], dc.low[i - 1]
        if high is None or low is None:
            continue
        close = bars[i].close
        if close > high:
            side = 1
        elif close < low:
            side = -1
        else:
            continue
        if te is not None:
            if te[i] is None:
                continue
            if side == 1 and not close > te[i]:
                continue
            if side == -1 and not close < te[i]:
                continue
        sides[i] = side
    return build_candidates(symbol, bars, sides, strategy_id="S07", risk=risk, candle_ms=candle_ms)
