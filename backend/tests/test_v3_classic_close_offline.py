"""The unified PAPER app must never leave dormant legacy close flags on a stopped bot."""
from __future__ import annotations

import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import desk_api
import desk_view as dv


def _portfolio(tmp_path, *, heartbeat=None, paused=True):
    state = {
        "main": {"cash": 900, "positions": {"BTC": {
            "symbol": "BTC", "side": -1, "entry": 100.0, "qty": 10.0,
            "margin": 100.0, "leverage": 20, "sl": 110.0,
        }}, "closed": [], "limits": {"start_equity": 1000}},
    }
    (tmp_path / "state_v2.json").write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "trade_history.jsonl").write_text("historic record stays untouched\n", encoding="utf-8")
    if heartbeat is not None:
        (tmp_path / "heartbeat.json").write_text(
            json.dumps({"ts": heartbeat, "close_position": True, "exec_mode": "paper"}),
            encoding="utf-8",
        )
    if paused:
        (tmp_path / "pause.flag").write_text("", encoding="utf-8")


def _app(tmp_path):
    app = FastAPI()
    def auth():
        return {"authenticated": True}
    async def prices(_symbol):
        return {"price": 101}
    app.include_router(desk_api.make_router("hawk", str(tmp_path), auth, prices), prefix="/api/desk")
    return app


@pytest.mark.parametrize("age", [None, 61, 3600, -31, "nan"])
def test_offline_classic_close_refused_without_any_writes(tmp_path, age):
    now = time.time()
    stamp = None if age is None else ("nan" if age == "nan" else now - age)
    _portfolio(tmp_path, heartbeat=stamp)
    state_before = (tmp_path / "state_v2.json").read_bytes()
    history_before = (tmp_path / "trade_history.jsonl").read_bytes()
    with TestClient(_app(tmp_path)) as client:
        close_all = client.post("/api/desk/close-all")
        assert close_all.status_code == 409
        assert "non sta rispondendo" in close_all.json()["detail"]
        close_one = client.post("/api/desk/close-position", json={"symbol": "BTC"})
        assert close_one.status_code == 409
        assert "non sta rispondendo" in close_one.json()["detail"]
    assert not (tmp_path / "reset.flag").exists()
    assert not (tmp_path / "close_position.flag").exists()
    assert (tmp_path / "state_v2.json").read_bytes() == state_before
    assert (tmp_path / "trade_history.jsonl").read_bytes() == history_before


def test_active_paper_worker_can_receive_manual_close_even_while_paused(tmp_path):
    _portfolio(tmp_path, heartbeat=time.time(), paused=True)
    assert dv.close_worker_ready(dv.read_heartbeat(str(tmp_path)))
    assert dv.can_close_position(dv.read_heartbeat(str(tmp_path)))
    with TestClient(_app(tmp_path)) as client:
        one = client.post("/api/desk/close-position", json={"symbol": "BTC"})
        assert one.status_code == 200
        assert one.json()["queued"] is True
        conflict = client.post("/api/desk/close-all")
        assert conflict.status_code == 409  # one active close at a time
        assert not (tmp_path / "reset.flag").exists()
        # Simulate acknowledgment/consumption, without changing trading state.
        (tmp_path / "close_position.flag").unlink()
        all_positions = client.post("/api/desk/close-all")
        assert all_positions.status_code == 200
        assert all_positions.json()["queued"] is True
    assert not (tmp_path / "close_position.flag").exists()
    assert (tmp_path / "reset.flag").is_file()
    # The endpoint itself only queues. It never mutates positions or pretends they closed.
    assert "BTC" in json.loads((tmp_path / "state_v2.json").read_text())["main"]["positions"]


def test_offline_close_remains_unavailable_even_when_old_heartbeat_advertises_capability(tmp_path):
    _portfolio(tmp_path, heartbeat=time.time() - 86400)
    hb = dv.read_heartbeat(str(tmp_path))
    assert hb is not None and hb["close_position"] is True
    assert dv.can_close_position(hb) is False
    assert dv.command_close_all(str(tmp_path))["queued"] is False
    assert dv.command_close_position(str(tmp_path), "BTC")[0] is False
    assert not (tmp_path / "reset.flag").exists()
    assert not (tmp_path / "close_position.flag").exists()
