"""Indicatori e livelli in Python puro, sulle sole barre CHIUSE. Una barra e' (t, open, high, low, close, volume).

Servono a descrivere al modello il grafico come lo leggerebbe un trader: medie mobili, volatilita', RSI, massimi e
minimi di svolta (supporti e resistenze) e trend su piu' tempi. Nessun dato futuro: ogni valore usa solo barre gia' chiuse.
"""
import math


def ema_series(values: list, n: int) -> list:
    """EMA con seme = media semplice delle prime n; prima del seme None."""
    out = [None] * len(values)
    if n <= 0 or len(values) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(values[:n]) / n
    out[n - 1] = e
    for i in range(n, len(values)):
        e = values[i] * k + e * (1 - k)
        out[i] = e
    return out


def atr_pct(bars: list, n: int = 14):
    """ATR semplice (media del true range delle ultime n barre) in % dell'ultima chiusura."""
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(len(bars) - n, len(bars)):
        h, l, pc = bars[i][2], bars[i][3], bars[i - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    c = bars[-1][4]
    return (sum(trs) / n) / c * 100.0 if c > 0 else None


def rsi(closes: list, n: int = 14):
    """RSI di Wilder."""
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / n, losses / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0.0)) / n
        al = (al * (n - 1) + max(-d, 0.0)) / n
    if al == 0:
        return 100.0 if ag > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def pivots(bars: list, k: int = 3) -> tuple:
    """Massimi e minimi di svolta CONFERMATI: un massimo con i k massimi prima e i k dopo piu' bassi. Il pivot piu'
    recente possibile e' quindi a k barre dalla fine: non si guarda mai oltre l'ultima barra chiusa."""
    highs, lows = [], []
    for i in range(k, len(bars) - k):
        h, l = bars[i][2], bars[i][3]
        if all(h > bars[j][2] for j in range(i - k, i)) and all(h >= bars[j][2] for j in range(i + 1, i + k + 1)):
            highs.append((bars[i][0], h))
        if all(l < bars[j][3] for j in range(i - k, i)) and all(l <= bars[j][3] for j in range(i + 1, i + k + 1)):
            lows.append((bars[i][0], l))
    return highs, lows


def _distinct(levels: list, tol: float = 0.002) -> list:
    out = []
    for lv in levels:
        if all(abs(lv - o) / o > tol for o in out):
            out.append(lv)
    return out


def nearest_levels(price: float, bars: list, k: int = 3, n: int = 2) -> tuple:
    """(supporti sotto il prezzo, resistenze sopra il prezzo), i piu' vicini, fino a n per lato."""
    highs, lows = pivots(bars, k)
    pool = [p for _, p in highs] + [p for _, p in lows]
    below = sorted({p for p in pool if p < price}, reverse=True)
    above = sorted({p for p in pool if p > price})
    return _distinct(below)[:n], _distinct(above)[:n]


def trend_label(close: float, e20, e50) -> str:
    if e20 is None or e50 is None:
        return "?"
    if close > e20 > e50:
        return "su"
    if close < e20 < e50:
        return "giu"
    return "laterale"


def fmt_price(x: float) -> str:
    if x is None or not math.isfinite(x):
        return "?"
    a = abs(x)
    if a >= 1000:
        return "%.1f" % x
    if a >= 100:
        return "%.2f" % x
    if a >= 1:
        return "%.3f" % x
    return "%.5f" % x


def _pct(a: float, b: float):
    return None if not b else (a / b - 1.0) * 100.0


def _sgn(v, nd=2) -> str:
    return "?" if v is None else ("%+." + str(nd) + "f") % v


def summarize(sym: str, tf: dict) -> dict:
    """Riassunto di un simbolo. `tf` = {"15m": barre, "1h": barre, "4h": barre, "1d": barre} (solo chiuse, ordinate).
    Ritorna {"price", "line"} oppure None se mancano i dati minimi (almeno 60 barre da 15 minuti)."""
    b15 = tf.get("15m") or []
    if len(b15) < 60:
        return None
    c15 = [b[4] for b in b15]
    px = c15[-1]
    e20, e50 = ema_series(c15, 20)[-1], ema_series(c15, 50)[-1]
    vol = [b[5] for b in b15]
    vavg = sum(vol[-21:-1]) / 20.0 if len(vol) >= 21 else None
    vratio = (vol[-1] / vavg) if vavg else None
    hi24 = max(b[2] for b in b15[-96:])
    lo24 = min(b[3] for b in b15[-96:])
    chg = lambda n: _pct(px, c15[-1 - n]) if len(c15) > n else None
    parts = ["%s %s" % (sym, fmt_price(px)),
             "15m: e20 %s%% e50 %s%% atr %s%% rsi %s vol x%s" % (
                 _sgn(_pct(px, e20)), _sgn(_pct(px, e50)),
                 "?" if atr_pct(b15) is None else "%.2f" % atr_pct(b15),
                 "?" if rsi(c15) is None else "%.0f" % rsi(c15),
                 "?" if vratio is None else "%.1f" % vratio),
             "var 1h %s 4h %s 24h %s" % (_sgn(chg(4), 1), _sgn(chg(16), 1), _sgn(chg(96), 1)),
             "24h min-max %s-%s" % (fmt_price(lo24), fmt_price(hi24))]
    for name, key, k in (("1h", "1h", 3), ("4h", "4h", 2)):
        bars = tf.get(key) or []
        if len(bars) >= 30:
            cl = [b[4] for b in bars]
            a20, a50 = ema_series(cl, 20)[-1], ema_series(cl, 50)[-1]
            sup, res = nearest_levels(px, bars, k=k)
            r = rsi(cl)
            parts.append("%s: %s rsi %s S[%s] R[%s]" % (
                name, trend_label(cl[-1], a20, a50), "?" if r is None else "%.0f" % r,
                " ".join(fmt_price(x) for x in sup) or "-", " ".join(fmt_price(x) for x in res) or "-"))
    d = tf.get("1d") or []
    if len(d) >= 21:
        cl = [b[4] for b in d]
        d20 = ema_series(cl, 20)[-1]
        parts.append("1g: %s var7g %s" % ("su" if cl[-1] > d20 else "giu", _sgn(_pct(cl[-1], cl[-8]) if len(cl) > 7 else None, 1)))
    return {"price": px, "line": " | ".join(parts)}
