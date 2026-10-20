"""Punteggio tecnico V2: aggiunge timeframe 1d, pattern candele, stagionalità.

Dalle candele 15m si ricavano 1h, 4h e 1d.
Punteggio 0-100 per il lato indicato + bonus stagionalità da seasonal.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from desk.seasonal import get_seasonal

H1, H4, H1D = 3_600_000, 14_400_000, 86_400_000


def resample(arr: np.ndarray, tf_ms: int, bar_ms: int = 900_000) -> np.ndarray:
    if len(arr) == 0:
        return np.empty((0, 6))
    per = tf_ms // bar_ms
    key = arr[:, 0].astype(np.int64) // tf_ms
    out = []
    for k in np.unique(key):
        g = arr[key == k]
        if len(g) != per or int(g[-1, 0]) - int(g[0, 0]) != (per - 1) * bar_ms:
            continue
        out.append([k * tf_ms, g[0, 1], g[:, 2].max(), g[:, 3].min(), g[-1, 4], g[:, 5].sum()])
    return np.array(out, dtype=float) if out else np.empty((0, 6))


def ema(x: np.ndarray, n: int) -> np.ndarray:
    a = 2 / (n + 1)
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def rsi(c: np.ndarray, n: int = 14) -> float:
    d = np.diff(c)
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    au, ad = up[:n].mean(), dn[:n].mean()
    for i in range(n, len(d)):
        au, ad = (au * (n - 1) + up[i]) / n, (ad * (n - 1) + dn[i]) / n
    return 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)


def atr(b: np.ndarray, n: int = 14) -> float:
    h, l, c = b[:, 2], b[:, 3], b[:, 4]
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    return float(tr[-n:].mean())


def doji_pattern(b: np.ndarray) -> str:
    """Identifica pattern di inversione sull'ultima candela 1h."""
    if len(b) < 3:
        return ""
    o, h, l, c = b[-1, 1], b[-1, 2], b[-1, 3], b[-1, 4]
    body = abs(c - o)
    candle_range = h - l
    if candle_range == 0:
        return ""
    body_ratio = body / candle_range
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    if body_ratio < 0.1:
        return "doji"  # indecisione
    if lower_shadow > body * 2 and upper_shadow < body * 0.5:
        return "hammer"  # potenziale inversione long
    if upper_shadow > body * 2 and lower_shadow < body * 0.5:
        return "shooting_star"  # potenziale inversione short
    # engulfing
    if len(b) >= 2:
        po, pc = b[-2, 1], b[-2, 4]
        if c > o and pc < po and c > po and o < pc:
            return "bullish_engulfing"
        if c < o and pc > po and c < po and o > pc:
            return "bearish_engulfing"
    return ""


@dataclass
class Reading:
    symbol: str
    price: float
    side: int = 0
    score: int = 0
    long_score: int = 0
    short_score: int = 0
    atr_pct: float = 0.0
    sl_pct: float = 0.01
    tp_pct: float = 0.02
    facts: dict = field(default_factory=dict)
    why: list = field(default_factory=list)
    seasonal_note: str = ""
    pattern: str = ""
    trade_type: str = "medio"   # "scalp" se segnale su 15m/1h, "medio" se su 4h/1d


DAILY_MIN_BARS = 200  # EMA50 contro EMA200 su barre 1d vere: con meno storia il trend 1d resta ASSENTE


def closed_daily(rows, now_ms: int) -> np.ndarray:
    """Barre giornaliere CHIUSE da righe BitGet [ts_apertura, o, h, l, c, vol].

    Tiene solo una serie regolare: passo esatto di 1 giorno, nessun buco, nessun duplicato. La barra del
    giorno in corso (ts + 1 giorno > now_ms) viene tolta. Qualunque anomalia -> array vuoto: il trend 1d
    resta assente come prima, invece di essere calcolato su dati sbagliati."""
    try:
        arr = np.array([[float(x) for x in r[:6]] for r in rows], dtype=float)
    except (TypeError, ValueError, IndexError):
        return np.empty((0, 6))
    if arr.ndim != 2 or len(arr) == 0 or not np.isfinite(arr).all():
        return np.empty((0, 6))
    arr = arr[np.argsort(arr[:, 0], kind="stable")]
    arr = arr[arr[:, 0] + H1D <= now_ms]
    if len(arr) == 0:
        return np.empty((0, 6))
    if len(arr) > 1 and not (np.diff(arr[:, 0]) == H1D).all():
        return np.empty((0, 6))
    return arr


