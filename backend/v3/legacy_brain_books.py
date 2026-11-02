"""Read-only Brain Free PAPER cash/PnL reconciliation on a FROZEN SQLite copy.

A final trade_closed event contains all earlier partial segments in its total.
Never sum partial_trade.net a second time on top of trade_closed.net.
This verifies historic book cash and segment arithmetic, not exchange-realized
returns nor the economics of the strategy.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

from .legacy_audit import _number
from .legacy_accounting import audit_brain_structure


@dataclass(frozen=True)
class BrainBooks:
    eligible: bool
    opened: int
    finalized: int
    partial_segments: int
    open_snapshot: int
    summed_closed_net: str
    actual_cash: str
    implied_cash: str
    cash_residual: str
    cash_pass: bool
    partial_segment_pass: bool
    entry_exit_pairing_pass: bool
    issues: tuple[str, ...]


def _event_decimal(e: dict, name: str) -> Decimal:
    return _number(e.get(name))


def audit_brain_books(
    db_path: str | Path, *,
    start_equity: Decimal = Decimal("2000"),
    tolerance: Decimal = Decimal("0.01"),
) -> BrainBooks:
    """Audit a *specific legacy* Brain Free run (not V3 planned 1000).

    Validate the full-open/final-close pairing, segment arithmetic, and
    closing cash. Any unexpected cash-affecting event type blocks promotion.
    A stream with unresolved open positions is not eligible for this
    flat-account cash check.
    """
    if tolerance <= 0 or tolerance > Decimal("0.01"):
        raise ValueError("invalid_tolerance")
    if start_equity != Decimal("2000"):
        raise ValueError("legacy_brain_start_must_be_2000")
    structure = audit_brain_structure(db_path)
    kinds = dict(structure.kind_counts)
    known = {
        "ai_decision", "ai_input", "ai_unavailable", "daily_report",
        "execution_rejected", "experiment_reframed",
        "experiment_started", "feed_status", "move_stop",
        "move_target", "open", "operator_pause", "partial_trade",
        "trade_closed",
    }
    issues = []
    if set(kinds) - known:
        issues.append("UNKNOWN_EVENT_KIND")
    if kinds.get("dca", 0):
        issues.append("DCA_REPLAY_NOT_IMPLEMENTED")
    # Historical position IDs restart at explicit experiment_reframed events.
    # An ID is unique only within an epoch, not across the entire SQLite file.
    opens: dict[tuple[int, str, int], dict] = {}
    partials: dict[tuple[int, str, int], list[dict]] = {}
    closes: dict[tuple[int, str, int], dict] = {}
    epochs = 0
    reframe_checkpoints: list[tuple[int, Decimal]] = []
    uri = Path(db_path).resolve().as_uri() + "?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True, timeout=5) as db:
        db.execute("PRAGMA query_only=ON")
        raw_state = db.execute(
            "SELECT body FROM state WHERE id=1"
        ).fetchone()
        if raw_state is None:
            raise ValueError("brain_missing_state")
        state = json.loads(raw_state[0])
        account_cash = _number(state.get("cash"))
        if not isinstance(state.get("positions"), dict):
            raise ValueError("invalid_positions")
        for kind, body in db.execute(
            """SELECT kind,body FROM events
               WHERE kind IN ('open','dca','partial_trade','trade_closed',
                              'experiment_reframed')
               ORDER BY seq"""
        ):
            e = json.loads(body)
            if not isinstance(e, dict):
                issues.append("INVALID_EVENT_BODY")
                continue
            if kind == "experiment_reframed":
                old_state = e.get("old_state")
                if not isinstance(old_state, dict):
                    issues.append("REFRAME_OLD_STATE_MISSING")
                else:
                    try:
                        before = _event_decimal(e, "old_cash")
                        after = _event_decimal(e, "new_cash")
                        state_before = _event_decimal(old_state, "cash")
                        if (abs(before - after) > tolerance or
                                abs(before - state_before) > tolerance or
                                old_state.get("positions")):
                            issues.append("REFRAME_NOT_CASH_NEUTRAL")
                        reframe_checkpoints.append((len(closes), before))
                    except ValueError:
                        issues.append("REFRAME_CASH_INVALID")
                if set(opens) != set(closes):
                    issues.append("REFRAME_HAS_ACTIVE_POSITION")
                epochs += 1
                continue
            if e.get("kind") != kind:
                issues.append("EVENT_BODY_KIND_MISMATCH")
                continue
            symbol, ident = e.get("symbol"), e.get("position_id")
            if not isinstance(symbol, str) or not symbol or type(ident) is not int:
                issues.append("INVALID_POSITION_IDENTITY")
                continue
            key = (epochs, symbol, ident)
            if kind == "open":
                if key in opens:
                    issues.append("DUPLICATE_POSITION_OPEN")
                else:
                    opens[key] = e
            elif kind == "partial_trade":
                if key not in opens or key in closes:
                    issues.append("PARTIAL_WITHOUT_ACTIVE_OPEN")
                partials.setdefault(key, []).append(e)
            elif kind == "trade_closed":
                if key not in opens or key in closes:
                    issues.append("FINAL_WITHOUT_ACTIVE_OPEN")
                closes[key] = e
            else:
                issues.append("DCA_REPLAY_NOT_IMPLEMENTED")
    if set(opens) != set(closes):
        issues.append("OPEN_CLOSE_SET_MISMATCH")
    if structure.open_positions:
        issues.append("POSITION_STILL_OPEN")

    accumulated = Decimal(0)
    final_nets = []
    partial_pass = True
    for key, final in closes.items():
        segments = partials.get(key, [])
        final_segment = final.get("segment")
        if not isinstance(final_segment, dict):
            issues.append("FINAL_SEGMENT_MISSING")
            partial_pass = False
            continue
        try:
            calculated = Decimal(0)
            for event in segments:
                segment = event.get("segment")
                if not isinstance(segment, dict):
                    raise ValueError("partial_segment_missing")
                if abs(_event_decimal(event, "net") -
                       _event_decimal(segment, "net")) > tolerance:
                    raise ValueError("partial_net_mismatch")
                calculated += _event_decimal(segment, "net")
                if abs(_event_decimal(segment, "net") -
                       (_event_decimal(segment, "gross") -
                        _event_decimal(segment, "fees") -
                        _event_decimal(segment, "funding"))) > tolerance:
                    raise ValueError("partial_components_mismatch")
            calculated += _event_decimal(final_segment, "net")
            if abs(_event_decimal(final_segment, "net") -
                   (_event_decimal(final_segment, "gross") -
                    _event_decimal(final_segment, "fees") -
                    _event_decimal(final_segment, "funding"))) > tolerance:
                raise ValueError("final_components_mismatch")
            final_total = _event_decimal(final, "net")
            if abs(final_total - calculated) > tolerance:
                raise ValueError("aggregate_net_mismatch")
            accumulated += final_total
            final_nets.append(final_total)
        except (ValueError, TypeError):
            partial_pass = False
            issues.append("SEGMENT_ACCOUNTING_MISMATCH")
    for end_count, old_cash in reframe_checkpoints:
        expected_before_reframe = start_equity + sum(
            final_nets[:end_count], Decimal(0)
        )
        if (len(final_nets) < end_count or
                abs(expected_before_reframe - old_cash) > tolerance):
            issues.append("REFRAME_PRIOR_CASH_MISMATCH")
    if reframe_checkpoints and state.get("v2_start_equity") is not None:
        if abs(_number(state["v2_start_equity"]) -
               reframe_checkpoints[-1][1]) > tolerance:
            issues.append("REFRAME_V2_START_MISMATCH")
    implied = start_equity + accumulated
    cash_residual = account_cash - implied
    cash_pass = abs(cash_residual) <= tolerance
    if not cash_pass:
        issues.append("BRAIN_CASH_NET_RESIDUAL")
    if not partial_pass:
        issues.append("PARTIAL_SEGMENT_INVALID")
    return BrainBooks(
        eligible=not issues,
        opened=len(opens),
        finalized=len(closes),
        partial_segments=sum(map(len, partials.values())),
        open_snapshot=structure.open_positions,
        summed_closed_net=str(accumulated),
        actual_cash=str(account_cash),
        implied_cash=str(implied),
        cash_residual=str(cash_residual),
        cash_pass=cash_pass,
        partial_segment_pass=partial_pass,
        entry_exit_pairing_pass=set(opens) == set(closes),
        issues=tuple(dict.fromkeys(issues)),
    )
