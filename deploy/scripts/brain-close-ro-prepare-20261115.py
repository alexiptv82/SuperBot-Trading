#!/usr/bin/env python3
"""Preparazione isolata della patch web Brain PAPER (nessun deploy).

Deriva un'immagine candidata esattamente dall'immagine del container web
corrente e modifica esclusivamente la lettura del lock di exit_service.py.
Non riavvia/sostituisce container; non modifica run, repo o servizi.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

WEB = "superbot"
OLD_TAG = "superbot:rc84-paper-single-close-20261111"
BASE_TAG = "superbot:brain-close-ro-base-20261115"
CANDIDATE = "superbot:brain-close-ro-candidate-20261115"
TARGET = "/app/backend/v3/runner/exit_service.py"
OLD = 'flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)'
NEW = 'flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)'


def cmd(*args: str, capture: bool = True) -> str:
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE if capture else None, timeout=180, check=False)
    if p.returncode:
        raise RuntimeError(f"command_failed: {args[0]} {args[1] if len(args)>1 else ''} / {p.returncode}")
    return (p.stdout or "").strip()


def say(key: str, value: object) -> None:
    print(f"BRAIN_CLOSE_PREPARE {key}={value}", flush=True)


def inspect_container() -> dict:
    x = json.loads(cmd("docker", "inspect", WEB))
    if type(x) is not list or len(x) != 1:
        raise RuntimeError("container_metadata_invalid")
    return x[0]


def image_exists(tag: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", tag],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          check=False, timeout=15).returncode == 0


def main() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("run_as_root")
    web = inspect_container()
    if web.get("State", {}).get("Running") is not True:
        raise RuntimeError("web_not_running")
    if web.get("Config", {}).get("Image") != OLD_TAG:
        raise RuntimeError("web_image_tag_unexpected")
    config = dict(row.split("=", 1) for row in web["Config"].get("Env", []) if "=" in row)
    expected = {
        "DESK_MODE": "paper", "TRADING_MODE": "paper",
        "V3_CUTOVER_READONLY": "1", "V3_CLOSE_BRIDGE_ONLY": "1",
        "V3_ALLOW_BRAIN_SINGLE_CLOSE": "1",
    }
    if any(config.get(k) != v for k, v in expected.items()):
        raise RuntimeError("web_paper_gate_unexpected")
    if not any(m.get("Source") == "/opt/superbot-v3-paper-runs/brain-v3-paper20261111"
               and m.get("RW") is False for m in web.get("Mounts", [])):
        raise RuntimeError("brain_mount_not_ro")
    if image_exists(BASE_TAG) or image_exists(CANDIDATE):
        raise RuntimeError("candidate_or_base_tag_already_exists")
    original_id = web.get("Image")
    if not isinstance(original_id, str) or not original_id.startswith("sha256:"):
        raise RuntimeError("web_image_id_invalid")
    if cmd("docker", "image", "inspect", OLD_TAG, "--format", "{{.Id}}") != original_id:
        raise RuntimeError("web_image_tag_drift")
    say("original_image", original_id)

    with tempfile.TemporaryDirectory(prefix="brain-close-ro-image-") as temp:
        work = Path(temp)
        module = work / "exit_service.py"
        cmd("docker", "cp", WEB + ":" + TARGET, str(module))
        raw = module.read_bytes()
        old_b, new_b = OLD.encode("ascii"), NEW.encode("ascii")
        if raw.count(old_b) != 1 or raw.count(new_b) != 0:
            raise RuntimeError("old_marker_not_unique_or_patch_already_present")
        patched = raw.replace(old_b, new_b, 1)
        if len(patched) != len(raw) + len(new_b) - len(old_b):
            raise RuntimeError("patch_not_surgical")
        module.write_bytes(patched)
        say("original_module_sha256", hashlib.sha256(raw).hexdigest())
        say("patched_module_sha256", hashlib.sha256(patched).hexdigest())
        # La base e' ancorata al medesimo IMAGE ID del web corrente; nessun pull.
        cmd("docker", "tag", original_id, BASE_TAG)
        (work / "Dockerfile").write_text(
            "FROM " + BASE_TAG + "\nCOPY exit_service.py " + TARGET + "\n",
            encoding="ascii")
        cmd("docker", "build", "--pull=false", "--network=none", "-t", CANDIDATE, str(work),
            capture=False)
        probe = ("from pathlib import Path; import inspect; "
                 "import backend.v3.runner.exit_service as e; "
                 "p=Path(e.__file__); s=p.read_text(); "
                 f"assert s.count({NEW!r})==1; "
                 f"assert s.count({OLD!r})==0; "
                 "print('IMAGE_MODULE_OK')")
        out = cmd("docker", "run", "--rm", "--network=none", "--read-only",
                  "--entrypoint", "python3", CANDIDATE, "-B", "-c", probe)
        if "IMAGE_MODULE_OK" not in out:
            raise RuntimeError("image_module_verification_failed")
        if inspect_container().get("Image") != original_id:
            raise RuntimeError("web_image_changed_during_preparation")
        say("candidate_image", cmd("docker", "image", "inspect", CANDIDATE, "--format", "{{.Id}}"))
        say("base_image", BASE_TAG)
        say("candidate_tag", CANDIDATE)
        say("test", "PASS_import_no_network_readonly")
        say("web_untouched", "YES")
        say("deploy_executed", "NO")
        say("ready_for_separate_publish", "YES")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        say("RESULT", "REFUSED_" + type(exc).__name__ + ":" + str(exc)[:100])
        sys.exit(2)
