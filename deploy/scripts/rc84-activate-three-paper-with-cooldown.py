#!/usr/bin/env python3
"""Authorize and arm THREE explicitly user-approved PAPER trading bots.

Do not install/merge code or change risk profiles. The first 20 minutes remain
PAUSED after --arm. A host systemd one-shot timer invokes --unpause after the
cooldown, re-checking original capital, owner, mandate and service state. A
failure before or during release keeps/returns all three to PAUSED and never
forcibly closes any position. No live exchange orders are possible here.

--check: readonly; --arm: backed-up PAPER Brain mandate and delayed timer;
--unpause: only called after >=20 min cooldown; --emergency-pause: stop timer
and halt NEW entries, preserving any OPEN paper positions for exit services.
"""
from __future__ import annotations

import argparse
import hashlib
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path("/opt/superbot-v3-paper-runs")
FALCO = ROOT / "classic-hawk-paper20261111"
TORO = ROOT / "classic-bull-paper20261111"
BRAIN = ROOT / "brain-v3-paper20261111"
WALLETS = (FALCO, TORO, BRAIN)
RUN_ID = "brain-v3-paper20261111"
RUNNER_CODE = Path("/opt/superbot-v3-rc84-stage")
STAGE_PIN = "0e29a73a36f668643da4088178bacb8616a45ac0"
CTRL = Path("/opt/superbot-v3-paper-activation-20261111")
STATE_FILE = CTRL / "activation-state.json"
MANDATE_BACKUP = CTRL / "original-brain-mandate.json"
SCRIPT = CTRL / "activate.py"
TIMER_UNIT = "superbot-v3-paper-authorized-unpause-20261111.timer"
SERVICE_UNIT = "superbot-v3-paper-authorized-unpause-20261111.service"
COOLDOWN_MS = 20 * 60 * 1000
MAX_DELAY_MS = 90 * 60 * 1000
PYTHON = "/usr/bin/python3"
BOTS = {
    "falco": ("superbot-v3-paper-falco.service", FALCO),
    "toro": ("superbot-v3-paper-toro.service", TORO),
    "brain-runner": ("superbot-v3-paper-brain-runner.service", BRAIN),
    "brain-exit": ("superbot-v3-paper-brain-exit.service", BRAIN),
}


class GuardFailure(RuntimeError):
    pass


def refuse(reason: str) -> None:
    raise GuardFailure(reason)


def run(*args: str, timeout: int = 20, allow_failure: bool = False) -> str:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        refuse("LOCAL_COMMAND_ERROR")
    if p.returncode and not allow_failure:
        refuse("LOCAL_COMMAND_REFUSED")
    return p.stdout.strip() if p.returncode == 0 else ""


def readjson(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        refuse("UNVERIFIED_LOCAL_FILE")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if type(data) is dict:
            return data
    except (OSError, ValueError, UnicodeError):
        pass
    refuse("LOCAL_JSON_INVALID")


def atomic_json(path: Path, data: dict) -> None:
    if path.is_symlink() or not path.parent.is_dir() or path.parent.is_symlink():
        refuse("UNSAFE_ATOMIC_PATH")
    fd, temp = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, sort_keys=True, separators=(",", ":"))
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
        dirfd = os.open(str(path.parent), os.O_DIRECTORY | os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def public_web_gate() -> None:
    old = json.loads(run("docker", "inspect", "superbot"))[0]
    bridge = json.loads(run("docker", "inspect", "superbot-rc84-paper-close-bridge"))[0]
    if (old.get("State", {}).get("Running") is not True
            or bridge.get("State", {}).get("Running") is not True
            or bridge.get("HostConfig", {}).get("NetworkMode") != "none"
            or old.get("Config", {}).get("Image") != "superbot:rc84-paper-single-close-20261111"):
        refuse("PUBLIC_OR_BRIDGE_STATE_CHANGED")
    env = dict(x.split("=", 1) for x in old["Config"].get("Env", []) if "=" in x)
    wanted = dict(DESK_MODE="paper", TRADING_MODE="paper",
                  V3_CUTOVER_READONLY="1", V3_ALLOW_CLASSIC_SINGLE_CLOSE="1",
                  V3_ALLOW_BRAIN_SINGLE_CLOSE="1", V3_CLOSE_BRIDGE_ONLY="1")
    if any(env.get(k) != v for k, v in wanted.items()):
        refuse("PUBLIC_PAPER_GATE_MISMATCH")
    for d in WALLETS:
        mounts = old.get("Mounts", []) or []
        if not any(m.get("Source") == str(d) and m.get("RW") is False for m in mounts):
            refuse("PUBLIC_WALLET_NOT_READONLY")
    def request(path, method="GET"):
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8002" + path, method=method,
                data=b"{}" if method == "POST" else None)
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            return e.code
        except (urllib.error.URLError, TimeoutError):
            return 0
    if (request("/api/health") != 200
            or request("/api/v3/overview") != 401
            or request("/api/desk/close-position", "POST") != 401
            or request("/api/v3/brain/close", "POST") != 401
            or request("/api/desk/resume", "POST") != 423
            or request("/api/desk/close-all", "POST") != 423
            or request("/api/desk/reset-portfolio", "POST") != 423):
        refuse("PUBLIC_AUTH_OR_MUTATION_GATES_CHANGED")


