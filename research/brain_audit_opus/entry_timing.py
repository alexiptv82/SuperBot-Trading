#!/usr/bin/env python3
"""SHORT dopo la discesa o dopo il rimbalzo? Stessa geometria di Brain (stop 0,74%, target 2R, 24 h, costi), ingressi
orari, uscite su 15m. Classi FISSATE prima di guardare: rendimento dell'ultima ora (4 candele 15m chiuse) e posizione
del prezzo nel range delle ultime 24 h. Periodi: 6/10-10/11 (uscite 15m) e 13/11-15/11 (uscite 1m, se fornite)."""
import calendar, sys, time
import numpy as np
SYMS = "BTCUSDT ETHUSDT SOLUSDT XRPUSDT BNBUSDT DOGEUSDT ADAUSDT LINKUSDT".split()
ms = lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%d %H:%M")) * 1000  # noqa: E731
FEE, SLIP, S = 6e-4, 2e-4, 0.0074
def trade(a, k, side, n_max):
    fill = a[k, 1] * (1 + side * SLIP); stop, tgt = fill * (1 - side * S), fill * (1 + side * 2 * S)
    for j in range(k, min(len(a), k + n_max)):
        o, h, l = a[j, 1:4]
        if (side == 1 and l <= stop) or (side == -1 and h >= stop):
            ex = (min(stop, o) if side == 1 else max(stop, o)) * (1 - side * SLIP); return side * (ex / fill - 1) - FEE * (1 + ex / fill)
        if (side == 1 and h >= tgt) or (side == -1 and l <= tgt):
            return side * (tgt / fill - 1) - FEE * (1 + tgt / fill)
    j = min(len(a) - 1, k + n_max - 1); return side * (a[j, 4] / fill - 1) - FEE * (1 + a[j, 4] / fill)
def run(t0, t1, d15, label, d1=None):
    rows = []
    for sym in SYMS:
        a = np.loadtxt(f"{d15}/{sym}_15m.csv", delimiter=",", skiprows=1)
        b = np.loadtxt(f"{d1}/{sym}_1m.csv", delimiter=",", skiprows=1) if d1 else None
        for t in range(t0, t1, 3_600_000):
            k = int(np.searchsorted(a[:, 0], t))
            if k < 97: continue
            r1h = a[k - 1, 4] / a[k - 5, 4] - 1
            hi, lo = a[k - 96:k, 2].max(), a[k - 96:k, 3].min(); pos = (a[k - 1, 4] - lo) / (hi - lo)
            for side in (-1, 1):
                if b is not None:
                    kb = int(np.searchsorted(b[:, 0], t))
                    if kb + 1440 >= len(b): continue
                    r = trade(b, kb, side, 1440)
                else:
                    r = trade(a, k, side, 96)
                rows.append((side, r / S, r1h, pos))
    print(f"== {label}")
    for side, lab in ((-1, "SHORT"), (1, "LONG ")):
        v = [x for x in rows if x[0] == side]; R = np.array([x[1] for x in v])
        h1 = np.array([x[2] for x in v]); p = np.array([x[3] for x in v])
        print(f"  {lab} tutti n={len(R)} R={R.mean():+.3f}")
        for name, m in (("ultima ora in CALO  (<-0,3%)", h1 < -0.003), ("ultima ora piatta", (h1 >= -0.003) & (h1 <= 0.003)),
                        ("ultima ora in RIALZO (>+0,3%)", h1 > 0.003),
                        ("prezzo nel 25% BASSO del range 24h", p < 0.25), ("prezzo a meta' range", (p >= 0.25) & (p <= 0.75)),
                        ("prezzo nel 25% ALTO del range 24h", p > 0.75)):
            x = R[m]; se = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 2 else np.nan
            print(f"     {name:36s} n={len(x):4d} R={x.mean():+.3f} (±{1.96 * se:.3f}) vincenti={np.mean(x > 0):.2f}")
run(ms("2026-10-06 00:00"), ms("2026-11-10 00:00"), sys.argv[1], "6/10-10/11/2026, uscite 15m")
run(ms("2026-11-13 15:00"), ms("2026-11-14 19:00"), sys.argv[1], "13/11-14/11/2026 (finestra Brain con 24 h di dati futuri), uscite 1m", sys.argv[2])
