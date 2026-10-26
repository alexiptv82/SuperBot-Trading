"""Installer contract tested offline; never invokes Docker, SSH or a provider."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parents[2]
spec=importlib.util.spec_from_file_location("brain_install",ROOT/"deploy/scripts/brain_pilot_install.py")
install=importlib.util.module_from_spec(spec);spec.loader.exec_module(install)
SHA="a"*40


def container(sha=SHA):
    return {"Name":"/"+install.NAME,"Config":{"Env":["DESK_MODE=paper"],"Labels":{"superbot.sha":sha}},
            "Mounts":[{"Type":"bind","Source":str(install.DATA),"Destination":"/out"}],
            "HostConfig":{"ReadonlyRootfs":True,"PortBindings":{},"CapDrop":["ALL"]},
            "State":{"Running":True,"Health":{"Status":"healthy"}},"RestartCount":0}


class InstallerTests(unittest.TestCase):
    def test_exact_isolated_docker_contract(self):
        args=install.docker_args(SHA)
        self.assertEqual(args[args.index("--mount")+1],"type=bind,src=/opt/superbot-desk-data/brain,dst=/out")
        self.assertIn("DESK_MODE=paper",args);self.assertIn("DEEPSEEK_API_KEY",args)
        self.assertNotIn("-p",args);self.assertNotIn("--publish",args)
        self.assertIn("unless-stopped",args);self.assertIn("--read-only",args)
        self.assertFalse(any("hawk" in a or "bull" in a for a in args))
        with patch.dict(os.environ,DEEPSEEK_API_KEY="MODEL-SECRET"):
            self.assertNotIn("MODEL-SECRET"," ".join(install.docker_args(SHA)))

    def test_invalid_sha(self):
        for sha in ("main","a"*39,"A"*40,"a"*40+"; echo no"):
            with self.assertRaises(ValueError):install.docker_args(sha)

    def test_existing_container_and_overlapping_mounts_rejected(self):
        with self.assertRaises(ValueError):install.reject_conflicts([container()])
        for source in (str(install.DATA),"/opt/superbot-desk-data",str(install.DATA/"child")):
            with self.assertRaises(ValueError):install.reject_conflicts([{"Mounts":[{"Type":"bind","Source":source}]}])
        install.reject_conflicts([{"Name":"/existing-bot","Mounts":[{"Type":"bind","Source":"/opt/superbot-desk-data/hawk"}]}])

    def test_verify_rejects_live_shared_mount_and_privileged(self):
        install.verify_container(container(),SHA)
        bad=container();bad["Config"]["Env"]=["DESK_MODE=live"]
        with self.assertRaises(ValueError):install.verify_container(bad,SHA)

    def test_readonly_parent_observer_is_not_a_writer(self):
        item={"Name":"/superbot-sidecar","Mounts":[{"Type":"bind","Source":"/opt/superbot-desk-data","RW":False}]}
        install.reject_conflicts([item])
        for writable in (True,None):
            item["Mounts"][0]["RW"]=writable
            with self.assertRaises(ValueError):install.reject_conflicts([item])
        item["Mounts"][0].update(Source=str(install.DATA),RW=False)
        with self.assertRaises(ValueError):install.reject_conflicts([item])
        item["Mounts"][0]["Source"]=str(install.DATA/"child")
        with self.assertRaises(ValueError):install.reject_conflicts([item])
        bad=container();bad["Mounts"].append({"Type":"bind","Source":"/opt/other","Destination":"/bad"})
        with self.assertRaises(ValueError):install.verify_container(bad,SHA)
        bad=container();bad["HostConfig"]["Privileged"]=True
        with self.assertRaises(ValueError):install.verify_container(bad,SHA)

    def test_backup_hashes_preserves_files_and_refuses_symlinks(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);data=root/"data";data.mkdir();(data/"state").write_text("existing virtual state")
            before=(data/"state").read_bytes()
            manifest=install.backup(data,root/"backup.tar.gz")
            self.assertIn("state",manifest);self.assertEqual(before,(data/"state").read_bytes())
            (data/"link").symlink_to(data/"state")
            with self.assertRaises(ValueError):install.backup(data,root/"bad.tar.gz")

    def test_unapproved_never_runs_command(self):
        with patch.dict(os.environ,BRAIN_INSTALL_APPROVED="no",DEEPSEEK_API_KEY="MODEL-SECRET"),patch.object(install,"run") as run:
            with self.assertRaises(ValueError):install.install(SHA,Path("unused"))
            run.assert_not_called()

    def test_install_success_and_failure_only_stop_own_container(self):
        for fail in (False,True):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as root:
                root=Path(root);data=root/"brain";data.mkdir()
                (data/"status.json").write_text(json.dumps({"mode":"paper","applied":False,"ts_ms":time.time()*1000}))
                commands=[]
                def run(args,timeout=600):
                    commands.append(args)
                    if args[0]=="git":return SHA+"\n"
                    if args[:2]==["docker","run"]:
                        (data/"status.json").write_text(json.dumps({"mode":"paper","applied":False,"ts_ms":time.time()*1000}))
                    if args[:2]==["docker","inspect"]:
                        item=container()
                        if fail:item["Config"]["Env"]=["DESK_MODE=live"]
                        return json.dumps([item])
                    return ""
                with patch.object(install,"DATA",data),patch.object(install,"BACKUPS",root/"backups"),patch.object(install,"run",side_effect=run),patch.object(install,"inspect_all",return_value=[]),patch.dict(os.environ,BRAIN_INSTALL_APPROVED="yes",DEEPSEEK_API_KEY="MODEL-SECRET"):
                    if fail:
                        with self.assertRaises(ValueError):install.install(SHA,root)
                        self.assertIn(["docker","stop",install.NAME],commands)
                    else:
                        install.install(SHA,root)
                        self.assertTrue(list((root/"backups").glob("install-*.json")))
                self.assertNotIn("MODEL-SECRET",str(commands))
                self.assertFalse(any("rm" in cmd for cmd in commands))


if __name__=="__main__":unittest.main()
