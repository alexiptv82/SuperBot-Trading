#!/usr/bin/env python3
"""Publish Brain Performance/Settings on existing RC84 PAPER dashboard ONLY.

Two modes: --preflight-only (no writes), --publish-readonly (controlled cutover).
Does not change trading workers, pause flags, Brain mandate, live orders or keys.
Keeps original RC84 container and frontend for rollback; RC73 stays untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

# Release owner fills an exact, immutable Git SHA when preparing the workflow.
RELEASE_SHA = os.environ.get("RC84_BRAIN_UI_RELEASE_SHA", "")
SRC = Path("/opt/superbot-v3-brain-ui-stage")
WEB = Path("/opt/superbot-web")
DB = Path("/opt/superbot/data/superbot.db")
BACKUPS = Path("/opt/superbot-backups")
BUNDLE = SRC / "brain-ui-build.tar.gz"
BUILD = SRC / "frontend-build"
PREV_BUILD = WEB / "build.rc84-before-brain-ui"
FAILED_BUILD = WEB / "build.brain-ui-failed"
CURRENT = WEB / "build"
CONTAINER = "superbot"
PREVIOUS = "superbot-rc84-before-brain-ui"
IMAGE = "superbot:brain-ui-20261111"
RUN_ROOT = Path("/opt/superbot-v3-paper-runs")
RUNS = {
    "hawk": RUN_ROOT / "classic-hawk-paper20261111",
    "bull": RUN_ROOT / "classic-bull-paper20261111",
    "brain": RUN_ROOT / "brain-v3-paper20261111",
}
RUN_ID = "brain-v3-paper20261111"

class GateError(Exception):
    pass

def refuse(code):
    raise GateError(code)

def run(*args, timeout=35, allow_error=False):
    try:
        cp = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        refuse("COMMAND_UNAVAILABLE")
    if cp.returncode and not allow_error:
        refuse("COMMAND_FAILED_" + str(args[0]).upper())
    return cp.stdout.strip() if cp.returncode == 0 else ""

def inspect(name):
    raw = run("docker", "inspect", name, timeout=12, allow_error=True)
    if not raw: return None
    try:
        data = json.loads(raw)
        if type(data) is list and len(data) == 1:
            return data[0]
    except ValueError:
        pass
    refuse("INVALID_DOCKER_INSPECT")

def http(path, method="GET"):
    try:
        req = urllib.request.Request("http://127.0.0.1:8002"+path, method=method)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except (OSError, ValueError):
        return 0

def checked_json(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
            refuse("RUN_FILE_MISSING")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict): refuse("RUN_MARKER_NOT_OBJECT")
        return value
    except (OSError, UnicodeError, ValueError):
        refuse("RUN_MARKER_INVALID")

def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for b in iter(lambda: stream.read(1048576),b""):
            h.update(b)
    return h.hexdigest()

def web_guards(*, require_new=False):
    if http("/api/health") != 200: refuse("PUBLIC_HEALTH")
    if http("/api/v3/overview") != 401: refuse("UNAUTH_OVERVIEW")
    if http("/api/auth/password-status") != 401: refuse("UNAUTH_PASSWORD")
    if require_new and http("/api/v3/brain/config") != 401:
        refuse("NEW_BRAIN_CONFIG_AUTH_GATE")
    for path in (
        "/api/desk/close-position", "/api/desk/bull/close-position",
        "/api/desk/close-all", "/api/desk/bull/close-all",
        "/api/desk/resume", "/api/desk/bull/resume",
        "/api/v3/brain/close",
    ):
        if http(path,method="POST") != 423: refuse("MUTATION_NOT_BLOCKED")
    return True

def preflight():
    if len(RELEASE_SHA) != 40 or any(ch not in "0123456789abcdef" for ch in RELEASE_SHA):
        refuse("RELEASE_PIN_UNSET")
    if not SRC.is_dir() or SRC.is_symlink():
        refuse("STAGING_NOT_SAFE")
    sha=run("git","-C",str(SRC),"rev-parse","HEAD",timeout=12)
    if sha!=RELEASE_SHA:refuse("CODE_SHA_DIFFERENT")
    if run("git","-C",str(SRC),"status","--porcelain","--untracked-files=no",timeout=12):
        refuse("CODE_WORKTREE_DIRTY")
    for item in ("backend/v3_api.py","frontend/src/pages/Performance.js",
                 "frontend/src/pages/Settings.js","Dockerfile"):
        if not (SRC/item).is_file():refuse("RELEASE_SOURCE_INCOMPLETE")
    if not BUNDLE.is_file() or BUNDLE.is_symlink() or BUNDLE.stat().st_size < 1000:
        refuse("RELEASE_BUNDLE_MISSING")
    if not CURRENT.is_dir() or CURRENT.is_symlink() or not (CURRENT/"index.html").is_file():
        refuse("CURRENT_PUBLIC_BUILD_MISSING")
    if any(x.exists() or x.is_symlink() for x in
           (BUILD,PREV_BUILD,FAILED_BUILD)):
        refuse("STAGING_OR_ROLLBACK_PATH_OCCUPIED")
    if inspect(PREVIOUS) is not None:
        refuse("ROLLBACK_CONTAINER_NAME_OCCUPIED")
    old=inspect(CONTAINER)
    if old is None or old.get("State",{}).get("Running") is not True:
        refuse("RC84_PUBLIC_NOT_RUNNING")
    env=dict(item.split("=",1) for item in old["Config"].get("Env",[]) if "=" in item)
    if (env.get("DESK_MODE")!="paper" or env.get("TRADING_MODE")!="paper"
            or env.get("V3_CUTOVER_READONLY")!="1"
            or env.get("V3_ALLOW_CLASSIC_SINGLE_CLOSE")!="0"
            or env.get("V3_ALLOW_BRAIN_SINGLE_CLOSE")!="0"
            or env.get("V3_RUN_ID")!=RUN_ID):
        refuse("RC84_NOT_PAPER_READONLY")
    if old.get("HostConfig",{}).get("RestartPolicy",{}).get("Name")!="always":
        refuse("OLD_RESTART_POLICY")
    bindings=old.get("HostConfig",{}).get("PortBindings",{}).get("8001/tcp") or []
    if len(bindings)!=1 or bindings[0].get("HostIp")!="127.0.0.1" or bindings[0].get("HostPort")!="8002":
        refuse("PUBLIC_BACKEND_PORT_CHANGED")
    mounts=old.get("Mounts") or []
    for key,p in RUNS.items():
        if not p.is_dir() or p.is_symlink() or not (p/"pause.flag").is_file():
            refuse("BOT_UNPAUSED_"+key)
        mark=checked_json(p/"PREPARED_PAUSED_ONLY.json")
        if mark.get("paper_only") is not True or mark.get("paused") is not True:
            refuse("BOT_NOT_PAPER_"+key)
        if not any(m.get("Source")==str(p) and m.get("RW") is False for m in mounts):
            refuse("PAPER_MOUNT_NOT_READONLY_"+key)
        if key in ("hawk","bull"):
            s=checked_json(p/"state_v2.json")
            if s.get("paused") is not True or (s.get("main") or {}).get("positions") not in ({},[]):
                refuse("CLASSIC_HAS_OPEN_POSITIONS")
            if int((s.get("main") or {}).get("cash",-1))!=1000:
                refuse("CLASSIC_CAPITAL_INCORRECT")
    if checked_json(RUNS["brain"]/"mandate.json").get("approved") is not False:
        refuse("BRAIN_MANDATE_APPROVED")
    if not (RUNS["brain"]/"journal.db").is_file(): refuse("BRAIN_JOURNAL_MISSING")
    if not DB.is_file() or DB.is_symlink():refuse("AUTH_DB_MISSING")
    if not BACKUPS.is_dir() or BACKUPS.is_symlink():refuse("AUTH_BACKUP_ROOT_MISSING")
    if shutil.disk_usage("/opt").free<1_500_000_000:
        refuse("INSUFFICIENT_DISK")
    web_guards()
    print("RC84_BRAIN_UI_PREFLIGHT=PASS",flush=True)
    print("RC84_BRAIN_UI_THREE_PAPER_RUNS_PAUSED=True",flush=True)
    print("RC84_BRAIN_UI_PUBLIC_SITE_CURRENTLY_SAFE=True",flush=True)
    return old

def auth_backup():
    folder=BACKUPS/("rc84-brain-ui-auth-"+time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())+"-"+str(os.getpid()))
    folder.mkdir(mode=0o700)
    target=folder/"superbot.db"
    a=b=None
    try:
        a=sqlite3.connect(DB.as_uri()+"?mode=ro",uri=True,timeout=15)
        a.execute("PRAGMA query_only=ON")
        b=sqlite3.connect(target)
        a.backup(b)
        if b.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            refuse("AUTH_BACKUP_INTEGRITY_FAILED")
        b.close();b=None
        a.close();a=None
        target.chmod(0o600)
        c=sqlite3.connect(target.as_uri()+"?mode=ro",uri=True,timeout=15)
        try:
            if c.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                refuse("AUTH_BACKUP_REOPEN_FAILED")
        finally:c.close()
    finally:
        if a:a.close()
        if b:b.close()
    print("RC84_BRAIN_UI_AUTH_BACKUP_CHECK=PASS",flush=True)
    return folder

def unpack():
    BUILD.mkdir(mode=0o700)
    with tarfile.open(BUNDLE,"r:gz") as tf:
        items=tf.getmembers()
        if len(items)>15000:refuse("ASSET_ARCHIVE_TOO_MANY_FILES")
        for m in items:
            p=PurePosixPath(m.name)
            if (p.is_absolute() or ".." in p.parts or not m.isfile() and not m.isdir()
                    or m.size>50_000_000):
                refuse("ASSET_ARCHIVE_UNSAFE")
            if m.isfile():
                target=BUILD.joinpath(*p.parts)
                target.parent.mkdir(parents=True,exist_ok=True)
                src=tf.extractfile(m)
                if src is None:refuse("ASSET_READ_FAILED")
                with src, target.open("wb") as dst:shutil.copyfileobj(src,dst)
    if not (BUILD/"index.html").is_file():refuse("ASSET_INDEX_MISSING")
    js=list((BUILD/"static/js").glob("main.*.js"))
    if len(js)!=1:refuse("MAIN_BUNDLE_MISSING")
    if not (BUILD/"asset-manifest.json").is_file():refuse("ASSET_MANIFEST_MISSING")
    print("RC84_BRAIN_UI_CANDIDATE_ASSET_STAGED=PASS",flush=True)

def portable_mounts(old):
    args=[]
    dests=set()
    for m in old.get("Mounts") or []:
        kind=m.get("Type")
        source=m.get("Source") if kind=="bind" else m.get("Name")
        dest=m.get("Destination")
        if (kind not in ("bind","volume") or not source or not dest
                or ":" in source+dest or dest in dests or "docker.sock" in dest):
            refuse("UNSAFE_MOUNT")
        dests.add(dest)
        args.extend(["-v",source+":"+dest+(":rw" if m.get("RW") else ":ro")])
    if "/app/data" not in dests or "/app/backend/.env" not in dests:
        refuse("AUTH_MOUNTS_MISSING")
    return args

def private_env(old):
    enforce={"DESK_MODE":"paper","TRADING_MODE":"paper",
             "V3_CUTOVER_READONLY":"1","V3_ALLOW_CLASSIC_SINGLE_CLOSE":"0",
             "V3_ALLOW_BRAIN_SINGLE_CLOSE":"0",
             "TELEGRAM_COMMANDS_ENABLED":"false",
             "V3_RUN_ID":RUN_ID,"PYTHONDONTWRITEBYTECODE":"1"}
    values={}
    for s in old["Config"].get("Env") or []:
        if "=" not in s:refuse("ENV_INVALID")
        key,value=s.split("=",1)
        if (not key.replace("_","").isalnum()
                or any(ch in value for ch in "\n\r\0")):refuse("ENV_INVALID")
        if key.startswith(("BITGET_","BYBIT_","BINANCE_")):continue
        values[key]=value
    values.update(enforce)
    fd,name=tempfile.mkstemp(prefix=".brain-ui-web-env-",dir="/run")
    os.fchmod(fd,0o600)
    try:
        with os.fdopen(fd,"w") as dest:
            for key,value in sorted(values.items()):
                dest.write(key+"="+value+"\n")
            dest.flush();os.fsync(dest.fileno())
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
    return Path(name)

def restore(renamed,created,front_swapped):
    print("RC84_BRAIN_UI_ROLLBACK_STARTED=True",flush=True)
    errors=[]
    if front_swapped:
        try:
            if CURRENT.exists() and not FAILED_BUILD.exists():CURRENT.replace(FAILED_BUILD)
            if PREV_BUILD.exists():PREV_BUILD.replace(CURRENT)
        except Exception:errors.append("frontend")
    if created:
        try: run("docker","rm","-f",CONTAINER,timeout=40)
        except GateError:errors.append("new_container")
    if renamed:
        try:
            run("docker","rename",PREVIOUS,CONTAINER,timeout=25)
            run("docker","update","--restart","always",CONTAINER,timeout=15)
            if inspect(CONTAINER)["State"]["Running"] is not True:
                run("docker","start",CONTAINER,timeout=40)
        except (GateError,TypeError): errors.append("old_container")
    if errors:
        print("RC84_BRAIN_UI_ROLLBACK_REQUIRES_OPERATOR=True",flush=True)
        refuse("ROLLBACK_PARTIAL")
    print("RC84_BRAIN_UI_ROLLBACK_OLD_RC84_HEALTHY="+str(http("/api/health")==200),flush=True)

def publish():
    old=preflight()
    unpack()
    backup=auth_backup()
    # docker build follows the exact same PIN as the frontend archive.
    run("docker","build","--pull=false","--quiet","-t",IMAGE,
        "-f",str(SRC/"Dockerfile"),str(SRC),timeout=480)
    print("RC84_BRAIN_UI_IMAGE_BUILT=PASS",flush=True)
    private=private_env(old)
    mounts=portable_mounts(old)
    renamed=created=front_swapped=success=False
    try:
        run("docker","rename",CONTAINER,PREVIOUS,timeout=25)
        renamed=True
        run("docker","stop","-t","12",PREVIOUS,timeout=35)
        args=["docker","create","--name",CONTAINER,"--restart","no",
              "--security-opt","no-new-privileges:true",
              "-p","127.0.0.1:8002:8001","--env-file",str(private)]
        args.extend(mounts)
        args.append(IMAGE)
        run(*args,timeout=40)
        created=True
        run("docker","start",CONTAINER,timeout=45)
        ok=False
        for _ in range(15):
            time.sleep(2)
            try:
                web_guards(require_new=True)
                ok=True
                break
            except GateError:
                continue
        if not ok:refuse("NEW_BACKEND_GUARDS_FAILED")
        print("RC84_BRAIN_UI_NEW_API_AUTHENTICATED_GATE=PASS",flush=True)
        CURRENT.replace(PREV_BUILD)
        front_swapped=True
        BUILD.replace(CURRENT)
        front_swapped=True
        if not (CURRENT/"index.html").is_file():refuse("NEW_FRONTEND_NOT_VISIBLE")
        if not web_guards(require_new=True):refuse("POST_RELEASE_GUARDS_FAILED")
        new=inspect(CONTAINER)
        if new is None or new["State"]["Running"] is not True:refuse("NEW_WEB_NOT_RUNNING")
        env=dict(x.split("=",1) for x in new["Config"]["Env"] if "=" in x)
        if (env.get("TRADING_MODE")!="paper" or env.get("DESK_MODE")!="paper"
            or env.get("V3_CUTOVER_READONLY")!="1"
            or env.get("V3_ALLOW_CLASSIC_SINGLE_CLOSE")!="0"
            or env.get("V3_ALLOW_BRAIN_SINGLE_CLOSE")!="0"):
            refuse("NEW_WEB_RUNTIME_NOT_SAFE")
        for p in RUNS.values():
            if not (p/"pause.flag").is_file():refuse("PAPER_PAUSE_DISAPPEARED")
        if checked_json(RUNS["brain"]/"mandate.json").get("approved") is not False:
            refuse("BRAIN_MANDATE_CHANGED")
        run("docker","update","--restart","always",CONTAINER,timeout=20)
        run("docker","update","--restart","no",PREVIOUS,timeout=20)
        success=True
        info={"release_sha":RELEASE_SHA,"timestamp_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
              "paper_paused":True,"brain_mandate_approved":False,
              "previous_container":PREVIOUS,"previous_frontend":str(PREV_BUILD),
              "auth_backup":str(backup)}
        report=SRC/"brain-ui-public-cutover-report.json"
        report.write_text(json.dumps(info,sort_keys=True)+"\n")
        report.chmod(0o600)
        print("RC84_BRAIN_UI_PUBLIC_RELEASE=PASS",flush=True)
        print("RC84_BRAIN_UI_OLD_RC84_RETAINED_FOR_ROLLBACK=True",flush=True)
        print("RC84_BRAIN_UI_RC73_BACKUP_UNTOUCHED=True",flush=True)
        print("RC84_BRAIN_UI_NO_PAPER_TRADE_OR_PROVIDER_CALLS=True",flush=True)
    finally:
        private.unlink(missing_ok=True)
        if not success:restore(renamed,created,front_swapped)

def main():
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--preflight-only",action="store_true")
    g.add_argument("--publish-readonly",action="store_true")
    args=p.parse_args()
    if args.preflight_only:preflight();return
    publish()

if __name__=="__main__":
    try:main()
    except GateError as e:
        print("RC84_BRAIN_UI_RELEASE_REFUSED="+str(e),file=sys.stderr,flush=True)
        sys.exit(2)
