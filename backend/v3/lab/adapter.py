"""P5 labels to P3 outcomes. All validation precedes arithmetic, in contract order."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from backend.v3.learning.opportunity import Candidate, HorizonLabel, OpportunityLabel
from backend.v3.outcomes import SCHEMA_VERSION, TradeOutcome

_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)


def _q4(d):
    r = d.quantize(Decimal('0.0001'))
    return abs(r) if r == 0 else r


def _q8(d):
    r = d.quantize(Decimal('0.00000001'))
    return abs(r) if r == 0 else r


def _finite(d):
    return isinstance(d, Decimal) and d.is_finite()


def outcomes_from_labels(candidates, labels, *, strategy_id, run_id, horizon_ms,
                         candle_ms, cost_bp, unit_notional, regimes):
    if type(candle_ms) is not int or candle_ms < 1:
        raise ValueError('invalid_candle_ms')
    if type(horizon_ms) is not int or horizon_ms <= 0 or horizon_ms % candle_ms:
        raise ValueError('invalid_horizon')
    if not _finite(cost_bp) or cost_bp < 0:
        raise ValueError('invalid_cost_bp')
    if not _finite(unit_notional) or unit_notional <= 0:
        raise ValueError('invalid_unit_notional')
    if type(strategy_id) is not str or re.fullmatch(r'S\d{2}', strategy_id) is None:
        raise ValueError('invalid_strategy_id')
    if type(run_id) is not str or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}', run_id) is None:
        raise ValueError('invalid_run_id')
    if not isinstance(candidates, Sequence) or not isinstance(labels, Sequence) or len(candidates) != len(labels):
        raise ValueError('invalid_labels')
    pairs = tuple(zip(candidates, labels))
    for c, label in pairs:
        if not isinstance(c, Candidate) or not isinstance(label, OpportunityLabel):
            raise ValueError('invalid_labels')
        if (c.candidate_id, c.symbol, c.side) != (label.candidate_id, label.symbol, label.side):
            raise ValueError('invalid_labels')
        if type(c.side) is not int or c.side not in (-1, 1) or type(label.side) is not int:
            raise ValueError('invalid_labels')
        if type(c.signal_time_ms) is not int or c.signal_time_ms <= 0 or not all(_finite(x) and x > 0 for x in (c.entry_price, c.stop_price, c.target_price)):
            raise ValueError('invalid_labels')
    selected = []
    for c, label in pairs:
        if not isinstance(label.horizons, Sequence) or not all(isinstance(h, HorizonLabel) and type(h.horizon_ms) is int for h in label.horizons):
            raise ValueError('invalid_horizon_in_labels')
        matches = [h for h in label.horizons if h.horizon_ms == horizon_ms]
        if len(matches) != 1:
            raise ValueError('invalid_horizon_in_labels')
        h = matches[0]
        if h.status not in ('complete', 'incomplete'):
            raise ValueError('invalid_labels')
        if h.status == 'complete':
            if h.barrier not in ('target', 'stop', 'timeout') or not all(_finite(x) for x in (h.exit_price, h.gross_bp, h.net_bp)):
                raise ValueError('invalid_labels')
            if h.barrier != 'timeout' and (type(h.touch_time_ms) is not int or h.touch_time_ms < 0):
                raise ValueError('invalid_labels')
        selected.append((c, h))
    if not isinstance(regimes, Mapping) or any(type(k) is not int or type(v) is not str for k, v in regimes.items()):
        raise ValueError('missing_regime')
    for c, h in selected:
        if h.status == 'complete' and c.signal_time_ms - candle_ms not in regimes:
            raise ValueError('missing_regime')
    try:
        with localcontext(_CTX):
            out = []
            incomplete = 0
            for c, h in selected:
                if h.status == 'incomplete':
                    incomplete += 1
                    continue
                start = ((c.signal_time_ms + candle_ms - 1) // candle_ms) * candle_ms
                closed = h.touch_time_ms + candle_ms if h.barrier in ('target', 'stop') else start + horizon_ms
                distance = abs(c.entry_price - c.stop_price) / c.entry_price * Decimal('10000')
                gross = _q8(unit_notional * h.gross_bp / Decimal('10000'))
                fees = _q8(unit_notional * cost_bp / Decimal('10000'))
                realized = gross - fees
                out.append(TradeOutcome(
                    schema_version=SCHEMA_VERSION, position_id=c.candidate_id, portfolio_id='lab',
                    run_id=run_id, symbol=c.symbol, side=c.side, originating_ai=strategy_id, leverage=1,
                    opened_at_ms=c.signal_time_ms, closed_at_ms=closed, hold_ms=closed - c.signal_time_ms,
                    entry_price=c.entry_price, exit_price=h.exit_price, quantity=_q8(unit_notional / c.entry_price),
                    notional_entry=unit_notional, margin_used=unit_notional, gross_pnl=gross, fees=fees,
                    realized_pnl=realized, gross_bp=h.gross_bp, costs_bp=cost_bp, net_bp=h.net_bp,
                    stop_distance_bp=_q4(distance), r_multiple=_q4(h.net_bp / distance),
                    exit_reason='stop' if h.barrier == 'stop' else 'brain_close',
                    loss_exceeds_margin=realized < -unit_notional, decision_event_id=c.candidate_id,
                    link_status='linked', decision_regime=regimes[c.signal_time_ms - candle_ms]))
            return tuple(out), incomplete
    except ArithmeticError:
        raise ValueError('numeric_out_of_range') from None
