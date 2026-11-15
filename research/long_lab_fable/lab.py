#!/usr/bin/env python3
"""Laboratorio LONG (Fable): esegue le ipotesi H1-H5 di PREREGISTRAZIONE.md su candele giornaliere reali Bitget.

Offline (legge i CSV scaricati da fetch_universe.py). Nessun parametro e' regolabile da riga di comando tranne le
sensibilita' dichiarate nella preregistrazione. Uso: python lab.py --data DIR --json out.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from functools import lru_cache

import numpy as np

DAY = 86_400_000
MIN_HISTORY, TOP_N, VOL_WIN = 90, 30, 30
FEE_SLIP_BP = {"base": 8.0, "stress": 15.0}            # per lato
FUND_BP_DAY = {"base": 3.0, "stress": 9.0}
PERIODS = (("DEV", "0000-00-00", "2023-12-31"), ("VAL", "2024-01-01", "2025-06-30"), ("TEST", "2025-07-01", "9999-99-99"))
G_SMA = 100
RS_WIN, DON_WIN, ATR_WIN, ATR_K, MAX_HOLD_H3, SLOTS = 28, 20, 20, 3.0, 30, 5
RES_WIN, BETA_WIN, MIN_DOWN = 30, 60, 8
STRESS_DD, STRESS_LOOK, STRESS_MAXAGE, RECLAIM_WIN, INVALID_WIN, MAX_HOLD_H4, PICKS_H4 = 0.10, 30, 10, 5, 10, 14, 3
N_RANDOM = 1000


# ------------------------------------------------------------------------------------------------ dati
def load_panel(data_dir: str) -> dict:
    series = {}
    for path in sorted(glob.glob(os.path.join(data_dir, "*_1Dutc.csv"))):
        sym = os.path.basename(path)[:-len("_1Dutc.csv")]
        try:
            a = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
        except Exception:
            continue
        if len(a) >= MIN_HISTORY:
            series[sym] = a
    t0 = min(int(a[0, 0]) for a in series.values())
    t1 = max(int(a[-1, 0]) for a in series.values())
    days = np.arange(t0, t1 + DAY, DAY)
    syms = sorted(series)
    shape = (len(days), len(syms))
    P = {k: np.full(shape, np.nan) for k in ("o", "h", "l", "c", "v")}
    integrity = {"simboli": len(syms), "giorni": len(days), "buchi": 0, "ohlc_invalidi": 0, "non_allineate": 0}
    for j, s in enumerate(syms):
        a = series[s]
        ts = a[:, 0].astype(np.int64)
        integrity["non_allineate"] += int(np.sum(ts % DAY != 0))
        integrity["buchi"] += int(np.sum(np.diff(ts) != DAY))
        bad = (a[:, 1:5] <= 0).any(1) | (a[:, 2] < np.maximum(a[:, 1], a[:, 4])) | (a[:, 3] > np.minimum(a[:, 1], a[:, 4]))
        integrity["ohlc_invalidi"] += int(bad.sum())
        idx = ((ts - t0) // DAY).astype(int)
        ok = ~bad & (ts % DAY == 0)
        for k, col in (("o", 1), ("h", 2), ("l", 3), ("c", 4), ("v", 6)):
            P[k][idx[ok], j] = a[ok, col]
    P.update(days=days, syms=syms, integrity=integrity,
             dates=np.array([np.datetime64(int(d), "ms").astype("datetime64[D]").astype(str) for d in days]))
    return P


def rolling(fn, x: np.ndarray, w: int) -> np.ndarray:
    """fn sulle ultime w righe (inclusa la corrente); NaN finche' la finestra non e' piena."""
    out = np.full(x.shape, np.nan)
    for i in range(w - 1, len(x)):
        out[i] = fn(x[i - w + 1:i + 1])
    return out


def build(P: dict) -> dict:
    c, h, l, v = P["c"], P["h"], P["l"], P["v"]
    n, m = c.shape
    syms = P["syms"]
    btc, eth = syms.index("BTCUSDT"), syms.index("ETHUSDT")
    hist = np.cumsum(~np.isnan(c), axis=0)
    with np.errstate(all="ignore"):
        medv = rolling(lambda w: np.nanmedian(w, axis=0), v, VOL_WIN)
    elig = np.zeros((n, m), dtype=bool)
    for i in range(n):
        ok = (hist[i] >= MIN_HISTORY) & ~np.isnan(c[i]) & ~np.isnan(medv[i])
        if ok.sum():
            order = np.argsort(-np.where(ok, medv[i], -1))
            elig[i, order[:TOP_N]] = True
            elig[i] &= ok
            for k in (btc, eth):
                elig[i, k] = bool(ok[k])
    ret = np.full((n, m), np.nan)
    ret[1:] = c[1:] / c[:-1] - 1
    rs = np.full((n, m), np.nan)
    rs[RS_WIN:] = c[RS_WIN:] / c[:-RS_WIN] - 1
    prev_c = np.vstack([np.full((1, m), np.nan), c[:-1]])
    tr = np.fmax(h - l, np.fmax(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr = rolling(lambda w: w.mean(axis=0), tr, ATR_WIN)
    don_hi = np.full((n, m), np.nan)
    don_lo = np.full((n, m), np.nan)
    for i in range(DON_WIN, n):
        don_hi[i] = h[i - DON_WIN:i].max(axis=0)
        don_lo[i] = l[i - DON_WIN:i].min(axis=0)
    cb = c[:, btc]
    gates, gate_ok = {}, {}
    for w in (50, 100, 200):
        sma = rolling(lambda x: x.mean(axis=0), cb[:, None], w)[:, 0]
        gates[w] = cb > sma                                    # False finche' la media non esiste
        gate_ok[w] = ~np.isnan(sma)
    # tenuta (H4): residuo medio nei giorni negativi di BTC
    b = ret[:, btc]
    res = np.full((n, m), np.nan)
    for i in range(BETA_WIN, n):
        rb = b[i - BETA_WIN + 1:i + 1]
        ra = ret[i - BETA_WIN + 1:i + 1]
        if np.isnan(rb).any():
            continue
        var = rb.var()
        if var <= 0:
            continue
        with np.errstate(all="ignore"):
            beta = ((ra - ra.mean(axis=0)) * (rb - rb.mean())[:, None]).mean(axis=0) / var
        wb, wa = rb[-RES_WIN:], ra[-RES_WIN:]
        down = wb < 0
        if down.sum() < MIN_DOWN:
            continue
        resid = wa[down] - beta[None, :] * wb[down][:, None]
        val = resid.mean(axis=0)
        val[np.isnan(ra).any(axis=0)] = np.nan                 # serve la finestra completa
        res[i] = val
    return dict(elig=elig, ret=ret, rs=rs, atr=atr, don_hi=don_hi, don_lo=don_lo, gates=gates, gate_ok=gate_ok, res=res, btc=btc)


def period_of(date: str) -> str:
    for name, a, b in PERIODS:
        if a <= date <= b:
            return name
    return "?"


def stats(x) -> dict:
    x = np.asarray(list(x), dtype=float)
    if len(x) == 0:
        return {"n": 0}
    eq = np.r_[0.0, np.cumsum(x)]
    wins, loss = x[x > 0].sum(), -x[x < 0].sum()
    return {"n": int(len(x)), "win": round(float((x > 0).mean()), 3), "media_pct": round(float(x.mean()) * 100, 3),
            "mediana_pct": round(float(np.median(x)) * 100, 3), "somma_pct": round(float(x.sum()) * 100, 1),
            "pf": round(float(wins / loss), 3) if loss > 0 else None,
            "dd_pct": round(float((np.maximum.accumulate(eq) - eq).max()) * 100, 1),
            "t": round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2) if len(x) > 2 and x.std() > 0 else None}


# ------------------------------------------------------------------------------------------------ H1
def h1(P, B) -> dict:
    ret, elig, dates = B["ret"], B["elig"], P["dates"]
    n = len(dates)
    uni = np.full(n, np.nan)
    for i in range(1, n):
        e = elig[i - 1] & ~np.isnan(ret[i])
        if e.sum() >= 5:
            uni[i] = ret[i, e].mean()
    out = {}
    for w, g in B["gates"].items():
        on = np.r_[False, g[:-1]]                              # stato noto alla chiusura precedente
        okg = np.r_[False, B["gate_ok"][w][:-1]]
        blk = {}
        for name, a, b in PERIODS + (("TUTTO", "0000", "9999"),):
            per = (dates >= a) & (dates <= b) & ~np.isnan(uni) & okg
            row = {}
            for lab, mask in (("G_acceso", per & on), ("G_spento", per & ~on)):
                row[lab] = {"giorni": int(mask.sum()),
                            "universo_bp_giorno": round(float(np.nanmean(uni[mask])) * 1e4, 1) if mask.sum() else None,
                            "btc_bp_giorno": round(float(np.nanmean(ret[mask, B["btc"]])) * 1e4, 1) if mask.sum() else None}
            blk[name] = row
        out[f"SMA{w}"] = blk
    return out


# ------------------------------------------------------------------------------------------------ H2 / H4a
def weekly(P, B, score: np.ndarray, gate: np.ndarray | None, rng) -> dict:
    o, elig, dates = P["o"], B["elig"], P["dates"]
    n = len(dates)
    wd = np.array([np.datetime64(d).astype("datetime64[D]").astype(int) for d in dates])
    sundays = [i for i in range(60, n - 8) if (wd[i] + 4) % 7 == 0]      # 1970-01-01 = giovedi'
    rows, prev = [], {"top": set(), "bot": set()}
    for i in sundays:
        fwd = o[i + 8] / o[i + 1] - 1
        ok = elig[i] & ~np.isnan(score[i]) & ~np.isnan(fwd)
        if ok.sum() < 12:
            continue
        if gate is not None and not gate[i]:
            prev = {"top": set(), "bot": set()}
            continue
        idx = np.flatnonzero(ok)
        order = idx[np.argsort(-score[i, idx])]
        top, bot = order[:5], order[-5:]
        turn = {k: (len(set(sel) - prev[k]) / 5.0) for k, sel in (("top", top), ("bot", bot))}
        prev = {"top": set(top), "bot": set(bot)}
        cost = lambda t: 2 * FEE_SLIP_BP["base"] / 1e4 * t + FUND_BP_DAY["base"] / 1e4 * 7  # noqa: E731
        rnd = np.array([fwd[rng.choice(idx, 5, replace=False)].mean() for _ in range(200)])
        rows.append({"d": dates[i + 1], "top": fwd[top].mean() - cost(turn["top"]), "bot": fwd[bot].mean() - cost(turn["bot"]),
                     "uni": fwd[idx].mean() - FUND_BP_DAY["base"] / 1e4 * 7, "btc": fwd[B["btc"]] - FUND_BP_DAY["base"] / 1e4 * 7,
                     "top_lordo": fwd[top].mean(), "rnd_media": rnd.mean(), "quota_rnd_battuti": float((fwd[top].mean() > rnd).mean())})
    out = {}
    for name, a, b in PERIODS + (("TUTTO", "0000", "9999"),):
        r = [x for x in rows if a <= x["d"] <= b]
        if not r:
            out[name] = {"settimane": 0}
            continue
        arr = {k: np.array([x[k] for x in r]) for k in ("top", "bot", "uni", "btc", "top_lordo", "rnd_media", "quota_rnd_battuti")}
        diff = arr["top"] - arr["uni"]
        out[name] = {"settimane": len(r), **{k + "_pct_sett": round(float(arr[k].mean()) * 100, 3) for k in ("top", "bot", "uni", "btc", "top_lordo", "rnd_media")},
                     "top_meno_uni_pct": round(float(diff.mean()) * 100, 3),
                     "t_top_meno_uni": round(float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))), 2) if len(diff) > 2 else None,
                     "top_meno_bot_pct": round(float((arr["top"] - arr["bot"]).mean()) * 100, 3),
                     "quota_casuali_battuti": round(float(arr["quota_rnd_battuti"].mean()), 3),
                     "top_settimane_positive": round(float((arr["top"] > 0).mean()), 3)}
    return out


# ------------------------------------------------------------------------------------------------ motore operazioni
class Sim:
    def __init__(self, P, B):
        self.P, self.B = P, B
        self.o, self.h, self.l, self.c = P["o"], P["h"], P["l"], P["c"]
        self.n = len(P["dates"])

    @lru_cache(maxsize=None)
    def run(self, j: int, i: int, side: int, max_hold: int, exit_rule: str, cost: str) -> tuple | None:
        """Decisione alla chiusura del giorno i, ingresso all'apertura di i+1. Ritorna (netto, giorni, motivo, mae)."""
        o, h, l, c, atr = self.o[:, j], self.h[:, j], self.l[:, j], self.c[:, j], self.B["atr"][:, j]
        if i + 1 >= self.n or np.isnan(o[i + 1]) or np.isnan(atr[i]) or np.isnan(c[i]):
            return None
        slip = 2.0 / 1e4
        entry = o[i + 1] * (1 + side * slip)
        best = c[i]
        stop = stop0 = best - side * ATR_K * atr[i]
        if side * (entry - stop) <= 0:
            return None
        cb = self.c[:, self.B["btc"]]
        gate = self.B["gates"][G_SMA]
        worst, why, px, k = entry, "tempo", None, i + 1
        for k in range(i + 1, min(self.n, i + 1 + max_hold)):
            if np.isnan(o[k]):
                px, why = c[k - 1], "dati"
                break
            worst = min(worst, l[k]) if side == 1 else max(worst, h[k])
            if (side == 1 and l[k] <= stop) or (side == -1 and h[k] >= stop):
                px, why, k = (min(stop, o[k]) if side == 1 else max(stop, o[k])), "stop", k + 1
                break
            best = max(best, c[k]) if side == 1 else min(best, c[k])
            if not np.isnan(atr[k]):
                ns = best - side * ATR_K * atr[k]
                stop = max(stop, ns) if side == 1 else min(stop, ns)
            nxt = k + 1 < self.n and not np.isnan(o[k + 1])
            if exit_rule == "gate_off" and nxt and not gate[k]:
                px, why, k = o[k + 1], "filtro", k + 1
                break
            if exit_rule == "gate_on" and nxt and gate[k]:
                px, why, k = o[k + 1], "filtro", k + 1
                break
            if exit_rule == "btc_low" and nxt and k >= INVALID_WIN and cb[k] < cb[k - INVALID_WIN:k].min():
                px, why, k = o[k + 1], "btc_minimo", k + 1
                break
        if px is None:
            last = min(self.n - 1, i + max_hold)
            px, k = (o[last + 1] if last + 1 < self.n and not np.isnan(o[last + 1]) else c[last]), last + 1
        exit_px = px * (1 - side * slip)
        days = max(1, k - (i + 1))
        fee_side = (FEE_SLIP_BP[cost] - 2.0) / 1e4          # lo slippage (2 bp/lato) e' gia' nei prezzi
        gross = side * (exit_px / entry - 1)
        fund = FUND_BP_DAY[cost] / 1e4 * days if side == 1 else 0.0
        net = gross - fee_side * (1 + exit_px / entry) - fund
        return net, days, why, side * (worst / entry - 1), gross, side * (entry - stop0) / entry

    def portfolio(self, signals, side: int, max_hold: int, exit_rule: str, slots: int = SLOTS) -> tuple[list, dict]:
        """signals: lista (i, j, priorita'). Rispetta slot e una posizione per simbolo."""
        by_day: dict[int, list] = {}
        for i, j, pr in signals:
            by_day.setdefault(i, []).append((pr, j))
        open_until: dict[int, int] = {}
        trades, skipped = [], 0
        for i in sorted(by_day):
            for j in [j for j, e in open_until.items() if e <= i + 1]:
                del open_until[j]
            for pr, j in sorted(by_day[i], reverse=True):
                if j in open_until:
                    continue
                if len(open_until) >= slots:
                    skipped += 1
                    continue
                r = self.run(j, i, side, max_hold, exit_rule, "base")
                if r is None:
                    continue
                net, days, why, mae, gross, risk = r
                rs = self.run(j, i, side, max_hold, exit_rule, "stress")
                trades.append({"i": i, "j": j, "sym": self.P["syms"][j], "d": self.P["dates"][i + 1], "net": net, "gross": gross,
                               "stress": rs[0], "days": days, "why": why, "mae": mae, "risk": risk})
                open_until[j] = i + 1 + days
        return trades, {"segnali": len(signals), "non_eseguiti_slot_pieni": skipped}


