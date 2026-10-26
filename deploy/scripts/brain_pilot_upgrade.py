"""State-preserving PAPER upgrader, including accounts with open positions.

Control script and application have separate immutable SHAs. Never bypasses the
flat-only repair. Never restores an old financial snapshot over newer activity.
"""
from __future__ import annotations
import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time


class UpgradeError(RuntimeError):
    """Messages are fixed public codes, never provider/Docker environment text."""


def load_helper():
    spec=importlib.util.spec_from_file_location("brain_install_helper",Path(__file__).with_name("brain_pilot_install.py"))
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    return helper


def read_database(root):
    path=Path(root)/"brain.sqlite3"
    if not path.is_file():raise UpgradeError("STATE_DATABASE_MISSING")
    db=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=10)
    try:
        if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":raise UpgradeError("DATABASE_INTEGRITY_FAILED")
        db.execute("BEGIN")
        row=db.execute("SELECT body FROM state WHERE id=1").fetchone()
        if not row:raise UpgradeError("STATE_ROW_MISSING")
        state=json.loads(row[0])
        events=list(db.execute("SELECT seq,kind,body FROM events ORDER BY seq"))
        return state,events
    finally:db.close()


def file_manifest(root):
    """Authoritative bytes, excluding only lock and SQLite shared-memory index."""
    result={}
    for p in sorted(Path(root).rglob("*")):
        if p.is_symlink():raise UpgradeError("SYMLINK_IN_DATA")
        if p.is_dir():continue
        if not p.is_file():raise UpgradeError("SPECIAL_FILE_IN_DATA")
        if p.name=="writer.lock" or p.name.endswith("-shm"):continue
        # SQLite read-only access can create an empty WAL shell. It contains no
        # transaction and is equivalent to absence; nonempty WAL is authoritative.
        if p.name.endswith("-wal") and p.stat().st_size==0:continue
        with p.open("rb") as stream:
            digest=hashlib.sha256()
            for chunk in iter(lambda:stream.read(1024*1024),b""):digest.update(chunk)
        result[str(p.relative_to(root))]={"size":p.stat().st_size,"sha256":digest.hexdigest()}
    return result


def validate_jsonl(root):
    for name in ("journal.jsonl","trade_history.jsonl","spend.jsonl"):
        path=Path(root)/name
        if not path.exists():continue
        with path.open("rb") as stream:
            for line in stream:
                if not line.endswith(b"\n"):raise UpgradeError("TRUNCATED_APPEND_LOG")
                obj=json.loads(line,parse_constant=lambda _:(_ for _ in ()).throw(ValueError("nonfinite")))
                if not isinstance(obj,dict):raise UpgradeError("INVALID_APPEND_LOG")


def clone_data(root,destination):
    """Copy logs + SQLite online-backup API, including committed WAL state."""
    import shutil
    root=Path(root);destination=Path(destination)
    for path in root.rglob("*"):
        relative=path.relative_to(root)
        if path.is_symlink():raise UpgradeError("SYMLINK_IN_DATA")
        if path.is_dir():(destination/relative).mkdir(parents=True,exist_ok=True)
        elif path.name not in ("writer.lock","brain.sqlite3","brain.sqlite3-wal","brain.sqlite3-shm"):
            (destination/relative).parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,destination/relative)
    source=sqlite3.connect((root/"brain.sqlite3").as_uri()+"?mode=ro",uri=True)
    target=sqlite3.connect(destination/"brain.sqlite3")
    try:source.backup(target)
    finally:target.close();source.close()


