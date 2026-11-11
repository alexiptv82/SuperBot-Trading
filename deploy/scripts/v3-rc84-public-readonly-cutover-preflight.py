#!/usr/bin/env python3
"""RC84 public cutover READ-ONLY PRECONDITION check. Does not make changes.

This evaluates if RC84 candidate and three NEW PAPER wallets are in a safe
state for a separate, rollback-capable publication. Never reads secret values.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

PIN = "0e29a73a36f668643da4088178bacb8616a45ac0"
STAGE = Path("/opt/superbot-v3-rc84-stage")
UI = Path("/opt/superbot-v3-rc84-ui-preview")
OLDWEB = Path("/opt/superbot-web")
ROOT = Path("/opt/superbot-v3-paper-runs")
RUNS = {
    "hawk": ROOT / "classic-hawk-paper20261111",
    "bull": ROOT / "classic-bull-paper20261111",
    "brain": ROOT / "brain-v3-paper20261111",
}
SERVICES = (
    "superbot-v3-paper-falco.service",
    "superbot-v3-paper-toro.service",
    "superbot-v3-paper-brain-exit.service",
    "superbot-v3-paper-brain-runner.service",
)
NEW_OLDNAME = "superbot-rc84-previous"
FORBIDDEN_NEW_WEB_DIRS = ("build.rc84-previous", "build.rc84-new", "build.rc84-failed")


def die(code: str) -> None:
    print("RC84_CUTOVER_NO_GO=" + code, flush=True)
    raise SystemExit(2)


def good(code: str) -> None:
    print("RC84_CUTOVER_CHECK_" + code + "=PASS", flush=True)


def run(*argv: str, timeout: float = 10) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, timeout=timeout, text=True, capture_output=True, check=False)
    except (OSError, subprocess.SubprocessError):
        die("REQUIRED_LOCAL_TOOL_FAILED")


def stat_file(path: Path) -> bool:
    return not path.is_symlink() and path.is_file()


def json_file(path: Path, max_size: int = 131072) -> dict:
    try:
        if not stat_file(path) or not 0 < path.stat().st_size < max_size:
            raise ValueError("not_regular_or_oversized")
        data = json.loads(path.read_bytes())
        if not isinstance(data, dict):
            raise ValueError("not_object")
        return data
    except (OSError, TypeError, ValueError):
        die("INVALID_JSON_MARKER")


def docker(name: str) -> dict | None:
    c = run("docker", "inspect", name, timeout=12)
    if c.returncode:
        return None
    try:
        val = json.loads(c.stdout)
        return val[0] if isinstance(val, list) and len(val) == 1 else None
    except (ValueError, IndexError, TypeError):
        die("DOCKER_INSPECT_INVALID")


def active(service: str) -> bool:
    return run("systemctl", "is-active", "--quiet", service, timeout=8).returncode == 0


def code(url: str, method: str = "GET") -> int:
    try:
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as err:
        return err.code
    except (OSError, ValueError, TimeoutError):
        return 0


def recent_heartbeat(path: Path, *, age_ms: int = 120000) -> dict:
    beat = json_file(path, 16384)
    timestamp = beat.get("ts_ms")
    if type(timestamp) is not int or not 0 <= time.time() * 1000 - timestamp < age_ms:
        die("HEARTBEAT_NOT_FRESH")
    return beat


def read_classic(name: str) -> None:
    path = RUNS[name]
    marker = json_file(path / "PREPARED_PAUSED_ONLY.json")
    state = json_file(path / "state_v2.json")
    if (marker.get("portfolio_id") != name or marker.get("paper_only") is not True
            or marker.get("paused") is not True or str(marker.get("initial_equity")) != "1000"):
        die("CLASSIC_MARKER_INCORRECT")
    main = state.get("main")
    if not isinstance(main, dict) or float(main.get("cash", -1)) != 1000:
        die("CLASSIC_EQUITY_NOT_1000")
    if main.get("positions") not in ({}, []):
        die("CLASSIC_ALREADY_HAS_POSITIONS")
    if state.get("paused") is not True or state.get("mode") != "paused":
        die("CLASSIC_STATE_NOT_PAUSED")
    hb = json_file(path / "heartbeat.json", 16384)
    ts = hb.get("ts")
    if (hb.get("portfolio") != name or hb.get("mode") != "paused"
            or hb.get("exec_mode") != "paper" or hb.get("open_positions") != 0
            or type(ts) not in (int, float) or not 0 <= time.time() - ts < 120):
        die("CLASSIC_HEARTBEAT_NOT_PAUSED")
    good(name.upper() + "_1000_PAUSED")


def main() -> None:
    # Python -I and PYTHONDONTWRITEBYTECODE=1 when running this script; no imports
    # from project code (such imports might initialize DBs).
    if not STAGE.is_dir() or STAGE.is_symlink() or not UI.is_dir() or UI.is_symlink():
        die("RC84_SOURCE_OR_PREVIEW_MISSING")
    if run("git", "-C", str(STAGE), "rev-parse", "HEAD").stdout.strip() != PIN:
        die("RC84_PIN_MISMATCH")
    for name in ("Dockerfile", "backend/server.py", "backend/v3/cutover_gate.py"):
        if not stat_file(STAGE / name):
            die("STAGE_SOURCE_INCOMPLETE")
    if not stat_file(UI / "frontend/index.html"):
        die("CANDIDATE_FRONTEND_MISSING")
    preview = json_file(UI / "preview-ready.json", 16384)
    if preview.get("pinned_sha") != PIN or preview.get("isolated") is not True:
        die("PREVIEW_NOT_CERTIFIED")
    if preview.get("trading_mutations_blocked") is not True:
        die("PREVIEW_GATE_NOT_CERTIFIED")
    good("PINNED_BACKEND_AND_FRONTEND")

    for label, path in RUNS.items():
        if not path.is_dir() or path.is_symlink() or not stat_file(path / "pause.flag"):
            die("RUN_MISSING_OR_NOT_PAUSED_" + label.upper())
    for service in SERVICES:
        if not active(service):
            die("SERVICE_NOT_ACTIVE_" + service.replace(".", "_"))
    read_classic("hawk")
    read_classic("bull")
    bp = RUNS["brain"]
    marker = json_file(bp / "PREPARED_PAUSED_ONLY.json")
    mandate = json_file(bp / "mandate.json")
    config_file = bp / "runner_config.json"
    config = json_file(config_file)
    risk = config.get("risk_policy")
    if not isinstance(risk, dict):
        die("BRAIN_RISK_MISSING")
    if (marker.get("run_id") != "brain-v3-paper20261111"
            or mandate.get("approved") is not False
            or marker.get("mandate_approved") is not False
            or marker.get("paused") is not True
            or marker.get("paper_only") is not True
            or str(config.get("initial_equity")) != "2000"
            or risk.get("min_leverage") != 20 or risk.get("max_leverage") != 50
            or str(risk.get("minimum_equity")) != "450"):
        die("BRAIN_MANDATE_OR_POLICY_INVALID")
    if marker.get("config_sha256") != hashlib.sha256(config_file.read_bytes()).hexdigest():
        die("BRAIN_RUN_CONFIG_HASH_INCORRECT")
    if not stat_file(bp / "journal.db") or not stat_file(bp / "budget.db"):
        die("BRAIN_JOURNALS_MISSING")
    beat = recent_heartbeat(bp / "heartbeat.json")
    ebeat = recent_heartbeat(bp / "exit_heartbeat.json")
    if (beat.get("run_id") != "brain-v3-paper20261111"
            or beat.get("state") not in ("halted", "paused")
            or ebeat.get("run_id") != "brain-v3-paper20261111"
            or ebeat.get("state") != "healthy" or ebeat.get("last_error") is not None):
        die("BRAIN_HEARTBEAT_NOT_SAFE")
    good("BRAIN_2000_PAUSED_EXIT_HEALTHY")

    for name in ("hawk", "bull"):
        old = docker("superbot-desk-" + name)
        if old is None or old.get("State", {}).get("Running") is not False:
            die("HISTORIC_CLASSIC_WORKER_ACTIVE")
        if not stat_file(Path("/opt/superbot-desk-data") / name / "pause.flag"):
            die("HISTORIC_CLASSIC_PAUSE_MISSING")
    for service in ("superbot-v3-falco-exit.service", "superbot-v3-toro-exit.service"):
        if not active(service):
            die("LEGACY_EXIT_SERVICE_MISSING")
    good("LEGACY_UNCHANGED")

    app = docker("superbot")
    if app is None or app.get("State", {}).get("Running") is not True:
        die("PUBLIC_WEB_CONTAINER_NOT_RUNNING")
    env = dict(e.split("=", 1) for e in app.get("Config", {}).get("Env", []) if "=" in e)
    if env.get("DESK_MODE") != "paper" or env.get("TRADING_MODE") != "paper":
        die("PUBLIC_NOT_PAPER")
    if not stat_file(Path("/opt/superbot/data/superbot.db")):
        die("AUTH_DB_MISSING")
    binds = app.get("HostConfig", {}).get("PortBindings", {}).get("8001/tcp") or []
    if len(binds) != 1 or binds[0].get("HostIp") != "127.0.0.1" or binds[0].get("HostPort") != "8002":
        die("PUBLIC_WEB_PORT_CHANGED")
    if NEW_OLDNAME in (x.get("Name", "").removeprefix("/") for x in []):
        die("OLD_WEB_NAME_EXISTS")
    if docker(NEW_OLDNAME) is not None:
        die("ROLLBACK_CONTAINER_NAME_OCCUPIED")
    if any((OLDWEB / name).exists() for name in FORBIDDEN_NEW_WEB_DIRS):
        die("ROLLBACK_FRONTEND_PATH_OCCUPIED")
    if not stat_file(OLDWEB / "build/index.html"):
        die("PRODUCTION_FRONTEND_MISSING")
    nginx = Path("/etc/nginx/sites-available/superbot")
    if not stat_file(nginx) or "/opt/superbot-web/build" not in nginx.read_text():
        die("PUBLIC_NGINX_UNEXPECTED_ROOT")
    if code("http://127.0.0.1:8002/api/health") != 200:
        die("PUBLIC_RC73_HEALTH_FAILED")
    good("PUBLIC_RC73_ROLLBACK_READY")

    if (code("http://127.0.0.1:18081/api/health") != 200
            or code("http://127.0.0.1:18081/") != 200
            or code("http://127.0.0.1:18081/api/v3/overview") != 401
            or code("http://127.0.0.1:18081/api/v3/brain/close", "POST") != 423):
        die("RC84_PREVIEW_API_GUARDS_FAILED")
    good("RC84_PREVIEW_HEALTH_AND_AUTH")

    free = shutil.disk_usage("/opt").free
    if free < 2_000_000_000:
        die("LOW_DISK_SPACE")
    good("DISK_AND_ROLLBACK_ROOM")
    print("RC84_CUTOVER_READONLY_PREFLIGHT=PASS", flush=True)
    print("RC84_CUTOVER_NO_TRADES_OR_PROVIDER_CALLS=True", flush=True)
    print("RC84_CUTOVER_NO_PRODUCTION_CHANGES=True", flush=True)


if __name__ == "__main__":
    main()
