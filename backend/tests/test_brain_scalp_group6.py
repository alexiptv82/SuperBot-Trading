"""Group 6 option C and margin-first PAPER allocation; no network or keys."""
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path
from director.brain_scalp.config import HAWK,BULL,SCANNER_MODEL,REVIEW_PROVIDER
from director.brain_scalp.engine import PaperWallet,_resize_for_budget,_risk
from director.brain_scalp.coordinator import BrainPair
from director.brain_scalp.plans import parse_plan
from backend.tests.test_brain_scalp_group1 import NOW,CONTRACTS,plan,quote

SYMBOLS=['BTC','ETH','BNB','XRP','SOL','ADA','DOGE','AVAX','DOT','LINK']
CONTRACT={s:dict(CONTRACTS['BTC']) for s in SYMBOLS}


def proposal(symbol='BTC',margin=250.,leverage=45,side=1,stop=None):
    raw=plan()
    raw.update(plan_id='group6-'+symbol,symbol=symbol,margin=margin,leverage=leverage,
               side=side,trigger='break_above' if side==1 else 'break_below',
               stop=(98. if side==1 else 102.) if stop is None else stop,
               target=104. if side==1 else 96.)
    return raw


def markets(now=NOW):
    return {s:{'quote':quote(ts=now),'bars':{'1m':[]},'funding':[]} for s in SYMBOLS}


