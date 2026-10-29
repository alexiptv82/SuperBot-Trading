"""
Laboratorio Edge — 29/10/2026
Testa tre ipotesi sull'esistenza di un vantaggio reale:
  Blocco A: impatto costi (maker vs taker)
  Blocco B: concentrazione posizioni (cap stesso lato)
  Blocco C: strategia trend 4h su BTC+ETH

Nessun bot toccato. Nessun file di produzione modificato.
Solo candele pubbliche Bitget in lettura.
"""
from __future__ import annotations
import argparse
import json
import multiprocessing as mp
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))                        # desk
sys.path.insert(0, os.path.join(HERE, "..", "long_lab_claude"))     # labdata, labrun
sys.path.insert(0, HERE)                                             # edge_strategies

import numpy as np
import labdata as ld
import labrun as lr
from edge_strategies import trend_replay, resample_4h


# ─── Blocco B: replay con cap stesso lato ─────────────────────────────────

def replay_b(M: lr.Market, name: str, spec,
             R, mode: str, cost_mult: float = 1.0,
             thr_other: int = 70, seed=None, rscore=None,
             thr_ab: int = 60, max_same_side=None) -> dict:
    """
    Copia di labrun.replay() con 4 righe aggiunte prima di acc.open()
    per applicare il cap di concentrazione (Blocco B).
    Non si tocca desk.engine.PaperAccount.
    """
    from desk.engine import PaperAccount
    from desk.brain import rules_decisions
    from desk.signals import Reading

    lims = lr.limits(cost_mult)
    acc  = PaperAccount(lims, name)

    K, J = M.IDX.shape
    blocked = 0
    rng = np.random.RandomState(seed) if seed is not None else None

    for k in range(K):
        t = int(M.grid[k])

        # on_bar per ogni simbolo
        for j in range(J):
            if not M.valid[k, j]:
                continue
            sym = M.symbols[j]
            row = M.OHLC[k, j]
            acc.on_bar(sym, t, float(row[0]), float(row[1]),
                       float(row[2]), float(row[3]), lr.BAR)

        # roll giornaliero
        if M.day[k] != (M.day[k-1] if k > 0 else ""):
            acc.roll_day(M.day[k], {sym: float(M.OHLC[k, j, 3])
                                     for j, sym in enumerate(M.symbols)
                                     if M.valid[k, j]})

        end = int(M.end[k])

        for j in range(J):
            if not M.valid[k, j]:
                continue
            sym = M.symbols[j]
            if not M.even30[k] and sym not in lr.TIER_AB:
                continue

            feat = {f: float(M.F[f][k, j]) for f in M.F}
            rd = Reading(sym=sym, ts=t, feat=feat, regime=R[mode][k, j],
                         prices={s: float(M.OHLC[k, jj, 3])
                                 for jj, s in enumerate(M.symbols)
                                 if M.valid[k, jj]})
            dec = rules_decisions(rd, spec, acc)
            if dec is None:
                continue

            sd, margin, lev, px, sl, tp, conf, reason, ttype = (
                dec.side, dec.margin, dec.leverage, dec.price,
                dec.sl, dec.tp, dec.confidence, dec.reason, dec.trade_type
            )

            # ── CAP BLOCCO B ──────────────────────────────────────────────
            if max_same_side is not None:
                same = sum(1 for p in acc.positions.values() if p.side == sd)
                if same >= max_same_side:
                    blocked += 1
                    continue
            # ─────────────────────────────────────────────────────────────

            pr2 = {s: float(M.OHLC[k, jj, 3])
                   for jj, s in enumerate(M.symbols) if M.valid[k, jj]}
            acc.open(sym, sd, margin, lev, px, sl, tp, end, pr2,
                     confidence=conf, reason=reason, source="rules",
                     trade_type=ttype)

    trades = [
        (r["id"], r["symbol"], r["side"],
         r["open_ms"], r["close_ms"],
         r["net"], r.get("net_r", 0.0),
         r["why"], 0, 0)
        for r in acc.closed
    ]
    return {
        "name":     name,
        "trades":   trades,
        "equity":   [],
        "blocked":  blocked,
        "open_end": len(acc.positions),
    }


