"""Estrazione dei valori di `desk.signals.read_symbol` (codice del 13/10) e punteggio vettoriale.

Perche' esiste: `read_symbol` ricalcola tutto da 1000 candele 15m ogni volta (4,5 ms); su ~18 mesi e 26 simboli sono
ore. Qui i valori (EMA, RSI, ATR, ...) si estraggono UNA volta per barra con le stesse funzioni del bot (`ema`, `rsi`,
`atr`, `doji_pattern`) e il punteggio si calcola in forma vettoriale per tutte le varianti. L'equivalenza con la
funzione vera e' verificata dal test `test_equivalenza_base` (stessi interi, stessi float).

Finestra come in produzione: ultime 1000 candele 15m → 1h/4h con `resample`. Per non rifare `resample` per ogni barra
si ricampiona UNA volta tutta la serie e per ogni finestra si prendono le barre complete interamente dentro la finestra:
e' identico a ricampionare la finestra (un gruppo e' completo in entrambi i casi oppure in nessuno dei due).
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

from desk.seasonal import HALVING_CYCLE, HALVING_MS, MONTHLY_BIAS, get_seasonal
from desk.signals import H1, H1D, H4, atr, doji_pattern, ema, resample, rsi

BAR = 900_000
WIN = 1000
PAT = {"": 0, "doji": 1, "hammer": 2, "shooting_star": 3, "bullish_engulfing": 4, "bearish_engulfing": 5}
FEATS = ("price", "e20", "e50", "e50_4", "e200_4", "r1h", "roc24", "hi20", "lo20", "c1l", "o1l", "vol_ratio",
         "a_pct", "pat", "rsi_min12", "rsi_max12", "mom1h")
COMMODITIES = ("XAU", "XAG")


def rsi_series(c: np.ndarray, n: int = 14) -> np.ndarray:
    """RSI di Wilder per ogni chiusura: l'ultimo valore e' identico a `desk.signals.rsi(c)`."""
    d = np.diff(c)
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    out = np.full(len(c), np.nan)
    au, ad = up[:n].mean(), dn[:n].mean()
    out[n] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    for i in range(n, len(d)):
        au, ad = (au * (n - 1) + up[i]) / n, (ad * (n - 1) + dn[i]) / n
        out[i + 1] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out


class Series:
    """Una serie 15m e i suoi ricampionamenti completi."""

    def __init__(self, arr15: np.ndarray):
        self.a = arr15
        self.ts = arr15[:, 0].astype(np.int64)
        self.b1 = resample(arr15, H1)
        self.b4 = resample(arr15, H4)
        self.t1 = self.b1[:, 0].astype(np.int64) if len(self.b1) else np.empty(0, np.int64)
        self.t4 = self.b4[:, 0].astype(np.int64) if len(self.b4) else np.empty(0, np.int64)

    def window(self, i: int):
        lo = max(0, i - WIN + 1)
        t_first, t_last = int(self.ts[lo]), int(self.ts[i])

        def cut(b, t, tf):
            j0 = int(np.searchsorted(t, t_first, "left"))
            j1 = int(np.searchsorted(t, t_last - tf + BAR, "right"))
            return b[j0:j1]
        return cut(self.b1, self.t1, H1), cut(self.b4, self.t4, H4)


def extract(S: Series, i: int) -> Optional[tuple]:
    """Valori di `read_symbol` per la finestra che finisce alla barra i. None se `read_symbol` darebbe None."""
    b1, b4 = S.window(i)
    if len(b1) < 60 or len(b4) < 60:
        return None
    c1, c4 = b1[:, 4], b4[:, 4]
    price = float(S.a[i, 4])
    e20, e50 = ema(c1, 20)[-1], ema(c1, 50)[-1]
    e50_4, e200_4 = ema(c4, 50)[-1], ema(c4, min(200, len(c4) - 1))[-1]
    rs = rsi_series(c1)
    r1h = rs[-1]
    roc24 = float(c1[-1] / c1[-25] - 1) if len(c1) > 25 else 0.0
    hi20, lo20 = float(b1[-21:-1, 2].max()), float(b1[-21:-1, 3].min())
    vol_ratio = float(b1[-1, 5] / max(1e-9, b1[-25:-1, 5].mean()))
    a_pct = atr(b1) / float(c1[-1])
    pat = PAT[doji_pattern(b1)]
    last12 = rs[-12:]
    c1_short = c1[-5:]
    mom1h = float(c1_short[-1] / c1_short[0] - 1)
    return (price, float(e20), float(e50), float(e50_4), float(e200_4), float(r1h), roc24, hi20, lo20,
            float(c1[-1]), float(b1[-1, 1]), vol_ratio, float(a_pct), float(pat),
            float(np.nanmin(last12)), float(np.nanmax(last12)), mom1h)


def extract_symbol(arr15: np.ndarray) -> dict:
    """Tutte le barre di un simbolo → dict di array (NaN dove la lettura non esiste)."""
    S = Series(arr15)
    n = len(arr15)
    out = {k: np.full(n, np.nan) for k in FEATS}
    for i in range(WIN - 1, n):
        v = extract(S, i)
        if v is None:
            continue
        for k, x in zip(FEATS, v):
            out[k][i] = x
    out["ts"] = S.ts
    return out


# ------------------------------------------------------------------ stagionalita'
def seasonal_bonus(base: str, ts_end: np.ndarray, mode: str = "S1"):
    """(bonus long, bonus short) per ogni istante (ms, fine barra).
    S1 = funzione vera `get_seasonal` alla data storica (com'e' in produzione).
    S2 = fase del ciclo di oggi (ottobre 2026: "bear market", moltiplicatore −1,0) congelata, mese della barra."""
    tm_month = ((ts_end.astype("datetime64[ms]").astype("datetime64[M]").astype(int)) % 12) + 1
    L = np.zeros(len(ts_end), dtype=np.int64)
    S = np.zeros(len(ts_end), dtype=np.int64)
    if mode == "S1":
        months_since = np.maximum(0, (ts_end - HALVING_MS) // (30 * 24 * 3_600_000))
        keys = np.stack([tm_month, months_since], axis=1)
        uniq, inv = np.unique(keys, axis=0, return_inverse=True)
        inv = inv.reshape(-1)
        lb = np.zeros(len(uniq), dtype=np.int64)
        sb = np.zeros(len(uniq), dtype=np.int64)
        for u, (mo, ms_) in enumerate(uniq):
            first = int(np.nonzero(inv == u)[0][0])
            c = get_seasonal(base, int(ts_end[first]))
            lb[u], sb[u] = c.long_bonus, c.short_bonus
        return lb[inv], sb[inv]
    if mode == "S2":
        crypto = base not in COMMODITIES
        mult = -1.0 if crypto else 1.0
        biases = MONTHLY_BIAS.get(base, MONTHLY_BIAS["DEFAULT"])
        for mo in range(1, 13):
            eff = biases[mo - 1] * mult
            lb = min(15, int(eff / 4)) if eff > 0 else 0
            sb = min(15, int(abs(eff) / 4)) if eff <= 0 else 0
            m = tm_month == mo
            L[m], S[m] = lb, sb
        return L, S
    raise ValueError(mode)


# ------------------------------------------------------------------ punteggio vettoriale
def points(F: dict, w4: int = 20, extra_long=None, extra_short=None, sea_long=None, sea_short=None):
    """Punteggi long/short (interi) per matrici di valori F (stessa forma). Replica `read_symbol` del 13/10.
    `extra_*`: punti aggiunti prima delle riduzioni (come i punti P1). `sea_*`: bonus stagionalita'."""
    shape = F["price"].shape
    ok = np.isfinite(F["price"])
    g = {k: np.where(ok, F[k], 0.0) for k in FEATS}
    L = np.zeros(shape, dtype=np.int64)
    S = np.zeros(shape, dtype=np.int64)
    t4 = g["e50_4"] > g["e200_4"]
    L += np.where(t4, w4, 0)
    S += np.where(t4, 0, w4)
    t1 = g["e20"] > g["e50"]
    L += np.where(t1, 15, 0)
    S += np.where(t1, 0, 15)
    pv = g["price"] > g["e50"]
    L += np.where(pv, 8, 0)
    S += np.where(pv, 0, 8)
    m = np.rint(np.minimum(np.abs(g["roc24"]) / 0.03, 1.0) * 12).astype(np.int64)
    up = g["roc24"] > 0
    L += np.where(up, m, 0)
    S += np.where(up, 0, m)
    bu = g["c1l"] > g["hi20"]
    bd = (~bu) & (g["c1l"] < g["lo20"])
    L += np.where(bu, 10, 0)
    S += np.where(bd, 10, 0)
    r = g["r1h"]
    L += np.where((r >= 50) & (r <= 70), 8, 0)
    S += np.where((r >= 30) & (r < 50), 8, 0)
    if extra_long is not None:
        L += extra_long.astype(np.int64)
    if extra_short is not None:
        S += extra_short.astype(np.int64)
    vol = g["vol_ratio"] > 1.3
    vup = g["c1l"] >= g["o1l"]
    L += np.where(vol & vup, 4, 0)
    S += np.where(vol & ~vup, 4, 0)
    pat = g["pat"]
    L += np.where((pat == PAT["hammer"]) | (pat == PAT["bullish_engulfing"]), 8, 0)
    S += np.where((pat == PAT["shooting_star"]) | (pat == PAT["bearish_engulfing"]), 8, 0)
    dj = pat == PAT["doji"]
    L = np.where(dj, np.maximum(0, L - 5), L)
    S = np.where(dj, np.maximum(0, S - 5), S)
    L = np.where(r > 78, np.maximum(0, L - 12), L)
    S = np.where(r < 22, np.maximum(0, S - 12), S)
    if sea_long is not None:
        L = np.where(sea_long > 0, np.minimum(100, L + sea_long), L)
    if sea_short is not None:
        S = np.where(sea_short > 0, np.minimum(100, S + sea_short), S)
    L, S = np.minimum(100, L), np.minimum(100, S)
    L, S = np.where(ok, L, 0), np.where(ok, S, 0)
    side = np.where(L > S, 1, np.where(S > L, -1, 0))
    score = np.maximum(L, S)
    sl = np.minimum(0.035, np.maximum(0.003, 1.2 * g["a_pct"]))
    return L, S, side, score, sl, ok


def p1_extra_long(F: dict) -> np.ndarray:
    """Bonus rimbalzo di P1: RSI1h < 35 e momento 1h > +0,3% → +10 long."""
    ok = np.isfinite(F["price"])
    cond = ok & (F["r1h"] < 35) & (F["mom1h"] > 0.003)
    return np.where(cond, 10, 0)


def now_ms_str(ms: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ms / 1000))
