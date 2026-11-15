"""Pure, isolated FRRD research detector: no IO, trading, or runner hooks.

Outputs a *hypothesis*, never an order or risk decision. Input bars are the
existing Brain V3 Decimal Bar objects. Only bars CLOSED at as_of_ms are used.
Fixed, pre-registered thresholds; no calibration from November trade outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Sequence

from backend.v3.features.indicators import Bar, _CTX, atr, check_bars, ema

M15 = 900_000
H1 = 3_600_000
H4 = 14_400_000
ATR_N = 14
EMA_N = 12
SWING_N = 8
REBOUND_ATR = Decimal("0.85")
STATES = (
    "CONTINUAZIONE_SHORT", "RIMBALZO_LOCALE",
    "INVERSIONE_CANDIDATA", "INCERTO",
)


@dataclass(frozen=True)
class Observation:
    as_of_ms: int
    state: str
    reason: str
    trend_1h: str
    trend_4h: str
    regime: str
    atr_bp: str | None
    rebound_atr: str | None
    break_up: bool
    break_down: bool

    def as_dict(self) -> dict:
        return {
            "as_of_ms": self.as_of_ms, "state": self.state,
            "reason": self.reason, "trend_1h": self.trend_1h,
            "trend_4h": self.trend_4h, "regime": self.regime,
            "atr_bp": self.atr_bp, "rebound_atr": self.rebound_atr,
            "break_up": self.break_up, "break_down": self.break_down,
            "advisory_only": True,
        }


def _uncertain(as_of_ms: int, reason: str, regime: str) -> Observation:
    return Observation(
        as_of_ms, "INCERTO", reason, "UNKNOWN", "UNKNOWN", regime,
        None, None, False, False,
    )


def _closed(
    bars: Sequence[Bar] | None, candle_ms: int, as_of_ms: int, minimum: int,
) -> tuple[Bar, ...] | None:
    """Require a fresh, contiguous closed prefix; ignore future valid bars.

    Never repair holes. Missing/stale input produces INCERTO, not a bearish
    default. Including future bars MUST NOT change a historical observation.
    """
    if not isinstance(bars, (list, tuple)) or any(type(b) is not Bar for b in bars):
        return None
    closed = tuple(b for b in bars if b.open_time_ms + candle_ms <= as_of_ms)
    if len(closed) < minimum:
        return None
    # Work only with a fixed causal lookback: an ancient data gap outside
    # the required indicator window must not contaminate later observations.
    closed = closed[-max(64, minimum):]
    try:
        check_bars(closed, candle_ms=candle_ms)
    except ValueError:
        return None
    last_end_ms = closed[-1].open_time_ms + candle_ms
    if not 0 <= as_of_ms - last_end_ms < candle_ms:
        return None
    return closed


def _trend(bars: tuple[Bar, ...]) -> str:
    closes = [b.close for b in bars]
    e = ema(closes, EMA_N)[-1]
    if e is None:
        return "UNKNOWN"
    if closes[-1] > e and closes[-1] > closes[-3]:
        return "UP"
    if closes[-1] < e and closes[-1] < closes[-3]:
        return "DOWN"
    return "NEUTRAL"


def observe(
    bars_15m: Sequence[Bar] | None,
    bars_1h: Sequence[Bar] | None,
    *,
    as_of_ms: int,
    bars_4h: Sequence[Bar] | None = None,
    regime: str = "UNKNOWN",
) -> Observation:
    """Classify *closed* historical market structure, without side effects.

    Two completed 15m closes must confirm an up/down structure break.
    REBOUND is local (does not imply a 4h trend reversal); candidate
    INVERSION requires upward 1h and non-bearish optional 4h context.
    No state here can veto a trade; the runner never imports this module.
    """
    if type(as_of_ms) is not int or as_of_ms <= 0:
        raise ValueError("invalid_as_of_ms")
    if type(regime) is not str or regime not in (
        "UNKNOWN", "EXPANSION", "TREND_DOWN", "TREND_UP", "RANGE",
        "SHOCK", "UNCERTAIN",
    ):
        raise ValueError("invalid_regime")
    m15 = _closed(bars_15m, M15, as_of_ms, 24)
    h1 = _closed(bars_1h, H1, as_of_ms, 14)
    if m15 is None:
        return _uncertain(as_of_ms, "missing_stale_or_invalid_15m", regime)
    if h1 is None:
        return _uncertain(as_of_ms, "missing_stale_or_invalid_1h", regime)
    h4 = None
    if bars_4h is not None:
        h4 = _closed(bars_4h, H4, as_of_ms, 14)
        if h4 is None:
            return _uncertain(as_of_ms, "missing_stale_or_invalid_4h", regime)

    try:
        with localcontext(_CTX):
            volatility = atr(m15, ATR_N, candle_ms=M15)[-1]
            if volatility is None or volatility <= 0:
                return _uncertain(as_of_ms, "atr_zero_or_unavailable", regime)
            hour = _trend(h1)
            four_hour = _trend(h4) if h4 is not None else "NOT_PROVIDED"
            previous = m15[-(SWING_N + 3):-2]  # fixed level BEFORE two confirmation bars
            if len(previous) != SWING_N + 1:
                return _uncertain(as_of_ms, "insufficient_swing_history", regime)
            ceiling = max(b.high for b in previous)
            floor = min(b.low for b in previous)
            p, q, r = m15[-3:]
            two_rising = p.close < q.close < r.close
            two_falling = p.close > q.close > r.close
            # Exclude confirmation bars themselves from the breakout reference.
            break_up = two_rising and q.close > ceiling and r.close > ceiling
            break_down = two_falling and q.close < floor and r.close < floor
            local_low = min(b.low for b in m15[-(SWING_N + 1):])
            rally = (r.close - local_low) / volatility
            bp = volatility / r.close * Decimal(10_000)
            rebound = two_rising and rally >= REBOUND_ATR
            atr_str = str(bp.quantize(Decimal("0.01")))
            rally_str = str(rally.quantize(Decimal("0.01")))

            if break_up and hour == "UP" and four_hour != "DOWN":
                state, reason = "INVERSIONE_CANDIDATA", "15m_break_up_twice_and_1h_up"
            elif rebound:
                state, reason = "RIMBALZO_LOCALE", (
                    "15m_recovery_against_4h_down"
                    if four_hour == "DOWN" else "15m_two_up_and_atr_recovery"
                )
            elif break_down and hour == "DOWN" and four_hour != "UP":
                state, reason = "CONTINUAZIONE_SHORT", "15m_break_down_twice_and_1h_down"
            elif break_down and four_hour == "UP":
                state, reason = "INCERTO", "higher_tf_conflict_against_short"
            elif break_up and hour == "DOWN":
                state, reason = "INCERTO", "15m_up_break_but_1h_down"
            else:
                state, reason = "INCERTO", "no_confirmed_structure"
            return Observation(
                as_of_ms, state, reason, hour, four_hour, regime,
                atr_str, rally_str, break_up, break_down,
            )
    except (ArithmeticError, ValueError):
        return _uncertain(as_of_ms, "numeric_out_of_range", regime)
