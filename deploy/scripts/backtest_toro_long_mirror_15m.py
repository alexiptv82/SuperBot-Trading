#!/usr/bin/env python3
"""Backtest di STUDIO del prototipo Toro LONG Mirror 15m su storico REALE Bitget USDT-FUTURES (scaricato con
fetch_bitget_futures_history.py). Offline: nessuna rete, nessun ordine, nessun collegamento al runner.

Regole fissate PRIMA di guardare i risultati (nessuna soglia del prototipo viene cambiata):
- decisione alla chiusura della candela 15m t con le sole candele chiuse; trend 4h = signals.htf_trend (RC84, invariato)
  sulle barre 4H native chiuse; ingresso all'apertura della candela t+1;
- uscite (il prototipo non ne ha: ipotesi di studio uguale per tutte le varianti): stop 1,2 x ATR(14) 1h chiuso,
  limitato 0,3%-3,5% (come signals.read_symbol), take profit 1,8 x stop, chiusura dopo 24 h;
  stop eseguito a min(stop, apertura) come engine.on_bar; stop prima del target nella stessa candela;
- costi del motore PAPER: commissione 6 bp/lato, slippage 2 bp/lato, funding LONG 1 bp ogni 8 h (lo storico pubblico
  del funding copre solo 90 giorni: media 0,45-0,61 bp/8h, quindi la costante del motore e' prudente);
- regime ex-ante (fissato a priori, calcolato solo con dati passati): rendimento delle ultime 7 giorni >= +3% rialzo,
  <= -3% ribasso, altrimenti laterale;
- periodo A (studio) e periodo B (valutazione finale) separati in ordine di tempo, data di taglio fissata a priori.

Varianti: PROTOTIPO; SENZA_CONFERME (stesso punteggio e soglie, senza le tre conferme 15m nuove);
ORIGINALE_1H (signals.read_symbol congelato, lato LONG con soglia del runner 60 BTC/ETH, 70 altri, valutato a ogni ora
chiusa); CASUALE (stessi numeri di ingressi in istanti casuali, 50 estrazioni); ESPOSIZIONE (buy and hold).
Portafoglio Toro: engine.PaperAccount invariato con Limits(1000, 200/op., totale 1000, 5 posizioni, kill 450,
stop giornaliero 12%).

Uso: python deploy/scripts/backtest_toro_long_mirror_15m.py --data DIR --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
from desk import signals as S  # noqa: E402
from desk.engine import Limits, PaperAccount, max_leverage_for  # noqa: E402
from desk.long_mirror_15m import BAR_MS, MIN_CLOSED, inspect_long_mirror_15m  # noqa: E402

H1, H4, D1 = 3_600_000, 14_400_000, 86_400_000
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
WARMUP_DAYS = 40
SPLIT_MS = 1_771_113_600_000            # 2026-02-15 00:00 UTC: A = prima, B = dopo (fissata prima dei risultati)
MAX_HOLD = 96
REGIME_BARS, REGIME_TH = 7 * 96, 0.03
RANDOM_DRAWS = 50
COSTS = {"base": (6.0, 2.0, 1.0), "zero": (0.0, 0.0, 0.0), "doppi": (12.0, 4.0, 2.0), "funding_3bp": (6.0, 2.0, 3.0)}


def load(path: str) -> np.ndarray:
    return np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)[:, :6]


# ------------------------------------------------------------------------------------------------ segnali
def signals_for(sym: str, a15: np.ndarray, a4: np.ndarray, start: int) -> dict:
    """Per ogni candela t (dalla fine del riscaldamento): stato del prototipo, variante senza conferme, regime, stop."""
    n = len(a15)
    proto = np.zeros(n, dtype=np.int8)        # 0 nessuno, 1 continuazione, 2 rimbalzo
    noconf = np.zeros(n, dtype=np.int8)
    reasons: dict[str, int] = {}
    b1 = S.resample(a15, H1)
    t4_cache: dict[int, str] = {}
    trend = np.empty(n, dtype=object)
    sl = np.full(n, np.nan)
    regime = np.zeros(n, dtype=np.int8)       # 1 rialzo, -1 ribasso, 0 laterale
    for t in range(start, n - 1):
        now = int(a15[t, 0]) + BAR_MS
        k4 = int(np.searchsorted(a4[:, 0], now - H4, side="right"))
        if k4 not in t4_cache:
            t4_cache[k4] = S.htf_trend(a4[:k4], now, H4)["state"]
        trend[t] = t4 = t4_cache[k4]
        r = inspect_long_mirror_15m(sym, a15[t + 1 - (MIN_CLOSED + 10):t + 1], now, trend4h_state=t4)
        reasons[r.state if r.state != "NO_TRADE" else r.reason] = reasons.get(r.state if r.state != "NO_TRADE" else r.reason, 0) + 1
        proto[t] = {"LONG_CONTINUATION_CANDIDATE": 1, "LONG_BOUNCE_CANDIDATE": 2}.get(r.state, 0)
        f = r.features
        if f:                                  # stesso punteggio e stesse soglie, senza le tre conferme 15m
            if t4 == "UP" and r.score >= 60:
                noconf[t] = 1
            elif t4 == "DOWN" and f["vol_ratio15m"] > 1.3 and 40 <= f["rsi15m"] <= 72 and r.score >= 30:
                noconf[t] = 2
        k1 = int(np.searchsorted(b1[:, 0], now - H1, side="right"))
        sl[t] = min(0.035, max(0.003, 1.2 * S.atr(b1[:k1]) / b1[k1 - 1, 4]))
        ret7 = a15[t, 4] / a15[t - REGIME_BARS, 4] - 1
        regime[t] = 1 if ret7 >= REGIME_TH else -1 if ret7 <= -REGIME_TH else 0
    return {"proto": proto, "noconf": noconf, "sl": sl, "regime": regime, "trend": trend, "reasons": reasons}


def original_long(sym: str, a15: np.ndarray, a4: np.ndarray, start: int) -> np.ndarray:
    """Lato LONG dell'algoritmo originale congelato (signals.read_symbol), valutato a ogni ora chiusa."""
    thr = 60 if max_leverage_for(sym) >= 30 else 70          # come cli.tier_entry_score: TIER A/B 60, TIER C 70
    out = np.zeros(len(a15), dtype=np.int8)
    for t in range(start, len(a15) - 1):
        now = int(a15[t, 0]) + BAR_MS
        if now % H1:
            continue
        k4 = int(np.searchsorted(a4[:, 0], now - H4, side="right"))
        r = S.read_symbol(sym, a15[t + 1 - 1000:t + 1], now, bars_4h=a4[:k4])
        if r is not None and r.side == 1 and r.score >= thr:
            out[t] = 1 if r.facts["trend4h_state"] == "UP" else 2
    return out


