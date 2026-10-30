"""V1.1 must never filter Brain candidates or override DeepSeek's plan."""
import tempfile
import unittest

from backend.tests.test_brain_ai_context import NOW,markets,shortlist,CONTRACTS
from director.brain_scalp.coordinator import BrainPair
from director.brain_scalp.ai_context import decode


class V11Context(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.pair=BrainPair(self.tmp.name,initialize=True,now_ms=NOW)
    def tearDown(self):
        self.pair.close();self.tmp.cleanup()

    @staticmethod
    def opinion(state='BEARISH',bias=-0.7):
        return {'kind':'trend_engine_v11','source':'user_trend_engine_v1_1_adapted',
                'authority':'advisory_only','may_authorize_entry':False,
                'may_block_entry':False,'may_modify_scores':False,
                'state':state,'quality':'OK','ready':True,'symbol':'BTC',
                'observed_ms':NOW,'bias':bias,'five_minute_ready':False}

    def request(self,regime):
        return self.pair.prepare_ai_request('hawk',shortlist(),markets(),CONTRACTS,
                                            {},NOW,NOW+30000,None,regime)

    def test_bearish_indicator_does_not_remove_existing_long_candidate(self):
        before=self.pair.hawk.store.load()
        base=decode(self.request(None).payload_json)
        bearish=decode(self.request({'BTC':self.opinion()}).payload_json)
        self.assertEqual([v['symbol'] for v in base['candidates']],
                         [v['symbol'] for v in bearish['candidates']])
        self.assertEqual(bearish['candidates'][0]['side'],1)
        shown=bearish['candidates'][0]['regime_v11_indicator']
        self.assertEqual(shown['status'],'available')
        self.assertEqual(shown['value']['state'],'BEARISH')
        self.assertFalse(shown['value']['may_block_entry'])
        self.assertFalse(shown['value']['may_authorize_entry'])
        self.assertEqual(before,self.pair.hawk.store.load())

    def test_bad_untrusted_indicator_is_not_an_entrance_gate_or_prompt_injection(self):
        bad=self.opinion()
        bad.update(may_block_entry=True,api_key='SECRET',state='BULLISH')
        request=decode(self.request({'BTC':bad}).payload_json)
        self.assertEqual(len(request['candidates']),1)
        self.assertEqual(request['candidates'][0]['regime_v11_indicator']['status'],'unavailable')
        self.assertNotIn('SECRET',str(request))
        self.assertEqual(decode(self.request(None).payload_json)['candidates'][0]['regime_v11_indicator']['status'],
                         'not_supplied')


if __name__=='__main__':unittest.main()
