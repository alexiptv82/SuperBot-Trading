#!/usr/bin/env python3
"""AI Arena: cutover del SOLO container web verso un'immagine con GET /api/v3/arena (sola lettura).

L'immagine candidata NON e' ricostruita dal repository: parte dall'ID dell'immagine web in uso (nessun
pull), aggiunge i 5 file Arena mancanti e inserisce in v3_api.py, del container, UN blocco di 21 righe
(solo lettura; nessun codice di chiusura manuale). Login, impronta, PWA, sessioni (JWT nel DB di /app/data)
e tutti i mount esistenti restano identici: il DB e' lo stesso file.

  --inspect   sola lettura: identita' container/immagine, compatibilita' file, test dell'ancora di patch
  --prepare   costruisce l'immagine candidata (senza rete) e la prova in un container usa-e-getta
  --publish   sostituzione atomica del container web con rollback automatico
  --rollback  ripristina il container precedente (conservato fermo)

Non tocca servizi systemd, run Arena, Brain, journal, nginx, build statica, rete o credenziali.
Nessun segreto viene stampato: l'ambiente passa solo per file 0600 in /run, cancellato a fine esecuzione.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
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
NEW_TMP = "superbot-arena-web-new-20261118"
BACKUP = "superbot-before-arena-web-20261118"
REJECTED_PREFIX = "superbot-arena-web-rejected-"
CURRENT_ID_DEFAULT = "sha256:bb914acdb7d02b55f6c51a27351fa98f69503d5632826af67758e1c11d501366"
BASE_TAG = "superbot:arena-web-readonly-base-20261118"
CANDIDATE_TAG = "superbot:arena-web-readonly-candidate-20261118"
KEEP_TAG = "superbot:before-arena-web-20261118"
ARENA_ROOT = "/opt/superbot-ai-arena-paper"
BACKUPS = "/opt/superbot-v3-backups"
HEALTH = "http://127.0.0.1:8002"
DOMAIN = "superbot-trading.duckdns.org"
EXPECTED_ENV = {"DESK_MODE": "paper", "TRADING_MODE": "paper", "V3_CUTOVER_READONLY": "1"}
WATCH_UNITS = tuple(f"superbot-arena-{kind}@{p}" for kind in ("runner", "exit")
                    for p in ("deepseek", "qwen", "minimax")) + (
    "superbot-v3-paper-brain-runner", "superbot-v3-paper-brain-exit")

OVERLAY_FILES = ("backend/v3/arena/openrouter_transport.py", "backend/v3/arena/read_router.py",
                 "backend/v3/arena/read_view.py", "backend/v3/arena/t0.py", "backend/v3/arena/trial_plan.py")
OVERLAY_SHA256 = {
    "backend/v3/arena/openrouter_transport.py": "87d9b5ce14ad702e852c98a85430cbb3db19a2488d9819fdac3c43e1dd4ffd37",
    "backend/v3/arena/read_router.py": "d4b1b851279494c0fb7c4b6c9f46a345af05624f66618cf3dc073ea4417ced95",
    "backend/v3/arena/read_view.py": "36731d9e207c797ae9c7a05880942b3237b1c2bbfd272a82127628c50bae882a",
    "backend/v3/arena/t0.py": "112d9e4fc2fddec57f839bd8c9d559007ac5ba3b447ff50b5df076421f3f18a2",
    "backend/v3/arena/trial_plan.py": "a357b6c9e6e7f4ab5c3ea89f626b39dfb8f8858a42039cb2be2fb85c035e00a9",
}
BLOCK_SHA256 = "b1f88b29cac93596e31a3588a8865522f19b0ebb82938cd9ba1cd66324736609"
SHARED_READ_CLOSURE = (
    "backend/v3/brain_f2/analyst.py", "backend/v3/brain_f2/contracts.py", "backend/v3/brain_f2/reviewer.py",
    "backend/v3/brain_f3/__init__.py", "backend/v3/brain_f3/providers.py", "backend/v3/dashboard.py",
    "backend/v3/events.py", "backend/v3/outcomes.py", "backend/v3/strategy_label.py",
)
ANCHOR = "    router = APIRouter(prefix='/api/v3')\n"
BLOCK_START = "    # Opt-in ONLY: this adds a session-gated, read-only GET."
BLOCK_END = "    @router.get('/overview')"
MANUAL_CLOSE_MARK = "            # Chiusura manuale PAPER per AI"
SAFE_GET_PATHS = ("/api/health", "/api/auth/webauthn/status", "/api/v3/overview",
                  "/api/v3/brain/config", "/api/v3/brain/status")
COMPARED_HOST = ("Memory", "MemorySwap", "NanoCpus", "CpuShares", "CpuQuota", "CpuPeriod", "PidsLimit", "CapAdd",
                 "CapDrop", "Devices", "Dns", "ExtraHosts", "Tmpfs", "Sysctls", "Ulimits", "GroupAdd", "Init",
                 "Privileged", "ReadonlyRootfs", "NetworkMode", "SecurityOpt", "PortBindings", "LogConfig",
                 "ShmSize", "Runtime", "IpcMode", "PidMode", "UsernsMode")
COMPARED_CONFIG = ("User", "WorkingDir", "Entrypoint", "Cmd", "ExposedPorts", "Healthcheck", "StopSignal",
                   "StopTimeout", "Domainname")
HERE = Path(__file__).resolve().parent
TEST_PREFIX = os.environ.get("ARENA_WEB_TEST_PREFIX", "")
if TEST_PREFIX:  # solo test: percorsi e porte sostituiti, nessun controllo di root
    ARENA_ROOT = TEST_PREFIX + "/arena"
    BACKUPS = TEST_PREFIX + "/backups"
    HEALTH = os.environ["ARENA_WEB_TEST_HEALTH"]


class Refused(RuntimeError):
    pass


CREATED_TAGS: list[str] = []


def say(key: str, value: object) -> None:
    print(f"ARENA_WEB_CUTOVER {key}={value}", flush=True)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


# ---------------------------------------------------------------- patch (pura, testata)

def derive_block(source_text: str) -> str:
    """Blocco di sola lettura estratto da v3_api.py del repository, senza il ramo di chiusura manuale."""
    lines = source_text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith(BLOCK_START)]
    ends = [i for i, line in enumerate(lines) if line.startswith(BLOCK_END)]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise Refused("source_block_markers_not_unique")
    cuts = [i for i in range(starts[0], ends[0]) if lines[i].startswith(MANUAL_CLOSE_MARK)]
    if len(cuts) != 1:
        raise Refused("source_manual_close_marker_not_unique")
    block = "".join(lines[starts[0]:cuts[0]]).rstrip("\n") + "\n"
    if any(word in block for word in ("close_bridge", "close_router", "manual_close", "arena_send")):
        raise Refused("block_contains_close_code")
    ast.parse("def _f():\n    router = 1\n" + block + "    return router\n")
    return block


def patch_v3_api(image_text: str, block: str) -> str:
    """Inserisce il blocco subito dopo la creazione del router; rifiuta ogni ambiguita'."""
    if image_text.count(ANCHOR) != 1:
        raise Refused("image_anchor_not_unique")
    if "V3_ARENA" in image_text or "backend.v3.arena" in image_text:
        raise Refused("image_already_has_arena_code")
    tree = ast.parse(image_text)
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(a.asname or a.name for a in node.names)
    for needed in ("os", "re", "Path"):
        if needed not in names:
            raise Refused("image_missing_import_" + needed)
    patched = image_text.replace(ANCHOR, ANCHOR + "\n" + block, 1)
    ast.parse(patched)
    if len(patched) != len(image_text) + len(block) + 1:
        raise Refused("patch_not_surgical")
    return patched