def read_symbol(symbol: str, arr15: np.ndarray, now_ms: int | None = None,
                daily: np.ndarray | None = None, price: float | None = None) -> Reading | None:
    """`arr15`: barre 15m CHIUSE. `daily`: barre 1d chiuse (vedi `closed_daily`); senza, il 1d si ricava dalle
    15m come prima (con ~10 giorni di storia resta assente). `price`: ultimo prezzo (barra in formazione)."""
    b1 = resample(arr15, H1)
    b4 = resample(arr15, H4)
    b1d = daily if daily is not None and len(daily) >= DAILY_MIN_BARS else resample(arr15, H1D)
    if len(b1) < 60 or len(b4) < 60:
        return None
    c1, c4 = b1[:, 4], b4[:, 4]
    price = float(arr15[-1, 4]) if price is None else float(price)
    e20, e50 = ema(c1, 20)[-1], ema(c1, 50)[-1]
    e50_4, e200_4 = ema(c4, 50)[-1], ema(c4, min(200, len(c4) - 1))[-1]
    r1h = rsi(c1)
    roc24 = float(c1[-1] / c1[-25] - 1) if len(c1) > 25 else 0.0
    hi20, lo20 = float(b1[-21:-1, 2].max()), float(b1[-21:-1, 3].min())
    vol_ratio = float(b1[-1, 5] / max(1e-9, b1[-25:-1, 5].mean()))
    a_pct = atr(b1) / float(c1[-1])

    # --- timeframe 1d (contesto di lungo)
    daily_trend = 0
    daily_note = ""
    # Servono almeno DAILY_MIN_BARS giorni. Prima bastavano 30: con 30-49 barre EMA200 coincideva con EMA50 e
    # il trend risultava sempre "bear" (difetto latente); con 50-199 si confrontavano due medie quasi uguali.
    if len(b1d) >= DAILY_MIN_BARS:
        cd = b1d[:, 4]
        e50d = ema(cd, 50)[-1]
        e200d = ema(cd, 200)[-1]
        r1d = rsi(cd)
        daily_trend = 1 if e50d > e200d else -1
        daily_note = f"trend 1d {'bull' if daily_trend == 1 else 'bear'}, RSI1d {r1d:.0f}"

    # --- pattern candele
    pat = doji_pattern(b1)

    # --- stagionalità
    sea = get_seasonal(symbol, now_ms)

    comp = {"long": [], "short": []}
    sc = {"long": 0, "short": 0}

    def add(side_name, pts, why):
        sc[side_name] += pts
        comp[side_name].append(f"{why} (+{pts})")

    # trend 4h: 20 punti
    add("long" if e50_4 > e200_4 else "short", 20, "trend 4h")
    # trend 1h: 15 punti
    add("long" if e20 > e50 else "short", 15, "trend 1h")
    # trend 1d: 15 punti (se disponibile)
    if daily_trend != 0:
        add("long" if daily_trend == 1 else "short", 15, "trend 1d")
    # prezzo vs EMA50 1h: 8 punti
    add("long" if price > e50 else "short", 8, "prezzo vs EMA50")
    # momentum 24h: fino a 12 punti
    m = int(round(min(abs(roc24) / 0.03, 1.0) * 12))
    if m:
        add("long" if roc24 > 0 else "short", m, f"momento 24h {roc24:+.1%}")
    # rottura massimi/minimi: 10 punti
    if c1[-1] > hi20:
        add("long", 10, "rottura massimi 20h")
    elif c1[-1] < lo20:
        add("short", 10, "rottura minimi 20h")
    # RSI 1h: 8 punti
    if 50 <= r1h <= 70:
        add("long", 8, f"RSI {r1h:.0f}")
    elif 30 <= r1h < 50:
        add("short", 8, f"RSI {r1h:.0f}")
    # volume: 4 punti
    if vol_ratio > 1.3:
        add("long" if c1[-1] >= b1[-1, 1] else "short", 4, f"volumi x{vol_ratio:.1f}")

    # --- pattern candele: fino a 8 punti
    if pat == "hammer":
        add("long", 8, "hammer")
    elif pat == "bullish_engulfing":
        add("long", 8, "bullish engulfing")
    elif pat == "shooting_star":
        add("short", 8, "shooting star")
    elif pat == "bearish_engulfing":
        add("short", 8, "bearish engulfing")
    # doji = indecisione: riduce entrambi i lati
    elif pat == "doji":
        sc["long"] = max(0, sc["long"] - 5)
        sc["short"] = max(0, sc["short"] - 5)

    # overbought/oversold
    if r1h > 78:
        sc["long"] = max(0, sc["long"] - 12)
        comp["long"].append(f"ipercomprato RSI {r1h:.0f} (-12)")
    if r1h < 22:
        sc["short"] = max(0, sc["short"] - 12)
        comp["short"].append(f"ipervenduto RSI {r1h:.0f} (-12)")

    # --- stagionalità: bonus fino a 15 punti per lato
    if sea.long_bonus > 0:
        sc["long"] = min(100, sc["long"] + sea.long_bonus)
        comp["long"].append(f"stagionalità long +{sea.long_bonus}")
    if sea.short_bonus > 0:
        sc["short"] = min(100, sc["short"] + sea.short_bonus)
        comp["short"].append(f"stagionalità short +{sea.short_bonus}")

    ls, ss = min(100, sc["long"]), min(100, sc["short"])
    side = 1 if ls > ss else -1 if ss > ls else 0
    score = max(ls, ss)

    # sl più morbido in V2: 1.2x ATR (era 1.5x)
    sl = float(min(0.035, max(0.003, 1.2 * a_pct)))
    # trade_type: scalp se segnale deciso su TF basso con volume sopra media.
    # Soglia abbassata da 75→68 e vol_ratio da 1.5→1.2 per permettere scalp reali
    # ad alta leva (15-45x) come previsto dalla roadmap V2.
    # V2 aggressivo: quasi sempre scalp. Solo se segnale debolissimo o trend 4h
    # contrario e volume piatto si usa medio (setup multi-TF molto lento).
    trade_type = "scalp" if score >= 55 else "medio"

    return Reading(
        symbol=symbol, price=price, side=side, score=score, long_score=ls, short_score=ss,
        atr_pct=a_pct, sl_pct=sl, tp_pct=round(sl * 1.8, 5),
        facts={"rsi1h": round(r1h, 1), "ema20_50_1h": "su" if e20 > e50 else "giu",
               "ema50_200_4h": "su" if e50_4 > e200_4 else "giu", "roc24h": round(roc24, 4),
               "atr1h_pct": round(a_pct, 4), "vol_ratio": round(vol_ratio, 2),
               "daily_trend": daily_note},
        why=comp["long" if side == 1 else "short"],
        seasonal_note=sea.note,
        pattern=pat,
        trade_type=trade_type,
    )
