#!/usr/bin/env python3
"""E0: misurare sugli storici CERTIFICATI se le nuove aperture dopo un guadagno di sessione e i reingressi ripetuti
peggiorano il risultato. Offline, sola libreria standard, nessuna rete, nessuna scrittura sugli input.

Ingresso: `examples.jsonl` prodotto dal Training Dataset Builder (PR #118) su copie attestate di Fase 0.
Uscita: SOLO numeri (nessun simbolo, prezzo, saldo o testo), in un file NUOVO 0600 fuori da qualunque repository.

Uso:
  python3 -I e0_measure.py --examples DIR/examples.jsonl --out /percorso/nuovo/e0.json
         [--session-hour 8] [--tz Europe/Rome] [--reentry-window-h 12] [--arm-r 4] [--seed 7] [--boot 2000]
         [--allow-unattested]     # solo per prove: l'esito e' marcato NOT_CERTIFIED

Domande pre-registrate (contrasti PRIMARI, corretti con Holm):
  H1  EV dei trade aperti con PnL realizzato di sessione >= arm_r R  contro  trade aperti con PnL di sessione in [-1R, +1R)
  H2  EV dei reingressi di indice >= 3 sulla stessa tesi             contro  primi ingressi (indice 1)
Tutto il resto (fasce intermedie, dopo TP / dopo SL, giveback, sensibilita') e' ESPLORATIVO.

Metodo: r = PnL netto in R (`net_r` registrato; altrimenti PnL / mediana delle perdite del flusso, marcato `r_proxy`);
effetto fisso per flusso (r meno la media del flusso, cosi' un bot migliore non crea effetti spuri); differenza fra
medie con intervallo da bootstrap a blocchi di SESSIONE dentro ogni flusso. Verdetto per contrasto:
  inconclusive_small_sample  meno di MIN_TRADES trade o MIN_SESSIONS sessioni in uno dei due gruppi
  worse                      limite superiore dell'IC 95% < 0 e p corretto (Holm) < 0,05
  better                     limite inferiore dell'IC 95% > 0 e p corretto < 0,05
  no_evidence                altrimenti (NON significa "uguale": significa che i dati non bastano a dirlo)
Il PnL di sessione e' solo REALIZZATO: gli storici non hanno l'equity mark-to-market per ciclo (limite dichiarato).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics as st
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

MIN_TRADES, MIN_SESSIONS = 30, 10
H1_BASE = (-1.0, 1.0)
REENTRY_PRIMARY = 3
NOT_ATTESTED = ("input_not_attested", "provenance_not_anchored")


# --------------------------------------------------------------------------- selezione

def select(rows: list, allow_unattested: bool = False) -> tuple:
    """(trade usabili, esclusi per motivo). Nessuna riga viene modificata o cancellata dall'input."""
    out, excl = [], Counter()
    for r in rows:
        o, p = r.get("outcome") or {}, r.get("provenance") or {}
        if r.get("record_kind") != "executed":
            excl["not_executed"] += 1
        elif r.get("is_synthetic") is not False:
            excl["synthetic"] += 1
        elif p.get("duplicate_of"):
            excl["duplicate"] += 1
        elif not allow_unattested and any(x in (r.get("ineligible_reasons") or []) for x in NOT_ATTESTED):
            excl["not_attested"] += 1
        elif o.get("status") != "closed" or o.get("net_pnl") is None:
            excl["not_closed_or_unknown_pnl"] += 1
        elif not isinstance(o.get("opened_ms"), int) or not isinstance(o.get("closed_ms"), int) \
                or o["closed_ms"] < o["opened_ms"] or r.get("side") not in (1, -1):
            excl["bad_times_or_side"] += 1
        else:
            out.append({"stream": f"{r['source_system']}|{r['source_run']}", "symbol": r["symbol"], "side": r["side"],
                        "opened": o["opened_ms"], "closed": o["closed_ms"], "pnl": float(o["net_pnl"]),
                        "net_r": o.get("net_r") if isinstance(o.get("net_r"), (int, float)) else None,
                        "manual": bool(o.get("is_manual"))})
    return out, excl