# ---------------------------------------------------------------- docker helpers

def docker_inspect(name: str) -> dict | None:
    raw = cmd("docker", "inspect", name, allow_failure=True)
    if not raw:
        return None
    obj = json.loads(raw)
    if type(obj) is not list or len(obj) != 1:
        raise Refused("invalid_docker_metadata")
    return obj[0]


def image_id(tag: str) -> str | None:
    out = cmd("docker", "image", "inspect", tag, "--format", "{{.Id}}", allow_failure=True)
    return out or None


def env_map(web: dict) -> dict:
    rows = web["Config"].get("Env") or []
    if type(rows) is not list or any(type(e) is not str or "=" not in e for e in rows):
        raise Refused("invalid_env")
    return dict(x.split("=", 1) for x in rows)


def mount_set(web: dict) -> set:
    return {(m["Destination"], m["Type"], bool(m["RW"]), m.get("Source") if m["Type"] == "bind" else m.get("Name"))
            for m in (web.get("Mounts") or [])}


def norm(value):
    if value in (None, "", [], {}, 0, False, "default"):
        return None
    if value == "bridge":
        return None
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return sorted(v.replace("no-new-privileges:true", "no-new-privileges") for v in value)
    return value


def worker_pids() -> dict[str, str]:
    result = {}
    for unit in WATCH_UNITS:
        if cmd("systemctl", "is-active", unit, allow_failure=True) == "active":
            pid = cmd("systemctl", "show", unit, "-p", "MainPID", "--value", allow_failure=True)
            result[unit] = pid if pid.isdecimal() and int(pid) > 1 else "?"
    return result


