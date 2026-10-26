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
import re
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
from desk import signals_pre_p1 as sig_old  # noqa: E402
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


def reading_at(data, pos_idx, sym, end, btc_ret3, sea, mode="full", score="new"):
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
    if mode in ("nd", "nd4") or (mode == "mix" and end < bt.DAILY_FROM_MS):
        dl = None
    if mode == "nd4":
        fh = None
    scorer = sig_old if score == "old" else bt.sig_mod
    scorer.get_seasonal = bt.sea_v1_compat if sea == "v1" else bt.SEA_V2
    try:
        kw = {} if scorer is sig_old else {"btc_return_3d": btc_ret3}      # la copia vecchia non conosce questo argomento
        r = scorer.read_symbol(sym, win, end, daily=dl, price=price, four_hour=fh, **kw)
    except Exception:
        r = None
    finally:
        scorer.get_seasonal = bt.SEA_V2
    return r, price


def btc_ret(data, pos_idx, end):
    i = pos_idx["BTC"].get(end - BAR)
    if i is None or i <= 288:
        return None
    b = data["BTC"]["a15"]
    return float(b[i, 4] / b[i - 288, 4] - 1.0)


def norm_label(text: str) -> str:
    t = re.sub(r"\s*mom1h.*$", "", str(text))
    t = re.sub(r"x\d+(\.\d+)?", "x#", t)
    return re.sub(r"\s[-+]?\d+(\.\d+)?%?$", "", t).strip()


def comp_report(real, bank, n):
    """Le voci che compongono il punteggio del lato aperto: quante volte compaiono (bot contro banco) e quanti punti danno."""
    labels = sorted(set(real) | set(bank), key=lambda k: -abs(len(real.get(k, [])) - len(bank.get(k, []))))
    print("   voci del punteggio (compare nel bot / nel banco su n trade; punti medi bot / banco):")
    for k in labels[:14]:
        a, b = real.get(k, []), bank.get(k, [])
        ma = sum(a) / len(a) if a else 0.0
        mb = sum(b) / len(b) if b else 0.0
        print(f"      {k[:34]:<34} {len(a):>4} / {len(b):<4} su {n}    punti {ma:+5.1f} / {mb:+5.1f}")


def signals_report(data, pos_idx, real, sea, mode="full", score="new", verbose=False):
    """A) punteggi e fattori: banco contro bot."""
    diff_side, n = 0, 0
    comp_real, comp_bank = defaultdict(list), defaultdict(list)
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
        r, price = reading_at(data, pos_idx, sym, end, btc_ret(data, pos_idx, end), sea, mode, score)
        if r is None:
            miss += 1
            continue
        f = t["f"]
        n += 1
        for src, store in ((f.get("why") or [], comp_real), (getattr(r, "why", None) or [], comp_bank)):
            for w in src:
                m = re.match(r"^(.*?)\s*\(([+-]?\d+)\)\s*$", str(w))
                if m:
                    store[norm_label(m.group(1))].append(int(m.group(2)))
                else:
                    m = re.match(r"^(stagionalit\S*)\s+\S+\s+\+(\d+)\s*$", str(w))
                    if m:
                        store["stagionalita'"].append(int(m.group(2)))
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
    if verbose:
        comp_report(comp_real, comp_bank, n)
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


