"""Isolated, read-only Toro LONG study inspired by the frozen classical SHORT score.

NOT CONNECTED TO THE DESK RUNNER. It never opens, resizes or closes positions.
The 4h trend is supplied by the unchanged RC84 HTF reader; all 15m features use
fully closed, contiguous candles. No interpolation and no look-ahead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

BAR_MS = 900_000
MIN_CLOSED = 110  # > 24h (96 x 15m) plus indicator warmup
STRATEGY_ID = "toro_long_mirror_15m_shadow_v0"


@dataclass(frozen=True)
class MirrorReading:
    state: str  # NO_TRADE, LONG_CONTINUATION_CANDIDATE, LONG_BOUNCE_CANDIDATE
    reason: str
    score: int = 0
    asof_ms: int | None = None
    features: dict[str, Any] = field(default_factory=dict)


def _ema(x: np.ndarray, period: int) -> np.ndarray:
    """Frozen scoring rule: same recursive EMA seed/alpha as desk.signals.ema."""
    a = 2.0 / (period + 1)
    out = np.empty(len(x), dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def _rsi(x: np.ndarray, period: int = 14) -> float:
    """Wilder RSI as in desk.signals.rsi (calculated on 15m closes)."""
    changes = np.diff(x)
    ups, downs = np.maximum(changes, 0), np.maximum(-changes, 0)
    au, ad = float(ups[:period].mean()), float(downs[:period].mean())
    for i in range(period, len(changes)):
        au = (au * (period - 1) + ups[i]) / period
        ad = (ad * (period - 1) + downs[i]) / period
    return 100.0 if ad == 0 else float(100 - 100 / (1 + au / ad))


def _long_pattern(bars: np.ndarray) -> str:
    """Same classification order as the unchanged desk.signals.doji_pattern, applied to 15m.

    A candle the original would read as "shooting_star" (a SHORT pattern) is reported as such and
    earns no LONG points: it must never be re-read as a bullish engulfing (precedence preserved)."""
    o, h, l, c = [float(v) for v in bars[-1, 1:5]]
    body = abs(c - o)
    full = h - l
    if full <= 0:
        return ""
    if body / full < 0.1:
        return "doji"
    upper, lower = h - max(o, c), min(o, c) - l
    if lower > 2 * body and upper < 0.5 * body:
        return "hammer"
    if upper > 2 * body and lower < 0.5 * body:
        return "shooting_star"
    po, pc = [float(v) for v in (bars[-2, 1], bars[-2, 4])]
    if c > o and pc < po and c > po and o < pc:
        return "bullish_engulfing"
    return ""


def _no(reason: str, *, score: int = 0, asof: int | None = None, features: dict | None = None) -> MirrorReading:
    return MirrorReading("NO_TRADE", reason, score, asof, dict(features or {}))


def inspect_long_mirror_15m(
    symbol: str, candles: np.ndarray, now_ms: int, *, trend4h_state: str,
) -> MirrorReading:
    """Read-only study. An emitted CANDIDATE is NEVER a trading instruction.

    LONG weights mirror classical SHORT weights, but lower-timeframe evidence is
    deliberately measured on 15m, not the original 1h. A bounce (4h DOWN) is
    labelled for separate replay; it is *not* proof of trend reversal.
    """
    sym = str(symbol or "").upper()
    if sym.startswith(("XAU", "XAG")):
        return _no("calendario_metalli_da_validare")
    if trend4h_state not in {"UP", "DOWN"}:
        return _no("trend_4h_unknown")
    if candles is None:
        return _no("candele_assenti")
    try:
        a = np.asarray(candles, dtype=float)
    except (ValueError, TypeError):
        return _no("serie_illeggibile")
    if a.ndim != 2 or a.shape[1] < 6:
        return _no("serie_illeggibile")
    a = a[:, :6]
    # Exclude the in-progress candle BEFORE validating fields; its temporary
    # price spike must not affect the decision. An invalid timestamp is unsafe.
    if not np.isfinite(a[:, 0]).all():
        return _no("timestamp_non_valido")
    a = a[a[:, 0] + BAR_MS <= now_ms]
    if len(a) < MIN_CLOSED:
        return _no("storia_15m_insufficiente")
    if (not np.isfinite(a).all() or np.any(a[:, 1:5] <= 0) or np.any(a[:, 5] < 0)
            or np.any(a[:, 2] < np.maximum(a[:, 1], a[:, 4]))
            or np.any(a[:, 3] > np.minimum(a[:, 1], a[:, 4]))
            or np.any(a[:, 2] < a[:, 3])):
        return _no("ohlcv_non_valide")
    a = a[np.argsort(a[:, 0], kind="stable")]
    ts = a[:, 0].astype(np.int64)
    if np.any(ts % BAR_MS != 0):
        return _no("aperture_15m_non_allineate")
    # Identical closed duplicates are harmless, conflicting ones fail closed.
    dup = np.flatnonzero(np.diff(ts) == 0)
    if len(dup):
        if any(not np.array_equal(a[i], a[i+1]) for i in dup):
            return _no("duplicati_15m_in_conflitto")
        a = a[np.r_[True, np.diff(ts) > 0]]
        ts = a[:, 0].astype(np.int64)
    if len(a) < MIN_CLOSED or np.any(np.diff(ts[-MIN_CLOSED:]) != BAR_MS):
        return _no("storia_15m_interrotta")
    a = a[-MIN_CLOSED:]
    asof = int(a[-1, 0]) + BAR_MS
    if now_ms < asof or now_ms - asof >= BAR_MS:
        return _no("dati_15m_vecchi", asof=asof)

    closes, opens, highs, volumes = a[:, 4], a[:, 1], a[:, 2], a[:, 5]
    e20, e50 = _ema(closes, 20), _ema(closes, 50)
    ref = float(closes[-1])
    prev20_high = float(highs[-21:-1].max())
    roc24 = ref / float(closes[-97]) - 1
    rsi = _rsi(closes)
    vol_ratio = float(volumes[-1] / max(1e-9, volumes[-25:-1].mean()))
    pattern = _long_pattern(a)
    two_green = bool(np.all(closes[-2:] > opens[-2:]))
    ema_rising = bool(e20[-1] > e20[-3])

    # Frozen SHORT scoring weights, mirrored by side; 15m timeframe is the
    # deliberate experimental difference. No seasonal adjustment in this pilot.
    score = 20 if trend4h_state == "UP" else 0
    score += 15 if e20[-1] > e50[-1] else 0
    score += 8 if ref > e50[-1] else 0
    if roc24 > 0:
        score += int(round(min(roc24 / 0.03, 1.0) * 12))
    score += 10 if ref > prev20_high else 0
    score += 8 if 50 <= rsi <= 70 else 0
    score += 4 if vol_ratio > 1.3 and ref >= opens[-1] else 0
    score += 8 if pattern in {"hammer", "bullish_engulfing"} else 0
    if pattern == "doji":
        score = max(0, score - 5)
    if rsi > 78:
        score = max(0, score - 12)
    score = min(score, 100)
    features = {
        "strategy": STRATEGY_ID, "symbol": sym, "trend4h": trend4h_state,
        "ema20_above_ema50_15m": bool(e20[-1] > e50[-1]),
        "close_above_ema50_15m": bool(ref > e50[-1]),
        "close_above_ema20_15m": bool(ref > e20[-1]),
        "ema20_rising_15m": ema_rising,
        "roc24h": round(float(roc24), 6), "rsi15m": round(rsi, 2),
        "vol_ratio15m": round(vol_ratio, 3),
        "breakout_20x15m": bool(ref > prev20_high), "long_pattern_15m": pattern,
        "last_two_closed_green": two_green, "last_closed_ms": asof,
        "short_weights_unchanged": "4h20,ema15,close8,roc12,breakout10,rsi8,volume4,pattern8",
    }
    if not two_green or not ema_rising or ref <= e20[-1]:
        return _no("conferme_15m_non_sufficienti", score=score, asof=asof, features=features)
    if trend4h_state == "UP" and score >= 60:
        return MirrorReading("LONG_CONTINUATION_CANDIDATE", "rialzo_15m_confermato", score, asof, features)
    if trend4h_state == "DOWN" and vol_ratio > 1.3 and 40 <= rsi <= 72 and score >= 30:
        return MirrorReading("LONG_BOUNCE_CANDIDATE", "rimbalzo_contro_trend_da_validare", score, asof, features)
    return _no("soglia_o_contesto_insufficiente", score=score, asof=asof, features=features)
