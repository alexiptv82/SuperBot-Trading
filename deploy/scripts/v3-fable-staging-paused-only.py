#!/usr/bin/env python3
"""Stage (do NOT deploy) a PINNED Fable SHADOW source revision on Singapore VPS.

Does not install/change systemd units, envfiles, token files, config, mandate,
run journals, public dashboard, exit owners or current code. Clones into a
private fresh path and validates Python syntax. No model calls of any kind.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PIN = os.environ.get("FABLE_STAGING_RELEASE_SHA", "")
REPO = "https://github.com/alexiptv82/SuperBot-Trading.git"
DEST = Path("/opt/superbot-v3-fable-shadow-staged-20261111")
ROOT = Path("/opt/superbot-v3-paper-runs")
RUNS = (
    ROOT / "classic-hawk-paper20261111",
    ROOT / "classic-bull-paper20261111",
    ROOT / "brain-v3-paper20261111",
)
SERVICES = (
    "superbot-v3-paper-falco.service",
    "superbot-v3-paper-toro.service",
    "superbot-v3-paper-brain-runner.service",
    "superbot-v3-paper-brain-exit.service",
)


def checked(*args: str, timeout: int = 120) -> str:
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, timeout=timeout, check=False)
    if p.returncode:
        raise RuntimeError("COMMAND_FAILED")
    return p.stdout.strip()


def guard_paused() -> tuple[str, ...]:
    if os.geteuid() != 0:
        raise RuntimeError("ROOT_REQUIRED")
    for p in RUNS:
        if not p.is_dir() or p.is_symlink() or not (p / "pause.flag").is_file():
            raise RuntimeError("RUN_PAUSE_MISSING")
        marker = json.loads((p / "PREPARED_PAUSED_ONLY.json").read_text())
        if marker.get("paper_only") is not True or marker.get("paused") is not True:
            raise RuntimeError("PAPER_MARKER_INVALID")
    mandate = json.loads((RUNS[2] / "mandate.json").read_text())
    if mandate.get("approved") is not False:
        raise RuntimeError("BRAIN_MANDATE_NOT_PAUSED")
    pids = []
    for name in SERVICES:
        checked("systemctl", "is-active", "--quiet", name)
        pids.append(checked("systemctl", "show", "-p", "MainPID", "--value", name))
    return tuple(pids)


def syntax_only(dest: Path) -> None:
    for filename in (
        "backend/v3/runner/fable_shadow.py",
        "backend/v3/runner/wiring.py",
        "backend/tests/test_v3_fable_shadow_budget.py",
    ):
        target = dest / filename
        if target.is_symlink() or not target.is_file():
            raise RuntimeError("STAGING_SOURCE_MISSING")
        ast.parse(target.read_text(encoding="utf-8"), filename=filename)


def main() -> None:
    if len(PIN) != 40 or any(s not in "0123456789abcdef" for s in PIN):
        raise RuntimeError("RELEASE_PIN_NOT_SET")
    before = guard_paused()
    print("FABLE_PAPER_PAUSE_PREFLIGHT=PASS", flush=True)
    if DEST.exists() or DEST.is_symlink():
        if DEST.is_symlink() or not DEST.is_dir():
            raise RuntimeError("STAGING_PATH_INVALID")
        if checked("git", "-C", str(DEST), "rev-parse", "HEAD") != PIN:
            raise RuntimeError("STAGED_SOURCE_PIN_MISMATCH")
        syntax_only(DEST)
        print("FABLE_STAGING_ALREADY_PINNED=True", flush=True)
    else:
        temp = Path(tempfile.mkdtemp(dir="/opt", prefix=".v3-fable-src-"))
        try:
            # This is ONLY a source clone; do not invoke setup.py, pip, Docker,
            # systemd, trading scripts, GitHub Actions or a model client.
            checked("git", "-c", "core.hooksPath=/dev/null", "clone", "-q",
                    "--no-checkout", REPO, str(temp), timeout=170)
            checked("git", "-C", str(temp), "-c", "core.hooksPath=/dev/null",
                    "checkout", "-q", "--detach", PIN, timeout=100)
            if checked("git", "-C", str(temp), "rev-parse", "HEAD") != PIN:
                raise RuntimeError("STAGED_COMMIT_MISMATCH")
            syntax_only(temp)
            temp.chmod(0o700)
            os.rename(temp, DEST)
            print("FABLE_SOURCE_STAGED_ISOLATED=PASS", flush=True)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
    after = guard_paused()
    if before != after:
        raise RuntimeError("PAUSED_SERVICES_CHANGED_DURING_STAGING")
    print("FABLE_STAGED_SOURCE_SHA=" + PIN[:12], flush=True)
    print("FABLE_ALL_FOUR_SERVICE_PIDS_UNCHANGED=True", flush=True)
    print("FABLE_NO_SERVICE_RESTART_NO_PROVIDER_CALLS=True", flush=True)
    print("FABLE_NO_MANDATE_APPROVAL_NO_UNPAUSE=True", flush=True)
    print("FABLE_PAUSED_STAGING_SUCCESS=PASS", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # No raw Git/stderr or secret-related details in CI logs.
        print("FABLE_STAGING_REFUSED=" + (
            str(exc) if type(exc) is RuntimeError else "PRECONDITION_FAILED"
        ), flush=True)
        sys.exit(2)
