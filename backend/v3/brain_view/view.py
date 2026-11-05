"""Pure PAPER scoreboard for the current market regime, net of costs."""
from __future__ import annotations

from backend.v3.outcomes import REGIMES, TradeOutcome
from backend.v3.learning.expectancy import cell_stats
from backend.v3.strategy_label import normalize_label
from backend.v3.brain_view.params import ViewParams


_STATUS_ORDER = {"positive": 0, "negative": 1, "inconclusive": 2, "insufficient": 3}


def build_scoreboard(outcomes, *, regime, params) -> dict:
    """Construct the scored strategy x side table in the current regime.

    1. Validate every outcome, then regime, then params, in that order.
    2. Count all nonmanual linked closes, across all regimes.
    3. Select only linked, nonmanual, regime-matching, valid labels; count
       all valid labelled closes separately across all regimes.
    4. Call P4 cell_stats once on selected closes, never on an empty set.
    5. Order by status, descending mean net bp, id and descending side;
       truncate to max_cells and return JSON-safe decimals as strings.
    """
    if not isinstance(outcomes, (list, tuple)) or any(type(o) is not TradeOutcome for o in outcomes):
        raise ValueError("invalid_outcomes") from None
    if type(regime) is not str or regime not in REGIMES:
        raise ValueError("invalid_regime") from None
    if type(params) is not ViewParams:
        raise ValueError("invalid_params") from None

    closed = 0
    labelled = 0
    selected = []
    for o in outcomes:
        if o.link_status != "linked" or o.is_manual:
            continue
        closed += 1
        sid, origin = normalize_label(o.strategy_id, o.strategy_origin)
        if not sid:
            continue
        labelled += 1
        if o.decision_regime == regime:
            selected.append(o)

    try:
        computed = cell_stats(
            selected, min_trades=params.min_trades, min_days=params.min_days,
            confidence=params.confidence, n_boot=params.n_boot, seed=params.seed,
            key=lambda o: (o.strategy_id, o.strategy_origin, o.side),
        ) if selected else ()
    except Exception:
        raise ValueError("invalid_outcomes") from None
    try:
        ordered = sorted(
            computed,
            key=lambda c: (_STATUS_ORDER[c.status], -c.mean_net_bp, c.key[0], -c.key[2]),
        )
        all_count = len(ordered)
        cells = [{
            "strategy_id": c.key[0], "origin": c.key[1], "side": c.key[2],
            "n": c.n, "n_days": c.n_days, "mean_net_bp": str(c.mean_net_bp),
            "ci_low": None if c.ci_low is None else str(c.ci_low),
            "ci_high": None if c.ci_high is None else str(c.ci_high),
            "status": c.status,
        } for c in ordered[:params.max_cells]]
    except Exception:
        raise ValueError("invalid_outcomes") from None
    return {"regime": regime, "n_closed_linked": closed, "n_labelled": labelled,
            "n_cells": all_count, "truncated": all_count > params.max_cells,
            "cells": cells}
