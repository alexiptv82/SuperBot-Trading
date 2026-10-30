"""Dati del laboratorio: candele 15m pubbliche Bitget (nessuna chiave) oppure dati finti per provare il codice."""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

BASE = "https://api.bitget.com"
BAR = 900_000
DAY = 86_400_000
# simboli di produzione del 13/10 (`desk.cli.SYMBOLS`); MATIC puo' non avere storia: viene escluso se mancano barre
SYMBOLS = ["BTC", "ETH", "BNB", "XRP", "SOL", "ADA", "DOGE", "AVAX", "DOT", "LINK", "MATIC", "UNI", "ATOM", "LTC",
           "BCH", "APT", "ARB", "OP", "NEAR", "FIL", "INJ", "SUI", "TIA", "RUNE", "STX", "XAU", "XAG"]
WARMUP_DAYS = 12

_lock = threading.Lock()
_last = [0.0]


def _gap(min_gap: float) -> None:
    with _lock:
        wait = _last[0] + min_gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def http_json(url: str, tries: int = 7, min_gap: float = 0.09):
    wait = 1.0
    last = None
    for _ in range(tries):
        _gap(min_gap)
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
        except Exception as e:      # rete: si riprova
            last = e
            time.sleep(wait)
            wait *= 2
    raise RuntimeError(f"rete: {url[:110]} ({last})")


def fetch_symbol(sym: str, start: int, end: int) -> list:
    """Righe [ts, o, h, l, c, vol] 15m tra start e end (ms), a finestre di 200 barre."""
    full = sym if sym.endswith("USDT") else sym + "USDT"
    rows: dict = {}
    cur_end = end
    empty_streak = 0
    for _ in range(2000):
        s = max(start, cur_end - 200 * BAR)
        url = (f"{BASE}/api/v2/mix/market/history-candles?symbol={full}&productType=USDT-FUTURES"
               f"&granularity=15m&startTime={s}&endTime={cur_end}&limit=200")
        d = http_json(url)
        data = d.get("data") if isinstance(d, dict) and d.get("code") == "00000" else None
        if data:
            empty_streak = 0
            for r in data:
                rows[int(float(r[0]))] = [float(x) for x in r[:6]]
        else:
            empty_streak += 1
            if empty_streak >= 6:       # niente piu' storia prima di qui
                break
        if s <= start:
            break
        cur_end = s - 1
    return [rows[k] for k in sorted(rows)]


def load_real(days: int, cache: str, end_ms: int, symbols=None, workers: int = 5) -> dict:
    """Scarica (o legge dalla cache) i 15m degli ultimi `days` giorni piu' l'avviamento. {sim: array Nx6}."""
    symbols = symbols or SYMBOLS
    start = end_ms - (days + WARMUP_DAYS) * DAY
    os.makedirs(cache, exist_ok=True)

    def one(sym):
        path = os.path.join(cache, f"{sym}_15m.json")
        if os.path.exists(path):
            rows = json.load(open(path))
        else:
            try:
                rows = fetch_symbol(sym, start, end_ms)
            except Exception as e:
                print(f"[DATI] {sym}: {e}", flush=True)
                rows = []
            if rows:
                json.dump(rows, open(path, "w"))
        arr = np.array(rows, dtype=float) if rows else np.empty((0, 6))
        if len(arr):
            arr = arr[(arr[:, 0] + BAR <= end_ms) & (arr[:, 0] >= start)]       # solo barre chiuse
        return sym, arr

    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for sym, arr in ex.map(one, symbols):
            if len(arr) < 1500:
                print(f"[DATI] {sym}: storia insufficiente ({len(arr)} barre): escluso", flush=True)
                continue
            out[sym] = arr
            t0 = time.strftime("%Y-%m-%d", time.gmtime(arr[0, 0] / 1000))
            miss = int((arr[-1, 0] - arr[0, 0]) // BAR + 1 - len(arr))
            print(f"[DATI] {sym}: {len(arr)} barre dal {t0}, buchi {miss}", flush=True)
    return out


def synthetic(days: int, end_ms: int, n_symbols: int = 8, seed: int = 7, gaps: bool = True) -> dict:
    """Dati finti con tratti di salita, discesa e laterale comuni: serve a provare codice e test, non a misurare."""
    rng = np.random.default_rng(seed)
    n = (days + WARMUP_DAYS) * 96
    seg = np.repeat(rng.choice([-1.0, 0.0, 1.0], size=n // 700 + 2), 700)[:n] * 0.0006
    common = rng.normal(0, 0.0016, n) + seg
    names = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LINK", "XAU", "AVAX", "DOT", "LTC", "UNI"][:n_symbols]
    out = {}
    for k, sym in enumerate(names):
        r = common * (0.7 + 0.6 * rng.random()) + rng.normal(0, 0.0013, n)
        c = 100.0 * (k + 1) * np.exp(np.cumsum(r))
        o = np.concatenate([[c[0]], c[:-1]])
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.0006, n)))
        l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.0006, n)))
        t = end_ms - (n - np.arange(n)) * BAR
        a = np.column_stack([t, o, h, l, c, rng.uniform(1, 10, n)])
        a = a[a[:, 0] + BAR <= end_ms]
        if gaps:
            keep = np.ones(len(a), bool)
            for g0 in rng.integers(2000, len(a) - 50, size=3):
                keep[g0:g0 + int(rng.integers(1, 6))] = False
            a = a[keep]
        out[sym] = a
    return out
