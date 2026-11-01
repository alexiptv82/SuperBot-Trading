"""Bitget v3 PUBLIC REST closed-candle overlay (research only, no trading).

Reference: https://www.bitget.com/docs/catalog/market/market-data
Endpoint GET /api/v3/market/candles; category USDT-FUTURES, interval
1m / 15m / 1H / 4H, list rows [open_ts,O,H,L,C,base_volume,turnover].

Safety design:
- no API secrets or private endpoints; network disabled unless caller opts in;
- historical candles are available only at actual GET receipt;
- bars still forming or too close to their boundary are discarded;
- verify ≥200 continuous CLOSED bars per TF, fresh end and aligned clocks;
- atomic 2-symbol * 4-timeframe refresh (failure discards whole old batch);
- preserve WS BBO source and its freshness, prevent replay as live context.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

from long_shadow_stream import SYMBOLS, TF_MS, TF_INTERNAL, FeedNotReady

ENDPOINT = 'https://api.bitget.com/api/v3/market/candles'
INTERVALS = ('1m','15m','1H','4H')
LIMIT = 500
MIN_BARS = 200
CLOSE_GRACE_MS = 2_000
MAX_SERVER_CLOCK_SKEW_MS = 15_000
MAX_BATCH_DURATION_MS = 30_000
MAX_REST_AGE_MS = 75_000
MAX_RESPONSE_BYTES = 1_200_000


class _BlockRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FeedNotReady('rest_redirect_rejected')


def public_candles(symbol, interval, *, timeout_s=5):
    """Deliberately opt-in public GET; returns raw response, local receive-ms.

    The only accepted endpoint is hardcoded HTTPS Bitget market candles.
    This function never reads credentials or makes order calls.
    """
    if symbol not in SYMBOLS or interval not in INTERVALS:
        raise FeedNotReady('unexpected_rest_request')
    query=urllib.parse.urlencode({'category':'USDT-FUTURES','symbol':symbol,
                                  'interval':interval,'type':'market',
                                  'limit':str(LIMIT)})
    request=urllib.request.Request(ENDPOINT+'?'+query,headers={
        'Accept':'application/json','User-Agent':'SuperBot-LONG-Research-ReadOnly/1'})
    opener=urllib.request.build_opener(_BlockRedirect())
    try:
        with opener.open(request,timeout=timeout_s) as response:
            if response.status!=200:
                raise FeedNotReady('rest_http_status')
            raw=response.read(MAX_RESPONSE_BYTES+1)
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        raise FeedNotReady('rest_public_unavailable') from exc
    received=int(time.time()*1000)
    if len(raw)>MAX_RESPONSE_BYTES:
        raise FeedNotReady('rest_response_oversized')
    try:
        data=json.loads(raw)
    except (UnicodeError,ValueError) as exc:
        raise FeedNotReady('rest_response_not_json') from exc
    return data,received


def _strict_int(value):
    if type(value) is int:
        return value
    if isinstance(value,str) and value.isdecimal():
        return int(value)
    raise FeedNotReady('rest_invalid_timestamp')


def _positive_decimal(value, allow_zero=False):
    if not isinstance(value,str):
        raise FeedNotReady('rest_invalid_number')
    try:
        number=Decimal(value)
    except (InvalidOperation,ValueError) as exc:
        raise FeedNotReady('rest_invalid_number') from exc
    if not number.is_finite() or number < 0 or (not allow_zero and number==0):
        raise FeedNotReady('rest_invalid_number')
    return number


def parse_closed_response(payload, symbol, interval, *,
                          started_ms, received_ms):
    """Parse a single response as a causal 500-bar snapshot.

    The returned bar availability is LOCAL RECEIVE time, never server
    requestTime or the historic candle's closing timestamp.
    """
    if symbol not in SYMBOLS or interval not in INTERVALS:
        raise FeedNotReady('invalid_rest_symbol_or_interval')
    if (type(started_ms) is not int or type(received_ms) is not int or
            not 0 <= received_ms-started_ms <= MAX_BATCH_DURATION_MS):
        raise FeedNotReady('rest_clock_reversed_or_slow')
    if not isinstance(payload,dict) or payload.get('code')!='00000':
        raise FeedNotReady('rest_exchange_rejected')
    server_time=payload.get('requestTime')
    if type(server_time) is not int or abs(server_time-received_ms)>MAX_SERVER_CLOCK_SKEW_MS:
        raise FeedNotReady('rest_server_clock_untrusted')
    rows=payload.get('data')
    if not isinstance(rows,list) or not MIN_BARS<=len(rows)<=1000:
        raise FeedNotReady('rest_invalid_row_count')
    width=TF_MS[interval]
    bars=[]
    opened=set()
    for row in rows:
        if not isinstance(row,list) or len(row)!=7:
            raise FeedNotReady('rest_invalid_row_schema')
        ts=_strict_int(row[0])
        if ts<=0 or ts % width or ts in opened:
            raise FeedNotReady('rest_unaligned_or_duplicate')
        opened.add(ts)
        o,h,l,c,v,turn=(_positive_decimal(x,allow_zero=(i>=4))
                        for i,x in enumerate(row[1:]))
        if l>min(o,c) or h<max(o,c) or l>h or turn<0:
            raise FeedNotReady('rest_invalid_ohlcv')
        closed=ts+width
        # REST is not a finality flag. Only observe candles that have
        # actually ended with a conservative local post-close grace.
        if closed+CLOSE_GRACE_MS > started_ms:
            continue
        bars.append({'open':float(o),'high':float(h),'low':float(l),
                     'close':float(c),'volume':float(v),
                     'close_ms':closed,'available_at_ms':received_ms,
                     'availability':'public_rest_observed_after_close'})
    bars.sort(key=lambda x:x['close_ms'])
    if len(bars)<MIN_BARS:
        raise FeedNotReady('rest_closed_warmup_insufficient')
    bars=bars[-LIMIT:]
    if any(b['close_ms']-a['close_ms']!=width for a,b in zip(bars,bars[1:])):
        raise FeedNotReady('rest_closed_gap')
    if received_ms-bars[-1]['close_ms']>=width+60_000:
        raise FeedNotReady('rest_latest_closed_stale')
    return bars


class RestClosedOverlay:
    """In-memory 8-response atomic REST candle overlay over an observed WS feed."""
    def __init__(self, websocket_feed):
        self.ws=websocket_feed
        self.session=None
        self.rest_receipt_ms=None
        self.bars={}
        self.last_failure=None

    @property
    def last_receipt_ms(self):
        # A public REST read is not a WS quote: return the actual WS receipt.
        return self.ws.last_receipt_ms

    def invalidate(self, reason):
        self.session=None
        self.rest_receipt_ms=None
        self.bars={}
        self.last_failure=str(reason)

    def refresh(self, getter, *, clock_ms=None):
        """Explicit refresh with injected getter(symbol, interval)->(payload,received_ms).

        Never use historical capture time as the clock. A partial/failed
        refresh invalidates prior snapshots instead of silently reusing them.
        """
        clock=clock_ms or (lambda:int(time.time()*1000))
        session=self.ws.session
        if type(session) is not int or session<=0:
            self.invalidate('ws_session_unavailable')
            raise FeedNotReady('ws_session_unavailable')
        batch={}
        began=clock()
        try:
            for symbol in SYMBOLS:
                for interval in INTERVALS:
                    start=clock()
                    payload,received=getter(symbol,interval)
                    parsed=parse_closed_response(payload,symbol,interval,
                        started_ms=start,received_ms=received)
                    if self.ws.session!=session:
                        raise FeedNotReady('ws_reconnected_during_rest_batch')
                    batch[symbol,interval]=(received,parsed)
            end=clock()
            if type(end) is not int or not 0 <= end-began <= MAX_BATCH_DURATION_MS:
                raise FeedNotReady('rest_batch_too_slow')
            if any(end-received<0 or end-received>MAX_BATCH_DURATION_MS
                   for received,_ in batch.values()):
                raise FeedNotReady('rest_receipt_clock_inconsistent')
        except (ValueError,TypeError,KeyError,OverflowError) as exc:
            self.invalidate(str(exc))
            if isinstance(exc,FeedNotReady):
                raise
            raise FeedNotReady('rest_invalid_batch') from exc
        self.bars=batch
        self.rest_receipt_ms=max(v[0] for v in batch.values())
        self.session=session
        self.last_failure=None
        return {'schema':'long-closed-rest-batch-v1','status':'closed_data_observed',
                'session':session,'rest_last_receipt_ms':self.rest_receipt_ms,
                'closed_series':len(batch),'can_execute_orders':False}

    def context(self, symbol, as_of_ms, *, max_quote_age_ms=2000):
        if symbol not in SYMBOLS or type(as_of_ms) is not int:
            raise FeedNotReady('invalid_rest_context')
        if not self.bars or self.session!=self.ws.session:
            raise FeedNotReady('rest_not_ready_or_ws_reconnected')
        if (self.rest_receipt_ms is None or
                not 0 <= as_of_ms-self.rest_receipt_ms <= MAX_REST_AGE_MS):
            raise FeedNotReady('rest_snapshot_stale')
        if any((symbol,tf) not in self.bars for tf in INTERVALS):
            raise FeedNotReady('missing_rest_timeframe')
        last_rest_received=max(self.bars[symbol,tf][0] for tf in INTERVALS)
        quote=self.ws.quotes.get(symbol)
        if (not isinstance(quote,dict) or
                type(quote.get('available_at_ms')) is not int or
                not last_rest_received <= quote['available_at_ms'] <= as_of_ms or
                as_of_ms-quote['available_at_ms']>max_quote_age_ms):
            raise FeedNotReady('quote_not_fresh_after_rest')
        for tf in INTERVALS:
            rows=self.bars[symbol,tf][1]
            if as_of_ms-rows[-1]['close_ms']>=TF_MS[tf]+60_000:
                raise FeedNotReady('rest_latest_closed_stale')
        return {'symbol':symbol,
                'bars':{TF_INTERNAL[tf]:self.bars[symbol,tf][1] for tf in INTERVALS},
                'quote':dict(quote),'source':'bitget_public_rest_closed_after_receipt',
                'live_close_ack_observed':False,'execution_verified':False}
