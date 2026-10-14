"""Laboratorio funding (solo ricerca): carry cross-sezionale market-neutral.

Idea: i perpetual pagano un funding periodico. Se si va short sulle coppie con il
funding piu' alto (chi e' long le paga) e long su quelle con il funding piu' basso,
si incassa un premio che non dipende dal prevedere la direzione del prezzo. Il
rischio e' che le coppie ad alto funding continuino a salire (posizioni affollate):
per questo si misura il risultato TOTALE (prezzo + funding) e lo si scompone.

Regole fissate PRIMA di guardare i risultati:
  * universo, dati di prezzo e calendario settimanale: come il laboratorio
    cross-sezionale (lunedi' 00:00 UTC, ingresso all'apertura, uscita al lunedi'
    successivo, quintile = max(3, 20%), minimo 12 coppie, dollar-neutral);
  * segnale: funding medio giornaliero dei 7 (F7) o 30 (F30) giorni precedenti,
    noto al lunedi' 00:00; long le coppie col funding piu' basso, short le piu' alto;
  * PnL: rendimento di prezzo + funding REALMENTE maturato nella settimana
    (il long paga il funding, lo short lo incassa); funding mancante = 0 (conteggiato);
  * costi: 8 bp per lato sul turnover reale (A), 15 bp (D);
  * periodi invariati (dev 2020-23, val 2024-giu 2025, test lug 2025-9 ago 2026);
    gli ultimi 60 giorni si calcolano solo se la variante supera le soglie;
  * PASS = netto A medio >0 in dev, val e test; t del lordo totale >=2,5; p-value di
    permutazione <=0,01; componente funding positiva in tutti e tre i periodi.
  * se la storia del funding non copre un periodo, il test dichiara "non testabile"
    invece di giudicare su una finestra diversa da quella fissata.

DEVIAZIONE DICHIARATA: l'API pubblica di BitGet conserva solo ~90 giorni di storico
del funding (verificato: da luglio 2026), quindi il test fissato non e' eseguibile con
i tassi di BitGet. Si usa come PROXY lo storico del funding dei perpetual USDT-M di
Binance (archivio pubblico data.binance.vision, mensile, dal 2019-09) per le coppie con
lo stesso simbolo base (anche 1000X): sia per il segnale sia per il funding maturato.
I tassi dei due exchange sono ancorati allo stesso premio sull'indice ma non uguali:
un eventuale risultato andra' riconfermato con i tassi di BitGet in avanti.

Limiti dichiarati: solo coppie ancora quotate e presenti anche su Binance; liquidita'
degli short su altcoin piccole; nessuno stop; funding BitGet reale non misurato.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import numpy as np

import breadth_lab as bl
import crosssec_lab as cs
import strategy_lab as sl

D1 = bl.D1
H1 = sl.H1
VARIANTS = {"F7": 7, "F30": 30}
MAX_PAGES = 600
PAGE = 100


# --------------------------------------------------------------------- download
def fetch_funding(symbol: str, end_ms: int, cache_dir: str, client=None) -> np.ndarray:
    """Storico dei funding (timestamp ms, tasso) dalla piu' recente alla piu' vecchia,
    con pageNo; si ferma quando una pagina non porta timestamp nuovi."""
    name = symbol.split("/")[0]
    path = os.path.join(cache_dir, f"{name}_fund_{end_ms}.npy")
    if os.path.exists(path):
        return np.load(path)
    if client is None:
        client = bl._new_client()
    got = {}
    for page in range(1, MAX_PAGES + 1):
        batch = None
        for attempt in range(5):
            try:
                batch = client.fetch_funding_rate_history(symbol, limit=PAGE, params={"pageNo": page})
                break
            except Exception:  # noqa: BLE001
                time.sleep(2 + 2 * attempt)
        if batch is None:
            raise RuntimeError(f"{symbol}: download funding fallito (pagina {page})")
        new = 0
        for r in batch:
            ts, rate = r.get("timestamp"), r.get("fundingRate")
            if ts is None or rate is None:
                continue
            if int(ts) not in got:
                new += 1
            got[int(ts)] = float(rate)
        if new == 0:
            break
        time.sleep(0.05)
    if not got:
        raise RuntimeError(f"{symbol}: nessun dato di funding")
    arr = np.array(sorted(got.items()), dtype=float)
    arr = arr[arr[:, 0] < end_ms]
    np.save(path, arr)
    return arr


def load_funding(symbols: list, cache_dir: str, end_ms: int, workers: int = 5):
    out, failed = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_funding, s, end_ms, cache_dir): s for s in symbols}
        for f in as_completed(futs):
            s = futs[f]
            try:
                out[s] = f.result()
            except Exception as exc:  # noqa: BLE001
                failed[s] = str(exc)[:100]
    return out, failed


# ------------------------------------------------- archivio pubblico (proxy)
VISION = "https://data.binance.vision/data/futures/um/monthly/fundingRate"


def vision_candidates(symbol: str) -> list:
    base = symbol.split("/")[0]
    return [f"{base}USDT", f"1000{base}USDT"]


def parse_vision_csv(text: str) -> list:
    rows = []
    for line in text.splitlines():
        parts = line.strip().split(",")
        if len(parts) < 3:
            continue
        try:
            rows.append((int(parts[0]), float(parts[2])))
        except ValueError:
            continue                                     # intestazione
    return rows


def months(start_ms: int, end_ms: int) -> list:
    d0 = datetime.fromtimestamp(start_ms / 1000, timezone.utc)
    d1 = datetime.fromtimestamp(end_ms / 1000, timezone.utc)
    out, y, m = [], d0.year, d0.month
    while (y, m) <= (d1.year, d1.month):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def http_zip(url: str):
    import io
    import urllib.request
    import zipfile
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
                return z.read(z.namelist()[0]).decode()
        except Exception as e:  # noqa: BLE001
            if getattr(e, "code", None) == 404:
                return None
            time.sleep(1 + attempt)
    raise RuntimeError(f"download fallito: {url}")


def fetch_funding_vision(symbol: str, end_ms: int, cache_dir: str, getter=http_zip) -> np.ndarray:
    name = symbol.split("/")[0]
    path = os.path.join(cache_dir, f"{name}_fundvis_{end_ms}.npy")
    if os.path.exists(path):
        return np.load(path)
    all_months = months(sl.DATA_START, end_ms - 31 * 86_400_000)      # solo mesi interi gia' chiusi
    chosen = None
    for cand in vision_candidates(symbol):
        if any(getter(f"{VISION}/{cand}/{cand}-fundingRate-{ym}.zip") is not None for ym in all_months[-3:]):
            chosen = cand
            break
    rows = []
    if chosen:
        for ym in all_months:
            text = getter(f"{VISION}/{chosen}/{chosen}-fundingRate-{ym}.zip")
            if text:
                rows.extend(parse_vision_csv(text))
    arr = np.array(sorted(set(rows)), dtype=float).reshape(-1, 2)
    arr = arr[arr[:, 0] < end_ms] if len(arr) else arr
    np.save(path, arr)
    return arr


def load_funding_vision(symbols: list, cache_dir: str, end_ms: int, workers: int = 8):
    out, failed = {}, {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_funding_vision, s, end_ms, cache_dir): s for s in symbols}
        for f in as_completed(futs):
            s = futs[f]
            try:
                arr = f.result()
                if len(arr) >= 30:
                    out[s] = arr
                else:
                    failed[s] = "assente su Binance"
            except Exception as exc:  # noqa: BLE001
                failed[s] = str(exc)[:80]
    return out, failed


def daily_funding(fund: dict, symbols: list, d0: int, n_days: int) -> np.ndarray:
    """Matrice (giorni x coppie) con la somma dei tassi di funding di ogni giorno UTC
    (NaN dove non c'e' nessun dato)."""
    F = np.full((n_days, len(symbols)), np.nan)
    for j, s in enumerate(symbols):
        arr = fund.get(s)
        if arr is None or len(arr) == 0:
            continue
        day = (arr[:, 0] // D1).astype(int) - d0
        for dd, rate in zip(day, arr[:, 1]):
            if 0 <= dd < n_days:
                F[dd, j] = rate if np.isnan(F[dd, j]) else F[dd, j] + rate
    return F


# ------------------------------------------------------------------- settimane
def funding_rows(O: np.ndarray, F: np.ndarray, d0: int, lookback: int):
    """Righe settimanali: segnale = funding medio dei `lookback` giorni precedenti (basso = long)."""
    rows = []
    n_days = O.shape[0]
    for d in range(lookback + 2, n_days - 8):
        if not cs.is_monday(d0 + d):
            continue
        win = F[d - lookback:d]                                   # solo giorni gia' chiusi
        covered = np.isfinite(win).sum(axis=0) >= max(1, int(0.8 * lookback))
        score = np.where(covered, np.nansum(win, axis=0) / lookback, np.nan)
        avail = covered & np.isfinite(O[d]) & np.isfinite(O[d + 7])
        w = cs.select_weights(-score, avail)                      # basso funding -> score alto -> long
        if w is None:
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            ret = O[d + 7] / O[d] - 1.0
        week = F[d:d + 7]
        fund_week = np.where(np.isfinite(week).any(axis=0), np.nansum(week, axis=0), np.nan)
        rows.append((d0 + d, w, ret, avail, fund_week))
    return rows


def run_funding(rows: list) -> list:
    prev, out = None, []
    for day, w, ret, avail, fw in rows:
        r = np.where(np.isfinite(ret), ret, 0.0)
        f = np.where(np.isfinite(fw), fw, 0.0)
        longs, shorts = w > 0, w < 0
        price = float((w * r).sum() * 1e4)
        fund = float(-(w * f).sum() * 1e4)                         # long (w>0) paga, short (w<0) incassa
        turnover = float(np.abs(w - (prev if prev is not None else 0.0)).sum())
        prev = w
        gross = price + fund
        out.append({"t": int(day) * D1, "price": price, "fund": fund, "gross": gross, "long": 0.0, "short": 0.0,
                    "turnover": turnover, "A": gross - turnover * cs.SIDE_COST["A"],
                    "D": gross - turnover * cs.SIDE_COST["D"], "n": int(avail.sum()),
                    "missing": int((~np.isfinite(fw) & (w != 0)).sum())})
    return out


def adjusted_rows(rows: list) -> list:
    """Righe per il test di permutazione: rendimento corretto del funding (un long
    lo paga, uno short lo incassa), cosi' la selezione casuale vale il totale."""
    out = []
    for day, w, ret, avail, fw in rows:
        f = np.where(np.isfinite(fw), fw, 0.0)
        out.append((day, w, ret - f, avail))
    return out


