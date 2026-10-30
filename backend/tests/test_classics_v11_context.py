"""Classical V1.1 shadow cannot alter rules or call a provider while disabled."""
import os
import unittest
from unittest.mock import patch
from desk import cli


class DummyShadow:
    def __init__(self,value):
        self.last_started=1800000000000
        self.value=value
        self.called=False
    def poll_public(self,now,selection,loader):
        self.called=True
        # The operator's wallet thread never invokes the loader here.
        return {'BTC':self.value}


class ClassicalV11(unittest.TestCase):
    def test_disabled_by_default_does_nothing_even_with_a_worker(self):
        state={'main':{'positions':{'BTC':{'id':5}}},'last_prices':{'BTC':99}}
        ctl={'_trend_v11':DummyShadow({})}
        original=repr(state)
        with patch.dict(os.environ,{'DESK_TREND_V11_SHADOW':'off'}):
            cli._poll_v11_shadow(state,ctl)
        self.assertEqual(repr(state),original)
        self.assertFalse(ctl['_trend_v11'].called)

    def test_bearish_observation_must_not_change_hawk_long_short_logic(self):
        opinion={'kind':'trend_engine_v11','symbol':'BTC','state':'BEARISH',
                 'observed_ms':1800000000000,'ready':True,'quality':'OK',
                 'authority':'advisory_only','may_block_entry':False,
                 'may_authorize_entry':False,'may_modify_scores':False}
        state={'main':{'positions':{'BTC':{'id':5}}},'last_prices':{'BTC':99}}
        ctl={'_trend_v11':DummyShadow(opinion)}
        with patch.dict(os.environ,{'DESK_TREND_V11_SHADOW':'on'}):
            with patch.object(cli.time,'time',return_value=1800000000):
                cli._poll_v11_shadow(state,ctl)
        self.assertEqual(state['main']['positions']['BTC']['id'],5)
        self.assertEqual(state['last_prices'],{'BTC':99})
        self.assertEqual(state['trend_v11_observations']['BTC']['state'],'BEARISH')
        self.assertFalse(state['trend_v11_observations']['BTC']['may_block_entry'])


if __name__=='__main__':unittest.main()
