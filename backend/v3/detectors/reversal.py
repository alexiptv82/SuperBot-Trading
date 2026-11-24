"""S05: strict percent-B extreme with MACD line and histogram confirmation."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from backend.v3.features.indicators import Bar, bollinger, check_bars, macd
from backend.v3.detectors.common import RiskSpec, build_candidates, check_candle_ms, check_risk, check_symbol


@dataclass(frozen=True)
class BbMacdParams:
    bb_n: int
    bb_k: Decimal
    pb_low: Decimal
    pb_high: Decimal
    macd_fast: int
    macd_slow: int
    macd_signal: int


def detect_bollinger_macd_reversal(symbol: str, bars: Sequence[Bar], params: BbMacdParams,
                                  risk: RiskSpec, *, candle_ms: int):
    check_candle_ms(candle_ms)
    check_symbol(symbol)
    if type(params) is not BbMacdParams:
        raise ValueError("invalid_params")
    if type(params.bb_n) is not int or params.bb_n < 2:
        raise ValueError("invalid_params")
    if not isinstance(params.bb_k, Decimal) or not params.bb_k.is_finite() or params.bb_k <= 0:
        raise ValueError("invalid_params")
    if not all(isinstance(v, Decimal) and v.is_finite() for v in (params.pb_low, params.pb_high)):
        raise ValueError("invalid_params")
    if not params.pb_low < params.pb_high:
        raise ValueError("invalid_params")
    for n in (params.macd_fast, params.macd_slow, params.macd_signal):
        if type(n) is not int or n < 1:
            raise ValueError("invalid_params")
    if not params.macd_fast < params.macd_slow:
        raise ValueError("invalid_params")
    check_risk(risk)
    check_bars(bars, candle_ms=candle_ms)
    bb = bollinger(bars, params.bb_n, params.bb_k, candle_ms=candle_ms)
    mc = macd(bars, params.macd_fast, params.macd_slow, params.macd_signal, candle_ms=candle_ms)
    sides = [0] * len(bars)
    for i in range(len(bars)):
        pb, line, hist = bb.percent_b[i], mc.line[i], mc.hist[i]
        if pb is None or line is None or hist is None:
            continue
        if pb < params.pb_low and hist > 0 and line < 0:
            sides[i] = 1
        elif pb > params.pb_high and hist < 0 and line > 0:
            sides[i] = -1
    return build_candidates(symbol, bars, sides, strategy_id="S05", risk=risk, candle_ms=candle_ms)
