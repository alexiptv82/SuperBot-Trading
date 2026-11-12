#!/usr/bin/env python3
"""Replay deterministico del percorso REGOLE di Falco: confronta due versioni del motore dei segnali sugli STESSI dati.

  python3 replay_signals_rc84.py run --backend /checkout-ab7e0b7/backend --label rc84 --out rc84.json [--jobs 4]
  python3 replay_signals_rc84.py run --backend /checkout-candidato/backend --label candidato --out cand.json
  python3 replay_signals_rc84.py run --backend ... --label cand_1d15 --daily-points 15 --out cand15.json
  python3 replay_signals_rc84.py compare rc84.json cand.json [cand15.json]

Metodo (identico per ogni versione; cambia SOLO il pacchetto ``desk`` caricato da --backend):
  * mercati sintetici riproducibili a 5 minuti (seme fisso), 240 giorni per percorso: ribassista, rialzista, laterale,
    ribasso con rimbalzi, rialzo con correzioni, inversione rialzista, inversione ribassista; 6 semi ciascuno;
  * ogni 15 minuti, a 5 o 10 minuti dall'apertura della candela (alternati), il ciclo riceve cio' che darebbe la Bitget:
    le ultime 1000 candele 15m CON quella in formazione (costruita dalle sole candele 5m gia' chiuse), e, se la versione
    le accetta, le barre native 4h e 1d (anche queste con quella in formazione). Nessun dato futuro;
  * decisioni: ``desk.brain.rules_decisions`` vero con soglia 60, politica RC84 di Falco (solo scalp dalle regole),
    cooldown, soglia per tier, filtro R:R 1,5, cap del margine di Falco, e — solo se la versione lo prevede — nessuna
    apertura con tendenza 4h UNKNOWN (come nel ciclo candidato);
  * esecuzione e uscite: ``desk.engine.PaperAccount`` vero (commissioni 6 bp, slippage 2 bp per lato, funding sui LONG,
    stop giornaliero, kill equity); stop/target/liquidazione con ``on_bar`` su ogni candela 15m CHIUSA dopo l'apertura;
    chiusure delle regole al prezzo corrente; a fine replay le posizioni aperte si chiudono al prezzo corrente.
Limiti dichiarati: Claude non si puo' riprodurre (solo il percorso regole); un simbolo per percorso (BTC, soglia 60);
dati sintetici, non di mercato: misurano il COMPORTAMENTO del motore nei regimi, non la redditivita' futura.
"""
import argparse
import inspect
import json
import math
import os
import sys
import time
from multiprocessing import Pool

M5, M15, H1, H4, D1 = 300_000, 900_000, 3_600_000, 14_400_000, 86_400_000
T_START = 1_773_000_000_000 - 1_773_000_000_000 % D1          # inizio dei percorsi (00:00 UTC)
DAYS, EVAL_DAYS = 240, 30
SCENARIOS = ("ribassista", "rialzista", "laterale", "ribasso_con_rimbalzi", "rialzo_con_correzioni",
             "inversione_rialzista", "inversione_ribassista")
SEEDS = (11, 22, 33, 44, 55, 66)
SYMBOL = "BTC"
SCALP_COOLDOWN_MS, MEDIO_COOLDOWN_MS = 600_000, 3_600_000      # come cli.py
FALCO = dict(start_equity=1000.0, max_margin_trade=100.0, max_margin_total=1000.0, max_open=10,
             kill_equity=450.0, daily_stop=0.12)
_TIER_AB = {"BTC", "ETH", "XAU", "XAG"}


def tier_entry_score(symbol):                                   # copia di cli.tier_entry_score (ab7e0b7)
    return 60 if symbol.upper() in _TIER_AB else 70


