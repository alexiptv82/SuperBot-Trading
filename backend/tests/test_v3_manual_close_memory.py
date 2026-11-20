"""Chiusura manuale dall'app fino alla memoria e al Dataset Builder (produttori reali, nessuna rete).

Requisito del proprietario: la chiusura manuale e' registrata nel journal come INTERVENTO dell'operatore, distinta
dalle uscite automatiche; il Brain puo' usarla per valutare le strategie ma non la interpreta come strategia corretta.
"""
from __future__ import annotations

import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

import backend.v3_api as api
from backend.tests.test_v3_runner_cycle import NOW, RUN, _events, _journal
from backend.v3.executor.paper_close import close_paper
from backend.v3.learning.expectancy import default_cell_key as default_key
from backend.v3.outcomes import extract_outcomes
from backend.v3.runner.manual_close import run_manual_close
from backend.v3.runner.test_decision_trace import ScriptAnalyst, _run
from backend.tests.test_v3_brain_memory_api import _client

D = Decimal
ROOT = Path(__file__).resolve().parents[2]


def _two_positions_one_closed_by_operator_one_by_stop():
    j = _journal()
    rep = _run(j, ScriptAnalyst())                                    # due aperture reali
    (_, manual_pid), (_, stop_pid) = rep.opened
    data_dir = Path(tempfile.mkdtemp())
    (data_dir / "close_request.json").write_text(json.dumps({"ts_ms": NOW + 60_000, "position_ids": [manual_pid]}))
    report = run_manual_close(journal=j, portfolio_id="brain", run_id=RUN, data_dir=data_dir,
                              price_of=lambda sym, now: D("101"), fee_bps=D("6"), now_ms=NOW + 61_000)
    assert report.status == "done" and report.closed == (manual_pid,)
    close_paper(portfolio_id="brain", run_id=RUN, position_id=stop_pid, exit_price=D("99"), reason="stop",
                fee_bps=D("6"), journal=j, now_ms=NOW + 120_000)
    return j, manual_pid, stop_pid


def test_the_journal_records_the_operator_close_distinct_from_the_automatic_exit():
    j, manual_pid, stop_pid = _two_positions_one_closed_by_operator_one_by_stop()
    closes = {e.payload["position_id"]: e.payload for e in _events(j, "paper_close")}
    assert closes[manual_pid]["reason"] == "manual" and closes[stop_pid]["reason"] == "stop"
    outs = {o.position_id: o for o in extract_outcomes(j, "brain", RUN).outcomes}
    assert outs[manual_pid].is_manual is True and outs[stop_pid].is_manual is False
    assert outs[manual_pid].link_status == "linked"                   # resta collegata alla decisione che l'ha aperta
    # nella valutazione per strategia manuale e automatico non si mischiano mai
    assert default_key(outs[manual_pid])[-1] is True and default_key(outs[stop_pid])[-1] is False


def test_the_strategy_scoreboard_never_counts_the_operator_close_as_strategy_result():
    from backend.v3.brain_view.view import build_scoreboard
    from backend.v3.brain_view.params import load_default_params
    j, manual_pid, stop_pid = _two_positions_one_closed_by_operator_one_by_stop()
    outs = extract_outcomes(j, "brain", RUN).outcomes
    regime = next(o.decision_regime for o in outs)
    board = build_scoreboard(outs, regime=regime, params=load_default_params())
    assert board["n_closed_linked"] == 1                              # solo l'uscita automatica


def test_memory_shows_operator_and_automatic_closes_separately():
    j, _, _ = _two_positions_one_closed_by_operator_one_by_stop()
    api._MEMORY_CACHE.clear()
    m = _client(str(j.filename)).get("/api/v3/brain/memory").json()["memory"]
    assert (m["manual_closes"], m["automatic_closes"]) == (1, 1)


def test_the_dataset_builder_keeps_the_operator_close_as_intervention_not_as_strategy():
    sys.path.insert(0, str(ROOT / "ops" / "brain-unico" / "training"))
    try:
        import builder as B
    finally:
        sys.path.pop(0)
    j, manual_pid, stop_pid = _two_positions_one_closed_by_operator_one_by_stop()
    res = B.build({"inputs": [{"id": "lab", "source_system": "brain_unico", "kind": "v3", "path": str(j.filename)}]})
    rows = {r["provenance"].get("link_status") and r["outcome"].get("exit_reason"): r for r in res["rows"]
            if r["record_kind"] == "executed"}
    manual, auto = rows["manual"], rows["stop"]
    assert manual["outcome"]["closed_by"] == "operator" and manual["outcome"]["is_manual"] is True
    assert auto["outcome"]["closed_by"] == "automatic"
    assert "manual_close_not_imitable" in manual["ineligible_reasons"]          # conservata, mai imitata
    assert "manual_close_not_imitable" not in auto["ineligible_reasons"]
    s = B.summarize(res)
    assert s["manual_closes"] == 1 and s["closed_by"]["operator"] == 1 and s["closed_by"]["automatic"] == 1
