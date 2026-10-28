"""Offline tests: never call provider, exchange API or VPS."""
from pathlib import Path
import tempfile
import unittest
from director.brain_scalp.config import BULL,HAWK
from director.brain_scalp.engine import PaperWallet
from director.brain_scalp.plans import parse_plan
from director.brain_scalp.scanner import scan

NOW=1800000000000
CONTRACT={'BTC':{'status':'normal','max_leverage':45,'maintenance':.005,
                 'price_step':.01,'qty_step':.001,'min_qty':.001,'min_notional':5.}}

def q(price=100.,ts=NOW): return {'price':price,'ts_ms':ts}
def quote_map(): return {'BTC':q()}
def market(price=100.,ts=NOW):
    return {'BTC':{'quote':q(price,ts),'bars':{'1m':[]},'funding':[]}}
def plan(name='x12345678',now=NOW,side=1,**kw):
    d={'plan_id':name,'symbol':'BTC','side':side,'created_ms':now,
       'expires_ms':now+240000,'trigger':'break_above' if side==1 else 'break_below',
       'trigger_price':100.,'stop':99.8 if side==1 else 100.2,
       'target':102. if side==1 else 98.,'margin':100. if side==1 else 150.,
       'leverage':10,'hold_max_ms':3600000,'protect_after_usd':5.,
       'take_net_usd':10.,'reason':'breakout confirmed with fresh volume',
       'invalidation':'close beyond invalidation level'}
    d.update(kw)
    return d


