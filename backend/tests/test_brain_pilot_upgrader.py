"""Offline orchestration tests and optional real Docker migration on a COPY."""
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from desk.engine import Limits,PaperAccount
from director.brain_pilot.pilot import Pilot,Store

ROOT=Path(__file__).parents[2]
spec=importlib.util.spec_from_file_location("upgrader",ROOT/"deploy/scripts/brain_pilot_upgrade.py")
up=importlib.util.module_from_spec(spec);spec.loader.exec_module(up)
OLD="a"*40;NEW="b"*40
NOW=1793059200000
NAME="superbot-brain-pilot"


def fixture(root):
    account=PaperAccount(Limits(min_margin=1,max_margin_trade=100,daily_stop=.12),"brain-paper")
    symbols=("BTC","ETH","SOL","XAU","ADA")
    prices=dict.fromkeys(symbols,100.)
    for symbol in symbols:
        p,msg=account.open(symbol,1,25,3,100,95,110,NOW,prices,reason="legacy",features={"invalidation":"legacy text"})
        assert p is not None,msg
    account.day="2026-10-26";account.day_start_equity=1000
    state={"version":"brain-pilot-v1","account":account.to_dict(),"last_bar":NOW-900000,
           "last_attempt":NOW-900000,"recent":[],"pause_until":0,"pause_start":0,
           "pause_epoch":-1,"epoch":0,"pause_reason":"","reentry_condition":"","last_prices":prices,
           "pending":[{"action":"close","symbol":"BTC","reason":"protect","execute_t":NOW+900000},
                      {"action":"open_long","symbol":"LTC","invalidation":"legacy","execute_t":NOW+900000}]}
    store=Store(root)
    store.commit(state,[("trade",{"id":0,"symbol":"ETH","net":-.5,"close_ms":NOW-1000}),
                        ("journal",{"kind":"legacy_record"})]);store.close()
    (Path(root)/"spend.jsonl").write_text(json.dumps({"day":"2026-10-26","cost":.025})+"\n")
    (Path(root)/"status.json").write_text(json.dumps({"mode":"paper","applied":False,"ts_ms":NOW}))
    return state


class FakeDocker:
    def __init__(self,root,fail=None):
        self.data=Path(root)/"brain";self.data.mkdir()
        fixture(self.data);self.commands=[];self.fail=fail;self.containers={NAME:self.item(OLD,NAME)}
        self.helper=SimpleNamespace(NAME=NAME,DATA=self.data,BACKUPS=Path(root)/"backups",
            validate_sha=lambda s:None,verify_container=self.verify,run=self.run,
            inspect_all=lambda:list(copy.deepcopy(self.containers).values()),reject_conflicts=self.reject,
            backup=self.backup,docker_args=lambda sha:["docker","run","-d","--name",NAME,"--env","DEEPSEEK_API_KEY","superbot-brain-pilot:sha-"+sha])

    def item(self,sha,name):
        return {"Name":"/"+name,"Config":{"Labels":{"superbot.sha":sha,"superbot.component":"brain-pilot"},"Env":["DESK_MODE=paper"]},
                "Mounts":[{"Source":str(self.data),"Type":"bind","Destination":"/out"}],
                "State":{"Running":True,"Health":{"Status":"healthy"}},"RestartCount":0}

    def verify(self,item,sha):
        if item["Config"]["Labels"]["superbot.sha"]!=sha:raise ValueError("wrong_sha")
        if item["Config"]["Env"]!=["DESK_MODE=paper"]:raise ValueError("not_paper")

    def reject(self,items):
        if any(m.get("Source")==str(self.data) for i in items for m in i.get("Mounts",[])):
            raise ValueError("another_writer")

    def backup(self,data,path):
        if self.fail=="backup":raise OSError("backup failed")
        s=importlib.util.spec_from_file_location("install_helper",ROOT/"deploy/scripts/brain_pilot_install.py")
        mod=importlib.util.module_from_spec(s);s.loader.exec_module(mod)
        return mod.backup(data,path)

    def migrate(self,directory):
        p=Pilot(directory,"",None)
        p.checkpoint([{"kind":"migration_test"}]);p.close()

    def run(self,args,timeout=600):
        self.commands.append(list(args))
        if args[0]=="git":return NEW+"\n"
        action=args[1]
        if action=="build":
            if self.fail=="build":raise RuntimeError("build failed")
        elif action=="inspect":
            if args[-1] not in self.containers:raise RuntimeError("not found")
            return json.dumps([self.containers[args[-1]]])
        elif action=="stop":self.containers[args[-1]]["State"]["Running"]=False
        elif action=="start":self.containers[args[-1]]["State"]["Running"]=True
        elif action=="rename":
            item=self.containers.pop(args[-2]);item["Name"]="/"+args[-1];self.containers[args[-1]]=item
        elif action=="run" and "--rm" in args:
            mount=args[args.index("--mount")+1];probe=Path(mount.split("src=",1)[1].split(",dst=",1)[0])
            if self.fail=="probe":raise RuntimeError("probe failed")
            self.migrate(probe)
            if self.fail=="probe_reset":
                db=sqlite3.connect(probe/"brain.sqlite3");row=json.loads(db.execute("SELECT body FROM state").fetchone()[0])
                row["account"]["cash"]=1000
                db.execute("UPDATE state SET body=?",(json.dumps(row),));db.commit();db.close()
        elif action=="run":
            self.containers[NAME]=self.item(NEW,NAME)
            if self.fail!="before_state":
                self.migrate(self.data)
                (self.data/"status.json").write_text(json.dumps({"mode":"paper","applied":False,"ts_ms":__import__('time').time()*1000}))
            if self.fail in ("before_state","after_state"):
                self.containers[NAME]["State"]["Running"]=False
        return ""


