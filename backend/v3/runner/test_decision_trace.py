"""Traccia causale delle decisioni nel ciclo reale (BrainEngine -> journal -> snapshot v2 -> apertura PAPER).

Produttori VERI: motore, journal, adattatore snapshot, execute_paper e lettore/regola del Dataset Builder. Finti solo
le candele e il modello, come in ``test_v3_runner_cycle``. Ogni garanzia chiesta dal proprietario ha un test:
causalita' (input catturati prima del modello, snapshot dopo la decisione e prima dell'apertura, niente futuro),
NO_TRADE conservate, niente duplicati, fallimento rilevabile e nessuna apertura non tracciata, copertura che conta
SOLO collegamenti validi (hash, ordine, coerenza), istanti distinti, letture indicizzate, uscite/rischio indipendenti,
esclusione dal training.
"""
from __future__ import annotations

import ast
import os
import sqlite3
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tests.test_v3_runner_cycle import (
    NOW, POLICY, RULES, RUN, STEP, VIEW, FakeStore, ScriptAnalyst, _bars, _events, _journal, _mandate,
)
from backend.v3.decision_snapshot_v2 import SNAPSHOT_KIND, WRITE_GRACE_MS
from backend.v3.events import Event, EventJournal
from backend.v3.features.indicators import Bar
from backend.v3.runner import decision_trace as dt
from backend.v3.runner.cycle import CycleBars, MarketEntryAnalyst, run_brain_cycle

D = Decimal
ROOT = Path(__file__).resolve().parents[3]
TRAINING = ROOT / "ops" / "brain-unico" / "training"


def _run(journal, analyst, *, store=None, trace="required", symbols=("AAAUSDT", "BBBUSDT"), mandate=...,
         holder=None, wall_ms=None, now=NOW):
    return run_brain_cycle(
        now_ms=now, journal=journal, run_id=RUN, symbols=symbols, store=store or FakeStore(now),
        bars_holder=holder or CycleBars(), analyst=MarketEntryAnalyst(analyst), view_params=VIEW, risk_policy=POLICY,
        mandate=_mandate() if mandate is ... else mandate, policy_verifier=lambda m, p: True,
        market_rules=lambda s: RULES, initial_equity=D("1000"), slippage_bps=2, allowed_strategy_ids=("S25",),
        trace=trace, wall_ms=wall_ms)


def _rows(j):
    return j.list_run("brain", RUN)


def _snapshot_for(j, decision_id):
    return [r for r in _rows(j) if r.event.kind == SNAPSHOT_KIND
            and r.event.payload["decision_event_id"] == decision_id]


def _capture():
    return dt.capture_inputs({tf: _bars(tf) for tf in STEP}, VIEW.timeframes, now_ms=NOW)


class Clock:
    def __init__(self, start=NOW + 5_000):
        self.t, self.log = start, []

    def __call__(self):
        self.t += 1_000
        return self.t


# ------------------------------------------------------------------------------------------------ causalita'

def test_every_open_has_its_snapshot_after_the_decision_and_before_the_open():
    j = _journal()
    rep = _run(j, ScriptAnalyst())
    assert [s for s, _ in rep.opened] == ["AAAUSDT", "BBBUSDT"] and rep.errors == ()
    assert [t[1] for t in rep.traces] == ["recorded", "recorded"]
    for op in [r for r in _rows(j) if r.event.kind == "paper_open"]:
        did = op.event.payload["decision_event_id"]
        dec = j.get(did)
        snap, = _snapshot_for(j, did)
        assert dec.seq < snap.seq < op.seq                                 # ordine di scrittura causale
        p = snap.event.payload
        assert p["decision_event_hash"] == dec.event_hash and p["action"] == "OPEN" and p["status"] == "APPROVED"
        assert p["decision_ts_ms"] == p["snapshot_captured_at_ms"] == NOW   # riferimento e taglio dei dati
        assert p["feature_asof_ms"] <= NOW
        assert p["capture_phase"] == "pre_model" and p["feature_set"] == dt.FEATURE_SET
        assert len(p["inputs_digest"]) == 64 and set(p["inputs_window"]) == {"15m", "1h", "4h"}
        assert p["inputs_verified"] is False and p["eligible_for_training"] is False
        assert {"t15m_ret_1", "t1h_rsi14", "t4h_atr14_pct"} <= set(p["features"])
        assert "fset_version" not in p["features"]                         # metadati fuori dalle feature
        assert set(p["risk"]) == {"equity_usd", "margin_in_use_usd", "open_risk_usd", "available_margin_usd"}


