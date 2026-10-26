"""Narrow rollout of daily candle validation fix; flat PAPER brain only.

Retains its complete database/history. Does not touch old AI shadow or bots.
On failure restores previous image using the same data (schema unchanged).
"""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import sqlite3


def repair(repo,sha,previous):
    spec=importlib.util.spec_from_file_location("install",repo/"deploy/scripts/brain_pilot_install.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    mod.validate_sha(sha);mod.validate_sha(previous)
    if os.getenv("BRAIN_INSTALL_APPROVED")!="yes" or not os.getenv("DEEPSEEK_API_KEY"):
        raise ValueError("authorization_required")
    item=json.loads(mod.run(["docker","inspect",mod.NAME]))[0]
    mod.verify_container(item,previous)
    # No state migration or trading positions during this first-install repair.
    db=sqlite3.connect("file:"+str(mod.DATA/"brain.sqlite3")+"?mode=ro",uri=True)
    try:
        state=json.loads(db.execute("SELECT body FROM state WHERE id=1").fetchone()[0])
    finally:
        db.close()
    if state["account"]["positions"] or state["pending"]:
        raise ValueError("flat_brain_required")
    mod.run(["docker","stop",mod.NAME])
    try:
        # Durable archive is verified BEFORE removing only the container config.
        mod.BACKUPS.mkdir(mode=0o700,exist_ok=True)
        with (mod.DATA/"writer.lock").open("a") as writer:
            fcntl.flock(writer,fcntl.LOCK_EX|fcntl.LOCK_NB)
            mod.backup(mod.DATA,mod.BACKUPS/("pre-daily-repair-"+sha+".tar.gz"))
        mod.run(["docker","rm",mod.NAME])  # no -v, never remove data or image
        mod.install(sha,repo)
    except Exception:
        # Previous image remains available. Stop/remove only the attempted new SHA.
        try:
            current=json.loads(mod.run(["docker","inspect",mod.NAME]))[0]
        except Exception:
            current=None
        if current and current.get("Config",{}).get("Labels",{}).get("superbot.sha")==sha:
            mod.run(["docker","stop",mod.NAME]);mod.run(["docker","rm",mod.NAME]);current=None
        if current is None:
            mod.run(mod.docker_args(previous))
        elif current.get("Config",{}).get("Labels",{}).get("superbot.sha")==previous:
            mod.run(["docker","start",mod.NAME])
        print("BRAIN_DAILY_REPAIR_ROLLBACK_REQUESTED",flush=True)
        raise


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--sha",required=True)
    parser.add_argument("--previous",required=True);parser.add_argument("--repo",type=Path,required=True)
    args=parser.parse_args()
    try:
        with open("/opt/superbot-brain-install.lock","a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            repair(args.repo,args.sha,args.previous)
    except Exception as exc:
        print("BRAIN_DAILY_REPAIR_FAILED="+type(exc).__name__,flush=True);raise SystemExit(1)


if __name__=="__main__":main()
