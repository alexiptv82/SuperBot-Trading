#!/usr/bin/env python3
"""RC84 Brain: compare Bitget CURRENT /candles against /history-candles.

PUBLIC HTTP GET ONLY. Does not touch services, wallet data, credentials,
orders, risk controls or the account. Uses aligned candle boundaries.
Printed metrics only: no token/account/keys or position data.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
import urllib.request
import urllib.error

BASE = "https://api.bitget.com"
METRICS = (
    ("SOLUSDT", "15m", 900_000, 3_000, 2_893),
    ("SOLUSDT", "1H", 3_600_000, 760, 733),
    ("BTCUSDT", "15m", 900_000, 3_000, 2_893),
)
WINDOW = 190                  # below Bitget's limit=200 even at inclusive boundaries
MAX_CALLS = 18               # bounded per instrument, no uncontrolled retry
INTERVAL = 0.22              # <= 5 req/sec, below documented 20 req/sec limit


def request(path: str, params: dict) -> tuple[int, str, list]:
    url = BASE + path + "?" + urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RC84-Bitget-PAPER-readonly/1.0"})
        with urllib.request.urlopen(req, timeout=12) as response:
            body = json.loads(response.read(650_000).decode("utf-8"))
            data = body.get("data") or []
            return response.status, str(body.get("code")), data if type(data) is list else []
    except urllib.error.HTTPError as exc:
        return exc.code, "HTTP_ERROR", []
    except Exception as exc:
        return 0, type(exc).__name__, []


def scan(sym, tf, step, wanted, minimum, endpoint, now_ms):
    end = now_ms // step * step       # first OPEN of forming bar
    start = end - wanted * step
    cursor = end
    rows = set()
    errors = []
    calls = 0
    for i in range(MAX_CALLS):
        if cursor <= start:
            break
        left = max(start, cursor - WINDOW * step)
        params = {
            "symbol": sym, "productType": "USDT-FUTURES", "granularity": tf,
            "startTime": left, "endTime": cursor, "limit": WINDOW,
        }
        status, code, values = request(endpoint, params)
        calls += 1
        time.sleep(INTERVAL)
        if status != 200 or code != "00000":
            errors.append({"page": i, "http": status, "code": code})
            break
        before = len(rows)
        for raw in values:
            if type(raw) not in (list, tuple) or len(raw) < 6:
                continue
            try:
                ts = int(raw[0])
                if start <= ts < end and ts % step == 0:
                    rows.add(ts)
            except (TypeError, ValueError):
                pass
        if len(rows) == before:
            errors.append({"page": i, "http": 200, "code": "NO_NEW_CANDLES"})
            break
        cursor = left + step  # overlap one bar, never skip a boundary
    last_expected = end - step
    lag = (last_expected - max(rows)) // step if rows else None
    consecutive = 0
    t = last_expected
    while t in rows:
        consecutive += 1
        t -= step
    # If latest is delayed, show the contiguous tail ending at newest actual.
    newest_tail = 0
    if rows:
        t = max(rows)
        while t in rows:
            newest_tail += 1
            t -= step
    return {
        "symbol": sym, "tf": tf, "endpoint": endpoint.split("/")[-1],
        "bars": len(rows), "consecutive_at_last_closed": consecutive,
        "newest_contiguous_tail": newest_tail,
        "latest_age_bars": lag, "minimum": minimum,
        "ready": bool(lag == 0 and consecutive >= minimum),
        "requests": calls, "errors": errors[:2],
    }


def main():
    now = int(time.time() * 1000)
    print("RC84_COMPARE_UTC=" + datetime.fromtimestamp(now / 1000, timezone.utc).isoformat(), flush=True)
    for sym, tf, step, wanted, minimum in METRICS:
        for endpoint in ("/api/v2/mix/market/history-candles", "/api/v2/mix/market/candles"):
            print("RC84_COMPARE_RESULT=" + json.dumps(
                scan(sym, tf, step, wanted, minimum, endpoint, now),
                sort_keys=True, separators=(",", ":")), flush=True)
    print("RC84_COMPARE_ONLY_PUBLIC_READS=PASS", flush=True)
    print("RC84_COMPARE_DONE=TRUE", flush=True)


if __name__ == "__main__":
    main()