def http_code(path: str, base: str | None = None) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request((base or HEALTH) + path), timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (OSError, TimeoutError):
        return 0


def behavior_vector() -> dict[str, int]:
    return {p: http_code(p) for p in SAFE_GET_PATHS}


def public_vector() -> dict[str, int]:
    """Stesse richieste dal percorso pubblico (nginx locale) senza credenziali."""
    out = {}
    for path in ("/api/health", "/api/auth/webauthn/status", "/api/v3/arena"):
        out[path] = int(cmd("curl", "-sS", "--max-time", "10", "--resolve", f"{DOMAIN}:443:127.0.0.1",
                            "-o", "/dev/null", "-w", "%{http_code}", f"https://{DOMAIN}{path}",
                            allow_failure=True) or 0)
    return out


def fresh_env_file(env: dict) -> Path:
    base = (TEST_PREFIX + "/run") if TEST_PREFIX else "/run"
    os.makedirs(base, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix=".arena-web-env-", dir=base)
    os.fchmod(fd, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for k, v in sorted(env.items()):
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) or any(ch in v for ch in "\r\n\0"):
                    raise Refused("unsafe_env_value")
                f.write(k + "=" + v + "\n")
            f.flush()
            os.fsync(f.fileno())
        return Path(filename)
    except BaseException:
        Path(filename).unlink(missing_ok=True)
        raise


def arena_flags(day: str) -> dict:
    return {"V3_ARENA_READONLY_ENABLED": "1", "V3_ARENA_TRIAL_DAY": day}


