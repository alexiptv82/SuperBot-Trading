"""Tests for replay contract, fabricated archives clearly identified as test fixtures."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from long_shadow_frozen_recorded_replay import replay

NOW = 1800000000000
WIDTHS={'1m':60000,'15m':900000,'1H':3600000,'4H':14400000}
SYMBOLS=('BTCUSDT','ETHUSDT')


def example_zip(path, *, corrupted_rest=False, corrupted_ws=False):
    rest=[]
    for symbol in SYMBOLS:
        for tf,w in WIDTHS.items():
            base=NOW//w*w
            rows=[]
            for n in range(250):
                start=base-(249-n)*w
                rows.append([str(start),'100','101','99','100.5','2','200'])
            payload={'code':'00000','msg':'success','requestTime':NOW+350,'data':rows}
            raw=json.dumps(payload)
            rest.append({
                'symbol':symbol,'interval':tf,
                'request_wall_ns':str(NOW*1000000),
                'response_wall_ns':str((NOW+500)*1000000),
                'raw_response':raw,
                'response_sha256':('0'*64 if corrupted_rest and symbol=='BTCUSDT' and tf=='1m'
                                   else hashlib.sha256(raw.encode()).hexdigest()),
                'error':None})
    ws=[]
    for s in SYMBOLS:
        raw=json.dumps({
            'arg':{'symbol':s,'topic':'books1','instType':'usdt-futures'},
            'action':'snapshot','data':[{'b':[['100','1']],'a':[['100.1','1']]}]})
        ws.append({'raw_frame':raw,'received_at_ms':NOW+2500,
                   'raw_sha256':('f'*64 if corrupted_ws and s=='BTCUSDT'
                                  else hashlib.sha256(raw.encode()).hexdigest())})
    with ZipFile(path,'w') as z:
        z.writestr('mtf_sample/rest_responses.jsonl',
                   '\n'.join(json.dumps(x) for x in rest)+'\n')
        z.writestr('mtf_sample/ws_raw_frames_00001.jsonl',
                   '\n'.join(json.dumps(x) for x in ws)+'\n')


class FrozenCaptureBridgeContract(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'recorded.zip'
    def engine_stub(self):
        def evaluate(context,at,p):
            return {'symbol':context['symbol'],'mode':p.mode,'setup':p.setup,
                    'decision':'NO_TRADE','reasons':['SETUP_ABSENT'],
                    'data_grade':'analysis','authority':'advisory_only',
                    'may_authorize_entry':False,'may_block_entry':False,
                    'may_modify_scores':False,'may_execute_exit':False}
        return SimpleNamespace(Parameters=lambda **x:SimpleNamespace(**x),
                               evaluate_long=evaluate)
    def test_synthetic_contract_12_observations_no_orders(self):
        example_zip(self.path)
        with patch('long_shadow_frozen_recorded_replay.frozen_engine',
                   return_value=self.engine_stub()):
            result=replay(self.path,'EXPLICIT_TEST_ENGINE')
        self.assertEqual(len(result['records']),12)
        self.assertEqual({x['decision'] for x in result['records']},{'NO_TRADE'})
        self.assertEqual({x['wallet_source'] for x in result['records']},
                         {'EXPLICIT_SYNTHETIC_FLAGS_ONLY'})
        self.assertEqual(result['orders_created'],0)
        self.assertFalse(result['paper_eligible'])
        self.assertTrue(result['historical_clock_not_live'])
    def test_rest_hash_tamper_rejected(self):
        example_zip(self.path,corrupted_rest=True)
        with patch('long_shadow_frozen_recorded_replay.frozen_engine',
                   return_value=self.engine_stub()):
            with self.assertRaisesRegex(ValueError,'rest_raw_sha_mismatch'):
                replay(self.path,'TEST')
    def test_ws_hash_tamper_rejected(self):
        example_zip(self.path,corrupted_ws=True)
        with patch('long_shadow_frozen_recorded_replay.frozen_engine',
                   return_value=self.engine_stub()):
            with self.assertRaisesRegex(ValueError,'ws_raw_sha_mismatch'):
                replay(self.path,'TEST')
    def test_loader_failure_is_not_bypassed(self):
        example_zip(self.path)
        with patch('long_shadow_frozen_recorded_replay.frozen_engine',
                   side_effect=ValueError('frozen_engine_sha_mismatch')):
            with self.assertRaisesRegex(ValueError,'frozen_engine_sha_mismatch'):
                replay(self.path,'TEST')

if __name__=='__main__':
    unittest.main()
