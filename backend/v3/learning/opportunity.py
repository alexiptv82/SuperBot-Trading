"""Opportunity labeling (F7 P5).

Modulo puro: etichetta candidati a posteriori su candele.
Nessuna I/O, rete, orologio, casualità. Nessuna soglia nel codice.

Limite noto: non si modellano gap né slippage. L'uscita a stop/target
è esattamente al livello dichiarato.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, Context
from typing import Mapping, Optional, Sequence

_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)
_Q4 = Decimal("0.0001")
_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")


def _q4(d: Decimal) -> Decimal:
    return d.quantize(_Q4, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class Candle:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    symbol: str
    side: int
    signal_time_ms: int
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal


@dataclass(frozen=True)
class HorizonLabel:
    horizon_ms: int
    status: str
    barrier: Optional[str]
    ambiguous: bool
    touch_time_ms: Optional[int]
    exit_price: Optional[Decimal]
    gross_bp: Optional[Decimal]
    net_bp: Optional[Decimal]


@dataclass(frozen=True)
class OpportunityLabel:
    candidate_id: str
    symbol: str
    side: int
    horizons: tuple[HorizonLabel, ...]


def _finite(d) -> bool:
    return isinstance(d, Decimal) and d.is_finite()


def _validate(candidates, candles, candle_ms, horizons_ms, cost_bp, ambiguous_policy):
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError("invalid_candle_ms")
    if not isinstance(horizons_ms, (list, tuple)) or not horizons_ms:
        raise ValueError("invalid_horizons")
    prev = 0
    for h in horizons_ms:
        if type(h) is not int or h <= 0 or h % candle_ms != 0 or h <= prev:
            raise ValueError("invalid_horizons")
        prev = h
    if not isinstance(cost_bp, Decimal) or not cost_bp.is_finite() or cost_bp < 0:
        raise ValueError("invalid_cost_bp")
    if ambiguous_policy not in ("stop_first", "target_first"):
        raise ValueError("invalid_ambiguous_policy")
    if candidates is None or not hasattr(candidates, "__iter__") or isinstance(candidates, (str, bytes)):
        raise ValueError("invalid_candidate")
    try:
        cands = list(candidates)
    except Exception:
        raise ValueError("invalid_candidate")
    seen = set()
    for c in cands:
        if not isinstance(c, Candidate):
            raise ValueError("invalid_candidate")
        if not isinstance(c.candidate_id, str) or not _ID_RE.match(c.candidate_id):
            raise ValueError("invalid_candidate")
        if c.candidate_id in seen:
            raise ValueError("invalid_candidate")
        seen.add(c.candidate_id)
        if not isinstance(c.symbol, str) or not c.symbol:
            raise ValueError("invalid_candidate")
        if type(c.side) is not int or c.side not in (-1, 1):
            raise ValueError("invalid_candidate")
        if type(c.signal_time_ms) is not int or c.signal_time_ms <= 0:
            raise ValueError("invalid_candidate")
        for p in (c.entry_price, c.stop_price, c.target_price):
            if not _finite(p) or p <= 0:
                raise ValueError("invalid_candidate")
        if c.side == 1:
            if not (c.stop_price < c.entry_price < c.target_price):
                raise ValueError("invalid_candidate")
        else:
            if not (c.target_price < c.entry_price < c.stop_price):
                raise ValueError("invalid_candidate")
    if not isinstance(candles, Mapping):
        raise ValueError("invalid_candles")
    for sym, series in candles.items():
        if not isinstance(sym, str):
            raise ValueError("invalid_candles")
        if series is None or not hasattr(series, "__iter__") or isinstance(series, (str, bytes)):
            raise ValueError("invalid_candles")
        try:
            cnds = list(series)
        except Exception:
            raise ValueError("invalid_candles")
        prev_t = -1
        for cn in cnds:
            if not isinstance(cn, Candle):
                raise ValueError("invalid_candles")
            for p in (cn.open, cn.high, cn.low, cn.close):
                if not _finite(p) or p <= 0:
                    raise ValueError("invalid_candles")
            if cn.low > min(cn.open, cn.close) or cn.high < max(cn.open, cn.close):
                raise ValueError("invalid_candles")
            if type(cn.open_time_ms) is not int or cn.open_time_ms < 0 or cn.open_time_ms % candle_ms != 0:
                raise ValueError("invalid_candles")
            if cn.open_time_ms <= prev_t:
                raise ValueError("invalid_candles")
            prev_t = cn.open_time_ms


def label_candidates(
    candidates: Sequence[Candidate],
    candles: Mapping[str, Sequence[Candle]],
    *,
    candle_ms: int,
    horizons_ms: Sequence[int],
    cost_bp: Decimal,
    ambiguous_policy: str,
) -> tuple[OpportunityLabel, ...]:
    _validate(candidates, candles, candle_ms, horizons_ms, cost_bp, ambiguous_policy)
    cands = list(candidates)
    candle_map = {sym: list(series) for sym, series in candles.items()}

    results = []
    for c in cands:
        series = candle_map.get(c.symbol, [])
        by_time = {cn.open_time_ms: cn for cn in series}
        horizons = []
        for h in horizons_ms:
            n = h // candle_ms
            start = ((c.signal_time_ms + candle_ms - 1) // candle_ms) * candle_ms
            window_times = [start + i * candle_ms for i in range(n)]
            window = [by_time.get(t) for t in window_times]
            if any(w is None for w in window):
                horizons.append(HorizonLabel(h, "incomplete", None, False, None, None, None, None))
                continue
            barrier = None
            ambiguous = False
            touch_time = None
            exit_price = None
            for cn in window:
                if c.side == 1:
                    stop_hit = cn.low <= c.stop_price
                    target_hit = cn.high >= c.target_price
                else:
                    stop_hit = cn.high >= c.stop_price
                    target_hit = cn.low <= c.target_price
                if stop_hit or target_hit:
                    ambiguous = stop_hit and target_hit
                    if ambiguous:
                        barrier = "stop" if ambiguous_policy == "stop_first" else "target"
                    elif stop_hit:
                        barrier = "stop"
                    else:
                        barrier = "target"
                    exit_price = c.stop_price if barrier == "stop" else c.target_price
                    touch_time = cn.open_time_ms
                    break
            if barrier is None:
                barrier = "timeout"
                exit_price = window[-1].close
                touch_time = None
            gross = Decimal(c.side) * (exit_price - c.entry_price) / c.entry_price * Decimal(10000)
            net = gross - cost_bp
            horizons.append(HorizonLabel(
                h, "complete", barrier, ambiguous, touch_time, exit_price, _q4(gross), _q4(net),
            ))
        results.append(OpportunityLabel(c.candidate_id, c.symbol, c.side, tuple(horizons)))
    return tuple(results)
