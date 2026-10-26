#!/usr/bin/env python3
"""Banco di prova storico di Hawk: rifa' la storia con il MOTORE VERO (desk.engine.PaperAccount) e le REGOLE VERE
(desk.signals.read_symbol + desk.brain.rules_decisions), cosi' come girano in produzione quando decidono le regole.

Cosa fa: scarica dall'API pubblica di Bitget (nessuna chiave) le candele 15m, 4h e 1d di tutti i simboli, poi percorre il
periodo barra per barra (15 minuti). A ogni passo calcola i segnali UNA volta e li da' a tutte le varianti, ognuna con il
suo conto separato da 1000$. Le varianti differiscono solo per il regime di mercato (desk/regime.py): filtro dei lati in
apertura, stop che segue il profitto, uscita se il mercato gira. "base" = regole come oggi, senza regime.

Limiti dichiarati (leggerli prima di fidarsi dei numeri):
- SOLO le regole decidono (come negli ultimi 15 giorni di storico reale: nessuna apertura di Claude e' mai stata eseguita);
- barre da 15 minuti: dentro la barra stop e TP si giudicano come fa il motore (stop prima del TP);
- niente calendario macro, niente seconda gamba, niente DCA: le regole non li usano;
- le commissioni, lo scivolamento e il funding sono quelli del motore;
- e' UN solo periodo di mercato: non e' una promessa sul futuro. Per questo si guardano anche i terzi del periodo.

Uso:  python3 deploy/scripts/desk_backtest.py --days 90 [--cache DIR] [--step 1] [--only base,full] [--out file.json]
      python3 deploy/scripts/desk_backtest.py --synthetic     (prova del codice su dati finti, nessuna rete)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "backend")))

from desk import regime as rg  # noqa: E402
from desk.brain import rules_decisions  # noqa: E402
from desk.engine import Limits, PaperAccount  # noqa: E402
from desk.signals import closed_daily, closed_four_hour, read_symbol  # noqa: E402

BASE = "https://api.bitget.com"
BAR = 900_000
H4 = 14_400_000
DAY = 86_400_000
SYMBOLS = ["BTC", "ETH", "BNB", "XRP", "SOL", "ADA", "DOGE", "AVAX", "DOT", "LINK", "UNI", "ATOM", "LTC", "BCH",
           "APT", "ARB", "OP", "NEAR", "FIL", "INJ", "SUI", "TIA", "RUNE", "STX", "XAU", "XAG"]
TIER_AB = {"BTC", "ETH", "XAU", "XAG"}
SCALP_COOLDOWN_MS = 600_000
MEDIO_COOLDOWN_MS = 3_600_000
ENTRY_SCORE_BASE = 60
# Capitale FISSO: il conto parte da 100000$ cosi' non si esaurisce mai (alla seconda prova il conto da 1000$ era finito in
# quattro settimane e le altre nove non venivano provate). Il margine per operazione (100$), il margine totale (1000$) e
# le posizioni massime (10) restano quelli di Hawk. Lo stop giornaliero e' 0.1% di 100000$ = 100$ al giorno, come il 10%
# di un conto da 1000$. kill_equity spento: in produzione l'utente azzera il portafoglio quando scende.
HAWK_LIMITS = dict(start_equity=100000.0, max_margin_trade=100.0, max_margin_total=1000.0, max_open=10,
                   kill_equity=-1e9, daily_stop=0.001)
HAWK_MIN_MARGIN, HAWK_MIN_LEV, HAWK_FORCED_MARGIN, HAWK_FORCED_LEV = 50.0, 10, 60.0, 15


def tier(sym: str) -> int:
    return 60 if sym in TIER_AB else 63


# ------------------------------------------------------------------ scarico dati
def http_json(url: str, tries: int = 6):
    wait = 1.0
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(wait)
                wait *= 2
                continue
            raise
        except Exception as e:     # rete: si riprova
            last = e
            time.sleep(wait)
            wait *= 2
    raise RuntimeError(f"rete: {url[:100]} ({last})")


def fetch_range(sym: str, gran: str, step_ms: int, start: int, end: int, gap: float = 0.12) -> list:
    """Righe [ts, o, h, l, c, vol] tra start e end, a finestre che non superano 85 giorni ne' 200 barre."""
    full = sym if sym.endswith("USDT") else sym + "USDT"
    rows: dict = {}
    cur_end = end
    for _ in range(600):
        win = min(200 * step_ms, 85 * DAY)
        s = max(start, cur_end - win)
        url = (f"{BASE}/api/v2/mix/market/history-candles?symbol={full}&productType=USDT-FUTURES"
               f"&granularity={gran}&startTime={s}&endTime={cur_end}&limit=200")
        d = http_json(url)
        data = d.get("data") if isinstance(d, dict) and d.get("code") == "00000" else None
        if data:
            for r in data:
                rows[int(float(r[0]))] = [float(x) for x in r[:6]]
        if s <= start:
            break
        cur_end = s - 1 if data else s - 1
        time.sleep(gap)
    return [rows[k] for k in sorted(rows)]


