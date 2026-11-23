#!/usr/bin/env python3
"""Brain Unico: collega la web app (container `superbot`) e il canale di chiusura PAPER alla NUOVA run.

Stesso meccanismo del cutover Arena del 18/11 (in produzione): immagine candidata costruita sull'immagine IN USO
(nessun pull, dipendenze e login invariati) con il backend del commit revisionato; prova in un container usa-e-getta
senza rete e con mount in sola lettura; nuovo container creato PRIMA di fermare il vecchio e confrontato campo per
campo; vecchio container conservato fermo; rollback automatico se un controllo fallisce.

Cambiamenti rispetto alla web attuale, e nient'altro:
  - backend = albero `backend/` del commit indicato (git archive), sopra l'immagine in uso;
  - variabili V3_* del Brain -> nuova run `brain-v3-unico-paper-rc1` (run_id `brain-unico-paper-rc1`);
  - mount in SOLA LETTURA della nuova run (se non e' gia' visibile da un mount esistente).
Canale di chiusura (bridge RC84, unita' superbot-v3-paper-single-close-bridge): stessa unita' e stesse protezioni,
immagine = candidata, mount scrivibile della nuova run al posto della vecchia run del Brain, run scelta con
V3_BRIDGE_BRAIN_RUN_DIR / V3_BRIDGE_BRAIN_RUN_ID. Falco/Toro: mount e codice di chiusura invariati.
NON tocca: database di login, .env, nginx, Arena, runner/uscite di qualunque run, Falco, Toro, Brain storico.

Uso (root):  --deploy --source-root <laboratorio> --sha <commit 40 hex>   |   --rollback
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

LIVE = "superbot"
NEW_TMP = "superbot-brain-unico-web-new"
BACKUP = "superbot-before-brain-unico-web"
REJECTED_PREFIX = "superbot-brain-unico-web-rejected-"
BRIDGE_UNIT = "superbot-v3-paper-single-close-bridge.service"
BRIDGE_UNIT_PATH = Path("/etc/systemd/system") / BRIDGE_UNIT
BRIDGE_IMAGE_OLD = "superbot:rc84-paper-single-close-20261111"
SOCKET_DIR = "/run/superbot-paper-close"
RUN_ROOT = "/opt/superbot-v3-paper-runs"
OLD_BRAIN = RUN_ROOT + "/brain-v3-paper20261111"
NEW_RUN = RUN_ROOT + "/brain-v3-unico-paper-rc1"
NEW_RUN_ID = "brain-unico-paper-rc1"
BACKUPS = Path("/opt/superbot-v3-backups")
STATE_DIR = BACKUPS / "brain-unico-web"
HEALTH = "http://127.0.0.1:8002"
DOMAIN = "superbot-trading.duckdns.org"
REQUIRED_ENV = {"DESK_MODE": "paper", "TRADING_MODE": "paper", "V3_CUTOVER_READONLY": "1",
                "V3_ALLOW_BRAIN_SINGLE_CLOSE": "1", "V3_CLOSE_BRIDGE_ONLY": "1",
                "V3_CLOSE_BRIDGE_SOCKET": SOCKET_DIR + "/close.sock"}
SAFE_GET_PATHS = ("/api/health", "/api/auth/webauthn/status", "/api/v3/overview", "/api/v3/brain/status")
COMPARED_HOST = ("Memory", "MemorySwap", "NanoCpus", "CpuShares", "CpuQuota", "CpuPeriod", "PidsLimit", "CapAdd",
                 "CapDrop", "Privileged", "ReadonlyRootfs", "SecurityOpt", "LogConfig", "NetworkMode",
                 "PortBindings", "Tmpfs", "ShmSize", "Ulimits", "UsernsMode", "IpcMode", "PidMode", "ExtraHosts",
                 "Dns", "Init")
COMPARED_CONFIG = ("User", "WorkingDir", "Entrypoint", "Cmd", "ExposedPorts", "Healthcheck", "StopSignal",
                   "Labels")
SNAPSHOT_SKIP = (BRIDGE_UNIT, "superbot-brain-unico-rc1-exit.service", "superbot-brain-unico-rc1-runner.service")
HERE = Path(__file__).resolve().parent


class Refused(RuntimeError):
    pass


def say(key: str, value: object) -> None:
    print(f"BRAIN_WEB_CUTOVER {key}={value}", flush=True)


def cmd(*args: str, timeout: int = 60, allow_failure: bool = False, stdin: str | None = None) -> str:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False, input=stdin)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Refused("command_unavailable_" + args[0]) from exc
    if p.returncode and not allow_failure:
        raise Refused("command_failed_%s_%s_%s" % (args[0], args[1] if len(args) > 1 else "", p.returncode))
    return p.stdout.strip() if p.returncode == 0 else ""


def run_text(*args: str, timeout: int = 60, stdin: str | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False, input=stdin)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Refused("command_unavailable_" + args[0]) from exc
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ---------------------------------------------------------------- funzioni pure (testate)

def new_run_env() -> dict:
    return {"V3_RUN_ID": NEW_RUN_ID, "V3_JOURNAL_PATH": NEW_RUN + "/journal.db",
            "V3_BUDGET_DB_PATH": NEW_RUN + "/budget.db", "V3_HEARTBEAT_PATH": NEW_RUN + "/heartbeat.json",
            "V3_PAUSE_FLAG_PATH": NEW_RUN + "/pause.flag", "V3_RUNNER_CONFIG_PATH": NEW_RUN + "/runner_config.json",
            "V3_CLOSE_REQUEST_PATH": NEW_RUN + "/close_request.json",
            "V3_CLOSE_RESULT_PATH": NEW_RUN + "/close_result.json"}


def target_env(old: dict) -> dict:
    for key, value in REQUIRED_ENV.items():
        if old.get(key) != value:
            raise Refused("web_paper_or_bridge_gate_unexpected_" + key)
    return {**old, **new_run_env()}


def mount_tuples(web: dict) -> set:
    return {(m["Destination"], m["Type"], bool(m["RW"]), m.get("Source") if m["Type"] == "bind" else m.get("Name"))
            for m in (web.get("Mounts") or [])}


def needs_run_mount(web: dict) -> bool:
    """False se la nuova run e' gia' visibile (stessa cartella o una cartella madre montata nello stesso punto)."""
    for m in web.get("Mounts") or []:
        dst, src = m["Destination"], m.get("Source")
        for parent in (NEW_RUN, RUN_ROOT, "/opt"):
            if dst == parent and src == parent and NEW_RUN.startswith(parent):
                if m.get("RW"):
                    raise Refused("run_visible_read_write_in_web")
                return False
        if dst == NEW_RUN:
            raise Refused("run_mount_with_unexpected_source")
    return True


def expected_mounts(web: dict) -> set:
    base = mount_tuples(web)
    return base | ({(NEW_RUN, "bind", False, NEW_RUN)} if needs_run_mount(web) else set())


def mount_args(web: dict, *, force_ro: bool) -> list[str]:
    args = []
    for m in web.get("Mounts") or []:
        src = m["Source"] if m["Type"] == "bind" else m["Name"]
        rw = bool(m["RW"]) and not force_ro
        args += ["-v", f"{src}:{m['Destination']}:{'rw' if rw else 'ro'}"]
    if needs_run_mount(web):
        args += ["-v", f"{NEW_RUN}:{NEW_RUN}:ro"]
    return args


def bridge_unit_text(old: str, image: str) -> str:
    """Unita' del bridge: stessa, con immagine candidata, run del Brain nuova (rw solo qui) e variabili di scelta."""
    if old.count(BRIDGE_IMAGE_OLD + "\n") != 1 and old.count(BRIDGE_IMAGE_OLD + " ") != 1:
        raise Refused("bridge_unit_image_not_found_once")
    mount = f"-v {OLD_BRAIN}:{OLD_BRAIN}:rw"
    if old.count(mount) != 1 or old.count("--entrypoint python3 ") != 1 or "V3_BRIDGE_BRAIN" in old:
        raise Refused("bridge_unit_unexpected")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.:/-]{0,120}", image):
        raise Refused("bridge_image_name_invalid")
    text = old.replace(BRIDGE_IMAGE_OLD, image, 1)
    text = text.replace(mount, f"-v {NEW_RUN}:{NEW_RUN}:rw", 1)
    text = text.replace("--entrypoint python3 ",
                        f"-e V3_BRIDGE_BRAIN_RUN_DIR={NEW_RUN.rsplit('/', 1)[1]} "
                        f"-e V3_BRIDGE_BRAIN_RUN_ID={NEW_RUN_ID} --entrypoint python3 ", 1)
    return text