# ─── Worker multiprocessing ────────────────────────────────────────────────

_SHARED: dict = {}

def _init(shared):
    global _SHARED
    _SHARED = shared

def _job_a(args):
    cost_mult, name = args
    M, spec, R = _SHARED["M"], _SHARED["spec"], _SHARED["R"]
    return lr.replay(M, name, spec, R, "S2", cost_mult=cost_mult)

def _job_b(args):
    max_ss, name = args
    M, spec, R = _SHARED["M"], _SHARED["spec"], _SHARED["R"]
    return replay_b(M, name, spec, R, "S2", cost_mult=1.0, max_same_side=max_ss)

def _job_b_placebo(args):
    seed, max_ss, name = args
    M, spec, R = _SHARED["M"], _SHARED["spec"], _SHARED["R"]
    return replay_b(M, name, spec, R, "S2", cost_mult=1.0,
                    max_same_side=max_ss, seed=seed)

def _job_c(args):
    cost_mult, invert, name = args
    raw = _SHARED["raw"]
    return trend_replay(raw, ["BTC", "ETH"], cost_mult, name,
                        invert=invert)


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days",      type=int, default=540)
    ap.add_argument("--end",       default="2026-10-29")
    ap.add_argument("--cache",     default="/tmp/edge-lab-cache")
    ap.add_argument("--out",       default="results")
    ap.add_argument("--workers",   type=int, default=4)
    ap.add_argument("--synthetic", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    print(f"[edge-lab] avvio — {args.days} giorni, end={args.end}, "
          f"synthetic={args.synthetic}", flush=True)

    # ── Dati ──────────────────────────────────────────────────────────────
    end_ms = ld.date_to_ms(args.end)
    if args.synthetic:
        raw = ld.synthetic(args.days, end_ms)
        print("[edge-lab] dati sintetici", flush=True)
    else:
        os.makedirs(args.cache, exist_ok=True)
        raw = ld.load_real(args.days, args.cache, end_ms, args.workers)
        print(f"[edge-lab] dati reali caricati ({len(raw)} simboli)", flush=True)

    # ── Market + features + regime (riuso da labrun) ──────────────────────
    from labfeat import extract_features, SYMBOLS as ALL_SYM
    feats = {}
    for sym in list(raw.keys()):
        if sym in raw and len(raw[sym]) > 50:
            feats[sym] = extract_features(raw[sym])

    import importlib
    spec_mod = importlib.import_module("desk.brain.rules_spec")
    spec     = spec_mod.load()

    M = lr.Market(raw, feats, args.days, end_ms)
    R = {
        "S1": lr.compute_regime(M, mode="S1"),
        "S2": lr.compute_regime(M, mode="S2"),
    }
    print(f"[edge-lab] Market costruito — {M.IDX.shape[0]} barre × "
          f"{M.IDX.shape[1]} simboli", flush=True)

    shared = {"M": M, "spec": spec, "R": R, "raw": raw}
    ctx = mp.get_context("fork")

    # ═══════════════════════════════════════════════════════════════════════
    # BLOCCO A — varianti di costo
    # ═══════════════════════════════════════════════════════════════════════
    jobs_a = [
        (1.00, "base_taker"),    # 16 bp giro (baseline)
        (0.67, "maker_4bp"),     # ~4 bp/lato
        (0.50, "maker_3bp"),     # 3 bp/lato
        (0.00, "zero_cost"),     # lordo puro
    ]
    with ctx.Pool(min(args.workers, len(jobs_a)),
                  initializer=_init, initargs=(shared,)) as pool:
        results_a = pool.map(_job_a, jobs_a)
    print("[edge-lab] Blocco A completato", flush=True)

    # ═══════════════════════════════════════════════════════════════════════
    # BLOCCO B — cap concentrazione
    # ═══════════════════════════════════════════════════════════════════════
    jobs_b = [
        (None, "cap_none"),   # nessun cap (base)
        (5,    "cap_5"),
        (3,    "cap_3"),
        (1,    "cap_1"),
    ]
    # Placebo: 8 cap casuali con seed fisso
    rng_pb = np.random.RandomState(42)
    placebo_caps = [int(rng_pb.randint(2, 8)) for _ in range(8)]
    jobs_b_pb = [(i+1, placebo_caps[i], f"placebo_b_{i+1}")
                 for i in range(8)]

    all_jobs_b = jobs_b + [(None, None)]   # marker per separare
    with ctx.Pool(min(args.workers, len(jobs_b)),
                  initializer=_init, initargs=(shared,)) as pool:
        results_b = pool.map(_job_b, jobs_b)
    with ctx.Pool(min(args.workers, len(jobs_b_pb)),
                  initializer=_init, initargs=(shared,)) as pool:
        results_b_pb = pool.map(_job_b_placebo, jobs_b_pb)
    print("[edge-lab] Blocco B completato", flush=True)

    # ═══════════════════════════════════════════════════════════════════════
    # BLOCCO C — trend 4h BTC+ETH
    # ═══════════════════════════════════════════════════════════════════════
    jobs_c = [
        (0.00, False, "trend4h_lordo"),
        (0.67, False, "trend4h_maker"),
        (1.00, False, "trend4h_taker"),
        (0.00, True,  "trend4h_invertito"),   # placebo
    ]
    with ctx.Pool(min(args.workers, len(jobs_c)),
                  initializer=_init, initargs=(shared,)) as pool:
        results_c = pool.map(_job_c, jobs_c)
    print("[edge-lab] Blocco C completato", flush=True)

    # ═══════════════════════════════════════════════════════════════════════
    # Riepilogo
    # ═══════════════════════════════════════════════════════════════════════
    t1 = int(M.grid[0])
    t2 = int(M.end[-1])

    # Split temporale out-of-sample
    span  = t2 - t1
    t_oos = t1 + int(span * 360 / 540)   # ultimo 1/3 ≈ giorni 361–540

    def summ(res):
        s = lr.summarize(res, t1, t2)
        s_oos = lr.summarize(res, t_oos, t2)
        s["R_oos"] = s_oos["R_medio"]
        s["netto_oos"] = s_oos["netto"]
        return s

    summary = {
        "blocco_A": [summ(r) for r in results_a],
        "blocco_B": [summ(r) for r in results_b],
        "blocco_B_placebo": [summ(r) for r in results_b_pb],
        "blocco_C": [summ(r) for r in results_c],
        "meta": {
            "days": args.days,
            "end":  args.end,
            "t1":   t1,
            "t2":   t2,
            "t_oos": t_oos,
            "elapsed_s": round(time.time() - t0, 1),
        },
    }

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)

    # ── Stampa rapida ──────────────────────────────────────────────────────
    print("\n=== BLOCCO A — Impatto costi ===")
    for s in summary["blocco_A"]:
        print(f"  {s['nome']:20s}  trade={s['trade']:4d}  "
              f"netto={s['netto']:+8.0f}  R={s['R_medio']:+.4f}")

    base_b = summary["blocco_B"][0]
    print(f"\n=== BLOCCO B — Concentrazione (base dd={base_b['dd']:.0f}) ===")
    for s in summary["blocco_B"]:
        print(f"  {s['nome']:12s}  trade={s['trade']:4d}  "
              f"netto={s['netto']:+8.0f}  dd={s['dd']:.0f}  "
              f"bloccate={s.get('bloccate', 0)}")
    pb_netti = [s["netto"] for s in summary["blocco_B_placebo"]]
    print(f"  placebo B mediana netto={np.median(pb_netti):+.0f}")

    print("\n=== BLOCCO C — Trend 4h BTC+ETH ===")
    for s in summary["blocco_C"]:
        print(f"  {s['nome']:24s}  trade={s['trade']:3d}  "
              f"R={s['R_medio']:+.4f}  R_oos={s['R_oos']:+.4f}")

    print(f"\n[edge-lab] fatto in {summary['meta']['elapsed_s']}s — "
          f"risultati in {args.out}/", flush=True)


if __name__ == "__main__":
    main()
