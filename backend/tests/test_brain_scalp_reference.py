"""Offline reference-context regressions: no exchange, model or wallet."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from director.brain_scalp.legacy_reference import (
    build_reference,REFERENCE_SOURCE_SHA,SOURCE_HASHES)

NOW=1800000000000


def reading():
    return {'symbol':'BTC','price':100.,'side':-1,'long_score':8,
            'short_score':73,'facts':{'rsi1h':44.,'ema20_50_1h':'giu',
            'ema50_200_4h':'giu','roc24h':-.02,'atr1h_pct':.01,
            'vol_ratio':1.8,'daily_trend':''},
            'why':['trend 4h (+20)','rottura minimi 20h (+10)']}


def context(value=None,**changes):
    args={'source_sha':REFERENCE_SOURCE_SHA,'source_hashes':dict(SOURCE_HASHES),
          'observed_ms':NOW,'now_ms':NOW+1000,'max_age_ms':60000}
    args.update(changes)
    return build_reference(reading() if value is None else value,**args)


class LegacyReference(unittest.TestCase):
    def test_both_scores_are_preserved_without_minting_order_or_confidence(self):
        src=reading();before=deepcopy(src)
        out=context(src)
        self.assertEqual(out['direction_scores'],{'LONG':8.,'SHORT':73.})
        self.assertEqual(out['legacy_preferred_side'],'SHORT')
        self.assertFalse(out['execution_permission'])
        self.assertEqual(out['authority'],'advisory_only')
        self.assertNotIn('plans',out)
        self.assertNotIn('confidence',out)
        self.assertEqual(src,before)
        self.assertFalse(out['opposite_side_reasons_available'])
        self.assertIn('equal indicator',str(out['cautions']))

    def test_long_and_neutral_are_not_overwritten_by_short_reference(self):
        for ls,ss,side,label in [(80,20,1,'LONG'),(40,40,0,'NEUTRAL')]:
            src=reading();src.update(long_score=ls,short_score=ss,side=side)
            self.assertEqual(context(src)['legacy_preferred_side'],label)

    def test_unknown_fields_and_trade_outcomes_are_not_forwarded(self):
        src=reading();src.update(net=9999,close_ms=NOW+999999,confidence=.99,
                                api_key='DO_NOT_FORWARD',plans=[{'symbol':'BTC'}])
        src['facts']['future_pnl']=9999
        text=json.dumps(context(src),allow_nan=False)
        for token in ('future_pnl','DO_NOT_FORWARD','close_ms','9999'):
            self.assertNotIn(token,text)

    def test_requires_frozen_source_sha_and_both_code_hashes(self):
        for changes in [
            {'source_sha':'5818aee'},
            {'source_sha':'x'*40},
            {'source_hashes':{'signals.py':SOURCE_HASHES['signals.py']}},
            {'source_hashes':dict(SOURCE_HASHES,**{'signals.py':'0'*64})},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError,'unverified_reference_source'):
                    context(**changes)

    def test_rejects_future_stale_and_invalid_clocks(self):
        for changes in [
            {'observed_ms':NOW+1001},{'observed_ms':NOW-60000},
            {'max_age_ms':0},{'max_age_ms':True},{'now_ms':float(NOW)},
        ]:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):context(**changes)
        self.assertEqual(context(now_ms=NOW+60000)['age_ms'],60000)

    def test_rejects_malformed_readings_scores_and_side(self):
        cases=[[],True,42,{},dict(reading(),long_score=float('nan')),
               dict(reading(),short_score=101),dict(reading(),side=1),
               dict(reading(),side=True),dict(reading(),why=[{}]),
               dict(reading(),facts=[]),dict(reading(),symbol='../BTC')]
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):context(value)

    def test_result_is_json_deterministic_and_has_no_shared_mutable_state(self):
        one=context();two=context()
        self.assertEqual(json.dumps(one,sort_keys=True,allow_nan=False),
                         json.dumps(two,sort_keys=True,allow_nan=False))
        one['source_hashes']['signals.py']='changed'
        one['selected_side_reasons'].append('changed')
        self.assertEqual(context(),two)

    def test_accepts_existing_reading_dataclass_without_importing_classical_engine(self):
        @dataclass
        class Reading:
            symbol:str='BTC'
            price:float=100.
            side:int=1
            long_score:int=70
            short_score:int=10
        self.assertEqual(context(Reading())['legacy_preferred_side'],'LONG')

    def test_pinned_git_sources_match_manifest(self):
        repo=Path(__file__).resolve().parents[2]
        for filename,digest in SOURCE_HASHES.items():
            raw=subprocess.check_output(
                ['git','show',REFERENCE_SOURCE_SHA+':backend/desk/'+filename],
                cwd=repo,timeout=15)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)

    def test_reference_cannot_be_submitted_as_ai_plan_or_mutate_wallets(self):
        import tempfile
        from director.brain_scalp.coordinator import BrainPair
        with tempfile.TemporaryDirectory() as folder:
            pair=BrainPair(folder,initialize=True,now_ms=NOW)
            try:
                before=[pair.hawk.store.load(),pair.bull.store.load()]
                with self.assertRaisesRegex(ValueError,'model_response_wrong_schema'):
                    pair.accept_ai_plans('hawk',context(),{}, {}, {},NOW+1000)
                self.assertEqual([pair.hawk.store.load(),pair.bull.store.load()],before)
            finally:
                pair.close()

    def test_real_archived_positions_reconcile_with_existing_auditor(self):
        from research.brain_short_reference.reconcile import reconcile
        repo=Path(__file__).resolve().parents[2]
        summary,chronology,original=reconcile(repo)
        self.assertEqual(original['groups']['golden']['all']['positions'],93)
        self.assertEqual(summary['groups']['golden']['SHORT']['n'],91)
        self.assertAlmostEqual(summary['groups']['golden']['SHORT']['net'],1992.7949)
        self.assertEqual(summary['groups']['golden']['LONG']['n'],2)
        self.assertAlmostEqual(summary['groups']['golden']['LONG']['net'],-131.4328)
        self.assertEqual(summary['groups']['crisis']['SHORT']['n'],48)
        self.assertAlmostEqual(summary['groups']['crisis']['SHORT']['net'],-373.6318)
        self.assertEqual(len(chronology.splitlines()),94)
        for values in summary['fingerprints'].values():
            self.assertEqual(values,SOURCE_HASHES)
