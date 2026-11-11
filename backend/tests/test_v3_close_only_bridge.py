"""Only offline/mock cases. No Bitget, providers, VPS or actual trade close."""
import json
import os
from pathlib import Path
import socket
import threading
import time

import pytest

from backend.v3 import close_bridge as client
from backend.v3 import close_bridge_server as host
from backend.v3.cutover_gate import (
    classic_single_close_enabled, brain_single_close_enabled,
    should_refuse_mutation,
)


def env(**change):
    d = {
        "V3_CUTOVER_READONLY": "1",
        "V3_ALLOW_CLASSIC_SINGLE_CLOSE": "1",
        "V3_ALLOW_BRAIN_SINGLE_CLOSE": "1",
        "V3_CLOSE_BRIDGE_ONLY": "1",
        "V3_CLOSE_BRIDGE_SOCKET": client.SOCKET_PATH,
        "TRADING_MODE": "paper",
        "DESK_MODE": "paper",
    }
    d.update(change)
    return d


def test_flags_fail_closed_without_bridge_paper_or_correct_socket():
    assert classic_single_close_enabled(env())
    assert brain_single_close_enabled(env())
    for override in (
        {"V3_CLOSE_BRIDGE_ONLY": "0"},
        {"V3_CLOSE_BRIDGE_SOCKET": "/run/other.sock"},
        {"DESK_MODE": "live"}, {"TRADING_MODE": "live"},
        {"V3_CUTOVER_READONLY": "0"},
    ):
        assert not classic_single_close_enabled(env(**override))
        assert not brain_single_close_enabled(env(**override))


def test_only_three_single_close_post_paths_bypass_readonly():
    for path in (
        "/api/desk/close-position",
        "/api/desk/bull/close-position",
        "/api/v3/brain/close",
    ):
        assert not should_refuse_mutation(
            "POST", path, readonly=True,
            allow_paper_single_close=True,
            allow_paper_brain_single_close=True,
        )
    for path in (
        "/api/desk/close-all", "/api/desk/bull/close-all",
        "/api/desk/reset-portfolio", "/api/desk/bull/resume",
        "/api/v3/brain/reset", "/api/bot/start",
        "/api/v3/brain/close/extra", "/api/desk/close-position/extra",
    ):
        assert should_refuse_mutation(
            "POST", path, readonly=True,
            allow_paper_single_close=True,
            allow_paper_brain_single_close=True,
        )


def test_host_strict_contract_rejects_bulk_unknown_wallet_and_extra_fields(monkeypatch):
    def unexpected():
        raise AssertionError("host validation should be first and cause zero writes")
    monkeypatch.setattr(host, "_assert_paper", unexpected)
    for payload in (
        {"wallet": "brain", "all": True},
        {"wallet": "falco", "all": True},
        {"wallet": "toro", "symbol": "BTC", "all": False},
        {"wallet": "brain", "position_id": "one", "pause": False},
        {"wallet": "falco", "symbol": "../../outside"},
        {"wallet": "brain", "position_id": "../../tmp"},
        {"wallet": "live", "symbol": "BTC"},
        ["brain", "BTC"],
    ):
        code, result = host.process_single_close(payload)
        assert code in (422, 423)
        assert result["ok"] is False


def test_no_position_classic_rejected_without_queuing_or_mutating(monkeypatch, tmp_path):
    path = tmp_path / "classic"
    path.mkdir()
    (path / "pause.flag").write_text("1")
    (path / "state_v2.json").write_text('{"main":{"positions":{}}}')
    (path / "exit_only_heartbeat.json").write_text(json.dumps({
        "mode": "paper-exit-only", "ready": True,
        "portfolio": "hawk", "ts": time.time(),
    }))
    originals = set(x.name for x in path.iterdir())
    monkeypatch.setattr(host, "_assert_paper", lambda: None)
    monkeypatch.setattr(host, "FALCO", path)
    status, response = host.process_single_close({"wallet": "falco", "symbol": "BTC"})
    assert status == 404
    assert response["ok"] is False
    assert {x.name for x in path.iterdir()} == originals
    assert not (path / "close_position.flag").exists()


