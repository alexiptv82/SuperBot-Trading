#!/usr/bin/env python3
"""READ-ONLY preflight and optional STAGE of close-only PAPER bridge source.

--check: no mutations; --stage: clone pinned source into NEW isolated path
and verify syntax. Never installs/starts bridge, never changes Docker web,
bot service or the three PAPER runs. No real close commands.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

PIN = os.environ.get("RC84_CLOSE_BRIDGE_STAGE_SHA", "")
REPO = "https://github.com/alexiptv82/SuperBot-Trading.git"
STAGE = Path("/opt/superbot-v3-rc84-close-bridge-stage")
RUN_ROOT = Path("/opt/superbot-v3-paper-runs")
RUNS = {
    "hawk": RUN_ROOT / "classic-hawk-paper20261111",
    "bull": RUN_ROOT / "classic-bull-paper20261111",
    "brain": RUN_ROOT / "brain-v3-paper20261111",
}
SERVICES = (
    "superbot-v3-paper-falco.service",
    "superbot-v3-paper-toro.service",
    "superbot-v3-paper-brain-runner.service",
    "superbot-v3-paper-brain-exit.service",
)


def fail(token: str) -> None:
    raise RuntimeError(token)


def cmd(*args: str, timeout: int = 30) -> str:
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        fail("LOCAL_COMMAND_FAILED")
    return p.stdout.strip()


def check() -> tuple[str, ...]:
    if os.geteuid() != 0:
        fail("ROOT_REQUIRED")
    for name, folder in RUNS.items():
        if folder.is_symlink() or not folder.is_dir():
            fail("RUN_MISSING")
        marker = folder / "PREPARED_PAUSED_ONLY.json"
        if marker.is_symlink() or not marker.is_file() or not (folder / "pause.flag").is_file():
            fail("RUN_NOT_PAUSED")
        data = json.loads(marker.read_text())
        if data.get("paper_only") is not True or data.get("paused") is not True:
            fail("NOT_PAUSED_PAPER")
        if name in ("hawk", "bull"):
            state = json.loads((folder / "state_v2.json").read_text())
            if (state.get("main") or {}).get("positions") not in ({}, []):
                fail("OPEN_CLASSIC_POSITIONS_PRESENT")
    mandate = json.loads((RUNS["brain"] / "mandate.json").read_text())
    if mandate.get("approved") is not False:
        fail("BRAIN_MANDATE_APPROVED")
    service_pids = []
    for name in SERVICES:
        cmd("systemctl", "is-active", "--quiet", name)
        pid = cmd("systemctl", "show", "-p", "MainPID", "--value", name)
        if not pid.isdecimal() or int(pid) < 2:
            fail("SERVICE_PID_INVALID")
        service_pids.append(pid)
    inspect = json.loads(cmd("docker", "inspect", "superbot", timeout=15))[0]
    if inspect.get("State", {}).get("Running") is not True:
        fail("PUBLIC_WEB_NOT_RUNNING")
    env = dict(item.split("=", 1) for item in inspect["Config"].get("Env", []) if "=" in item)
    if (env.get("TRADING_MODE") != "paper" or env.get("DESK_MODE") != "paper"
            or env.get("V3_CUTOVER_READONLY") != "1"
            or env.get("V3_ALLOW_CLASSIC_SINGLE_CLOSE") != "0"
            or env.get("V3_ALLOW_BRAIN_SINGLE_CLOSE") != "0"):
        fail("CURRENT_WEB_GATE_CHANGED")
    mounts = inspect.get("Mounts") or []
    if any(not any(m.get("Source") == str(path) and m.get("RW") is False for m in mounts)
           for path in RUNS.values()):
        fail("PAPER_RUN_MOUNT_NOT_READONLY")
    # The new web must be able to reach a root-only socket; verify user ID
    # before claiming that 0600 root-owned socket is sufficient.
    if inspect["Config"].get("User", "") not in ("", "0", "root", "0:0", "root:root"):
        fail("WEB_NOT_ROOT_USER_REQUIRES_SOCKET_PERMISSION_DESIGN")
    if Path("/run/superbot-paper-close").exists():
        fail("BRIDGE_ALREADY_INSTALLED")
    if not Path("/opt/superbot-web/build/index.html").is_file():
        fail("PUBLIC_FRONTEND_MISSING")
    if not Path("/opt/superbot-web/build.rc84-before-brain-ui/index.html").is_file():
        fail("RC84_ROLLBACK_MISSING")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8002/api/health", timeout=5) as r:
            if r.status != 200: fail("PUBLIC_HEALTH_UNAVAILABLE")
    except (urllib.error.URLError, TimeoutError):
        fail("PUBLIC_HEALTH_UNAVAILABLE")
    print("RC84_SINGLE_CLOSE_STAGE_PRECHECK=PASS", flush=True)
    print("RC84_EXISTING_WEB_READONLY_ALL_PAPER_RO_MOUNTS=True", flush=True)
    print("RC84_BRAIN_MANDATE_UNAPPROVED_AND_WALLETS_PAUSED=True", flush=True)
    return tuple(service_pids)


def syntax(path: Path) -> None:
    for filename in (
        "backend/v3/close_bridge.py",
        "backend/v3/close_bridge_server.py",
        "backend/v3/cutover_gate.py",
        "backend/desk_api.py",
        "backend/v3_api.py",
        "backend/tests/test_v3_close_only_bridge.py",
    ):
        f = path / filename
        if f.is_symlink() or not f.is_file():
            fail("MISSING_CODE")
        ast.parse(f.read_text(encoding="utf-8"), filename=filename)


def stage() -> None:
    if len(PIN) != 40 or any(s not in "0123456789abcdef" for s in PIN):
        fail("CODE_PIN_NOT_SET")
    before = check()
    if STAGE.exists() or STAGE.is_symlink():
        if STAGE.is_symlink() or not STAGE.is_dir() or cmd("git", "-C", str(STAGE), "rev-parse", "HEAD") != PIN:
            fail("STAGE_ALREADY_OCCUPIED")
        syntax(STAGE)
        print("RC84_SINGLE_CLOSE_SOURCE_ALREADY_PINNED=True", flush=True)
    else:
        tmp = Path(tempfile.mkdtemp(prefix=".rc84-close-bridge-", dir="/opt"))
        try:
            cmd("git", "-c", "core.hooksPath=/dev/null", "clone", "-q",
                "--no-checkout", REPO, str(tmp), timeout=130)
            cmd("git", "-C", str(tmp), "-c", "core.hooksPath=/dev/null",
                "checkout", "-q", "--detach", PIN, timeout=75)
            if cmd("git", "-C", str(tmp), "rev-parse", "HEAD") != PIN:
                fail("CODE_PIN_MISMATCH")
            syntax(tmp)
            tmp.chmod(0o700)
            os.rename(tmp, STAGE)
        finally:
            if tmp.exists(): shutil.rmtree(tmp)
        print("RC84_SINGLE_CLOSE_SOURCE_STAGED=PASS", flush=True)
    after = check()
    if after != before:
        fail("TRADING_SERVICE_CHANGED_DURING_STAGE")
    print("RC84_SINGLE_CLOSE_SERVICE_PIDS_UNCHANGED=True", flush=True)
    print("RC84_SINGLE_CLOSE_ZERO_BOT_RESTARTS_OR_ORDERS=True", flush=True)
    print("RC84_SINGLE_CLOSE_WEB_DEPLOY_NOT_PERFORMED=True", flush=True)


def main():
    p = argparse.ArgumentParser()
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--check", action="store_true")
    grp.add_argument("--stage", action="store_true")
    opt = p.parse_args()
    if opt.stage: stage()
    else: check()


if __name__ == "__main__":
    try: main()
    except Exception as err:
        print("RC84_SINGLE_CLOSE_STAGE_REFUSED=" + (
            str(err) if type(err) is RuntimeError else "UNEXPECTED_ERROR"), flush=True)
        sys.exit(2)
