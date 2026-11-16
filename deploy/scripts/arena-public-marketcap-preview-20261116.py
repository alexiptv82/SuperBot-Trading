#!/usr/bin/env python3
"""Public, non-trading 23-crypto market-cap preview for SuperBot AI Arena.

IMPORTANT: This is NOT production market classification or an allowlist. It
crosses one CoinGecko rankings snapshot with two public Bitget catalogs and
produces PROVISIONAL candidates ONLY. Categories/native-vs-synthetic identity,
closed candles at multiple timeframes, risk and signal scoring remain unverified.

Exactly three public GETs maximum; zero API keys, OpenRouter calls, writes,
orders, Docker changes or service actions. Includes fail-closed offline tests.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BITGET = "https://api.bitget.com"
GECKO = "https://api.coingecko.com"
COIN_ENDPOINT = "/api/v3/coins/markets"
CONTRACT_ENDPOINT = "/api/v2/mix/market/contracts"
TICKER_ENDPOINT = "/api/v2/mix/market/tickers"
METALS = ("XAUUSDT", "XAGUSDT")
CRYPTO_COUNT = 23
MAX_GET = 3
MIN_QUOTE_VOLUME = Decimal("1000000")
MAX_SPREAD_BPS = Decimal("30")
MAX_AGE_MS = 3 * 60 * 1000
MAX_BODY = 1_000_000
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
# Guards against OBVIOUS non-native entries only. Dynamic category
# verification (stablecoin/wrapped/tokenized RWA) is still mandatory.
BLOCK_IDS = frozenset({
    "tether", "usd-coin", "dai", "ethena-usde", "usds",
    "first-digital-usd", "paypal-usd", "ripple-usd",
    "world-liberty-financial-usd", "usual-usd", "ondo-us-dollar-yield",
    "circle-usyc", "pax-gold", "tether-gold", "wrapped-bitcoin",
    "coinbase-wrapped-btc", "wrapped-steth", "staked-ether",
    "wrapped-beacon-eth", "figure-heloc", "wrapped-ether",
})
BLOCK_SYMBOLS = frozenset({
    "USDT", "USDC", "DAI", "USDE", "USDS", "FDUSD", "PYUSD",
    "RLUSD", "USD1", "USYC", "USDY", "XAUT", "PAXG",
    "WBTC", "WETH", "WSTETH", "CBBTC", "WBETH", "STETH",
    "WEETH", "EURC",
})
BLOCK_NAME = re.compile(
    r"\b(?:wrapped|bridged|staked|tokenized|synthetic|stablecoin|"
    r"gold|silver|dollar|usd|treasury)\b", re.IGNORECASE,
)


def decimal(value: object) -> Decimal:
    if type(value) not in (str, int, float):
        raise ValueError("UNSAFE_NUMERIC_TYPE")
    try:
        x = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("INVALID_NUMBER") from None
    if not x.is_finite():
        raise ValueError("INVALID_NUMBER")
    return x


def rank_rows(body: object) -> list[dict]:
    """Strictly validate a time-local page before any recommendation."""
    if type(body) is not list or not 40 <= len(body) <= 250:
        raise ValueError("RANKING_INCOMPLETE")
    out = []
    ids, ranks = set(), set()
    for row in body:
        if type(row) is not dict:
            raise ValueError("INVALID_RANKING_ITEM")
        asset_id = row.get("id")
        symbol = row.get("symbol")
        name = row.get("name")
        rank = row.get("market_cap_rank")
        cap = row.get("market_cap")
        if (type(asset_id) is not str or ID_RE.fullmatch(asset_id) is None
                or type(name) is not str or not 1 <= len(name) <= 100
                or type(rank) is not int or rank < 1 or rank > 20000):
            raise ValueError("INVALID_RANKED_ASSET")
        if type(symbol) is not str or SYMBOL_RE.fullmatch(symbol.upper()) is None:
            # Unsupported exchange ticker format does not invalidate other
            # market-cap ranking rows; it can never become a trade candidate.
            continue
        try:
            cap_num = decimal(cap)
        except ValueError:
            raise ValueError("UNVERIFIED_MARKET_CAP") from None
        if cap_num <= 0 or asset_id in ids or rank in ranks:
            raise ValueError("DUPLICATE_OR_ZERO_RANKING")
        ids.add(asset_id)
        ranks.add(rank)
        out.append({
            "id": asset_id, "symbol": symbol.upper(),
            "name": name, "rank": rank, "cap": cap_num,
        })
    out.sort(key=lambda x: (x["rank"], -x["cap"], x["id"]))
    return out


def obviously_non_native(asset: dict) -> bool:
    return (asset["id"] in BLOCK_IDS
            or asset["symbol"] in BLOCK_SYMBOLS
            or bool(BLOCK_NAME.search(asset["name"])))


def _unique(rows: list, symbol: str) -> dict | None:
    hits = [r for r in rows if type(r) is dict and r.get("symbol") == symbol]
    if len(hits) > 1:
        raise ValueError("DUPLICATE_EXCHANGE_SYMBOL")
    return hits[0] if hits else None


def futures_precheck(contract: dict | None, ticker: dict | None,
                     now_ms: int) -> bool:
    """Catalog-only precheck. Cannot certify trading or candles."""
    if contract is None or ticker is None:
        return False
    if (contract.get("symbolType") != "perpetual"
            or contract.get("symbolStatus") != "normal"
            or contract.get("quoteCoin") != "USDT"
            or type(contract.get("baseCoin")) is not str
            or contract["baseCoin"] + "USDT" != contract.get("symbol")
            or contract.get("symbol") != ticker.get("symbol")):
        return False
    try:
        minlev = decimal(contract.get("minLever"))
        maxlev = decimal(contract.get("maxLever"))
        timestamp = int(ticker.get("ts"))
        bid = decimal(ticker.get("bidPr"))
        ask = decimal(ticker.get("askPr"))
        volume = decimal(ticker.get("quoteVolume"))
        if (minlev < 1 or minlev > 20 or maxlev < 20
                or not 0 <= now_ms - timestamp <= MAX_AGE_MS
                or bid <= 0 or ask < bid or ask <= 0
                or volume < MIN_QUOTE_VOLUME):
            return False
        spread_bps = (ask-bid)/((ask+bid)/2)*10000
        return spread_bps <= MAX_SPREAD_BPS
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return False


def preview(coins: object, contracts: object, tickers: object, *,
            now_ms: int) -> dict:
    if (type(contracts) is not list or type(tickers) is not list
            or type(now_ms) is not int or now_ms <= 0):
        raise ValueError("INVALID_PREVIEW_INPUTS")
    ranked = rank_rows(coins)
    # CoinGecko IDs are unique, ticker strings are NOT. If multiple ranked
    # IDs use the same ticker, the match to one Bitget contract is ambiguous.
    # Never silently attribute the first candidate's market cap to another.
    ticker_ids: dict[str, set[str]] = {}
    for coin in ranked:
        ticker_ids.setdefault(coin["symbol"], set()).add(coin["id"])
    ambiguous = {ticker for ticker, ids in ticker_ids.items() if len(ids) > 1}
    selected = []
    seen = set()
    excluded_non_native = 0
    excluded_ambiguous = 0
    unavailable_on_bitget = 0
    for coin in ranked:
        if len(selected) >= CRYPTO_COUNT:
            break
        if obviously_non_native(coin):
            excluded_non_native += 1
            continue
        if coin["symbol"] in ambiguous:
            excluded_ambiguous += 1
            continue
        symbol = coin["symbol"] + "USDT"
        if symbol in seen or symbol in METALS:
            continue
        seen.add(symbol)
        contract = _unique(contracts, symbol)
        ticker = _unique(tickers, symbol)
        if not futures_precheck(contract, ticker, now_ms):
            unavailable_on_bitget += 1
            continue
        selected.append({
            "coin_id": coin["id"], "symbol": symbol,
            "market_cap_rank": coin["rank"],
            "identity_status": "SYMBOL_MATCH_ONLY_REVIEW_REQUIRED",
        })
    return {
        "schema": "arena_marketcap_preview_v1",
        "state": "PROVISIONAL_REQUIRES_CATEGORY_AND_CANDLE_AUDIT",
        "asof_ms": now_ms,
        "crypto_target": CRYPTO_COUNT,
        "crypto_candidates_found": len(selected),
        "obvious_non_native_excluded": excluded_non_native,
        "ambiguous_tickers_excluded": excluded_ambiguous,
        "unavailable_or_illiquid_excluded": unavailable_on_bitget,
        "metals_reserved": list(METALS),
        "candidate_crypto": selected,
        "tradable_or_approved": False,
    }


def _get(url: str) -> object:
    if not (url.startswith(GECKO+COIN_ENDPOINT+"?")
            or url in (
                BITGET+CONTRACT_ENDPOINT+"?productType=USDT-FUTURES",
                BITGET+TICKER_ENDPOINT+"?productType=USDT-FUTURES",
            )):
        raise ValueError("ENDPOINT_NOT_ALLOWLISTED")
    req = urllib.request.Request(url, method="GET", headers={
        "Accept":"application/json",
        "User-Agent":"SuperBotArenaPublicCapPreview/1.0",
    })
    try:
        with urllib.request.urlopen(
            req, timeout=15, context=ssl.create_default_context(),
        ) as resp:
            if resp.geturl().split("?",1)[0] not in (
                GECKO+COIN_ENDPOINT, BITGET+CONTRACT_ENDPOINT,
                BITGET+TICKER_ENDPOINT,
            ):
                raise ValueError("UNEXPECTED_REDIRECT")
            raw = resp.read(MAX_BODY+1)
    except urllib.error.HTTPError as exc:
        raise ValueError("HTTP_"+str(exc.code)) from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise ValueError("PUBLIC_SOURCE_NETWORK_UNAVAILABLE") from None
    if len(raw) > MAX_BODY:
        raise ValueError("PUBLIC_SOURCE_TOO_LARGE")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("PUBLIC_SOURCE_BAD_JSON") from None


def _bitget_catalog(body: object) -> list:
    if (type(body) is not dict or body.get("code") != "00000"
            or type(body.get("data")) is not list
            or len(body["data"]) > 20000):
        raise ValueError("BITGET_CATALOG_INVALID")
    return body["data"]


def selftest() -> int:
    now = 1795000000000
    assets = [
        {
            "id": "coin-"+str(i), "name": "Coin "+str(i),
            "symbol": "A"+str(i), "market_cap_rank": i,
            "market_cap": 1000000000 - 1000000*i,
        } for i in range(1, 70)
    ]
    symbols = [x["symbol"].upper()+"USDT" for x in assets]
    contracts = [
        {"symbol":sym,"symbolType":"perpetual",
         "quoteCoin":"USDT","baseCoin":sym[:-4],"symbolStatus":"normal",
         "minLever":"1","maxLever":"50"} for sym in symbols
    ]
    ticks = [
        {"symbol":sym,"ts":str(now-10000),"bidPr":"99.9",
         "askPr":"100.1","quoteVolume":"2000000"} for sym in symbols
    ]
    result=preview(assets,contracts,ticks,now_ms=now)
    assert result["crypto_candidates_found"] == CRYPTO_COUNT
    assert result["candidate_crypto"][0]["market_cap_rank"] == 1
    assert result["candidate_crypto"][-1]["market_cap_rank"] == 23
    assert result["metals_reserved"] == ["XAUUSDT","XAGUSDT"]
    assert result["tradable_or_approved"] is False
    stable = [dict(x) for x in assets]
    stable[0]["id"] = "tether"
    stable[1]["name"] = "Wrapped coin"
    stable[2]["symbol"] = "USDC"
    filtered=preview(stable,contracts,ticks,now_ms=now)
    assert filtered["candidate_crypto"][0]["market_cap_rank"] == 4
    assert filtered["candidate_crypto"][-1]["market_cap_rank"] == 26
    missing_contract = [x for x in contracts if x["symbol"] != symbols[3]]
    assert preview(assets,missing_contract,ticks,now_ms=now)[
        "candidate_crypto"][-1]["market_cap_rank"] == 24
    stale=[dict(x) for x in ticks]
    stale[0]["ts"] = str(now-600000)
    assert preview(assets,contracts,stale,now_ms=now)[
        "candidate_crypto"][0]["market_cap_rank"] == 2
    duplicated = [dict(x) for x in assets]
    duplicated[1]["market_cap_rank"] = 1
    try:
        preview(duplicated,contracts,ticks,now_ms=now)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate rank accepted")
    for value in ("NaN",float("inf"),None,True):
        try:
            decimal(value)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid decimal accepted")
    assert obviously_non_native({"id":"pax-gold","symbol":"PAXG",
                                  "name":"PAX Gold"})
    # Reject a ticker shared by two distinct CoinGecko assets. The next
    # eligible rank is allowed to fill the candidate slot instead.
    collision = [dict(x) for x in assets]
    collision[30]["symbol"] = "A1"  # two IDs, ranks 1 and 31
    collision_result = preview(collision,contracts,ticks,now_ms=now)
    # Count is for rows actually scanned before 23 eligible entries
    # were collected: rank 31 is not scanned, but rank 1 is still
    # rejected because all 250 ranking rows were checked for collisions.
    assert collision_result["ambiguous_tickers_excluded"] == 1
    assert collision_result["candidate_crypto"][0]["market_cap_rank"] == 2
    assert collision_result["candidate_crypto"][-1]["market_cap_rank"] == 24
    # When both colliding assets occur inside the scanned portion, both
    # appear in the exclusion count and neither can be attributed to Bitget.
    early_collision = [dict(x) for x in assets]
    early_collision[1]["symbol"] = "A1"  # ranks 1 and 2
    early_result = preview(early_collision,contracts,ticks,now_ms=now)
    assert early_result["ambiguous_tickers_excluded"] == 2
    assert early_result["candidate_crypto"][0]["market_cap_rank"] == 3
    assert early_result["candidate_crypto"][-1]["market_cap_rank"] == 25
    # Bitget baseCoin is a second (exchange-owned) symbol consistency check.
    mismatch = [dict(x) for x in contracts]
    mismatch[0]["baseCoin"] = "DIFFERENT_ASSET"
    mismatch_result = preview(assets,mismatch,ticks,now_ms=now)
    assert mismatch_result["candidate_crypto"][0]["market_cap_rank"] == 2
    assert mismatch_result["unavailable_or_illiquid_excluded"] >= 1
    unsupported = [dict(x) for x in assets]
    unsupported[45]["symbol"] = "Ω"
    assert preview(unsupported,contracts,ticks,now_ms=now)["crypto_candidates_found"] == 23
    print("ARENA_CAP SELFTEST=PASS_OFFLINE")
    print("ARENA_CAP SELFTEST paid_ai_calls=0 public_GET_calls=0 orders=0")
    return 0


def probe() -> int:
    print("=== Arena provisional TOP-23 by market cap ===", flush=True)
    print("ARENA_CAP public_get_calls_max=3",flush=True)
    print("ARENA_CAP paid_ai_calls=0 keys=0 orders=0 services_changed=0",flush=True)
    print("ARENA_CAP classification=INCOMPLETE_REVIEW_REQUIRED",flush=True)
    url = GECKO+COIN_ENDPOINT+"?"+urllib.parse.urlencode({
        "vs_currency":"usd", "order":"market_cap_desc",
        "per_page":"250", "page":"1", "sparkline":"false",
    })
    try:
        ranking = _get(url)
        contracts = _bitget_catalog(_get(
            BITGET+CONTRACT_ENDPOINT+"?productType=USDT-FUTURES"))
        tickers = _bitget_catalog(_get(
            BITGET+TICKER_ENDPOINT+"?productType=USDT-FUTURES"))
        result=preview(ranking,contracts,tickers,now_ms=int(time.time()*1000))
    except ValueError as exc:
        reason = str(exc)
        if not re.fullmatch(r"[A-Z0-9_]+", reason):
            reason = "UNCLASSIFIED_SOURCE_ERROR"
        print("ARENA_CAP RESULT=SOURCE_UNVERIFIED_"+reason,flush=True)
        print("ARENA_CAP no_deploy=YES",flush=True)
        return 2
    for i,item in enumerate(result["candidate_crypto"],start=1):
        print(f"ARENA_CAP candidate_{i:02d}="
              f"{item['symbol']} rank={item['market_cap_rank']}"
              f" coingecko_id={item['coin_id']}",flush=True)
    print("ARENA_CAP crypto_found="+str(result["crypto_candidates_found"])+"/23",flush=True)
    print("ARENA_CAP excluded_obvious_nonnative="+str(
        result["obvious_non_native_excluded"]),flush=True)
    print("ARENA_CAP excluded_ambiguous_tickers="+str(
        result["ambiguous_tickers_excluded"]),flush=True)
    print("ARENA_CAP contracts_unavailable_or_illiquid="+str(
        result["unavailable_or_illiquid_excluded"]),flush=True)
    print("ARENA_CAP metals_reserved=XAUUSDT,XAGUSDT",flush=True)
    print("ARENA_CAP tradable_or_approved=NO",flush=True)
    print("ARENA_CAP RESULT=PROVISIONAL_LIST_CATEGORY_AND_CANDLES_PENDING",flush=True)
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    if sys.argv[1:] == ["--probe"]:
        sys.exit(probe())
    print("ARENA_CAP RESULT=USE_SELFTEST_OR_PROBE")
    sys.exit(2)