# --------------------------------------------------------------------------------------------- mercati
def drift_schedule(scenario, n, np):
    """Deriva logaritmica per passo da 5 minuti lungo il percorso (288 passi al giorno)."""
    d = 0.20 / 100 / 288                                        # ~0,2% al giorno
    day = np.arange(n) // 288
    if scenario == "ribassista":
        return np.full(n, -d)
    if scenario == "rialzista":
        return np.full(n, d)
    if scenario == "laterale":
        return np.zeros(n)                                      # mean reversion aggiunta nel generatore
    if scenario == "ribasso_con_rimbalzi":                      # ogni 8 giorni, 3 giorni di rimbalzo forte
        return np.where(day % 8 >= 5, 2.2 * d, -1.8 * d)
    if scenario == "rialzo_con_correzioni":
        return np.where(day % 8 >= 5, -2.2 * d, 1.8 * d)
    if scenario == "inversione_rialzista":                      # ribasso, poi rialzo negli ultimi 40 giorni
        return np.where(day < DAYS - 40, -d, 2.0 * d)
    if scenario == "inversione_ribassista":
        return np.where(day < DAYS - 40, d, -2.0 * d)
    raise ValueError(scenario)


def market(scenario, seed, np):
    n = DAYS * 288
    rng = np.random.default_rng(seed * 1000 + SCENARIOS.index(scenario))
    drift = drift_schedule(scenario, n, np)
    ret = drift + rng.normal(0, 0.0012, n)
    logp = np.empty(n)
    x = math.log(30000.0)
    for i in range(n):
        if scenario == "laterale":
            ret[i] += -0.0008 * (x - math.log(30000.0))         # ritorno verso il centro
        x += ret[i]
        logp[i] = x
    c = np.exp(logp)
    o = np.r_[c[0], c[:-1]]
    wig = np.abs(rng.normal(0, 0.0006, n))
    h = np.maximum(o, c) * (1 + wig)
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.0006, n)))
    v = 100 + 60 * rng.random(n) * (1 + 3 * (np.abs(ret) > 0.003))
    ts = T_START + np.arange(n) * M5
    return np.column_stack([ts, o, h, lo, c, v])


def aggregate(b5, period, np):
    """Barre COMPLETE del periodo dalle 5m (stessi confini dell'exchange: multipli del periodo in UTC)."""
    per = period // M5
    n = len(b5) // per * per
    g = b5[:n].reshape(-1, per, 6)
    return np.column_stack([g[:, 0, 0], g[:, 0, 1], g[:, :, 2].max(1), g[:, :, 3].min(1), g[:, -1, 4], g[:, :, 5].sum(1)])


def partial(b5, start_ms, now_ms, np):
    """Barra in formazione dalle 5m CHIUSE tra start_ms e now_ms (None se nessuna)."""
    i0 = (start_ms - T_START) // M5
    i1 = (now_ms - T_START) // M5                               # 5m con apertura + 5m <= now
    if i1 <= i0:
        return None
    g = b5[i0:i1]
    return [start_ms, g[0, 1], g[:, 2].max(), g[:, 3].min(), g[-1, 4], g[:, 5].sum()]


