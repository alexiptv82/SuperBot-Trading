#!/usr/bin/env python3
"""Replace expired Claude API key on Falco/Toro safely from operator's terminal.

Use only on the Singapore VPS AS ROOT, from an interactive SSH TTY. Do not run
under GitHub Actions, send keys in chat, shell history, scripts or repositories.

Validates the new key with GET /v1/models (NO inference), then atomically writes
ONLY both root-owned Claude EnvironmentFiles, restarts only two PAUSED strategy
services, verifies loaded key and PAPER pauses. Rolls old files back on failure.
No account resets, no exchange access, no model generation, no Brain changes.
"""
from __future__ import annotations
import getpass
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

RUNS = (
    Path("/opt/superbot-v3-paper-runs/classic-hawk-paper20261111"),
    Path("/opt/superbot-v3-paper-runs/classic-bull-paper20261111"),
    Path("/opt/superbot-v3-paper-runs/brain-v3-paper20261111"),
)
FILE_DIR = Path("/etc/superbot-v3-paper")
TARGETS = (
    (FILE_DIR / "falco-ai.env", "superbot-v3-paper-falco.service"),
    (FILE_DIR / "toro-ai.env", "superbot-v3-paper-toro.service"),
)
PROVIDER_NAME = "ANTHROPIC_API_KEY"
EXPECTED = re.compile(r"[A-Za-z0-9_.=-]{20,1024}\Z")


class KeyUpdateError(Exception):
    pass


def fail(code: str) -> None:
    raise KeyUpdateError(code)


def run(*args: str, timeout: int = 30) -> bool:
    try:
        p = subprocess.run(args, timeout=timeout, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
        return p.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ensure_safe() -> None:
    if os.geteuid() != 0 or not sys.stdin.isatty():
        fail("RUN_FROM_INTERACTIVE_ROOT_SSH_ONLY")
    for p in RUNS:
        if (p.is_symlink() or not p.is_dir() or not (p / "pause.flag").is_file()
                or (p / "pause.flag").is_symlink()):
            fail("WALLET_NOT_PAUSED")
        marker = p / "PREPARED_PAUSED_ONLY.json"
        try:
            m = json.loads(marker.read_text())
            if m.get("paper_only") is not True or m.get("paused") is not True:
                fail("WALLET_NOT_PAPER")
        except (OSError, ValueError):
            fail("WALLET_MARKER_INVALID")
    try:
        mandate = json.loads((RUNS[2] / "mandate.json").read_text())
        if mandate.get("approved") is not False:
            fail("BRAIN_MANDATE_APPROVED")
    except (OSError, ValueError):
        fail("BRAIN_MANDATE_INVALID")
    if FILE_DIR.is_symlink() or not FILE_DIR.is_dir():
        fail("KEY_DIRECTORY_MISSING")
    st = FILE_DIR.stat()
    if st.st_uid != 0 or (st.st_mode & 0o077):
        fail("KEY_DIRECTORY_UNSAFE")
    for path, service in TARGETS:
        if path.is_symlink() or not path.is_file():
            fail("KEY_FILE_NOT_REGULAR")
        st = path.stat()
        if (st.st_uid != 0 or stat.S_IMODE(st.st_mode) != 0o600
                or st.st_size > 8192):
            fail("KEY_FILE_UNSAFE")
        if not run("systemctl", "is-active", "--quiet", service):
            fail("CLASSIC_SERVICE_NOT_ACTIVE")


def validate_new_api_key(key: str) -> bool:
    # No model generation; only public model metadata with authenticated GET.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/models?limit=1",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "accept": "application/json"},
        method="GET",
    )
    try:
        with opener.open(request, timeout=12) as response:
            if response.status != 200:
                return False
            body = response.read(8192)
            data = json.loads(body)
            return isinstance(data, dict) and isinstance(data.get("data"), list)
    except (urllib.error.HTTPError, OSError, ValueError, TimeoutError):
        return False