def test_no_exit_worker_rejects_before_writing_classic_command(monkeypatch,tmp_path):
    path = tmp_path / "classic"
    path.mkdir()
    (path / "pause.flag").write_text("1")
    (path / "state_v2.json").write_text('{"main":{"positions":{"BTC":{"margin":1}}}}')
    monkeypatch.setattr(host, "_assert_paper", lambda: None)
    monkeypatch.setattr(host, "TORO", path)
    status, result = host.process_single_close({"wallet": "toro", "symbol": "BTC"})
    assert status == 409
    assert result["ok"] is False
    assert not (path / "close_position.flag").exists()


def test_brain_handler_forward_is_one_id_and_never_bulk(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(host, "_assert_paper", lambda: None)
    seen = []
    monkeypatch.setattr(host, "_brain_paths", lambda: SimpleNamespace(run_id="brain-v3-paper20261111"))
    def single(paths, body, now):
        seen.append((paths.run_id, body, now))
        return {"ok": True, "pending": True, "ts_ms": now}
    monkeypatch.setattr(host, "_close_request", single)
    status, payload = host.process_single_close(
        {"wallet": "brain", "position_id": "exact-001"}, now_ms=12345)
    assert status == 200 and payload["pending"] is True
    assert seen == [("brain-v3-paper20261111", {"position_id": "exact-001"}, 12345)]


def test_bridge_server_rejects_when_any_runtime_flag_live(monkeypatch,tmp_path):
    dirs = [tmp_path / name for name in ("falco", "toro", "brain")]
    for p in dirs:
        p.mkdir()
        (p / "PREPARED_PAUSED_ONLY.json").write_text('{"paper_only":true}')
    (dirs[2] / "journal.db").write_bytes(b"sqlite")
    monkeypatch.setattr(host, "FALCO", dirs[0])
    monkeypatch.setattr(host, "TORO", dirs[1])
    monkeypatch.setattr(host, "BRAIN", dirs[2])
    for key, value in env().items():
        monkeypatch.setenv(key, value)
    host._assert_paper()
    monkeypatch.setenv("TRADING_MODE", "live")
    with pytest.raises(RuntimeError, match="bridge_not_paper_only"):
        host._assert_paper()


def test_client_unreachable_socket_fails_closed(monkeypatch,tmp_path):
    missing=str(tmp_path / "missing.sock")
    monkeypatch.setattr(client, "SOCKET_PATH", missing)
    monkeypatch.setenv("V3_CLOSE_BRIDGE_SOCKET", missing)
    with pytest.raises(client.CloseBridgeError) as e:
        client.send_single_close("brain", "fake-position")
    assert e.value.status == 409


def test_unix_socket_round_trip_rejects_missing_position_and_no_file(monkeypatch,tmp_path):
    s=str(tmp_path / "close.sock")
    monkeypatch.setattr(client, "SOCKET_PATH", s)
    monkeypatch.setenv("V3_CLOSE_BRIDGE_SOCKET", s)
    monkeypatch.setattr(host, "_assert_paper", lambda: None)
    d=tmp_path / "hawk"
    d.mkdir()
    (d / "pause.flag").write_text("1")
    (d / "state_v2.json").write_text('{"main":{"positions":{}}}')
    (d / "exit_only_heartbeat.json").write_text(json.dumps({
        "mode": "paper-exit-only", "ready": True,
        "portfolio": "hawk", "ts": time.time(),
    }))
    monkeypatch.setattr(host, "FALCO", d)
    with host._Server(s, host._Handler) as server:
        task=threading.Thread(target=server.serve_forever,daemon=True)
        task.start()
        try:
            with pytest.raises(client.CloseBridgeError) as e:
                client.send_single_close("falco", "BTC")
            assert e.value.status == 404
            assert not (d / "close_position.flag").exists()
        finally:
            server.shutdown()
            task.join(2)
