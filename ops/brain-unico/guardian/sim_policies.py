#!/usr/bin/env python3
"""Simulazione SINTETICA delle politiche di protezione del profitto (Smart Profit Guardian).

Nessun dato reale, nessuna rete, solo libreria standard. Serve a mostrare proprieta'
matematiche delle politiche, NON a stimare rendimenti di SuperBot.

Modello: ogni sessione offre un numero Poisson di occasioni; ogni trade chiude a +2R o
-1R lordi (indipendenti), meno un costo fisso in R. R = 85.71 USDT (4.2857% di 2000,
limite per posizione dell'Arena). La dimensione del trade (0..1 R) e' decisa dalla
politica in base al PnL di sessione e al suo picco.

Uso:  python3 -I sim_policies.py [--sessions 40000] [--seed 7]
"""
import argparse
import math
import random
import statistics as st

R = 85.71           # USDT per 1R
COST_R = 0.10       # costi a/r per trade, in R (ipotesi)
LOSS_R = 1.0 + COST_R


def poisson(rng, lam):
    k, L, p = 0, math.exp(-lam), rng.random()
    while p > L:
        k += 1
        p *= rng.random()
    return k


def run_session(rng, p_base, p_after, decay_at_r, n_mean, policy):
    """Ritorna (pnl_finale, picco, n_trade)."""
    pnl = peak = 0.0
    trades = 0
    for _ in range(poisson(rng, n_mean)):
        size = policy(pnl, peak)
        if size <= 0:
            break
        p = p_after if pnl >= decay_at_r * R else p_base
        out = (2.0 if rng.random() < p else -1.0) - COST_R
        pnl += out * R * size
        peak = max(peak, pnl)
        trades += 1
    return pnl, peak, trades


# --- politiche -------------------------------------------------------------

def baseline(pnl, peak):
    return 1.0


def fixed_400_500(pnl, peak):
    """B: soglie fisse del report: >= +400 meta' rischio, >= +500 stop aperture."""
    if peak >= 500 or pnl >= 500:
        return 0.0
    return 0.5 if pnl >= 400 else 1.0


def floor_policy(activation_r, giveback):
    """D: floor mobile (tipo CPPI). Armato quando il picco >= activation_r * R;
    floor = (1-giveback) * picco; il rischio del nuovo trade (costi inclusi) non puo'
    superare la distanza dal floor; sotto 0.25 R la sessione si blocca."""
    def f(pnl, peak):
        if peak < activation_r * R:
            return 1.0
        room = (pnl - (1 - giveback) * peak) / R
        size = min(1.0, room / LOSS_R)
        return size if size >= 0.25 else 0.0
    return f


def with_session_loss_limit(inner, limit_r):
    """E/F: limite di perdita di sessione in R, applicato prima dell'apertura."""
    def f(pnl, peak):
        room = (pnl + limit_r * R) / R
        size = min(inner(pnl, peak), room / LOSS_R)
        return size if size >= 0.25 else 0.0
    return f


SCENARIOS = {
    "S1 edge costante +0.10R": (0.40, 0.40),
    "S2 edge nullo": (0.3667, 0.3667),
    "S3 edge che decade dopo +4R (rincorsa)": (0.40, 0.30),
}

POLICIES = {
    "A baseline": baseline,
    "B fissa 400/500": fixed_400_500,
    "D floor 25% (att. 3R)": floor_policy(3.0, 0.25),
    "D2 floor 25% (att. 4.67R=400)": floor_policy(4.67, 0.25),
    "E solo stop sessione -3R": with_session_loss_limit(baseline, 3.0),
    "F D2 + stop sessione -3R": with_session_loss_limit(floor_policy(4.67, 0.25), 3.0),
}


def leverage_table(margin=400.0, fee=0.0006, slip=0.0003):
    """Relazione leva / stop / costi con rischio fisso = 1R (ipotesi di costo)."""
    rows = []
    for lev in (5, 10, 20, 35, 50):
        notional = margin * lev
        cost = notional * 2 * (fee + slip)
        c = cost / R
        stop = (R - cost) / notional
        breakeven = 1.0 / (3.0 - 3.0 * c)   # TP a 2x la distanza dello stop
        rows.append((lev, notional, cost, c, stop, breakeven))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=40000)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    print("Leva con margine 400 USDT e rischio massimo 1R = 85.71 USDT (costi ipotetici 0.06%+0.03% per lato)")
    print(f"{'leva':>5} {'nozionale':>9} {'costi':>7} {'costi/R':>8} {'stop max':>9} {'win rate pareggio (TP 2x)':>26}")
    for lev, n, cost, c, stop, be in leverage_table():
        print(f"{lev:>4}x {n:>9.0f} {cost:>7.1f} {c:>8.1%} {stop:>9.2%} {be:>26.1%}")
    print()

    hdr = f"{'scenario':40s} {'politica':30s} {'media':>7s} {'p5':>8s} {'trade':>6s} {'giveback|picco>=400':>20s} {'fine<75% picco':>15s}"
    print(hdr)
    for sname, (pb, pa) in SCENARIOS.items():
        for pname, pol in POLICIES.items():
            rng = random.Random(a.seed)
            res = [run_session(rng, pb, pa, 4.0, 6, pol) for _ in range(a.sessions)]
            pnls = sorted(r[0] for r in res)
            hi = [r for r in res if r[1] >= 400]
            gb = st.mean(r[1] - r[0] for r in hi) if hi else 0.0
            under = sum(1 for r in hi if r[0] < 0.75 * r[1]) / len(hi) if hi else 0.0
            print(f"{sname:40s} {pname:30s} {st.mean(pnls):7.1f} {pnls[int(0.05 * len(pnls))]:8.1f} "
                  f"{st.mean(r[2] for r in res):6.2f} {gb:20.1f} {under:15.1%}")
        print()
    rng = random.Random(1)
    res = [run_session(rng, 0.40, 0.40, 99, 6, baseline) for _ in range(a.sessions)]
    print(f"S1 baseline: sessioni con picco >= +400: {sum(r[1] >= 400 for r in res) / len(res):.1%}; "
          f">= +500: {sum(r[1] >= 500 for r in res) / len(res):.1%}")


if __name__ == "__main__":
    main()