def summarize(P, trades: list, slots: int, active_mask: np.ndarray | None = None) -> dict:
    dates = P["dates"]
    out = {"tutto": stats(t["net"] for t in trades), "stress": stats(t["stress"] for t in trades),
           "lordo": stats(t["gross"] for t in trades)}
    for name, a, b in PERIODS:
        out[name] = stats(t["net"] for t in trades if a <= t["d"] <= b)
    if not trades:
        return out
    out["uscite"] = {w: sum(1 for t in trades if t["why"] == w) for w in sorted({t["why"] for t in trades})}
    out["giorni_medi"] = round(float(np.mean([t["days"] for t in trades])), 1)
    out["mae_medio_pct"] = round(float(np.mean([t["mae"] for t in trades])) * 100, 2)
    out["mae_p05_pct"] = round(float(np.percentile([t["mae"] for t in trades], 5)) * 100, 2)
    first, last = min(t["i"] for t in trades), len(dates) - 1
    span_w = (last - first + 1) / 7
    occ = np.zeros(len(dates))
    for t in trades:
        occ[t["i"] + 1:t["i"] + 1 + t["days"]] += 1
    seg = occ[first:last + 1]
    ent = sorted(t["i"] for t in trades)
    out["continuita"] = {"operazioni_a_settimana": round(len(trades) / span_w, 2),
                         "occupazione_slot_pct": round(float(seg.mean() / slots) * 100, 1),
                         "giorni_senza_posizioni_pct": round(float((seg == 0).mean()) * 100, 1),
                         "max_giorni_senza_nuovi_ingressi": int(max(np.diff(ent))) if len(ent) > 1 else None}
    if active_mask is not None:
        act = active_mask[first:last + 1]
        if act.sum():
            n_act = sum(1 for t in trades if active_mask[t["i"]])
            out["continuita"]["operazioni_a_settimana_con_filtro_acceso"] = round(n_act / (act.sum() / 7), 2)
            out["continuita"]["giorni_filtro_acceso_pct"] = round(float(act.mean()) * 100, 1)
    per_sym: dict[str, float] = {}
    for t in trades:
        per_sym[t["sym"]] = per_sym.get(t["sym"], 0.0) + t["net"]
    pos = sum(v for v in per_sym.values() if v > 0)
    best = max(per_sym.items(), key=lambda kv: kv[1])
    out["simboli"] = {"n": len(per_sym), "positivi": sum(1 for v in per_sym.values() if v > 0),
                      "migliore": best[0], "quota_migliore_su_profitti": round(best[1] / pos, 3) if pos > 0 else None}
    by_year: dict[str, list] = {}
    for t in trades:
        by_year.setdefault(t["d"][:4], []).append(t["net"])
    out["per_anno"] = {y: {"n": len(v), "somma_pct": round(sum(v) * 100, 1)} for y, v in sorted(by_year.items())}
    return out


