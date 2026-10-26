"""Contracts, ATR risk conservation, persistent UTC stop and public context."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from test_brain_pilot_v1 import NOW, frames, decision, reply, Cache, Model
from director.brain_pilot import prompt_builder as pb
from director.brain_pilot.pilot import Pilot, parse_response, config
from director.brain_pilot.portfolio import Portfolio
from director.brain_pilot.context import ContextCollector, view, HOUR
from dataclasses import replace


class ThesisTests(unittest.TestCase):
    def parse(self,d):
        summaries={s:pb.summarize(s,frames(),NOW) for s in ("BTC","ETH")}
        return parse_response(json.dumps(reply(d)),{"BTC","ETH"},summaries)

    def test_exposure_requires_both_scenarios_and_verdict(self):
        for action in ("open_long","open_short","average"):
            for key in ("bull_scenario","bear_scenario","verdict"):
                d=decision(action,support_level=99);d.pop(key)
                self.assertFalse(self.parse(d)[1])

    def test_invalidation_level_finite_numeric_description_nonempty(self):
        for level in (None,True,"bad","98",0):
            d=decision();d["invalidation"]["level"]=level
            self.assertFalse(self.parse(d)[1])
        for description in ("",[],None,"   "):
            d=decision();d["invalidation"]["description"]=description
            self.assertFalse(self.parse(d)[1])
        d=decision();d["invalidation"]["level"]=float("nan")
        with self.assertRaises(ValueError):self.parse(d)
        self.assertEqual(self.parse(decision())[1][0]["invalidation"]["level"],98.)

    def test_protective_exits_do_not_need_entry_fields(self):
        for action in ("close","partial_close","save_profit","move_stop"):
            d={"symbol":"ETH","action":action,"reason":"thesis failed","new_stop":99}
            self.assertEqual(len(self.parse(d)[1]),1)


class ATRTests(unittest.TestCase):
    def test_floor_reduces_quantity_at_same_capital_risk(self):
        positions=[]
        for atr in (.1,2.):
            p=Portfolio();d=decision();d.update(sl=99.5,tp=110,_atr_1h=atr)
            event=p.apply(d,100,NOW,{"ETH":100},{})
            pos=p.account.positions["ETH"]
            self.assertLessEqual(event["risk"],6+1e-8)
            self.assertAlmostEqual(event["risk"],6,places=7)
            positions.append(pos)
        self.assertLess(positions[1].qty,positions[0].qty)
        self.assertEqual(positions[1].sl,98.4)

    def test_parser_floor_then_rr_recheck(self):
        summaries={s:pb.summarize(s,frames(),NOW) for s in ("BTC","ETH")}
        summaries["ETH"]["atr14_1h"]=2
        d=decision();d.update(sl_pct=.001,tp_pct=.04)
        order=parse_response(json.dumps(reply(d)),{"ETH"},summaries)[1][0]
        self.assertAlmostEqual(order["sl"],98.4)
        self.assertTrue(order["_atr_adjusted"])
        d["tp_pct"]=.002
        self.assertFalse(parse_response(json.dumps(reply(d)),{"ETH"},summaries)[1])

    def test_existing_stop_never_widens_for_averaging(self):
        p=Portfolio();d=decision();d.update(sl=99,tp=110,_atr_1h=.1)
        p.apply(d,100,NOW,{"ETH":100},{})
        original=p.to_dict()
        avg=decision("average",support_level=99.1);avg["_atr_1h"]=2
        ctx={"trend":{"4h":"up","1d":"up"},"support_20h":99.1,"atr14_1h":2}
        with self.assertRaises(ValueError):p.apply(avg,99.2,NOW,{"ETH":99.2},ctx)
        self.assertEqual(original,p.to_dict())


class DailyStopTests(unittest.TestCase):
    def test_equal_threshold_latches_and_survives_recovery_restart(self):
        p=Portfolio();p.roll_day(NOW,{})
        p.account.cash=800
        self.assertEqual(p.halted({},NOW+1),"daily_stop_20pct")
        p.account.cash=900
        restored=Portfolio(p.to_dict())
        self.assertEqual(restored.halted({},NOW+1000),"daily_stop_20pct")
        self.assertFalse(restored.halted({},NOW+86400000))
        self.assertEqual(restored.account.cash,900)
        self.assertEqual(restored.daily["start_equity"],900)

    def test_unrealized_loss_triggers_while_management_remains_available(self):
        p=Portfolio();p.apply(decision(),100,NOW,{"ETH":100},{})
        p.daily["start_equity"]=1250 # synthetic book near threshold, including unrealized
        px=99
        self.assertEqual(p.halted({"ETH":px},NOW+1000),"daily_stop_20pct")
        with self.assertRaises(ValueError):p.apply(decision(),px,NOW+1000,{"ETH":px},{})
        event=p.apply({"symbol":"ETH","action":"close","reason":"protect"},px,NOW+1000,{"ETH":px},{})
        self.assertEqual(event["kind"],"close")
        self.assertFalse(p.account.positions)

    def test_migrates_old_saved_limits_without_reset(self):
        p=Portfolio();state=p.account.to_dict();state["cash"]=850;state["limits"]["daily_stop"]=.12
        state.update(day="2026-10-27",day_start_equity=1000)
        # Use the saved reference at the actual UTC day of the injected clock.
        import time
        state["day"]=time.strftime("%Y-%m-%d",time.gmtime(NOW/1000))
        restored=Portfolio(state);restored.roll_day(NOW,{})
        self.assertEqual(restored.account.limits.daily_stop,.2)
        self.assertEqual(restored.account.cash,850)
        self.assertEqual(restored.daily["start_equity"],1000)
        self.assertFalse(restored.daily["stopped"])

    def test_journal_latch_once_across_restart(self):
        with tempfile.TemporaryDirectory() as root:
            cfg=replace(config(),symbols=("BTC","ETH"),min_symbols_ok=2)
            p=Pilot(root,"fake",Cache(),Model(),cfg=cfg)
            p.portfolio.roll_day(NOW,{})
            p.portfolio.account.cash=800;p.portfolio.halted({},NOW+1)
            p.checkpoint([]);p.checkpoint([]);p.close()
            p=Pilot(root,"fake",Cache(),Model(),cfg=cfg)
            self.assertEqual(p.portfolio.halted({},NOW+1000),"daily_stop_20pct")
            p.checkpoint([]);p.close()
            rows=[json.loads(l) for l in (Path(root)/"journal.jsonl").read_text().splitlines()]
            self.assertEqual(sum(r["kind"]=="daily_stop" for r in rows),1)

    def test_legacy_pending_rejects_exposure_only(self):
        with tempfile.TemporaryDirectory() as root:
            cfg=replace(config(),symbols=("BTC","ETH"),min_symbols_ok=2)
            p=Pilot(root,"fake",Cache(),Model(),cfg=cfg)
            p.state["pending"]=[{"action":"open_long","symbol":"ETH","invalidation":"legacy"},
                                  {"action":"close","symbol":"ETH","execute_t":NOW}]
            p.checkpoint([]);p.close()
            p=Pilot(root,"fake",Cache(),Model(),cfg=cfg)
            self.assertEqual([o["action"] for o in p.state["pending"]],["close"])
            self.assertEqual(p.migration_rejected,1);p.close()

    def test_loop_blocks_open_but_executes_protective_close_after_restart(self):
        with tempfile.TemporaryDirectory() as root:
            cfg=replace(config(),symbols=("BTC","ETH"),min_symbols_ok=2)
            opening=decision();opening["symbol"]="BTC"
            p=Pilot(root,"fake",Cache(),Model([reply({"symbol":"ETH","action":"close","reason":"protect"},opening)]),cfg=cfg)
            p.portfolio.apply(decision(),100,NOW,{"ETH":100},{})
            p.portfolio.daily["start_equity"]=1250
            p.run_once(NOW+15000)
            self.assertEqual([d["action"] for d in p.state["pending"]],["close"])
            self.assertTrue(p.portfolio.daily["stopped"]);p.close()
            p=Pilot(root,"fake",Cache(),Model(),cfg=cfg)
            p.run_once(NOW+900000+15000)
            self.assertFalse(p.portfolio.account.positions)
            self.assertTrue(p.portfolio.daily["stopped"]);p.close()


class ContextTests(unittest.TestCase):
    def fetcher(self,url):
        if "alternative.me" in url:return {"data":[{"value":"45","timestamp":NOW//1000,"time_until_update":86400,"value_classification":"Neutral"}]}
        if "history-fund-rate" in url:return {"code":"00000","data":[{"fundingRate":".0006","fundingTime":NOW-8*HOUR}]}
        if "current-fund-rate" in url:return {"code":"00000","data":[{"fundingRate":".0006"}]}
        return {"code":"00000","data":{"openInterestList":[{"symbol":"ETHUSDT","size":"120"}]}}

    def test_recent_and_settled_distinct_deduplicated_persistent(self):
        state={};collector=ContextCollector(self.fetcher,clock=lambda:0)
        for stamp in (NOW,NOW,NOW+900000,NOW+1800000):result=collector.collect(["ETH"],stamp,state)
        row=result["symbols"]["ETHUSDT"]
        self.assertEqual(len(row["funding_recent_samples"]),3)
        self.assertEqual(row["funding_settled"][0]["kind"],"settled_payment")
        self.assertIn("not_reversal_proof",row["funding_interpretation"])
        self.assertIsNone(row["oi_change_4h_pct"])
        self.assertEqual(view(json.loads(json.dumps(state)),["ETH"],NOW+1800000),result)

    def test_oi_four_hours_uses_quantity_and_timestamp(self):
        state={"symbols":{"ETH":{"oi":[{"quantity":100,"ts_ms":NOW-4*HOUR},{"quantity":120,"ts_ms":NOW}]}}}
        row=view(state,["ETH"],NOW)["symbols"]["ETHUSDT"]
        self.assertAlmostEqual(row["oi_change_4h_pct"],20)
        self.assertEqual(row["oi_reference_ts_ms"],NOW-4*HOUR)
        self.assertIsNone(view(state,["ETH"],NOW+HOUR)["symbols"]["ETHUSDT"]["oi_change_4h_pct"])

    def test_optional_failures_and_deadline_are_neutral(self):
        def unavailable(url):raise OSError("offline")
        result=ContextCollector(unavailable,clock=lambda:0).collect(["ETH"],NOW,{})
        self.assertEqual(result["symbols"]["ETHUSDT"]["availability"],"non disponibile")
        calls=[]
        collector=ContextCollector(lambda u:calls.append(u),clock=lambda:0,max_seconds=0)
        collector.collect(["ETH"],NOW,{})
        self.assertFalse(calls)

    def test_fng_once_global_with_source_and_cache(self):
        calls=[]
        def fetch(url):calls.append(url);return self.fetcher(url)
        state={};collector=ContextCollector(fetch,clock=lambda:0)
        result=collector.collect(["ETH"],NOW,state)
        collector.collect(["ETH"],NOW+900000,state)
        self.assertEqual(sum("alternative.me" in u for u in calls),1)
        self.assertEqual(result["btc_macro"]["fear_greed"]["value"],45)
        self.assertNotIn("fear_greed",result["symbols"]["ETHUSDT"])

    def test_failed_context_source_does_not_block_model(self):
        class Broken:
            def collect(self,*args):raise OSError("optional feed down")
        with tempfile.TemporaryDirectory() as root:
            cfg=replace(config(),symbols=("BTC","ETH"),min_symbols_ok=2)
            model=Model();p=Pilot(root,"fake",Cache(),model,cfg=cfg,context=Broken())
            self.assertTrue(p.run_once(NOW+15000)["called"])
            self.assertEqual(model.calls[0]["derivatives_context"]["availability"],"non disponibile")
            p.close()


if __name__=="__main__":unittest.main()