def _proc_env(pid: int) -> dict[bytes, bytes]:
    path = Path(f"/proc/{pid}/environ")
    try:
        raw = path.read_bytes()
    except OSError:
        refuse("RUNNER_PROCESS_ENV_UNAVAILABLE")
    return dict(row.split(b"=", 1) for row in raw.split(b"\0") if b"=" in row)


def _pid(name: str) -> int:
    run("systemctl", "is-active", "--quiet", name)
    p = run("systemctl", "show", name, "-p", "MainPID", "--value")
    if not p.isdecimal() or int(p) <= 1:
        refuse("PAPER_WORKER_PID_INVALID")
    return int(p)


def verify(*, expected_approved: bool, expect_paused: bool = True) -> dict:
    if os.geteuid() != 0:
        refuse("ROOT_REQUIRED")
    if not RUNNER_CODE.is_dir() or RUNNER_CODE.is_symlink():
        refuse("CODE_STAGE_MISSING")
    if run("git", "-C", str(RUNNER_CODE), "rev-parse", "HEAD") != STAGE_PIN:
        refuse("TRADING_CODE_NOT_PINNED_RC84")
    if not CTRL.is_dir() or CTRL.is_symlink() or CTRL.stat().st_mode & 0o077:
        refuse("CONTROL_DIR_NOT_PRIVATE")
    if SCRIPT.is_symlink() or not SCRIPT.is_file():
        refuse("CONTROL_SCRIPT_MISSING")
    # The immutable script is staged by operator from GitHub, not pulled from
    # unknown web content at the point of trading activation.
    if not ROOT.is_dir() or ROOT.is_symlink():
        refuse("RUN_ROOT_UNSAFE")
    pids = {}
    for name, (unit, root) in BOTS.items():
        pid = _pid(unit)
        env = _proc_env(pid)
        if env.get(b"DESK_MODE") != b"paper":
            refuse("TRADING_WORKER_NOT_PAPER")
        if name == "falco":
            if env.get(b"DESK_PORTFOLIO") != b"hawk" or not env.get(b"ANTHROPIC_API_KEY"):
                refuse("FALCO_AI_OR_PORTFOLIO_WRONG")
        if name == "toro":
            if env.get(b"DESK_PORTFOLIO") != b"bull" or not env.get(b"ANTHROPIC_API_KEY"):
                refuse("TORO_AI_OR_PORTFOLIO_WRONG")
        if name == "brain-runner":
            if not env.get(b"DEEPSEEK_API_KEY"):
                refuse("BRAIN_DEEPSEEK_NOT_PRESENT")
            if env.get(b"BRAIN_FABLE_SHADOW") == b"1" or env.get(b"BRAIN_FABLE_BUDGET_APPROVED") == b"1":
                refuse("FABLE_MUST_STAY_OFF")
        pids[name] = pid
    for folder in WALLETS:
        if folder.is_symlink() or not folder.is_dir():
            refuse("PAPER_DIR_MISSING")
        marker = readjson(folder / "PREPARED_PAUSED_ONLY.json")
        if marker.get("paper_only") is not True or marker.get("paused") is not True:
            refuse("WRONG_PREPARED_IDENTITY")
        if expect_paused and ((folder / "pause.flag").is_symlink() or not (folder / "pause.flag").is_file()):
            refuse("PAUSE_FILE_MISSING")
    for path, wallet in ((FALCO, "hawk"), (TORO, "bull")):
        marker = readjson(path / "PREPARED_PAUSED_ONLY.json")
        if marker.get("initial_equity") != "1000" or marker.get("portfolio_id") != wallet:
            refuse("CLASSIC_START_CAPITAL_WRONG")
        state = readjson(path / "state_v2.json")
        main = state.get("main") or {}
        if float(main.get("cash", -1)) != 1000 or main.get("positions") not in ({}, []):
            refuse("CLASSIC_PAPER_NOT_EMPTY_OR_CAPITAL_CHANGED")
        if expect_paused and state.get("paused") is not True:
            refuse("CLASSIC_PROCESS_NOT_PAUSED")
        hb = readjson(path / "heartbeat.json")
        if (hb.get("portfolio") != wallet or hb.get("exec_mode") != "paper"
                or time.time() - float(hb.get("ts", 0)) > 100
                or time.time() - float(hb.get("ts", 0)) < -10):
            refuse("CLASSIC_HEARTBEAT_STALE")
    conf = BRAIN / "runner_config.json"
    raw = conf.read_bytes()
    config = json.loads(raw)
    mr = readjson(BRAIN / "PREPARED_PAUSED_ONLY.json")
    if (mr.get("run_id") != RUN_ID or mr.get("initial_equity") != "2000"
            or hashlib.sha256(raw).hexdigest() != mr.get("config_sha256")):
        refuse("BRAIN_RUN_CONFIG_CHANGED")
    rp = config.get("risk_policy") or {}
    if (float(config.get("initial_equity", 0)) != 2000
            or rp.get("min_leverage") != 20 or rp.get("max_leverage") != 50
            or float(rp.get("minimum_equity", 0)) != 450
            or abs(float(rp.get("max_open_risk_fraction", 0)) - 0.12) > 1e-12
            or abs(float(rp.get("max_total_margin_fraction", 0)) - 0.55) > 1e-12
            or abs(float(rp.get("max_position_margin_fraction", 0)) - 0.20) > 1e-12
            or abs(float(rp.get("max_loss_margin_fraction", 0)) - (75/350)) > 1e-9
            or config.get("cycle_minutes") != 60
            or config.get("model", "").lower().find("deepseek") < 0):
        refuse("BRAIN_RISK_OR_MODEL_MISMATCH")
    if any((BRAIN / name).exists() for name in ("close_request.json", "reset.flag")):
        refuse("BRAIN_PENDING_MUTATION")
    mandate = readjson(BRAIN / "mandate.json")
    if (set(mandate) != {"version", "approved", "approved_by", "portfolio_id", "run_id", "policy_hash"}
            or mandate.get("approved") is not expected_approved
            or mandate.get("portfolio_id") != "brain"
            or mandate.get("run_id") != RUN_ID
            or not isinstance(mandate.get("policy_hash"), str)
            or not re.fullmatch(r"[0-9a-f]{16}", mandate["policy_hash"])
            or mandate["policy_hash"] != expected_policy_hash(rp)):
        refuse("BRAIN_MANDATE_NOT_EXPECTED")
    if expected_approved and mandate.get("approved_by") != "user-authorized-PAPER-2026-11-11":
        refuse("BRAIN_PAPER_APPROVER_CHANGED")
    hb = readjson(BRAIN / "heartbeat.json")
    ex = readjson(BRAIN / "exit_heartbeat.json")
    now_ms = int(time.time() * 1000)
    if (hb.get("run_id") != RUN_ID or ex.get("run_id") != RUN_ID
            or not isinstance(hb.get("ts_ms"), int) or now_ms - hb["ts_ms"] not in range(-15000, 100001)
            or not isinstance(ex.get("ts_ms"), int) or now_ms - ex["ts_ms"] not in range(-15000, 30001)
            or ex.get("state") != "healthy" or ex.get("last_error") is not None):
        refuse("BRAIN_OR_EXIT_OWNER_NOT_HEALTHY")
    if expect_paused and hb.get("state") not in ("paused", "halted"):
        refuse("BRAIN_NOT_PAUSED")
    # All services healthy and sole owner of their new run. Old legacy
    # strategies must remain stopped, preserving independent history.
    for legacy in ("superbot-desk-hawk", "superbot-desk-bull"):
        if run("docker", "inspect", "-f", "{{.State.Running}}", legacy, allow_failure=True) == "true":
            refuse("LEGACY_CLASSIC_RUNNING")
    for unit in ("superbot-v3-falco-exit.service", "superbot-v3-toro-exit.service"):
        run("systemctl", "is-active", "--quiet", unit)
    run("systemctl", "is-active", "--quiet", "superbot-v3-paper-single-close-bridge.service")
    public_web_gate()
    return {"worker_pids": pids, "mandate": mandate, "heartbeat_state": hb.get("state")}


