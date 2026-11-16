#!/usr/bin/env python3
"""Public Bitget-to-Arena-cache delta adapter, isolated research only.

The initial 25-market historical snapshot was memory-only, not a saved cache.
This tool DOES NOT bootstrap it or install a service. It proves that a
previously verified FrozenMarketBatch can be updated with exactly the newly
closed public Bitget candles, with no partial/uncertain market state.

--selftest : deterministic 25-market in-memory test; zero network and disk.
--probe    : at most four public Bitget GETs on BTC for 4 timeframes, no writes.
Never uses trading keys, AI provider APIs, order endpoints, journal or services.
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

from backend.v3.arena.frozen_market import (
    FRAME_MS, _closed_rows, freeze_market_batch,
)
from backend.v3.arena.incremental_cache import delta_plan, merge_delta

MAX_PUBLIC_DELTA_GETS = 100     # 25 symbols times 4 frames, hard limit
MAX_PUBLIC_PROBE_GETS = 4
LANES = ("deepseek", "qwen", "minimax")


def _history_module():
    path = Path(__file__).with_name("arena-historical-warmup-20261116.py")
    spec = spec_from_file_location("arena_historical_public_adapter", path)
    if spec is None or spec.loader is None:
        raise ValueError("HISTORY_MODULE_UNAVAILABLE")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _exact_delta(rows: object, frame: str, first: int, last: int) -> list[list]:
    """Discard provider rounding outside interval; never tolerate gaps inside."""
    if frame not in FRAME_MS or type(rows) is not list or len(rows) > 200:
        raise ValueError("PUBLIC_DELTA_INVALID_RESPONSE")
    step = FRAME_MS[frame]
    expected = list(range(first, last + step, step))
    selected: dict[int, list] = {}
    for row in rows:
        if type(row) is not list or len(row) < 7 or type(row[0]) not in (str, int):
            raise ValueError("PUBLIC_DELTA_INVALID_ROW")
        try:
            stamp = int(row[0])
        except ValueError:
            raise ValueError("PUBLIC_DELTA_INVALID_TIMESTAMP") from None
        if first <= stamp <= last:
            if stamp in selected:
                raise ValueError("PUBLIC_DELTA_DUPLICATE_TIMESTAMP")
            selected[stamp] = row
    if sorted(selected) != expected:
        raise ValueError("PUBLIC_DELTA_MISSING_OR_EXTRA_CANDLE")
    # Prior to merging, verify OHLC, volumes, time alignment and closed-only
    # with the existing central validator, not another indicator formula.
    closed = _closed_rows(list(selected.values()), frame, len(expected), last + step)
    return closed


def fetch_and_merge(previous, *, target_asof_ms: int, public_get):
    """Return a new immutable batch and read-only GET count; no persistence."""
    needed = delta_plan(previous, target_asof_ms)
    request_count = 0
    received = {}
    for symbol in previous.symbols:
        frames = needed.get(symbol)
        if frames is None:
            continue
        received[symbol] = {}
        for frame, (first, last) in frames.items():
            if request_count >= MAX_PUBLIC_DELTA_GETS:
                raise ValueError("PUBLIC_DELTA_GET_BUDGET_EXCEEDED")
            request_count += 1
            rows = public_get(symbol, frame, first, last)
            received[symbol][frame] = _exact_delta(rows, frame, first, last)
    merged = merge_delta(previous, target_asof_ms, received)
    if merged.classification != "PROVISIONAL_NOT_TRADE_APPROVED":
        raise ValueError("PUBLIC_DELTA_UNEXPECTED_APPROVAL")
    for lane in LANES:
        body, digest = merged.for_provider(lane)
        if body != merged.canonical_bytes or digest != merged.sha256_hex:
            raise ValueError("PUBLIC_DELTA_AI_DATA_MISMATCH")
    return merged, request_count


def selftest() -> int:
    frame4h = FRAME_MS["4h"]
    asof = (1795000000000 // frame4h) * frame4h - 5 * 60_000
    target = asof + 10 * 60_000
    required = {"1m": 60, "15m": 30, "1h": 24, "4h": 16}
    symbols = ["BTCUSDT"] + [f"T{i}USDT" for i in range(1, 23)] + [
        "XAUUSDT", "XAGUSDT",
    ]
    assert len(symbols) == 25
    def candle(t):
        return [str(t), "100", "102", "98", "101", "3", "300"]
    data = {}
    for symbol in symbols:
        data[symbol] = {}
        for frame, step in FRAME_MS.items():
            end = asof // step * step - step
            data[symbol][frame] = [
                candle(end - (required[frame] - 1 - i) * step)
                for i in range(required[frame])
            ]
    initial = freeze_market_batch(
        data, required, asof_ms=asof, source_id="bitget.v2.synthetic-delta",
    )
    calls = []
    def fake_get(symbol, frame, first, last):
        calls.append((symbol, frame, first, last))
        step = FRAME_MS[frame]
        # Bitget sometimes includes an older/newer period due to rounding.
        return [candle(t) for t in range(
            last + step, first - step - 1, -step
        )]
    updated, total = fetch_and_merge(
        initial, target_asof_ms=target, public_get=fake_get,
    )
    assert total == len(calls) == 100
    assert updated.asof_ms == target
    assert updated.symbols == initial.symbols
    assert updated.sha256_hex != initial.sha256_hex
    assert initial.asof_ms == asof
    assert updated.for_provider("deepseek") == updated.for_provider("qwen")
    assert updated.for_provider("qwen") == updated.for_provider("minimax")

    def missing_get(symbol, frame, first, last):
        rows = fake_get(symbol, frame, first, last)
        return rows[:-2] if symbol == "XAGUSDT" and frame == "1m" else rows
    try:
        fetch_and_merge(initial, target_asof_ms=target,
                        public_get=missing_get)
    except ValueError as exc:
        assert str(exc) == "PUBLIC_DELTA_MISSING_OR_EXTRA_CANDLE"
    else:
        raise AssertionError("GAP_SILENTLY_ACCEPTED")

    def duplicate_get(symbol, frame, first, last):
        rows = fake_get(symbol, frame, first, last)
        if symbol == "BTCUSDT" and frame == "1m":
            rows.append(rows[1][:])
        return rows
    try:
        fetch_and_merge(initial, target_asof_ms=target,
                        public_get=duplicate_get)
    except ValueError as exc:
        assert str(exc) == "PUBLIC_DELTA_DUPLICATE_TIMESTAMP"
    else:
        raise AssertionError("DUPLICATE_SILENTLY_ACCEPTED")

    def invalid_ohlc_get(symbol, frame, first, last):
        rows = fake_get(symbol, frame, first, last)
        if symbol == "BTCUSDT" and frame == "1m":
            rows[1][2] = "0"
        return rows
    try:
        fetch_and_merge(initial, target_asof_ms=target,
                        public_get=invalid_ohlc_get)
    except ValueError as exc:
        assert str(exc) == "INVALID_OHLC"
    else:
        raise AssertionError("INVALID_OHLC_SILENTLY_ACCEPTED")

    # The data owner is responsible for cache bootstrap; this function is
    # not allowed to silently rebootstrap when previous history is stale.
    try:
        fetch_and_merge(initial, target_asof_ms=asof + 31 * 60_000,
                        public_get=fake_get)
    except ValueError as exc:
        assert str(exc) == "CACHE_TOO_OLD_REBOOTSTRAP_REQUIRED"
    else:
        raise AssertionError("EXPIRED_CACHE_SILENTLY_ACCEPTED")

    print("ARENA_DELTA SELFTEST=PASS_OFFLINE", flush=True)
    print("ARENA_DELTA synthetic_markets=25 simulated_delta_GETs=100", flush=True)
    print("ARENA_DELTA verified_gap_duplicate_OHLC_expiry=YES", flush=True)
    print("ARENA_DELTA actual_public_GETs=0 paid_AI_calls=0 orders=0", flush=True)
    return 0


def probe_public_btc() -> int:
    """Public fresh-candle availability only; deliberately no cache writes."""
    history = _history_module()
    asof = int(time.time() * 1000)
    count = 0
    print("ARENA_DELTA mode=PUBLIC_BTC_PROBE_READ_ONLY max_GETs=4",
          flush=True)
    for frame, step in FRAME_MS.items():
        if count >= MAX_PUBLIC_PROBE_GETS:
            raise ValueError("PUBLIC_PROBE_BUDGET_EXCEEDED")
        last = asof // step * step - step
        count += 1
        try:
            rows = history._public_get("BTCUSDT", frame, last, last)
            exact = _exact_delta(rows, frame, last, last)
        except ValueError as exc:
            reason = str(exc)
            if not re.fullmatch(r"[A-Z0-9_]+", reason):
                reason = "UNVERIFIED_PUBLIC_DATA"
            print("ARENA_DELTA public_GETs=" + str(count), flush=True)
            print("ARENA_DELTA RESULT=NOT_VERIFIED_" + reason,
                  flush=True)
            return 2
        assert len(exact) == 1
        print("ARENA_DELTA BTCUSDT_" + frame + "_CLOSED=VERIFIED",
              flush=True)
        time.sleep(0.15)
    print("ARENA_DELTA public_GETs=" + str(count), flush=True)
    print("ARENA_DELTA paid_AI_calls=0 orders=0 services_changed=0",
          flush=True)
    print("ARENA_DELTA RESULT=BTC_DELTA_SOURCE_VERIFIED_NO_DEPLOY",
          flush=True)
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    if sys.argv[1:] == ["--probe"]:
        sys.exit(probe_public_btc())
    print("ARENA_DELTA RESULT=USE_SELFTEST_OR_PROBE")
    sys.exit(2)
