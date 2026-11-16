#!/usr/bin/env python3
"""AI Arena: Bitget PUBLIC market feed preflight (BTC, XAU and XAG).

No API keys, no OpenRouter, no trading API, no journal/service writes.
Exactly five public HTTP GET requests maximum: one contract catalog, one
ticker catalog, and three 15m candle batches. Diagnostic only; even PASS
does not authorize PAPER/LIVE orders, or certify an entire 25-asset universe.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.bitget.com"
SYMBOLS = ("BTCUSDT", "XAUUSDT", "XAGUSDT")
MAX_HTTP = 1_000_000
TIMEFRAME_MS = 900_000
MAX_TICK_AGE_MS = 180_000
MIN_CLOSED = 30
MIN_VOLUME = Decimal("1000000")
MAX_SPREAD_BPS = Decimal("30")
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}USDT$")


def dec(value: object) -> Decimal:
    if type(value) not in (str, int, float) or isinstance(value, bool):
        raise ValueError("INVALID_DECIMAL")
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("INVALID_DECIMAL") from None
    if not n.is_finite():
        raise ValueError("INVALID_DECIMAL")
    return n


def envelope(body: object, limit: int = 10_000) -> list[dict] | list[list]:
    if type(body) is not dict or body.get("code") != "00000":
        raise ValueError("BITGET_RESPONSE_ERROR")
    data = body.get("data")
    if type(data) is not list or len(data) > limit:
        raise ValueError("UNEXPECTED_DATA_SHAPE")
    return data


def find_unique(rows: list, symbol: str) -> dict | None:
    found = [x for x in rows if type(x) is dict and x.get("symbol") == symbol]
    if len(found) > 1:
        raise ValueError("DUPLICATE_CONTRACT_OR_TICKER")
    return found[0] if found else None


def contract_status(contract: dict | None) -> tuple[str, str]:
    if contract is None:
        return "UNAVAILABLE", "NOT_LISTED_IN_USDT_FUTURES"
    if (contract.get("symbolType") != "perpetual"
            or contract.get("quoteCoin") != "USDT"
            or contract.get("symbolStatus") != "normal"):
        return "UNAVAILABLE", "NOT_OPEN_PERPETUAL"
    try:
        low = dec(contract.get("minLever"))
        high = dec(contract.get("maxLever"))
        if low > 20 or high < 20 or low < 1:
            return "UNAVAILABLE", "LEVERAGE_20X_NOT_SUPPORTED"
    except ValueError:
        return "UNVERIFIED", "LEVERAGE_NOT_VERIFIED"
    return "ELIGIBLE", "CONTRACT_20X_OK"


def ticker_status(ticker: dict | None, now_ms: int) -> tuple[str, str]:
    if ticker is None:
        return "UNAVAILABLE", "NO_TICKER"
    try:
        stamp = int(ticker.get("ts"))
        bid = dec(ticker.get("bidPr"))
        ask = dec(ticker.get("askPr"))
        volume = dec(ticker.get("quoteVolume"))
        if (stamp <= 0 or not 0 <= now_ms - stamp <= MAX_TICK_AGE_MS
                or bid <= 0 or ask <= 0 or ask < bid
                or volume <= 0):
            return "UNVERIFIED", "STALE_OR_INVALID_QUOTES"
        spread_bps = (ask - bid) / ((ask + bid) / 2) * 10_000
        if spread_bps > MAX_SPREAD_BPS or volume < MIN_VOLUME:
            return "UNAVAILABLE", "SPREAD_OR_VOLUME_FILTER"
    except (ValueError, TypeError, OverflowError):
        return "UNVERIFIED", "TICKER_MISSING_REQUIRED_FIELDS"
    return "ELIGIBLE", "FRESH_LIQUID_TICKER"


def validate_candles(rows: list, now_ms: int) -> tuple[str, int, str]:
    if type(rows) is not list or len(rows) > 100:
        return "INVALID_CANDLES", 0, "-"
    by_time = {}
    try:
        for row in rows:
            if type(row) is not list or len(row) < 7:
                raise ValueError("BAD_ROW")
            t = int(row[0])
            if t % TIMEFRAME_MS != 0 or t in by_time or t <= 0:
                raise ValueError("BAD_TIMESTAMP")
            o,h,l,c,base,quote = (dec(x) for x in row[1:7])
            if (min(o,h,l,c) <= 0 or h < max(o,c)
                    or l > min(o,c) or h < l
                    or min(base,quote) < 0):
                raise ValueError("BAD_OHLC")
            by_time[t] = (str(o),str(h),str(l),str(c),str(base),str(quote))
    except (ValueError, TypeError, OverflowError):
        return "INVALID_CANDLES", 0, "-"
    # Latest open candle is deliberately excluded from the shared snapshot.
    closed = sorted(t for t in by_time if 0 <= now_ms - t >= TIMEFRAME_MS)
    if len(closed) < MIN_CLOSED:
        return "INSUFFICIENT_CLOSED_BARS", len(closed), "-"
    tail = closed[-MIN_CLOSED:]
    if (any(b-a != TIMEFRAME_MS for a,b in zip(tail,tail[1:]))
            or now_ms - tail[-1] > 2 * TIMEFRAME_MS):
        return "GAP_OR_STALE_CANDLES", len(closed), "-"
    serial = json.dumps([(t,*by_time[t]) for t in tail],separators=(",",":"))
    return "CLOSED_15M_VERIFIED",len(closed),sha256(serial.encode()).hexdigest()[:16]


def assess(symbol: str, contracts: list, tickers: list, candles: list,
           now_ms: int) -> dict:
    if symbol not in SYMBOLS or type(now_ms) is not int or now_ms <= 0:
        raise ValueError("INVALID_PROBE_SCOPE")
    con = find_unique(contracts, symbol)
    tic = find_unique(tickers, symbol)
    cs,cr=contract_status(con)
    ts,tr=ticker_status(tic,now_ms)
    bs,bn,digest=validate_candles(candles,now_ms)
    return {
        "symbol":symbol, "contract":cs, "contract_reason":cr,
        "ticker":ts, "ticker_reason":tr,
        "candles":bs, "closed_15m_count":bn,
        "closed_candles_hash16":digest,
        "paper_candidate_data_ready":(
            cs=="ELIGIBLE" and ts=="ELIGIBLE"
            and bs=="CLOSED_15M_VERIFIED"
        ),
    }


def public_get(path: str, params: dict[str,str]) -> list:
    if path not in ("/api/v2/mix/market/contracts",
                    "/api/v2/mix/market/tickers",
                    "/api/v2/mix/market/candles"):
        raise ValueError("ENDPOINT_NOT_ALLOWLISTED")
    if params.get("productType") != "USDT-FUTURES":
        raise ValueError("PRODUCT_NOT_ALLOWLISTED")
    if path.endswith("/candles") and (
        params.get("symbol") not in SYMBOLS
        or params.get("granularity") != "15m"
        or params.get("limit") != "64"
    ):
        raise ValueError("CANDLE_SCOPE_NOT_ALLOWLISTED")
    url=BASE+path+"?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={
        "Accept":"application/json",
        "User-Agent":"SuperBotArenaPublicFeedReadOnly/1.0",
    },method="GET")
    try:
        with urllib.request.urlopen(
            req, timeout=12, context=ssl.create_default_context()
        ) as resp:
            if resp.geturl().split("?",1)[0] != BASE+path:
                raise ValueError("UNEXPECTED_REDIRECT")
            raw=resp.read(MAX_HTTP+1)
    except urllib.error.HTTPError as exc:
        raise ValueError("HTTP_"+str(exc.code)) from None
    except (urllib.error.URLError,TimeoutError,OSError):
        raise ValueError("PUBLIC_MARKET_NETWORK_ERROR") from None
    if len(raw)>MAX_HTTP:
        raise ValueError("PUBLIC_RESPONSE_TOO_BIG")
    try:
        obj=json.loads(raw)
    except (ValueError,UnicodeDecodeError):
        raise ValueError("PUBLIC_RESPONSE_NOT_JSON") from None
    return envelope(obj)


def synthetic(now_ms: int, symbol: str) -> tuple[dict,dict,list]:
    last_start=now_ms//TIMEFRAME_MS*TIMEFRAME_MS
    c={
        "symbol":symbol,"quoteCoin":"USDT",
        "symbolType":"perpetual","symbolStatus":"normal",
        "minLever":"1","maxLever":"50",
    }
    t={
        "symbol":symbol,"ts":str(now_ms-10_000),
        "bidPr":"99.9","askPr":"100.1",
        "quoteVolume":"2000000",
    }
    candles=[
        [str(last_start-i*TIMEFRAME_MS),"100","102","98","101","20","2000"]
        for i in range(64)
    ]
    return c,t,candles


def selftest() -> int:
    now=1795000000000
    # A realistic test clock for the latest closed candle.
    c,t,b=synthetic(now,"BTCUSDT")
    ok=assess("BTCUSDT",[c],[t],b,now)
    assert ok["paper_candidate_data_ready"] is True
    assert ok["candles"]=="CLOSED_15M_VERIFIED"
    assert ok["closed_15m_count"]>=MIN_CLOSED
    assert len(ok["closed_candles_hash16"])==16
    assert assess("XAUUSDT",[],[],[],now)["paper_candidate_data_ready"] is False
    assert contract_status({**c,"symbolStatus":"limit_open"})[0]=="UNAVAILABLE"
    assert contract_status({**c,"maxLever":"10"})[0]=="UNAVAILABLE"
    assert ticker_status({**t,"ts":str(now-600_000)},now)[0]=="UNVERIFIED"
    assert ticker_status({**t,"bidPr":"101","askPr":"99"},now)[0]=="UNVERIFIED"
    assert ticker_status({**t,"quoteVolume":"10"},now)[0]=="UNAVAILABLE"
    assert validate_candles([[*row] for row in b[:3]],now)[0]=="INSUFFICIENT_CLOSED_BARS"
    assert validate_candles([*b,b[1]],now)[0]=="INVALID_CANDLES"
    bad=[*b]
    bad[20]=[str(int(b[20][0])-60_000),*b[20][1:]]
    assert validate_candles(bad,now)[0]!="CLOSED_15M_VERIFIED"
    try:
        find_unique([c,c],"BTCUSDT")
        raise AssertionError("duplicates accepted")
    except ValueError:
        pass
    for value in (None,True,"NaN","Infinity","-Infinity"):
        try:
            dec(value)
            raise AssertionError("invalid decimal accepted")
        except ValueError:
            pass
    print("ARENA_FEED SELFTEST=PASS_OFFLINE")
    print("ARENA_FEED SELFTEST api_calls=0 api_keys=0 orders=0")
    return 0


def probe() -> int:
    print("=== Arena Bitget public-feed preflight ===",flush=True)
    print("ARENA_FEED endpoints=contracts,tickers,candles15m",flush=True)
    print("ARENA_FEED max_public_GET_requests=5",flush=True)
    print("ARENA_FEED market_symbols=BTCUSDT,XAUUSDT,XAGUSDT",flush=True)
    print("ARENA_FEED paid_ai_calls=0 api_keys=0 orders=0 services_changed=0",flush=True)
    try:
        all_contracts=public_get("/api/v2/mix/market/contracts",{
            "productType":"USDT-FUTURES"})
        all_tickers=public_get("/api/v2/mix/market/tickers",{
            "productType":"USDT-FUTURES"})
    except ValueError as exc:
        print("ARENA_FEED RESULT=CATALOG_ERROR_"+str(exc))
        return 2
    now=int(time.time()*1000)
    ready=0
    for symbol in SYMBOLS:
        try:
            rows=public_get("/api/v2/mix/market/candles",{
                "symbol":symbol,"productType":"USDT-FUTURES",
                "granularity":"15m","limit":"64",
            })
            result=assess(symbol,all_contracts,all_tickers,rows,now)
            if result["paper_candidate_data_ready"]:
                ready+=1
            print("ARENA_FEED "+symbol+"="+json.dumps(
                result,sort_keys=True,separators=(",",":")),flush=True)
        except ValueError as exc:
            # Deliberately do not print arbitrary provider error text.
            print("ARENA_FEED "+symbol+"=DATA_UNVERIFIED",flush=True)
    print(f"ARENA_FEED ready={ready}/3",flush=True)
    print("ARENA_FEED orders=0 services_changed=0 paid_ai_calls=0",flush=True)
    print("ARENA_FEED RESULT=PUBLIC_MARKET_DIAGNOSTIC_ONLY_NO_DEPLOY",flush=True)
    return 0


if __name__=="__main__":
    if sys.argv[1:]==["--selftest"]:
        sys.exit(selftest())
    if sys.argv[1:]==["--probe"]:
        sys.exit(probe())
    print("ARENA_FEED RESULT=USE_SELFTEST_OR_PROBE")
    sys.exit(2)
