"""
Blocco C: strategia trend su barre 4h — BTC e ETH.
Usa solo candele pubbliche Bitget (già caricate da labdata).
Nessun bot, nessun deploy, nessuna API di trading.
"""
from __future__ import annotations
import numpy as np

BAR_15M = 900_000      # ms
BAR_4H  = 14_400_000   # ms  (16 × 15m)
DAY     = 86_400_000   # ms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resample_4h(raw_15m: np.ndarray) -> np.ndarray:
    """
    Ricampiona candele 15m → 4h.
    raw_15m: (N, 5+) — colonne [ts_start_ms, open, high, low, close, ...]
    Restituisce (M, 5) — [ts_4h_start, open, high, low, close]
    """
    if len(raw_15m) == 0:
        return np.empty((0, 5), dtype=np.float64)

    ts    = raw_15m[:, 0].astype(np.int64)
    o_arr = raw_15m[:, 1].astype(np.float64)
    h_arr = raw_15m[:, 2].astype(np.float64)
    l_arr = raw_15m[:, 3].astype(np.float64)
    c_arr = raw_15m[:, 4].astype(np.float64)

    bar_id = ts // BAR_4H
    unique_bars, inv = np.unique(bar_id, return_inverse=True)

    rows = []
    for i, bid in enumerate(unique_bars):
        mask = inv == i
        rows.append([
            int(bid * BAR_4H),
            float(o_arr[mask][0]),
            float(h_arr[mask].max()),
            float(l_arr[mask].min()),
            float(c_arr[mask][-1]),
        ])
    return np.array(rows, dtype=np.float64)


def _compute_atr(h: np.ndarray, l: np.ndarray, c: np.ndarray,
                 period: int = 14) -> np.ndarray:
    """ATR di Wilder su barre 4h."""
    n = len(c)
    atr = np.full(n, np.nan)
    if n < 2:
        return atr
    tr = np.maximum(h[1:] - l[1:],
         np.maximum(np.abs(h[1:] - c[:-1]),
                    np.abs(l[1:] - c[:-1])))
    if len(tr) < period:
        return atr
    atr[period] = tr[:period].mean()
    for i in range(period + 1, n):
        atr[i] = (atr[i-1] * (period - 1) + tr[i-1]) / period
    return atr


def generate_signals(bars4h: np.ndarray,
                     lookback: int = 20,
                     atr_period: int = 14,
                     atr_sl: float = 2.0,
                     atr_tp: float = 4.0,
                     invert: bool = False) -> dict:
    """
    Genera segnali di breakout a 4h.
    Restituisce {ts_entry_ms: (side, sl_pct, tp_pct)}
    ts_entry_ms = inizio della PROSSIMA barra 4h dopo il segnale.
    """
    if len(bars4h) < lookback + 2:
        return {}

    ts  = bars4h[:, 0].astype(np.int64)
    h   = bars4h[:, 2]
    l   = bars4h[:, 3]
    c   = bars4h[:, 4]
    atr = _compute_atr(h, l, c, atr_period)

    sigs: dict = {}
    for i in range(lookback, len(c) - 1):
        if np.isnan(atr[i]) or atr[i] <= 0:
            continue
        roll_h = h[i - lookback:i].max()
        roll_l = l[i - lookback:i].min()
        px     = c[i]
        if px <= 0:
            continue

        sl_pct = float(np.clip(atr[i] * atr_sl / px, 0.003, 0.04))
        tp_pct = float(np.clip(atr[i] * atr_tp / px, 0.006, 0.12))
        entry_ts = int(ts[i + 1])   # apri alla prossima barra

        if c[i] > roll_h and not invert:
            sigs[entry_ts] = (1, sl_pct, tp_pct)
        elif c[i] < roll_l and not invert:
            sigs[entry_ts] = (-1, sl_pct, tp_pct)
        elif c[i] > roll_h and invert:
            sigs[entry_ts] = (-1, sl_pct, tp_pct)
        elif c[i] < roll_l and invert:
            sigs[entry_ts] = (1, sl_pct, tp_pct)

    return sigs


# ---------------------------------------------------------------------------
# Replay principale del Blocco C
# ---------------------------------------------------------------------------

