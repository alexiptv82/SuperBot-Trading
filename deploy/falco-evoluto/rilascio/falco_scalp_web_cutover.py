#!/usr/bin/env python3
"""Falco Evoluto + Brain Scalp: web app e canale di chiusura PAPER collegati alle DUE nuove run (sola aggiunta).

Stesso meccanismo collaudato del cutover Brain Unico (``brain_unico_web_cutover.py``, usato qui come libreria per le
funzioni generiche): immagine candidata = immagine IN USO + ``backend/`` del commit revisionato (nessun pull), prova in
un container usa-e-getta senza rete con mount in sola lettura, nuovo container creato PRIMA di fermare il vecchio e
confrontato campo per campo, vecchio container conservato fermo, rollback automatico a ogni errore.

Cambiamenti, e nient'altro:
  web    : backend del commit; ``V3_COMPARE_RUNS`` (le due run); le due run montate in SOLA LETTURA.
           Le variabili V3_* di Brain RC1 restano identiche (RC1 continua a essere la run della pagina Brain).
  bridge : stessa unita' e stesse protezioni; immagine candidata; le due run montate in scrittura (solo qui);
           ``V3_BRIDGE_EXTRA_RUNS`` in formato compatto. Mount e variabili di RC1, Falco e Toro invariati.
NON tocca: login, .env, nginx, Arena, runner/uscite di qualunque run, journal, mandati.

Uso (root): --deploy --source-root <laboratorio> --sha <commit 40 hex>   |   --rollback
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import brain_unico_web_cutover as base  # noqa: E402  (funzioni generiche gia' collaudate)
from brain_unico_web_cutover import (  # noqa: E402
    Refused, cmd, config_differences, docker_inspect, env_map, fresh_env_file, http_code, image_id, run_probe,
)

LIVE = base.LIVE
NEW_TMP = "superbot-falco-scalp-web-new"
BACKUP = "superbot-before-falco-scalp-web"
REJECTED_PREFIX = "superbot-falco-scalp-web-rejected-"
BRIDGE_UNIT = base.BRIDGE_UNIT
BRIDGE_UNIT_PATH = base.BRIDGE_UNIT_PATH
SOCKET_DIR = base.SOCKET_DIR
RUN_ROOT = base.RUN_ROOT
RC1_RUN = base.NEW_RUN
STATE_DIR = Path("/opt/superbot-v3-backups/falco-scalp-web")
TAG_PREFIX = "superbot:falco-scalp-web-"
KEEP_TAG = "superbot:before-falco-scalp-web"
RUNS = (("falco_evoluto", "Falco Evoluto", "brain-v3-falco-evoluto-p1", "falco-evoluto-paper-p1"),
        ("brain_scalp", "Brain Scalp", "brain-v3-brain-scalp-p1", "brain-scalp-paper-p1"))
NEW_UNITS = ("superbot-falco-evoluto-p1-exit.service", "superbot-falco-evoluto-p1-runner.service",
             "superbot-brain-scalp-p1-exit.service", "superbot-brain-scalp-p1-runner.service")
SNAPSHOT_SKIP = base.SNAPSHOT_SKIP + NEW_UNITS


def say(key: str, value: object) -> None:
    print(f"FALCO_SCALP_WEB {key}={value}", flush=True)


# ---------------------------------------------------------------- funzioni pure (testate)

def run_dirs() -> list[str]:
    return [f"{RUN_ROOT}/{folder}" for _, _, folder, _ in RUNS]


def compare_env_value() -> str:
    return json.dumps([{"name": n, "label": l, "dir": f"{RUN_ROOT}/{d}", "run_id": r} for n, l, d, r in RUNS],
                      separators=(",", ":"))


def bridge_env_value() -> str:
    return ",".join(f"{n}={d}:{r}" for n, _, d, r in RUNS)


def target_env(old: dict) -> dict:
    for key, value in base.REQUIRED_ENV.items():
        if old.get(key) != value:
            raise Refused("web_paper_or_bridge_gate_unexpected_" + key)
    if old.get("V3_RUN_ID") != base.NEW_RUN_ID or "V3_COMPARE_RUNS" in old:
        raise Refused("web_not_on_rc1_or_compare_already_set")
    return {**old, "V3_COMPARE_RUNS": compare_env_value()}


def needs_mount(web: dict, run: str) -> bool:
    for m in web.get("Mounts") or []:
        dst, src = m["Destination"], m.get("Source")
        for parent in (run, RUN_ROOT, "/opt"):
            if dst == parent and src == parent and run.startswith(parent):
                if m.get("RW"):
                    raise Refused("run_visible_read_write_in_web")
                return False
        if dst == run:
            raise Refused("run_mount_with_unexpected_source")
    return True


def expected_mounts(web: dict) -> set:
    return base.mount_tuples(web) | {(r, "bind", False, r) for r in run_dirs() if needs_mount(web, r)}


def mount_args(web: dict, *, force_ro: bool) -> list[str]:
    args = []
    for m in web.get("Mounts") or []:
        src = m["Source"] if m["Type"] == "bind" else m["Name"]
        rw = bool(m["RW"]) and not force_ro
        args += ["-v", f"{src}:{m['Destination']}:{'rw' if rw else 'ro'}"]
    for r in run_dirs():
        if needs_mount(web, r):
            args += ["-v", f"{r}:{r}:ro"]
    return args


def bridge_unit_text(old: str, image: str, current_image: str) -> str:
    """Unita' del bridge: stessa, immagine candidata, due run in scrittura accanto a RC1, variabile delle run."""
    rc1_mount = f"-v {RC1_RUN}:{RC1_RUN}:rw"
    if (old.count(current_image + " ") != 1 or old.count(rc1_mount) != 1 or old.count("--entrypoint python3 ") != 1
            or "V3_BRIDGE_EXTRA_RUNS" in old or any(d in old for d in run_dirs())
            or f"-e V3_BRIDGE_BRAIN_RUN_ID={base.NEW_RUN_ID} " not in old):
        raise Refused("bridge_unit_unexpected")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.:/-]{0,120}", image):
        raise Refused("bridge_image_name_invalid")
    text = old.replace(current_image + " ", image + " ", 1)
    extra = " ".join(f"-v {r}:{r}:rw" for r in run_dirs())
    text = text.replace(rc1_mount, f"{rc1_mount} {extra}", 1)
    text = text.replace("--entrypoint python3 ", f"-e V3_BRIDGE_EXTRA_RUNS={bridge_env_value()} --entrypoint python3 ",
                        1)
    return text


