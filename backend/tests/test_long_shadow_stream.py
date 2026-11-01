"""Pure streaming classification tests. No broker, no network, no wallets."""
import hashlib
import json
import unittest
from long_shadow_stream import ObservedFeed, FeedNotReady, TF_MS

START=1793549782000

def emit(raw, ts=START, session=1):
    return {'raw_frame':raw,'raw_sha256':hashlib.sha256(raw.encode()).hexdigest(),
            'received_at_ms':ts,'session':session}

def candle(sym,tf,ts=START,action='snapshot'):
    width=TF_MS[tf]; period=ts//width*width
    rows=[]
    for i in range(500):
        t=period-(499-i)*width
        rows.append({'start':str(t),'open':'100','high':'101','low':'99','close':'100.5','volume':'1'})
    return emit(json.dumps({'arg':{'instType':'usdt-futures','symbol':sym,'topic':'kline','interval':tf},
                             'action':action,'data':rows}),ts)

def book(sym,ts=START+300):
    return emit(json.dumps({'arg':{'instType':'usdt-futures','symbol':sym,'topic':'books1'},
                             'action':'update','data':[{'b':[['100','1']],'a':[['100.1','1']]}]}),ts)

class TestObservedFeed(unittest.TestCase):
    def test_no_future_closed_snapshot(self):
        f=ObservedFeed();f.ingest(candle('BTCUSDT','1m'))
        bars=f.snapshots['BTCUSDT','1m'][1]
        self.assertEqual(len(bars),499)
        self.assertTrue(all(b['close_ms']<=START and b['available_at_ms']==START for b in bars))
    def test_ignores_unconfirmed_update(self):
        f=ObservedFeed();f.ingest(candle('BTCUSDT','1m'))
        prior=f.snapshots['BTCUSDT','1m']
        self.assertEqual(f.ingest(candle('BTCUSDT','1m',ts=START+20,action='update')), 'UNCONFIRMED_KLINE_UPDATE')
        self.assertIs(f.snapshots['BTCUSDT','1m'],prior)
    def test_all_timeframes_required(self):
        f=ObservedFeed();f.ingest(candle('BTCUSDT','1m'));f.ingest(book('BTCUSDT'))
        with self.assertRaisesRegex(FeedNotReady,'missing_timeframe_snapshot'):
            f.context('BTCUSDT',START+300)
    def test_200_bars_and_quote_ready(self):
        f=ObservedFeed()
        for tf in TF_MS:f.ingest(candle('BTCUSDT',tf))
        f.ingest(book('BTCUSDT'))
        ctx=f.context('BTCUSDT',START+300)
        self.assertTrue(all(len(rows)==499 for rows in ctx['bars'].values()))
        self.assertFalse(ctx['execution_verified'])
    def test_reconnect_requires_rewarmup(self):
        f=ObservedFeed()
        for tf in TF_MS:f.ingest(candle('BTCUSDT',tf))
        f.ingest(book('BTCUSDT'))
        second=book('BTCUSDT',START+500);second['session']=2;f.ingest(second)
        with self.assertRaisesRegex(FeedNotReady,'missing_timeframe_snapshot'):
            f.context('BTCUSDT',START+500)
    def test_stale_quote_is_not_ready(self):
        f=ObservedFeed()
        for tf in TF_MS:f.ingest(candle('BTCUSDT',tf))
        f.ingest(book('BTCUSDT'))
        with self.assertRaisesRegex(FeedNotReady,'stale_quote'):
            f.context('BTCUSDT',START+5000)
    def test_raw_sha_tamper_rejected(self):
        f=ObservedFeed();a=book('BTCUSDT');a['raw_sha256']='0'*64
        with self.assertRaisesRegex(FeedNotReady,'sha_mismatch'):
            f.ingest(a)
    def test_backwards_receipt_resets(self):
        f=ObservedFeed();f.ingest(book('BTCUSDT',START+200))
        with self.assertRaisesRegex(FeedNotReady,'time_reversal'):
            f.ingest(book('BTCUSDT',START+100))
        self.assertEqual(f.snapshots,{})
    def test_wrong_symbol_ignored(self):
        f=ObservedFeed();q=book('XRPUSDT');self.assertEqual(f.ingest(q),'OTHER')
    def test_pong(self):
        f=ObservedFeed();self.assertEqual(f.ingest(emit('pong')),'HEARTBEAT')
if __name__=='__main__':unittest.main()
