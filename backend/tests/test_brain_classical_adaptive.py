"""Offline regression/protection/real classical-cycle tests. No network or keys."""
import concurrent.futures
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from desk.engine import PaperAccount, Limits
from director.ai_shadow.config import Config
from director.classical_adaptive.budget import SharedBudget, baseline_from_spend
from director.classical_adaptive.provider import Provider, Unavailable, validate
from director.classical_adaptive.protection import manage, series, close_estimate
from director.classical_adaptive.feeds import Feeds
from director.classical_adaptive.runtime import safe_root
from director.classical_adaptive.outbox import CachedStore
from director.brain_pilot import learning as lm

NOW=1793102400000


def bars(now=NOW,price=100):
    end=now//60000*60000
    return [[end-(9-i)*60000,price,price+.01,price-.01,price,100] for i in range(10)]


class ProtectionTests(unittest.TestCase):
    def account(self,side=1):
        a=PaperAccount(Limits(max_margin_trade=350,min_margin=1),"brain-bull")
        p,msg=a.open("ETH",side,200,15,100,99 if side==1 else 101,102 if side==1 else 98,NOW-360000,{})
        self.assertIsNotNone(p,msg)
        return a,p

    def test_long_and_short_stops_have_real_costs(self):
        for side in (1,-1):
            a,p=self.account(side)
            result=manage(a,"ETH",bars(price=98 if side==1 else 102),NOW)
            self.assertLess(result["trade"]["net"],0)
            self.assertGreater(result["trade"]["fees"],0)
            self.assertFalse(a.positions)

    def test_entry_containing_minute_cannot_retroactively_stop(self):
        a,p=self.account();p.open_ms=NOW-30000
        rows=bars();rows[-2][3]=90;rows[-1][3]=90
        result=manage(a,"ETH",rows,NOW)
        self.assertIsNone(result["trade"])
        self.assertIn("ETH",a.positions)

    def test_profitable_weakening_exits_net_but_strong_trend_continues(self):
        a,p=self.account();rows=bars(price=101)
        # Flat continuation after useful gain is treated as weakening.
        result=manage(a,"ETH",rows,NOW)
        self.assertGreater(result["trade"]["net"],0)
        a,p=self.account()
        rows=[[b[0],100+i*.1,100+i*.1+.01,100+i*.1-.01,100+i*.1,100] for i,b in enumerate(bars())]
        self.assertIsNone(manage(a,"ETH",rows,NOW)["trade"])
        self.assertEqual(a.positions["ETH"].sl,99)

    def test_tiny_gross_profit_does_not_trigger_net_capture(self):
        a,p=self.account()
        self.assertLess(close_estimate(a,p,100.03,NOW)[0],0)
        self.assertIsNone(manage(a,"ETH",bars(price=100.03),NOW)["trade"])

    def test_bad_fast_data_never_fills(self):
        for bad in ("stale","future","nan","gap","range"):
            rows=bars()
            if bad=="stale":rows=bars(NOW-180000)
            if bad=="future":rows=bars(NOW+60000)
            if bad=="nan":rows[-1][4]=float("nan")
            if bad=="gap":rows.pop(3)
            if bad=="range":rows[-1][2]=90
            a,p=self.account();before=copy.deepcopy(a.to_dict())
            with self.assertRaises(ValueError):manage(a,"ETH",rows,NOW)
            self.assertEqual(before,a.to_dict())

    def test_paused_profile_cancels_split_but_still_protects(self):
        a,p=self.account();p.pending_split={"trigger":99.5,"margin":50,"expire_ms":NOW+60000}
        manage(a,"ETH",bars(price=98),NOW,paused=True)
        self.assertFalse(a.positions)
        self.assertTrue(a.events)


class BudgetProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cfg=replace(Config(),max_tokens=100)
        self.budget=SharedBudget(Path(self.tmp.name)/"budget.sqlite3",self.cfg,{"version":1,"mode":"paper","source_sha256":"0"*64,"by_day":{}})

    def test_reservation_survives_restart_and_no_duplicate_minute(self):
        ok,_,cost=self.budget.reserve("hawk",NOW,100,100);self.assertTrue(ok)
        again=SharedBudget(Path(self.tmp.name)/"budget.sqlite3",self.cfg)
        self.assertEqual(again.reserve("hawk",NOW,100,100)[1],"already_reserved")
        self.assertGreater(cost,0)

    def test_shared_budget_race_never_multiplies_allowance(self):
        def reserve(i):return self.budget.reserve("hawk" if i%2 else "bull",NOW+i*60000,50000,3000)
        with concurrent.futures.ThreadPoolExecutor(8) as pool:list(pool.map(reserve,range(100)))
        with self.budget.connect() as db:
            for day,total in db.execute("SELECT day,SUM(cost) FROM reservations GROUP BY day"):
                self.assertLessEqual(total,.5+1e-9)

    def test_pacing_and_budget_increase_guard(self):
        midnight=NOW//86400000*86400000
        self.assertEqual(self.budget.reserve("hawk",midnight,200000,3000)[1],"paced_profile_allowance")
        with self.assertRaises(ValueError):SharedBudget(Path(self.tmp.name)/"extra",replace(self.cfg,daily_cap_usd=1))

    def test_async_pending_does_not_wait_and_fresh_result_works(self):
        ready=threading.Event()
        def call(*args):
            ready.wait(2)
            return {"content":json.dumps({"decisions":[],"note":"hold"})}
        p=Provider("hawk",self.cfg,"fake",self.budget,call)
        try:
            start=time.monotonic()
            with self.assertRaises(Unavailable):p.request("system","user",{}, {"ETH":100},NOW,{"ETH"})
            self.assertLess(time.monotonic()-start,.5)
            ready.set();p.pending["future"].result(2)
            text,usage=p.request("system","user",{}, {"ETH":100},NOW+60000,{"ETH"})
            self.assertEqual(json.loads(text)["decisions"],[])
            self.assertEqual(p.last_status,"adaptive_ai")
        finally:ready.set();p.close()

    def test_failed_pre_call_audit_blocks_api_but_never_refunds_uncertain_reservation(self):
        calls=[]
        p=Provider('hawk',self.cfg,'fake',self.budget,lambda *_:calls.append(True))
        def fail():raise OSError('synthetic audit failure')
        try:
            with self.assertRaises(OSError):p.request('s','u',{}, {},NOW,set(),fail)
            self.assertFalse(calls);self.assertIsNone(p.pending)
            self.assertGreater(self.budget.view(NOW,'hawk')['profile_reserved'],0)
        finally:p.close()

    def test_expired_or_changed_exposure_result_is_rejected(self):
        for changed in (False,True):
            p=Provider("bull",self.cfg,"fake",self.budget,lambda *_:{"content":'{"decisions":[]}'})
            try:
                stamp=NOW+(600000 if changed else 0)
                with self.assertRaises(Unavailable):p.request("s","u",{}, {},stamp,set())
                p.pending["future"].result(2)
                state={"main":{"cash":900}} if changed else {}
                with self.assertRaises(Unavailable):p.request("s","u",state,{},stamp+(60000 if changed else 180000),set())
                self.assertEqual(p.last_status,"stale_model_result")
            finally:p.close()

    def test_schema_rejects_nonfinite_booleans_duplicates_and_scrubs_key(self):
        self.assertNotIn("private",json.dumps(validate('{"decisions":[],"note":"private"}',set(),"private")))
        d={"symbol":"ETH","action":"open_long","margin_usd":200,"leverage":15,"confidence":90,"stop_loss_pct":.004,"take_profit_pct":.008,"reason":"test"}
        for field,value in (("margin_usd",float("nan")),("leverage",True),("take_profit_pct",2)):
            row=dict(d,**{field:value})
            with self.assertRaises(ValueError):validate(json.dumps({"decisions":[row]}),{"ETH"},"")
        with self.assertRaises(ValueError):validate(json.dumps({"decisions":[d,d]}),{"ETH"},"")

    def test_learning_identity_and_strategy_cohorts_are_distinct(self):
        raw={"id":1,"symbol":"ETH","side":1,"open_ms":NOW}
        self.assertNotEqual(lm.position_key(dict(raw,account="brain-hawk")),lm.position_key(dict(raw,account="brain-bull")))
        ctx=lm.entry_context({"trend":{"1d":"up","4h":"up"}},strategy_version="classical-hawk-123")
        self.assertEqual(lm.context(ctx)["strategy_version"],"classical-hawk-123")
        ctx.pop("strategy_version")
        self.assertEqual(lm.context(ctx)["strategy_version"],"unknown")

    def test_price_drift_rejects_entry_without_changing_orders(self):
        row={"symbol":"ETH","action":"open_long","margin_usd":200,"leverage":15,"confidence":90,"stop_loss_pct":.004,"take_profit_pct":.008,"reason":"test"}
        p=Provider("hawk",self.cfg,"fake",self.budget,lambda *_:{"content":json.dumps({"decisions":[row]})})
        try:
            with self.assertRaises(Unavailable):p.request("s","u",{}, {"ETH":100},NOW,{"ETH"})
            p.pending["future"].result(2)
            with self.assertRaises(Unavailable):p.request("s","u",{}, {"ETH":102},NOW+60000,{"ETH"})
            self.assertEqual(p.last_status,"invalid_or_failed_model_result")
        finally:p.close()

    def test_slow_public_entry_feed_does_not_block_fast_feed_or_writer(self):
        blocked=threading.Event()
        def daily(*_):blocked.wait(2);return []
        f=Feeds(lambda *_:bars(),daily,lambda *_:[],lambda *_:None,clock=lambda:NOW/1000)
        try:
            start=time.monotonic();f.poll(["BTC"],{"BTC"},NOW)
            self.assertLess(time.monotonic()-start,.5)
            f.pending["fast"].result(2)
            fast,entry=f.poll(["BTC"],{"BTC"},NOW)
            self.assertIn("BTC",fast)
            self.assertTrue(Feeds.fresh(fast["BTC"],NOW))
            self.assertFalse(Feeds.fresh(fast["BTC"],NOW+180000))
        finally:blocked.set();f.close()

    def test_foreign_and_symlink_data_roots_are_rejected(self):
        for name in ("hawk","bull","brain"):
            with self.assertRaises(ValueError):safe_root(Path(self.tmp.name)/name)
        link=Path(self.tmp.name)/"link";link.symlink_to(self.tmp.name,target_is_directory=True)
        with self.assertRaises(ValueError):safe_root(link)
        ledger=Path(self.tmp.name)/"alias.sqlite3";ledger.symlink_to(Path(self.tmp.name)/"budget.sqlite3")
        with self.assertRaises(ValueError):SharedBudget(ledger,self.cfg)

    def test_old_brain_spend_is_carried_and_missing_baseline_never_resets(self):
        path=Path(self.tmp.name)/"old-spend.jsonl"
        day=time.strftime("%Y-%m-%d",time.gmtime(NOW/1000))
        path.write_text(json.dumps({"day":day,"cost":.49})+"\n")
        seed=baseline_from_spend(path)
        carried=SharedBudget(Path(self.tmp.name)/"carried.sqlite3",self.cfg,seed)
        self.assertAlmostEqual(carried.view(NOW,"hawk")["daily_reserved"],.49)
        self.assertFalse(carried.reserve("hawk",NOW,50000,3000)[0])
        with self.assertRaises(ValueError):SharedBudget(Path(self.tmp.name)/"missing.sqlite3",self.cfg)
        path.write_text('{"day":"2026-10-27","cost":-1}\n')
        with self.assertRaises(ValueError):baseline_from_spend(path)

    def test_different_strategy_versions_cannot_pool_learning(self):
        from test_brain_pilot_learning import memory,SUMMARIES,NOW as MEMORY_NOW
        sample=memory()
        for i,e in enumerate(sample["episodes"]):e["context"]["strategy_version"]="classical-hawk-v1" if i<6 else "classical-hawk-v2"
        self.assertFalse(lm.build_view(sample,SUMMARIES,MEMORY_NOW-12*lm.DAY)["lessons"])

    def test_healthcheck_does_not_initialize_or_write_files(self):
        root=Path(self.tmp.name)/"health"
        result=subprocess.run([sys.executable,"-m","director.classical_adaptive.runtime","--out",str(root),"--profile","hawk","--healthcheck"],env=dict(os.environ,PYTHONPATH="backend"),capture_output=True,timeout=10)
        self.assertEqual(result.returncode,1)
        self.assertFalse(root.exists())