def evaluate(per_period: dict, overall_t: float, p_value: float) -> dict:
    ps = [per_period.get(p) for p in ("dev", "val", "test")]
    testable = all(s is not None and s["weeks"] >= 20 for s in ps)
    checks = {"testabile": bool(testable)}
    checks["netto_A_positivo"] = bool(testable and all(s["A"] > 0 for s in ps))
    checks["t_lordo"] = bool(overall_t == overall_t and overall_t >= cs.T_MIN)
    checks["permutazione"] = bool(p_value == p_value and p_value <= cs.P_MAX)
    checks["funding_positivo"] = bool(testable and all(s["fund"] > 0 for s in ps))
    checks["pass"] = all(checks.values())
    return checks


def summarize(series: list):
    s = cs.summarize(series)
    if s is None:
        return None
    s["price"] = float(np.mean([x["price"] for x in series]))
    s["fund"] = float(np.mean([x["fund"] for x in series]))
    return s


def fmt(tag: str, s) -> str:
    if s is None:
        return f"{tag}: nessuna settimana"
    return (f"{tag} sett={s['weeks']} totale={s['gross']:+.0f}bp/sett (prezzo {s['price']:+.0f} + funding {s['fund']:+.0f}) "
            f"t={s['t']:+.1f} netA={s['A']:+.0f} D={s['D']:+.0f} sharpeA={s['sharpe_A']:+.2f} win={100 * s['win']:.0f}% "
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
        raise RuntimeError("troppe coppie di prezzo non scaricate")
    O, C, d0 = cs.build_panel(frames, symbols)
    if args.source == "vision":
        fund, ffailed = load_funding_vision(symbols, args.cache_dir, sl.DATA_END, 8)
        symbols = [x for x in symbols if x in fund]                    # solo coppie con funding noto
        O, C, d0 = cs.build_panel({x: frames[x] for x in symbols}, symbols)
    else:
        fund, ffailed = load_funding(symbols, args.cache_dir, sl.DATA_END, args.workers)
    lines: dict = {}

    def add(title, text):
        print(text, flush=True)
        lines.setdefault(title, []).append(text[:230])

    add("Copertura", f"sorgente funding={args.source}; coppie con prezzi e funding: {len(symbols)}; senza funding: {len(ffailed)}"
                     + (": " + ", ".join(x.split('/')[0] for x in list(ffailed)[:12]) if ffailed else ""))
    if len(symbols) < cs.MIN_NAMES:
        raise RuntimeError("funding disponibile per troppe poche coppie")
    cov = []
    for s in symbols:
        a = fund.get(s)
        if a is None or len(a) < 3:
            cov.append(f"{s.split('/')[0]} n/d")
            continue
        gaps = np.diff(a[:, 0]) / 3.6e6
        cov.append(f"{s.split('/')[0]} {datetime.fromtimestamp(a[0, 0] / 1000, timezone.utc):%y-%m} n={len(a)} h={np.median(gaps):.0f}")
    for i in range(0, len(cov), 6):
        add("Copertura", "; ".join(cov[i:i + 6]))
    starts = [datetime.fromtimestamp(fund[s][0, 0] / 1000, timezone.utc) for s in symbols if s in fund and len(fund[s])]
    add("Copertura", f"primo funding: mediana {sorted(starts)[len(starts) // 2]:%Y-%m-%d}, piu' vecchio {min(starts):%Y-%m-%d}, "
                     f"piu' recente {max(starts):%Y-%m-%d}")
    F = daily_funding(fund, symbols, d0, O.shape[0])
    results, summary = {}, []
    for name, lookback in VARIANTS.items():
        rows = funding_rows(O, F, d0, lookback)
        series = run_funding(rows)
        merged = [s for p in ("dev", "val", "test") for s in cs.period_series(series, p)]
        per_period = {p: summarize(cs.period_series(series, p)) for p in ("dev", "val", "test")}
        overall = summarize(merged)
        ttl = f"Variante {name}"
        if overall is None:
            add(ttl, f"== {name} == nessuna settimana valida (copertura insufficiente)")
            results[name] = {"checks": {"pass": False, "testabile": False}}
            summary.append(f"{name}: non testabile")
            continue
        mask = [any(sl.PERIODS[p][0] <= r[0] * D1 < sl.PERIODS[p][1] for p in ("dev", "val", "test")) for r in rows]
        pval = cs.permutation_p(adjusted_rows(rows), overall["gross"], mask, cs.N_PERM, zlib.crc32(name.encode()))
        checks = evaluate(per_period, overall["t"], pval)
        results[name] = {"checks": checks, "per_period": per_period, "overall": overall, "p": pval}
        add(ttl, f"== {name} == PASS={checks['pass']} {checks} p_permutazione={pval:.3f}")
        for p in ("dev", "val", "test"):
            add(ttl, fmt(f"  {p}", per_period[p]))
        add(ttl, fmt("  TUTTI", overall))
        by_year = {}
        for s in merged:
            by_year.setdefault(datetime.fromtimestamp(s["t"] / 1000, timezone.utc).year, []).append(s)
        add(ttl, "  per anno (sett: totale/funding/netA): " + " ".join(
            f"{y}:{len(v)}:{np.mean([x['gross'] for x in v]):+.0f}/{np.mean([x['fund'] for x in v]):+.0f}/{np.mean([x['A'] for x in v]):+.0f}"
            for y, v in sorted(by_year.items())))
        a = np.array([x["A"] for x in merged])
        if len(a) > 20:
            top = np.sort(a)[::-1][:10].sum()
            add(ttl, f"  mediana netA={np.median(a):+.0f}bp; 10 settimane migliori = {100 * top / a.sum() if a.sum() else float('nan'):.0f}% "
                     f"del netto A totale; funding mancante in {sum(x['missing'] for x in merged)} posizioni-settimana")
        if checks["pass"]:
            fresh = summarize(cs.period_series(series, "fresh"))
            results[name]["fresh"] = fresh
            add(ttl, fmt("  ULTIMI 60 GG (intoccati)", fresh))
        summary.append(f"{name}: PASS={checks['pass']} totale={overall['gross']:+.0f} (funding {overall['fund']:+.0f}) "
                       f"netA={overall['A']:+.0f} sharpeA={overall['sharpe_A']:+.2f} t={overall['t']:+.2f} p={pval:.3f}")
    add("Riepilogo", "Soglie fissate in anticipo: netto A>0 in dev, val e test; t>=2,5; p<=0,01; funding>0 in ogni periodo")
    for s in summary:
        add("Riepilogo", s)
    add("Riepilogo", f"durata {time.time() - t0:.0f}s")
    with open(args.out, "w") as f:
        json.dump({"results": results, "lines": lines, "symbols": symbols}, f, indent=1, default=float)
    if args.annotate:
        for title, ls in lines.items():
            for i in range(0, len(ls), 14):
                msg = "%0A".join(x.replace("%", "%25") for x in ls[i:i + 14])
                suffix = f" ({i // 14 + 1})" if len(ls) > 14 else ""
                print(f"::notice title=Funding - {title}{suffix}::{msg}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default="breadth_cache")
    ap.add_argument("--out", default="funding_results.json")
    ap.add_argument("--top-n", type=int, default=bl.TOP_N)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--source", choices=("vision", "bitget"), default="vision")
    ap.add_argument("--annotate", action="store_true")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
