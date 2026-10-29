"""Banco di prova storico per la modifica long: motore e regole VERI del 13/10, varianti sullo stesso mercato.

Usa `desk.engine.PaperAccount` (commissioni, scivolamento, funding, liquidazione), `desk.brain.rules_decisions`
(apertura/chiusura) e `desk.regime` (solo per le varianti che leggono il mercato). Il punteggio e' calcolato in forma
vettoriale da `labfeat` (equivalenza con `read_symbol` verificata dai test).
"""
from __future__ import annotations

import math
import os
import time
from collections import defaultdict
from types import SimpleNamespace

import numpy as np

from desk import regime as rg
from desk.brain import rules_decisions
from desk.engine import Limits, PaperAccount
from desk.signals import Reading

from labfeat import BAR, COMMODITIES, FEATS, p1_extra_long, points, seasonal_bonus

DAY = 86_400_000
TIER_AB = {"BTC", "ETH", "XAU", "XAG"}
SCALP_COOLDOWN_MS = 600_000
ENTRY_BASE = 60
G_MIN_MARGIN, G_MIN_LEV, G_MARGIN_FORCED, G_LEV_FORCED = 50.0, 10, 60.0, 15      # guardrail Hawk del 13/10
RPARAMS = rg.RegimeParams(ratchet=False, flip_exit=False, range_extra=0)          # profilo "standard" di regime.py


def limits(cost_mult: float = 1.0) -> Limits:
    # Capitale fisso 100000$ (non si esaurisce): margine per trade (100$), margine totale (1000$), posizioni (10) e
    # stop giornaliero (120$ = 12% di 1000$) sono quelli di Hawk. Nessun kill-switch (in produzione si azzera a mano).
    return Limits(start_equity=100000.0, max_margin_trade=100.0, max_margin_total=1000.0, max_open=10,
                  kill_equity=-1e9, daily_stop=0.0012, fee_bp_side=6.0 * cost_mult, slip_bp_side=2.0 * cost_mult)


