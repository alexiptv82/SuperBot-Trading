"""Offline tests: no provider/exchange/VPS access."""
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from director.brain_pilot import prompt_builder as pb
from director.brain_pilot.pilot import Pilot, Store, BAR, config, parse_response
from director.brain_pilot.portfolio import Portfolio
from director.ai_shadow.deepseek import ModelError

NOW=1793059200000  # aligned UTC day


def frames(now=NOW,down=False,price=100):
    out={}
    for tf,ms in pb.TF_MS.items():
        end=now//ms*ms
        c=np.linspace(price*(1.1 if down else .9),price,120)
        out[tf]=[[end-(120-i)*ms,float(x),float(x*1.0003),float(x*.9997),float(x),100.] for i,x in enumerate(c)]
    return out


class Cache:
    def __init__(self):self.data={};self.missing=set();self.down=False;self.price=100
    def refresh(self,now,bar_t):
        self.data={s:frames(bar_t+BAR,self.down,self.price) for s in ("BTC","ETH") if s not in self.missing}
        return self.data


class Model:
    def __init__(self,replies=None):self.replies=list(replies or []);self.calls=[]
    def __call__(self,cfg,key,system,user):
        self.calls.append(json.loads(user))
        row=self.replies.pop(0) if self.replies else {"market_view":"range; no trigger yet","decisions":[],"next_check_minutes":15}
        if isinstance(row,Exception):raise row
        return {"content":json.dumps(row),"usage":{"hit":0,"miss":10,"out":10}}


def decision(action="open_long",**kw):
    return dict(symbol="ETH",action=action,size_pct=.8,conviction=75,
                sl=98.,tp=105.,sl_pct=.02,tp_pct=.05,
                reason="support tested",invalidation="hourly close below support",**kw)


def reply(*ds):return {"market_view":"Daily and 4h confirmed, level tested","next_check_minutes":15,"decisions":list(ds)}


class FeatureTests(unittest.TestCase):
    def test_macro_down_is_explicit_and_no_forced_direction(self):
        result=pb.summarize("ETH",frames(down=True),NOW)
        self.assertEqual(result["trend"]["1d"],"down")
        self.assertEqual(result["phase_estimate"],"bearish_continuation")
        self.assertIn("pullback_up_0786",result["fib"])

    def test_deterministic_prompt_btc_once(self):
        s={sym:pb.summarize(sym,frames(),NOW) for sym in ("BTC","ETH")}
        user=pb.build_user(NOW,s,{},[],{})
        self.assertEqual(user,pb.build_user(NOW,dict(reversed(list(s.items()))),{},[],{}))
        self.assertEqual(user.count('"BTCUSDT"'),1)
        self.assertNotIn("raw_candles",user)

    def test_stale_future_nonfinite_and_gap_rejected(self):
        for mode in ("stale","future","nan","gap","duplicate"):
            f=frames()
            if mode=="stale":f["1d"]=f["1d"][:-1]
            if mode=="future":f["1h"][-1][0]+=3600000
            if mode=="nan":f["15m"][-1][4]=float("nan")
            if mode=="gap":f["4h"].pop(15)
            if mode=="duplicate":f["4h"][10][0]=f["4h"][9][0]
            with self.assertRaises(ValueError):pb.summarize("ETH",f,NOW)


class ParseTests(unittest.TestCase):
    def setUp(self):self.s={sym:pb.summarize(sym,frames(),NOW) for sym in ("ETH","BTC")}
    def test_written_invalidation_and_fraction(self):
        _,d,_=parse_response(json.dumps(reply(decision(symbol_alias="ignored"))),{"BTC","ETH"},self.s)
        self.assertEqual(len(d),1)
        for key,val in (("invalidation",""),("size_pct",80),("conviction",True),("sl_pct",float("inf"))):
            row=decision();row[key]=val
            if key=="sl_pct":
                with self.assertRaises(ValueError):parse_response(json.dumps(reply(row)),{"ETH"},self.s)
            else:self.assertEqual(parse_response(json.dumps(reply(row)),{"ETH"},self.s)[1],[])

    def test_no_macro_no_new_exposure(self):
        self.assertEqual(parse_response(json.dumps(reply(decision())),{"ETH"},{"ETH":self.s["ETH"]})[1],[])

    def test_partial_fixed_and_pause_bounded(self):
        for row in (dict(symbol="ETH",action="partial_close",close_fraction=.8,reason="uncertain"),
                    dict(action="pause",pause_minutes=121,reason="uncertain",reentry_condition="break")):
            self.assertEqual(parse_response(json.dumps(reply(row)),{"ETH"},self.s)[1],[])
        row=dict(action="pause",pause_minutes=120,reason="uncertain",reentry_condition="break")
        self.assertEqual(len(parse_response(json.dumps(reply(row)),{"ETH"},self.s)[1]),1)

    def test_duplicate_and_key_echo_scrubbed(self):
        raw=reply(decision(),decision());raw["market_view"]="echo SECRET"
        view,ds,errors=parse_response(json.dumps(raw),{"ETH"},self.s,"SECRET")
        self.assertNotIn("SECRET",view);self.assertEqual(len(ds),1);self.assertEqual(len(errors),1)


