"""Rotte autenticate + canale host della chiusura manuale Arena + guardia di sola lettura. Nessuna rete."""
from __future__ import annotations

import json
import threading

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from backend.v3.arena import close_bridge as CB
from backend.v3.arena import close_bridge_server as CBS
from backend.v3.arena import manual_close as MC
from backend.v3.arena.close_router import make_arena_close_router
from backend.v3.arena.test_arena_manual_close import RID, T0, _opened
from backend.v3.cutover_gate import should_refuse_mutation

PAPER_ENV = {"V3_ARENA_ALLOW_MANUAL_CLOSE": "1", "DESK_MODE": "paper", "TRADING_MODE": "paper",
             "V3_ARENA_CLOSE_SOCKET": CB.SOCKET_PATH, "V3_ARENA_TRIAL_DAY": "2026-11-18"}


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "arena"
    r.mkdir()
    return r


def _session(request: Request):
    if request.headers.get("authorization") != "Bearer ok":
        raise HTTPException(401)
    return "owner"


def _client(plan, clock):
    plans = {plan.provider: plan}

    def send(op, provider, body):                          # stesso percorso del socket: codifica -> host -> decodifica
        status, payload = CBS.process(plans, CB.encode(op, provider, body), clock["now"])
        return CB.decode_reply(json.dumps({"status": status, "payload": payload}).encode() + b"\n")
    app = FastAPI()
    app.include_router(make_arena_close_router(_session, (plan,), send=send, now_fn=lambda: clock["now"]),
                       prefix="/api/v3")
    return TestClient(app)


AUTH = {"authorization": "Bearer ok"}


def test_flag_requires_paper_and_pinned_socket():
    assert CB.arena_manual_close_enabled(PAPER_ENV)
    for k, bad in (("V3_ARENA_ALLOW_MANUAL_CLOSE", "0"), ("DESK_MODE", "live"), ("TRADING_MODE", "live"),
                   ("V3_ARENA_CLOSE_SOCKET", "/tmp/x.sock")):
        assert not CB.arena_manual_close_enabled(dict(PAPER_ENV, **{k: bad}))


def test_readonly_gate_opens_only_the_arena_close_paths():
    gate = lambda m, p, allow: should_refuse_mutation(m, p, readonly=True, allow_arena_manual_close=allow)
    ok = ("/api/v3/arena/qwen/close", "/api/v3/arena/minimax/close", "/api/v3/arena/deepseek/close",
          "/api/v3/arena/qwen/close/req-0000000000000001/annotation")
    for path in ok:
        assert gate("POST", path, True) is False
        assert gate("POST", path, False) is True             # senza opt-in resta bloccata
    for path in ("/api/v3/brain/close", "/api/v3/arena/claude/close", "/api/v3/arena/qwen/close-all",
                 "/api/v3/arena/qwen/close/../../brain/close", "/api/v3/arena/qwen/reset",
                 "/api/v3/arena/qwen/close/short/annotation", "/api/desk/close-position"):
        assert gate("POST", path, True) is True
    assert gate("DELETE", "/api/v3/arena/qwen/close", True) is True


def test_api_close_status_annotation_end_to_end(root):
    plan, exits, _, (pid, other) = _opened(root)
    clock = {"now": T0 + 1}
    c = _client(plan, clock)
    try:
        assert c.post("/api/v3/arena/qwen/close", json={"position_id": pid, "request_id": RID}).status_code == 401
        r = c.post("/api/v3/arena/qwen/close", json={"position_id": pid, "request_id": RID}, headers=AUTH)
        assert r.status_code == 200 and r.json()["status"] == "pending"
        assert r.headers["cache-control"] == "no-store"
        # chiusura di massa o corpo diverso: rifiutati
        r = c.post("/api/v3/arena/qwen/close", json={"position_ids": [pid, other], "request_id": RID}, headers=AUTH)
        assert r.status_code == 422
        r = c.post("/api/v3/arena/claude/close", json={"position_id": pid, "request_id": RID}, headers=AUTH)
        assert r.status_code == 422
        # motivazione prima della conferma: 409
        r = c.post(f"/api/v3/arena/qwen/close/{RID}/annotation", json={"reason": "trend_change"}, headers=AUTH)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "close_not_confirmed"
        exits.tick(T0 + 5_000)
        clock["now"] = T0 + 6_000
        r = c.get(f"/api/v3/arena/qwen/close/{RID}", headers=AUTH)
        assert r.status_code == 200 and r.json()["status"] == "closed" and r.json()["terminal"] is True
        r = c.post(f"/api/v3/arena/qwen/close/{RID}/annotation",
                   json={"reason": "trend_change", "note": "inversione su 15m"}, headers=AUTH)
        assert r.status_code == 200 and r.json()["annotation"]["reason"] == "trend_change"
        r = c.get("/api/v3/arena/qwen/annotations", headers=AUTH)
        rows = r.json()["annotations"]
        assert len(rows) == 1 and rows[0]["position_id"] == pid and rows[0]["note"] == "inversione su 15m"
        assert r.json()["manual_close_ready"] is True
        assert c.get("/api/v3/arena/qwen/close/req-9999999999999999", headers=AUTH).status_code == 404
    finally:
        exits.stop()


