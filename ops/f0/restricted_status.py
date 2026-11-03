#!/usr/bin/env python3
"""Fixed-command, unprivileged SuperBot F0 status probe.

Designed for root-owned installation at /usr/local/libexec/superbot-f0-status
and execution as the dedicated superbot-f0 account via SSH authorized_keys
forced-command. Never imports deploy code, executes remote requests, accesses
SQLite, Docker's privileged socket, API credentials or trading engines.

Output is a bounded JSON status (no log contents, paths or secrets).
This output is an inventory, NOT a stopped-services or backup certificate.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

SOURCE = Path("/opt/superbot-brain-free")
CLASSICS = Path("/opt/superbot-desk-data")
BACKUPS = Path("/opt/superbot-v3-backups")
NAMES = ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md")
PROCESS_MATCH = ("superbot", "brain-free", "deepseek", "rule-pool", "desk-hawk", "desk-bull")
CAPTURE_LIMIT = 32 * 1024


def metadata(path: Path) -> dict[str, object]:
    """Stat a known path, but never open/read it or follow a final symlink."""
    try:
        if path.is_symlink():
            return {"status": "UNSAFE_SYMLINK"}
        st = path.stat()
        if not path.is_file():
            return {"status": "NOT_REGULAR_FILE"}
        return {"status": "PRESENT", "bytes": st.st_size}
    except (FileNotFoundError, PermissionError, OSError):
        return {"status": "UNAVAILABLE"}


def directory(path: Path) -> str:
    try:
        return "PRESENT" if not path.is_symlink() and path.is_dir() else "UNAVAILABLE"
    except OSError:
        return "UNAVAILABLE"


def services() -> dict[str, object]:
    """Read service metadata, not process argument strings or environment."""
    try:
        p = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--state=running",
             "--no-pager", "--no-legend", "--plain"],
            text=True, capture_output=True, timeout=6, check=False,
        )
        if p.returncode or len(p.stdout) > CAPTURE_LIMIT:
            return {"status": "UNKNOWN"}
        matches = sum(
            any(marker in line.split()[0].lower() for marker in PROCESS_MATCH)
            for line in p.stdout.splitlines() if line.split()
        )
        return {"status": "POSSIBLE_ACTIVE" if matches else "NO_MATCHING_UNITS",
                "matching_count": matches}
    except (OSError, subprocess.SubprocessError):
        return {"status": "UNKNOWN"}


def processes() -> dict[str, object]:
    """Conservatively count process-name matches; don't print command lines."""
    try:
        p = subprocess.run(
            ["ps", "-eo", "pid=,args="], text=True, capture_output=True,
            timeout=6, check=False
        )
        if p.returncode or len(p.stdout) > 2 * 1024 * 1024:
            return {"status": "UNKNOWN"}
        matches = 0
        for line in p.stdout.splitlines():
            pid, sep, cmd = line.strip().partition(" ")
            if not sep or not pid.isdigit() or int(pid) == os.getpid():
                continue
            first = cmd.strip().split(" ", 1)[0].lower()
            # Do not count the script's own interpreter or generic shells;
            # DO NOT print cmd, which may include sensitive arguments.
            if any(marker in first for marker in PROCESS_MATCH):
                matches += 1
        return {"status": "POSSIBLE_ACTIVE" if matches else "NO_NAME_MATCH",
                "matching_count": matches}
    except (OSError, subprocess.SubprocessError):
        return {"status": "UNKNOWN"}


def collect() -> dict[str, object]:
    brain = {name: metadata(SOURCE / name) for name in
             ("brain.sqlite3", "brain.sqlite3-wal", "brain.sqlite3-shm")}
    classic = {}
    for port in ("hawk", "bull"):
        root = CLASSICS / port
        classic[port] = {
            "directory": directory(root),
            "archive_directory": directory(root / "archive"),
            "required": {name: metadata(root / name) for name in NAMES},
        }
    findings = {
        "schema": "superbot-v3-f0-restricted-status-v1",
        "operator": "superbot-f0",
        "read_only": True,
        "not_a_backup_certificate": True,
        "brain": brain,
        "classics": classic,
        "backup_root": directory(BACKUPS),
        "systemd": services(),
        "processes": processes(),
    }
    # Never claim that "no match" proves no active database handles.
    findings["status"] = "OBSERVATION_ONLY"
    return findings


def main() -> int:
    if os.geteuid() == 0:
        print('{"status":"REFUSED_ROOT_EXECUTION"}')
        return 3
    print(json.dumps(collect(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
