#!/usr/bin/env python3
"""App PAPER: aggiornamento della web (backend con le rotte GET di Trade, Performance, Archivio) con rollback automatico.

Stesso meccanismo collaudato dei cutover precedenti (``brain_unico_web_cutover.py`` come libreria): immagine candidata =
immagine IN USO + ``backend/`` del commit (archivio tar verificato con la sua impronta, nessun git e nessun pull), prova
in un container usa-e-getta senza rete con mount in sola lettura e sonda sulle run VERE, nuovo container creato PRIMA di
fermare il vecchio e confrontato campo per campo, vecchio container conservato fermo, rollback automatico a ogni errore.

Cambiamenti, e nient'altro:
  web: backend del commit; ``V3_PAPER_ARCHIVE_ROOT``; archivio del reset (``/opt/superbot-v3-paper-runs/.archivio``)
       montato in SOLA LETTURA.
NON tocca: bridge di chiusura, runner e uscite di qualunque run, journal, mandati, pause, Brain RC1, login, .env, nginx.

Uso (root): --deploy --backend-tar <file> --tar-sha256 <hex> --sha <commit>   |   --rollback
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1] / "brain-unico" / "avvio"):
    if (p / "brain_unico_web_cutover.py").is_file():
        sys.path.insert(0, str(p))
        break
import brain_unico_web_cutover as base  # noqa: E402
from brain_unico_web_cutover import (  # noqa: E402
    Refused, cmd, config_differences, docker_inspect, env_map, fresh_env_file, http_code, image_id, run_text,
)

LIVE = base.LIVE
NEW_TMP = "superbot-paper-app-web-new"
BACKUP = "superbot-before-paper-app-web"
REJECTED_PREFIX = "superbot-paper-app-web-rejected-"
RETIRED_PREFIX = "superbot-before-paper-app-web-archived-"
STATE_DIR = Path("/opt/superbot-v3-backups/paper-app-web")
TAG_PREFIX = "superbot:paper-app-web-"
RUN_ROOT = base.RUN_ROOT
ARCHIVE = RUN_ROOT + "/.archivio"
ENV_ARCHIVE = "V3_PAPER_ARCHIVE_ROOT"
RUNS = (("falco_evoluto", "Falco Evoluto", "brain-v3-falco-evoluto-p1", "falco-evoluto-paper-p1"),
        ("brain_scalp", "Brain Scalp", "brain-v3-brain-scalp-p1", "brain-scalp-paper-p1"))
# Brain unico PAPER 2000 (24/11): la web mostra UNA sola run, nello slot di Brain Scalp (stessa cartella e stesso run_id:
# bridge, unita' e superbot-ops invariati), con l'etichetta "Brain". Falco Evoluto resta solo nell'Archivio.
UNICO_RUNS = (("brain_scalp", "Brain", "brain-v3-brain-scalp-p1", "brain-scalp-paper-p1"),)
UNICO = {"on": False}
_STAMP = re.compile(r"^reset-[0-9]{8}T[0-9]{6}Z$")
_DIR = re.compile(r"^brain-v3-[a-z0-9-]{1,48}$")


def say(key: str, value: object) -> None:
    print(f"PAPER_APP_WEB {key}={value}", flush=True)


# ---------------------------------------------------------------- funzioni pure (testate)

def run_dirs() -> list[str]:
    return [f"{RUN_ROOT}/{folder}" for _, _, folder, _ in RUNS]


def compare_env_value(runs=RUNS) -> str:
    """Il valore scritto dal cutover di Falco Evoluto/Brain Scalp (o, con ``runs=UNICO_RUNS``, dal Brain unico)."""
    return json.dumps([{"name": n, "label": l, "dir": f"{RUN_ROOT}/{d}", "run_id": r} for n, l, d, r in runs],
                      separators=(",", ":"))


def target_env(old: dict) -> dict:
    for key, value in base.REQUIRED_ENV.items():
        if old.get(key) != value:
            raise Refused("web_paper_or_bridge_gate_unexpected_" + key)
    accepted = (compare_env_value(), compare_env_value(UNICO_RUNS)) if UNICO["on"] else (compare_env_value(),)
    if old.get("V3_COMPARE_RUNS") not in accepted:
        raise Refused("web_not_on_falco_evoluto_and_brain_scalp")
    if old.get(ENV_ARCHIVE) not in (None, ARCHIVE):
        raise Refused("archive_root_unexpected")
    new = {**old, ENV_ARCHIVE: ARCHIVE}
    if UNICO["on"]:
        new["V3_COMPARE_RUNS"] = compare_env_value(UNICO_RUNS)
    return new


def needs_archive_mount(web: dict) -> bool:
    """False se l'archivio e' gia' visibile in sola lettura (stessa cartella o cartella madre montata nello stesso punto)."""
    for m in web.get("Mounts") or []:
        dst, src = m["Destination"], m.get("Source")
        for parent in (ARCHIVE, RUN_ROOT, "/opt"):
            if dst == parent and src == parent:
                if m.get("RW"):
                    raise Refused("archive_visible_read_write_in_web")
                return False
        if dst == ARCHIVE:
            raise Refused("archive_mount_with_unexpected_source")
    return True


