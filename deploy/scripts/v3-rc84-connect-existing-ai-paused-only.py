#!/usr/bin/env python3
"""Install ONLY existing Claude/DeepSeek credentials into the NEW PAUSED PAPER units.

- Source secrets remain on the SAME VPS, read in private memory from stopped old
  PAPER containers. No values/stdout/remote upload, no live exchange credentials.
- New root-only 0600 EnvironmentFiles; source remains untouched.
- Three new strategy units restarted paused to load their keys. Brain exit sidecar,
  public web, all old services and historical data are NEVER restarted or changed.
- No model/provider calls. A key being present does not prove its validity/credit.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

DEST = Path("/etc/superbot-v3-paper")
RUNS = {
    "hawk": Path("/opt/superbot-v3-paper-runs/classic-hawk-paper20261111"),
    "bull": Path("/opt/superbot-v3-paper-runs/classic-bull-paper20261111"),
    "brain": Path("/opt/superbot-v3-paper-runs/brain-v3-paper20261111"),
}
PROVIDERS = (
    ("hawk", "superbot-desk-hawk", "superbot-v3-paper-falco.service",
     "falco-ai.env", "ANTHROPIC_API_KEY"),
    ("bull", "superbot-desk-bull", "superbot-v3-paper-toro.service",
     "toro-ai.env", "ANTHROPIC_API_KEY"),
    ("brain", "superbot-brain-free", "superbot-v3-paper-brain-runner.service",
     "brain-ai.env", "DEEPSEEK_API_KEY"),
)
BRAIN_EXIT = "superbot-v3-paper-brain-exit.service"
LEGACY_EXITS = ("superbot-v3-falco-exit.service",
                "superbot-v3-toro-exit.service")
ALLOWED_KEY_VALUE = re.compile(r"[A-Za-z0-9_.=-]{20,1024}\Z")


def fail(reason: str) -> None:
    print("RC84_AI_PAUSED_REFUSED=" + reason, flush=True)
    raise SystemExit(2)


def capture(*argv: str, timeout: int = 12) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        fail("REQUIRED_LOCAL_COMMAND_UNAVAILABLE")


def service_active(service: str) -> bool:
    return capture("systemctl", "is-active", "--quiet", service).returncode == 0


def assert_paused() -> None:
    for name, path in RUNS.items():
        if (not path.is_dir() or path.is_symlink()
                or not (path / "pause.flag").is_file()
                or (path / "pause.flag").is_symlink()):
            fail("WALLET_NOT_PAUSED_" + name.upper())
        marker = path / "PREPARED_PAUSED_ONLY.json"
        try:
            data = json.loads(marker.read_text())
        except (OSError, ValueError):
            fail("RUN_MARKER_UNAVAILABLE_" + name.upper())
        if data.get("paper_only") is not True or data.get("paused") is not True:
            fail("RUN_NOT_DECLARED_PAPER_PAUSED_" + name.upper())
    brain = RUNS["brain"]
    try:
        mandate = json.loads((brain / "mandate.json").read_text())
    except (OSError, ValueError):
        fail("BRAIN_MANDATE_MISSING")
    if mandate.get("approved") is not False:
        fail("BRAIN_MANDATE_APPROVED")
    if not service_active(BRAIN_EXIT):
        fail("BRAIN_EXIT_NOT_ACTIVE")
    for service in LEGACY_EXITS:
        if not service_active(service):
            fail("LEGACY_EXIT_NOT_ACTIVE")
    for _, _, service, _, _ in PROVIDERS:
        if not service_active(service):
            fail("NEW_PAPER_STRATEGY_UNIT_NOT_ACTIVE")
    print("RC84_AI_THREE_WALLETS_PAUSED_AND_EXIT_HEALTHY=PASS", flush=True)


def get_key_from_stopped_container(container: str, key: str) -> str:
    # docker inspect's stdout is CAPTURED and never emitted to Actions logs.
    cp = capture("docker", "inspect", container)
    if cp.returncode != 0:
        fail("LEGACY_SOURCE_UNAVAILABLE")
    try:
        info = json.loads(cp.stdout)[0]
    except (ValueError, IndexError, TypeError):
        fail("LEGACY_SOURCE_METADATA_INVALID")
    if info.get("State", {}).get("Running") is not False:
        fail("LEGACY_SOURCE_IS_RUNNING")
    values = {}
    for pair in info.get("Config", {}).get("Env", []) or []:
        if "=" in pair:
            name, val = pair.split("=", 1)
            values[name] = val
    if values.get("DESK_MODE") != "paper":
        fail("LEGACY_SOURCE_NOT_PAPER")
    value = values.get(key, "")
    if not isinstance(value, str) or not ALLOWED_KEY_VALUE.fullmatch(value):
        fail("LEGACY_PROVIDER_KEY_MISSING_OR_UNSAFE_FORMAT")
    return value


def prepare() -> list[tuple[str, str, str, str]]:
    assert_paused()
    if DEST.is_symlink():
        fail("PRIVATE_ENV_DIRECTORY_SYMLINK")
    if DEST.exists():
        st = DEST.stat()
        if (not stat.S_ISDIR(st.st_mode) or (st.st_mode & 0o077)
                or st.st_uid != 0):
            fail("PRIVATE_ENV_DIRECTORY_UNSAFE")
    targets = []
    for label, old_container, service, filename, key in PROVIDERS:
        path = DEST / filename
        if path.exists() or path.is_symlink():
            fail("TARGET_FILE_ALREADY_EXISTS_" + label.upper())
        value = get_key_from_stopped_container(old_container, key)
        targets.append((filename, key, value, service))
    print("RC84_AI_CLAUDE_FALCO_TORO_SOURCE_PRESENT=True", flush=True)
    print("RC84_AI_DEEPSEEK_BRAIN_SOURCE_PRESENT=True", flush=True)
    print("RC84_AI_THREE_NEW_TARGETS_AVAILABLE=True", flush=True)
    return targets


def write_private_files(targets: list[tuple[str, str, str, str]]) -> list[Path]:
    created: list[Path] = []
    try:
        if not DEST.exists():
            DEST.mkdir(mode=0o700)
        if DEST.stat().st_mode & 0o077:
            fail("PRIVATE_ENV_DIRECTORY_LOST_MODE")
        for filename, key, value, _ in targets:
            p = DEST / filename
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(p, flags, 0o600)
            created.append(p)
            with os.fdopen(fd, "wb") as out:
                out.write((key + "=" + value + "\n").encode("ascii"))
                out.flush()
                os.fsync(out.fileno())
            st = p.stat()
            if st.st_uid != 0 or stat.S_IMODE(st.st_mode) != 0o600:
                fail("SECRET_FILE_PERMISSIONS_UNSAFE")
        # The values are never output. Compare in memory to verify file integrity.
        for filename, key, value, _ in targets:
            text = (DEST / filename).read_text(encoding="ascii")
            if text != (key + "=" + value + "\n"):
                fail("PRIVATE_KEY_FILE_CONTENT_MISMATCH")
        return created
    except BaseException:
        for p in created:
            try:
                p.unlink()
            except OSError:
                pass
        raise


def runtime_has_same_key(service: str, key: str, value: str) -> bool:
    p = capture("systemctl", "show", service, "--property=MainPID", "--value")
    try:
        pid = int(p.stdout.strip())
        if p.returncode or pid < 2:
            return False
        # Only key equality checked. NEVER print /proc/PID/environ or secret bytes.
        data = Path(f"/proc/{pid}/environ").read_bytes()
        target = (key + "=" + value).encode("ascii")
        return target in data.split(b"\0")
    except (ValueError, OSError):
        return False


def safe_heartbeat() -> bool:
    try:
        import time
        t = time.time()
        for name in ("hawk", "bull"):
            h = json.loads((RUNS[name] / "heartbeat.json").read_text())
            if (h.get("mode") != "paused" or h.get("exec_mode") != "paper"
                    or h.get("open_positions") != 0
                    or not (0 <= t - float(h["ts"]) < 120)):
                return False
        brain = json.loads((RUNS["brain"] / "heartbeat.json").read_text())
        if (brain.get("state") not in ("halted", "paused")
                or not (0 <= t * 1000 - int(brain["ts_ms"]) < 120000)):
            return False
        exit_beat = json.loads((RUNS["brain"] / "exit_heartbeat.json").read_text())
        if exit_beat.get("state") != "healthy" or exit_beat.get("last_error") is not None:
            return False
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply-paused", action="store_true")
    args = parser.parse_args()

    targets = prepare()
    if args.check:
        print("RC84_AI_PRECHECK_PASS_NO_FILES_WRITTEN=True", flush=True)
        return

    write_private_files(targets)
    print("RC84_AI_PROVIDER_KEYS_INSTALLED_ROOT_0600=3", flush=True)
    print("RC84_AI_NO_EXCHANGE_KEYS_OR_MODEL_CALLS=True", flush=True)

    # Existing systemd units read EnvironmentFile only at service exec.
    # Do NOT restart web or Brain exit sidecar, or any LEGACY unit.
    for filename, key, value, service in targets:
        assert_paused()
        cp = capture("systemctl", "restart", service, timeout=30)
        if cp.returncode:
            fail("NEW_PAUSED_STRATEGY_RESTART_FAILED")
        if not service_active(service):
            fail("NEW_PAUSED_STRATEGY_NOT_RUNNING")
    time.sleep(10)
    for filename, key, value, service in targets:
        if not runtime_has_same_key(service, key, value):
            fail("PROVIDER_KEY_NOT_LOADED_IN_NEW_PROCESS")
    assert_paused()
    if not safe_heartbeat():
        fail("PAUSED_HEARTBEAT_NOT_HEALTHY")
    print("RC84_AI_CLAUDE_FALCO_LOADED_AND_PAUSED=True", flush=True)
    print("RC84_AI_CLAUDE_TORO_LOADED_AND_PAUSED=True", flush=True)
    print("RC84_AI_DEEPSEEK_BRAIN_LOADED_AND_PAUSED=True", flush=True)
    print("RC84_AI_ALL_THREE_HEARTBEATS_PAUSED=PASS", flush=True)
    print("RC84_AI_BRAIN_EXIT_AND_LEGACY_UNCHANGED=True", flush=True)
    print("RC84_AI_KEYS_NOT_PRINTED_OR_UPLOADED=True", flush=True)
    print("RC84_AI_ZERO_PROVIDER_REQUESTS_AND_ZERO_TRADES=True", flush=True)


if __name__ == "__main__":
    main()
