"""Fix B Portfolio Trend Alert V1 — observations ONLY, never closes orders.

One-hour CLOSED candles only. Monitor all currently SHORT symbols + BTC/ETH.
An alert requires >=3 UNIQUE symbols confirming the same hourly reversal.
Event priority is MAX, but per-position Claude review still observes 30m cooldown.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any
from desk.profit_guardian import position_key

HOUR_MS = 3_600_000
MAX_BAR_AGE_MS = 90 * 60_000
MIN_BARS = 60
MIN_RSI = 55.0
MIN_RSI_RISE = 2.0
MIN_VOLUME_RATIO = 1.5
TRIGGER_COUNT = 3


class AlertInputError(ValueError):
    pass


def _num(v: Any) -> float:
    if isinstance(v, bool):
        raise AlertInputError("non-numeric candle")
    try:
        x = float(v)
    except (TypeError, ValueError) as exc:
        raise AlertInputError("invalid candle") from exc
    if not math.isfinite(x):
        raise AlertInputError("non-finite candle")
    return x


def _ema(closes: list[float], span: int) -> list[float]:
    """SMA seed then chronological EMA. Always closed bars."""
    alpha = 2.0 / (span + 1)
    if len(closes) < span + 2:
        raise AlertInputError("insufficient EMA warmup")
    result = [float("nan")] * (span - 1)
    value = sum(closes[:span]) / span
    result.append(value)
    for c in closes[span:]:
        value = alpha * c + (1-alpha) * value
        result.append(value)
    return result


def _rsi_at(closes: list[float], index: int, period: int = 14) -> float:
    """Wilder RSI using history up to index (NO future candles)."""
    if index < period:
        raise AlertInputError("RSI warmup")
    changes = [closes[i] - closes[i-1] for i in range(1, index+1)]
    avg_gain = sum(max(x, 0) for x in changes[:period]) / period
    avg_loss = sum(max(-x, 0) for x in changes[:period]) / period
    for change in changes[period:]:
        avg_gain = (avg_gain * (period-1) + max(change, 0)) / period
        avg_loss = (avg_loss * (period-1) + max(-change, 0)) / period
    if avg_gain == avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0/(1+avg_gain/avg_loss)


def reversal_evidence(candles: list[dict], *, now_ms: int) -> dict:
    """Reclaim 1h EMA20/50 + bullish RSI rise + abnormal closed-bar volume.

    Invalidation/missing data -> signal=False, never hallucinate evidence.
    """
    invalid = {"signal":False, "reason":"invalid_or_stale_closed_bars"}
    if len(candles) < MIN_BARS or type(now_ms) is not int:
        return invalid
    try:
        recent = candles[-MIN_BARS:]
        times = [int(_num(c["close_ms"])) for c in recent]
        closes = [_num(c["close"]) for c in recent]
        volumes = [_num(c["volume"]) for c in recent]
        if (min(closes) <= 0 or min(volumes) < 0 or
            any(t % HOUR_MS for t in times) or
            any(times[i]-times[i-1]!=HOUR_MS for i in range(1,len(times))) or
            not 0 <= now_ms-times[-1] <= MAX_BAR_AGE_MS):
            return invalid
        e20, e50 = _ema(closes, 20), _ema(closes, 50)
        rsi_now = _rsi_at(closes,len(closes)-1)
        rsi_prev = _rsi_at(closes,len(closes)-2)
        normal_vol = sum(volumes[-21:-1]) / 20
        if normal_vol <= 0:
            return invalid
        vol_ratio = volumes[-1] / normal_vol
        reclaim = ((closes[-2] <= e20[-2] or closes[-2] <= e50[-2])
                   and closes[-1] > e20[-1] and closes[-1] > e50[-1])
        rsi_ok = rsi_now >= MIN_RSI and rsi_now-rsi_prev >= MIN_RSI_RISE
        vol_ok = vol_ratio >= MIN_VOLUME_RATIO
        evidence = {"signal":bool(reclaim and rsi_ok and vol_ok),
                    "reason":"confirmed_1h_bullish_reversal" if reclaim and rsi_ok and vol_ok
                    else "no_confirmed_reversal",
                    "close_ms":times[-1], "price":round(closes[-1],8),
                    "ema20":round(e20[-1],8), "ema50":round(e50[-1],8),
                    "rsi":round(rsi_now,3), "rsi_rise":round(rsi_now-rsi_prev,3),
                    "volume_ratio":round(vol_ratio,3), "ema_reclaim":reclaim}
        return evidence
    except (AlertInputError, KeyError, IndexError, TypeError, OverflowError, ValueError):
        return invalid


def detect_portfolio_alert(*, short_positions: list[dict],
                           hourly_closed_candles: dict[str, list[dict]],
                           now_ms: int) -> dict:
    """Return immutable-style decision data only, not an order.

    BTC/ETH are each counted once even if already present in short_positions.
    ALL SHORTS reviewed, including ROI <20, when 3 signals share a closed hour.
    """
    short_positions = [p for p in short_positions if p.get("side") == -1]
    keys = [position_key(p) for p in short_positions]
    symbols = sorted(set(["BTC","ETH"] + [str(p["symbol"]).upper() for p in short_positions]))
    evidence = {sym:reversal_evidence(hourly_closed_candles.get(sym,[]),now_ms=now_ms)
                for sym in symbols}
    buckets: dict[int,list[str]] = {}
    for sym,ev in evidence.items():
        if ev.get("signal") is True:
            buckets.setdefault(ev["close_ms"],[]).append(sym)
    # Different 1h bars are NOT a simultaneous market confirmation.
    bucket = max(buckets, key=lambda k:(len(buckets[k]),k)) if buckets else None
    triggered = sorted(buckets[bucket]) if bucket is not None else []
    active = bool(keys and len(triggered)>=TRIGGER_COUNT)
    fingerprint = "2026-fix-b-alert-v1:%s:%s" % (bucket,",".join(triggered))
    return {"schema":1,"mode":"ombra","applied":False,"active":active,
            "priority":"MAX" if active else "NONE",
            "event_id":hashlib.sha256(fingerprint.encode()).hexdigest()[:24] if active else None,
            "bar_close_ms":bucket if active else None,
            "triggering_symbols":triggered if active else [],
            "monitored_symbols":symbols,
            "position_keys":sorted(set(keys)) if active else [],
            "indicator_evidence":evidence,
            "threshold_symbols":TRIGGER_COUNT,
            "action":"REVIEW_SHORT_POSITIONS_ONLY" if active else "NO_ALERT",
            "execution":"NONE"}
