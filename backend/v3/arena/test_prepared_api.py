"""GET /api/v3/arena sulle tre run preparate in pausa: stato autentico, nessun numero, nessuna scrittura."""
from __future__ import annotations

import hashlib

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from backend.v3.arena import trial_setup as TS
from backend.v3.arena.read_router import make_arena_router
from backend.v3.arena.test_trial_setup import DAY, NOW, _prepare, _key_limit  # noqa: F401


def _session(request: Request):
    if request.headers.get("authorization") != "Bearer ok":
        raise HTTPException(401)


def _fingerprint(root):
    return {str(p.relative_to(root)): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_prepared_runs_are_shown_as_not_started_without_numbers_or_writes(tmp_path):
    root = tmp_path / "arena"
    root.mkdir(mode=0o700)
    _prepare(root)
    plans = tuple(TS._plans(root, DAY).values())
    app = FastAPI()
    app.include_router(make_arena_router(_session, plans, enabled=True))
    c = TestClient(app)
    before = _fingerprint(root)
    assert c.get("/api/v3/arena").status_code == 401
    body = c.get("/api/v3/arena", headers={"authorization": "Bearer ok"}).json()
    assert _fingerprint(root) == before                       # nessun -wal/-shm, nessun file toccato
    for p in ("deepseek", "qwen", "minimax"):
        w = body["portfolios"][p]
        assert w["state"] == "not_started" and w["data_status"] == "PREPARED_AWAITING_T0"
        assert w["trial_start_ms"] is None and w["trial_comparable"] is False
        assert all(w.get(k) is None for k in ("equity", "realized_pnl", "settled_equity", "open_count"))
