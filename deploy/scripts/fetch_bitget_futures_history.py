#!/usr/bin/env python3
"""Scarica storico PUBBLICO Bitget USDT-FUTURES (candele e funding) per lo studio offline. Nessuna credenziale.

Fonte: endpoint pubblici documentati
  GET /api/v2/mix/market/history-candles   (productType=USDT-FUTURES, limit 200, paginazione con endTime)
  GET /api/v2/mix/market/history-fund-rate (pageSize 100, pageNo)
Le righe sono salvate COME RICEVUTE (nessuna correzione, nessuna interpolazione, nessuna deduplica): i controlli di
integrita' si fanno dopo, con check_bitget_history(). Vengono scartate solo le candele non ancora chiuse al momento
dello scaricamento. Un manifest registra parametri, numero di richieste e SHA-256 di ogni file.

Uso: python deploy/scripts/fetch_bitget_futures_history.py --out DIR --days 580 BTCUSDT ETHUSDT SOLUSDT
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request

API = "https://api.bitget.com"
GRAN_MS = {"15m": 900_000, "1H": 3_600_000, "4H": 14_400_000}


def _get(path: str, params: dict, tries: int = 4) -> list:
    url = API + path + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "study-client"}),
                                        timeout=30) as r:
                body = json.loads(r.read())
            if body.get("code") != "00000":
                raise RuntimeError(f"risposta Bitget {body.get('code')}: {body.get('msg')}")
            return body.get("data") or []
        except Exception:                                   # rete o limite di frequenza: riprova con attesa
            if i == tries - 1:
                raise
            time.sleep(2 ** i)
    return []


def fetch_candles(symbol: str, gran: str, start_ms: int, now_ms: int, sleep: float = 0.12) -> tuple[list, int]:
    step = GRAN_MS[gran]
    rows, end, n = [], now_ms, 0
    while end > start_ms:
        page = _get("/api/v2/mix/market/history-candles",
                    {"symbol": symbol, "productType": "USDT-FUTURES", "granularity": gran, "limit": 200,
                     "endTime": end})
        n += 1
        if not page:
            break
        rows.extend(page)
        first = min(int(r[0]) for r in page)
        if first >= end:
            break
        end = first          # Bitget restituisce le candele con chiusura <= endTime: cosi' la pagina dopo finisce a first-step
        time.sleep(sleep)
    closed = [r for r in rows if int(r[0]) >= start_ms and int(r[0]) + step <= now_ms]
    closed.sort(key=lambda r: int(r[0]))                       # ordinamento stabile: i duplicati restano
    return closed, n


def fetch_funding(symbol: str, start_ms: int, sleep: float = 0.12) -> tuple[list, int]:
    rows, page_no, n = [], 1, 0
    while True:
        page = _get("/api/v2/mix/market/history-fund-rate",
                    {"symbol": symbol, "productType": "USDT-FUTURES", "pageSize": 100, "pageNo": page_no})
        n += 1
        if not page:
            break
        rows.extend(page)
        if min(int(r["fundingTime"]) for r in page) < start_ms or len(page) < 100:
            break
        page_no += 1
        time.sleep(sleep)
    out = sorted(([int(r["fundingTime"]), float(r["fundingRate"])] for r in rows if int(r["fundingTime"]) >= start_ms))
    return out, n


def _write(path: str, header: list, rows: list) -> str:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--days", type=int, default=580)
    ap.add_argument("--grans", default="15m,4H")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    now = int(time.time() * 1000)
    start = now - args.days * 86_400_000
    start -= start % GRAN_MS["4H"]
    man = {"fonte": API + " (endpoint pubblici, productType USDT-FUTURES)", "scaricato_ms": now, "inizio_ms": start,
           "giorni": args.days, "file": {}}
    for sym in args.symbols:
        for g in args.grans.split(","):
            rows, n = fetch_candles(sym, g, start, now)
            name = f"{sym}_{g}.csv"
            man["file"][name] = {"righe": len(rows), "richieste": n,
                                 "sha256": _write(os.path.join(args.out, name),
                                                  ["ts", "open", "high", "low", "close", "base_vol", "quote_vol"], rows)}
            print(name, man["file"][name], flush=True)
        rows, n = fetch_funding(sym, start)
        name = f"{sym}_funding.csv"
        man["file"][name] = {"righe": len(rows), "richieste": n,
                             "sha256": _write(os.path.join(args.out, name), ["funding_ms", "rate"], rows)}
        print(name, man["file"][name], flush=True)
    with open(os.path.join(args.out, "manifest.json"), "w") as fh:
        json.dump(man, fh, indent=1)


if __name__ == "__main__":
    main()