def assign_r(trades: list) -> dict:
    """r per trade. Senza `net_r`: PnL / mediana delle perdite del flusso (proxy dichiarato)."""
    info = {}
    by = defaultdict(list)
    for t in trades:
        by[t["stream"]].append(t)
    for s, ts in by.items():
        losses = [-t["pnl"] for t in ts if t["pnl"] < 0]
        unit = st.median(losses) if losses else None
        proxy = 0
        for t in ts:
            if t["net_r"] is not None:
                t["r"] = float(t["net_r"])
            elif unit:
                t["r"], proxy = t["pnl"] / unit, proxy + 1
            else:
                t["r"] = None
        info[s] = {"trades": len(ts), "r_proxy_trades": proxy}
    return info


# --------------------------------------------------------------------------- sessioni, stato di sessione, reingressi

def session_key(ts_ms: int, tz: str, hour: int) -> str:
    """Sessione = giorno locale che inizia alle `hour` nel fuso `tz` (DST gestito: sessioni di 23/25 ore)."""
    loc = datetime.fromtimestamp(ts_ms / 1000, timezone.utc).astimezone(ZoneInfo(tz))
    return (loc - timedelta(hours=hour)).date().isoformat()


def annotate(trades: list, tz: str, hour: int, window_h: float) -> None:
    """Per ogni trade, SOLO informazione disponibile all'apertura (nessun look-ahead):
    sess_pnl_before / sess_peak_before = PnL realizzato nella sessione dell'apertura da trade CHIUSI prima dell'apertura;
    open_concurrent = posizioni dello stesso flusso aperte in quel momento; reentry = indice nella tesi (stesso flusso,
    simbolo e lato, apertura entro window_h dall'ingresso precedente della tesi, nessun trade di lato opposto in mezzo);
    prev_outcome = esito dell'ultimo trade della tesi gia' chiuso all'apertura (tp/sl/none)."""
    by = defaultdict(list)
    for t in trades:
        by[t["stream"]].append(t)
    w = window_h * 3_600_000
    for ts in by.values():
        ts.sort(key=lambda t: (t["opened"], t["closed"]))
        closes_by_session = defaultdict(list)
        for c in sorted((t for t in ts if t["r"] is not None), key=lambda t: t["closed"]):
            closes_by_session[session_key(c["closed"], tz, hour)].append(c)
        active: list = []                                      # trade gia' aperti, ancora potenzialmente aperti
        last_by_key: dict = {}
        last_open: dict = {}
        thesis: dict = {}
        for t in ts:
            t["session"] = session_key(t["opened"], tz, hour)
            cum = peak = 0.0
            for c in closes_by_session.get(t["session"], ()):
                if c["closed"] >= t["opened"]:
                    break
                cum += c["r"]
                peak = max(peak, cum)
            t["sess_pnl_before"], t["sess_peak_before"] = cum, peak
            active = [o for o in active if o["closed"] > t["opened"]]
            t["open_concurrent"] = len(active)
            key = (t["symbol"], t["side"])
            prev = last_by_key.get(key)
            opp = last_open.get((t["symbol"], -t["side"]))
            opposite_between = prev is not None and opp is not None and prev["opened"] < opp < t["opened"]
            if prev is not None and t["opened"] - prev["opened"] <= w and not opposite_between:
                t["reentry"], t["thesis_start"] = prev["reentry"] + 1, prev["thesis_start"]
                members = thesis[key]
            else:
                t["reentry"], t["thesis_start"] = 1, t["opened"]
                members = thesis[key] = []
            done = [o for o in members if o["closed"] < t["opened"] and o["r"] is not None]
            t["prev_outcome"] = ("tp" if max(done, key=lambda o: o["closed"])["r"] > 0 else "sl") if done else "none"
            members.append(t)
            active.append(t)
            last_by_key[key] = t
            last_open[key] = t["opened"]


# --------------------------------------------------------------------------- statistica

def _demean(trades: list) -> None:
    by = defaultdict(list)
    for t in trades:
        by[t["stream"]].append(t["r"])
    mu = {s: st.fmean(v) for s, v in by.items()}
    for t in trades:
        t["r_fe"] = t["r"] - mu[t["stream"]]


