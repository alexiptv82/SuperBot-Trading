"""Read-only, run-scoped Brain PAPER accounting for the unified dashboard.

The journal stores realized close results, not verified live marks. Do NOT call
initial capital plus realized P&L "mark-to-market equity" while any position is
open. The run config must be explicitly supplied by the deployment: the
repository's default profile may be for a different run/capital.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from backend.v3.events import EventJournal
from backend.v3.dashboard import PortfolioSummary
from backend.v3.outcomes import extract_outcomes
from backend.v3.runner.config import load_runner_config


def unavailable() -> dict:
    return {
        "start_equity": None,
        "settled_equity": None,
        "equity": None,
        "equity_basis": "unavailable",
        "day_pnl": None,
        "pnl_day_timezone": "UTC",
    }


def brain_book_metrics(*, journal: EventJournal | None,
                       summary: PortfolioSummary | None,
                       run_id: str, config_path: str | None,
                       now_ms: int) -> dict:
    """Verify net closes from the same run and use its explicit initial capital.

    No guessed prices, no cross-run trades, no global wallet balances, and no
    partial totals if any close is inconsistent. Results are Decimal strings.
    Day boundary is UTC (same convention used for V3 daily trading limits).
    """
    out = unavailable()
    if (journal is None or summary is None or not summary.total_events
            or summary.portfolio_id != "brain" or summary.run_id != run_id
            or not run_id or not config_path or type(now_ms) is not int or now_ms <= 0):
        return out
    try:
        raw = Path(config_path).read_bytes()
        config = load_runner_config(raw)
        report = extract_outcomes(journal, "brain", run_id)
        if report.skipped or len(report.outcomes) != len(summary.closed_trades):
            return out
        realized = sum((o.realized_pnl for o in report.outcomes), Decimal("0"))
        if not realized.is_finite() or realized != summary.realized_pnl:
            return out
        settled = config.initial_equity + realized
        if not settled.is_finite():
            return out
        utc_day_start_ms = (now_ms // 86_400_000) * 86_400_000
        day = sum((o.realized_pnl for o in report.outcomes
                   if utc_day_start_ms <= o.closed_at_ms <= now_ms), Decimal("0"))
        out.update({
            "start_equity": str(config.initial_equity),
            "settled_equity": str(settled),
            # Total equity must remain unknown while even one open position is unmarked.
            "equity": str(settled) if not summary.open_positions else None,
            "equity_basis": "settled" if not summary.open_positions else "open_unmarked",
            "day_pnl": str(day),
        })
        return out
    except (OSError, ValueError, TypeError, ArithmeticError):
        return out
