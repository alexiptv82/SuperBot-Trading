"""RC84 D1: stato di riconciliazione dei claim PAPER esposto (sola lettura, sanitizzato) in /api/v3/overview."""
import json
import re
import time

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.tests.test_v3_dashboard_unified import _paths
from backend.v3_api import V3Paths, _claim_reconciliation, make_router

NOW = time.time()
SECRET_MARKERS = ("claim_id", "rec", "notice", "net", "5.03", "close_ms", "margin", "reason")


def _claim(symbol="BTC", status=None, net=5.0267, claim_id="1|BTC|7|1|2|terminal|5.0267"):
    c = {"claim_id": claim_id, "run_no": 1, "notice": ["motivo riservato", "chiusura manuale"],
         "rec": {"id": 7, "symbol": symbol, "side": 1, "open_ms": 1, "close_ms": 2, "net": net,
                 "why": "x", "margin": 30.0}}
    if status:
        c["status"] = status
    return c


def _state(claims=None, **extra):
    st = {"main": {"positions": {}, "closed": [], "cash": 1000.0}, "run_no": 1}
    if claims is not None:
        st["paper_close_claims"] = claims
    st.update(extra)
    return st


def _write(d, name, obj):
    (d / name).write_text(json.dumps(obj), encoding="utf-8")


def _hb(**extra):
    return dict({"age_s": 3.0}, **extra)


# ---------------------------------------------------------------- funzione pura

def test_no_claims_is_ok():
    r = _claim_reconciliation(_state([]), _hb())
    assert r == {"state": "ok", "pending_count": 0, "conflict_count": 0, "affected_symbols": [],
                 "checkpointed_not_final": False}
    assert _claim_reconciliation(_state(None), None)["state"] == "ok"     # chiave assente: nessun claim


def test_pending_claim_is_reported_with_sanitized_symbols_only():
    r = _claim_reconciliation(_state([_claim("BTC"), _claim("ETH", claim_id="2|ETH|8|1|2|terminal|1")]), _hb())
    assert r["state"] == "pending" and r["pending_count"] == 2 and r["conflict_count"] == 0
    assert r["affected_symbols"] == ["BTC", "ETH"] and r["checkpointed_not_final"] is True
    blob = json.dumps(r)
    assert not any(m in blob for m in ("claim_id", "notice", "motivo riservato", "5.0267", "close_ms", "margin"))


def test_conflict_dominates_and_heartbeat_conflict_is_used_only_when_fresh():
    r = _claim_reconciliation(_state([_claim("BTC", "conflict"), _claim("ETH")]), _hb())
    assert r["state"] == "conflict" and r["conflict_count"] == 1 and r["pending_count"] == 1
    st = _state([_claim("BTC")])
    assert _claim_reconciliation(st, _hb(paper_close_claims={"pending": 0, "conflict": ["x"]}))["state"] == "conflict"
    stale = {"age_s": 9999.0, "paper_close_claims": {"conflict": ["x"]}}
    assert _claim_reconciliation(st, stale)["state"] == "pending"


@pytest.mark.parametrize("bad", ["str", {"a": 1}, [1, 2], [None], 7])
def test_malformed_claims_are_unknown_not_ok(bad):
    r = _claim_reconciliation(_state(bad), _hb())
    assert r["state"] == "unknown" and r["checkpointed_not_final"] is False


@pytest.mark.parametrize("missing", [None, {}, "x", []])
def test_missing_state_is_unknown_not_ok(missing):
    assert _claim_reconciliation(missing, _hb())["state"] == "unknown"


def test_symbols_are_validated_unique_sorted_and_limited():
    claims = [_claim(s) for s in ["<script>", "A" * 40, "../x", "eth", "ETH", "BTC"] + [f"S{i}" for i in range(20)]]
    r = _claim_reconciliation(_state(claims), _hb())
    assert len(r["affected_symbols"]) <= 8
    assert all(re.fullmatch(r"[A-Z0-9]{1,16}", s) for s in r["affected_symbols"])
    assert r["affected_symbols"] == sorted(set(r["affected_symbols"]))
    assert "<script>" not in json.dumps(r) and "../x" not in json.dumps(r)


def test_recovery_completed_returns_to_ok():
    st = _state([_claim()])
    assert _claim_reconciliation(st, _hb())["state"] == "pending"
    st["paper_close_claims"] = []                                           # claim provato e rimosso
    assert _claim_reconciliation(st, _hb(paper_close_claims={"pending": 0, "conflict": []}))["state"] == "ok"


# ---------------------------------------------------------------- endpoint autenticato

def _client(tmp_path, authorized=True):
    paths = _paths(tmp_path)
    app = FastAPI()

    def auth():
        if not authorized:
            raise HTTPException(401, "session_missing")
        return "authorized"
    app.include_router(make_router(auth, paths, None))
    return TestClient(app), paths


