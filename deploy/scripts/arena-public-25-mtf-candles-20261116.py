#!/usr/bin/env python3
"""AI Arena: public Bitget multi-timeframe candles for dynamic 23 crypto + XAU/XAG.

DATA AUDIT ONLY. The 23 symbols are selected afresh by the sibling provisional
CoinGecko/Bitget market-cap preview; they are NOT whitelisted for trading.
No keys, payments, AI calls, orders, runtime writes, retries, journal or service
changes. --sample makes <= 15 public GETs; --full makes <= 103 public GETs.
Four intervals are 1m, 15m, 1H, 4H (Bitget V2 futures convention).
Closed candles only, and 200 consecutive closed 4H candles required so the
next phase can build a real EMA200 without fabricated history.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import importlib.util
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BITGET = "https://api.bitget.com"
CANDLE_PATH = "/api/v2/mix/market/candles"
FRAME = {
    "1m": (60_000, 75, 60),
    "15m": (900_000, 80, 60),
    "1H": (3_600_000, 90, 60),
    "4H": (14_400_000, 240, 200),
}
METALS = ("XAUUSDT", "XAGUSDT")
ALL_LIMIT = 3 + 25 * len(FRAME)
SAMPLE_LIMIT = 3 + 3 * len(FRAME)
MAX_RESPONSE_BYTES = 400_000
SYM_RE = re.compile(r"[A-Z0-9]{2,20}USDT\Z")


def _preview_module():
    # Only fixed sibling in the same checked-out branch, not user-supplied code.
    source = Path(__file__).resolve().with_name(
        "arena-public-marketcap-preview-20261116.py")
    if not source.is_file():
        raise ValueError("MISSING_PINNED_PREVIEW_MODULE")
    spec = importlib.util.spec_from_file_location("arena_cap_preview", source)
    if spec is None or spec.loader is None:
        raise ValueError("PREVIEW_MODULE_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decimal(value: object) -> Decimal:
    if type(value) not in (str, int, float):
        raise ValueError("INVALID_DECIMAL_TYPE")
    try:
        number = Decimal(str(value))
    except (ValueError, InvalidOperation):
        raise ValueError("INVALID_DECIMAL") from None
    if not number.is_finite():
        raise ValueError("NONFINITE_DECIMAL")
    return number


def validate_bars(rows: object, *, frame: str, now_ms: int) -> tuple[str, int, str]:
    """Return (status, count, hash16); fail closed if bar coverage is suspect."""
    if frame not in FRAME or type(now_ms) is not int or now_ms <= 0:
        raise ValueError("INVALID_BAR_VALIDATION_REQUEST")
    frame_ms, fetch_limit, minimum = FRAME[frame]
    if type(rows) is not list or len(rows) > fetch_limit:
        return "INVALID_SHAPE", 0, "-"
    bars: dict[int, tuple[str, ...]] = {}
    try:
        for row in rows:
            if type(row) is not list or len(row) < 7 or type(row[0]) not in (str, int):
                raise ValueError("BAD_CANDLE_ROW")
            stamp = int(row[0])
            if stamp <= 0 or stamp % frame_ms or stamp in bars or stamp > now_ms:
                raise ValueError("BAD_CANDLE_TIME")
            o, h, l, c, base, quote = [_decimal(x) for x in row[1:7]]
            if (min(o, h, l, c) <= 0 or h < max(o, c)
                    or l > min(o, c) or h < l or min(base, quote) < 0):
                raise ValueError("BAD_CANDLE_OHLC")
            bars[stamp] = tuple(str(x) for x in (o, h, l, c, base, quote))
    except (ValueError, OverflowError, TypeError):
        return "INVALID_CANDLES", 0, "-"
    # Current forming bar is excluded even when returned by Bitget.
    closed = sorted(t for t in bars if t + frame_ms <= now_ms)
    if len(closed) < minimum:
        return "INSUFFICIENT_HISTORY", len(closed), "-"
    selected = closed[-minimum:]
    if any(t2 - t1 != frame_ms for t1, t2 in zip(selected, selected[1:])):
        return "CLOSED_BAR_GAPS", len(closed), "-"
    if now_ms - (selected[-1] + frame_ms) > 2 * frame_ms:
        return "STALE_LAST_BAR", len(closed), "-"
    payload = json.dumps(
        {"tf": frame, "rows": [(t, *bars[t]) for t in selected]},
        separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return "CLOSED_VERIFIED", len(closed), sha256(payload).hexdigest()[:16]


def _get_candles(symbol: str, frame: str) -> list:
    if type(symbol) is not str or SYM_RE.fullmatch(symbol) is None:
        raise ValueError("SYMBOL_NOT_VALIDATED")
    if frame not in FRAME:
        raise ValueError("GRANULARITY_NOT_ALLOWED")
    url = BITGET + CANDLE_PATH + "?" + urllib.parse.urlencode({
        "symbol": symbol,
        "productType": "USDT-FUTURES",
        "granularity": frame,
        "limit": str(FRAME[frame][1]),
    })
    req = urllib.request.Request(url, method="GET", headers={
        "Accept": "application/json",
        "User-Agent": "SuperBotArenaPublicMTFDiagnostics/1.0",
    })
    try:
        with urllib.request.urlopen(
            req, context=ssl.create_default_context(), timeout=12,
        ) as response:
            if response.geturl().split("?", 1)[0] != BITGET + CANDLE_PATH:
                raise ValueError("UNEXPECTED_REDIRECT")
            data = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise ValueError("HTTP_" + str(exc.code)) from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise ValueError("PUBLIC_NETWORK_UNAVAILABLE") from None
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("RESPONSE_TOO_LARGE")
    try:
        result = json.loads(data)
    except (UnicodeDecodeError, ValueError):
        raise ValueError("UNPARSEABLE_RESPONSE") from None
    if (type(result) is not dict or result.get("code") != "00000"
            or type(result.get("data")) is not list):
        raise ValueError("BITGET_CANDLES_UNAVAILABLE")
    return result["data"]


def selftest() -> int:
    now = 1795000000000
    for frame, (ms, size, minimum) in FRAME.items():
        current = (now // ms) * ms
        rows = [
            [str(current - i * ms), "100", "102", "98", "101", "10", "1000"]
            for i in range(size)
        ]
        result = validate_bars(rows, frame=frame, now_ms=now)
        assert result[0] == "CLOSED_VERIFIED", (frame, result)
        assert result[1] == size - 1
        assert len(result[2]) == 16
        assert validate_bars(rows[:minimum - 1], frame=frame, now_ms=now)[0] == "INSUFFICIENT_HISTORY"
        assert validate_bars(rows + [rows[0]], frame=frame, now_ms=now)[0] == "INVALID_SHAPE"
        duplicate = [list(r) for r in rows]
        duplicate[5] = duplicate[4]
        assert validate_bars(duplicate, frame=frame, now_ms=now)[0] == "INVALID_CANDLES"
        gap = [list(r) for r in rows]
        del gap[7]
        assert validate_bars(gap, frame=frame, now_ms=now)[0] == "CLOSED_BAR_GAPS"
        future = [list(r) for r in rows]
        future[0][0] = str(current + ms * 2)
        assert validate_bars(future, frame=frame, now_ms=now)[0] == "INVALID_CANDLES"
        invalid_ohlc = [list(r) for r in rows]
        invalid_ohlc[2][2] = "90"
        assert validate_bars(invalid_ohlc, frame=frame, now_ms=now)[0] == "INVALID_CANDLES"
        invalid_nan = [list(r) for r in rows]
        invalid_nan[2][2] = "NaN"
        assert validate_bars(invalid_nan, frame=frame, now_ms=now)[0] == "INVALID_CANDLES"
        previous = [list(r) for r in rows]
        previous = [[str(int(r[0]) - 4 * ms), *r[1:]] for r in previous]
        assert validate_bars(previous, frame=frame, now_ms=now)[0] == "STALE_LAST_BAR"
    for bad in (True, None, "NaN", "Infinity", "-Infinity"):
        try:
            _decimal(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid numeric type accepted")
    print("ARENA_MTF SELFTEST=PASS_OFFLINE")
    print("ARENA_MTF SELFTEST public_GETs=0 paid_ai_calls=0 orders=0")
    return 0


def run_probe(scope: str) -> int:
    if scope not in ("sample", "full"):
        raise ValueError("UNKNOWN_PROBE_SCOPE")
    print("=== Arena public market cap and MTF diagnostics ===", flush=True)
    print("ARENA_MTF public_GETs_max=" + str(
        SAMPLE_LIMIT if scope == "sample" else ALL_LIMIT), flush=True)
    print("ARENA_MTF mode=PAPER_OFFLINE_READONLY", flush=True)
    print("ARENA_MTF paid_ai_calls=0 api_keys=0 orders=0 services_changed=0", flush=True)
    print("ARENA_MTF classification=PROVISIONAL_NOT_TRADE_APPROVED", flush=True)
    cap = _preview_module()
    url = cap.GECKO + cap.COIN_ENDPOINT + "?" + urllib.parse.urlencode({
        "vs_currency": "usd", "order": "market_cap_desc", "per_page": "250",
        "page": "1", "sparkline": "false",
    })
    try:
        ranking = cap._get(url)
        contracts = cap._bitget_catalog(cap._get(
            cap.BITGET + cap.CONTRACT_ENDPOINT + "?productType=USDT-FUTURES"))
        tickers = cap._bitget_catalog(cap._get(
            cap.BITGET + cap.TICKER_ENDPOINT + "?productType=USDT-FUTURES"))
        run_snapshot_time = int(time.time() * 1000)
        listing = cap.preview(ranking, contracts, tickers, now_ms=run_snapshot_time)
    except ValueError as exc:
        name = str(exc)
        if not re.fullmatch(r"[A-Z0-9_]+", name):
            name = "CATALOG_UNVERIFIED"
        print("ARENA_MTF RESULT=CATALOG_UNVERIFIED_" + name, flush=True)
        return 2
    candidates = [row["symbol"] for row in listing["candidate_crypto"]]
    if len(candidates) != 23 or len(set(candidates)) != 23:
        print("ARENA_MTF RESULT=INSUFFICIENT_UNIQUE_CRYPTO_CANDIDATES", flush=True)
        return 2
    if scope == "sample":
        symbols = ("BTCUSDT", *METALS)
        if "BTCUSDT" not in candidates:
            print("ARENA_MTF RESULT=BTC_NOT_IN_PROVISIONAL_UNIVERSE", flush=True)
            return 2
    else:
        symbols = tuple(candidates) + METALS
    print("ARENA_MTF markets_to_check=" + str(len(symbols)), flush=True)
    print("ARENA_MTF crypto_provisional=23 metals_reserved=2", flush=True)
    checks_passed = 0
    total = len(symbols) * len(FRAME)
    for symbol in symbols:
        results: list[str] = []
        for frame in FRAME:
            try:
                # Keep well below Bitget 20 GET/sec/IP limit, no automatic retry.
                time.sleep(0.12)
                rows = _get_candles(symbol, frame)
                status, count, digest = validate_bars(
                    rows, frame=frame, now_ms=int(time.time() * 1000))
                if status == "CLOSED_VERIFIED":
                    checks_passed += 1
                results.append(frame + "=" + status + "(" + str(count) + "," + digest + ")")
            except ValueError as exc:
                reason = str(exc)
                if not re.fullmatch(r"[A-Z0-9_]+", reason):
                    reason = "DATA_UNVERIFIED"
                results.append(frame + "=UNVERIFIED_" + reason)
        print("ARENA_MTF " + symbol + " " + " ".join(results), flush=True)
    print("ARENA_MTF closed_frame_checks=" + str(checks_passed) + "/" + str(total), flush=True)
    print("ARENA_MTF orders=0 paid_ai_calls=0 services_changed=0", flush=True)
    print("ARENA_MTF RESULT=PUBLIC_DATA_PREVIEW_NOT_TRADE_APPROVED", flush=True)
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    if sys.argv[1:] == ["--sample"]:
        sys.exit(run_probe("sample"))
    if sys.argv[1:] == ["--full"]:
        sys.exit(run_probe("full"))
    print("ARENA_MTF RESULT=USE_SELFTEST_SAMPLE_OR_FULL")
    sys.exit(2)