class PortfolioTests(unittest.TestCase):
    def test_long_short_sizing_fee_and_leverage_tiers(self):
        for sym,cap in (("BTC",45),("XAU",45),("XAG",45),("ETH",30),("SOL",25)):
            for side in ("open_long","open_short"):
                p=Portfolio();d=decision(side)
                if side=="open_short":d.update(sl=102,tp=95)
                p.apply(d|{"symbol":sym},100,NOW,{sym:100},{})
                pos=p.account.positions[sym]
                self.assertLessEqual(pos.leverage,cap)
                self.assertAlmostEqual(pos.fee_open,pos.total_margin*pos.leverage*.0006)
                self.assertLessEqual(p.risk_at_stop(pos),1000*.01*.8*.75+1e-8)

    def test_conviction_proportional(self):
        quantities=[]
        for c in (60,90):
            p=Portfolio();d=decision();d["conviction"]=c
            p.apply(d,100,NOW,{"ETH":100},{})
            quantities.append(p.account.positions["ETH"].qty)
        self.assertAlmostEqual(quantities[1]/quantities[0],1.5)

    def test_ten_slots(self):
        p=Portfolio()
        for i in range(10):p.apply(decision()|{"symbol":str(i)},100,NOW,{str(i):100},{})
        before=p.to_dict()
        with self.assertRaises(ValueError):p.apply(decision()|{"symbol":"11"},100,NOW,{"11":100},{})
        self.assertEqual(p.to_dict(),before)

    def test_early_close_and_partial_and_profit_save(self):
        for action in ("close","partial_close","save_profit"):
            p=Portfolio();p.apply(decision(),100,NOW,{"ETH":100},{})
            qty=p.account.positions["ETH"].qty
            event=p.apply(decision(action),103,NOW+7200000,{"ETH":103},{})
            self.assertGreater(event["trade"]["net"],0)
            if action=="partial_close":self.assertAlmostEqual(p.account.positions["ETH"].qty,qty/2)
            else:self.assertNotIn("ETH",p.account.positions)

    def test_profit_save_rejects_loss_stop_never_widens(self):
        p=Portfolio();p.apply(decision(),100,NOW,{"ETH":100},{})
        before=p.to_dict()
        with self.assertRaises(ValueError):p.apply(decision("save_profit"),99,NOW,{"ETH":99},{})
        with self.assertRaises(ValueError):p.apply(decision("move_stop",new_stop=97),100,NOW,{"ETH":100},{})
        self.assertEqual(p.to_dict(),before)
        p.apply(decision("move_stop",new_stop=99),100,NOW,{"ETH":100},{})
        self.assertEqual(p.account.positions["ETH"].sl,99)

    def test_average_macro_support_and_risk(self):
        p=Portfolio();d=decision();d["size_pct"]=.4
        p.apply(d,100,NOW,{"ETH":100},{})
        avg=decision("average",support_level=99);avg.update(size_pct=1,conviction=100)
        ctx={"trend":{"4h":"up","1d":"up"},"support_20h":99}
        before=p.to_dict()
        with self.assertRaises(ValueError):p.apply(avg,99.2,NOW,{"ETH":99.2},{**ctx,"trend":{"4h":"down","1d":"up"}})
        self.assertEqual(p.to_dict(),before)
        result=p.apply(avg,99.2,NOW,{"ETH":99.2},ctx)
        self.assertEqual(result["kind"],"average")
        self.assertLessEqual(result["risk"],p.account.equity({"ETH":99.2})*.01+.01)
        self.assertEqual(p.account.positions["ETH"].sl,98)
        self.assertEqual(p.account.positions["ETH"].dca_count,1)

    def test_average_halted_and_fabricated_level_rejected(self):
        p=Portfolio();p.apply(decision(),100,NOW,{"ETH":100},{})
        avg=decision("average",support_level=99)
        with self.assertRaises(ValueError):p.apply(avg,99,NOW,{"ETH":99},{"trend":{"4h":"up","1d":"up"},"support_20h":95})
        p.account.day_start_equity=2000
        with self.assertRaises(ValueError):p.apply(avg,99,NOW,{"ETH":99},{})

    def test_adverse_gap_and_sl_tp_same_bar(self):
        p=Portfolio()
        with self.assertRaises(ValueError):p.apply(decision(),97,NOW,{"ETH":97},{})
        p.apply(decision(),100,NOW,{"ETH":100},{})
        p.account.on_bar("ETH",NOW,100,106,97,103,BAR)
        self.assertEqual(p.account.closed[-1]["why"],"stop loss")