def validate_projection(before,after,before_events,after_events):
    """Allowed migration: stop policy + additive metadata + legacy entry filter."""
    old=copy.deepcopy(before["account"]);new=copy.deepcopy(after["account"])
    old.pop("brain_daily",None);new.pop("brain_daily",None)
    old["limits"].pop("daily_stop",None);new["limits"].pop("daily_stop",None)
    if old!=new:raise UpgradeError("MIGRATION_CHANGED_ACCOUNT_OR_POSITIONS")
    protected=[d for d in before["pending"] if d.get("action") in ("close","save_profit","partial_close","move_stop","hold")]
    for decision in protected:
        if decision not in after["pending"]:raise UpgradeError("MIGRATION_LOST_PROTECTIVE_ORDER")
    for key in ("last_bar","last_attempt","recent","pause_until","pause_start","pause_epoch","epoch","pause_reason","reentry_condition","last_prices","market_context"):
        if before.get(key)!=after.get(key):raise UpgradeError("MIGRATION_CHANGED_NONPOLICY_STATE")
    if after_events[:len(before_events)]!=before_events:raise UpgradeError("MIGRATION_REWROTE_EVENT_HISTORY")
    if after["account"]["limits"]["daily_stop"]!=.20:raise UpgradeError("MIGRATION_DAILY_POLICY_MISMATCH")


def validate_runtime_history(before,before_events,after,after_events):
    if after_events[:len(before_events)]!=before_events:raise UpgradeError("RUNTIME_REWROTE_HISTORY")
    remaining={(p["symbol"],p["id"]) for p in after["account"]["positions"].values()}
    closed=set()
    for _,kind,body in after_events[len(before_events):]:
        if kind=="trade":
            record=json.loads(body)
            if not record.get("partial"):closed.add((record.get("symbol"),record.get("id")))
    for p in before["account"]["positions"].values():
        if (p["symbol"],p["id"]) not in remaining|closed:raise UpgradeError("RUNTIME_POSITION_LOST_WITHOUT_CLOSE")
    if after["account"]["next_id"]<before["account"]["next_id"]:raise UpgradeError("RUNTIME_ID_RESET")


def validate_log_prefixes(root,before_manifest):
    for name in ("journal.jsonl","trade_history.jsonl","spend.jsonl"):
        if name not in before_manifest:continue
        meta=before_manifest[name];path=Path(root)/name
        if not path.is_file() or path.stat().st_size<meta["size"]:raise UpgradeError("APPEND_LOG_TRUNCATED")
        with path.open("rb") as stream:
            digest=hashlib.sha256();remaining=meta["size"]
            while remaining:
                block=stream.read(min(1024*1024,remaining))
                if not block:raise UpgradeError("APPEND_LOG_TRUNCATED")
                digest.update(block);remaining-=len(block)
        if digest.hexdigest()!=meta["sha256"]:raise UpgradeError("APPEND_LOG_REWRITTEN")


def retired_container(item,helper):
    if not item.get("Name","").lstrip("/").startswith(helper.NAME+"-rollback-"):return False
    state=item.get("State",{})
    if state.get("Running") or state.get("Restarting"):return False
    try:
        sha=item["Config"]["Labels"]["superbot.sha"]
        helper.validate_sha(sha);helper.verify_container(item,sha)
        return True
    except (ValueError,KeyError,TypeError):return False


def check_conflicts(helper,previous=None):
    others=[]
    for item in helper.inspect_all():
        if item.get("Name","").lstrip("/")==helper.NAME and previous is not None:
            helper.verify_container(item,previous)
            continue
        if retired_container(item,helper):continue
        others.append(item)
    helper.reject_conflicts(others)


