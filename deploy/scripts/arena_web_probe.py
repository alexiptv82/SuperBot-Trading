#!/usr/bin/env python3
"""Sonda in sola lettura per GET /api/v3/arena. Si esegue DENTRO un container, via stdin.

  candidate: container usa-e-getta (senza rete, mount tutti :ro). NON avvia server.py (niente
             polling Telegram, niente task di background). Monta il router vero con la dipendenza
             di sessione vera, su una COPIA del DB di autenticazione, e chiama l'app via ASGI.
  live:      dentro il container web vero dopo lo switch: stessa verifica via HTTP interno.

Non scrive nulla di persistente, non stampa token, password, ambiente o importi in USD.
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

PROVIDERS = {"deepseek", "qwen", "minimax"}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def say(key: str, value: object) -> None:
    print(f"ARENA_WEB_PROBE {key}={value}", flush=True)


def where(exc: BaseException) -> str:
    """Tipo e posizione dell'errore (file:riga dell'ultimo frame), mai il messaggio."""
    tb, last = exc.__traceback__, None
    while tb is not None:
        last = tb
        tb = tb.tb_next
    if last is None:
        return type(exc).__name__
    name = getattr(exc, "name", None)
    tail = "@" + os.path.basename(last.tb_frame.f_code.co_filename) + ":" + str(last.tb_lineno)
    return type(exc).__name__ + (":" + str(name) if isinstance(exc, ImportError) and name else "") + tail


def fail(code: str) -> None:
    say("RESULT", "FAILED_" + code)
    sys.exit(2)


def check_payload(data: object, expect: str) -> dict:
    """Controlli di forma e coerenza. Ritorna un riepilogo senza importi."""
    if type(data) is not dict or data.get("schema") != "brain_arena_readonly_v1" or data.get("mode") != "paper":
        fail("payload_schema")
    wallets = data.get("portfolios")
    if type(wallets) is not dict or set(wallets) != PROVIDERS:
        fail("payload_providers")
    starts, states, opens, closed = set(), {}, {}, {}
    for name, w in wallets.items():
        if (type(w) is not dict or w.get("portfolio_id") != name or w.get("mode") != "paper"
                or w.get("source") != "arena_independent_journal_v1" or w.get("initial_capital") != 2000):
            fail("wallet_shape_" + name)
        if expect == "started":
            if w.get("data_status") != "VERIFIED" or w.get("trial_comparable") is not True:
                fail("journal_not_verified_" + name + "_" + str(w.get("data_status")))
            if type(w.get("trial_start_ms")) is not int:
                fail("t0_missing_" + name)
            starts.add(w["trial_start_ms"])
        states[name] = w.get("state")
        opens[name] = w.get("open_count")
        closed[name] = w.get("total_closed")
    if expect == "started" and len(starts) != 1:
        fail("t0_not_identical")
    return {"states": states, "open": opens, "closed": closed, "t0_identical": len(starts) <= 1}


async def _asgi(app, method: str, path: str, headers: list[tuple[str, str]]) -> tuple[int, bytes]:
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "path": path, "raw_path": path.encode(), "query_string": b"", "scheme": "http",
             "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
             "client": ("127.0.0.1", 1), "server": ("probe", 80)}
    state = {"status": 0, "body": b"", "sent": False}

    async def receive():
        if not state["sent"]:
            state["sent"] = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.sleep(30)
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            state["status"] = message["status"]
        elif message["type"] == "http.response.body":
            state["body"] += message.get("body", b"")

    await asyncio.wait_for(app(scope, receive, send), timeout=20)
    return state["status"], state["body"]


def _copy_auth_db() -> None:
    """Copia consistente del DB di sessione in /tmp (backup API, read-only; ripiego immutable)."""
    raw = os.environ.get("DB_PATH", "./data/superbot.db")
    source = os.path.abspath(raw)
    if not os.path.isfile(source):
        fail("auth_db_missing")
    target_dir = tempfile.mkdtemp(prefix="arena-probe-")
    target = os.path.join(target_dir, "probe.db")
    last = None
    for uri in ("file:%s?mode=ro", "file:%s?immutable=1"):
        try:
            src = sqlite3.connect(uri % source, uri=True, timeout=5)
            dst = sqlite3.connect(target)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            os.environ["DB_PATH"] = target
            return
        except sqlite3.Error as exc:
            last = type(exc).__name__
            if os.path.exists(target):
                os.unlink(target)
    fail("auth_db_copy_" + str(last))


def candidate(expect: str) -> None:
    for key, value in (("V3_ARENA_READONLY_ENABLED", "1"), ("DESK_MODE", "paper"), ("TRADING_MODE", "paper")):
        if os.environ.get(key) != value:
            fail("env_" + key)
    _copy_auth_db()
    try:
        from fastapi import FastAPI
        from backend import v3_api
        from backend.auth import require_session, create_session_token
    except Exception as exc:  # noqa: BLE001 - report only the type, never the message
        fail("import_" + where(exc))
    paths = v3_api.V3Paths.from_env("/nonexistent", "/nonexistent")
    app = FastAPI()
    app.include_router(v3_api.make_router(require_session, paths))
    arena_routes = [r for r in app.routes if "/arena" in getattr(r, "path", "")]
    if [r.path for r in arena_routes] != ["/api/v3/arena"]:
        fail("arena_routes_unexpected")
    for r in arena_routes:
        if set(r.methods) - {"GET", "HEAD"} or set(r.methods) & WRITE_METHODS:
            fail("arena_route_has_write_method")
    say("arena_routes", "GET_ONLY")
    run = asyncio.new_event_loop().run_until_complete
    if run(_asgi(app, "GET", "/api/v3/arena", []))[0] != 401:
        fail("no_session_not_401")
    if run(_asgi(app, "GET", "/api/v3/arena", [("Authorization", "Bearer invalid")]))[0] != 401:
        fail("bad_session_not_401")
    for method in ("POST", "PUT", "DELETE"):
        if run(_asgi(app, method, "/api/v3/arena", [("Authorization", "Bearer invalid")]))[0] not in (401, 405):
            fail("write_method_reachable")
    token = create_session_token("full")
    status, body = run(_asgi(app, "GET", "/api/v3/arena", [("Authorization", "Bearer " + token)]))
    if status != 200:
        fail("valid_session_status_%s" % status)
    summary = check_payload(json.loads(body), expect)
    say("no_session", 401)
    say("valid_session", 200)
    say("summary", json.dumps(summary, sort_keys=True))
    say("RESULT", "PASS_CANDIDATE")


def _http(url: str, headers: dict | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def live(expect: str) -> None:
    base = os.environ.get("PROBE_BASE", "http://127.0.0.1:8001")
    from backend.auth import create_session_token
    if _http(base + "/api/health")[0] != 200:
        fail("health")
    status, body = _http(base + "/api/auth/webauthn/status")
    try:
        auth = json.loads(body)
        ok = status == 200 and type(auth) is dict and type(auth.get("available")) is bool \
            and type(auth.get("has_credentials")) is bool
    except ValueError:
        ok = False
    if not ok:
        fail("webauthn_status")
    if _http(base + "/api/v3/arena")[0] != 401:
        fail("no_session_not_401")
    if _http(base + "/api/v3/overview")[0] != 401:
        fail("overview_not_401")
    token = create_session_token("full")
    status, body = _http(base + "/api/v3/arena", {"Authorization": "Bearer " + token})
    if status != 200:
        fail("valid_session_status_%s" % status)
    summary = check_payload(json.loads(body), expect)
    say("webauthn_status", 200)
    say("no_session", 401)
    say("valid_session", 200)
    say("summary", json.dumps(summary, sort_keys=True))
    say("RESULT", "PASS_LIVE")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    expect = sys.argv[2] if len(sys.argv) > 2 else "started"
    if expect not in ("started", "any") or mode not in ("candidate", "live"):
        fail("usage")
    {"candidate": candidate, "live": live}[mode](expect)


if __name__ == "__main__":
    main()
