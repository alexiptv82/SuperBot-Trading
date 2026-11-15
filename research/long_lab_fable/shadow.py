#!/usr/bin/env python3
"""Toro «Trend dei leader» in OMBRA: solo osservazione, nessun ordine, nessun collegamento ai bot.

Applica le regole H3 CONGELATE di PREREGISTRAZIONE.md (importate da lab.py, mai ridefinite qui) alle candele
giornaliere scaricate con fetch_universe.py, a partire da una data di inizio fissa, e scrive:

* ``osservazioni.jsonl``: una riga per ogni segnale (eseguito o rifiutato per slot pieni) e per ogni operazione
  virtuale (aperta o chiusa) con i campi utili al confronto Toro-Brain: regime, indicatori, motivo, stop iniziale,
  durata, massimo profitto flottante, MAE, risultato netto, R, motivo d'uscita;
* ``stato.json``: filtro di mercato, ampiezza delle altcoin (solo osservata), posizioni virtuali aperte, riepilogo.

Il risultato viene RICOSTRUITO da zero a ogni esecuzione: nessuno stato nascosto, stesso input = stesso output.
Una riga gia' scritta non cambia quando arrivano nuovi giorni (verificato dai test), salvo le operazioni ancora aperte.

Uso: python shadow.py --data DIR --start 2026-11-15 --out DIR
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np

from lab import (ATR_K, FEE_SLIP_BP, FUND_BP_DAY, G_SMA, MAX_HOLD_H3, SLOTS, Sim, build, h3_signals, load_panel, rolling)

VERSION = "toro_trend_leader_shadow_v1"


def _trade_view(P, B, j: int, i: int) -> dict | None:
    """Ricalcola l'operazione virtuale con le stesse regole di lab.Sim.run, esponendo anche lo stato intermedio."""
    o, h, l, c, atr = P["o"][:, j], P["h"][:, j], P["l"][:, j], P["c"][:, j], B["atr"][:, j]
    n, gate = len(c), B["gates"][G_SMA]
    if i + 1 >= n or np.isnan(o[i + 1]) or np.isnan(atr[i]):
        return None
    entry = o[i + 1] * (1 + 2e-4)
    best = c[i]
    stop0 = stop = best - ATR_K * atr[i]
    if entry <= stop:
        return None
    hi, lo = entry, entry
    status, why, px, k_end = "aperta", None, None, None
    for k in range(i + 1, min(n, i + 1 + MAX_HOLD_H3)):
        if np.isnan(o[k]):
            status, why, px, k_end = "chiusa", "dati", c[k - 1], k
            break
        hi, lo = max(hi, h[k]), min(lo, l[k])
        if l[k] <= stop:
            status, why, px, k_end = "chiusa", "stop", min(stop, o[k]), k + 1
            break
        best = max(best, c[k])
        if not np.isnan(atr[k]):
            stop = max(stop, best - ATR_K * atr[k])
        if k + 1 < n and not np.isnan(o[k + 1]) and not gate[k]:
            status, why, px, k_end = "chiusa", "filtro", o[k + 1], k + 1
            break
    else:
        last = i + MAX_HOLD_H3
        if last + 1 < n and not np.isnan(o[last + 1]):
            status, why, px, k_end = "chiusa", "tempo", o[last + 1], last + 1
    risk = (entry - stop0) / entry
    out = {"stato": status, "ingresso": float(entry), "stop_iniziale": float(stop0), "distanza_stop_pct": round(risk * 100, 2),
           "massimo_flottante_pct": round((hi / entry - 1) * 100, 2), "mae_pct": round((lo / entry - 1) * 100, 2)}
    if status == "chiusa":
        days = max(1, k_end - (i + 1))
        exit_px = px * (1 - 2e-4)
        net = exit_px / entry - 1 - (FEE_SLIP_BP["base"] - 2) / 1e4 * (1 + exit_px / entry) - FUND_BP_DAY["base"] / 1e4 * days
        out.update(uscita=float(exit_px), motivo_uscita=why, giorni=int(days), data_uscita=P["dates"][min(k_end, n - 1)],
                   netto_pct=round(net * 100, 2), R=round(net / risk, 2), libera_slot_da=int(k_end))
    else:
        out.update(stop_attuale=float(stop), giorni=int(n - (i + 1)), flottante_pct=round((c[n - 1] / entry - 1) * 100, 2),
                   libera_slot_da=None)
    return out


