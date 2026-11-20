"""Endpoint /api/v3/brain/memory: memoria e apprendimento del Brain in sola lettura, da un journal prodotto dal ciclo
REALE (motore, traccia, snapshot, tesi). Nessuna rete; sessione obbligatoria; nessun training dichiarato."""
from __future__ import annotations

import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import backend.v3_api as api
from backend.tests.test_v3_runner_cycle import NOW, RUN
from backend.v3.events import EventJournal
from backend.v3.runner.test_decision_trace import ScriptAnalyst, _run
from backend.v3.runner.test_thesis import _chain
from backend.v3_api import V3Paths, make_router


def _client(journal_path, run_id=RUN, authorized=True):
    app = FastAPI()

    def auth():
        if not authorized:
            raise HTTPException(status_code=401)
        return "ok"
    app.include_router(make_router(auth, V3Paths(journal_path=journal_path, run_id=run_id, budget_db_path=None,
                                                  heartbeat_path=None, pause_flag_path=None,
                                                  falco_data_dir="/nonexistent", toro_data_dir="/nonexistent")))
    return TestClient(app)


def _get(client):
    r = client.get("/api/v3/brain/memory")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    return r.json()


def _journal_with(cycle):
    from backend.tests.test_v3_runner_cycle import _journal
    api._MEMORY_CACHE.clear()
    j = _journal()
    cycle(j)
    return j


def test_session_is_required(tmp_path):
    assert _client(str(tmp_path / "j.db"), authorized=False).get("/api/v3/brain/memory").status_code == 401


def test_without_journal_the_brain_is_not_started(tmp_path):
    assert _get(_client(str(tmp_path / "none.db")))["state"] == "not_started"


def test_memory_counts_only_valid_links_and_keeps_no_trade():
    j = _journal_with(lambda j: (_run(j, ScriptAnalyst()), _run(j, ScriptAnalyst(kind="NO_TRADE"),
                                                                    symbols=("CCCUSDT",))))
    d = _get(_client(str(j.filename)))
    m = d["memory"]
    assert d["state"] == "ok" and (m["decisions"], m["valid_links"], m["coverage_pct"]) == (3, 3, "100.0")
    assert m["chain_ok"] is True and m["no_trade"] == 1 and m["untraced_opens"] == 0
    assert [x["link"] for x in d["recent"]] == ["valid"] * 3 and d["recent"][0]["symbol"] == "CCCUSDT"


def test_untraced_decisions_and_opens_are_visible():
    j = _journal_with(lambda j: _run(j, ScriptAnalyst(), trace="off"))
    m = _get(_client(str(j.filename)))["memory"]
    assert (m["valid_links"], m["missing"], m["untraced_opens"], m["coverage_pct"]) == (0, 2, 2, "0.0")


def test_a_broken_chain_trusts_nothing():
    j = _journal_with(lambda j: _run(j, ScriptAnalyst()))
    con = sqlite3.connect(j.filename)
    con.execute("DROP TRIGGER v3_no_update")
    con.execute("UPDATE v3_events SET source='x' WHERE seq=1")
    con.commit()
    con.close()
    api._MEMORY_CACHE.clear()
    d = _get(_client(str(j.filename)))
    assert d["memory"]["chain_ok"] is False and d["memory"]["valid_links"] == 0
    assert {x["link"] for x in d["recent"]} == {"chain_broken"}
    assert d["learning"]["valid_examples_collected"] == 0


def test_theses_and_reentries_are_shown_in_observe_mode():
    j = _journal_with(lambda j: _chain(j, 3))
    d = _get(_client(str(j.filename)))
    t = d["theses"]
    assert (t["mode"], t["enforce_active"], t["opens_with_thesis"], t["distinct_theses"]) == ("observe", False, 3, 1)
    assert (t["reentries"], t["would_block"], t["rules"]) == (2, 1, {"reentry_limit": 1})
    assert d["recent"][0]["reentry_index"] == 3 and d["recent"][0]["would_block"] is True


def test_learning_is_collection_progress_never_training():
    j = _journal_with(lambda j: _run(j, ScriptAnalyst()))
    lr = _get(_client(str(j.filename)))["learning"]
    assert lr["training_authorized"] is False and lr["model_active"] is False and lr["inputs_verified"] == 0
    assert lr["verification"] == "dataset_builder" and lr["valid_examples_collected"] == 2 and lr["distinct_days"] == 1
    assert lr["shadow_threshold"] == {"examples": 300, "days": 20}
    assert lr["promotion_review_threshold"] == {"examples": 1000, "days": 45}


def test_the_cache_follows_the_journal():
    j = _journal_with(lambda j: _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",)))
    c = _client(str(j.filename))
    assert _get(c)["memory"]["decisions"] == 1
    _run(EventJournal(j.filename), ScriptAnalyst(kind="NO_TRADE"), symbols=("BBBUSDT",))
    assert _get(c)["memory"]["decisions"] == 2


def test_the_endpoint_never_exposes_features_risk_or_model_text():
    j = _journal_with(lambda j: _run(j, ScriptAnalyst()))
    text = _client(str(j.filename)).get("/api/v3/brain/memory").text
    for banned in ("features", "inputs_digest", "equity_usd", "claim", "context_hash"):
        assert banned not in text


def test_arena_history_route_is_opt_in_read_only_and_has_no_close(monkeypatch):
    from fastapi import FastAPI
    from backend.v3_api import V3Paths, make_router
    paths = V3Paths(journal_path=None, run_id="r", budget_db_path=None, heartbeat_path=None, pause_flag_path=None,
                    falco_data_dir="/x", toro_data_dir="/y")

    def client(env):
        for k in ("V3_ARENA_READONLY_ENABLED", "DESK_MODE", "TRADING_MODE", "V3_ARENA_TRIAL_DAY", "V3_ARENA_ROOT"):
            monkeypatch.delenv(k, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        app = FastAPI()
        app.include_router(make_router(lambda: "ok", paths))
        return TestClient(app)
    import tempfile
    on = {"V3_ARENA_READONLY_ENABLED": "1", "DESK_MODE": "paper", "TRADING_MODE": "paper", "V3_ARENA_TRIAL_DAY": "2026-11-18",
          "V3_ARENA_ROOT": tempfile.mkdtemp()}                                       # mai i dati reali in un test
    assert client({}).get("/api/v3/arena").status_code == 404                          # spento di default
    c = client(on)
    r = c.get("/api/v3/arena")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert c.post("/api/v3/arena").status_code == 405                                  # solo lettura
    assert c.post("/api/v3/arena/close", json={}).status_code == 404                   # chiusura non portata
    assert client({**on, "TRADING_MODE": "live"}).get("/api/v3/arena").status_code == 404
