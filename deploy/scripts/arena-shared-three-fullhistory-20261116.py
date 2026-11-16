#!/usr/bin/env python3
"""Public Bitget full Brain history for BTC, gold and silver at ONE as-of time.

Single shared frozen SHA256 payload for DeepSeek, Qwen and MiniMax.
--selftest uses synthetic stub data and zero HTTP calls.
--pilot performs <=75 public GET calls, no retries, credentials, AI requests,
orders, journal updates, stateful writes, or bot service modifications.
Strictly research-only; no trade approval or portfolio deployment.
"""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.v3.arena.frozen_market import FRAME_MS, freeze_market_batch

SYMBOLS = ("BTCUSDT", "XAUUSDT", "XAGUSDT")
LANES = ("deepseek", "qwen", "minimax")
MAX_PUBLIC_GET = 75


def _historical():
    path = Path(__file__).with_name("arena-historical-warmup-20261116.py")
    if not path.is_file():
        raise ValueError("HISTORY_MODULE_MISSING")
    spec = spec_from_file_location("arena_public_history", path)
    if spec is None or spec.loader is None:
        raise ValueError("HISTORY_MODULE_INVALID")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect(
    get, *, asof_ms: int, allowed_symbols: tuple[str, ...] = SYMBOLS
):
    """Return immutable batch & per-symbol request counters.

    Importantly, all markets and all TFs use the SAME asof_ms, not the time
    at which each HTTP response arrives. An incomplete symbol aborts the
    ENTIRE snapshot: no mix of fresh and incomplete market inputs.
    """
    if (type(asof_ms) is not int or asof_ms <= 0
            or allowed_symbols != SYMBOLS):
        raise ValueError("INVALID_SHARED_SNAPSHOT_SCOPE")
    history = _historical()
    wanted = history.requirements()
    if set(wanted) != set(FRAME_MS):
        raise ValueError("INCOMPLETE_BRAIN_PARAMS")

    datasets = {}
    requests = {}
    for symbol in allowed_symbols:
        dataset = {}
        count = 0
        for frame in FRAME_MS:
            rows, pages = history._fetch_frame(
                frame, wanted[frame], asof_ms, get, symbol=symbol
            )
            count += pages
            if count > history.MAX_REQUESTS:
                raise ValueError("SYMBOL_REQUEST_BUDGET_EXCEEDED")
            dataset[frame] = rows
        datasets[symbol] = dataset
        requests[symbol] = count
    if sum(requests.values()) > MAX_PUBLIC_GET:
        raise ValueError("GLOBAL_PUBLIC_REQUEST_BUDGET_EXCEEDED")
    frozen = freeze_market_batch(
        datasets, wanted, asof_ms=asof_ms,
        source_id="bitget.v2.history-candles.3market-pilot"
    )
    fingerprints = [frozen.for_provider(lane)[1] for lane in LANES]
    if len(set(fingerprints)) != 1:
        raise ValueError("CROSS_MODEL_SNAPSHOT_MISMATCH")
    return frozen, wanted, requests


