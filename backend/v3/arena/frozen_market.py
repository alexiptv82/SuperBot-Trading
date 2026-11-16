"""Immutable, causal research snapshot shared by the three Arena analysts.

No I/O, network, accounts or orders. This module only validates supplied
closed-candle rows; the caller must supply vetted asset identity separately.
Outputs are always PROVISIONAL_NOT_TRADE_APPROVED, even when all bars pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Mapping
import json
import re

SCHEMA = "arena_frozen_market_v1"
FRAME_MS = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
AI_LANES = ("deepseek", "qwen", "minimax")
SYMBOL = re.compile(r"[A-Z0-9]{2,20}USDT\Z")


@dataclass(frozen=True)
class FrozenMarketBatch:
    asof_ms: int
    symbols: tuple[str, ...]
    sha256_hex: str
    canonical_bytes: bytes
    classification: str = "PROVISIONAL_NOT_TRADE_APPROVED"

    def verify(self) -> None:
        if (type(self.canonical_bytes) is not bytes
                or len(self.canonical_bytes) == 0
                or sha256(self.canonical_bytes).hexdigest() != self.sha256_hex):
            raise ValueError("SNAPSHOT_INTEGRITY_FAILURE")
        try:
            decoded = json.loads(self.canonical_bytes)
        except (ValueError, UnicodeDecodeError):
            raise ValueError("SNAPSHOT_INTEGRITY_FAILURE") from None
        if (type(decoded) is not dict or decoded.get("schema") != SCHEMA
                or decoded.get("asof_ms") != self.asof_ms
                or tuple(decoded.get("symbols", ())) != self.symbols
                or decoded.get("classification") != self.classification
                or self.classification != "PROVISIONAL_NOT_TRADE_APPROVED"):
            raise ValueError("SNAPSHOT_SCOPE_MISMATCH")

    def for_provider(self, provider: str) -> tuple[bytes, str]:
        """Same bytes + immutable hash for every model. No provider mutation."""
        if provider not in AI_LANES:
            raise ValueError("UNTRUSTED_ARENA_PROVIDER")
        self.verify()
        return self.canonical_bytes, self.sha256_hex


def _decimal_text(value: object) -> str:
    if type(value) not in (str, int):
        raise ValueError("CANDLE_NUMBER_TYPE")
    if type(value) is str and len(value) > 80:
        raise ValueError("CANDLE_NUMBER_SIZE")
    try:
        num = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError("CANDLE_INVALID_NUMBER") from None
    if not num.is_finite() or num.adjusted() < -100 or num.adjusted() > 100:
        raise ValueError("CANDLE_UNSAFE_NUMBER")
    return format(num.normalize(), "f") if num else "0"


def _closed_rows(rows: object, frame: str, required: int, asof_ms: int) -> list[list]:
    if frame not in FRAME_MS or type(rows) not in (list, tuple):
        raise ValueError("UNSUPPORTED_FRAME_OR_ROWS")
    step = FRAME_MS[frame]
    if len(rows) > 6000 or type(required) is not int or not 1 <= required <= 6000:
        raise ValueError("INVALID_HISTORY_SIZE")
    seen: set[int] = set()
    selected: list[list] = []
    for raw in rows:
        if type(raw) not in (list, tuple) or len(raw) < 7:
            raise ValueError("MALFORMED_CANDLE")
        try:
            if type(raw[0]) not in (int, str):
                raise ValueError()
            stamp = int(raw[0])
        except ValueError:
            raise ValueError("MALFORMED_CANDLE_TIME") from None
        if stamp <= 0 or stamp % step != 0 or stamp in seen:
            raise ValueError("DUPLICATE_OR_MISALIGNED_CANDLE")
        seen.add(stamp)
        nums = tuple(Decimal(_decimal_text(x)) for x in raw[1:7])
        o, h, l, c, base, quote = nums
        if (min(o, h, l, c) <= 0 or h < max(o, c)
                or l > min(o, c) or h < l or min(base, quote) < 0):
            raise ValueError("INVALID_OHLC")
        if stamp + step <= asof_ms:
            selected.append([stamp, *(_decimal_text(x) for x in raw[1:7])])
        elif stamp > asof_ms:
            raise ValueError("FUTURE_CANDLE")
        # A forming candle at asof may exist but is never frozen.
    selected.sort(key=lambda row: row[0])
    if len(selected) < required:
        raise ValueError("INSUFFICIENT_FULL_BRAIN_HISTORY")
    selected = selected[-required:]
    if any(b[0] - a[0] != step for a, b in zip(selected, selected[1:])):
        raise ValueError("GAP_IN_CLOSED_HISTORY")
    # The last completed candle must be the last expected closed interval
    # at asof, so we never claim a stale market as 'ready'.
    expected_last = asof_ms // step * step - step
    if selected[-1][0] != expected_last:
        raise ValueError("STALE_SNAPSHOT_HISTORY")
    return selected


def freeze_market_batch(
    candles_by_symbol: Mapping[str, Mapping[str, object]],
    required_by_frame: Mapping[str, int],
    *, asof_ms: int,
    source_id: str,
) -> FrozenMarketBatch:
    """A deterministic identical market input for DeepSeek, Qwen, MiniMax.

    Does not call external data sources or generate any trading decision.
    Native/wrapped/stablecoin classification is NOT certified in this step.
    """
    if (type(asof_ms) is not int or asof_ms <= 0
            or type(source_id) is not str or not re.fullmatch(r"[a-z0-9_.:-]{1,80}", source_id)
            or not isinstance(candles_by_symbol, Mapping)
            or not 1 <= len(candles_by_symbol) <= 25
            or not isinstance(required_by_frame, Mapping)
            or set(required_by_frame) != set(FRAME_MS)):
        raise ValueError("INVALID_SNAPSHOT_REQUEST")
    symbols = tuple(sorted(candles_by_symbol))
    if any(type(s) is not str or SYMBOL.fullmatch(s) is None for s in symbols):
        raise ValueError("INVALID_SNAPSHOT_SYMBOL")
    verified = {}
    for symbol in symbols:
        views = candles_by_symbol[symbol]
        if not isinstance(views, Mapping) or set(views) != set(FRAME_MS):
            raise ValueError("INCOMPLETE_SYMBOL_TIMEFRAMES")
        verified[symbol] = {
            frame: _closed_rows(views[frame], frame, required_by_frame[frame], asof_ms)
            for frame in FRAME_MS
        }
    doc = {
        "schema": SCHEMA, "asof_ms": asof_ms, "source_id": source_id,
        "classification": "PROVISIONAL_NOT_TRADE_APPROVED",
        "symbols": symbols, "required": dict(required_by_frame),
        "candles": verified,
    }
    canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("utf-8")
    batch = FrozenMarketBatch(asof_ms, symbols, sha256(canonical).hexdigest(), canonical)
    batch.verify()
    return batch