def test_inputs_are_captured_before_the_model_is_called_and_written_after():
    clock = Clock()

    class Timed(ScriptAnalyst):
        def analyze(self, context, open_positions):
            clock.log.append(clock())
            return super().analyze(context, open_positions)

    j = _journal()
    _run(j, Timed(kind="NO_TRADE"), symbols=("AAAUSDT",), wall_ms=clock)
    p = _events(j, SNAPSHOT_KIND)[0].payload
    assert p["capture_wall_ms"] < clock.log[0] < p["write_wall_ms"]


def test_the_features_come_from_the_same_candles_the_model_received():
    j, holder = _journal(), CycleBars()
    _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",), holder=holder)
    p = _events(j, SNAPSHOT_KIND)[0].payload
    seen = dt.closed_windows(holder("AAAUSDT"), VIEW.timeframes, now_ms=NOW)
    assert p["inputs_digest"] == dt.inputs_digest(seen)
    assert p["inputs_window"] == {k: [v[0].open_time_ms, len(v)] for k, v in seen.items()}


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
    clean = dt.capture_inputs({tf: _bars(tf) for tf in STEP}, VIEW.timeframes, now_ms=NOW)
    leaked = dt.capture_inputs({tf: _with_open_bar(tf) for tf in STEP}, VIEW.timeframes, now_ms=NOW)
    assert leaked == clean and clean.asof_ms <= NOW


def test_the_cycle_does_not_decide_on_a_view_containing_an_open_bar():
    class FutureStore(FakeStore):
        def refresh(self, symbol, tf, now_ms):
            return _with_open_bar(tf)

    j = _journal()
    rep = _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",), store=FutureStore(NOW))
    assert rep.decisions == () and _events(j, SNAPSHOT_KIND) == [] and rep.errors


def test_feature_values_and_digest_are_recomputable_from_the_same_bars():
    cap = _capture()
    b = _bars("15m")
    assert cap.features["t15m_ret_1"] == (b[-1].close / b[-2].close - 1).quantize(D("1e-10"))
    assert cap.asof_ms == max(_bars(tf)[-1].open_time_ms + STEP[tf] for tf in STEP)
    # stesse candele scritte con zeri finali diversi: stesso digest
    padded = {tf: [Bar(x.open_time_ms, x.open, x.high, x.low, x.close + D("0.000000"), x.volume) for x in _bars(tf)]
              for tf in STEP}
    assert dt.capture_inputs(padded, VIEW.timeframes, now_ms=NOW).inputs_digest == cap.inputs_digest
    assert dt.capture_inputs({}, VIEW.timeframes, now_ms=NOW) == dt.Capture({}, None, None, {}, None)


# ------------------------------------------------------------------------------------------------ duplicati

def _portfolio(j):
    from backend.v3.dashboard import build_summary
    from backend.v3.runner.cycle import snapshot_from_summary
    return snapshot_from_summary(build_summary(j, "brain", RUN), D("1000"), POLICY.estimated_roundtrip_cost_bp)


def test_retracing_the_same_decision_does_not_duplicate():
    j = _journal()
    rep = _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",))
    did = rep.traces[0][2]
    again = dt.record_decision_trace(journal=j, run_id=RUN, symbol="AAAUSDT", now_ms=NOW, after_seq=0,
                                     expected_event_id=did, capture=_capture(), portfolio=_portfolio(j))
    assert again.ok and again.code == "already_recorded" and len(_snapshot_for(j, did)) == 1


def test_a_replayed_cycle_never_creates_a_second_snapshot_for_a_decision():
    j = _journal()
    _run(j, ScriptAnalyst(kind="NO_TRADE"))
    rep2 = _run(j, ScriptAnalyst(kind="NO_TRADE"))                        # stesso istante: stessa decisione
    ids = [e.payload["decision_event_id"] for e in _events(j, SNAPSHOT_KIND)]
    assert len(ids) == len(set(ids)) == len(_events(j, "brain_decision"))
    assert {c for _, c in rep2.errors} == {"decision_not_journaled"}