# ------------------------------------------------------------------------------------------------ operazioni
def trade(a: np.ndarray, k: int, sl_pct: float, cost: tuple) -> dict:
    fee, slip, fund = cost
    entry = a[k, 1] * (1 + slip / 1e4)
    sl, tp = entry * (1 - sl_pct), entry * (1 + 1.8 * sl_pct)
    last = min(len(a) - 1, k + MAX_HOLD - 1)
    px, why, j = a[last, 4], "tempo", last
    for j in range(k, last + 1):
        if a[j, 3] <= sl:
            px, why = min(sl, a[j, 1]), "stop"
            break
        if a[j, 2] >= tp:
            px, why = tp, "target"
            break
    exit_px = px * (1 - slip / 1e4)
    hours = (j - k + 1) * 0.25
    net = exit_px / entry - 1 - fee / 1e4 * (1 + exit_px / entry) - fund / 1e4 * hours / 8
    return {"k": k, "exit": j, "why": why, "net": net, "hours": hours}


def run_trades(a: np.ndarray, sig: np.ndarray, sl: np.ndarray, start: int, cost: tuple) -> list:
    out, busy = [], -1
    for t in range(start, len(a) - 1):
        if t <= busy or not sig[t] or np.isnan(sl[t]):
            continue
        tr = trade(a, t + 1, float(sl[t]), cost)
        tr.update(t=t, kind=int(sig[t]))
        out.append(tr)
        busy = tr["exit"]
    return out


def stats(x) -> dict:
    x = np.asarray([v for v in x], dtype=float)
    if len(x) == 0:
        return {"n": 0}
    eq = np.r_[0.0, np.cumsum(x)]
    wins, loss = x[x > 0].sum(), -x[x < 0].sum()
    return {"n": int(len(x)), "win": round(float((x > 0).mean()), 3), "media_pct": round(float(x.mean()) * 100, 4),
            "somma_pct": round(float(x.sum()) * 100, 2),
            "profit_factor": round(float(wins / loss), 3) if loss > 0 else None,
            "max_drawdown_pct": round(float((np.maximum.accumulate(eq) - eq).max()) * 100, 2),
            "t": round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2) if len(x) > 2 and x.std() > 0 else None}


