"""Cumulative legacy history reconciliation; all synthetic PAPER fixtures."""
import json
from pathlib import Path

from v3.legacy_multirun import (
    audit_classic_multirun, plan_classic_multirun_events,
)


def record(ident, when, net):
    return {
        "id": ident, "symbol": "ADA/USDT:USDT", "side": -1,
        "close_ms": when, "open_ms": when - 10000,
        "net": net, "margin": 100, "leverage": 20,
        "entry": 1.0, "exit": 0.9, "fees": 1.0, "funding": 0.0,
        "why": "stop loss", "reason": "some long explanation",
    }


def setup(tmp_path, *, omit_old_log=False, duplicate=False):
    root = tmp_path / "hawk"
    root.mkdir()
    old = record(1, 1793610000000, -4.5)
    now = record(2, 1793630000000, 7.25)
    (root / "state_v2.json").write_text(json.dumps({
        "run_no": 8, "main": {"closed": [now], "positions": {"BTC": {"id": 3}}}
    }))
    history = [old, now]
    if duplicate:
        history.append(old)
    (root / "trade_history.jsonl").write_text("".join(json.dumps(x) + "\n" for x in history))
    learning = (
        [] if omit_old_log else [{"ev": "close", "run_no": 7, "portfolio": "hawk",
                                  **old}]
    ) + [{"ev": "close", "run_no": 8, "portfolio": "hawk", **now}]
    (root / "learning_log.jsonl").write_text("".join(json.dumps(x) + "\n" for x in learning))
    return root


def test_cumulative_jsonl_maps_older_and_current_run(tmp_path):
    root = setup(tmp_path)
    before = {x.name: x.read_bytes() for x in root.iterdir()}
    report, events = plan_classic_multirun_events(root, "hawk")
    assert report.eligible
    assert report.current_run == 8
    assert report.history_closes == report.learning_closes == 2
    assert report.state_current_closes == report.current_history_closes == 1
    assert report.current_net_matches
    assert report.runs == ((7, 1, "-4.5"), (8, 1, "7.25"))
    assert [ev.run_id for ev in events] == ["legacy-hawk-7", "legacy-hawk-8"]
    assert [ev.payload["history_row"] for ev in events] == [1, 2]
    assert before == {x.name: x.read_bytes() for x in root.iterdir()}


def test_prevents_history_without_learning_provenance(tmp_path):
    root = setup(tmp_path, omit_old_log=True)
    report, events = plan_classic_multirun_events(root, "hawk")
    assert not report.eligible
    assert "UNMATCHED_OR_AMBIGUOUS_LEARNING_CLOSE" in report.issues
    assert not events


def test_duplicate_history_row_blocks_entire_plan(tmp_path):
    root = setup(tmp_path, duplicate=True)
    report, events = plan_classic_multirun_events(root, "hawk")
    assert not report.eligible
    assert "DUPLICATE_HISTORY_ROW" in report.issues
    assert not events


def test_current_state_disagreement_blocks_plan(tmp_path):
    root = setup(tmp_path)
    state = json.loads((root / "state_v2.json").read_text())
    state["main"]["closed"][0]["net"] = 4
    (root / "state_v2.json").write_text(json.dumps(state))
    report = audit_classic_multirun(root, "hawk")
    assert not report.eligible
    assert "CURRENT_RUN_STATE_HISTORY_MISMATCH" in report.issues
    assert not report.current_net_matches


def test_nonmatching_field_other_than_identity_is_rejected(tmp_path):
    root = setup(tmp_path)
    lines = (root / "learning_log.jsonl").read_text().splitlines()
    payload = json.loads(lines[0])
    payload["reason"] = "truncated by logger"  # expected / historically valid
    payload["why"] = "something other than history"  # NOT valid
    lines[0] = json.dumps(payload)
    (root / "learning_log.jsonl").write_text("\n".join(lines) + "\n")
    report, events = plan_classic_multirun_events(root, "hawk")
    assert "LEARNING_FIELD_MISMATCH" in report.issues
    assert events == ()


def test_truncated_reason_is_not_mismatch(tmp_path):
    root = setup(tmp_path)
    rows = (root / "learning_log.jsonl").read_text().splitlines()
    row = json.loads(rows[0])
    row["reason"] = "short"
    rows[0] = json.dumps(row)
    (root / "learning_log.jsonl").write_text("\n".join(rows) + "\n")
    report = audit_classic_multirun(root, "hawk")
    assert report.eligible
