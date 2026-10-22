"""Regression tests for proposal A only. No LLM/network or changes to B policies."""
import ast
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from desk import signals,brain
from desk.engine import PaperAccount,Limits
from desk.position_card import metrics

NOW=1792627200000


def bars(n,step,flat=False):
    c=np.full(n,100.) if flat else np.linspace(90.,110.,n)
    t=NOW-n*step+np.arange(n)*step
    return np.column_stack((t,c,c+.01,c-.01,c,np.ones(n)))


class ProposalTests(unittest.TestCase):
    def test_rsi_flat_is_neutral(self):self.assertEqual(signals.rsi(np.ones(100)),50.)

    def test_flat_scores_neutral_with_seasonality_off(self):
        with patch.object(signals,'get_seasonal',return_value=SimpleNamespace(long_bonus=0,short_bonus=0,note='')):
            r=signals.read_symbol('SYNTHETIC',bars(1000,900000,True),NOW,
                                  daily=bars(200,86400000,True),four_hour=bars(300,14400000,True))
        self.assertEqual((r.side,r.long_score,r.short_score),(0,0,0))
        self.assertIn('neutro',r.facts['daily_trend'])

    def test_insufficient_4h_never_uses_ema61(self):
        r=signals.read_symbol('SYNTHETIC',bars(1000,900000),NOW)
        self.assertIsNone(r.facts['slow_4h_period']);self.assertEqual(r.facts['ema50_200_4h'],'nd')
        r=signals.read_symbol('SYNTHETIC',bars(1000,900000),NOW,four_hour=bars(300,14400000))
        self.assertEqual(r.facts['slow_4h_period'],200);self.assertEqual(r.facts['bars_4h'],300)

    def test_native_bars_reject_gaps_duplicates_and_open_bar(self):
        data=bars(300,14400000)
        self.assertEqual(len(signals.closed_four_hour(data,NOW)),300)
        self.assertEqual(len(signals.closed_four_hour(np.delete(data,10,axis=0),NOW)),0)
        self.assertEqual(len(signals.closed_four_hour(np.vstack((data,data[-1])),NOW)),0)
        opened=data[-1].copy();opened[0]=NOW
        self.assertEqual(len(signals.closed_four_hour(np.vstack((data,opened)),NOW)),300)

    def test_position_metrics_match_independent_cashflows_and_constant_reference(self):
        acc=PaperAccount();p,_=acc.open('SYNTHETIC',1,50,10,100,99,102,NOW,{'SYNTHETIC':100})
        acc.partial_close('SYNTHETIC',101,NOW+1000,.5)
        result=metrics(p,101,NOW+2000,acc.closed,acc.limits)
        # Reference stays original; residual total margin is halved.
        self.assertEqual(result['reference_margin'],50)
        self.assertEqual(result['total_margin'],25)
        self.assertIsNone(result['giveback_net_roi_pp'])
        clone=PaperAccount.from_dict(acc.to_dict())
        final=clone.close('SYNTHETIC',101,NOW+2000)
        net=acc.closed[0]['net']+final['net']
        self.assertAlmostEqual(result['roi_net_pct'],net/50*100,places=3)

    def test_score_card_uses_own_side_and_includes_tp(self):
        tree=ast.parse((ROOT/'backend/desk/cli.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='position_info')
        ns={'Limits':Limits};exec(compile(ast.Module(body=[fn],type_ignores=[]),'<actual_position_info>','exec'),ns)
        acc=PaperAccount();p,_=acc.open('SYNTHETIC',1,50,10,100,99,102,NOW,{'SYNTHETIC':100})
        r=signals.Reading('SYNTHETIC',100,score=85,long_score=10,short_score=85)
        card=ns['position_info'](p,101,{'SYNTHETIC':r},NOW+1,acc.closed,acc.limits)
        self.assertEqual(card['score_now'],10);self.assertEqual(card['score_opposite'],85)
        self.assertEqual(card['tp'],102)
        text=brain.build_prompt(dict(equity=1000,cash=900,margin=100,n_open=1,day_pnl=0),[],[card],[],'')
        self.assertIn('ROI_base=iniziale+DCA_non_ridotta_dai_parziali',text)
        self.assertIn('score_lato 10 score_opposto 85',text)

    def test_native_four_hour_cache_uses_correct_granularity(self):
        tree=ast.parse((ROOT/'backend/desk/cli.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='four_hour_bars')
        calls=[]
        def fetch(symbol,bar,limit):
            calls.append((bar,limit));return bars(300,14400000).tolist()
        ns={'_FOUR_HOUR_CACHE':{},'fetch_candles':fetch}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<actual_four_hour_cache>','exec'),ns)
        self.assertEqual(len(ns['four_hour_bars']('SYNTHETIC',NOW)),300)
        ns['four_hour_bars']('SYNTHETIC',NOW+1)
        self.assertEqual(calls,[('4H',300)])

    def test_example_bull_arithmetic(self):
        self.assertIn('SL 2% = 120$ rischio',brain.SYSTEM_BULL)
        self.assertIn('300$ (5% con leva 20x)',brain.SYSTEM_BULL)

    def test_mirror_transform_high_low_and_volume(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('mirror',ROOT/'deploy/scripts/mirror_pair_audit.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        data=bars(1000,900000);result=m.mirror(data)
        np.testing.assert_allclose(result[:,2],1/data[:,3]);np.testing.assert_allclose(result[:,3],1/data[:,2])
        np.testing.assert_array_equal(result[:,5],data[:,5]);np.testing.assert_allclose(m.mirror(result),data)
        self.assertEqual(m.exact_mcnemar(0,0),1.)
        self.assertAlmostEqual(m.exact_mcnemar(0,5),.0625)

if __name__=='__main__':unittest.main()