def norm(value):
    if value in (None, "", [], {}, 0, False, "default", "bridge"):
        return None
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return sorted(v.replace("no-new-privileges:true", "no-new-privileges") for v in value)
    return value


def config_differences(old: dict, new: dict) -> list[str]:
    diffs = []
    for key in COMPARED_HOST:
        if norm((old.get("HostConfig") or {}).get(key)) != norm((new.get("HostConfig") or {}).get(key)):
            diffs.append("HostConfig." + key)
    for key in COMPARED_CONFIG:
        if norm((old.get("Config") or {}).get(key)) != norm((new.get("Config") or {}).get(key)):
            diffs.append("Config." + key)
    return diffs


# ---------------------------------------------------------------- docker / systemd

def docker_inspect(name: str) -> dict | None:
    raw = cmd("docker", "inspect", name, allow_failure=True)
    if not raw:
        return None
    obj = json.loads(raw)
    if type(obj) is not list or len(obj) != 1:
        raise Refused("invalid_docker_metadata")
    return obj[0]


def image_id(tag: str) -> str | None:
    return cmd("docker", "image", "inspect", tag, "--format", "{{.Id}}", allow_failure=True) or None


def env_map(web: dict) -> dict:
    rows = web["Config"].get("Env") or []
    if type(rows) is not list or any(type(e) is not str or "=" not in e for e in rows):
        raise Refused("invalid_env")
    return dict(x.split("=", 1) for x in rows)


