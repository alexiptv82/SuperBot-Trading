"""Experimental mirrored level-reclaim observation. Never an entry permission.

OHLCV proxy only: does not assert CVD, passive absorption or institutional flow.
No dependencies on regime-v2; no portfolio, provider, orders or production hook.
"""
from statistics import median
from director.brain_scalp.scanner import _closed


def observe(symbol,bars,now_ms,*,duration_ms=300000):
    if (not isinstance(symbol,str) or not symbol.isascii() or not symbol.isalnum() or
            not 1<=len(symbol)<=20 or type(now_ms)!=int or now_ms<=0 or
            duration_ms not in (60000,300000,900000)):
        raise ValueError('invalid_probe_input')
    rows=_closed(bars,now_ms,duration_ms,22)
    base={'schema_version':1,'symbol':symbol,'execution_permission':False,
          'validation':'unvalidated_research','duration_ms':duration_ms,'events':[]}
    if not rows or now_ms-(rows[-1][0]+duration_ms)>duration_ms:
        return dict(base,status='data_unavailable')
    history,reaction,confirmation=rows[:-2],rows[-2],rows[-1]
    typical=median(b[5] for b in history)
    if typical<=0:return dict(base,status='volume_unavailable')
    volume_ratio=reaction[5]/typical
    support=min(b[3] for b in history);resistance=max(b[2] for b in history)
    checks={
        'LONG':(reaction[3]<support and reaction[4]>support and confirmation[4]>reaction[2]),
        'SHORT':(reaction[2]>resistance and reaction[4]<resistance and confirmation[4]<reaction[3]),
    }
    at=confirmation[0]+duration_ms
    for side,confirmed in checks.items():
        if confirmed and volume_ratio>=1.5:
            base['events'].append({'event_id':f'reclaim-v1:{symbol}:{duration_ms}:{at}:{side}',
                'side':side,'observed_ms':at,'reference_level':support if side=='LONG' else resistance,
                'reaction_extreme':reaction[3] if side=='LONG' else reaction[2],
                'confirmation_close':confirmation[4],'reaction_volume_ratio':volume_ratio})
    return dict(base,status='observed')
