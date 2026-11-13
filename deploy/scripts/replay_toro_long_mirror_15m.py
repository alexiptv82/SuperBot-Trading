#!/usr/bin/env python3
"""Replay di STUDIO del prototipo Toro LONG Mirror 15m su mercati SINTETICI (nessun dato reale, nessun ordine).

Scopo: misurare il comportamento del prototipo in tre regimi separati (rialzo, ribasso con rimbalzi, laterale) e
confrontarlo con ingressi LONG casuali con le STESSE uscite e gli STESSI costi. I numeri descrivono il generatore
sintetico, non il mercato: non autorizzano nulla e non sostituiscono un backtest su storico reale 15m.

Regole del replay (ipotesi di studio, non parametri del motore):
- decisione alla chiusura della candela 15m t, solo candele chiuse; ingresso all'apertura di t+1 (nessuna informazione futura);
- trend 4h dal lettore RC84 invariato (signals.htf_trend su barre 4h CHIUSE, EMA50/EMA200);
- uscite: stop = 1.2 x ATR(14) 1h chiuso, limitato 0.3%-3.5% (come signals.read_symbol), TP = 1.8 x stop, massimo 24 h;
  se nella stessa candela si toccano stop e target vale lo stop (ipotesi prudente);
- costi del motore PAPER: commissione 6 bp per lato, slippage 2 bp per lato, funding LONG 1 bp ogni 8 h;
- una posizione per mercato alla volta. Rendimenti in % del nozionale (senza leva).

Uso: python deploy/scripts/replay_toro_long_mirror_15m.py [--days 60] [--seeds 6] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
from desk import signals as S  # noqa: E402
from desk.long_mirror_15m import BAR_MS, MIN_CLOSED, inspect_long_mirror_15m  # noqa: E402

H1, H4 = 3_600_000, 14_400_000
FEE_BP, SLIP_BP, FUND_BP_8H = 6.0, 2.0, 1.0
MAX_HOLD = 96
CONTROL_DRAWS = 20                   # estrazioni casuali per mercato
WARMUP_DAYS = 40                     # EMA200 su 4h richiede >= 200 barre 4h (33,3 giorni)
T0 = 1_780_000_000_000 - 1_780_000_000_000 % H4
REGIMES = ("rialzo", "ribasso_con_rimbalzi", "laterale")


def market(regime: str, days: int, seed: int) -> np.ndarray:
    """Candele 15m sintetiche con volatilita' a grappoli e volume legato all'ampiezza del movimento."""
    rng = np.random.default_rng(seed)
    n = (WARMUP_DAYS + days) * 96
    vol = np.empty(n)
    v = 0.0025
    for i in range(n):                                   # volatilita' a grappoli (persistenza 0.98)
        v = 0.98 * v + 0.02 * 0.0025 * np.exp(rng.normal(0, 0.6))
        vol[i] = v
    eps = rng.standard_normal(n) * vol
    r = np.empty(n)
    if regime == "rialzo":
        drift = np.full(n, 0.006 / 96)                   # +0,6% al giorno
    elif regime == "ribasso_con_rimbalzi":
        drift = np.full(n, -0.015 / 96)                  # -1,5% al giorno fuori dai rimbalzi
        i = 0
        while i < n:                                     # un rimbalzo ogni 1-3 giorni: 4-12 h, +1,5%-4% in totale
            i += int(rng.integers(96, 288))
            ln = int(rng.integers(16, 48))
            drift[i:i + ln] = rng.uniform(0.015, 0.04) / ln
            i += ln                                      # in media circa -0,3% al giorno: il 4h resta ribassista
    elif regime == "laterale":
        drift = np.zeros(n)
    else:
        raise ValueError(regime)
    logp = np.log(100.0)
    level = logp
    for i in range(n):
        mr = -0.02 * (logp - level) if regime == "laterale" else 0.0     # ritorno verso il livello (laterale)
        r[i] = drift[i] + mr + eps[i] + (0.05 * r[i - 1] if i else 0.0)  # leggera persistenza
        logp += r[i]
    close = 100.0 * np.exp(np.cumsum(r))
    op = np.r_[100.0, close[:-1]]
    wick = np.abs(rng.normal(0, 0.5, (2, n))) * vol
    hi = np.maximum(op, close) * (1 + wick[0])
    lo = np.minimum(op, close) * (1 - wick[1])
    volume = 1000 * np.exp(rng.normal(0, 0.3, n)) * (1 + 150 * np.abs(r))
    ts = T0 + np.arange(n) * BAR_MS
    return np.column_stack([ts, op, hi, lo, close, volume])


def exit_trade(a: np.ndarray, k: int, sl_pct: float) -> dict:
    """Ingresso all'apertura della candela k; uscita su stop, target o tempo massimo."""
    entry = a[k, 1] * (1 + SLIP_BP / 1e4)
    sl, tp = entry * (1 - sl_pct), entry * (1 + 1.8 * sl_pct)
    last = min(len(a) - 1, k + MAX_HOLD - 1)
    px, why, j = a[last, 4], "tempo", last
    for j in range(k, last + 1):
        if a[j, 3] <= sl:
            px, why = sl, "stop"
            break
        if a[j, 2] >= tp:
            px, why = tp, "target"
            break
    exit_px = px * (1 - SLIP_BP / 1e4)
    hours = (j - k + 1) * 0.25
    gross = exit_px / entry - 1
    cost = FEE_BP / 1e4 * (1 + exit_px / entry) + FUND_BP_8H / 1e4 * hours / 8
    mae = float(a[k:j + 1, 3].min() / entry - 1)
    return {"k": k, "exit": j, "why": why, "net": gross - cost, "gross": gross, "hours": hours, "mae": mae,
            "sl_pct": sl_pct}


