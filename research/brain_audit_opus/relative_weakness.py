#!/usr/bin/env python3
"""Selezione dinamica del simbolo (non lista nera): a ogni ora, gli 8 simboli ordinati per rendimento 24 h RELATIVO a BTC
(solo candele chiuse). SHORT sul piu' debole vs sul piu' forte vs media; LONG speculare. Geometria di Brain, uscite 15m
(ottobre) o 1m (finestra Brain). Classi fissate prima di guardare."""
import calendar, sys, time
import numpy as np
from frrd_check import SYMS, trade
ms = lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%d %H:%M")) * 1000  # noqa: E731
S = 0.0074
def run(t0, t1, label, d1=None):
    A = {s: np.loadtxt(f"{sys.argv[1]}/{s}_15m.csv", delimiter=",", skiprows=1) for s in SYMS}
    M = {s: np.loadtxt(f"{d1}/{s}_1m.csv", delimiter=",", skiprows=1) for s in SYMS} if d1 else None
    out = {k: [] for k in ("short_piu_debole", "short_2_piu_deboli", "short_media", "short_2_piu_forti", "long_piu_forte", "long_media")}
    for t in range(t0, t1, 3_600_000):
        rs, r = {}, {}
        for s in SYMS:
            a = A[s]; k = int(np.searchsorted(a[:, 0], t))
            rs[s] = a[k - 1, 4] / a[k - 97, 4] - 1
        btc = rs["BTCUSDT"]
        order = sorted((x for x in SYMS if x != "BTCUSDT"), key=lambda s: rs[s] - btc)
        for s in SYMS:
            if M:
                kb = int(np.searchsorted(M[s][:, 0], t))
                if kb + 1440 >= len(M[s]): break
                r[s] = (trade(M[s], kb, -1, 1440) / S, trade(M[s], kb, 1, 1440) / S)
            else:
                k = int(np.searchsorted(A[s][:, 0], t)); r[s] = (trade(A[s], k, -1, 96) / S, trade(A[s], k, 1, 96) / S)
        if len(r) < len(SYMS): continue
        out["short_piu_debole"].append(r[order[0]][0]); out["short_2_piu_deboli"] += [r[order[0]][0], r[order[1]][0]]
        out["short_2_piu_forti"] += [r[order[-1]][0], r[order[-2]][0]]; out["short_media"] += [r[s][0] for s in order]
        out["long_piu_forte"].append(r[order[-1]][1]); out["long_media"] += [r[s][1] for s in order]
    print(f"== {label}")
    for k, v in out.items():
        x = np.array(v); print(f"   {k:20s} n={len(x):4d} R={x.mean():+.3f} ±{1.96 * x.std(ddof=1) / np.sqrt(len(x)):.3f} vincenti={np.mean(x > 0):.2f}")
run(ms("2026-10-08 00:00"), ms("2026-11-10 00:00"), "6/10-10/11, uscite 15m (altcoin, BTC escluso dalla classifica)")
run(ms("2026-11-13 15:00"), ms("2026-11-14 19:00"), "13/11-14/11 finestra Brain, uscite 1m", sys.argv[2])
