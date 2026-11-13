"""Toro LONG-only twin in PAPER: same core signal/scalp parameters as Falco, not the failed 15m mirror.

New entries are one-sided, existing SHORT positions retain normal exits.
All tests use synthetic candles only and cannot send orders.
"""
from dataclasses import asdict
from pathlib import Path
import hashlib

import pytest

from desk import cli
from test_desk_rc84_phase2 import _proposal, _learning
from test_desk_rc84_phase3_collaudo import _go
from test_long_s25 import sandbox  # noqa: F401


def test_twin_mode_is_opt_in_paper_only_and_invalid_values_block_new(monkeypatch):
    monkeypatch.delenv("DESK_BULL_TWIN_MODE", raising=False)
    monkeypatch.setenv("DESK_MODE", "paper")
    assert cli._bull_twin_mode() == "OFF"
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "long_only")
    assert cli._bull_twin_mode() == "LONG_ONLY"
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "long-onli")
    assert cli._bull_twin_mode() == "BLOCK_NEW"
    monkeypatch.setenv("DESK_MODE", "live")
    assert cli._bull_twin_mode() == "OFF"  # no LIVE behavior change


def test_twin_has_identical_limits_and_guards_to_hawk_but_independent_state(monkeypatch):
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "LONG_ONLY")
    monkeypatch.delenv("DESK_DATA_DIR", raising=False)
    hawk, bull = cli._make_hawk_config(), cli._make_bull_config()
    assert asdict(bull.limits) == asdict(hawk.limits)
    for key in ("guardrail_min_margin", "guardrail_min_lev", "guardrail_margin_forced",
                "guardrail_lev_forced", "guardrail_type_forced"):
        assert getattr(hawk, key) == getattr(bull, key)
    assert bull.name == "bull" and hawk.name == "hawk"
    assert bull.data_dir != hawk.data_dir
    assert bull.limits.start_equity == 1000 and bull.limits.max_open == 10
    assert bull.limits.max_margin_trade == 100 and bull.limits.kill_equity == 450
    assert "SOLTANTO LONG" in bull.system_prompt
    assert bull.system_prompt.endswith(cli.SYSTEM_HAWK)  # identical underlying trading instructions


def test_legacy_toro_config_is_unchanged_without_opt_in(monkeypatch):
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.delenv("DESK_BULL_TWIN_MODE", raising=False)
    b = cli._make_bull_config()
    assert b.limits.max_open == 3 and b.limits.max_margin_trade == 350
    assert b.guardrail_margin_forced == 200 and b.guardrail_type_forced == "medio"
    assert b.system_prompt == cli.SYSTEM_BULL


@pytest.mark.parametrize("source", ["claude", "rules"])
@pytest.mark.parametrize("act", ["open_short", "open_short_split"])
def test_twin_rejects_all_new_short_variants(source, act):
    decisions = [_proposal(action=act), _proposal(symbol="BTC", action="open_long"),
                 {"symbol": "ETH", "action": "close"}]
    kept, rejected = cli._rc84_paper_classic_entry_policy(
        "bull", source, decisions, bull_twin_mode="LONG_ONLY")
    assert rejected == decisions[:1] and kept == decisions[1:]


@pytest.mark.parametrize("source", ["claude", "rules"])
def test_twin_accepts_scalp_long_but_does_not_force_a_short(source):
    long = _proposal(action="open_long")
    long_split = _proposal(symbol="BTC", action="open_long_split")
    long_medio = _proposal(symbol="SOL", action="open_long", trade_type="medio")
    short = _proposal(symbol="XRP", action="open_short")
    kept, rejected = cli._rc84_paper_classic_entry_policy(
        "bull", source, [long, long_split, long_medio, short], bull_twin_mode="LONG_ONLY")
    assert kept == [long, long_split] and rejected == [long_medio, short]


def test_invalid_twin_setting_denies_all_new_exposure():
    d = [_proposal(), _proposal(symbol="BTC", action="open_short"),
         {"symbol": "ETH", "action": "hold"}]
    kept, rejected = cli._rc84_paper_classic_entry_policy(
        "bull", "claude", d, bull_twin_mode="BLOCK_NEW")
    assert kept == [d[2]] and rejected == d[:2]


