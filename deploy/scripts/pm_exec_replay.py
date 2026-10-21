"""Replay ESEGUIBILE della gestione del profitto sui trade chiusi veri (SOLA LETTURA, nessun ordine).

Per ogni trade "pulito" del registro dei bot (una sola gamba, nessun parziale, nessun DCA) scarica le candele 15m vere di
Bitget e rigioca la vita del trade con regole alternative di protezione del profitto, confrontando il netto che si
sarebbe ottenuto con quello vero. Usa il motore di ricerca di ChatGPT (desk.profit.*, SOLA LETTURA, non modificato).

Modello di esecuzione dichiarato (NON e' un backtest di portafoglio):
- ogni trade e' un controfattuale a se': uscire prima libera lo slot ma non si simulano i rientri;
- una regola decisa a barra chiusa esce all'APERTURA della barra successiva, con slippage e commissione dell'engine;
- le regole a pavimento di prezzo si giudicano come l'engine giudica gli stop: sulla barra, minimo/massimo contro il
  livello, fill al livello (o all'apertura se la barra apre oltre); un livello nuovo vale dalla barra SUCCESSIVA;
- TEMPO: l'uscita vera di stop/TP avviene nella barra che finisce a close_ms (come in engine.on_bar). Una regola
  decisa a barra chiusa conta solo se la sua uscita cade PRIMA dell'inizio di quella barra; per i pavimenti la barra
  d'uscita e' inclusa (se l'uscita vera e' uno stop loss il pavimento, piu' vicino al prezzo, scatta prima o insieme;
  se e' un take profit vale la convenzione dell'engine "lo stop prevale sul TP", ipotesi sfavorevole alla regola);
  per le uscite discrezionali vale l'istante close_ms;
- se la regola non scatta prima, vale l'uscita vera. Le azioni discrezionali di Claude durante il trade (stop spostati,
  chiusure) sono gia' nel risultato vero e NON si rigiocano;
- la barra in cui il trade e' nato contiene prezzi precedenti all'ingresso: per i pavimenti non conta per il massimo.
Costi come l'engine: commissione 6 bp e slippage 2 bp per lato, funding 1 bp/8h sui long.
Uso (nel contenitore usa-e-getta): python - --data-root /data --bots hawk,bull < pm_exec_replay.py
"""
import argparse
import collections
import json
import os
import sys
import time
import urllib.error
import urllib.request

BAR_MS = 900_000
FEE_BP, SLIP_BP, FUND_BP = 6.0, 2.0, 1.0
BASE = "https://api.bitget.com"
WARMUP_BARS = 24
TAIL_BARS = 6             # barre dopo l'uscita vera: servono a eseguire un'uscita decisa sull'ultima barra utile
BAR_EXITS = ("stop loss", "take profit")


# ------------------------------------------------------------------ trade puliti dal registro

def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def load_trades(path, bot):
    """Trade puliti: una sola chiusura finale, nessun parziale, nessun DCA, una gamba. Ritorna (puliti, scartati)."""
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
                 "exit": float(r["exit"]), "open_ms": int(r["open_ms"]), "close_ms": int(r["close_ms"]),
                 "net": float(r["net"]), "fees": float(r.get("fees") or 0.0), "funding": float(r.get("funding") or 0.0),
                 "why": str(r.get("why")), "mfe_r": _f(r.get("mfe_r")), "r_dist": float(r["r_dist"])}
        except (KeyError, TypeError, ValueError):
            skipped["campi mancanti"] += 1
            continue
        if t["side"] not in (-1, 1) or min(t["margin"], t["lev"], t["entry"], t["r_dist"]) <= 0 \
                or t["close_ms"] <= t["open_ms"]:
            skipped["campi non validi"] += 1
            continue
        t["qty"] = t["margin"] * t["lev"] / t["entry"]
        # coerenza: il netto ricalcolato con le formule dell'engine deve coincidere con quello registrato
        gross = t["side"] * (t["exit"] - t["entry"]) * t["qty"]
        t["recon_err"] = abs(gross - t["fees"] - t["funding"] - t["net"])
        clean.append(t)
    return clean, skipped


# ------------------------------------------------------------------ candele 15m vere