def contrast(trades: list, in_a, in_b, boot: int, seed: int) -> dict:
    """Differenza fra medie (A - B) di r a effetto fisso di flusso; IC da bootstrap a blocchi di sessione per flusso."""
    a = [t for t in trades if in_a(t)]
    b = [t for t in trades if in_b(t)]
    sa, sb = {(t["stream"], t["session"]) for t in a}, {(t["stream"], t["session"]) for t in b}
    res = {"n_a": len(a), "n_b": len(b), "sessions_a": len(sa), "sessions_b": len(sb),
           "mean_r_a": round(st.fmean(t["r"] for t in a), 4) if a else None,
           "mean_r_b": round(st.fmean(t["r"] for t in b), 4) if b else None}
    if min(len(a), len(b)) < MIN_TRADES or min(len(sa), len(sb)) < MIN_SESSIONS:
        res.update(verdict="inconclusive_small_sample", p=None)
        return res
    diff = st.fmean(t["r_fe"] for t in a) - st.fmean(t["r_fe"] for t in b)
    blocks = defaultdict(lambda: defaultdict(list))
    for t in trades:
        blocks[t["stream"]][t["session"]].append(t)
    rng = random.Random(seed)
    diffs = []
    for _ in range(boot):
        xa, xb = [], []
        for sess in blocks.values():
            keys = list(sess)
            for k in (keys[rng.randrange(len(keys))] for _ in keys):
                for t in sess[k]:
                    if in_a(t):
                        xa.append(t["r_fe"])
                    elif in_b(t):
                        xb.append(t["r_fe"])
        if xa and xb:
            diffs.append(st.fmean(xa) - st.fmean(xb))
    diffs.sort()
    q = lambda p: diffs[min(len(diffs) - 1, max(0, int(p * len(diffs))))]  # noqa: E731
    p_two = 2 * min(sum(d >= 0 for d in diffs), sum(d <= 0 for d in diffs)) / len(diffs)
    res.update(diff_r=round(diff, 4), ci95=[round(q(0.025), 4), round(q(0.975), 4)], ci90=[round(q(0.05), 4), round(q(0.95), 4)],
               p=round(min(1.0, p_two), 4), boot=len(diffs))
    return res


def holm(results: dict) -> None:
    """Correzione di Holm sui contrasti primari; assegna il verdetto."""
    tested = sorted((k for k, v in results.items() if v.get("p") is not None), key=lambda k: results[k]["p"])
    m, running = len(tested), 0.0
    for i, k in enumerate(tested):
        running = max(running, min(1.0, (m - i) * results[k]["p"]))
        v = results[k]
        v["p_holm"] = round(running, 4)
        if v["ci95"][1] < 0 and running < 0.05:
            v["verdict"] = "worse"
        elif v["ci95"][0] > 0 and running < 0.05:
            v["verdict"] = "better"
        else:
            v["verdict"] = "no_evidence"


def giveback(trades: list, arm_r: float) -> dict:
    """Sessioni (per flusso) il cui picco realizzato ha raggiunto arm_r: quanto e' stato restituito alla fine."""
    by = defaultdict(list)
    for t in trades:
        if t["r"] is not None:
            by[(t["stream"], t["session"])].append(t)
    gb, share = [], []
    for ts in by.values():
        cum = peak = 0.0
        for t in sorted(ts, key=lambda t: t["closed"]):
            cum += t["r"]
            peak = max(peak, cum)
        if peak >= arm_r:
            gb.append(peak - cum)
            share.append((peak - cum) / peak)
    if not gb:
        return {"sessions_armed": 0}
    return {"sessions_armed": len(gb), "sessions_total": len(by), "giveback_r_median": round(st.median(gb), 3),
            "giveback_share_median": round(st.median(share), 3),
            "sessions_below_75pct_of_peak": sum(1 for s in share if s > 0.25)}


# --------------------------------------------------------------------------- analisi completa

