#!/usr/bin/env python3
"""RC84: read-only prerequisites and versioned source staging ONLY.

--check: NEVER writes.
--stage-source: creates one NEW source directory; no systemd edits, no restarts,
no wallet, snapshot, control flag, nginx, cloud, API, order or LIVE access.
Refuses any unexpected service state or backup identity.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

OLD = "0e29a73a36f668643da4088178bacb8616a45ac0"
NEW = "ab7e0b7d991b8f4bd714fccfec23b09a936e6717"
OLD_STAGE = Path("/opt/superbot-v3-rc84-stage")
NEW_STAGE = Path("/opt/superbot-v3-rc84-repair-ab7e0b7")
PAPER = Path("/opt/superbot-v3-paper-runs")
BACKUP = Path("/opt/superbot-backups/rc84-current-paper-before-fix-20261112T092631Z-15704")
MANIFEST_SHA = "a18aff67032605045dd3ef3888f5d225fdd8930b49d89d780aa676aca8f6c8fa"
REPO = "https://github.com/alexiptv82/SuperBot-Trading.git"
RUNS = (
    ("falco", "classic-hawk-paper20261111", "superbot-v3-paper-falco.service", "hawk"),
    ("toro", "classic-bull-paper20261111", "superbot-v3-paper-toro.service", "bull"),
    ("brain", "brain-v3-paper20261111", "superbot-v3-paper-brain-runner.service", "brain"),
)
EXIT = "superbot-v3-paper-brain-exit.service"


def refuse(reason: str) -> None:
    raise RuntimeError(reason)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fd:
        for chunk in iter(lambda: fd.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(args: list[str], timeout: int = 15) -> str:
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        refuse("command_failed_" + Path(args[0]).name)
    return p.stdout.strip()


def is_safe_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink()


def check_services() -> None:
    for unit in [*(item[2] for item in RUNS), EXIT]:
        state = subprocess.run(["systemctl", "is-active", unit],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        # No partial cutover if a worker, even EXIT-only, can still write data.
        if state != "inactive":
            refuse("service_not_stopped_" + unit.replace(".", "_"))
        workdir = run(["systemctl", "show", unit, "--property=WorkingDirectory", "--value"])
        if workdir != str(OLD_STAGE):
            refuse("unit_workdir_mismatch_" + unit.replace(".", "_"))
    print("RC84_STAGE_FOUR_SERVICES_INACTIVE=PASS", flush=True)


def check_snapshot() -> None:
    if not is_safe_dir(BACKUP) or not is_safe_dir(BACKUP / "snapshot"):
        refuse("certified_backup_path_missing")
    mf = BACKUP / "MANIFEST.json"
    if not mf.is_file() or mf.is_symlink() or sha256(mf) != MANIFEST_SHA:
        refuse("certified_manifest_sha_mismatch")
    data = json.loads(mf.read_text(encoding="utf-8"))
    if (data.get("schema") != "rc84-private-paper-three-wallet-snapshot-v1"
            or data.get("source_sha") != OLD
            or data.get("all_four_paper_services_stopped") is not True
            or data.get("all_three_pause_flags_present") is not True
            or set(data.get("wallets", {})) != {"falco", "toro", "brain"}
            or data["wallets"]["falco"].get("open_count") != 7
            or data["wallets"]["toro"].get("open_count") != 3):
        refuse("backup_manifest_identity_invalid")
    # Inspect the snapshot bytes, not the live wallet contents. Every filename
    # and SHA must still match the frozen inventory. No symlinks are permitted.
    checked = 0
    for label, dirname, _, _ in RUNS:
        block = data["wallets"][label]
        if block.get("dirname") != dirname:
            refuse("backup_wallet_identity_invalid")
        base = BACKUP / "snapshot" / dirname
        if not is_safe_dir(base):
            refuse("backup_wallet_folder_invalid")
        inventory = block.get("files")
        if not isinstance(inventory, dict):
            refuse("backup_inventory_invalid")
        found: set[str] = set()
        for root, folders, files in os.walk(base, followlinks=False):
            for folder in folders:
                p = Path(root) / folder
                if p.is_symlink() or not p.is_dir():
                    refuse("backup_subfolder_invalid")
            for name in files:
                file = Path(root) / name
                rel = file.relative_to(base).as_posix()
                if file.is_symlink() or not file.is_file() or rel not in inventory:
                    refuse("backup_file_unknown")
                expected = inventory[rel]
                if (file.stat().st_size != expected.get("size")
                        or sha256(file) != expected.get("sha256")):
                    refuse("backup_file_hash_mismatch")
                found.add(rel)
        if found != set(inventory):
            refuse("backup_inventory_incomplete")
        checked += len(found)
    print("RC84_STAGE_CERTIFIED_MANIFEST_SHA256=" + MANIFEST_SHA, flush=True)
    print("RC84_STAGE_BACKUP_FILES_REVERIFIED=" + str(checked), flush=True)
    print("RC84_STAGE_SNAPSHOT_FALCO_OPEN=7", flush=True)
    print("RC84_STAGE_SNAPSHOT_TORO_OPEN=3", flush=True)


def check_identity() -> None:
    if not is_safe_dir(OLD_STAGE) or run(
        ["git", "-C", str(OLD_STAGE), "rev-parse", "HEAD"]
    ) != OLD:
        refuse("old_source_not_pinned")
    # Previously running unit may have locally modified files; refuse rather
    # than assume that the git commit alone represents actual runtime code.
    dirty = run(["git", "-C", str(OLD_STAGE), "status", "--porcelain",
                 "--untracked-files=no"])
    if dirty:
        refuse("old_source_worktree_modified")
    if not is_safe_dir(PAPER):
        refuse("paper_parent_invalid")
    for label, dirname, _, ident in RUNS:
        root = PAPER / dirname
        if not is_safe_dir(root):
            refuse("paper_run_dir_invalid_" + label)
        flag = root / "pause.flag"
        if not flag.is_file() or flag.is_symlink():
            refuse("paper_pause_missing_" + label)
        marker = root / "PREPARED_PAUSED_ONLY.json"
        if not marker.is_file() or marker.is_symlink():
            refuse("paper_marker_missing_" + label)
        data = json.loads(marker.read_text(encoding="utf-8"))
        if data.get("paper_only") is not True:
            refuse("not_a_paper_wallet_" + label)
        if ident != "brain" and data.get("portfolio_id") != ident:
            refuse("classic_identity_mismatch_" + label)
        if ident == "brain":
            mandate = json.loads((root / "mandate.json").read_text(encoding="utf-8"))
            if mandate.get("run_id") != dirname or mandate.get("approved") is not True:
                refuse("brain_mandate_not_approved")
    print("RC84_STAGE_PAPER_IDENTITIES_PAUSES=PASS", flush=True)


def stage_source() -> None:
    if NEW_STAGE.exists() or NEW_STAGE.is_symlink():
        if not is_safe_dir(NEW_STAGE):
            refuse("target_stage_unsafe")
        pinned = run(["git", "-C", str(NEW_STAGE), "rev-parse", "HEAD"])
        if pinned != NEW or run(["git", "-C", str(NEW_STAGE), "status",
                                "--porcelain", "--untracked-files=all"]):
            refuse("existing_new_stage_not_exactly_pinned_clean")
        print("RC84_STAGE_ALREADY_PINNED=" + NEW, flush=True)
        return
    # The ONLY writes are in this new, independent directory.
    subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "clone",
                    "--quiet", "--no-checkout", REPO, str(NEW_STAGE)],
                   timeout=150, check=True)
    NEW_STAGE.chmod(0o700)
    run(["git", "-C", str(NEW_STAGE), "-c", "core.hooksPath=/dev/null",
         "checkout", "--quiet", "--detach", NEW], timeout=120)
    if (run(["git", "-C", str(NEW_STAGE), "rev-parse", "HEAD"]) != NEW or
            run(["git", "-C", str(NEW_STAGE), "status",
                 "--porcelain", "--untracked-files=all"])):
        refuse("new_checkout_mismatch")
    for name in ("backend/desk/cli.py", "backend/desk/long_s25.py",
                 "backend/v3/lab_tools/fetch_candles.py",
                 "backend/v3/runner/contracts.py", "backend/v3/runner/runner.py"):
        if not (NEW_STAGE / name).is_file():
            refuse("required_patched_source_missing")
    print("RC84_STAGE_NEW_PIN=" + NEW, flush=True)
    print("RC84_STAGE_NEW_SOURCE_READY=PASS", flush=True)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("--check", "--stage-source"):
        print("USAGE: script.py --check | --stage-source")
        return 2
    os.umask(0o077)
    try:
        if os.geteuid() != 0:
            refuse("root_required")
        check_services()
        check_identity()
        check_snapshot()
        if sys.argv[1] == "--check":
            print("RC84_STAGE_PREFLIGHT_READ_ONLY=PASS", flush=True)
        else:
            stage_source()
            print("RC84_STAGE_NO_SERVICE_OR_PAPER_WALLET_CHANGES=PASS", flush=True)
        return 0
    except (RuntimeError, OSError, subprocess.SubprocessError,
            ValueError, KeyError, TypeError) as e:
        # Intentionally do not print paths/secret values.
        print("RC84_STAGE_REFUSED=" + (str(e) if isinstance(e, RuntimeError)
                                       else type(e).__name__), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
