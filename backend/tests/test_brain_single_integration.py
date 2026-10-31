"""Offline integration smoke: no real API, secrets, or exchange orders."""
from dataclasses import asdict,replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from director.brain_scalp.config import HAWK
from director.brain_scalp.market_bridge import fetch_closed_gap,validate_feed_snapshot,PublicBrainFeed
from director.brain_scalp.transports import PriceLimit,make_primary,make_reviewer,claude_message
from director.brain_scalp.service import mandate_from_json,required_env,BrainService,main
from backend.tests.test_brain_resume import NOW,markets,CONTRACTS

SPEC=replace(HAWK,name='brain',account_id='brain-scalp-single-paper',
             start_cash=2000,max_margin_total=1600)


def setup_env(path):
    return {
        'DESK_MODE':'paper','BRAIN_SINGLE_ENABLED':'paper',
        'BRAIN_SINGLE_MANDATE_JSON':json.dumps(asdict(SPEC)),
        'BRAIN_SINGLE_DATA_DIR':str(path/'wallet'),
        'BRAIN_SINGLE_SNAPSHOT_PATH':str(path/'snapshot.json'),
        'BRAIN_AI_BUDGET_USD':'1.0','BRAIN_DEEPSEEK_INPUT_USD_M':'1.0',
        'BRAIN_DEEPSEEK_OUTPUT_USD_M':'2.0','BRAIN_AI_MAX_INPUT_BYTES':'120000',
        'BRAIN_AI_MAX_OUTPUT_TOKENS':'4096','DEEPSEEK_API_KEY':'synthetic-do-not-send',
    }


class FakeReader:
    def __init__(self,data=None):self.data=data or markets(NOW);self.closed=False
    def poll(self,positions,now):
        return self.data,CONTRACTS,{}
    def close(self):self.closed=True


class Response:
    def __init__(self,text):self.text=text
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def read(self,n):return self.text[:n]


