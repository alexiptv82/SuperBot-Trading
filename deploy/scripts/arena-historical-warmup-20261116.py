#!/usr/bin/env python3
"""Bitget public historical-warmup diagnostic for BTC, with immutable snapshot.

No API keys, no OpenRouter, no paper/live orders, no trading journal, and no
service or wallet changes. --selftest is fully offline. --sample performs at
most 25 public GET requests across historical 1m/15m/1H/4H intervals.
Every frame uses the actual bundled Brain V3 params for minimum warmup.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import re
import ssl
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
from backend.v3.arena.frozen_market import FRAME_MS, freeze_market_batch
from backend.v3.brain_market.params import load_default_params
from backend.v3.brain_market.view import min_bars

ROOT = "https://api.bitget.com"
PATH = "/api/v2/mix/market/history-candles"
SYMBOL = "BTCUSDT"  # intentional: one sample before a wider 25-market trial
PAGE = 190   # <200 provider maximum; 10 spare for rounded endpoints
MAX_REQUESTS = 25
MAX_BYTES = 160_000
MAX_HISTORY = 6000
SAFE_SYMBOL = re.compile(r"[A-Z0-9]{2,20}USDT\Z")


def requirements() -> dict[str, int]:
    p = load_default_params()
    req = {"1m": 60}
    for spec in p.timeframes:
        if spec.name not in FRAME_MS or spec.name in req:
            raise ValueError("UNSUPPORTED_BRAIN_TIMEFRAME")
        req[spec.name] = min_bars(spec, p.indicators)
    if set(req) != set(FRAME_MS) or any(n > MAX_HISTORY for n in req.values()):
        raise ValueError("UNSUPPORTED_BRAIN_HISTORY_REQUIREMENTS")
    return req


def _public_get(symbol: str, frame: str, first: int, last: int) -> list:
    if (type(symbol) is not str or not SAFE_SYMBOL.fullmatch(symbol)
            or frame not in FRAME_MS or last < first):
        raise ValueError("INVALID_PUBLIC_GET_SCOPE")
    step = FRAME_MS[frame]
    # Endpoints can round startTime/endTime. We include one extra period on
    # both ends but filter to [first,last] and require each expected stamp.
    url = ROOT + PATH + "?" + urlencode({
        "symbol": symbol, "productType": "USDT-FUTURES",
        "granularity": "1H" if frame == "1h" else "4H" if frame == "4h" else frame,
        "startTime": str(first - step), "endTime": str(last + step),
        "limit": "200",
    })
    request = Request(url, method="GET", headers={
        "Accept": "application/json", "User-Agent": "SuperBotArenaHistoryResearch/1.0"})
    try:
        with urlopen(request, timeout=15, context=ssl.create_default_context()) as response:
            if response.geturl().split("?",1)[0] != ROOT + PATH:
                raise ValueError("REDIRECT_NOT_ALLOWED")
            blob = response.read(MAX_BYTES + 1)
    except HTTPError as exc:
        raise ValueError("HTTP_" + str(exc.code)) from None
    except (URLError, TimeoutError, OSError):
        raise ValueError("NETWORK_FAILURE") from None
    if len(blob) > MAX_BYTES:
        raise ValueError("OVERSIZED_RESPONSE")
    try:
        result = json.loads(blob)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("INVALID_RESPONSE_JSON") from None
    if (type(result) is not dict or result.get("code") != "00000"
            or type(result.get("data")) is not list
            or len(result["data"]) > 200):
        raise ValueError("INVALID_HISTORY_RESPONSE")
    return result["data"]


def _fetch_frame(
    frame: str, required: int, asof_ms: int,
    get: Callable[[str, str, int, int], list], *, symbol: str = SYMBOL
) -> tuple[list[list], int]:
    if (frame not in FRAME_MS or type(required) is not int
            or not 1 <= required <= MAX_HISTORY or type(symbol) is not str
            or not SAFE_SYMBOL.fullmatch(symbol)):
        raise ValueError("INVALID_FETCH_SCOPE")
    step = FRAME_MS[frame]
    last_closed = asof_ms // step * step - step
    first_needed = last_closed - (required - 1) * step
    collected: dict[int, list] = {}
    pages = 0
    for offset in range(0, required, PAGE):
        first = first_needed + offset * step
        last = min(last_closed, first + (PAGE - 1) * step)
        rows = get(symbol, frame, first, last)
        pages += 1
        if type(rows) is not list or len(rows) > 200:
            raise ValueError("INVALID_PAGE")
        matched = set()
        for raw in rows:
            if type(raw) is not list or len(raw) < 7 or type(raw[0]) not in (str, int):
                raise ValueError("INVALID_HISTORY_ROW")
            try:
                t = int(raw[0])
            except ValueError:
                raise ValueError("INVALID_HISTORY_TIMESTAMP") from None
            if first <= t <= last:
                if t in matched or t in collected:
                    raise ValueError("OVERLAPPING_DUPLICATE_CANDLE")
                matched.add(t)
                collected[t] = raw
        if len(matched) != (last - first)//step + 1:
            raise ValueError("INCOMPLETE_HISTORY_PAGE")
    return [collected[t] for t in sorted(collected)], pages


def _sample(get: Callable[[str, str, int, int], list], asof_ms: int, *,
            symbol: str = SYMBOL) -> tuple[str, dict, int]:
    wanted = requirements()
    dataset = {}
    calls = 0
    for frame in FRAME_MS:
        rows, n = _fetch_frame(frame, wanted[frame], asof_ms, get, symbol=symbol)
        dataset[frame] = rows
        calls += n
    if calls > MAX_REQUESTS:
        raise ValueError("PUBLIC_REQUEST_BUDGET_EXCEEDED")
    frozen = freeze_market_batch(
        {symbol: dataset}, wanted, asof_ms=asof_ms,
        source_id="bitget.v2.history-candles")
    return frozen.sha256_hex, wanted, calls


def selftest() -> int:
    # A deterministic fake public endpoint with narrow, overlapping returns.
    asof_ms = 1795000000000
    tally = []
    def fake_get(symbol, frame, first, last):
        assert symbol == SYMBOL
        assert frame in FRAME_MS
        tally.append((frame, first, last))
        step = FRAME_MS[frame]
        output = [
            [str(t), "100", "102", "98", "101", "8", "800"]
            for t in range(first-step, last+2*step, step)
        ]
        return list(reversed(output))
    digest, wanted, calls = _sample(fake_get, asof_ms)
    assert len(digest) == 64
    assert wanted["15m"] == 2893
    assert wanted["1h"] == 733
    assert wanted["4h"] == 193
    assert wanted["1m"] == 60
    assert calls == len(tally) and calls <= MAX_REQUESTS
    # An empty page is an error, never silently padded with synthetic bars.
    try:
        _sample(lambda _s, _f, _a, _b: [], asof_ms)
    except ValueError as exc:
        assert str(exc) == "INCOMPLETE_HISTORY_PAGE"
    else:
        raise AssertionError("empty page accepted")
    # Provider may return endpoints outside interval, but must not supply
    # different/duplicate rows inside the requested interval.
    try:
        _sample(lambda symbol, frame, first, last: [
            *fake_get(symbol, frame, first, last),
            [str(first), "100", "102", "98", "101", "8", "800"],
        ], asof_ms)
    except ValueError as exc:
        assert str(exc) == "OVERLAPPING_DUPLICATE_CANDLE"
    else:
        raise AssertionError("duplicate page accepted")
    print("ARENA_HISTORY SELFTEST=PASS_OFFLINE")
    print("ARENA_HISTORY api_calls=0 paid_ai_calls=0 orders=0")
    print("ARENA_HISTORY full_brain_required=" + str(wanted))
    print("ARENA_HISTORY estimated_BTC_GETs=" + str(calls))
    return 0


def probe() -> int:
    print("=== AI Arena read-only BTC full Brain history sample ===", flush=True)
    print("ARENA_HISTORY public_GETs_max=25 paid_ai_calls=0 orders=0", flush=True)
    print("ARENA_HISTORY symbols=BTCUSDT mode=PUBLIC_READ_ONLY", flush=True)
    # Snap to the time BEFORE requesting any symbol's candles.
    asof_ms = int(time.time() * 1000)
    try:
        def throttled(symbol, frame, first, last):
            time.sleep(0.15)
            return _public_get(symbol, frame, first, last)
        digest, wanted, count = _sample(throttled, asof_ms)
    except ValueError as exc:
        reason = str(exc)
        if not re.fullmatch("[A-Z0-9_]+", reason):
            reason = "DATA_NOT_VERIFIED"
        print("ARENA_HISTORY RESULT=NOT_VERIFIED_" + reason, flush=True)
        return 2
    print("ARENA_HISTORY bars_required=" + str(wanted), flush=True)
    print("ARENA_HISTORY public_GETs=" + str(count), flush=True)
    print("ARENA_HISTORY BTC_snapshot_sha256=" + digest, flush=True)
    print("ARENA_HISTORY paid_ai_calls=0 orders=0 services_changed=0", flush=True)
    print("ARENA_HISTORY RESULT=FULL_BRAIN_WARMUP_BTC_VERIFIED_NO_DEPLOY", flush=True)
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    if sys.argv[1:] == ["--sample"]:
        sys.exit(probe())
    print("ARENA_HISTORY RESULT=USE_SELFTEST_OR_SAMPLE")
    sys.exit(2)
