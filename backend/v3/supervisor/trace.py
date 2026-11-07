"""Reconstructed S0 read model for PAPER decision history.

This is NOT a byte-identical copy of the original S0 archive. It derives only
claims supported by the append-only journal and the existing outcome extractor.
Unknown data is explicitly absent; no AI reasoning or trading behavior is added.
"""
from __future__ import annotations

from decimal import Decimal
import re

from backend.v3.events import EventJournal
from backend.v3.outcomes import extract_outcomes, REGIMES
from backend.v3.strategy_label import normalize_label

_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9/_:.-]{0,31}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_KINDS = frozenset({"OPEN", "NO_TRADE", "HOLD", "CLOSE", "MODIFY_STOP"})
_STATES = frozenset({"DRAFT", "PENDING_REVIEW", "APPROVED", "REJECTED", "RISK_REJECTED", "EXECUTED_PAPER"})
_REASONS = frozenset({
    "ai_unavailable", "reviewer_unavailable", "risk_rejected", "market_gate",
    "missing_journal", "journal_persist_failed", "invalid_input", "portfolio_boundary",
    "malformed_output", "duplicate_request", "symbol_mismatch", "price_divergence",
    "close_modify_not_executable_r1", "risk_quote_ok", "sanitized",
    "policy_not_authorized", "deepseek:mock", "claude:mock", "deepseek:analysis", "claude:review",
})


def _safe(value, options):
    return value if type(value) is str and value in options else None


def _reason(kind, status, why):
    if status == "RISK_REJECTED": return "risk_blocked"
    if why == "ai_unavailable": return "ai_unavailable"
    if why in ("market_gate", "price_divergence"): return "market_or_execution_gate"
    if why == "policy_not_authorized": return "mandate_blocked"
    if kind == "NO_TRADE" and why in ("deepseek:analysis", "deepseek:mock"): return "brain_wait"
    if kind == "OPEN" and status == "APPROVED": return "approved_open"
    return "other_recorded_decision"


def read_brain_timeline(journal: EventJournal, *, run_id: str, limit: int) -> dict:
    if (type(journal) is not EventJournal or type(run_id) is not str
            or not _RUN.fullmatch(run_id) or type(limit) is not int or not 1 <= limit <= 500):
        raise ValueError("invalid_request")
    # A hash chain without an external anchor cannot detect deletion of its tail.
    journal.verify_chain()
    events = journal.list_run("brain", run_id)
    results = extract_outcomes(journal, "brain", run_id)
    by_decision = {}
    closes = {}
    for e in events:
        p = e.event.payload
        if type(p) is not dict: continue
        if e.event.kind == "paper_open":
            did = p.get("decision_event_id")
            if type(did) is str and did:
                by_decision.setdefault(did, []).append(e)
        if e.event.kind == "paper_close" and type(p.get("position_id")) is str:
            closes[p["position_id"]] = e
    verified = {o.position_id: o for o in results.outcomes
                if o.link_status == "linked" and type(o.net_bp) is Decimal
                and o.net_bp.is_finite() and type(o.realized_pnl) is Decimal
                and o.realized_pnl.is_finite()}
    cards = []
    for e in events:
        if e.event.kind != "brain_decision": continue
        p = e.event.payload if type(e.event.payload) is dict else {}
        kind = _safe(p.get("kind"), _KINDS)
        status = _safe(p.get("status"), _STATES)
        reason = _safe(p.get("rationale"), _REASONS)
        symbol = p.get("symbol") if type(p.get("symbol")) is str and _SYMBOL.fullmatch(p["symbol"]) else None
        sid, origin = normalize_label(p.get("strategy_id"), p.get("strategy_origin"))
        if kind != "OPEN" or status != "APPROVED": sid, origin = "", ""
        matches = [x for x in by_decision.get(e.event.event_id, [])
                   if x.event.occurred_at_ms >= e.event.occurred_at_ms
                   and type(x.event.payload) is dict and x.event.payload.get("symbol") == symbol]
        execution = "not_executed"
        position_id = result = context_hash = margin = notional = None
        if len(matches) > 1:
            execution = "ambiguous_link"
        elif kind == "OPEN" and status == "APPROVED" and len(matches) == 1:
            opening = matches[0]
            q = opening.event.payload
            position_id = q.get("position_id") if type(q.get("position_id")) is str else None
            context_hash = q.get("context_hash") if type(q.get("context_hash")) is str and _HEX.fullmatch(q["context_hash"]) else None
            for src, key in (("margin_used", "margin"), ("notional", "notional")):
                val = q.get(src)
                if type(val) is str:
                    try:
                        d = Decimal(val)
                        if d.is_finite():
                            if key == "margin": margin = str(d)
                            else: notional = str(d)
                    except Exception: pass
            execution = "open_unverified_outcome"
            o = verified.get(position_id)
            close = closes.get(position_id)
            if (o is not None and close is not None and o.decision_event_id == e.event.event_id
                    and o.symbol == symbol and o.opened_at_ms == opening.event.occurred_at_ms
                    and o.closed_at_ms == close.event.occurred_at_ms):
                execution = "closed_verified"
                result = o
            elif close is not None:
                execution = "closed_unverified"
        cards.append({
            "decision_event_id": e.event.event_id,
            "decision_event_hash": e.event_hash,
            "decision_at_ms": e.event.occurred_at_ms,
            "kind": kind, "status": status, "reason_code": reason,
            "reason_class": _reason(kind, status, reason),
            "symbol": symbol,
            "regime": _safe(p.get("regime"), REGIMES),
            "strategy_id": sid or None, "strategy_origin": origin or None,
            "position_id": position_id, "execution": execution,
            "context_hash": context_hash, "margin_used": margin,
            "position_notional": notional, "risk_at_stop": None,
            "net_bp_after_costs": str(result.net_bp) if result is not None else None,
            "realized_pnl": str(result.realized_pnl) if result is not None else None,
            "exit_reason": result.exit_reason if result is not None else None,
            "closed_at_ms": result.closed_at_ms if result is not None else None,
            "outcome_stats_eligible": bool(sid) and result is not None and not result.is_manual,
            "market_snapshot": "not_recorded", "risk_quote": "not_recorded",
            "memory_references": "not_recorded", "invalidation_rule": "not_recorded",
        })
    return {"schema_version": 1, "portfolio_id": "brain", "run_id": run_id,
            "total_decisions": len(cards),
            "closed_verified": sum(c["execution"] == "closed_verified" for c in cards),
            "unavailable_snapshots": len(cards),
            "has_more": len(cards) > limit, "decisions": list(reversed(cards[-limit:]))}