def _http_json(url, opener, sleep):
    for wait in (2.0, 4.0, None):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with opener(req, timeout=10) as r:
                d = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code != 429 or wait is None:
                raise
            sleep(wait)
            continue
        if isinstance(d, dict) and str(d.get("code")) == "429" and wait is not None:
            sleep(wait)
            continue
        return d
    raise ValueError("troppe richieste")


def fetch_bars(symbol, start_ms, end_ms, now_ms=None, opener=urllib.request.urlopen, sleep=time.sleep):
    """Candele 15m CHIUSE [ts_apertura, o, h, l, c] tra start e end: finestre da 190 barre, doppioni e barra in corso tolti."""
    sym = symbol.upper() + ("" if symbol.upper().endswith("USDT") else "USDT")
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    rows = {}
    w0 = start_ms
    while w0 < end_ms:
        w1 = min(end_ms, w0 + 190 * BAR_MS)
        url = (f"{BASE}/api/v2/mix/market/history-candles?symbol={sym}&productType=USDT-FUTURES"
               f"&granularity=15m&startTime={w0}&endTime={w1}&limit=200")
        d = _http_json(url, opener, sleep)
        if not isinstance(d, dict) or d.get("code") != "00000" or not isinstance(d.get("data"), list):
            raise ValueError("risposta rifiutata")
        for r in d["data"]:
            ts = int(float(r[0]))
            if ts + BAR_MS <= now_ms:
                rows[ts] = [ts, float(r[1]), float(r[2]), float(r[3]), float(r[4])]
        w0 = w1
        sleep(0.4)
    return [rows[k] for k in sorted(rows)]


def complete_window(bars, open_ms, close_ms):
    """Require warmup AND every bar through the exit timestamp bucket.

    Conservative: includes a full bar starting exactly at close_ms when aligned,
    so next-open execution has a price. Recent exits may need one additional bar.
    Missing tail is never interpreted as a HOLD decision.
    """
    if not bars or close_ms < open_ms:
        return False
    start = open_ms // BAR_MS * BAR_MS - WARMUP_BARS * BAR_MS
    last = close_ms // BAR_MS * BAR_MS
    required = [b for b in bars if start <= b[0] <= last]
    return (len(required) == (last - start) // BAR_MS + 1
            and required[0][0] == start and required[-1][0] == last
            and regular(required))


def regular(bars):
    return all(b[0] - a[0] == BAR_MS for a, b in zip(bars, bars[1:]))


# ------------------------------------------------------------------ netto di un'uscita ipotetica

def exit_net(t, px_ref, exit_ms):
    """Netto del trade se si esce al prezzo di riferimento `px_ref` con chiusura a mercato (slippage contro di noi):
    stesse formule di PaperAccount._close (commissione di apertura gia' pagata, di chiusura sul valore di uscita, funding sui long)."""
    side, qty = t["side"], t["qty"]
    fill = px_ref * (1 - side * SLIP_BP / 1e4)
    gross = side * (fill - t["entry"]) * qty
    fee_open = t["margin"] * t["lev"] * FEE_BP / 1e4
    fee_close = qty * fill * FEE_BP / 1e4
    hours = max(0.0, (exit_ms - t["open_ms"]) / 3_600_000)
    funding = qty * t["entry"] * FUND_BP / 1e4 * hours / 8 if side == 1 else 0.0
    return gross - fee_open - fee_close - funding


def stop_net(t, level, bar_open, exit_ms):
    """Uscita su uno stop come engine.on_bar: fill al livello o all'apertura se la barra apre oltre, poi slippage."""
    px = min(level, bar_open) if t["side"] == 1 else max(level, bar_open)
    return exit_net(t, px, exit_ms)


def decision_limit_ms(t):
    """Istante massimo (incluso) in cui un'uscita ipotetica deve avvenire per precedere quella vera."""
    return t["close_ms"] - BAR_MS if t["why"] in BAR_EXITS else t["close_ms"]


# ------------------------------------------------------------------ regole a pavimento di prezzo