def expected_mounts(web: dict) -> set:
    extra = {(ARCHIVE, "bind", False, ARCHIVE)} if needs_archive_mount(web) else set()
    return base.mount_tuples(web) | extra


def mount_args(web: dict, *, force_ro: bool) -> list[str]:
    args = []
    for m in web.get("Mounts") or []:
        src = m["Source"] if m["Type"] == "bind" else m["Name"]
        rw = bool(m["RW"]) and not force_ro
        args += ["-v", f"{src}:{m['Destination']}:{'rw' if rw else 'ro'}"]
    if needs_archive_mount(web):
        args += ["-v", f"{ARCHIVE}:{ARCHIVE}:ro"]
    return args


def host_archived(root: Path) -> int:
    """Run archiviate COMPLETE sull'host (cartella + RISULTATI.json): la sonda deve vederle tutte."""
    n = 0
    for st in (root.iterdir() if root.is_dir() else []):
        if not (st.is_dir() and _STAMP.match(st.name)):
            continue
        for f in st.iterdir():
            if f.name.endswith(".RISULTATI.json"):
                folder = f.name[: -len(".RISULTATI.json")]
                n += bool(_DIR.match(folder) and (st / folder).is_dir())
    return n


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_backend_tar(path: Path, want: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", want or "") or not path.is_file() or sha256(path) != want:
        raise Refused("backend_tar_hash_mismatch")
    with tarfile.open(path) as t:
        for m in t.getmembers():
            if (not (m.isfile() or m.isdir()) or not (m.name == "backend" or m.name.startswith("backend/"))
                    or ".." in m.name.split("/")):
                raise Refused("backend_tar_unexpected_member")


# ---------------------------------------------------------------- docker

def units_snapshot() -> dict[str, str]:
    out = {}
    listing = cmd("systemctl", "list-units", "superbot*", "--all", "--no-legend", "--plain", allow_failure=True)
    for line in listing.splitlines():
        unit = line.split(" ", 1)[0]
        if unit:
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
    if not Path(ARCHIVE).is_dir() or Path(ARCHIVE).is_symlink():
        raise Refused("archive_missing")
    needs_archive_mount(web)
    if http_code("/api/health") != 200:
        raise Refused("web_not_healthy")
    return web


def build_candidate(web: dict, tar: Path, sha: str) -> str:
    tag = TAG_PREFIX + sha[:12]
    if image_id(tag):
        raise Refused("candidate_tag_already_exists")
    with tempfile.TemporaryDirectory(prefix="paper-app-web-image-") as tmp:
        ctx = Path(tmp)
        shutil.copyfile(tar, ctx / "src.tar")
        (ctx / "Dockerfile").write_text(f"FROM {web['Image']}\nADD src.tar /app/\n")
        cmd("docker", "build", "--pull=false", "--network=none", "-t", tag, str(ctx), timeout=900)
    cand = image_id(tag)
    if not cand or cand == web["Image"]:
        raise Refused("candidate_build_failed")
    say("candidate_tag", tag)
    return tag


def _probe(args: list[str], mode: str, archived: int) -> None:
    extra = ["unico"] if UNICO["on"] else []
    code, out = run_text(*args, "-B", "-", mode, str(archived), *extra, timeout=240,
                         stdin=(HERE / "app_probe.py").read_text())
    for line in out.splitlines():
        if line.startswith("APP_PROBE "):
            say(mode + "_" + line.split(" ", 1)[1].split("=", 1)[0], line.split("=", 1)[1])
    if code != 0 or "APP_PROBE RESULT=PASS_" + mode.upper() not in out:
        raise Refused(mode + "_probe_failed")


def candidate_probe(web: dict, tag: str, archived: int) -> None:
    env_file = fresh_env_file(target_env(env_map(web)))
    try:
        _probe(["docker", "run", "--rm", "-i", "--network", "none", "--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--pids-limit", "200", "--memory", "1g", "--env-file", str(env_file)]
               + mount_args(web, force_ro=True) + ["--entrypoint", "python3", tag], "candidate", archived)
    finally:
        env_file.unlink(missing_ok=True)


def create_args(web: dict, image: str, env_file: Path) -> list[str]:
    args = base.create_args(web, image, env_file)
    args[args.index("--name") + 1] = NEW_TMP
    first_v = args.index("-v") if "-v" in args else len(args) - 1
    return args[:first_v] + mount_args(web, force_ro=False) + [image]


def start_and_verify(units: dict, archived: int) -> None:
    cmd("docker", "start", LIVE, timeout=60)
    for _ in range(40):
        if http_code("/api/health") == 200:
            break
        time.sleep(2)
    else:
        raise Refused("new_web_not_healthy")
    after = base.behavior_vector()
    if after != {"/api/health": 200, "/api/auth/webauthn/status": 200, "/api/v3/overview": 401,
                 "/api/v3/brain/status": 401} or http_code("/api/v3/compare") != 401 \
            or http_code("/api/v3/paper-archive") != 401:
        raise Refused("behavior_unexpected:" + json.dumps(after, sort_keys=True))
    _probe(["docker", "exec", "-i", LIVE, "python3"], "live", archived)
    pub = base.public_vector()
    if pub != {"/api/health": 200, "/api/auth/webauthn/status": 200, "/api/v3/brain/status": 401}:
        raise Refused("public_path_check_failed:" + json.dumps(pub, sort_keys=True))
    if units_snapshot() != units:
        raise Refused("other_services_changed")


def restore_old_web(*, switched: bool) -> None:
    say("web_rollback", "START")
    cmd("docker", "rm", "-f", NEW_TMP, timeout=30, allow_failure=True)
    if switched:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        cmd("docker", "update", "--restart", "no", LIVE, allow_failure=True)
        cmd("docker", "stop", "-t", "10", LIVE, timeout=40, allow_failure=True)
        cmd("docker", "rename", LIVE, REJECTED_PREFIX + stamp, allow_failure=True)
        say("rejected_container_kept", REJECTED_PREFIX + stamp)
    if docker_inspect(BACKUP):
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
    if not re.fullmatch(r"[0-9a-f]{40}", args.sha or ""):
        raise Refused("sha_required")
    tar = Path(args.backend_tar)
    check_backend_tar(tar, args.tar_sha256)
    web = check_live()
    if docker_inspect(NEW_TMP):
        raise Refused("temp_container_already_exists")
    old_backup = docker_inspect(BACKUP)
    if old_backup is not None:
        # aggiornamento successivo: il backup del rilascio precedente viene ARCHIVIATO (mai cancellato)
        if old_backup.get("State", {}).get("Running") is True:
            raise Refused("previous_backup_is_running")
        retired = RETIRED_PREFIX + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        cmd("docker", "rename", BACKUP, retired)
        say("previous_backup_archived", retired)
    archived = host_archived(Path(ARCHIVE))
    say("host_archived_runs", archived)
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    fd = os.open(STATE_DIR / f"container-inspect.before-{stamp}.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(web, f, indent=1)
    units = units_snapshot()
    say("web_image_before", web["Image"])
    tag = build_candidate(web, tar, args.sha)
    candidate_probe(web, tag, archived)
    switched = renamed = False
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
        say("new_config_identical_except_archive", "TRUE")
        current = docker_inspect(LIVE)
        if current is None or current.get("Id") != web.get("Id") or units_snapshot() != units:
            raise Refused("state_changed_since_preflight")
        cmd("docker", "update", "--restart", "no", LIVE)
        cmd("docker", "stop", "-t", "10", LIVE, timeout=40)
        cmd("docker", "rename", LIVE, BACKUP)
        renamed = True
        cmd("docker", "rename", NEW_TMP, LIVE)
        switched = True
        start_and_verify(units, archived)
        cmd("docker", "update", "--restart", "always", LIVE)
        say("web_replaced", "TRUE")
        say("old_web_kept_stopped", BACKUP)
        say("RESULT", "WEB_WITH_PAPER_APP_ROUTES")
    except BaseException:
        if renamed:
            restore_old_web(switched=switched)
        else:
            cmd("docker", "rm", "-f", NEW_TMP, allow_failure=True)
            cmd("docker", "update", "--restart", "always", LIVE, allow_failure=True)
        raise
    finally:
        env_file.unlink(missing_ok=True)


def do_rollback(_args) -> None:
    """Idempotente: rimette la web precedente (conservata ferma), senza cancellare nulla."""
    if os.geteuid() != 0:
        raise Refused("root_required")
    live, backup = docker_inspect(LIVE), docker_inspect(BACKUP)
    cmd("docker", "rm", "-f", NEW_TMP, allow_failure=True)
    if backup is None:
        say("RESULT", "NOTHING_TO_ROLL_BACK" if live is not None else "NO_WEB_CONTAINER")
        return
    if backup.get("State", {}).get("Running") is True:
        raise Refused("previous_web_backup_is_running")
    if live is not None:
        if not str((live.get("Config") or {}).get("Image", "")).startswith(TAG_PREFIX):
            raise Refused("live_web_is_not_the_paper_app_candidate")
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        cmd("docker", "update", "--restart", "no", LIVE)
        cmd("docker", "stop", "-t", "10", LIVE, timeout=40, allow_failure=True)
        cmd("docker", "rename", LIVE, REJECTED_PREFIX + stamp)
        say("rejected_container_kept", REJECTED_PREFIX + stamp)
    cmd("docker", "rename", BACKUP, LIVE)
    cmd("docker", "update", "--restart", "always", LIVE)
    cmd("docker", "restart", "-t", "10", LIVE, timeout=60)
    for _ in range(20):
        if http_code("/api/health") == 200:
            break
        time.sleep(2)
    else:
        raise Refused("restored_web_not_healthy")
    say("RESULT", "PREVIOUS_WEB_RESTORED")


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--deploy", action="store_true")
    g.add_argument("--rollback", action="store_true")
    ap.add_argument("--backend-tar")
    ap.add_argument("--tar-sha256")
    ap.add_argument("--sha")
    ap.add_argument("--brain-unico", action="store_true", help="la web mostra il solo Brain unico PAPER 2000")
    args = ap.parse_args()
    UNICO["on"] = bool(args.brain_unico)
    try:
        (do_deploy if args.deploy else do_rollback)(args)
    except Refused as exc:
        say("RESULT", "REFUSED_" + str(exc)[:200])
        sys.exit(2)


if __name__ == "__main__":
    main()