def run(data_dir: str, start: str) -> tuple[list, dict]:
    P = load_panel(data_dir)
    B = build(P)
    sim = Sim(P, B)
    dates, syms, gate = P["dates"], P["syms"], B["gates"][G_SMA]
    n = len(dates)
    signals = [s for s in h3_signals(P, B, 1) if dates[s[0]] >= start]
    by_day: dict[int, list] = {}
    for i, j, pr in signals:
        by_day.setdefault(i, []).append((pr, j))
    rows, open_until = [], {}                            # simbolo -> indice da cui lo slot e' libero (None = aperta)
    for i in sorted(by_day):
        for j in [j for j, e in open_until.items() if e is not None and e <= i + 1]:
            del open_until[j]
        for pr, j in sorted(by_day[i], reverse=True):
            base = {"versione": VERSION, "data_segnale": dates[i], "simbolo": syms[j], "lato": "LONG",
                    "regime": "BTC_sopra_SMA%d" % G_SMA, "forza_relativa_28g_pct": round(pr * 100, 2),
                    "motivo": "prima chiusura sopra il massimo a 20 giorni, terzo superiore di forza relativa"}
            if j in open_until:
                rows.append({**base, "esito": "ignorato_posizione_gia_aperta"})
                continue
            if len(open_until) >= SLOTS:
                rows.append({**base, "esito": "rifiutato_slot_pieni"})
                continue
            view = _trade_view(P, B, j, i)
            if view is None:
                rows.append({**base, "esito": "non_eseguibile_dati"})
                continue
            if view["stato"] == "chiusa":                # coerenza con il motore del laboratorio
                ref = sim.run(j, i, 1, MAX_HOLD_H3, "gate_off", "base")
                assert ref is not None and abs(ref[0] * 100 - view["netto_pct"]) < 0.02, (syms[j], dates[i])
            open_until[j] = view.pop("libera_slot_da")
            rows.append({**base, "esito": "eseguito_virtuale", **view})
    # ampiezza: quota dell'universo ammesso sopra la propria media a 100 giorni (solo osservata, non usata)
    sma = rolling(lambda w: w.mean(axis=0), P["c"], G_SMA)
    e = B["elig"][n - 1] & ~np.isnan(sma[n - 1])
    breadth = float((P["c"][n - 1, e] > sma[n - 1, e]).mean()) if e.sum() else None
    closed = [r for r in rows if r.get("stato") == "chiusa"]
    state = {"versione": VERSION, "inizio_ombra": start, "ultimo_giorno_chiuso": dates[n - 1],
             "filtro_mercato_acceso": bool(gate[n - 1]), "ampiezza_sopra_sma100": None if breadth is None else round(breadth, 3),
             "posizioni_virtuali_aperte": [{k: r[k] for k in ("simbolo", "data_segnale", "ingresso", "stop_attuale", "flottante_pct", "giorni")}
                                           for r in rows if r.get("stato") == "aperta"],
             "riepilogo": {"segnali": len(rows), "eseguiti": sum(r["esito"] == "eseguito_virtuale" for r in rows),
                           "rifiutati_slot": sum(r["esito"] == "rifiutato_slot_pieni" for r in rows), "chiuse": len(closed),
                           "R_medio": round(float(np.mean([r["R"] for r in closed])), 3) if closed else None,
                           "vincenti": round(float(np.mean([r["netto_pct"] > 0 for r in closed])), 3) if closed else None,
                           "netto_medio_pct": round(float(np.mean([r["netto_pct"] for r in closed])), 2) if closed else None},
             "criterio_di_valutazione": "almeno 40 chiuse in avanti; approvazione solo con R medio > 0 e sopra la mediana dei casuali"}
    return rows, state


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--start", default="2026-11-15")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows, state = run(a.data, a.start)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "osservazioni.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")
    with open(os.path.join(a.out, "stato.json"), "w") as fh:
        json.dump(state, fh, indent=1, ensure_ascii=False)
    print(json.dumps(state, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