class DualWallet(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.h=PaperWallet(Path(self.temp.name)/'hawk','hawk',initialize=True,now_ms=NOW)
        self.b=PaperWallet(Path(self.temp.name)/'bull','bull',initialize=True,now_ms=NOW)
    def tearDown(self):
        self.h.close();self.b.close();self.temp.cleanup()

    def test_wallet_separation(self):
        a,b=self.h.store.load(),self.b.store.load()
        self.assertEqual((a['account_id'],a['cash']),('brain-scalp-hawk-paper',1000))
        self.assertEqual((b['account_id'],b['cash']),('brain-scalp-bull-paper',1000))
        self.assertEqual((HAWK.slots,BULL.slots),(10,3))
        self.assertNotEqual(self.h.store.root,self.b.store.root)
        self.assertEqual((a['positions'],b['positions']),({},{}))

    def test_reject_duplicate_writer(self):
        with self.assertRaisesRegex(ValueError,'wallet_writer_already_active'):
            PaperWallet(self.h.store.root,'hawk')

    def test_never_implicitly_reset(self):
        with self.assertRaisesRegex(ValueError,'wallet_root_not_empty'):
            PaperWallet(self.h.store.root,'hawk',initialize=True,now_ms=NOW)
        with self.assertRaisesRegex(ValueError,'explicit_initialization_required'):
            PaperWallet(Path(self.temp.name)/'notfound'/'bull','bull')

    def test_reject_foreign_volume(self):
        with self.assertRaises(ValueError):
            PaperWallet(Path(self.temp.name)/'superbot-brain-free'/'hawk','hawk',True,NOW)

    def test_duplicate_and_reserved_slot(self):
        self.h.submit(plan(),NOW,CONTRACT,quote_map())
        with self.assertRaisesRegex(ValueError,'duplicate_plan_id'):
            self.h.submit(plan(),NOW,CONTRACT,quote_map())
        with self.assertRaisesRegex(ValueError,'symbol_already_reserved'):
            self.h.submit(plan(name='x99999999'),NOW,CONTRACT,quote_map())

    def test_open_long_isolated_from_bull(self):
        self.h.submit(plan(),NOW,CONTRACT,quote_map())
        out=self.h.tick(market(),CONTRACT,NOW+1000)
        self.assertEqual((out['positions'],out['pending']),(1,0))
        self.assertEqual(out['events'][-1]['kind'],'open')
        self.assertEqual(self.b.store.load()['cash'],1000.)
        self.assertEqual(self.h.store.load()['positions']['BTC']['side'],1)

    def test_short_net_profit_exit(self):
        self.b.submit(plan(side=-1,target=95.),NOW,CONTRACT,quote_map())
        opened=self.b.tick(market(),CONTRACT,NOW+1000)
        self.assertEqual(opened['positions'],1)
        closed=self.b.tick(market(price=98.,ts=NOW+3000),CONTRACT,NOW+3000)
        self.assertEqual(closed['positions'],0)
        self.assertTrue(any(e.get('kind')=='trade_closed' and
            e.get('reason')=='scalp_net_target_observed' for e in closed['events']))

    def test_expiration_frees_slot(self):
        self.h.submit(plan(),NOW,CONTRACT,quote_map())
        result=self.h.tick(market(price=99.,ts=NOW+240000),CONTRACT,NOW+240000)
        self.assertEqual(result['pending'],0)
        self.assertTrue(any(e['kind']=='plan_expired' for e in result['events']))

    def test_stale_quote_cannot_open(self):
        self.h.submit(plan(),NOW,CONTRACT,quote_map())
        res=self.h.tick(market(price=101,ts=NOW-31000),CONTRACT,NOW+1000)
        self.assertEqual((res['positions'],res['pending']),(0,1))

    def test_risk_cap_rejects_excess_leverage(self):
        self.h.submit(plan(margin=250.,leverage=45,stop=98.),NOW,CONTRACT,quote_map())
        out=self.h.tick(market(),CONTRACT,NOW+1000)
        self.assertEqual(out['positions'],0)
        self.assertTrue(any(e.get('why')=='stop_risk_budget' for e in out['events']))

    def test_backup_and_reopen_persist(self):
        self.h.submit(plan(),NOW,CONTRACT,quote_map())
        before=self.h.store.load()
        self.h.store.backup(Path(self.temp.name)/'backup.sqlite3')
        self.h.close()
        self.h=PaperWallet(Path(self.temp.name)/'hawk','hawk')
        self.assertEqual(before['plans'],self.h.store.load()['plans'])
        self.assertEqual(before['cash'],self.h.store.load()['cash'])

    def test_plan_rejects_malformed_fields(self):
        for bad in [plan(side=0),plan(trigger='break_below'),plan(stop=110.),
                    plan(expires_ms=NOW+600000),plan(created_ms=NOW-100000),
                    plan(leverage=80),plan(margin=10),plan(stop=float('nan'))]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                parse_plan(bad,HAWK,NOW,CONTRACT)


class Scanner(unittest.TestCase):
    def bars(self,duration,n,side):
        start=NOW-duration*n;rows=[]
        for i in range(n):
            if i==n-1:
                op=100.;close=103. if side>0 else 97.
                hi=max(op,close)+.1;lo=min(op,close)-.1;vol=250.
            else:
                op=close=100.;hi=100.5;lo=99.5;vol=100.
            rows.append([start+i*duration,op,hi,lo,close,vol])
        return rows

    def test_symmetric_long_and_short(self):
        for side in (1,-1):
            data={'BTC':{'quote':q(),'bars':{'1m':self.bars(60000,18,side),
                                            '5m':self.bars(300000,22,side)}}}
            res=scan(data,NOW)
            self.assertEqual(res['symbols_checked'],1)
            self.assertEqual(len(res['candidates']),1)
            self.assertEqual(res['candidates'][0]['side'],side)

    def test_future_bar_is_not_used(self):
        data={'BTC':{'quote':q(),'bars':{'1m':self.bars(60000,18,1),
                                        '5m':self.bars(300000,22,1)}}}
        self.assertEqual(len(scan(data,NOW)['candidates']),1)
        self.assertEqual(scan(data,NOW-300000+1000)['candidates'],[])

    def test_missing_and_stale_explained(self):
        data={'BTC':{'quote':q(ts=NOW-31000),'bars':{'1m':[],'5m':[]}},
              'ETH':{'quote':q(),'bars':{'1m':[],'5m':[]}}}
        res=scan(data,NOW)
        self.assertEqual(res['coverage']['BTC'],'quote_missing_or_stale')
        self.assertEqual(res['coverage']['ETH'],'closed_bars_missing_gap_or_stale')


if __name__=='__main__': unittest.main()
