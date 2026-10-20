"""Shared outcome convention v1 for BOTH research replay and Claude's labeler.

Pure OHLC implementation, no trading, no I/O, no exchange integration. IMPORTANT:
The next closed candle after the signal supplies its OPEN as the entry price;
stop wins an OHLC tie. Round-trip cost_bp includes fees AND slippage and is
subtracted once from gross price movement. Never double charge slippage.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Optional, Sequence

BAR_HOUR_MS = 3_600_000
REASONS = ("STOP", "TARGET", "TIME", "UNRESOLVED")


@dataclass(frozen=True)
class OHLC:
    open_ms: int
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self):
        if type(self.open_ms) is not int or self.open_ms < 0:
            raise ValueError("open_ms must be UTC milliseconds")
        if not all(type(v) in (int, float) and isfinite(v) and v > 0 for v in
                   (self.open, self.high, self.low, self.close)):
            raise ValueError("OHLC prices must be finite positive")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("OHLC invalid high/low")


@dataclass(frozen=True)
class Outcome:
    reason: str
    entry: float
    exit: Optional[float]
    entry_ms: int
    exit_ms: Optional[int]
    bars_held: int
    gross_bp: Optional[float]
    net_bp: Optional[float]
    net_r: Optional[float]
    mfe_r: Optional[float]
    mae_r: Optional[float]
    stop_target_ambiguous: bool
    gap_through_stop: bool

    def as_payload(self) -> dict:
        return asdict(self)


def evaluate_path(*, signal_open_ms: int, bar_ms: int, side: str,
                  stop: float, target: Optional[float], bars: Sequence[OHLC],
                  max_hold_bars: int, cost_bp_roundtrip: float,
                  funding_bp_8h_long: float = 1.0) -> Outcome:
    """Score a pre-specified strategy idea from the first *complete* bar after signal.

    Bars are the consecutive, fully completed 5m/15m bars available to a labeler.
    Empty/incomplete history returns UNRESOLVED, never a fabricated time exit.
    Gap beyond stop fills at unfavorable OPEN; target fills at LIMIT target even
    on a favorable opening gap. MAE/MFE are OHLC bounds, NOT tick-order claims.
    Funding baseline: 1 bp per 8h for long only, same as existing paper engine;
    scenarios with signed real funding are a separate versioned extension.
    """
    if type(signal_open_ms) is not int or signal_open_ms < 0 or type(bar_ms) is not int or bar_ms <= 0:
        raise ValueError("invalid signal or bar timestamp")
    if side not in ("LONG", "SHORT") or type(max_hold_bars) is not int or max_hold_bars <= 0:
        raise ValueError("invalid side or horizon")
    if not all(type(v) in (int, float) and isfinite(v) and v >= 0 for v in
               (cost_bp_roundtrip, funding_bp_8h_long)):
        raise ValueError("nonnegative finite costs required")
    if not bars:
        return Outcome("UNRESOLVED", 0, None, signal_open_ms + bar_ms, None, 0,
                       None, None, None, None, None, False, False)
    if not all(isinstance(b, OHLC) for b in bars):
        raise ValueError("bars must be OHLC")
    if bars[0].open_ms != signal_open_ms + bar_ms:
        raise ValueError("LOOKAHEAD/GAP: entry must be next bar open")
    for a, b in zip(bars, bars[1:]):
        if b.open_ms != a.open_ms + bar_ms:
            raise ValueError("GAP: no interpolation of missing bars")
    entry = bars[0].open
    if not isinstance(stop, (int, float)) or not isfinite(stop) or stop <= 0:
        raise ValueError("invalid stop")
    if side == "LONG" and not stop < entry or side == "SHORT" and not stop > entry:
        raise ValueError("stop must be on adverse side of actual entry")
    if target is not None:
        if not isinstance(target, (int, float)) or not isfinite(target) or target <= 0:
            raise ValueError("invalid target")
        if side == "LONG" and not target > entry or side == "SHORT" and not target < entry:
            raise ValueError("target must be on favorable side")
    risk_bp = abs(entry - stop) / entry * 10_000
    mfe_bp, mae_bp = 0.0, 0.0
    reason, exit_price, held, ambiguous, gap = "UNRESOLVED", None, 0, False, False
    for held, b in enumerate(bars[:max_hold_bars], 1):
        if side == "LONG":
            mfe_bp = max(mfe_bp, (b.high - entry) / entry * 10_000)
            mae_bp = max(mae_bp, (entry - b.low) / entry * 10_000)
            hit_stop = b.low <= stop
            hit_target = target is not None and b.high >= target
            gap_stop = b.open < stop
        else:
            mfe_bp = max(mfe_bp, (entry - b.low) / entry * 10_000)
            mae_bp = max(mae_bp, (b.high - entry) / entry * 10_000)
            hit_stop = b.high >= stop
            hit_target = target is not None and b.low <= target
            gap_stop = b.open > stop
        if hit_stop:  # stop BEFORE TP, even if both touched
            reason, exit_price = "STOP", (min(stop, b.open) if side == "LONG" else max(stop, b.open))
            ambiguous, gap = bool(hit_target), bool(gap_stop)
            break
        if hit_target:
            reason, exit_price = "TARGET", target
            break
    else:
        if len(bars) >= max_hold_bars:
            reason, exit_price = "TIME", bars[max_hold_bars - 1].close
            held = max_hold_bars
        else:
            return Outcome("UNRESOLVED", entry, None, bars[0].open_ms, None,
                           len(bars), None, None, None,
                           round(mfe_bp / risk_bp, 7), round(mae_bp / risk_bp, 7), False, False)
    assert exit_price is not None
    exit_ms = bars[held - 1].open_ms + bar_ms
    gross = (exit_price / entry - 1) * (1 if side == "LONG" else -1) * 10_000
    funding = (funding_bp_8h_long * ((exit_ms - bars[0].open_ms) / BAR_HOUR_MS) / 8
               if side == "LONG" else 0.0)
    net = gross - cost_bp_roundtrip - funding
    return Outcome(reason, entry, exit_price, bars[0].open_ms, exit_ms, held,
                   round(gross, 7), round(net, 7), round(net / risk_bp, 7),
                   round(mfe_bp / risk_bp, 7), round(mae_bp / risk_bp, 7),
                   ambiguous, gap)
