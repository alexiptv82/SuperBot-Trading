"""Laboratorio cross-sezionale (solo ricerca): momentum/reversal market-neutral
sui perpetual liquidi di BitGet, ribilanciato ogni settimana.

Idea: invece di prevedere la direzione assoluta del prezzo, si ordina l'universo
per rendimento recente e si va long sul quintile migliore e short sul peggiore
(o il contrario), con la stessa esposizione per lato: il rialzo/ribasso generale
del mercato si annulla e le commissioni si pagano solo una volta a settimana e
solo sulle posizioni che cambiano.

Regole fissate PRIMA di guardare i risultati:
  * universo e dati: gli stessi del laboratorio ampiezza (cache);
  * ribilanciamento ogni lunedi' 00:00 UTC: segnale dalle chiusure giornaliere
    fino a domenica, ingresso all'apertura del lunedi', uscita all'apertura del
    lunedi' successivo; serve un minimo di 12 coppie valide;
  * 3 varianti: M30 (continuazione sul rendimento a 30 giorni), M7 (continuazione
    a 7 giorni), R7 (inversione a 7 giorni); quintile = max(3, 20% delle coppie);
    pesi uguali, long totale 1 e short totale 1 (dollar-neutral), nessuno stop;
  * costi: scenario A = 8 bp per lato (16 bp round trip) sul turnover REALE,
    scenario D = 15 bp per lato; funding ignorato (book neutrale: long paga,
    short riceve);
  * periodi invariati (dev 2020-23, val 2024-giu 2025, test lug 2025-9 ago 2026);
    gli ultimi 60 giorni si calcolano solo se la variante supera le soglie;
  * PASS = netto A medio >0 in dev, val e test, t settimanale del lordo >=2,5 sui
    tre periodi insieme e p-value di permutazione <=0,01 (selezione casuale).

Limiti dichiarati: solo coppie ancora quotate (bias di sopravvivenza); liquidita'
e slippage degli short su altcoin piccole potrebbero essere peggiori; nessun costo
di funding differenziale tra le coppie.
"""
from __future__ import annotations

import argparse
import json
import math
import time
import zlib
from datetime import datetime, timezone

import numpy as np

import breadth_lab as bl
import strategy_lab as sl

D1 = bl.D1
H1 = sl.H1
MIN_NAMES = 12
QUINTILE = 0.2
SIDE_COST = {"A": 8.0, "D": 15.0}
VARIANTS = {"M30": (30, +1), "M7": (7, +1), "R7": (7, -1)}
T_MIN = 2.5
P_MAX = 0.01
N_PERM = 1000