def expected_policy_hash(risk: dict) -> str:
    """Match BrainEngine._policy_hash exactly; its checksum is 16 hex chars."""
    keys = (
        "max_loss_fraction", "max_open_risk_fraction",
        "max_position_margin_fraction", "max_total_margin_fraction",
        "minimum_equity", "estimated_roundtrip_cost_bp",
        "liquidation_buffer_fraction", "max_loss_margin_fraction",
    )
    try:
        fields = [str(Decimal(str(risk[key]))) for key in keys]
        fields.extend((str(risk["min_leverage"]), str(risk["max_leverage"])))
        return hashlib.sha256("|".join(fields).encode("utf-8")).hexdigest()[:16]
    except (KeyError, ValueError, TypeError):
        refuse("BRAIN_RISK_HASH_NOT_COMPUTABLE")


def update_mandate(approved: bool) -> None:
    data = readjson(BRAIN / "mandate.json")
    data["approved"] = approved
    data["approved_by"] = "user-authorized-PAPER-2026-11-11" if approved else ""
    atomic_json(BRAIN / "mandate.json", data)


def save_state(state: dict) -> None:
    atomic_json(STATE_FILE, state)


def check_mode() -> None:
    v = verify(expected_approved=False)
    print("PAPER_PRESTART_THREE_WALLETS_PAUSED=PASS",flush=True)
    print("PAPER_PRESTART_RC84_CODE_AI_AND_RISK=PASS",flush=True)
    print("PAPER_PRESTART_BRAIN_EXIT_AND_MANUAL_CLOSE=PASS",flush=True)
    print("PAPER_PRESTART_FABLE_DISABLED=PASS",flush=True)
    print("PAPER_PRESTART_CLASSIC_AND_BRAIN_CAPITAL=PASS",flush=True)


