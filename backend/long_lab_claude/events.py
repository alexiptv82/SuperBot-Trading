"""Esperimento sugli eventi: il segnale di rimbalzo di P1 ha un vantaggio PROPRIO, a prescindere da come lo usa il bot?

Per ogni barra (ogni 30 minuti) di ogni simbolo si simula un long e uno short con la geometria del bot (stop 1,2xATR1h
limitato a 0,3-3,5%, TP 1,8x lo stop, massimo 48 ore, stop prima del TP nella stessa barra) e costi 16 bp a giro; il
risultato e' in R. Poi si confrontano le categorie. L'intervallo di confidenza si calcola ricampionando i GIORNI (gli
eventi dello stesso giorno sono correlati tra loro).
"""
from __future__ import annotations

import numpy as np

from labrun import DAY, Market

HOR = 192                 # 48 ore di barre 15m
COST = 0.0016             # 2 x (6 bp commissione + 2 bp scivolamento)


def _ft(H, Lo, C, i, entry, sl, side):
    tp = 1.8 * sl
    sh, sl_arr = H[i + 1:i + 1 + HOR], Lo[i + 1:i + 1 + HOR]
    if len(sh) < 8:
        return np.nan
    if side == 1:
        stop = sl_arr <= entry * (1 - sl)
        take = sh >= entry * (1 + tp)
    else:
        stop = sh >= entry * (1 + sl)
        take = sl_arr <= entry * (1 - tp)
    big = 10 ** 9
    a = int(np.argmax(stop)) if stop.any() else big
    b = int(np.argmax(take)) if take.any() else big
    if a <= b and a < big:
        g = -1.0
    elif b < big:
        g = 1.8
    else:
        g = side * (C[min(i + HOR, len(C) - 1)] / entry - 1) / sl
    return g - COST / sl


def outcomes(M: Market):
    """Matrici (K,J) del risultato in R di un long e di uno short aperti a fine barra (NaN dove non applicabile)."""
    RL = np.full((M.K, M.J), np.nan)
    RS = np.full((M.K, M.J), np.nan)
    a_pct = M.F["a_pct"]
    for j in range(M.J):
        A = M.OHLC[j]
        H, Lo, C = A[:, 2], A[:, 3], A[:, 4]
        ks = np.nonzero(M.valid[:, j] & M.even30)[0]
        for k in ks:
            i = int(M.IDX[k, j])
            entry = float(C[i])
            sl = float(min(0.035, max(0.003, 1.2 * a_pct[k, j])))
            RL[k, j] = _ft(H, Lo, C, i, entry, sl, 1)
            RS[k, j] = _ft(H, Lo, C, i, entry, sl, -1)
    return RL, RS


def categories(M: Market, R: dict) -> dict:
    F = M.F
    base = M.valid & M.even30[:, None]
    turn, st = R["turn"][:, None], R["state"][:, None]
    nc = ~M.is_comm[None, :]
    ab = np.array([s in ("BTC", "ETH", "XAU", "XAG") for s in M.syms])[None, :]
    with np.errstate(invalid="ignore"):
        os_ = base & (F["r1h"] < 35)
        p1 = os_ & (F["mom1h"] > 0.003)
        fall = os_ & ~(F["mom1h"] > 0.003)
        bear4 = F["e50_4"] < F["e200_4"]
        conf = base & (F["rsi_min12"] < 35) & (F["r1h"] - F["rsi_min12"] >= 8) & (F["price"] > F["e20"])
        confu = conf & ((turn == 1) | (st == 1)) & nc
        ob = base & (F["r1h"] > 65)
        p1s = ob & (F["mom1h"] < -0.003)
    return {
        "TUTTE le barre": base,
        "ipervenduto SENZA rimbalzo (RSI<35, mom<=0,3%)": fall,
        "P1: RSI<35 e mom1h>+0,3%": p1,
        "P1 con 4h ribassista": p1 & bear4,
        "P1 con 4h rialzista": p1 & ~bear4,
        "P1 su BTC/ETH/XAU/XAG": p1 & ab,
        "P1 su altcoin": p1 & ~ab,
        "rimbalzo confermato (RSI risalito 8 punti, sopra EMA20)": conf,
        "rimbalzo confermato + mercato su/inversione su": confu,
        "specchio: RSI>65 e mom1h<-0,3% (short)": p1s,
        "specchio + mercato giu/inversione giu": p1s & ((turn == -1) | (st == -1)) & nc,
    }


