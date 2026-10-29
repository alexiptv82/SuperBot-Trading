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
import calendar
import json
import multiprocessing as mp
import os
import sys
import time as _time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))                        # desk
sys.path.insert(0, os.path.join(HERE, "..", "long_lab_claude"))     # labdata, labfeat, labrun
sys.path.insert(0, HERE)                                             # edge_strategies

import numpy as np
import labdata as ld
import labfeat as lf
import labrun as lr
from edge_strategies import trend_replay


# ─── Blocco B: replay con cap stesso lato (monkey-patch in processo isolato) ─

def _replay_b_worker(args):
    """Worker: chiama replay() con acc.open() intercettata per il cap."""
    max_ss, name, cost_mult = args
    M   = _SHARED["M"]
    R   = _SHARED["R"]          # regime dict con mode="S2"
    spec = {}                    # base13

    if max_ss is None:
        # Nessun cap: replay standard
        res = lr.replay(M, name, spec, R, "S2", cost_mult=cost_mult)
        return res

    # Monkey-patch in processo forked (sicuro: ogni worker ha il proprio spazio)
    from desk.engine import PaperAccount
    _orig_open = PaperAccount.open
    _blocked_cnt = [0]

    def _capped_open(self, sym, sd, *a, **kw):
        same = sum(1 for p in self.positions.values() if p.side == sd)
        if same >= max_ss:
            _blocked_cnt[0] += 1
            return None, None
        return _orig_open(self, sym, sd, *a, **kw)

    PaperAccount.open = _capped_open
    try:
        res = lr.replay(M, name, spec, R, "S2", cost_mult=cost_mult)
    finally:
        PaperAccount.open = _orig_open

    res["blocked"] = _blocked_cnt[0]
    return res


def _replay_b_placebo_worker(args):
    """Worker per placebo Blocco B: cap casuale con seed fisso."""
    seed, cap, name = args
    return _replay_b_worker((cap, name, 1.0))


# ─── Worker per Blocco A ──────────────────────────────────────────────────────

def _replay_a_worker(args):
    cost_mult, name = args
    return lr.replay(_SHARED["M"], name, {}, _SHARED["R"], "S2",
                     cost_mult=cost_mult)


# ─── Worker per Blocco C ──────────────────────────────────────────────────────

def _replay_c_worker(args):
    cost_mult, invert, name = args
    return trend_replay(_SHARED["raw"], ["BTC", "ETH"],
                        cost_mult, name, invert=invert)


# ─── Stato condiviso tra i worker ─────────────────────────────────────────────

_SHARED: dict = {}