def random_trades(a: np.ndarray, sl: np.ndarray, cands: np.ndarray, n: int, rng, cost: tuple) -> list:
    out, busy = [], -1
    if n == 0 or len(cands) == 0:
        return out
    for t in np.sort(rng.choice(cands, size=min(len(cands), n * 4), replace=False)):
        if t <= busy or len(out) >= n:
            continue
        tr = trade(a, int(t) + 1, float(sl[t]), cost)
        tr.update(t=int(t))
        out.append(tr)
        busy = tr["exit"]
    return out


# ------------------------------------------------------------------------------------------------ portafoglio
def portfolio(data: dict, sigkey: str, lev_req: int, margin: float, start: int, end: int) -> dict:
    """engine.PaperAccount invariato, limiti Toro proposti. Ingressi solo dai segnali, uscite stop/TP/24h/liquidazione."""
    acc = PaperAccount(Limits(start_equity=1000.0, max_margin_trade=200.0, max_margin_total=1000.0, max_open=5,
                              kill_equity=450.0, daily_stop=0.12), name="toro_backtest")
    pending, refused, opened = {}, {}, 0
    eq_curve, max_open = [], 0
    halted_bars, kill = 0, None
    for i in range(start, end):
        ts = int(data[SYMBOLS[0]]["a"][i, 0])
        acc.roll_day(time.strftime("%Y-%m-%d", time.gmtime(ts / 1000)), {})
        prices_open = {s: float(data[s]["a"][i, 1]) for s in SYMBOLS}
        for s, (sl_pct, kind) in list(pending.items()):      # ingressi decisi alla chiusura della candela prima
            px = prices_open[s]
            lev = min(lev_req, max_leverage_for(s))
            pos, why = acc.open(s, 1, margin, lev, px, px * (1 - sl_pct), px * (1 + 1.8 * sl_pct), ts, prices_open,
                                source="toro_long_mirror_15m", trade_type="scalp", reason=f"kind {kind}")
            if pos is None:
                refused[why] = refused.get(why, 0) + 1
            else:
                opened += 1
        pending = {}
        for s in SYMBOLS:
            b = data[s]["a"][i]
            acc.on_bar(s, ts, b[1], b[2], b[3], b[4], BAR_MS)
            p = acc.positions.get(s)
            if p is not None and ts + BAR_MS - p.open_ms >= MAX_HOLD * BAR_MS:
                acc.close(s, float(b[4]), ts + BAR_MS, "tempo massimo")
        prices = {s: float(data[s]["a"][i, 4]) for s in SYMBOLS}
        eq = acc.equity(prices)
        eq_curve.append(eq)
        max_open = max(max_open, len(acc.positions))
        h = acc.halted(prices)
        if h:
            halted_bars += 1
            if kill is None and "soglia minima" in h:
                kill = ts
        for s in SYMBOLS:                                     # decisioni alla chiusura della candela i
            if s not in acc.positions and data[s][sigkey][i]:
                pending[s] = (float(data[s]["sig"]["sl"][i]), int(data[s][sigkey][i]))
    for s in list(acc.positions):
        acc.close(s, float(data[s]["a"][end - 1, 4]), int(data[s]["a"][end - 1, 0]) + BAR_MS, "fine test")
    e = np.asarray(eq_curve)
    nets = [c["net"] for c in acc.closed]
    return {"leva_richiesta": lev_req, "margine": margin, "equity_finale": round(acc.cash, 2),
            "pnl_netto": round(acc.cash - 1000.0, 2), "equity_minima": round(float(e.min()), 2),
            "max_drawdown_pct": round(float(((np.maximum.accumulate(e) - e) / np.maximum.accumulate(e)).max()) * 100, 2),
            "operazioni": len(acc.closed), "aperture_rifiutate": refused, "max_posizioni_insieme": max_open,
            "liquidazioni": sum(1 for c in acc.closed if c["why"] == "liquidazione"),
            "candele_in_blocco": halted_bars, "protezione_450_ms": kill,
            "commissioni": round(sum(c["fees"] for c in acc.closed), 2),
            "funding": round(sum(c["funding"] for c in acc.closed), 2),
            "win": round(float(np.mean([n > 0 for n in nets])), 3) if nets else None,
            "profit_factor": round(sum(n for n in nets if n > 0) / -sum(n for n in nets if n < 0), 3)
            if any(n < 0 for n in nets) else None}


