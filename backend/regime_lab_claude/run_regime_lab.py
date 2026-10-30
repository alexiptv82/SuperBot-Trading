#!/usr/bin/env python3
"""Laboratorio lettore di regime v2 (Claude). Criteri in PREREGISTRAZIONE.md (scritti prima dei risultati).

Uso:  python run_regime_lab.py --days 540 --cache /tmp/regime-cache --out results --end 2026-10-29
      python run_regime_lab.py --synthetic --days 60 --out /tmp/regime-synth      (prova del codice con dati e trade finti)
"""
from __future__ import annotations

import argparse
import calendar
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import labdata  # noqa: E402
import regime_v2 as rg  # noqa: E402

BAR, DAY = 900_000, 86_400_000
P = rg.Params()
PROFILE = rg.CLASSIC15
COMMODITIES = ("XAU", "XAG")
SOURCES = ("market", "symbol", "combined")
POLICIES = ("G_A", "G_N", "S_W")
THR_P = {"market": 0.10, "symbol": 0.10 / 3, "combined": 0.10 / 3}
SW = {rg.ALIGNED: 1.0, rg.NEUTRAL: 0.5, rg.OPPOSED: 0.25}
N_BOOT, N_PLACEBO, STRESS_R = 5000, 200, 0.08


# ---------------------------------------------------------------------------------------------------------------- regime
def build_regime(candles: dict):
    res = {}
    for sym, arr in candles.items():
        base = dict(ts=arr[:, 0].astype(np.int64), o=arr[:, 1], h=arr[:, 2], l=arr[:, 3], c=arr[:, 4], v=arr[:, 5])
        res[sym] = rg.compute_series(base, PROFILE, P)
        res[sym]["base"] = base
    master_src = "BTC" if "BTC" in res else next(iter(res))
    master = res[master_src]["close_ms"]
    mkt = rg.market_series(res, master, PROFILE, P)
    return res, mkt


def state_at(close_ms, state, t_ms):
    """Stato noto a `t_ms`: ultima barra con chiusura <= t_ms, NA se piu' vecchia di una barra (buco)."""
    j = np.searchsorted(close_ms, t_ms, side="right") - 1
    jj = np.clip(j, 0, None)
    ok = (j >= 0) & ((t_ms - close_ms[jj]) < BAR)
    return np.where(ok, state[jj], rg.NA).astype(np.int8)


def classify_trades(tr: pd.DataFrame, res: dict, mkt: dict, shift_days: int = 0, span: tuple | None = None):
    """Classi per ogni trade (lato del trade). Con shift_days>0: serie di regime letta `shift_days` giorni prima, in modo
    circolare dentro l'intervallo dati (placebo)."""
    t = tr.open_ms.to_numpy(np.int64).copy()
    if shift_days:
        lo, hi = span
        t = t - shift_days * DAY
        t = np.where(t < lo, t + (hi - lo), t)
    sym_state = np.full(len(tr), rg.NA, dtype=np.int8)
    for s, idx in tr.groupby("symbol").indices.items():
        if s in res:
            sym_state[idx] = state_at(res[s]["close_ms"], res[s]["state"], t[idx])
    m_state = state_at(mkt["close_ms"], mkt["state"], t)
    side = tr.side.to_numpy()
    cls_s, cls_m = np.zeros(len(tr), np.int8), np.zeros(len(tr), np.int8)
    for sd in (rg.LONG, rg.SHORT):
        k = side == sd
        cls_s[k] = rg.side_class(sym_state[k], sd)
        cls_m[k] = rg.side_class(m_state[k], sd)
    crypto = ~tr.symbol.isin(COMMODITIES).to_numpy()
    cls_m = np.where(crypto, cls_m, rg.NEUTRAL).astype(np.int8)     # oro/argento: nessuna classe di mercato (come desk.regime)
    return dict(sym_state=sym_state, m_state=m_state, symbol=cls_s, market=cls_m, combined=rg.combine_classes(cls_s, cls_m))


def weights(cls: np.ndarray, policy: str) -> np.ndarray:
    if policy == "G_A":
        return (cls == rg.ALIGNED).astype(float)
    if policy == "G_N":
        return (cls != rg.OPPOSED).astype(float)
    return np.vectorize(SW.get)(cls).astype(float)


def delta(R, w, policy):
    """Discriminazione: tenuti - scartati (gating); R pesato - R base (S_W). NaN se un gruppo e' vuoto."""
    if len(R) == 0:
        return np.nan
    if policy == "S_W":
        sw = w.sum()
        return (np.dot(w, R) / sw - R.mean()) if sw > 0 else np.nan
    sk, sd = w.sum(), (1 - w).sum()
    if sk == 0 or sd == 0:
        return np.nan
    return np.dot(w, R) / sk - np.dot(1 - w, R) / sd


def boot_delta(R, w, blocks, policy, rng):
    """Bootstrap a blocchi: distribuzione di delta con estrazione dei blocchi (7 giorni)."""
    ub, inv = np.unique(blocks, return_inverse=True)
    nb = len(ub)
    if policy == "S_W":
        st = np.stack([np.bincount(inv, weights=x, minlength=nb) for x in (w, w * R, np.ones_like(R), R)], axis=1)
    else:
        st = np.stack([np.bincount(inv, weights=x, minlength=nb) for x in (w, w * R, 1 - w, (1 - w) * R)], axis=1)
    idx = rng.integers(0, nb, size=(N_BOOT, nb))
    s = st[idx].sum(axis=1)
    with np.errstate(all="ignore"):
        if policy == "S_W":
            d = s[:, 1] / s[:, 0] - s[:, 3] / s[:, 2]
        else:
            d = s[:, 1] / s[:, 0] - s[:, 3] / s[:, 2]
    return d[~np.isnan(d)]


