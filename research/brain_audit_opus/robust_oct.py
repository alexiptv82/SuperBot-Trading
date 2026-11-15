#!/usr/bin/env python3
"""Controllo di robustezza su un periodo DIVERSO (6/10 -> 10/11/2026), uscite su candele 15m (stop prima del target
nella stessa candela, stop in gap all'apertura): stop fisso 0,74% contro stop 1,5/2 x ATR15m a parita' di perdita in USDT."""
import calendar, sys, time
import numpy as np
SYMS = "BTCUSDT ETHUSDT SOLUSDT XRPUSDT BNBUSDT DOGEUSDT ADAUSDT LINKUSDT".split()
ms = lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%d")) * 1000  # noqa: E731
T0, T1, H, FEE, SLIP, RISK = ms("2026-10-06"), ms("2026-11-10"), 3_600_000, 6e-4, 2e-4, 72.0
def trade(a, k, side, s):
    fill = a[k, 1] * (1 + side * SLIP); stop, tgt = fill * (1 - side * s), fill * (1 + side * 2 * s)
    for j in range(k, min(len(a), k + 96)):
        o, h, l = a[j, 1:4]
        if (side == 1 and l <= stop) or (side == -1 and h >= stop):
            ex = (min(stop, o) if side == 1 else max(stop, o)) * (1 - side * SLIP)
            return side * (ex / fill - 1) - FEE * (1 + ex / fill)
        if (side == 1 and h >= tgt) or (side == -1 and l <= tgt):
            return side * (tgt / fill - 1) - FEE * (1 + tgt / fill)
    j = min(len(a) - 1, k + 95)
    return side * (a[j, 4] / fill - 1) - FEE * (1 + a[j, 4] / fill)
res, mkt = {}, {}
for sym in SYMS:
    a = np.loadtxt(f"{sys.argv[1]}/{sym}_15m.csv", delimiter=",", skiprows=1)
    tr = np.maximum(a[1:, 2], a[:-1, 4]) - np.minimum(a[1:, 3], a[:-1, 4])
    atr = np.r_[np.nan, np.convolve(tr / a[1:, 4], np.ones(14) / 14, "full")[:len(tr)]]
    i0, i1 = np.searchsorted(a[:, 0], [T0, T1]); mkt[sym] = round((a[i1, 4] / a[i0, 4] - 1) * 100, 1)
    for t in range(T0, T1, H):
        k = int(np.searchsorted(a[:, 0], t))
        for side in (-1, 1):
            for var, s in (("fisso_0.74%", 0.0074), ("1.5xATR", 1.5 * atr[k - 1]), ("2.0xATR", 2.0 * atr[k - 1])):
                r = trade(a, k, side, s)
                res.setdefault((side, var), []).append((sym, r / s, r * RISK / (s + 0.0016), atr[k - 1]))
print("variazione prezzo nel periodo %:", mkt)
for (side, var), v in sorted(res.items()):
    R = np.array([x[1] for x in v]); u = np.array([x[2] for x in v]); a_ = np.array([x[3] for x in v])
    hi = a_ >= np.quantile(a_, 2 / 3)
    bysym = {s: round(float(np.mean([x[1] for x in v if x[0] == s])), 2) for s in ("BTCUSDT", "ETHUSDT", "BNBUSDT")}
    print(f"{'SHORT' if side == -1 else 'LONG '} {var:11s} n={len(R)} win={np.mean(R > 0):.2f} R={R.mean():+.3f} usdt/op={u.mean():+.1f} | ATR alto R={R[hi].mean():+.3f} resto R={R[~hi].mean():+.3f} | R per simbolo {bysym}")
