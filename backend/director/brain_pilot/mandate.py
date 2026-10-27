"""Versioned operator intent, distinct from the execution capabilities in service."""
VERSION = "operator-classical-adaptive-h24-20261026"


def build(portfolio, memory):
    transferred = (memory or {}).get("transferred_experience", {})
    return {
        "version": VERSION,
        "authority": "explicit_user_trading_objective",
        "requested_style": "adaptive_scalp",
        "objective": "Use the actual Hawk and Bull trading methods as the base, adding adaptive intelligence continuously, 24 hours a day.",
        "method_contract": {
            "base": "shared_classical_hawk_and_bull_method",
            "profiles": ["hawk", "bull"],
            "profile_identity": "Keep each profile's actual entry rules, margin/leverage policy, execution controls and risk limits distinct and versioned.",
            "adaptation": "Evaluate current LONG and SHORT evidence, entries, continuation and net-profit protection within the selected profile's executable controls.",
            "rule_changes": "The model cannot silently replace the operator's method, invent profile settings, bypass limits or copy a historical error as a rule.",
            "standalone_bull_sizing_profile": "not_the_requested_architecture",
            "connection_status": "not_implemented",
        },
        "continuous_operation": {
            "requested_coverage": "24h_7d",
            "scope": "Both profiles: market evaluation, protective management and opportunity assessment, subject to valid data, pauses and risk stops.",
            "model_calls": "Within explicit API budgets; 24h operation does not imply an API call at every tick or permission to raise spend limits.",
            "degradation": "Protective management must remain active if the model is unavailable. Record whether the decision used adaptive AI or classical fallback; never label fallback as an AI decision.",
            "adaptive_h24_status": "not_implemented",
        },
        "duration": {"reference_minutes": [[1, 5], [5, 15]], "fixed_exit_timer": False,
                     "extension": "Only with concrete favorable evidence; no indefinite wait for recovery."},
        "profit_management": "Capture useful estimated NET profit after costs when continuation weakens; protect gains and release capital for a new valid setup.",
        "classical_basis": {"sources": ["hawk", "bull"],
                            "role": "Trading method baseline plus verified experience, not historical inspiration alone.",
                            "history_status": transferred.get("status", "not_imported"),
                            "live_classical_signals": "not_connected",
                            "use": "Both favorable and adverse cases with bot/run/entry-version provenance. Do not inherit a directional bias or historical error as a rule."},
        "requested_margin_reference": {"source": "bull_configuration", "minimum": 150, "maximum": 350,
                                       "state": "requested_reference_not_applied_to_brain"},
        "active_execution": portfolio.get("execution_capabilities", {"status": "unknown"}),
        "readiness": "full_scalp_engine_not_implemented",
        "precedence": "Actual risk/data/execution limits govern every action. Never invent fast monitoring, applied margins, source data or guaranteed profits.",
    }
