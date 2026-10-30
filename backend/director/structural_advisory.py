"""Experimental market structure observer. No orders, score changes or vetoes.

Version frozen before evaluation: two closed 15m bars beyond the previous
eight-bar range, buffered by 0.25 ATR14. Slow EMA12/24 context is descriptive,
never a condition to emit the fast observation. No predictive claim.
"""
import math

BAR_MS = 900000
MAX_AGE_MS = 1800000
VERSION = 'structure_15m_v1'


def closed_rows(rows, now_ms):
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError('invalid_clock')
    mapped = {}
    for source in rows:
        # Future/incomplete candle values must not affect current knowledge.
        ts = float(source[0])
        if not math.isfinite(ts) or ts != int(ts) or ts < 0 or ts % BAR_MS:
            raise ValueError('invalid_timestamp')
        if ts + BAR_MS > now_ms:
            continue
        row = [float(v) for v in source[:6]]
        if (len(row) != 6 or not all(math.isfinite(v) for v in row)
                or min(row[1:5]) <= 0 or row[2] < max(row[1], row[3], row[4])
                or row[3] > min(row[1], row[2], row[4]) or row[5] < 0):
            raise ValueError('invalid_ohlcv')
        key = int(ts)
        if key in mapped and mapped[key] != row:
            raise ValueError('conflicting_revision')
        mapped[key] = row
    rows = [mapped[k] for k in sorted(mapped)][-1000:]
    if not rows or any(b[0]-a[0] != BAR_MS for a, b in zip(rows, rows[1:])):
        raise ValueError('missing_history')
    if not 0 <= now_ms-(rows[-1][0]+BAR_MS) <= MAX_AGE_MS:
        raise ValueError('stale_history')
    return rows


def aggregate(rows, duration):
    groups = {}
    for row in rows:
        groups.setdefault(int(row[0])//duration, []).append(row)
    out = []
    count = duration//BAR_MS
    for key, group in sorted(groups.items()):
        if len(group) == count and group[0][0] == key*duration:
            out.append([key*duration, group[0][1], max(b[2] for b in group),
                        min(b[3] for b in group), group[-1][4], sum(b[5] for b in group)])
    return out


def _ema(values, period):
    value = values[0]
    for price in values[1:]:
        value += 2/(period+1)*(price-value)
    return value


def context(rows):
    if len(rows) < 48:
        return 'UNKNOWN'
    prices = [b[4] for b in rows]
    fast, slow = _ema(prices, 12), _ema(prices, 24)
    delta = (fast-slow)/slow
    return 'UP' if delta > 0.001 else 'DOWN' if delta < -0.001 else 'RANGE'


def observe_structure(symbol, rows, now_ms):
    try:
        if (not isinstance(symbol, str) or not symbol.isascii()
                or not symbol.isalnum() or not 1 <= len(symbol) <= 20):
            return None
        rows = closed_rows(rows, now_ms)
        if len(rows) < 32:
            return None
        # Both confirming closes compare to a range known before either bar.
        prior = rows[-10:-2]
        high, low = max(b[2] for b in prior), min(b[3] for b in prior)
        trs = [max(b[2]-b[3], abs(b[2]-a[4]), abs(b[3]-a[4]))
               for a, b in zip(rows[-17:-3], rows[-16:-2])]
        atr = sum(trs)/len(trs)
        last = [b[4] for b in rows[-2:]]
        up = min(last) > high+0.25*atr
        down = max(last) < low-0.25*atr
        phase = 'UP_REASSESSMENT' if up else 'DOWN_REASSESSMENT' if down else 'NO_BREAK'
        return {'kind': 'structural_market_advisory', 'version': VERSION,
                'symbol': symbol, 'observed_ms': int(rows[-1][0])+BAR_MS,
                'authority': 'advisory_only', 'may_authorize_entry': False,
                'may_block_entry': False, 'may_modify_scores': False,
                'phase': phase, 'context_1h': context(aggregate(rows, 3600000)),
                'context_4h': context(aggregate(rows, 14400000)),
                'range_high': high, 'range_low': low, 'atr_15m': atr,
                'confirmed_closes': last, 'evidence_bars': len(rows),
                'predictive_value': 'not_demonstrated'}
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def project_advisory(raw, symbol, now_ms):
    """Allowlist projection at the AI trust boundary; bad advice never gates."""
    if raw is None:
        return {'status': 'not_supplied'}
    try:
        if (not isinstance(raw, dict) or raw.get('kind') != 'structural_market_advisory'
                or raw.get('version') != VERSION or raw.get('symbol') != symbol
                or raw.get('authority') != 'advisory_only'
                or any(raw.get(k) is not False for k in
                       ('may_authorize_entry', 'may_block_entry', 'may_modify_scores'))
                or type(raw.get('observed_ms')) is not int
                or not 0 <= now_ms-raw['observed_ms'] <= MAX_AGE_MS
                or raw.get('phase') not in ('UP_REASSESSMENT', 'DOWN_REASSESSMENT', 'NO_BREAK')
                or any(raw.get(k) not in ('UP', 'DOWN', 'RANGE', 'UNKNOWN')
                       for k in ('context_1h', 'context_4h'))):
            raise ValueError('invalid_advisory')
        values = {}
        for k in ('range_high', 'range_low', 'atr_15m'):
            value = raw[k]
            if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
                raise ValueError('invalid_level')
            values[k] = value
        allowed = ('kind', 'version', 'symbol', 'observed_ms', 'authority',
                   'may_authorize_entry', 'may_block_entry', 'may_modify_scores',
                   'phase', 'context_1h', 'context_4h')
        return {'status': 'available', 'value': {
            **{k: raw[k] for k in allowed}, **values,
            'predictive_value': 'not_demonstrated'}}
    except (TypeError, ValueError, KeyError):
        return {'status': 'unavailable'}
