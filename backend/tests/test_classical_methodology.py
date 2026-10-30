"""Actual frozen scorer -> service evidence -> independent AI PAPER plan."""
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import hashlib
import numpy as np

from director.classical_methodology import frozen_reader, observe_methodology
from director.brain_scalp.legacy_reference import SOURCE_HASHES
from director.brain_scalp.ai_context import decode
from director.brain_scalp.ai_analysis import evaluate
from director.brain_scalp.coordinator import BrainPair
from director.brain_scalp.service import BrainService
from director.structural_advisory import observe_structure
from backend.tests.test_structural_advisory import history
from backend.tests.test_brain_ai_context import NOW, markets, shortlist, CONTRACTS, primary
from backend.tests.test_brain_scalp_group1 import plan


def rows_at_now():
    rows=history(turn=False)
    shift=NOW//900000*900000-(rows[-1][0]+900000)
    return [[b[0]+shift]+b[1:] for b in rows]


class ClassicalMethodology(unittest.TestCase):
    def test_frozen_files_match_current_classical_scorer_pin(self):
        root=Path(__file__).parents[1]/'director'/'frozen_classics'
        for name,digest in SOURCE_HASHES.items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest)

    def test_actual_method_runs_on_causal_history_and_keeps_both_scores(self):
        rows=rows_at_now()
        reading=frozen_reader()('BTC',np.array(rows),NOW)
        result=observe_methodology('BTC',rows,NOW)
        self.assertEqual(result['status'],'available')
        self.assertEqual(result['value']['direction_scores'],
                         {'LONG':reading.long_score,'SHORT':reading.short_score})
        self.assertGreater(reading.short_score,reading.long_score)
        self.assertFalse(result['value']['execution_permission'])
        self.assertEqual(result,observe_methodology('BTC',rows+[[NOW//900000*900000,'bad']],NOW))

    def test_insufficient_history_is_declared_not_fabricated(self):
        self.assertEqual(observe_methodology('BTC',rows_at_now()[-120:],NOW)['status'],
                         'insufficient_classical_history')

    def test_ai_can_take_long_against_real_classical_short_without_forced_review(self):
        with tempfile.TemporaryDirectory() as path:
            pair=BrainPair(path,initialize=True,now_ms=NOW)
            try:
                item=observe_structure('BTC',rows_at_now(),NOW)
                item['classical_methodology']=observe_methodology('BTC',rows_at_now(),NOW)
                before=pair.hawk.store.load()
                request=pair.prepare_ai_request('hawk',shortlist(),markets(),CONTRACTS,
                    {},NOW,NOW+30000,None,None,{'BTC':item})
                c=decode(request.payload_json)['candidates'][0]
                self.assertEqual(c['side'],1)
                self.assertEqual(c['classical_methodology']['value']['legacy_preferred_side'],'SHORT')
                self.assertEqual(pair.hawk.store.load(),before)
                result=evaluate(request,primary(request,[plan()]))
                self.assertFalse(result.reviewed)
                accepted=pair.accept_ai_analysis('hawk',request,result,markets(NOW+1000),CONTRACTS,NOW+1000)
                self.assertEqual(len(accepted['accepted']),1)
            finally:pair.close()

    def test_bad_advice_does_not_remove_candidate_or_leak_fields(self):
        with tempfile.TemporaryDirectory() as path:
            pair=BrainPair(path,initialize=True,now_ms=NOW)
            try:
                req=pair.prepare_ai_request('hawk',shortlist(),markets(),CONTRACTS,
                    {},NOW,NOW+30000,None,None,{'BTC':{'secret':'DO_NOT_LEAK'}})
                payload=decode(req.payload_json)
                self.assertEqual(len(payload['candidates']),1)
                self.assertNotIn('DO_NOT_LEAK',str(payload))
            finally:pair.close()

    def test_service_passes_completed_evidence_without_calling_loader_on_owner(self):
        service=BrainService.__new__(BrainService)
        service.clock=lambda:NOW
        service.account=Mock();service.account.brain.store.load.return_value={'positions':{}}
        service.feed=Mock();service.feed.poll.return_value=(markets(),CONTRACTS)
        service.trend_v11=Mock();service.trend_v11.poll.return_value={}
        service.structural=Mock();service.structural.poll.return_value={'BTC':{'kind':'fixture'}}
        service.structure_enabled=True;service.supervisor=Mock()
        with patch('director.brain_free.feeds.candles',side_effect=AssertionError('owner network')):
            service.tick()
        self.assertEqual(service.supervisor.step.call_args.kwargs['market_advisory'],
                         {'BTC':{'kind':'fixture'}})


if __name__=='__main__':unittest.main()