def test_two_decisions_for_the_same_symbol_and_instant_are_ambiguous_not_guessed():
    j = _journal()
    for i in (1, 2):
        j.append(Event(f"brain-req-x{i}", "brain", RUN, "brain_decision", NOW, "brain_f2_engine",
                       {"kind": "NO_TRADE", "status": "REJECTED", "rationale": "deepseek:analysis",
                        "sources": [], "claim": str(i), "symbol": "AAAUSDT", "regime": "RANGE"}))
    tr = dt.record_decision_trace(journal=j, run_id=RUN, symbol="AAAUSDT", now_ms=NOW, after_seq=0,
                                  expected_event_id=None, capture=_capture(), portfolio=None)
    assert (tr.ok, tr.code) == (False, "decision_ambiguous") and _events(j, SNAPSHOT_KIND) == []


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
    assert cov.decisions == 1 and cov.valid == 0 and len(cov.missing) == 1


def test_snapshot_refused_by_the_adapter_blocks_the_open(monkeypatch):
    def refused(**kw):
        raise ValueError("snapshot_after_open")
    monkeypatch.setattr(dt, "append_snapshot", refused)
    j = _journal()
    rep = _run(j, ScriptAnalyst(), symbols=("AAAUSDT",))
    assert rep.opened == ()
    assert rep.errors == (("AAAUSDT", "snapshot_snapshot_after_open"), ("AAAUSDT", "open_blocked_untraced"))


def test_a_failed_capture_blocks_the_open(monkeypatch):
    import backend.v3.runner.cycle as cyc

    def boom(*a, **k):
        raise ArithmeticError("x")
    monkeypatch.setattr(cyc, "capture_inputs", boom)
    j = _journal()
    rep = _run(j, ScriptAnalyst(), symbols=("AAAUSDT",))
    assert rep.opened == () and rep.errors == (("AAAUSDT", "capture_missing"), ("AAAUSDT", "open_blocked_untraced"))


def test_no_trade_trace_failure_is_reported_without_side_effects(monkeypatch):
    def broken(**kw):
        raise OSError("x")
    monkeypatch.setattr(dt, "append_snapshot", broken)
    j = _journal()
    rep = _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",))
    assert rep.errors == (("AAAUSDT", "snapshot_write_failed"),) and rep.opened == ()


def test_a_decision_the_engine_failed_to_journal_is_made_visible():
    class NoDecisions(EventJournal):
        def append(self, event):
            if event.kind == "brain_decision":
                raise OSError("locked")
            return super().append(event)

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


# ------------------------------------------------------------------------------------------------ ritardo

def _stamp_beyond_window(j, eid="exit-1", at=NOW + WRITE_GRACE_MS + 30_000):
    """Come il sidecar delle uscite: un evento con l'ora reale, oltre la finestra del giro."""
    j.append(Event(eid, "brain", RUN, "paper_close", at, "exit_service", {"position_id": "old"}))


def test_a_decision_written_after_the_window_is_recorded_but_not_counted_valid():
    j = _journal()
    _stamp_beyond_window(j)                         # il giro e' lungo: un'uscita reale e' gia' stata scritta
    rep = _run(j, ScriptAnalyst(), symbols=("AAAUSDT",))
    assert rep.traces[0][1] == "recorded_decision_written_late"
    assert len(rep.opened) == 1 and rep.errors == ()                # evidenza scritta: l'apertura non e' bloccata
    cov = dt.trace_coverage(j, RUN)
    assert cov.valid == 0 and cov.invalid[0][1] == "decision_written_late"
    assert cov.untraced_opens == (rep.opened[0][1],)                # e non viene presentata come tracciata


def test_a_snapshot_written_after_a_later_stamped_event_is_late():
    j = _journal()
    _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",), trace="off")
    _stamp_beyond_window(j)
    tr = dt.record_decision_trace(journal=j, run_id=RUN, symbol="AAAUSDT", now_ms=NOW, after_seq=0,
                                  expected_event_id=None, capture=_capture(), portfolio=None)
    assert tr.ok and tr.code == "recorded_snapshot_written_late"
    assert dt.trace_coverage(j, RUN).verdicts == {"snapshot_written_late": 1}


