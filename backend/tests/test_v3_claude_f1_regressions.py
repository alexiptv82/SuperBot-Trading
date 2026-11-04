"""Adversarial regressions from Claude F1 independent review; synthetic only."""
import json
import sqlite3

import pytest

from v3.legacy_audit import open_frozen_sqlite, audit_brain_snapshot, plan_classic_closed_events
from v3.legacy_accounting import audit_brain_structure
from v3.legacy_brain_books import audit_brain_books
from v3.legacy_multirun import audit_classic_multirun, plan_classic_multirun_events
from v3.risk import RiskPolicy, RiskRequest, quote_paper_risk
from decimal import Decimal as D


def _record(i, stamp, net, partial=False):
    return {
        "id": i, "symbol": "ADA/USDT:USDT", "side": -1,
        "open_ms": stamp - 60000, "close_ms": stamp,
        "net": net, "partial": partial, "margin": 100,
        "entry": 1.0, "exit": 0.9, "fees": 1,
        "funding": 0, "leverage": 20, "why": "time",
    }


def _classic(tmp_path, history, runs, current, portfolio="hawk", current_run=8):
    folder = tmp_path / "classic"
    folder.mkdir()
    (folder / "state_v2.json").write_text(json.dumps({
        "run_no": current_run, "main": {"closed": current, "positions": {}}
    }))
    (folder / "trade_history.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in history)
    )
    (folder / "learning_log.jsonl").write_text(
        "".join(json.dumps({"ev": "close", "run_no": run,
                            "portfolio": portfolio, **row}) + "\n"
                for run, row in zip(runs, history))
    )
    return folder


def test_p0_1_all_brain_audits_refuse_nonempty_wal(tmp_path):
    dbpath = tmp_path / "brain.sqlite3"
    db = sqlite3.connect(dbpath)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
        db.execute("CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)")
        db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,id TEXT,kind TEXT,ts INTEGER,body TEXT)")
        db.execute("INSERT INTO state VALUES(1,?)", (json.dumps({
            "mode": "paper", "account_id": "brain-free-paper",
            "cash": 2000, "positions": {},
        }),))
        db.execute("INSERT INTO events VALUES(1,'a','trade_closed',1,'{}')")
        db.commit()
        wal = tmp_path / "brain.sqlite3-wal"
        assert wal.is_file() and wal.stat().st_size > 0
        for audit in (open_frozen_sqlite, audit_brain_snapshot,
                      audit_brain_structure, audit_brain_books):
            with pytest.raises(ValueError, match="sqlite_sidecar_present"):
                audit(dbpath)
    finally:
        db.close()


def test_p0_2_deprecated_planner_must_not_return_second_event_id(tmp_path):
    row = _record(1, 1793630000000, 7.25)
    folder = _classic(tmp_path, [row], [8], [row])
    with pytest.raises(NotImplementedError, match="superseded"):
        plan_classic_closed_events(folder, "hawk")
    report, events = plan_classic_multirun_events(folder, "hawk")
    assert report.eligible and len(events) == 1


def test_p0_3_duplicate_final_close_in_old_run_rejected(tmp_path):
    first = _record(4, 1793601000000, -9)
    ghost = _record(4, 1793602000000, -3)
    current = _record(1, 1793630000000, 7)
    folder = _classic(tmp_path, [first, ghost, current], [7, 7, 8], [current])
    report, staged = plan_classic_multirun_events(folder, "hawk")
    assert not report.eligible
    assert "DUPLICATE_FINAL_CLOSE" in report.issues
    assert staged == ()


def test_p0_3_orphan_old_partial_rejected(tmp_path):
    earlier = _record(4, 1793601000000, 2, partial=True)
    current = _record(1, 1793630000000, 7)
    folder = _classic(tmp_path, [earlier, current], [7, 8], [current])
    report = audit_classic_multirun(folder, "hawk")
    assert not report.eligible
    assert "PARTIAL_WITHOUT_FINAL_IN_CLOSED_RUN" in report.issues


def test_p1_3_wrong_portfolio_learning_row_rejected(tmp_path):
    row = _record(1, 1793630000000, 7)
    folder = _classic(tmp_path, [row], [8], [row], portfolio="bull")
    report = audit_classic_multirun(folder, "hawk")
    assert not report.eligible
    assert "LEARNING_PORTFOLIO_MISMATCH" in report.issues


def test_content_derived_event_id_stable_to_history_reorder(tmp_path):
    first = _record(4, 1793601000000, -9)
    current = _record(1, 1793630000000, 7)
    folder = _classic(tmp_path, [first, current], [7, 8], [current])
    first_ids = {e.event_id for e in plan_classic_multirun_events(folder, "hawk")[1]}
    assert len(first_ids) == 2
    (folder / "trade_history.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in [current, first])
    )
    second_ids = {e.event_id for e in plan_classic_multirun_events(folder, "hawk")[1]}
    assert second_ids == first_ids


def test_p1_9_equity_floor_accounts_for_existing_risk():
    policy = RiskPolicy(D("0.015"), D("0.06"), D("0.25"), D("0.70"),
                        D("450"), D("16"), D("0.5"))
    req = RiskRequest(
        equity=D(470), available_cash=D(470), margin_used=D(0),
        existing_open_risk=D(15), entry_price=D(100), stop_price=D(99),
        side=1, requested_leverage=10, exchange_leverage_limit=20,
        quantity_step=D("0.001"), minimum_notional=D(5),
        maintenance_fraction=D("0.005"), market_data_fresh=True,
        paused=False, daily_loss_latched=False,
    )
    quote = quote_paper_risk(policy, req)
    assert quote.allowed
    assert quote.worst_case_loss_estimate <= D(5)
    assert req.equity - req.existing_open_risk - quote.worst_case_loss_estimate >= D(450)
