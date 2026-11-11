#!/usr/bin/env python3
"""RC84 — read-only exact Bitget futures metadata and candle continuity.

Run via pinned hash in Termius on Singapore if GitHub Actions stay queued.
Uses ONLY public Bitget GET endpoints; never reads credentials, stops or
changes bot processes, journals, positions, controls or wallet directories.
"""
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HOST = "https://api.bitget.com"
HEADERS = {"User-Agent": "superbot-rc84-user-diagnostic-readonly/1.0"}
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT")
SAMPLES = ("BTCUSDT", "SOLUSDT")
TFS = (("15m", 900000, 3000, 2893), ("1H", 3600000, 760, 733), ("4H", 14400000, 210, 193))


def fetch(path, params):
    url = HOST + path + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=14) as response:
            body = json.loads(response.read(900000).decode("utf-8"))
            return response.status, body.get("code"), body.get("data")
    except Exception as exc:
        return 0, type(exc).__name__, None


def output(key, value):
    print("RC84_FEED_" + key + "=" + str(value), flush=True)


def contracts():
    http, code, data = fetch("/api/v2/mix/market/contracts", {"productType": "USDT-FUTURES"})
    output("CONTRACT_HTTP", http)
    output("CONTRACT_CODE", code)
    output("CONTRACT_COUNT", len(data) if type(data) is list else -1)
    if type(data) is not list:
        return
    table = {x.get("symbol"): x for x in data if type(x) is dict and x.get("symbol") in SYMS}
    for sym in SYMS:
        item = table.get(sym, {})
        obj = {k: item.get(k) for k in ("symbolStatus", "sizeMultiplier", "minTradeUSDT", "maxLever")}
        output("CONTRACT_" + sym, json.dumps(obj, sort_keys=True))


def feed(sym, tf, step, wanted, minimum):
    now_ms = int(time.time() * 1000)
    end = now_ms // step * step
    start = end - wanted * step
    cur_end = end - 1
    rows = {}
    err = ""
    calls = 0
    while cur_end >= start and calls <= wanted // 200 + 2:
        s = max(start, cur_end - 200 * step)
        http, code, data = fetch("/api/v2/mix/market/history-candles",
                                 {"symbol": sym, "productType": "USDT-FUTURES",
                                  "granularity": tf, "startTime": s,
                                  "endTime": cur_end, "limit": 200})
        calls += 1
        if http != 200 or code != "00000" or type(data) is not list:
            err = "http_%s_code_%s" % (http, code)
            break
        seen = 0
        for row in data:
            if type(row) not in (list, tuple) or len(row) < 6:
                continue
            try:
                t = int(row[0])
                if start <= t < end and t % step == 0:
                    rows[t] = True
                    seen += 1
            except (TypeError, ValueError):
                pass
        if seen == 0:
            err = "empty_page_" + str(calls)
            break
        cur_end = s - 1
    latest = max(rows) if rows else None
    tail = 0
    pos = latest
    while pos is not None and pos in rows:
        tail += 1
        pos -= step
    latest_age = (end - step - latest) // step if latest is not None else -1
    output(sym + "_" + tf + "_SUMMARY", json.dumps({
        "count": len(rows), "contiguous_tail": tail,
        "latest_age_candles": latest_age, "required_minimum": minimum,
        "can_warmup": latest_age == 0 and tail >= minimum,
        "pages": calls, "first_error": err
    }, sort_keys=True))


def main():
    output("UTC", datetime.now(timezone.utc).isoformat())
    contracts()
    for sym in SAMPLES:
        for tf, step, bars, minimum in TFS:
            feed(sym, tf, step, bars, minimum)
    output("NO_TRADING_OR_SECRET_ACCESS", "PASS")
    output("COMPLETE", "TRUE")


if __name__ == "__main__":
    main()
