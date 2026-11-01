"""Public REST close observation: synthetic 500-row deterministic tests."""
import unittest
from types import SimpleNamespace
from long_shadow_rest_closed import (
    RestClosedOverlay, parse_closed_response, FeedNotReady,
    TF_MS, INTERVALS, SYMBOLS, LIMIT,
)

NOW = 1800000100000

def payload(symbol, tf, *, at=NOW, edits=None):
    width=TF_MS[tf]
    latest=(at//width)*width
    rows=[]
    for i in range(LIMIT):
        ts=latest-(LIMIT-1-i)*width
        rows.append([str(ts),'100','101','99','100.5','4.5','453'])
    if edits:
        edits(rows)
    return {'code':'00000','requestTime':at,'msg':'success','data':rows}

def ws(*, session=1, quote_time=NOW+1500):
    quotes={s:{'bid':100.,'ask':100.1,'available_at_ms':quote_time} for s in SYMBOLS}
    return SimpleNamespace(session=session,last_receipt_ms=quote_time,quotes=quotes)

def getter(s,tf):
    return payload(s,tf,at=NOW),NOW+1000

def batch_clock():
    # Begin + eight starts are BEFORE response receipt; the final batch
    # end must occur AFTER all eight receive timestamps.
    calls=[0]
    def now():
        calls[0]+=1
        return NOW+1500 if calls[0]>=10 else NOW
    return now

class PublicClosedCandleContracts(unittest.TestCase):
    def test_correct_v3_shape_and_causal_timestamp(self):
        result=parse_closed_response(payload('BTCUSDT','1m'),
                                     'BTCUSDT','1m',started_ms=NOW,received_ms=NOW+1000)
        self.assertGreaterEqual(len(result),200)
        self.assertTrue(all(row['available_at_ms']==NOW+1000 for row in result))
        self.assertTrue(all(row['close_ms']+2000<=NOW for row in result))
        self.assertEqual(result[-1]['availability'],'public_rest_observed_after_close')
    def test_unfinished_bar_excluded_even_from_valid_http(self):
        now=NOW
        width=TF_MS['1m']
        raw=payload('BTCUSDT','1m',at=now)
        newest=int(raw['data'][-1][0])+width
        self.assertGreater(newest+2000,now)
        bars=parse_closed_response(raw,'BTCUSDT','1m',started_ms=now,received_ms=now+1000)
        self.assertNotIn(newest,[row['close_ms'] for row in bars])
    def test_duplicate_open_rejected(self):
        p=payload('BTCUSDT','1H')
        p['data'][3][0]=p['data'][2][0]
        with self.assertRaisesRegex(FeedNotReady,'duplicate'):
            parse_closed_response(p,'BTCUSDT','1H',started_ms=NOW,received_ms=NOW+1000)
    def test_gap_rejected(self):
        p=payload('BTCUSDT','1H')
        del p['data'][200]
        with self.assertRaisesRegex(FeedNotReady,'gap'):
            parse_closed_response(p,'BTCUSDT','1H',started_ms=NOW,received_ms=NOW+1000)
    def test_exchange_error_rejected(self):
        p=payload('BTCUSDT','15m');p['code']='40017'
        with self.assertRaisesRegex(FeedNotReady,'exchange_rejected'):
            parse_closed_response(p,'BTCUSDT','15m',started_ms=NOW,received_ms=NOW+1000)
    def test_server_clock_skew_rejected(self):
        p=payload('BTCUSDT','15m');p['requestTime']=NOW+30000
        with self.assertRaisesRegex(FeedNotReady,'clock_untrusted'):
            parse_closed_response(p,'BTCUSDT','15m',started_ms=NOW,received_ms=NOW+1000)
    def test_nonfinite_and_crossover_rejected(self):
        for bad in ('NaN','Infinity','-1','0','105'):
            p=payload('BTCUSDT','1m')
            p['data'][3][3]=bad
            with self.subTest(bad=bad):
                with self.assertRaises(FeedNotReady):
                    parse_closed_response(p,'BTCUSDT','1m',
                                          started_ms=NOW,received_ms=NOW+1000)
    def test_only_allowlisted_symbols_and_intervals(self):
        with self.assertRaisesRegex(FeedNotReady,'invalid_rest_symbol'):
            parse_closed_response(payload('BTCUSDT','1m'),
                                  'XRPUSDT','1m',started_ms=NOW,received_ms=NOW+1000)
    def test_atomic_eight_series(self):
        market=ws()
        overlay=RestClosedOverlay(market)
        with self.assertRaisesRegex(FeedNotReady,'rest_not_ready'):
            overlay.context('BTCUSDT',NOW+1500)
        status=overlay.refresh(getter,clock_ms=batch_clock())
        self.assertEqual(status['closed_series'],8)
        self.assertEqual(len(overlay.bars),8)
        self.assertEqual(len(overlay.context('BTCUSDT',NOW+1500)['bars']),4)
        self.assertEqual(overlay.context('ETHUSDT',NOW+1500)['source'],
                         'bitget_public_rest_closed_after_receipt')
    def test_partial_http_failure_invalidates_previous_snapshot(self):
        market=ws()
        overlay=RestClosedOverlay(market)
        overlay.refresh(getter,clock_ms=batch_clock())
        def broken(symbol,interval):
            if symbol=='ETHUSDT' and interval=='4H':
                raise FeedNotReady('rest_public_unavailable')
            return getter(symbol,interval)
        with self.assertRaisesRegex(FeedNotReady,'rest_public_unavailable'):
            overlay.refresh(broken,clock_ms=batch_clock())
        self.assertEqual(overlay.bars,{})
        with self.assertRaisesRegex(FeedNotReady,'rest_not_ready'):
            overlay.context('BTCUSDT',NOW+1500)
    def test_reconnect_invalidates_rest_context(self):
        market=ws()
        overlay=RestClosedOverlay(market)
        overlay.refresh(getter,clock_ms=batch_clock())
        market.session=2
        with self.assertRaisesRegex(FeedNotReady,'ws_reconnected'):
            overlay.context('BTCUSDT',NOW+1500)
    def test_quote_must_arrive_after_last_rest_receipt(self):
        market=ws(quote_time=NOW+500)
        overlay=RestClosedOverlay(market)
        overlay.refresh(getter,clock_ms=batch_clock())
        with self.assertRaisesRegex(FeedNotReady,'quote_not_fresh_after_rest'):
            overlay.context('BTCUSDT',NOW+1000)
    def test_quote_staleness(self):
        market=ws()
        overlay=RestClosedOverlay(market)
        overlay.refresh(getter,clock_ms=batch_clock())
        with self.assertRaisesRegex(FeedNotReady,'quote_not_fresh_after_rest'):
            overlay.context('BTCUSDT',NOW+5000)
    def test_rest_expiration(self):
        market=ws()
        overlay=RestClosedOverlay(market)
        overlay.refresh(getter,clock_ms=batch_clock())
        with self.assertRaisesRegex(FeedNotReady,'rest_snapshot_stale'):
            overlay.context('BTCUSDT',NOW+90000)
    def test_request_before_close_grace_does_not_take_new_candle(self):
        minute=(NOW//60000)*60000
        # Request only 1ms after boundary; the new closed bar is still
        # untrusted for 2s. It must not be used even if API returns it.
        start=minute+1
        p=payload('BTCUSDT','1m',at=start)
        bars=parse_closed_response(p,'BTCUSDT','1m',
                                   started_ms=start,received_ms=start+300)
        self.assertLessEqual(bars[-1]['close_ms'],minute-60000)
    def test_nonnumeric_timestamp_and_missing_columns(self):
        p=payload('BTCUSDT','1H');p['data'][4]=['oops','1']
        with self.assertRaisesRegex(FeedNotReady,'row_schema'):
            parse_closed_response(p,'BTCUSDT','1H',
                                  started_ms=NOW,received_ms=NOW+1000)
    def test_http_response_invalidated_when_time_is_backwards(self):
        with self.assertRaisesRegex(FeedNotReady,'clock_reversed'):
            parse_closed_response(payload('BTCUSDT','1m'),
                                  'BTCUSDT','1m',started_ms=NOW,received_ms=NOW-1)
    def test_no_trade_authority_in_overlay(self):
        market=ws()
        overlay=RestClosedOverlay(market)
        result=overlay.refresh(getter,clock_ms=batch_clock())
        self.assertFalse(result['can_execute_orders'])
        self.assertFalse(overlay.context('BTCUSDT',NOW+1500)['execution_verified'])
    def test_historic_bar_becomes_available_on_receipt_only(self):
        bars=parse_closed_response(payload('BTCUSDT','4H'),
                                   'BTCUSDT','4H',started_ms=NOW,received_ms=NOW+1200)
        self.assertEqual(bars[0]['available_at_ms'],NOW+1200)
        self.assertLess(bars[0]['close_ms'],NOW-100*TF_MS['4H'])

if __name__=='__main__':
    unittest.main()
