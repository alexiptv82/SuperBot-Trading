#!/usr/bin/env python3
"""Stessi ingressi orari di geometry.py, ma stop = k x ATR(14) 15m all'ingresso e dimensione decisa dal RISCHIO:
perdita pianificata fissa (72 USDT, quella tipica di Brain oggi), quindi il nozionale scende quando lo stop si allarga.
Confronta con lo stop fisso 0,74% (nozionale ~8.000). Nessun dato della VPS; solo candele reali Bitget."""
import json
import sys
import numpy as np
import geometry as G

RISK_USDT = 72.0
M15 = G.M15
rows = []
for sym in G.SYMS:
    a15, a1 = G.load(f"{sys.argv[1]}/{sym}_15m.csv"), G.load(f"{sys.argv[2]}/{sym}_1m.csv")
    reg = G.regimes(a15)
    tr = np.maximum(a15[1:, 2], a15[:-1, 4]) - np.minimum(a15[1:, 3], a15[:-1, 4])
    atr = np.r_[np.nan, np.convolve(tr / a15[1:, 4], np.ones(14) / 14, "full")[:len(tr)]]
    for t in range(G.WINDOW[0], G.WINDOW[1] + 1, G.H):
        if G.PAUSE[0] <= t < G.PAUSE[1]:
            continue
        k15 = int(np.searchsorted(a15[:, 0], t - M15, side="right")) - 1
        for side in (-1, 1):
            for name, s in [("fisso_0.74%", 0.0074)] + [(f"{m}xATR15m", m * float(atr[k15])) for m in (1.0, 1.5, 2.0)]:
                r = G.trade(a1, t, side, s)
                if r is None:
                    continue
                notional = RISK_USDT / (s + 0.0016)
                rows.append({"sym": sym, "side": side, "var": name, "R": r[0] / s, "usdt": r[0] * notional, "notional": notional,
                             "stop": s, "regime": reg[int(a15[k15, 0])], "why": r[1], "min": r[2]})


def st(sel):
    if not sel:
        return None
    R = np.array([x["R"] for x in sel]); u = np.array([x["usdt"] for x in sel])
    return {"n": len(sel), "vincenti": round(float((R > 0).mean()), 2), "R_medio": round(float(R.mean()), 2),
            "usdt_medio": round(float(u.mean()), 1), "usdt_totale": round(float(u.sum()), 0),
            "stop_mediano_pct": round(float(np.median([x["stop"] for x in sel])) * 100, 2),
            "nozionale_mediano": round(float(np.median([x["notional"] for x in sel])), 0),
            "leva_a_400_di_margine": round(float(np.median([x["notional"] for x in sel])) / 400, 1),
            "minuti_mediani": int(np.median([x["min"] for x in sel]))}


out = {}
for side, lab in ((-1, "SHORT"), (1, "LONG")):
    for var in ("fisso_0.74%", "1.0xATR15m", "1.5xATR15m", "2.0xATR15m"):
        sel = [x for x in rows if x["side"] == side and x["var"] == var]
        out[f"{lab}_{var}"] = {"tutti": st(sel), "EXPANSION": st([x for x in sel if x["regime"] == "EXPANSION"]),
                               "altri_regimi": st([x for x in sel if x["regime"] != "EXPANSION"]),
                               **{s: st([x for x in sel if x["sym"] == s]) for s in ("BTCUSDT", "ETHUSDT", "BNBUSDT")}}
json.dump(out, open(sys.argv[3], "w"), indent=1)
for k, v in out.items():
    print(k)
    for kk, s in v.items():
        print(f"   {kk:13s} {s}")