def analyze(rows: list, tz: str = "Europe/Rome", hour: int = 8, window_h: float = 12, arm_r: float = 4.0,
            boot: int = 2000, seed: int = 7, allow_unattested: bool = False) -> dict:
    trades, excl = select(rows, allow_unattested)
    r_info = assign_r(trades)
    no_r = sum(1 for t in trades if t["r"] is None)
    trades = [t for t in trades if t["r"] is not None]
    if no_r:
        excl["no_r_unit"] += no_r
    rep = {"kind": "e0_measure_v1", "classification": "NUMBERS_ONLY",
           "certification": "NOT_CERTIFIED_unattested_allowed" if allow_unattested else "attested_inputs_only",
           "params": {"tz": tz, "session_hour": hour, "reentry_window_h": window_h, "arm_r": arm_r, "boot": boot, "seed": seed,
                      "min_trades": MIN_TRADES, "min_sessions": MIN_SESSIONS},
           "pnl_basis": "realized_only_no_mark_to_market", "trades_used": len(trades), "excluded": dict(sorted(excl.items())),
           "streams": len(r_info), "r_proxy_trades": sum(v["r_proxy_trades"] for v in r_info.values())}
    if not trades:
        rep["primary"] = {}
        return rep
    annotate(trades, tz, hour, window_h)
    _demean(trades)
    lo, hi = H1_BASE
    base = lambda t: lo <= t["sess_pnl_before"] < hi  # noqa: E731
    primary = {
        "H1_after_session_profit": contrast(trades, lambda t: t["sess_pnl_before"] >= arm_r, base, boot, seed),
        "H2_reentry_3plus_vs_first": contrast(trades, lambda t: t["reentry"] >= REENTRY_PRIMARY, lambda t: t["reentry"] == 1, boot, seed),
    }
    holm(primary)
    rep["primary"] = primary
    expl = {
        "session_pnl_buckets": {},
        "reentry_index": {},
        "reentry_2_vs_first": contrast(trades, lambda t: t["reentry"] == 2, lambda t: t["reentry"] == 1, boot, seed),
        "after_tp_vs_first": contrast(trades, lambda t: t["prev_outcome"] == "tp", lambda t: t["reentry"] == 1, boot, seed),
        "after_sl_vs_first": contrast(trades, lambda t: t["prev_outcome"] == "sl", lambda t: t["reentry"] == 1, boot, seed),
        "concurrent_2plus_vs_none": contrast(trades, lambda t: t["open_concurrent"] >= 2, lambda t: t["open_concurrent"] == 0, boot, seed),
        "giveback": giveback(trades, arm_r),
    }
    for name, f in (("<-1", lambda x: x < -1), ("[-1,1)", lambda x: -1 <= x < 1), ("[1,2)", lambda x: 1 <= x < 2),
                    ("[2,4)", lambda x: 2 <= x < 4), (">=4", lambda x: x >= 4)):
        g = [t["r"] for t in trades if f(t["sess_pnl_before"])]
        expl["session_pnl_buckets"][name] = {"n": len(g), "mean_r": round(st.fmean(g), 4) if g else None}
    for k in (1, 2, 3):
        g = [t["r"] for t in trades if (t["reentry"] == k if k < 3 else t["reentry"] >= 3)]
        expl["reentry_index"][str(k) if k < 3 else "3+"] = {"n": len(g), "mean_r": round(st.fmean(g), 4) if g else None}
    rep["exploratory"] = expl
    no_manual = [t for t in trades if not t["manual"]]
    if len(no_manual) != len(trades):
        _demean(no_manual)
        sens = {"H1_after_session_profit": contrast(no_manual, lambda t: t["sess_pnl_before"] >= arm_r, base, boot, seed),
                "H2_reentry_3plus_vs_first": contrast(no_manual, lambda t: t["reentry"] >= REENTRY_PRIMARY, lambda t: t["reentry"] == 1, boot, seed)}
        holm(sens)
        rep["sensitivity_without_manual_closes"] = sens
    return rep


# --------------------------------------------------------------------------- I/O

def _inside_git(path: str) -> bool:
    d = os.path.dirname(os.path.abspath(path))
    while not os.path.isdir(d):
        d = os.path.dirname(d)
    try:
        r = subprocess.run(["git", "-C", d, "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def load_rows(path: str) -> list:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--examples", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tz", default="Europe/Rome")
    ap.add_argument("--session-hour", type=int, default=8)
    ap.add_argument("--reentry-window-h", type=float, default=12)
    ap.add_argument("--arm-r", type=float, default=4.0)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--allow-unattested", action="store_true")
    a = ap.parse_args(argv)
    if not 0 <= a.session_hour <= 23 or a.boot < 100 or a.reentry_window_h <= 0 or not math.isfinite(a.arm_r) or a.arm_r <= 0:
        print("NO-GO: parametri non validi")
        return 2
    if _inside_git(a.out):
        print("NO-GO: --out dentro un repository git")
        return 1
    try:
        rep = analyze(load_rows(a.examples), a.tz, a.session_hour, a.reentry_window_h, a.arm_r, a.boot, a.seed, a.allow_unattested)
        fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except (OSError, ValueError, KeyError) as exc:
        print(f"NO-GO: {type(exc).__name__}: {str(exc)[:80]}")
        return 1
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1, sort_keys=True)
    p = rep.get("primary", {})
    print("OK: trades=%d %s" % (rep["trades_used"], " ".join(f"{k}={v.get('verdict')}" for k, v in p.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
