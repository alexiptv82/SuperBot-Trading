"""Causal higher-timeframe market observations for PAPER AI contexts.

This is strictly read-only evidence, not an entry signal, trading filter,
probability, or independent permission to reduce/close positions. Missing or
bad input is explicit. All calculations use closed OHLCV candles only.
"""
import math

FRAMES = {'15m': 900000, '1H': 3600000, '4H': 14400000}
WINDOW = 24


def _frame(rows, now_ms, duration):
    if not isinstance(rows, (list, tuple)) or not rows:
        return {'status': 'unavailable', 'reason': 'missing'}
    if len(rows) > 2000:
        return {'status': 'unavailable', 'reason': 'too_many_bars'}
    closed = []
    prior = None
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            return {'status': 'unavailable', 'reason': 'invalid_bars'}
        try:
            ts = float(row[0])
            values = [float(x) for x in row[1:6]]
        except (ValueError, TypeError, OverflowError):
            return {'status': 'unavailable', 'reason': 'invalid_bars'}
        if (not math.isfinite(ts) or not all(math.isfinite(x) for x in values)
                or ts != int(ts) or int(ts) % duration != 0
                or (prior is not None and ts <= prior)):
            return {'status': 'unavailable', 'reason': 'invalid_bars'}
        prior = ts
        o, h, l, c, v = values
        if min(o, l, c) <= 0 or h < max(o, c) or l > min(o, c) or v < 0:
            return {'status': 'unavailable', 'reason': 'invalid_bars'}
        if ts + duration <= now_ms:
            closed.append((int(ts), o, h, l, c, v))
    if len(closed) < WINDOW:
        return {'status': 'unavailable', 'reason': 'insufficient_closed_bars'}
    tail = closed[-WINDOW:]
    if any(tail[i][0] - tail[i-1][0] != duration for i in range(1, WINDOW)):
        return {'status': 'unavailable', 'reason': 'candle_gap'}
    latest = tail[-1][0] + duration
    if now_ms - latest > 2 * duration:
        return {'status': 'unavailable', 'reason': 'stale', 'data_cutoff_ms': latest}
    previous = tail[-13][4]
    pct = (tail[-1][4] / previous - 1) * 100
    prior_high = max(r[2] for r in tail[-13:-1])
    prior_low = min(r[3] for r in tail[-13:-1])
    close = tail[-1][4]
    relative = 'above' if close > prior_high else 'below' if close < prior_low else 'inside'
    return {'status': 'available', 'data_cutoff_ms': latest,
            'observed_return_pct_12bars': round(pct, 4),
            'close_vs_prior_12bar_range': relative,
            'bars_used': WINDOW, 'age_ms': now_ms - latest,
            'range_is_not_predictive': True}


def project_closed_mtf(market, now_ms):
    """Bounded, deterministic context; never influences eligibility or risk."""
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError('invalid_mtf_clock')
    bars = market.get('bars') if isinstance(market, dict) else None
    bars = bars if isinstance(bars, dict) else {}
    result = {frame: _frame(bars.get(frame), now_ms, duration)
              for frame, duration in FRAMES.items()}
    ready = sum(x['status'] == 'available' for x in result.values())
    return {'kind': 'closed_mtf_v1', 'authority': 'advisory_only',
            'may_authorize_entry': False, 'may_block_entry': False,
            'may_modify_scores': False, 'may_execute_exit': False,
            'status': 'available' if ready == len(FRAMES) else 'partial' if ready else 'unavailable',
            'as_of_ms': now_ms, 'timeframes': result,
            'no_trade_or_hold_not_required_by_missing_mtf': True}