# ------------------------------------------------------------------------------------------------ copertura

def test_coverage_counts_only_valid_links():
    j = _journal()
    _run(j, ScriptAnalyst())
    cov = dt.trace_coverage(j, RUN)
    assert (cov.decisions, cov.valid, cov.chain_ok, cov.verdicts) == (2, 2, True, {"valid": 2})
    assert cov.ratio == 1 and cov.missing == cov.invalid == cov.untraced_opens == ()


def _raw_snapshot(j, decision, eid="raw-snap", **over):
    p = {"schema_version": 2, "decision_event_id": decision.event.event_id,
         "decision_event_hash": decision.event_hash, "decision_ts_ms": decision.event.occurred_at_ms,
         "snapshot_captured_at_ms": decision.event.occurred_at_ms, "feature_asof_ms": NOW - 1,
         "symbol": decision.event.payload["symbol"], "action": decision.event.payload["kind"],
         "status": decision.event.payload["status"], "features": {"x": "1"}, "risk": {},
         "inputs_verified": False, "eligible_for_training": False}
    p.update(over)
    return j.append(Event(eid, "brain", RUN, SNAPSHOT_KIND, decision.event.occurred_at_ms, "forged", p))


def _decided(j):
    _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",), trace="off")
    return [r for r in _rows(j) if r.event.kind == "brain_decision"][0]


@pytest.mark.parametrize("over, reason", [
    ({}, "valid"),
    ({"decision_event_hash": "0" * 64}, "snapshot_hash_mismatch"),
    ({"symbol": "ZZZUSDT"}, "snapshot_symbol_mismatch"),
    ({"action": "OPEN"}, "snapshot_decision_mismatch"),
    ({"decision_ts_ms": NOW - 1}, "snapshot_ts_mismatch"),
    ({"snapshot_captured_at_ms": NOW + 1}, "snapshot_time_order"),
    ({"feature_asof_ms": NOW + 1}, "snapshot_time_order"),
    ({"feature_asof_ms": None}, "snapshot_time_order"),
    ({"schema_version": 1}, "snapshot_schema"),
    ({"features": {"x": "1e5"}}, "snapshot_features_invalid"),
    ({"eligible_for_training": True}, "snapshot_self_attested"),
    ({"inputs_verified": True}, "snapshot_self_attested"),
])
def test_an_association_by_id_alone_is_not_a_valid_link(over, reason):
    j = _journal()
    dec = _decided(j)
    _raw_snapshot(j, dec, **over)
    cov = dt.trace_coverage(j, RUN)
    assert cov.verdicts == {reason: 1} and cov.valid == (1 if reason == "valid" else 0)


def test_a_snapshot_written_after_the_open_is_not_valid():
    j = _journal()
    dec = _decided(j)
    j.append(Event("open-x", "brain", RUN, "paper_open", NOW, "paper",
                   {"position_id": "px", "decision_event_id": dec.event.event_id}))
    _raw_snapshot(j, dec)
    cov = dt.trace_coverage(j, RUN)
    assert cov.verdicts == {"snapshot_after_open": 1} and cov.untraced_opens == ("px",)


def test_two_snapshots_for_one_decision_are_a_conflict():
    j = _journal()
    dec = _decided(j)
    _raw_snapshot(j, dec, "s1")
    _raw_snapshot(j, dec, "s2")
    assert dt.trace_coverage(j, RUN).verdicts == {"snapshot_conflict": 1}


def test_a_broken_hash_chain_means_no_link_is_trusted():
    j = _journal()
    _run(j, ScriptAnalyst())
    con = sqlite3.connect(j.filename)
    con.execute("DROP TRIGGER v3_no_update")
    con.execute("UPDATE v3_events SET source='tampered' WHERE seq=(SELECT MIN(seq) FROM v3_events)")
    con.commit()
    con.close()
    j2 = EventJournal(j.filename)
    cov = dt.trace_coverage(j2, RUN)
    assert cov.chain_ok is False and cov.valid == 0 and "valid" not in cov.verdicts
    assert dt.trace_coverage(j2, RUN, verify_chain=False).chain_ok is None


