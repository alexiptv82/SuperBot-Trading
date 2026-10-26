import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

ROOT=Path(__file__).parents[2]
spec=importlib.util.spec_from_file_location("repair",ROOT/"deploy/scripts/brain_pilot_repair_daily.py")
repair=importlib.util.module_from_spec(spec);spec.loader.exec_module(repair)


class RepairTests(unittest.TestCase):
    def run_case(self,nonflat=False,fail=False):
        with tempfile.TemporaryDirectory() as root:
            data=Path(root)/"brain";data.mkdir()
            db=sqlite3.connect(data/"brain.sqlite3")
            db.execute("CREATE TABLE state(id INTEGER,body TEXT)")
            db.execute("INSERT INTO state VALUES(1,?)",(json.dumps({"account":{"positions":{"ETH":{}} if nonflat else {}},"pending":[]}),))
            db.commit();db.close();before=(data/"brain.sqlite3").read_bytes()
            previous="a"*40;sha="b"*40;commands=[];current={"sha":previous}
            def run(args,**kw):
                commands.append(args)
                if args[:2]==["docker","inspect"]:
                    if current["sha"] is None:raise RuntimeError("absent")
                    return json.dumps([{"Config":{"Labels":{"superbot.sha":current["sha"]}}}])
                if args[:2]==["docker","rm"]:current["sha"]=None
                if args[:2]==["docker","run"]:current["sha"]=previous
                return ""
            def install(*args):
                current["sha"]=sha
                if fail:raise RuntimeError("simulated health failure")
            mod=SimpleNamespace(DATA=data,BACKUPS=Path(root)/"backups",NAME="superbot-brain-pilot",
                validate_sha=Mock(),verify_container=Mock(),run=run,backup=Mock(),install=install,
                docker_args=lambda old:["docker","run",old])
            fake_spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda mod:None))
            with patch.object(repair.importlib.util,"spec_from_file_location",return_value=fake_spec),patch.object(repair.importlib.util,"module_from_spec",return_value=mod),patch.dict(repair.os.environ,BRAIN_INSTALL_APPROVED="yes",DEEPSEEK_API_KEY="fake"):
                if nonflat:
                    with self.assertRaises(ValueError):repair.repair(Path(root),sha,previous)
                    self.assertFalse(any(c[:2]==["docker","stop"] for c in commands))
                elif fail:
                    with self.assertRaises(RuntimeError):repair.repair(Path(root),sha,previous)
                    self.assertEqual(current["sha"],previous)
                else:
                    repair.repair(Path(root),sha,previous)
                    self.assertEqual(current["sha"],sha)
                self.assertEqual(before,(data/"brain.sqlite3").read_bytes())
                self.assertFalse(any("-v" in c for c in commands))

    def test_flat_repair_preserves_database(self):self.run_case()
    def test_positions_prevent_stop(self):self.run_case(nonflat=True)
    def test_health_failure_restores_previous_image(self):self.run_case(fail=True)


if __name__=="__main__":unittest.main()