def random_same_days(sim: Sim, P, B, trades: list, side: int, max_hold: int, exit_rule: str, rng, pool=None) -> dict:
    """Controllo: stessi giorni d'ingresso, simbolo ammesso a caso, stesse uscite e costi."""
    elig = B["elig"]
    sums, means = [], []
    cand = {i: (np.flatnonzero(elig[i]) if pool is None else pool(i)) for i in {t["i"] for t in trades}}
    for _ in range(N_RANDOM):
        nets = []
        for t in trades:
            c = cand[t["i"]]
            if len(c) == 0:
                continue
            r = sim.run(int(rng.choice(c)), t["i"], side, max_hold, exit_rule, "base")
            if r is not None:
                nets.append(r[0])
        sums.append(sum(nets))
        means.append(np.mean(nets) if nets else 0.0)
    mine = sum(t["net"] for t in trades)
    return {"media_controllo_pct": round(float(np.mean(means)) * 100, 3), "somma_controllo_mediana_pct": round(float(np.median(sums)) * 100, 1),
            "quota_controlli_battuti": round(float(np.mean([mine > s for s in sums])), 3)}


def sizing(trades: list) -> dict:
    """DESCRITTIVO (aggiunto dopo i risultati, non usato per scegliere): traduzione in USDT con rischio fisso per
    operazione. Nozionale = rischio / distanza dello stop iniziale; il risultato non dipende dalla leva."""
    if not trades:
        return {}
    tr = sorted(trades, key=lambda t: t["i"])
    risk = np.array([t["risk"] for t in tr])
    r_mult = np.array([t["net"] / t["risk"] for t in tr])
    out = {"distanza_stop_iniziale_pct": {k: round(float(np.percentile(risk, q)) * 100, 1) for k, q in (("p10", 10), ("mediana", 50), ("p90", 90))},
           "R_medio": round(float(r_mult.mean()), 3), "R_mediano": round(float(np.median(r_mult)), 3),
           "R_peggiore": round(float(r_mult.min()), 2), "R_migliore": round(float(r_mult.max()), 2),
           "quota_perdite_oltre_1R": round(float((r_mult < -1.05).mean()), 3),
           "R_medio_per_periodo": {name: round(float(np.mean([t["net"] / t["risk"] for t in tr if a <= t["d"] <= b] or [0])), 3)
                                   for name, a, b in PERIODS}}
    scen = {}
    for usd in (12, 16, 25, 30):
        pnl = usd * r_mult
        eq = np.r_[0.0, np.cumsum(pnl)]
        yearly: dict[str, float] = {}
        for t, x in zip(tr, pnl):
            yearly[t["d"][:4]] = yearly.get(t["d"][:4], 0.0) + float(x)
        scen[f"rischio_{usd}_usdt"] = {
            "nozionale_mediano": round(float(np.median(usd / risk)), 0), "nozionale_p90": round(float(np.percentile(usd / risk, 90)), 0),
            "pnl_medio_per_operazione": round(float(pnl.mean()), 2), "pnl_mediano": round(float(np.median(pnl)), 2),
            "pnl_totale": round(float(pnl.sum()), 0), "drawdown_massimo": round(float((np.maximum.accumulate(eq) - eq).max()), 0),
            "per_anno": {y: round(v, 0) for y, v in sorted(yearly.items())}}
    out["scenari"] = scen
    return out