def test_opens_without_a_snapshot_are_listed_by_coverage():
    j = _journal()
    rep = _run(j, ScriptAnalyst(), trace="off")
    cov = dt.trace_coverage(j, RUN)
    assert cov.valid == 0 and set(cov.untraced_opens) == {pid for _, pid in rep.opened}


def _builder():
    sys.path.insert(0, str(TRAINING))
    try:
        import readers as R
        import snapshot_link as SL
    finally:
        sys.path.remove(str(TRAINING))
    return R, SL


# la copertura distingue il ritardo della decisione da quello dello snapshot; il builder li chiama entrambi "late"
_BUILDER_SAME = {"valid": "admitted", "decision_written_late": "snapshot_written_late"}


@pytest.mark.parametrize("scenario", ["clean", "late_decision", "late_snapshot", "hash", "after_open", "asof"])
def test_coverage_and_the_dataset_builder_give_the_same_verdict(scenario):
    R, SL = _builder()
    j = _journal()
    if scenario == "clean":
        _run(j, ScriptAnalyst())
    elif scenario == "late_decision":
        _stamp_beyond_window(j)
        _run(j, ScriptAnalyst())
    else:
        dec = _decided(j)
        if scenario == "late_snapshot":
            _stamp_beyond_window(j)
            _raw_snapshot(j, dec)
        elif scenario == "hash":
            _raw_snapshot(j, dec, decision_event_hash="1" * 64)
        elif scenario == "after_open":
            j.append(Event("open-x", "brain", RUN, "paper_open", NOW, "paper",
                           {"position_id": "px", "decision_event_id": dec.event.event_id}))
            _raw_snapshot(j, dec)
        else:
            _raw_snapshot(j, dec, feature_asof_ms=NOW + 1)
    data = R.read_v3(str(j.filename))
    opens = {}
    for o in data["opens"].values():
        opens.setdefault(o["p"].get("decision_event_id"), []).append(o["seq"])
    cov = dt.trace_coverage(j, RUN)
    mine = {d: "valid" for d in data["decisions"]}
    mine.update(dict(cov.invalid))
    assert data["decisions"]
    for did, dec in data["decisions"].items():
        adm = SL.admit(did, dec, data["snapshots"].get(did), opens.get(did, []), data["timeline"])
        got = adm.status if adm.status == "admitted" else adm.reason
        assert _BUILDER_SAME.get(mine[did], mine[did]) == got, (scenario, mine[did], got)


def test_the_dataset_builder_reads_cycle_snapshots_but_they_stay_unverified():
    R, SL = _builder()
    j = _journal()
    _run(j, ScriptAnalyst())
    _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("CCCUSDT",))
    data = R.read_v3(str(j.filename))
    assert len(data["decisions"]) == 3 and len(data["snapshots"]) == 3
    for snaps in data["snapshots"].values():
        assert all(s["p"]["eligible_for_training"] is False and s["p"]["inputs_verified"] is False for s in snaps)


# ------------------------------------------------------------------------------------------------ prestazioni

def test_tracing_adds_no_full_read_of_the_journal():
    class Counting(EventJournal):
        full = 0

        def list_run(self, portfolio_id, run_id):
            Counting.full += 1
            return super().list_run(portfolio_id, run_id)

    def reads(trace):
        Counting.full = 0
        j = Counting(os.path.join(tempfile.mkdtemp(), "journal.db"))
        j.init_schema()
        _run(j, ScriptAnalyst(), trace=trace)
        return Counting.full

    assert reads("required") == reads("off")


def test_the_adapter_and_the_engine_read_by_index_not_by_run():
    for module in ("backend/v3/decision_snapshot_v2.py", "backend/v3/runner/decision_trace.py",
                   "backend/v3/brain_f2/engine.py"):
        src = (ROOT / module).read_text()
        hot = src.split("def trace_coverage")[0]                    # la copertura e' un audit: legge tutto apposta
        assert "list_run(" not in hot, module


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


