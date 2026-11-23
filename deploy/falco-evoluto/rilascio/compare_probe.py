"""Sonda del confronto Falco Evoluto / Brain Scalp. Si esegue DENTRO un container, via stdin (nessun file scritto).

  candidate: container usa-e-getta senza rete, mount in sola lettura: router V3 vero con sessione vera su una COPIA del
             DB di autenticazione, chiamato via ASGI (nessun server, nessun polling).
  live:      dentro il container web vero dopo lo scambio: stesse verifiche via HTTP interno, piu' una chiusura
             NEGATIVA per ciascun portafoglio (posizione inesistente -> 404 dal bridge della SUA run, mai 200).
Non stampa token, password, ambiente o importi.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request

EXPECT = {"falco_evoluto": ("falco-evoluto-paper-p1", "1000", "falco_evoluto", 15),
          "brain_scalp": ("brain-scalp-paper-p1", "2000", "deepseek", 30)}


def say(key, value):
    print(f"COMPARE_PROBE {key}={value}", flush=True)


def fail(code):
    say("RESULT", "FAILED_" + code)
    sys.exit(2)


def check(data, live):
    if data.get("available") is not True:
        fail("compare_not_available")
    runs = {r.get("name"): r for r in data.get("runs") or []}
    if set(runs) != set(EXPECT):
        fail("compare_runs_unexpected")
    for name, (run_id, equity, analyst, cycle) in EXPECT.items():
        r = runs[name]
        cfg = r.get("config") or {}
        if (r.get("available") is not True or r.get("run_id") != run_id or r.get("initial_equity") != equity
                or cfg.get("analyst") != analyst or cfg.get("cycle_minutes") != cycle or cfg.get("leverage") != [15, 45]
                or cfg.get("guardian") is not True or r.get("open_positions") != []):
            fail("run_not_as_prepared_" + name)
        if r.get("paused") is not True:
            fail("run_not_paused_" + name)
        if r.get("manual_close_allowed") is not True:
            fail("close_not_ready_" + name)
        say(name, "prepared_paused_close_ready")


async def _asgi(app, method, path, headers, body=b""):
    p, _, q = path.partition("?")
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "path": p,
             "raw_path": p.encode(), "query_string": q.encode(), "scheme": "http",
             "headers": [(k.lower().encode(), v.encode()) for k, v in headers], "client": ("127.0.0.1", 1),
             "server": ("probe", 80)}
    state = {"status": 0, "body": b"", "sent": False}

    async def receive():
        if not state["sent"]:
            state["sent"] = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.sleep(30)
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            state["status"] = message["status"]
        elif message["type"] == "http.response.body":
            state["body"] += message.get("body", b"")

    await asyncio.wait_for(app(scope, receive, send), timeout=20)
    return state["status"], state["body"]


def _copy_auth_db():
    source = os.path.abspath(os.environ.get("DB_PATH", "./data/superbot.db"))
    target = os.path.join(tempfile.mkdtemp(prefix="compare-probe-"), "probe.db")
    for uri in ("file:%s?mode=ro", "file:%s?immutable=1"):
        try:
            src, dst = sqlite3.connect(uri % source, uri=True, timeout=5), sqlite3.connect(target)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            os.environ["DB_PATH"] = target
            return
        except sqlite3.Error:
            if os.path.exists(target):
                os.unlink(target)
    fail("auth_db_copy")


def candidate():
    _copy_auth_db()
    try:
        from fastapi import FastAPI
        from backend import v3_api
        from backend.auth import require_session, create_session_token
    except Exception as exc:  # noqa: BLE001
        fail("import_" + type(exc).__name__)
    app = FastAPI()
    app.include_router(v3_api.make_router(require_session, v3_api.V3Paths.from_env("/nonexistent", "/nonexistent")))
    run = asyncio.new_event_loop().run_until_complete
    if run(_asgi(app, "GET", "/api/v3/compare", []))[0] != 401:
        fail("no_session_not_401")
    auth = [("Authorization", "Bearer " + create_session_token("full"))]
    status, body = run(_asgi(app, "GET", "/api/v3/compare", auth))
    if status != 200:
        fail("compare_status_%s" % status)
    check(json.loads(body), live=False)
    for name in EXPECT:
        status, _ = run(_asgi(app, "POST", f"/api/v3/compare/{name}/close",
                              auth + [("Content-Type", "application/json")], b'{"all": true}'))
        if status not in (422, 423):
            fail("close_all_not_refused_" + name)
    say("RESULT", "PASS_CANDIDATE")


def _http(url, headers=None, data=None):
    req = urllib.request.Request(url, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def live():
    base = "http://127.0.0.1:8001"
    from backend.auth import create_session_token
    if _http(base + "/api/v3/compare")[0] != 401:
        fail("no_session_not_401")
    hdr = {"Authorization": "Bearer " + create_session_token("full"), "Content-Type": "application/json"}
    status, body = _http(base + "/api/v3/compare", hdr)
    if status != 200:
        fail("compare_status_%s" % status)
    check(json.loads(body), live=True)
    for name in EXPECT:
        if _http(base + f"/api/v3/compare/{name}/close", hdr, b'{"all": true}')[0] not in (422, 423):
            fail("close_all_not_refused_" + name)
        status, _ = _http(base + f"/api/v3/compare/{name}/close", hdr, b'{"position_id": "probe-posizione-inesistente"}')
        if status != 404:
            fail("bridge_negative_close_%s_%s" % (name, status))
        say(name + "_bridge_negative_close", 404)
    say("RESULT", "PASS_LIVE")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("candidate", "live"):
        fail("usage")
    candidate() if mode == "candidate" else live()