def _init_worker(shared):
    global _SHARED
    _SHARED = shared


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days",      type=int, default=540)
    ap.add_argument("--end",       default="2026-10-29")
    ap.add_argument("--cache",     default="/tmp/edge-lab-cache")
    ap.add_argument("--out",       default="results")
    ap.add_argument("--workers",   type=int, default=4)
    ap.add_argument("--synthetic", action="store_true")
    args = ap.parse_args()

    t0_wall = _time.time()
    print(f"[edge-lab] avvio — {args.days} giorni, end={args.end}, "
          f"synthetic={args.synthetic}", flush=True)

    # ── Dati ──────────────────────────────────────────────────────────────────
    end_ms = int(calendar.timegm(
        _time.strptime(args.end, "%Y-%m-%d")
    ) * 1000)
    t_start = end_ms - args.days * ld.DAY

    if args.synthetic:
        raw = ld.synthetic(args.days, end_ms)
        print("[edge-lab] dati sintetici", flush=True)
    else:
        os.makedirs(args.cache, exist_ok=True)
        meta_path = os.path.join(args.cache, "meta.json")
        if os.path.exists(meta_path):
            saved = json.load(open(meta_path))
            end_ms  = int(saved["end_ms"])
            t_start = end_ms - args.days * ld.DAY
        raw = ld.load_real(args.days, args.cache, end_ms,
                           workers=min(6, args.workers + 2))
        if not os.path.exists(meta_path):
            json.dump({"end_ms": end_ms, "days": args.days}, open(meta_path, "w"))
        print(f"[edge-lab] dati reali — {len(raw)} simboli", flush=True)

    # ── Feature ──────────────────────────────────────────────────────────────
    feats = {}
    for sym, arr in raw.items():
        if len(arr) > 50:
            feats[sym] = lf.extract_symbol(arr)
    print(f"[edge-lab] feature estratte — {len(feats)} simboli", flush=True)

    # ── Market + Regime ───────────────────────────────────────────────────────
    M  = lr.Market(raw, feats, t_start, end_ms)
    R  = lr.compute_regime(M, mode="S2")   # modalità primaria (oggi congelata)
    print(f"[edge-lab] Market {M.K} barre × {M.J} simboli, "
          f"regime S2 calcolato", flush=True)

    shared = {"M": M, "R": R, "raw": raw}
    ctx    = mp.get_context("fork")

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCCO A — varianti di costo
    # ══════════════════════════════════════════════════════════════════════════
    jobs_a = [
        (1.00, "base_taker"),    # 16 bp/giro — baseline
        (0.67, "maker_4bp"),     # ≈4 bp/lato (ordini maker)
        (0.50, "maker_3bp"),     # 3 bp/lato
        (0.00, "zero_cost"),     # lordo puro
    ]
    with ctx.Pool(min(args.workers, len(jobs_a)),
                  initializer=_init_worker, initargs=(shared,)) as pool:
        results_a = pool.map(_replay_a_worker, jobs_a)
    print("[edge-lab] Blocco A completato", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCCO B — cap concentrazione
    # ══════════════════════════════════════════════════════════════════════════
    jobs_b = [
        (None, "cap_none", 1.0),   # nessun cap (base)
        (5,    "cap_5",    1.0),
        (3,    "cap_3",    1.0),
        (1,    "cap_1",    1.0),
    ]
    rng_pb    = np.random.RandomState(42)
    pb_caps   = [int(rng_pb.randint(2, 8)) for _ in range(8)]
    jobs_b_pb = [(i + 1, pb_caps[i], f"placebo_b_{i+1}") for i in range(8)]

    with ctx.Pool(min(args.workers, len(jobs_b)),
                  initializer=_init_worker, initargs=(shared,)) as pool:
        results_b = pool.map(_replay_b_worker, jobs_b)
    with ctx.Pool(min(args.workers, len(jobs_b_pb)),
                  initializer=_init_worker, initargs=(shared,)) as pool:
        results_b_pb = pool.map(_replay_b_placebo_worker, jobs_b_pb)
    print("[edge-lab] Blocco B completato", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCCO C — trend 4h BTC+ETH
    # ══════════════════════════════════════════════════════════════════════════
    jobs_c = [
        (0.00, False, "trend4h_lordo"),
        (0.67, False, "trend4h_maker"),
        (1.00, False, "trend4h_taker"),
        (0.00, True,  "trend4h_invertito"),   # placebo segnale invertito
    ]
    with ctx.Pool(min(args.workers, len(jobs_c)),
                  initializer=_init_worker, initargs=(shared,)) as pool:
        results_c = pool.map(_replay_c_worker, jobs_c)
    print("[edge-lab] Blocco C completato", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # Riepilogo e output
    # ══════════════════════════════════════════════════════════════════════════
    t_oos = t_start + int((end_ms - t_start) * 360 / 540)   # inizio ultimo terzo

    def summ(res):
        s     = lr.summarize(res, t_start, end_ms)
        s_oos = lr.summarize(res, t_oos, end_ms)
        s["R_oos"]    = s_oos["R_medio"]
        s["netto_oos"] = s_oos["netto"]
        return s

    summary = {
        "blocco_A":        [summ(r) for r in results_a],
        "blocco_B":        [summ(r) for r in results_b],
        "blocco_B_placebo":[summ(r) for r in results_b_pb],
        "blocco_C":        [summ(r) for r in results_c],
        "meta": {
            "days":      args.days,
            "end":       args.end,
            "end_ms":    end_ms,
            "t_start":   t_start,
            "t_oos":     t_oos,
            "elapsed_s": round(_time.time() - t0_wall, 1),
        },
    }

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)

    # ── Stampa finale ──────────────────────────────────────────────────────────
    print("\n=== BLOCCO A — Impatto costi ===")
    for s in summary["blocco_A"]:
        print(f"  {s['nome']:20s}  trade={s['trade']:4d}  "
              f"netto={s['netto']:+9.0f}  R={s['R_medio']:+.4f}")

    base_b = summary["blocco_B"][0]
    print(f"\n=== BLOCCO B — Concentrazione  (base: dd={base_b['dd']:.0f}$) ===")
    for s in summary["blocco_B"]:
        print(f"  {s['nome']:12s}  trade={s['trade']:4d}  "
              f"netto={s['netto']:+9.0f}  dd={s['dd']:.0f}  "
              f"bloccate={s.get('bloccate', 0)}")
    pb_n = [s["netto"] for s in summary["blocco_B_placebo"]]
    print(f"  placebo B  mediana netto={np.median(pb_n):+.0f}$")

    print("\n=== BLOCCO C — Trend 4h BTC+ETH ===")
    for s in summary["blocco_C"]:
        print(f"  {s['nome']:26s}  trade={s['trade']:3d}  "
              f"R={s['R_medio']:+.4f}  R_oos={s['R_oos']:+.4f}")

    elapsed = summary["meta"]["elapsed_s"]
    print(f"\n[edge-lab] completato in {elapsed}s — "
          f"risultati in {args.out}/summary.json", flush=True)


if __name__ == "__main__":
    main()
