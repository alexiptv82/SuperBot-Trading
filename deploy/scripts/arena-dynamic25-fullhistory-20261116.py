#!/usr/bin/env python3
"""AI Arena research: one immutable historical batch for 23 ranked crypto + metals.

Public CoinGecko/Bitget GETs ONLY. No API secrets, paid AI calls, orders,
journal writes, production trading services, or deployment.

--selftest : in-memory fake 25-market snapshot (zero GETs).
--plan     : 3 public GETs for a DYNAMIC provisional candidate manifest.
--full25   : 3 catalog GETs + at most 575 paginated historical GETs; fail
             closed if any asset/frame is incomplete. NO retry.
All markets use a single as-of timestamp fixed before historical requests.
The data are PROVISIONAL_NOT_TRADE_APPROVED even on full success.
"""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from urllib.parse import urlencode
import re
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from backend.v3.arena.frozen_market import FRAME_MS, freeze_market_batch

SYMBOLS_TOTAL = 25
CRYPTO_COUNT = 23
METALS = ("XAUUSDT", "XAGUSDT")
LANES = ("deepseek", "qwen", "minimax")
MAX_CATALOG_GETS = 3
MAX_HISTORY_GETS = 575
MAX_PUBLIC_GETS = MAX_CATALOG_GETS + MAX_HISTORY_GETS
SAFE_SYMBOL = re.compile(r"[A-Z0-9]{2,20}USDT\Z")


def sibling(name: str, module_id: str):
    if name not in (
        "arena-public-marketcap-preview-20261116.py",
        "arena-historical-warmup-20261116.py",
    ):
        raise ValueError("UNAPPROVED_RESEARCH_MODULE")
    path = Path(__file__).with_name(name)
    if not path.is_file():
        raise ValueError("REQUIRED_RESEARCH_MODULE_MISSING")
    spec = spec_from_file_location(module_id, path)
    if spec is None or spec.loader is None:
        raise ValueError("RESEARCH_MODULE_UNLOADABLE")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cap_module():
    return sibling("arena-public-marketcap-preview-20261116.py", "arena_ranked_cap_v1")


def history_module():
    return sibling("arena-historical-warmup-20261116.py", "arena_public_history_v1")


def checked_symbols(listing: object) -> tuple[str, ...]:
    if (type(listing) is not dict
            or listing.get("schema") != "arena_marketcap_preview_v1"
            or listing.get("state") != "PROVISIONAL_REQUIRES_CATEGORY_AND_CANDLE_AUDIT"
            or listing.get("tradable_or_approved") is not False
            or listing.get("crypto_candidates_found") != CRYPTO_COUNT
            or listing.get("metals_reserved") != list(METALS)):
        raise ValueError("UNVERIFIED_UNIVERSE_METADATA")
    candidates = listing.get("candidate_crypto")
    if type(candidates) is not list or len(candidates) != CRYPTO_COUNT:
        raise ValueError("UNVERIFIED_UNIVERSE_LENGTH")
    crypto = []
    ranks = set()
    ids = set()
    for item in candidates:
        if type(item) is not dict:
            raise ValueError("UNVERIFIED_UNIVERSE_ITEM")
        symbol = item.get("symbol")
        rank = item.get("market_cap_rank")
        coin_id = item.get("coin_id")
        if (type(symbol) is not str or SAFE_SYMBOL.fullmatch(symbol) is None
                or type(rank) is not int or rank < 1
                or type(coin_id) is not str
                or not re.fullmatch(r"[a-z0-9-]{1,100}", coin_id)
                or item.get("identity_status") != "SYMBOL_MATCH_ONLY_REVIEW_REQUIRED"):
            raise ValueError("UNVERIFIED_SYMBOL_IDENTITY")
        crypto.append(symbol)
        if rank in ranks or coin_id in ids:
            raise ValueError("DUPLICATE_RANK_OR_COIN_ID")
        ranks.add(rank)
        ids.add(coin_id)
    if (len(set(crypto)) != CRYPTO_COUNT
            or any(metal in crypto for metal in METALS)
            or len(crypto + list(METALS)) != SYMBOLS_TOTAL):
        raise ValueError("AMBIGUOUS_OR_INCOMPLETE_SYMBOL_SET")
    return tuple(crypto) + METALS


def catalog_snapshot():
    cap = cap_module()
    url = cap.GECKO + cap.COIN_ENDPOINT + "?" + urlencode({
        "vs_currency": "usd", "order": "market_cap_desc",
        "per_page": "250", "page": "1", "sparkline": "false",
    })
    ranked = cap._get(url)
    contracts = cap._bitget_catalog(cap._get(
        cap.BITGET + cap.CONTRACT_ENDPOINT + "?productType=USDT-FUTURES"))
    tickers = cap._bitget_catalog(cap._get(
        cap.BITGET + cap.TICKER_ENDPOINT + "?productType=USDT-FUTURES"))
    asof_ms = int(time.time() * 1000)
    listing = cap.preview(ranked, contracts, tickers, now_ms=asof_ms)
    symbols = checked_symbols(listing)
    return symbols, listing, asof_ms