def http_code(path: str) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(HEALTH + path), timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (OSError, TimeoutError):
        return 0


def behavior_vector() -> dict[str, int]:
    return {p: http_code(p) for p in SAFE_GET_PATHS}


def public_vector() -> dict[str, int]:
    out = {}
    for path in ("/api/health", "/api/auth/webauthn/status", "/api/v3/brain/status"):
        out[path] = int(cmd("curl", "-sS", "--max-time", "10", "--resolve", f"{DOMAIN}:443:127.0.0.1",
                            "-o", "/dev/null", "-w", "%{http_code}", f"https://{DOMAIN}{path}",
                            allow_failure=True) or 0)
    return out


def units_snapshot() -> dict[str, str]:
    """PID e stato di tutte le unita' superbot* tranne il bridge (riavviato per scelta) e le unita' Brain Unico."""
    out = {}
    listing = cmd("systemctl", "list-units", "superbot*", "--all", "--no-legend", "--plain", allow_failure=True)
    for line in listing.splitlines():
        unit = line.split(" ", 1)[0]
        if not unit or unit in SNAPSHOT_SKIP:
            continue
        out[unit] = cmd("systemctl", "show", unit, "-p", "MainPID,ActiveState", "--value", allow_failure=True)
    return out


def fresh_env_file(env: dict) -> Path:
    fd, filename = tempfile.mkstemp(prefix=".brain-unico-web-env-", dir="/run")
    os.fchmod(fd, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for k, v in sorted(env.items()):
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) or any(ch in v for ch in "\r\n\0"):
                    raise Refused("unsafe_env_value")
                f.write(k + "=" + v + "\n")
        return Path(filename)
    except BaseException:
        Path(filename).unlink(missing_ok=True)
        raise


def check_live() -> dict:
    if os.geteuid() != 0:
        raise Refused("root_required")
    web = docker_inspect(LIVE)
    if web is None or web.get("State", {}).get("Running") is not True:
        raise Refused("web_missing_or_stopped")
    target_env(env_map(web))
    host = web.get("HostConfig") or {}
    if (host.get("RestartPolicy", {}).get("Name") != "always" or host.get("Privileged") is True
            or host.get("AutoRemove") is True or host.get("NetworkMode") not in ("default", "bridge")):
        raise Refused("unsupported_web_host_configuration")
    bound = (host.get("PortBindings") or {}).get("8001/tcp") or []
    if (set((host.get("PortBindings") or {})) != {"8001/tcp"} or len(bound) != 1
            or bound[0].get("HostIp") != "127.0.0.1" or bound[0].get("HostPort") != "8002"):
        raise Refused("unexpected_web_port_mapping")
    dests = [m.get("Destination") for m in web.get("Mounts") or []]
    if len(dests) != len(set(dests)):
        raise Refused("duplicate_mount_destinations")
    for p in ("/app/data", "/app/backend/.env", SOCKET_DIR):
        if p not in dests:
            raise Refused("missing_original_web_mount_" + p)
    for m in web.get("Mounts") or []:
        src = m.get("Source") if m.get("Type") == "bind" else m.get("Name")
        if (m.get("Type") not in ("bind", "volume") or type(src) is not str or not src
                or any(ch in src + m["Destination"] for ch in "\n\r\0:") or "docker.sock" in m["Destination"]):
            raise Refused("unsafe_mount")
        if m["Destination"].startswith(RUN_ROOT) and m.get("RW"):
            raise Refused("run_mounted_read_write_in_web")
    needs_run_mount(web)
    if not Path(NEW_RUN, "journal.db").is_file() or not Path(NEW_RUN, "PREPARED_PAUSED_ONLY.json").is_file():
        raise Refused("new_run_missing")
    if http_code("/api/health") != 200:
        raise Refused("web_not_healthy")
    return web


