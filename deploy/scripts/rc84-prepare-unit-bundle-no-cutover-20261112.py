#!/usr/bin/env python3
"""RC84 PAPER: package candidate + rollback systemd units, NEVER install/start them.

--check: read-only validation, no output files.
--prepare: write a NEW versioned bundle only under /opt; systemd and
wallet data are NEVER modified. Requires the pinned PR#88 preflight PASS.
Fail closed on any modified unit, new/unknown process, pending close/reset
flag, or insufficient confirmation of the 3 wallet pauses.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

CHECKER = Path("/root/rc84-paper-cutover-preflight.py")
CHECKER_GIT_SHA = "da54f677ca0d50255bad9a03a9c5ff8f6898a972"
OLD = "/opt/superbot-v3-rc84-stage"
NEW = "/opt/superbot-v3-rc84-repair-ab7e0b7"
NEW_PIN = "ab7e0b7d991b8f4bd714fccfec23b09a936e6717"
BUNDLE = Path("/opt/superbot-v3-rc84-unit-bundle-ab7e0b7")
UNIT_DIR = Path("/etc/systemd/system")
WALLET_ROOT = Path("/opt/superbot-v3-paper-runs")
UNITS = (
    "superbot-v3-paper-falco.service",
    "superbot-v3-paper-toro.service",
    "superbot-v3-paper-brain-exit.service",
    "superbot-v3-paper-brain-runner.service",
)
WALLET_DIRS = (
    "classic-hawk-paper20261111",
    "classic-bull-paper20261111",
    "brain-v3-paper20261111",
)
PENDING_COMMANDS = (
    ("classic-hawk-paper20261111", ("close_position.flag", "close_position.flag.work",
                                    "reset.flag", "reset_portfolio.flag")),
    ("classic-bull-paper20261111", ("close_position.flag", "close_position.flag.work",
                                    "reset.flag", "reset_portfolio.flag")),
    ("brain-v3-paper20261111", ("close_request.json", "close_request.work",
                                "reset.flag", "reset_portfolio.flag")),
)

def refuse(reason: str) -> None:
    raise RuntimeError(reason)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + bytes([0]) + data).hexdigest()

def regular_file(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        refuse("missing_or_linked_" + path.name)
    return path.read_bytes()

def candidate_unit(data: bytes, unit: str) -> bytes:
    # No change to any service property except the OLD -> NEW source path.
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        refuse("invalid_unit_encoding_" + unit)
    if text.count(OLD) != 2 or NEW in text:
        refuse("unexpected_path_layout_" + unit)
    revised = text.replace(OLD, NEW)
    if (revised.count(NEW) != 2 or OLD in revised
            or "WorkingDirectory=" + NEW not in revised
            or "PYTHONPATH=" + NEW not in revised
            or "DESK_MODE=paper" not in revised):
        refuse("candidate_integrity_" + unit)
    if revised.replace(NEW, OLD) != text:
        refuse("candidate_not_reversible_" + unit)
    return revised.encode("utf-8")

def safety_gate() -> None:
    if git_blob(regular_file(CHECKER)) != CHECKER_GIT_SHA:
        refuse("gate_script_sha_mismatch")
    result = subprocess.run([sys.executable, "-I", str(CHECKER), "--check"],
                            capture_output=True, text=True, timeout=120)
    if (result.returncode != 0
            or "RC84_CUTOVER_PREFLIGHT_READ_ONLY=PASS" not in result.stdout
            or "RC84_CUTOVER_AUTHORIZED_CLOSE_BRIDGE_ONLY=PASS" not in result.stdout
            or "RC84_CUTOVER_NO_OTHER_DOCKER_WALLET_RW=PASS" not in result.stdout):
        refuse("precutover_gate_not_passed")
    print("RC84_BUNDLE_FULL_PREFLIGHT=PASS", flush=True)

def pending_gate() -> None:
    for wallet, names in PENDING_COMMANDS:
        parent = WALLET_ROOT / wallet
        if not parent.is_dir() or parent.is_symlink():
            refuse("wallet_invalid_" + wallet)
        if not (parent / "pause.flag").is_file():
            refuse("wallet_not_paused_" + wallet)
        for name in names:
            candidate = parent / name
            if candidate.exists() or candidate.is_symlink():
                refuse("pending_paper_command_" + wallet + "_" + name)
    print("RC84_BUNDLE_NO_PENDING_CLOSE_OR_RESET=PASS", flush=True)

def make_plan() -> dict[str, tuple[bytes, bytes]]:
    planned = {}
    for unit in UNITS:
        original = regular_file(UNIT_DIR / unit)
        model = regular_file(Path(NEW) / "deploy/rc84-paper-services" / unit)
        if original != model:
            refuse("unit_mismatch_at_bundle_" + unit)
        revised = candidate_unit(original, unit)
        planned[unit] = original, revised
    print("RC84_BUNDLE_FOUR_CANDIDATE_AND_ROLLBACK_UNITS=PASS", flush=True)
    return planned

def validate_bundle(plan: dict[str, tuple[bytes, bytes]]) -> bool:
    if not BUNDLE.is_dir() or BUNDLE.is_symlink():
        return False
    try:
        manifest = json.loads(regular_file(BUNDLE / "MANIFEST.json"))
        expected_manifest = manifest_for(plan)
        if manifest != expected_manifest:
            return False
        for unit, (old_data, new_data) in plan.items():
            if regular_file(BUNDLE / "rollback" / unit) != old_data:
                return False
            if regular_file(BUNDLE / "candidate" / unit) != new_data:
                return False
    except (OSError, ValueError, RuntimeError):
        return False
    return True

def manifest_for(plan: dict[str, tuple[bytes, bytes]]) -> dict:
    return {
        "schema": "rc84-paper-unit-bundle-prepared-only-v1",
        "old_path": OLD,
        "new_path": NEW,
        "new_pin": NEW_PIN,
        "backup_manifest_sha256":
            "a18aff67032605045dd3ef3888f5d225fdd8930b49d89d780aa676aca8f6c8fa",
        "no_systemd_changes": True,
        "paper_only": True,
        "pause_flags_kept": True,
        "units": {unit: {"old_sha256": sha(pair[0]),
                          "candidate_sha256": sha(pair[1])}
                  for unit, pair in plan.items()},
    }

def store_bundle(plan: dict[str, tuple[bytes, bytes]]) -> None:
    if BUNDLE.exists() or BUNDLE.is_symlink():
        if not validate_bundle(plan):
            refuse("bundle_existing_not_exactly_verified")
        print("RC84_BUNDLE_ALREADY_PREPARED_AND_VERIFIED=PASS", flush=True)
        return
    tmp = BUNDLE.with_name("." + BUNDLE.name + ".creating-" + str(os.getpid()))
    if tmp.exists() or tmp.is_symlink():
        refuse("bundle_temp_already_exists")
    tmp.mkdir(mode=0o700)
    try:
        for folder in ("candidate", "rollback"):
            (tmp / folder).mkdir(mode=0o700)
        for unit, (old_data, new_data) in plan.items():
            for folder, data in (("rollback", old_data), ("candidate", new_data)):
                p = tmp / folder / unit
                with p.open("xb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                p.chmod(0o600)
        manifest_bytes = (json.dumps(manifest_for(plan), indent=2, sort_keys=True) +
                          "\n").encode("utf-8")
        mf = tmp / "MANIFEST.json"
        with mf.open("xb") as f:
            f.write(manifest_bytes)
            f.flush()
            os.fsync(f.fileno())
        mf.chmod(0o600)
        if BUNDLE.exists() or BUNDLE.is_symlink():
            refuse("bundle_concurrent_creation")
        tmp.rename(BUNDLE)
    finally:
        if tmp.is_dir() and not tmp.is_symlink():
            shutil.rmtree(tmp)
    if not validate_bundle(plan):
        refuse("bundle_verification_failed")
    print("RC84_BUNDLE_PREPARED_AND_VERIFIED=PASS", flush=True)
    print("RC84_BUNDLE_PATH=" + str(BUNDLE), flush=True)

def main() -> int:
    if sys.argv[1:] not in (["--check"], ["--prepare"]):
        print("USAGE: script.py --check | --prepare")
        return 2
    try:
        os.umask(0o077)
        if os.geteuid() != 0:
            refuse("root_required")
        safety_gate()
        pending_gate()
        plan = make_plan()
        if sys.argv[1] == "--check":
            print("RC84_BUNDLE_READ_ONLY_CHECK=PASS", flush=True)
        else:
            store_bundle(plan)
            print("RC84_BUNDLE_NO_SYSTEMD_CHANGES=PASS", flush=True)
            print("RC84_BUNDLE_NO_WALLET_CHANGES=PASS", flush=True)
        print("RC84_BUNDLE_NO_DEPLOY_OR_RESTART=True", flush=True)
        return 0
    except (RuntimeError, OSError, ValueError, TypeError,
            subprocess.SubprocessError) as e:
        print("RC84_BUNDLE_REFUSED=" + (
            str(e) if isinstance(e, RuntimeError) else type(e).__name__),
            flush=True)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
