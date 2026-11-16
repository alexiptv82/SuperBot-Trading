"""Bounded, causal gap recovery for *research* Arena historical snapshots.

Offline library: no HTTP, model API, orders, file writes, timers or services.
The caller supplies public closed Bitget candles, and persistence remains a
separate explicit decision. The existing <=30-minute delta path is untouched.

A data gap exceeding the retained history for a timeframe (normally 1m=60)
is explicitly REBASED to the latest full window; intervening 1m candles are
NOT claimed to be preserved. Trading approval is never created.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json

from backend.v3.arena.frozen_market import (
    FRAME_MS, FrozenMarketBatch, _closed_rows, freeze_market_batch,
)

MAX_GAP_MS = 72 * 60 * 60 * 1000
PAGE_BARS = 190
MAX_PUBLIC_GETS = 125
MAX_ASSETS = 25


@dataclass(frozen=True)
class PublicPage:
    symbol: str
    frame: str
    first_ms: int
    last_ms: int

    @property
    def expected_rows(self) -> int:
        return (self.last_ms - self.first_ms) // FRAME_MS[self.frame] + 1


@dataclass(frozen=True)
class RecoveryPlan:
    initial_sha256: str
    initial_asof_ms: int
    target_asof_ms: int
    pages: tuple[PublicPage, ...]
    rebased: tuple[tuple[str, str], ...]
    classification: str = "PROVISIONAL_NOT_TRADE_APPROVED"


def _verified_doc(previous: FrozenMarketBatch) -> dict:
    if type(previous) is not FrozenMarketBatch:
        raise ValueError("RECOVERY_INVALID_SNAPSHOT")
    previous.verify()
    doc = json.loads(previous.canonical_bytes)
    required = doc.get("required")
    candles = doc.get("candles")
    if (doc.get("classification") != "PROVISIONAL_NOT_TRADE_APPROVED"
            or not 1 <= len(previous.symbols) <= MAX_ASSETS
            or type(required) is not dict or set(required) != set(FRAME_MS)
            or any(type(n) is not int or not 1 <= n <= 6000
                   for n in required.values())
            or type(candles) is not dict or set(candles) != set(previous.symbols)
            or type(doc.get("source_id")) is not str):
        raise ValueError("RECOVERY_SNAPSHOT_SCOPE_INVALID")
    return doc


def recovery_plan(previous: FrozenMarketBatch,
                  target_asof_ms: int) -> RecoveryPlan:
    doc = _verified_doc(previous)
    if type(target_asof_ms) is not int or target_asof_ms <= previous.asof_ms:
        raise ValueError("RECOVERY_NONMONOTONIC_TIME")
    if target_asof_ms - previous.asof_ms > MAX_GAP_MS:
        raise ValueError("RECOVERY_TOO_OLD_MANUAL_REVIEW")
    required = doc["required"]
    pages = []
    rebased = []
    for symbol in previous.symbols:
        frames = doc["candles"][symbol]
        if type(frames) is not dict or set(frames) != set(FRAME_MS):
            raise ValueError("RECOVERY_MISSING_FRAME")
        for frame, step in FRAME_MS.items():
            prev_last = previous.asof_ms // step * step - step
            target_last = target_asof_ms // step * step - step
            if target_last <= prev_last:
                continue
            required_first = target_last - (required[frame] - 1) * step
            start = max(prev_last + step, required_first)
            if start > prev_last + step:
                rebased.append((symbol, frame))
            for first in range(start, target_last + step, PAGE_BARS * step):
                last = min(target_last, first + (PAGE_BARS - 1) * step)
                pages.append(PublicPage(symbol, frame, first, last))
                if len(pages) > MAX_PUBLIC_GETS:
                    raise ValueError("RECOVERY_PUBLIC_REQUEST_LIMIT")
    return RecoveryPlan(
        initial_sha256=previous.sha256_hex,
        initial_asof_ms=previous.asof_ms,
        target_asof_ms=target_asof_ms,
        pages=tuple(pages),
        rebased=tuple(rebased),
    )


def _validate_page(raw: object, page: PublicPage) -> list[list]:
    if type(raw) is not list or len(raw) > 200:
        raise ValueError("RECOVERY_PROVIDER_PAGE_INVALID")
    required = list(range(
        page.first_ms, page.last_ms + FRAME_MS[page.frame],
        FRAME_MS[page.frame],
    ))
    selected = {}
    for row in raw:
        if type(row) is not list or len(row) < 7 or type(row[0]) not in (str, int):
            raise ValueError("RECOVERY_PROVIDER_ROW_INVALID")
        try:
            stamp = int(row[0])
        except ValueError:
            raise ValueError("RECOVERY_PROVIDER_TIMESTAMP_INVALID") from None
        if page.first_ms <= stamp <= page.last_ms:
            if stamp in selected:
                raise ValueError("RECOVERY_DUPLICATE_CANDLE")
            selected[stamp] = row
    if sorted(selected) != required:
        raise ValueError("RECOVERY_CANDLES_INCOMPLETE")
    return _closed_rows(
        list(selected.values()), page.frame, len(required),
        page.last_ms + FRAME_MS[page.frame],
    )


def recover_gap(previous: FrozenMarketBatch, target_asof_ms: int,
                public_get: Callable[[str, str, int, int], list]
                ) -> tuple[FrozenMarketBatch, RecoveryPlan]:
    """No I/O beyond invoking the supplied public candle getter.

    If any symbol, page or timeframe fails, no snapshot is returned. The
    original snapshot is immutable; the caller must persist only on success.
    """
    if not callable(public_get):
        raise ValueError("RECOVERY_GETTER_MISSING")
    plan = recovery_plan(previous, target_asof_ms)
    doc = _verified_doc(previous)
    required = doc["required"]
    incoming: dict[str, dict[str, list]] = {
        symbol: {frame: [] for frame in FRAME_MS}
        for symbol in previous.symbols
    }
    for page in plan.pages:
        raw = public_get(page.symbol, page.frame, page.first_ms, page.last_ms)
        incoming[page.symbol][page.frame].extend(_validate_page(raw, page))
    rebase_set = set(plan.rebased)
    result_data = {}
    for symbol in previous.symbols:
        result_data[symbol] = {}
        for frame, step in FRAME_MS.items():
            old = doc["candles"][symbol][frame]
            last_before = previous.asof_ms // step * step - step
            last_after = target_asof_ms // step * step - step
            expected_count = max(0, (last_after - last_before) // step)
            data = incoming[symbol][frame]
            if (symbol, frame) in rebase_set:
                if len(data) != required[frame]:
                    raise ValueError("RECOVERY_REBASE_INCOMPLETE")
                candidate = data
            else:
                if len(data) != expected_count:
                    raise ValueError("RECOVERY_DELTA_INCOMPLETE")
                candidate = (old + data)[-required[frame]:]
            result_data[symbol][frame] = candidate
    result = freeze_market_batch(
        result_data, required, asof_ms=target_asof_ms,
        source_id=doc["source_id"],
    )
    if (result.symbols != previous.symbols
            or result.classification != plan.classification):
        raise ValueError("RECOVERY_SCOPE_CHANGED")
    for lane in ("deepseek", "qwen", "minimax"):
        content, digest = result.for_provider(lane)
        if content != result.canonical_bytes or digest != result.sha256_hex:
            raise ValueError("RECOVERY_PROVIDER_MISMATCH")
    return result, plan
