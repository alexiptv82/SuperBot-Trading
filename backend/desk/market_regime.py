"""Optional, entry-only market context. No I/O and no trading actions.

Input: CLOSED OHLCV bars [open_timestamp_ms, open, high, low, close, volume],
or a DataFrame with those named columns (timestamp, open, high, low, close,
volume). Oldest first; irregular, stale, incomplete or nonfinite data is neutral.
Thresholds are research defaults requiring paper replay, not calibrated edge.
"""
from __future__ import annotations

import threading
import time
import numpy as np
import pandas as pd


def _bars(value, interval, now_ms):
    if isinstance(value, pd.DataFrame):
        value = value.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]]
    a = np.asarray(value, dtype=float)
    if a.ndim != 2 or a.shape[1] < 6 or len(a) < 40:
        raise ValueError("insufficient OHLCV")
    a = a[-240:, :6].copy()
    if not np.isfinite(a).all() or np.any(a[:, 1:5] <= 0) or np.any(a[:, 5] < 0):
        raise ValueError("invalid OHLCV")
    if (np.any(np.diff(a[:, 0]) != interval) or np.any(a[:, 0] % interval)
            or a[-1, 0] + interval > now_ms
            or now_ms - (a[-1, 0] + interval) >= interval):
        raise ValueError("unordered, incomplete or stale bars")
    if np.any(a[:, 2] < np.maximum(a[:, 1], a[:, 4])) or np.any(a[:, 3] > np.minimum(a[:, 1], a[:, 4])):
        raise ValueError("invalid range")
    return a


def _rsi(close, period=14):
    delta = np.diff(close)
    result = np.full(len(close), np.nan)
    gain, loss = np.maximum(delta, 0), np.maximum(-delta, 0)
    up, down = gain[:period].mean(), loss[:period].mean()
    for i in range(period, len(close)):
        if i > period:
            up = (up * (period - 1) + gain[i - 1]) / period
            down = (down * (period - 1) + loss[i - 1]) / period
        result[i] = 50 if up == down == 0 else 100 if down == 0 else 100 - 100 / (1 + up / down)
    return result


def _reversal(h, m):
    window = h[-20:]
    rsi = _rsi(h[:, 4])[-20:]
    # Positional indices, never index labels; compare RSI at the price extreme
    # with RSI at the START of the window, as requested by the specification.
    low, high = int(np.argmin(window[:, 3])), int(np.argmax(window[:, 2]))
    bull_div = low >= 15 and window[low, 3] < window[0, 3] and rsi[low] > rsi[0]
    bear_div = high >= 15 and window[high, 2] > window[0, 2] and rsi[high] < rsi[0]
    momentum = float(m[-1, 4] / m[-5, 4] - 1)
    up_break = m[-1, 4] > m[-5:-1, 2].max()
    down_break = m[-1, 4] < m[-5:-1, 3].min()
    average_volume = float(m[-21:-1, 5].mean())
    volume = average_volume > 0 and m[-1, 5] >= 1.3 * average_volume
    # A fast breakout plus volume can detect a rebound before hourly EMA flips.
    up = momentum > 0.003 and (bull_div or (up_break and volume))
    down = momentum < -0.003 and (bear_div or (down_break and volume))
    return {"direction": 1 if up and not down else -1 if down and not up else 0,
            "bullish_divergence": bool(bull_div), "bearish_divergence": bool(bear_div),
            "volume_confirmed": bool(volume), "momentum_1h": momentum, "valid": True}


def detect_reversal(candles_1h, candles_15m, *, now_ms=None):
    """Return evidence and direction (-1/0/+1); invalid inputs are neutral."""
    try:
        now = time.time() * 1000 if now_ms is None else float(now_ms)
        if not np.isfinite(now):
            raise ValueError("invalid clock")
        return _reversal(_bars(candles_1h, 3_600_000, now),
                         _bars(candles_15m, 900_000, now))
    except Exception:
        return {"direction": 0, "bullish_divergence": False, "bearish_divergence": False,
                "volume_confirmed": False, "momentum_1h": 0.0, "valid": False}