def collect(symbols: tuple[str, ...], asof_ms: int, get, *, on_symbol=None):
    """Fail if any historical candle is missing; never silently drop assets."""
    if (type(symbols) is not tuple or len(symbols) != SYMBOLS_TOTAL
            or len(set(symbols)) != SYMBOLS_TOTAL
            or symbols[-2:] != METALS
            or any(type(s) is not str or SAFE_SYMBOL.fullmatch(s) is None
                   for s in symbols)
            or type(asof_ms) is not int or asof_ms <= 0):
        raise ValueError("INVALID_25_MARKET_SCOPE")
    history = history_module()
    required = history.requirements()
    if set(required) != set(FRAME_MS):
        raise ValueError("INCOMPLETE_BRAIN_WARMUP_PARAMS")
    estimate = len(symbols) * sum(
        (n + history.PAGE - 1) // history.PAGE for n in required.values())
    if estimate > MAX_HISTORY_GETS:
        raise ValueError("HISTORY_REQUEST_CAP_EXCEEDED")
    counters = {}
    data = {}
    for symbol in symbols:
        market = {}
        used = 0
        for frame in FRAME_MS:
            bars, n = history._fetch_frame(
                frame, required[frame], asof_ms, get, symbol=symbol
            )
            used += n
            if used > history.MAX_REQUESTS:
                raise ValueError("PER_SYMBOL_HISTORY_BUDGET_EXCEEDED")
            market[frame] = bars
        counters[symbol] = used
        data[symbol] = market
        if on_symbol is not None:
            on_symbol(symbol, used)
    if sum(counters.values()) != estimate:
        raise ValueError("PAGE_ACCOUNTING_MISMATCH")
    frozen = freeze_market_batch(
        data, required, asof_ms=asof_ms,
        source_id="bitget.v2.history-candles.dynamic25-research"
    )
    if (len(frozen.symbols) != SYMBOLS_TOTAL
            or frozen.classification != "PROVISIONAL_NOT_TRADE_APPROVED"):
        raise ValueError("FROZEN_UNIVERSE_INCOMPLETE")
    for lane in LANES:
        body, digest = frozen.for_provider(lane)
        if body != frozen.canonical_bytes or digest != frozen.sha256_hex:
            raise ValueError("CROSS_MODEL_SNAPSHOT_MISMATCH")
    return frozen, counters, required


def selftest() -> int:
    asof_ms = 1795000000000
    crypto = ["A" + str(i) + "USDT" for i in range(1, 24)]
    listing = {
        "schema": "arena_marketcap_preview_v1",
        "state": "PROVISIONAL_REQUIRES_CATEGORY_AND_CANDLE_AUDIT",
        "tradable_or_approved": False,
        "crypto_candidates_found": 23,
        "metals_reserved": list(METALS),
        "candidate_crypto": [
            {"symbol": s, "market_cap_rank": i, "coin_id": "coin-" + str(i),
             "identity_status": "SYMBOL_MATCH_ONLY_REVIEW_REQUIRED"}
            for i, s in enumerate(crypto, 1)
        ],
    }
    symbols = checked_symbols(listing)
    assert len(symbols) == 25 and symbols[-2:] == METALS
    calls = []
    def fake(symbol, frame, first, last):
        calls.append((symbol, frame, first, last))
        step = FRAME_MS[frame]
        return [[str(t), "100", "102", "98", "101", "10", "1000"]
                for t in range(last + step, first - step - 1, -step)]
    frozen, counters, req = collect(symbols, asof_ms, fake)
    assert sum(counters.values()) == len(calls) == MAX_HISTORY_GETS == 575
    assert req == {"1m": 60, "15m": 2893, "1h": 733, "4h": 193}
    assert frozen.symbols == tuple(sorted(symbols))
    assert frozen.for_provider("deepseek") == frozen.for_provider("qwen")
    assert frozen.for_provider("qwen") == frozen.for_provider("minimax")
    assert len(frozen.sha256_hex) == 64
    assert len({x[0] for x in calls}) == 25
    bad = dict(listing)
    bad["candidate_crypto"] = [dict(c) for c in listing["candidate_crypto"]]
    bad["candidate_crypto"][2]["symbol"] = "A1USDT"
    try:
        checked_symbols(bad)
    except ValueError as exc:
        assert str(exc) == "AMBIGUOUS_OR_INCOMPLETE_SYMBOL_SET"
    else:
        raise AssertionError("DUPLICATE_ASSET_ACCEPTED")
    bad = dict(listing, tradable_or_approved=True)
    try:
        checked_symbols(bad)
    except ValueError as exc:
        assert str(exc) == "UNVERIFIED_UNIVERSE_METADATA"
    else:
        raise AssertionError("TRADING_APPROVAL_INJECTED")
    try:
        collect(symbols, asof_ms, lambda *args: [])
    except ValueError as exc:
        assert str(exc) == "INCOMPLETE_HISTORY_PAGE"
    else:
        raise AssertionError("INCOMPLETE_CANDLES_ACCEPTED")
    print("ARENA_FULL25 SELFTEST=PASS_OFFLINE")
    print("ARENA_FULL25 SELFTEST public_GETs=0 paid_AI_calls=0 orders=0")
    print("ARENA_FULL25 simulated_HISTORICAL_pages=575")
    print("ARENA_FULL25 required=" + str(req))
    return 0


def run(mode: str) -> int:
    if mode not in ("plan", "full25"):
        raise ValueError("INVALID_MODE")
    print("=== AI Arena dynamic full history -- provisional markets ===",
          flush=True)
    print("ARENA_FULL25 mode=" + mode + " public_READ_ONLY=YES", flush=True)
    print("ARENA_FULL25 max_public_GETs=" + str(
        3 if mode == "plan" else MAX_PUBLIC_GETS), flush=True)
    print("ARENA_FULL25 paid_AI_calls=0 credentials=0 orders=0 services_changed=0",
          flush=True)
    try:
        symbols, listing, asof_ms = catalog_snapshot()
    except ValueError as exc:
        reason = str(exc)
        if re.fullmatch(r"[A-Z0-9_]+", reason) is None:
            reason = "UNVERIFIED_CATALOG"
        print("ARENA_FULL25 RESULT=NOT_VERIFIED_" + reason, flush=True)
        return 2
    print("ARENA_FULL25 asof_ms=" + str(asof_ms), flush=True)
    print("ARENA_FULL25 crypto=23 metals=2 classification=PROVISIONAL",
          flush=True)
    print("ARENA_FULL25 universe=" + ",".join(symbols), flush=True)
    if mode == "plan":
        print("ARENA_FULL25 RESULT=PLAN_ONLY_NO_HISTORICAL_GETS", flush=True)
        return 0

    count = 0
    history = history_module()
    def public_history(symbol, frame, first, last):
        nonlocal count
        if count >= MAX_HISTORY_GETS:
            raise ValueError("PUBLIC_GET_HARD_CAP_REACHED")
        count += 1
        time.sleep(0.2)
        return history._public_get(symbol, frame, first, last)

    try:
        frozen, per_symbol, required = collect(
            symbols, asof_ms, public_history,
            on_symbol=lambda sym, pages: print(
                "ARENA_FULL25 completed=" + sym + " pages=" + str(pages)
                + " historical_GETs=" + str(count), flush=True),
        )
    except ValueError as exc:
        reason = str(exc)
        if re.fullmatch(r"[A-Z0-9_]+", reason) is None:
            reason = "UNVERIFIED_HISTORY"
        print("ARENA_FULL25 history_GETs_attempted=" + str(count), flush=True)
        print("ARENA_FULL25 RESULT=NOT_VERIFIED_" + reason, flush=True)
        print("ARENA_FULL25 orders=0 services_changed=0", flush=True)
        return 2
    for symbol in symbols:
        print("ARENA_FULL25 " + symbol + "_pages="
              + str(per_symbol[symbol]), flush=True)
    print("ARENA_FULL25 requirements=" + str(required), flush=True)
    print("ARENA_FULL25 history_GETs=" + str(count), flush=True)
    print("ARENA_FULL25 combined_SHA256=" + frozen.sha256_hex, flush=True)
    for lane in LANES:
        print("ARENA_FULL25 " + lane.upper()
              + "_snapshot_sha256=" + frozen.for_provider(lane)[1], flush=True)
    print("ARENA_FULL25 classification=PROVISIONAL_NOT_TRADE_APPROVED",
          flush=True)
    print("ARENA_FULL25 orders=0 paid_AI_calls=0 services_changed=0",
          flush=True)
    print("ARENA_FULL25 RESULT=ALL_25_SHARED_HISTORY_VERIFIED_NO_DEPLOY",
          flush=True)
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    if sys.argv[1:] == ["--plan"]:
        sys.exit(run("plan"))
    if sys.argv[1:] == ["--full25"]:
        sys.exit(run("full25"))
    print("ARENA_FULL25 RESULT=USE_SELFTEST_PLAN_OR_FULL25")
    sys.exit(2)