# ------------------------------------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--json")
    ap.add_argument("--no-original", action="store_true")
    args = ap.parse_args()
    data = {}
    for s in SYMBOLS:
        a, a4 = load(f"{args.data}/{s}_15m.csv"), load(f"{args.data}/{s}_4H.csv")
        data[s] = {"a": a, "a4": a4}
    n = min(len(d["a"]) for d in data.values())
    assert all(np.array_equal(data[s]["a"][:n, 0], data[SYMBOLS[0]]["a"][:n, 0]) for s in SYMBOLS), "orari diversi"
    start = WARMUP_DAYS * 96
    split = int(np.searchsorted(data[SYMBOLS[0]]["a"][:, 0], SPLIT_MS))
    rep = {"nota": "STORICO REALE Bitget USDT-FUTURES; uscite e regime sono ipotesi di studio fissate a priori",
           "periodi": {}, "mercati": {}, "portafoglio": {}}
    ts = data[SYMBOLS[0]]["a"][:, 0]
    iso = lambda ms: time.strftime("%Y-%m-%d %H:%M", time.gmtime(ms / 1000))  # noqa: E731
    rep["periodi"] = {"riscaldamento": [iso(ts[0]), iso(ts[start])], "A_studio": [iso(ts[start]), iso(ts[split])],
                      "B_valutazione": [iso(ts[split]), iso(ts[n - 1] + BAR_MS)]}
    for s in SYMBOLS:
        t0 = time.time()
        d = data[s]
        d["sig"] = signals_for(s, d["a"], d["a4"], start)
        d["proto"], d["noconf"] = d["sig"]["proto"], d["sig"]["noconf"]
        d["orig"] = np.zeros(n, dtype=np.int8) if args.no_original else original_long(s, d["a"], d["a4"], start)
        print(s, "segnali in", round(time.time() - t0), "s", flush=True)
    for s in SYMBOLS:
        d, a = data[s], data[s]["a"]
        sl, reg = d["sig"]["sl"], d["sig"]["regime"]
        m = {"stati_prototipo": d["sig"]["reasons"]}
        for per, (lo, hi) in {"A": (start, split), "B": (split, n - 1)}.items():
            r = {"esposizione_pct": round((a[hi, 4] / a[lo, 1] - 1) * 100, 2),
                 "giorni_regime": {k: int(np.sum(reg[lo:hi] == v)) // 96 for k, v in
                                   (("rialzo", 1), ("ribasso", -1), ("laterale", 0))}}
            for cname, cost in COSTS.items():
                for key in ("proto", "noconf", "orig"):
                    sig = d[key].copy()
                    sig[:lo] = 0
                    sig[hi:] = 0
                    trs = [x for x in run_trades(a, sig, sl, lo, cost) if x["exit"] < hi + MAX_HOLD]
                    if cname != "base":
                        r.setdefault("costi_" + cname, {})[key] = stats([x["net"] for x in trs])
                        continue
                    blk = {"tutti": stats([x["net"] for x in trs]),
                           "continuazione": stats([x["net"] for x in trs if x["kind"] == 1]),
                           "rimbalzo": stats([x["net"] for x in trs if x["kind"] == 2])}
                    for rn, rv in (("rialzo", 1), ("ribasso", -1), ("laterale", 0)):
                        blk["regime_" + rn] = stats([x["net"] for x in trs if reg[x["t"]] == rv])
                    blk["uscite"] = {w: sum(1 for x in trs if x["why"] == w) for w in ("stop", "target", "tempo")}
                    blk["ore_medie"] = round(float(np.mean([x["hours"] for x in trs])), 2) if trs else None
                    if key == "proto":                 # controllo casuale: stessi numeri, stesso periodo
                        cands = np.arange(lo, hi)
                        draws = [random_trades(a, sl, cands, len(trs), np.random.default_rng(1000 * i + lo), cost)
                                 for i in range(RANDOM_DRAWS)]
                        sums = [sum(x["net"] for x in dr) for dr in draws]
                        mine = sum(x["net"] for x in trs)
                        blk["casuale"] = stats([x["net"] for dr in draws for x in dr])
                        blk["quota_casuali_battuti"] = round(float(np.mean([mine > v for v in sums])), 3)
                        for rn, rv in (("rialzo", 1), ("ribasso", -1), ("laterale", 0)):
                            blk["casuale_regime_" + rn] = stats([x["net"] for dr in draws for x in dr if reg[x["t"]] == rv])
                    r[key] = blk
            m[per] = r
        rep["mercati"][s] = m
    for per, (lo, hi) in {"A": (start, split), "B": (split, n - 1)}.items():
        for key in ("proto", "noconf", "orig"):
            rows = []
            for lev in (3, 5, 10, 15, 20, 30):
                for mar in (100.0, 200.0):
                    rows.append(portfolio(data, key, lev, mar, lo, hi))
            rep["portafoglio"][f"{per}_{key}"] = rows
    txt = json.dumps(rep, indent=1, ensure_ascii=False, default=str)
    if args.json:
        with open(args.json, "w") as fh:
            fh.write(txt)
    print("ok", flush=True)


if __name__ == "__main__":
    main()