def selftest() -> int:
    asof_ms = 1795000000000
    requested = []
    def stub(symbol, frame, first, last):
        if symbol not in SYMBOLS or frame not in FRAME_MS:
            raise AssertionError("OUTSIDE_RESEARCH_SCOPE")
        requested.append((symbol, frame, first, last))
        step = FRAME_MS[frame]
        price = "100" if symbol == "BTCUSDT" else (
            "200" if symbol == "XAUUSDT" else "300")
        return [
            [str(t), price, str(int(price)+2),
             str(int(price)-2), str(int(price)+1), "2", "400"]
            for t in range(last+step, first-step-1, -step)
        ]

    frozen, wanted, counts = collect(stub, asof_ms=asof_ms)
    assert set(counts) == set(SYMBOLS)
    assert sum(counts.values()) == len(requested) == 69
    assert sum(counts.values()) <= MAX_PUBLIC_GET
    assert wanted == {"1m": 60, "15m": 2893, "1h": 733, "4h": 193}
    assert frozen.symbols == tuple(sorted(SYMBOLS))
    assert frozen.classification == "PROVISIONAL_NOT_TRADE_APPROVED"
    assert frozen.for_provider("deepseek") == frozen.for_provider("qwen")
    assert frozen.for_provider("qwen") == frozen.for_provider("minimax")
    assert len(frozen.sha256_hex) == 64
    assert len({s for s, _tf, _a, _b in requested}) == 3

    def fail_xag(symbol, frame, first, last):
        return [] if symbol == "XAGUSDT" else stub(symbol, frame, first, last)
    try:
        collect(fail_xag, asof_ms=asof_ms)
    except ValueError as exc:
        assert str(exc) == "INCOMPLETE_HISTORY_PAGE"
    else:
        raise AssertionError("INCOMPLETE_METAL_WAS_ACCEPTED")

    try:
        collect(stub, asof_ms=asof_ms, allowed_symbols=("BTCUSDT",))
    except ValueError as exc:
        assert str(exc) == "INVALID_SHARED_SNAPSHOT_SCOPE"
    else:
        raise AssertionError("PARTIAL_3_MARKET_SCOPE_ACCEPTED")

    print("ARENA_SHARED3 SELFTEST=PASS_OFFLINE")
    print("ARENA_SHARED3 SELFTEST public_GETs=0 paid_AI_calls=0 orders=0")
    print("ARENA_SHARED3 simulated_pages=" + str(sum(counts.values())))
    print("ARENA_SHARED3 required=" + str(wanted))
    return 0


def pilot() -> int:
    print("=== AI Arena: public 3-market common-time full-history pilot ===",
          flush=True)
    print("ARENA_SHARED3 markets=BTCUSDT,XAUUSDT,XAGUSDT", flush=True)
    print("ARENA_SHARED3 max_public_GETs=75", flush=True)
    print("ARENA_SHARED3 paid_AI_calls=0 keys=0 orders=0 services_changed=0",
          flush=True)
    print("ARENA_SHARED3 mode=RESEARCH_PUBLIC_READ_ONLY", flush=True)
    asof_ms = int(time.time() * 1000)
    print("ARENA_SHARED3 shared_asof_ms=" + str(asof_ms), flush=True)
    history = _historical()
    count = 0
    def rate_limited(symbol, frame, first, last):
        nonlocal count
        if count >= MAX_PUBLIC_GET:
            raise ValueError("PUBLIC_REQUEST_BUDGET_EXCEEDED")
        count += 1
        time.sleep(0.20)
        return history._public_get(symbol, frame, first, last)

    try:
        frozen, wanted, per_symbol = collect(rate_limited, asof_ms=asof_ms)
    except ValueError as exc:
        label = str(exc)
        if not re.fullmatch(r"[A-Z0-9_]+", label):
            label = "UNCLASSIFIED_DATA_ERROR"
        print("ARENA_SHARED3 RESULT=NOT_VERIFIED_" + label, flush=True)
        print("ARENA_SHARED3 orders=0 paid_AI_calls=0 services_changed=0",
              flush=True)
        return 2

    for symbol in SYMBOLS:
        print(f"ARENA_SHARED3 {symbol}_historical_pages={per_symbol[symbol]}",
              flush=True)
    print("ARENA_SHARED3 requirements=" + str(wanted), flush=True)
    print("ARENA_SHARED3 public_GETs=" + str(count), flush=True)
    print("ARENA_SHARED3 combined_SHA256=" + frozen.sha256_hex, flush=True)
    for lane in LANES:
        blob, digest = frozen.for_provider(lane)
        if digest != frozen.sha256_hex or blob != frozen.canonical_bytes:
            raise RuntimeError("SHARED_SNAPSHOT_MUTATED")
        print("ARENA_SHARED3 " + lane.upper()
              + "_snapshot_sha256=" + digest, flush=True)
    print("ARENA_SHARED3 classification=PROVISIONAL_NOT_TRADE_APPROVED",
          flush=True)
    print("ARENA_SHARED3 orders=0 paid_AI_calls=0 services_changed=0",
          flush=True)
    print("ARENA_SHARED3 RESULT=THREE_MARKET_FROZEN_HISTORY_VERIFIED_NO_DEPLOY",
          flush=True)
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    if sys.argv[1:] == ["--pilot"]:
        sys.exit(pilot())
    print("ARENA_SHARED3 RESULT=USE_SELFTEST_OR_PILOT")
    sys.exit(2)
