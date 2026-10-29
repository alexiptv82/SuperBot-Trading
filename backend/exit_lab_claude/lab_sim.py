"""Simulatore offline di uscite e entrate su candele fini (1m/5m) per le entrate REALI dei classici.

Solo PAPER e solo lettura: non importa nulla da backend/desk, non scrive su dati di produzione.
Costi e regole di fill replicano backend/desk/engine.py (Limits e PaperAccount):
  fee 6 bp per lato sul nozionale, slippage 2 bp per lato AVVERSO (anche su stop e TP),
  funding 1 bp / 8h solo sui long, liquidazione con maint 0,5%, stop massimo = 0,75 * (1/lev - maint),
  nella stessa candela la liquidazione prevale sullo stop e lo stop sul take profit (caso peggiore),
  stop a gap: si esce all'apertura se peggiore.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

FEE = 6e-4
SLIP = 2e-4
MAINT = 0.005
SL_LIQ_FRAC = 0.75
FUNDING_8H_LONG = 1e-4
HOUR_MS = 3_600_000
G5 = 300_000                      # barra di conferma del "rimbalzo": 5 minuti
HORIZON_MS = 24 * HOUR_MS         # tetto di permanenza uguale per tutte le varianti


def liq_price(side: int, entry: float, lev: float) -> float:
    return entry * (1 - side * (1.0 / lev - MAINT))


def cap_distance(dist: float, lev: float):
    """Distanza di stop massima eseguibile (come engine.open). Ritorna (distanza, ridotta?)."""
    dmax = SL_LIQ_FRAC * (1.0 / lev - MAINT)
    return (dmax, True) if dist > dmax else (dist, False)


@dataclass
class Trade:
    key: str
    bot: str
    run_no: int
    symbol: str
    side: int
    t0: int                 # ms del segnale reale
    price: float            # prezzo di riferimento (entry_fill senza slippage)
    fill0: float            # entry_fill reale
    d_sl: float             # distanza stop reale (frazione del prezzo)
    d_tp: float             # distanza TP reale
    lev: int
    margin: float
    notional: float
    risk_usd: float         # perdita allo stop pianificata = margine * leva * d_sl (come engine.risk_plan_usd)
    phase: str
    real_net: float
    real_kind: str
    parts: int


@dataclass
class Result:
    kind: str               # SL, TP, LIQ, TIME, NOFILL, NODATA
    net: float = 0.0
    entry_ms: int = 0
    exit_ms: int = 0
    legs: int = 1
    mfe_r: float = 0.0
    mae_r: float = 0.0
    capped: bool = False
    scale: float = 1.0      # fattore per portare la size a "stessa perdita massima" (solo varianti di uscita)


def _dt(c: np.ndarray) -> int:
    return int(c[1, 0] - c[0, 0]) if len(c) > 1 else 60_000


def simulate(c: np.ndarray, start: int, side: int, fill: float, notional: float, stop: float,
             tp_dist: Optional[float], lev: float, entry_ms: int, t_ref_ms: int, max_ms: int,
             leg2: Optional[dict] = None, r_ref: float = 0.0, stop_only_first: bool = False) -> Result:
    """Gestisce una posizione candela per candela da `start`. `c` ha colonne t,o,h,l,c.

    leg2 = {"trigger", "notional", "expire_ms"} per la seconda gamba (entrata scaglionata). Il TP si ricalcola
    sul prezzo medio dopo la seconda gamba (ipotesi dichiarata: vedi README).
    stop_only_first: sulla candela di ingresso valgono solo stop e liquidazione (il TP potrebbe essere stato
    toccato prima dell'ingresso: non si sa l'ordine, si assume il caso peggiore).
    """
    n = len(c)
    dt = _dt(c)
    qty = notional / fill
    avg = fill
    fees = notional * FEE
    liq = liq_price(side, avg, lev)
    tp = None if tp_dist is None else avg * (1 + side * tp_dist)
    legs = 1
    pending = dict(leg2) if leg2 else None
    fav = adv = fill
    for k in range(start, n):
        t, o, h, l, cl = (float(x) for x in c[k])
        end = int(t) + dt
        if pending is not None:
            if t >= pending["expire_ms"]:
                pending = None
            elif (side == 1 and l <= pending["trigger"]) or (side == -1 and h >= pending["trigger"]):
                f2 = pending["trigger"] * (1 + side * SLIP)
                q2 = pending["notional"] / f2
                avg = (avg * qty + f2 * q2) / (qty + q2)
                qty += q2
                fees += pending["notional"] * FEE
                legs = 2
                liq = liq_price(side, avg, lev)
                tp = None if tp_dist is None else avg * (1 + side * tp_dist)
                pending = None
        fav = max(fav, h) if side == 1 else min(fav, l)
        adv = min(adv, l) if side == 1 else max(adv, h)
        first = stop_only_first and k == start
        kind = None
        raw = 0.0
        if side == 1:
            if l <= liq:
                kind, raw = "LIQ", liq
            elif l <= stop:
                kind, raw = "SL", min(stop, o)
            elif tp is not None and h >= tp and not first:
                kind, raw = "TP", tp
        else:
            if h >= liq:
                kind, raw = "LIQ", liq
            elif h >= stop:
                kind, raw = "SL", max(stop, o)
            elif tp is not None and l <= tp and not first:
                kind, raw = "TP", tp
        if kind is None and end - t_ref_ms >= max_ms:
            kind, raw = "TIME", cl
        if kind is not None:
            exit_fill = raw if kind == "LIQ" else raw * (1 - side * SLIP)
            gross = side * (exit_fill - avg) * qty
            fee_close = qty * exit_fill * FEE
            hours = max(0.0, (end - entry_ms) / HOUR_MS)
            funding = qty * avg * FUNDING_8H_LONG * hours / 8 if side == 1 else 0.0
            net = gross - fees - fee_close - funding
            mfe = max(0.0, side * (fav - fill)) / r_ref if r_ref > 0 else 0.0
            mae = max(0.0, side * (fill - adv)) / r_ref if r_ref > 0 else 0.0
            return Result(kind, net, int(entry_ms), end, legs, mfe, mae)
    return Result("NODATA")


def first_index(c: np.ndarray, t_ms: int) -> int:
    return int(np.searchsorted(c[:, 0], t_ms, side="left"))


def run_exit_variant(c: np.ndarray, tr: Trade, sl_mult: float, tp_mult: float, flip: bool = False,
                     max_ms: int = HORIZON_MS) -> Result:
    """Entrata immediata come nella realtà (o al contrario se flip=True: placebo), uscite con distanze scalate."""
    side = -tr.side if flip else tr.side
    fill = tr.price * (1 + side * SLIP)
    d_sl, capped = cap_distance(tr.d_sl * sl_mult, tr.lev)
    stop = fill * (1 - side * d_sl)
    res = simulate(c, first_index(c, tr.t0), side, fill, tr.notional, stop, tr.d_tp * tp_mult, tr.lev,
                   tr.t0, tr.t0, max_ms, r_ref=fill * tr.d_sl)
    res.capped = capped
    res.scale = tr.d_sl / d_sl if d_sl > 0 else 1.0
    return res


def run_scalein_variant(c: np.ndarray, tr: Trade, pull: float, sl_mult: float, tp_mult: float,
                        sizing: str, ttl_ms: int, f1: float = 0.5, max_ms: int = HORIZON_MS) -> Result:
    """Prima gamba f1 all'ingresso reale, seconda gamba (1-f1) a un ritracciamento di `pull` x distanza stop
    originale. Stop largo fissato dall'inizio. sizing 'S' = nozionale totale uguale all'originale;
    'R' = nozionale scelto in modo che la perdita allo stop (entrambe le gambe) sia uguale a risk_usd."""
    side = tr.side
    fill = tr.fill0
    d_sl, capped = cap_distance(tr.d_sl * sl_mult, tr.lev)
    stop = fill * (1 - side * d_sl)
    trigger = tr.price * (1 - side * pull * tr.d_sl)
    n_tot = tr.notional
    if sizing == "R":
        f2 = trigger * (1 + side * SLIP)
        loss_unit = f1 * side * (fill - stop) / fill + (1 - f1) * side * (f2 - stop) / f2
        n_tot = tr.risk_usd / loss_unit if loss_unit > 0 else tr.notional
    leg2 = {"trigger": trigger, "notional": n_tot * (1 - f1), "expire_ms": tr.t0 + ttl_ms}
    res = simulate(c, first_index(c, tr.t0), side, fill, n_tot * f1, stop, tr.d_tp * tp_mult, tr.lev,
                   tr.t0, tr.t0, max_ms, leg2=leg2, r_ref=fill * tr.d_sl)
    res.capped = capped
    return res


def _find_touch(c: np.ndarray, i0: int, side: int, level: float, t_limit: int) -> Optional[int]:
    for k in range(i0, len(c)):
        if c[k, 0] >= t_limit:
            return None
        if (side == 1 and c[k, 3] <= level) or (side == -1 and c[k, 2] >= level):
            return k
    return None


def _find_bounce(c: np.ndarray, kt: int, side: int, window_end_ms: int):
    """Prima barra da 5 minuti completa, dopo la candela del tocco, che chiude a favore (rimbalzo).
    Ritorna (indice successivo, prezzo di chiusura, ms di ingresso) oppure None."""
    n = len(c)
    dt = _dt(c)
    per_group = max(1, G5 // dt)
    first_start = ((int(c[kt, 0]) + dt + G5 - 1) // G5) * G5
    k = kt + 1
    while k < n and c[k, 0] < first_start:
        k += 1
    while k < n:
        gs = int(c[k, 0]) // G5 * G5
        j = k
        while j < n and int(c[j, 0]) // G5 * G5 == gs:
            j += 1
        if gs + G5 > window_end_ms:
            return None
        if j - k == per_group and (c[j - 1, 4] - c[k, 1]) * side > 0:
            return j, float(c[j - 1, 4]), gs + G5
        k = j
    return None


def run_pullback_variant(c: np.ndarray, tr: Trade, mode: str, window_ms: int, p: float,
                         max_ms: int = HORIZON_MS) -> Result:
    """Entra solo se il prezzo ritraccia CONTRO la direzione del segnale di p x distanza stop originale entro
    window_ms. mode 'limit': ordine limite al livello. mode 'bounce': attende una barra da 5 minuti che chiude a
    favore dopo il tocco. Uscite come l'originale (stesse distanze) a partire dal nuovo ingresso."""
    side = tr.side
    level = tr.price * (1 - side * p * tr.d_sl)
    i0 = first_index(c, tr.t0)
    kt = _find_touch(c, i0, side, level, tr.t0 + window_ms)
    if kt is None:
        return Result("NOFILL")
    if mode == "limit":
        fill = level * (1 + side * SLIP)
        start, entry_ms, only_stop = kt, int(c[kt, 0]), True
    else:
        b = _find_bounce(c, kt, side, tr.t0 + window_ms)
        if b is None:
            return Result("NOFILL")
        start, px, entry_ms = b
        fill = px * (1 + side * SLIP)
        only_stop = False
    d_sl, capped = cap_distance(tr.d_sl, tr.lev)
    stop = fill * (1 - side * d_sl)
    res = simulate(c, start, side, fill, tr.notional, stop, tr.d_tp, tr.lev, entry_ms, tr.t0, max_ms,
                   r_ref=fill * tr.d_sl, stop_only_first=only_stop)
    res.capped = capped
    return res


def reversal_after_stop(c: np.ndarray, tr: Trade, res: Result, horizon_ms: int = 6 * HOUR_MS) -> str:
    """Dopo uno stop dell'originale: il prezzo ha toccato prima il TP originale o prima uno stop a 2x?
    'TP_first' = un stop piu' largo avrebbe salvato il trade; 'STOP2_first' = avrebbe perso di piu'."""
    if res.kind != "SL":
        return "n/a"
    side = tr.side
    fill = tr.fill0
    tp = fill * (1 + side * tr.d_tp)
    stop2 = fill * (1 - side * 2 * tr.d_sl)
    end_ms = min(res.exit_ms + horizon_ms, tr.t0 + HORIZON_MS)
    for k in range(first_index(c, res.exit_ms), len(c)):
        if c[k, 0] >= end_ms:
            break
        h, l = c[k, 2], c[k, 3]
        if (side == 1 and l <= stop2) or (side == -1 and h >= stop2):
            return "STOP2_first"
        if (side == 1 and h >= tp) or (side == -1 and l <= tp):
            return "TP_first"
    return "neither"
