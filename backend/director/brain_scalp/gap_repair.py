"""Causal, injected backfill for CLOSED Brain Scalp 1m candles.

No HTTP/Bitget client lives here. A future supervisor supplies fetcher
(symbol, first_open_ms, exclusive_end_ms) -> original OHLCV bars.
Unverifiable gaps are never synthesized or silently dropped.
"""
from copy import deepcopy
import math

MINUTE=60000
MAX_BACKFILL_BARS=240
MAX_BACKFILL_CALLS=8


def _valid_bar(bar,now):
    if not isinstance(bar,(list,tuple)) or len(bar)<6:
        return False
    ts,o,hi,lo,cl,vol=bar[:6]
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or
           not math.isfinite(v) for v in (ts,o,hi,lo,cl,vol)):
        return False
    if (int(ts)!=ts or ts<0 or ts%MINUTE or ts+MINUTE>now or
            o<=0 or cl<=0 or lo<=0 or vol<0 or
            hi<max(o,cl) or lo>min(o,cl)):
        return False
    return True


def _closed_index(bars,now):
    result={}
    for bar in bars:
        if not isinstance(bar,(list,tuple)) or not bar:
            raise ValueError('malformed_candle')
        if not isinstance(bar[0],(float,int)) or not math.isfinite(bar[0]):
            raise ValueError('invalid_candle_timestamp')
        if bar[0]+MINUTE>now:
            # The still-forming candle is never used as a substitute for a
            # missing closed candle. A future bar is not backfilled either.
            continue
        if not _valid_bar(bar,now):
            raise ValueError('invalid_closed_candle')
        ts=int(bar[0])
        if ts in result and tuple(result[ts][:6])!=tuple(bar[:6]):
            raise ValueError('conflicting_duplicate_candles')
        result[ts]=list(bar)
    return result


def _gaps(by_time,now,anchor_ms):
    times=sorted(by_time)
    gaps=[]
    if anchor_ms is not None:
        if anchor_ms%MINUTE or anchor_ms<0:
            raise ValueError('invalid_position_cursor')
        # Do not backfill into a future/incomplete minute.
        prev=anchor_ms
        for ts in times:
            if ts<=anchor_ms: continue
            if ts>prev+MINUTE:
                gaps.append((prev+MINUTE,ts))
            prev=ts
        # If feed dropped the most recent completed minute, repair that too.
        last_closed_open=(now//MINUTE-1)*MINUTE
        if last_closed_open>=prev+MINUTE:
            gaps.append((prev+MINUTE,last_closed_open+MINUTE))
    elif times:
        for prev,ts in zip(times,times[1:]):
            if ts>prev+MINUTE:
                gaps.append((prev+MINUTE,ts))
    return gaps


def repair_markets(markets,now,fetcher=None,anchors=None):
    """Return (copied_market_snapshot, audit_events).

    If a required gap cannot be verified, do not fabricate continuity.
    The wallet's coverage gate is set by the coordinator/engine on failure.
    """
    anchors=anchors or {}
    fixed={}
    events=[]
    for sym,data in markets.items():
        if not isinstance(data,dict):
            fixed[sym]=data
            continue
        series=(data.get('bars') or {}).get('1m',[])
        try:
            by_time=_closed_index(series,now)
            gaps=_gaps(by_time,now,anchors.get(sym))
        except (ValueError,TypeError,OverflowError) as exc:
            fixed[sym]=data
            events.append({'kind':'gap_unresolvable','symbol':sym,
                           'reason':str(exc)[:80]})
            continue
        if not gaps:
            fixed[sym]=data
            continue
        if len(gaps)>MAX_BACKFILL_CALLS or any(
                (end-start)//MINUTE>MAX_BACKFILL_BARS for start,end in gaps):
            fixed[sym]=data
            events.append({'kind':'gap_unresolvable','symbol':sym,
                           'reason':'backfill_bounded'})
            continue
        if fetcher is None:
            fixed[sym]=data
            events.append({'kind':'gap_unresolvable','symbol':sym,
                           'reason':'no_backfill_provider'})
            continue
        candidate=dict(by_time)
        valid=True
        staged=[]
        for first,end in gaps:
            try:
                recovered=fetcher(sym,first,end)
                if not isinstance(recovered,(list,tuple)):
                    raise ValueError('backfill_invalid_payload')
                expected=list(range(first,end,MINUTE))
                if len(recovered)!=len(expected):
                    raise ValueError('backfill_incomplete')
                for ts,bar in zip(expected,recovered):
                    if not _valid_bar(bar,now) or int(bar[0])!=ts:
                        raise ValueError('backfill_noncausal_or_invalid')
                    if ts in candidate and tuple(candidate[ts][:6])!=tuple(bar[:6]):
                        raise ValueError('backfill_conflict')
                    candidate[ts]=list(bar)
                staged.append({'kind':'gap_backfilled','symbol':sym,
                               'start_ms':first,'end_ms':end,
                               'bars':len(expected)})
            except Exception as exc:
                # Caller can inspect reason without logging possible secrets.
                events.append({'kind':'gap_backfill_failed','symbol':sym,
                               'start_ms':first,'end_ms':end,
                               'error_type':type(exc).__name__})
                valid=False
                break
        if valid and not _gaps(candidate,now,anchors.get(sym)):
            cloned=dict(data)
            cloned['bars']=dict(data.get('bars') or {})
            cloned['bars']['1m']=[candidate[ts] for ts in sorted(candidate)]
            fixed[sym]=cloned
            events.extend(staged)
        else:
            fixed[sym]=data
            events.append({'kind':'gap_unresolvable','symbol':sym,
                           'reason':'incomplete_after_retry'})
    return fixed,events