class UpgraderTests(unittest.TestCase):
    def case(self,fail=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        return FakeDocker(temp.name,fail)

    def execute(self,fake):
        with patch.dict(os.environ,BRAIN_INSTALL_APPROVED="yes",DEEPSEEK_API_KEY="MODEL-TEST-SECRET"):
            return up.upgrade(ROOT,NEW,OLD,fake.helper)

    def test_nonflat_upgrade_preserves_five_positions_history_and_budget(self):
        f=self.case();before,events=up.read_database(f.data);original_spend=(f.data/"spend.jsonl").read_bytes()
        manifest=self.execute(f);after,new_events=up.read_database(f.data)
        self.assertEqual(manifest["open_positions_before"],5)
        self.assertEqual(before["account"]["positions"],after["account"]["positions"])
        self.assertEqual(before["account"]["cash"],after["account"]["cash"])
        self.assertEqual(new_events[:len(events)],events)
        self.assertEqual(original_spend,(f.data/"spend.jsonl").read_bytes())
        self.assertEqual(after["account"]["limits"]["daily_stop"],.20)
        self.assertEqual(after["pending"],[before["pending"][0]])
        self.assertNotIn("MODEL-TEST-SECRET",str(f.commands))
        self.assertFalse(any(c[1]=="rm" for c in f.commands if c[0]=="docker"))

    def test_build_failure_never_stops_old_process(self):
        f=self.case("build")
        with self.assertRaises(RuntimeError):self.execute(f)
        self.assertTrue(f.containers[NAME]["State"]["Running"])
        self.assertFalse(any(c[1]=="stop" for c in f.commands if c[0]=="docker"))

    def test_backup_or_probe_failure_restarts_unchanged_previous(self):
        for failure in ("backup","probe","probe_reset"):
            f=self.case(failure);before=up.file_manifest(f.data)
            with self.assertRaises((RuntimeError,OSError,up.UpgradeError)):self.execute(f)
            self.assertEqual(f.containers[NAME]["Config"]["Labels"]["superbot.sha"],OLD)
            self.assertTrue(f.containers[NAME]["State"]["Running"])
            self.assertEqual(before,up.file_manifest(f.data))

    def test_failure_before_state_change_can_rollback(self):
        f=self.case("before_state")
        with self.assertRaises(up.UpgradeError):self.execute(f)
        self.assertEqual(f.containers[NAME]["Config"]["Labels"]["superbot.sha"],OLD)
        self.assertTrue(f.containers[NAME]["State"]["Running"])

    def test_failure_after_state_change_never_overwrites_or_starts_old_code(self):
        f=self.case("after_state");before,_=up.read_database(f.data)
        with self.assertRaisesRegex(up.UpgradeError,"STATE_CHANGED_PRESERVED_STOPPED"):self.execute(f)
        self.assertFalse(any(i["State"]["Running"] for i in f.containers.values()))
        after,_=up.read_database(f.data)
        self.assertEqual(after["account"]["positions"],before["account"]["positions"])
        self.assertEqual(after["account"]["limits"]["daily_stop"],.20)

    def test_additional_writer_or_wrong_version_prevent_any_stop(self):
        for problem in ("writer","version"):
            f=self.case()
            if problem=="writer":f.containers["intruder"]=f.item(NEW,"intruder")
            else:f.containers[NAME]["Config"]["Labels"]["superbot.sha"]="c"*40
            with self.assertRaises(ValueError):self.execute(f)
            self.assertTrue(f.containers[NAME]["State"]["Running"])

    def test_logged_closure_is_valid_but_silent_position_loss_is_not(self):
        f=self.case();before,events=up.read_database(f.data);after=copy.deepcopy(before)
        removed=after["account"]["positions"].pop("BTC")
        with self.assertRaises(up.UpgradeError):up.validate_runtime_history(before,events,after,events)
        closed=events+[(999,"trade",json.dumps({"symbol":"BTC","id":removed["id"],"partial":False}))]
        up.validate_runtime_history(before,events,after,closed)

    def test_append_log_rewrite_is_detected(self):
        f=self.case();manifest=up.file_manifest(f.data)
        (f.data/"spend.jsonl").write_text('{}\n')
        with self.assertRaises(up.UpgradeError):up.validate_log_prefixes(f.data,manifest)

    def test_clone_uses_committed_wal_and_does_not_modify_source(self):
        f=self.case();before=up.file_manifest(f.data)
        with tempfile.TemporaryDirectory() as copy_dir:
            up.clone_data(f.data,Path(copy_dir))
            self.assertEqual(up.read_database(f.data),up.read_database(Path(copy_dir)))
        self.assertEqual(before,up.file_manifest(f.data))

    def test_committed_wal_is_included_in_database_clone(self):
        f=self.case();db=sqlite3.connect(f.data/"brain.sqlite3")
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("INSERT INTO events(kind,body) VALUES('journal',?)",(json.dumps({"kind":"committed_in_wal"}),))
            db.commit()
            self.assertGreater((f.data/"brain.sqlite3-wal").stat().st_size,0)
            with tempfile.TemporaryDirectory() as copied:
                up.clone_data(f.data,Path(copied))
                self.assertEqual(up.read_database(f.data),up.read_database(Path(copied)))
        finally:db.close()

    def test_busy_unknown_writer_never_starts_another_process(self):
        f=self.case()
        with (f.data/"writer.lock").open("a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.execute(f)
            self.assertFalse(f.containers[NAME]["State"]["Running"])
            self.assertFalse(any(c[1]=="start" for c in f.commands if c[0]=="docker"))

    def test_unexpected_container_is_never_stopped_by_rollback(self):
        f=self.case();baseline=up.file_manifest(f.data)
        f.containers[NAME]["Config"]["Labels"]["superbot.sha"]="c"*40
        with self.assertRaisesRegex(up.UpgradeError,"FOREIGN_CONTAINER"):
            up.rollback(f.helper,OLD,NEW,"unused",baseline)
        self.assertTrue(f.containers[NAME]["State"]["Running"])

    @unittest.skipUnless(os.getenv("BRAIN_TEST_IMAGE"),"Docker image integration runs in CI")
    def test_actual_target_image_migrates_copy_of_five_position_legacy_account(self):
        f=self.case();before,events=up.read_database(f.data);source=up.file_manifest(f.data)
        with tempfile.TemporaryDirectory() as copied:
            probe=Path(copied);up.clone_data(f.data,probe);manifest=up.file_manifest(probe)
            subprocess.run(["docker","run","--rm","--read-only","--cap-drop","ALL","--network","none",
                "--user",str(os.getuid())+":"+str(os.getgid()),
                "--env","DESK_MODE=paper","--mount","type=bind,src="+str(probe)+",dst=/out",
                os.environ["BRAIN_TEST_IMAGE"],"python","-c",
                "from director.brain_pilot.pilot import Pilot; p=Pilot('/out','',None); p.checkpoint([{'kind':'ci_migration_probe'}]); p.close()"],check=True,timeout=120)
            after,new_events=up.read_database(probe)
            up.validate_projection(before,after,events,new_events)
            up.validate_log_prefixes(probe,manifest)
        self.assertEqual(source,up.file_manifest(f.data))


if __name__=="__main__":unittest.main()
