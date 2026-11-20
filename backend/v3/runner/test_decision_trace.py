"""Traccia causale delle decisioni nel ciclo reale (BrainEngine -> journal -> snapshot v2 -> apertura PAPER).

Produttori VERI: motore, journal, adattatore snapshot, execute_paper e lettore del Dataset Builder. Finti solo le
candele e il modello, come in ``test_v3_runner_cycle``. Ogni garanzia chiesta dal proprietario ha un test:
causalita' (dopo la decisione, prima dell'apertura, niente futuro), NO_TRADE conservate, niente duplicati,
fallimento rilevabile e nessuna apertura non tracciata, uscite/rischio indipendenti, esclusione dal training.
"""
from __future__ import annotations

import ast
import dataclasses
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tests.test_v3_runner_cycle import (
    NOW, RULES, RUN, STEP, VIEW, FakeStore, ScriptAnalyst, _bars, _events, _journal, _mandate, POLICY,
)
from backend.v3.decision_snapshot_v2 import SNAPSHOT_KIND
from backend.v3.events import EventJournal
from backend.v3.features.indicators import Bar
from backend.v3.runner import decision_trace as dt
from backend.v3.runner.cycle import CycleBars, MarketEntryAnalyst, run_brain_cycle

D = Decimal
ROOT = Path(__file__).resolve().parents[3]
TRAINING = ROOT / "ops" / "brain-unico" / "training"


def _run(journal, analyst, *, store=None, trace="required", symbols=("AAAUSDT", "BBBUSDT"), mandate=...):
    return run_brain_cycle(
        now_ms=NOW, journal=journal, run_id=RUN, symbols=symbols, store=store or FakeStore(NOW),
        bars_holder=CycleBars(), analyst=MarketEntryAnalyst(analyst), view_params=VIEW, risk_policy=POLICY,
        mandate=_mandate() if mandate is ... else mandate, policy_verifier=lambda m, p: True,
        market_rules=lambda s: RULES, initial_equity=D("1000"), slippage_bps=2, allowed_strategy_ids=("S25",),
        trace=trace)


def _rows(j):
    return j.list_run("brain", RUN)


def _snapshot_for(j, decision_id):
    return [r for r in _rows(j) if r.event.kind == SNAPSHOT_KIND
            and r.event.payload["decision_event_id"] == decision_id]


# ------------------------------------------------------------------------------------------------ causalita'

def test_every_open_has_its_snapshot_after_the_decision_and_before_the_open():
    j = _journal()
    rep = _run(j, ScriptAnalyst())
    assert [s for s, _ in rep.opened] == ["AAAUSDT", "BBBUSDT"] and rep.errors == ()
    assert [t[1] for t in rep.traces] == ["recorded", "recorded"]
    for op in [r for r in _rows(j) if r.event.kind == "paper_open"]:
        did = op.event.payload["decision_event_id"]
        dec = [r for r in _rows(j) if r.event.event_id == did][0]
        snap, = _snapshot_for(j, did)
        assert dec.seq < snap.seq < op.seq                                 # ordine di scrittura causale
        p = snap.event.payload
        assert p["decision_event_hash"] == dec.event_hash and p["action"] == "OPEN" and p["status"] == "APPROVED"
        assert p["decision_ts_ms"] == p["snapshot_captured_at_ms"] == NOW
        assert p["feature_asof_ms"] <= NOW
        assert p["inputs_verified"] is False and p["eligible_for_training"] is False
        assert p["feature_source"] == "unverified_snapshot"
        assert {"t15m_ret_1", "t1h_rsi14", "t4h_atr14_pct", "fset_version"} <= set(p["features"])
        assert set(p["risk"]) == {"equity_usd", "margin_in_use_usd", "open_risk_usd", "available_margin_usd"}


def test_no_trade_decisions_are_traced_too():
    j = _journal()
    rep = _run(j, ScriptAnalyst(kind="NO_TRADE"))
    assert rep.opened == () and rep.errors == ()
    decs = _events(j, "brain_decision")
    assert len(decs) == 2 and {d.payload["kind"] for d in decs} == {"NO_TRADE"}
    for d in decs:
        snap, = _snapshot_for(j, d.event_id)
        assert snap.event.payload["action"] == "NO_TRADE"
    assert {t[2] for t in rep.traces} == {d.event_id for d in decs}


def test_engine_fail_closed_no_trade_is_traced():
    j = _journal()
    rep = _run(j, ScriptAnalyst(raises=True), symbols=("AAAUSDT",))
    dec, = _events(j, "brain_decision")
    assert dec.payload["rationale"] == "ai_unavailable" and _snapshot_for(j, dec.event_id)
    assert rep.traces[0][1] == "recorded"