def _overview(client):
    r = client.get("/api/v3/overview")
    assert r.status_code == 200, r.text
    return {p["id"]: p for p in r.json()["portfolios"]}


def test_overview_exposes_pending_and_conflict_per_portfolio_even_with_zero_positions(tmp_path):
    client, paths = _client(tmp_path)
    from pathlib import Path
    _write(Path(paths.falco_data_dir), "state_v2.json", _state([_claim("BTC")]))
    _write(Path(paths.toro_data_dir), "state_v2.json", _state([_claim("ETH", "conflict")]))
    _write(Path(paths.falco_data_dir), "heartbeat.json", {"ts": NOW, "portfolio": "hawk", "exec_mode": "paper"})
    ov = _overview(client)
    f, t = ov["falco"], ov["toro"]
    assert f["open_positions"] == 0 and t["open_positions"] == 0
    assert f["close_reconciliation"]["state"] == "pending" and f["close_reconciliation"]["affected_symbols"] == ["BTC"]
    assert t["close_reconciliation"]["state"] == "conflict"
    blob = json.dumps(ov)
    assert "claim_id" not in blob and "motivo riservato" not in blob and "5.0267" not in blob
    assert "close_reconciliation" not in ov["brain"]                         # il Brain non eredita il campo classico
    assert f["closed_trades"] == [] and f["realized_pnl"] == "0"            # nessun importo inventato o azzerato a mano


def test_overview_without_state_reports_unknown_and_with_clean_state_reports_ok(tmp_path):
    client, paths = _client(tmp_path)
    from pathlib import Path
    _write(Path(paths.toro_data_dir), "state_v2.json", _state([]))
    ov = _overview(client)
    assert ov["falco"]["close_reconciliation"]["state"] == "unknown"        # nessun dato verificabile
    assert ov["toro"]["close_reconciliation"]["state"] == "ok"


def test_overview_works_with_brain_data_absent_and_keeps_stop_health(tmp_path):
    client, paths = _client(tmp_path)                                         # nessun journal/heartbeat Brain
    from pathlib import Path
    _write(Path(paths.falco_data_dir), "state_v2.json", _state([_claim("BTC")]))
    ov = _overview(client)
    assert ov["falco"]["close_reconciliation"]["state"] == "pending"
    assert "stop_health" in ov["falco"] and ov["brain"]["state"] == "not_started"


def test_unauthenticated_overview_is_refused_and_no_write_routes_were_added(tmp_path):
    client, _ = _client(tmp_path, authorized=False)
    assert client.get("/api/v3/overview").status_code == 401
    router = make_router(lambda: "ok", V3Paths(None, "", None, None, None, "/tmp", "/tmp"), None)
    methods = {r.path: r.methods for r in router.routes}
    assert methods["/api/v3/brain/close"] == {"POST"}                         # unica scrittura preesistente (Brain)
    assert all(m == {"GET"} for path, m in methods.items() if path != "/api/v3/brain/close")
    assert set(methods) == {"/api/v3/overview", "/api/v3/brain/status", "/api/v3/brain/scoreboard",
                            "/api/v3/brain/trades", "/api/v3/brain/close", "/api/v3/brain/close-result"}


def test_reading_the_overview_never_modifies_state_or_registers(tmp_path):
    client, paths = _client(tmp_path)
    from pathlib import Path
    d = Path(paths.falco_data_dir)
    _write(d, "state_v2.json", _state([_claim("BTC")]))
    (d / "trade_history.jsonl").write_text("", encoding="utf-8")
    before = {p.name: p.read_bytes() for p in d.iterdir()}
    _overview(client)
    _overview(client)
    after = {p.name: p.read_bytes() for p in d.iterdir()}
    assert before == after


# ---------------------------------------------------------------- snapshot divergenti

def test_fresh_heartbeat_with_pending_claims_but_clean_state_is_never_ok():
    r = _claim_reconciliation(_state([]), _hb(paper_close_claims={"pending": 2, "conflict": []}))
    assert r["state"] == "unknown" and r["pending_count"] == 0


def test_stale_or_invalid_heartbeat_claims_do_not_change_a_clean_state():
    stale = {"age_s": 9999.0, "paper_close_claims": {"pending": 3, "conflict": []}}
    assert _claim_reconciliation(_state([]), stale)["state"] == "ok"
    for bad in ({"pending": "3"}, {"pending": True}, {"pending": -1}, {"pending": 0}, "x", None):
        assert _claim_reconciliation(_state([]), _hb(paper_close_claims=bad))["state"] == "ok"


def test_agreeing_snapshots_stay_pending_and_a_heartbeat_pending_zero_confirms_ok():
    assert _claim_reconciliation(_state([_claim()]), _hb(paper_close_claims={"pending": 1, "conflict": []}))["state"] == "pending"
    assert _claim_reconciliation(_state([]), _hb(paper_close_claims={"pending": 0, "conflict": []}))["state"] == "ok"