def validate_old(old: bytes) -> None:
    try:
        s = old.decode("ascii").strip()
    except UnicodeError:
        fail("OLD_KEY_ENCODING_UNSAFE")
    if not s.startswith(PROVIDER_NAME + "=") or "\n" in s or "\r" in s:
        fail("OLD_KEY_FILE_UNEXPECTED_CONTENT")
    if not EXPECTED.fullmatch(s.split("=", 1)[1]):
        fail("OLD_KEY_FILE_UNEXPECTED_FORMAT")


def atomic_write(path: Path, data: bytes) -> None:
    # No symlinks, never creates a private key backup anywhere public.
    temp = path.with_name("." + path.name + ".replacement-" + str(os.getpid()))
    if temp.exists() or temp.is_symlink():
        fail("PRIVATE_TEMP_NAME_OCCUPIED")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def loaded(service: str, key: str) -> bool:
    # Boolean equality only; never expose process environ or key content.
    try:
        p = subprocess.run(["systemctl", "show", service, "--property=MainPID",
                            "--value"], capture_output=True, timeout=8)
        pid = int(p.stdout.strip()) if p.returncode == 0 else 0
        if pid < 2:
            return False
        return (PROVIDER_NAME + "=" + key).encode("ascii") in (
            Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"))
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def main() -> None:
    ensure_safe()
    old = {}
    for path, _ in TARGETS:
        old[path] = path.read_bytes()
        validate_old(old[path])
    print("RC84_CLAUDE_NEW_KEY_REPLACE_PREFLIGHT=PASS", flush=True)
    print("Inserisci una NUOVA API key Anthropic valida (non apparira' sullo schermo).")
    try:
        key = getpass.getpass("Claude API key: ")
    except (OSError, EOFError):
        fail("TTY_KEY_INPUT_UNAVAILABLE")
    if not EXPECTED.fullmatch(key):
        fail("NEW_KEY_FORMAT_INVALID")
    if any(old_file == (PROVIDER_NAME + "=" + key + "\n").encode("ascii")
           for old_file in old.values()):
        fail("NEW_KEY_SAME_AS_REJECTED_OLD_KEY")
    if not validate_new_api_key(key):
        fail("NEW_KEY_NOT_ACCEPTED_BY_ANTHROPIC")
    print("RC84_CLAUDE_NEW_KEY_MODELS_HTTP_200=PASS", flush=True)
    new_data = (PROVIDER_NAME + "=" + key + "\n").encode("ascii")
    changed = []
    try:
        ensure_safe()
        for path, _ in TARGETS:
            atomic_write(path, new_data)
            changed.append(path)
        for _, service in TARGETS:
            if not run("systemctl", "restart", service):
                fail("PAUSED_CLASSIC_SERVICE_RESTART_FAILED")
            if not run("systemctl", "is-active", "--quiet", service):
                fail("PAUSED_CLASSIC_SERVICE_INACTIVE")
        for _, service in TARGETS:
            if not loaded(service, key):
                fail("NEW_KEY_NOT_LOADED_IN_CLASSIC_PROCESS")
        ensure_safe()
        print("RC84_CLAUDE_NEW_KEY_LOADED_FALCO_AND_TORO=True", flush=True)
        print("RC84_CLAUDE_ALL_BOTS_REMAIN_PAUSED=True", flush=True)
        print("RC84_CLAUDE_NO_MODEL_GENERATION_OR_TRADES=True", flush=True)
        print("RC84_CLAUDE_NEW_KEY_VALUES_NOT_LOGGED=True", flush=True)
        print("RC84_CLAUDE_REKEY_COMPLETED=PASS", flush=True)
    except BaseException:
        for path in changed:
            try:
                atomic_write(path, old[path])
            except OSError:
                print("RC84_CLAUDE_ROLLBACK_FILE_FAILED", flush=True)
        for _, service in TARGETS:
            run("systemctl", "restart", service)
        print("RC84_CLAUDE_KEY_CHANGE_FAILED_OLD_FILES_RESTORED_ATTEMPTED=True",
              flush=True)
        raise


if __name__ == "__main__":
    try:
        main()
    except KeyUpdateError as e:
        print("RC84_CLAUDE_KEY_REPLACEMENT_REFUSED=" + str(e), flush=True)
        sys.exit(2)