def rollback(helper,previous,target,retained,before_manifest):
    """May restart old code ONLY if no authoritative byte has changed."""
    try:
        active=json.loads(helper.run(["docker","inspect",helper.NAME]))[0]
    except Exception:active=None
    if active:
        if active.get("Config",{}).get("Labels",{}).get("superbot.sha")==previous:
            if file_manifest(helper.DATA)!=before_manifest:
                raise UpgradeError("ROLLBACK_BLOCKED_STATE_CHANGED")
            helper.run(["docker","start",helper.NAME]);return "previous_restarted"
        # Do not stop or rename an unrelated/new third-party container.
        labels=active.get("Config",{}).get("Labels",{})
        if labels.get("superbot.component")!="brain-pilot" or labels.get("superbot.sha")!=target:
            raise UpgradeError("ROLLBACK_BLOCKED_FOREIGN_CONTAINER")
        helper.run(["docker","stop","--time","60",helper.NAME],timeout=90)
        helper.run(["docker","rename",helper.NAME,helper.NAME+"-failed-"+str(time.time_ns())])
    if file_manifest(helper.DATA)!=before_manifest:
        # Never overwrite fills, model spend, daily latch or newly added history.
        raise UpgradeError("ROLLBACK_BLOCKED_STATE_CHANGED_PRESERVED_STOPPED")
    helper.run(["docker","rename",retained,helper.NAME])
    helper.run(["docker","start",helper.NAME])
    return "previous_restarted"


def wait_healthy(helper,sha,started_ms,timeout=420):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        item=json.loads(helper.run(["docker","inspect",helper.NAME]))[0]
        helper.verify_container(item,sha)
        if not item.get("State",{}).get("Running"):raise UpgradeError("CANDIDATE_NOT_RUNNING")
        if item.get("RestartCount",0):raise UpgradeError("CANDIDATE_RESTARTED")
        try:status=json.loads((helper.DATA/"status.json").read_text())
        except (OSError,ValueError):status={}
        if (item.get("State",{}).get("Health",{}).get("Status")=="healthy"
                and started_ms<=status.get("ts_ms",0)<=time.time()*1000+5000
                and status.get("mode")=="paper" and status.get("applied") is False):return status
        time.sleep(5)
    raise UpgradeError("HEALTH_OR_FRESH_HEARTBEAT_TIMEOUT")


