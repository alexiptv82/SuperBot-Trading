"""Sonda dell'app PAPER (Trade, Performance, Archivio) sulle run VERE. Si esegue DENTRO un container, via stdin.

  candidate: container usa-e-getta senza rete, mount in sola lettura: router V3 vero, sessione vera su una COPIA del DB
             di autenticazione, chiamato via ASGI (nessun server).
  live:      dentro il container web vero dopo lo scambio, via HTTP interno.
Verifica, per Falco Evoluto e Brain Scalp: rotte nuove solo con sessione (401 senza), stessi numeri di /api/v3/compare
(run, chiusure, P&L netto, commissioni, posizioni aperte, equity contabile), take profit su ogni posizione aperta,
nessuna scrittura (POST rifiutata), archivio del reset leggibile e separato, chiavi non valide -> 404.
Argomenti: <modo> <run archiviate attese sull'host>. Non stampa token, ambiente o importi: solo conteggi ed esiti.
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
from decimal import Decimal

EXPECT = {"falco_evoluto": ("falco-evoluto-paper-p1", "1000"), "brain_scalp": ("brain-scalp-paper-p1", "2000")}


def say(key, value):
    print(f"APP_PROBE {key}={value}", flush=True)


def fail(code):
    say("RESULT", "FAILED_" + code)
    sys.exit(2)


def D(v):
    return Decimal(str(v))


def checks(get, post, archived: int):
    for path in ("/api/v3/compare/falco_evoluto/trades", "/api/v3/compare/brain_scalp/performance", "/api/v3/paper-archive"):
        if get(path, auth=False)[0] != 401:
            fail("no_session_not_401")
    status, body = get("/api/v3/compare")
    if status != 200:
        fail("compare_status_%s" % status)
    cmp = {r.get("name"): r for r in json.loads(body).get("runs") or []}
    if set(cmp) != set(EXPECT):
        fail("compare_runs_unexpected")
    for name, (run_id, equity) in EXPECT.items():
        c = cmp[name]
        if c.get("run_id") != run_id or c.get("initial_equity") != equity or c.get("available") is not True:
            fail("compare_run_unexpected_" + name)
        status, body = get(f"/api/v3/compare/{name}/trades?limit=500")
        if status != 200:
            fail(f"trades_status_{name}_{status}")
        t = json.loads(body)
        closed, opened = t.get("closed_trades") or [], t.get("open_positions") or []
        if t.get("run_id") != run_id or t.get("name") != name:
            fail("trades_run_mismatch_" + name)
        if t.get("total_closed") != c.get("closed") or len(closed) != c.get("closed"):
            fail("trades_closed_count_mismatch_" + name)
        if sum((D(x["realized_pnl"]) for x in closed), Decimal(0)) != D(c.get("net_pnl")):
            fail("trades_net_mismatch_" + name)
        if sum((D(x["fees"]) for x in closed), Decimal(0)) != D(c.get("fees")):
            fail("trades_fees_mismatch_" + name)
        if sorted(p["position_id"] for p in opened) != sorted(p["position_id"] for p in c.get("open_positions") or []):
            fail("trades_open_mismatch_" + name)
        if any(p.get("take_profit") is None or p.get("stop") is None for p in opened):
            fail("trades_open_without_tp_or_stop_" + name)
        if any(x.get("exit_reason") is None or x.get("stop") is None for x in closed):
            fail("trades_closed_incomplete_" + name)
        status, body = get(f"/api/v3/compare/{name}/performance")
        if status != 200:
            fail(f"performance_status_{name}_{status}")
        p = json.loads(body)
        if p.get("available") is not True or p.get("run_id") != run_id or not p.get("daily"):
            fail("performance_unavailable_" + name)
        if D(p["daily"][-1]["equity_end"]) != D(c.get("settled_equity")):
            fail("performance_equity_mismatch_" + name)
        if sum(p["daily"][i]["trades"] for i in range(len(p["daily"]))) != c.get("closed"):
            fail("performance_daily_count_mismatch_" + name)
        dec = (p.get("decisions") or {}).get("total")
        say(name, f"run {run_id}: {c.get('closed')} chiusi, {len(opened)} aperti, {len(p['daily'])} giorni, "
                  f"{dec} decisioni, numeri coerenti con compare")
        st = post(f"/api/v3/compare/{name}/trades")
        if st not in (405, 423):
            fail(f"trades_post_not_refused_{name}_{st}")
    if get("/api/v3/compare/rc1/trades")[0] != 404 or get("/api/v3/paper-archive/..%2F..")[0] != 404:
        fail("unknown_keys_not_404")
    status, body = get("/api/v3/paper-archive")
    if status != 200:
        fail("archive_status_%s" % status)
    a = json.loads(body)
    rows = a.get("runs") or []
    if a.get("available") is not True or len(rows) != archived or any(r.get("available") is not True for r in rows):
        fail(f"archive_not_readable_{len(rows)}_of_{archived}")
    if any("manual_close_allowed" in r or "paused" in r for r in rows):
        fail("archive_has_live_fields")
    if any(r.get("ai_cost_total") is None for r in rows):
        fail("archive_ai_cost_unreadable")
    for r in rows:
        status, body = get("/api/v3/paper-archive/" + r["name"])
        if status != 200 or len(json.loads(body).get("closed_trades") or []) != r.get("closed"):
            fail("archive_detail_mismatch")
    say("archivio", f"{len(rows)} run archiviate leggibili (journal e costi AI leggibili), separate dalle attive")
    say("ui_build", "rotte nuove presenti, sola lettura")


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

    await asyncio.wait_for(app(scope, receive, send), timeout=30)
    return state["status"], state["body"]


def _copy_auth_db():
    source = os.path.abspath(os.environ.get("DB_PATH", "./data/superbot.db"))
    target = os.path.join(tempfile.mkdtemp(prefix="app-probe-"), "probe.db")
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


def candidate(archived):
    _copy_auth_db()
    try:
        from fastapi import FastAPI
        from backend import v3_api
        from backend.auth import require_session, create_session_token
    except Exception as exc:  # noqa: BLE001
        fail("import_" + type(exc).__name__)
    app = FastAPI()
    app.include_router(v3_api.make_router(require_session, v3_api.V3Paths.from_env("/nonexistent", "/nonexistent")))
    loop = asyncio.new_event_loop()
    hdrs = [("Authorization", "Bearer " + create_session_token("full"))]

    def get(path, auth=True):
        return loop.run_until_complete(_asgi(app, "GET", path, hdrs if auth else []))

    def post(path):
        return loop.run_until_complete(_asgi(app, "POST", path, hdrs + [("Content-Type", "application/json")], b"{}"))[0]
    checks(get, post, archived)
    say("RESULT", "PASS_CANDIDATE")


def live(archived):
    base = "http://127.0.0.1:8001"
    from backend.auth import create_session_token
    hdr = {"Authorization": "Bearer " + create_session_token("full")}

    def http(path, method="GET", auth=True):
        req = urllib.request.Request(base + path, method=method, headers=hdr if auth else {},
                                     data=b"{}" if method == "POST" else None)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
    checks(lambda p, auth=True: http(p, auth=auth), lambda p: http(p, "POST")[0], archived)
    say("RESULT", "PASS_LIVE")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("candidate", "live") or not sys.argv[2].isdigit():
        fail("usage")
    (candidate if sys.argv[1] == "candidate" else live)(int(sys.argv[2]))
