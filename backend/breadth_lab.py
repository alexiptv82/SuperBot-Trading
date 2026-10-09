"""Laboratorio ampiezza (solo ricerca): le regole trend-following del laboratorio
strategie, applicate alle coppie piu' liquide dei perpetual USDT di BitGet.

Perche': su BTC/ETH il trend following ha lordo positivo ma non misurabile (poche
operazioni, molta varianza). Con molte coppie il campione cresce.

Regole fissate PRIMA di guardare i risultati:
  * 3 varianti, parametri fissi: S1 Donchian 4h, S2 Donchian 1h (identiche al
    laboratorio precedente) e S6 Donchian giornaliero (ingresso: massimo dei 50
    giorni precedenti + EMA20>EMA50; stop 3 ATR; uscita sotto il minimo dei 20
    giorni; max 120 giorni).
  * universo: prime TOP_N (80) per volume 24h tra i perpetual USDT attivi, tenendo quelli con almeno
    365 giorni di storia 1h; fissato al primo run e salvato in cache.
  * periodi invariati (dev 2020-23, val 2024-giu 2025, test lug 2025-9 ago 2026);
    gli ultimi 60 giorni si calcolano solo se la variante supera tutte le soglie.
  * PASS = in dev, val e test (tutte le coppie insieme): n>=100, lordo >=20 bp,
    netto A (16 bp + funding) >0, e inoltre su tutti i periodi insieme: t
    raggruppato per mese >=2,5, lordo positivo in >=60% delle coppie (con
    >=10 operazioni) ed eccesso sul controllo a ingressi casuali >=10 bp.
Il controllo a ingressi casuali applica lo STESSO lato e le STESSE regole di
uscita a ingressi spostati a caso di 20-300 barre: misura quanto vale davvero il
momento d'ingresso rispetto al semplice trend/volatilita' del mercato.

Limiti dichiarati: solo coppie ancora quotate oggi (bias di sopravvivenza, favorisce
i long); le coppie contemporanee sono molto correlate (da qui il t per mese);
slippage da altcoin piu' alta dei 2 bp/lato assunti (scenario D = 30 bp).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

import numpy as np

import strategy_lab as sl
from strategy_lab import (Bars, ExitCfg, Sig, Strategy, H1, H4, DATA_START, DATA_END,
                          PERIODS, aggregate, atr, bars_from_array, donch_arrays, ema,
                          rolling_max, rolling_min, shift1, simulate_exit, stats, _finish)

D1 = 86_400_000
TOP_N = 80
MIN_HISTORY_BARS = 365 * 24
MIN_N_PERIOD = 100
GROSS_MIN = 20.0
CLUSTER_T_MIN = 2.5
POS_SHARE_MIN = 0.6
EXCESS_MIN = 10.0
MIN_N_SYMBOL = 10
TF_MS = {"1h": H1, "4h": H4, "1d": D1}


# ------------------------------------------------------------------ universo
def select_universe(tickers: dict, markets: dict, top_n: int = TOP_N) -> list:
    """Perpetual lineari USDT attivi, ordinati per volume 24h (quote) decrescente."""
    rows = []
    for sym, m in markets.items():
        if not (m.get("swap") and m.get("linear") and m.get("quote") == "USDT"):
            continue
        if m.get("active") is False:
            continue
        vol = (tickers.get(sym) or {}).get("quoteVolume") or 0.0
        if vol > 0:
            rows.append((float(vol), sym))
    rows.sort(reverse=True)
    return [s for _, s in rows[:top_n]]


# ------------------------------------------------------------------- download
def _new_client():
    import ccxt  # import locale: i test non richiedono ccxt
    return ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})


def _probe(client, symbol: str, since_ms: int):
    import ccxt
    for attempt in range(5):
        try:
            time.sleep(0.1)
            data = client.fetch_ohlcv(symbol, "1h", since=since_ms, limit=50)
            return int(data[0][0]) if data else None
        except (ccxt.DDoSProtection, ccxt.RateLimitExceeded, ccxt.RequestTimeout):
            time.sleep(2 + attempt * 2)
        except Exception:  # noqa: BLE001
            return None
    return None


def earliest_ts(client, symbol: str, end_ms: int) -> Optional[int]:
    """Prima barra 1h disponibile (bisezione su since, risoluzione ~1 giorno)."""
    first = _probe(client, symbol, DATA_START)
    if first is not None:
        return first
    lo, hi = DATA_START, end_ms - 2 * 86_400_000
    if _probe(client, symbol, hi) is None:
        return None
    while hi - lo > 86_400_000:
        mid = (lo + hi) // 2
        if _probe(client, symbol, mid) is not None:
            hi = mid
        else:
            lo = mid
    return _probe(client, symbol, hi)


def fetch_1h(symbol: str, end_ms: int, cache_dir: str) -> np.ndarray:
    name = symbol.split("/")[0]
    path = os.path.join(cache_dir, f"{name}_1h_{end_ms}.npy")
    if os.path.exists(path):
        return np.load(path)
    client = _new_client()
    start = earliest_ts(client, symbol, end_ms)
    if start is None:
        raise RuntimeError(f"{symbol}: nessuna storia 1h")
    since, got, empties = start, {}, 0
    while since < end_ms:
        batch = None
        for attempt in range(5):
            try:
                batch = client.fetch_ohlcv(symbol, "1h", since=since, limit=200)
                break
            except Exception:  # noqa: BLE001
                time.sleep(2 + 2 * attempt)
        if batch is None:
            raise RuntimeError(f"{symbol}: download fallito (since={since})")
        if not batch:
            empties += 1
            if empties > 30:
                break
            since += 200 * H1
            continue
        empties = 0
        for c in batch:
            if c[0] < end_ms:
                got[int(c[0])] = [float(x) for x in c[:6]]
        last = int(max(c[0] for c in batch))
        since = last + H1 if last >= since else since + 200 * H1
        time.sleep(0.05)
    arr = np.array([got[k] for k in sorted(got)], dtype=float)
    if len(arr) == 0 or arr[-1, 0] < end_ms - 3 * 86_400_000:
        raise RuntimeError(f"{symbol}: copertura incompleta; non salvo la cache")
    np.save(path, arr)
    return arr


def load_universe(cache_dir: str, end_ms: int, top_n: int) -> list:
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "universe.json")
    if os.path.exists(path):
        return json.load(open(path))
    client = _new_client()
    markets = client.load_markets()
    tickers = client.fetch_tickers()
    uni = select_universe(tickers, markets, top_n)
    json.dump(uni, open(path, "w"))
    return uni


def load_all(symbols: list, cache_dir: str, end_ms: int, workers: int = 5):
    out, failed = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_1h, s, end_ms, cache_dir): s for s in symbols}
        for i, f in enumerate(as_completed(futs), 1):
            s = futs[f]
            try:
                out[s] = f.result()
            except Exception as exc:  # noqa: BLE001
                failed[s] = str(exc)[:100]
            if i % 10 == 0:
                print(f"  ...{i}/{len(symbols)} coppie scaricate", flush=True)
    return out, failed


# ---------------------------------------------------------------- strategie
def sig_donch1d(a: dict) -> Sig:
    b = a["1d"]
    dh, dl = shift1(rolling_max(b.h, 50)), shift1(rolling_min(b.l, 50))
    e20, e50 = ema(b.c, 20), ema(b.c, 50)
    return _finish((b.c > dh) & (e20 > e50), (b.c < dl) & (e20 < e50), atr(b.h, b.l, b.c))


def breadth_strategies() -> list:
    base = {s.name: s for s in sl.STRATEGIES}
    return [base["S1_donchian_4h"], base["S2_donchian_1h"],
            Strategy("S6_donchian_1d", "1d", sig_donch1d,
                     ExitCfg(stop_mult=3.0, donch_exit=20, max_hold=120))]


def frames_from_1h(b1h: Bars) -> dict:
    return {"1h": b1h, "4h": aggregate(b1h, H4, H1), "1d": aggregate(b1h, D1, H1)}


# ----------------------------------------------------------------- statistiche
def month_key(t_ms: int) -> int:
    d = datetime.fromtimestamp(t_ms / 1000, timezone.utc)
    return d.year * 12 + d.month


def clustered_t(trades: list):
    """t sulla media mensile dei rendimenti lordi (le coppie dello stesso mese
    sono correlate: il mese e' l'unita' di campionamento)."""
    by = {}
    for t in trades:
        by.setdefault(month_key(t["t"]), []).append(t["gross"])
    m = np.array([np.mean(v) for v in by.values()])
    if len(m) < 3 or m.std(ddof=1) == 0:
        return float("nan"), len(m)
    return float(m.mean() / (m.std(ddof=1) / math.sqrt(len(m)))), len(m)


def control_trades(b: Bars, sig: Sig, cfg: ExitCfg, trades: list, tf_ms: int, seed: int) -> list:
    """Per ogni operazione reale, 3 ingressi spostati a caso (20-300 barre) con lo
    stesso lato e le stesse regole di uscita."""
    rng = np.random.default_rng(seed)
    n = len(b)
    dlow, dhigh = donch_arrays(b, cfg)
    out = []
    for tr in trades:
        for _ in range(3):
            shift = int(rng.integers(20, 301)) * (1 if rng.random() < 0.5 else -1)
            e2 = tr["e"] + shift
            if e2 < 2 or e2 >= n - 1:
                continue
            a = sig.atr[e2 - 1]
            if not np.isfinite(a) or a <= 0:
                continue
            side, p = tr["side"], b.o[e2]
            j, px, _ = simulate_exit(b, e2, side, cfg.stop_mult * a, cfg, sig,
                                     float("nan"), dlow, dhigh)
            out.append({"t": int(b.t[e2]), "side": side, "gross": side * (px / p - 1.0) * 1e4})
    return out


def evaluate_breadth(per_period: dict, overall: dict, pos_share: float, excess: float,
                     cluster_t: float) -> dict:
    ps = [per_period.get(p) for p in ("dev", "val", "test")]
    periods_ok = all(s is not None and s["n"] >= MIN_N_PERIOD and s["gross"] >= GROSS_MIN
                     and s["A"] > 0 for s in ps)
    checks = {"periodi": bool(periods_ok),
              "t_mese": bool(cluster_t == cluster_t and cluster_t >= CLUSTER_T_MIN),
              "coppie_positive": bool(pos_share >= POS_SHARE_MIN),
              "eccesso": bool(excess == excess and excess >= EXCESS_MIN)}
    checks["pass"] = all(checks.values())
    return checks


def fmt(tag: str, s: Optional[dict], extra: str = "") -> str:
    if s is None:
        return f"{tag}: nessuna operazione"
    return (f"{tag} n={s['n']} lordo={s['gross']:+.1f}bp win={100 * s['win']:.0f}% netA={s['A']:+.1f} "
            f"B={s['B']:+.1f} D={s['D']:+.1f} L/S={s['gL']:+.0f}({s['nL']})/{s['gS']:+.0f}({s['nS']})"
            f" tenuta={s['hold_h']:.0f}h{extra}")


def mean_gross(trs: list) -> float:
    return float(np.mean([t["gross"] for t in trs])) if trs else float("nan")


# ------------------------------------------------------------------------ main
def run(args) -> dict:
    t0 = time.time()
    end_ms = DATA_END
    universe = load_universe(args.cache_dir, end_ms, args.top_n)
    raw, failed = load_all(universe, args.cache_dir, end_ms, args.workers)
    lines: dict = {}

    def add(title, text):
        print(text, flush=True)
        lines.setdefault(title, []).append(text[:230])

    frames, hist = {}, {}
    for sym in universe:
        if sym not in raw:
            continue
        b1h = bars_from_array(raw[sym])
        if len(b1h) < MIN_HISTORY_BARS:
            continue
        frames[sym] = frames_from_1h(b1h)
        hist[sym] = int(b1h.t[0])
    syms = [s for s in universe if s in frames]
    add("Universo", f"richieste {len(universe)}, scaricate {len(raw)}, con >=365 giorni {len(syms)}, fallite {len(failed)}"
                    + (f": {', '.join(list(failed)[:5])}" if failed else ""))
    if len(raw) < 0.8 * len(universe):
        raise RuntimeError("troppe coppie non scaricate: risultato non affidabile")
    chunk = []
    for s in syms:
        chunk.append(f"{s.split('/')[0]} {datetime.fromtimestamp(hist[s] / 1000, timezone.utc):%y-%m}")
    for i in range(0, len(chunk), 12):
        add("Universo", ", ".join(chunk[i:i + 12]))
    top10 = set(syms[:10])
    established = {s for s in syms if hist[s] < sl.ms(2023, 1, 1)}
    add("Universo", f"top10 per volume={len(top10)} coppie; storia prima del 2023={len(established)} coppie")

    results, summary = {}, []
    for st in breadth_strategies():
        tf_ms = TF_MS[st.tf]
        per_sym, ctrl = {}, []
        for sym in syms:
            fr = frames[sym]
            base = fr[st.tf]
            if len(base) < 120:
                continue
            sig = st.build(fr)
            tr = sl.run_strategy(base, sig, st.cfg, tf_ms)
            per_sym[sym] = tr
            ctrl.extend(control_trades(base, sig, st.cfg, tr, tf_ms, zlib.crc32(f"{sym}{st.name}".encode())))
        allt = [t for tr in per_sym.values() for t in tr]
        per_period, per_period_extra = {}, {}
        for p in ("dev", "val", "test"):
            tp = sl.in_period(allt, p)
            cp = sl.in_period(ctrl, p)
            per_period[p] = stats(tp)
            ct, nm = clustered_t(tp)
            per_period_extra[p] = (ct, nm, mean_gross(cp))
        merged = [t for p in ("dev", "val", "test") for t in sl.in_period(allt, p)]
        merged_ctrl = [t for p in ("dev", "val", "test") for t in sl.in_period(ctrl, p)]
        overall = stats(merged)
        ct_all, months = clustered_t(merged)
        excess = (overall["gross"] - mean_gross(merged_ctrl)) if overall and merged_ctrl else float("nan")
        eligible = [s for s, tr in per_sym.items()
                    if len([t for t in tr if any(PERIODS[p][0] <= t["t"] < PERIODS[p][1] for p in ("dev", "val", "test"))]) >= MIN_N_SYMBOL]
        pos = [s for s in eligible
               if mean_gross([t for t in per_sym[s] if any(PERIODS[p][0] <= t["t"] < PERIODS[p][1] for p in ("dev", "val", "test"))]) > 0]
        pos_share = len(pos) / len(eligible) if eligible else 0.0
        checks = evaluate_breadth(per_period, overall, pos_share, excess, ct_all)
        results[st.name] = {"checks": checks, "per_period": per_period, "overall": overall,
                            "cluster_t_all": ct_all, "months": months, "excess": excess,
                            "pos_share": pos_share, "n_symbols": len(eligible)}
        ttl = f"Strategia {st.name}"
        add(ttl, f"== {st.name} == PASS={checks['pass']} {checks}")
        for p in ("dev", "val", "test"):
            ct, nm, cg = per_period_extra[p]
            add(ttl, fmt(f"tutte {p}", per_period[p], f" t_mese={ct:+.1f}({nm}m) casuale={cg:+.1f}"))
        add(ttl, fmt("TUTTI I PERIODI", overall, f" t_mese={ct_all:+.2f}({months}m) eccesso_su_casuale={excess:+.1f}bp "
                                                  f"coppie_positive={100 * pos_share:.0f}% di {len(eligible)}"))
        for tag, subset in (("top10", top10), ("storia>=2023", established)):
            sub = [t for s in subset if s in per_sym for t in per_sym[s]
                   if any(PERIODS[p][0] <= t["t"] < PERIODS[p][1] for p in ("dev", "val", "test"))]
            cs, nm = clustered_t(sub)
            add(ttl, fmt(f"  gruppo {tag}", stats(sub), f" t_mese={cs:+.1f}"))
        if checks["pass"]:
            fresh = stats(sl.in_period(allt, "fresh"))
            results[st.name]["fresh"] = fresh
            add(ttl, fmt("ULTIMI 60 GG (intoccati)", fresh))
        summary.append(f"{st.name}: PASS={checks['pass']} lordo={overall['gross']:+.1f}bp netA={overall['A']:+.1f} "
                       f"t_mese={ct_all:+.2f} eccesso={excess:+.1f} coppie+={100 * pos_share:.0f}%" if overall
                       else f"{st.name}: nessuna operazione")
    add("Riepilogo", "Soglie fissate in anticipo: ogni periodo n>=100, lordo>=20bp, netto A>0; t_mese>=2,5; coppie positive>=60%; eccesso>=10bp")
    for s in summary:
        add("Riepilogo", s)
    add("Riepilogo", f"durata {time.time() - t0:.0f}s")
    with open(args.out, "w") as f:
        json.dump({"results": results, "lines": lines, "universe": syms}, f, indent=1, default=float)
    if args.annotate:
        for title, ls in lines.items():
            for i in range(0, len(ls), 14):
                msg = "%0A".join(x.replace("%", "%25") for x in ls[i:i + 14])
                suffix = f" ({i // 14 + 1})" if len(ls) > 14 else ""
                print(f"::notice title=Ampiezza - {title}{suffix}::{msg}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default="breadth_cache")
    ap.add_argument("--out", default="breadth_lab_results.json")
    ap.add_argument("--top-n", type=int, default=TOP_N)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--annotate", action="store_true")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
