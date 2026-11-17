"""Read-only AI Arena readiness/cost audit; never enable a PAPER run.

This module uses configured token-rate *estimates*, not verified provider
invoices or an assertion that every potential symbol is called. The gate
cannot mark the 14-day trial ready from source-code configuration alone:
market eligibility, feed, budgets, exits and VPS health need runtime proofs.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from backend.v3.arena.trial_plan import PROVIDERS
from backend.v3.runner.config import RunnerConfig, load_runner_config

CONFIG_DIR = Path(__file__).with_name("configs")
ONE_MILLION = Decimal("1000000")
MIN_CRYPTO_TARGET = 25

# Explicit hypothetical usage for sensitivity, not provider-measured tokens.
# Includes thinking tokens inside output when the model exposes them.
SCENARIOS = (
    ("lean", 2500, 100),
    ("moderate", 2500, 1000),
    ("max_configured_output", 2500, None),
)


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _forecast(cfg: RunnerConfig, input_tokens: int, output_tokens: int) -> dict:
    # One request per configured symbol per cycle is a STRESS CASE, not a
    # prediction. The runner skips symbols holding open positions.
    # At T0, a 75-minute cycle, for example, can occur 20 times in 24h,
    # not 19.2; ceil ensures conservative, integer-aligned call forecasts.
    cycles_per_day = (Decimal(1440) / Decimal(cfg.cycle_minutes)).to_integral_value(
        rounding=ROUND_CEILING,
    )
    requests = cycles_per_day * Decimal(len(cfg.symbols))
    per_request = (
        Decimal(input_tokens) * cfg.input_usd_per_million
        + Decimal(output_tokens) * cfg.output_usd_per_million
    ) / ONE_MILLION
    projected = requests * per_request
    return {
        "input_tokens_per_request_assumed": input_tokens,
        "output_tokens_per_request_assumed": output_tokens,
        "evaluations_per_day_if_all_symbols_eligible": int(requests),
        "configured_rate_projected_usd_per_day": _money(projected),
        "configured_cap_usd_per_day": _money(cfg.daily_cap_usd),
        "projection_over_cap": projected > cfg.daily_cap_usd,
        "note": "stress_scenario_not_actual_calls_or_current_price",
    }


def audit_trial_configs(directory: Path = CONFIG_DIR) -> dict:
    """Read only three repository config files; no network, secrets, or DB."""
    if type(directory) is not Path:
        raise ValueError("arena_readiness_invalid_config_dir")
    cfgs: dict[str, RunnerConfig] = {}
    for provider in PROVIDERS:
        path = directory / (provider + ".json")
        if path.is_symlink() or not path.is_file():
            raise ValueError("arena_readiness_missing_config")
        try:
            cfgs[provider] = load_runner_config(path.read_bytes())
        except (OSError, ValueError):
            raise ValueError("arena_readiness_invalid_config") from None

    first = cfgs[PROVIDERS[0]]
    symbol_sets_equal = all(c.symbols == first.symbols for c in cfgs.values())
    policy_equal = all(c.risk_policy == first.risk_policy for c in cfgs.values())
    cycles_equal = all(c.cycle_minutes == first.cycle_minutes for c in cfgs.values())
    capital_equal = all(c.initial_equity == Decimal("2000") for c in cfgs.values())
    entries = {}
    for provider in PROVIDERS:
        cfg = cfgs[provider]
        estimates = {}
        for name, inputs, outputs in SCENARIOS:
            estimates[name] = _forecast(
                cfg, inputs, cfg.max_tokens if outputs is None else outputs,
            )
        entries[provider] = {
            "model": cfg.model,
            "configured_symbols": list(cfg.symbols),
            "symbol_count": len(cfg.symbols),
            "cycle_minutes": cfg.cycle_minutes,
            "initial_paper_usdt": str(cfg.initial_equity),
            "max_output_tokens_per_call": cfg.max_tokens,
            "thinking": cfg.thinking,
            "reasoning_effort": cfg.reasoning_effort,
            "price_rate_origin": "repository_estimate_not_verified_invoice",
            "configured_input_usd_per_million": str(cfg.input_usd_per_million),
            "configured_output_usd_per_million": str(cfg.output_usd_per_million),
            "scenarios": estimates,
        }
    blockers = []
    if not symbol_sets_equal:
        blockers.append("DIFFERENT_SYMBOL_ORDER_OR_UNIVERSE")
    if not policy_equal:
        blockers.append("DIFFERENT_RISK_MANDATES")
    if not cycles_equal:
        blockers.append("DIFFERENT_DECISION_CADENCE")
    if not capital_equal:
        blockers.append("DIFFERENT_PAPER_CAPITAL")
    if len(first.symbols) < MIN_CRYPTO_TARGET:
        blockers.append("CRYPTO_UNIVERSE_BELOW_25_TARGET")
    # Source config has no ranking snapshot, exchange eligibility, metal
    # contracts or proof of 1m/15m/1h/4h candle coverage. Never waive these.
    blockers.extend((
        "MARKET_CAP_RANKING_NOT_VERIFIED",
        "GOLD_AND_SILVER_CONTRACTS_NOT_VERIFIED",
        "MARKET_FEED_AND_SYMBOL_RULES_NOT_VERIFIED",
        "OPENROUTER_PRICE_AND_REASONING_NOT_VERIFIED",
        "RUNTIME_EXIT_WORKERS_AND_BACKUP_NOT_VERIFIED",
        "TRIAL_T0_AND_THREE_JOURNALS_NOT_VERIFIED",
    ))
    if any(
        entry["scenarios"]["moderate"]["projection_over_cap"]
        for entry in entries.values()
    ):
        blockers.append("DAILY_AI_BUDGET_NEEDS_COVERAGE_REVIEW")
    return {
        "schema": "arena_trial_readiness_preflight_v1",
        "scope": "REPOSITORY_CONFIG_ONLY_NO_RUNTIME_VERIFICATION",
        "paper_only": True,
        "automatically_approve_mandate": False,
        "trial_ready": False,
        "configured_universe_identical": symbol_sets_equal,
        "configured_risk_policy_identical": policy_equal,
        "configured_decision_cadence_identical": cycles_equal,
        "configured_capital_equal": capital_equal,
        "providers": entries,
        "blocking_evidence": blockers,
        "warning": (
            "The forecast is a stress case using repository token prices, "
            "not observed API usage. Do not change caps, launch services "
            "or use paid inference based solely on these projections."
        ),
    }
