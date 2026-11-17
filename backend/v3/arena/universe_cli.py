"""Genera l'istantanea dell'universo comune (solo dati pubblici in lettura; nessuna chiave, nessun ordine).

Uso: python -m backend.v3.arena.universe_cli --out docs/v3/arena_universe_snapshot_AAAAMMGG.json
Non modifica le configurazioni: l'applicazione ai tre config e' un passo separato e rivisto.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

from backend.v3.arena.prepare import config_path
from backend.v3.arena.universe import build_snapshot, candle_probe
from backend.v3.brain_market.params import load_default_params
from backend.v3.brain_market.view import min_bars
from backend.v3.lab_tools.fetch_candles import http_json
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.contracts import CONTRACTS_URL

TICKERS_URL = "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"
RANKING_URL = ("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc"
               "&per_page=100&page=1")


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "superbot-arena-universe", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read(5_000_000))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--crypto-target", type=int, default=25)
    a = ap.parse_args(argv)
    now = int(time.time() * 1000)
    vp = load_default_params()
    req = {s.name: (s.candle_ms, min_bars(s, vp.indicators)) for s in vp.timeframes}
    min_lev = load_runner_config(config_path("qwen").read_bytes()).risk_policy.min_leverage
    contracts = _get(CONTRACTS_URL).get("data") or []
    ranking = _get(RANKING_URL)
    tickers = _get(TICKERS_URL).get("data") or []
    snap = build_snapshot(ranking, contracts, candle_probe(http_json, now_ms=now, requirements=req),
                          tickers=tickers, as_of_ms=now, min_leverage=min_lev, crypto_target=a.crypto_target)
    snap["feed_requirements"] = {k: {"candle_ms": v[0], "min_contiguous_bars": v[1]} for k, v in req.items()}
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    print(json.dumps({"symbols": snap["symbols"], "crypto_target_met": snap["crypto_target_met"],
                      "metals": snap["metals"]}))
    return 0 if snap["crypto_target_met"] else 2


if __name__ == "__main__":
    sys.exit(main())
