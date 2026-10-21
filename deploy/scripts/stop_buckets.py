"""Vincite e R netto medio per LARGHEZZA DELLO STOP, sui trade chiusi veri di Hawk e Bull (SOLA LETTURA).

Perche': con costi di ~16 bp per giro (commissioni 6+6, slippage 2+2) il peso del costo, misurato in R, dipende dalla
larghezza dello stop: costo_R = 0,0016 / stop. Il pareggio in percentuale di vincenti dipende quindi dallo stop
(circa 55% a stop 0,3%, 41% a 1%, 37% a 3,5% con TP = 1,8 x stop). Gli stop dei bot sono guidati dall'ATR (0,3-3,5%) e la
loro distribuzione reale non e' mai stata misurata: questo script la misura e guarda se le fasce strette rendono meno.

Cosa fa: legge SOLO `learning_log.jsonl` di ogni bot (montato in sola lettura), prende i trade "puliti" (una gamba, nessun
parziale, nessun DCA, nessuna liquidazione; netto coerente con le formule del motore), li divide per `r_dist` (stop iniziale
in % del prezzo) e per ogni fascia stampa: quanti sono, % di vincenti, R netto medio con intervallo bootstrap al 95%, R medio
dei vincenti e dei perdenti, pareggio "proprio" (ricavato dai R della fascia) e pareggio teorico (TP 1,8, SL 1,0, 16 bp) allo
stop mediano della fascia, e come sono usciti (TP / stop / altro).

NON apre file in scrittura, NON usa la rete, NON ordina nulla. Le fasce hanno pochi trade: sono indizi, non prove.
Uso (nel contenitore usa-e-getta): python - --data-root /data --bots hawk,bull < stop_buckets.py
"""
import argparse
import collections
import json
import math
import os
import random

COST_BP = 16.0              # commissione 6 + slippage 2, per lato, due lati
TP_TEORICO, SL_TEORICO = 1.8, 1.0
EDGES_PCT = (0.5, 1.0, 2.0)  # confini delle fasce, in % del prezzo
BOOT_N = 2000
BOOT_SEED = 20261021
MIN_FOR_CI = 5


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


# ------------------------------------------------------------------ trade puliti dal registro

def load_trades(path, bot):
    """Trade puliti (stessi criteri di pm_exec_replay.load_trades). Ritorna (puliti, scartati)."""
    groups = collections.defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("ev") == "close" and r.get("id") is not None:
                groups[(r.get("run_no"), r["id"])].append(r)
    clean, skipped = [], collections.Counter()
    for (run, i), recs in groups.items():
        if len(recs) != 1 or recs[0].get("partial"):
            skipped["con parziali"] += 1
            continue
        r = recs[0]
        if (r.get("dca_count") or 0) != 0 or (r.get("legs") or 1) != 1:
            skipped["dca o due gambe"] += 1
            continue
        if r.get("why") == "liquidazione":
            skipped["liquidazione"] += 1
            continue
        try:
            t = {"bot": bot, "run": run, "id": i, "symbol": str(r["symbol"]), "side": int(r["side"]),
                 "margin": float(r["margin"]), "lev": float(r["leverage"]), "entry": float(r["entry"]),
                 "exit": float(r["exit"]), "net": float(r["net"]), "fees": float(r.get("fees") or 0.0),
                 "funding": float(r.get("funding") or 0.0), "why": str(r.get("why")), "r_dist": float(r["r_dist"])}
        except (KeyError, TypeError, ValueError):
            skipped["campi mancanti"] += 1
            continue
        if t["side"] not in (-1, 1) or min(t["margin"], t["lev"], t["entry"], t["r_dist"]) <= 0:
            skipped["campi non validi"] += 1
            continue
        qty = t["margin"] * t["lev"] / t["entry"]
        gross = t["side"] * (t["exit"] - t["entry"]) * qty
        t["recon_err"] = abs(gross - t["fees"] - t["funding"] - t["net"])
        # 1R in dollari: quello registrato dal motore (margine pianificato x leva x stop); se manca, lo si ricalcola
        risk = _f(r.get("risk_plan_usd"))
        t["risk"] = risk if risk > 0 else t["margin"] * t["lev"] * t["r_dist"]
        t["net_r"] = t["net"] / t["risk"]
        t["stop_pct"] = t["r_dist"] * 100.0
        clean.append(t)
    return clean, skipped


# ------------------------------------------------------------------ statistiche

def breakeven_pct(stop_pct, tp=TP_TEORICO, sl=SL_TEORICO, cost_bp=COST_BP):
    """% di vincenti per il pareggio dopo i costi: un TP netto vale tp - c, uno stop netto -(sl + c), c = costo / stop."""
    c = (cost_bp / 10_000.0) / (stop_pct / 100.0)
    return 100.0 * (sl + c) / (tp + sl)


def bucket_label(stop_pct, edges=EDGES_PCT):
    lo = 0.0
    for e in edges:
        if stop_pct < e:
            return "%g-%g%%" % (lo, e) if lo else "<%g%%" % e
        lo = e
    return ">=%g%%" % edges[-1]


