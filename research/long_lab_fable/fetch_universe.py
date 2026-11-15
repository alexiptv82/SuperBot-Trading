#!/usr/bin/env python3
"""Scarica storico PUBBLICO Bitget USDT-FUTURES per il laboratorio LONG (nessuna credenziale, nessun ordine).

Passo 1 (--gran 1Dutc): candele giornaliere UTC di TUTTI i perpetual crypto oggi quotati (isRwa=NO), dall'inizio.
Passo 2 (--gran 4H --symbols-file F): candele 4H solo per i simboli indicati.
Righe salvate come ricevute, solo candele CHIUSE; nessuna interpolazione. Manifest con SHA-256.
Limite dichiarato: i contratti rimossi dal listino non sono scaricabili (bias di sopravvivenza, favorisce i LONG).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request

API = "https://api.bitget.com"
STEP = {"1Dutc": 86_400_000, "4H": 14_400_000, "1H": 3_600_000}
EXCLUDE_BASE = {"USDC", "FDUSD", "DAI", "TUSD", "USDE", "USDD", "PYUSD", "USD1", "PAXG", "XAUT", "EURT", "BUSD"}


def get(path: str, params: dict, tries: int = 5):
    url = API + path + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "study-client"}),
                                        timeout=30) as r:
                body = json.loads(r.read())
            if body.get("code") != "00000":
                raise RuntimeError(str(body.get("code")))
            return body.get("data") or []
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * 2 ** i)


def candles(symbol: str, gran: str, start_ms: int, now_ms: int) -> list:
    step, rows, end = STEP[gran], [], now_ms
    while end > start_ms:
        page = get("/api/v2/mix/market/history-candles",
                   {"symbol": symbol, "productType": "USDT-FUTURES", "granularity": gran, "limit": 200, "endTime": end})
        if not page:
            break
        rows.extend(page)
        first = min(int(r[0]) for r in page)
        if first >= end:
            break
        end = first                                  # Bitget: candele con chiusura <= endTime
        time.sleep(0.05)
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: int(r[0])):
        t = int(r[0])
        if t in seen or t < start_ms or t + step > now_ms:
            continue
        seen.add(t)
        out.append(r[:7])
    return out


def one(sym: str, gran: str, start: int, now: int, out: str) -> tuple:
    path = os.path.join(out, f"{sym}_{gran}.csv")
    if not os.path.exists(path):
        rows = candles(sym, gran, start, now)
        with open(path + ".tmp", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["ts", "open", "high", "low", "close", "base_vol", "quote_vol"])
            w.writerows(rows)
        os.replace(path + ".tmp", path)
    data = open(path, "rb").read()
    return sym, data.count(b"\n") - 1, hashlib.sha256(data).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--gran", default="1Dutc")
    ap.add_argument("--symbols-file")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    now = int(time.time() * 1000)
    start = int(time.mktime(time.strptime(a.start + " UTC", "%Y-%m-%d %Z")) * 1000) if False else \
        int(__import__("calendar").timegm(time.strptime(a.start, "%Y-%m-%d")) * 1000)
    if a.symbols_file:
        syms = [s.strip() for s in open(a.symbols_file) if s.strip()]
    else:
        contracts = get("/api/v2/mix/market/contracts", {"productType": "USDT-FUTURES"})
        with open(os.path.join(a.out, "contracts_snapshot.json"), "w") as fh:
            json.dump([{k: c.get(k) for k in ("symbol", "baseCoin", "isRwa", "symbolStatus", "maxLever", "fundInterval")}
                       for c in contracts], fh)
        syms = sorted(c["symbol"] for c in contracts
                      if c.get("isRwa") == "NO" and c.get("quoteCoin") == "USDT" and c.get("baseCoin") not in EXCLUDE_BASE)
    man = {"fonte": API + " history-candles USDT-FUTURES", "gran": a.gran, "scaricato_ms": now, "inizio": a.start, "file": {}}
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(one, s, a.gran, start, now, a.out): s for s in syms}
        for i, f in enumerate(cf.as_completed(futs)):
            try:
                sym, n, sha = f.result()
                man["file"][f"{sym}_{a.gran}.csv"] = {"righe": n, "sha256": sha}
            except Exception as e:
                man["file"][f"{futs[f]}_{a.gran}.csv"] = {"errore": type(e).__name__}
            if i % 50 == 0:
                print(i, "/", len(syms), flush=True)
    with open(os.path.join(a.out, f"manifest_{a.gran}.json"), "w") as fh:
        json.dump(man, fh, indent=1, sort_keys=True)
    print("fatto", len(man["file"]), "errori", sum(1 for v in man["file"].values() if "errore" in v), flush=True)


if __name__ == "__main__":
    main()
