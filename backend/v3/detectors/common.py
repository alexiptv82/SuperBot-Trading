"""Shared validation and unrounded ATR barriers; no execution or position state."""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext

from backend.v3.features.indicators import Bar, _CTX, atr
from backend.v3.learning.opportunity import Candidate


@dataclass(frozen=True)
class RiskSpec:
    atr_n: int
    stop_atr_mult: Decimal
    target_r_mult: Decimal
    cooldown_bars: int


def check_candle_ms(candle_ms) -> None:
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")


def check_symbol(symbol) -> None:
    if type(symbol) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,39}", symbol) is None:
        raise ValueError("invalid_symbol")


def check_risk(risk) -> None:
    if type(risk) is not RiskSpec:
        raise ValueError("invalid_risk")
    if type(risk.atr_n) is not int or risk.atr_n < 1:
        raise ValueError("invalid_risk")
    if type(risk.cooldown_bars) is not int or risk.cooldown_bars < 0:
        raise ValueError("invalid_risk")
    for value in (risk.stop_atr_mult, risk.target_r_mult):
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise ValueError("invalid_risk")


def build_candidates(symbol: str, bars: Sequence[Bar], sides: Sequence[int], *,
                     strategy_id: str, risk: RiskSpec, candle_ms: int) -> tuple[Candidate, ...]:
    """Validated inputs required; sides contain -1/0/1. Only emitted indices cool down."""
    if len(sides) != len(bars):
        raise ValueError("invalid_sides")
    try:
        with localcontext(_CTX):
            a = atr(bars, risk.atr_n, candle_ms=candle_ms)  # rule 1
            out = []
            last = None
            for i, side in enumerate(sides):
                if side == 0 or a[i] is None:  # rule 2
                    continue
                if last is not None and not (i - last > risk.cooldown_bars):  # rule 3
                    continue
                entry = bars[i].close  # rule 4
                distance = risk.stop_atr_mult * a[i]
                if side == 1:
                    stop = entry - distance
                    target = entry + risk.target_r_mult * distance
                    valid = 0 < stop < entry < target
                else:
                    stop = entry + distance
                    target = entry - risk.target_r_mult * distance
                    valid = 0 < target < entry < stop
                if not valid:
                    continue
                signal_time_ms = bars[i].open_time_ms + candle_ms  # rule 5
                candidate_id = f"{strategy_id}:{symbol}:{signal_time_ms}:{'L' if side == 1 else 'S'}"  # rule 6
                out.append(Candidate(candidate_id, symbol, side, signal_time_ms, entry, stop, target))  # rule 7
                last = i
            return tuple(out)
    except ArithmeticError:  # rule 8
        raise ValueError("numeric_out_of_range") from None