def trend_replay(raw_data: dict,
                 symbols: list,
                 cost_mult: float,
                 name: str,
                 lookback: int = 20,
                 atr_period: int = 14,
                 atr_sl: float = 2.0,
                 atr_tp: float = 4.0,
                 invert: bool = False) -> dict:
    """
    Simula la strategia trend 4h su `symbols` (tipicamente BTC e ETH).
    Usa PaperAccount dal desk engine — sola lettura dei file produzione.
    """
    import sys, os
    HERE = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(HERE, ".."))             # desk
    sys.path.insert(0, os.path.join(HERE, "..", "long_lab_claude"))  # labrun

    from desk.engine import PaperAccount, Limits
    import labrun as lr

    lims = lr.limits(cost_mult)
    acc  = PaperAccount(lims, name)

    # Ricampionamento 15m → 4h per ogni simbolo
    sym_4h: dict[str, np.ndarray] = {}
    sym_sigs: dict[str, dict]     = {}
    for sym in symbols:
        if sym not in raw_data or len(raw_data[sym]) == 0:
            continue
        b4 = resample_4h(raw_data[sym])
        if len(b4) < lookback + 2:
            continue
        sym_4h[sym]   = b4
        sym_sigs[sym] = generate_signals(b4, lookback, atr_period,
                                         atr_sl, atr_tp, invert=invert)

    if not sym_4h:
        return {"name": name, "trades": [], "equity": [], "blocked": 0, "open_end": 0}

    # Tutti i timestamp 4h unificati
    all_ts = sorted({int(ts) for sym in sym_4h for ts in sym_4h[sym][:, 0]})

    last_open: dict[str, int] = {}
    equity_curve: list = []
    prev_day: str | None = None
    cur_px: dict[str, float] = {}
    blocked = 0

    for ts_s in all_ts:
        ts_e = ts_s + BAR_4H

        # Prezzi correnti
        for sym, b4 in sym_4h.items():
            idx = int(np.searchsorted(b4[:, 0], ts_s))
            if idx < len(b4) and b4[idx, 0] == ts_s:
                cur_px[sym] = float(b4[idx, 4])

        # Aggiorna posizioni aperte con on_bar 4h
        for sym in list(acc.positions.keys()):
            if sym not in sym_4h:
                continue
            b4  = sym_4h[sym]
            idx = int(np.searchsorted(b4[:, 0], ts_s))
            if idx < len(b4) and b4[idx, 0] == ts_s:
                r = b4[idx]
                acc.on_bar(sym, ts_s, float(r[1]), float(r[2]),
                           float(r[3]), float(r[4]), BAR_4H)

        # Roll giornaliero
        day_id = str(ts_e // DAY)
        if day_id != prev_day:
            acc.roll_day(day_id, dict(cur_px))
            prev_day = day_id

        # Verifica segnali di ingresso
        for sym in symbols:
            sig = sym_sigs.get(sym, {}).get(ts_s)
            if sig is None:
                continue
            if sym in acc.positions:
                blocked += 1
                continue
            # Cooldown: almeno 2 barre 4h tra un trade e il successivo
            if ts_s - last_open.get(sym, 0) < BAR_4H * 2:
                continue
            b4  = sym_4h.get(sym)
            if b4 is None:
                continue
            idx = int(np.searchsorted(b4[:, 0], ts_s))
            if idx >= len(b4) or b4[idx, 0] != ts_s:
                continue
            px = float(b4[idx, 1])   # prezzo open della barra di entrata
            if px <= 0:
                continue
            side, sl_pct, tp_pct = sig
            pr2 = dict(cur_px)
            pr2[sym] = px
            pos, _ = acc.open(
                sym, side, 100.0, 15, px,
                px * (1 - side * sl_pct),
                px * (1 + side * tp_pct),
                ts_e, pr2,
                confidence=75,
                reason="trend4h",
                source="rules",
                trade_type="medio",
            )
            if pos:
                last_open[sym] = ts_s

        equity_curve.append((ts_e, acc.equity(cur_px)))

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
        "equity":   equity_curve,
        "blocked":  blocked,
        "open_end": len(acc.positions),
    }
