"""Etichette forward da candele CHIUSE: come sarebbe andata una decisione (anche NO_TRADE e rifiuti).

Regole (pure, nessuna rete, nessuna interpolazione):
- ingresso = apertura della PRIMA candela con open >= ts (la candela che contiene la decisione e' esclusa);
- orizzonte h: servono TUTTE le h/intervallo candele; se ne manca una l'etichetta e' `complete=false` senza numeri;
- barriere: stop/target toccati per candela; se nella stessa candela si toccano entrambi vince lo STOP e il caso e'
  marcato `ambiguous` (scelta prudente); nessun tocco = `timeout` alla chiusura dell'ultima candela;
- costi: `cost_bp` round-trip sottratti dal rendimento (net_bp = gross_bp - cost_bp).
"""
from __future__ import annotations

from typing import Optional

from candles import first_bar_start

HORIZONS = {"1h": 3_600_000, "4h": 14_400_000, "24h": 86_400_000}


def _bars(store, symbol: str, ts: int, n: int) -> Optional[list]:
    start = first_bar_start(ts, store.interval)
    cs = store.window(symbol, start, start + n * store.interval)
    return cs if len(cs) == n and cs[0].t == start and store.contiguous(cs) else None


def forward_returns(store, symbol: str, ts: int, side: int, cost_bp: float, horizons: dict = HORIZONS) -> dict:
    out = {}
    for name, h in horizons.items():
        n = h // store.interval
        cs = _bars(store, symbol, ts, n)
        if cs is None:
            out[name] = {"complete": False}
            continue
        entry, exit_ = cs[0].o, cs[-1].c
        gross = side * (exit_ - entry) / entry * 10_000
        out[name] = {"complete": True, "gross_bp": round(gross, 4), "net_bp": round(gross - cost_bp, 4)}
    return out


def barrier(store, symbol: str, ts: int, side: int, stop_pct: float, target_pct: float, max_ms: int, cost_bp: float) -> dict:
    """stop_pct/target_pct: distanze in FRAZIONE del prezzo d'ingresso (es. 0.01 = 1 %)."""
    n = max_ms // store.interval
    cs = _bars(store, symbol, ts, n)
    if cs is None or stop_pct <= 0 or target_pct <= 0 or side not in (-1, 1):
        return {"first": "incomplete", "complete": False}
    entry = cs[0].o
    stop = entry * (1 - side * stop_pct)
    target = entry * (1 + side * target_pct)
    best = worst = 0.0                                   # in frazione: massimo favorevole / sfavorevole
    for i, c in enumerate(cs):
        hit_stop = c.l <= stop if side == 1 else c.h >= stop
        hit_tgt = c.h >= target if side == 1 else c.l <= target
        fav = (c.h - entry) / entry if side == 1 else (entry - c.l) / entry
        adv = (entry - c.l) / entry if side == 1 else (c.h - entry) / entry
        if hit_stop or hit_tgt:
            first = "stop" if hit_stop else "target"
            exit_ = stop if hit_stop else target
            gross = side * (exit_ - entry) / entry * 10_000
            return {"first": first, "ambiguous": bool(hit_stop and hit_tgt), "complete": True,
                    "bars": i + 1, "net_bp": round(gross - cost_bp, 4),
                    "mfe_bp": round(max(best, 0 if hit_stop else fav) * 10_000, 2),
                    "mae_bp": round(max(worst, adv if hit_stop else worst) * 10_000, 2),
                    "stop_pct": round(stop_pct, 6), "target_pct": round(target_pct, 6)}
        best, worst = max(best, fav), max(worst, adv)
    gross = side * (cs[-1].c - entry) / entry * 10_000
    return {"first": "timeout", "ambiguous": False, "complete": True, "bars": n, "net_bp": round(gross - cost_bp, 4),
            "mfe_bp": round(best * 10_000, 2), "mae_bp": round(worst * 10_000, 2),
            "stop_pct": round(stop_pct, 6), "target_pct": round(target_pct, 6)}


def mfe_mae_r(store, symbol: str, side: int, entry: float, stop: float, open_ms: int, close_ms: int) -> Optional[dict]:
    """MFE/MAE in multipli di R (distanza entry-stop) tra apertura e chiusura reali, ricostruiti dalle candele CHIUSE.
    Risoluzione = intervallo delle candele; None se mancano candele o la distanza dello stop non e' valida."""
    r = abs(entry - stop)
    if r <= 0 or side not in (-1, 1) or close_ms <= open_ms:
        return None
    start = first_bar_start(open_ms, store.interval)
    n = max(1, -(-(close_ms - start) // store.interval))
    cs = store.window(symbol, start, start + n * store.interval)
    if len(cs) != n or not store.contiguous(cs):
        return None
    fav = max((c.h - entry) if side == 1 else (entry - c.l) for c in cs)
    adv = max((entry - c.l) if side == 1 else (c.h - entry) for c in cs)
    return {"mfe_r": round(max(fav, 0) / r, 4), "mae_r": round(max(adv, 0) / r, 4)}
