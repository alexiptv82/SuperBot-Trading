"""Offline probe cannot elevate authority or manufacture empty wallets."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from long_shadow_offline_probe import (PINNED_ENGINE_SHA256,
                                       evaluate_capture,write_new_output,frozen_engine)

class ProbeTest(unittest.TestCase):
    def test_engine_pin_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'engine.py';path.write_text('pass\n')
            with self.assertRaisesRegex(ValueError,'sha_mismatch'):
                frozen_engine(path)

    def test_missing_wallet_produces_no_trade_not_candidate(self):
        ctx={'BTCUSDT':{'symbol':'BTCUSDT','bars':{},
                         'quote':{'available_at_ms':1793549782000,'bid':100.,'ask':100.1}}}
        engine=SimpleNamespace(
            Parameters=lambda **kw: kw,
            evaluate_long=lambda context,at,parameters: {
                'decision':'NO_TRADE','reasons':['SETUP_ABSENT'],
                'authority':'advisory_only',
                'may_authorize_entry':False,'may_block_entry':False,
                'may_modify_scores':False,'may_execute_exit':False})
        def wallet(consumer,**kw):
            if consumer=='brain':
                return {'status':'unavailable'}
            return {'status':'ok','snapshot':{'positions':[
                {'symbol':'BTCUSDT','status':'OPEN','side':'SHORT'}] if consumer=='hawk' else []}}
        with patch('long_shadow_offline_probe.startup_contexts',return_value=ctx), \
             patch('long_shadow_offline_probe.frozen_engine',return_value=engine), \
             patch('long_shadow_offline_probe.wallet_snapshot',side_effect=wallet):
            result=evaluate_capture(capture_zip='unused',engine_file='unused',
               roots={'hawk':'A','bull':'B','brain':'C'})
        self.assertEqual(len(result['records']),5)
        self.assertEqual(result['orders_created'],0)
        self.assertFalse(result['paper_eligible'])
        self.assertTrue(all(not x['can_execute_orders'] for x in result['records']))
        brain=[x for x in result['records'] if x['consumer']=='brain']
        self.assertEqual(brain[0]['reasons'],['WALLET_UNAVAILABLE'])
        self.assertEqual(brain[0]['decision'],'NO_TRADE')

    def test_rejects_engine_elevating_order_authority(self):
        context={'BTCUSDT':{'symbol':'BTCUSDT','quote':{'available_at_ms':1793549782000},'bars':{}}}
        engine=SimpleNamespace(
          Parameters=lambda **kw:kw,
          evaluate_long=lambda *_:{'decision':'CANDIDATE','reasons':[],
             'authority':'advisory_only','may_authorize_entry':True,
             'may_block_entry':False,'may_modify_scores':False,'may_execute_exit':False})
        with patch('long_shadow_offline_probe.startup_contexts',return_value=context),\
             patch('long_shadow_offline_probe.frozen_engine',return_value=engine),\
             patch('long_shadow_offline_probe.wallet_snapshot',return_value={
                'status':'ok','snapshot':{'positions':[]}}):
            with self.assertRaisesRegex(ValueError,'engine_authority_contract_failed'):
                evaluate_capture(capture_zip='none',engine_file='none',roots={})

    def test_output_never_overwrites_existing_folder(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'output'
            target.mkdir()
            with self.assertRaises(FileExistsError):
                write_new_output({'records':[]},target)

if __name__=='__main__':
    unittest.main()
