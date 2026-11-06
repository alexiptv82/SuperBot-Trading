"""Advisory-only EMA crossover on *closed* 1h bars for classic portfolios.

No trading decisions, score adjustments, risk gates, alerts or mutable state.
This information is passed to Claude as an observation, never as a veto.
The 4h bias is reported only if a full 200-bar history is available.
"""
from __future__ import annotations

import numpy as np

HOUR_MS = 3_600_000
H4_MS = 14_400_000


def _closed_tail(bars: np.ndarray, now_ms: int, period_ms: int, minimum: int) -> np.ndarray | None:
    """Use only a contiguous fresh tail of complete, finite OHLCV bars."""
    if not isinstance(bars, np.ndarray) or bars.ndim != 2 or bars.shape[1] < 6:
        return None
    if len(bars) < minimum or not np.isfinite(bars).all():
        return None
    # Timestamp is the opening of a candle; any open/current candle is excluded.
    completed = bars[bars[:, 0] + period_ms <= now_ms]
    if len(completed) < minimum:
        return None
    tail = completed[-minimum:]
    ts = tail[:, 0]
    if not np.all(np.diff(ts) == period_ms):
        return None
    if not (np.all(tail[:, 1:5] > 0) and np.all(tail[:, 5] >= 0)
            and np.all(tail[:, 2] >= np.maximum(tail[:, 1], tail[:, 4]))
            and np.all(tail[:, 3] <= np.minimum(tail[:, 1], tail[:, 4]))
            and np.all(tail[:, 2] >= tail[:, 3])):
        return None
    age = now_ms - (int(tail[-1, 0]) + period_ms)
    if age < 0 or age >= period_ms:
        return None
    return tail


def advisory(bars_1h: np.ndarray, bars_4h: np.ndarray, now_ms: int | None, *, ema_fn) -> dict:
    """Return closed-vocabulary trend-change evidence; never controls entries/exits.

    event: ``UP_CROSS``/``DOWN_CROSS`` (EMA20/50 1h crossing on the
    latest completed hour), ``NONE``, or ``UNKNOWN`` on insufficient data.
    h4_bias: ``UP``/``DOWN`` on native EMA50/200 using >=200 valid closed
    4h bars, else ``UNKNOWN``. Bias is context, not confirmation or a veto.
    """
    result = {"event": "UNKNOWN", "h4_bias": "UNKNOWN", "asof_ms": None}
    if type(now_ms) is not int or now_ms <= 0:
        return result
    one = _closed_tail(bars_1h, now_ms, HOUR_MS, 60)
    if one is None:
        return result
    closes = one[:, 4]
    e20, e50 = ema_fn(closes, 20), ema_fn(closes, 50)
    old_gap, new_gap = e20[-2] - e50[-2], e20[-1] - e50[-1]
    if not np.isfinite([old_gap, new_gap]).all():
        return result
    # Floating-point EMA roundoff on perfectly flat candles is not a cross.
    old_gap = 0.0 if np.isclose(e20[-2], e50[-2], rtol=1e-12, atol=0) else old_gap
    new_gap = 0.0 if np.isclose(e20[-1], e50[-1], rtol=1e-12, atol=0) else new_gap
    if old_gap <= 0 < new_gap:
        event = "UP_CROSS"
    elif old_gap >= 0 > new_gap:
        event = "DOWN_CROSS"
    else:
        event = "NONE"
    result = {"event": event, "h4_bias": "UNKNOWN",
              "asof_ms": int(one[-1, 0]) + HOUR_MS}
    four = _closed_tail(bars_4h, now_ms, H4_MS, 200)
    if four is not None:
        cf = four[:, 4]
        e50_4, e200_4 = ema_fn(cf, 50)[-1], ema_fn(cf, 200)[-1]
        if np.isfinite([e50_4, e200_4]).all():
            result["h4_bias"] = ("NEUTRAL" if np.isclose(e50_4, e200_4, rtol=1e-12, atol=0)
                                 else "UP" if e50_4 > e200_4 else "DOWN")
    return result
