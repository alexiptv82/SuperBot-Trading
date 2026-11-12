#!/usr/bin/env python3
"""RC84 PAPER ONLY: freeze four identified systemd units and take a verified
private local snapshot of the three current run directories.
No network calls, no reset, no orders, no Git merges and no restart on success.
An error attempts to restart previously active units (pause flags stay present).
Run from a pinned Git commit with --check or --freeze-snapshot.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote

ROOT = Path("/opt/superbot-v3-paper-runs")
BACKUP_ROOT = Path("/opt/superbot-backups")
STAGE = Path("/opt/superbot-v3-rc84-stage")
EXPECTED_STAGE = "0e29a73a36f668643da4088178bacb8616a45ac0"
BOTS = {
    "falco": (ROOT / "classic-hawk-paper20261111", "superbot-v3-paper-falco.service", "hawk"),
    "toro": (ROOT / "classic-bull-paper20261111", "superbot-v3-paper-toro.service", "bull"),
    "brain": (ROOT / "brain-v3-paper20261111", "superbot-v3-paper-brain-runner.service", "brain"),
}
EXIT = "superbot-v3-paper-brain-exit.service"
SERVICES = (BOTS["brain"][1], BOTS["falco"][1], BOTS["toro"][1], EXIT)
MAX_FILE_COUNT = 100_000
MAX_TOTAL_BYTES = 2_500_000_000
MIN_DISK_FREE = 600_000_000


def refuse(reason):
    raise RuntimeError(reason)


def run(args, timeout=20):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout.strip()


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as fd:
        for chunk in iter(lambda: fd.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def regular_dir(path):
    return path.is_dir() and not path.is_symlink()


def read_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256_000:
        refuse("invalid_json_path")
    return json.loads(path.read_text(encoding="utf-8"))


def inventory(path):
    files = {}
    total = 0
    for base, dirs, names in os.walk(path, followlinks=False):
        dirs.sort()
        names.sort()
        for dirname in dirs:
            p = Path(base) / dirname
            if p.is_symlink() or not p.is_dir():
                refuse("symlink_or_non_dir_in_paper_data")
        for name in names:
            file = Path(base) / name
            st = file.lstat()
            if not stat.S_ISREG(st.st_mode):
                refuse("symlink_or_non_regular_file_in_paper_data")
            relative = file.relative_to(path).as_posix()
            total += st.st_size
            if total > MAX_TOTAL_BYTES or len(files) >= MAX_FILE_COUNT:
                refuse("snapshot_exceeds_file_or_size_limit")
            files[relative] = {"size": st.st_size, "sha256": sha256(file)}
    return files, total


def current_positions(path):
    data = read_json(path / "state_v2.json")
    positions = data.get("main", {}).get("positions")
    if not isinstance(positions, dict):
        refuse("classic_position_map_invalid")
    return len(positions)


def paper_process(unit, expected_folder):
    rc, s = run(["systemctl", "show", unit, "--property=MainPID", "--value"])
    if rc or not s.isdecimal() or int(s) <= 1:
        refuse("missing_paper_service_pid:" + unit)
    pid = int(s)
    proc = Path("/proc") / str(pid) / "environ"
    if not proc.is_file():
        refuse("missing_paper_process")
    rows = [x for x in proc.read_bytes().split(b"\0") if b"=" in x]
    env = dict(x.split(b"=", 1) for x in rows)
    if env.get(b"DESK_MODE") != b"paper":
        refuse("service_not_verified_as_paper:" + unit)
    if expected_folder:
        if env.get(b"DESK_DATA_DIR") != os.fsencode(expected_folder):
            refuse("service_data_dir_mismatch:" + unit)


def verify_prerequisites():
    if os.geteuid() != 0:
        refuse("root_permissions_required")
    for path in (ROOT, BACKUP_ROOT, STAGE):
        if not regular_dir(path):
            refuse("required_private_root_not_present_or_symlink")
    rc, pin = run(["git", "-C", str(STAGE), "rev-parse", "HEAD"])
    if rc or pin != EXPECTED_STAGE:
        refuse("runtime_source_pin_mismatch")
    for label, (path, service, ident) in BOTS.items():
        if not regular_dir(path) or not (path / "pause.flag").is_file():
            refuse("missing_paused_paper_folder:" + label)
        marker = read_json(path / "PREPARED_PAUSED_ONLY.json")
        if marker.get("paper_only") is not True:
            refuse("paper_identity_missing:" + label)
        if ident != "brain" and marker.get("portfolio_id") != ident:
            refuse("classic_portfolio_id_mismatch:" + label)
        if label == "brain":
            mandate = read_json(path / "mandate.json")
            if mandate.get("run_id") != "brain-v3-paper20261111":
                refuse("brain_mandate_run_mismatch")
            print("RC84_SNAPSHOT_BRAIN_MANDATE_APPROVED=" + str(mandate.get("approved") is True), flush=True)
        else:
            print("RC84_SNAPSHOT_" + label.upper() + "_OPEN=" + str(current_positions(path)), flush=True)
        rc, active = run(["systemctl", "is-active", service])
        if rc or active != "active":
            refuse("paper_service_inactive:" + service)
        paper_process(service, str(path) if label != "brain" else None)
        print("RC84_SNAPSHOT_" + label.upper() + "_ACTIVE_PAUSED_PAPER=True", flush=True)
    rc, active = run(["systemctl", "is-active", EXIT])
    if rc or active != "active":
        refuse("brain_exit_service_inactive")
    paper_process(EXIT, None)
    print("RC84_SNAPSHOT_BRAIN_EXIT_ACTIVE_PAPER=True", flush=True)


def verify_sqlite_copies(snapshot):
    """Check SQLite only on expendable *second* copies, never on saved snapshot.

    A mode=ro SQLite connection may update WAL/SHM sidecars on close. The
    preceding manifest-inventory hashes must remain byte-for-byte unchanged.
    Keep journal.db, budget.db and each database's potential WAL/SHM/journal
    sidecars together while validating, and discard only the temporary copies.
    """
    with tempfile.TemporaryDirectory(prefix=".rc84-sqlite-verify-",
                                     dir=str(snapshot.parent)) as isolated:
        isolated_root = Path(isolated)
        for relative in ("brain-v3-paper20261111/journal.db",
                         "brain-v3-paper20261111/budget.db"):
            file = snapshot / relative
            if not file.is_file() or file.is_symlink():
                refuse("essential_brain_database_missing_or_symlink:" + relative)
            scratch = isolated_root / Path(relative).parent
            scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
            temp_db = scratch / file.name
            for suffix in ("", "-wal", "-shm", "-journal"):
                original = file.with_name(file.name + suffix)
                if original.is_symlink():
                    refuse("sqlite_snapshot_symlink")
                if not original.exists():
                    if suffix == "":
                        refuse("essential_brain_database_missing:" + relative)
                    continue
                if not original.is_file():
                    refuse("sqlite_snapshot_non_regular_file")
                temporary = scratch / (file.name + suffix)
                shutil.copy2(original, temporary)
                if sha256(temporary) != sha256(original):
                    refuse("sqlite_validation_copy_sha_mismatch")
            uri = "file:" + quote(str(temp_db)) + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5)
            try:
                conn.execute("PRAGMA query_only=ON")
                result = conn.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    refuse("sqlite_integrity_check_failed:" + relative)
            finally:
                conn.close()
        print("RC84_SNAPSHOT_SQLITE_VERIFIED_IN_ISOLATION=PASS", flush=True)


def freeze_and_snapshot():
    dest = None
    were_stopped = []
    complete = False
    try:
        # All four are PAPER, active, correctly matched to the run, and paused.
        # Explicit systemctl stop (NOT restart) prevents a state-copy race.
        for service in SERVICES:
            rc, _ = run(["systemctl", "stop", service], timeout=30)
            if rc:
                refuse("could_not_stop_paper_service:" + service)
            were_stopped.append(service)
        for service in SERVICES:
            rc, active = run(["systemctl", "is-active", service])
            if active == "active":
                refuse("paper_service_still_active:" + service)

        inventory_before = {}
        total = 0
        for label, (path, _, _) in BOTS.items():
            files, nbytes = inventory(path)
            inventory_before[label] = files
            total += nbytes
        if shutil.disk_usage(BACKUP_ROOT).free < max(MIN_DISK_FREE, total * 2 + 250_000_000):
            refuse("insufficient_free_disk_for_private_snapshot")

        now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        dest = BACKUP_ROOT / ("rc84-current-paper-before-fix-" + now + "-" + str(os.getpid()))
        dest.mkdir(mode=0o700)
        snapshot = dest / "snapshot"
        snapshot.mkdir(mode=0o700)
        for label, (path, _, _) in BOTS.items():
            out = snapshot / path.name
            shutil.copytree(path, out, symlinks=False, copy_function=shutil.copy2)
            for base, dirs, names in os.walk(out):
                os.chmod(base, 0o700)
                for name in names:
                    os.chmod(Path(base) / name, 0o600)
            copied, _ = inventory(out)
            if copied != inventory_before[label]:
                refuse("copied_file_sha_mismatch:" + label)
            current, _ = inventory(path)
            if current != inventory_before[label]:
                refuse("source_changed_after_paper_stop:" + label)
        verify_sqlite_copies(snapshot)
        # No SQLite connection ever opens the actual snapshot databases.
        # Rehash originals anyway: this also catches any external writer.
        for label, (source, _, _) in BOTS.items():
            copied_final, _ = inventory(snapshot / source.name)
            if copied_final != inventory_before[label]:
                refuse("sqlite_check_or_other_writer_modified_snapshot:" + label)
        # A concurrent systemd operator/automatic activation must not race
        # with a successful snapshot. Recheck the identity gates at the end.
        for service in SERVICES:
            _, service_state = run(["systemctl", "is-active", service])
            if service_state == "active":
                refuse("paper_service_restarted_during_snapshot:" + service)
        for _, (source, _, _) in BOTS.items():
            if not (source / "pause.flag").is_file():
                refuse("paper_pause_flag_removed_during_snapshot")
        manifest = {
            "schema": "rc84-private-paper-three-wallet-snapshot-v1",
            "created_utc": now,
            "source_sha": EXPECTED_STAGE,
            "all_four_paper_services_stopped": True,
            "all_three_pause_flags_present": True,
            "wallets": {label: {"dirname": path.name,
                                "files": inventory_before[label],
                                "open_count": current_positions(path) if label != "brain" else None}
                        for label, (path, _, _) in BOTS.items()},
        }
        path = dest / "MANIFEST.json"
        with path.open("x", encoding="utf-8") as fd:
            json.dump(manifest, fd, sort_keys=True, separators=(",", ":"))
            fd.flush()
            os.fsync(fd.fileno())
        os.chmod(path, 0o600)
        manifest_sha = sha256(path)
        # MANIFEST validated; freeze is intentional on success until release.
        complete = True
        print("RC84_SNAPSHOT_VERIFIED=PASS", flush=True)
        print("RC84_SNAPSHOT_DIRECTORY=" + str(dest), flush=True)
        print("RC84_SNAPSHOT_MANIFEST_SHA256=" + manifest_sha, flush=True)
        print("RC84_SNAPSHOT_PAPER_SERVICES_STOPPED=4", flush=True)
        print("RC84_SNAPSHOT_PAPER_PAUSE_FLAGS_RETAINED=3", flush=True)
        print("RC84_SNAPSHOT_NO_RESET_NO_TRADE_NO_LIVE=PASS", flush=True)
    finally:
        if not complete:
            # If any prerequisite AFTER stopping fails, restore exactly the
            # previously running PAPER units. Pause flags remain untouched.
            for unit in reversed(were_stopped):
                try:
                    run(["systemctl", "start", unit], timeout=30)
                except (OSError, subprocess.SubprocessError):
                    pass
            print("RC84_SNAPSHOT_FAILED_ATTEMPTED_PAPER_RESTART=True", flush=True)
            print("RC84_SNAPSHOT_NO_RESET=True", flush=True)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("--check", "--freeze-snapshot"):
        print("USAGE: script.py --check | --freeze-snapshot")
        return 2
    os.umask(0o077)
    try:
        verify_prerequisites()
        if sys.argv[1] == "--check":
            print("RC84_SNAPSHOT_PREFLIGHT=PASS", flush=True)
            print("RC84_SNAPSHOT_DRY_RUN_NO_CHANGES=True", flush=True)
        else:
            freeze_and_snapshot()
        return 0
    except (RuntimeError, OSError, ValueError, KeyError, TypeError,
            subprocess.SubprocessError, sqlite3.DatabaseError) as exc:
        # Do not print paths/keys or filesystem data; only error class.
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print("RC84_SNAPSHOT_REFUSED=" + reason, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