def load_data(symbols, days: int, cache: str | None, end_ms: int):
    t_start = end_ms - days * DAY
    spec = (("a15", "15m", BAR, t_start - 12 * DAY), ("a4", "4H", H4, t_start - 62 * DAY), ("ad", "1D", DAY, t_start - 300 * DAY))
    data = {}
    for sym in symbols:
        d = {}
        ok = True
        for key, gran, step, st in spec:
            path = os.path.join(cache, f"{sym}_{gran}_{days}.json") if cache else None
            rows = None
            if path and os.path.exists(path):
                rows = json.load(open(path))
            if rows is None:
                try:
                    rows = fetch_range(sym, gran, step, st, end_ms)
                except Exception as e:
                    print(f"[DATI] {sym} {gran}: {e}", flush=True)
                    rows = []
                if path and rows:
                    os.makedirs(cache, exist_ok=True)
                    json.dump(rows, open(path, "w"))
            arr = np.array(rows, dtype=float) if rows else np.empty((0, 6))
            if len(arr):
                arr = arr[arr[:, 0] + step <= end_ms]            # solo barre chiuse
            d[key] = arr
        if len(d["a15"]) < 1500 or len(d["a4"]) < 220:
            print(f"[DATI] {sym}: storia insufficiente (15m={len(d['a15'])}, 4h={len(d['a4'])}): escluso", flush=True)
            ok = False
        if ok:
            data[sym] = d
            print(f"[DATI] {sym}: 15m={len(d['a15'])} 4h={len(d['a4'])} 1d={len(d['ad'])}", flush=True)
    return data


