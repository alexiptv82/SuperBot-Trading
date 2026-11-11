#!/usr/bin/env python3
"""One-time RC84 SINGLE-CLOSE-ONLY PAPER dashboard cutover; RC84 rollback.

Approved purpose: allow one manual PAPER close via root-only Unix socket
bridge, with original three portfolio data mounts STILL read-only in Docker.
Absolutely no startup of strategy engines, unpause, Brain mandate approval,
exchange live calls, reset, bulk close or AI provider calls.

--preflight is read-only; --publish starts bridge and swaps web container, with
atomic identity checks, backend HTTP gates, and rollback on failure.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

PIN = "d6ef68730ba2017e1cb37daca1c0447e069a5d7b"
STAGE = Path("/opt/superbot-v3-rc84-close-bridge-stage")
UNIT_FILE = Path("/etc/systemd/system/superbot-v3-paper-single-close-bridge.service")
UNIT = UNIT_FILE.name
UNIT_SOURCE = Path("/opt/superbot-v3-rc84-close-bridge-release-unit/superbot-v3-paper-single-close-bridge.service")
UNIT_SHA = "9555640cdeda3cc28303532078ea12f5be470316"
SOCKET_DIR = Path("/run/superbot-paper-close")
SOCKET = SOCKET_DIR / "close.sock"
PREVIOUS = "superbot-rc84-before-singleclose"
LIVE = "superbot"
OLD_IMAGE = "superbot:brain-ui-20261111"
NEW_IMAGE = "superbot:rc84-paper-single-close-20261111"
RUN_ROOT = Path("/opt/superbot-v3-paper-runs")
RUNS = {
    "hawk": RUN_ROOT / "classic-hawk-paper20261111",
    "bull": RUN_ROOT / "classic-bull-paper20261111",
    "brain": RUN_ROOT / "brain-v3-paper20261111",
}
AUTH_DB = Path("/opt/superbot/data/superbot.db")
BACKUP_DIR = Path("/opt/superbot-backups")
WEB_DIR = Path("/opt/superbot-web")
PORT = 8002
HOST = "http://127.0.0.1:" + str(PORT)


class Refused(RuntimeError):
    pass


def refuse(code: str):
    raise Refused(code)


def call(*args: str, timeout: int = 30, fail_ok: bool = False) -> str:
    try:
        p = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        refuse("LOCAL_COMMAND_UNAVAILABLE")
    if p.returncode and not fail_ok:
        refuse("LOCAL_COMMAND_FAILED_" + str(args[0]).upper())
    return p.stdout.strip() if p.returncode == 0 else ""


def inspect(name: str) -> dict | None:
    raw = call("docker", "inspect", name, timeout=12, fail_ok=True)
    if not raw:
        return None
    try:
        result = json.loads(raw)
        if type(result) is list and len(result) == 1:
            return result[0]
    except ValueError:
        pass
    refuse("INVALID_CONTAINER_METADATA")


def web_status(path: str, method="GET", data: bytes | None = None) -> int:
    request = urllib.request.Request(
        HOST + path, method=method, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=6) as res:
            return res.status
    except urllib.error.HTTPError as e:
        return e.code
    except (OSError, ValueError, TimeoutError):
        return 0


def valid_paper_wallets() -> tuple[str, ...]:
    pids = []
    for name, folder in RUNS.items():
        if folder.is_symlink() or not folder.is_dir():
            refuse("RUN_DIR_UNEXPECTED")
        marker = folder / "PREPARED_PAUSED_ONLY.json"
        if marker.is_symlink() or not marker.is_file() or not (folder / "pause.flag").is_file():
            refuse("PAPER_PAUSE_MISSING")
        try:
            m = json.loads(marker.read_text())
        except (OSError, ValueError):
            refuse("PAPER_MARKER_INVALID")
        if m.get("paper_only") is not True or m.get("paused") is not True:
            refuse("PAPER_MARKER_NOT_PAUSED")
        if name in ("hawk", "bull"):
            try:
                state = json.loads((folder / "state_v2.json").read_text())
            except (OSError, ValueError):
                refuse("CLASSIC_STATE_UNAVAILABLE")
            if (state.get("main") or {}).get("positions") not in ({}, []):
                refuse("CLASSIC_POSITIONS_CURRENTLY_OPEN")
    try:
        mandate = json.loads((RUNS["brain"] / "mandate.json").read_text())
    except (OSError, ValueError):
        refuse("BRAIN_MANDATE_UNAVAILABLE")
    if mandate.get("approved") is not False:
        refuse("BRAIN_MANDATE_APPROVED")
    # No strategy/exit process may be restarted by this migration.
    for unit in (
        "superbot-v3-paper-falco.service",
        "superbot-v3-paper-toro.service",
        "superbot-v3-paper-brain-runner.service",
        "superbot-v3-paper-brain-exit.service",
    ):
        call("systemctl", "is-active", "--quiet", unit)
        pid = call("systemctl", "show", unit, "-p", "MainPID", "--value")
        if not pid.isdecimal() or int(pid) < 2:
            refuse("TRADING_UNIT_NOT_RUNNING")
        pids.append(pid)
    return tuple(pids)


def web_gates(*, new: bool) -> bool:
    if web_status("/api/health") != 200:
        refuse("BACKEND_HEALTH_FAILED")
    if web_status("/api/v3/overview") != 401:
        refuse("AUTH_DASHBOARD_GATE_FAILED")
    if web_status("/api/v3/brain/config") != 401:
        refuse("AUTH_BRAIN_CONFIG_GATE_FAILED")
    for endpoint in (
        "/api/desk/close-all", "/api/desk/bull/close-all",
        "/api/desk/resume", "/api/desk/bull/resume",
        "/api/bot/start", "/api/desk/reset-portfolio",
    ):
        if web_status(endpoint, "POST", b"{}") != 423:
            refuse("FORBIDDEN_MUTATION_GATE_FAILED")
    for endpoint in (
        "/api/desk/close-position", "/api/desk/bull/close-position",
        "/api/v3/brain/close",
    ):
        expected = 401 if new else 423
        if web_status(endpoint, "POST", b"{}") != expected:
            refuse("SINGLE_CLOSE_SESSION_GATE_FAILED")
    return True


def preflight() -> tuple[dict, tuple[str, ...]]:
    if os.geteuid() != 0:
        refuse("ROOT_REQUIRED")
    if STAGE.is_symlink() or not STAGE.is_dir():
        refuse("STAGED_SOURCE_MISSING")
    if call("git", "-C", str(STAGE), "rev-parse", "HEAD") != PIN:
        refuse("STAGED_SOURCE_PIN_CHANGED")
    if call("git", "-C", str(STAGE), "status", "--porcelain", "--untracked-files=no"):
        refuse("STAGED_SOURCE_DIRTY")
    if (not UNIT_SOURCE.is_file() or UNIT_SOURCE.is_symlink()
            or not UNIT_SOURCE.parent.is_dir() or UNIT_SOURCE.parent.is_symlink()
            or UNIT_SOURCE.parent.stat().st_uid != 0
            or UNIT_SOURCE.parent.stat().st_mode & 0o077):
        refuse("BRIDGE_SYSTEMD_TEMPLATE_MISSING")
    if call("git", "hash-object", str(UNIT_SOURCE)) != UNIT_SHA:
        refuse("BRIDGE_UNIT_TEMPLATE_HASH_MISMATCH")
    if UNIT_FILE.exists() or UNIT_FILE.is_symlink() or SOCKET_DIR.exists() or SOCKET_DIR.is_symlink():
        refuse("BRIDGE_UNIT_OR_SOCKET_ALREADY_EXISTS")
    if inspect(PREVIOUS) is not None:
        refuse("RC84_ROLLBACK_NAME_OCCUPIED")
    old = inspect(LIVE)
    if old is None or old.get("State", {}).get("Running") is not True:
        refuse("RC84_PUBLIC_NOT_RUNNING")
    if old.get("Config", {}).get("Image") != OLD_IMAGE:
        refuse("CURRENT_PUBLIC_IMAGE_CHANGED")
    if old.get("HostConfig", {}).get("RestartPolicy", {}).get("Name") != "always":
        refuse("PUBLIC_RESTART_POLICY_CHANGED")
    e = dict(row.split("=", 1) for row in old["Config"].get("Env", []) if "=" in row)
    if any(e.get(k) != v for k, v in {
        "V3_CUTOVER_READONLY": "1", "DESK_MODE": "paper",
        "TRADING_MODE": "paper", "V3_ALLOW_CLASSIC_SINGLE_CLOSE": "0",
        "V3_ALLOW_BRAIN_SINGLE_CLOSE": "0",
        "V3_RUN_ID": "brain-v3-paper20261111",
    }.items()):
        refuse("CURRENT_PUBLIC_NOT_READONLY")
    if old["Config"].get("User", "") not in ("", "0", "root", "0:0", "root:root"):
        refuse("WEB_NONROOT_REQUIRES_DIFFERENT_SOCKET_PERMISSIONS")
    bound = old.get("HostConfig", {}).get("PortBindings", {}).get("8001/tcp") or []
    if (len(bound) != 1 or bound[0].get("HostIp") != "127.0.0.1"
            or bound[0].get("HostPort") != str(PORT)):
        refuse("PUBLIC_PORT_CHANGED")
    mounts = old.get("Mounts") or []
    if any(not any(m.get("Source") == str(p) and m.get("RW") is False for m in mounts)
           for p in RUNS.values()):
        refuse("ORIGINAL_PAPER_MOUNT_NOT_RO")
    if not (WEB_DIR / "build/index.html").is_file() or not (
            WEB_DIR / "build.rc84-before-brain-ui/index.html").is_file():
        refuse("PUBLIC_STATIC_OR_EXISTING_ROLLBACK_MISSING")
    call("runuser", "-u", "www-data", "--", "test", "-r", str(WEB_DIR / "build/index.html"))
    if not AUTH_DB.is_file() or AUTH_DB.is_symlink() or not BACKUP_DIR.is_dir():
        refuse("AUTH_BACKUP_ROOT_MISSING")
    if shutil.disk_usage("/opt").free < 1_500_000_000:
        refuse("DISK_NOT_SUFFICIENT")
    current_pids = valid_paper_wallets()
    web_gates(new=False)
    print("RC84_CLOSE_ONLY_ROLLBACK_PREFLIGHT=PASS",flush=True)
    print("RC84_CLOSE_ONLY_PUBLIC_RC84_READONLY=PASS",flush=True)
    print("RC84_CLOSE_ONLY_THREE_PAPER_RUNS_PAUSED=PASS",flush=True)
    return old,current_pids


def auth_backup() -> None:
    folder = BACKUP_DIR / ("rc84-closebridge-login-" +
                          time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + str(os.getpid()))
    folder.mkdir(mode=0o700)
    out = folder / "superbot.db"
    source = None
    target = None
    try:
        source = sqlite3.connect(AUTH_DB.as_uri() + "?mode=ro", uri=True, timeout=15)
        source.execute("PRAGMA query_only=ON")
        target = sqlite3.connect(out)
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            refuse("LOGIN_BACKUP_INTEGRITY")
        target.close(); target=None
        source.close(); source=None
        out.chmod(0o600)
        check = sqlite3.connect(out.as_uri() + "?mode=ro", uri=True, timeout=15)
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                refuse("LOGIN_BACKUP_REOPEN")
        finally:
            check.close()
    finally:
        if source:source.close()
        if target:target.close()
    print("RC84_CLOSE_ONLY_LOGIN_SQLITE_BACKUP=PASS",flush=True)


def start_bridge() -> None:
    shutil.copy2(UNIT_SOURCE, UNIT_FILE)
    UNIT_FILE.chmod(0o644)
    call("systemctl", "daemon-reload", timeout=30)
    call("systemctl", "start", UNIT, timeout=30)
    for _ in range(10):
        status = subprocess.run(
            ["systemctl", "is-active", "--quiet", UNIT],
            capture_output=True, check=False, timeout=8)
        if status.returncode == 0 and SOCKET.is_socket():
            st = SOCKET.stat()
            if st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o600:
                break
        time.sleep(0.3)
    else:
        refuse("BRIDGE_DID_NOT_START")
    print("RC84_CLOSE_ONLY_HOST_BRIDGE_RUNNING=PASS",flush=True)


def socket_ro_docker_test() -> None:
    # A fresh throwaway container sees ONLY the socket, no portfolio data,
    # with network disabled and file system read-only. It sends an INVALID
    # request (never a close), verifying RO bind connectivity and 423 deny.
    snippet = (
        "import json,socket;"
        "c=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);"
        "c.settimeout(3);c.connect('/run/superbot-paper-close/close.sock');"
        "c.sendall(json.dumps(dict(wallet='invalid',symbol='BTC')).encode()+bytes([10]));"
        "data=json.loads(c.recv(2048));"
        "assert data.get('status')==423 and data.get('payload',{}).get('ok') is False;"
        "print('RC84_CLOSE_ONLY_SOCKET_RO_DOCKER_TEST=PASS')"
    )
    result = call(
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--user", "0",
        "-v", str(SOCKET_DIR) + ":" + str(SOCKET_DIR) + ":ro",
        "--entrypoint", "python3", NEW_IMAGE, "-c", snippet,
        timeout=45)
    if "RC84_CLOSE_ONLY_SOCKET_RO_DOCKER_TEST=PASS" not in result:
        refuse("RO_DOCKER_SOCKET_TEST_FAILED")
    print("RC84_CLOSE_ONLY_SOCKET_RO_DOCKER_TEST=PASS",flush=True)


def original_mount_args(old: dict) -> list[str]:
    args, destinations = [], set()
    for m in old.get("Mounts") or []:
        kind = m.get("Type")
        src = m.get("Source") if kind == "bind" else m.get("Name")
        dst = m.get("Destination")
        if (kind not in ("bind", "volume") or not src or not dst
                or dst in destinations or ":" in src + dst or "docker.sock" in dst):
            refuse("MOUNT_UNSAFE")
        destinations.add(dst)
        args.extend(["-v", src + ":" + dst + (":rw" if m.get("RW") else ":ro")])
    if "/app/data" not in destinations or "/app/backend/.env" not in destinations:
        refuse("WEB_AUTH_MOUNTS_INCOMPLETE")
    if str(SOCKET_DIR) in destinations:
        refuse("SOCKET_ALREADY_MOUNTED")
    args.extend(["-v", str(SOCKET_DIR) + ":" + str(SOCKET_DIR) + ":ro"])
    return args


def private_env_file(old: dict) -> Path:
    env = {}
    for row in old.get("Config", {}).get("Env", []) or []:
        if "=" not in row:
            refuse("ENV_ROW_INVALID")
        k, v = row.split("=", 1)
        if not k.replace("_", "").isalnum() or any(x in v for x in "\n\r\0"):
            refuse("ENV_ROW_UNSAFE")
        if k.startswith(("BITGET_", "BYBIT_", "BINANCE_")):
            continue  # The web never needs exchange trade keys.
        env[k] = v
    env.update({
        "V3_CUTOVER_READONLY": "1",
        "DESK_MODE": "paper", "TRADING_MODE": "paper",
        "V3_ALLOW_CLASSIC_SINGLE_CLOSE": "1",
        "V3_ALLOW_BRAIN_SINGLE_CLOSE": "1",
        "V3_CLOSE_BRIDGE_ONLY": "1",
        "V3_CLOSE_BRIDGE_SOCKET": str(SOCKET),
        "V3_RUN_ID": "brain-v3-paper20261111",
        "TELEGRAM_COMMANDS_ENABLED": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    fd, filename = tempfile.mkstemp(prefix=".rc84-close-bridge-env-", dir="/run")
    os.fchmod(fd, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            for k, v in sorted(env.items()):
                f.write(k + "=" + v + "\n")
            f.flush(); os.fsync(f.fileno())
        return Path(filename)
    except BaseException:
        Path(filename).unlink(missing_ok=True)
        raise


def rollback_web(renamed: bool, created: bool) -> None:
    print("RC84_CLOSE_ONLY_WEB_ROLLBACK_BEGIN=True",flush=True)
    errors=[]
    if created:
        try: call("docker", "rm", "-f", LIVE, timeout=40)
        except Refused: errors.append("new_web")
    if renamed:
        try:
            call("docker", "rename", PREVIOUS, LIVE, timeout=20)
            call("docker", "update", "--restart", "always", LIVE, timeout=15)
            original=inspect(LIVE)
            if original is not None and original.get("State",{}).get("Running") is not True:
                call("docker", "start", LIVE, timeout=35)
        except Refused: errors.append("old_web")
    if errors or web_status("/api/health")!=200:
        print("RC84_CLOSE_ONLY_WEB_ROLLBACK_NEEDS_OPERATOR=True",flush=True)
    else:
        print("RC84_CLOSE_ONLY_WEB_ROLLBACK=PASS",flush=True)


def cleanup_bridge() -> None:
    try:call("systemctl", "stop", UNIT, timeout=25, fail_ok=True)
    except Refused:pass
    try:
        if UNIT_FILE.is_file() and not UNIT_FILE.is_symlink():
            UNIT_FILE.unlink()
        call("systemctl", "daemon-reload", timeout=25, fail_ok=True)
    except (OSError,Refused):
        print("RC84_CLOSE_ONLY_BRIDGE_UNIT_CLEANUP_NEEDS_OPERATOR=True",flush=True)


def publish() -> None:
    old,pids=preflight()
    auth_backup()
    installed=False
    renamed=created=success=False
    keyfile=None
    try:
        # The existing web remains online while the candidate is built.
        # Docker image includes FastAPI; never install any packages into the
        # paused strategy Python environment.
        call("docker", "build", "--pull=false", "--quiet",
             "-t", NEW_IMAGE, "-f", str(STAGE / "Dockerfile"), str(STAGE),
             timeout=500)
        print("RC84_CLOSE_ONLY_PINNED_WEB_IMAGE_BUILD=PASS",flush=True)
        installed=True  # cleanup even if the bridge start partially failed
        start_bridge()
        socket_ro_docker_test()
        if valid_paper_wallets()!=pids:
            refuse("PAPER_WORKER_CHANGED_DURING_BRIDGE_PREP")
        mount_args=original_mount_args(old)
        keyfile=private_env_file(old)
        call("docker", "rename", LIVE, PREVIOUS, timeout=25)
        renamed=True
        call("docker", "stop", "-t", "12", PREVIOUS, timeout=35)
        args=["docker","create","--name",LIVE,"--restart","no",
              "--security-opt","no-new-privileges:true",
              "-p","127.0.0.1:8002:8001","--env-file",str(keyfile)]
        args.extend(mount_args)
        args.append(NEW_IMAGE)
        call(*args,timeout=50)
        created=True
        call("docker","start",LIVE,timeout=50)
        healthy=False
        for _ in range(16):
            time.sleep(2)
            try:
                web_gates(new=True)
                healthy=True
                break
            except Refused:
                continue
        if not healthy:
            refuse("NEW_PUBLIC_WEB_AUTH_OR_CLOSE_GATE_FAILED")
        new=inspect(LIVE)
        if new is None or new.get("State",{}).get("Running") is not True:
            refuse("NEW_WEB_STOPPED")
        new_env = dict(x.split("=",1) for x in new["Config"].get("Env",[]) if "=" in x)
        if any(new_env.get(k)!=v for k,v in {
            "TRADING_MODE":"paper", "DESK_MODE":"paper",
            "V3_CUTOVER_READONLY":"1",
            "V3_ALLOW_CLASSIC_SINGLE_CLOSE":"1",
            "V3_ALLOW_BRAIN_SINGLE_CLOSE":"1",
            "V3_CLOSE_BRIDGE_ONLY":"1",
            "V3_CLOSE_BRIDGE_SOCKET":str(SOCKET),
        }.items()):
            refuse("NEW_WEB_GATES_DIFFER")
        for p in list(RUNS.values())+[SOCKET_DIR]:
            if not any(m.get("Source")==str(p) and m.get("RW") is False
                       for m in new.get("Mounts",[]) or []):
                refuse("NEW_WEB_UNSAFE_MOUNT")
        if valid_paper_wallets()!=pids:
            refuse("PAPER_SERVICE_CHANGED_DURING_CUTOVER")
        if not SOCKET.is_socket():
            refuse("CLOSE_BRIDGE_SOCKET_DISAPPEARED")
        # Existing React static assets are UNCHANGED: this release changes
        # only the authenticated backend and adds the separate command bridge.
        call("runuser", "-u", "www-data", "--", "test", "-r",
             str(WEB_DIR / "build/index.html"))
        call("docker","update","--restart","always",LIVE,timeout=20)
        call("docker","update","--restart","no",PREVIOUS,timeout=15)
        success=True
        print("RC84_CLOSE_ONLY_PUBLIC_SINGLE_CLOSE_ENABLED=PASS",flush=True)
        print("RC84_CLOSE_ONLY_WEB_PAPER_AND_RUN_MOUNTS_RO=PASS",flush=True)
        print("RC84_CLOSE_ONLY_RESET_BULK_AND_START_BLOCKED=PASS",flush=True)
        print("RC84_CLOSE_ONLY_AUTH_LOGIN_PRESERVED=PASS",flush=True)
        print("RC84_CLOSE_ONLY_FALCO_TORO_BRAIN_PAUSED=PASS",flush=True)
        print("RC84_CLOSE_ONLY_PREVIOUS_PUBLIC_RC84_RETAINED_FOR_ROLLBACK=True",flush=True)
        print("RC84_CLOSE_ONLY_NO_AI_OR_EXCHANGE_ORDERS=True",flush=True)
    finally:
        if keyfile is not None:
            keyfile.unlink(missing_ok=True)
        if not success:
            # A failed docker create may leave a named container behind before
            # returning nonzero. Detect it, otherwise rollback could fail to
            # rename the original public web into its rightful name.
            if renamed:
                created = created or inspect(LIVE) is not None
            if renamed or created:
                rollback_web(renamed,created)
            if installed:
                cleanup_bridge()


def main() -> None:
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight",action="store_true")
    group.add_argument("--publish",action="store_true")
    args=parser.parse_args()
    if args.preflight:
        preflight()
    else:
        publish()


if __name__ == "__main__":
    try:main()
    except Exception as exc:
        print("RC84_CLOSE_ONLY_RELEASE_REFUSED="+(
            str(exc) if type(exc) is Refused else "UNEXPECTED_ERROR"),flush=True)
        sys.exit(2)