class Integration(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()

    def test_reject_partial_or_modified_mandate_and_no_data_writes(self):
        env=setup_env(self.root)
        self.assertEqual(main(['--validate'],env)['status'],'valid_offline_configuration')
        self.assertFalse((self.root/'wallet').exists())
        spec=json.loads(env['BRAIN_SINGLE_MANDATE_JSON']);del spec['daily_stop_pct']
        with self.assertRaisesRegex(ValueError,'complete_explicit_brain_mandate'):
            mandate_from_json(json.dumps(spec))
        env['BRAIN_SINGLE_MANDATE_JSON']=json.dumps(asdict(replace(SPEC,start_cash=900,
            max_margin_total=950)))
        with self.assertRaisesRegex(ValueError,'invalid_wallet_mandate'):
            required_env(env)
        env=setup_env(self.root);env['DESK_MODE']='live'
        with self.assertRaisesRegex(ValueError,'paper_mode'):
            required_env(env)

    def test_budget_is_conservative_and_requires_explicit_provider_prices(self):
        rule=PriceLimit('1','2','9','11','1',reviewer_enabled=False)
        daily,res=rule.reservation()
        self.assertEqual(daily,1000000)
        self.assertEqual(res,128192)
        low=PriceLimit('1','2','9','11','0.01',reviewer_enabled=False)
        with self.assertRaisesRegex(ValueError,'reservation'):
            low.reservation()
        with self.assertRaisesRegex(ValueError,'invalid_ai_price'):
            PriceLimit('1','2','','','1').reservation()
        env=setup_env(self.root);env['ANTHROPIC_API_KEY']='synthetic'
        with self.assertRaisesRegex(ValueError,'reviewer_key_model'):
            required_env(env)

    def test_explicit_init_and_restart_backup(self):
        env=setup_env(self.root)
        with self.assertRaisesRegex(ValueError,'not_approved'):
            main(['--initialize-new'],env)
        env['BRAIN_INIT_ACK']='CREATE_NEW_EMPTY_PAPER_ACCOUNT'
        self.assertEqual(main(['--initialize-new'],env)['status'],'new_paper_wallet_initialized')
        with self.assertRaises(ValueError):
            main(['--initialize-new'],env)
        feed=PublicBrainFeed(reader=FakeReader(),fetcher=lambda _:None)
        config=required_env(env);now=NOW
        s=BrainService(config,feed=feed,clock_ms=lambda:now)
        try:
            result=s.tick()
            self.assertIn('analysis_status',result)
            snap=json.loads((self.root/'snapshot.json').read_text())
            self.assertEqual(snap['schema_version'],2)
            self.assertEqual(snap['account']['initial_cash'],2000)
            backup=s.backup(self.root/'before_start.sqlite3')
            self.assertTrue(backup.exists())
            self.assertFalse((self.root/'wallet'/'hawk').exists())
        finally:s.close()
        self.assertTrue(feed.reader.closed)
        s2=BrainService(config,feed=PublicBrainFeed(reader=FakeReader()),clock_ms=lambda:now)
        s2.close()

    def test_transport_flags_model_and_timeout_without_calling_network(self):
        called=[]
        def fake(key,system,user,cfg):
            called.append((cfg.model,cfg.thinking,cfg.timeout_s,cfg.max_tokens))
            return {'error':'balance','usage':None}
        primary=make_primary('synthetic',timeout_s=8,inner=fake)
        self.assertEqual(primary('system','{}')['error'],'balance')
        self.assertEqual(called,[('deepseek-flash','high',8,4096)])
        with self.assertRaisesRegex(ValueError,'reserved_ceiling'):
            primary('a'*120001,'{}')

    def test_feed_exception_still_reaches_owner_and_snapshot(self):
        env=setup_env(self.root)
        feed=PublicBrainFeed(reader=FakeReader(),fetcher=lambda _:None)
        s=BrainService(required_env(env),feed=feed,clock_ms=lambda:NOW,initialize=True)
        try:
            from backend.tests.test_brain_resume import plan,shortlist
            s.account.accept_ai_plans('brain',{'plans':[plan()]},shortlist(),markets(),CONTRACTS,NOW)
            s.account.tick(markets(),CONTRACTS,NOW+1)
            before=s.account.brain.store.load()['positions']['BTC']
            s.clock=lambda:NOW+1000
            s.supervisor.clock=s.clock
            feed.poll=Mock(side_effect=RuntimeError('SYNTHETIC_SECRET_BODY'))
            result=s.tick()
            self.assertIn('tick',result)
            self.assertEqual(s.last_markets,{})
            snap=json.loads((self.root/'snapshot.json').read_text())
            self.assertEqual(snap['schema_version'],2)
            self.assertEqual(snap['account']['positions'][0]['price_status'],'unavailable')
            self.assertEqual(s.account.brain.store.load()['positions']['BTC']['qty'],before['qty'])
            self.assertNotIn('SYNTHETIC_SECRET_BODY',json.dumps(result))
        finally:s.close()

    def test_claude_reviewer_uses_current_messages_api_no_key_echo(self):
        incoming=[]
        def opener(req,timeout):
            incoming.append((req,timeout))
            return Response(json.dumps({'stop_reason':'end_turn',
                'content':[{'type':'text','text':'{"ok":true}'}],
                'usage':{'input_tokens':50,'output_tokens':30}}).encode())
        text,usage=claude_message('synthetic','approved-model','sys','{}',
                                  opener=opener)
        self.assertEqual(json.loads(text),{'ok':True})
        self.assertEqual(usage['output_tokens'],30)
        self.assertEqual(incoming[0][0].get_header('X-api-key'),'synthetic')
        self.assertEqual(incoming[0][0].full_url,'https://api.anthropic.com/v1/messages')
        self.assertLessEqual(incoming[0][1],10)
        self.assertNotIn('synthetic',text)
        reviewer=make_reviewer('synthetic','model',
            inner=lambda key,model,system,user,**kw:('{"ok":true}',{}))
        self.assertEqual(reviewer('sys','{}')[0],'{"ok":true}')

    def test_backfill_exact_contiguous_and_untrusted_bars_rejected(self):
        first=(NOW//60000-3)*60000
        calls=[]
        def api(url):
            calls.append(url)
            return {'data':[[str(t),'100','101','99','100','1','100']
                            for t in (first,first+60000,first+120000)]}
        rows=fetch_closed_gap('BTC',first,first+3*60000,api)
        self.assertEqual(len(rows),3)
        self.assertIn('/history-candles?',calls[0])
        self.assertIn('productType=USDT-FUTURES',calls[0])
        self.assertIn('startTime=',calls[0])
        with self.assertRaisesRegex(ValueError,'gap_incomplete'):
            fetch_closed_gap('BTC',first,first+4*60000,api)
        with self.assertRaises(ValueError):
            fetch_closed_gap('BTC',first,first+201*60000,api)
        broken=lambda url:{'data':[[str(first),'100','99','101','100','1']]}
        with self.assertRaisesRegex(ValueError,'untrusted_gap_candle'):
            fetch_closed_gap('BTC',first,first+60000,broken)

    def test_missing_or_stale_public_market_never_fabricates_quotes(self):
        m={'BTC':{'quote':{'price':float('nan'),'ts_ms':NOW},'bars':{'1m':[]}},
           'ETH':{'quote':{'price':100,'ts_ms':NOW},'bars':{'1m':[]}}}
        new,contracts=validate_feed_snapshot(m,CONTRACTS)
        self.assertNotIn('quote',new['BTC'])
        self.assertEqual(new['ETH']['quote']['price'],100)
        self.assertFalse(new['ETH']['bars']['5m'])
        self.assertIs(contracts,CONTRACTS)


if __name__=='__main__':unittest.main()
