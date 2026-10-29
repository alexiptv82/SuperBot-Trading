#!/usr/bin/env python3
"""Laboratorio "modifica long": orchestrazione. Vedi PREREGISTRAZIONE.md per le domande e i criteri.

Uso:  python run_lab.py --days 540 --cache /tmp/lab-cache --out results
      python run_lab.py --synthetic --days 40 --out /tmp/lab-synth        (prova del codice, nessuna rete)
"""
from __future__ import annotations

import argparse
import calendar
import json
import multiprocessing as mp
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

import events as ev  # noqa: E402
import labdata  # noqa: E402
import labrun as lr  # noqa: E402
from labfeat import extract_symbol, now_ms_str  # noqa: E402

_G: dict = {}


def _features(args):
    sym, arr = args
    return sym, extract_symbol(arr)


def _job(job):
    kind, name, mode, cm, thr, seed, shift, thr_ab = job
    M, REG = _G["M"], _G["REG"]
    R = REG[mode]
    if kind == "placebo_shift":
        R = lr.shift_regime(R, shift)
    spec = (dict(lr.SPECS["t_bonus_g"]) if kind == "placebo_shift"
            else dict(lr.SPECS["p1_reb"], extra="p1reb_placebo") if kind == "placebo_reb"
            else dict(lr.SPECS["p1"], extra="p1reb_placebo") if kind == "placebo_p1" else lr.SPECS[name])
    res = lr.replay(M, name, spec, R, mode, cost_mult=cm, thr_other=thr, seed=seed, thr_ab=thr_ab)
    t0, t1 = int(M.grid[0]), int(M.end[-1])
    summ = lr.summarize(res, t0, t1)
    keep = kind == "main" and cm == 1.0 and thr == 70 and thr_ab == 60
    return job, summ, (res["trades"] if keep else None), (lr.by_regime_table(res) if keep and name == "base13" else None)


