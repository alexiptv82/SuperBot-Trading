"""Mirrored barriers and seeded within-segment circular controls."""
from __future__ import annotations

import random
from collections.abc import Sequence
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from backend.v3.learning.opportunity import Candidate, _check_candidate
from backend.v3.features.indicators import check_bars
from backend.v3.detectors.common import build_candidates, check_candle_ms, check_risk, check_symbol

_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)


def _candidates(candidates):
    if not isinstance(candidates, Sequence):
        raise ValueError('invalid_candidates')
    seen = set()
    try:
        for c in candidates:
            _check_candidate(c, seen)
    except ValueError:
        raise ValueError('invalid_candidates') from None


def invert_candidates(candidates):
    _candidates(candidates)
    try:
        with localcontext(_CTX):
            out = []
            skipped = 0
            for c in candidates:
                stop = Decimal('2') * c.entry_price - c.stop_price
                target = Decimal('2') * c.entry_price - c.target_price
                inverse = Candidate('INV:' + c.candidate_id, c.symbol, -c.side,
                                    c.signal_time_ms, c.entry_price, stop, target)
                try:
                    _check_candidate(inverse, set())
                except ValueError:
                    skipped += 1
                    continue
                out.append(inverse)
            return tuple(out), skipped
    except ArithmeticError:
        raise ValueError('numeric_out_of_range') from None


def sides_from_candidates(bars, candidates, *, candle_ms):
    check_candle_ms(candle_ms)
    check_bars(bars, candle_ms=candle_ms)
    _candidates(candidates)
    sides = [0] * len(bars)
    for c in candidates:
        if not bars:
            raise ValueError('invalid_candidates')
        offset = c.signal_time_ms - candle_ms - bars[0].open_time_ms
        i, remainder = divmod(offset, candle_ms)
        if remainder or not 0 <= i < len(bars) or sides[i] != 0:
            raise ValueError('invalid_candidates')
        sides[i] = c.side
    return sides


def shifted_sides(sides, k):
    if not isinstance(sides, Sequence) or any(type(v) is not int or v not in (-1, 0, 1) for v in sides):
        raise ValueError('invalid_sides')
    if type(k) is not int or k < 0:
        raise ValueError('invalid_shift')
    out = [0] * len(sides)
    for i, v in enumerate(sides):
        out[(i + k) % len(sides)] = v
    return out


def shifted_candidate_sets(symbol, segments, candidates, *, strategy_id, risk,
                           candle_ms, n_shifts, min_shift_bars, seed):
    check_candle_ms(candle_ms)
    check_symbol(symbol)
    check_risk(risk)
    if type(n_shifts) is not int or n_shifts < 1 or type(min_shift_bars) is not int or min_shift_bars < 1 or type(seed) is not int:
        raise ValueError('invalid_shift')
    _candidates(candidates)
    if not isinstance(segments, Sequence):
        raise ValueError('invalid_candidates')
    locations = {}
    groups = [[] for _ in segments]
    for j, segment in enumerate(segments):
        check_bars(segment, candle_ms=candle_ms)
        for b in segment:
            if b.open_time_ms in locations:
                raise ValueError('invalid_candidates')
            locations[b.open_time_ms] = j
    for c in candidates:
        t = c.signal_time_ms - candle_ms
        if c.symbol != symbol or t not in locations:
            raise ValueError('invalid_candidates')
        groups[locations[t]].append(c)
    eligible = []
    for segment, group in zip(segments, groups):
        sides = sides_from_candidates(segment, group, candle_ms=candle_ms)
        if len(segment) >= 2 * min_shift_bars:
            eligible.append((segment, sides))
    rng = random.Random(f'{seed}|{strategy_id}|{symbol}')
    sets = []
    for _ in range(n_shifts):
        out = []
        for segment, sides in eligible:
            k = rng.randrange(min_shift_bars, len(segment) - min_shift_bars + 1)
            out.extend(build_candidates(symbol, segment, shifted_sides(sides, k),
                                        strategy_id=strategy_id, risk=risk, candle_ms=candle_ms))
        sets.append(tuple(sorted(out, key=lambda c: c.signal_time_ms)))
    return tuple(sets)
