"""Archive proof tests: none of these fixtures are live or archived user data."""
import json

from v3.legacy_archives import audit_classic_archives


def _rec(ident, stamp, net):
    return {"id": ident, "symbol": "BTC/USDT:USDT", "side": -1,
            "open_ms": stamp - 60000, "close_ms": stamp, "net": net,
            "fees": 0.2, "why": "time"}


def _snapshot(tmp_path):
    root = tmp_path / "hawk"
    root.mkdir()
    older = _rec(1, 1793600000000, -4.5)
    current = _rec(2, 1793630000000, 7.25)
    (root / "state_v2.json").write_text(json.dumps({
        "run_no": 8, "main": {"closed": [current], "positions": {}}
    }))
    (root / "trade_history.jsonl").write_text(
        json.dumps(older) + "\n" + json.dumps(current) + "\n"
    )
    (root / "learning_log.jsonl").write_text(
        json.dumps({"ev": "close", "run_no": 7, "portfolio": "hawk", **older}) + "\n" +
        json.dumps({"ev": "close", "run_no": 8, "portfolio": "hawk", **current}) + "\n"
    )
    return root, older


def _archive(root, old):
    a = root / "archive" / "one-run"
    a.mkdir(parents=True)
    (a / "state_v2.json").write_text(json.dumps({
        "run_no": 7, "main": {"closed": [old], "positions": {}}
    }))
    (a / "trade_history.jsonl").write_text(json.dumps(old) + "\n")
    (a / "summary.json").write_text(json.dumps({
        "run_no": 7, "portfolio": "hawk",
        "start_equity": 1000, "end_equity": 995.5,
        "pnl": -4.5, "net_total": -4.5, "trades": 1,
    }))
    return a


def test_archive_matches_historic_closed_and_cash(tmp_path):
    root, old = _snapshot(tmp_path)
    _archive(root, old)
    report = audit_classic_archives(root, "hawk")
    assert report.eligible, report.issues
    assert report.expected_runs == report.verified_runs == (7,)


def test_archive_missing_is_not_silent_success(tmp_path):
    root, old = _snapshot(tmp_path)
    report = audit_classic_archives(root, "hawk")
    assert not report.eligible
    assert "ARCHIVE_DIRECTORY_MISSING" in report.issues


def test_archive_bad_cash_cannot_pass(tmp_path):
    root, old = _snapshot(tmp_path)
    folder = _archive(root, old)
    summary_path = folder / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["end_equity"] += 20
    summary_path.write_text(json.dumps(summary))
    report = audit_classic_archives(root, "hawk")
    assert not report.eligible
    assert any(x.startswith("ARCHIVE_SUMMARY_MISMATCH") for x in report.issues)


def test_archive_with_ghost_double_final_is_blocked(tmp_path):
    root, old = _snapshot(tmp_path)
    _archive(root, old)
    extra = dict(old, close_ms=old["close_ms"] + 1000, net=-3)
    with (root / "trade_history.jsonl").open("a") as out:
        out.write(json.dumps(extra) + "\n")
    with (root / "learning_log.jsonl").open("a") as out:
        out.write(json.dumps({"ev": "close", "run_no": 7, "portfolio": "hawk", **extra}) + "\n")
    report = audit_classic_archives(root, "hawk")
    assert not report.eligible
    assert "DUPLICATE_FINAL_CLOSE" in report.issues
