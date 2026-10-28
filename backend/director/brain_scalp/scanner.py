"""Causal 1m/5m closed-candle shortlist. Pure, no network/AI.

Bars: (open_ms, open, high, low, close, volume). Quote: {price, ts_ms}.
Every symbol gets a status: absent signals are never hidden.
"""
import math
from statistics import median


def _closed(bars, now, duration, n):
    try:
        rows = [b for b in bars if len(b) >= 6 and b[0] + duration <= now]
        rows = rows[-n:]
        if len(rows) < n or any(not all(math.isfinite(float(v)) for v in b[:6]) or
                                b[1] <= 0 or b[3] <= 0 or b[2] < max(b[1], b[4]) or
                                b[3] > min(b[1], b[4]) or b[5] < 0 for b in rows):
            return None
        if any(b[0] - a[0] != duration for a, b in zip(rows[:-1], rows[1:])):
            return None
        return rows
    except (ValueError, TypeError, IndexError):
        return None


def scan(markets, now_ms, limit=5):
    if not isinstance(now_ms, int) or now_ms < 0 or not 1 <= limit <= 10:
        raise ValueError('invalid_scan_arguments')
    found, coverage = [], {}
    for symbol in sorted(markets):
        m = markets[symbol]
        q = m.get('quote') or {}
        try:
            px, ts = float(q['price']), int(q['ts_ms'])
            if not math.isfinite(px) or px <= 0 or not 0 <= now_ms - ts <= 30000:
                raise ValueError('stale_quote')
        except (KeyError, TypeError, ValueError):
            coverage[symbol] = 'quote_missing_or_stale'
            continue
        bars = m.get('bars') or {}
        one = _closed(bars.get('1m', []), now_ms, 60000, 18)
        five = _closed(bars.get('5m', []), now_ms, 300000, 22)
        if not one or not five or now_ms-(one[-1][0]+60000)>90000 or now_ms-(five[-1][0]+300000)>360000:
            coverage[symbol] = 'closed_bars_missing_gap_or_stale'
            continue
        recent_high = max(b[2] for b in five[-13:-1])
        recent_low = min(b[3] for b in five[-13:-1])
        close5, close1 = five[-1][4], one[-1][4]
        delta = close1/one[-4][4]-1
        volume_ratio = five[-1][5]/max(1e-9,median(b[5] for b in five[-13:-1]))
        if volume_ratio < 1.05:
            coverage[symbol] = 'volume_not_confirmed'
            continue
        if close5>recent_high and delta>0 and close1>=close5*0.997:
            side, setup = 1, 'breakout_long'
        elif close5<recent_low and delta<0 and close1<=close5*1.003:
            side, setup = -1, 'breakout_short'
        else:
            coverage[symbol] = 'no_valid_breakout'
            continue
        movement = abs(close5/five[-2][4]-1)
        score = round(1000*movement+min(volume_ratio,5)*2+min(abs(delta)*1000,10),4)
        found.append({'symbol':symbol,'side':side,'setup':setup,'score':score,
                      'signal_close_ms':five[-1][0]+300000,
                      'volume_ratio':round(volume_ratio,3),'quote_ms':ts})
        coverage[symbol] = 'shortlisted_candidate'
    found.sort(key=lambda c:(-c['score'],c['symbol']))
    for c in found[limit:]:
        coverage[c['symbol']] = 'eligible_not_shortlisted'
    return {'candidates':found[:limit],'coverage':coverage,'symbols_checked':len(coverage)}