def run_market(a: np.ndarray, start: int) -> tuple[list[dict], list[int], dict]:
    b4 = S.resample(a, H4)
    b1 = S.resample(a, H1)
    trades, eligible, states = [], [], {}
    t4_cache: dict[int, str] = {}
    busy_until = -1
    for t in range(start, len(a) - 1):
        now = int(a[t, 0]) + BAR_MS                            # chiusura della candela t: t+1 non e' visibile
        n4 = int(np.searchsorted(b4[:, 0], now - H4, side="right"))
        if n4 not in t4_cache:
            t4_cache[n4] = S.htf_trend(b4[:n4], now, H4)["state"]
        t4 = t4_cache[n4]
        window = a[t + 1 - (MIN_CLOSED + 10):t + 1]
        r = inspect_long_mirror_15m("BTCUSDT", window, now, trend4h_state=t4)
        key = r.state if r.state != "NO_TRADE" else "NO_TRADE:" + r.reason
        states[key] = states.get(key, 0) + 1
        if t <= busy_until:
            continue
        eligible.append(t)
        if r.state == "NO_TRADE":
            continue
        n1 = int(np.searchsorted(b1[:, 0], now - H1, side="right"))
        sl_pct = float(min(0.035, max(0.003, 1.2 * S.atr(b1[:n1]) / b1[n1 - 1, 4])))
        tr = exit_trade(a, t + 1, sl_pct)
        tr.update(kind=r.state, score=r.score, trend4h=t4)
        trades.append(tr)
        busy_until = tr["exit"]
    return trades, eligible, states


def stats(nets: list[float]) -> dict:
    if not nets:
        return {"n": 0}
    x = np.asarray(nets)
    eq = np.cumsum(x)
    dd = float((np.maximum.accumulate(np.r_[0.0, eq]) - np.r_[0.0, eq]).max())
    return {"n": int(len(x)), "win": round(float((x > 0).mean()), 3), "media_pct": round(float(x.mean()) * 100, 4),
            "mediana_pct": round(float(np.median(x)) * 100, 4), "somma_pct": round(float(x.sum()) * 100, 2),
            "max_drawdown_pct": round(dd * 100, 2),
            "t": round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2) if len(x) > 2 and x.std() > 0 else None}


def random_control(a: np.ndarray, eligible: list[int], n: int, rng: np.random.Generator) -> list[float]:
    """Una estrazione: stesso numero di ingressi LONG, istanti casuali senza sovrapposizione, stesse uscite e costi."""
    if n == 0:
        return []
    b1 = S.resample(a, H1)
    out, busy = [], -1
    picks = sorted(rng.choice(eligible, size=min(len(eligible), n * 3), replace=False))
    for t in picks:
        if t <= busy or len(out) >= n:
            continue
        now = int(a[t, 0]) + BAR_MS
        n1 = int(np.searchsorted(b1[:, 0], now - H1, side="right"))
        sl_pct = float(min(0.035, max(0.003, 1.2 * S.atr(b1[:n1]) / b1[n1 - 1, 4])))
        tr = exit_trade(a, t + 1, sl_pct)
        out.append(tr["net"])
        busy = tr["exit"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--json")
    args = ap.parse_args()
    report = {"nota": "MERCATI SINTETICI: risultati del generatore, non del mercato reale", "giorni": args.days,
              "semi": args.seeds, "costi": {"fee_bp_lato": FEE_BP, "slip_bp_lato": SLIP_BP, "funding_bp_8h": FUND_BP_8H},
              "regimi": {}}
    for regime in REGIMES:
        allt, ctrl, states, per_seed = [], [], {}, []
        for seed in range(args.seeds):
            a = market(regime, args.days, 1000 * REGIMES.index(regime) + seed)
            trades, eligible, st = run_market(a, WARMUP_DAYS * 96)
            for k, v in st.items():
                states[k] = states.get(k, 0) + v
            draws = [random_control(a, eligible, len(trades), np.random.default_rng(seed * 100 + d))
                     for d in range(CONTROL_DRAWS)]
            for c in draws:
                ctrl += c
            allt += trades
            mine = sum(t["net"] for t in trades)
            sums = [sum(c) for c in draws]
            per_seed.append({"seed": seed, "trades": len(trades),
                             "somma_pct": round(mine * 100, 2),
                             "controllo_somma_media_pct": round(float(np.mean(sums)) * 100, 2),
                             "quota_controlli_battuti": round(float(np.mean([mine > x for x in sums])), 2),
                             "buy_and_hold_pct": round((a[-1, 4] / a[WARMUP_DAYS * 96, 1] - 1) * 100, 2)})
        by_kind = {k: stats([t["net"] for t in allt if t["kind"] == k])
                   for k in ("LONG_CONTINUATION_CANDIDATE", "LONG_BOUNCE_CANDIDATE")}
        whys = {w: sum(1 for t in allt if t["why"] == w) for w in ("stop", "target", "tempo")}
        report["regimi"][regime] = {
            "prototipo": stats([t["net"] for t in allt]), "per_tipo": by_kind, "uscite": whys,
            "controllo_casuale": stats(ctrl),
            "stop_medio_pct": round(float(np.mean([t["sl_pct"] for t in allt])) * 100, 3) if allt else None,
            "mae_peggiore_pct": round(min(t["mae"] for t in allt) * 100, 2) if allt else None,
            "stati": dict(sorted(states.items(), key=lambda kv: -kv[1])), "per_seme": per_seed}
    txt = json.dumps(report, indent=1, ensure_ascii=False)
    if args.json:
        with open(args.json, "w") as fh:
            fh.write(txt)
    print(txt)


if __name__ == "__main__":
    main()