def test_hawk_rule_and_policy_are_unaffected_by_toro_switch():
    d = [_proposal(), _proposal(symbol="BTC", action="open_short")]
    for mode in ("OFF", "LONG_ONLY", "BLOCK_NEW"):
        kept, rej = cli._rc84_paper_classic_entry_policy(
            "hawk", "rules", d, hawk_entry_mode="SHORT_ONLY", bull_twin_mode=mode)
        assert kept == [d[1]] and rej == [d[0]]


def test_twin_full_cycle_rules_long_opens_and_short_only_is_logged(sandbox, monkeypatch):
    c, data = sandbox
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "LONG_ONLY")
    st = {}
    _go(c, monkeypatch, st, portfolio="bull",
        rules=[_proposal(action="open_long", margin_usd=100),
               _proposal(symbol="BTC", action="open_short")])
    acc = c.make_account(st)
    assert "ETH" in acc.positions and acc.positions["ETH"].side == 1
    assert "BTC" not in acc.positions
    assert c.HB["bull_twin_mode"] == "LONG_ONLY"
    assert any(e.get("status") == "toro_long_only" and e.get("side") == -1 for e in _learning(data))


def test_twin_full_cycle_claude_short_is_not_transformed_into_long(sandbox, monkeypatch):
    c, data = sandbox
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "LONG_ONLY")
    st = {}
    _go(c, monkeypatch, st, portfolio="bull",
        claude=[_proposal(action="open_short", margin_usd=100)], htf=-1)
    assert not c.make_account(st).positions
    assert not [e for e in _learning(data) if e.get("ev") == "open"]
    assert any(e.get("status") == "toro_long_only" for e in _learning(data))


def test_twin_keeps_explicit_claude_no_trade(sandbox, monkeypatch):
    c, data = sandbox
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "LONG_ONLY")
    st = {}
    _go(c, monkeypatch, st, portfolio="bull", claude=[])
    assert not c.make_account(st).positions


def test_twin_prevents_legacy_short_split_without_forcing_close(sandbox, monkeypatch):
    c, data = sandbox
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "OFF")
    st = {}
    now = _go(c, monkeypatch, st, portfolio="bull",
        claude=[_proposal(action="open_short", trade_type="medio", margin_usd=200)], htf=-1)
    acc = c.make_account(st)
    p = acc.positions["ETH"]
    assert p.side == -1
    p.pending_split = {"trigger": p.entry * 1.5, "margin": 20, "retrace_pct": 0.003,
                       "created_ms": now, "expire_ms": now + 86_400_000}
    c.save_account(acc, st)
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "LONG_ONLY")
    _go(c, monkeypatch, st, portfolio="bull", now=now + 60_000)
    p2 = c.make_account(st).positions["ETH"]
    assert p2.side == -1 and p2.pending_split is None
    assert c.HB["bull_twin_short_splits_cancelled"] == 1


def test_twin_s25_gate_is_off_even_if_toro_s25_flag_was_set(monkeypatch):
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "LONG_ONLY")
    # Guard against regressing to the old unguarded S25 Toro opt-in.
    source = open(cli.__file__, encoding="utf-8").read()
    assert 's25_new_entries = (PORTFOLIO.name == "bull" and bull_mode == "OFF" and' in source


def test_twin_has_no_dependency_on_failed_long_mirror():
    src = open(cli.__file__, encoding="utf-8").read()
    assert "from desk.long_mirror_15m import" not in src
    assert "import desk.long_mirror_15m" not in src


def test_short_scoring_and_rules_sources_are_byte_identical_to_phase3():
    """CLI differs for Toro routing, but the SHORT signal/rule formulas remain frozen."""
    root = Path(__file__).resolve().parents[2]
    blobs = {
        "backend/desk/signals.py": "5dca1e58db4bce70c170e60e343d10cf7336bde9",
        "backend/desk/brain.py": "6a8fc76448e486f7db86edb4bdfb9dbbbf249fcf",
        "backend/desk/engine.py": "6e2110a55ef39ee49439ff9b085782376224e601",
    }
    for path, expected in blobs.items():
        raw = (root / path).read_bytes()
        got = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        assert got == expected, f"protected SHORT logic changed: {path}"