class RealClassicalProcessTests(unittest.TestCase):
    def test_real_hawk_and_bull_cycles_ai_size_stop_recovery_and_rollback(self):
        # Profile selection happens at import, exactly like the actual bots.
        for profile,side,market in (("hawk","long","long"),("bull","long","long"),("hawk","short","short"),("bull","short","short"),("hawk","short","long"),("bull","long","short")):
            env=dict(os.environ,DESK_MODE="paper",DESK_MACRO_FETCH="0",DESK_DAILY_FETCH="0",PYTHONPATH="backend:backend/tests")
            result=subprocess.run([sys.executable,"backend/tests/brain_classical_probe.py",profile,side,market],env=env,text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout[-4000:]+result.stderr[-2000:])
            self.assertIn("CLASSICAL_ADAPTIVE_PROBE=PASS",result.stdout)


class IncrementalOutboxTests(unittest.TestCase):
    def test_minute_exports_append_without_rereading_history_and_restart_deduplicates(self):
        with tempfile.TemporaryDirectory() as root:
            s=CachedStore(root,learning_enabled=False)
            try:
                s.commit({'value':0},[('journal',{'kind':'first'})])
                original=Path.open;reads=[]
                def observed(path,*args,**kwargs):
                    if args and args[0]=='rb':reads.append(str(path))
                    return original(path,*args,**kwargs)
                from unittest.mock import patch
                with patch.object(Path,'open',observed):
                    for i in range(1,10):s.commit({'value':i},[('journal',{'kind':'next','value':i})])
                self.assertFalse(reads)
                before=(Path(root)/'journal.jsonl').read_bytes()
            finally:s.close()
            s=CachedStore(root,learning_enabled=False)
            try:
                s.export();self.assertEqual((Path(root)/'journal.jsonl').read_bytes(),before)
                s.commit({'value':10},[('journal',{'kind':'last'})])
                after=(Path(root)/'journal.jsonl').read_bytes()
                self.assertTrue(after.startswith(before))
                rows=[json.loads(line) for line in after.splitlines()]
                self.assertEqual(len({r['brain_event_id'] for r in rows}),11)
            finally:s.close()
    def test_external_torn_projection_is_not_repaired_or_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            s=CachedStore(root,learning_enabled=False)
            try:
                s.commit({'value':1},[('journal',{'kind':'first'})])
                path=Path(root)/'journal.jsonl'
                with path.open('ab') as f:f.write(b'{')
                before=path.read_bytes()
                with self.assertRaises(ValueError):s.export()
                self.assertEqual(path.read_bytes(),before)
                self.assertEqual(s.load()['value'],1)
            finally:s.close()


if __name__=="__main__":unittest.main()
