#!/usr/bin/env python3
"""Brain V3 — la geometria dello stop spiega EXPANSION ed ETH? Controllo con candele REALI, senza dati della VPS.

Per ogni ora di attivita' di Brain (13/11 15:00 -> 15/11 19:00 UTC, esclusa la pausa notturna del 13-14/11) e per
ciascuno degli 8 simboli, simula uno SHORT (e per confronto un LONG) con la geometria imposta dalla configurazione
installata: stop fisso a distanza percentuale, target 2R, massimo 24 h, stop prima del target, stop eseguito
all'apertura del minuto SUCCESSIVO al tocco (comportamento osservato sulla VPS il 13/11), 6 bp di commissione per lato,
2 bp di slippage. Il regime e' calcolato con il classificatore VERO di Brain (features/regime.py, 15m, finestra 2880).

Nessuna scelta del modello: e' un controllo di cosa fa la sola geometria, simbolo per simbolo e regime per regime.
Uso: PYTHONPATH=<checkout Brain> python geometry.py --m15 DIR --m1 DIR --json out.json
"""
from __future__ import annotations

import argparse
import calendar
import json
import math
import time
from decimal import Decimal

import numpy as np

from backend.v3.features.indicators import Bar
from backend.v3.features.regime import RegimeParams, regime_labels

SYMS = "BTCUSDT ETHUSDT SOLUSDT XRPUSDT BNBUSDT DOGEUSDT ADAUSDT LINKUSDT".split()
M1, M15, H = 60_000, 900_000, 3_600_000
ms = lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%d %H:%M")) * 1000  # noqa: E731
WINDOW = (ms("2026-11-13 15:00"), ms("2026-11-15 19:00"))
PAUSE = (ms("2026-11-13 21:30"), ms("2026-11-14 00:10"))
PARAMS = RegimeParams(Decimal("3"), Decimal("80"), Decimal("25"), Decimal("20"))
FEE, SLIP = 6e-4, 2e-4
STOPS = (0.0050, 0.0074, 0.0091)


def load(path):
    return np.loadtxt(path, delimiter=",", skiprows=1)


def regimes(a15) -> dict:
    bars = [Bar(int(r[0]), Decimal(repr(float(r[1]))), Decimal(repr(float(r[2]))), Decimal(repr(float(r[3]))), Decimal(repr(float(r[4]))),
                Decimal(repr(float(r[5])))) for r in a15]
    lab = regime_labels(bars, 14, 2880, 14, PARAMS, candle_ms=M15)
    return {int(r[0]): l for r, l in zip(a15, lab)}


def trade(a1, t, side, s):
    """Decisione all'istante t (inizio di un minuto): fill = chiusura del minuto precedente +/- slippage."""
    k = int(np.searchsorted(a1[:, 0], t))
    if k < 1 or k >= len(a1):
        return None
    fill = a1[k - 1, 4] * (1 + side * SLIP)
    stop, tgt = fill * (1 - side * s), fill * (1 + side * 2 * s)
    for j in range(k, min(len(a1), k + 1440)):
        o, h, l, c = a1[j, 1:5]
        if (side == 1 and l <= stop) or (side == -1 and h >= stop):
            if j + 1 >= len(a1):
                return None
            nxt = a1[j + 1, 1]                                    # eseguito al minuto dopo, come sulla VPS
            base = min(stop, nxt) if side == 1 else max(stop, nxt)
            ex = base * (1 - side * SLIP)
            return side * (ex / fill - 1) - FEE * (1 + ex / fill), "stop", j - k + 1
        if (side == 1 and h >= tgt) or (side == -1 and l <= tgt):
            return side * (tgt / fill - 1) - FEE * (1 + tgt / fill), "tp", j - k + 1
    if k + 1440 < len(a1):
        ex = a1[k + 1439, 4]
        return side * (ex / fill - 1) - FEE * (1 + ex / fill), "tempo", 1440
    return None                                                     # ancora aperta: esclusa (dichiarato)


