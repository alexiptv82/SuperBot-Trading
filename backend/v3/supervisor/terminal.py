"""S2: conservative decision-card projection from S0 + S1 read models.

This module cannot certify a model's private reasoning or historical learning.
Only recorded allowlisted values are returned. All other free text is dropped.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9/_:.-]{0,31}\Z")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
DECIMAL = re.compile(r"-?[0-9]{1,24}(?:\.[0-9]{1,12})?\Z")
DECISION_KINDS = frozenset({"OPEN", "NO_TRADE", "HOLD", "CLOSE", "MODIFY_STOP"})
DECISION_STATUS = frozenset({"DRAFT", "PENDING_REVIEW", "APPROVED", "REJECTED", "RISK_REJECTED", "EXECUTED_PAPER"})
REASONS = frozenset({"risk_blocked", "ai_unavailable", "brain_wait", "market_or_execution_gate",
                     "mandate_blocked", "approved_open", "other_recorded_decision", "preflight_skipped"})
EXECUTIONS = frozenset({"not_executed", "ambiguous_link", "open_unverified_outcome",
                         "closed_unverified", "closed_verified", "preflight_skipped"})
PHASES = frozenset({"ready", "skipped"})
SKIP_REASONS = frozenset({"already_open", "no_market_rules", "feed_error", "view_error",
                          "data_unavailable", "price_error", "cycle_error"})
REGIMES = frozenset({"TRENDING", "RANGING", "VOLATILE", "UNKNOWN", "TREND_UP",
                      "TREND_DOWN", "RANGE", "EXPANSION", "SHOCK", "UNCERTAIN"})
TF = frozenset({"1m", "5m", "15m", "1h", "4h", "1d"})
TF_STATUS = frozenset({"ok", "missing", "stale", "insufficient_history"})


def _token(v, opts):
    return v if type(v) is str and v in opts else None


def _pattern(v, regex):
    return v if type(v) is str and regex.fullmatch(v) else None


def _positive_ms(v):
    return v if type(v) is int and 0 < v < 10**16 else None


def _numeric(v):
    return _pattern(v, DECIMAL)


def _market_summary(market):
    if type(market) is not dict or type(market.get("timeframes")) is not list:
        return None
    frames = []
    for item in market["timeframes"]:
        if type(item) is not dict:
            return None
        tf = _token(item.get("tf"), TF)
        status = _token(item.get("status"), TF_STATUS)
        if tf is None or status is None:
            return None
        frames.append({"tf": tf, "status": status, "regime": _token(item.get("regime"), REGIMES),
                       "rsi": _numeric(item.get("rsi")), "adx": _numeric(item.get("adx")),
                       "ema_fast_gap_bp": _numeric(item.get("ema_fast_gap_bp"))})
    return frames if len(frames) <= 6 else None


def _safe_observation(e):
    if type(e) is not dict:
        return None
    symbol = _pattern(e.get("symbol"), SYMBOL)
    at_ms = _positive_ms(e.get("at_ms"))
    oid = _pattern(e.get("observation_id"), ID)
    if symbol is None or at_ms is None or oid is None:
        return None
    phase = _token(e.get("phase"), PHASES)
    if phase is None:
        return None
    d = e.get("decision")
    if d is not None and type(d) is not dict:
        return None
    resolved = e.get("resolution_state")
    if resolved not in ("resolved", "pending", "skipped"):
        return None
    if (phase == "skipped" and (d is not None or resolved != "skipped")) or (phase == "ready" and resolved == "skipped"):
        return None
    if (resolved == "resolved") != (d is not None):
        return None
    risk = d.get("risk_quote") if d else None
    if risk is not None and type(risk) is not dict:
        risk = None
    p = e.get("portfolio")
    if p is not None and type(p) is not dict:
        p = None
    return {
        "id": oid, "phase": phase, "at_ms": at_ms, "symbol": symbol,
        "reason": _token(e.get("reason"), SKIP_REASONS) if phase == "skipped" else None,
        "market_sha256": _pattern(e.get("market_sha256"), HASH),
        "timeframes": _market_summary(e.get("market")),
        "equity": _numeric(p.get("equity")) if p else None,
        "cash": _numeric(p.get("available_cash")) if p else None,
        "risk_at_stop": _numeric(risk.get("worst_case_loss_estimate")) if risk else None,
        "risk_budget": _numeric(risk.get("risk_budget")) if risk else None,
        "resolution_state": resolved,
        "resolution_link_id": _pattern(d.get("decision_event_id"), ID) if d else None,
        "resolution_kind": _token(d.get("kind"), DECISION_KINDS) if d else None,
        "resolution_status": _token(d.get("status"), DECISION_STATUS) if d else None,
        "resolution_reason": _pattern(d.get("reason_code"), ID) if d else None,
    }


def project_timeline(s0: dict, s1: tuple | list, *, run_id: str, limit: int = 50,
                     symbol: str | None = None, reason: str | None = None) -> dict:
    """Provide only bounded, sanitized cards. Source window is limited to S0's latest 500.

    Filters apply to this bounded source, NOT the entire historical journal;
    callers must display `source_window_limited` to avoid false completeness.
    """
    if (type(run_id) is not str or not ID.fullmatch(run_id) or type(limit) is not int
            or not 1 <= limit <= 100 or symbol is not None and _pattern(symbol, SYMBOL) is None
            or reason is not None and reason not in REASONS):
        raise ValueError("invalid_request") from None
    if (type(s0) is not dict or s0.get("run_id") != run_id or s0.get("portfolio_id") != "brain"
            or type(s0.get("decisions")) is not list or type(s1) not in (tuple, list)
            or type(s0.get("total_decisions", 0)) is not int
            or s0.get("total_decisions", 0) < len(s0["decisions"])):
        raise ValueError("invalid_sources") from None
    evidence = {}
    skips = []
    for raw in s1:
        e = _safe_observation(raw)
        if e is None:
            continue
        if e["resolution_link_id"]:
            evidence.setdefault(e["resolution_link_id"], []).append(e)
        if e["phase"] == "skipped":
            skips.append({"id": e["id"], "kind": "SKIPPED", "status": "NOT_ANALYZED",
                          "reason_class": "preflight_skipped", "reason_code": e["reason"],
                          "at_ms": e["at_ms"], "symbol": e["symbol"], "regime": None,
                          "strategy_id": None, "execution": "preflight_skipped",
                          "net_bp": None, "realized_pnl": None,
                          "evidence": e, "evidence_status": "preflight_recorded"})
    cards = []
    seen = set()
    for raw in s0["decisions"]:
        if type(raw) is not dict:
            continue
        event_id = _pattern(raw.get("decision_event_id"), ID)
        at_ms = _positive_ms(raw.get("decision_at_ms"))
        if event_id is None or at_ms is None:
            continue
        if event_id in seen:
            raise ValueError("invalid_sources") from None
        seen.add(event_id)
        symbol_at_decision = _pattern(raw.get("symbol"), SYMBOL)
        kind_at_decision = _token(raw.get("kind"), DECISION_KINDS)
        status_at_decision = _token(raw.get("status"), DECISION_STATUS)
        reason_at_decision = _pattern(raw.get("reason_code"), ID)
        matched = evidence.get(event_id, [])
        # An ID alone is NOT proof that an observation belongs to a decision.
        # Require equality of symbol, kind, status, recorded reason and time ordering.
        eligible = [e for e in matched if (
            e["phase"] == "ready" and e["resolution_state"] == "resolved"
            and e["symbol"] == symbol_at_decision and symbol_at_decision is not None
            and e["at_ms"] <= at_ms
            and e["resolution_kind"] == kind_at_decision and kind_at_decision is not None
            and e["resolution_status"] == status_at_decision and status_at_decision is not None
            and e["resolution_reason"] == reason_at_decision and reason_at_decision is not None
        )]
        details = eligible[0] if len(matched) == 1 and len(eligible) == 1 else None
        execution = _token(raw.get("execution"), EXECUTIONS)
        closed_verified = execution == "closed_verified"
        cards.append({
            "id": event_id, "kind": kind_at_decision,
            "status": status_at_decision,
            "reason_class": _token(raw.get("reason_class"), REASONS) or "other_recorded_decision",
            "reason_code": reason_at_decision,
            "at_ms": at_ms, "symbol": symbol_at_decision,
            "regime": _token(raw.get("regime"), REGIMES),
            "strategy_id": _pattern(raw.get("strategy_id"), ID),
            "execution": execution,
            "net_bp": _numeric(raw.get("net_bp_after_costs")) if closed_verified else None,
            "realized_pnl": _numeric(raw.get("realized_pnl")) if closed_verified else None,
            "evidence": details,
            "evidence_status": ("recorded" if details else
                                "ambiguous" if len(matched) > 1 else
                                "inconsistent" if len(matched) == 1 else "not_recorded"),
        })
    cards.extend(skips)
    cards.sort(key=lambda x: (x["at_ms"], x["id"]), reverse=True)
    if symbol is not None:
        cards = [c for c in cards if c["symbol"] == symbol]
    if reason is not None:
        cards = [c for c in cards if c["reason_class"] == reason]
    return {
        "schema_version": 1, "portfolio_id": "brain", "run_id": run_id,
        "source_window_limited": bool(s0.get("has_more")) or bool(s0.get("total_decisions", 0) > len(s0["decisions"])),
        "matched_in_window": len(cards), "has_more": len(cards) > limit,
        "decisions": cards[:limit],
    }