def overlay_report(data, rules):
    """D) Il regime applicato ai trade VERI di Hawk (gli stessi che i bot hanno aperto): quanto cambierebbe il risultato?
    Per ogni trade vero il filtro decide se aprirlo (con il mercato noto un attimo prima); se lo apre, protezione e uscita per
    inversione lo gestiscono barra per barra. I trade sono gli stessi dei bot, quindi la scelta delle aperture non pesa:
    pesa solo l'effetto del regime. (Non puo' dire nulla sui trade che il filtro farebbe aprire in piu'.)"""
    from desk import regime as rg
    P = rg.RegimeParams
    variants = {
        "nessun overlay": None,
        "solo filtro": P(ratchet=False, flip_exit=False),
        "solo protezione": P(gate=False, flip_exit=False),
        "solo uscita inversione": P(gate=False, ratchet=False),
        "completo": P(),
        "completo soglia 0.15": P(state_thr=0.15),
        "completo soglia 0.35": P(state_thr=0.35),
        "completo senza capitolazione": P(capitulation_roc=None),
        "completo laterale extra 0": P(range_extra=0),
        "completo be 0.8": P(be_at_r=0.8),
        "completo be 1.3": P(be_at_r=1.3),
        "completo trail 1.2": P(trail_at_r=1.2),
        "completo trail 1.7": P(trail_at_r=1.7),
    }
    trades = sorted([t for t in rules if t.get("net") is not None and t["sym"] in data and not t.get("split")],
                    key=lambda t: t["ts"])
    if not trades:
        print("   nessun trade")
        return
    syms = list(data)
    pos_idx = {s: {int(t): i for i, t in enumerate(data[s]["a15"][:, 0])} for s in syms}
    lim = {**bt.HAWK_LIMITS, "max_open": 99, "max_margin_total": 1e12, "daily_stop": 1.0}
    st = {n: {"acc": PaperAccount(Limits(**lim), n), "hist": [], "regime": None, "blocked": [], "ids": {}} for n in variants}
    t_first = (trades[0]["ts"] // BAR) * BAR - 2 * DAY
    t_end = min(max(int(d["a15"][-1, 0]) for d in data.values()) + BAR, max(t["cts"] for t in trades) + 2 * BAR)
    ptr = 0
    for t in range(t_first, t_end, BAR):
        end = t + BAR
        while ptr < len(trades) and trades[ptr]["ts"] < end:
            tr = trades[ptr]
            ptr += 1
            sym, side, px = tr["sym"], int(tr["side"]), float(tr["px"])
            for name, s_ in st.items():
                prm, reg = variants[name], s_["regime"]
                if prm is not None and reg is not None:
                    ok, extra = rg.entry_gate(side, sym, reg, prm)
                    if (not ok) or (extra and int(tr.get("conf") or 0) < bt.tier(sym) + extra):
                        s_["blocked"].append(tr)
                        continue
                pos, _m = s_["acc"].open(sym, side, float(tr["mar"]), int(tr["lev"]), px, float(tr["sl"]),
                                         float(tr["tp"]) if tr.get("tp") else None, int(tr["ts"]), {sym: px},
                                         confidence=int(tr.get("conf") or 0), source="rules", trade_type=tr.get("type") or "scalp")
                if pos:
                    s_["ids"][pos.id] = tr
        for s_ in st.values():
            acc = s_["acc"]
            for sym in list(acc.positions):
                i = pos_idx[sym].get(t)
                if i is not None:
                    row = data[sym]["a15"][i]
                    acc.on_bar(sym, int(t), float(row[1]), float(row[2]), float(row[3]), float(row[4]), BAR)
        # segnali e regime a fine barra (punteggi di prima di P1, stagionalita' vecchia, trend 1d come nei bot)
        b3 = btc_ret(data, pos_idx, end)
        readings, prices = [], {}
        for sym in syms:
            r, price = reading_at(data, pos_idx, sym, end, b3, "v1", "mix", "old")
            if price is not None:
                prices[sym] = price
            if r is not None:
                readings.append(r)
        if not readings:
            continue
        for name, s_ in st.items():
            prm = variants[name]
            if prm is None:
                continue
            reg = rg.compute(readings, s_["hist"], prm)
            s_["hist"] = rg.push_hist(s_["hist"], reg)
            s_["regime"] = reg
            acc = s_["acc"]
            protect = rg.apply_ratchet(acc.positions, prices, prm)
            info = []
            for sym, pos in acc.positions.items():
                pxs = prices.get(sym, pos.entry)
                cur_r, _pk = rg.r_metrics(pos.side, pos.entry, pxs, rg.peak_price(pos), rg.r_unit(pos))
                info.append({"symbol": sym, "side": pos.side, "trade_type": pos.trade_type, "cur_r": cur_r})
            for d in rg.management_closes(info, [], reg, protect, prm):
                if d["symbol"] in acc.positions and d["symbol"] in prices:
                    acc.close(d["symbol"], prices[d["symbol"]], end, d.get("close_why") or "chiusura regime")
    third = (t_end - trades[0]["ts"]) / 3.0
    print(f"   {'variante':<30}{'aperti':>7}{'bloccati':>9}{'netto$':>9}{'diff$':>8}{'vinc%':>6}  {'long':<12}{'short':<12}terzi del periodo")
    base_net = None
    for name, s_ in st.items():
        done = {}
        for c in s_["acc"].closed:
            g = done.setdefault(c["id"], {"net": 0.0, "side": c["side"], "cm": None})
            g["net"] += float(c.get("net") or 0.0)
            if not c.get("partial"):
                g["cm"] = c.get("close_ms")
        fin = [g for g in done.values() if g["cm"] is not None]
        net = sum(g["net"] for g in fin)
        if base_net is None:
            base_net = net
        wins = sum(1 for g in fin if g["net"] > 0)
        lg = [g for g in fin if g["side"] == 1]
        sh = [g for g in fin if g["side"] == -1]
        th = [sum(g["net"] for g in fin if trades[0]["ts"] + i * third <= g["cm"] < trades[0]["ts"] + (i + 1) * third + 1) for i in range(3)]
        bl = len(s_["blocked"])
        bll = sum(1 for b_ in s_["blocked"] if int(b_["side"]) == 1)
        print(f"   {name:<30}{len(fin):>7}{bl:>6}({bll}L){net:>9.0f}{net - base_net:>+8.0f}{100 * wins / max(1, len(fin)):>6.0f}  "
              f"{len(lg)}/{sum(g['net'] for g in lg):+.0f}$".ljust(12) + f"  {len(sh)}/{sum(g['net'] for g in sh):+.0f}$".ljust(14)
              + " [" + ", ".join(f"{x:+.0f}" for x in th) + "]")


def matching_report(data, rules, extra, name):
    """Rifa' il periodo con la variante `name` e dice, per ogni apertura del banco, che cosa ha fatto il bot nello stesso momento."""
    t0 = min(t["ts"] for t in rules)
    t_start = (t0 // DAY) * DAY - 2 * DAY
    end_ms = max(int(d["a15"][-1, 0]) for d in data.values()) + BAR
    vs = bt.replay(data, bt.make_variants({name}), t_start, end_ms, 1)
    v = vs[name]
    bank = [c for c in v.acc.closed if not c.get("partial")]
    for p in v.acc.positions.values():                 # ancora aperte a fine periodo
        bank.append({"symbol": p.symbol, "side": p.side, "open_ms": p.open_ms, "why": "aperta", "net": 0.0})
    bank = [c for c in bank if c["open_ms"] >= t0 - 3600_000]
    real_open = defaultdict(list)
    for t in rules:
        real_open[t["sym"]].append(t)
    cand = defaultdict(list)
    cc = []
    for e in extra:
        if e["k"] == "cand":
            cand[e["sym"]].append(e)
        else:
            cc.append(e)
    W = 20 * 60_000
    res = defaultdict(lambda: defaultdict(int))
    stat_by = defaultdict(lambda: defaultdict(int))
    for c in bank:
        side = "LONG" if c["side"] == 1 else "SHORT"
        sym, ts = c["symbol"], c["open_ms"]
        near_open = [t for t in real_open.get(sym, []) if abs(t["ts"] - ts) <= W]
        if near_open:
            res[side]["il bot ha aperto lo stesso simbolo (+-20 min)"] += 1
            continue
        near_c = [e for e in cand.get(sym, []) if abs(e["ts"] - ts) <= W]
        if near_c:
            res[side]["il bot l'ha scartata"] += 1
            for e in near_c[:1]:
                stat_by[side][e["st"]] += 1
            continue
        in_claude = any(abs(e["ts"] - ts) <= 10 * 60_000 for e in cc)
        res[side]["nessun evento dal bot" + (" (ciclo con chiamata a Claude)" if in_claude else "")] += 1
    for side in ("LONG", "SHORT"):
        tot = sum(res[side].values())
        print(f"   {side}: aperture del banco = {tot}")
        for k, n in sorted(res[side].items(), key=lambda x: -x[1]):
            print(f"      {n:>4}  {k}")
        for k, n in sorted(stat_by[side].items(), key=lambda x: -x[1])[:8]:
            print(f"            motivo dello scarto: {k}  x{n}")
    # uscite
    mix = defaultdict(int)
    for c in bank:
        mix[exit_class(c.get("why"))] += 1
    print("   uscite del banco: " + "  ".join(f"{k}:{n}" for k, n in sorted(mix.items(), key=lambda x: -x[1])))
    rm = defaultdict(int)
    for t in rules:
        if t.get("why"):
            rm[exit_class(t["why"])] += 1
    print("   uscite dei bot:   " + "  ".join(f"{k}:{n}" for k, n in sorted(rm.items(), key=lambda x: -x[1])))
    # per giorno
    pd_b, pd_r = defaultdict(int), defaultdict(int)
    for c in bank:
        pd_b[bt.time.strftime("%m-%d", bt.time.gmtime(c["open_ms"] / 1000))] += 1
    for t in rules:
        pd_r[bt.time.strftime("%m-%d", bt.time.gmtime(t["ts"] / 1000))] += 1
    print("   aperture per giorno (banco / bot): " + "  ".join(f"{k}:{pd_b.get(k, 0)}/{pd_r.get(k, 0)}" for k in sorted(set(pd_b) | set(pd_r)) if k >= "10-12"))
    # stato dei candidati del bot in generale
    st = defaultdict(int)
    for e in extra:
        if e["k"] == "cand":
            st[e["st"]] += 1
    print("   candidate del bot per motivo: " + "  ".join(f"{k}:{n}" for k, n in sorted(st.items(), key=lambda x: -x[1])[:10]))
    ccs = [e for e in cc]
    print(f"   chiamate a Claude registrate: {len(ccs)}   (con 0 decisioni: {sum(1 for e in ccs if e.get('n') == 0)}, senza risposta valida: {sum(1 for e in ccs if not e.get('ok'))})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--real", required=True)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--overlay", action="store_true", help="applica il regime ai trade veri e confronta")
    ap.add_argument("--match", default=None, help="nome della variante del banco da confrontare con le aperture vere (es. base@old@v1@mix)")
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
    b = data["BTC"]["a15"]
    gi = np.where(np.diff(b[:, 0]) != BAR)[0]
    for i in gi[:3]:
        print(f"   buco 15m BTC: tra {bt.time.strftime('%Y-%m-%d %H:%M', bt.time.gmtime(b[i, 0] / 1000))} e "
              f"{bt.time.strftime('%Y-%m-%d %H:%M', bt.time.gmtime(b[i + 1, 0] / 1000))} UTC")
    print("\n=== BARRE 4h CHE IL BOT SCARTEREBBE (controllo severo di closed_four_hour) ===")
    nbad_tot = 0
    for sym, d in data.items():
        a4 = d["a4"]
        bad_hl = np.where((a4[:, 3] > np.minimum(a4[:, 1], a4[:, 4])) | (a4[:, 2] < np.maximum(a4[:, 1], a4[:, 4])))[0]
        bad_pos = np.where(np.any(a4[:, 1:5] <= 0, axis=1))[0]
        nbad_tot += len(bad_hl) + len(bad_pos)
        if len(bad_hl) or len(bad_pos):
            ex = bad_hl[0] if len(bad_hl) else bad_pos[0]
            print(f"   {sym:<5} massimo/minimo incoerenti: {len(bad_hl):>3}   valori <=0: {len(bad_pos):>3}   esempio "
                  f"{bt.time.strftime('%Y-%m-%d %H:%M', bt.time.gmtime(a4[ex, 0] / 1000))} O/H/L/C={a4[ex, 1]:.6g}/{a4[ex, 2]:.6g}/{a4[ex, 3]:.6g}/{a4[ex, 4]:.6g}")
    print(f"   totale barre 4h incoerenti: {nbad_tot}")
    # quante letture (una al giorno, sul periodo del confronto) hanno la serie 4h accettata dal bot
    acc_n = acc_ok = 0
    for sym, d in data.items():
        a4 = d["a4"]
        for k in range(len(a4) - 60, len(a4), 6):
            win = a4[max(0, k - 300): k]
            acc_n += 1
            acc_ok += int(len(closed_four_hour(win, int(win[-1, 0]) + H4)) >= 200)
    print(f"   finestre da 300 barre accettate dal bot: {acc_ok}/{acc_n}")
    print("\n=== COERENZA DELLE BARRE 4h CON LE 15m (stesso scaricamento) ===")
    for sym in ("BTC", "ETH", "SOL", "DOGE"):
        d = data[sym]
        a15, a4 = d["a15"], d["a4"]
        key = (a15[:, 0] // H4).astype(np.int64)
        ok = tot_n = 0
        shift_ok = 0
        for r in a4[-120:]:
            g = a15[key == int(r[0] // H4)]
            if len(g) != H4 // BAR:
                continue
            tot_n += 1
            agg = (g[0, 1], g[:, 2].max(), g[:, 3].min(), g[-1, 4])
            if all(abs(x / y - 1) < 1e-6 for x, y in zip(r[1:5], agg)):
                ok += 1
            # ipotesi: l'orario della barra 4h e' quello di CHIUSURA (spostato di 4 ore)
            g2 = a15[key == int(r[0] // H4) - 1]
            if len(g2) == H4 // BAR:
                agg2 = (g2[0, 1], g2[:, 2].max(), g2[:, 3].min(), g2[-1, 4])
                if all(abs(x / y - 1) < 1e-6 for x, y in zip(r[1:5], agg2)):
                    shift_ok += 1
        print(f"   {sym:<5} barre 4h uguali alle 15m aggregate: {ok}/{tot_n}   se spostate di 4 ore: {shift_ok}/{tot_n}")
    real, extra = [], []
    for line in open(a.real, encoding="utf-8"):
        line = line.strip()
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            (extra if obj.get("k") in ("cand", "cc") else real).append(obj)
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
    print("\n=== QUANDO SONO CAMBIATI I PESI DEL PUNTEGGIO NEI BOT (voce 'trend 4h': 20 punti prima, 14 dopo la modifica P1) ===")
    wk = defaultdict(lambda: [0, 0, 0, 0])
    for t in rules:
        k = bt.time.strftime("%m-%d", bt.time.gmtime(t["ts"] / 1000))
        for w in (t["f"] or {}).get("why") or []:
            m = re.match(r"^trend 4h \(\+(\d+)\)", str(w))
            if m:
                wk[k][0] += 1
                wk[k][1 if int(m.group(1)) == 20 else 2 if int(m.group(1)) == 14 else 3] += 1
    for k in sorted(wk):
        n4, a20, a14, oth = wk[k]
        print(f"   {k}  aperture con trend 4h {n4:>3}   a 20 punti {a20:>3}   a 14 punti {a14:>3}   altro {oth}")
    print("\n=== TREND 4h: con quante barre il banco ritrova il segno scritto dai bot? ===")
    from desk.signals import ema as _ema, direction as _dir
    for L in (200, 205, 220, 250, 300, 400):
        agree = n_t = 0
        for t in rules:
            sym = t["sym"]
            if sym not in data:
                continue
            end = (t["ts"] // BAR) * BAR
            a4 = data[sym]["a4"]
            n4 = int(np.searchsorted(a4[:, 0] + H4, end, side="right"))
            if n4 < L:
                continue
            x = a4[n4 - L: n4, 4]
            sg = _dir(_ema(x, 50)[-1], _ema(x, 200)[-1])
            real_sg = (t["f"] or {}).get("ema50_200_4h")
            if real_sg is None:
                continue
            n_t += 1
            agree += int(sg == int(real_sg))
        print(f"   ultime {L:>3} barre: segno uguale nel {100 * agree / max(1, n_t):5.1f}% dei {n_t} trade")
    for sea, mode, score, verb, nm in (
            ("v1", "mix", "old", True, "punteggi VECCHI (prima di P1), stagionalita' vecchia, trend 1d come nei bot"),
            ("v1", "mix", "new", False, "punteggi NUOVI (P1), stagionalita' vecchia, trend 1d come nei bot"),
            ("v2", "full", "new", False, "COME GIRA OGGI: punteggi P1 + stagionalita' V2 + dati completi"),
            ("v2", "full", "old", False, "punteggi vecchi + stagionalita' V2 + dati completi")):
        print(f"\n=== A) SEGNALI - {nm} ===")
        signals_report(data, pos_idx, rules, sea, mode, score, verb)
    print("\n=== B) ESITI - trade veri rifatti sulle candele del banco ===")
    outcomes_report(data, pos_idx, rules)
    if a.overlay:
        print("\n=== D) IL REGIME APPLICATO AI TRADE VERI DI HAWK (stessi trade dei bot, effetto del solo regime) ===")
        overlay_report(data, rules)
    if a.match:
        print("\n=== C) LE APERTURE DEL BANCO CONTRO QUELLE DEI BOT (stessa configurazione dei bot di allora) ===")
        matching_report(data, rules, extra, a.match)


if __name__ == "__main__":
    main()