# ------------------------------------------------------------------ mercato (matrici tempo x simbolo)
class Market:
    def __init__(self, data: dict, feats: dict, t_start: int, t_end: int):
        self.syms = [s for s in data if s in feats]
        self.grid = np.arange(t_start, t_end, BAR, dtype=np.int64)
        K, J = len(self.grid), len(self.syms)
        self.K, self.J = K, J
        self.IDX = np.full((K, J), -1, dtype=np.int64)
        self.F = {k: np.full((K, J), np.nan) for k in FEATS}
        self.OHLC = []
        for j, s in enumerate(self.syms):
            ts = feats[s]["ts"]
            pos = np.searchsorted(ts, self.grid)
            pos = np.clip(pos, 0, len(ts) - 1)
            hit = ts[pos] == self.grid
            self.IDX[hit, j] = pos[hit]
            for k in FEATS:
                self.F[k][hit, j] = feats[s][k][pos[hit]]
            self.OHLC.append(data[s])
        self.valid = np.isfinite(self.F["price"])
        self.jmap = {s: j for j, s in enumerate(self.syms)}
        self.end = self.grid + BAR
        self.even30 = (self.end % 1_800_000) == 0
        self.day = (self.end // DAY).astype(np.int64)
        self.is_comm = np.array([s in COMMODITIES for s in self.syms])
        self._sea = {}

    def seasonal(self, mode: str):
        if mode not in self._sea:
            L = np.zeros((self.K, self.J), dtype=np.int64)
            S = np.zeros((self.K, self.J), dtype=np.int64)
            for j, s in enumerate(self.syms):
                L[:, j], S[:, j] = seasonal_bonus(s, self.end, mode)
            self._sea[mode] = (L, S)
        return self._sea[mode]


# ------------------------------------------------------------------ regime di mercato (dai punteggi del 13/10)
def compute_regime(M: Market, mode: str) -> dict:
    sl_, ss_ = M.seasonal(mode)
    L, S, *_ = points(M.F, 20, None, None, sl_, ss_)
    roc = M.F["roc24"]
    K = M.K
    state = np.zeros(K, dtype=np.int8)
    turn = np.zeros(K, dtype=np.int8)
    smooth = np.zeros(K)
    rocb = np.zeros(K)
    gl = np.zeros(K, dtype=bool)
    gs = np.zeros(K, dtype=bool)
    hist: list = []
    cur = (0, 0, 0.0, 0.0, False, False)
    syms = M.syms
    for k in range(K):
        if M.even30[k]:
            valid = np.nonzero(M.valid[k])[0]
            if len(valid):
                rd = [SimpleNamespace(symbol=syms[j], long_score=int(L[k, j]), short_score=int(S[k, j]),
                                      facts={"roc24h": round(float(roc[k, j]), 4)}) for j in valid]
                r = rg.compute(rd, hist, RPARAMS)
                hist = rg.push_hist(hist, r)
                okl, _ = rg.entry_gate(1, "ALT", r, RPARAMS)
                oks, _ = rg.entry_gate(-1, "ALT", r, RPARAMS)
                cur = (1 if r.state == "up" else -1 if r.state == "down" else 0,
                       1 if r.turn == "up" else -1 if r.turn == "down" else 0, r.smooth, r.roc, okl, oks)
        state[k], turn[k], smooth[k], rocb[k], gl[k], gs[k] = cur
    return {"state": state, "turn": turn, "smooth": smooth, "roc": rocb, "gl": gl, "gs": gs}


def shift_regime(R: dict, days: int) -> dict:
    n = int(days * 96)
    return {k: np.roll(v, n) for k, v in R.items()}


# ------------------------------------------------------------------ varianti
SPECS = {
    "base13": dict(),
    "p1": dict(w4=14, extra="p1reb"),
    "p1_w": dict(w4=14),
    "p1_reb": dict(extra="p1reb"),
    "g_long": dict(gate="long"),
    "t_bonus": dict(extra="turn"),
    "t_bonus_g": dict(extra="turn", gate="long"),
    "r_reb": dict(extra="rreb"),
    "ref_gate": dict(gate="both"),
}
CANDIDATES = ["p1", "p1_w", "p1_reb", "g_long", "t_bonus", "t_bonus_g", "r_reb"]
N_PLACEBO = 12


def build_extra(M: Market, spec: dict, R: dict, rng_seed=None):
    F = M.F
    ex = spec.get("extra")
    nc = ~M.is_comm[None, :]
    if ex is None:
        return None, None
    if ex == "p1reb":
        return p1_extra_long(F), None
    if ex == "p1reb_placebo":
        base = p1_extra_long(F)
        rng = np.random.default_rng(rng_seed)
        out = np.zeros_like(base)
        for j in range(M.J):
            sh = int(rng.integers(20, 200) * 96)
            out[:, j] = np.roll(base[:, j], sh)
        return out, None
    turn = R["turn"][:, None]
    if ex == "turn":
        lo = np.where((turn == 1) & nc, 10, 0)
        sh = np.where((turn == -1) & nc, 10, 0)
        return lo, sh
    if ex == "rreb":
        st = R["state"][:, None]
        with np.errstate(invalid="ignore"):
            lo = ((F["rsi_min12"] < 35) & (F["r1h"] - F["rsi_min12"] >= 8) & (F["price"] > F["e20"])
                  & ((turn == 1) | (st == 1)) & nc)
            sh = ((F["rsi_max12"] > 65) & (F["rsi_max12"] - F["r1h"] >= 8) & (F["price"] < F["e20"])
                  & ((turn == -1) | (st == -1)) & nc)
        return np.where(lo, 10, 0), np.where(sh, 10, 0)
    raise ValueError(ex)


def score_variant(M: Market, spec: dict, R: dict, mode: str, seed=None):
    sl_, ss_ = M.seasonal(mode)
    el, es = build_extra(M, spec, R, seed)
    L, S, side, score, slp, ok = points(M.F, spec.get("w4", 20), el, es, sl_, ss_)
    return L, S, side, score, slp


# ------------------------------------------------------------------ riproduzione
def replay(M: Market, name: str, spec: dict, R: dict, mode: str, cost_mult: float = 1.0, thr_other: int = 70,
           seed=None, rscore=None, thr_ab: int = 60) -> dict:
    L, S, side, score, slp = rscore if rscore is not None else score_variant(M, spec, R, mode, seed)
    acc = PaperAccount(limits(cost_mult), name)
    gate = spec.get("gate")
    K = M.K
    price = M.F["price"]
    last_open: dict = {}
    ctx: dict = {}
    eq: list = []
    blocked = 0
    meta_open: dict = {}
    for k in range(K):
        t = int(M.grid[k])
        end = int(M.end[k])
        for sym in list(acc.positions):
            j = M.jmap[sym]
            i = M.IDX[k, j]
            if i >= 0:
                row = M.OHLC[j][i]
                acc.on_bar(sym, t, float(row[1]), float(row[2]), float(row[3]), float(row[4]), BAR)
        npos = len(acc.positions)
        if not (M.even30[k] or npos):
            continue                        # ciclo normale 30 min; con posizioni aperte 15 min (come il bot)
        sc_k = score[k]
        cand = np.nonzero((sc_k >= ENTRY_BASE) & (side[k] != 0) & M.valid[k])[0]
        rel = set(int(x) for x in cand)
        for s in acc.positions:
            rel.add(M.jmap[s])
        readings = []
        for j in rel:
            if not M.valid[k, j]:
                continue
            sc = int(sc_k[j])
            sl = float(slp[k, j])
            readings.append(Reading(symbol=M.syms[j], price=float(price[k, j]), side=int(side[k, j]), score=sc,
                                    long_score=int(L[k, j]), short_score=int(S[k, j]), sl_pct=sl,
                                    tp_pct=round(sl * 1.8, 5), trade_type="scalp" if sc >= 55 else "medio"))
        pr = {s: float(price[k, M.jmap[s]]) if M.valid[k, M.jmap[s]] else p.entry for s, p in acc.positions.items()}
        acc.roll_day(str(M.day[k]), pr)
        pos_info = [{"symbol": s, "side": p.side} for s, p in acc.positions.items()]
        decisions = rules_decisions(readings, pos_info, set(acc.positions), ENTRY_BASE)
        for dec in decisions:
            sym = dec["symbol"]
            j = M.jmap[sym]
            px = float(price[k, j])
            if dec["action"] == "close":
                if sym in acc.positions:
                    acc.close(sym, px, end, "chiusura regole")
                continue
            if dec["action"] not in ("open_long", "open_short"):
                continue
            sd = 1 if dec["action"] == "open_long" else -1
            if gate and sym not in COMMODITIES:
                if (sd == 1 and not R["gl"][k]) or (sd == -1 and gate == "both" and not R["gs"][k]):
                    blocked += 1
                    continue
            if end - last_open.get(sym, 0) < SCALP_COOLDOWN_MS or sym in acc.positions:
                continue
            if dec["confidence"] < (thr_ab if sym in TIER_AB else thr_other):
                continue
            sl_pct, tp_pct = dec["stop_loss_pct"], dec["take_profit_pct"]
            if sl_pct > 0 and tp_pct > 0 and tp_pct / sl_pct < 1.5:
                continue
            margin, lev, ttype = dec["margin_usd"], dec["leverage"], dec["trade_type"]
            if margin < G_MIN_MARGIN or lev < G_MIN_LEV:
                margin, lev, ttype = G_MARGIN_FORCED, G_LEV_FORCED, "scalp"
            margin = min(margin, acc.limits.max_margin_trade)
            pr2 = dict(pr)
            pr2[sym] = px
            pos, _ = acc.open(sym, sd, margin, lev, px, px * (1 - sd * sl_pct),
                              px * (1 + sd * tp_pct) if tp_pct > 0 else None, end, pr2,
                              confidence=dec["confidence"], reason="", source="rules", trade_type=ttype)
            if pos:
                last_open[sym] = end
                ctx[pos.id] = (int(R["state"][k]), int(R["turn"][k]))
        pr3 = {s: float(price[k, M.jmap[s]]) if M.valid[k, M.jmap[s]] else p.entry for s, p in acc.positions.items()}
        eq.append((end, acc.equity(pr3)))
    trades = []
    for rec in acc.closed:
        st, tu = ctx.get(rec["id"], (0, 0))
        trades.append((rec["id"], rec["symbol"], rec["side"], rec["open_ms"], rec["close_ms"], rec["net"],
                       rec["net_r"] if rec.get("net_r") is not None else 0.0, rec["why"], st, tu))
    return {"name": name, "trades": trades, "equity": eq, "blocked": blocked, "open_end": len(acc.positions)}


# ------------------------------------------------------------------ statistiche
def daily_net(trades, t0: int, ndays: int) -> np.ndarray:
    d = np.zeros(ndays)
    for tr in trades:
        k = int((tr[4] - t0) // DAY)
        if 0 <= k < ndays:
            d[k] += tr[5]
    return d


def max_dd(eq) -> float:
    peak, dd = -1e18, 0.0
    for _, e in eq:
        peak = max(peak, e)
        dd = max(dd, peak - e)
    return dd


def summarize(res: dict, t0: int, t1: int) -> dict:
    tr = res["trades"]
    n = len(tr)
    nets = np.array([x[5] for x in tr]) if n else np.zeros(0)
    rs = np.array([x[6] for x in tr]) if n else np.zeros(0)
    longs = [x for x in tr if x[2] == 1]
    shorts = [x for x in tr if x[2] == -1]
    third = (t1 - t0) / 3.0
    thirds = [round(sum(x[5] for x in tr if t0 + i * third <= x[4] < t0 + (i + 1) * third + 1), 1) for i in range(3)]
    gl = nets[nets > 0].sum() if n else 0.0
    gp = -nets[nets <= 0].sum() if n else 0.0
    return {"nome": res["name"], "trade": n, "netto": round(float(nets.sum()), 1) if n else 0.0,
            "vinc_pct": round(100 * float((nets > 0).mean()), 1) if n else 0.0,
            "R_medio": round(float(rs.mean()), 4) if n else 0.0,
            "PF": round(float(gl / gp), 3) if gp > 0 else None,
            "dd": round(max_dd(res["equity"]), 1),
            "long_n": len(longs), "long_netto": round(sum(x[5] for x in longs), 1),
            "long_R": round(float(np.mean([x[6] for x in longs])), 4) if longs else 0.0,
            "short_n": len(shorts), "short_netto": round(sum(x[5] for x in shorts), 1),
            "short_R": round(float(np.mean([x[6] for x in shorts])), 4) if shorts else 0.0,
            "terzi": thirds, "bloccate": res["blocked"]}


def block_bootstrap_delta(dv: np.ndarray, block: int = 7, n: int = 5000, seed: int = 11):
    """Prob(somma della differenza < 0) e intervallo 90% della somma, con blocchi di `block` giorni."""
    rng = np.random.default_rng(seed)
    nd = len(dv)
    if nd < 2 * block:
        return None
    nb = int(math.ceil(nd / block))
    sums = np.empty(n)
    for i in range(n):
        starts = rng.integers(0, nd - block + 1, size=nb)
        sums[i] = sum(dv[s:s + block].sum() for s in starts) * (nd / (nb * block))
    return {"p_neg": float((sums < 0).mean()), "lo90": float(np.percentile(sums, 5)),
            "hi90": float(np.percentile(sums, 95)), "media": float(sums.mean())}


def gates(base: dict, var: dict, base_tr, var_tr, t0: int, t1: int, placebo_deltas=None, cost_delta=None,
          other_mode_delta=None) -> dict:
    """Criteri G1-G9 della pre-registrazione. `placebo_deltas`: lista di Δ dei placebo; `cost_delta`: Δ con costi x1,5;
    `other_mode_delta`: Δ con l'altra stagionalita'."""
    nd = int((t1 - t0) // DAY)
    dv = daily_net(var_tr, t0, nd) - daily_net(base_tr, t0, nd)
    d_tot = var["netto"] - base["netto"]
    d_th = [v - b for v, b in zip(var["terzi"], base["terzi"])]
    ok_th = sum(1 for x in d_th if x >= 0)
    worst_ok = True
    for x, b in zip(d_th, base["terzi"]):
        if x < 0 and x < -0.25 * abs(b):
            worst_ok = False
    bs = block_bootstrap_delta(dv)
    g = {"d_tot": round(d_tot, 1), "d_terzi": [round(x, 1) for x in d_th], "bootstrap": bs}
    g["G1"] = d_tot >= 0
    g["G2"] = (ok_th >= 2) and worst_ok
    g["G3"] = bs is not None and bs["p_neg"] <= 0.25
    g["G4"] = var["short_netto"] >= base["short_netto"] - 0.05 * abs(base["short_netto"])
    g["G5"] = (0.65 * base["trade"] <= var["trade"] <= 1.35 * base["trade"])
    g["G6"] = var["dd"] <= 1.15 * base["dd"]
    if placebo_deltas:
        second = sorted(placebo_deltas, reverse=True)[1] if len(placebo_deltas) > 1 else max(placebo_deltas)
        g["G7"] = d_tot >= second
        g["placebo"] = {"max": round(max(placebo_deltas), 1), "secondo": round(second, 1),
                        "mediana": round(float(np.median(placebo_deltas)), 1)}
    else:
        g["G7"] = None
    g["G8"] = None if cost_delta is None else cost_delta >= 0
    g["G9"] = None if other_mode_delta is None else (other_mode_delta >= 0 and d_tot >= 0)
    g["d_costi_x1.5"] = None if cost_delta is None else round(cost_delta, 1)
    g["d_altra_stagionalita"] = None if other_mode_delta is None else round(other_mode_delta, 1)
    keys = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"]
    g["tutti"] = all(g[k] is True for k in keys)
    g["falliti"] = [k for k in keys if g[k] is False]
    g["non_valutati"] = [k for k in keys if g[k] is None]
    return g


def by_regime_table(res: dict) -> list:
    g = defaultdict(list)
    names = {1: "su", -1: "giu", 0: "laterale"}
    tnames = {1: "+inv.su", -1: "+inv.giu", 0: ""}
    for tr in res["trades"]:
        g[(names[tr[8]] + tnames[tr[9]], "LONG" if tr[2] == 1 else "SHORT")].append(tr)
    rows = []
    for (rgm, sd), v in sorted(g.items()):
        nets = [x[5] for x in v]
        rows.append({"regime": rgm, "lato": sd, "n": len(v), "vinc_pct": round(100 * sum(1 for x in nets if x > 0) / len(v), 0),
                     "netto": round(sum(nets), 1), "R_medio": round(float(np.mean([x[6] for x in v])), 3)})
    return rows


# ------------------------------------------------------------------ finestre, mesi, diagnostica
def window_net(trades, a: int, b: int) -> dict:
    sel = [t for t in trades if a <= t[4] < b]
    return {"n": len(sel), "netto": round(sum(t[5] for t in sel), 1),
            "long_n": sum(1 for t in sel if t[2] == 1), "short_n": sum(1 for t in sel if t[2] == -1),
            "long_netto": round(sum(t[5] for t in sel if t[2] == 1), 1),
            "short_netto": round(sum(t[5] for t in sel if t[2] == -1), 1),
            "R_medio": round(float(np.mean([t[6] for t in sel])), 3) if sel else 0.0}


def monthly_net(trades, t0: int, t1: int) -> dict:
    import calendar
    out = {}
    for t in trades:
        tm = time.gmtime(t[4] / 1000)
        key = f"{tm.tm_year}-{tm.tm_mon:02d}"
        o = out.setdefault(key, [0, 0.0])
        o[0] += 1
        o[1] += t[5]
    return {k: [v[0], round(v[1], 1)] for k, v in sorted(out.items())}


def diag_p1(M: Market, R: dict, mode: str, thr_other: int = 70) -> dict:
    """Quante volte il bonus rimbalzo di P1 cambia una decisione? (scatta, porta un long sopra soglia, ribalta il lato)."""
    sl_, ss_ = M.seasonal(mode)
    el = p1_extra_long(M.F)
    L0, S0, side0, sc0, _, ok = points(M.F, 20, None, None, sl_, ss_)
    L1, S1, side1, sc1, _, _ = points(M.F, 20, el, None, sl_, ss_)
    thr = np.where(M.is_comm[None, :] | np.array([s in TIER_AB for s in M.syms])[None, :], 60, thr_other)
    fire = (el > 0) & ok & M.even30[:, None]
    open0 = (side0 != 0) & (sc0 >= thr)
    open1 = (side1 != 0) & (sc1 >= thr)
    chg = fire & ((open0 != open1) | (side0 != side1))
    long_new = fire & (side1 == 1) & (L1 >= thr) & ~((side0 == 1) & (L0 >= thr))
    return {"scatti": int(fire.sum()), "decisioni_cambiate": int(chg.sum()), "nuovi_long_aperti": int(long_new.sum()),
            "L_base_mediano_quando_scatta": float(np.median(L0[fire])) if fire.any() else None,
            "L_base_max_quando_scatta": int(L0[fire].max()) if fire.any() else None,
            "S_base_mediano_quando_scatta": float(np.median(S0[fire])) if fire.any() else None,
            "scatti_con_long_gia_sopra_soglia": int((fire & (side0 == 1) & (L0 >= thr)).sum())}
