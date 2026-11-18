"""Cutover web Arena: patch, pin di integrita', orchestrazione con Docker finto, sonda su immagine simulata.

Nessuna rete, nessun Docker vero, nessuna scrittura fuori da tmp. Il test end-to-end con mount in sola lettura
vero gira solo se l'ambiente lo consente (root, mount, interprete con le dipendenze dell'app).
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/scripts/arena-web-readonly-cutover-20261118.py"
SECRET = "SUPERSECRETVALUE-do-not-print-9f3a"
OLD_ID = "sha256:" + "a" * 64
CAND_ID = "sha256:" + "c" * 64


def _load(prefix: str, health: str = "http://127.0.0.1:1"):
    os.environ["ARENA_WEB_TEST_PREFIX"] = prefix
    os.environ["ARENA_WEB_TEST_HEALTH"] = health
    import types
    mod = types.ModuleType("arena_cutover_under_test")
    mod.__file__ = str(SCRIPT)
    exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), mod.__dict__)        # niente .pyc: sorgente sempre attuale
    return mod


# ------------------------------------------------------------------ parte pura

@pytest.fixture(scope="module")
def pure(tmp_path_factory):
    return _load(str(tmp_path_factory.mktemp("pure")))


def _repo_text() -> str:
    return (ROOT / "backend/v3_api.py").read_text()


def _pre_arena_text() -> str:
    lines = _repo_text().splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if l.startswith("    # Opt-in ONLY: this adds a session-gated"))
    end = next(i for i, l in enumerate(lines) if l.startswith("    @router.get('/overview')"))
    return "".join(lines[:start] + lines[end:])


def test_source_pins_match_the_reviewed_files(pure):
    for rel in pure.OVERLAY_FILES:
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == pure.OVERLAY_SHA256[rel], rel
    block = pure.derive_block(_repo_text())
    assert hashlib.sha256(block.encode()).hexdigest() == pure.BLOCK_SHA256


def test_block_is_read_only_and_contains_no_close_code(pure):
    block = pure.derive_block(_repo_text())
    for word in ("close_bridge", "close_router", "manual_close", "arena_send", "post(", "delete(", "put("):
        assert word not in block
    assert "make_arena_router" in block and "enabled=True" in block and "require_session" in block
    for gate in ("V3_ARENA_READONLY_ENABLED", "DESK_MODE", "TRADING_MODE", "V3_ARENA_TRIAL_DAY"):
        assert gate in block


def test_patch_equals_repo_version_minus_manual_close(pure):
    block = pure.derive_block(_repo_text())
    patched = pure.patch_v3_api(_pre_arena_text(), block)
    lines = _repo_text().splitlines(keepends=True)
    cut = next(i for i, l in enumerate(lines) if l.startswith(pure.MANUAL_CLOSE_MARK))
    end = next(i for i, l in enumerate(lines) if l.startswith("    @router.get('/overview')"))
    expected = "".join(lines[:cut] + ["\n"] + lines[end:])
    assert patched == expected
    ast.parse(patched)
    assert patched.count("make_arena_router") == 2 and "backend.v3.arena.close" not in patched


def test_patch_refuses_ambiguity(pure):
    block = pure.derive_block(_repo_text())
    old = _pre_arena_text()
    with pytest.raises(pure.Refused, match="anchor_not_unique"):
        pure.patch_v3_api(old.replace(pure.ANCHOR, "    router = None\n"), block)
    with pytest.raises(pure.Refused, match="anchor_not_unique"):
        pure.patch_v3_api(old + "\n" + pure.ANCHOR, block)
    with pytest.raises(pure.Refused, match="already_has_arena_code"):
        pure.patch_v3_api(old.replace(pure.ANCHOR, pure.ANCHOR + "    x = 'V3_ARENA_X'\n"), block)
    with pytest.raises(pure.Refused, match="missing_import_re"):
        pure.patch_v3_api(old.replace("import re\n", "import sys\n", 1), block)


def test_read_path_closure_is_exactly_the_overlay_plus_known_shared_modules(pure):
    seen, todo = {}, ["backend.v3.arena.trial_plan", "backend.v3.arena.read_router"]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        p = ROOT / (name.replace(".", "/") + ".py")
        if not p.exists():
            p = ROOT / name.replace(".", "/") / "__init__.py"
            if not p.exists():
                continue
        seen[name] = p
        pkg = name if p.name == "__init__.py" else name.rsplit(".", 1)[0]
        for node in ast.walk(ast.parse(p.read_text())):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = (node.module or "") if not node.level else ".".join(
                    pkg.split(".")[:len(pkg.split(".")) - (node.level - 1)] + ([node.module] if node.module else []))
                mods = [base] + [base + "." + a.name for a in node.names]
            for m in mods:
                if m.startswith("backend"):
                    todo.append(m)
                    parts = m.split(".")
                    todo.extend(".".join(parts[:k]) for k in range(1, len(parts)))
    files = {str(p.relative_to(ROOT)) for p in seen.values()}
    arena = {f for f in files if f.startswith("backend/v3/arena/")}
    assert arena == set(pure.OVERLAY_FILES)
    shared = files - arena - {"backend/__init__.py", "backend/v3/__init__.py"}
    assert shared == set(pure.SHARED_READ_CLOSURE)


@pytest.mark.skipif(subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", "42934567^{commit}"],
                                   capture_output=True).returncode != 0, reason="storia git non disponibile")
def test_patch_applies_to_the_last_pre_arena_version_of_v3_api(pure):
    old = subprocess.run(["git", "-C", str(ROOT), "show", "42934567:backend/v3_api.py"],
                         capture_output=True, text=True, check=True).stdout
    patched = pure.patch_v3_api(old, pure.derive_block(_repo_text()))
    ast.parse(patched)
    assert patched.count(pure.ANCHOR) == 1 and "V3_ARENA_READONLY_ENABLED" in patched


# ------------------------------------------------------------------ Docker finto

FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, sys, hashlib
S = os.environ["FAKE_STATE"]
st = json.load(open(S))
a = sys.argv[1:]
fail = os.environ.get("FAKE_FAIL", "")
def save(): json.dump(st, open(S, "w"))
def log(*x): st["log"].append(" ".join(x)); save()
def out(o): print(json.dumps(o)); sys.exit(0)
def opt(name):
    return [a[i + 1] for i, v in enumerate(a) if v == name and i + 1 < len(a)]
cmd = a[0]
if cmd == "inspect":
    c = st["containers"].get(a[1])
    if not c: sys.exit(1)
    out([c])
if cmd == "image" and a[1] == "inspect":
    i = st["images"].get(a[2])
    if not i: sys.exit(1)
    print(i); sys.exit(0)
if cmd == "image" and a[1] == "rm":
    log("image-rm", a[2]); st["images"].pop(a[2], None); save(); sys.exit(0)
if cmd == "tag":
    log("tag", a[1], a[2]); st["images"][a[2]] = st["images"].get(a[1], a[1]); save(); sys.exit(0)
if cmd == "run":
    stdin = sys.stdin.read() if "-i" in a else ""
    if "cat" in a and "--entrypoint" in a:
        print(st["v3_api_text"], end=""); sys.exit(0)
    if "os.walk" in stdin:
        print(json.dumps(st["image_hashes"])); sys.exit(0)
    if "candidate" in a:
        log("candidate-probe", " ".join(x for x in a if x.startswith("/") or x.endswith(":ro")))
        assert any(x.endswith(":ro") for x in a), "mounts must be read-only"
        assert not any(x.endswith(":rw") for x in a), "no rw mount in probe"
        assert "--network" in a and a[a.index("--network") + 1] == "none"
        if fail == "candidate_probe":
            print("ARENA_WEB_PROBE RESULT=FAILED_arena_routes_unexpected"); sys.exit(2)
        print("ARENA_WEB_PROBE arena_routes=GET_ONLY\nARENA_WEB_PROBE RESULT=PASS_CANDIDATE"); sys.exit(0)
    sys.exit(0)
if cmd == "build":
    ctx = a[-1]
    log("build", sorted(os.listdir(ctx)).__repr__())
    st["build_ctx"] = {n: open(os.path.join(ctx, n)).read() for n in os.listdir(ctx) if n != "arena"}
    st["build_ctx"]["arena"] = sorted(os.listdir(os.path.join(ctx, "arena")))
    st["images"][a[a.index("-t") + 1]] = st["candidate_id"]; save(); sys.exit(0)
if cmd == "create":
    name = opt("--name")[0]; image = a[-1]
    old = st["containers"]["superbot"]
    env = dict(e.split("=", 1) for e in st["image_env"])
    for line in open(opt("--env-file")[0]).read().splitlines():
        k, v = line.split("=", 1); env[k] = v
    binds = [v for v in opt("-v")]
    mounts = [{"Destination": b.split(":")[1], "Source": b.split(":")[0], "Type": "bind", "RW": b.endswith(":rw")} for b in binds]
    host = {"PortBindings": {"8001/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8002"}]},
            "SecurityOpt": opt("--security-opt"), "RestartPolicy": {"Name": opt("--restart")[0]},
            "NetworkMode": "default", "Privileged": False}
    cfg = {"User": (opt("--user") or [""])[0], "WorkingDir": (opt("--workdir") or [""])[0],
           "Env": ["%s=%s" % kv for kv in env.items()], "Entrypoint": None, "Cmd": old["Config"]["Cmd"], "Image": image}
    st["containers"][name] = {"Id": "id-" + name, "Name": name, "Image": st["images_by_tag"].get(image, image),
                              "State": {"Running": False}, "Config": cfg, "HostConfig": host, "Mounts": mounts}
    log("create", name); save(); sys.exit(0)
if cmd == "start":
    if fail == "start_new" and st["containers"][a[1]]["Image"] == st["candidate_id"]: sys.exit(1)
    st["containers"][a[1]]["State"]["Running"] = True; log("start", a[1]); sys.exit(0)
if cmd == "stop":
    if fail == "stop_old" and a[-1] == "superbot": sys.exit(1)
    st["containers"][a[-1]]["State"]["Running"] = False; log("stop", a[-1]); sys.exit(0)
if cmd == "rename":
    if fail == "rename_new" and a[1] == "superbot-arena-web-new-20261118": sys.exit(1)
    st["containers"][a[2]] = st["containers"].pop(a[1]); st["containers"][a[2]]["Name"] = a[2]; log("rename", a[1], a[2]); sys.exit(0)
if cmd == "update":
    st["containers"][a[-1]]["HostConfig"]["RestartPolicy"] = {"Name": a[a.index("--restart") + 1]}; log("update", a[-1], a[a.index("--restart") + 1]); sys.exit(0)
if cmd == "rm":
    st["containers"].pop(a[-1], None); log("rm", a[-1]); sys.exit(0)
if cmd == "exec":
    c = st["containers"].get(a[2])
    sys.stdin.read()
    if not c or not c["State"]["Running"] or c["Image"] != st["candidate_id"] or fail == "live_probe":
        print("ARENA_WEB_PROBE RESULT=FAILED_valid_session_status_401"); sys.exit(2)
    print("ARENA_WEB_PROBE no_session=401\nARENA_WEB_PROBE valid_session=200\nARENA_WEB_PROBE RESULT=PASS_LIVE"); sys.exit(0)
sys.exit(0)
'''

FAKE_SYSTEMCTL = r'''#!/usr/bin/env python3
import os, sys
a = sys.argv[1:]
if a[0] == "is-active":
    print("active"); sys.exit(0)
if a[0] == "show":
    pid = "4242"
    if os.environ.get("FAKE_FAIL") == "pid_change" and os.path.exists(os.environ["FAKE_STATE"] + ".switched"):
        pid = "9999"
    print(pid); sys.exit(0)
sys.exit(0)
'''

FAKE_CURL = r'''#!/usr/bin/env python3
import json, os, sys
st = json.load(open(os.environ["FAKE_STATE"]))
url = sys.argv[-1]
c = st["containers"].get("superbot")
new = bool(c and c["State"]["Running"] and c["Image"] == st["candidate_id"])
code = 200
if url.endswith("/api/v3/arena"):
    code = 401 if new else 404
if os.environ.get("FAKE_FAIL") == "public" and url.endswith("/api/auth/webauthn/status"):
    code = 502
print(code, end="")
'''


class FakeHost:
    def __init__(self, tmp_path, monkeypatch):
        self.tmp = tmp_path
        self.state_file = tmp_path / "state.json"
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        for name, body in (("docker", FAKE_DOCKER), ("systemctl", FAKE_SYSTEMCTL), ("curl", FAKE_CURL)):
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        (tmp_path / "arena").mkdir()
        (tmp_path / "backups").mkdir()
        old = {"Id": "id-superbot", "Name": "superbot", "Image": OLD_ID, "State": {"Running": True},
               "Config": {"User": "", "WorkingDir": "/app", "Entrypoint": None, "Cmd": ["python", "-m", "uvicorn"],
                          "Env": ["PATH=/usr/bin", "PYTHONPATH=/app/backend", "DESK_MODE=paper", "TRADING_MODE=paper",
                                  "V3_CUTOVER_READONLY=1", "TELEGRAM_TOKEN=" + SECRET], "Image": "superbot:old"},
               "HostConfig": {"PortBindings": {"8001/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8002"}]},
                              "SecurityOpt": ["no-new-privileges:true"], "RestartPolicy": {"Name": "always"},
                              "NetworkMode": "default", "Privileged": False},
               "Mounts": [
                   {"Destination": "/app/data", "Source": "/opt/web-data", "Type": "bind", "RW": True},
                   {"Destination": "/app/backend/.env", "Source": "/opt/web.env", "Type": "bind", "RW": True},
                   {"Destination": "/opt/superbot-v3-paper-runs/brain", "Source": "/opt/superbot-v3-paper-runs/brain",
                    "Type": "bind", "RW": False}]}
        self.state = {
            "containers": {"superbot": old}, "log": [], "candidate_id": CAND_ID,
            "images": {"superbot:old": OLD_ID}, "images_by_tag": {"superbot:arena-web-readonly-candidate-20261118": CAND_ID},
            "image_env": ["PATH=/usr/bin", "PYTHONPATH=/app/backend", "DESK_MODE=paper", "TRADING_MODE=paper",
                          "V3_CUTOVER_READONLY=1", "TELEGRAM_TOKEN=" + SECRET],
            "v3_api_text": _pre_arena_text(),
            "image_hashes": {"backend/v3_api.py": hashlib.sha256(_pre_arena_text().encode()).hexdigest(),
                             **{r: "0" * 64 for r in ("backend/v3/brain_f2/analyst.py", "backend/v3/brain_f2/contracts.py",
                                                       "backend/v3/brain_f2/reviewer.py", "backend/v3/brain_f3/__init__.py",
                                                       "backend/v3/brain_f3/providers.py", "backend/v3/dashboard.py",
                                                       "backend/v3/events.py", "backend/v3/outcomes.py",
                                                       "backend/v3/strategy_label.py")}},
        }
        self.state["images"]["superbot:arena-web-readonly-candidate-20261118"] = CAND_ID
        self.save()
        monkeypatch.setenv("PATH", str(self.bin) + os.pathsep + os.environ["PATH"])
        monkeypatch.setenv("FAKE_STATE", str(self.state_file))
        monkeypatch.delenv("FAKE_FAIL", raising=False)
        self.server = HTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.health = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.mod = _load(str(tmp_path), self.health)
        monkeypatch.setattr(self.mod.time, "sleep", lambda s: None)

    def save(self):
        self.state_file.write_text(json.dumps(self.state))

    def reload(self):
        self.state = json.loads(self.state_file.read_text())
        return self.state

    def _handler(host):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                st = json.loads(host.state_file.read_text())
                c = st["containers"].get("superbot")
                if not c or not c["State"]["Running"]:
                    self.send_response(503); self.end_headers(); return
                new = c["Image"] == st["candidate_id"]
                path = self.path
                code, body = 401, b"{}"
                if path == "/api/health":
                    code = 200
                elif path == "/api/auth/webauthn/status":
                    code, body = 200, b'{"available": true, "has_credentials": true}'
                elif path == "/api/v3/arena":
                    code = 401 if new else 404
                if os.environ.get("FAKE_FAIL") == "behavior" and new and path == "/api/v3/overview":
                    code = 500
                if os.environ.get("FAKE_FAIL") == "unhealthy" and new:
                    code = 503
                self.send_response(code); self.end_headers(); self.wfile.write(body)
        return H

    def args(self, **kw):
        base = dict(source_root=str(ROOT), sha="0" * 40, day="2026-11-18", candidate_id=CAND_ID, expect_image_id=OLD_ID)
        base.update(kw)
        return type("A", (), base)()

    def live(self):
        return self.reload()["containers"].get("superbot")

    def fresh_prepare(self):
        self.state = self.reload()
        self.state["images"].pop("superbot:arena-web-readonly-candidate-20261118", None)
        self.save()
        self.mod.CREATED_TAGS.clear()


@pytest.fixture
def host(tmp_path, monkeypatch):
    h = FakeHost(tmp_path, monkeypatch)
    yield h
    h.server.shutdown()


def test_publish_success_replaces_only_the_web_container_and_keeps_the_previous_one(host, capsys):
    host.mod.do_publish(host.args())
    st = host.reload()
    live, backup = st["containers"]["superbot"], st["containers"][host.mod.BACKUP]
    assert live["Image"] == CAND_ID and live["State"]["Running"] and live["HostConfig"]["RestartPolicy"]["Name"] == "always"
    assert backup["Image"] == OLD_ID and not backup["State"]["Running"] and backup["HostConfig"]["RestartPolicy"]["Name"] == "no"
    assert host.mod.NEW_TMP not in st["containers"]
    old_mounts = {(m["Destination"], m["RW"]) for m in backup["Mounts"]}
    new_mounts = {(m["Destination"], m["RW"]) for m in live["Mounts"]}
    assert new_mounts == old_mounts | {(host.mod.ARENA_ROOT, False)}
    env = dict(e.split("=", 1) for e in live["Config"]["Env"])
    assert env["V3_ARENA_READONLY_ENABLED"] == "1" and env["V3_ARENA_TRIAL_DAY"] == "2026-11-18"
    assert env["DESK_MODE"] == "paper" and env["TELEGRAM_TOKEN"] == SECRET        # ambiente conservato
    assert "V3_ARENA_ALLOW_MANUAL_CLOSE" not in env
    assert host.mod.KEEP_TAG in st["images"] and st["images"][host.mod.KEEP_TAG] == OLD_ID
    saved = next((host.tmp / "backups").iterdir())
    assert oct((saved / "container-inspect.json").stat().st_mode & 0o777) == "0o600"
    assert oct(saved.stat().st_mode & 0o777) == "0o700"
    assert not list((host.tmp / "run").glob(".arena-web-env-*"))                  # env-file cancellato
    printed = capsys.readouterr()
    assert SECRET not in printed.out + printed.err
    assert "RESULT=WEB_UPDATED_ARENA_READONLY" in printed.out


def test_publish_never_prints_or_stores_the_secret_outside_the_private_inspect_copy(host, capsys):
    host.mod.do_publish(host.args())
    for f in (host.tmp / "backups").rglob("*"):
        if f.is_file() and f.name != "container-inspect.json":
            assert SECRET not in f.read_text()
    assert SECRET not in capsys.readouterr().out


def test_publish_refuses_before_touching_anything_when_config_would_differ(host):
    host.state["containers"]["superbot"]["HostConfig"]["Memory"] = 512 * 1024 * 1024     # limite che create non replica
    host.save()
    with pytest.raises(host.mod.Refused, match="new_container_config_differs:HostConfig.Memory"):
        host.mod.do_publish(host.args())
    st = host.reload()
    assert st["containers"]["superbot"]["State"]["Running"] and st["containers"]["superbot"]["Image"] == OLD_ID
    assert host.mod.NEW_TMP not in st["containers"] and host.mod.BACKUP not in st["containers"]
    assert not any(l.startswith(("stop", "rename")) for l in st["log"])


@pytest.mark.parametrize("fail, match", [("candidate_probe", "candidate_probe_failed")])
def test_publish_refuses_when_the_candidate_probe_fails(host, monkeypatch, fail, match):
    monkeypatch.setenv("FAKE_FAIL", fail)
    with pytest.raises(host.mod.Refused, match=match):
        host.mod.do_publish(host.args())
    st = host.reload()
    assert st["containers"]["superbot"]["Image"] == OLD_ID and st["containers"]["superbot"]["State"]["Running"]
    assert not any(l.startswith(("create", "stop", "rename")) for l in st["log"])


@pytest.mark.parametrize("fail", ["live_probe", "public", "behavior", "unhealthy", "pid_change", "start_new"])
def test_publish_rolls_back_automatically_when_any_post_switch_check_fails(host, monkeypatch, fail):
    monkeypatch.setenv("FAKE_FAIL", fail)
    if fail == "pid_change":
        original = host.mod.cmd

        def cmd(*a, **k):
            result = original(*a, **k)
            if a[:2] == ("docker", "start"):
                Path(str(host.state_file) + ".switched").write_text("1")
            return result
        monkeypatch.setattr(host.mod, "cmd", cmd)
    with pytest.raises(host.mod.Refused):
        host.mod.do_publish(host.args())
    st = host.reload()
    live = st["containers"]["superbot"]
    assert live["Image"] == OLD_ID and live["State"]["Running"] and live["HostConfig"]["RestartPolicy"]["Name"] == "always"
    assert host.mod.BACKUP not in st["containers"] and host.mod.NEW_TMP not in st["containers"]
    rejected = [n for n in st["containers"] if n.startswith(host.mod.REJECTED_PREFIX)]
    assert len(rejected) == 1 and st["containers"][rejected[0]]["Image"] == CAND_ID                  # conservato per i log
    assert not st["containers"][rejected[0]]["State"]["Running"]


@pytest.mark.parametrize("fail", ["stop_old", "rename_new"])
def test_publish_failure_between_stop_and_switch_leaves_the_previous_web_running(host, monkeypatch, fail):
    monkeypatch.setenv("FAKE_FAIL", fail)
    with pytest.raises(host.mod.Refused):
        host.mod.do_publish(host.args())
    st = host.reload()
    live = st["containers"]["superbot"]
    assert live["Image"] == OLD_ID and live["State"]["Running"] and live["HostConfig"]["RestartPolicy"]["Name"] == "always"
    assert host.mod.NEW_TMP not in st["containers"] and host.mod.BACKUP not in st["containers"]


def test_manual_rollback_after_success_and_it_is_idempotent(host):
    host.mod.do_publish(host.args())
    host.mod.do_rollback(host.args())
    st = host.reload()
    assert st["containers"]["superbot"]["Image"] == OLD_ID and st["containers"]["superbot"]["State"]["Running"]
    assert st["containers"]["superbot"]["HostConfig"]["RestartPolicy"]["Name"] == "always"
    host.mod.do_rollback(host.args())                                                                  # seconda volta: nessun danno
    assert host.live()["Image"] == OLD_ID and host.live()["State"]["Running"]


def test_rollback_recovers_a_session_killed_after_stop_and_rename(host):
    st = host.reload()
    old = st["containers"].pop("superbot")
    old["State"]["Running"] = False
    old["HostConfig"]["RestartPolicy"] = {"Name": "no"}
    st["containers"][host.mod.BACKUP] = old
    st["containers"][host.mod.NEW_TMP] = {**old, "Image": CAND_ID, "State": {"Running": False}}
    host.state = st
    host.save()
    host.mod.do_rollback(host.args())
    st = host.reload()
    assert st["containers"]["superbot"]["Image"] == OLD_ID and st["containers"]["superbot"]["State"]["Running"]
    assert host.mod.NEW_TMP not in st["containers"] and host.mod.BACKUP not in st["containers"]


def test_rollback_recovers_a_session_killed_after_old_web_was_stopped_but_before_rename(host):
    st = host.reload()
    st["containers"]["superbot"]["State"]["Running"] = False
    st["containers"]["superbot"]["HostConfig"]["RestartPolicy"] = {"Name": "no"}
    st["containers"][host.mod.NEW_TMP] = {**st["containers"]["superbot"], "Image": CAND_ID}
    host.state = st
    host.save()
    host.mod.do_rollback(host.args())
    live = host.live()
    assert live["Image"] == OLD_ID and live["State"]["Running"] and live["HostConfig"]["RestartPolicy"]["Name"] == "always"
    assert host.mod.NEW_TMP not in host.reload()["containers"]


def test_rollback_refuses_when_live_is_an_unexpected_image(host):
    st = host.reload()
    old = st["containers"].pop("superbot")
    old["State"]["Running"] = False
    st["containers"][host.mod.BACKUP] = old
    st["containers"]["superbot"] = {**old, "Image": "sha256:" + "f" * 64, "State": {"Running": True}}
    host.state = st
    host.save()
    with pytest.raises(host.mod.Refused, match="live_web_is_not_the_candidate"):
        host.mod.do_rollback(host.args())


def test_publish_refuses_wrong_candidate_wrong_image_or_existing_backup(host):
    with pytest.raises(host.mod.Refused, match="candidate_id_required"):
        host.mod.do_publish(host.args(candidate_id=None))
    with pytest.raises(host.mod.Refused, match="candidate_image_id_differs"):
        host.mod.do_publish(host.args(candidate_id="sha256:" + "d" * 64))
    with pytest.raises(host.mod.Refused, match="web_image_id_unexpected"):
        host.mod.do_publish(host.args(expect_image_id="sha256:" + "b" * 64))
    host.state["containers"][host.mod.BACKUP] = {"Id": "x", "State": {"Running": False}}
    host.save()
    with pytest.raises(host.mod.Refused, match="backup_or_temp_container_already_exists"):
        host.mod.do_publish(host.args())
    assert host.live()["Image"] == OLD_ID


@pytest.mark.parametrize("mutation, match", [
    (lambda c: c["Config"]["Env"].append("V3_ARENA_READONLY_ENABLED=1"), "web_already_has_arena_env"),
    (lambda c: c["Config"]["Env"].remove("DESK_MODE=paper"), "web_paper_gates_unexpected"),
    (lambda c: c["HostConfig"].update(Privileged=True), "unsupported_web_host_configuration"),
    (lambda c: c["HostConfig"]["PortBindings"]["8001/tcp"][0].update(HostIp="0.0.0.0"), "unexpected_web_port_mapping"),
    (lambda c: c["Mounts"].append({"Destination": "/var/run/docker.sock", "Source": "/var/run/docker.sock",
                                   "Type": "bind", "RW": True}), "unsafe_mount"),
    (lambda c: c["Mounts"].append({"Destination": "@ARENA@", "Source": "/x", "Type": "bind",
                                   "RW": False}), "arena_present"),
])
def test_publish_preflight_refuses_unexpected_live_configuration(host, mutation, match):
    mutation(host.state["containers"]["superbot"])
    for m in host.state["containers"]["superbot"]["Mounts"]:
        if m["Destination"] == "@ARENA@":
            m["Destination"] = host.mod.ARENA_ROOT
    host.save()
    with pytest.raises(host.mod.Refused, match=match):
        host.mod.do_publish(host.args())
    assert not any(l.startswith(("create", "stop", "rename")) for l in host.reload()["log"])


def test_prepare_builds_from_the_running_image_with_only_the_five_files_and_the_patched_module(host, capsys):
    host.fresh_prepare()
    host.mod.do_prepare(host.args())
    st = host.reload()
    ctx = st["build_ctx"]
    assert st["images"][host.mod.BASE_TAG] == OLD_ID
    assert ctx["Dockerfile"].startswith("FROM " + host.mod.BASE_TAG)
    assert ctx["arena"] == sorted(Path(r).name for r in host.mod.OVERLAY_FILES)
    assert ctx["Dockerfile"].count("COPY") == 6 and "RUN" not in ctx["Dockerfile"]
    assert "make_arena_router" in ctx["v3_api.py"] and "backend.v3.arena.close" not in ctx["v3_api.py"]
    out = capsys.readouterr().out
    assert "RESULT=CANDIDATE_READY_FOR_SEPARATE_PUBLISH" in out and SECRET not in out
    assert host.live()["Image"] == OLD_ID and host.live()["State"]["Running"]


def test_prepare_refuses_without_removing_an_existing_good_candidate(host):
    host.fresh_prepare()
    host.mod.do_prepare(host.args())
    host.state = host.reload()
    with pytest.raises(host.mod.Refused, match="candidate_or_base_tag_already_exists"):
        host.mod.do_prepare(host.args())
    assert host.mod.CANDIDATE_TAG in host.reload()["images"]


def test_prepare_failure_cleans_only_the_tags_it_created(host, monkeypatch):
    host.fresh_prepare()
    monkeypatch.setenv("FAKE_FAIL", "candidate_probe")
    host.mod.CREATED_TAGS.clear()
    with pytest.raises(host.mod.Refused, match="candidate_probe_failed"):
        host.mod.do_prepare(host.args())
    images = host.reload()["images"]
    assert host.mod.BASE_TAG not in images and host.mod.CANDIDATE_TAG not in images and "superbot:old" in images


def test_prepare_refuses_when_overlay_files_already_exist_in_the_image(host):
    host.fresh_prepare()
    host.state["image_hashes"]["backend/v3/arena/read_view.py"] = "1" * 64
    host.save()
    with pytest.raises(host.mod.Refused, match="overlay_files_already_in_image"):
        host.mod.do_prepare(host.args())
    assert host.mod.BASE_TAG not in host.reload()["images"]


def test_inspect_reports_without_changing_anything_or_printing_secrets(host, capsys):
    before = json.dumps(host.reload()["containers"], sort_keys=True)
    host.mod.do_inspect(host.args())
    out = capsys.readouterr().out
    assert "web_untouched=TRUE" in out and "patch_anchor_test=PASS" in out and SECRET not in out
    assert "TELEGRAM_TOKEN" in out                                              # solo il nome
    assert json.dumps(host.reload()["containers"], sort_keys=True) == before


# ------------------------------------------------------------------ sonda su immagine simulata (end-to-end vero)

def _can_e2e() -> str | None:
    if os.geteuid() != 0 or not Path("/proc/self/mountinfo").exists():
        return "serve root e mount"
    if Path("/opt/superbot-ai-arena-paper").exists():
        return "percorso Arena presente"
    interp = os.environ.get("ARENA_WEB_E2E_PYTHON")
    if not interp:
        return "ARENA_WEB_E2E_PYTHON non impostato (interprete con fastapi, sqlalchemy, jwt, dotenv)"
    ok = subprocess.run([interp, "-c", "import fastapi, sqlalchemy.orm, jwt, dotenv"], capture_output=True)
    if ok.returncode:
        return "interprete senza dipendenze"
    if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", "42934567^{commit}"], capture_output=True).returncode:
        return "storia git non disponibile"
    return None


@pytest.mark.skipif(_can_e2e() is not None, reason=str(_can_e2e()))
def test_probe_end_to_end_on_a_pre_arena_image_tree_with_a_real_read_only_mount(tmp_path):
    mod = _load(str(tmp_path / "p"))
    interp = os.environ["ARENA_WEB_E2E_PYTHON"]
    tree = tmp_path / "image"
    tree.mkdir()
    subprocess.run(f"git -C {ROOT} archive 42934567 | tar -x -C {tree}", shell=True, check=True)
    (tree / "backend/v3/arena").mkdir()
    for rel in mod.OVERLAY_FILES:
        (tree / rel).write_bytes((ROOT / rel).read_bytes())
    unpatched = tree / "backend/v3_api.py"
    original = unpatched.read_text()
    patched_text = mod.patch_v3_api(original, mod.derive_block(_repo_text()))
    arena_src = tmp_path / "arena-data"
    maker = tmp_path / "mk.py"
    maker.write_text(
        "import sys, tempfile, pathlib\nfrom decimal import Decimal\nsys.path.insert(0, %r)\n"
        "from backend.v3.arena import openrouter_transport as ORT\nORT.KEY_LIMIT = Decimal('6')\n"
        "from backend.v3.arena import test_trial_setup as T\nroot = pathlib.Path(sys.argv[1]); root.mkdir(mode=0o700)\n"
        "T._prepare(root)\nexits, _ = T._exits(root)\nT._activate(root, pathlib.Path(tempfile.mkdtemp()))\n"
        "[w.stop() for w in exits.values()]\n" % str(ROOT))
    subprocess.run([sys.executable, str(maker), str(arena_src)], check=True, capture_output=True)
    data = tmp_path / "data"
    data.mkdir()
    env = {**os.environ, "PYTHONPATH": str(tree / "backend"), "DB_PATH": str(data / "superbot.db"),
           "DESK_MODE": "paper", "TRADING_MODE": "paper", "V3_ARENA_READONLY_ENABLED": "1",
           "V3_ARENA_TRIAL_DAY": "2026-11-18"}
    subprocess.run([interp, "-c", "import database, auth; database.init_db(); auth.init_auth()"],
                   cwd=tree, env=env, check=True, capture_output=True)
    wrapper = tmp_path / "wrap.py"
    wrapper.write_text(
        "import os, sys, types, runpy\nsys.path.insert(0, os.getcwd())\n"
        "from backend.v3.arena import read_router\n"
        "read_router.time = types.SimpleNamespace(time=lambda: 1800000100.0)\n"       # T0 sintetico nel futuro del sandbox
        "sys.argv = ['probe'] + sys.argv[1:]\n"
        "runpy.run_path(%r, run_name='__main__')\n" % str(ROOT / "deploy/scripts/arena_web_probe.py"))

    def probe():
        return subprocess.run([interp, "-B", str(wrapper), "candidate", "started"], cwd=tree, env=env,
                              capture_output=True, text=True)

    mount = Path("/opt/superbot-ai-arena-paper")
    mount.mkdir(parents=True)
    try:
        # 1) immagine NON patchata (stato reale del VPS): la sonda deve rifiutarla
        unpatched_run = probe()
        assert "FAILED_arena_routes_unexpected" in unpatched_run.stdout and unpatched_run.returncode == 2
        unpatched.write_text(patched_text)
        # 2) patchata ma Arena non montata: il lettore non verifica nulla, la sonda rifiuta
        no_mount = probe()
        assert "FAILED_journal_not_verified" in no_mount.stdout
        # 3) patchata + mount vero in sola lettura: PASS
        subprocess.run(["mount", "--bind", str(arena_src), str(mount)], check=True)
        subprocess.run(["mount", "-o", "remount,bind,ro", str(mount)], check=True)
        with pytest.raises(OSError):
            (mount / "write-test").write_text("x")
        before = subprocess.run(["find", str(arena_src), "-type", "f", "-exec", "sha256sum", "{}", "+"],
                                capture_output=True, text=True).stdout
        ok = probe()
        assert ok.returncode == 0 and "RESULT=PASS_CANDIDATE" in ok.stdout, ok.stdout + ok.stderr
        assert "arena_routes=GET_ONLY" in ok.stdout and "no_session=401" in ok.stdout and "valid_session=200" in ok.stdout
        assert '"t0_identical": true' in ok.stdout
        after = subprocess.run(["find", str(arena_src), "-type", "f", "-exec", "sha256sum", "{}", "+"],
                               capture_output=True, text=True).stdout
        assert sorted(before.splitlines()) == sorted(after.splitlines())               # nessun file Arena toccato
    finally:
        subprocess.run(["umount", str(mount)], capture_output=True)
        try:
            mount.rmdir()
        except OSError:
            pass


def test_probe_payload_checks_reject_inconsistent_data():
    spec = importlib.util.spec_from_file_location("probe_under_test", ROOT / "deploy/scripts/arena_web_probe.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    def wallet(name, t0=1_000, status="VERIFIED"):
        return {"portfolio_id": name, "mode": "paper", "source": "arena_independent_journal_v1", "initial_capital": 2000,
                "data_status": status, "trial_comparable": True, "trial_start_ms": t0, "state": "running",
                "open_count": 1, "total_closed": 0}

    good = {"schema": "brain_arena_readonly_v1", "mode": "paper",
            "portfolios": {n: wallet(n) for n in ("deepseek", "qwen", "minimax")}}
    assert probe.check_payload(good, "started")["t0_identical"] is True
    bad_t0 = json.loads(json.dumps(good)); bad_t0["portfolios"]["qwen"]["trial_start_ms"] = 2_000
    bad_status = json.loads(json.dumps(good)); bad_status["portfolios"]["minimax"]["data_status"] = "UNVERIFIED_JOURNAL"
    bad_mode = json.loads(json.dumps(good)); bad_mode["mode"] = "live"
    missing = json.loads(json.dumps(good)); del missing["portfolios"]["deepseek"]
    for payload in (bad_t0, bad_status, bad_mode, missing):
        with pytest.raises(SystemExit):
            probe.check_payload(payload, "started")