# --------------------------------------------------------------------------------------------- replay
def replay(args):
    backend, scenario, seed, daily_points = args
    sys.path.insert(0, backend)
    import numpy as np
    from desk import signals
    from desk.brain import rules_decisions
    from desk.engine import Limits, PaperAccount
    if daily_points is not None:
        if not hasattr(signals, "DAILY_TREND_POINTS"):
            raise SystemExit("questa versione non ha DAILY_TREND_POINTS")
        signals.DAILY_TREND_POINTS = daily_points
    takes_htf = "bars_4h" in inspect.signature(signals.read_symbol).parameters
    b5 = market(scenario, seed, np)
    b15, b4, bd = aggregate(b5, M15, np), aggregate(b5, H4, np), aggregate(b5, D1, np)
    acc = PaperAccount(Limits(**FALCO), "main")
    last_open, trades, opened_info = {}, [], {}
    eval_start = T_START + (DAYS - EVAL_DAYS) * D1
    end = T_START + DAYS * D1
    done15 = int(np.searchsorted(b15[:, 0], eval_start))       # prima candela 15m da passare a on_bar
    stats = {"cicli": 0, "letture": 0, "letture_side0": 0, "trend4h_unknown": 0, "rifiuti_trend": 0}
    k = 0
    t15 = eval_start
    while t15 < end - M15:
        now = t15 + (5 if k % 2 == 0 else 10) * 60_000
        k += 1
        n_closed = int(np.searchsorted(b15[:, 0], now - M15, side="right"))   # 15m con apertura + 15m <= now
        # uscite: ogni candela 15m CHIUSA non ancora vista
        while done15 < n_closed:
            row = b15[done15]
            done15 += 1
            if SYMBOL in acc.positions:
                res = acc.on_bar(SYMBOL, int(row[0]), row[1], row[2], row[3], row[4], M15)
                if res:
                    trades.append(dict(res, **opened_info.pop(res["id"], {})))
        p15 = partial(b5, t15, now, np)
        arr15 = b15[max(0, n_closed - 999):n_closed]
        if p15 is not None:
            arr15 = np.vstack([arr15, p15])
        px = float(arr15[-1, 4])
        prices = {SYMBOL: px}
        acc.roll_day(time.strftime("%Y-%m-%d", time.gmtime(now / 1000)), prices)
        kw = {}
        if takes_htf:
            for key, bars, period in (("bars_4h", b4, H4), ("bars_1d", bd, D1)):
                n_c = int(np.searchsorted(bars[:, 0], now - period, side="right"))
                sel = bars[max(0, n_c - 999):n_c]
                pb = partial(b5, now - now % period, now, np)
                kw[key] = np.vstack([sel, pb]) if pb is not None else sel
        r = signals.read_symbol(SYMBOL, arr15, now, **kw)
        stats["cicli"] += 1
        if r is None:
            t15 += M15
            continue
        stats["letture"] += 1
        stats["letture_side0"] += r.side == 0
        unknown4 = r.facts.get("trend4h_state") == "UNKNOWN"
        stats["trend4h_unknown"] += unknown4
        pos_info = [{"symbol": s, "side": p.side} for s, p in acc.positions.items()]
        decs = rules_decisions([r], pos_info, set(acc.positions), 60)
        halt = acc.halted(prices)
        for d in decs:
            if d["action"] == "close":
                if SYMBOL in acc.positions:
                    rec = acc.close(SYMBOL, px, now, "chiusura decisa")
                    if rec:
                        trades.append(dict(rec, **opened_info.pop(rec["id"], {})))
                continue
            if d["action"] not in ("open_long", "open_short") or d.get("trade_type") != "scalp":   # politica RC84 Falco
                continue
            if halt or SYMBOL in acc.positions:
                continue
            if "trend4h_state" in r.facts and unknown4:          # cli candidato: nessuna apertura con 4h UNKNOWN
                stats["rifiuti_trend"] += 1
                continue
            cd = SCALP_COOLDOWN_MS if d["trade_type"] == "scalp" else MEDIO_COOLDOWN_MS
            if now - last_open.get(SYMBOL, 0) < cd or d["confidence"] < tier_entry_score(SYMBOL):
                continue
            sl_pct, tp_pct = d["stop_loss_pct"], d["take_profit_pct"]
            if sl_pct > 0 and tp_pct > 0 and tp_pct / sl_pct < 1.5:
                continue
            side = 1 if d["action"] == "open_long" else -1
            margin = min(d["margin_usd"], FALCO["max_margin_trade"])
            pos, _msg = acc.open(SYMBOL, side, margin, d["leverage"], px, px * (1 - side * sl_pct),
                                 px * (1 + side * tp_pct), now, prices, confidence=d["confidence"],
                                 reason=d["reason"], source="rules", trade_type=d["trade_type"])
            if pos:
                last_open[SYMBOL] = now
                opened_info[pos.id] = {"stato_trend": r.facts.get("trend_state", "n/d"),
                                       "trend4h": r.facts.get("trend4h_state", r.facts.get("ema50_200_4h")),
                                       "trend1d": r.facts.get("trend1d_state", r.facts.get("daily_trend") or "assente"),
                                       "punteggio": r.score}
        t15 += M15
    if SYMBOL in acc.positions:
        rec = acc.close(SYMBOL, float(b5[-1, 4]), end, "fine replay")
        trades.append(dict(rec, **opened_info.pop(rec["id"], {})))
    keep = ("side", "net", "net_r", "why", "open_ms", "close_ms", "leverage", "stato_trend", "trend4h", "trend1d",
            "punteggio", "funding", "fees", "mae_r", "mfe_r")
    return {"scenario": scenario, "seed": seed, "stats": stats, "equity_end": acc.equity(prices),
            "trades": [{k: t.get(k) for k in keep} for t in trades if not t.get("partial")]}


