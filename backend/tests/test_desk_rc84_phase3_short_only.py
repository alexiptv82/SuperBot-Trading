"""Phase 3 PAPER experiment: Falco SHORT_ONLY; no live orders, no new strategy or risk change.

These checks use actual cli.run_cycle and the existing synthetic sandbox fixtures.
They intentionally do NOT remove pause flags on the VPS or enable the mode in any systemd unit.
"""
import pytest

from desk import cli
from test_desk_rc84_phase2 import _proposal, _run, _learning, native_htf
from test_long_s25 import sandbox  # noqa: F401


@pytest.mark.parametrize("source", ["claude", "rules"])
@pytest.mark.parametrize("action", ["open_long", "open_long_split"])
def test_short_only_rejects_long_entries_from_any_regular_source(source, action):
    long = _proposal(action=action)
    short = _proposal(symbol="BTC", action="open_short")
    hold = {"symbol": "ETH", "action": "hold"}
    kept, rejected = cli._rc84_paper_classic_entry_policy(
        "hawk", source, [long, short, hold], hawk_entry_mode="SHORT_ONLY"
    )
    assert rejected == [long]
    assert kept == [short, hold]


def test_short_only_is_reversible_and_default_policy_is_unchanged():
    long = _proposal()
    short = _proposal(symbol="BTC", action="open_short")
    for mode in ("BOTH",):
        kept, rejected = cli._rc84_paper_classic_entry_policy(
            "hawk", "rules", [long, short], hawk_entry_mode=mode
        )
        assert kept == [long, short] and rejected == []
    kept, rejected = cli._rc84_paper_classic_entry_policy(
        "hawk", "rules", [long, short], hawk_entry_mode="SHORT_ONLY"
    )
    assert kept == [short] and rejected == [long]


def test_invalid_hawk_mode_fails_short_only_not_accidental_long(monkeypatch):
    monkeypatch.delenv("DESK_HAWK_ENTRY_MODE", raising=False)
    assert cli._hawk_entry_mode() == "BOTH"
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "shoRt_Only")
    assert cli._hawk_entry_mode() == "SHORT_ONLY"
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "short-onli")
    assert cli._hawk_entry_mode() == "SHORT_ONLY"


def test_toro_keeps_claude_medium_long_and_short_but_not_shared_rules():
    long = _proposal(trade_type="medio")
    short = _proposal(symbol="BTC", action="open_short", trade_type="medio")
    kept, rejected = cli._rc84_paper_classic_entry_policy(
        "bull", "claude", [long, short], hawk_entry_mode="SHORT_ONLY"
    )
    assert kept == [long, short] and rejected == []
    kept, rejected = cli._rc84_paper_classic_entry_policy(
        "bull", "rules", [long, short], hawk_entry_mode="SHORT_ONLY"
    )
    assert kept == [] and rejected == [long, short]


def test_full_cycle_rejects_long_and_logs_candidate_without_open(sandbox, monkeypatch):
    cli_, data_dir = sandbox
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "SHORT_ONLY")
    monkeypatch.delenv("DESK_LONG_S25", raising=False)
    state = {}
    _run(cli_, monkeypatch, state, [_proposal()], lambda now: native_htf(now, 1))
    assert not cli_.make_account(state).positions
    assert cli_.HB["hawk_entry_mode"] == "SHORT_ONLY"
    assert cli_.HB["hawk_short_only_long_candidates"] == 1
    cand = [x for x in _learning(data_dir) if x.get("ev") == "candidate"
            and x.get("status") == "falco_short_only"]
    assert len(cand) == 1 and cand[0]["symbol"] == "ETH" and cand[0]["side"] == 1
    assert cand[0]["features"]["trend4h_state"] == "UP"


def test_full_cycle_short_still_opens_when_valid(sandbox, monkeypatch):
    cli_, data_dir = sandbox
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "SHORT_ONLY")
    monkeypatch.delenv("DESK_LONG_S25", raising=False)
    state = {}
    _run(cli_, monkeypatch, state,
         [_proposal(action="open_short")], lambda now: native_htf(now, -1))
    pos = cli_.make_account(state).positions
    assert list(pos) == ["ETH"] and pos["ETH"].side == -1
    assert cli_.HB["hawk_short_only_long_candidates"] == 0


def test_full_cycle_both_mode_restores_long(sandbox, monkeypatch):
    cli_, data_dir = sandbox
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "BOTH")
    state = {}
    _run(cli_, monkeypatch, state, [_proposal()], lambda now: native_htf(now, 1))
    assert cli_.make_account(state).positions["ETH"].side == 1


def test_legacy_long_pending_split_is_cancelled_without_closing_position(sandbox, monkeypatch):
    cli_, data_dir = sandbox
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "BOTH")
    state = {}
    now = _run(cli_, monkeypatch, state, [_proposal()], lambda t: native_htf(t, 1))
    account = cli_.make_account(state)
    old = account.positions["ETH"]
    old.pending_split = {
        "trigger": old.entry * 0.997, "margin": 20, "retrace_pct": 0.003,
        "created_ms": now, "expire_ms": now + 60_000,
    }
    cli_.save_account(account, state)
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "SHORT_ONLY")
    _run(cli_, monkeypatch, state, [], lambda t: native_htf(t, 1))
    current = cli_.make_account(state).positions["ETH"]
    assert current.side == 1 and current.pending_split is None
    assert cli_.HB["hawk_short_only_long_splits_cancelled"] == 1


def test_legacy_long_dca_does_not_increase_exposure_in_short_only(sandbox, monkeypatch):
    cli_, data_dir = sandbox
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "BOTH")
    state = {}
    _run(cli_, monkeypatch, state, [_proposal()], lambda t: native_htf(t, 1))
    original = cli_.make_account(state)
    p = original.positions["ETH"]
    # A historical medium position may exist on a wallet after a policy change.
    p.trade_type = "medio"
    cli_.save_account(original, state)
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "SHORT_ONLY")
    _run(cli_, monkeypatch, state, [{
        "symbol": "ETH", "action": "dca", "dca_sl_pct": 0.01,
        "dca_tp_pct": 0.02, "reason": "legacy LONG",
    }], lambda t: native_htf(t, 1))
    current = cli_.make_account(state).positions["ETH"]
    assert current.side == 1 and current.dca_count == 0
    assert cli_.HB["hawk_short_only_long_dca_blocked"] >= 1
