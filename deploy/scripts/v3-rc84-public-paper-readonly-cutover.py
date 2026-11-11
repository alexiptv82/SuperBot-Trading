#!/usr/bin/env python3
"""RC84 controlled PUBLIC WEB cutover; never opens/closes any trades.

Creates a new backend image from pinned RC84 code, preserves the EXISTING
authentication SQLite database, backups, current web container and static assets.
It does not touch systemd bot services, old history, pause flags or Brain mandate.

Default --preflight-only: no writes. Explicit --publish-readonly: cutover with
rollback. NO closes enabled yet (all new wallets are paused and have zero trades).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

PIN = "0e29a73a36f668643da4088178bacb8616a45ac0"
STAGE = Path("/opt/superbot-v3-rc84-stage")
PREVIEW = Path("/opt/superbot-v3-rc84-ui-preview")
WEB = Path("/opt/superbot-web")
DB = Path("/opt/superbot/data/superbot.db")
ROOT = Path("/opt/superbot-v3-paper-runs")
HAWK = ROOT / "classic-hawk-paper20261111"
BULL = ROOT / "classic-bull-paper20261111"
BRAIN = ROOT / "brain-v3-paper20261111"
RUN_ID = "brain-v3-paper20261111"
IMAGE = "superbot:rc84-0e29a73a"
NAME = "superbot"
PREVIOUS = "superbot-rc84-previous"
PREV_BUILD = WEB / "build.rc84-previous"
NEXT_BUILD = WEB / "build.rc84-new"
FAILED_BUILD = WEB / "build.rc84-failed"

class Refused(RuntimeError):
    pass


def refuse(reason: str) -> None:
    raise Refused(reason)


def command(*args: str, timeout: int = 35, allow_error: bool = False) -> str:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        refuse("tool_unavailable")
    if p.returncode and not allow_error:
        refuse("external_command_failed_" + args[0])
    return p.stdout.strip() if p.returncode == 0 else ""


def docker(*args: str, timeout: int = 35) -> str:
    return command("docker", *args, timeout=timeout)


def inspected(container: str) -> dict | None:
    raw = command("docker", "inspect", container, timeout=10, allow_error=True)
    if not raw:
        return None
    try:
        value = json.loads(raw)
        if isinstance(value, list) and len(value) == 1:
            return value[0]
    except (ValueError, TypeError, IndexError):
        pass
    refuse("invalid_docker_inspection")


def regular(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def http(path: str, *, method: str = "GET") -> int:
    try:
        req = urllib.request.Request("http://127.0.0.1:8002" + path, method=method)
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as e:
        return e.code
    except (OSError, ValueError):
        return 0


def verify_web() -> None:
    if http("/api/health") != 200:
        refuse("web_health_failed")
    if http("/api/v3/overview") != 401:
        refuse("v3_view_unauthenticated")
    if http("/api/auth/password-status") != 401:
        refuse("auth_view_unprotected")
    for path in (
        "/api/desk/close-position",
        "/api/desk/bull/close-position",
        "/api/desk/close-all",
        "/api/desk/bull/close-all",
        "/api/desk/resume",
        "/api/desk/bull/resume",
        "/api/v3/brain/close",
    ):
        if http(path, method="POST") != 423:
            refuse("mutation_not_blocked_" + path.replace("/", "_"))
    if http("/api/health") != 200:
        refuse("post_verification_web_not_healthy")


def verify_identity() -> None:
    # Run the separately audited, RO, PINNED preflight before any write.
    path = Path(__file__).with_name("v3-rc84-public-readonly-cutover-preflight.py")
    if not regular(path):
        refuse("preflight_file_missing")
    p = subprocess.run(
        [sys.executable, "-I", str(path)], text=True, capture_output=True, timeout=30,
        check=False, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    # This subprocess prints only fixed, nonsecret status codes, never environment values.
    if p.returncode != 0 or "RC84_CUTOVER_READONLY_PREFLIGHT=PASS" not in p.stdout:
        refuse("readonly_preflight_failed")
    print("RC84_PUBLIC_ROLLBACK_PREFLIGHT=PASS", flush=True)


def backup_auth_db() -> Path:
    backup_root = Path("/opt/superbot-backups")
    if not backup_root.is_dir() or backup_root.is_symlink():
        refuse("backup_root_missing")
    folder = backup_root / ("rc84-auth-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + str(os.getpid()))
    folder.mkdir(mode=0o700)
    dst = folder / "superbot.db"
    src_conn = out_conn = None
    try:
        src_conn = sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True, timeout=15)
        src_conn.execute("PRAGMA query_only=ON")
        out_conn = sqlite3.connect(dst)
        src_conn.backup(out_conn)
        if out_conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            refuse("auth_backup_integrity_failed")
        table_names = {r[0] for r in out_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"auth_settings", "trades"}.issubset(table_names):
            refuse("auth_backup_schema_changed")
        out_conn.close()
        out_conn = None
        src_conn.close()
        src_conn = None
        dst.chmod(0o600)
        check = sqlite3.connect(dst.as_uri() + "?mode=ro", uri=True)
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                refuse("auth_restore_rehearsal_failed")
        finally:
            check.close()
    finally:
        if out_conn is not None:
            out_conn.close()
        if src_conn is not None:
            src_conn.close()
    print("RC84_AUTH_SQLITE_BACKUP_AND_RESTORE_CHECK=PASS", flush=True)
    return folder


def env_file(old: dict) -> Path:
    # Reuse the EXISTING dashboard's environment, but enforce the NEW PAPER
    # run identities and prohibit every direct exchange-order credential.
    changes = {
        "TRADING_MODE": "paper",
        "DESK_MODE": "paper",
        "TELEGRAM_COMMANDS_ENABLED": "false",
        "V3_CUTOVER_READONLY": "1",
        "V3_ALLOW_CLASSIC_SINGLE_CLOSE": "0",
        "V3_ALLOW_BRAIN_SINGLE_CLOSE": "0",
        "V3_BRAIN_PEER_OBSERVATIONS": "disabled",
        "DB_PATH": "/app/data/superbot.db",
        "DESK_DATA_DIR": str(HAWK),
        "DESK_DATA_DIR_BULL": str(BULL),
        "DESK_HAWK_CAPITAL": "1000",
        "DESK_BULL_CAPITAL": "1000",
        "V3_RUN_ID": RUN_ID,
        "V3_JOURNAL_PATH": str(BRAIN / "journal.db"),
        "V3_BUDGET_DB_PATH": str(BRAIN / "budget.db"),
        "V3_HEARTBEAT_PATH": str(BRAIN / "heartbeat.json"),
        "V3_PAUSE_FLAG_PATH": str(BRAIN / "pause.flag"),
        "V3_RUNNER_CONFIG_PATH": str(BRAIN / "runner_config.json"),
        "V3_CLOSE_REQUEST_PATH": str(BRAIN / "close_request.json"),
        "V3_CLOSE_RESULT_PATH": str(BRAIN / "close_result.json"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    env = {}
    for item in old["Config"].get("Env") or []:
        if "=" not in item:
            refuse("old_env_invalid")
        key, value = item.split("=", 1)
        if not key.replace("_", "").isalnum() or any(c in value for c in "\n\r\0"):
            refuse("old_env_invalid")
        if key.startswith(("BITGET_API_", "BITGET_SECRET_", "BITGET_PASSPHRASE")):
            continue
        if key not in changes:
            env[key] = value
    env.update(changes)
    fd, name = tempfile.mkstemp(prefix=".rc84-public-web-", dir="/run")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as file:
            for key, value in sorted(env.items()):
                if any(c in value for c in "\n\r\0"):
                    refuse("unsafe_environment_value")
                file.write(key + "=" + value + "\n")
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
    return Path(name)


def mounts(old: dict) -> list[str]:
    output = []
    dests = set()
    for mount in old.get("Mounts") or []:
        kind = mount.get("Type")
        src = mount.get("Source") if kind == "bind" else mount.get("Name")
        dest = mount.get("Destination")
        if kind not in ("bind", "volume") or not src or not dest or not dest.startswith("/"):
            refuse("original_mount_invalid")
        if ":" in src + dest or "docker.sock" in dest or dest in dests:
            refuse("unsafe_or_duplicate_mount")
        dests.add(dest)
        output.extend(("-v", str(src) + ":" + dest + (":rw" if mount.get("RW") else ":ro")))
    if not {"/app/data", "/app/backend/.env"}.issubset(dests):
        refuse("required_original_login_mount_missing")
    for path in (HAWK, BULL, BRAIN):
        dest = str(path)
        if dest in dests:
            refuse("new_run_already_mounted")
        output.extend(("-v", dest + ":" + dest + ":ro"))
    return output


def rollback(*, old_renamed: bool, new_created: bool, web_changed: bool) -> None:
    print("RC84_ROLLBACK_INITIATED=True", flush=True)
    try:
        if web_changed and PREV_BUILD.is_dir():
            if (WEB / "build").exists():
                if FAILED_BUILD.exists():
                    refuse("failed_build_name_already_exists")
                (WEB / "build").replace(FAILED_BUILD)
            PREV_BUILD.replace(WEB / "build")
        if new_created:
            subprocess.run(("docker", "rm", "-f", NAME), stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=35)
        if old_renamed:
            subprocess.run(("docker", "update", "--restart", "always", PREVIOUS),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            docker("rename", PREVIOUS, NAME, timeout=20)
            if not inspected(NAME)["State"]["Running"]:
                docker("start", NAME, timeout=35)
        time.sleep(2)
        print("RC84_ROLLBACK_RC73_HEALTHY=" + str(http("/api/health") == 200), flush=True)
    except BaseException:
        print("RC84_ROLLBACK_REQUIRES_OPERATOR=True", flush=True)
        raise


def publish() -> None:
    # Important: no transactions or trading engine touches; the four PAPER
    # strategy systemd units and the new Brain exit-owner remain untouched.
    code = command("git", "-C", str(STAGE), "rev-parse", "HEAD", timeout=10)
    if code != PIN:
        refuse("pin_changed")
    image = IMAGE
    docker("build", "--pull=false", "--quiet", "-t", image,
           "-f", str(STAGE / "Dockerfile"), str(STAGE), timeout=300)
    shutil.copytree(PREVIEW / "frontend", NEXT_BUILD, symlinks=False)
    if not regular(NEXT_BUILD / "index.html"):
        refuse("staged_frontend_invalid")
    print("RC84_PINNED_PUBLIC_CANDIDATE_READY=True", flush=True)

    backup = backup_auth_db()
    old = inspected(NAME)
    if old is None or old.get("State", {}).get("Running") is not True:
        refuse("original_container_unavailable")
    if old.get("HostConfig", {}).get("RestartPolicy", {}).get("Name") != "always":
        refuse("original_restart_policy_changed")
    bindings = old.get("HostConfig", {}).get("PortBindings", {}).get("8001/tcp") or []
    if len(bindings) != 1 or bindings[0].get("HostIp") != "127.0.0.1" or bindings[0].get("HostPort") != "8002":
        refuse("original_port_unexpected")
    mountflags = mounts(old)
    private_env = env_file(old)
    old_renamed = new_created = web_changed = completed = False
    try:
        docker("rename", NAME, PREVIOUS, timeout=20)
        old_renamed = True
        docker("stop", "-t", "12", PREVIOUS, timeout=28)
        args = [
            "create", "--name", NAME, "--restart", "no",
            "--security-opt", "no-new-privileges:true",
            "-p", "127.0.0.1:8002:8001",
            "--env-file", str(private_env),
        ]
        args.extend(mountflags)
        args.append(image)
        docker(*args, timeout=35)
        new_created = True
        docker("start", NAME, timeout=35)
        ok = False
        for _ in range(15):
            time.sleep(2)
            try:
                verify_web()
                ok = True
                break
            except Refused:
                pass
        if not ok:
            refuse("new_authenticated_backend_failed")
        print("RC84_NEW_PAPER_WEB_GATES=PASS", flush=True)
        (WEB / "build").replace(PREV_BUILD)
        web_changed = True
        NEXT_BUILD.replace(WEB / "build")
        if sha256(WEB / "build/index.html") != sha256(PREVIEW / "frontend/index.html"):
            refuse("frontend_mismatch")
        verify_web()
        fresh = inspected(NAME)
        if fresh is None:
            refuse("new_container_missing")
        live_env = dict(s.split("=",1) for s in fresh["Config"]["Env"] if "=" in s)
        for key, value in {
            "DESK_MODE":"paper", "TRADING_MODE":"paper", "V3_CUTOVER_READONLY":"1",
            "V3_ALLOW_CLASSIC_SINGLE_CLOSE":"0", "V3_ALLOW_BRAIN_SINGLE_CLOSE":"0",
            "V3_RUN_ID":RUN_ID, "DESK_DATA_DIR":str(HAWK),
            "DESK_DATA_DIR_BULL":str(BULL),
        }.items():
            if live_env.get(key) != value:
                refuse("new_environment_drift")
        for path in (HAWK, BULL, BRAIN):
            live_mounts = fresh.get("Mounts", [])
            if not any(m.get("Source") == str(path) and m.get("RW") is False for m in live_mounts):
                refuse("new_paper_mount_not_ro")
            if not (path / "pause.flag").is_file():
                refuse("paper_wallet_unpaused")
        mandate = json.loads((BRAIN / "mandate.json").read_text())
        if mandate.get("approved") is not False:
            refuse("brain_mandate_changed")

        docker("update", "--restart", "always", NAME, timeout=15)
        docker("update", "--restart", "no", PREVIOUS, timeout=15)
        completed = True
        report = {
            "schema": "rc84-paper-public-web-readonly-cutover-v1",
            "release_sha": PIN,
            "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "auth_backup_done": regular(backup / "superbot.db"),
            "old_web_available": True, "old_frontend_available": True,
            "all_new_runs_paused": True, "brain_mandate_approved": False,
            "manual_closes_temporarily_disabled": True,
            "model_requests_sent": False, "trading_workers_changed": False,
        }
        marker = Path("/opt/superbot-v3-rc84-ui-preview/rc84-public-cutover.json")
        marker.write_text(json.dumps(report, sort_keys=True) + "\n")
        marker.chmod(0o600)
        print("RC84_PUBLIC_WEB_ROLLOUT=PASS", flush=True)
        print("RC84_NEW_PAPER_RUNS_VISIBLE_UNDER_AUTH=True", flush=True)
        print("RC84_NO_PAPER_UNPAUSE_OR_PROVIDER_CALLS=True", flush=True)
        print("RC84_OLD_RC73_WEB_RETAINED_FOR_ROLLBACK=True", flush=True)
    finally:
        private_env.unlink(missing_ok=True)
        if not completed:
            rollback(old_renamed=old_renamed, new_created=new_created, web_changed=web_changed)



def recover_aborted_staging_only() -> None:
    """Remove only the failed, never-published RC84 candidate frontend.

    Does not touch /opt/superbot-web/build or any Docker container.
    Refuses if the current web is not the original RC73 or if a cutover began.
    """
    old = inspected(NAME)
    if old is None or old.get("State", {}).get("Running") is not True:
        refuse("recover_original_web_not_running")
    if inspected(PREVIOUS) is not None:
        refuse("recover_previous_container_exists")
    if (PREV_BUILD.exists() or PREV_BUILD.is_symlink()
            or FAILED_BUILD.exists() or FAILED_BUILD.is_symlink()):
        refuse("recover_rollback_folder_exists")
    if not regular(WEB / "build/index.html") or http("/api/health") != 200:
        refuse("recover_original_web_unhealthy")
    if not NEXT_BUILD.is_dir() or NEXT_BUILD.is_symlink():
        refuse("recover_candidate_not_directory")
    if not regular(NEXT_BUILD / "index.html") or not regular(PREVIEW / "frontend/index.html"):
        refuse("recover_candidate_index_missing")
    if sha256(NEXT_BUILD / "index.html") != sha256(PREVIEW / "frontend/index.html"):
        refuse("recover_candidate_not_pinned_preview")
    # This directory is a temporary copy created by the first, aborted attempt.
    # It was never published; the live frontend under WEB/build is untouched.
    shutil.rmtree(NEXT_BUILD)
    print("RC84_ABORTED_ONLY_CANDIDATE_REMOVED=True", flush=True)
    print("RC84_RC73_PUBLIC_WEB_UNCHANGED=True", flush=True)


def main() -> None:
    p = argparse.ArgumentParser()
    exclusive = p.add_mutually_exclusive_group(required=True)
    exclusive.add_argument("--preflight-only", action="store_true")
    exclusive.add_argument("--publish-readonly", action="store_true")
    exclusive.add_argument("--recover-aborted-candidate", action="store_true")
    args = p.parse_args()
    if args.recover_aborted_candidate:
        recover_aborted_staging_only()
        return
    verify_identity()
    if args.preflight_only:
        print("RC84_PUBLIC_CUTOVER_DRY_RUN=PASS", flush=True)
        return
    publish()


if __name__ == "__main__":
    try:
        main()
    except Refused as e:
        print("RC84_PUBLIC_CUTOVER_REFUSED=" + str(e), file=sys.stderr, flush=True)
        raise SystemExit(2)