def summarize(rows, s):
    if not rows:
        return {"n": 0}
    x = np.array([r["net"] for r in rows])
    R = x / s
    return {"n": len(x), "vincenti": round(float((x > 0).mean()), 3), "R_medio": round(float(R.mean()), 3),
            "ic95_R": [round(float(R.mean() - 1.96 * R.std(ddof=1) / math.sqrt(len(R))), 3),
                       round(float(R.mean() + 1.96 * R.std(ddof=1) / math.sqrt(len(R))), 3)] if len(R) > 2 else None,
            "minuti_mediani": int(np.median([r["min"] for r in rows])),
            "usdt_medio_su_8000": round(float(x.mean()) * 8000, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--m15", required=True)
    ap.add_argument("--m1", required=True)
    ap.add_argument("--json", required=True)
    a = ap.parse_args()
    rows = []
    vol = {}
    for sym in SYMS:
        a15, a1 = load(f"{a.m15}/{sym}_15m.csv"), load(f"{a.m1}/{sym}_1m.csv")
        reg = regimes(a15)
        tr = np.maximum(a15[1:, 2], a15[:-1, 4]) - np.minimum(a15[1:, 3], a15[:-1, 4])
        atr15 = np.r_[np.nan, np.convolve(tr / a15[1:, 4], np.ones(14) / 14, "full")[:len(tr)]]
        r1 = np.diff(np.log(a1[:, 4]))
        i0, i1 = np.searchsorted(a1[:, 0], WINDOW)
        vol[sym] = {"dev_std_1m_bp": round(float(r1[i0:i1].std()) * 1e4, 2),
                    "atr15m_medio_bp": round(float(np.nanmean(atr15[np.searchsorted(a15[:, 0], WINDOW[0]):np.searchsorted(a15[:, 0], WINDOW[1])])) * 1e4, 1),
                    "variazione_finestra_pct": round(float(a1[i1, 4] / a1[i0, 4] - 1) * 100, 2)}
        for t in range(WINDOW[0], WINDOW[1] + 1, H):
            if PAUSE[0] <= t < PAUSE[1]:
                continue
            k15 = int(np.searchsorted(a15[:, 0], t - M15, side="right")) - 1      # ultima 15m chiusa
            if k15 < 16 or a15[k15, 0] + M15 > t:
                continue
            ret4h = a15[k15, 4] / a15[k15 - 16, 4] - 1
            for s in STOPS:
                for side in (-1, 1):
                    r = trade(a1, t, side, s)
                    if r is None:
                        continue
                    rows.append({"sym": sym, "t": t, "side": side, "stop": s, "net": r[0], "why": r[1], "min": r[2],
                                 "regime": reg[int(a15[k15, 0])], "atr15_bp": float(atr15[k15]) * 1e4,
                                 "ret4h": float(ret4h), "stop_su_atr": s / float(atr15[k15])})
    out = {"finestra_utc": ["2026-11-13 15:00", "2026-11-15 19:00"], "volatilita": vol, "risultati": {}}
    for s in STOPS:
        for side, lab in ((-1, "SHORT"), (1, "LONG")):
            sel = [r for r in rows if r["stop"] == s and r["side"] == side]
            blk = {"tutti": summarize(sel, s),
                   "per_simbolo": {sym: summarize([r for r in sel if r["sym"] == sym], s) for sym in SYMS},
                   "per_regime": {g: summarize([r for r in sel if r["regime"] == g], s)
                                  for g in sorted({r["regime"] for r in sel})}}
            q = np.quantile([r["stop_su_atr"] for r in sel], [1 / 3, 2 / 3])
            blk["per_stop_su_atr15m"] = {
                f"stretto (<{q[0]:.2f} ATR)": summarize([r for r in sel if r["stop_su_atr"] < q[0]], s),
                "medio": summarize([r for r in sel if q[0] <= r["stop_su_atr"] < q[1]], s),
                f"largo (>={q[1]:.2f} ATR)": summarize([r for r in sel if r["stop_su_atr"] >= q[1]], s)}
            q4 = np.quantile([r["ret4h"] for r in sel], [1 / 3, 2 / 3])
            blk["per_rendimento_4h_prima"] = {
                f"gia_sceso (<{q4[0] * 100:.2f}%)": summarize([r for r in sel if r["ret4h"] < q4[0]], s),
                "intermedio": summarize([r for r in sel if q4[0] <= r["ret4h"] < q4[1]], s),
                f"salito (>={q4[1] * 100:.2f}%)": summarize([r for r in sel if r["ret4h"] >= q4[1]], s)}
            out["risultati"][f"{lab}_stop_{s * 100:.2f}%"] = blk
    with open(a.json, "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print("ok", len(rows))


if __name__ == "__main__":
    main()