def synthetic_data(days: int, end_ms: int):
    """Dati finti con tratti di discesa, salita e laterale comuni a tutti i simboli: serve solo a provare il codice."""
    rng = np.random.default_rng(7)
    n15 = (days + 14) * 96
    seg = np.repeat(rng.choice([-1.0, 0.0, 1.0], size=n15 // 800 + 2), 800)[:n15] * 0.0007
    common = rng.normal(0, 0.0015, n15) + seg
    data = {}
    for k, sym in enumerate(SYMBOLS):
        r = common * (0.8 + 0.4 * rng.random()) + rng.normal(0, 0.0012, n15)
        c = 100.0 * (k + 1) * np.exp(np.cumsum(r))
        o = np.concatenate([[c[0]], c[:-1]])
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.0006, n15)))
        l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.0006, n15)))
        t = end_ms - (n15 - np.arange(n15)) * BAR
        a15 = np.column_stack([t, o, h, l, c, rng.uniform(1, 10, n15)])
        a15 = a15[a15[:, 0] + BAR <= end_ms]

        def agg(step):
            key = (a15[:, 0] // step).astype(np.int64)
            out = []
            for kk in np.unique(key):
                g = a15[key == kk]
                if len(g) == step // BAR:
                    out.append([kk * step, g[0, 1], g[:, 2].max(), g[:, 3].min(), g[-1, 4], g[:, 5].sum()])
            return np.array(out, dtype=float)
        data[sym] = {"a15": a15, "a4": agg(H4), "ad": agg(DAY)}
    return data


# ------------------------------------------------------------------ varianti
class Variant:
    def __init__(self, name: str, params):
        self.name, self.params = name, params           # params None = regole di oggi, senza regime
        self.acc = PaperAccount(Limits(**HAWK_LIMITS), name)
        self.hist: list = []
        self.last_open: dict = {}
        self.ctx: dict = {}                              # id posizione -> {regime, side}
        self.equity: list = []
        self.slots: list = []
        self.opens = 0
        self.blocked = 0


def make_variants(only=None):
    P = rg.RegimeParams
    v = {"base": None,
         "solo_protezione": P(gate=False, flip_exit=False),
         "solo_filtro": P(ratchet=False, flip_exit=False),
         "filtro+protezione": P(flip_exit=False),
         "completo": P(),
         "solo_uscita_inversione": P(gate=False, ratchet=False)}
    sweeps = {
        "completo_soglia0.15": P(state_thr=0.15), "completo_soglia0.35": P(state_thr=0.35),
        "completo_inv0.25": P(turn_delta=0.25), "completo_inv0.50": P(turn_delta=0.50),
        "completo_senza_capitolazione": P(capitulation_roc=None),
        "completo_extra0": P(range_extra=0), "completo_extra6": P(range_extra=6),
        "completo_long_anche_laterale": P(long_needs_up=False),
        "completo_be0.8": P(be_at_r=0.8), "completo_be1.3": P(be_at_r=1.3),
        "completo_trail1.2": P(trail_at_r=1.2), "completo_trail1.7": P(trail_at_r=1.7),
        "completo_gap0.4": P(trail_gap_r=0.4), "completo_gap0.9": P(trail_gap_r=0.9),
        "completo_flip-0.25": P(flip_min_r=-0.25), "completo_flip-1.0": P(flip_min_r=-1.0),
        "completo_senza_flip": P(flip_exit=False),
    }
    v.update(sweeps)
    if only:
        v = {k: x for k, x in v.items() if k in only}
    return v


# ------------------------------------------------------------------ esecuzione (copia fedele del percorso di cli.py)
def execute(var: Variant, decisions, prices, now_ms: int, reg_state: str):
    acc = var.acc
    for dec in decisions:
        sym = dec["symbol"]
        px = prices.get(sym)
        if px is None:
            continue
        if dec["action"] == "close":
            if sym in acc.positions:
                acc.close(sym, px, now_ms, dec.get("close_why") or "chiusura regole")
            continue
        if dec["action"] not in ("open_long", "open_short"):
            continue
        trade_type = dec.get("trade_type", "medio")
        cooldown = SCALP_COOLDOWN_MS if trade_type == "scalp" else MEDIO_COOLDOWN_MS
        if now_ms - var.last_open.get(sym, 0) < cooldown or sym in acc.positions:
            continue
        if dec["confidence"] < tier(sym):
            continue
        sl_pct, tp_pct = dec.get("stop_loss_pct", 0), dec.get("take_profit_pct", 0)
        if sl_pct > 0 and tp_pct > 0 and tp_pct / sl_pct < 1.5:
            continue
        side = 1 if dec["action"] == "open_long" else -1
        sl = px * (1 - side * sl_pct)
        tp = px * (1 + side * tp_pct) if tp_pct > 0 else None
        margin, lev = dec["margin_usd"], dec["leverage"]
        if margin < HAWK_MIN_MARGIN or lev < HAWK_MIN_LEV:
            margin, lev, trade_type = HAWK_FORCED_MARGIN, HAWK_FORCED_LEV, "scalp"
        margin = min(margin, acc.limits.max_margin_trade)
        pos, _msg = acc.open(sym, side, margin, lev, px, sl, tp, now_ms, prices, confidence=dec["confidence"],
                             reason=dec.get("reason", "")[:200], source="rules", trade_type=trade_type)
        if pos:
            var.last_open[sym] = now_ms
            var.opens += 1
            var.ctx[pos.id] = {"regime": reg_state, "side": side}
        else:
            var.blocked += 1


# ------------------------------------------------------------------ riproduzione
def replay(data, variants: dict, t_start: int, t_end: int, step: int):
    syms = list(data)
    pos_idx = {s: {int(t): i for i, t in enumerate(data[s]["a15"][:, 0])} for s in syms}
    vs = {name: Variant(name, p) for name, p in variants.items()}
    grid = list(range(t_start, t_end, BAR))
    n_steps = 0
    t_wall = time.time()
    for k, t in enumerate(grid):
        end = t + BAR
        # 1) la barra appena chiusa viene giudicata per le posizioni aperte (stop/TP come nel motore)
        for var in vs.values():
            for sym in list(var.acc.positions):
                i = pos_idx.get(sym, {}).get(t)
                if i is None:
                    continue
                row = data[sym]["a15"][i]
                var.acc.on_bar(sym, int(t), float(row[1]), float(row[2]), float(row[3]), float(row[4]), BAR)
        if k % step:
            continue
        # 2) segnali: una volta sola per passo
        readings = []
        prices = {}
        btc_ret3 = None
        i_btc = pos_idx.get("BTC", {}).get(t)
        if i_btc is not None and i_btc > 288:
            b = data["BTC"]["a15"]
            btc_ret3 = float(b[i_btc, 4] / b[i_btc - 288, 4] - 1.0)
        for sym in syms:
            i = pos_idx[sym].get(t)
            if i is None:
                continue
            d = data[sym]
            win = d["a15"][max(0, i - 999): i + 1]
            prices[sym] = float(win[-1, 4])
            n4 = int(np.searchsorted(d["a4"][:, 0] + H4, end, side="right"))
            fh = closed_four_hour(d["a4"][max(0, n4 - 300): n4], end) if n4 else []
            nd = int(np.searchsorted(d["ad"][:, 0] + DAY, end, side="right")) if len(d["ad"]) else 0
            dl = closed_daily(d["ad"][max(0, nd - 340): nd], end) if nd else None
            try:
                r = read_symbol(sym, win, end, daily=dl, price=prices[sym], four_hour=fh, btc_return_3d=btc_ret3)
            except Exception:
                r = None
            if r is not None:
                readings.append(r)
        if not readings:
            continue
        n_steps += 1
        day = time.strftime("%Y-%m-%d", time.gmtime(end / 1000))
        # 3) ogni variante decide con i suoi parametri
        for var in vs.values():
            acc = var.acc
            acc.roll_day(day, prices)
            regime = None
            if var.params is not None:
                regime = rg.compute(readings, var.hist, var.params)
                var.hist = rg.push_hist(var.hist, regime)
            protect = rg.apply_ratchet(acc.positions, prices, var.params) if regime is not None else {}
            pos_info = []
            for sym, pos in acc.positions.items():
                px = prices.get(sym, pos.entry)
                cur_r, _pk = rg.r_metrics(pos.side, pos.entry, px, rg.peak_price(pos), rg.r_unit(pos))
                pos_info.append({"symbol": sym, "side": pos.side, "trade_type": pos.trade_type, "cur_r": cur_r})
            decisions = rules_decisions(readings, pos_info, set(acc.positions), ENTRY_SCORE_BASE,
                                        regime=regime, rparams=var.params, tier_fn=tier)
            if regime is not None:
                decisions = list(decisions) + rg.management_closes(pos_info, decisions, regime, protect, var.params)
            execute(var, decisions, prices, end, regime.state if regime else "-")
            var.equity.append((end, acc.equity(prices)))
            var.slots.append(len(acc.positions))
        if n_steps % 500 == 0:
            print(f"[RIPRODUZIONE] passo {n_steps} ({k + 1}/{len(grid)} barre) {time.time() - t_wall:.0f}s", flush=True)
    return vs


# ------------------------------------------------------------------ risultati
def trades_of(var: Variant):
    by = defaultdict(lambda: {"net": 0.0, "final": None, "side": None, "open_ms": None})
    for rec in var.acc.closed:
        g = by[rec["id"]]
        g["net"] += float(rec.get("net") or 0.0)
        g["side"] = rec.get("side")
        if not rec.get("partial"):
            g["final"] = rec
            g["close_ms"] = rec.get("close_ms")
            g["hold_min"] = rec.get("hold_min")
            g["why"] = str(rec.get("why") or "")
    out = []
    for tid, g in by.items():
        if g["final"] is None:
            continue
        g["id"] = tid
        g["regime"] = var.ctx.get(tid, {}).get("regime", "-")
        out.append(g)
    return out


def summarize(var: Variant, t_start: int, t_end: int, since_ms: int | None = None):
    ts = [t for t in trades_of(var) if since_ms is None or (t.get("close_ms") or 0) >= since_ms]
    n = len(ts)
    wins = [t["net"] for t in ts if t["net"] > 0]
    loss = [t["net"] for t in ts if t["net"] <= 0]
    net = sum(t["net"] for t in ts)
    gl = -sum(loss)
    eq = [e for (tm, e) in var.equity if since_ms is None or tm >= since_ms]
    peak, dd = -1e18, 0.0
    for e in eq:
        peak = max(peak, e)
        dd = max(dd, peak - e)                       # drawdown massimo in dollari (il capitale puo' scendere sotto 450$)
    span_days = max(1e-9, ((t_end - (since_ms or t_start)) / DAY))
    third = (t_end - t_start) / 3.0
    thirds = [sum(t["net"] for t in ts if t_start + i * third <= (t.get("close_ms") or 0) < t_start + (i + 1) * third + 1) for i in range(3)]
    weeks: dict = defaultdict(float)
    for t in ts:
        weeks[int(((t.get("close_ms") or 0) - t_start) // (7 * DAY))] += t["net"]
    n_weeks = max(1, int(math.ceil((t_end - max(t_start, since_ms or t_start)) / (7 * DAY))))
    longs = [t for t in ts if t["side"] == 1]
    shorts = [t for t in ts if t["side"] == -1]
    holds = [t["hold_min"] for t in ts if t.get("hold_min") is not None]
    return {"nome": var.name, "trade": n, "netto": round(net, 1), "vinc%": round(100 * len(wins) / n, 0) if n else 0,
            "medio": round(net / n, 2) if n else 0.0, "PF": round(sum(wins) / gl, 2) if gl > 0 else None,
            "vinc_medio": round(sum(wins) / len(wins), 1) if wins else 0.0,
            "perd_medio": round(sum(loss) / len(loss), 1) if loss else 0.0,
            "dd$": round(dd, 0), "aperture/giorno": round(len(ts) / span_days, 1),
            "tenuta_min": round(sum(holds) / len(holds), 0) if holds else 0,
            "slot_medi": round(sum(var.slots) / len(var.slots), 1) if var.slots else 0.0,
            "long": f"{len(longs)}/{sum(t['net'] for t in longs):+.0f}$", "short": f"{len(shorts)}/{sum(t['net'] for t in shorts):+.0f}$",
            "terzi": [round(x, 0) for x in thirds],
            "sett+": f"{sum(1 for v in weeks.values() if v > 0)}/{n_weeks}", "bloccate": var.blocked}


def print_table(rows, title):
    print(f"\n=== {title} ===")
    print(f"{'variante':<30}{'trade':>6}{'netto$':>9}{'vinc%':>6}{'medio':>7}{'PF':>6}{'DD$':>6}{'ap/g':>6}{'tenuta':>7}{'slot':>5}  {'long':<11}{'short':<11}{'sett+':>6}  terzi del periodo")
    for r in rows:
        print(f"{r['nome']:<30}{r['trade']:>6}{r['netto']:>9.1f}{r['vinc%']:>6.0f}{r['medio']:>7.2f}{(r['PF'] if r['PF'] is not None else 0):>6.2f}"
              f"{r['dd$']:>6.0f}{r['aperture/giorno']:>6.1f}{r['tenuta_min']:>7.0f}{r['slot_medi']:>5.1f}  {r['long']:<11}{r['short']:<11}{r['sett+']:>6}  {r['terzi']}")


def weekly(var: Variant, t_start: int, t_end: int):
    n = int(math.ceil((t_end - t_start) / (7 * DAY)))
    w = [0.0] * n
    c = [0] * n
    for t in trades_of(var):
        k = int(((t.get("close_ms") or 0) - t_start) // (7 * DAY))
        if 0 <= k < n:
            w[k] += t["net"]
            c[k] += 1
    print(f"   {var.name:<30} netto per settimana: " + " ".join(f"{x:+.0f}" for x in w))
    print(f"   {'':<30} trade per settimana : " + " ".join(f"{x}" for x in c))


def by_regime(var: Variant):
    g = defaultdict(list)
    for t in trades_of(var):
        g[(t["regime"], "LONG" if t["side"] == 1 else "SHORT")].append(t["net"])
    print(f"\n--- {var.name}: esito per regime al momento dell'apertura ---")
    for (rgm, sd), v in sorted(g.items()):
        w = sum(1 for x in v if x > 0)
        print(f"   {rgm:<7}{sd:<6} n={len(v):<4} vinc={100 * w / len(v):3.0f}% netto={sum(v):+8.1f}$ medio={sum(v) / len(v):+6.2f}$")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--step", type=int, default=1, help="barre da 15m tra una decisione e l'altra (1 = 15 minuti)")
    ap.add_argument("--cache", default=None)
    ap.add_argument("--only", default=None, help="elenco di varianti separate da virgola")
    ap.add_argument("--out", default=None)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--compare-from", default="2026-10-12", help="data (UTC) da cui confrontare col periodo reale dei bot")
    a = ap.parse_args()

    end_ms = (int(time.time() * 1000) // BAR) * BAR
    meta = os.path.join(a.cache, "meta.json") if a.cache else None
    if meta and os.path.exists(meta):
        end_ms = int(json.load(open(meta))["end_ms"])        # stessi dati per tutte le esecuzioni: confronti onesti
        print(f"[DATI] cache trovata: fine periodo fissata a {time.strftime('%Y-%m-%d %H:%M', time.gmtime(end_ms / 1000))} UTC", flush=True)
    data = synthetic_data(a.days, end_ms) if a.synthetic else load_data(SYMBOLS, a.days, a.cache, end_ms)
    if meta and not os.path.exists(meta) and data:
        os.makedirs(a.cache, exist_ok=True)
        json.dump({"end_ms": end_ms, "days": a.days}, open(meta, "w"))
    if "BTC" not in data:
        raise SystemExit("BTC mancante: impossibile calcolare il regime")
    t_start = end_ms - a.days * DAY
    only = set(a.only.split(",")) if a.only else None
    variants = make_variants(only)
    print(f"[PROVA] {len(data)} simboli, {a.days} giorni, {len(variants)} varianti, passo {a.step * 15} min", flush=True)
    vs = replay(data, variants, t_start, end_ms, a.step)

    rows = [summarize(v, t_start, end_ms) for v in vs.values()]
    print_table(rows, f"TUTTO IL PERIODO ({a.days} giorni)")
    try:
        since = int(time.mktime(time.strptime(a.compare_from, "%Y-%m-%d")) * 1000)
    except ValueError:
        since = None
    if since and since > t_start:
        rows2 = [summarize(v, t_start, end_ms, since) for v in vs.values()]
        print_table(rows2, f"SOLO DAL {a.compare_from} (periodo reale dei bot: Hawk reale ~ +350$ netti con ~245 aperture)")
    print("\n--- andamento per settimana (dalla piu' vecchia alla piu' recente) ---")
    for v in vs.values():
        weekly(v, t_start, end_ms)
    for name in ("base", "completo"):
        if name in vs:
            by_regime(vs[name])
    if a.out:
        json.dump({"tutto": rows, "dal": rows2 if since and since > t_start else None}, open(a.out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