def arm() -> None:
    if STATE_FILE.exists() or MANDATE_BACKUP.exists():
        refuse("ACTIVATION_ALREADY_ARMED")
    before = verify(expected_approved=False)
    if (run("systemctl", "is-active", TIMER_UNIT, allow_failure=True) == "active"
            or run("systemctl", "is-enabled", TIMER_UNIT, allow_failure=True) == "enabled"):
        refuse("PAPER_TIMER_ALREADY_EXISTS")
    old = before["mandate"]
    atomic_json(MANDATE_BACKUP, old)
    armed_at_ms = int(time.time() * 1000)
    data = {
        "schema": 1, "mode": "armed_pause", "armed_at_ms": armed_at_ms,
        "cooldown_ms": COOLDOWN_MS, "run_id": RUN_ID,
        "worker_pids": before["worker_pids"],
        "mandate_sha_before": hashlib.sha256(
            (json.dumps(old, sort_keys=True, separators=(",", ":"))).encode()).hexdigest(),
        "user_approved": True, "approved_scope": "paper_only",
        "fable_enabled": False,
    }
    try:
        update_mandate(True)
        save_state(data)
        verify(expected_approved=True)
        # Timer belongs to SYSTEMD, not the chat. No service activation now;
        # if reboot/health changes, --unpause refuses and all pauses remain.
        run("systemd-run", "--quiet",
            "--unit=superbot-v3-paper-authorized-unpause-20261111",
            "--on-active=20min", "--property=Type=oneshot",
            "--property=TimeoutStartSec=600",
            PYTHON, "-I", str(SCRIPT), "--unpause", timeout=30)
        if run("systemctl", "is-active", TIMER_UNIT) != "active":
            refuse("STARTUP_COOLDOWN_TIMER_NOT_ACTIVE")
        print("PAPER_BRAIN_MANDATE_APPROVED_USER_AUTHORIZED=PASS",flush=True)
        print("PAPER_THREE_PAUSE_FLAGS_STILL_PRESENT=PASS",flush=True)
        print("PAPER_20_MINUTE_STARTUP_COOLDOWN_ARMED=PASS",flush=True)
        print("PAPER_FABLE_REMAINS_OFF=True",flush=True)
        print("PAPER_NO_ORDERS_YET=True",flush=True)
    except Exception:
        run("systemctl", "stop", TIMER_UNIT, allow_failure=True)
        try:update_mandate(False)
        except Exception:pass
        for folder in WALLETS:
            p = folder / "pause.flag"
            if not p.exists():
                p.write_text("fallback_paused\n")
                p.chmod(0o600)
        if STATE_FILE.exists():
            data["mode"] = "arming_failed_paused"
            save_state(data)
        raise