def test_bridge_refuses_a_run_without_matching_manifest(root):
    plan, exits, _, (pid, _) = _opened(root)
    try:
        man = json.loads((plan.folder / "arena_manifest.json").read_text())
        (plan.folder / "arena_manifest.json").write_text(json.dumps(dict(man, mode="live")))
        status, payload = CBS.process({"qwen": plan}, CB.encode("close", "qwen", {"position_id": pid,
                                                                                  "request_id": RID}), T0 + 1)
        assert (status, payload["code"]) == (409, "arena_run_not_available")
        for raw in (b"{}\n", b"not json\n", b'{"op":"close"}', b'{"op":"reset","provider":"qwen","body":{}}\n',
                    b"x" * 2000 + b"\n"):
            assert CBS.process({"qwen": plan}, raw, T0)[0] == 422
        assert not (plan.folder / "close_request.json").exists()
    finally:
        exits.stop()


def test_load_plans_refuses_non_paper_environment(root):
    with pytest.raises(RuntimeError):
        CBS.load_plans(dict(PAPER_ENV, DESK_MODE="live"), root)
    plans = CBS.load_plans(PAPER_ENV, root)
    assert set(plans) == {"deepseek", "qwen", "minimax"}


def test_client_never_reports_success_on_bad_or_missing_channel(tmp_path, monkeypatch):
    with pytest.raises(CB.ArenaBridgeError):                 # socket non fissato
        CB.send("close", "qwen", {"position_id": "p", "request_id": RID}, environ={})
    with pytest.raises(CB.ArenaBridgeError):                 # socket assente
        CB.send("close", "qwen", {"position_id": "p", "request_id": RID}, environ=PAPER_ENV)
    for reply in (b"", b'{"status":200,"payload":{"ok":false}}\n', b'{"status":500,"payload":{}}\n',
                  b'{"status":200,"payload":{"ok":true}}'):
        with pytest.raises(CB.ArenaBridgeError):
            CB.decode_reply(reply)
    with pytest.raises(CB.ArenaBridgeError) as e:
        CB.decode_reply(b'{"status":409,"payload":{"ok":false,"code":"exit_service_not_ready"}}\n')
    assert (e.value.status, e.value.code) == (409, "exit_service_not_ready")


def test_real_unix_socket_round_trip(root, monkeypatch, tmp_path):
    plan, exits, _, (pid, _) = _opened(root)
    sock = tmp_path / "s" / "arena.sock"
    sock.parent.mkdir()
    monkeypatch.setattr(CB, "SOCKET_PATH", str(sock))
    server = CBS._Server(str(sock), CBS._handler({"qwen": plan}))
    t = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    t.start()
    try:
        env = dict(PAPER_ENV, V3_ARENA_CLOSE_SOCKET=str(sock))
        # il server usa l'ora reale: la richiesta e' valida ma il servizio uscite (heartbeat sintetico) e' vecchio
        with pytest.raises(CB.ArenaBridgeError) as e:
            CB.send("close", "qwen", {"position_id": pid, "request_id": RID}, environ=env)
        assert e.value.code == "exit_service_not_ready"
        with pytest.raises(CB.ArenaBridgeError) as e:
            CB.send("status", "qwen", {"request_id": RID}, environ=env)
        assert (e.value.status, e.value.code) == (404, "request_not_found")
    finally:
        server.shutdown()
        server.server_close()
        exits.stop()
    assert MC.read_chain(plan.folder / MC.REQUESTS_FILE) == []
