"""Versioned operator intent, distinct from the execution capabilities in service."""
VERSION = "operator-adaptive-scalp-20261026"


def build(portfolio, memory):
    transferred = (memory or {}).get("transferred_experience", {})
    return {
        "version": VERSION,
        "authority": "explicit_user_trading_objective",
        "requested_style": "adaptive_scalp",
        "objective": "Apply the operator's trading idea using analysis and verified classical-bot experience.",
        "duration": {"reference_minutes": [[1, 5], [5, 15]], "fixed_exit_timer": False,
                     "extension": "Only with concrete favorable evidence; no indefinite wait for recovery."},
        "profit_management": "Capture useful estimated NET profit after costs when continuation weakens; protect gains and release capital for a new valid setup.",
        "classical_basis": {"sources": ["hawk", "bull"],
                            "history_status": transferred.get("status", "not_imported"),
                            "live_classical_signals": "not_connected",
                            "use": "Both favorable and adverse cases with bot/run/entry-version provenance. Do not inherit a directional bias or historical error as a rule."},
        "requested_margin_reference": {"source": "bull_configuration", "minimum": 150, "maximum": 350,
                                       "state": "requested_reference_not_applied_to_brain"},
        "active_execution": portfolio.get("execution_capabilities", {"status": "unknown"}),
        "readiness": "full_scalp_engine_not_implemented",
        "precedence": "Actual risk/data/execution limits govern every action. Never invent fast monitoring, applied margins, source data or guaranteed profits.",
    }
