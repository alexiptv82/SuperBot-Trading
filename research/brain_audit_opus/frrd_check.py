#!/usr/bin/env python3
"""Esito degli SHORT (geometria di Brain) per stato FRRD all'ingresso, sul prototipo VERO del ramo FRRD (non modificato).
1h e 4h aggregate da 4 e 16 candele 15m chiuse contigue. Esplorativo: nessuna soglia viene scelta da questi numeri."""
import calendar, sys, time
from decimal import Decimal
import numpy as np
from backend.v3.features.indicators import Bar
from research.brain_frrd.detector import observe
SYMS = "BTCUSDT ETHUSDT SOLUSDT XRPUSDT BNBUSDT DOGEUSDT ADAUSDT LINKUSDT".split()
ms = lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%d %H:%M")) * 1000  # noqa: E731
FEE, SLIP, S = 6e-4, 2e-4, 0.0074
def bars(a):
    return [Bar(int(r[0]), Decimal(repr(float(r[1]))), Decimal(repr(float(r[2]))), Decimal(repr(float(r[3]))),
                Decimal(repr(float(r[4]))), Decimal(repr(float(r[5])))) for r in a]
def agg(a, n, step):
    out = []
    for i in range(0, len(a) - n + 1):
        g = a[i:i + n]
        if g[0, 0] % step == 0 and g[-1, 0] - g[0, 0] == (n - 1) * 900_000:
            out.append([g[0, 0], g[0, 1], g[:, 2].max(), g[:, 3].min(), g[-1, 4], g[:, 5].sum()])
    return np.array(out)
def trade(a, k, side, n_max):
    fill = a[k, 1] * (1 + side * SLIP); stop, tgt = fill * (1 - side * S), fill * (1 + side * 2 * S)
    for j in range(k, min(len(a), k + n_max)):
        o, h, l = a[j, 1:4]
        if (side == 1 and l <= stop) or (side == -1 and h >= stop):
            ex = (min(stop, o) if side == 1 else max(stop, o)) * (1 - side * SLIP); return side * (ex / fill - 1) - FEE * (1 + ex / fill)
        if (side == 1 and h >= tgt) or (side == -1 and l <= tgt):
            return side * (tgt / fill - 1) - FEE * (1 + tgt / fill)
    j = min(len(a) - 1, k + n_max - 1); return side * (a[j, 4] / fill - 1) - FEE * (1 + a[j, 4] / fill)
def run(t0, t1, label, d1=None):
    res = {}
    for sym in SYMS:
        a = np.loadtxt(f"{sys.argv[1]}/{sym}_15m.csv", delimiter=",", skiprows=1)
        h1, h4 = agg(a, 4, 3_600_000), agg(a, 16, 14_400_000)
        b15, b1h, b4h = bars(a), bars(h1), bars(h4)
        m1 = np.loadtxt(f"{d1}/{sym}_1m.csv", delimiter=",", skiprows=1) if d1 else None
        for t in range(t0, t1, 3_600_000):
            k = int(np.searchsorted(a[:, 0], t))
            k1, k4 = int(np.searchsorted(h1[:, 0], t)), int(np.searchsorted(h4[:, 0], t))
            st = observe(b15[max(0, k - 80):k], b1h[max(0, k1 - 40):k1], as_of_ms=t, bars_4h=b4h[max(0, k4 - 40):k4]).state
            if m1 is not None:
                kb = int(np.searchsorted(m1[:, 0], t))
                if kb + 1440 >= len(m1): continue
                r = trade(m1, kb, -1, 1440)
            else:
                r = trade(a, k, -1, 96)
            res.setdefault(st, []).append(r / S)
    print(f"== {label} (SHORT, stop 0,74%, 2R)")
    tot = sum(len(v) for v in res.values())
    for st, v in sorted(res.items()):
        x = np.array(v); se = 1.96 * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 2 else float("nan")
        print(f"   {st:22s} n={len(x):4d} ({len(x) / tot:4.0%}) R={x.mean():+.3f} ±{se:.3f} vincenti={np.mean(x > 0):.2f}")
run(ms("2026-10-08 00:00"), ms("2026-11-10 00:00"), "6/10-10/11, uscite 15m")
run(ms("2026-11-13 15:00"), ms("2026-11-14 19:00"), "13/11-14/11 finestra Brain, uscite 1m", sys.argv[2])
