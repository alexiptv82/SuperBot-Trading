"""One-off REAL Bitget 1m closed-bar rollover test, no trading.

Reads two public BTC/ETH 1m snapshots >=67 s apart and independently
validates both against the same non-lookahead closed-bar parser used by
LONG Shadow. Checks that the latest closed minute has advanced, with
actual local request/receipt timestamps. Public GETs only, NO credentials.
"""
from __future__ import annotations
import json
import sys
import time

from long_shadow_rest_closed import public_candles, parse_closed_response, FeedNotReady

SYMBOLS=('BTCUSDT','ETHUSDT')
MIN_WAIT_SECONDS=67


def sample():
    result={}
    for symbol in SYMBOLS:
        start=int(time.time()*1000)
        payload,recv=public_candles(symbol,'1m',timeout_s=7)
        closed=parse_closed_response(payload,symbol,'1m',
                                     started_ms=start,received_ms=recv)
        result[symbol]={
            'latest_close_ms':closed[-1]['close_ms'],
            'received_ms':recv,'closed_bars':len(closed),
            'availability':'public_rest_observed_after_close'}
        time.sleep(.2)
    return result


def run():
    started=time.monotonic()
    try:
        first=sample()
        elapsed=time.monotonic()-started
        time.sleep(max(0,MIN_WAIT_SECONDS-elapsed))
        second=sample()
        for symbol in SYMBOLS:
            delta=second[symbol]['latest_close_ms']-first[symbol]['latest_close_ms']
            if delta < 60_000 or delta%60_000:
                raise FeedNotReady('new_closed_minute_missing:'+symbol)
            if second[symbol]['received_ms']<=first[symbol]['received_ms']:
                raise FeedNotReady('receipt_time_not_progressing:'+symbol)
    except (FeedNotReady,ValueError,TimeoutError) as exc:
        print('PUBLIC_REST_1M_ROLLOVER_FAIL:'+str(exc)[:160],file=sys.stderr)
        return 2
    report={'schema':'long-shadow-live-rest-1m-rollover-v1',
            'source':'Bitget public market candles (no orders)',
            'symbols':list(SYMBOLS),'calls_attempted':4,
            'minimum_sample_separation_s':MIN_WAIT_SECONDS,
            'orders_created':0,'keys_used':False,'passed':True,
            'result':{s:{'first_close_ms':first[s]['latest_close_ms'],
                         'second_close_ms':second[s]['latest_close_ms'],
                         'advance_minutes':(second[s]['latest_close_ms']-
                                            first[s]['latest_close_ms'])//60_000,
                         'first_received_ms':first[s]['received_ms'],
                         'second_received_ms':second[s]['received_ms'],
                         'bar_count_first':first[s]['closed_bars'],
                         'bar_count_second':second[s]['closed_bars']} for s in SYMBOLS}}
    print(json.dumps(report,sort_keys=True,indent=2))
    print('PUBLIC_REST_1M_ROLLOVER_PASS')
    return 0


if __name__=='__main__':
    raise SystemExit(run())