def run_stop_rule(t, bars, arm_r, give_r, tp_bar=True):
    """Pavimento sul prezzo, in unita' di R (R = distanza dello stop iniziale). Quando il massimo favorevole (barre CHIUSE
    dopo l'ingresso) raggiunge `arm_r`, il pavimento sale a pareggio+costi; con `give_r` non nullo insegue il massimo a
    distanza give_r x R (mai sotto pareggio+costi). Un livello nuovo vale dalla barra dopo. Ritorna (netto, ms uscita,
    motivo) se scatta PRIMA dell'uscita vera, altrimenti None."""
    side, entry = t["side"], t["entry"]
    rd = entry * t["r_dist"]
    cost = entry * (2 * FEE_BP + 2 * SLIP_BP) / 1e4           # costo andata e ritorno in prezzo
    be = entry + side * cost
    # barra d'uscita vera: inclusa per lo stop loss (il pavimento scatta prima o insieme); per il take profit dipende da
    # `tp_bar`: True = convenzione dell'engine (lo stop prevale), False = ipotesi favorevole alla regola (barra esclusa)
    last_end = t["close_ms"] if (t["why"] == "stop loss" or (t["why"] == "take profit" and tp_bar)) else decision_limit_ms(t)
    floor, best = None, None
    for ts, o, h, l, c in bars:
        end = ts + BAR_MS
        if end <= t["open_ms"]:
            continue
        if end > last_end:
            break
        if floor is not None and (l <= floor if side == 1 else h >= floor):
            return stop_net(t, floor, o, end), end, "pavimento"
        if ts <= t["open_ms"] < end:                           # barra d'ingresso: estremi in parte precedenti all'ingresso
            continue
        ext = h if side == 1 else l
        best = ext if best is None else (max(best, ext) if side == 1 else min(best, ext))
        if side * (best - entry) / rd >= arm_r:
            cand = be
            if give_r:
                cand = max(be, best - give_r * rd) if side == 1 else min(be, best + give_r * rd)
            floor = cand if floor is None else (max(floor, cand) if side == 1 else min(floor, cand))
    return None


# ------------------------------------------------------------------ chiusura parziale a +N R (+ pareggio sul resto)

def _scaled(t, frac):
    return dict(t, margin=t["margin"] * frac, qty=t["qty"] * frac)


def run_partial(t, bars, level_r, frac, be_rest):
    """Ordine limite che chiude la frazione `frac` quando il prezzo tocca +level_r R (fill al livello con le regole
    dell'engine). Con `be_rest` il resto ha da quel momento un pavimento a pareggio+costi (vale dalla barra dopo).
    Il resto, se il pavimento non scatta prima, finisce come l'uscita vera (il netto e' proporzionale alla quantita').
    Ritorna (netto totale, ms della prima azione, motivo) solo se il parziale e' scattato PRIMA dell'uscita vera."""
    side, entry = t["side"], t["entry"]
    level = entry + side * level_r * entry * t["r_dist"]
    be = entry + side * entry * (2 * FEE_BP + 2 * SLIP_BP) / 1e4
    part, rest = _scaled(t, frac), _scaled(t, 1.0 - frac)
    limit = decision_limit_ms(t)                                   # il parziale solo in barre che finiscono prima dell'uscita vera
    part_end = None
    for ts, o, h, l, c in bars:
        end = ts + BAR_MS
        if end <= t["open_ms"]:
            continue
        if end > t["close_ms"]:
            break
        if part_end is None:
            if end > limit or ts <= t["open_ms"] < end:            # barra d'ingresso: estremi in parte precedenti
                continue
            if (h >= level) if side == 1 else (l <= level):
                part_end = end
        elif be_rest and (l <= be if side == 1 else h >= be):
            return exit_net(part, level, part_end) + stop_net(rest, be, o, end), part_end, "parziale+pareggio"
    if part_end is None:
        return None
    return exit_net(part, level, part_end) + (1.0 - frac) * t["net"], part_end, "parziale"


# ------------------------------------------------------------------ regole di ChatGPT (desk.profit) a barra chiusa

