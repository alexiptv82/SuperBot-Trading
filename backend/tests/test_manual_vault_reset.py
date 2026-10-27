"""Regression: manual PAPER reset clears vault only after explicit confirmation; brain files survive."""
import json
from copy import deepcopy
from pathlib import Path
from decimal import Decimal

from desk.engine import PaperAccount
from desk.vault_manager import VaultState, PendingLot


def test_nonempty_vault_reset_archive_and_brain_survive(tmp_path, monkeypatch):
    from desk import cli
    monkeypatch.setattr(cli, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "STATE_FILE", str(tmp_path / "state_v2.json"))
    monkeypatch.setattr(cli, "_CAPITAL_JOURNAL_INSTANCE", None)
    monkeypatch.setattr(cli, "_capital_enabled", lambda: True)
    monkeypatch.setattr(cli, "LIVE", type("Paper", (), {"_live": False})())
    account = PaperAccount(cli.PORTFOLIO.limits, "main").to_dict()
    account["cash"] = 1000.0
    vault = VaultState(balance=Decimal("75.25"),
                       pending=(PendingLot("pending:old", "2026-10-26", Decimal("12.50")),))
    state = {
        "main": account, "run_no": 3, "budget": {"spent": .21},
        "capital": {
            "schema_version": 1, "policy": "salvadanaio-only-v1", "status": "READY",
            "revision": 0, "vault": vault.to_dict(),
            "day": {"utc_day": "2026-10-27"}, "deposits": [
                {"kind": "rollover", "amount": "75.25"}],
            "valuation": {"fresh": False, "unrealized": "0"}
        }
    }
    for filename, body in (
        ("trade_history.jsonl", b'{"symbol":"OLD","net":25}\n'),
        ("learning_log.jsonl", b'{"symbol":"OLD","lesson":"important"}\n'),
        ("lessons.md", b"persistent lesson\n"),
        ("errors.md", b"persistent errors\n")
    ):
        (tmp_path / filename).write_bytes(body)
    brain_before = {p: (tmp_path / p).read_bytes() for p in
                    ("trade_history.jsonl", "learning_log.jsonl", "lessons.md", "errors.md")}
    Path(cli.STATE_FILE).write_text(json.dumps(state))
    (tmp_path / "pause.flag").write_text("1")
    # Start ledger baseline before requesting any reset.
    cli.save_state(state, cli.STATE_FILE)
    # No explicit confirmation must be rejected with no balance mutation.
    (tmp_path / "reset_portfolio.flag").write_text(json.dumps({"reset_vault": False}))
    assert cli._check_portfolio_reset_flag(state) is False
    assert state["capital"]["vault"]["balance"] == "75.25"
    assert state["run_no"] == 3
    # Explicit user-confirmed reset.
    (tmp_path / "reset_portfolio.flag").write_text(json.dumps({"reset_vault": True}))
    assert cli._check_portfolio_reset_flag(state) is True
    recovered = cli.load_state(cli.STATE_FILE)
    assert recovered["run_no"] == 4
    assert recovered["main"]["positions"] == {}
    assert recovered["main"]["cash"] == cli.PORTFOLIO.limits.start_equity
    assert recovered["capital"]["vault"]["balance"] == "0"
    assert recovered["capital"]["vault"]["pending"] == []
    assert recovered["capital"]["deposits"] == []
    assert (tmp_path / "pause.flag").exists()
    for p, before in brain_before.items():
        assert (tmp_path / p).read_bytes() == before
    archive = tmp_path / "archive" / recovered["last_action"]["archive"]
    archived = json.loads((archive / "state_v2.json").read_text())
    assert archived["capital"]["vault"]["balance"] == "75.25"
    assert archived["capital"]["vault"]["pending"][0]["remaining"] == "12.50"
    assert (tmp_path / "salvadanaio-journal.jsonl").exists()
    # Re-running without a new explicit command must be idempotent.
    assert cli._check_portfolio_reset_flag(recovered) is False
    assert cli.load_state(cli.STATE_FILE)["run_no"] == 4


def test_manual_reset_rejects_unreconciled_vault(tmp_path, monkeypatch):
    from desk import cli
    monkeypatch.setattr(cli, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "STATE_FILE", str(tmp_path / "state_v2.json"))
    monkeypatch.setattr(cli, "_CAPITAL_JOURNAL_INSTANCE", None)
    monkeypatch.setattr(cli, "_capital_enabled", lambda: True)
    acc = PaperAccount(cli.PORTFOLIO.limits, "main").to_dict()
    st = {"main": acc, "run_no": 1, "capital": {
        "schema_version": 1, "policy": "salvadanaio-only-v1",
        "status": "ROLLOVER_PENDING", "revision": 0,
        "vault": VaultState(balance=Decimal("15")).to_dict(),
        "day": {"utc_day": "2026-10-27"}, "deposits": []}}
    Path(cli.STATE_FILE).write_text(json.dumps(st))
    (tmp_path / "pause.flag").write_text("1")
    (tmp_path / "reset_portfolio.flag").write_text('{"reset_vault":true}')
    assert cli._check_portfolio_reset_flag(st) is False
    assert cli.load_state(cli.STATE_FILE)["capital"]["vault"]["balance"] == "15"