def bridge_image(unit_text: str) -> str:
    m = re.search(r"--entrypoint python3 (\S+) -m backend\.v3\.close_bridge_server", unit_text)
    if not m:
        raise Refused("bridge_image_not_found")
    return m.group(1)


# ---------------------------------------------------------------- docker / systemd

def units_snapshot() -> dict[str, str]:
    out = {}
    listing = cmd("systemctl", "list-units", "superbot*", "--all", "--no-legend", "--plain", allow_failure=True)
    for line in listing.splitlines():
        unit = line.split(" ", 1)[0]
        if not unit or unit in SNAPSHOT_SKIP:
            continue
        out[unit] = cmd("systemctl", "show", unit, "-p", "MainPID,ActiveState", "--value", allow_failure=True)
    return out


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
    for m in web.get("Mounts") or []:
        src = m.get("Source") if m.get("Type") == "bind" else m.get("Name")
        if (m.get("Type") not in ("bind", "volume") or type(src) is not str or not src
                or any(ch in src + m["Destination"] for ch in "\n\r\0:") or "docker.sock" in m["Destination"]):
            raise Refused("unsafe_mount")
        if m["Destination"].startswith(RUN_ROOT) and m.get("RW"):
            raise Refused("run_mounted_read_write_in_web")
    for r in run_dirs():
        needs_mount(web, r)
        if not Path(r, "journal.db").is_file() or not Path(r, "PREPARED_PAUSED_ONLY.json").is_file():
            raise Refused("new_run_missing_" + Path(r).name)
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
    tag = TAG_PREFIX + sha_pin[:12]
    if image_id(tag):
        raise Refused("candidate_tag_already_exists")
    cmd("docker", "tag", web["Image"], KEEP_TAG)
    say("previous_image_kept_as", KEEP_TAG)
    with tempfile.TemporaryDirectory(prefix="falco-scalp-web-image-") as tmp:
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
    say("candidate_tag", tag)
    return tag


def probes() -> str:
    """Sonda Brain RC1 (invariata) seguita dalla sonda del confronto: un solo script letto dal container via stdin."""
    return (HERE / "brain_unico_web_probe.py").read_text()


def candidate_probe(web: dict, tag: str) -> None:
    env_file = fresh_env_file(target_env(env_map(web)))
    try:
        common = ["docker", "run", "--rm", "-i", "--network", "none", "--read-only", "--tmpfs", "/tmp",
                  "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "200",
                  "--memory", "1g", "--env-file", str(env_file)] + mount_args(web, force_ro=True)
        run_probe(common + ["--entrypoint", "python3", tag, "-B", "-", "candidate", "exit-healthy"], probes(), "probe")
        _compare_probe(common + ["--entrypoint", "python3", tag, "-B", "-", "candidate"], "probe")
    finally:
        env_file.unlink(missing_ok=True)


def _compare_probe(args: list[str], mode: str) -> None:
    code, out = base.run_text(*args, timeout=180, stdin=(HERE / "compare_probe.py").read_text())
    for line in out.splitlines():
        if line.startswith("COMPARE_PROBE "):
            say(mode + "_compare_" + line.split(" ", 1)[1].split("=", 1)[0], line.split("=", 1)[1])
    if code != 0 or "COMPARE_PROBE RESULT=PASS" not in out:
        raise Refused(mode + "_compare_failed")


