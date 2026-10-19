"""Closed-bar features; all timestamps are UTC milliseconds, close exclusive."""
from dataclasses import dataclass
from .liquidable import finite


@dataclass(frozen=True)
class Bar:
    close_ms: int
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self):
        finite(self.close_ms, self.open, self.high, self.low, self.close)
        if type(self.close_ms) is not int or self.close_ms < 0 or self.low <= 0 or not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("invalid OHLC bar")


@dataclass(frozen=True)
class Features:
    bar_close_ms: int
    mark: float
    atr: float
    atr_change: float
    ema_slope: float
    rsi: float
    lower_break: bool
    upper_break: bool
    regime: str
    duration_ms: int
    since_peak_ms: int
    valid: bool
    reason: str


def extract(bars, *, asof_ms, opened_ms, peak_ms, interval_ms, max_age_ms, period=14):
    if any(type(x) is not int for x in (asof_ms, opened_ms, peak_ms, interval_ms, max_age_ms, period)) or not 0 <= opened_ms <= asof_ms or not opened_ms <= peak_ms <= asof_ms or interval_ms <= 0 or max_age_ms < 0 or period < 2:
        raise ValueError("invalid feature clock/window")
    closed = tuple(b for b in bars if b.close_ms <= asof_ms)
    times = [b.close_ms for b in closed]
    if times != sorted(set(times)):
        raise ValueError("bars must be ordered and unique")
    window = closed[-(period + 2):]
    reason = "ok"
    if len(window) < period + 2:
        reason = "warmup"
    elif asof_ms - window[-1].close_ms > max_age_ms:
        reason = "stale"
    elif any(b.close_ms - a.close_ms != interval_ms for a, b in zip(window, window[1:])):
        reason = "missing_bar"
    if reason != "ok":
        return Features(times[-1] if times else 0, closed[-1].close if closed else 0, 0, 0, 0, 50, False, False, "unknown", asof_ms-opened_ms, asof_ms-peak_ms, False, reason)
    tr = [max(b.high-b.low, abs(b.high-a.close), abs(b.low-a.close)) for a,b in zip(window,window[1:])]
    atr = sum(tr[-period:]) / period
    prev = sum(tr[-period-1:-1]) / period
    changes = [b.close-a.close for a,b in zip(window,window[1:])][-period:]
    gain, loss = sum(max(0,x) for x in changes), sum(max(0,-x) for x in changes)
    rsi = 50 if gain+loss == 0 else 100*gain/(gain+loss)
    ema = window[0].close
    slope = 0.0
    for b in window[1:]:
        new = ema + 2/(period+1)*(b.close-ema)
        slope, ema = new-ema, new
    prior = window[-period-1:-1]
    regime = "high_volatility" if prev > 0 and atr > 1.25*prev else ("trend" if abs(slope) > .2*atr else "range")
    return Features(window[-1].close_ms, window[-1].close, atr, atr-prev, slope, rsi, window[-1].close < min(b.low for b in prior), window[-1].close > max(b.high for b in prior), regime, asof_ms-opened_ms, asof_ms-peak_ms, True, reason)
