"""Punteggio a regole (gratis, ripetibile) calcolato solo su candele CHIUSE.

Dalle candele 15m si ricavano 1h e 4h; il punteggio 0-100 dice quanto i dati sono allineati
con un long o con uno short. Non e' una previsione: e' un riassunto dei dati per il cervello.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

H1, H4 = 3_600_000, 14_400_000


def resample(arr: np.ndarray, tf_ms: int, bar_ms: int = 900_000) -> np.ndarray:
    """Barre complete di `tf_ms` da candele 15m (righe [t,o,h,l,c,v]). Le barre incomplete si scartano."""
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


@dataclass
class Reading:
    symbol: str
    price: float
    side: int = 0                    # +1 long, -1 short, 0 nessuno
    score: int = 0                   # 0-100 per il lato indicato
    long_score: int = 0
    short_score: int = 0
    atr_pct: float = 0.0
    sl_pct: float = 0.01
    tp_pct: float = 0.02
    facts: dict = field(default_factory=dict)
    why: list = field(default_factory=list)


def read_symbol(symbol: str, arr15: np.ndarray) -> Reading | None:
    b1, b4 = resample(arr15, H1), resample(arr15, H4)
    if len(b1) < 60 or len(b4) < 60:
        return None
    c1, c4 = b1[:, 4], b4[:, 4]
    price = float(arr15[-1, 4])
    e20, e50 = ema(c1, 20)[-1], ema(c1, 50)[-1]
    e50_4, e200_4 = ema(c4, 50)[-1], ema(c4, min(200, len(c4) - 1))[-1]
    r = rsi(c1)
    roc24 = float(c1[-1] / c1[-25] - 1) if len(c1) > 25 else 0.0
    hi20, lo20 = float(b1[-21:-1, 2].max()), float(b1[-21:-1, 3].min())
    vol_ratio = float(b1[-1, 5] / max(1e-9, b1[-25:-1, 5].mean()))
    a_pct = atr(b1) / float(c1[-1])
    comp = {"long": [], "short": []}
    sc = {"long": 0, "short": 0}

    def add(side, pts, why):
        sc[side] += pts
        comp[side].append(f"{why} (+{pts})")

    add("long" if e50_4 > e200_4 else "short", 25, "trend 4h")
    add("long" if e20 > e50 else "short", 20, "trend 1h")
    add("long" if price > e50 else "short", 10, "prezzo vs media 1h")
    m = int(round(min(abs(roc24) / 0.03, 1.0) * 15))
    if m:
        add("long" if roc24 > 0 else "short", m, f"momento 24h {roc24:+.1%}")
    if c1[-1] > hi20:
        add("long", 15, "rottura massimi 20h")
    elif c1[-1] < lo20:
        add("short", 15, "rottura minimi 20h")
    if 50 <= r <= 70:
        add("long", 10, f"RSI {r:.0f}")
    elif 30 <= r < 50:
        add("short", 10, f"RSI {r:.0f}")
    if r > 78:
        sc["long"] = max(0, sc["long"] - 10)
        comp["long"].append(f"ipercomprato RSI {r:.0f} (-10)")
    if r < 22:
        sc["short"] = max(0, sc["short"] - 10)
        comp["short"].append(f"ipervenduto RSI {r:.0f} (-10)")
    if vol_ratio > 1.3:
        add("long" if c1[-1] >= b1[-1, 1] else "short", 5, f"volumi x{vol_ratio:.1f}")
    ls, ss = min(100, sc["long"]), min(100, sc["short"])
    side = 1 if ls > ss else -1 if ss > ls else 0
    score = max(ls, ss)
    sl = float(min(0.03, max(0.004, 1.5 * a_pct)))
    return Reading(symbol, price, side, score, ls, ss, a_pct, sl, round(sl * 1.7, 5),
                   {"rsi1h": round(r, 1), "ema20_50_1h": "su" if e20 > e50 else "giu",
                    "ema50_200_4h": "su" if e50_4 > e200_4 else "giu", "roc24h": round(roc24, 4),
                    "atr1h_pct": round(a_pct, 4), "vol_ratio": round(vol_ratio, 2)},
                   comp["long" if side == 1 else "short"])
