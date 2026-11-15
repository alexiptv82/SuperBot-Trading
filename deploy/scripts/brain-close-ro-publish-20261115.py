#!/usr/bin/env python3
"""Brain PAPER: atomic web-only rollout of the already built O_RDONLY image.

--preflight: read-only diagnostic; --publish: replaces ONLY Docker container
'superbot', preserving old container (renamed, stopped) for rollback.
Fail-closed on unexpected image/config/mounts; auto-rollback on failure.
Never touches systemd workers, journal or trading settings.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

LIVE = "superbot"
BACKUP = "superbot-before-brain-close-ro-20261115"
OLD_TAG = "superbot:rc84-paper-single-close-20261111"
OLD_ID = "sha256:61a6a8ca908570dcd57e9efbe05e8af074b56e4583bcc87fd31e7bb5c2bc9b89"
NEW_TAG = "superbot:brain-close-ro-candidate-20261115"
NEW_ID = "sha256:bb914acdb7d02b55f6c51a27351fa98f69503d5632826af67758e1c11d501366"
HEALTH = "http://127.0.0.1:8002"
BRAIN_RUN = "/opt/superbot-v3-paper-runs/brain-v3-paper20261111"
UNITS = ("superbot-v3-paper-brain-runner", "superbot-v3-paper-brain-exit",
         "superbot-v3-paper-single-close-bridge")
EXPECTED_ENV = {
    "DESK_MODE": "paper", "TRADING_MODE": "paper",
    "V3_ALLOW_BRAIN_SINGLE_CLOSE": "1", "V3_CLOSE_BRIDGE_ONLY": "1",
    "V3_CUTOVER_READONLY": "1", "V3_RUN_ID": "brain-v3-paper20261111",
}
OLD_MARKER = 'flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)'
NEW_MARKER = 'flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)'


def say(key: str, value: object) -> None:
    print(f"BRAIN_CLOSE_PUBLISH {key}={value}", flush=True)


def cmd(*args: str, timeout: int = 45, allow_failure: bool = False) -> str:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("command_unavailable_" + args[0]) from exc
    if p.returncode and not allow_failure:
        raise RuntimeError("command_failed_" + args[0] + "_" + args[1] + "_" + str(p.returncode))
    return p.stdout.strip() if p.returncode == 0 else ""


def docker_inspect(name: str) -> dict | None:
    raw = cmd("docker", "inspect", name, allow_failure=True)
    if not raw:
        return None
    obj = json.loads(raw)
    if type(obj) is not list or len(obj) != 1:
        raise RuntimeError("invalid_docker_metadata")
    return obj[0]


def image_info(tag: str) -> dict:
    raw = cmd("docker", "image", "inspect", tag)
    obj = json.loads(raw)
    if type(obj) is not list or len(obj) != 1:
        raise RuntimeError("invalid_image_metadata")
    return obj[0]


def env_map(web: dict) -> dict:
    rows = web["Config"].get("Env", [])
    if type(rows) is not list or any(type(e) is not str or "=" not in e for e in rows):
        raise RuntimeError("invalid_env")
    return dict(x.split("=", 1) for x in rows)


def worker_pids() -> dict[str, str]:
    results = {}
    for u in UNITS:
        if cmd("systemctl", "is-active", u, allow_failure=True) != "active":
            raise RuntimeError("worker_not_active_" + u)
        pid = cmd("systemctl", "show", u, "-p", "MainPID", "--value")
        if not pid.isdecimal() or int(pid) <= 1:
            raise RuntimeError("invalid_worker_pid_" + u)
        results[u] = pid
    return results


def check_preflight() -> tuple[dict, dict[str, str]]:
    if os.geteuid() != 0:
        raise RuntimeError("root_required")
    if docker_inspect(BACKUP) is not None:
        raise RuntimeError("backup_name_already_exists")
    web = docker_inspect(LIVE)
    if web is None or web.get("State", {}).get("Running") is not True:
        raise RuntimeError("web_missing_or_stopped")
    if (web.get("Config", {}).get("Image") != OLD_TAG or web.get("Image") != OLD_ID
            or image_info(OLD_TAG).get("Id") != OLD_ID):
        raise RuntimeError("web_image_unexpected_or_tag_drift")
    if image_info(NEW_TAG).get("Id") != NEW_ID:
        raise RuntimeError("candidate_image_id_unexpected")
    e = env_map(web)
    if any(e.get(k) != v for k, v in EXPECTED_ENV.items()):
        raise RuntimeError("web_paper_gates_unexpected")
    host = web.get("HostConfig") or {}
    if (host.get("RestartPolicy", {}).get("Name") != "always"
            or host.get("NetworkMode") not in ("default", "bridge")
            or host.get("Privileged") is True or host.get("ReadonlyRootfs") is True
            or host.get("AutoRemove") is True):
        raise RuntimeError("unsupported_web_host_configuration")
    opts = host.get("SecurityOpt") or []
    if opts not in (["no-new-privileges:true"], ["no-new-privileges"]):
        raise RuntimeError("unexpected_security_options")
    bound = (host.get("PortBindings") or {}).get("8001/tcp") or []
    if (set((host.get("PortBindings") or {}).keys()) != {"8001/tcp"}
            or len(bound) != 1 or bound[0].get("HostIp") != "127.0.0.1"
            or bound[0].get("HostPort") != "8002"):
        raise RuntimeError("unexpected_web_port_mapping")
    if web.get("Config", {}).get("Entrypoint") != image_info(OLD_TAG)["Config"].get("Entrypoint"):
        raise RuntimeError("custom_entrypoint_unsupported")
    if web.get("Config", {}).get("Cmd") != image_info(OLD_TAG)["Config"].get("Cmd"):
        raise RuntimeError("custom_command_unsupported")
    mounts = web.get("Mounts") or []
    if not mounts or not any(m.get("Source") == BRAIN_RUN and m.get("RW") is False for m in mounts):
        raise RuntimeError("brain_run_mount_not_readonly")
    paths = [m.get("Destination") for m in mounts]
    if len(paths) != len(set(paths)):
        raise RuntimeError("duplicate_mount_destinations")
    for m in mounts:
        if m.get("Type") not in ("bind", "volume") or not m.get("Destination"):
            raise RuntimeError("unsupported_mount")
        src = m.get("Source") if m["Type"] == "bind" else m.get("Name")
        if (type(src) is not str or not src or any(ch in src + m["Destination"] for ch in "\n\r\0:")
                or "/var/run/docker.sock" in m["Destination"]):
            raise RuntimeError("unsafe_mount")
    for p in ("/app/data", "/app/backend/.env"):
        if p not in paths:
            raise RuntimeError("missing_original_web_mount_" + p)
    if cmd("curl", "-fsS", "--max-time", "5", HEALTH + "/api/health", allow_failure=True) == "":
        raise RuntimeError("web_not_healthy")
    services = worker_pids()
    code = (
        "from pathlib import Path; "
        "from backend.v3.runner import exit_service as e; "
        "s=Path(e.__file__).read_text(); "
        "assert s.count(" + repr(NEW_MARKER) + ")==1; "
        "assert s.count(" + repr(OLD_MARKER) + ")==0; "
        "print('PINNED_RO_PATCH_OK')"
    )
    result = cmd("docker", "run", "--rm", "--network", "none", "--read-only",
                 "--entrypoint", "python3", NEW_TAG, "-B", "-c", code, timeout=35)
    if "PINNED_RO_PATCH_OK" not in result:
        raise RuntimeError("candidate_patch_check_failed")
    say("preflight", "PASS")
    say("web_image_old", OLD_ID)
    say("candidate_image", NEW_ID)
    say("mounts_verified", len(mounts))
    say("worker_pids", ",".join(k + ":" + v for k, v in services.items()))
    return web, services


def fresh_env_file(env: dict):
    fd, filename = tempfile.mkstemp(prefix=".brain-close-ro-env-", dir="/run")
    os.fchmod(fd, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for k, v in sorted(env.items()):
                if (not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k)
                        or any(ch in v for ch in "\r\n\0")):
                    raise RuntimeError("unsafe_env_value")
                f.write(k + "=" + v + "\n")
            f.flush()
            os.fsync(f.fileno())
        return Path(filename)
    except BaseException:
        Path(filename).unlink(missing_ok=True)
        raise


def candidate_args(web: dict, env_file: Path) -> list[str]:
    args = ["docker", "create", "--name", LIVE, "--restart", "no",
            "--security-opt", "no-new-privileges:true",
            "-p", "127.0.0.1:8002:8001", "--env-file", str(env_file)]
    cfg = web.get("Config") or {}
    if cfg.get("User"):
        args += ["--user", cfg["User"]]
    if cfg.get("WorkingDir"):
        args += ["--workdir", cfg["WorkingDir"]]
    if cfg.get("Labels"):
        for key, val in sorted(cfg["Labels"].items()):
            if any(c in key + val for c in "\r\n\0"):
                raise RuntimeError("invalid_label")
            args += ["--label", key + "=" + val]
    for m in web["Mounts"]:
        src = m["Source"] if m["Type"] == "bind" else m["Name"]
        args += ["-v", src + ":" + m["Destination"] + (":rw" if m["RW"] else ":ro")]
    args.append(NEW_TAG)
    return args


def http_code(path: str, method: str = "GET", body: bytes | None = None) -> int:
    r = urllib.request.Request(HEALTH + path, method=method, data=body)
    try:
        with urllib.request.urlopen(r, timeout=4) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (OSError, TimeoutError):
        return 0


def web_ready() -> bool:
    if http_code("/api/health") != 200:
        return False
    for path in ("/api/v3/overview", "/api/v3/brain/config"):
        if http_code(path) != 401:
            return False
    for path in ("/api/desk/reset-portfolio", "/api/bot/start", "/api/desk/close-all"):
        if http_code(path, "POST", b"{}") != 423:
            return False
    if http_code("/api/v3/brain/close", "POST", b"{}") != 401:
        return False
    code = (
        "import time; from backend import v3_api as a; "
        "p=a.V3Paths.from_env('/nonexistent','/nonexistent'); "
        "assert a._brain_single_close_ready(p,int(time.time()*1000)) is True; "
        "print('WEB_CLOSE_ALLOWED_TRUE')"
    )
    try:
        result = cmd("docker", "exec", "-e", "PYTHONDONTWRITEBYTECODE=1", LIVE,
                     "python3", "-B", "-c", code, timeout=15)
        return "WEB_CLOSE_ALLOWED_TRUE" in result
    except RuntimeError:
        return False


def rollback(*, renamed: bool, new_maybe_created: bool) -> None:
    say("rollback", "START")
    try:
        if new_maybe_created and docker_inspect(LIVE):
            cmd("docker", "rm", "-f", LIVE, timeout=30)
        if renamed and docker_inspect(BACKUP):
            cmd("docker", "rename", BACKUP, LIVE)
            cmd("docker", "update", "--restart", "always", LIVE)
            if docker_inspect(LIVE)["State"]["Running"] is not True:
                cmd("docker", "start", LIVE)
        say("rollback", "DONE" if http_code("/api/health") == 200 else "MANUAL_CHECK_REQUIRED")
    except Exception as exc:
        say("rollback", "FAILED_" + type(exc).__name__ + "_CHECK_DOCKER")
        raise


def publish() -> None:
    web, pids = check_preflight()
    env_file = fresh_env_file(env_map(web))
    renamed = False
    new_maybe_created = False
    success = False
    try:
        args = candidate_args(web, env_file)
        # Before any interruption, confirm no state has changed since preflight.
        current = docker_inspect(LIVE)
        if current is None or current.get("Id") != web.get("Id") or worker_pids() != pids:
            raise RuntimeError("state_changed_since_preflight")
        cmd("docker", "rename", LIVE, BACKUP)
        renamed = True
        cmd("docker", "update", "--restart", "no", BACKUP)
        cmd("docker", "stop", "-t", "10", BACKUP, timeout=30)
        new_maybe_created = True  # even a failed create could leave a container behind
        cmd(*args, timeout=45)
        cmd("docker", "start", LIVE, timeout=45)
        good = False
        for _ in range(20):
            if web_ready():
                good = True
                break
            time.sleep(2)
        if not good:
            raise RuntimeError("new_web_readiness_failed")
        new = docker_inspect(LIVE)
        if (new is None or new.get("Image") != NEW_ID or new["State"]["Running"] is not True
                or worker_pids() != pids):
            raise RuntimeError("new_image_or_worker_identity_failed")
        original_mounts = {(m["Destination"], m["Type"], m["RW"], m["Source"]) for m in web["Mounts"]}
        new_mounts = {(m["Destination"], m["Type"], m["RW"], m["Source"]) for m in new["Mounts"]}
        if new_mounts != original_mounts:
            raise RuntimeError("new_mounts_differ")
        if any(env_map(new).get(k) != v for k, v in EXPECTED_ENV.items()):
            raise RuntimeError("new_paper_gates_differ")
        cmd("docker", "update", "--restart", "always", LIVE, timeout=20)
        # Preserve old container STOPPED and named BACKUP for rollback.
        success = True
        say("public_web", "UPDATED")
        say("web_close_allowed", "TRUE")
        say("workers_untouched", "TRUE")
        say("old_web_backup", BACKUP)
        say("trading_deploy", "NO")
    finally:
        env_file.unlink(missing_ok=True)
        if not success and renamed:
            rollback(renamed=renamed, new_maybe_created=new_maybe_created)


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    if args.publish:
        publish()
    else:
        check_preflight()
        say("web_untouched", "TRUE")
        say("publish_executed", "NO")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        say("RESULT", "REFUSED_" + type(exc).__name__ + ":" + str(exc)[:100])
        sys.exit(2)
