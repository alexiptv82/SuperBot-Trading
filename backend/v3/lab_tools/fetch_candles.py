"""Scarica le candele da 15 minuti PUBBLICHE dei futures USDT di Bitget (nessuna chiave) e le scrive nel formato CSV
che legge `backend.v3.lab.run`.

* Solo libreria standard. Nessun segreto, nessun ordine, nessun contatto col bot in funzione: sola lettura di dati pubblici.
* Si prendono SOLO barre chiuse (quella in formazione si scarta) e si conservano i buchi cosi' come sono: mai interpolare.
* I prezzi restano le STRINGHE restituite da Bitget (nessun passaggio da `float`).
* L'ordine delle pagine restituite non conta: le righe si raccolgono per istante di apertura, senza doppioni.
* `fetch_meta.json` accanto ai CSV riporta cosa e' stato scaricato (conteggi, buchi, impronte SHA-256, ora dello scaricamento);
  l'ora sta SOLO li', mai nel rapporto del laboratorio.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

BASE = "https://api.bitget.com"
PATH = "/api/v2/mix/market/history-candles"
HEADER = ["open_time_ms", "open", "high", "low", "close", "volume"]
_SYMBOL = re.compile(r"[A-Z0-9]{3,30}")
_NUM = re.compile(r"-?\d+(\.\d+)?([eE][+-]?\d+)?")

# Nomi di granularita' documentati da Bitget (minuti in minuscolo, ore e giorni in maiuscolo): "1H" e "4H", non "60m"/"240m".
# Fuori tabella resta il vecchio ``<n>m``. Non verificato da qui (Bitget non e' raggiungibile): prima prova sulla VPS.
_GRANULARITY = {60_000: "1m", 180_000: "3m", 300_000: "5m", 900_000: "15m", 1_800_000: "30m", 3_600_000: "1H",
                14_400_000: "4H", 21_600_000: "6H", 43_200_000: "12H", 86_400_000: "1D"}

_lock = threading.Lock()
_last = [0.0]


def http_json(url: str, tries: int = 7, min_gap: float = 0.09):
    """GET con ritardo minimo fra le richieste e nuovi tentativi (429/5xx e rete) con attesa raddoppiata."""
    wait, last = 1.0, None
    for _ in range(tries):
        with _lock:
            pause = _last[0] + min_gap - time.time()
            if pause > 0:
                time.sleep(pause)
            _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "superbot-lab/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504):
                raise
        except Exception as e:      # rete: si riprova
            last = e
        time.sleep(wait)
        wait *= 2
    raise RuntimeError(f"rete: {url[:110]} ({last})")


def _row(raw, start_ms: int, end_ms: int):
    """(ts, (open, high, low, close, volume)) come stringhe; None se la riga e' fuori intervallo o non e' una riga;
    ("invalid", ts) se e' nell'intervallo ma incoerente (non numerica, prezzi <= 0, low/high che non contengono open/close):
    una riga cosi' si scarta come se la barra mancasse (buco), mai corretta."""
    if not isinstance(raw, (list, tuple)) or len(raw) < 6:
        return None
    try:
        ts = int(float(raw[0]))
    except (TypeError, ValueError):
        return None
    vals = tuple(str(x) for x in raw[1:6])
    if not all(_NUM.fullmatch(v) for v in vals):
        return "invalid", ts
    if ts < start_ms or ts >= end_ms:
        return None
    o, h, l, c, v = (Decimal(x) for x in vals)
    if min(o, h, l, c) <= 0 or v < 0 or not (l <= o <= h and l <= c <= h):      # riga incoerente: si scarta come se mancasse
        return "invalid", ts
    return ts, vals