def build_candidate(web: dict, root: Path, sha_pin: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", sha_pin or ""):
        raise Refused("sha_pin_required")
    env = dict(os.environ, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="safe.directory", GIT_CONFIG_VALUE_0="*")
    try:
        subprocess.run(["git", "-C", str(root), "cat-file", "-e", sha_pin + "^{commit}"], env=env, check=True,
                       capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Refused("commit_not_in_source_root") from exc
    tag = "superbot:brain-unico-web-" + sha_pin[:12]
    keep = "superbot:before-brain-unico-web"
    if image_id(tag):
        raise Refused("candidate_tag_already_exists")
    cmd("docker", "tag", web["Image"], keep)
    say("previous_image_kept_as", keep)
    with tempfile.TemporaryDirectory(prefix="brain-unico-web-image-") as tmp:
        ctx = Path(tmp)
        with open(ctx / "src.tar", "wb") as out:
            p = subprocess.run(["git", "-C", str(root), "archive", sha_pin, "backend"], env=env, stdout=out,
                               stderr=subprocess.PIPE, timeout=120)
        if p.returncode:
            raise Refused("git_archive_failed")
        (ctx / "Dockerfile").write_text(f"FROM {web['Image']}\nADD src.tar /app/\n")
        cmd("docker", "build", "--pull=false", "--network=none", "-t", tag, str(ctx), timeout=900)
    cand = image_id(tag)
    if not cand or cand == web["Image"]:
        raise Refused("candidate_build_failed")
    say("candidate_image", cand)
    say("candidate_tag", tag)
    return tag


def run_probe(args: list[str], probe: str, mode: str) -> None:
    code, out = run_text(*args, timeout=180, stdin=probe)
    for line in out.splitlines():
        if line.startswith("BRAIN_WEB_PROBE "):
            say(mode + "_" + line.split(" ", 1)[1].split("=", 1)[0], line.split("=", 1)[1])
    want = "BRAIN_WEB_PROBE RESULT=PASS_" + ("CANDIDATE" if mode == "probe" else "LIVE")
    if code != 0 or want not in out:
        raise Refused(mode + "_failed")


def candidate_probe(web: dict, tag: str, probe: str) -> None:
    env_file = fresh_env_file(target_env(env_map(web)))
    try:
        args = ["docker", "run", "--rm", "-i", "--network", "none", "--read-only", "--tmpfs", "/tmp",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "200",
                "--memory", "1g", "--env-file", str(env_file)] + mount_args(web, force_ro=True)
        args += ["--entrypoint", "python3", tag, "-B", "-", "candidate", "exit-healthy"]
        run_probe(args, probe, "probe")
    finally:
        env_file.unlink(missing_ok=True)


def wait_bridge_ready() -> bool:
    for _ in range(30):
        if (cmd("systemctl", "is-active", BRIDGE_UNIT, allow_failure=True) == "active"
                and Path(SOCKET_DIR, "close.sock").is_socket()):
            return True
        time.sleep(1)
    return False


def switch_bridge(tag: str) -> None:
    old = BRIDGE_UNIT_PATH.read_text()
    new = bridge_unit_text(old, tag)
    saved = STATE_DIR / "bridge-unit.before"
    if not saved.exists():
        saved.write_text(old)
        os.chmod(saved, 0o600)
    BRIDGE_UNIT_PATH.write_text(new)
    cmd("systemctl", "daemon-reload")
    cmd("systemctl", "restart", BRIDGE_UNIT, timeout=90)
    if not wait_bridge_ready():
        raise Refused("bridge_not_ready_after_switch")
    say("bridge", "NEW_RUN_" + NEW_RUN_ID)


def restore_bridge() -> None:
    saved = STATE_DIR / "bridge-unit.before"
    if not saved.is_file():
        say("bridge_restore", "NOTHING_SAVED")
        return
    if BRIDGE_UNIT_PATH.read_text() != saved.read_text():
        BRIDGE_UNIT_PATH.write_text(saved.read_text())
        cmd("systemctl", "daemon-reload")
        cmd("systemctl", "restart", BRIDGE_UNIT, timeout=90, allow_failure=True)
        say("bridge_restore", "PREVIOUS_UNIT_RESTARTED" if wait_bridge_ready() else "CHECK_MANUALLY")
    else:
        say("bridge_restore", "ALREADY_PREVIOUS")


def create_args(web: dict, image: str, env_file: Path) -> list[str]:
    host, cfg = web["HostConfig"], web["Config"]
    args = ["docker", "create", "--name", NEW_TMP, "--restart", "no", "-p", "127.0.0.1:8002:8001",
            "--env-file", str(env_file)]
    for opt in host.get("SecurityOpt") or []:
        args += ["--security-opt", opt]
    if cfg.get("User"):
        args += ["--user", cfg["User"]]
    if cfg.get("WorkingDir"):
        args += ["--workdir", cfg["WorkingDir"]]
    for key, val in sorted((cfg.get("Labels") or {}).items()):
        if any(c in key + val for c in "\r\n\0"):
            raise Refused("invalid_label")
        args += ["--label", key + "=" + val]
    args += mount_args(web, force_ro=False)
    args.append(image)
    return args


def start_and_verify(probe: str, units: dict) -> None:
    cmd("docker", "start", LIVE, timeout=60)
    for _ in range(40):
        if http_code("/api/health") == 200:
            break
        time.sleep(2)
    else:
        raise Refused("new_web_not_healthy")
    after = behavior_vector()
    if after != {"/api/health": 200, "/api/auth/webauthn/status": 200, "/api/v3/overview": 401,
                 "/api/v3/brain/status": 401}:
        raise Refused("behavior_unexpected:" + json.dumps(after, sort_keys=True))
    run_probe(["docker", "exec", "-i", LIVE, "python3", "-B", "-", "live", "exit-healthy"], probe, "live")
    pub = public_vector()
    if pub != {"/api/health": 200, "/api/auth/webauthn/status": 200, "/api/v3/brain/status": 401}:
        raise Refused("public_path_check_failed:" + json.dumps(pub, sort_keys=True))
    if units_snapshot() != units:
        raise Refused("other_services_changed")


def restore_old_web(*, renamed: bool, switched: bool) -> None:
    say("web_rollback", "START")
    cmd("docker", "rm", "-f", NEW_TMP, timeout=30, allow_failure=True)
    if switched:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        cmd("docker", "update", "--restart", "no", LIVE, allow_failure=True)
        cmd("docker", "stop", "-t", "10", LIVE, timeout=40, allow_failure=True)
        cmd("docker", "rename", LIVE, REJECTED_PREFIX + stamp, allow_failure=True)
        say("rejected_container_kept", REJECTED_PREFIX + stamp)
    if renamed and docker_inspect(BACKUP):
        cmd("docker", "rename", BACKUP, LIVE)
    cmd("docker", "update", "--restart", "always", LIVE, allow_failure=True)
    # riavvio: il socket del bridge puo' essere stato ricreato, il bind va risolto di nuovo
    cmd("docker", "restart", "-t", "10", LIVE, timeout=60, allow_failure=True)
    for _ in range(20):
        if http_code("/api/health") == 200:
            say("web_rollback", "DONE_PREVIOUS_WEB_RESTORED")
            return
        time.sleep(2)
    say("web_rollback", "MANUAL_CHECK_REQUIRED")


def do_deploy(args) -> None:
    web = check_live()
    probe = (HERE / "brain_unico_web_probe.py").read_text()
    if docker_inspect(BACKUP) or docker_inspect(NEW_TMP):
        raise Refused("backup_or_temp_container_already_exists")
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if (STATE_DIR / "bridge-unit.before").exists():
        raise Refused("previous_cutover_state_present_run_rollback_first")
    units = units_snapshot()
    say("web_image_before", web["Image"])
    say("env_names_only", ",".join(sorted(env_map(web))))
    say("run_mount_added", needs_run_mount(web))
    fd = os.open(STATE_DIR / "container-inspect.before.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(web, f, indent=1)
    tag = build_candidate(web, Path(args.source_root), args.sha)
    candidate_probe(web, tag, probe)
    renamed = switched = bridged = False
    env_file = fresh_env_file(target_env(env_map(web)))
    try:
        cmd(*create_args(web, tag, env_file), timeout=60)
        new = docker_inspect(NEW_TMP)
        diffs = config_differences(web, new)
        if diffs:
            raise Refused("new_container_config_differs:" + ",".join(diffs))
        if env_map(new) != target_env(env_map(web)):
            raise Refused("new_container_env_differs")
        if mount_tuples(new) != expected_mounts(web):
            raise Refused("new_container_mounts_differ")
        say("new_config_identical_except_brain_run", "TRUE")
        bridged = True
        switch_bridge(tag)
        current = docker_inspect(LIVE)
        if current is None or current.get("Id") != web.get("Id") or units_snapshot() != units:
            raise Refused("state_changed_since_preflight")
        cmd("docker", "update", "--restart", "no", LIVE)
        cmd("docker", "stop", "-t", "10", LIVE, timeout=40)
        cmd("docker", "rename", LIVE, BACKUP)
        renamed = True
        cmd("docker", "rename", NEW_TMP, LIVE)
        switched = True
        start_and_verify(probe, units)
        cmd("docker", "update", "--restart", "always", LIVE)
        say("web_replaced", "TRUE")
        say("old_web_kept_stopped", BACKUP)
        say("other_services_untouched", "TRUE")
        say("RESULT", "WEB_AND_CLOSE_CHANNEL_ON_BRAIN_UNICO")
    except BaseException:
        restore_bridge()
        if renamed:
            restore_old_web(renamed=True, switched=switched)
        else:
            cmd("docker", "rm", "-f", NEW_TMP, allow_failure=True)
            cmd("docker", "update", "--restart", "always", LIVE, allow_failure=True)
            if bridged:      # cartella del socket ricreata dal riavvio del bridge: il web la rimonta
                cmd("docker", "restart", "-t", "10", LIVE, timeout=60, allow_failure=True)
        (STATE_DIR / "bridge-unit.before").unlink(missing_ok=True)
        raise
    finally:
        env_file.unlink(missing_ok=True)


def do_rollback(_args) -> None:
    """Idempotente: rimette bridge e web precedenti (conservati), senza cancellare nulla."""
    if os.geteuid() != 0:
        raise Refused("root_required")
    restore_bridge()
    live, backup = docker_inspect(LIVE), docker_inspect(BACKUP)
    cmd("docker", "rm", "-f", NEW_TMP, allow_failure=True)
    if backup is not None:
        if backup.get("State", {}).get("Running") is True:
            raise Refused("previous_web_backup_is_running")
        if live is not None:
            if not str((live.get("Config") or {}).get("Image", "")).startswith("superbot:brain-unico-web-"):
                raise Refused("live_web_is_not_the_brain_unico_candidate")
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            cmd("docker", "update", "--restart", "no", LIVE)
            cmd("docker", "stop", "-t", "10", LIVE, timeout=40, allow_failure=True)
            cmd("docker", "rename", LIVE, REJECTED_PREFIX + stamp)
            say("rejected_container_kept", REJECTED_PREFIX + stamp)
        cmd("docker", "rename", BACKUP, LIVE)
    elif live is None:
        raise Refused("no_web_container")
    cmd("docker", "update", "--restart", "always", LIVE)
    cmd("docker", "restart", "-t", "10", LIVE, timeout=60)
    for _ in range(20):
        if http_code("/api/health") == 200:
            break
        time.sleep(2)
    else:
        raise Refused("restored_web_not_healthy")
    (STATE_DIR / "bridge-unit.before").unlink(missing_ok=True)
    say("RESULT", "PREVIOUS_WEB_AND_BRIDGE_RESTORED")


def main() -> None:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--deploy", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    ap.add_argument("--source-root")
    ap.add_argument("--sha")
    args = ap.parse_args()
    if args.deploy:
        if not args.source_root:
            raise Refused("source_root_required")
        do_deploy(args)
    else:
        do_rollback(args)


if __name__ == "__main__":
    try:
        main()
    except Refused as exc:
        say("RESULT", "REFUSED_" + str(exc)[:200])
        sys.exit(2)
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        say("RESULT", "FAILED_" + type(exc).__name__ + ":" + str(exc)[:100])
        sys.exit(2)
