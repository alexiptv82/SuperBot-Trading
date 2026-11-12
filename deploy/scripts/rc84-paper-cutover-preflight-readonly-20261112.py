#!/usr/bin/env python3
"""RC84: READ-ONLY audit before any PAPER unit cutover.

Does NOT stop/start/reload/enable systemd, alter flags, DBs, snapshots,
manifests, git branches, service files, credentials, or trading settings.
Inspect unit files without printing their potentially sensitive contents.
FAIL CLOSED on any unexpected identity, writer, stage, or backup.
"""
from __future__ import annotations

import hashlib
import json
import shlex
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
        # Original OLD checkout predates these unit templates. Compare instead
        # against exact, pinned NEW source; fail closed if any version differs.
        source_template = safe_file(NEW / "deploy" / "rc84-paper-services" / unit)
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

CLOSE_UNIT = "superbot-v3-paper-single-close-bridge.service"
CLOSE_CONTAINER = "superbot-rc84-paper-close-bridge"
CLOSE_UNIT_BLOB = "9555640cdeda3cc28303532078ea12f5be470316"
CLOSE_IMAGE = "superbot:rc84-paper-single-close-20261111"

def docker_inspect(container: str) -> dict:
    data = json.loads(command(["docker", "inspect", container], timeout=30))
    if not isinstance(data, list) or len(data) != 1:
        refuse("docker_inspect_ambiguous")
    return data[0]

def mount_matches(obj: dict, source: Path, writable: bool) -> bool:
    entries = [m for m in obj.get("Mounts", [])
               if m.get("Source") == str(source)]
    return len(entries) == 1 and entries[0].get("RW") is writable

def inspect_authorized_bridge_process(pid: int, argv: bytes) -> bool:
    # A narrow exception, NOT a blanket exception for Docker. Prove that the
    # candidate PID is systemd's *exact* MainPID for the pinned close bridge.
    if prop(CLOSE_UNIT, "ActiveState") != "active":
        return False
    if prop(CLOSE_UNIT, "MainPID") != str(pid):
        return False
    if prop(CLOSE_UNIT, "FragmentPath") != str(SYSTEMD / CLOSE_UNIT):
        return False
    if prop(CLOSE_UNIT, "DropInPaths") or prop(CLOSE_UNIT, "NeedDaemonReload") != "no":
        return False
    if git_blob(safe_file(SYSTEMD / CLOSE_UNIT)) != CLOSE_UNIT_BLOB:
        refuse("close_bridge_unit_not_pinned")
    try:
        exe = os.readlink("/proc/" + str(pid) + "/exe")
        parts = [x.decode("utf-8") for x in argv.split(bytes([0])) if x]
    except (OSError, UnicodeDecodeError):
        return False
    if exe != "/usr/bin/docker" or len(parts) < 8 or parts[0] != "/usr/bin/docker":
        return False
    # Compare the full argv with the signed-off systemd unit's ExecStart
    # rather than guessing from only 'docker run' or the container name.
    unit_data = safe_file(SYSTEMD / CLOSE_UNIT).decode("utf-8")
    cmd_lines = [line.split("=", 1)[1] for line in unit_data.splitlines()
                 if line.startswith("ExecStart=")]
    if len(cmd_lines) != 1 or parts != shlex.split(cmd_lines[0]):
        return False
    obj = docker_inspect(CLOSE_CONTAINER)
    if obj.get("Name") != "/" + CLOSE_CONTAINER:
        return False
    if obj.get("State", {}).get("Running") is not True:
        return False
    host = obj.get("HostConfig", {})
    if (host.get("NetworkMode") != "none"
            or host.get("ReadonlyRootfs") is not True
            or host.get("AutoRemove") is not True
            or obj.get("Config", {}).get("Image") != CLOSE_IMAGE):
        return False
    if not all(mount_matches(obj, RUNS / name, True) for name in WALLETS):
        return False
    if not mount_matches(obj, Path("/run/superbot-paper-close"), True):
        return False
    web = docker_inspect("superbot")
    if web.get("State", {}).get("Running") is not True:
        return False
    if not all(mount_matches(web, RUNS / name, False) for name in WALLETS):
        return False
    # Detect *all other currently running containers* that have wallet RW
    # mounts, including a parent mount that may expose multiple wallets.
    running_ids = command(["docker", "ps", "-q", "--no-trunc"], timeout=30).splitlines()
    if not running_ids:
        return False
    for ident in running_ids:
        other = docker_inspect(ident)
        if other.get("Id") == obj.get("Id"):
            continue
        for m in other.get("Mounts", []):
            source = m.get("Source")
            if not isinstance(source, str) or m.get("RW") is not True:
                continue
            # /opt or /opt/superbot-v3-paper-runs mounted RW can expose
            # wallets even if their full path is absent from argv.
            if any(str((RUNS / name)) == source or
                   str((RUNS / name)).startswith(source.rstrip("/") + "/")
                   for name in WALLETS):
                refuse("another_container_has_wallet_rw_mount")
    return True

def inspect_running_wallet_owners() -> None:
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
            seen.append((int(entry.name), argv))
    if len(seen) == 1 and inspect_authorized_bridge_process(*seen[0]):
        print("RC84_CUTOVER_AUTHORIZED_CLOSE_BRIDGE_ONLY=PASS", flush=True)
        print("RC84_CUTOVER_NO_OTHER_DOCKER_WALLET_RW=PASS", flush=True)
    elif seen:
        refuse("unclassified_wallet_argv_process_count_" + str(len(seen)))
    else:
        # A missing close bridge is NOT a substitute for healthy exit paths.
        refuse("authorized_close_bridge_process_missing")
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
