"""Fast, deterministic five-minute *observer* for already-closed 1m candles.

No network calls, AI calls, order execution, journal writes, risk bypasses or
new policy. This is a priority list for human/AI observation, NOT a trade signal.
The runner's configured 60-minute cycle is unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext, InvalidOperation, Overflow
from typing import Mapping, Sequence
import re

from backend.v3.features.indicators import Bar, check_bars

STEP_MS = 60_000
SCAN_MS = 300_000
_MIN_BARS = 25
_PATTERN = re.compile(r"^[A-Z0-9]{2,20}USDT$")


@dataclass(frozen=True)
class Candidate:
    symbol: str
    side_bias: str           # LONG/SHORT: observational only
    move_5m_bps: Decimal
    volume_ratio: Decimal    # mean last 5m / mean preceding 15m
    rank_score: Decimal      # relative heuristic, NOT probability/edge
    snapshot_end_ms: int


@dataclass(frozen=True)
class ScanReport:
    slot: int
    candidates: tuple[Candidate, ...]
    excluded: tuple[tuple[str, str], ...]
    observational_only: bool = True


def slot_due(now_ms: int, previous_slot: int | None) -> int | None:
    """Single five-minute slot per timestamp; caller stores last executed slot.

    Returns None when called again in the same slot. Does not run any work.
    """
    if type(now_ms) is not int or now_ms <= 0 or (previous_slot is not None and
            (type(previous_slot) is not int or previous_slot < 0)):
        raise ValueError("invalid_scan_clock")
    slot = now_ms // SCAN_MS
    if previous_slot is not None and slot <= previous_slot:
        return None
    return slot


def _candidate(symbol: str, bars: Sequence[Bar], now_ms: int) -> tuple[Candidate | None, str | None]:
    if not isinstance(bars, (tuple, list)) or len(bars) < _MIN_BARS:
        return None, "short_history"
    # 1m bars must be strictly contiguous, closed, valid. Only inspect the
    # last 25 bars rather than reprocessing a multi-thousand-bar L5 history.
    tail = list(bars[-_MIN_BARS:])
    try:
        check_bars(tail, candle_ms=STEP_MS)
    except (ValueError, ArithmeticError, TypeError):
        return None, "invalid_candles"
    last_end = tail[-1].open_time_ms + STEP_MS
    if last_end > now_ms:
        return None, "unclosed_candle"
    if now_ms - last_end >= 2 * STEP_MS:
        return None, "stale_candles"
    try:
        with localcontext() as ctx:
            ctx.prec = 40
            first = tail[-6].close
            last = tail[-1].close
            change = (last / first - Decimal(1)) * Decimal(10000)
            v_now = sum((b.volume for b in tail[-5:]), Decimal(0)) / 5
            v_prev = sum((b.volume for b in tail[-20:-5]), Decimal(0)) / 15
            if v_prev <= 0:
                return None, "no_volume_baseline"
            volume_ratio = v_now / v_prev
            if change == 0:
                return None, "flat_price"
            # Deterministic relative sorting, not predicted profitability.
            score = abs(change) * min(volume_ratio, Decimal(4))
    except (InvalidOperation, Overflow, ArithmeticError):
        return None, "invalid_arithmetic"
    return Candidate(symbol, "LONG" if change > 0 else "SHORT", change,
                     volume_ratio, score, last_end), None


def scan_closed_minutes(*, now_ms: int, bars_by_symbol: Mapping[str, Sequence[Bar]],
                        previous_slot: int | None = None, top_k: int = 5) -> ScanReport | None:
    """Rank candidates supplied by an external 1m cache; no side effects.

    The caller is responsible for collecting 1m data within its existing feed
    budget. Errors are recorded per symbol instead of converting to fake prices.
    """
    slot = slot_due(now_ms, previous_slot)
    if slot is None:
        return None
    if not isinstance(bars_by_symbol, Mapping) or type(top_k) is not int or not 1 <= top_k <= 50:
        raise ValueError("invalid_scan_input")
    ranked: list[Candidate] = []
    excluded: list[tuple[str, str]] = []
    seen: set[str] = set()
    for symbol, bars in bars_by_symbol.items():
        if type(symbol) is not str or not _PATTERN.fullmatch(symbol) or symbol in seen:
            raise ValueError("invalid_scan_symbol")
        seen.add(symbol)
        candidate, reason = _candidate(symbol, bars, now_ms)
        if candidate is not None:
            ranked.append(candidate)
        else:
            excluded.append((symbol, reason or "unknown"))
    ranked.sort(key=lambda c: (-c.rank_score, c.symbol))
    return ScanReport(slot, tuple(ranked[:top_k]), tuple(sorted(excluded)))