def fmt_table(rows, title):
    out = [f"\n### {title}\n",
           "| variante | trade | netto $ | Δ vs base | vinc % | R medio | PF | DD $ | long n / $ / R | short n / $ / R | terzi $ | bloccate |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|---:|"]
    base = next((r for r in rows if r["nome"] == "base13"), None)
    for r in rows:
        d = "" if base is None or r is base else f"{r['netto'] - base['netto']:+.0f}"
        out.append(f"| {r['nome']} | {r['trade']} | {r['netto']:+.0f} | {d} | {r['vinc_pct']:.0f} | {r['R_medio']:+.3f} | "
                   f"{r['PF'] if r['PF'] is not None else '-'} | {r['dd']:.0f} | {r['long_n']} / {r['long_netto']:+.0f} / {r['long_R']:+.3f} | "
                   f"{r['short_n']} / {r['short_netto']:+.0f} / {r['short_R']:+.3f} | {r['terzi']} | {r['bloccate']} |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=540)
    ap.add_argument("--cache", default="/tmp/long-lab-cache")
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--no-placebo", action="store_true")
    ap.add_argument("--end", default=None, help="fine periodo UTC YYYY-MM-DD (default: oggi 00:00 UTC)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t_wall = time.time()

    if a.end:
        end_ms = calendar.timegm(time.strptime(a.end, "%Y-%m-%d")) * 1000
    else:
        end_ms = (int(time.time() * 1000) // labdata.DAY) * labdata.DAY
    meta = os.path.join(a.cache, "meta.json")
    if not a.synthetic and os.path.exists(meta):
        end_ms = int(json.load(open(meta))["end_ms"])
        print(f"[DATI] cache trovata: fine periodo {now_ms_str(end_ms)} UTC", flush=True)
    if a.synthetic:
        data = labdata.synthetic(a.days, end_ms)
    else:
        data = labdata.load_real(a.days, a.cache, end_ms, workers=min(6, a.workers + 2))
        os.makedirs(a.cache, exist_ok=True)
        json.dump({"end_ms": end_ms, "days": a.days}, open(meta, "w"))
    if "BTC" not in data:
        raise SystemExit("BTC mancante")
    print(f"[DATI] {len(data)} simboli, fine {now_ms_str(end_ms)} UTC ({time.time() - t_wall:.0f}s)", flush=True)

    ctx = mp.get_context("fork")
    with ctx.Pool(a.workers) as pool:
        feats = dict(pool.map(_features, list(data.items()), chunksize=1))
    print(f"[FEATURE] estratte ({time.time() - t_wall:.0f}s)", flush=True)

    t_start = end_ms - a.days * labdata.DAY
    M = lr.Market(data, feats, t_start, end_ms)
    t0, t1 = int(M.grid[0]), int(M.end[-1])
    cover = {s: int(M.valid[:, j].sum()) for j, s in enumerate(M.syms)}
    print(f"[MERCATO] {M.J} simboli x {M.K} barre; periodo {now_ms_str(t0)} -> {now_ms_str(t1)} UTC", flush=True)
    REG = {m: lr.compute_regime(M, m) for m in ("S1", "S2")}
    print(f"[REGIME] calcolato ({time.time() - t_wall:.0f}s)", flush=True)
    _G["M"], _G["REG"] = M, REG

    names = list(lr.SPECS)
    jobs = []
    for mode in ("S2", "S1"):
        for n in names:
            jobs.append(("main", n, mode, 1.0, 70, None, 0, 60))
    for n in ["base13"] + lr.CANDIDATES + ["ref_gate"]:
        jobs.append(("main", n, "S2", 1.5, 70, None, 0, 60))          # costi x1,5
        jobs.append(("main", n, "S2", 1.0, 63, None, 0, 60))          # soglia 63 per le altcoin (informativo)
        jobs.append(("main", n, "S2", 0.0, 70, None, 0, 60))          # senza commissioni ne' scivolamento (lordo)
    jobs.append(("main", "base13", "S2", 1.0, 76, None, 0, 66))       # controllo: soglie +6 (= togliere 6 punti a entrambi i lati)
    jobs.append(("main", "base13", "S1", 1.0, 76, None, 0, 66))
    if not a.no_placebo:
        rng = np.random.default_rng(2026)
        for k in range(lr.N_PLACEBO):
            jobs.append(("placebo_reb", f"pl_reb_{k}", "S2", 1.0, 70, 1000 + k, 0, 60))
            jobs.append(("placebo_p1", f"pl_p1_{k}", "S2", 1.0, 70, 2000 + k, 0, 60))
            d = int(rng.integers(5, 61)) * (1 if k % 2 == 0 else -1)
            jobs.append(("placebo_shift", f"pl_shift_{k}", "S2", 1.0, 70, None, d, 60))
    print(f"[RIPRODUZIONE] {len(jobs)} prove su {a.workers} processi", flush=True)
    with ctx.Pool(a.workers) as pool:
        done = pool.map(_job, jobs, chunksize=1)
    print(f"[RIPRODUZIONE] finita ({time.time() - t_wall:.0f}s)", flush=True)

    summ: dict = {}
    trades: dict = {}
    base_regime_table = None
    for job, s, tr, brt in done:
        kind, name, mode, cm, thr, _, _, thr_ab = job
        key = f"{mode}|c{cm}|t{thr}"
        summ.setdefault(key, {})[name] = s
        if tr is not None:
            trades[(mode, name)] = tr
        if brt is not None and mode == "S2":
            base_regime_table = brt

    gate_out: dict = {}
    for mode in ("S2", "S1"):
        other = "S1" if mode == "S2" else "S2"
        base_s = summ[f"{mode}|c1.0|t70"]["base13"]
        base_tr = trades[(mode, "base13")]
        pl_reb = [v["netto"] - base_s["netto"] for k, v in summ[f"{mode}|c1.0|t70"].items() if k.startswith("pl_reb_")]
        pl_p1 = [v["netto"] - base_s["netto"] for k, v in summ[f"{mode}|c1.0|t70"].items() if k.startswith("pl_p1_")]
        pl_sh = [v["netto"] - base_s["netto"] for k, v in summ[f"{mode}|c1.0|t70"].items() if k.startswith("pl_shift_")]
        gate_out[mode] = {}
        for n in lr.CANDIDATES + ["ref_gate"]:
            v = summ[f"{mode}|c1.0|t70"][n]
            pl = (pl_reb if n == "p1_reb" else pl_p1 if n == "p1"
                  else pl_sh if n in ("t_bonus_g", "g_long", "t_bonus", "r_reb", "ref_gate") else None)
            if mode != "S2":
                pl = None                     # i placebo girano solo con la stagionalita' di oggi (S2)
            cdelta = None
            if mode == "S2":
                cb = summ["S2|c1.5|t70"]
                cdelta = cb[n]["netto"] - cb["base13"]["netto"]
            o_s = summ[f"{other}|c1.0|t70"]
            odelta = o_s[n]["netto"] - o_s["base13"]["netto"]
            gate_out[mode][n] = lr.gates(base_s, v, base_tr, trades[(mode, n)], t0, t1, pl, cdelta, odelta)

    # ---- calibrazione: finestre reali, mesi, mercato, diagnostica P1, fasce di punteggio
    import calendar as _cal
    def ms(y, m, d, h=0):
        return _cal.timegm((y, m, d, h, 0, 0)) * 1000
    WINDOWS = {"reale 12-26/10/2026": (ms(2026, 10, 12), ms(2026, 10, 27)),
               "giorni d'oro 13-15/10/2026": (ms(2026, 10, 13), ms(2026, 10, 16)),
               "20-26/10/2026": (ms(2026, 10, 20), ms(2026, 10, 27)),
               "ultimi 30 giorni": (t1 - 30 * lr.DAY, t1)}
    windows = {}
    monthly = {}
    for mode in ("S1", "S2"):
        for n in names:
            tr = trades[(mode, n)]
            windows[f"{mode}|{n}"] = {w: lr.window_net(tr, a, b) for w, (a, b) in WINDOWS.items()}
            monthly[f"{mode}|{n}"] = lr.monthly_net(tr, t0, t1)
    btc = data["BTC"]
    btc_m = {}
    for row in btc[btc[:, 0] >= t0]:
        tm = time.gmtime(row[0] / 1000)
        k_ = f"{tm.tm_year}-{tm.tm_mon:02d}"
        o = btc_m.setdefault(k_, [row[1], row[4]])
        o[1] = row[4]
    btc_month = {k_: round(100 * (v[1] / v[0] - 1), 1) for k_, v in btc_m.items()}
    d1 = diag1 = None
    try:
        d1 = {m: lr.diag_p1(M, REG[m], m) for m in ("S1", "S2")}
    except Exception as e:
        print(f"[DIAG] errore: {e}", flush=True)
    for (mode, n), tr in trades.items():
        if mode in ("S1", "S2"):
            import gzip
            with gzip.open(os.path.join(a.out, f"trades_{mode}_{n}.csv.gz"), "wt") as f:
                f.write("id,symbol,side,open_ms,close_ms,net,net_r,why,reg_state,reg_turn\n")
                for t in tr:
                    f.write(",".join(str(x) for x in t) + "\n")

    ev_rows = []
    buckets = []
    try:
        RL, RS = ev.outcomes(M)
        ev_rows = ev.summarize_events(M, REG["S2"], RL, RS)
        sl_, ss_ = M.seasonal("S2")
        L_, S_, side_, score_, _, _ = lr.points(M.F, 20, None, None, sl_, ss_)
        buckets = ev.score_buckets(M, RL, RS, (L_, S_, side_, score_))
    except Exception as e:                       # l'esperimento sugli eventi non deve far perdere il resto
        print(f"[EVENTI] errore: {e}", flush=True)

    out = {"periodo": [now_ms_str(t0), now_ms_str(t1)], "simboli": M.syms, "barre_valide": cover,
           "riassunti": summ, "criteri": gate_out, "regime_base13_S2": base_regime_table, "eventi": ev_rows,
           "finestre": windows, "mensile": monthly, "btc_mensile_pct": btc_month, "diag_p1": d1, "fasce_punteggio": buckets,
           "secondi": round(time.time() - t_wall)}
    json.dump(out, open(os.path.join(a.out, "summary.json"), "w"), ensure_ascii=False, indent=1, default=str)

    md = [f"# Laboratorio modifica long — risultati\n",
          f"Periodo: {now_ms_str(t0)} → {now_ms_str(t1)} UTC, {M.J} simboli, barre da 15 minuti. "
          f"Calcolato in {round(time.time() - t_wall)} s.\n"]
    for mode, label in (("S2", "stagionalita' di oggi congelata (S2, giudizio principale)"),
                        ("S1", "stagionalita' come in produzione alla data storica (S1)")):
        rows = [summ[f"{mode}|c1.0|t70"][n] for n in names]
        md.append(fmt_table(rows, f"Varianti — {label}"))
    md.append(fmt_table([summ["S2|c1.5|t70"][n] for n in ["base13"] + lr.CANDIDATES + ["ref_gate"]],
                        "Sensibilita': costi ×1,5 (S2)"))
    md.append(fmt_table([summ["S2|c1.0|t63"][n] for n in ["base13"] + lr.CANDIDATES + ["ref_gate"]],
                        "Sensibilita': soglia 63 per le altcoin (S2)"))
    md.append(fmt_table([summ["S2|c0.0|t70"][n] for n in ["base13"] + lr.CANDIDATES + ["ref_gate"]],
                        "Sensibilita': SENZA commissioni ne' scivolamento (lordo, S2)"))
    md.append(fmt_table([summ["S2|c1.0|t70"]["base13"], dict(summ["S2|c1.0|t76"]["base13"], nome="base13 soglie +6 (AB 66, altre 76)"),
                         summ["S2|c1.0|t70"]["p1_w"]], "Controllo: P1 (peso 4h a 14) contro semplici soglie piu' alte di 6 punti (S2)"))
    md.append("\n### Finestre reali (netto $ / n trade; S1 = stagionalita' del periodo)\n")
    wn = list(WINDOWS)
    md.append("| variante | " + " | ".join(wn) + " |\n|---|" + "---|" * len(wn))
    for n in names:
        row = windows[f"S1|{n}"]
        md.append(f"| {n} | " + " | ".join(f"{row[w]['netto']:+.0f} / {row[w]['n']} (L {row[w]['long_n']} S {row[w]['short_n']})" for w in wn) + " |")
    md.append("\n### Netto per mese di chiusura (base13) e rendimento di BTC nel mese\n")
    md.append("| mese | BTC % | base13 S1 n / $ | base13 S2 n / $ | p1 S2 n / $ |\n|---|---:|---|---|---|")
    for mth in sorted(monthly["S2|base13"]):
        g1 = monthly["S1|base13"].get(mth, [0, 0.0])
        g2 = monthly["S2|base13"].get(mth, [0, 0.0])
        g3 = monthly["S2|p1"].get(mth, [0, 0.0])
        md.append(f"| {mth} | {btc_month.get(mth, '')} | {g1[0]} / {g1[1]:+.0f} | {g2[0]} / {g2[1]:+.0f} | {g3[0]} / {g3[1]:+.0f} |")
    if d1:
        md.append("\n### Il bonus rimbalzo di P1 cambia davvero le decisioni?\n")
        for m_, d_ in d1.items():
            md.append(f"- {m_}: scatti {d_['scatti']}, decisioni cambiate {d_['decisioni_cambiate']}, nuovi long aperti {d_['nuovi_long_aperti']}; "
                      f"punteggio long mediano quando scatta {d_['L_base_mediano_quando_scatta']} (max {d_['L_base_max_quando_scatta']}), "
                      f"short mediano {d_['S_base_mediano_quando_scatta']}")
    for mode in ("S2", "S1"):
        md.append(f"\n### Criteri G1–G9 ({mode})\n")
        md.append("| variante | Δ netto | Δ terzi | G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | G9 | TUTTI |")
        md.append("|---|---:|---|---|---|---|---|---|---|---|---|---|---|")
        for n, g in gate_out[mode].items():
            f = lambda k: "—" if g[k] is None else ("sì" if g[k] else "NO")  # noqa: E731
            md.append(f"| {n} | {g['d_tot']:+.0f} | {g['d_terzi']} | " + " | ".join(f(k) for k in
                      ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"]) + f" | {'SI' if g['tutti'] else 'no'} |")
        for n, g in gate_out[mode].items():
            if g.get("bootstrap"):
                b = g["bootstrap"]
                md.append(f"- {n}: bootstrap Δ medio {b['media']:+.0f}$, 90% [{b['lo90']:+.0f}, {b['hi90']:+.0f}], P(Δ<0)={b['p_neg']:.2f}"
                          + (f"; placebo Δ: mediana {g['placebo']['mediana']:+.0f}, secondo {g['placebo']['secondo']:+.0f}, max {g['placebo']['max']:+.0f}" if g.get("placebo") else ""))
    if base_regime_table:
        md.append("\n### Base 13/10 — esito per regime di mercato all'apertura (S2)\n")
        md.append("| regime | lato | n | vinc % | netto $ | R medio |\n|---|---|---:|---:|---:|---:|")
        for r in base_regime_table:
            md.append(f"| {r['regime']} | {r['lato']} | {r['n']} | {r['vinc_pct']:.0f} | {r['netto']:+.0f} | {r['R_medio']:+.3f} |")
    if buckets:
        md.append("\n### Il punteggio ha potere predittivo? R medio del trade simulato per fascia di punteggio (S2, costi 16 bp)\n")
        md.append("| gruppo | lato | fascia | n | R medio | vinc % |\n|---|---|---|---:|---:|---:|")
        for r in buckets:
            md.append(f"| {r['gruppo']} | {r['lato']} | {r['fascia']} | {r['n']} | {r['R_medio']:+.3f} | {r['vinc_pct']:.0f} |")
    if ev_rows:
        md.append("\n### Esperimento sugli eventi (R per trade simulato, costi 16 bp)\n")
        md.append("| categoria | lato | n | R medio | vinc % | R tutte | differenza | IC90 differenza | R per terzo |\n|---|---|---:|---:|---:|---:|---:|---|---|")
        for r in ev_rows:
            if "R_medio" not in r:
                md.append(f"| {r['categoria']} | {r['lato_simulato']} | {r['n']} | (pochi eventi) | | | | | |")
                continue
            md.append(f"| {r['categoria']} | {r['lato_simulato']} | {r['n']} | {r['R_medio']:+.3f} | {r['vinc_pct']:.0f} | {r['R_medio_tutte']:+.3f} | "
                      f"{r['diff_vs_tutte']:+.3f} | [{r['ic90_diff'][0]:+.3f}, {r['ic90_diff'][1]:+.3f}] | {r['R_per_terzo']} |")
    open(os.path.join(a.out, "report.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
