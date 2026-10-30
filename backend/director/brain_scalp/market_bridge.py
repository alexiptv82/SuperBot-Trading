"""Public Bitget feed for the isolated PAPER Brain Scalp account.

Uses the existing Brain Free public-market reader. No account keys, positions
API or order endpoints. History repair is independently validated by the engine.
"""
import math
from urllib.parse import urlencode

from director.brain_free.feeds import Feeds, get as public_get
from director.brain_scalp.gap_repair import MAX_BACKFILL_BARS, MINUTE


def validate_feed_snapshot(markets, contracts):
    """No made-up quotes/contract defaults when a public feed is unavailable."""
    if not isinstance(markets,dict) or not isinstance(contracts,dict):
        raise ValueError('invalid_feed_snapshot')
    clean={}
    for symbol,market in markets.items():
        if not isinstance(symbol,str) or not symbol.isascii() or not symbol.isalnum():
            continue
        if not isinstance(market,dict):
            continue
        m=dict(market)
        bars=m.get('bars')
        if not isinstance(bars,dict):
            bars={}
        # Only the existing engine decides whether these series are complete
        # and causal. A missing frame is left missing rather than fabricated.
        m['bars']={tf:list(bars.get(tf) or ()) for tf in ('1m','5m')}
        q=m.get('quote')
        if not isinstance(q,dict):
            m.pop('quote',None)
        else:
            try:
                px=float(q['price']);ts=int(q['ts_ms'])
                if not (math.isfinite(px) and px>0 and ts>0):
                    raise ValueError('bad_quote')
            except (KeyError,TypeError,ValueError,OverflowError):
                m.pop('quote',None)
        clean[symbol]=m
    return clean,contracts


def fetch_closed_gap(symbol, first_open_ms, exclusive_end_ms, fetcher=public_get):
    """V2 public historical endpoint, one bounded request per causal gap."""
    if (not isinstance(symbol,str) or not symbol.isascii() or
        not symbol.isalnum() or len(symbol)>20 or
        type(first_open_ms)!=int or type(exclusive_end_ms)!=int or
        first_open_ms<0 or exclusive_end_ms<=first_open_ms or
        first_open_ms%MINUTE or exclusive_end_ms%MINUTE or
        (exclusive_end_ms-first_open_ms)//MINUTE>MAX_BACKFILL_BARS):
        raise ValueError('invalid_gap_request')
    # V2 caps historical response at 200 rows. For a larger required range
    # return empty and let the engine quarantine; do not accept partial replay.
    count=(exclusive_end_ms-first_open_ms)//MINUTE
    if count>200:
        raise ValueError('gap_more_than_endpoint_limit')
    params=urlencode({'symbol':symbol+'USDT','productType':'USDT-FUTURES',
                      'granularity':'1m','startTime':first_open_ms,
                      'endTime':exclusive_end_ms,'limit':count})
    payload=fetcher('/api/v2/mix/market/history-candles?'+params)
    rows=payload.get('data')
    if not isinstance(rows,list):
        raise ValueError('invalid_gap_payload')
    mapped={}
    for source in rows:
        if not isinstance(source,list) or len(source)<6:
            raise ValueError('invalid_gap_candle')
        bar=[]
        for item in source[:6]:
            n=float(item)
            if not math.isfinite(n):
                raise ValueError('nonfinite_gap_candle')
            bar.append(n)
        stamp=int(bar[0])
        if (bar[0]!=stamp or stamp%MINUTE or
            stamp<first_open_ms or stamp>=exclusive_end_ms or
            stamp in mapped or min(bar[1],bar[4])<=0 or
            bar[2]<max(bar[1],bar[4]) or bar[3]>min(bar[1],bar[4]) or bar[5]<0):
            raise ValueError('untrusted_gap_candle')
        mapped[stamp]=bar
    expected=range(first_open_ms,exclusive_end_ms,MINUTE)
    if len(mapped)!=count or any(ts not in mapped for ts in expected):
        raise ValueError('gap_incomplete')
    return [mapped[ts] for ts in expected]


class PublicBrainFeed:
    def __init__(self,reader=None,fetcher=public_get):
        self.reader=reader if reader is not None else Feeds()
        self.fetcher=fetcher

    def poll(self,positions,now_ms):
        raw,contracts,_context=self.reader.poll(positions,now_ms)
        return validate_feed_snapshot(raw,contracts)

    def backfill(self,symbol,start,end):
        return fetch_closed_gap(symbol,start,end,self.fetcher)

    def close(self):
        self.reader.close()