def go(summary: dict, ctrl: dict, n_tot: int, n_per: int) -> dict:
    t = summary["tutto"]
    checks = {
        "1_numerosita": t.get("n", 0) >= n_tot and all(summary[p].get("n", 0) >= n_per for p in ("DEV", "VAL", "TEST")),
        "2_netto_positivo_in_ogni_periodo": all((summary[p].get("media_pct") or -1) > 0 for p in ("DEV", "VAL", "TEST")),
        "3_pf_almeno_1_20": (t.get("pf") or 0) >= 1.20,
        "4_batte_95pct_dei_casuali": ctrl.get("quota_controlli_battuti", 0) >= 0.95,
        "5_positivo_ai_costi_di_stress": (summary["stress"].get("media_pct") or -1) > 0,
        "6_nessun_simbolo_oltre_40pct": (summary.get("simboli", {}).get("quota_migliore_su_profitti") or 1) <= 0.40,
    }
    checks["ESITO"] = "GO_SHADOW" if all(checks.values()) else "NO-GO"
    return checks


# ------------------------------------------------------------------------------------------------ H3 / H5
def h3_signals(P, B, side: int, use_rs: bool = True, use_gate: bool = True, gate_w: int = G_SMA) -> list:
    c, elig, rs = P["c"], B["elig"], B["rs"]
    gate = B["gates"][gate_w]
    lvl = B["don_hi"] if side == 1 else B["don_lo"]
    out = []
    for i in range(max(DON_WIN, RS_WIN) + 1, len(c) - 1):
        if use_gate and (not B["gate_ok"][gate_w][i] or bool(gate[i]) != (side == 1)):
            continue
        e = elig[i] & ~np.isnan(rs[i])
        if e.sum() < 9:
            continue
        idx = np.flatnonzero(e)
        order = idx[np.argsort(-rs[i, idx])]
        third = max(3, len(order) // 3)
        allowed = set(order[:third] if side == 1 else order[-third:]) if use_rs else set(idx)
        brk = (c[i] > lvl[i]) if side == 1 else (c[i] < lvl[i])
        prev_brk = (c[i - 1] > lvl[i - 1]) if side == 1 else (c[i - 1] < lvl[i - 1])
        for j in idx:
            if j in allowed and brk[j] and not prev_brk[j]:        # prima chiusura oltre il livello
                out.append((i, int(j), float(side * rs[i, j])))
    return out


# ------------------------------------------------------------------------------------------------ H4b
def h4b_triggers(P, B) -> list:
    cb = P["c"][:, B["btc"]]
    out, armed, last_deep = [], False, -10 ** 9
    for i in range(STRESS_LOOK + 1, len(cb) - 1):
        if np.isnan(cb[i - STRESS_LOOK:i + 1]).any():
            continue
        if cb[i] <= (1 - STRESS_DD) * cb[i - STRESS_LOOK:i].max():
            armed, last_deep = True, i
        if armed and i - last_deep > STRESS_MAXAGE:
            armed = False
        if armed and i > last_deep and cb[i] > cb[i - RECLAIM_WIN:i].max():
            out.append(i)
            armed = False
    return out


def h4b(P, B, sim: Sim, rng) -> dict:
    elig, res = B["elig"], B["res"]
    trig = h4b_triggers(P, B)
    top, bot, btc_tr = [], [], []
    for i in trig:
        e = elig[i] & ~np.isnan(res[i])
        e[B["btc"]] = False
        idx = np.flatnonzero(e)
        if len(idx) < 9:
            continue
        order = idx[np.argsort(-res[i, idx])]
        for rank, j in enumerate(order[:PICKS_H4]):
            if res[i, j] > 0:
                top.append((i, int(j), -rank))
        for rank, j in enumerate(order[-PICKS_H4:]):
            bot.append((i, int(j), rank))
        btc_tr.append((i, B["btc"], 0))
    t_top, m_top = sim.portfolio(top, 1, MAX_HOLD_H4, "btc_low")
    t_bot, _ = sim.portfolio(bot, 1, MAX_HOLD_H4, "btc_low")
    t_btc, _ = sim.portfolio(btc_tr, 1, MAX_HOLD_H4, "btc_low")
    s_top = summarize(P, t_top, SLOTS)
    pool = lambda i: np.array([j for j in np.flatnonzero(elig[i] & ~np.isnan(res[i])) if j != B["btc"]])  # noqa: E731
    ctrl = random_same_days(sim, P, B, t_top, 1, MAX_HOLD_H4, "btc_low", rng, pool)
    return {"inneschi": len(trig), "date_inneschi": [P["dates"][i] for i in trig], "primi_per_tenuta": s_top, "meta": m_top,
            "ultimi_per_tenuta": summarize(P, t_bot, SLOTS), "btc_agli_inneschi": summarize(P, t_btc, SLOTS),
            "controllo_casuale": ctrl, "criteri": go(s_top, ctrl, 60, 10)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--json", required=True)
    a = ap.parse_args()
    rng = np.random.default_rng(20261115)
    P = load_panel(a.data)
    B = build(P)
    sim = Sim(P, B)
    rep = {"nota": "Storico REALE Bitget USDT-FUTURES giornaliero; regole di PREREGISTRAZIONE.md; rendimenti in % del nozionale senza leva",
           "dati": {**P["integrity"], "dal": P["dates"][0], "al": P["dates"][-1],
                    "simboli_mai_ammessi": int((~B["elig"].any(axis=0)).sum()),
                    "ammessi_per_anno": {y: int(B["elig"][[i for i, d in enumerate(P["dates"]) if d.startswith(y)]].any(axis=0).sum())
                                         for y in sorted({d[:4] for d in P["dates"]})}}}
    rep["H1_deriva"] = h1(P, B)
    rep["H2_forza_relativa"] = {"senza_filtro": weekly(P, B, B["rs"], None, rng), "con_filtro_G": weekly(P, B, B["rs"], B["gates"][G_SMA], rng)}
    rep["H4a_tenuta"] = {"senza_filtro": weekly(P, B, B["res"], None, rng), "con_filtro_G": weekly(P, B, B["res"], B["gates"][G_SMA], rng),
                         "solo_G_spento": weekly(P, B, B["res"], ~B["gates"][G_SMA] & B["gate_ok"][G_SMA], rng)}
    gate = B["gates"][G_SMA]
    h3 = {}
    for name, kw in (("H3", {}), ("senza_forza_relativa", {"use_rs": False}), ("senza_filtro", {"use_gate": False}),
                     ("sens_SMA50", {"gate_w": 50}), ("sens_SMA200", {"gate_w": 200})):
        sig = h3_signals(P, B, 1, **kw)
        exit_rule = "gate_off" if kw.get("use_gate", True) else "none"
        tr, meta = sim.portfolio(sig, 1, MAX_HOLD_H3, exit_rule)
        s = summarize(P, tr, SLOTS, gate if kw.get("use_gate", True) else None)
        blk = {"meta": meta, "risultati": s}
        if name == "H3":
            ctrl = random_same_days(sim, P, B, tr, 1, MAX_HOLD_H3, exit_rule, rng)
            blk["controllo_casuale"] = ctrl
            blk["criteri"] = go(s, ctrl, 100, 20)
            blk["dimensionamento_descrittivo"] = sizing(tr)
            for slots in (3,):
                tr3, meta3 = sim.portfolio(sig, 1, MAX_HOLD_H3, exit_rule, slots)
                blk["con_3_slot"] = {"meta": meta3, "risultati": summarize(P, tr3, slots, gate)}
        h3[name] = blk
    rep["H3_trend_dei_leader"] = h3
    sig5 = h3_signals(P, B, -1)
    tr5, meta5 = sim.portfolio(sig5, -1, MAX_HOLD_H3, "gate_on")
    s5 = summarize(P, tr5, SLOTS, ~gate)
    rep["H5_specchio_short"] = {"meta": meta5, "risultati": s5, "dimensionamento_descrittivo": sizing(tr5),
                                "controllo_casuale": random_same_days(sim, P, B, tr5, -1, MAX_HOLD_H3, "gate_on", rng)}
    rep["H4b_riconquista"] = h4b(P, B, sim, rng)
    with open(a.json, "w") as fh:
        json.dump(rep, fh, indent=1, ensure_ascii=False, default=str)
    print("ok")


if __name__ == "__main__":
    main()
