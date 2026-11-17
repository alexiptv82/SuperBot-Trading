#!/usr/bin/env python3
"""Retire Falco/Toro PAPER only after checking real processes and backing up data.

Strictly scoped to the two classic desk loops and classic exit-only units.
Does NOT touch the historical Brain, Arena, Docker, trading keys, or strategies.
No remote calls. No deletion or state reset. Run explicitly with --retire.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone

CLASSICS = (("falco", "hawk"), ("toro", "bull"))
DATA_ROOT = Path("/opt/superbot-desk-data")
BACKUP_ROOT = Path("/opt/superbot-v3-backups")
BRAIN_UNITS = ("superbot-v3-paper-brain-runner.service",
               "superbot-v3-paper-brain-exit.service")
RUNNER_UNITS = tuple("superbot-v3-paper-" + n + ".service" for n, _ in CLASSICS)
EXIT_UNITS = ("superbot-v3-falco-exit.service",
              "superbot-v3-toro-exit.service")


def refuse(reason: str) -> None:
    print("CLASSIC_RETIRE_REFUSED=" + reason, flush=True)
    raise SystemExit(2)


def ctl(*args: str, check: bool = True) -> str:
    p = subprocess.run(["/usr/bin/systemctl", *args],
                       capture_output=True, text=True, check=False)
    if check and p.returncode:
        refuse("SYSTEMCTL_FAILED_" + args[0].upper())
    return p.stdout.strip()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def real_process_env(pid: int) -> dict[str, str]:
    raw = Path("/proc") / str(pid) / "environ"
    items = raw.read_bytes().split(b"\0")
    result = {}
    for item in items:
        if b"=" in item:
            key, value = item.split(b"=", 1)
            if key in (b"DESK_DATA_DIR", b"DESK_MODE"):
                result[key.decode("ascii")] = value.decode("utf-8")
    return result


def check_classic(name: str, portfolio: str) -> dict:
    unit = "superbot-v3-paper-" + name + ".service"
    if ctl("is-active", unit, check=False) != "active":
        refuse(name.upper() + "_RUNNER_NOT_ACTIVE_FOR_AUDIT")
    pid_text = ctl("show", unit, "--property=MainPID", "--value")
    if not pid_text.isdecimal() or int(pid_text) <= 1:
        refuse(name.upper() + "_PID_MISSING")
    pid = int(pid_text)
    argv = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\0")
    if not (b"desk.cli" in argv and b"loop" in argv
            and (b"--portfolio=" + portfolio.encode() in argv
                 or (b"--portfolio" in argv and portfolio.encode() in argv))):
        refuse(name.upper() + "_PROCESS_NOT_EXPECTED_DESK_LOOP")
    env = real_process_env(pid)
    expected = DATA_ROOT / portfolio
    if env.get("DESK_DATA_DIR") != str(expected) or env.get("DESK_MODE") != "paper":
        refuse(name.upper() + "_DATA_PATH_OR_PAPER_MODE_UNVERIFIED")
    if DATA_ROOT.is_symlink() or expected.is_symlink() or not expected.is_dir():
        refuse(name.upper() + "_DATA_DIRECTORY_UNSAFE")
    if not (expected / "pause.flag").is_file():
        refuse(name.upper() + "_NOT_PAUSED")
    state_file = expected / "state_v2.json"
    if state_file.is_symlink() or not state_file.is_file():
        refuse(name.upper() + "_STATE_MISSING_OR_SYMLINK")
    state = json.loads(state_file.read_text(encoding="utf-8"))
    main = state.get("main")
    positions = main.get("positions") if isinstance(main, dict) else None
    if not isinstance(positions, dict):
        refuse(name.upper() + "_POSITIONS_NOT_VERIFIABLE")
    if positions:
        refuse(name.upper() + "_HAS_OPEN_POSITIONS")
    return {"name": name, "portfolio": portfolio, "unit": unit,
            "pid": pid, "directory": expected,
            "state_sha256": digest(state_file), "open_positions": 0}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "--retire":
        refuse("EXPLICIT_FLAG_REQUIRED")
    if os.geteuid() != 0 or not Path("/usr/bin/systemctl").is_file():
        refuse("ROOT_AND_SYSTEMD_REQUIRED")
    if BACKUP_ROOT.is_symlink() or not BACKUP_ROOT.is_dir():
        refuse("BACKUP_ROOT_MISSING_OR_UNSAFE")
    for brain_unit in BRAIN_UNITS:
        if ctl("is-active", brain_unit, check=False) != "active":
            refuse("BRAIN_NOT_ACTIVE_ABORT")
    # Do not assume no other legacy Docker bot is running.
    docker = shutil.which("docker")
    if docker:
        ps = subprocess.run([docker, "ps", "--format", "{{.Names}}"],
                            capture_output=True, text=True, check=False)
        if ps.returncode != 0:
            refuse("DOCKER_INVENTORY_FAILED")
        names = set(ps.stdout.splitlines())
        if names.intersection({"superbot-desk-hawk", "superbot-desk-bull"}):
            refuse("OTHER_CLASSIC_DOCKER_RUNNING")

    details = [check_classic(name, portfolio) for name, portfolio in CLASSICS]
    print("CLASSIC_RETIRE_PRECHECK=PASS", flush=True)
    for d in details:
        print("CLASSIC_" + d["name"].upper() + "_OPEN_POSITIONS=0", flush=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = BACKUP_ROOT / ("classic-retire-" + timestamp)
    archive.mkdir(mode=0o700, exist_ok=False)
    os.chmod(archive, 0o700)
    (archive / "prestop").mkdir(mode=0o700)

    records = []
    for d in details:
        src = d["directory"]
        dst = archive / "prestop" / d["portfolio"]
        dst.mkdir(mode=0o700)
        hashes = {}
        for basename in ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl",
                         "lessons.md", "errors.md", "pause.flag", "trading_enabled.json"):
            source = src / basename
            if source.is_symlink():
                refuse("UNSAFE_SYMLINK_" + d["name"].upper())
            if not source.is_file():
                continue
            before = digest(source)
            target = dst / basename
            shutil.copy2(source, target)
            os.chmod(target, 0o600)
            if digest(source) != before or digest(target) != before:
                refuse("FILE_CHANGED_WHILE_BACKING_UP_" + d["name"].upper())
            hashes[basename] = before
        if "state_v2.json" not in hashes:
            refuse("CRITICAL_STATE_BACKUP_MISSING")
        (archive / (d["name"] + "-unit.txt")).write_text(
            ctl("cat", d["unit"]), encoding="utf-8")
        records.append({"portfolio": d["portfolio"], "prestop_sha256": hashes})
    # Re-validate pause, open positions, process PID and state after copying.
    updated = [check_classic(name, portfolio) for name, portfolio in CLASSICS]
    if [(d["pid"], d["state_sha256"]) for d in details] != [
            (d["pid"], d["state_sha256"]) for d in updated]:
        refuse("PROCESS_OR_STATE_CHANGED_BEFORE_STOP")

    (archive / "prestop-verification.json").write_text(
        json.dumps(records, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("CLASSIC_RETIRE_PRESTOP_BACKUP=VERIFIED", flush=True)
    print("CLASSIC_RETIRE_BACKUP_DIRECTORY=" + str(archive), flush=True)
    sys.stdout.flush()

    # User authorized retiring only these four exact classic services.
    ctl("disable", "--now", *RUNNER_UNITS, *EXIT_UNITS)
    for unit in RUNNER_UNITS + EXIT_UNITS:
        if ctl("is-active", unit, check=False) == "active":
            refuse("CLASSIC_SERVICE_STILL_ACTIVE")
    print("CLASSIC_RETIRE_CLASSIC_SERVICES=STOPPED_DISABLED", flush=True)

    # Full, post-stop snapshot of the unchanged classic directories.
    output = archive / "classic-data-full.tar.gz"
    with tarfile.open(output, "w:gz", dereference=False) as tar:
        for _, portfolio in CLASSICS:
            tar.add(DATA_ROOT / portfolio, arcname=portfolio, recursive=True)
    with tarfile.open(output, "r:gz") as tar:
        files = set(tar.getnames())
        if not {"hawk/state_v2.json", "bull/state_v2.json"} <= files:
            refuse("FULL_ARCHIVE_MISSING_STATE")
        if not tar.getmembers():
            refuse("FULL_ARCHIVE_EMPTY")

    for brain_unit in BRAIN_UNITS:
        if ctl("is-active", brain_unit, check=False) != "active":
            refuse("BRAIN_STATE_CHANGED_ALERT")
    print("CLASSIC_RETIRE_ARCHIVE_SHA256=" + digest(output), flush=True)
    print("CLASSIC_RETIRE_BRAIN_UNCHANGED=ACTIVE", flush=True)
    print("CLASSIC_RETIRE_RESULT=SUCCESS_NO_DATA_DELETED", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print("CLASSIC_RETIRE_ERROR_TYPE=" + type(exc).__name__, flush=True)
        sys.exit(2)