def _heartbeat_started(folder: Path, klass: str, deadline_s: int = 110) -> None:
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        hb = readjson(folder / "heartbeat.json")
        if klass == "classic":
            if hb.get("mode") == "running" and 0 <= time.time() - float(hb.get("ts", 0)) < 50:
                return
        else:
            if hb.get("state") == "running" and (
                0 <= int(time.time()*1000) - int(hb.get("ts_ms",0)) < 50000):
                return
        time.sleep(2)
    refuse("RUNNER_DID_NOT_ACKNOWLEDGE_PAPER_RUNNING")


def _emergency_flags_only() -> None:
    # Never close an existing PAPER position: exit workers stay alive.
    for folder in WALLETS:
        p = folder / "pause.flag"
        if not p.exists():
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as out:
                out.write("emergency_new_entries_off\n")
                out.flush(); os.fsync(out.fileno())


def unpause() -> None:
    state = readjson(STATE_FILE)
    now_ms = int(time.time() * 1000)
    armed = state.get("armed_at_ms")
    if (state.get("mode") != "armed_pause"
            or state.get("user_approved") is not True
            or state.get("approved_scope") != "paper_only"
            or type(armed) is not int
            or now_ms - armed < COOLDOWN_MS
            or now_ms - armed > MAX_DELAY_MS):
        refuse("COOLDOWN_NOT_SATISFIED_OR_ALREADY_USED")
    try:
        current = verify(expected_approved=True)
        if current["worker_pids"] != state.get("worker_pids"):
            refuse("PAPER_SERVICE_RESTARTED_DURING_COOLDOWN")
        # Change state BEFORE touching pauses: crashes can be recognized and
        # never blindly re-execute a partially finished delayed release.
        state["mode"] = "unpause_in_progress"
        save_state(state)
        (FALCO / "pause.flag").unlink()
        _heartbeat_started(FALCO, "classic")
        (TORO / "pause.flag").unlink()
        _heartbeat_started(TORO, "classic")
        if not (BRAIN / "exit_heartbeat.json").is_file():
            refuse("BRAIN_EXIT_OWNER_DISAPPEARED")
        (BRAIN / "pause.flag").unlink()
        _heartbeat_started(BRAIN, "brain")
        # All workers remain the initial PAPER PIDs, and the web cutover never
        # allowed START/RESET/BULK.
        for name, (unit, _) in BOTS.items():
            if _pid(unit) != state["worker_pids"][name]:
                refuse("WORKER_CHANGED_DURING_UNPAUSE")
        public_web_gate()
        state["mode"] = "paper_running"
        state["unpaused_at_ms"] = int(time.time() * 1000)
        save_state(state)
        print("PAPER_FALCO_RUNNING=PASS",flush=True)
        print("PAPER_TORO_RUNNING=PASS",flush=True)
        print("PAPER_BRAIN_RUNNING=PASS",flush=True)
        print("PAPER_NO_LIVE_ORDERS_CAPABLE=True",flush=True)
        print("PAPER_FABLE_DISABLED=True",flush=True)
        print("PAPER_20_MIN_STARTUP_COOLDOWN_COMPLETED=PASS",flush=True)
    except Exception:
        _emergency_flags_only()
        update_mandate(False)
        state["mode"] = "activation_failed_repaused"
        save_state(state)
        print("PAPER_ACTIVATION_FAILURE_ALL_NEW_ENTRIES_PAUSED=True",flush=True)
        raise


def emergency_pause() -> None:
    if not STATE_FILE.exists():
        refuse("NOT_ARMED")
    run("systemctl", "stop", TIMER_UNIT, allow_failure=True)
    _emergency_flags_only()
    update_mandate(False)
    state = readjson(STATE_FILE)
    state["mode"] = "operator_emergency_paused"
    save_state(state)
    print("PAPER_THREE_WALLETS_NEW_ENTRIES_PAUSED=PASS", flush=True)
    print("PAPER_OPEN_POSITIONS_STILL_MANAGED_NO_FORCE_CLOSE=True",flush=True)


def main():
    arg = argparse.ArgumentParser()
    group = arg.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--arm", action="store_true")
    group.add_argument("--unpause", action="store_true")
    group.add_argument("--emergency-pause", action="store_true")
    a = arg.parse_args()
    if a.check: check_mode()
    elif a.arm:arm()
    elif a.unpause:unpause()
    else:emergency_pause()


if __name__ == "__main__":
    try:main()
    except Exception as e:
        print("RC84_PAPER_ACTIVATION_REFUSED="+(
            str(e) if type(e) is GuardFailure else "UNKNOWN_ERROR"),flush=True)
        sys.exit(2)