class Group6Sizing(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.pair=BrainPair(self.tmp.name,initialize=True,now_ms=NOW)

    def tearDown(self):
        self.pair.close()
        self.tmp.cleanup()

    def test_option_c_keeps_capital_risk_and_margin_mandates(self):
        self.assertEqual((HAWK.start_cash,HAWK.max_margin_total,HAWK.slots), (1000.,950.,10))
        self.assertEqual((HAWK.min_margin,HAWK.max_margin_trade),(100,250))
        self.assertEqual((BULL.min_margin,BULL.max_margin_trade,BULL.slots),(150,350,3))
        for spec in (HAWK,BULL):
            self.assertEqual((spec.risk_trade_usd,spec.risk_portfolio_usd),(50,150))

    def test_high_leverage_keeps_250_margin_by_lowering_leverage_long_and_short(self):
        for side in (1,-1):
            w=self.pair.hawk
            state=w.store.load()
            raw=proposal(side=side)
            parsed=parse_plan(raw,w.spec,NOW,CONTRACT)
            fill=100*(1+side*w.cfg.slippage)
            size,lev,risk=_resize_for_budget(parsed,fill,state,w.spec,w.cfg,0)
            self.assertEqual(size,250.)
            self.assertEqual(lev,9)
            self.assertLessEqual(risk,50.)

    def test_trigger_executes_requested_margin_and_respects_risk(self):
        w=self.pair.hawk
        w.submit(proposal(),NOW,CONTRACT,{'BTC':quote()})
        out=w.tick(markets(NOW+1000),CONTRACT,NOW+1000)
        position=w.store.load()['positions']['BTC']
        self.assertGreaterEqual(position['margin'],249.98)
        self.assertEqual(position['leverage'],9)
        self.assertLessEqual(_risk(position,w.cfg),50.+1e-7)
        self.assertTrue(any(e['kind']=='plan_resized' for e in out['events']))

    def test_low_risk_does_not_raise_either_ai_request(self):
        w=self.pair.hawk
        parsed=parse_plan(proposal(margin=150,leverage=10,stop=99.8),w.spec,NOW,CONTRACT)
        size,lev,_=_resize_for_budget(parsed,100.02,w.store.load(),w.spec,w.cfg,0)
        self.assertEqual((size,lev),(150.,10))

    def test_margin_is_reduced_only_when_full_margin_at_one_x_cannot_fit(self):
        w=self.pair.hawk
        parsed=parse_plan(proposal(),w.spec,NOW,CONTRACT)
        size,lev,risk=_resize_for_budget(parsed,100.02,w.store.load(),
                                        replace(w.spec,risk_trade_usd=3.),w.cfg,0)
        self.assertEqual(lev,1)
        self.assertGreaterEqual(size,100.)
        self.assertLess(size,250.)
        self.assertLessEqual(risk,3.)

    def test_hawk_nine_minimum_reservations_leave_tenth_slot_empty(self):
        w=self.pair.hawk
        quotes={s:quote() for s in SYMBOLS}
        for sym in SYMBOLS[:9]:
            w.submit(proposal(sym,100,1),NOW,CONTRACT,quotes)
        before=w.store.load()
        with self.assertRaisesRegex(ValueError,'insufficient_capital_for_min_margin'):
            w.submit(proposal('LINK',100,1),NOW,CONTRACT,quotes)
        self.assertEqual(w.store.load(),before)
        self.assertEqual(sum(p['margin'] for p in before['plans'].values()),900.)

    def test_bull_third_reservation_fits_residual_capital_and_survives_restart(self):
        w=self.pair.bull
        quotes={s:quote() for s in SYMBOLS}
        for sym in SYMBOLS[:3]:
            accepted=w.submit(proposal(sym,350,10),NOW,CONTRACT,quotes)
        self.assertEqual(accepted.margin,250.)
        before=w.store.load()
        self.assertEqual([before['plans'][sym]['margin'] for sym in SYMBOLS[:3]],
                         [350,350,250])
        w.close()
        self.pair.bull=PaperWallet(Path(self.tmp.name)/'bull','bull')
        self.assertEqual(self.pair.bull.store.load(),before)
        events=[kind for kind, in self.pair.bull.store.db.execute('SELECT kind FROM events')]
        self.assertIn('plan_reservation_resized',events)

    def test_other_pending_cash_and_entry_fees_cannot_be_spent_twice(self):
        w=self.pair.hawk
        state=w.store.load();state['cash']=810.;w.store.commit(state,NOW)
        quotes={s:quote() for s in SYMBOLS}
        for sym in SYMBOLS[:3]:
            w.submit(proposal(sym,250,25),NOW,CONTRACT,quotes)
        before=w.store.load()
        reserved=sum(p['margin']*(1+p['leverage']*w.cfg.fee_rate)
                     for p in before['plans'].values())
        self.assertLessEqual(reserved,810.)
        with self.assertRaisesRegex(ValueError,'insufficient_capital_for_min_margin'):
            w.submit(proposal('XRP',100,25),NOW,CONTRACT,quotes)
        self.assertEqual(w.store.load(),before)

    def test_coarse_exchange_lot_cannot_create_subminimum_trade(self):
        w=self.pair.hawk
        raw=proposal(margin=100,leverage=10,stop=99.8)
        w.submit(raw,NOW,CONTRACT,{'BTC':quote()})
        contracts=dict(CONTRACT,BTC=dict(CONTRACT['BTC'],qty_step=3.,min_qty=3.))
        out=w.tick(markets(NOW+1000),contracts,NOW+1000)
        state=w.store.load()
        self.assertEqual(state['positions'],{})
        self.assertEqual(state['cash'],1000.)
        self.assertFalse(any(e['kind']=='open' for e in out['events']))
        self.assertTrue(any(e.get('why')=='margin_below_min_after_execution_normalization'
                            for e in out['events']))

    def test_pair_returns_allocated_size_to_caller_and_keeps_wallets_separate(self):
        raw={'plans':[proposal(sym,350,10) for sym in SYMBOLS[:3]]}
        shortlist={'candidates':[{'symbol':sym,'side':1} for sym in SYMBOLS[:3]]}
        out=self.pair.accept_ai_plans('bull',raw,shortlist,markets(),CONTRACT,NOW)
        self.assertEqual([p['margin'] for p in out['accepted']],[350,350,250])
        self.assertEqual(out['rejected'],[])
        self.assertEqual(self.pair.hawk.store.load()['plans'],{})

    def test_multiple_triggered_plans_stay_within_aggregate_risk_and_capital(self):
        w=self.pair.hawk
        quotes={s:quote() for s in SYMBOLS}
        for sym in SYMBOLS[:4]:
            w.submit(proposal(sym,250,25),NOW,CONTRACT,quotes)
        w.tick(markets(NOW+1000),CONTRACT,NOW+1000)
        state=w.store.load()
        positions=list(state['positions'].values())
        self.assertGreaterEqual(len(positions),3)
        self.assertTrue(all(p['margin']>=100-.01-1e-8 for p in positions))
        self.assertTrue(all(_risk(p,w.cfg)<=50+1e-7 for p in positions))
        self.assertLessEqual(sum(_risk(p,w.cfg) for p in positions),150+1e-7)
        self.assertLessEqual(sum(p['margin'] for p in positions),950+1e-7)
        self.assertGreaterEqual(state['cash'],0.)

    def test_current_models_are_isolated_from_brain_free_defaults(self):
        self.assertEqual(SCANNER_MODEL,'deepseek-flash')
        self.assertEqual(REVIEW_PROVIDER,'claude')
        for spec in (HAWK,BULL):
            self.assertEqual(spec.brain_config().model,'deepseek-flash')
            self.assertEqual(spec.brain_config().thinking,'high')
        from director.brain_free.config import Config
        self.assertEqual(Config().thinking,'low')