def summarize_events(M: Market, R: dict, RL, RS, boot: int = 3000, seed: int = 5) -> list:
    cats = categories(M, R)
    day_idx = (M.day - M.day[0]).astype(int)
    nd = int(day_idx.max()) + 1
    t0, t1 = int(M.grid[0]), int(M.end[-1])
    third = (t1 - t0) / 3.0
    th = np.minimum(2, ((M.end - t0) // third).astype(int))
    rng = np.random.default_rng(seed)

    def per_day(mask, Rm):
        s = np.zeros(nd)
        n = np.zeros(nd)
        v = mask & np.isfinite(Rm)
        kk, jj = np.nonzero(v)
        np.add.at(s, day_idx[kk], Rm[kk, jj])
        np.add.at(n, day_idx[kk], 1)
        return s, n

    all_s, all_n = per_day(cats["TUTTE le barre"], RL)
    out = []
    for name, mask in cats.items():
        side_is_short = name.startswith("specchio")
        Rm = RS if side_is_short else RL
        s, n = per_day(mask, Rm)
        tot_n = n.sum()
        if tot_n < 30:
            out.append({"categoria": name, "lato_simulato": "short" if side_is_short else "long", "n": int(tot_n)})
            continue
        mean = s.sum() / tot_n
        a_s, a_n = per_day(cats["TUTTE le barre"], RS if side_is_short else RL)
        ref = a_s.sum() / a_n.sum()
        diffs = np.empty(boot)
        means = np.empty(boot)
        for b in range(boot):
            pick = rng.integers(0, nd, size=nd)
            nn = n[pick].sum()
            means[b] = s[pick].sum() / nn if nn else np.nan
            diffs[b] = means[b] - a_s[pick].sum() / a_n[pick].sum()
        kk, jj = np.nonzero(mask & np.isfinite(Rm))
        win = float((Rm[kk, jj] > 0).mean())
        thirds = []
        for q in range(3):
            sel = th[kk] == q
            thirds.append(round(float(Rm[kk[sel], jj[sel]].mean()), 3) if sel.any() else None)
        out.append({"categoria": name, "lato_simulato": "short" if side_is_short else "long", "n": int(tot_n),
                    "R_medio": round(float(mean), 4), "vinc_pct": round(100 * win, 1),
                    "R_medio_tutte": round(float(ref), 4), "diff_vs_tutte": round(float(mean - ref), 4),
                    "ic90_R": [round(float(np.nanpercentile(means, 5)), 4), round(float(np.nanpercentile(means, 95)), 4)],
                    "ic90_diff": [round(float(np.nanpercentile(diffs, 5)), 4), round(float(np.nanpercentile(diffs, 95)), 4)],
                    "R_per_terzo": thirds})
    return out


def score_buckets(M: Market, RL, RS, mode_scores) -> list:
    """Il punteggio ha capacita' predittiva? R medio del long/short simulato per fascia di punteggio del lato scelto."""
    L, S, side, score = mode_scores
    ab = np.array([s in ("BTC", "ETH", "XAU", "XAG") for s in M.syms])[None, :]
    rows = []
    edges = [(60, 64), (65, 69), (70, 74), (75, 79), (80, 100)]
    base = M.valid & M.even30[:, None]
    for lab, grp in (("BTC/ETH/XAU/XAG", ab), ("altcoin", ~ab)):
        for sd, Rm in ((1, RL), (-1, RS)):
            for lo, hi in edges:
                with np.errstate(invalid="ignore"):
                    m = base & grp & (side == sd) & (score >= lo) & (score <= hi) & np.isfinite(Rm)
                n = int(m.sum())
                if n >= 30:
                    rows.append({"gruppo": lab, "lato": "long" if sd == 1 else "short", "fascia": f"{lo}-{hi}", "n": n,
                                 "R_medio": round(float(Rm[m].mean()), 3), "vinc_pct": round(100 * float((Rm[m] > 0).mean()), 1)})
    return rows
