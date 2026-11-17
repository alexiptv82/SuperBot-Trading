"""Offline cost/preparation checks. They do not call any model or VPS."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.v3.arena.readiness import (
    CONFIG_DIR, MIN_CRYPTO_TARGET, audit_trial_configs,
)


def test_repository_arena_is_not_claimed_ready():
    report = audit_trial_configs()
    assert report["paper_only"] is True
    assert report["automatically_approve_mandate"] is False
    assert report["trial_ready"] is False
    assert report["configured_universe_identical"] is True
    assert report["configured_risk_policy_identical"] is True
    assert report["configured_decision_cadence_identical"] is True
    assert report["configured_capital_equal"] is True
    assert set(report["providers"]) == {"deepseek", "qwen", "minimax"}
    assert all(p["symbol_count"] == 8 for p in report["providers"].values())
    assert "CRYPTO_UNIVERSE_BELOW_25_TARGET" in report["blocking_evidence"]


def test_model_cost_projection_is_only_a_stress_scenario():
    result = audit_trial_configs()
    qwen = result["providers"]["qwen"]
    moderate = qwen["scenarios"]["moderate"]
    assert moderate["evaluations_per_day_if_all_symbols_eligible"] == 192
    assert moderate["configured_rate_projected_usd_per_day"] == "2.496000"
    assert moderate["configured_cap_usd_per_day"] == "0.750000"
    assert moderate["projection_over_cap"] is True
    assert "stress_scenario_not_actual_calls_or_current_price" == moderate["note"]
    assert result["providers"]["deepseek"]["scenarios"]["moderate"][
        "configured_rate_projected_usd_per_day"
    ] == "0.374400"
    assert "DAILY_AI_BUDGET_NEEDS_COVERAGE_REVIEW" in result["blocking_evidence"]


def _copy_config_dir(tmp_path: Path) -> Path:
    root = tmp_path / "configs"
    root.mkdir()
    for provider in ("deepseek", "qwen", "minimax"):
        (root / f"{provider}.json").write_bytes(
            (CONFIG_DIR / f"{provider}.json").read_bytes()
        )
    return root


def _modify(path: Path, update):
    obj = json.loads(path.read_text(encoding="utf-8"))
    update(obj)
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_different_universes_are_blocked(tmp_path):
    root = _copy_config_dir(tmp_path)
    _modify(root / "minimax.json", lambda d: d["symbols"].reverse())
    out = audit_trial_configs(root)
    assert not out["configured_universe_identical"]
    assert "DIFFERENT_SYMBOL_ORDER_OR_UNIVERSE" in out["blocking_evidence"]


def test_different_risk_policy_is_blocked(tmp_path):
    root = _copy_config_dir(tmp_path)
    _modify(
        root / "qwen.json",
        lambda d: d["risk_policy"].update(max_total_margin_fraction="0.54"),
    )
    result = audit_trial_configs(root)
    assert not result["configured_risk_policy_identical"]
    assert "DIFFERENT_RISK_MANDATES" in result["blocking_evidence"]


def test_larger_universe_does_not_magically_certify_market_feed(tmp_path):
    root = _copy_config_dir(tmp_path)
    symbols = [f"COIN{i}USDT" for i in range(MIN_CRYPTO_TARGET + 2)]
    for provider in ("deepseek", "qwen", "minimax"):
        _modify(root / f"{provider}.json", lambda d: d.update(symbols=symbols))
    result = audit_trial_configs(root)
    assert "CRYPTO_UNIVERSE_BELOW_25_TARGET" not in result["blocking_evidence"]
    assert result["trial_ready"] is False
    assert "MARKET_CAP_RANKING_NOT_VERIFIED" in result["blocking_evidence"]
    assert "GOLD_AND_SILVER_CONTRACTS_NOT_VERIFIED" in result["blocking_evidence"]
    assert "MARKET_FEED_AND_SYMBOL_RULES_NOT_VERIFIED" in result["blocking_evidence"]


def test_no_missing_config_is_silently_assumed(tmp_path):
    root = _copy_config_dir(tmp_path)
    (root / "qwen.json").unlink()
    with pytest.raises(ValueError, match="arena_readiness_missing_config"):
        audit_trial_configs(root)


def test_symlink_config_is_refused(tmp_path):
    root = _copy_config_dir(tmp_path)
    p = root / "qwen.json"
    p.unlink()
    p.symlink_to(CONFIG_DIR / "qwen.json")
    with pytest.raises(ValueError, match="arena_readiness_missing_config"):
        audit_trial_configs(root)


def test_malformed_config_is_refused(tmp_path):
    root = _copy_config_dir(tmp_path)
    (root / "minimax.json").write_text('{"bad":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="arena_readiness_invalid_config"):
        audit_trial_configs(root)


def test_can_be_serialized_without_secrets():
    result = audit_trial_configs()
    raw = json.dumps(result, sort_keys=True)
    assert "api_key" not in raw
    assert "secret" not in raw
    assert "TRIAL_T0_AND_THREE_JOURNALS_NOT_VERIFIED" in raw
