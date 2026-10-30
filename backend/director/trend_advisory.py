"""Causal, symmetrical trend-change *observation*, NEVER a trading strategy.

One identical reader shared by isolated classic and Brain branches.
Closed, contiguous OHLCV candles only. No network, no trades, no thresholds
for risk/entry/admission, no moving-average warmup or long-only privilege.
An early turn is a hypothesis for later evaluation, never confirmed profit.
"""
import math

MIN_BARS=40


def observe(symbol,bars,now_ms,bar_ms):
    """Read *completed* candles and return advisory dict, or None on bad data.

    Latest unclosed bar is ignored, not treated as knowledge. A missing bar
    invalidates the observation without excluding any trade from its strategy.
    """
    if (not isinstance(symbol,str) or not symbol.isascii() or
            not symbol.isalnum() or not 1<=len(symbol)<=20 or
            type(now_ms)!=int or now_ms<=0 or type(bar_ms)!=int or
            bar_ms not in (60000,300000,900000)):
        return None
    try:
        completed=[]
        for b in bars:
            if len(b)<6:
                return None
            raw=[float(v) for v in b[:6]]
            ts=int(raw[0])
            if (not all(math.isfinite(v) for v in raw) or raw[0]!=ts or
                    ts<0 or ts%bar_ms or raw[1]<=0 or raw[4]<=0 or
                    raw[2]<max(raw[1],raw[4]) or
                    raw[3]>min(raw[1],raw[4]) or raw[3]<=0 or raw[5]<0):
                return None
            if ts+bar_ms<=now_ms:
                completed.append((ts,raw[4],raw[5]))
        if len(completed)<MIN_BARS:
            return None
        completed=completed[-MIN_BARS:]
        if any(b[0]-a[0]!=bar_ms for a,b in zip(completed,completed[1:])):
            return None
        observed_ms=completed[-1][0]+bar_ms
        if not 0<=now_ms-observed_ms<=2*bar_ms:
            return None
        closes=[b[1] for b in completed]
        # Symmetric in log-price: multiplying all prices by any constant
        # cannot change the conclusion, and reflecting log-price swaps up/down.
        earlier=math.log(closes[-8]/closes[-28])
        recent=math.log(closes[-1]/closes[-4])
        acceleration=recent-earlier*3/20
        prior=('up' if earlier>0.001 else
               'down' if earlier< -0.001 else 'flat')
        recent_dir=('up' if recent>0.0004 else
                    'down' if recent< -0.0004 else 'flat')
        if prior=='down' and recent_dir=='up':
            phase='early_upshift'
        elif prior=='up' and recent_dir=='down':
            phase='early_downshift'
        elif prior=='up' and recent_dir=='up':
            phase='up_continuation'
        elif prior=='down' and recent_dir=='down':
            phase='down_continuation'
        else:
            phase='uncertain'
        result={
            'kind':'trend_change_observation',
            'authority':'advisory_only',
            'may_authorize_entry':False,
            'may_block_entry':False,
            'symbol':symbol,'observed_ms':observed_ms,
            'bar_ms':bar_ms,'prior_direction':prior,
            'recent_direction':recent_dir,'phase':phase,
            'prior_return_pct':round(100*math.expm1(earlier),4),
            'recent_return_pct':round(100*math.expm1(recent),4),
            'acceleration_pct':round(100*acceleration,4),
            'evidence_bars':MIN_BARS,
            'interpretation':'possible_turn_not_confirmed',
        }
        return result
    except (TypeError,ValueError,IndexError,OverflowError,ZeroDivisionError):
        return None


def observe_many(series,now_ms,bar_ms):
    """Read each symbol independently; one bad symbol cannot affect others."""
    if not isinstance(series,dict):
        return {}
    out={}
    for symbol,bars in series.items():
        try:
            item=observe(symbol,bars,now_ms,bar_ms)
            if item is not None:
                out[symbol]=item
        except Exception:
            # This is secondary observational data, not part of protection.
            continue
    return out
