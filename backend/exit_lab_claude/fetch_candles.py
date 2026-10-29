"""Scarica da Bitget (endpoint PUBBLICI di sola lettura, nessuna chiave) le candele fini attorno alle entrate reali.

Per ogni simbolo scarica solo le finestre [apertura - 2 barre, apertura + 24h + 2 barre], unite se si
sovrappongono. Salva un file .npy per simbolo (colonne t,o,h,l,c) e meta.json con granularita' e impronta SHA256.
La granularita' 'auto' prova 1m e, se lo storico non e' disponibile per quelle date, ripiega su 5m.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

BITGET = "https://api.bitget.com"
HORIZON_MS = 24 * 3_600_000
GRAN_MS = {"1m": 60_000, "5m": 300_000}


def http_get(url: str, retries: int = 5, timeout: int = 20) -> str:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode()
        except Exception as e:                       # rete, 429, 5xx: si riprova con attesa crescente
            last = e
            time.sleep(min(8.0, 0.6 * 2 ** i))
    raise RuntimeError(f"GET fallita dopo {retries} tentativi: {url} :: {last}")


def fetch_range(symbol: str, gran: str, start_ms: int, end_ms: int, get=http_get, max_pages: int = 400) -> np.ndarray:
    """Candele [t,o,h,l,c] tra start e end, a pagine da 200, dalla piu' recente indietro (come desk/analyst.py)."""
    sym = symbol.upper()
    sym = sym if sym.endswith("USDT") else sym + "USDT"
    out: dict = {}
    end = end_ms
    for _ in range(max_pages):
        url = (f"{BITGET}/api/v2/mix/market/history-candles?symbol={sym}&productType=USDT-FUTURES"
               f"&granularity={gran}&startTime={start_ms}&endTime={end}&limit=200")
        d = json.loads(get(url))
        if d.get("code") != "00000":
            raise RuntimeError(f"risposta Bitget non valida per {sym} {gran}: {str(d)[:200]}")
        rows = d.get("data") or []
        if not rows:
            break
        got = [[float(x) for x in r[:5]] for r in rows]
        for r in got:
            out[int(r[0])] = r
        oldest = min(int(r[0]) for r in got)
        if oldest <= start_ms or len(got) < 2:
            break
        end = oldest - 1
    if not out:
        return np.zeros((0, 5))
    arr = np.array([out[k] for k in sorted(out)], dtype=float)
    return arr[(arr[:, 0] >= start_ms) & (arr[:, 0] <= end_ms)]


def merged_windows(t0s, gran_ms: int, now_ms: int):
    wins = sorted((int(t) - 2 * gran_ms, min(int(t) + HORIZON_MS + 2 * gran_ms, now_ms)) for t in t0s)
    merged = []
    for a, b in wins:
        if merged and a <= merged[-1][1] + gran_ms:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def fetch_symbol(symbol: str, gran: str, windows) -> np.ndarray:
    parts = [fetch_range(symbol, gran, a, b) for a, b in windows]
    parts = [p for p in parts if len(p)]
    if not parts:
        return np.zeros((0, 5))
    arr = np.vstack(parts)
    _, idx = np.unique(arr[:, 0], return_index=True)
    return arr[np.sort(idx)]


def probe(gran: str, t_ms: int) -> float:
    """Quota di candele attese ricevute per BTC su 2 ore a partire da t_ms (1.0 = nessun buco)."""
    gm = GRAN_MS[gran]
    arr = fetch_range("BTCUSDT", gran, t_ms, t_ms + 2 * 3_600_000)
    expected = 2 * 3_600_000 // gm
    cov = len(arr) / expected
    print(f"[probe] {gran}: {len(arr)}/{expected} candele BTC nelle prime 2h ({cov:.0%})", flush=True)
    return cov


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entries", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--granularity", default="auto", choices=["auto", "1m", "5m"])
    ap.add_argument("--workers", type=int, default=5)
    a = ap.parse_args()

    df = pd.read_csv(a.entries)
    df = df[df.entry_fill.notna() & df.entry_sl.notna() & df.entry_tp.notna()]
    now_ms = int(time.time() * 1000)
    t_min = int(df.open_ms.min())

    cands = ["1m", "5m"] if a.granularity == "auto" else [a.granularity]
    gran = None
    for g in cands:
        try:
            if probe(g, t_min) >= 0.9:
                gran = g
                break
        except Exception as e:
            print(f"[probe] {g} fallita: {e}", flush=True)
    if gran is None:
        print("ERRORE: nessuna granularita' fine disponibile per le date richieste", file=sys.stderr)
        return 2
    gm = GRAN_MS[gran]
    print(f"[fetch] granularita' scelta: {gran}", flush=True)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    by_sym = {s: g.open_ms.astype("int64").tolist() for s, g in df.groupby("symbol")}
    meta = {"granularity": gran, "symbols": {}, "fetched_at_ms": now_ms}
    h = hashlib.sha256()

    def work(sym):
        return sym, fetch_symbol(sym, gran, merged_windows(by_sym[sym], gm, now_ms))

    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = dict(ex.map(work, sorted(by_sym)))
    for sym in sorted(results):
        arr = results[sym]
        np.save(out / f"{sym}.npy", arr)
        h.update(sym.encode())
        h.update(arr.tobytes())
        meta["symbols"][sym] = {"n": int(len(arr)),
                                "first_ms": int(arr[0, 0]) if len(arr) else None,
                                "last_ms": int(arr[-1, 0]) if len(arr) else None}
        print(f"[fetch] {sym}: {len(arr)} candele", flush=True)
    meta["sha256"] = h.hexdigest()
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    print(f"[fetch] fatto. sha256 dati = {meta['sha256']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
