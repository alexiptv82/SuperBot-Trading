#!/usr/bin/env python3
"""Controllo di FEDELTA' del banco di prova: confronta il banco con le aperture VERE di Hawk (paper) dal 12 ottobre.
Due domande, separate:
  A) SEGNALI: alla stessa ora e sullo stesso simbolo, il banco calcola gli stessi punteggi e lo stesso lato dei bot?
  B) ESITI:   rifacendo ogni trade vero (stessi prezzo, stop, take profit, leva, margine) sulle candele del banco col
              motore vero, ottiene lo stesso risultato e la stessa uscita?
Se A e B tornano, il banco e' affidabile; se no, il confronto dice dove si rompe. Sola lettura, nessuna rete di scambio
(usa i dati gia' in cache) e il file delle aperture vere letto dal server in sola lettura.

Uso: python3 desk_fedelta.py --cache DIR --real real.jsonl"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import desk_backtest as bt  # noqa: E402
from desk.engine import Limits, PaperAccount  # noqa: E402
from desk.learning import _sign  # noqa: E402
from desk.signals import closed_daily, closed_four_hour, read_symbol  # noqa: E402

BAR, H4, DAY = bt.BAR, bt.H4, bt.DAY


def exit_class(why) -> str:
    w = str(why or "").lower()
    for key, name in (("stop", "SL"), ("take profit", "TP"), ("liquid", "LIQ"), ("claude", "Claude"), ("segnale", "regole")):
        if key in w:
            return name
    return "altro"


def med(x):
    return st.median(x) if x else float("nan")


def pct(x, p):
    if not x:
        return float("nan")
    s = sorted(x)
    return s[min(len(s) - 1, max(0, int(round(p / 100 * (len(s) - 1)))))]


def reading_at(data, pos_idx, sym, end, btc_ret3, sea, mode="full"):
    """mode: full = tutti i dati; nd = senza barre 1d (trend giornaliero assente); nd4 = senza 1d e senza 4h."""
    i = pos_idx[sym].get(end - BAR)
    if i is None:
        return None, None
    d = data[sym]
    win = d["a15"][max(0, i - 999): i + 1]
    price = float(win[-1, 4])
    n4 = int(np.searchsorted(d["a4"][:, 0] + H4, end, side="right"))
    fh = closed_four_hour(d["a4"][max(0, n4 - 300): n4], end) if n4 else []
    nd = int(np.searchsorted(d["ad"][:, 0] + DAY, end, side="right")) if len(d["ad"]) else 0
    dl = closed_daily(d["ad"][max(0, nd - 340): nd], end) if nd else None
    if mode in ("nd", "nd4"):
        dl = None
    if mode == "nd4":
        fh = None
    bt.sig_mod.get_seasonal = bt.sea_v1_compat if sea == "v1" else bt.SEA_V2
    try:
        r = read_symbol(sym, win, end, daily=dl, price=price, four_hour=fh, btc_return_3d=btc_ret3)
    except Exception:
        r = None
    finally:
        bt.sig_mod.get_seasonal = bt.SEA_V2
    return r, price


def btc_ret(data, pos_idx, end):
    i = pos_idx["BTC"].get(end - BAR)
    if i is None or i <= 288:
        return None
    b = data["BTC"]["a15"]
    return float(b[i, 4] / b[i - 288, 4] - 1.0)


def signals_report(data, pos_idx, real, sea, mode="full"):
    """A) punteggi e fattori: banco contro bot."""
    diff_side, n = 0, 0
    d_score, d_long, d_short, d_px, d_rsi, d_roc, d_atr, d_sl = [], [], [], [], [], [], [], []
    agree = defaultdict(lambda: [0, 0])
    miss = 0
    by_sym_missing = defaultdict(int)
    for t in real:
        sym, ts = t["sym"], t["ts"]
        if sym not in data:
            miss += 1
            by_sym_missing[sym] += 1
            continue
        end = (ts // BAR) * BAR
        r, price = reading_at(data, pos_idx, sym, end, btc_ret(data, pos_idx, end), sea, mode)
        if r is None:
            miss += 1
            continue
        f = t["f"]
        n += 1
        if f.get("sig_side") is not None and int(f["sig_side"]) == int(r.side):
            diff_side += 1
        side = int(t["side"])
        mine = r.long_score if side == 1 else r.short_score
        real_mine = f.get("sig_long") if side == 1 else f.get("sig_short")
        if real_mine is not None:
            d_score.append(float(mine) - float(real_mine))
        if f.get("sig_long") is not None:
            d_long.append(float(r.long_score) - float(f["sig_long"]))
        if f.get("sig_short") is not None:
            d_short.append(float(r.short_score) - float(f["sig_short"]))
        if f.get("price"):
            d_px.append(abs(price / float(f["price"]) - 1.0) * 1e4)
        fa = getattr(r, "facts", None) or {}
        if f.get("rsi1h") is not None and fa.get("rsi1h") is not None:
            d_rsi.append(float(fa["rsi1h"]) - float(f["rsi1h"]))
        if f.get("roc24h") is not None and fa.get("roc24h") is not None:
            d_roc.append(float(fa["roc24h"]) - float(f["roc24h"]))
        if f.get("atr_pct") and getattr(r, "atr_pct", None):
            d_atr.append(float(r.atr_pct) / float(f["atr_pct"]))
        if f.get("sig_sl_pct") and getattr(r, "sl_pct", None):
            d_sl.append(float(r.sl_pct) / float(f["sig_sl_pct"]))
        for key in ("ema20_50_1h", "ema50_200_4h", "daily_trend"):
            a, b = f.get(key), fa.get(key)
            if a is not None and b is not None:
                agree[key][1] += 1
                agree[key][0] += int(int(a) == _sign(b))      # nel registro il segno e' gia' un intero (1, -1, 0)
    print(f"   confrontati {n} trade veri (non confrontabili: {miss})")
    if not n:
        return
    print(f"   lato del banco = lato del bot:            {100 * diff_side / n:5.1f}%")
    print(f"   punteggio del lato aperto (banco - bot):  mediana {med(d_score):+.1f}   10%/90% {pct(d_score, 10):+.0f}/{pct(d_score, 90):+.0f}   "
          f"|diff|<=3 nel {100 * sum(1 for x in d_score if abs(x) <= 3) / max(1, len(d_score)):.0f}%")
    print(f"   punteggio long  (banco - bot):            mediana {med(d_long):+.1f}   10%/90% {pct(d_long, 10):+.0f}/{pct(d_long, 90):+.0f}")
    print(f"   punteggio short (banco - bot):            mediana {med(d_short):+.1f}   10%/90% {pct(d_short, 10):+.0f}/{pct(d_short, 90):+.0f}")
    print(f"   prezzo (|banco/bot - 1|):                 mediana {med(d_px):.1f} punti base   90% {pct(d_px, 90):.1f}")
    print(f"   RSI 1h (banco - bot):                     mediana {med(d_rsi):+.2f}   10%/90% {pct(d_rsi, 10):+.1f}/{pct(d_rsi, 90):+.1f}")
    print(f"   rendimento 24h (banco - bot):             mediana {med(d_roc):+.4f}")
    print(f"   ATR% (banco / bot):                       mediana {med(d_atr):.3f}   10%/90% {pct(d_atr, 10):.2f}/{pct(d_atr, 90):.2f}")
    print(f"   stop% (banco / bot):                      mediana {med(d_sl):.3f}")
    for key, (a, b) in agree.items():
        print(f"   {key:<14} segno uguale: {100 * a / max(1, b):5.1f}%  su {b}")


def outcomes_report(data, pos_idx, real):
    """B) rifare ogni trade vero sulle candele del banco, col motore vero."""
    rows = []
    for t in real:
        if t.get("net") is None or t.get("cts") is None or t["sym"] not in data or t.get("split"):
            continue
        sym, ts = t["sym"], t["ts"]
        acc = PaperAccount(Limits(**bt.HAWK_LIMITS), "fedelta")
        px = float(t["px"])
        pos, _m = acc.open(sym, int(t["side"]), float(t["mar"]), int(t["lev"]), px, float(t["sl"]),
                           float(t["tp"]) if t.get("tp") else None, int(ts), {sym: px},
                           confidence=int(t.get("conf") or 0), source="rules", trade_type=t.get("type") or "scalp")
        if not pos:
            rows.append({"t": t, "sim": None, "why": str(_m)})
            continue
        a15 = data[sym]["a15"]
        i0 = int(np.searchsorted(a15[:, 0] + BAR, ts, side="right"))
        sim = None
        for i in range(i0, min(len(a15), i0 + 96 * 14)):
            row = a15[i]
            res = acc.on_bar(sym, int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), BAR)
            if sym not in acc.positions:
                break
        fin = [c for c in acc.closed if not c.get("partial")]
        if fin:
            net = sum(float(c.get("net") or 0.0) for c in acc.closed)
            sim = {"net": net, "why": exit_class(fin[-1].get("why")), "cts": fin[-1].get("close_ms")}
        rows.append({"t": t, "sim": sim})
    ok = [r for r in rows if r["sim"]]
    print(f"   rifatti {len(ok)} trade su {len(rows)} (non rifacibili: {len(rows) - len(ok)})")
    if not ok:
        return
    real_net = [r["t"]["net"] for r in ok]
    sim_net = [r["sim"]["net"] for r in ok]
    dif = [s - r for s, r in zip(sim_net, real_net)]
    print(f"   netto vero {sum(real_net):+.0f}$   netto del banco {sum(sim_net):+.0f}$   differenza per trade: mediana {med(dif):+.2f}$  "
          f"10%/90% {pct(dif, 10):+.1f}/{pct(dif, 90):+.1f}")
    print(f"   vinc% vera {100 * sum(1 for x in real_net if x > 0) / len(ok):.0f}   vinc% banco {100 * sum(1 for x in sim_net if x > 0) / len(ok):.0f}")
    same = sum(1 for r in ok if exit_class(r["t"]["why"]) == r["sim"]["why"])
    print(f"   stessa uscita (SL/TP/...): {100 * same / len(ok):.0f}%")
    tab = defaultdict(int)
    for r in ok:
        tab[(exit_class(r["t"]["why"]), r["sim"]["why"])] += 1
    print("   uscita vera -> uscita banco: " + "  ".join(f"{a}->{b}:{n}" for (a, b), n in sorted(tab.items(), key=lambda x: -x[1])[:8]))
    hold_real = [(r["t"]["cts"] - r["t"]["ts"]) / 60000.0 for r in ok]
    hold_sim = [((r["sim"]["cts"] or 0) - r["t"]["ts"]) / 60000.0 for r in ok]
    print(f"   durata mediana: vera {med(hold_real):.0f} min   banco {med(hold_sim):.0f} min")
    for side, nm in ((1, "LONG"), (-1, "SHORT")):
        sel = [r for r in ok if int(r["t"]["side"]) == side]
        if sel:
            print(f"   {nm:<5} n={len(sel):<4} vero {sum(r['t']['net'] for r in sel):+8.0f}$   banco {sum(r['sim']['net'] for r in sel):+8.0f}$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--real", required=True)
    ap.add_argument("--days", type=int, default=90)
    a = ap.parse_args()
    meta = json.load(open(os.path.join(a.cache, "meta.json")))
    data = bt.load_data(bt.SYMBOLS, a.days, a.cache, int(meta["end_ms"]))
    pos_idx = {s: {int(t): i for i, t in enumerate(data[s]["a15"][:, 0])} for s in data}
    print("\n=== QUALITA' DEI DATI SCARICATI (buchi nelle serie) ===")
    tot = {"a15": 0, "a4": 0, "ad": 0}
    for sym, d in data.items():
        row = []
        for key, step in (("a15", BAR), ("a4", H4), ("ad", DAY)):
            arr = d[key]
            gaps = int(np.sum(np.diff(arr[:, 0]) != step)) if len(arr) > 1 else 0
            tot[key] += gaps
            row.append(f"{key}:{gaps}")
        # il controllo severo del bot sulle barre 4h: sulle ultime 300 barre ci deve essere nessun buco
        a4 = d["a4"][-300:]
        ok4 = bool(len(a4) >= 200 and not np.any(np.diff(a4[:, 0]) != H4) and not np.any(a4[:, 0] % H4))
        print(f"   {sym:<5} buchi " + "  ".join(row) + f"   ultime 300 barre 4h accettate dal bot: {'si' if ok4 else 'NO'}")
    print(f"   totale buchi: 15m={tot['a15']} 4h={tot['a4']} 1d={tot['ad']}")
    real = []
    for line in open(a.real, encoding="utf-8"):
        line = line.strip()
        if line.startswith("{"):
            try:
                real.append(json.loads(line))
            except ValueError:
                pass
    rules = [t for t in real if str(t.get("src")) == "rules"]
    print(f"[FEDELTA] aperture vere lette: {len(real)}, di cui decise dalle regole: {len(rules)}")
    day0 = min((t["ts"] for t in real), default=0)
    print(f"[FEDELTA] lato: long {sum(1 for t in real if t['side'] == 1)}, short {sum(1 for t in real if t['side'] == -1)}")
    print("\n=== DATI DI TREND NEL REGISTRO DEI BOT: quota di aperture con il trend presente, per giorno ===")
    byday = defaultdict(lambda: [0, 0, 0])
    for t in rules:
        k = bt.time.strftime("%m-%d", bt.time.gmtime(t["ts"] / 1000))
        byday[k][0] += 1
        byday[k][1] += int(bool((t["f"] or {}).get("daily_trend")))
        byday[k][2] += int(bool((t["f"] or {}).get("ema50_200_4h")))
    for k in sorted(byday):
        n, dd, h4 = byday[k]
        print(f"   {k}  aperture {n:>3}   trend 1d presente {100 * dd / n:3.0f}%   trend 4h presente {100 * h4 / n:3.0f}%")
    for sea, mode, nm in (("v1", "full", "stagionalita' vecchia, dati completi"),
                          ("v1", "nd", "stagionalita' vecchia, SENZA trend 1d"),
                          ("v1", "nd4", "stagionalita' vecchia, SENZA trend 1d e 4h"),
                          ("v2", "full", "stagionalita' nuova V2, dati completi")):
        print(f"\n=== A) SEGNALI - {nm} ===")
        signals_report(data, pos_idx, rules, sea, mode)
    print("\n=== B) ESITI - trade veri rifatti sulle candele del banco ===")
    outcomes_report(data, pos_idx, rules)


if __name__ == "__main__":
    main()
