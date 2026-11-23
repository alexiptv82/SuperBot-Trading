"""Sonda in sola lettura della web app collegata al Brain Unico. Si esegue DENTRO un container, via stdin.

  candidate: container usa-e-getta (senza rete, mount tutti :ro, ambiente della nuova web). NON avvia server.py
             (niente polling Telegram). Compila TUTTO il backend con l'interprete dell'immagine (sintassi), importa i
             moduli della web e del bridge, monta il router V3 vero con la dipendenza di sessione vera su una COPIA
             del DB di autenticazione e lo chiama via ASGI.
  live:      dentro il container web vero dopo lo switch: stesse verifiche via HTTP interno.

Verifica che la web legga la NUOVA run (run_id, capitale iniziale, modello DeepSeek Flash, profilo B), che senza
sessione risponda 401, che le chiusure siano solo singole PAPER. Non scrive nulla di persistente, non stampa token,
password, ambiente o importi.
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

RUN_ID = "brain-unico-paper-rc1"
RUN_DIR = "/opt/superbot-v3-paper-runs/brain-v3-unico-paper-rc1"
GETS = ("/api/v3/overview", "/api/v3/brain/status", "/api/v3/brain/trades?limit=20", "/api/v3/brain/memory",
        "/api/v3/brain/config")


def say(key: str, value: object) -> None:
    print(f"BRAIN_WEB_PROBE {key}={value}", flush=True)


def fail(code: str) -> None:
    say("RESULT", "FAILED_" + code)
    sys.exit(2)


def where(exc: BaseException) -> str:
    tb, last = exc.__traceback__, None
    while tb is not None:
        last, tb = tb, tb.tb_next
    tail = "" if last is None else "@%s:%d" % (os.path.basename(last.tb_frame.f_code.co_filename), last.tb_lineno)
    name = getattr(exc, "name", None)
    return type(exc).__name__ + (":" + str(name) if isinstance(exc, ImportError) and name else "") + tail


def check_env() -> None:
    expect = {"DESK_MODE": "paper", "TRADING_MODE": "paper", "V3_CUTOVER_READONLY": "1",
              "V3_ALLOW_BRAIN_SINGLE_CLOSE": "1", "V3_CLOSE_BRIDGE_ONLY": "1", "V3_RUN_ID": RUN_ID}
    for key, value in expect.items():
        if os.environ.get(key) != value:
            fail("env_" + key)
    for key, name in (("V3_JOURNAL_PATH", "journal.db"), ("V3_HEARTBEAT_PATH", "heartbeat.json"),
                      ("V3_BUDGET_DB_PATH", "budget.db"), ("V3_PAUSE_FLAG_PATH", "pause.flag"),
                      ("V3_RUNNER_CONFIG_PATH", "runner_config.json"),
                      ("V3_CLOSE_REQUEST_PATH", "close_request.json"), ("V3_CLOSE_RESULT_PATH", "close_result.json")):
        if os.environ.get(key) != RUN_DIR + "/" + name:
            fail("env_" + key)


def check_payloads(data: dict, expect_exit_healthy: bool) -> dict:
    ov, st, tr, cfg = (data[p] for p in ("/api/v3/overview", "/api/v3/brain/status", "/api/v3/brain/trades?limit=20",
                                         "/api/v3/brain/config"))
    brain = [p for p in ov.get("portfolios", []) if p.get("id") == "brain"]
    if len(brain) != 1:
        fail("overview_without_brain")
    brain = brain[0]
    if st.get("run_id") != RUN_ID:
        fail("status_run_id_%s" % st.get("run_id"))
    if cfg.get("available") is not True or cfg.get("run_id") != RUN_ID or cfg.get("model") != "deepseek-flash":
        fail("config_not_new_run")
    if str(cfg.get("initial_equity")) not in ("2000", "2000.0", "2000.00"):
        fail("config_initial_equity")
    if ov.get("cutover_readonly") is not True:
        fail("not_readonly")
    if type(tr.get("open_positions")) is not list:
        fail("trades_shape")
    if expect_exit_healthy and (ov.get("brain_single_close_allowed") is not True
                                or brain.get("manual_close_allowed") is not True):
        fail("close_not_allowed_with_healthy_exit")
    return {"state": brain.get("state"), "status_state": st.get("state"), "run_id": st.get("run_id"),
            "model": cfg.get("model"), "open": len(tr["open_positions"]),
            "close_allowed": ov.get("brain_single_close_allowed") is True, "paused": st.get("paused")}


async def _asgi(app, method: str, path: str, headers: list, body: bytes = b"") -> tuple[int, bytes]:
    p, _, q = path.partition("?")
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "path": p, "raw_path": p.encode(), "query_string": q.encode(), "scheme": "http",
             "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
             "client": ("127.0.0.1", 1), "server": ("probe", 80)}
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


def _copy_auth_db() -> None:
    source = os.path.abspath(os.environ.get("DB_PATH", "./data/superbot.db"))
    if not os.path.isfile(source):
        fail("auth_db_missing")
    target = os.path.join(tempfile.mkdtemp(prefix="brain-probe-"), "probe.db")
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
        except sqlite3.Error:
            if os.path.exists(target):
                os.unlink(target)
    fail("auth_db_copy")


def compile_backend(root: str = "/app/backend") -> int:
    """Sintassi di tutto il backend con l'interprete dell'immagine, senza scrivere .pyc."""
    n = 0
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(base, f)
                try:
                    with open(path, "rb") as fh:
                        compile(fh.read(), path, "exec", dont_inherit=True)
                except SyntaxError as exc:
                    fail("syntax_%s:%s" % (os.path.relpath(path, root), exc.lineno))
                n += 1
    return n


def candidate(expect_exit_healthy: bool) -> None:
    check_env()
    say("python", "%d.%d" % sys.version_info[:2])
    say("backend_files_compiled", compile_backend())
    _copy_auth_db()
    try:
        from fastapi import FastAPI
        from backend import v3_api
        from backend.auth import require_session, create_session_token
        import backend.desk_api  # noqa: F401  (chiusure classiche via bridge)
        import backend.v3.close_bridge_server as bridge
    except Exception as exc:  # noqa: BLE001 - solo tipo e posizione, mai il messaggio
        fail("import_" + where(exc))
    if bridge._brain_from_env({"V3_BRIDGE_BRAIN_RUN_DIR": os.path.basename(RUN_DIR),
                               "V3_BRIDGE_BRAIN_RUN_ID": RUN_ID})[1] != RUN_ID:
        fail("bridge_cannot_select_new_run")
    paths = v3_api.V3Paths.from_env("/nonexistent", "/nonexistent")
    app = FastAPI()
    app.include_router(v3_api.make_router(require_session, paths))
    run = asyncio.new_event_loop().run_until_complete
    for path in GETS:
        if run(_asgi(app, "GET", path, []))[0] != 401:
            fail("no_session_not_401_" + path)
    token = create_session_token("full")
    auth = [("Authorization", "Bearer " + token)]
    data = {}
    for path in GETS:
        status, body = run(_asgi(app, "GET", path, auth))
        if status != 200:
            fail("valid_session_%s_%s" % (path, status))
        data[path] = json.loads(body)
    summary = check_payloads(data, expect_exit_healthy)
    # chiusura di tutte: sempre rifiutata; nessuna scrittura (mount in sola lettura)
    status, _ = run(_asgi(app, "POST", "/api/v3/brain/close", auth + [("Content-Type", "application/json")],
                          b'{"all": true}'))
    if status not in (409, 422, 423):
        fail("close_all_not_refused_%s" % status)
    say("summary", json.dumps(summary, sort_keys=True))
    say("RESULT", "PASS_CANDIDATE")


def _http(url: str, headers: dict | None = None, data: bytes | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def live(expect_exit_healthy: bool) -> None:
    check_env()
    base = "http://127.0.0.1:8001"
    from backend.auth import create_session_token
    if _http(base + "/api/health")[0] != 200:
        fail("health")
    status, body = _http(base + "/api/auth/webauthn/status")
    try:
        ok = status == 200 and type(json.loads(body).get("available")) is bool
    except (ValueError, AttributeError):
        ok = False
    if not ok:
        fail("webauthn_status")
    for path in GETS:
        if _http(base + path)[0] != 401:
            fail("no_session_not_401_" + path)
    token = create_session_token("full")
    data = {}
    for path in GETS:
        status, body = _http(base + path, {"Authorization": "Bearer " + token})
        if status != 200:
            fail("valid_session_%s_%s" % (path, status))
        data[path] = json.loads(body)
    summary = check_payloads(data, expect_exit_healthy)
    hdr = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    if _http(base + "/api/v3/brain/close", hdr, b'{"all": true}')[0] not in (409, 422, 423):
        fail("close_all_not_refused")
    # canale di chiusura vero (web -> bridge -> run nuova): una posizione inesistente deve dare 404, mai 200
    status, _ = _http(base + "/api/v3/brain/close", hdr, b'{"position_id": "probe-posizione-inesistente"}')
    if status != 404:
        fail("bridge_negative_close_%s" % status)
    for path in ("/api/bot/start", "/api/desk/close-all", "/api/v3/brain/reset"):
        if _http(base + path, hdr, b"{}")[0] not in (404, 405, 423):
            fail("mutation_not_blocked_" + path)
    say("bridge_negative_close", 404)
    say("summary", json.dumps(summary, sort_keys=True))
    say("RESULT", "PASS_LIVE")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    exit_flag = sys.argv[2] if len(sys.argv) > 2 else ""
    if mode not in ("candidate", "live") or exit_flag not in ("exit-healthy", "any"):
        fail("usage")
    {"candidate": candidate, "live": live}[mode](exit_flag == "exit-healthy")


if __name__ == "__main__":
    main()