def test_risk_rejected_and_unauthorized_decisions_are_traced():
    j = _journal()
    _run(j, ScriptAnalyst(), mandate=_mandate(approved=False), symbols=("AAAUSDT",))
    dec, = _events(j, "brain_decision")
    assert dec.payload["rationale"] == "policy_not_authorized" and _snapshot_for(j, dec.event_id)
    assert _events(j, "paper_open") == []


def _with_open_bar(tf):
    bars = _bars(tf)
    last = bars[-1]
    # una barra ancora aperta (chiude dopo NOW) con un prezzo estremo: non deve entrare in nessuna feature
    return bars + [Bar(last.open_time_ms + STEP[tf], last.close, D("999"), last.close, D("999"), D("1"))]


def test_features_never_use_a_bar_that_was_not_closed_at_decision_time():
    clean = dt.decision_features({tf: _bars(tf) for tf in STEP}, VIEW.timeframes, now_ms=NOW)
    leaked = dt.decision_features({tf: _with_open_bar(tf) for tf in STEP}, VIEW.timeframes, now_ms=NOW)
    assert leaked == clean and clean[1] <= NOW


def test_the_cycle_does_not_decide_on_a_view_containing_an_open_bar():
    class FutureStore(FakeStore):
        def refresh(self, symbol, tf, now_ms):
            return _with_open_bar(tf)

    j = _journal()
    rep = _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",), store=FutureStore(NOW))
    assert rep.decisions == () and _events(j, SNAPSHOT_KIND) == [] and rep.errors


def test_feature_values_are_recomputable_from_the_same_bars():
    feats, asof = dt.decision_features({tf: _bars(tf) for tf in STEP}, VIEW.timeframes, now_ms=NOW)
    b = _bars("15m")
    assert feats["t15m_ret_1"] == (b[-1].close / b[-2].close - 1).quantize(D("1e-10"))
    assert asof == max(_bars(tf)[-1].open_time_ms + STEP[tf] for tf in STEP)
    assert dt.decision_features({}, VIEW.timeframes, now_ms=NOW) == ({}, None)


# ------------------------------------------------------------------------------------------------ duplicati

def test_retracing_the_same_decision_does_not_duplicate():
    j = _journal()
    rep = _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",))
    did = rep.traces[0][2]
    again = dt.record_decision_trace(
        journal=j, run_id=RUN, symbol="AAAUSDT", now_ms=NOW, after_seq=0, expected_event_id=did,
        bars_by_tf={tf: _bars(tf) for tf in STEP}, timeframes=VIEW.timeframes,
        portfolio=__import__("backend.v3.runner.cycle", fromlist=["x"]).snapshot_from_summary(
            __import__("backend.v3.dashboard", fromlist=["x"]).build_summary(j, "brain", RUN), D("1000")))
    assert again.ok and again.code == "already_recorded" and len(_snapshot_for(j, did)) == 1


def test_a_replayed_cycle_never_creates_a_second_snapshot_for_a_decision():
    j = _journal()
    _run(j, ScriptAnalyst(kind="NO_TRADE"))
    rep2 = _run(j, ScriptAnalyst(kind="NO_TRADE"))                        # stesso istante: stessa decisione
    snaps = _events(j, SNAPSHOT_KIND)
    ids = [e.payload["decision_event_id"] for e in snaps]
    assert len(ids) == len(set(ids)) == len(_events(j, "brain_decision"))
    # la seconda decisione non e' entrata nel journal (id gia' usato): il giro lo dice invece di tacere
    assert {c for _, c in rep2.errors} == {"decision_not_journaled"}


# ------------------------------------------------------------------------------------------------ fallimento

def test_snapshot_failure_blocks_the_open_and_is_reported(monkeypatch):
    def broken(**kw):
        raise OSError("disk full")
    monkeypatch.setattr(dt, "append_snapshot", broken)
    j = _journal()
    rep = _run(j, ScriptAnalyst(), symbols=("AAAUSDT",))
    assert rep.opened == () and _events(j, "paper_open") == []
    assert rep.errors == (("AAAUSDT", "snapshot_write_failed"), ("AAAUSDT", "open_blocked_untraced"))
    assert rep.decisions[0][1:3] == ("OPEN", "APPROVED")                   # la decisione resta registrata
    cov = dt.trace_coverage(j, RUN)
    assert cov.decisions == 1 and cov.traced == 0 and len(cov.untraced_decisions) == 1


def test_snapshot_rejected_by_the_adapter_blocks_the_open(monkeypatch):
    def late(**kw):
        raise ValueError("snapshot_written_late")
    monkeypatch.setattr(dt, "append_snapshot", late)
    j = _journal()
    rep = _run(j, ScriptAnalyst(), symbols=("AAAUSDT",))
    assert rep.opened == ()
    assert rep.errors == (("AAAUSDT", "snapshot_snapshot_written_late"), ("AAAUSDT", "open_blocked_untraced"))