def upgrade(repo,sha,previous,helper=None):
    helper=helper or load_helper()
    helper.validate_sha(sha);helper.validate_sha(previous)
    if sha==previous:raise UpgradeError("TARGET_EQUALS_PREVIOUS")
    if os.getenv("BRAIN_INSTALL_APPROVED")!="yes" or not os.getenv("DEEPSEEK_API_KEY"):
        raise UpgradeError("APPROVAL_AND_KEY_REQUIRED")
    if helper.run(["git","-C",str(repo),"rev-parse","HEAD"]).strip()!=sha:
        raise UpgradeError("CHECKOUT_SHA_MISMATCH")
    if helper.DATA.resolve()!=helper.DATA:raise UpgradeError("NONCANONICAL_DATA")
    current=json.loads(helper.run(["docker","inspect",helper.NAME]))[0]
    helper.verify_container(current,previous)
    if not current.get("State",{}).get("Running"):raise UpgradeError("PREVIOUS_NOT_RUNNING")
    check_conflicts(helper,previous)
    # Slow build happens while old paper management remains running.
    helper.run(["docker","build","--label","superbot.sha="+sha,"-f",str(repo/"Dockerfile.brainpilot"),
                "-t","superbot-brain-pilot:sha-"+sha,str(repo)],timeout=900)
    print("BRAIN_UPGRADE_IMAGE_BUILT=PASS",flush=True)
    current=json.loads(helper.run(["docker","inspect",helper.NAME]))[0]
    helper.verify_container(current,previous)
    check_conflicts(helper,previous)
    retained=helper.NAME+"-rollback-"+previous[:12]+"-"+str(time.time_ns())
    helper.run(["docker","stop","--time","60",helper.NAME],timeout=90)
    renamed=False;before_manifest=None
    try:
        with (helper.DATA/"writer.lock").open("a") as writer:
            fcntl.flock(writer,fcntl.LOCK_EX|fcntl.LOCK_NB)
            before,before_events=read_database(helper.DATA)
            validate_jsonl(helper.DATA)
            before_manifest=file_manifest(helper.DATA)
            helper.BACKUPS.mkdir(mode=0o700,exist_ok=True)
            archive=helper.BACKUPS/("pre-upgrade-"+sha+"-"+str(time.time_ns())+".tar.gz")
            helper.backup(helper.DATA,archive)
            print("BRAIN_UPGRADE_BACKUP_VERIFIED=PASS",flush=True)
            with tempfile.TemporaryDirectory(prefix="migration-probe-",dir=helper.BACKUPS) as temp:
                probe=Path(temp);clone_data(helper.DATA,probe)
                probe_before=file_manifest(probe)
                # Constructor+checkpoint ONLY, network denied and no key passed.
                code=("from director.brain_pilot.pilot import Pilot; "
                      "p=Pilot('/out','',None); "
                      "p.checkpoint([{'kind':'upgrade_migration_probe'}]); p.close()")
                helper.run(["docker","run","--rm","--network","none","--read-only","--cap-drop","ALL",
                            "--user",str(os.getuid())+":"+str(os.getgid()),
                            "--security-opt","no-new-privileges","--memory","384m","--cpus","0.5",
                            "--tmpfs","/tmp:rw,nosuid,noexec,size=32m","--env","DESK_MODE=paper",
                            "--mount","type=bind,src="+str(probe)+",dst=/out",
                            "superbot-brain-pilot:sha-"+sha,"python","-c",code],timeout=120)
                after,after_events=read_database(probe)
                validate_projection(before,after,before_events,after_events)
                validate_log_prefixes(probe,probe_before)
            if file_manifest(helper.DATA)!=before_manifest:raise UpgradeError("SOURCE_CHANGED_DURING_PROBE")
            print("BRAIN_UPGRADE_MIGRATION_PROBE=PASS",flush=True)
            helper.run(["docker","rename",helper.NAME,retained]);renamed=True
            check_conflicts(helper)
            fcntl.flock(writer,fcntl.LOCK_UN)
            started_ms=time.time()*1000
            helper.run(helper.docker_args(sha),timeout=120)
        status=wait_healthy(helper,sha,started_ms)
        after,after_events=read_database(helper.DATA)
        validate_runtime_history(before,before_events,after,after_events)
        validate_log_prefixes(helper.DATA,before_manifest)
        if after["account"]["limits"]["daily_stop"]!=.20:raise UpgradeError("RUNNING_POLICY_NOT_MIGRATED")
        manifest={"application_sha":sha,"previous_sha":previous,"retained_container":retained,
                  "backup":str(archive),"mode":"paper","status_ts_ms":status["ts_ms"],
                  "open_positions_before":len(before["account"]["positions"]),
                  "open_positions_after":len(after["account"]["positions"])}
        (helper.BACKUPS/("upgrade-"+sha+".json")).write_text(json.dumps(manifest,sort_keys=True))
        print("BRAIN_UPGRADE_PAPER_STATE_HISTORY_HEALTH=PASS",flush=True)
        return manifest
    except Exception:
        if before_manifest is not None:
            result=rollback(helper,previous,sha,retained,before_manifest)
            print("BRAIN_UPGRADE_ROLLBACK="+result,flush=True)
        elif not renamed:
            # Cannot prove consistency/ownership (e.g. busy writer, corrupt DB).
            # Keep data and previous config; never race an unknown writer.
            print("BRAIN_UPGRADE_PREVIOUS_LEFT_STOPPED_UNVERIFIED_STATE",flush=True)
        raise


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--sha",required=True)
    parser.add_argument("--previous",required=True);parser.add_argument("--repo",type=Path,required=True)
    args=parser.parse_args()
    try:
        with open("/opt/superbot-brain-install.lock","a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            upgrade(args.repo,args.sha,args.previous)
    except UpgradeError as exc:
        print("BRAIN_UPGRADE_FAILED="+str(exc),flush=True);raise SystemExit(1)
    except Exception as exc:
        print("BRAIN_UPGRADE_FAILED="+type(exc).__name__,flush=True);raise SystemExit(1)


if __name__=="__main__":main()
