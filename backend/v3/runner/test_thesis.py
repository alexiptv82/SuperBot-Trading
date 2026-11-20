"""Tesi persistenti (thesis_id) e anti-reingresso nel ciclo reale, ricostruiti dal solo journal e in modo causale.

Produttori veri (motore, journal, execute_paper, snapshot); finti solo candele e modello. Il confronto con lo strumento
E0 garantisce che runner e misura sugli storici usino la stessa definizione di reingresso.
"""
from __future__ import annotations

import os
import random
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tests.test_v3_runner_cycle import NOW, RUN, _events, _journal
from backend.v3.decision_snapshot_v2 import SNAPSHOT_KIND, DecisionSnapshotV2, append_snapshot
from backend.v3.events import Event, EventJournal
from backend.v3.runner.test_decision_trace import ScriptAnalyst, _run
from backend.v3.runner.thesis import (
    HOUR_MS, ReentryPolicy, ThesisBook, evaluate, thesis_id_for,
)

D = Decimal
ROOT = Path(__file__).resolve().parents[3]
OBSERVE = ReentryPolicy()


def _cycle(j, at, *, side=1, policy=OBSERVE, symbols=("AAAUSDT",)):
    analyst = ScriptAnalyst(side=side, stop_factor=D("0.99") if side == 1 else D("1.01"))
    from backend.v3.runner.cycle import CycleBars, MarketEntryAnalyst, run_brain_cycle
    from backend.tests.test_v3_runner_cycle import FakeStore, POLICY, RULES, VIEW, _mandate
    return run_brain_cycle(
        now_ms=at, journal=j, run_id=RUN, symbols=symbols, store=FakeStore(at), bars_holder=CycleBars(),
        analyst=MarketEntryAnalyst(analyst), view_params=VIEW, risk_policy=POLICY, mandate=_mandate(),
        policy_verifier=lambda m, p: True, market_rules=lambda s: RULES, initial_equity=D("1000"), slippage_bps=2,
        allowed_strategy_ids=("S25",), trace="required", reentry_policy=policy)


def _close(j, pid, at, pnl, symbol="AAAUSDT"):
    j.append(Event(f"close-{pid}", "brain", RUN, "paper_close", at, "exit_service",
                   {"position_id": pid, "symbol": symbol, "realized_pnl": str(pnl)}))


def _thesis_of(j, position_id):
    op = [e for e in _events(j, "paper_open") if e.payload["position_id"] == position_id][0]
    snap = [e for e in _events(j, SNAPSHOT_KIND) if e.payload["decision_event_id"] == op.payload["decision_event_id"]]
    return snap[0].payload["thesis"], snap[0].payload["anti_reentry"]


