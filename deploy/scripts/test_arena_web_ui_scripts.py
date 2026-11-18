import hashlib
import os
import stat
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
RELEASE = HERE / "arena-web-ui-readonly-release-rollback-20261118.sh"
PREFLIGHT = HERE / "arena-web-ui-readonly-preflight-20261118.sh"

CURL_SHIM = r'''#!/usr/bin/env python3
import os, shutil, sys
a = sys.argv[1:]
out = a[a.index("-o") + 1] if "-o" in a else None
url = a[-1]
root = os.environ["ARENA_WEBUI_ROOT"]
switched = os.path.exists(os.path.join(root, ".arena-webui-previous"))
code, body = 200, b""
if url.endswith("/api/v3/arena"):
    code = int(os.environ.get("FAKE_ARENA_CODE", "401"))
elif url.endswith("/api/auth/webauthn/status"):
    body = b'{"available": true, "has_credentials": true}'
elif url.endswith("/"):
    if switched and os.environ.get("FAKE_FAIL_AFTER_SWITCH") == "1":
        code = 500
    else:
        body = open(os.path.join(root, "build", "index.html"), "rb").read()
if out:
    open(out, "wb").write(body)
sys.stdout.write(str(code))
'''
OK_SHIM = "#!/bin/sh\n[ \"$1\" = is-active ] && echo active\nexit 0\n"


def sha(path: Path) -> str:
    return hashlib.sha256((path / "index.html").read_bytes()).hexdigest()


def make_build(root: Path, marker: str, js: str) -> Path:
    (root / "static" / "js").mkdir(parents=True)
    (root / "index.html").write_text("<html>" + marker + "</html>")
    (root / "manifest.json").write_text('{"name":"%s"}' % marker)
    (root / "service-worker.js").write_text("// sw " + marker)
    (root / "static" / "js" / "main.js").write_text(js)
    return root


@pytest.fixture
def env(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    live = make_build(web / "build", "OLD", "x=/api/auth/login;")
    (live / "icons").mkdir()
    (live / "icons" / "i.png").write_text("live-icon")
    cand = make_build(tmp_path / "cand", "NEW", "a='/api/v3/arena';b='3 giorni';")
    (cand / "manifest.json").write_text('{"name":"CANDIDATE-MUST-BE-IGNORED"}')
    backups = tmp_path / "backups"
    backups.mkdir()
    shims = tmp_path / "shims"
    shims.mkdir()
    for name, body in (("curl", CURL_SHIM), ("nginx", OK_SHIM), ("systemctl", OK_SHIM)):
        p = shims / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    e = dict(os.environ, PATH=f"{shims}:{os.environ['PATH']}", ARENA_WEBUI_ROOT=str(web),
             ARENA_WEBUI_BACKUPS=str(backups), ARENA_WEBUI_TEST_MODE="1")
    return {"env": e, "web": web, "live": live, "cand": cand, "backups": backups,
            "old": sha(live), "new": sha(cand)}


def run(ctx, mode, **over):
    e = dict(ctx["env"], **{k: str(v) for k, v in over.pop("extra", {}).items()})
    args = ["bash", str(RELEASE), mode, "--candidate", str(over.get("cand", ctx["cand"])),
            "--new-sha", over.get("new", ctx["new"]), "--old-sha", over.get("old", ctx["old"])]
    return subprocess.run(args, env=e, capture_output=True, text=True, timeout=60)


def test_bash_syntax():
    for script in (RELEASE, PREFLIGHT):
        r = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def test_activate_ok_keeps_pwa_identity_and_backup(env):
    r = run(env, "--activate")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "RESULT=SUCCESS_UI_ONLY" in r.stdout
    assert sha(env["live"]) == env["new"]
    assert (env["live"] / "manifest.json").read_text() == '{"name":"OLD"}'
    assert (env["live"] / "service-worker.js").read_text() == "// sw OLD"
    assert (env["live"] / "icons" / "i.png").read_text() == "live-icon"
    saved = list(env["backups"].glob("arena-webui-before-*/build"))
    assert len(saved) == 1 and sha(saved[0]) == env["old"]
    assert sha(env["web"] / ".arena-webui-previous") == env["old"]


def test_manual_rollback_restores_previous(env):
    assert run(env, "--activate").returncode == 0
    r = run(env, "--rollback")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "RESULT=RESTORED_PREVIOUS_UI" in r.stdout
    assert sha(env["live"]) == env["old"]
    assert not (env["web"] / ".arena-webui-previous").exists()
    assert list(env["web"].glob(".arena-webui-rejected-*"))


def test_automatic_rollback_when_post_switch_check_fails(env):
    r = run(env, "--activate", extra={"FAKE_FAIL_AFTER_SWITCH": "1"})
    assert r.returncode == 2
    assert "AUTO_ROLLBACK=TRUE" in r.stdout
    assert sha(env["live"]) == env["old"]
    assert not (env["web"] / ".arena-webui-previous").exists()
    assert list(env["web"].glob(".arena-webui-auto-rejected-*"))


def test_refuses_when_live_hash_is_not_the_declared_old(env):
    r = run(env, "--activate", old="0" * 64)
    assert r.returncode == 2 and "REFUSED=LIVE_INDEX_NOT_OLD_SHA" in r.stdout
    assert sha(env["live"]) == env["old"]


def test_refuses_missing_candidate(env):
    r = run(env, "--activate", cand=env["web"] / "nope")
    assert r.returncode == 2 and "REFUSED=CANDIDATE_MISSING" in r.stdout


def test_refuses_candidate_with_wrong_hash(env):
    r = run(env, "--activate", new="1" * 64)
    assert r.returncode == 2 and "REFUSED=CANDIDATE_SHA_MISMATCH" in r.stdout
    assert sha(env["live"]) == env["old"]


def test_refuses_when_backend_arena_route_is_404(env):
    r = run(env, "--activate", extra={"FAKE_ARENA_CODE": "404"})
    assert r.returncode == 2 and "REFUSED=BACKEND_ARENA_ROUTE_NOT_LIVE" in r.stdout
    assert sha(env["live"]) == env["old"]
    assert not list(env["backups"].iterdir())


def test_refuses_candidate_with_old_text_or_http_fallback(env):
    (env["cand"] / "static" / "js" / "main.js").write_text("a='/api/v3/arena';b='3 giorni 14 giorni';")
    new = sha(env["cand"])
    r = run(env, "--activate", new=new)
    assert r.returncode == 2 and "REFUSED=CANDIDATE_SAYS_14_DAYS" in r.stdout


def test_preflight_requires_pinned_40_hex_sha():
    for args in ([], ["--sha", "abc"], ["--sha", "g" * 40]):
        r = subprocess.run(["bash", str(PREFLIGHT), *args], capture_output=True, text=True,
                           env=dict(os.environ, ARENA_WEBUI_TEST_MODE="1"))
        assert r.returncode == 2 and "REFUSED=SHA_PIN_REQUIRED_40_HEX" in r.stdout