def cmd_run(a):
    jobs = [(os.path.abspath(a.backend), s, seed, a.daily_points) for s in a.scenarios for seed in SEEDS]
    t0 = time.time()
    with Pool(a.jobs) as pool:
        res = pool.map(replay, jobs)
    out = {"label": a.label, "backend": os.path.abspath(a.backend), "daily_points": a.daily_points,
           "giorni": DAYS, "giorni_valutati": EVAL_DAYS, "semi": SEEDS, "secondi": round(time.time() - t0, 1),
           "risultati": res}
    with open(a.out, "w") as f:
        json.dump(out, f)
    print("%s: %d percorsi in %.0f s -> %s" % (a.label, len(res), time.time() - t0, a.out))
    return 0


# --------------------------------------------------------------------------------------------- confronto
def summarize(trades):
    nets = [t["net"] for t in trades]
    wins, losses = [x for x in nets if x > 0], [-x for x in nets if x < 0]
    pf = (sum(wins) / sum(losses)) if losses else (float("inf") if wins else 0.0)
    eq, peak, dd = 0.0, 0.0, 0.0
    for t in sorted(trades, key=lambda t: t["close_ms"]):
        eq += t["net"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return {"n": len(trades), "wr": 100.0 * len(wins) / len(trades) if trades else 0.0, "pf": pf, "net": sum(nets),
            "dd": dd}


def fmt_pf(pf):
    return "inf" if pf == float("inf") else "%.2f" % pf


def cmd_compare(a):
    runs = []
    for p in a.files:
        with open(p) as f:
            runs.append(json.load(f))
    labels = [r["label"] for r in runs]
    base = runs[0]
    print("# Replay percorso regole Falco: %d giorni valutati per percorso, semi %s; base = %s" % (
        base["giorni_valutati"], base["semi"], labels[0]))
    print("\n## Per regime e lato (somma dei semi)")
    head = "%-24s %-6s" % ("regime", "lato") + "".join(" | %-26s" % l[:26] for l in labels)
    print(head)
    print("%-31s" % "" + "".join(" | %-26s" % "n   win%   PF     netto$" for _ in labels))
    regress = []
    tot = {l: {1: [], -1: []} for l in labels}
    for sc in SCENARIOS:
        for side, sname in ((1, "LONG"), (-1, "SHORT")):
            cells, sums = [], []
            for r in runs:
                tr = [t for x in r["risultati"] if x["scenario"] == sc for t in x["trades"] if t["side"] == side]
                tot[r["label"]][side] += tr
                s = summarize(tr)
                sums.append(s)
                cells.append(" | %3d %5.0f %6s %9.2f" % (s["n"], s["wr"], fmt_pf(s["pf"]), s["net"]))
            print("%-24s %-6s" % (sc, sname) + "".join("%-29s" % c for c in cells))
            for l, s in zip(labels[1:], sums[1:]):
                delta = s["net"] - sums[0]["net"]
                if delta < -max(20.0, 0.05 * abs(sums[0]["net"])):
                    regress.append((sc, sname, l, sums[0]["net"], s["net"], delta, sums[0]["n"], s["n"]))
    print("\n## Totali")
    for l in labels:
        for side, sname in ((1, "LONG"), (-1, "SHORT")):
            s = summarize(tot[l][side])
            print("%-26s %-6s n=%4d win=%5.1f%% PF=%6s netto=%10.2f$ drawdown=%8.2f$" % (l, sname, s["n"], s["wr"],
                                                                                     fmt_pf(s["pf"]), s["net"], s["dd"]))
        s = summarize(tot[l][1] + tot[l][-1])
        print("%-26s %-6s n=%4d win=%5.1f%% PF=%6s netto=%10.2f$ drawdown=%8.2f$" % (l, "TUTTI", s["n"], s["wr"],
                                                                                 fmt_pf(s["pf"]), s["net"], s["dd"]))
    print("\n## Tabella dei regressi (candidato peggio della base di oltre max(20$, 5%%) per regime e lato)")
    if not regress:
        print("nessun regresso")
    for sc, sname, l, b, c, d, nb, nc in regress:
        print("- %-24s %-5s %-22s base %9.2f$ (%d trade) -> %9.2f$ (%d trade)  delta %+9.2f$" % (sc, sname, l, b, nb, c, nc, d))
    print("\n## Confronto APPAIATO per percorso (stesso mercato e stesso seme): differenza di netto candidato - base")
    print("t = media / errore standard sui %d percorsi; |t| < 2 = differenza non distinguibile dal rumore" % len(base["risultati"]))
    key = lambda x: (x["scenario"], x["seed"])                                    # noqa: E731
    for r in runs[1:]:
        bmap = {key(x): x for x in base["risultati"]}
        for side, sname in ((1, "LONG"), (-1, "SHORT"), (0, "TUTTI")):
            ds = []
            for x in r["risultati"]:
                b = bmap.get(key(x))
                if b is None:
                    continue
                f = (lambda tr: sum(t["net"] for t in tr if side == 0 or t["side"] == side))
                ds.append(f(x["trades"]) - f(b["trades"]))
            n = len(ds)
            m = sum(ds) / n if n else 0.0
            sd = math.sqrt(sum((d - m) ** 2 for d in ds) / (n - 1)) if n > 1 else 0.0
            t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
            print("%-22s %-6s media %+8.2f$/percorso  migliorati %2d/%d  t=%+5.2f" % (
                r["label"], sname, m, sum(1 for d in ds if d > 0), n, t))
    for r in runs[1:]:
        states = {}
        for x in r["risultati"]:
            for t in x["trades"]:
                states.setdefault((t.get("stato_trend") or "n/d", t["side"]), []).append(t)
        if any(k[0] != "n/d" for k in states):
            print("\n## %s: esito per stato del trend all'ingresso (classificazione consultiva, tutti i regimi)" % r["label"])
            for (st, side), tr in sorted(states.items()):
                s = summarize(tr)
                print("%-28s %-5s n=%4d win=%5.1f%% PF=%6s netto=%9.2f$" % (st, "LONG" if side == 1 else "SHORT", s["n"],
                                                                         s["wr"], fmt_pf(s["pf"]), s["net"]))
        st = {}
        for x in r["risultati"]:
            for k_, v in x["stats"].items():
                st[k_] = st.get(k_, 0) + v
        print("\n## %s: cicli %d, letture %d, senza lato %d, tendenza 4h UNKNOWN %d, aperture rifiutate per trend %d" % (
            r["label"], st["cicli"], st["letture"], st["letture_side0"], st["trend4h_unknown"], st["rifiuti_trend"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--backend", required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--daily-points", type=int, default=None)
    r.add_argument("--jobs", type=int, default=4)
    r.add_argument("--scenarios", nargs="*", default=list(SCENARIOS))
    c = sub.add_parser("compare")
    c.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    return cmd_run(a) if a.cmd == "run" else cmd_compare(a)


if __name__ == "__main__":
    sys.exit(main())
