#!/usr/bin/env python3
"""RC84: READ-ONLY audit before any PAPER unit cutover.

Does NOT stop/start/reload/enable systemd, alter flags, DBs, snapshots,
manifests, git branches, service files, credentials, or trading settings.
Inspect unit files without printing their potentially sensitive contents.
FAIL CLOSED on any unexpected identity, writer, stage, or backup.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys

OLD = Path("/opt/superbot-v3-rc84-stage")
NEW = Path("/opt/superbot-v3-rc84-repair-ab7e0b7")
SOURCE_UNITS = Path("/opt/superbot-v3-rc84-services-staged-v2")
SYSTEMD = Path("/etc/systemd/system")
OLD_PIN = "0e29a73a36f668643da4088178bacb8616a45ac0"
NEW_PIN = "ab7e0b7d991b8f4bd714fccfec23b09a936e6717"
CHECKER = Path("/root/rc84-stage-tested.py")
CHECKER_GIT_BLOB = "302f27c8e36b5aaea90aa6c6db215fcd59617bfe"
RUNS = Path("/opt/superbot-v3-paper-runs")
WALLETS = ("classic-hawk-paper20261111", "classic-bull-paper20261111",
           "brain-v3-paper20261111")
UNITS = (
    "superbot-v3-paper-falco.service",
    "superbot-v3-paper-toro.service",
    "superbot-v3-paper-brain-exit.service",
    "superbot-v3-paper-brain-runner.service",
)

def refuse(reason: str) -> None:
    raise RuntimeError(reason)

def command(args: list[str], timeout: int = 20) -> str:
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        refuse("command_failed_" + Path(args[0]).name)
    return p.stdout.strip()

def safe_file(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        refuse("missing_or_linked_file_" + path.name)
    return path.read_bytes()

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + bytes([0]) + data).hexdigest()

def inspect_backups_and_sources() -> None:
    if git_blob(safe_file(CHECKER)) != CHECKER_GIT_BLOB:
        refuse("checkpoint_checker_not_pinned")
    p = subprocess.run([sys.executable, "-I", str(CHECKER), "--check"],
                       capture_output=True, text=True, timeout=90)
    if p.returncode != 0 or "RC84_STAGE_PREFLIGHT_READ_ONLY=PASS" not in p.stdout:
        refuse("snapshot_or_wallet_checks_not_passed")
    for path, pin in ((OLD, OLD_PIN), (NEW, NEW_PIN)):
        if not path.is_dir() or path.is_symlink():
            refuse("source_directory_invalid_" + path.name)
        if command(["git", "-C", str(path), "rev-parse", "HEAD"]) != pin:
            refuse("source_git_pin_invalid_" + path.name)
        # OLD may contain innocuous untracked runtime files; tracked files
        # must be clean. NEW must be pristine including untracked paths.
        untracked = "no" if path == OLD else "all"
        if command(["git", "-C", str(path), "status", "--porcelain",
                    "--untracked-files=" + untracked]):
            refuse("source_dirty_" + path.name)
    print("RC84_CUTOVER_BACKUP_AND_SOURCES=PASS", flush=True)

def prop(unit: str, name: str) -> str:
    return command(["systemctl", "show", unit, "--property=" + name, "--value"])

def inspect_four_unit_templates() -> None:
    for unit in UNITS:
        if prop(unit, "ActiveState") != "inactive":
            refuse("unit_not_inactive_" + unit)
        if prop(unit, "WorkingDirectory") != str(OLD):
            refuse("unit_wrong_workdir_" + unit)
        if prop(unit, "FragmentPath") != str(SYSTEMD / unit):
            refuse("unit_wrong_fragment_" + unit)
        if prop(unit, "DropInPaths"):
            refuse("unit_has_override_" + unit)
        if prop(unit, "NeedDaemonReload") != "no":
            refuse("unit_has_unloaded_changes_" + unit)
        if prop(unit, "UnitFileState") not in ("disabled", "static"):
            refuse("unit_unexpected_enable_state_" + unit)
        installed = safe_file(SYSTEMD / unit)
        staged = safe_file(SOURCE_UNITS / unit)
        source_template = safe_file(OLD / "deploy" / "rc84-paper-services" / unit)
        if installed != staged or staged != source_template:
            refuse("unit_not_exact_old_template_" + unit)
        original = installed.decode("utf-8")
        if original.count(str(OLD)) != 2 or str(NEW) in original:
            refuse("unit_source_path_not_expected_" + unit)
        planned = original.replace(str(OLD), str(NEW))
        if planned.count(str(NEW)) != 2 or str(OLD) in planned:
            refuse("unit_candidate_substitution_invalid_" + unit)
        if "DESK_MODE=paper" not in planned:
            refuse("unit_missing_explicit_paper_" + unit)
    print("RC84_CUTOVER_FOUR_EXACT_UNIT_TEMPLATES=PASS", flush=True)
    print("RC84_CUTOVER_UNIT_PATH_SWAP_PLAN=PASS", flush=True)

def inspect_running_wallet_owners() -> None:
    # Catch extra processes with explicit wallet paths in their argv without
    # exposing argv, account identifiers, credential values, or env contents.
    needles = [str(RUNS / w).encode() for w in WALLETS]
    seen = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = (entry / "cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if any(needle in argv for needle in needles):
            seen.append(entry.name)
    if seen:
        refuse("possible_competing_paper_wallet_process_count_" + str(len(seen)))
    print("RC84_CUTOVER_NO_ARGV_WRITERS_TO_THREE_RUNS=PASS", flush=True)
    # This is additional evidence, NOT proof there are no env-only writers.
    for unit in ("superbot-v3-falco-exit.service",
                 "superbot-v3-toro-exit.service",
                 "superbot-v3-brain-exit.service"):
        state = subprocess.run(["systemctl", "is-active", unit],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        if state not in ("active", "inactive", "failed", "unknown"):
            refuse("unreadable_legacy_exit_state_" + unit)
        print("RC84_CUTOVER_LEGACY_" + unit.removesuffix(".service") +
              "=" + state.upper(), flush=True)

def main() -> int:
    if sys.argv[1:] != ["--check"]:
        print("USAGE: script.py --check")
        return 2
    try:
        if os.geteuid() != 0:
            refuse("root_required")
        inspect_backups_and_sources()
        inspect_four_unit_templates()
        inspect_running_wallet_owners()
        print("RC84_CUTOVER_PREFLIGHT_READ_ONLY=PASS", flush=True)
        print("RC84_CUTOVER_NO_SERVICES_OR_DATA_MODIFIED=PASS", flush=True)
        print("RC84_CUTOVER_ACTIVATION_NOT_AUTHORIZED=True", flush=True)
        return 0
    except (RuntimeError, OSError, ValueError, UnicodeError,
            subprocess.SubprocessError) as exc:
        print("RC84_CUTOVER_REFUSED=" +
              (str(exc) if isinstance(exc, RuntimeError)
               else type(exc).__name__), flush=True)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
