"""Contract tests for actual MTF snapshot -> analytical-only market context."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from long_shadow_capture_context import startup_contexts, FeedUnavailable, TF_MS

REC = 1793549782000
SYMBOLS=('BTCUSDT','ETHUSDT')

def pack(path, *, tamper=False, ack=10, missing=None):
    events=[]
    for sym in SYMBOLS:
        for tf,w in TF_MS.items():
            if (sym,tf)==missing:
                continue
            period=REC//w*w
            rows=[]
            for i in range(500):
                start=period-(499-i)*w
                rows.append({'start':str(start),'open':'100','high':'101','low':'99',
                             'close':'100','volume':'1','turnover':'100'})
            wire=json.dumps({'arg':{'instType':'usdt-futures','topic':'kline',
                                   'symbol':sym,'interval':tf},
                             'action':'snapshot','data':rows},separators=(',',':'))
            events.append((REC,wire))
        wire=json.dumps({'arg':{'instType':'usdt-futures','topic':'books1',
                               'symbol':sym},'action':'snapshot',
                         'data':[{'a':[['100.1','1']], 'b':[['100','1']]}]})
        events.append((REC+100,wire))
    raw=[]
    for i,(stamp,wire) in enumerate(events):
        raw.append(json.dumps({'raw_frame':wire,'raw_sha256':('0'*64 if tamper and i==0 else hashlib.sha256(wire.encode()).hexdigest()),
                               'received_at_ms':stamp},separators=(',',':')))
    rawbytes=('\n'.join(raw)+'\n').encode()
    summary={'schema':'live_mtf_capture_01','duration_completed':True,
             'ever_acked_subscriptions':ack,'errors':{},'raw_parts':['ws_raw_frames_00001.jsonl']}
    summbytes=json.dumps(summary).encode()
    manifest=('\n'.join(hashlib.sha256(content).hexdigest()+'  '+name
           for name,content in [('ws_raw_frames_00001.jsonl',rawbytes),
                                ('capture_summary.json',summbytes)])+'\n').encode()
    with ZipFile(path,'w') as z:
        base='mtf_example'
        z.writestr(base+'/ws_raw_frames_00001.jsonl',rawbytes)
        z.writestr(base+'/capture_summary.json',summbytes)
        z.writestr(base+'/SHA256SUMS.txt',manifest)

class TestStartupContext(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'capture.zip'
    def test_closed_bars_are_observed_at_receipt_not_retrodated(self):
        pack(self.path)
        contexts=startup_contexts(self.path)
        self.assertEqual(set(contexts),set(SYMBOLS))
        for sym,ctx in contexts.items():
            self.assertEqual(ctx['quote']['available_at_ms'],REC+100)
            self.assertEqual(ctx['source'],'bitget_verified_capture_startup_snapshots')
            self.assertFalse(ctx['execution_verified'])
            self.assertFalse(ctx['live_close_ack_observed'])
            self.assertEqual(set(ctx['bars']),{'1m','15m','1h','4h'})
            for tf,bars in ctx['bars'].items():
                self.assertEqual(len(bars),499)
                self.assertTrue(all(b['available_at_ms']==REC for b in bars))
                self.assertTrue(all(b['close_ms']<=REC for b in bars))
    def test_corrupted_raw_fails(self):
        pack(self.path,tamper=True)
        with self.assertRaisesRegex(FeedUnavailable,'frame_hash_mismatch'):
            startup_contexts(self.path)
    def test_not_all_channels_acked(self):
        pack(self.path,ack=9)
        with self.assertRaisesRegex(FeedUnavailable,'missing_acks'):
            startup_contexts(self.path)
    def test_missing_tf_fails(self):
        pack(self.path,missing=('BTCUSDT','4H'))
        with self.assertRaisesRegex(FeedUnavailable,'missing_tf_snapshot'):
            startup_contexts(self.path)
if __name__=='__main__': unittest.main()