def _chain(j, n, *, gap=HOUR_MS, pnl=-1, policy=OBSERVE, side=1):
    """n ingressi successivi sullo stesso simbolo e lato, ognuno chiuso prima del successivo."""
    reports = []
    for i in range(n):
        at = NOW + i * gap
        rep = _cycle(j, at, policy=policy, side=side)
        reports.append(rep)
        for _, pid in rep.opened:
            _close(j, pid, at + gap // 2, pnl)
    return reports


# ------------------------------------------------------------------------------------------------ tesi

def test_the_first_entry_starts_a_thesis_named_by_its_decision():
    j = _journal()
    rep = _cycle(j, NOW)
    (sym, pid), = rep.opened
    thesis, reentry = _thesis_of(j, pid)
    did = _events(j, "paper_open")[0].payload["decision_event_id"]
    assert thesis == {"thesis_id": thesis_id_for(RUN, "AAAUSDT", 1, did), "reentry_index": 1,
                      "prev_outcome": "none", "truncated": False}
    assert reentry["would_block"] is False and reentry["mode"] == "observe"
    assert rep.theses == (("AAAUSDT", thesis["thesis_id"], 1, ""),)


def test_reentries_on_the_same_symbol_and_side_continue_the_thesis():
    j = _journal()
    reps = _chain(j, 3)
    ths = [_thesis_of(j, r.opened[0][1])[0] for r in reps]
    assert len({t["thesis_id"] for t in ths}) == 1
    assert [t["reentry_index"] for t in ths] == [1, 2, 3]
    assert [t["prev_outcome"] for t in ths] == ["none", "loss", "loss"]


def test_a_gap_beyond_the_window_starts_a_new_thesis():
    j = _journal()
    reps = _chain(j, 2, gap=13 * HOUR_MS)
    a, b = (_thesis_of(j, r.opened[0][1])[0] for r in reps)
    assert a["thesis_id"] != b["thesis_id"] and b["reentry_index"] == 1


def test_an_opposite_entry_in_between_breaks_the_thesis():
    j = _journal()
    r1 = _cycle(j, NOW)
    _close(j, r1.opened[0][1], NOW + 10 * 60_000, -1)
    r2 = _cycle(j, NOW + HOUR_MS, side=-1)
    _close(j, r2.opened[0][1], NOW + HOUR_MS + 10 * 60_000, 1)
    r3 = _cycle(j, NOW + 2 * HOUR_MS)
    t1, t2, t3 = (_thesis_of(j, r.opened[0][1])[0] for r in (r1, r2, r3))
    assert t3["thesis_id"] not in (t1["thesis_id"], t2["thesis_id"]) and t3["reentry_index"] == 1
    assert t2["reentry_index"] == 1                               # il lato opposto e' un'altra tesi


def test_other_symbols_are_independent():
    j = _journal()
    rep = _cycle(j, NOW, symbols=("AAAUSDT", "BBBUSDT"))
    ids = [t[1] for t in rep.theses]
    assert len(set(ids)) == 2 and [t[2] for t in rep.theses] == [1, 1]


# ------------------------------------------------------------------------------------------------ anti-reingresso

def test_observe_mode_records_what_it_would_block_but_opens():
    j = _journal()
    reps = _chain(j, 3)
    assert all(len(r.opened) == 1 for r in reps)
    _, third = _thesis_of(j, reps[2].opened[0][1])
    assert third["would_block"] is True and third["rule"] == "reentry_limit"
    assert reps[2].theses[0][3] == "reentry_limit" and reps[2].errors == ()


def test_enforce_mode_blocks_the_open_and_still_records_the_evidence():
    j = _journal()
    reps = _chain(j, 3, policy=ReentryPolicy(mode="enforce"))
    assert [len(r.opened) for r in reps] == [1, 1, 0]
    assert reps[2].errors == (("AAAUSDT", "anti_reentry_blocked"),)
    dec = [e for e in _events(j, "brain_decision")][-1]
    snap = [e for e in _events(j, SNAPSHOT_KIND) if e.payload["decision_event_id"] == dec.event_id][0]
    assert snap.payload["anti_reentry"]["would_block"] is True and snap.payload["thesis"]["reentry_index"] == 3


def test_loss_cooldown_rule():
    policy = ReentryPolicy(mode="enforce", max_reentry_index=100, loss_cooldown_ms=2 * HOUR_MS)
    j = _journal()
    reps = _chain(j, 2, policy=policy)                    # chiusura in perdita 30 min prima del reingresso
    assert len(reps[1].opened) == 0 and reps[1].errors == (("AAAUSDT", "anti_reentry_blocked"),)
    j2 = _journal()
    reps2 = _chain(j2, 2, policy=policy, pnl=1)           # chiusura in utile: nessun blocco
    assert len(reps2[1].opened) == 1


def test_loss_cooldown_expires():
    policy = ReentryPolicy(mode="enforce", max_reentry_index=100, loss_cooldown_ms=2 * HOUR_MS)
    j = _journal()
    reps = _chain(j, 2, policy=policy, gap=8 * HOUR_MS)     # perdita chiusa 4 h prima: attesa di 2 h gia' trascorsa
    assert len(reps[1].opened) == 1
    assert _thesis_of(j, reps[1].opened[0][1])[0]["prev_outcome"] == "loss"


def test_an_open_recorded_after_the_evaluation_instant_is_not_known():
    j = _journal()
    d = j.append(Event("brain-req-a", "brain", RUN, "brain_decision", NOW - HOUR_MS, "brain_f2_engine",
                       {"kind": "OPEN", "status": "APPROVED", "symbol": "AAAUSDT"}))
    j.append(Event("open-a", "brain", RUN, "paper_open", NOW + HOUR_MS, "paper",
                   {"position_id": "pa", "symbol": "AAAUSDT", "side": 1, "decision_event_id": d.event.event_id}))
    book = ThesisBook.from_journal(j, RUN, now_ms=NOW, window_ms=12 * HOUR_MS)
    assert book.assess("AAAUSDT", 1, NOW, "d2").reentry_index == 1


def test_off_and_none_change_nothing():
    for policy in (None, ReentryPolicy(mode="off")):
        j = _journal()
        reps = _chain(j, 3, policy=policy)
        assert all(len(r.opened) == 1 and r.theses == () for r in reps)
        assert all(e.payload["thesis"] is None for e in _events(j, SNAPSHOT_KIND))


# ------------------------------------------------------------------------------------------------ causalita'

def _book(entries, closes=None, since=NOW - 30 * 24 * HOUR_MS):
    return ThesisBook(RUN, 12 * HOUR_MS, since, entries, closes)


def test_nothing_after_the_decision_instant_is_used():
    from backend.v3.runner.thesis import Entry
    e1 = Entry("p1", "AAAUSDT", 1, NOW, "d1")
    future = Entry("p9", "AAAUSDT", 1, NOW + 2 * HOUR_MS, "d9")
    book = _book([e1, future], {"p1": (NOW + 3 * HOUR_MS, "loss")})
    info = book.assess("AAAUSDT", 1, NOW + HOUR_MS, "d2")
    assert info.reentry_index == 2 and info.prev_outcome == "none"     # chiusura e ingresso futuri ignorati


def test_wall_clock_open_time_does_not_change_the_chain():
    """In sidecar paper_open porta l'ora reale: la catena usa l'istante della decisione."""
    j = _journal()
    d = j.append(Event("brain-req-a", "brain", RUN, "brain_decision", NOW, "brain_f2_engine",
                       {"kind": "OPEN", "status": "APPROVED", "symbol": "AAAUSDT"}))
    j.append(Event("open-a", "brain", RUN, "paper_open", NOW + 11 * HOUR_MS, "paper",   # 11 h dopo (assurdo, ma prova)
                   {"position_id": "pa", "symbol": "AAAUSDT", "side": 1, "decision_event_id": d.event.event_id}))
    book = ThesisBook.from_journal(j, RUN, now_ms=NOW + 13 * HOUR_MS, window_ms=12 * HOUR_MS)
    assert book.assess("AAAUSDT", 1, NOW + 13 * HOUR_MS, "d2").reentry_index == 1   # 13 h dalla decisione


def test_a_chain_reaching_the_lookback_edge_is_marked_truncated():
    from backend.v3.runner.thesis import Entry
    since = NOW
    book = _book([Entry("p1", "AAAUSDT", 1, NOW + HOUR_MS, "d1")], since=since)
    assert book.assess("AAAUSDT", 1, NOW + 2 * HOUR_MS, "d2").truncated is True
    far = _book([Entry("p1", "AAAUSDT", 1, NOW + 20 * HOUR_MS, "d1")], since=since)
    assert far.assess("AAAUSDT", 1, NOW + 21 * HOUR_MS, "d2").truncated is False


def test_the_thesis_reads_no_full_run():
    class Counting(EventJournal):
        full = 0

        def list_run(self, portfolio_id, run_id):
            Counting.full += 1
            return super().list_run(portfolio_id, run_id)

    def reads(policy):
        Counting.full = 0
        j = Counting(os.path.join(tempfile.mkdtemp(), "journal.db"))
        j.init_schema()
        _cycle(j, NOW, policy=policy)
        return Counting.full

    assert reads(OBSERVE) == reads(None)


# ------------------------------------------------------------------------------------------------ coerenza con E0

def test_reentry_indices_match_the_e0_measurement_tool():
    sys.path.insert(0, str(ROOT / "ops" / "brain-unico" / "guardian"))
    try:
        import e0_measure as E0
    finally:
        sys.path.pop(0)
    from backend.v3.runner.thesis import Entry
    rng = random.Random(7)
    t, entries, trades = NOW, [], []
    for i in range(80):
        t += rng.choice([1, 2, 5, 11, 13, 30]) * HOUR_MS // 2
        sym, side = rng.choice(["AAAUSDT", "BBBUSDT"]), rng.choice([1, -1])
        entries.append(Entry(f"p{i}", sym, side, t, f"d{i}"))
        trades.append({"stream": "s", "symbol": sym, "side": side, "opened": t, "closed": t + 60_000, "r": 0.0})
    E0.annotate(trades, "UTC", 0, 12)
    book = _book([], since=NOW - 30 * 24 * HOUR_MS)
    for e, tr in zip(entries, trades):
        assert book.assess(e.symbol, e.side, e.opened_ms, e.decision_event_id).reentry_index == tr["reentry"]
        book.add_open(e.position_id, e.symbol, e.side, e.opened_ms, e.decision_event_id)


# ------------------------------------------------------------------------------------------------ validazione

def test_policy_and_cycle_arguments_are_validated():
    for bad in (dict(mode="on"), dict(window_ms=0), dict(max_reentry_index=0), dict(loss_cooldown_ms=-1)):
        with pytest.raises(ValueError):
            ReentryPolicy(**bad)
    from backend.v3.runner.cycle import run_brain_cycle
    args = dict(now_ms=NOW, journal=_journal(), run_id=RUN, symbols=(), store=None, bars_holder=None, analyst=None,
                view_params=None, risk_policy=None, mandate=None, policy_verifier=None, market_rules=None,
                initial_equity=D("1"), slippage_bps=0)
    with pytest.raises(ValueError, match="reentry_requires_trace"):
        run_brain_cycle(**args, reentry_policy=OBSERVE)
    with pytest.raises(ValueError, match="invalid_reentry_policy"):
        run_brain_cycle(**args, trace="required", reentry_policy="observe")


def test_the_adapter_refuses_a_thesis_on_a_no_trade_or_malformed():
    j = _journal()
    _run(j, ScriptAnalyst(kind="NO_TRADE"), symbols=("AAAUSDT",), trace="off")
    dec = _events(j, "brain_decision")[0]
    good = {"thesis_id": "th-" + "a" * 24, "reentry_index": 1, "prev_outcome": "none", "truncated": False}
    with pytest.raises(ValueError, match="^thesis_without_open$"):
        append_snapshot(journal=j, run_id=RUN, snapshot=DecisionSnapshotV2(dec.event_id, NOW, NOW, thesis=good))
    for bad in ({**good, "reentry_index": 0}, {**good, "thesis_id": "x"}, {**good, "extra": 1}):
        with pytest.raises(ValueError, match="^invalid_thesis$"):
            append_snapshot(journal=j, run_id=RUN, snapshot=DecisionSnapshotV2(dec.event_id, NOW, NOW, thesis=bad))
    with pytest.raises(ValueError, match="^invalid_thesis$"):                 # verdetto senza tesi
        append_snapshot(journal=j, run_id=RUN, snapshot=DecisionSnapshotV2(
            dec.event_id, NOW, NOW, anti_reentry={"mode": "observe"}))


def test_the_wired_runner_observes_reentries():
    src = (ROOT / "backend/v3/runner/wiring.py").read_text()
    assert 'reentry_policy=ReentryPolicy(mode="observe")' in src