def _decision_points(t, bars, phase):
    """Per ogni barra chiusa utile: (indice, istante, vista posizione, caratteristiche, liquidazione). Solo barre la cui
    esecuzione (apertura della barra dopo) precede l'uscita vera."""
    from desk.profit.features import Bar, extract
    from desk.profit.liquidable import Costs, Leg, PositionView, evaluate
    costs = Costs(FEE_BP / 1e4, 0.0, SLIP_BP / 1e4)
    fee_open = t["margin"] * t["lev"] * FEE_BP / 1e4
    limit = decision_limit_ms(t)
    pb = [Bar(b[0] + BAR_MS, b[1], b[2], b[3], b[4]) for b in bars]
    for i, b in enumerate(bars):
        at = b[0] + BAR_MS
        if at <= t["open_ms"]:
            continue
        if at > limit or i + 1 >= len(bars):
            break
        if phase is not None and (at // BAR_MS) % 2 != phase:
            continue
        hours = max(0.0, (at - t["open_ms"]) / 3_600_000)
        funding = t["qty"] * t["entry"] * FUND_BP / 1e4 * hours / 8 if t["side"] == 1 else 0.0
        view = PositionView(t["side"], (Leg(t["entry"], t["qty"], fee_open),), funding, 0.0, t["margin"])
        f = extract(pb[max(0, i - 24):i + 1], asof_ms=at, opened_ms=t["open_ms"], peak_ms=t["open_ms"],
                    interval_ms=BAR_MS, max_age_ms=BAR_MS)
        if f.mark <= 0:
            continue
        yield i, at, view, f, evaluate(view, f.mark, costs)


def _exit_at_next_open(t, bars, i):
    nb = bars[i + 1]
    return exit_net(t, nb[1], nb[0]), nb[0], "mercato"


def run_machine(t, bars, policy, phase):
    """Il Profit Manager di ChatGPT (desk.profit.machine) valutato a barra chiusa; uscita a mercato alla barra dopo."""
    from desk.profit.machine import State, step
    from desk.profit.reversal import assess
    state = State()
    for i, at, view, f, liq in _decision_points(t, bars, phase):
        d = step(state, features=f, liquidation=liq, qty=t["qty"], reversal=assess(f, t["side"]), policy=policy)
        state = d.state
        if d.action == "ESCI":
            return _exit_at_next_open(t, bars, i)
    return None


def run_roi(t, bars, roi_policy, phase, with_target):
    """Varianti A/B in ROI (profit_sidecar.roi_variants), uscita a mercato alla barra dopo."""
    from desk.profit_sidecar import roi_variants as rv
    st = rv.RoiState()
    key = "b" if with_target else "a"
    for i, at, view, f, liq in _decision_points(t, bars, phase):
        st, dec = rv.step(st, roi=liq.roi_pct, eval_ms=at, credible_reversal=False, features_valid=f.valid,
                          policy=roi_policy)
        if dec[key] in ("EXIT_FLOOR", "EXIT_TARGET"):
            return _exit_at_next_open(t, bars, i)
    return None


# ------------------------------------------------------------------ confronto

def evaluate_policy(trades, bars_by_trade, runner):
    """Per ogni trade: netto vero, netto con la regola. Se la regola non scatta prima, vale l'uscita vera."""
    rows, errors = [], 0
    for t in trades:
        bars = bars_by_trade.get(id(t))
        if not bars:
            continue
        try:
            res = runner(t, bars)
        except (ValueError, ArithmeticError):
            errors += 1
            continue
        alt = t["net"] if res is None else res[0]
        rows.append({"t": t, "alt": alt, "changed": res is not None, "delta": alt - t["net"]})
    return rows, errors


def halves(rows):
    """Differenza (regola - vero) nella prima e nella seconda meta' dei trade, in ordine di chiusura: e' stabile?"""
    rs = sorted(rows, key=lambda r: r["t"]["close_ms"])
    h = len(rs) // 2
    return sum(r["delta"] for r in rs[:h]), sum(r["delta"] for r in rs[h:])


def summarize(rows, errors=0):
    n = len(rows)
    if not n:
        return "n=0 (errori %d)" % errors
    ch = [r for r in rows if r["changed"]]
    base = sum(r["t"]["net"] for r in rows)
    alt = sum(r["alt"] for r in rows)
    up = [r for r in ch if r["delta"] > 0]
    dn = [r for r in ch if r["delta"] < 0]
    gb = [r for r in rows if r["t"]["net"] < 0 and r["t"]["mfe_r"] >= 1.0]
    gb_fix = sum(1 for r in gb if r["alt"] > 0)
    cut_w = [r for r in dn if r["t"]["net"] > 0]
    wins_b = sum(1 for r in rows if r["t"]["net"] > 0)
    wins_a = sum(1 for r in rows if r["alt"] > 0)
    return ("n=%d | vero %+.0f$ -> regola %+.0f$ (diff %+.0f$) | scatta %d: meglio %d (%+.0f$), peggio %d (%+.0f$; di cui %d erano vincenti) | "
            "vincenti %d%% -> %d%% | meta' %+.0f$/%+.0f$ | persi dopo +1R: %d, girati in utile %d%s" % (
                n, base, alt, alt - base, len(ch), len(up), sum(r["delta"] for r in up), len(dn),
                sum(r["delta"] for r in dn), len(cut_w), round(100 * wins_b / n), round(100 * wins_a / n), halves(rows)[0], halves(rows)[1], len(gb), gb_fix,
                (" | errori %d" % errors) if errors else ""))


def r_multiple(t, px):
    return t["side"] * (px - t["entry"]) / (t["entry"] * t["r_dist"])


def distribution(trades):
    """Dove si trovano i profitti: quanti trade toccano +1R e come finiscono (per tipo di uscita)."""
    out = []
    reached = [t for t in trades if t["mfe_r"] >= 1.0]
    out.append("toccano +1R: %d di %d" % (len(reached), len(trades)))
    for lab, grp in (("take profit", [t for t in reached if t["why"] == "take profit"]),
                     ("stop loss", [t for t in reached if t["why"] == "stop loss"]),
                     ("chiusura Claude/manuale", [t for t in reached if t["why"] not in BAR_EXITS])):
        if grp:
            out.append("  finiti con %s: %d, netto %+.0f$ (medio %+.1f$)" % (lab, len(grp), sum(t["net"] for t in grp),
                                                                              sum(t["net"] for t in grp) / len(grp)))
    tps = sorted(r_multiple(t, t["exit"]) for t in trades if t["why"] == "take profit")
    sls = sorted(r_multiple(t, t["exit"]) for t in trades if t["why"] == "stop loss")
    q = lambda a, p: a[min(len(a) - 1, int(p * len(a)))]
    if tps:
        out.append("take profit in R: min %.2f mediana %.2f max %.2f (n=%d)" % (tps[0], q(tps, .5), tps[-1], len(tps)))
    if sls:
        out.append("stop loss in R: min %.2f mediana %.2f max %.2f (n=%d)" % (sls[0], q(sls, .5), sls[-1], len(sls)))
    lost = [t for t in trades if t["net"] < 0 and t["mfe_r"] >= 1.0]
    if lost:
        out.append("persi dopo +1R: %d, netto %+.0f$ (se fossero usciti a pareggio: %+.0f$)" % (
            len(lost), sum(t["net"] for t in lost), sum(exit_net(t, t["entry"], t["close_ms"]) for t in lost)))
    return out


def build_runners(bot):
    from desk.profit.policy_bull import research_policy as bull_p
    from desk.profit.policy_hawk import research_policy as hawk_p
    from desk.profit_sidecar.roi_variants import RoiPolicy
    pol = hawk_p() if bot == "hawk" else bull_p()
    runners = {}
    for phase, lab in ((None, "15m"), (0, "30m-a"), (1, "30m-b")):
        runners["PM ATR research-1 (%s)" % lab] = (lambda t, b, ph=phase: run_machine(t, b, pol, ph))
    for phase, lab in ((None, "15m"), (0, "30m-a"), (1, "30m-b")):
        runners["ROI-A 15/5/5 (%s)" % lab] = (lambda t, b, ph=phase: run_roi(t, b, RoiPolicy(), ph, False))
        runners["ROI-B +target25 (%s)" % lab] = (lambda t, b, ph=phase: run_roi(t, b, RoiPolicy(), ph, True))
    for arm, give in ((0.75, 0), (1.0, 0), (1.5, 0), (1.0, 0.75), (1.0, 1.0), (1.5, 1.0), (1.5, 0.75), (2.0, 1.0), (2.0, 1.5)):
        lab = "pareggio dopo +%gR" % arm if not give else "insegue %gR dopo +%gR" % (give, arm)
        runners["stop: " + lab] = (lambda t, b, a=arm, g=give: run_stop_rule(t, b, a, g))
    for arm, give in ((1.0, 0), (1.0, 0.75), (0.75, 0)):
        lab = "pareggio dopo +%gR" % arm if not give else "insegue %gR dopo +%gR" % (give, arm)
        runners["stop (barra TP esclusa): " + lab] = (lambda t, b, a=arm, g=give: run_stop_rule(t, b, a, g, False))
    for lvl, frac, be in ((1.0, 0.5, False), (1.0, 0.5, True), (1.0, 0.33, True), (0.75, 0.5, True), (1.5, 0.5, True)):
        runners["parziale %d%% a +%gR%s" % (round(frac * 100), lvl, " + pareggio sul resto" if be else "")] = (
            lambda t, b, l=lvl, f=frac, e=be: run_partial(t, b, l, f, e))
    return runners


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="/data")
    ap.add_argument("--bots", default="hawk,bull")
    args = ap.parse_args(argv)
    now_ms = int(time.time() * 1000)
    cache = {}
    for bot in args.bots.split(","):
        path = os.path.join(args.data_root, bot, "learning_log.jsonl")
        trades, skipped = load_trades(path, bot)
        print("=== %s: trade puliti %d | scartati %s" % (bot.upper(), len(trades), dict(skipped)), flush=True)
        bad = [t for t in trades if t["recon_err"] > 0.5]
        print("coerenza formule engine: %d su %d tornano al centesimo (|diff|<=0.5$), %d no (esclusi)" % (
            len(trades) - len(bad), len(trades), len(bad)), flush=True)
        if bad:
            print("  esempi non coerenti: " + "; ".join("%s %s net %.2f diff %.2f" % (
                t["symbol"], t["why"], t["net"], t["recon_err"]) for t in bad[:3]), flush=True)
        trades = [t for t in trades if t["recon_err"] <= 0.5]
        by_sym = collections.defaultdict(list)
        for t in trades:
            by_sym[t["symbol"]].append(t)
        bars_by, miss = {}, 0
        for sym, ts in sorted(by_sym.items()):
            lo = min(t["open_ms"] for t in ts) // BAR_MS * BAR_MS - WARMUP_BARS * BAR_MS
            hi = max(t["close_ms"] for t in ts) // BAR_MS * BAR_MS + TAIL_BARS * BAR_MS
            key = (sym, lo, hi)
            if key not in cache:
                try:
                    cache[key] = fetch_bars(sym, lo, hi, now_ms)
                except Exception as e:
                    print("candele %s: errore %s" % (sym, type(e).__name__), flush=True)
                    cache[key] = []
            allb = cache[key]
            for t in ts:
                a = t["open_ms"] // BAR_MS * BAR_MS - WARMUP_BARS * BAR_MS
                z = t["close_ms"] // BAR_MS * BAR_MS + TAIL_BARS * BAR_MS
                seg = [b for b in allb if a <= b[0] <= z]
                if complete_window(seg, t["open_ms"], t["close_ms"]) and regular(seg):
                    bars_by[id(t)] = seg
                else:
                    miss += 1
        print("candele 15m: trade con serie completa %d, senza %d" % (len(bars_by), miss), flush=True)
        runnable = [t for t in trades if id(t) in bars_by]
        why = collections.Counter(t["why"] for t in runnable)
        print("uscite vere: %s" % dict(why.most_common(6)), flush=True)
        for line in distribution(runnable):
            print(line, flush=True)
        print("BASE (uscita vera): n=%d netto %+.0f$ vincenti %d%% | persi dopo +1R: %d" % (
            len(runnable), sum(t["net"] for t in runnable),
            round(100 * sum(1 for t in runnable if t["net"] > 0) / max(1, len(runnable))),
            sum(1 for t in runnable if t["net"] < 0 and t["mfe_r"] >= 1.0)), flush=True)
        for name, runner in build_runners(bot).items():
            rows, errs = evaluate_policy(runnable, bars_by, runner)
            print("%-30s %s" % (name, summarize(rows, errs)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