def test_the_wired_runner_requires_the_trace_with_a_wall_clock():
    src = (ROOT / "backend/v3/runner/wiring.py").read_text()
    assert 'trace="required"' in src and "wall_ms=" in src


def test_indexed_journal_reads():
    j = _journal()
    assert j.last_seq("brain", RUN) == 0 and j.get("nope") is None and j.list_run_after("brain", RUN, 0) == []
    _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",))
    rows = _rows(j)
    assert j.last_seq("brain", RUN) == rows[-1].seq and j.get(rows[0].event.event_id) == rows[0]
    assert j.list_run_after("brain", RUN, rows[0].seq) == rows[1:]
    assert j.first_seq_stamped_after("brain", RUN, NOW - 1, SNAPSHOT_KIND) == rows[0].seq   # lo snapshot non conta
    assert j.first_seq_stamped_after("brain", RUN, NOW, SNAPSHOT_KIND) is None
    for bad in (lambda: j.get(""), lambda: j.list_run_after("brain", RUN, -1), lambda: j.last_seq("x", RUN),
                lambda: j.first_seq_stamped_after("brain", RUN, "1", SNAPSHOT_KIND)):
        with pytest.raises(ValueError):
            bad()


@pytest.mark.parametrize("over, code", [
    ({"inputs_digest": "XYZ"}, "invalid_inputs_digest"),
    ({"capture_phase": "post_decision"}, "invalid_capture_phase"),
    ({"capture_wall_ms": 0}, "invalid_wall_clock"),
    ({"capture_wall_ms": NOW + 9, "write_wall_ms": NOW + 1}, "capture_after_write"),
    ({"feature_set": "bad set!"}, "invalid_feature_set"),
    ({"inputs_window": {"15m": (1, 0)}}, "invalid_inputs_window"),
    ({"inputs_window": {"week": (1, 2)}}, "invalid_inputs_window"),
])
def test_the_adapter_refuses_malformed_provenance(over, code):
    from backend.v3.decision_snapshot_v2 import DecisionSnapshotV2, append_snapshot
    j = _journal()
    dec = _decided(j)
    snap = DecisionSnapshotV2(decision_event_id=dec.event.event_id, decision_ts_ms=NOW, captured_at_ms=NOW, **over)
    with pytest.raises(ValueError, match="^" + code + "$"):
        append_snapshot(journal=j, run_id=RUN, snapshot=snap)
    assert _events(j, SNAPSHOT_KIND) == []


def test_the_engine_does_not_approve_a_decision_it_did_not_write():
    """Un journal che su id gia' usato restituisce l'evento esistente invece del conflitto: la lettura per id deve
    ancora riconoscere che la scrittura non e' la propria (claim diverso) e rifiutare l'apertura."""
    from backend.v3.events import EventConflict

    class Lenient(EventJournal):
        def append(self, event):
            try:
                return super().append(event)
            except EventConflict:
                return self.get(event.event_id)

    j = Lenient(os.path.join(tempfile.mkdtemp(), "journal.db"))
    j.init_schema()
    first = _run(j, ScriptAnalyst(), symbols=("AAAUSDT",), trace="off")
    assert len(first.opened) == 1
    # stesso istante e stessa proposta, nuova istanza: stesso id di richiesta, claim diverso
    j2 = Lenient(j.filename)
    from backend.v3.brain_f2.contracts import MarketContext
    from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot
    from backend.v3.runner.cycle import NoReviewer
    eng = BrainEngine(analyst=MarketEntryAnalyst(ScriptAnalyst()), reviewer=NoReviewer(), risk_policy=POLICY,
                      portfolio_snapshot=BrainPortfolioSnapshot(D("1000"), D("1000"), D("0"), D("0")),
                      market_params={**RULES, "market_data_fresh": True, "paused": False, "daily_loss_latched": False},
                      journal=j2, portfolio_id="brain", run_id=RUN, policy_mandate=_mandate(),
                      policy_verifier=lambda m, p: True, allowed_strategy_ids=("S25",))
    from backend.v3.runner.cycle import price_with_room
    d = eng.step(MarketContext("AAAUSDT", price_with_room(_bars("15m")[-1].close), NOW, "TREND"), 0.0)
    assert d.journal_event_id is None and d.rationale == "journal_persist_failed"
