"""Atomic, separate-research-output tests. No real wallets or orders."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from long_shadow_observer_runner import (
    guarded_output_directory,publish_observation,_write_json_atomic,
)


NOW=1793549782400
CONSUMERS=('hawk','bull','brain')


def report(*, candidate=False):
    recs=[]
    for consumer in CONSUMERS:
        for sym in ('BTCUSDT','ETHUSDT'):
            for setup in ('CONTINUATION','REVERSAL'):
                recs.append({'schema':'long-shadow-record-v1',
                             'authority':'advisory_only',
                             'observation_only':True,
                             'consumer':consumer,'symbol':sym,'setup':setup,
                             'decision':'CANDIDATE' if candidate and sym=='ETHUSDT' and
                                setup=='REVERSAL' and consumer=='brain' else 'NO_TRADE',
                             'reasons':['SETUP_ABSENT'],
                             'as_of_ms':NOW,'can_execute_orders':False})
    return {'schema':'long-shadow-observer-v1','as_of_ms':NOW,
            'can_execute_orders':False,'orders_created':0,'paper_eligible':False,
            'records':recs}


class WriterGuards(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.input=self.path/'capture';self.input.mkdir()
        self.wallet=self.path/'wallet';self.wallet.mkdir()
        self.output=self.path/'results'
    def test_output_cannot_overlap_input_or_wallet(self):
        for target in (self.input,self.input/'results',self.wallet,
                       self.wallet/'results',self.path):
            with self.subTest(target=target):
                with self.assertRaisesRegex(ValueError,'collides'):
                    guarded_output_directory(target,
                        {'hawk':self.wallet},self.input)
    def test_output_separate_and_private(self):
        output=guarded_output_directory(self.output,
                                         {'hawk':self.wallet},self.input)
        self.assertTrue(output.is_dir())
    def test_symlink_output_rejected(self):
        self.output.symlink_to(self.wallet,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'symlink'):
            guarded_output_directory(self.output,
                                     {'hawk':self.wallet},self.input)
    def test_report_produces_exactly_3_advisories_and_full_audit(self):
        self.output.mkdir()
        publish_observation(report(candidate=True),self.output)
        self.assertEqual({p.name for p in self.output.iterdir()},
                         {'observer_state.json','hawk.json','bull.json','brain.json'})
        brain=json.loads((self.output/'brain.json').read_text())
        self.assertEqual(brain['symbol'],'ETHUSDT')
        self.assertEqual(brain['decision'],'CANDIDATE')
        self.assertFalse(brain['can_execute_orders'])
        all_records=json.loads((self.output/'observer_state.json').read_text())
        self.assertEqual(len(all_records['records']),12)
    def test_illicit_can_execute_report_rejected(self):
        self.output.mkdir()
        invalid=report()
        invalid['can_execute_orders']=True
        with self.assertRaisesRegex(ValueError,'invalid_observer_report'):
            publish_observation(invalid,self.output)
        self.assertEqual(list(self.output.iterdir()),[])
    def test_invalid_consumer_record_rejected(self):
        self.output.mkdir()
        bad=report()
        bad['records'][0]['can_execute_orders']=True
        with self.assertRaisesRegex(ValueError,'invalid_consumer_records'):
            publish_observation(bad,self.output)
    def test_atomic_replace_of_diagnostic_file(self):
        self.output.mkdir()
        _write_json_atomic(self.output,'hawk.json',{'schema':'first'})
        _write_json_atomic(self.output,'hawk.json',{'schema':'second'})
        self.assertEqual(json.loads((self.output/'hawk.json').read_text())['schema'],
                         'second')
        self.assertFalse(any(p.name.startswith('.shadow') for p in self.output.iterdir()))
    def test_disallow_arbitrary_filename(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError,'unexpected_output_name'):
            _write_json_atomic(self.output,'state_v2.json',{'bad':True})
    def test_no_wallet_file_changes(self):
        self.output.mkdir()
        wallet_file=self.wallet/'state_v2.json'
        wallet_file.write_text('{"positions":{}}')
        before=wallet_file.read_bytes()
        publish_observation(report(),self.output)
        self.assertEqual(wallet_file.read_bytes(),before)

if __name__=='__main__':
    unittest.main()