class PilotTests(unittest.TestCase):
    def make(self,root,replies=None):
        model=Model(replies);cache=Cache()
        p=Pilot(root,"TEST-KEY",cache,model,cfg=replace(config(),symbols=("BTC","ETH"),min_symbols_ok=2))
        return p,cache,model

    def test_next_open_and_no_duplicate_restart(self):
        with tempfile.TemporaryDirectory() as root:
            p,c,m=self.make(root,[reply(decision())])
            now=NOW+15000;p.run_once(now)
            self.assertFalse(p.portfolio.account.positions)
            self.assertEqual(len(p.state["pending"]),1)
            p.run_once(now);self.assertEqual(len(m.calls),1)
            p.close()
            p,c,m=self.make(root)
            p.run_once(now);self.assertEqual(len(m.calls),0)
            p.run_once(now+BAR)
            self.assertIn("ETH",p.portfolio.account.positions)
            self.assertEqual(p.portfolio.account.positions["ETH"].open_ms,NOW)
            p.close()

    def test_error_never_opens_and_budget_is_reserved(self):
        with tempfile.TemporaryDirectory() as root:
            p,c,m=self.make(root,[ModelError("network","TEST-KEY provider echo")])
            result=p.run_once(NOW+15000)
            self.assertEqual(result["error"],"model_or_response_failed")
            self.assertFalse(p.state["pending"])
            self.assertGreater(p.budget.spent_day(NOW),0)
            p.close()
            text="".join(path.read_text() for path in Path(root).glob("*.json*"))
            self.assertNotIn("TEST-KEY",text)

    def test_pause_reassesses_every_bar_and_capped_episode(self):
        with tempfile.TemporaryDirectory() as root:
            pause=dict(action="pause",pause_minutes=120,reason="loss; no structure",reentry_condition="break support")
            p,c,m=self.make(root,[reply(pause),reply(decision())])
            p.run_once(NOW+15000)
            p.run_once(NOW+BAR+15000)
            self.assertEqual(len(m.calls),2);self.assertFalse(p.state["pending"])
            with self.assertRaises(ValueError):p.control(pause,NOW+7200000)
            p.control(dict(action="resume",reason="clear thesis"),NOW+BAR)
            self.assertEqual(p.state["pause_until"],0)
            p.close()

    def test_pause_does_not_block_close(self):
        with tempfile.TemporaryDirectory() as root:
            pause=dict(action="pause",pause_minutes=60,reason="uncertain",reentry_condition="level")
            p,c,m=self.make(root,[reply(pause,decision("close"))])
            p.portfolio.apply(decision(),100,NOW-7200000,{"ETH":100},{})
            p.run_once(NOW+15000);p.run_once(NOW+BAR+15000)
            self.assertNotIn("ETH",p.portfolio.account.positions)
            history=[json.loads(l) for l in (Path(root)/"trade_history.jsonl").read_text().splitlines()]
            self.assertIn("close_ms",history[0]);self.assertIn("net",history[0]);self.assertEqual(history[0]["source"],"brain-deepseek")
            p.close()

    def test_missing_macro_skips_model(self):
        with tempfile.TemporaryDirectory() as root:
            p,c,m=self.make(root);c.missing.add("BTC")
            self.assertEqual(p.run_once(NOW+15000)["skip"],"missing_key_or_macro_data")
            self.assertFalse(m.calls);p.close()

    def test_budget_cap_and_operator_pause(self):
        with tempfile.TemporaryDirectory() as root:
            p,c,m=self.make(root)
            p.budget.daily_cap=0
            self.assertEqual(p.run_once(NOW+15000)["skip"],"budget_cap")
            (Path(root)/"pause.flag").touch()
            self.assertEqual(p.run_once(NOW+BAR+15000)["skip"],"operator_pause")
            self.assertFalse(m.calls);p.close()

    def test_paper_guard(self):
        with patch.dict(os.environ,DESK_MODE="live"):
            with tempfile.TemporaryDirectory() as root:
                with self.assertRaises(ValueError):self.make(root)

    def test_queued_entry_requires_fresh_btc(self):
        with tempfile.TemporaryDirectory() as root:
            p,c,m=self.make(root,[reply(decision())])
            p.run_once(NOW+15000);c.missing.add("BTC")
            p.run_once(NOW+BAR+15000)
            self.assertFalse(p.portfolio.account.positions)
            self.assertFalse(p.state["pending"]);p.close()

    def test_operator_pause_blocks_pending_entry(self):
        with tempfile.TemporaryDirectory() as root:
            p,c,m=self.make(root,[reply(decision())])
            p.run_once(NOW+15000);(Path(root)/"pause.flag").touch()
            p.run_once(NOW+BAR+15000)
            self.assertFalse(p.portfolio.account.positions);p.close()

    def test_queued_close_and_export_no_duplicates(self):
        with tempfile.TemporaryDirectory() as root:
            p,c,m=self.make(root,[reply(decision()),reply(decision("partial_close")),reply(decision("close"))])
            for k in range(4):p.run_once(NOW+k*BAR+15000)
            self.assertFalse(p.portfolio.account.positions)
            rows=[json.loads(l) for l in (Path(root)/"trade_history.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows),2);self.assertTrue(rows[0]["partial"])
            original=(Path(root)/"trade_history.jsonl").read_bytes()
            p.close();p,c,m=self.make(root);p.run_once(NOW+3*BAR+15000)
            self.assertEqual(original,(Path(root)/"trade_history.jsonl").read_bytes());p.close()

    def test_expired_order_never_executes_later(self):
        with tempfile.TemporaryDirectory() as root:
            p,c,m=self.make(root,[reply(decision())])
            p.run_once(NOW+15000)
            # Missing destination data: no retroactive fill when it arrives later.
            c.missing.add("ETH");p.run_once(NOW+BAR+15000)
            c.missing.clear();p.run_once(NOW+2*BAR+15000)
            self.assertFalse(p.portfolio.account.positions);p.close()


class RecoveryTests(unittest.TestCase):
    def test_outbox_replays_exactly_once(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root)
            original=store.export
            store.export=lambda:(_ for _ in ()).throw(OSError("interrupted"))
            with self.assertRaises(OSError):store.commit({"saved":True},[("trade",{"net":1})])
            store.close()
            store=Store(root);self.assertTrue(store.load()["saved"])
            store.export();first=(Path(root)/"trade_history.jsonl").read_bytes()
            store.export();self.assertEqual(first,(Path(root)/"trade_history.jsonl").read_bytes())
            store.close()

    def test_no_second_writer_or_silent_reset(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root)
            with self.assertRaises(BlockingIOError):Store(root)
            store.close()
            (Path(root)/"journal.jsonl").write_text('{"old":true}\n')
            with self.assertRaises(ValueError):Store(root)

    def test_no_foreign_data_dir(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ("hawk","bull","ai"):
                with self.assertRaises(ValueError):Store(Path(root)/name)

    def test_torn_export_and_corrupt_database_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);store.commit({"saved":True},[("journal",{"kind":"test"})])
            with (Path(root)/"journal.jsonl").open("ab") as f:f.write(b'{"partial"')
            with self.assertRaises(ValueError):store.export()
            store.close()
        with tempfile.TemporaryDirectory() as root:
            (Path(root)/"brain.sqlite3").write_bytes(b"invalid database")
            import sqlite3
            with self.assertRaises(sqlite3.DatabaseError):Store(root)


if __name__=="__main__":unittest.main()
