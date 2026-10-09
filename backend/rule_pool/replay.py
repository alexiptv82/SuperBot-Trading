"""Calcolo dei trade di una regola sulle candele e aggiornamento del giornale.

Usa ESATTAMENTE il motore del laboratorio (strategy_lab.run_strategy): la stessa
funzione serve la riproduzione storica e, in fase 2, il paper in avanti. I test
verificano che calcolare su un prefisso di candele dia gli stessi trade del calcolo
su tutta la storia (nessun look-ahead, trade chiusi immutabili).
"""
from __future__ import annotations

import math
import zlib
from typing import Optional

import numpy as np

import strategy_lab as sl
from rule_pool import evidence as ev
from rule_pool.journal import Journal
from rule_pool.rules import Rule

CLOSED_WHY = ("stop", "target", "donchian", "time")


def frames_for(b15: sl.Bars) -> dict:
    return sl.build_frames(b15)


def _exit_idx(e: int, hold_h: float, tf_ms: int) -> int:
    return e + int(round(hold_h * sl.H1 / tf_ms)) - 1


def _mae_mfe(b: sl.Bars, e: int, j: int, side: int, why: str, p: float):
    """Escursione avversa/favorevole massima in bp. Con uscita 'donchian' la barra j
    e' quella della sola apertura (l'uscita avviene al suo open): non si conta."""
    jj = max(j - 1 if why == "donchian" else j, e)
    hi, lo = float(b.h[e:jj + 1].max()), float(b.l[e:jj + 1].min())
    if side == 1:
        return (lo / p - 1.0) * 1e4, (hi / p - 1.0) * 1e4
    return (1.0 - hi / p) * 1e4, (1.0 - lo / p) * 1e4


def _record(rule: Rule, symbol: str, venue: str, b: sl.Bars, tr: dict, tf_ms: int) -> dict:
    e, side, p = tr["e"], tr["side"], tr["entry"]
    rec = {"rule_id": rule.rule_id, "version": rule.version, "venue": venue, "symbol": symbol,
           "side": side, "entry_t": tr["t"], "entry_px": p}
    if tr["why"] not in CLOSED_WHY:
        rec.update(status="open")
        return rec
    j = _exit_idx(e, tr["hold_h"], tf_ms)
    mae, mfe = _mae_mfe(b, e, j, side, tr["why"], p)
    fund = sl.FUND_BP_8H * tr["hold_h"] / 8.0 if side == 1 else 0.0
    rec.update(status="closed", exit_t=int(b.t[j]), exit_px=tr["exit"], why=tr["why"],
               hold_h=tr["hold_h"], gross_bp=tr["gross"], cost_bp=rule.cost_bp, funding_bp=fund,
               net_bp=ev.net_bp(tr["gross"], side, tr["hold_h"], rule.cost_bp),
               mae_bp=mae, mfe_bp=mfe)
    return rec


def compute_trades(rule: Rule, symbol: str, frames: dict, venue: str = "replay") -> list:
    """Trade della regola (chiusi e, al massimo, uno aperto in coda) sulle candele date."""
    s = rule.strat()
    b, sig = frames[s.tf], s.build(frames)
    raw = sl.run_strategy(b, sig, s.cfg, rule.tf_ms)
    return [_record(rule, symbol, venue, b, tr, rule.tf_ms) for tr in raw]


def control_records(rule: Rule, symbol: str, frames: dict, venue: str = "replay") -> list:
    """Controllo casuale: per ogni trade reale della regola di base, 3 ingressi spostati
    a caso (20-300 barre) con lo stesso lato e le stesse uscite. `rule` e' il controllo
    (strategia e simboli come la base). Il funding e' incluso come per la regola."""
    s = rule.strat()
    b, sig, cfg = frames[s.tf], s.build(frames), s.cfg
    raw = sl.run_strategy(b, sig, cfg, rule.tf_ms)
    rng = np.random.default_rng(zlib.crc32(f"{rule.rule_id}|{symbol}".encode()))
    dlow, dhigh = sl.donch_arrays(b, cfg)
    n, out, seen = len(b), [], set()
    for tr in raw:
        for _ in range(3):
            shift = int(rng.integers(20, 301)) * (1 if rng.random() < 0.5 else -1)
            e2 = tr["e"] + shift
            if e2 < 2 or e2 >= n - 1 or e2 in seen:
                continue
            a = sig.atr[e2 - 1]
            if not np.isfinite(a) or a <= 0:
                continue
            side, p = tr["side"], float(b.o[e2])
            j, px, why = sl.simulate_exit(b, e2, side, cfg.stop_mult * a, cfg, sig,
                                          float("nan"), dlow, dhigh)
            if why not in CLOSED_WHY:
                continue
            seen.add(e2)
            hold_h = (j - e2 + 1) * rule.tf_ms / sl.H1
            gross = side * (px / p - 1.0) * 1e4
            out.append(_record(rule, symbol, venue, b, {
                "e": e2, "side": side, "entry": p, "t": int(b.t[e2]), "why": why,
                "hold_h": hold_h, "exit": float(px), "gross": gross}, rule.tf_ms))
    return out


def pending_signal(rule: Rule, frames: dict, busy: bool = False) -> Optional[dict]:
    """Segnale sull'ULTIMA barra chiusa: se non None, si entra all'apertura della barra
    successiva (stessa regola del laboratorio). `busy` = c'e' gia' una posizione aperta
    su questo simbolo per la regola (una posizione alla volta)."""
    s = rule.strat()
    b, sig = frames[s.tf], s.build(frames)
    i = len(b) - 1
    if i < 0 or busy:
        return None
    side, a = int(sig.side[i]), float(sig.atr[i])
    if side == 0 or not math.isfinite(a) or a <= 0:
        return None
    return {"side": side, "signal_t": int(b.t[i]), "enter_at_t": int(b.t[i]) + rule.tf_ms,
            "atr": a, "stop_dist": s.cfg.stop_mult * a,
            "abs_target": float(sig.tgt[i]) if s.cfg.abs_target else None}


def sync_journal(journal: Journal, rule: Rule, symbol: str, frames: dict,
                 venue: str = "replay") -> dict:
    """Allinea il giornale ai trade calcolati. Un trade chiuso non cambia mai
    (altrimenti ImmutableTradeError)."""
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    recs = (control_records(rule, symbol, frames, venue) if rule.kind == "control"
            else compute_trades(rule, symbol, frames, venue))
    for rec in recs:
        counts[journal.upsert_trade(rec)] += 1
    return counts