def check_live(expect_id: str) -> dict:
    if not TEST_PREFIX and os.geteuid() != 0:
        raise Refused("root_required")
    web = docker_inspect(LIVE)
    if web is None or web.get("State", {}).get("Running") is not True:
        raise Refused("web_missing_or_stopped")
    if web.get("Image") != expect_id:
        raise Refused("web_image_id_unexpected:" + str(web.get("Image")))
    env = env_map(web)
    if any(env.get(k) != v for k, v in EXPECTED_ENV.items()):
        raise Refused("web_paper_gates_unexpected")
    if any(k.startswith("V3_ARENA_") for k in env):
        raise Refused("web_already_has_arena_env")
    host = web.get("HostConfig") or {}
    if (host.get("RestartPolicy", {}).get("Name") != "always" or host.get("Privileged") is True
            or host.get("AutoRemove") is True or host.get("NetworkMode") not in ("default", "bridge")):
        raise Refused("unsupported_web_host_configuration")
    bound = (host.get("PortBindings") or {}).get("8001/tcp") or []
    if (set((host.get("PortBindings") or {})) != {"8001/tcp"} or len(bound) != 1
            or bound[0].get("HostIp") != "127.0.0.1" or bound[0].get("HostPort") != "8002"):
        raise Refused("unexpected_web_port_mapping")
    mounts = web.get("Mounts") or []
    dests = [m.get("Destination") for m in mounts]
    if len(dests) != len(set(dests)) or ARENA_ROOT in dests:
        raise Refused("mount_destinations_duplicate_or_arena_present")
    for p in ("/app/data", "/app/backend/.env"):
        if p not in dests:
            raise Refused("missing_original_web_mount_" + p)
    for m in mounts:
        src = m.get("Source") if m.get("Type") == "bind" else m.get("Name")
        if (m.get("Type") not in ("bind", "volume") or type(src) is not str or not src
                or any(ch in src + m["Destination"] for ch in "\n\r\0:") or "docker.sock" in m["Destination"]):
            raise Refused("unsafe_mount")
    arena = Path(ARENA_ROOT)
    if not arena.is_dir() or arena.is_symlink():
        raise Refused("arena_root_missing")
    if http_code("/api/health") != 200:
        raise Refused("web_not_healthy")
    return web


def mount_args(web: dict, *, force_ro: bool) -> list[str]:
    args = []
    for m in web.get("Mounts") or []:
        src = m["Source"] if m["Type"] == "bind" else m["Name"]
        rw = bool(m["RW"]) and not force_ro
        args += ["-v", f"{src}:{m['Destination']}:{'rw' if rw else 'ro'}"]
    args += ["-v", f"{ARENA_ROOT}:{ARENA_ROOT}:ro"]
    return args


def image_hashes(image: str) -> dict:
    script = ("import hashlib, json, os\nout = {}\n"
              "for base, dirs, files in os.walk('/app/backend/v3'):\n"
              "    dirs[:] = [d for d in dirs if d != '__pycache__']\n"
              "    for f in files:\n"
              "        if f.endswith('.py'):\n"
              "            p = os.path.join(base, f)\n"
              "            out[os.path.relpath(p, '/app')] = hashlib.sha256(open(p, 'rb').read()).hexdigest()\n"
              "p = '/app/backend/v3_api.py'\n"
              "out['backend/v3_api.py'] = hashlib.sha256(open(p, 'rb').read()).hexdigest()\n"
              "print(json.dumps(out))\n")
    out = cmd("docker", "run", "--rm", "-i", "--network", "none", "--read-only", "--entrypoint", "python3",
              image, "-B", "-", timeout=90, stdin=script)
    data = json.loads(out)
    if type(data) is not dict:
        raise Refused("image_hash_listing_invalid")
    return data