def boot_mean_ci(R, blocks, rng):
    if len(R) == 0:
        return (np.nan, np.nan)
    ub, inv = np.unique(blocks, return_inverse=True)
    nb = len(ub)
    st = np.stack([np.bincount(inv, weights=R, minlength=nb), np.bincount(inv, minlength=nb).astype(float)], axis=1)
    s = st[rng.integers(0, nb, size=(2000, nb))].sum(axis=1)
    with np.errstate(all="ignore"):
        m = s[:, 0] / s[:, 1]
    m = m[~np.isnan(m)]
    return (float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))) if len(m) else (np.nan, np.nan)


# ---------------------------------------------------------------------------------------------------------- analisi trade
def analyse_scenario(name: str, tr: pd.DataFrame, res: dict, mkt: dict, span: tuple, seed: int):
    rng = np.random.default_rng(seed)
    tr = tr.sort_values("open_ms").reset_index(drop=True)
    cl = classify_trades(tr, res, mkt)
    R = tr.net_r.to_numpy(float)
    side = tr.side.to_numpy()
    t0 = int(tr.open_ms.min())
    blocks = ((tr.open_ms.to_numpy() - t0) // (7 * DAY)).astype(int)
    third = np.minimum(((tr.open_ms.to_numpy() - t0) * 3 // max(int(tr.open_ms.max()) - t0 + 1, 1)).astype(int), 2)
    rows, tables = [], {}
    # placebo: classi con serie spostata
    shifts = rng.integers(5, 61, size=N_PLACEBO)
    plc = [classify_trades(tr, res, mkt, int(k), span) for k in shifts]
    for src in SOURCES:
        cls = cl[src]
        for pol in POLICIES:
            w = weights(cls, pol)
            d_obs = delta(R, w, pol)
            bd = boot_delta(R, w, blocks, pol, rng)
            p_le0 = float(np.mean(bd <= 0)) if len(bd) else np.nan
            d_third = [delta(R[third == k], w[third == k], pol) for k in range(3)]
            d_plc = np.array([delta(R, weights(pc[src], pol), pol) for pc in plc])
            d_plc = d_plc[~np.isnan(d_plc)]
            p_plc = float(np.mean(d_plc >= d_obs)) if len(d_plc) and not np.isnan(d_obs) else np.nan
            d_side = {sd: delta(R[side == sd], w[side == sd], pol) for sd in (rg.SHORT, rg.LONG)}
            kept = (w >= 1).mean() if pol != "S_W" else np.nan
            ret_mean = float(np.dot(w, R) / w.sum()) if w.sum() > 0 else np.nan
            rows.append(dict(scenario=name, source=src, policy=pol, n=len(R), kept_frac=kept, delta=d_obs, p_delta_le0=p_le0,
                             p_placebo=p_plc, third_deltas=[None if np.isnan(x) else float(x) for x in d_third],
                             delta_short=d_side[rg.SHORT], delta_long=d_side[rg.LONG], retained_R=ret_mean,
                             retained_R_stress=ret_mean - STRESS_R if not np.isnan(ret_mean) else np.nan,
                             base_R=float(R.mean()), placebo_p95=float(np.percentile(d_plc, 95)) if len(d_plc) else np.nan))
    # specchio e tabelle descrittive
    mir = []
    for src in SOURCES:
        for sd, sn in ((rg.SHORT, "SHORT"), (rg.LONG, "LONG")):
            for c, cn in ((rg.ALIGNED, "ALIGNED"), (rg.NEUTRAL, "NEUTRAL"), (rg.OPPOSED, "OPPOSED")):
                k = (side == sd) & (cl[src] == c)
                lo, hi = boot_mean_ci(R[k], blocks[k], rng)
                mir.append(dict(scenario=name, source=src, side=sn, cls=cn, n=int(k.sum()),
                                R=float(R[k].mean()) if k.any() else np.nan, ci_lo=lo, ci_hi=hi,
                                win=float((R[k] > 0).mean()) if k.any() else np.nan))
    bystate = []
    for lvl, key in (("market", "m_state"), ("symbol", "sym_state")):
        for sd, sn in ((rg.SHORT, "SHORT"), (rg.LONG, "LONG")):
            for st in range(len(rg.STATE_NAMES)):
                k = (side == sd) & (cl[key] == st)
                if k.sum():
                    bystate.append(dict(scenario=name, level=lvl, side=sn, state=rg.STATE_NAMES[st], n=int(k.sum()),
                                        R=float(R[k].mean()), win=float((R[k] > 0).mean())))
    month = pd.to_datetime(tr.open_ms, unit="ms", utc=True).dt.strftime("%Y-%m").to_numpy()
    mrows = []
    for mo in sorted(set(month)):
        k = month == mo
        ks = k & (side == rg.SHORT) & (cl["market"] == rg.ALIGNED)
        kb = k & (side == rg.SHORT)
        mrows.append(dict(scenario=name, month=mo, short_n=int(kb.sum()), short_R=float(R[kb].mean()) if kb.any() else np.nan,
                          short_aligned_n=int(ks.sum()), short_aligned_R=float(R[ks].mean()) if ks.any() else np.nan))
    occ_trades = {src: {sn: float((cl[src][side == sd] == rg.ALIGNED).mean()) for sd, sn in ((rg.SHORT, "SHORT"), (rg.LONG, "LONG"))}
                  for src in SOURCES}
    out_tr = tr[["id", "symbol", "side", "open_ms", "net_r"]].copy()
    out_tr["m_state"] = [rg.STATE_NAMES[x] for x in cl["m_state"]]
    out_tr["sym_state"] = [rg.STATE_NAMES[x] for x in cl["sym_state"]]
    return dict(policies=rows, mirror=mir, by_state=bystate, monthly=mrows, aligned_share=occ_trades), out_tr


def verdicts(rows_by_scn: dict):
    """Applica R1-R7 (PREREGISTRAZIONE.md). R5: R1 e R3 veri in S1 e S2."""
    out = []
    keys = {(r["source"], r["policy"]) for sc in rows_by_scn.values() for r in sc}
    for src, pol in sorted(keys):
        per = {}
        for sc, rows in rows_by_scn.items():
            r = next(x for x in rows if x["source"] == src and x["policy"] == pol)
            thirds = [x for x in r["third_deltas"] if x is not None]
            g = {}
            g["R1"] = bool(r["p_delta_le0"] <= THR_P[src] and r["delta"] > 0) if not np.isnan(r["delta"]) else False
            g["R2"] = bool(len(thirds) == 3 and sum(x > 0 for x in thirds) >= 2 and all(x >= -0.15 for x in thirds))
            g["R3"] = bool(not np.isnan(r["p_placebo"]) and r["p_placebo"] <= 0.05)
            need = {"G_A": 0.25, "G_N": 0.50}.get(pol)
            g["R4"] = True if need is None else bool(r["kept_frac"] >= need)
            g["R6"] = bool(not np.isnan(r["delta_short"]) and not np.isnan(r["delta_long"]) and r["delta_short"] > 0 and r["delta_long"] > 0)
            g["R7"] = bool(not np.isnan(r["retained_R_stress"]) and r["retained_R_stress"] >= 0)
            per[sc] = (g, r)
        scs = list(per)
        r5 = all(per[sc][0]["R1"] and per[sc][0]["R3"] for sc in scs)
        main = per["S2"] if "S2" in per else per[scs[0]]
        g = dict(main[0])
        g["R5"] = bool(r5)
        cand = all(g[k] for k in ("R1", "R2", "R3", "R4", "R5", "R6"))
        out.append(dict(source=src, policy=pol, gates=g, candidate=cand, by_scenario={sc: per[sc][0] for sc in scs},
                        main=main[1]))
    return out


# --------------------------------------------------------------------------------------------------- rilevamento svolte
def _ema(x, n):
    out, k = np.empty(len(x)), 2.0 / (n + 1)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = out[i - 1] + k * (x[i] - out[i - 1])
    return out


def _starts(dirv, d, persist=8):
    """Indici t dove inizia una serie di almeno `persist` barre con direzione d (e la barra prima non era d)."""
    eq = (dirv == d).astype(int)
    cs = np.concatenate(([0], np.cumsum(eq)))
    n = len(dirv)
    ok = np.zeros(n, bool)
    t = np.arange(0, max(n - persist + 1, 0))
    ok[t] = (cs[t + persist] - cs[t]) == persist
    prev = np.r_[False, eq[:-1].astype(bool)]
    return ok & ~prev


def detection_experiment(res: dict, sym: str, rng: np.random.Generator):
    r = res[sym]
    b = r["base"]
    agg1 = rg.aggregate(b["ts"], b["o"], b["h"], b["l"], b["c"], b["v"], BAR, 3_600_000)
    f1 = rg.features(agg1["o"], agg1["h"], agg1["l"], agg1["c"], agg1["ts"], 3_600_000, P)
    A1, C1, cl1, ts1 = f1["A"], agg1["c"], agg1["close_ms"], agg1["ts"]
    W, HZ = 24, 96
    turns = []
    for i in range(W, len(C1) - W):
        if np.isnan(A1[i]) or ts1[i + W] - ts1[i - W] != 2 * W * 3_600_000:
            continue
        win = C1[i - W:i + W + 1]
        if C1[i] == win.max() and C1[i] - C1[i + 1:i + W + 1].min() >= 4 * A1[i] and C1[i] - C1[i - W:i].min() >= 4 * A1[i]:
            turns.append((int(cl1[i]), -1))
        elif C1[i] == win.min() and C1[i + 1:i + W + 1].max() - C1[i] >= 4 * A1[i] and C1[i - W:i].max() - C1[i] >= 4 * A1[i]:
            turns.append((int(cl1[i]), +1))
    close15 = r["close_ms"]
    N = len(close15)
    d_v2 = rg.DIR_OF_STATE[r["state"]].astype(int)
    e20, e50 = _ema(C1, 20), _ema(C1, 50)
    sg = np.where(np.arange(len(C1)) < 100, np.nan, np.sign(e20 - e50))
    d_ema = np.nan_to_num(rg._on_base(close15, agg1, sg, 3_600_000), nan=0.0).astype(int)
    starts = {(nm, d): np.flatnonzero(_starts(dv, d)) for nm, dv in (("v2", d_v2), ("ema", d_ema)) for d in (-1, 1)}

    def lag_of(nm, T, nd):
        g0 = int(np.searchsorted(close15, T))
        st = starts[(nm, nd)]
        c = st[(st >= g0 - 16) & (st <= g0 + 96)]
        return int(c[0] - g0) if len(c) else None

    lag_v2 = [lag_of("v2", T, nd) for T, nd in turns]
    lag_ema = [lag_of("ema", T, nd) for T, nd in turns]
    both = [(x, y) for x, y in zip(lag_v2, lag_ema) if x is not None and y is not None]
    # placebo delle svolte: stesse direzioni, istanti spostati di k giorni (circolare) -> quante ne "rileva" il lettore a caso?
    lo, hi = int(close15[0]), int(close15[-1])
    plc_v2, plc_ema = [], []
    for k in rng.integers(5, 61, size=100):
        sh = [(lo + (T + int(k) * DAY - lo) % (hi - lo), nd) for T, nd in turns]
        plc_v2.append(np.mean([lag_of("v2", T, nd) is not None for T, nd in sh]) if sh else np.nan)
        plc_ema.append(np.mean([lag_of("ema", T, nd) is not None for T, nd in sh]) if sh else np.nan)
    # confermati rispetto al tasso di base: movimento favorevole >= 2 ATR(1h) entro 96 barre 15m
    A1b = rg._on_base(close15, agg1, A1, 3_600_000)
    fav = {1: np.full(N, np.nan), -1: np.full(N, np.nan)}
    if N > HZ + 1:
        t = np.arange(N - HZ)
        wh = np.lib.stride_tricks.sliding_window_view(b["h"][1:], HZ).max(axis=1)
        wl = np.lib.stride_tricks.sliding_window_view(b["l"][1:], HZ).min(axis=1)
        fav[1][t] = np.where(np.isnan(A1b[t]), np.nan, (wh - b["c"][t]) >= 2 * A1b[t])
        fav[-1][t] = np.where(np.isnan(A1b[t]), np.nan, (b["c"][t] - wl) >= 2 * A1b[t])
    base_rate = {d: float(np.nanmean(fav[d])) for d in (1, -1)}

    def flips(dirv):
        ev, last_nz = [], 0
        nzfill = np.zeros(len(dirv), int)
        for i, x in enumerate(dirv):
            nzfill[i] = last_nz
            if x != 0:
                last_nz = x
        for d in (-1, 1):
            for t_ in np.flatnonzero(_starts(dirv, d)):
                if nzfill[t_] == -d:
                    ev.append((int(t_), d))
        return ev

    def lift(ev):
        vals = [(fav[d][t_], base_rate[d]) for t_, d in ev if not np.isnan(fav[d][t_])]
        if not vals:
            return np.nan, np.nan, 0
        conf = float(np.mean([v for v, _ in vals]))
        base = float(np.mean([bb for _, bb in vals]))
        return conf, conf / base if base > 0 else np.nan, len(vals)

    ev_v2, ev_ema = flips(d_v2), flips(d_ema)
    days = (close15[-1] - close15[0]) / DAY
    cv, lv, nv = lift(ev_v2)
    ce, le, ne = lift(ev_ema)
    dwell = {}
    for nm, arr in (("simbolo", r["state"]), ("mercato", None)):
        if arr is None:
            continue
        run = np.diff(np.flatnonzero(np.r_[True, arr[1:] != arr[:-1], True]))
        dwell[nm] = float(np.median(run))
    return dict(symbol=sym, turns=len(turns), detected_v2=sum(x is not None for x in lag_v2),
                detected_ema=sum(x is not None for x in lag_ema), both=len(both),
                median_lag_v2=float(np.median([x for x, _ in both])) if both else np.nan,
                median_lag_ema=float(np.median([y for _, y in both])) if both else np.nan, lags_both=both,
                detect_rate_v2=float(np.mean([x is not None for x in lag_v2])) if turns else np.nan,
                detect_rate_v2_placebo_p95=float(np.nanpercentile(plc_v2, 95)) if turns else np.nan,
                detect_rate_v2_placebo_med=float(np.nanmedian(plc_v2)) if turns else np.nan,
                detect_rate_ema=float(np.mean([x is not None for x in lag_ema])) if turns else np.nan,
                detect_rate_ema_placebo_p95=float(np.nanpercentile(plc_ema, 95)) if turns else np.nan,
                flips_v2=len(ev_v2), flips_ema=len(ev_ema), flips_per_day_v2=len(ev_v2) / days, flips_per_day_ema=len(ev_ema) / days,
                confirm_v2=cv, lift_v2=lv, confirm_ema=ce, lift_ema=le, base_rate_up=base_rate[1], base_rate_down=base_rate[-1],
                dwell_median_bars=dwell.get("simbolo"))


def detection_gates(rows):
    both = [x for r in rows for x in r["lags_both"]]
    if not both:
        return dict(D1=False, D2=False, D3=False, note="nessuna svolta rilevata da entrambi")
    mv, me = float(np.median([a for a, _ in both])), float(np.median([e for _, e in both]))
    lift_v2 = float(np.nanmean([r["lift_v2"] for r in rows]))
    lift_ema = float(np.nanmean([r["lift_ema"] for r in rows]))
    fpd = float(np.mean([r["flips_per_day_v2"] for r in rows]))
    tot_turns = sum(r["turns"] for r in rows)
    rate = sum(r["detect_rate_v2"] * r["turns"] for r in rows) / max(tot_turns, 1)
    p95 = sum(r["detect_rate_v2_placebo_p95"] * r["turns"] for r in rows) / max(tot_turns, 1)
    return dict(D1=bool(me > 0 and mv <= 0.5 * me), D2=bool(lift_v2 >= 1.15 and fpd <= 2.0), D3=bool(rate > p95),
                median_lag_v2=mv, median_lag_ema=me, ratio=(mv / me if me else None), lift_v2=lift_v2, lift_ema=lift_ema,
                flips_per_day_v2=fpd, detect_rate_v2=float(rate), detect_rate_placebo_p95=float(p95), n_turns_both=len(both),
                n_turns=int(tot_turns))


# ------------------------------------------------------------------------------------------------------------- rapporto
def f3(x, nd=3):
    return "n/d" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:+.{nd}f}"


def pct(x):
    return "n/d" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100 * x:.0f}%"


def write_report(path, meta, occ, sanity, verd, scen, det, detg, per_symbol_occ):
    L = ["# Laboratorio lettore di regime v2 - rapporto (Claude)\n",
         f"Esecuzione: {meta['when']} | dati: {meta['symbols']} simboli, {meta['bars']} barre 15m, {meta['days']} giorni | "
         f"config `{meta.get('config', '')}` (`{meta['hash']}`) | profilo `classic15` (non validato). Criteri: `PREREGISTRAZIONE.md` (scritti prima).\n",
         "## 0. Sanita' del lettore (prima degli esiti)\n",
         f"- S0a occupazione stati di mercato: {sanity['S0a_text']} -> **{'OK' if sanity['S0a'] else 'FALLITO'}**",
         f"- S0b quota ALIGNED sui trade (8%-60%): {sanity['S0b_text']} -> **{'OK' if sanity['S0b'] else 'FALLITO'}**",
         "- S0c test unitari: eseguiti prima nel workflow.\n",
         "| stato di mercato | quota barre |", "|---|---:|"]
    for k, v in occ.items():
        L.append(f"| {k} | {pct(v)} |")
    L += ["", "## 1. Riconoscimento della svolta (BTC, ETH; 15m)\n",
          "| simbolo | svolte | rilevate v2 (a caso p95) | rilevate EMA20/50 | entrambe | ritardo mediano v2 (barre 15m) | ritardo mediano EMA | cambi/giorno v2 | cambi/giorno EMA | lift confermati v2 | lift EMA | durata mediana stato |",
          "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in det:
        L.append(f"| {r['symbol']} | {r['turns']} | {pct(r['detect_rate_v2'])} ({pct(r['detect_rate_v2_placebo_p95'])}) | {pct(r['detect_rate_ema'])} | {r['both']} | "
                 f"{f3(r['median_lag_v2'], 1)} | {f3(r['median_lag_ema'], 1)} | {r['flips_per_day_v2']:.2f} | {r['flips_per_day_ema']:.2f} | "
                 f"{f3(r['lift_v2'], 2)} | {f3(r['lift_ema'], 2)} | {f3(r['dwell_median_bars'], 0)} |")
    L.append(f"\n**Cancelli:** D1 (ritardo v2 <= 50% EMA): **{'VERO' if detg.get('D1') else 'FALSO'}**; D2 (lift >= 1,15 e <= 2 cambi/giorno): "
             f"**{'VERO' if detg.get('D2') else 'FALSO'}**; D3 (rileva le svolte vere piu' dei placebo): **{'VERO' if detg.get('D3') else 'FALSO'}** "
             f"| dettaglio: {json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in detg.items() if k not in ('D1', 'D2', 'D3')}, ensure_ascii=False)}\n")
    L += ["## 2. Specchio: il lato long funziona quanto lo short quando il regime lo sostiene?\n",
          "R netto medio per trade (IC 95% a blocchi di 7 giorni) per lato e classe. Se LONG|ALIGNED resta negativo e SHORT|ALIGNED no, "
          "un lettore simmetrico non pareggia i lati: serve un motore long diverso.\n"]
    for sc in scen:
        L += [f"\n### Scenario {sc}\n", "| fonte | lato | classe | n | R medio | IC95 | vittorie |", "|---|---|---|---:|---:|---|---:|"]
        for m in scen[sc]["mirror"]:
            L.append(f"| {m['source']} | {m['side']} | {m['cls']} | {m['n']} | {f3(m['R'])} | [{f3(m['ci_lo'])}, {f3(m['ci_hi'])}] | {pct(m['win'])} |")
    L += ["\n## 3. Politiche e cancelli R1-R7\n",
          "delta = R medio dei trade tenuti meno scartati (S_W: R pesato meno R base). Verdetto sullo scenario S2 (fase di oggi) se S1 e S2 concordano su R1/R3 (R5).\n",
          "| fonte | politica | tenuti | delta | P(delta<=0) | P placebo | delta short | delta long | R tenuti (stress -0,08) | R1 | R2 | R3 | R4 | R5 | R6 | R7 | candidata |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|"]
    for v in verd:
        r, g = v["main"], v["gates"]
        yn = lambda b: "si" if b else "no"  # noqa: E731
        L.append(f"| {v['source']} | {v['policy']} | {pct(r['kept_frac'])} | {f3(r['delta'])} | {pct(r['p_delta_le0'])} | {pct(r['p_placebo'])} | "
                 f"{f3(r['delta_short'])} | {f3(r['delta_long'])} | {f3(r['retained_R'])} ({f3(r['retained_R_stress'])}) | "
                 + " | ".join(yn(g[k]) for k in ("R1", "R2", "R3", "R4", "R5", "R6", "R7")) + f" | **{'CANDIDATA' if v['candidate'] else 'no'}** |")
    L.append("\nBase (tutti i trade): R medio " + ", ".join(f"{sc} {f3(scen[sc]['policies'][0]['base_R'])}" for sc in scen) + ".\n")
    L += ["### Dettaglio per scenario (R1/R3)\n", "| fonte | politica | scenario | delta | P(delta<=0) | P placebo | R1 | R3 | terzi (delta) |", "|---|---|---|---:|---:|---:|:-:|:-:|---|"]
    for sc in scen:
        for r in scen[sc]["policies"]:
            g = next(v for v in verd if v["source"] == r["source"] and v["policy"] == r["policy"])["by_scenario"][sc]
            L.append(f"| {r['source']} | {r['policy']} | {sc} | {f3(r['delta'])} | {pct(r['p_delta_le0'])} | {pct(r['p_placebo'])} | "
                     f"{'si' if g['R1'] else 'no'} | {'si' if g['R3'] else 'no'} | {', '.join(f3(x) for x in r['third_deltas'])} |")
    for sc in scen:
        L += [f"\n## 4. Descrittivo per stato - scenario {sc} (nessun cancello)\n", "| livello | lato | stato | n | R medio | vittorie |", "|---|---|---|---:|---:|---:|"]
        for b in scen[sc]["by_state"]:
            L.append(f"| {b['level']} | {b['side']} | {b['state']} | {b['n']} | {f3(b['R'])} | {pct(b['win'])} |")
        L += [f"\n### Mesi - short con mercato ALIGNED ({sc})\n", "| mese | short n | short R | short ALIGNED n | short ALIGNED R |", "|---|---:|---:|---:|---:|"]
        for m in scen[sc]["monthly"]:
            L.append(f"| {m['month']} | {m['short_n']} | {f3(m['short_R'])} | {m['short_aligned_n']} | {f3(m['short_aligned_R'])} |")
    L += ["\n## 5. Occupazione per simbolo (quota barre in ciascuno stato, primi 6)\n"]
    for s, o in per_symbol_occ.items():
        L.append(f"- {s}: " + ", ".join(f"{k} {pct(v)}" for k, v in o.items() if v >= 0.03))
    L += ["\n## Limiti\n", "La replica base13 sottostima i giorni d'oro (R +0,06 contro +0,54 reali): valori assoluti pessimisti, confronti interni validi. "
          "Un periodo di mercato. Trade correlati (blocchi di 7 giorni). Stress costi approssimato (+0,08 R/trade). "
          "Il profilo `scalp1m` per il Brain non e' coperto: servono dati 1m.\n"]
    open(path, "w", encoding="utf-8").write("\n".join(L))


def dwell_stats(state):
    """Durata (barre) delle serie continue di uno stato valido: mediana e quartili."""
    st = np.asarray(state)
    runs = np.diff(np.flatnonzero(np.r_[True, st[1:] != st[:-1], True]))
    vals = st[np.r_[0, np.cumsum(runs)[:-1]]] if len(st) else st
    runs = runs[vals != rg.NA] if len(runs) else runs
    return (float(np.median(runs)), float(np.percentile(runs, 25)), float(np.percentile(runs, 75))) if len(runs) else (np.nan,) * 3


def write_structure(path, meta, occ, sanity, det, detg, dw_mkt, dw_sym, per_symbol_occ, iteration):
    L = ["# Fase STRUTTURALE - lettore di regime v2 (nessun rendimento dei trade usato)\n",
         f"Esecuzione: {meta['when']} | config `{meta['hash']}` | iterazione strutturale n. {iteration} | {meta['symbols']} simboli, {meta['bars']} barre 15m\n",
         f"- S0a occupazione mercato (max <= 60%): {sanity['S0a_text']} -> **{'OK' if sanity['S0a'] else 'FALLITO'}**",
         f"- S0b quota ALIGNED sui trade, solo istanti e lati (8%-60%): {sanity['S0b_text']} -> **{'OK' if sanity['S0b'] else 'FALLITO'}**",
         f"- S0d stabilita' (mediana >= 8 barre): {sanity['S0d_text']} -> **{'OK' if sanity['S0d'] else 'FALLITO'}**",
         f"- **Accettazione strutturale (S0a, S0b, S0d, D1, D2, D3 tutti veri): {'SI -> si puo' + chr(39) + ' passare alla fase completa senza cambiare nulla' if sanity['structural_accept'] else 'NO -> serve una correzione dichiarata (E2) oppure si procede e si dichiara il lettore come non idoneo'}**",
         f"- Stabilita': durata mediana di uno stato di mercato {dw_mkt[0]:.0f} barre 15m (quartili {dw_mkt[1]:.0f}-{dw_mkt[2]:.0f}); "
         f"per simbolo, mediana delle mediane {dw_sym[0]:.0f} (quartili {dw_sym[1]:.0f}-{dw_sym[2]:.0f}).",
         f"- Rilevamento svolte BTC+ETH: D1 **{'VERO' if detg.get('D1') else 'FALSO'}**, D2 **{'VERO' if detg.get('D2') else 'FALSO'}**, D3 **{'VERO' if detg.get('D3') else 'FALSO'}** | "
         f"{json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in detg.items() if k not in ('D1', 'D2', 'D3')}, ensure_ascii=False)}\n",
         "| stato di mercato | quota barre |", "|---|---:|"]
    for k, v in occ.items():
        L.append(f"| {k} | {pct(v)} |")
    L += ["", "| simbolo | svolte | rilevate v2 (placebo p95) | rilevate EMA | ritardo mediano v2 / EMA | cambi/giorno v2 | lift v2 |", "|---|---:|---|---:|---|---:|---:|"]
    for r in det:
        L.append(f"| {r['symbol']} | {r['turns']} | {pct(r['detect_rate_v2'])} ({pct(r['detect_rate_v2_placebo_p95'])}) | {pct(r['detect_rate_ema'])} | "
                 f"{f3(r['median_lag_v2'], 1)} / {f3(r['median_lag_ema'], 1)} | {r['flips_per_day_v2']:.2f} | {f3(r['lift_v2'], 2)} |")
    L += ["", "Occupazione per simbolo (primi 6): "] + [f"- {s}: " + ", ".join(f"{k} {pct(v)}" for k, v in o.items() if v >= 0.03) for s, o in per_symbol_occ.items()]
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")


# ------------------------------------------------------------------------------------------------------------------ main
def synthetic_trades(candles: dict, n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    syms = list(candles)
    t0 = max(int(a[0, 0]) for a in candles.values()) + 400 * BAR
    t1 = min(int(a[-1, 0]) for a in candles.values()) - 10 * BAR
    ot = t0 + rng.integers(0, (t1 - t0) // BAR, n) * BAR
    return pd.DataFrame(dict(id=np.arange(n), symbol=rng.choice(syms, n), side=rng.choice([-1, 1], n), open_ms=ot, close_ms=ot + 4 * BAR,
                             net=0.0, net_r=rng.normal(-0.15, 1.0, n), why="synthetic", reg_state=0, reg_turn=0))


def cfg_name(confirm_n, w15, k, d):
    return f"c{confirm_n}_w{int(round(w15 * 100))}_k{int(round(k * 100))}_d{int(round(d * 100))}"


def cfg_from_name(name):
    import re
    m = re.fullmatch(r"c(\d+)_w(\d+)_k(\d+)_d(\d+)", name)
    if not m:
        raise ValueError(f"configurazione sconosciuta: {name}")
    n, w, k, d = int(m[1]), int(m[2]) / 100, int(m[3]) / 100, int(m[4]) / 100
    prof = rg.Profile("classic15", "15m", (("15m", w), ("1h", round(1 - w, 2))), (("4h", 1.0),), "1h", vr_w=288, dd_lag=4)
    return prof, rg.Params(confirm_n=n, k_thr=k, d_thr=d, dd_thr=round(1.5 * d, 4))


BASELINE = "c2_w60_k25_d20"                                   # v2.0
GRID = [cfg_name(n, w, k, d) for n in (2, 4) for w in (0.6, 0.3) for k in (0.25, 0.15) for d in (0.20, 0.30)]


def use_config(name):
    global PROFILE, P
    PROFILE, P = cfg_from_name(name)


def structure_block(candles, synthetic, inputs):
    """Metriche strutturali per la configurazione attiva. NON legge mai i rendimenti dei trade."""
    res, mkt = build_regime(candles)
    st = mkt["state"]
    valid = st != rg.NA
    occ = {rg.STATE_NAMES[k]: float((st[valid] == k).mean()) for k in range(1, len(rg.STATE_NAMES)) if (st[valid] == k).any()} if valid.any() else {}
    span = (int(min(r["close_ms"][0] for r in res.values())) + 600 * BAR, int(max(r["close_ms"][-1] for r in res.values())))

    def load_trades(i, sc):
        tr = synthetic_trades(candles, 1500, seed=11 + i) if synthetic else pd.read_csv(os.path.join(inputs, f"trades_{sc}_base13.csv.gz"))
        return tr[(tr.open_ms >= span[0]) & (tr.open_ms <= span[1])]

    al = {}
    for i, sc in enumerate(("S1", "S2")):
        tr = load_trades(i, sc).sort_values("open_ms").reset_index(drop=True)
        cl = classify_trades(tr, res, mkt)
        side_ = tr.side.to_numpy()
        al[sc] = {src: {sn: float((cl[src][side_ == sd] == rg.ALIGNED).mean()) for sd, sn in ((rg.SHORT, "SHORT"), (rg.LONG, "LONG"))} for src in SOURCES}
    det = [detection_experiment(res, s, np.random.default_rng(77)) for s in ("BTC", "ETH") if s in res]
    detg = detection_gates(det)
    dw_mkt = dwell_stats(mkt["state"])
    dws = np.array([dwell_stats(r["state"]) for r in res.values()])
    dw_sym = tuple(float(np.nanmedian(dws[:, k])) for k in range(3))
    per_symbol_occ = {}
    for s in list(res)[:6]:
        sv = res[s]["state"][res[s]["state"] != rg.NA]
        per_symbol_occ[s] = {rg.STATE_NAMES[k]: float((sv == k).mean()) for k in range(1, 11)} if len(sv) else {}
    sanity = dict(S0a=bool(occ) and max(occ.values()) <= 0.60, S0a_text=(f"massimo {pct(max(occ.values()))}" if occ else "nessun dato"),
                  S0b=all(0.08 <= v <= 0.60 for sc in al.values() for src in sc.values() for v in src.values()),
                  S0b_text="; ".join(f"{src} short {pct(v['SHORT'])} / long {pct(v['LONG'])}" for src, v in al["S2"].items()),
                  S0d=bool(dw_mkt[0] >= 8), S0d_text=f"{dw_mkt[0]:.0f} barre 15m (minimo 8)")
    sanity["structural_accept"] = bool(sanity["S0a"] and sanity["S0b"] and sanity["S0d"] and detg.get("D1") and detg.get("D2") and detg.get("D3"))
    meta = dict(when=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), symbols=len(res), bars=int(sum(len(r["ts"]) for r in res.values())),
                hash=rg.config_hash(PROFILE, P))
    return dict(res=res, mkt=mkt, occ=occ, sanity=sanity, det=det, detg=detg, dw_mkt=dw_mkt, dw_sym=dw_sym, per_symbol_occ=per_symbol_occ,
                meta=meta, span=span, load_trades=load_trades)


def select_v21(rows):
    """Regola E3: S0a, S0b, S0d veri e D1, D2, D3 veri; tra queste la piu' vicina a v2.0, poi il rapporto di ritardo piu' basso."""
    base = cfg_from_name(BASELINE)
    def changed(nm):
        pr, pa = cfg_from_name(nm)
        return int(pa.confirm_n != base[1].confirm_n) + int(pr.d_weights != base[0].d_weights) + int(pa.k_thr != base[1].k_thr) + int(pa.d_thr != base[1].d_thr)
    ok = [r for r in rows if r["S0a"] and r["S0b"] and r["S0d"] and r["D1"] and r["D2"] and r["D3"]]
    ok.sort(key=lambda r: (changed(r["name"]), r["ratio"] if r["ratio"] is not None else 9e9))
    return ok[0]["name"] if ok else None


def write_grid(path, rows, chosen):
    L = ["# Fase GRIGLIA (E3) - solo metriche strutturali, nessun rendimento dei trade\n",
         f"Regola di scelta (fissata prima): S0a, S0b, S0d e D1, D2, D3 tutti veri; la piu' vicina a v2.0, poi ritardo D1 piu' basso. **Scelta: {chosen or 'NESSUNA -> lettore non idoneo, il laboratorio si ferma'}**\n",
         "| configurazione | S0a (max stato) | S0b | S0d (durata mediana) | D1 (ritardo v2/EMA) | D2 (lift; cambi/giorno) | D3 (rilevate vs placebo p95) | tutti |",
         "|---|---|:-:|---|---|---|---|:-:|"]
    yn = lambda b: "si" if b else "no"  # noqa: E731
    for r in rows:
        L.append(f"| {r['name']}{' (v2.0)' if r['name'] == BASELINE else ''} | {yn(r['S0a'])} ({pct(r['max_occ'])}) | {yn(r['S0b'])} | {yn(r['S0d'])} ({r['dwell']:.0f}) | "
                 f"{yn(r['D1'])} ({f3(r['ratio'], 2) if r['ratio'] is not None else 'n/d'}) | {yn(r['D2'])} ({f3(r['lift'], 2)}; {r['fpd']:.2f}) | "
                 f"{yn(r['D3'])} ({pct(r['rate'])} vs {pct(r['p95'])}) | **{yn(r['all'])}** |")
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")


def jdefault(o):
    return None if (isinstance(o, float) and np.isnan(o)) else (float(o) if isinstance(o, (np.floating, np.integer)) else bool(o) if isinstance(o, np.bool_) else str(o))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=540)
    ap.add_argument("--cache", default="/tmp/regime-cache")
    ap.add_argument("--out", default="results")
    ap.add_argument("--end", default="2026-10-29")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--phase", choices=["structure", "grid", "full"], default="full")
    ap.add_argument("--iteration", type=int, default=1)
    ap.add_argument("--config", default=BASELINE)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t_start = time.time()
    end_ms = calendar.timegm(time.strptime(a.end, "%Y-%m-%d")) * 1000
    candles = labdata.synthetic(a.days, end_ms, n_symbols=12) if a.synthetic else labdata.load_real(a.days, a.cache, end_ms, workers=a.workers)
    print(f"[LAB] simboli con dati: {len(candles)}", flush=True)
    inputs = os.path.join(HERE, "inputs")
    if a.phase == "grid":
        rows = []
        for nm in GRID:
            use_config(nm)
            b = structure_block(candles, a.synthetic, inputs)
            g, sn = b["detg"], b["sanity"]
            rows.append(dict(name=nm, S0a=sn["S0a"], max_occ=max(b["occ"].values()) if b["occ"] else float("nan"), S0b=sn["S0b"], S0d=sn["S0d"],
                             dwell=b["dw_mkt"][0], D1=bool(g.get("D1")), D2=bool(g.get("D2")), D3=bool(g.get("D3")), ratio=g.get("ratio"),
                             lift=g.get("lift_v2", float("nan")), fpd=g.get("flips_per_day_v2", float("nan")), rate=g.get("detect_rate_v2", float("nan")),
                             p95=g.get("detect_rate_placebo_p95", float("nan")), all=sn["structural_accept"], hash=b["meta"]["hash"]))
            print(f"[GRID] {nm} {b['meta']['hash']}: S0a={sn['S0a']} S0b={sn['S0b']} S0d={sn['S0d']} D1={g.get('D1')} D2={g.get('D2')} D3={g.get('D3')} ({time.time() - t_start:.0f}s)", flush=True)
        chosen = select_v21(rows)
        write_grid(os.path.join(a.out, "grid.md"), rows, chosen)
        json.dump(dict(rows=rows, chosen=chosen, seconds=time.time() - t_start), open(os.path.join(a.out, "grid.json"), "w"), default=jdefault, indent=1)
        print(f"[GRID] scelta E3: {chosen}", flush=True)
        return
    use_config(a.config)
    b = structure_block(candles, a.synthetic, inputs)
    res, mkt, occ, sanity, det, detg, span = b["res"], b["mkt"], b["occ"], b["sanity"], b["det"], b["detg"], b["span"]
    meta = dict(b["meta"], days=a.days, config=a.config)
    if a.phase == "structure":
        write_structure(os.path.join(a.out, "structure.md"), meta, occ, sanity, det, detg, b["dw_mkt"], b["dw_sym"], b["per_symbol_occ"], a.iteration)
        json.dump(dict(meta=meta, sanity=sanity, occupancy=occ, detection_gates=detg, dwell_market=b["dw_mkt"], dwell_symbol=b["dw_sym"],
                       detection=[{k: v for k, v in r.items() if k != "lags_both"} for r in det]),
                  open(os.path.join(a.out, "structure.json"), "w"), default=jdefault, indent=1)
        print(f"[LAB] fase STRUTTURA {a.config} in {time.time() - t_start:.0f}s | accettata={sanity['structural_accept']}", flush=True)
        return
    scen_rows, scen_trades = {}, {}
    for i, sc in enumerate(("S1", "S2")):
        tr = b["load_trades"](i, sc)
        rows, trout = analyse_scenario(sc, tr, res, mkt, span, seed=100 + i)
        scen_rows[sc], scen_trades[sc] = rows, trout
        print(f"[LAB] {sc}: {len(tr)} trade analizzati ({time.time() - t_start:.0f}s)", flush=True)
    verd = verdicts({sc: scen_rows[sc]["policies"] for sc in scen_rows})
    write_report(os.path.join(a.out, "report.md"), meta, occ, sanity, verd, scen_rows, det, detg, b["per_symbol_occ"])
    summ = dict(meta=meta, sanity=sanity, occupancy=occ, detection=[{k: v for k, v in r.items() if k != "lags_both"} for r in det], detection_gates=detg,
                scenarios={sc: {k: v for k, v in scen_rows[sc].items()} for sc in scen_rows},
                verdicts=[{k: v for k, v in x.items() if k != "main"} for x in verd], seconds=time.time() - t_start)
    json.dump(summ, open(os.path.join(a.out, "summary.json"), "w"), default=jdefault, indent=1)
    for sc in scen_trades:
        scen_trades[sc].to_csv(os.path.join(a.out, f"trades_regime_{sc}.csv.gz"), index=False)
    print(f"[LAB] fatto in {time.time() - t_start:.0f}s | config {a.config} | candidate: {[(v['source'], v['policy']) for v in verd if v['candidate']]}", flush=True)


if __name__ == "__main__":
    main()