def bucket_order(edges=EDGES_PCT):
    labels, lo = [], 0.0
    for e in edges:
        labels.append("%g-%g%%" % (lo, e) if lo else "<%g%%" % e)
        lo = e
    labels.append(">=%g%%" % edges[-1])
    return labels


def quantile(sorted_xs, q):
    """Quantile con interpolazione lineare su una lista gia' ordinata."""
    if not sorted_xs:
        return float("nan")
    pos = q * (len(sorted_xs) - 1)
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


def boot_ci(values, n_boot=BOOT_N, seed=BOOT_SEED):
    """Intervallo bootstrap 95% della media (rimescolamenti con seme fisso: stesso input, stesso intervallo)."""
    if len(values) < MIN_FOR_CI:
        return None
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return quantile(means, 0.025), quantile(means, 0.975)


def bucket_stats(trades):
    n = len(trades)
    wins = [t for t in trades if t["net"] > 0]
    losses = [t for t in trades if t["net"] <= 0]
    rs = [t["net_r"] for t in trades]
    out = {"n": n, "wins": len(wins), "win_pct": 100.0 * len(wins) / n if n else float("nan"),
           "mean_net": sum(t["net"] for t in trades) / n if n else float("nan"),
           "mean_r": sum(rs) / n if n else float("nan"),
           "ci": boot_ci(rs),
           "w_r": sum(t["net_r"] for t in wins) / len(wins) if wins else None,
           "l_r": sum(t["net_r"] for t in losses) / len(losses) if losses else None,
           "exits": collections.Counter("TP" if t["why"] == "take profit" else "SL" if t["why"] == "stop loss" else "altro"
                                        for t in trades)}
    # pareggio proprio: % di vincenti per cui la media dei vincenti compensa la media dei perdenti
    if out["w_r"] is not None and out["l_r"] is not None and out["w_r"] - out["l_r"] > 0:
        out["be_own"] = 100.0 * (-out["l_r"]) / (out["w_r"] - out["l_r"])
    else:
        out["be_own"] = None
    stops = sorted(t["stop_pct"] for t in trades)
    out["stop_med"] = quantile(stops, 0.5) if stops else None
    out["be_theory"] = breakeven_pct(out["stop_med"]) if out["stop_med"] else None
    return out


def fmt_stats(label, s):
    ci = "n<%d" % MIN_FOR_CI if s["ci"] is None else "%+.2f/%+.2f" % s["ci"]
    f = lambda v, p="%.2f": "-" if v is None else p % v
    ex = s["exits"]
    return ("%-8s n=%3d | vinc %5.1f%% | R netto medio %+.2f [IC95 %s] | $ medio %+.1f | R vinc %s | R perd %s | "
            "pareggio proprio %s%% | teorico a stop %s%%: %s%% | uscite TP %d SL %d altro %d") % (
        label, s["n"], s["win_pct"], s["mean_r"], ci, s["mean_net"], f(s["w_r"], "%+.2f"), f(s["l_r"], "%+.2f"),
        f(s["be_own"], "%.1f"), f(s["stop_med"], "%.2f"), f(s["be_theory"], "%.1f"), ex["TP"], ex["SL"], ex["altro"])


def report(bot, trades, skipped):
    print("=== %s: trade puliti %d | scartati %s" % (bot.upper(), len(trades), dict(skipped)), flush=True)
    bad = [t for t in trades if t["recon_err"] > 0.5]
    print("coerenza formule engine: %d su %d tornano al centesimo, %d esclusi" % (len(trades) - len(bad), len(trades), len(bad)),
          flush=True)
    trades = [t for t in trades if t["recon_err"] <= 0.5]
    if not trades:
        print("nessun trade utilizzabile", flush=True)
        return
    stops = sorted(t["stop_pct"] for t in trades)
    print("stop iniziale in %% del prezzo: min %.2f | p10 %.2f | p25 %.2f | mediana %.2f | p75 %.2f | p90 %.2f | max %.2f" % (
        stops[0], quantile(stops, .1), quantile(stops, .25), quantile(stops, .5), quantile(stops, .75), quantile(stops, .9),
        stops[-1]), flush=True)
    print("costo di un giro (16 bp) in R: mediana %.2f | stop piu' stretto %.2f | stop piu' largo %.2f" % (
        COST_BP / 1e4 / (quantile(stops, .5) / 100), COST_BP / 1e4 / (stops[0] / 100), COST_BP / 1e4 / (stops[-1] / 100)),
          flush=True)
    by = collections.defaultdict(list)
    for t in trades:
        by[bucket_label(t["stop_pct"])].append(t)
    for lab in bucket_order():
        if by.get(lab):
            print(fmt_stats(lab, bucket_stats(by[lab])), flush=True)
    print(fmt_stats("TUTTI", bucket_stats(trades)), flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="/data")
    ap.add_argument("--bots", default="hawk,bull")
    args = ap.parse_args(argv)
    for bot in args.bots.split(","):
        path = os.path.join(args.data_root, bot, "learning_log.jsonl")
        if not os.path.exists(path):
            print("=== %s: registro non trovato" % bot.upper(), flush=True)
            continue
        trades, skipped = load_trades(path, bot)
        report(bot, trades, skipped)


if __name__ == "__main__":
    main()