def read_image_file(image: str, path: str) -> bytes:
    """Byte esatti del file nell'immagine (nessuno strip, nessuna traduzione di fine riga)."""
    try:
        p = subprocess.run(["docker", "run", "--rm", "--network", "none", "--read-only", "--entrypoint", "cat",
                            image, path], capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Refused("command_unavailable_docker") from exc
    if p.returncode or not p.stdout:
        raise Refused("image_file_unreadable")
    return p.stdout


def source_checks(root: Path, sha_pin: str) -> dict:
    """Il codice sorgente dell'overlay e' esattamente quello revisionato (SHA + hash dei file)."""
    texts = {}
    for rel in OVERLAY_FILES + ("backend/v3_api.py", "deploy/scripts/arena_web_probe.py"):
        p = root / rel
        if not p.is_file() or p.is_symlink():
            raise Refused("source_file_missing_" + rel)
        texts[rel] = p.read_bytes()
    for rel in OVERLAY_FILES:
        if sha(texts[rel]) != OVERLAY_SHA256[rel]:
            raise Refused("source_hash_differs_" + rel)
    if not TEST_PREFIX:
        if not re.fullmatch(r"[0-9a-f]{40}", sha_pin or ""):
            raise Refused("sha_pin_required")
        head = cmd("git", "-C", str(root), "rev-parse", "HEAD")
        dirty = cmd("git", "-C", str(root), "status", "--porcelain", "--", *OVERLAY_FILES, "backend/v3_api.py")
        if head != sha_pin or dirty:
            raise Refused("source_not_at_pinned_sha_or_dirty")
    block = derive_block(texts["backend/v3_api.py"].decode())
    if sha(block.encode()) != BLOCK_SHA256:
        raise Refused("source_block_hash_differs")
    return {"texts": texts, "block": block}


def probe_script(root: Path) -> str:
    return (root / "deploy/scripts/arena_web_probe.py").read_text()


def run_candidate_probe(web: dict, image: str, day: str, probe: str) -> str:
    env = {**env_map(web), **arena_flags(day)}
    env_file = fresh_env_file(env)
    try:
        args = ["docker", "run", "--rm", "-i", "--network", "none", "--read-only", "--tmpfs", "/tmp",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "200",
                "--memory", "1g", "--env-file", str(env_file)] + mount_args(web, force_ro=True)
        args += ["--entrypoint", "python3", image, "-B", "-", "candidate", "started"]
        code, out = run_text(*args, timeout=120, stdin=probe)
    finally:
        env_file.unlink(missing_ok=True)
    for line in out.splitlines():
        if line.startswith("ARENA_WEB_PROBE "):
            say("probe_" + line.split(" ", 1)[1].split("=", 1)[0], line.split("=", 1)[1])
    if code != 0 or "ARENA_WEB_PROBE RESULT=PASS_CANDIDATE" not in out:
        raise Refused("candidate_probe_failed:" + ",".join(
            l.split("=", 1)[1] for l in out.splitlines() if l.startswith("ARENA_WEB_PROBE RESULT=")))
    return out


# ---------------------------------------------------------------- modalita'

def do_inspect(args) -> None:
    web = check_live(args.expect_image_id)
    say("web_image", web["Image"])
    say("restart_policy", web["HostConfig"]["RestartPolicy"]["Name"])
    say("mounts", len(web["Mounts"]))
    say("env_names_only", ",".join(sorted(env_map(web))))
    say("arena_flags_absent", "TRUE")
    say("behavior_now", json.dumps(behavior_vector(), sort_keys=True))
    if args.source_root:
        src = source_checks(Path(args.source_root), args.sha)
        hashes = image_hashes(web["Image"])
        for rel in OVERLAY_FILES:
            say("overlay_" + rel.rsplit("/", 1)[1], "MISSING_IN_IMAGE_OK" if rel not in hashes else "ALREADY_IN_IMAGE")
        missing = [r for r in SHARED_READ_CLOSURE if r not in hashes]
        differs = [r for r in SHARED_READ_CLOSURE if r in hashes and hashes[r] != sha((Path(args.source_root) / r).read_bytes())]
        say("shared_closure_missing", ",".join(missing) or "NONE")
        say("shared_closure_differs", ",".join(differs) or "NONE")
        patch_v3_api(read_image_file(web["Image"], "/app/backend/v3_api.py").decode("utf-8"), src["block"])
        say("patch_anchor_test", "PASS")
    say("web_untouched", "TRUE")


def do_prepare(args) -> None:
    CREATED_TAGS.clear()
    try:
        _prepare(args)
    except BaseException:
        for tag in reversed(CREATED_TAGS):
            cmd("docker", "image", "rm", tag, allow_failure=True)
        raise


def _prepare(args) -> None:
    web = check_live(args.expect_image_id)
    src = source_checks(Path(args.source_root), args.sha)
    if image_id(BASE_TAG) or image_id(CANDIDATE_TAG):
        raise Refused("candidate_or_base_tag_already_exists")
    hashes = image_hashes(web["Image"])
    already = [r for r in OVERLAY_FILES if r in hashes]
    if already:
        raise Refused("overlay_files_already_in_image:" + ",".join(already))
    missing = [r for r in SHARED_READ_CLOSURE if r not in hashes]
    if missing:
        raise Refused("shared_read_closure_missing_in_image:" + ",".join(missing))
    old_bytes = read_image_file(web["Image"], "/app/backend/v3_api.py")
    if sha(old_bytes) != hashes["backend/v3_api.py"]:
        raise Refused("image_v3_api_hash_mismatch")
    patched = patch_v3_api(old_bytes.decode("utf-8"), src["block"])
    say("v3_api_image_sha256", hashes["backend/v3_api.py"])
    say("v3_api_patched_sha256", sha(patched.encode()))
    cmd("docker", "tag", web["Image"], BASE_TAG)
    CREATED_TAGS.append(BASE_TAG)
    with tempfile.TemporaryDirectory(prefix="arena-web-image-") as tmp:
        ctx = Path(tmp)
        (ctx / "arena").mkdir()
        for rel in OVERLAY_FILES:
            (ctx / "arena" / rel.rsplit("/", 1)[1]).write_bytes(src["texts"][rel])
        (ctx / "v3_api.py").write_bytes(patched.encode("utf-8"))
        copies = "".join(f"COPY arena/{rel.rsplit('/', 1)[1]} /app/{rel}\n" for rel in OVERLAY_FILES)
        (ctx / "Dockerfile").write_text(f"FROM {BASE_TAG}\n{copies}COPY v3_api.py /app/backend/v3_api.py\n")
        CREATED_TAGS.append(CANDIDATE_TAG)
        cmd("docker", "build", "--pull=false", "--network=none", "-t", CANDIDATE_TAG, str(ctx), timeout=600)
    cand = image_id(CANDIDATE_TAG)
    if not cand or cand == web["Image"]:
        raise Refused("candidate_build_failed")
    run_candidate_probe(web, CANDIDATE_TAG, args.day, probe_script(Path(args.source_root)))
    if docker_inspect(LIVE).get("Image") != web["Image"]:
        raise Refused("web_image_changed_during_preparation")
    say("candidate_image", cand)
    say("candidate_tag", CANDIDATE_TAG)
    say("web_untouched", "TRUE")
    say("deploy_executed", "NO")
    say("RESULT", "CANDIDATE_READY_FOR_SEPARATE_PUBLISH")


def create_args(web: dict, name: str, image: str, env_file: Path) -> list[str]:
    host, cfg = web["HostConfig"], web["Config"]
    args = ["docker", "create", "--name", name, "--restart", "no", "-p", "127.0.0.1:8002:8001",
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


def config_differences(old: dict, new: dict) -> list[str]:
    diffs = []
    for key in COMPARED_HOST:
        if norm((old.get("HostConfig") or {}).get(key)) != norm((new.get("HostConfig") or {}).get(key)):
            diffs.append("HostConfig." + key)
    for key in COMPARED_CONFIG:
        if norm((old.get("Config") or {}).get(key)) != norm((new.get("Config") or {}).get(key)):
            diffs.append("Config." + key)
    return diffs


def start_and_verify(probe: str, before: dict[str, int], pids: dict[str, str]) -> None:
    cmd("docker", "start", LIVE, timeout=60)
    good = False
    for _ in range(30):
        if http_code("/api/health") == 200:
            good = True
            break
        time.sleep(2)
    if not good:
        raise Refused("new_web_not_healthy")
    after = behavior_vector()
    expected = dict(before)
    if after != expected:
        raise Refused("behavior_changed:" + json.dumps(after, sort_keys=True))
    code, out = run_text("docker", "exec", "-i", LIVE, "python3", "-B", "-", "live", "started", timeout=60, stdin=probe)
    for line in out.splitlines():
        if line.startswith("ARENA_WEB_PROBE "):
            say("live_" + line.split(" ", 1)[1].split("=", 1)[0], line.split("=", 1)[1])
    if code != 0 or "ARENA_WEB_PROBE RESULT=PASS_LIVE" not in out:
        raise Refused("live_probe_failed")
    pub = public_vector()
    if pub != {"/api/health": 200, "/api/auth/webauthn/status": 200, "/api/v3/arena": 401}:
        raise Refused("public_path_check_failed:" + json.dumps(pub, sort_keys=True))
    if worker_pids() != pids:
        raise Refused("worker_identity_changed")


def restore_old(*, renamed: bool, new_exists: bool) -> None:
    say("rollback", "START")
    try:
        cmd("docker", "rm", "-f", NEW_TMP, timeout=30, allow_failure=True)
        if new_exists:
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            cmd("docker", "update", "--restart", "no", LIVE, allow_failure=True)
            cmd("docker", "stop", "-t", "10", LIVE, timeout=40, allow_failure=True)
            cmd("docker", "rename", LIVE, REJECTED_PREFIX + stamp, allow_failure=True)
            say("rejected_container_kept", REJECTED_PREFIX + stamp)
        if renamed and docker_inspect(BACKUP):
            cmd("docker", "rename", BACKUP, LIVE)
            cmd("docker", "update", "--restart", "always", LIVE)
            if docker_inspect(LIVE)["State"]["Running"] is not True:
                cmd("docker", "start", LIVE)
        ok = False
        for _ in range(15):
            if http_code("/api/health") == 200:
                ok = True
                break
            time.sleep(2)
        say("rollback", "DONE_PREVIOUS_WEB_RESTORED" if ok else "MANUAL_CHECK_REQUIRED")
    except Exception as exc:  # noqa: BLE001
        say("rollback", "FAILED_" + type(exc).__name__ + "_CHECK_DOCKER")
        raise


def do_publish(args) -> None:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.candidate_id or ""):
        raise Refused("candidate_id_required")
    web = check_live(args.expect_image_id)
    probe = probe_script(Path(args.source_root))
    source_checks(Path(args.source_root), args.sha)
    if docker_inspect(BACKUP) or docker_inspect(NEW_TMP):
        raise Refused("backup_or_temp_container_already_exists")
    if image_id(CANDIDATE_TAG) != args.candidate_id:
        raise Refused("candidate_image_id_differs_from_tested")
    pids = worker_pids()
    before = behavior_vector()
    run_candidate_probe(web, CANDIDATE_TAG, args.day, probe)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    saved = Path(BACKUPS) / f"arena-web-before-{stamp}"
    saved.mkdir(mode=0o700, parents=True)
    inspect_file = saved / "container-inspect.json"
    fd = os.open(inspect_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(web, f, indent=1)
    (saved / "mounts.txt").write_text("\n".join(sorted("%s|%s|%s|%s" % t for t in mount_set(web))) + "\n")
    (saved / "behavior-before.json").write_text(json.dumps(before, sort_keys=True))
    cmd("docker", "tag", web["Image"], KEEP_TAG)
    say("backup", str(saved))
    say("previous_image_kept_as", KEEP_TAG)
    env_file = fresh_env_file({**env_map(web), **arena_flags(args.day)})
    renamed = switched = False
    try:
        cmd(*create_args(web, NEW_TMP, args.candidate_id, env_file), timeout=60)
        new = docker_inspect(NEW_TMP)
        diffs = config_differences(web, new)
        if diffs:
            raise Refused("new_container_config_differs:" + ",".join(diffs))
        if env_map(new) != {**env_map(web), **arena_flags(args.day)}:
            raise Refused("new_container_env_differs")
        if mount_set(new) != mount_set(web) | {(ARENA_ROOT, "bind", False, ARENA_ROOT)}:
            raise Refused("new_container_mounts_differ")
        say("new_config_identical_except_arena", "TRUE")
        current = docker_inspect(LIVE)
        if current is None or current.get("Id") != web.get("Id") or worker_pids() != pids:
            raise Refused("state_changed_since_preflight")
        cmd("docker", "update", "--restart", "no", LIVE)
        cmd("docker", "stop", "-t", "10", LIVE, timeout=40)
        cmd("docker", "rename", LIVE, BACKUP)
        renamed = True
        cmd("docker", "rename", NEW_TMP, LIVE)
        switched = True
        start_and_verify(probe, before, pids)
        cmd("docker", "update", "--restart", "always", LIVE)
        say("web_replaced", "TRUE")
        say("login_webauthn_status_ok", "TRUE")
        say("workers_untouched", "TRUE")
        say("old_web_backup_stopped", BACKUP)
        say("RESULT", "WEB_UPDATED_ARENA_READONLY")
    except BaseException:
        if renamed:
            restore_old(renamed=True, new_exists=switched)
        else:
            cmd("docker", "rm", "-f", NEW_TMP, allow_failure=True)
            cmd("docker", "update", "--restart", "always", LIVE, allow_failure=True)
            cmd("docker", "start", LIVE, timeout=60, allow_failure=True)
        raise
    finally:
        env_file.unlink(missing_ok=True)


def do_rollback(args) -> None:
    """Idempotente: dopo un publish riuscito, dopo un'interruzione a meta' (SIGKILL, sessione persa) o in dubbio."""
    live, backup, tmp = docker_inspect(LIVE), docker_inspect(BACKUP), docker_inspect(NEW_TMP)
    candidate = image_id(CANDIDATE_TAG)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    if tmp is not None:
        cmd("docker", "rm", "-f", NEW_TMP, timeout=30)
        say("temporary_new_container_removed", "TRUE")
    if backup is None:
        if live is None:
            raise Refused("nothing_to_restore_and_no_web_container")
        if candidate and live.get("Image") == candidate:
            raise Refused("live_is_candidate_but_previous_backup_missing_manual_check")
        say("previous_web_already_in_place", "TRUE")
    else:
        if backup.get("State", {}).get("Running") is True:
            raise Refused("previous_web_backup_is_running")
        if live is not None:
            if not candidate or live.get("Image") != candidate:
                raise Refused("live_web_is_not_the_candidate")
            cmd("docker", "update", "--restart", "no", LIVE)
            cmd("docker", "stop", "-t", "10", LIVE, timeout=40, allow_failure=True)
            cmd("docker", "rename", LIVE, REJECTED_PREFIX + stamp)
            say("rejected_container_kept", REJECTED_PREFIX + stamp)
        cmd("docker", "rename", BACKUP, LIVE)
    cmd("docker", "update", "--restart", "always", LIVE)
    if docker_inspect(LIVE)["State"]["Running"] is not True:
        cmd("docker", "start", LIVE, timeout=60)
    for _ in range(20):
        if http_code("/api/health") == 200:
            break
        time.sleep(2)
    else:
        raise Refused("restored_web_not_healthy")
    say("rollback", "PREVIOUS_WEB_IN_PLACE")
    say("behavior_now", json.dumps(behavior_vector(), sort_keys=True))
    say("RESULT", "PREVIOUS_WEB_RESTORED")


def main() -> None:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    for flag in ("inspect", "prepare", "publish", "rollback"):
        mode.add_argument("--" + flag, action="store_true")
    ap.add_argument("--source-root")
    ap.add_argument("--sha")
    ap.add_argument("--day", default="2026-11-18")
    ap.add_argument("--candidate-id")
    ap.add_argument("--expect-image-id", default=CURRENT_ID_DEFAULT)
    args = ap.parse_args()
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", args.day):
        raise Refused("invalid_day")
    if (args.prepare or args.publish) and not args.source_root:
        raise Refused("source_root_required")
    {"inspect": do_inspect, "prepare": do_prepare, "publish": do_publish, "rollback": do_rollback}[
        next(k for k in ("inspect", "prepare", "publish", "rollback") if getattr(args, k))](args)


if __name__ == "__main__":
    try:
        main()
    except Refused as exc:
        say("RESULT", "REFUSED_" + str(exc)[:160])
        sys.exit(2)
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        say("RESULT", "FAILED_" + type(exc).__name__ + ":" + str(exc)[:100])
        sys.exit(2)