# -------------------------------------------------------------------- pannello
def build_panel(frames: dict, symbols: list):
    """Matrici (giorni x coppie) di apertura e chiusura giornaliere (NaN se mancanti)."""
    d0 = sl.DATA_START // D1
    d1 = sl.DATA_END // D1 + 1
    n_days = d1 - d0
    O = np.full((n_days, len(symbols)), np.nan)
    C = np.full((n_days, len(symbols)), np.nan)
    for j, s in enumerate(symbols):
        b = frames[s]["1d"]
        idx = (b.t // D1 - d0).astype(int)
        ok = (idx >= 0) & (idx < n_days)
        O[idx[ok], j] = b.o[ok]
        C[idx[ok], j] = b.c[ok]
    return O, C, d0


def is_monday(day_number: int) -> bool:
    return (day_number + 3) % 7 == 0       # il giorno 0 (1970-01-01) era un giovedi'


def select_weights(score: np.ndarray, avail: np.ndarray):
    """Pesi dollar-neutral: long sul quintile con score piu' alto, short sul piu' basso."""
    idx = np.flatnonzero(avail)
    if len(idx) < MIN_NAMES:
        return None
    k = max(3, int(round(QUINTILE * len(idx))))
    order = idx[np.argsort(score[idx], kind="stable")]
    w = np.zeros(len(score))
    w[order[-k:]] = 1.0 / k
    w[order[:k]] = -1.0 / k
    return w


def weekly_returns(O: np.ndarray, C: np.ndarray, d0: int, lookback: int, sign: int):
    """Una riga per lunedi': (giorno, pesi, rendimenti settimanali per coppia)."""
    rows = []
    n_days = O.shape[0]
    for d in range(lookback + 2, n_days - 8):
        if not is_monday(d0 + d):
            continue
        past, base = C[d - 1], C[d - 1 - lookback]          # solo chiusure fino a domenica
        with np.errstate(invalid="ignore", divide="ignore"):
            mom = past / base - 1.0
        avail = np.isfinite(mom) & np.isfinite(O[d])
        w = select_weights(sign * mom, avail)
        if w is None:
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            ret = O[d + 7] / O[d] - 1.0
        rows.append((d0 + d, w, ret, avail))
    return rows


def run_variant(rows: list):
    """Serie settimanali (bp su 1 di long + 1 di short): lordo, netto A/D, turnover."""
    prev = None
    out = []
    for day, w, ret, avail in rows:
        r = np.where(np.isfinite(ret), ret, 0.0)
        longs, shorts = w > 0, w < 0
        gl = float((w[longs] * r[longs]).sum() * 1e4)
        gs = float((w[shorts] * r[shorts]).sum() * 1e4)         # contributo dello short (w<0: positivo se scende)
        turnover = float(np.abs(w - (prev if prev is not None else 0.0)).sum())
        prev = w
        gross = gl + gs
        out.append({"t": int(day) * D1, "gross": gross, "long": gl, "short": gs, "turnover": turnover,
                    "A": gross - turnover * SIDE_COST["A"], "D": gross - turnover * SIDE_COST["D"],
                    "n": int(avail.sum()), "missing": int((~np.isfinite(ret) & (w != 0)).sum())})
    return out


def permutation_p(rows: list, observed_mean: float, mask: list, n_perm: int, seed: int) -> float:
    """Frazione di selezioni casuali (stessa numerosita', stessa settimana) con spread medio
    >= a quello osservato, sulle sole settimane indicate da `mask`."""
    rng = np.random.default_rng(seed)
    sel = [r for r, m in zip(rows, mask) if m]
    if not sel:
        return float("nan")
    sims = np.zeros(n_perm)
    for _, w, ret, avail in sel:
        idx = np.flatnonzero(avail)
        k = int((w > 0).sum())
        r = np.where(np.isfinite(ret), ret, 0.0)[idx]
        for p in range(n_perm):
            perm = rng.permutation(len(idx))
            sims[p] += (r[perm[:k]].mean() - r[perm[k:2 * k]].mean()) * 1e4
    sims /= len(sel)
    return float((np.sum(sims >= observed_mean) + 1) / (n_perm + 1))


# ----------------------------------------------------------------- statistiche
def period_series(series: list, name: str) -> list:
    lo, hi = sl.PERIODS[name]
    return [s for s in series if lo <= s["t"] < hi]


def summarize(series: list):
    if not series:
        return None
    g = np.array([s["gross"] for s in series])
    a = np.array([s["A"] for s in series])
    d = np.array([s["D"] for s in series])
    n = len(g)
    sd = g.std(ddof=1) if n > 1 else float("nan")
    sda = a.std(ddof=1) if n > 1 else float("nan")
    cum = np.cumsum(a)
    return {"weeks": n, "gross": float(g.mean()), "t": float(g.mean() / (sd / math.sqrt(n))) if n > 1 and sd > 0 else float("nan"),
            "A": float(a.mean()), "D": float(d.mean()),
            "sharpe_A": float(a.mean() / sda * math.sqrt(52)) if n > 1 and sda > 0 else float("nan"),
            "win": float((a > 0).mean()), "long": float(np.mean([s["long"] for s in series])),
            "short": float(np.mean([s["short"] for s in series])),
            "turnover": float(np.mean([s["turnover"] for s in series])),
            "names": float(np.mean([s["n"] for s in series])),
            "median_A": float(np.median(a)), "maxdd_A": float((np.maximum.accumulate(cum) - cum).max())}


def evaluate(per_period: dict, overall_t: float, p_value: float) -> dict:
    ps = [per_period.get(p) for p in ("dev", "val", "test")]
    checks = {"netto_A_positivo": bool(all(s is not None and s["A"] > 0 for s in ps)),
              "t_lordo": bool(overall_t == overall_t and overall_t >= T_MIN),
              "permutazione": bool(p_value == p_value and p_value <= P_MAX)}
    checks["pass"] = all(checks.values())
    return checks


def fmt(tag: str, s) -> str:
    if s is None:
        return f"{tag}: nessuna settimana"
    return (f"{tag} sett={s['weeks']} lordo={s['gross']:+.0f}bp/sett t={s['t']:+.1f} netA={s['A']:+.0f} D={s['D']:+.0f} "
            f"sharpeA={s['sharpe_A']:+.2f} win={100 * s['win']:.0f}% long/short={s['long']:+.0f}/{s['short']:+.0f} "
            f"turnover={s['turnover']:.2f} coppie={s['names']:.0f} maxDD={s['maxdd_A']:.0f}bp")


# ------------------------------------------------------------------------ main
def run(args) -> dict:
    t0 = time.time()
    universe = bl.load_universe(args.cache_dir, sl.DATA_END, args.top_n)
    raw, failed = bl.load_all(universe, args.cache_dir, sl.DATA_END, args.workers)
    frames, symbols = {}, []
    for s in universe:
        if s not in raw:
            continue
        b1h = sl.bars_from_array(raw[s])
        if len(b1h) < bl.MIN_HISTORY_BARS:
            continue
        frames[s] = {"1d": sl.aggregate(b1h, D1, H1)}
        symbols.append(s)
    if len(raw) < 0.8 * len(universe):
        raise RuntimeError("troppe coppie non scaricate: risultato non affidabile")
    O, C, d0 = build_panel(frames, symbols)
    lines: dict = {}

    def add(title, text):
        print(text, flush=True)
        lines.setdefault(title, []).append(text[:230])

    add("Dati", f"{len(symbols)} coppie, giorni={O.shape[0]}, fallite={len(failed)}")
    results, summary = {}, []
    for name, (lookback, sign) in VARIANTS.items():
        rows = weekly_returns(O, C, d0, lookback, sign)
        series = run_variant(rows)
        merged = [s for p in ("dev", "val", "test") for s in period_series(series, p)]
        per_period = {p: summarize(period_series(series, p)) for p in ("dev", "val", "test")}
        overall = summarize(merged)
        mask = [any(sl.PERIODS[p][0] <= r[0] * D1 < sl.PERIODS[p][1] for p in ("dev", "val", "test")) for r in rows]
        pval = permutation_p(rows, overall["gross"], mask, N_PERM, zlib.crc32(name.encode())) if overall else float("nan")
        checks = evaluate(per_period, overall["t"] if overall else float("nan"), pval)
        results[name] = {"checks": checks, "per_period": per_period, "overall": overall, "p": pval}
        ttl = f"Variante {name}"
        add(ttl, f"== {name} == PASS={checks['pass']} {checks} p_permutazione={pval:.3f}")
        for p in ("dev", "val", "test"):
            add(ttl, fmt(f"  {p}", per_period[p]))
        add(ttl, fmt("  TUTTI", overall))
        by_year = {}
        for s in merged:
            by_year.setdefault(datetime.fromtimestamp(s["t"] / 1000, timezone.utc).year, []).append(s["A"])
        add(ttl, "  netto A per anno (sett/media/mediana): " + " ".join(
            f"{y}:{len(v)}/{np.mean(v):+.0f}/{np.median(v):+.0f}" for y, v in sorted(by_year.items())))
        a = np.array([s["A"] for s in merged])
        if len(a) > 20:
            top = np.sort(a)[::-1][:10].sum()
            add(ttl, f"  le 10 settimane migliori = {100 * top / a.sum() if a.sum() else float('nan'):.0f}% del netto A totale; "
                     f"settimane con dati mancanti nell'uscita={sum(s['missing'] for s in merged)}")
        if checks["pass"]:
            fresh = summarize(period_series(series, "fresh"))
            results[name]["fresh"] = fresh
            add(ttl, fmt("  ULTIMI 60 GG (intoccati)", fresh))
        summary.append(f"{name}: PASS={checks['pass']} lordo={overall['gross']:+.0f}bp/sett netA={overall['A']:+.0f} "
                       f"sharpeA={overall['sharpe_A']:+.2f} t={overall['t']:+.2f} p={pval:.3f}")
    add("Riepilogo", "Soglie fissate in anticipo: netto A>0 in dev, val e test; t lordo>=2,5; p permutazione<=0,01")
    for s in summary:
        add("Riepilogo", s)
    add("Riepilogo", f"durata {time.time() - t0:.0f}s")
    with open(args.out, "w") as f:
        json.dump({"results": results, "lines": lines, "symbols": symbols}, f, indent=1, default=float)
    if args.annotate:
        for title, ls in lines.items():
            msg = "%0A".join(x.replace("%", "%25") for x in ls[:14])
            print(f"::notice title=Cross - {title}::{msg}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default="breadth_cache")
    ap.add_argument("--out", default="crosssec_results.json")
    ap.add_argument("--top-n", type=int, default=bl.TOP_N)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--annotate", action="store_true")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