def test_no_trade_trace_failure_is_reported_without_side_effects(monkeypatch):
    monkeypatch.setattr(dt, "append_snapshot", lambda **kw: (_ for _ in ()).throw(OSError("x")))
    j = _journal()
    rep = _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",))
    assert rep.errors == (("AAAUSDT", "snapshot_write_failed"),) and rep.opened == ()


def test_a_decision_the_engine_failed_to_journal_is_made_visible():
    class NoDecisions(EventJournal):
        def append(self, event):
            if event.kind == "brain_decision":
                raise OSError("locked")
            return super().append(event)

    import os, tempfile
    j = NoDecisions(os.path.join(tempfile.mkdtemp(), "journal.db"))
    j.init_schema()
    rep = _run(j, ScriptAnalyst(), symbols=("AAAUSDT",))
    assert rep.opened == () and _events(j, "paper_open") == []
    assert ("AAAUSDT", "decision_not_journaled") in rep.errors


def test_trace_off_keeps_the_previous_behaviour_and_bad_mode_is_refused():
    j = _journal()
    rep = _run(j, ScriptAnalyst(), trace="off")
    assert len(rep.opened) == 2 and rep.traces == () and _events(j, SNAPSHOT_KIND) == []
    with pytest.raises(ValueError, match="invalid_trace_mode"):
        _run(_journal(), ScriptAnalyst(), trace="on")


def test_coverage_counts_from_the_journal_alone():
    j = _journal()
    _run(j, ScriptAnalyst())
    cov = dt.trace_coverage(j, RUN)
    assert cov == dt.Coverage(2, 2, (), ())


# ------------------------------------------------------------------------------------------------ indipendenza

@pytest.mark.parametrize("module", [
    "backend/v3/runner/exit_service.py", "backend/v3/runner/exit_worker.py", "backend/v3/runner/exits.py",
    "backend/v3/runner/daily_loss.py", "backend/v3/runner/post_ai_guard.py", "backend/v3/runner/open_serial.py",
    "backend/v3/risk.py",
])
def test_risk_and_exit_paths_do_not_depend_on_the_trace(module):
    tree = ast.parse((ROOT / module).read_text())
    names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any("decision_trace" in m or "decision_snapshot" in m for m in names)


def test_the_wired_runner_requires_the_trace():
    src = (ROOT / "backend/v3/runner/wiring.py").read_text()
    assert 'trace="required"' in src


# ------------------------------------------------------------------------------------------------ training

def test_the_dataset_builder_admits_the_snapshot_but_never_as_verified_training_data():
    sys.path.insert(0, str(TRAINING))
    try:
        import readers as R
        import snapshot_link as SL
    finally:
        sys.path.remove(str(TRAINING))
    j = _journal()
    _run(j, ScriptAnalyst())
    _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("CCCUSDT",))
    data = R.read_v3(str(j.filename))
    opens_by_decision = {}
    for o in data["opens"].values():
        opens_by_decision.setdefault(o["p"].get("decision_event_id"), []).append(o["seq"])
    assert len(data["decisions"]) == 3
    for did, dec in data["decisions"].items():
        adm = SL.admit(did, dec, data["snapshots"].get(did), opens_by_decision.get(did, []), data["timeline"])
        assert adm.status == "admitted", (did, adm.reason)
    for snaps in data["snapshots"].values():
        assert all(s["p"]["eligible_for_training"] is False and s["p"]["inputs_verified"] is False for s in snaps)


def test_opens_without_a_snapshot_are_listed_by_coverage():
    j = _journal()
    rep = _run(j, ScriptAnalyst(), trace="off")
    cov = dt.trace_coverage(j, RUN)
    assert cov.traced == 0 and set(cov.untraced_opens) == {pid for _, pid in rep.opened}


def test_two_decisions_for_the_same_symbol_and_instant_are_ambiguous_not_guessed():
    from backend.v3.events import Event
    j = _journal()
    for i in (1, 2):
        j.append(Event(event_id=f"brain-req-x{i}", portfolio_id="brain", run_id=RUN, kind="brain_decision",
                       occurred_at_ms=NOW, source="brain_f2_engine",
                       payload={"kind": "NO_TRADE", "status": "REJECTED", "rationale": "deepseek:analysis",
                                "sources": [], "claim": str(i), "symbol": "AAAUSDT", "regime": "RANGE"}))
    tr = dt.record_decision_trace(journal=j, run_id=RUN, symbol="AAAUSDT", now_ms=NOW, after_seq=0,
                                  expected_event_id=None, bars_by_tf={tf: _bars(tf) for tf in STEP},
                                  timeframes=VIEW.timeframes, portfolio=None)
    assert (tr.ok, tr.code) == (False, "decision_ambiguous") and _events(j, SNAPSHOT_KIND) == []
