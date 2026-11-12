#!/usr/bin/env python3
"""RC84 PAPER-only controlled unit cutover, initially PAUSED.

--check          strictly read-only; no service control, files or wallet writes
--apply-paused   requires separate operator authorization: swaps only 4 systemd
                 unit source paths from the pinned versioned bundle, starts
                 4 workers while the 3 wallet pause flags remain present.
                 On any failure attempts to STOP new workers, restore the
                 exact original 4 unit bytes, daemon-reload and leave inactive.

This does NOT resume openings, merge branches, reset wallets, touch backups,
replace exit services belonging to legacy portfolios, or change the app/bridge.
Never use with LIVE money. Do not run apply from a generic CI workflow.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time

BUNDLE = Path("/opt/superbot-v3-rc84-unit-bundle-ab7e0b7")
CHECK = Path("/root/rc84-prepare-units.py")
CHECK_BLOB = "94837f683d8a195e0b2259d05c5fe7cac2216de7"
OLD = "/opt/superbot-v3-rc84-stage"
NEW = "/opt/superbot-v3-rc84-repair-ab7e0b7"
PIN = "ab7e0b7d991b8f4bd714fccfec23b09a936e6717"
BACKUP_SHA = "a18aff67032605045dd3ef3888f5d225fdd8930b49d89d780aa676aca8f6c8fa"
SYSTEMD = Path("/etc/systemd/system")
ROOT = Path("/opt/superbot-v3-paper-runs")
FALCO = ROOT / "classic-hawk-paper20261111"
TORO = ROOT / "classic-bull-paper20261111"
BRAIN = ROOT / "brain-v3-paper20261111"
PAUSES = (FALCO, TORO, BRAIN)
# Start exit owner FIRST. Rollback stops in reverse order.
UNITS = (
    "superbot-v3-paper-brain-exit.service",
    "superbot-v3-paper-falco.service",
    "superbot-v3-paper-toro.service",
    "superbot-v3-paper-brain-runner.service",
)
PENDING = {
    FALCO: ("close_position.flag", "close_position.flag.work", "reset.flag",
            "reset_portfolio.flag"),
    TORO: ("close_position.flag", "close_position.flag.work", "reset.flag",
           "reset_portfolio.flag"),
    BRAIN: ("close_request.json", "close_request.work", "reset.flag",
            "reset_portfolio.flag"),
}

def refuse(code: str) -> None:
    raise RuntimeError(code)

def run(*args: str, timeout: int = 40) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        refuse("command_failed_" + Path(args[0]).name)
    return result.stdout.strip()

def prop(unit: str, property: str) -> str:
    return run("systemctl", "show", unit, "--property=" + property, "--value")

def state(unit: str) -> str:
    return prop(unit, "ActiveState")

def regular(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        refuse("missing_or_linked_" + path.name)
    return path.read_bytes()

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + bytes([0]) + data).hexdigest()

def check_flags() -> None:
    for path in PAUSES:
        if not path.is_dir() or path.is_symlink():
            refuse("paper_wallet_directory_missing")
        pause = path / "pause.flag"
        if not pause.is_file() or pause.is_symlink():
            refuse("paper_wallet_pause_missing")
        for filename in PENDING[path]:
            flag = path / filename
            if flag.exists() or flag.is_symlink():
                refuse("pending_close_or_reset_command")

def positions_count(path: Path) -> int:
    raw = json.loads(regular(path / "state_v2.json"))
    positions = raw["main"]["positions"]
    if not isinstance(positions, dict):
        refuse("invalid_classic_positions")
    return len(positions)

def approved_bundle() -> dict:
    if BUNDLE.is_symlink() or not BUNDLE.is_dir():
        refuse("bundle_not_regular_directory")
    mf = json.loads(regular(BUNDLE / "MANIFEST.json"))
    if (mf.get("schema") != "rc84-paper-unit-bundle-prepared-only-v1"
            or mf.get("old_path") != OLD or mf.get("new_path") != NEW
            or mf.get("new_pin") != PIN
            or mf.get("backup_manifest_sha256") != BACKUP_SHA
            or mf.get("paper_only") is not True
            or mf.get("pause_flags_kept") is not True
            or mf.get("no_systemd_changes") is not True
            or set(mf.get("units", {})) != set(UNITS)):
        refuse("manifest_identity_mismatch")
    for sub in ("candidate", "rollback"):
        folder = BUNDLE / sub
        if folder.is_symlink() or not folder.is_dir():
            refuse("bundle_subfolder_invalid")
        if {p.name for p in folder.iterdir()} != set(UNITS):
            refuse("bundle_contains_unexpected_units")
    for unit in UNITS:
        oldbytes = regular(BUNDLE / "rollback" / unit)
        newbytes = regular(BUNDLE / "candidate" / unit)
        expected = mf["units"][unit]
        if (sha256(oldbytes) != expected.get("old_sha256")
                or sha256(newbytes) != expected.get("candidate_sha256")):
            refuse("bundle_unit_hash_mismatch_" + unit)
        original = oldbytes.decode("utf-8")
        if original.count(OLD) != 2 or original.replace(OLD, NEW).encode() != newbytes:
            refuse("bundle_unit_not_exact_replacement_" + unit)
        if ("WorkingDirectory=" + NEW not in newbytes.decode()
                or "DESK_MODE=paper" not in original):
            refuse("bundle_unit_not_paper_" + unit)
    return mf

def verify_read_only_prerequisites() -> dict:
    if os.geteuid() != 0:
        refuse("root_required")
    if git_blob(regular(CHECK)) != CHECK_BLOB:
        refuse("bundle_checker_sha_invalid")
    p = subprocess.run([sys.executable, "-I", str(CHECK), "--check"],
                       capture_output=True, text=True, timeout=150)
    if (p.returncode != 0
            or "RC84_BUNDLE_READ_ONLY_CHECK=PASS" not in p.stdout
            or "RC84_BUNDLE_NO_PENDING_CLOSE_OR_RESET=PASS" not in p.stdout):
        refuse("complete_prior_gates_not_passed")
    mf = approved_bundle()
    check_flags()
    for unit in UNITS:
        if state(unit) != "inactive":
            refuse("paper_worker_not_inactive_" + unit)
        if prop(unit, "WorkingDirectory") != OLD:
            refuse("installed_workdir_changed_" + unit)
        if regular(SYSTEMD / unit) != regular(BUNDLE / "rollback" / unit):
            refuse("installed_unit_changed_" + unit)
    print("RC84_RELEASE_BACKUP_AND_GATE=PASS", flush=True)
    print("RC84_RELEASE_FOUR_UNIT_BUNDLE_HASHES=PASS", flush=True)
    print("RC84_RELEASE_FOUR_WORKERS_INACTIVE=PASS", flush=True)
    return mf

def write_unit_atomic(unit: str, data: bytes) -> None:
    path = SYSTEMD / unit
    fd, name = tempfile.mkstemp(prefix=".rc84-unit-", dir=SYSTEMD)
    tmp = Path(name)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "wb") as f:
            fd = -1
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        tmp = None
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp is not None and tmp.exists():
            tmp.unlink()

def restore_original_units() -> bool:
    ok = True
    for unit in reversed(UNITS):
        try:
            run("systemctl", "stop", unit, timeout=80)
        except Exception:
            ok = False
    for unit in UNITS:
        try:
            write_unit_atomic(unit, regular(BUNDLE / "rollback" / unit))
        except Exception:
            ok = False
    try:
        run("systemctl", "daemon-reload", timeout=40)
    except Exception:
        ok = False
    for unit in UNITS:
        try:
            if (regular(SYSTEMD / unit) != regular(BUNDLE / "rollback" / unit)
                    or prop(unit, "WorkingDirectory") != OLD
                    or state(unit) != "inactive"):
                ok = False
        except Exception:
            ok = False
    return ok

def fresh_heartbeat(path: Path, start_seconds: float) -> dict:
    body = json.loads(regular(path))
    if not isinstance(body, dict):
        refuse("invalid_heartbeat")
    ts = body.get("ts_ms")
    if type(ts) is int:
        value = ts / 1000
    else:
        ts = body.get("ts")
        value = float(ts) if type(ts) in (float, int) else 0.0
    if not start_seconds - 5 <= value <= time.time() + 5:
        refuse("stale_or_invalid_heartbeat_" + path.parent.name)
    return body

def verify_paused_run(started: float, old_counts: tuple[int,int]) -> None:
    deadline = time.monotonic() + 35
    problem = "heartbeat_not_ready"
    while time.monotonic() <= deadline:
        check_flags()
        if any(state(u) != "active" for u in UNITS):
            refuse("one_paper_worker_not_active")
        try:
            falco = fresh_heartbeat(FALCO / "heartbeat.json", started)
            toro = fresh_heartbeat(TORO / "heartbeat.json", started)
            brain = fresh_heartbeat(BRAIN / "heartbeat.json", started)
            ex = fresh_heartbeat(BRAIN / "exit_heartbeat.json", started)
            if (falco.get("exec_mode") != "paper"
                    or falco.get("portfolio") != "hawk"
                    or falco.get("pause_requested") is not True
                    or falco.get("mode") not in ("paused", "draining")
                    or toro.get("exec_mode") != "paper"
                    or toro.get("portfolio") != "bull"
                    or toro.get("pause_requested") is not True
                    or toro.get("mode") not in ("paused", "draining")):
                refuse("classic_heartbeat_not_paused_paper")
            if (brain.get("run_id") != "brain-v3-paper20261111"
                    or brain.get("state") not in ("paused", "halted")
                    or brain.get("cycle") != 0
                    or brain.get("exit_mode") != "sidecar"):
                refuse("brain_heartbeat_not_paused_sidecar")
            if (ex.get("run_id") != "brain-v3-paper20261111"
                    or ex.get("state") != "healthy"
                    or ex.get("last_error") is not None):
                refuse("brain_exit_heartbeat_not_healthy")
            now_counts = (positions_count(FALCO), positions_count(TORO))
            if any(now > old for now, old in zip(now_counts, old_counts)):
                refuse("new_classic_position_while_paused")
            print("RC84_RELEASE_HEARTBEATS_FALCO_TORO_BRAIN=PASS", flush=True)
            print("RC84_RELEASE_BRAIN_EXIT_HEALTHY=PASS", flush=True)
            print("RC84_RELEASE_NO_NEW_CLASSIC_POSITIONS=PASS", flush=True)
            return
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            problem = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        time.sleep(2)
    refuse("poststart_" + problem)

def apply_paused() -> None:
    verify_read_only_prerequisites()
    before = (positions_count(FALCO), positions_count(TORO))
    # All prechecks have completed and no worker is yet running. The first
    # systemd mutation starts here; any failure requires local rollback.
    changed = False
    try:
        changed = True
        for unit in UNITS:
            check_flags()
            if regular(SYSTEMD / unit) != regular(BUNDLE / "rollback" / unit):
                refuse("unexpected_unit_write_before_swap_" + unit)
            write_unit_atomic(unit, regular(BUNDLE / "candidate" / unit))
        run("systemctl", "daemon-reload", timeout=45)
        for unit in UNITS:
            if (prop(unit, "WorkingDirectory") != NEW
                    or state(unit) != "inactive"
                    or prop(unit, "NeedDaemonReload") != "no"):
                refuse("unit_cutover_not_loaded_" + unit)
        print("RC84_RELEASE_FOUR_UNITS_SWITCHED=PASS", flush=True)
        started = time.time()
        for unit in UNITS:
            check_flags()
            run("systemctl", "start", unit, timeout=210)
        verify_paused_run(started, before)
        print("RC84_RELEASE_PAPER_WORKERS_STARTED_PAUSED=PASS", flush=True)
        print("RC84_RELEASE_NO_RESET_NO_LIVE=PASS", flush=True)
        print("RC84_RELEASE_PAUSE_FLAGS_RETAINED=3", flush=True)
        print("RC84_RELEASE_MANUAL_RESUME_NOT_AUTHORIZED=True", flush=True)
    except BaseException as exc:
        # The Android/Termius connection or operator may deliver SIGINT/SIGTERM
        # halfway through unit replacement. Never leave a mixed source config.
        code = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print("RC84_RELEASE_ABORT_REASON=" + code, flush=True)
        if changed:
            # A second interrupt must not interrupt the recovery itself.
            previous_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
            previous_term = signal.signal(signal.SIGTERM, signal.SIG_IGN)
            try:
                restored = restore_original_units()
            finally:
                signal.signal(signal.SIGINT, previous_int)
                signal.signal(signal.SIGTERM, previous_term)
            print("RC84_RELEASE_ROLLBACK_UNITS=" + ("PASS" if restored else "FAILED"), flush=True)
            print("RC84_RELEASE_ALL_WORKERS_LEFT_INACTIVE=" +
                  ("PASS" if restored else "NOT_VERIFIED"), flush=True)
        raise

def interrupt_as_error(signum: int, _frame: object) -> None:
    raise InterruptedError("operator_signal_" + str(signum))


def main() -> int:
    if sys.argv[1:] not in (["--check"], ["--apply-paused"]):
        print("USAGE: script.py --check | --apply-paused")
        return 2
    try:
        os.umask(0o077)
        if sys.argv[1] == "--check":
            verify_read_only_prerequisites()
            print("RC84_RELEASE_READ_ONLY_CHECK=PASS", flush=True)
            print("RC84_RELEASE_NOT_APPLIED=True", flush=True)
        else:
            # Only the write-capable command installs signal-to-exception
            # handlers. The apply_paused() exception handler attempts rollback.
            previous_int = signal.signal(signal.SIGINT, interrupt_as_error)
            previous_term = signal.signal(signal.SIGTERM, interrupt_as_error)
            try:
                apply_paused()
            finally:
                signal.signal(signal.SIGINT, previous_int)
                signal.signal(signal.SIGTERM, previous_term)
        return 0
    except (RuntimeError, OSError, ValueError, KeyError, TypeError,
            subprocess.SubprocessError, json.JSONDecodeError, InterruptedError) as e:
        print("RC84_RELEASE_REFUSED=" + (
            str(e) if isinstance(e, RuntimeError) else type(e).__name__), flush=True)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
