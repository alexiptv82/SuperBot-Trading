"""Confirmed Brain 2,000 USDT PAPER run; tests never touch legacy storage."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from backend.v3.events import EventJournal
from backend.v3.runner.config import default_config_path, load_runner_config
from backend.v3.runner.exit_worker import check_existing_data
from backend.v3.runner.prepare_paper_run import RunPreparationError, prepare_new_paper_run, main

BASE = default_config_path()
BRAIN2000 = BASE.with_name("runner_config_brain2000_paper.json")
RUN_ID = "brain-rc-2000-20261106"
RUN_NAME = "brain-v3-rc2000-safe"


def _provision(parent: Path, *, expected: str = "2000"):
    return prepare_new_paper_run(
        parent=parent, run_name=RUN_NAME, run_id=RUN_ID,
        config_bytes=BRAIN2000.read_bytes(), desk_mode="paper",
        now_ms=1794000000000, expected_initial_equity=expected
    )


def test_confirmed_capital_and_user_approved_risk_profile():
    # The earlier version changed ONLY capital. The user later approved a
    # separate, exact PAPER risk profile. Check no unrelated setting changes.
    standard, release = json.loads(BASE.read_bytes()), json.loads(BRAIN2000.read_bytes())
    assert standard["initial_equity"] == "1000"
    assert release["initial_equity"] == "2000"
    expected_risk = dict(standard["risk_policy"])
    expected_risk.update({
        "max_loss_fraction": "0.042857142857142857",
        "max_open_risk_fraction": "0.12",
        "max_position_margin_fraction": "0.20",
        "max_total_margin_fraction": "0.55",
        "max_loss_margin_fraction": "0.214285714285714285",
        "min_leverage": 20,
        "max_leverage": 50,
    })
    assert release == dict(standard, initial_equity="2000", risk_policy=expected_risk)
    baseline, chosen = load_runner_config(BASE.read_bytes()), load_runner_config(BRAIN2000.read_bytes())
    expected_policy = replace(
        baseline.risk_policy,
        max_loss_fraction=Decimal("0.042857142857142857"),
        max_open_risk_fraction=Decimal("0.12"),
        max_position_margin_fraction=Decimal("0.20"),
        max_total_margin_fraction=Decimal("0.55"),
        max_loss_margin_fraction=Decimal("0.214285714285714285"),
        min_leverage=20, max_leverage=50,
    )
    assert chosen == replace(baseline, initial_equity=Decimal("2000"),
                             risk_policy=expected_policy)
    assert chosen.risk_policy.minimum_equity == Decimal("450")
    assert chosen.risk_policy.max_open_risk_fraction == Decimal("0.12")
    assert chosen.daily_loss_warn == Decimal("0.35")
    assert chosen.daily_loss_halt == Decimal("0.50")
    assert (chosen.initial_equity * chosen.risk_policy.max_loss_fraction
            < Decimal("85.72"))
    assert chosen.initial_equity * chosen.risk_policy.max_open_risk_fraction == Decimal("240")


def test_paused_brain_2000_run_preserves_sibling_history(tmp_path):
    for role in ("hawk", "bull", "brain"):
        old = tmp_path / role
        old.mkdir()
        (old / "legacy_history").write_bytes(b"LEGACY-IMMUTABLE:" + role.encode())
    before = {role: (tmp_path / role / "legacy_history").read_bytes()
              for role in ("hawk", "bull", "brain")}
    folder = _provision(tmp_path)
    assert folder != (tmp_path / "brain")
    assert (folder / "pause.flag").is_file()
    assert (folder / "budget.db").is_file()
    assert (folder / "runner_config.json").read_bytes() == BRAIN2000.read_bytes()
    mandate = json.loads((folder / "mandate.json").read_text())
    marker = json.loads((folder / "PREPARED_PAUSED_ONLY.json").read_text())
    assert mandate["approved"] is False
    assert marker["initial_equity"] == "2000"
    assert marker["paused"] is True
    assert marker["mandate_approved"] is False
    assert marker["config_sha256"] == hashlib.sha256(BRAIN2000.read_bytes()).hexdigest()
    j = check_existing_data(data_dir=folder, run_id=RUN_ID)
    events = j.list_run("brain", RUN_ID)
    assert len(events) == 1
    assert events[0].event.kind == "run_prepared"
    assert events[0].event.payload["initial_equity"] == "2000"
    assert not [e for e in events if e.event.kind in {"paper_open", "paper_close"}]
    with sqlite3.connect(folder / "budget.db") as c:
        assert c.execute("SELECT count(*) FROM spend_events").fetchone()[0] == 0
    for role in before:
        assert (tmp_path / role / "legacy_history").read_bytes() == before[role]


def test_wrong_1000_confirmation_refuses_without_creating_directory(tmp_path):
    with pytest.raises(RunPreparationError, match="capital_confirmation_mismatch"):
        _provision(tmp_path, expected="1000")
    assert not (tmp_path / RUN_NAME).exists()


def test_2000_requires_explicit_cli_flag_and_paper_mode(tmp_path):
    args = ["--parent", str(tmp_path), "--run-name", RUN_NAME,
            "--run-id", RUN_ID, "--config", str(BRAIN2000),
            "--expected-initial-equity", "2000"]
    assert main(args, env={"DESK_MODE": "paper"}) == 2
    assert main(args + ["--prepare-paper-paused"], env={"DESK_MODE": "live"}) == 2
    assert not (tmp_path / RUN_NAME).exists()
    assert main(args + ["--prepare-paper-paused"], env={"DESK_MODE": "paper"}) == 0
    assert (tmp_path / RUN_NAME / "pause.flag").is_file()


def test_duplicate_run_refused_without_touching_prepared_journal(tmp_path):
    folder = _provision(tmp_path)
    before = hashlib.sha256((folder / "journal.db").read_bytes()).digest()
    with pytest.raises(RunPreparationError, match="run_already_exists"):
        _provision(tmp_path)
    assert hashlib.sha256((folder / "journal.db").read_bytes()).digest() == before