def _adx(a, period=14):
    up, down = np.diff(a[:, 2]), -np.diff(a[:, 3])
    plus = np.where((up > down) & (up > 0), up, 0.0)
    minus = np.where((down > up) & (down > 0), down, 0.0)
    tr = np.maximum(a[1:, 2] - a[1:, 3],
                    np.maximum(abs(a[1:, 2] - a[:-1, 4]), abs(a[1:, 3] - a[:-1, 4])))
    atr, p, n = tr[:period].mean(), plus[:period].mean(), minus[:period].mean()
    dx = []
    for i in range(period - 1, len(tr)):
        if i >= period:
            atr, p, n = ((v * (period - 1) + x[i]) / period
                         for v, x in ((atr, tr), (p, plus), (n, minus)))
        dx.append(0.0 if atr == 0 or p + n == 0 else 100 * abs(p - n) / (p + n))
    result = float(np.mean(dx[:period]))
    for x in dx[period:]:
        result = (result * (period - 1) + x) / period
    return result


class MarketRegimeClassifier:
    """Per-symbol hysteresis; one observation per new closed 15m bar.

    Reversals require one observation; ordinary switches require two by default.
    Invalid data returns UNKNOWN/1.0 and clears that symbol's pending state.
    State is process-local, bounded and protected by a lock. Use one instance
    per bot, reused across cycles; no globals shared across wallets.
    """
    MODIFIERS = {"UNKNOWN": (1.0, 1.0), "RANGING": (1.0, 1.0),
                 "TRENDING_UP": (1.0, 0.7), "TRENDING_DOWN": (0.7, 1.0),
                 "REVERSING_UP": (1.0, 0.30), "REVERSING_DOWN": (0.30, 1.0),
                 "VOLATILE": (0.7, 0.7)}

    def __init__(self, confirmations=2, max_symbols=256):
        if confirmations < 1 or max_symbols < 1:
            raise ValueError("positive limits required")
        self.confirmations, self.max_symbols = int(confirmations), int(max_symbols)
        self._lock = threading.Lock()
        self._states = {}

    @classmethod
    def _result(cls, regime, valid=True):
        long, short = cls.MODIFIERS[regime]
        return {"regime": regime, "long_modifier": long, "short_modifier": short, "valid": valid}

    def classify(self, candles_1h, candles_15m, *, symbol, now_ms=None, adx=None):
        try:
            if not isinstance(symbol, str) or not symbol:
                return self._result("UNKNOWN", False)
            now = time.time() * 1000 if now_ms is None else float(now_ms)
            if not np.isfinite(now):
                raise ValueError("invalid clock")
            h, m = _bars(candles_1h, 3_600_000, now), _bars(candles_15m, 900_000, now)
            reversal = _reversal(h, m)["direction"]
            strength = _adx(h) if adx is None else float(adx)
            close = pd.Series(h[:, 4])
            trend = float(close.ewm(span=20, adjust=False).mean().iloc[-1]
                          - close.ewm(span=50, adjust=False).mean().iloc[-1])
            volatility = float(np.std(np.diff(np.log(m[-25:, 4]))))
            candidate = "RANGING"
            if reversal:
                candidate = "REVERSING_UP" if reversal > 0 else "REVERSING_DOWN"
            elif volatility > 0.02:
                candidate = "VOLATILE"
            elif strength is not None and np.isfinite(strength) and strength >= 25:
                if not np.isclose(trend, 0, atol=1e-12 * h[-1, 4]):
                    candidate = "TRENDING_UP" if trend > 0 else "TRENDING_DOWN"
            stamp = int(m[-1, 0])
            with self._lock:
                previous = self._states.get(symbol)
                if previous and stamp <= previous[0]:
                    return self._result(previous[1])
                if previous and stamp - previous[0] > 900_000:
                    previous = None  # no confirmation across missed bars
                current = previous[1] if previous else "UNKNOWN"
                count = previous[3] + 1 if previous and previous[2] == candidate else 1
                needed = 1 if candidate.startswith("REVERSING") else self.confirmations
                if count >= needed:
                    current = candidate
                if symbol not in self._states and len(self._states) >= self.max_symbols:
                    del self._states[next(iter(self._states))]
                self._states[symbol] = (stamp, current, candidate, count)
                return self._result(current)
        except Exception:
            if isinstance(symbol, str):
                with self._lock:
                    self._states.pop(symbol, None)
            return self._result("UNKNOWN", False)