def switch_bridge(tag: str) -> None:
    old = BRIDGE_UNIT_PATH.read_text()
    new = bridge_unit_text(old, tag, bridge_image(old))
    saved = STATE_DIR / "bridge-unit.before"
    if not saved.exists():
        saved.write_text(old)
        os.chmod(saved, 0o600)
    BRIDGE_UNIT_PATH.write_text(new)
    cmd("systemctl", "daemon-reload")
    cmd("systemctl", "restart", BRIDGE_UNIT, timeout=90)
    if not base.wait_bridge_ready():
        raise Refused("bridge_not_ready_after_switch")
    say("bridge", "EXTRA_RUNS_" + bridge_env_value())


def restore_bridge() -> None:
    saved = STATE_DIR / "bridge-unit.before"
    if not saved.is_file():
        say("bridge_restore", "NOTHING_SAVED")
        return
    if BRIDGE_UNIT_PATH.read_text() != saved.read_text():
        BRIDGE_UNIT_PATH.write_text(saved.read_text())
        cmd("systemctl", "daemon-reload")
        cmd("systemctl", "restart", BRIDGE_UNIT, timeout=90, allow_failure=True)
        say("bridge_restore", "PREVIOUS_UNIT_RESTARTED" if base.wait_bridge_ready() else "CHECK_MANUALLY")
    else:
        say("bridge_restore", "ALREADY_PREVIOUS")


def create_args(web: dict, image: str, env_file: Path) -> list[str]:
    args = base.create_args(web, image, env_file)
    # stessa costruzione del cutover RC1, con il nome temporaneo e i mount di QUESTO rilascio
    i = args.index("--name")
    args[i + 1] = NEW_TMP
    first_v = args.index("-v")
    return args[:first_v] + mount_args(web, force_ro=False) + [image]


def start_and_verify(units: dict) -> None:
    cmd("docker", "start", LIVE, timeout=60)
    for _ in range(40):
        if http_code("/api/health") == 200:
            break
        time.sleep(2)
    else:
        raise Refused("new_web_not_healthy")
    after = base.behavior_vector()
    if after != {"/api/health": 200, "/api/auth/webauthn/status": 200, "/api/v3/overview": 401,
                 "/api/v3/brain/status": 401} or http_code("/api/v3/compare") != 401:
        raise Refused("behavior_unexpected:" + json.dumps(after, sort_keys=True))
    run_probe(["docker", "exec", "-i", LIVE, "python3", "-B", "-", "live", "exit-healthy"], probes(), "live")
    _compare_probe(["docker", "exec", "-i", LIVE, "python3", "-B", "-", "live"], "live")
    pub = base.public_vector()
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
    cmd("docker", "restart", "-t", "10", LIVE, timeout=60, allow_failure=True)
    for _ in range(20):
        if http_code("/api/health") == 200:
            say("web_rollback", "DONE_PREVIOUS_WEB_RESTORED")
            return
        time.sleep(2)
    say("web_rollback", "MANUAL_CHECK_REQUIRED")


def do_deploy(args) -> None:
    web = check_live()
    if docker_inspect(BACKUP) or docker_inspect(NEW_TMP):
        raise Refused("backup_or_temp_container_already_exists")
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if (STATE_DIR / "bridge-unit.before").exists():
        raise Refused("previous_cutover_state_present_run_rollback_first")
    bridge_unit_text(BRIDGE_UNIT_PATH.read_text(), "superbot:check", bridge_image(BRIDGE_UNIT_PATH.read_text()))
    units = units_snapshot()
    say("web_image_before", web["Image"])
    fd = os.open(STATE_DIR / "container-inspect.before.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(web, f, indent=1)
    tag = build_candidate(web, Path(args.source_root), args.sha)
    candidate_probe(web, tag)
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
        if base.mount_tuples(new) != expected_mounts(web):
            raise Refused("new_container_mounts_differ")
        say("new_config_identical_except_compare_runs", "TRUE")
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
        start_and_verify(units)
        cmd("docker", "update", "--restart", "always", LIVE)
        say("web_replaced", "TRUE")
        say("old_web_kept_stopped", BACKUP)
        say("RESULT", "WEB_AND_CLOSE_CHANNEL_WITH_FALCO_EVOLUTO_AND_BRAIN_SCALP")
    except BaseException:
        restore_bridge()
        if renamed:
            restore_old_web(renamed=True, switched=switched)
        else:
            cmd("docker", "rm", "-f", NEW_TMP, allow_failure=True)
            cmd("docker", "update", "--restart", "always", LIVE, allow_failure=True)
            if bridged:
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
            if not str((live.get("Config") or {}).get("Image", "")).startswith(TAG_PREFIX):
                raise Refused("live_web_is_not_the_falco_scalp_candidate")
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