def fetch_rows(symbol: str, start_ms: int, end_ms: int, *, candle_ms: int,
               get_json: Callable[[str], object] = http_json, window_bars: int = 200,
               max_requests: int = 3000, empty_limit: int = 6, stats: Optional[dict] = None) -> dict:
    """{apertura_ms: (open, high, low, close, volume)} per le barre con `start_ms <= apertura < end_ms`, scorrendo a ritroso
    a finestre di `window_bars` barre. Si ferma quando la storia finisce (`empty_limit` finestre vuote di fila)."""
    if not _SYMBOL.fullmatch(symbol):
        raise ValueError("invalid_symbol")
    if candle_ms < 60_000 or candle_ms % 60_000 or end_ms <= start_ms:
        raise ValueError("invalid_window")
    gran = _GRANULARITY.get(candle_ms, f"{candle_ms // 60_000}m")
    rows: dict = {}
    cur_end, empty = end_ms - 1, 0
    for _ in range(max_requests):
        s = max(start_ms, cur_end - window_bars * candle_ms)
        url = f"{BASE}{PATH}?symbol={symbol}&productType=USDT-FUTURES&granularity={gran}&startTime={s}&endTime={cur_end}&limit={window_bars}"
        d = get_json(url)
        data = d.get("data") if isinstance(d, dict) and d.get("code") == "00000" else None
        got = 0
        for raw in data or ():
            r = _row(raw, start_ms, end_ms)
            if r is None:
                continue
            if r[0] == "invalid":
                if stats is not None:
                    stats.setdefault("invalid_ts", set()).add(r[1])
                continue
            rows[r[0]] = r[1]
            got += 1
        empty = 0 if got else empty + 1
        if empty >= empty_limit or s <= start_ms:
            break
        cur_end = s - 1
    else:
        raise RuntimeError("troppe richieste")

    # RC84: Bitget requires endTime aligned to the timeframe. The historical
    # backwards paginator above uses end_ms - 1 to avoid including the live
    # candle, but Bitget may FLOOR that to the preceding boundary, excluding
    # the LAST CLOSED bar as well. Strict freshness (max_age_candles=1)
    # correctly rejects that stale view and Brain never reaches DeepSeek.
    # Recover exactly the latest CLOSED bar with aligned start/end boundaries.
    # Keep the original history, its gaps and all existing price validation.
    # If the exchange has not published the bar, remain fail-closed (stale).
    if (end_ms % candle_ms == 0 and end_ms - candle_ms >= start_ms
            and end_ms - candle_ms not in rows):
        recent_start = end_ms - 2 * candle_ms
        recent_url = (f"{BASE}{PATH}?symbol={symbol}&productType=USDT-FUTURES"
                      f"&granularity={gran}&startTime={recent_start}"
                      f"&endTime={end_ms}&limit=2")
        try:
            response = get_json(recent_url)
            recent_data = (response.get("data")
                           if isinstance(response, dict) and response.get("code") == "00000" else ())
            for raw in recent_data or ():
                parsed = _row(raw, start_ms, end_ms)
                if parsed is None:
                    continue
                if parsed[0] == "invalid":
                    if stats is not None:
                        stats.setdefault("invalid_ts", set()).add(parsed[1])
                    continue
                if parsed[0] == end_ms - candle_ms:
                    rows[parsed[0]] = parsed[1]
        except Exception:
            # Supplementary public GET is best effort; no synthetic price,
            # no lowered freshness tolerance, and retry on a later cycle.
            pass
    return rows


def write_csv(path: Path, rows: dict) -> str:
    """Scrive il CSV (intestazione esatta, righe in ordine di tempo). Restituisce l'impronta SHA-256 del file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(HEADER)
        for ts in sorted(rows):
            w.writerow([ts, *rows[ts]])
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None, *, now_ms: Optional[int] = None, get_json: Callable[[str], object] = http_json) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", required=True, help="es. BTCUSDT,ETHUSDT")
    ap.add_argument("--days", type=int, required=True)
    ap.add_argument("--candle-ms", type=int, default=900_000)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--min-fraction", type=float, default=0.8, help="sotto questa quota di barre attese: errore")
    a = ap.parse_args(argv)
    now = int(time.time() * 1000) if now_ms is None else now_ms
    end = (now // a.candle_ms) * a.candle_ms                      # la barra in formazione (apertura == end) e' esclusa
    start = end - a.days * 86_400_000
    expected = a.days * 86_400_000 // a.candle_ms
    out, meta, ok = Path(a.out_dir), {}, True
    for sym in [s.strip() for s in a.symbols.split(",") if s.strip()]:
        stats: dict = {}
        rows = fetch_rows(sym, start, end, candle_ms=a.candle_ms, get_json=get_json, stats=stats)
        bad = sorted(stats.get("invalid_ts", set()) - set(rows))
        ts = sorted(rows)
        n = len(ts)
        missing = (ts[-1] - ts[0]) // a.candle_ms + 1 - n if n else 0
        sha = write_csv(out / f"{sym}_{a.candle_ms // 60_000}m.csv", rows) if n else None
        meta[sym] = dict(n_bars=n, expected_bars=expected, first_open_ms=ts[0] if n else None, last_open_ms=ts[-1] if n else None,
                         n_missing_bars=missing, n_invalid_rows_dropped=len(bad), invalid_rows_open_ms=bad[:50], sha256=sha)
        print(f"{sym}: {n}/{expected} barre, buchi {missing}, righe incoerenti scartate {len(bad)}", flush=True)
        ok = ok and n >= a.min_fraction * expected
    meta["_run"] = dict(end_ms=end, start_ms=start, days=a.days, candle_ms=a.candle_ms,
                        fetched_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now / 1000)))
    out.mkdir(parents=True, exist_ok=True)
    (out / "fetch_meta.json").write_text(json.dumps(meta, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
