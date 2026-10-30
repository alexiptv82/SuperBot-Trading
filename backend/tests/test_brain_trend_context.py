"""Brain AI receives early trend shifts as context only; never admission/veto."""
import tempfile
import unittest
from director.trend_advisory import observe
from director.brain_scalp.coordinator import BrainPair
from director.brain_scalp.ai_context import decode
from backend.tests.test_brain_ai_context import NOW,markets,shortlist,CONTRACTS


def turn():
    closes=[];p=150.
    for i in range(40):
        p*=1.003 if i>=36 else .999
        closes.append(p)
    rows=[[NOW-(40-i)*300000,p,p*1.001,p*.999,p,20]
          for i,p in enumerate(closes)]
    return observe('BTC',rows,NOW,300000)


class NonbindingTurn(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.pair=BrainPair(self.tmp.name,initialize=True,now_ms=NOW)
    def tearDown(self):
        self.pair.close();self.tmp.cleanup()

    def request(self,turns=None):
        return self.pair.prepare_ai_request('hawk',shortlist(),markets(),
            CONTRACTS,{},NOW,NOW+30000,turns)

    def test_turn_is_a_description_and_not_an_entry_gate(self):
        observation=turn()
        self.assertEqual(observation['phase'],'early_upshift')
        req=self.request({'BTC':observation})
        candidate=decode(req.payload_json)['candidates'][0]
        self.assertEqual(candidate['trend_change_observation']['status'],'available')
        self.assertEqual(candidate['trend_change_observation']['value']['phase'],'early_upshift')
        self.assertFalse(candidate['trend_change_observation']['value']['may_block_entry'])
        self.assertEqual(candidate['side'],1)

    def test_absent_invalid_stale_turn_does_not_remove_candidates(self):
        original=decode(self.request().payload_json)
        absent=original['candidates'][0]['trend_change_observation']
        self.assertEqual(absent['status'],'not_supplied')
        for bad in ({'BTC':dict(turn(),observed_ms=NOW-700000)},
                    {'BTC':dict(turn(),may_block_entry=True)},
                    {'BTC':{'api_key':'PRIVATE_SECRET'}},
                    {'ETH':turn()}):
            req=decode(self.request(bad).payload_json)
            self.assertEqual(len(req['candidates']),len(original['candidates']))
            self.assertNotIn('PRIVATE_SECRET',str(req))
            self.assertEqual(req['candidates'][0]['symbol'],'BTC')

    def test_no_turn_does_not_mutate_wallet_or_expand_lesson_training(self):
        before=self.pair.hawk.store.load()
        self.request({'BTC':turn()})
        self.assertEqual(self.pair.hawk.store.load(),before)


if __name__=='__main__':unittest.main()
