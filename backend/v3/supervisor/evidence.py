"""Reconstructed S1 PAPER evidence contract (NOT the original ZIP's exact bytes).

Opt-in functions; no changes to the existing runner, no AI/network activity.
Observations are written before decisions; resolutions are linked afterwards.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
import re

from backend.v3.events import Event, EventJournal
from backend.v3.brain_market.params import MarketViewParams
from backend.v3.brain_market.view import build_market_view
from backend.v3.brain_f2.contracts import BrainDecision, OpenProposal, DecisionKind, ProposalStatus
from backend.v3.risk import RiskQuote
from backend.v3.strategy_label import normalize_label

_VALID_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_VALID_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9/_:.-]{0,31}\Z")
_VALID_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SKIP = frozenset({"already_open", "no_market_rules", "feed_error", "view_error",
                   "data_unavailable", "price_error", "cycle_error"})
_RISKS = frozenset({
    "quote_only", "portfolio_locked", "stale_market_data", "invalid_side",
    "invalid_leverage", "invalid_numeric_input", "invalid_policy_or_market",
    "equity_floor_reached", "stop_wrong_side", "stop_near_liquidation",
    "risk_budget_exhausted", "margin_budget_exhausted", "below_minimum_size",
    "internal_risk_invariant", "ok",
})
_REASON = frozenset({
    "ai_unavailable", "reviewer_unavailable", "risk_rejected", "market_gate",
    "missing_journal", "journal_persist_failed", "invalid_input", "portfolio_boundary",
    "malformed_output", "duplicate_request", "symbol_mismatch", "price_divergence",
    "close_modify_not_executable_r1", "risk_quote_ok", "sanitized",
    "policy_not_authorized", "deepseek:mock", "claude:mock", "deepseek:analysis", "claude:review",
})


class EvidenceError(ValueError):
    """Fixed code only; no untrusted free text in error messages."""


@dataclass(frozen=True)
class PreparedMarketView:
    """Immutable snapshot computed once from the closed-candle L5 builder.

    The serialized JSON is the source of truth, not a mutable caller mapping.
    Reuse can avoid an EXTRA L5 pass from the S1 evidence collector.
    """
    symbol: str
    timestamp_ms: int
    params: MarketViewParams
    market_json: str
    market_sha256: str

    def market(self) -> dict:
        """Return a fresh JSON tree; do not expose the saved representation."""
        return json.loads(self.market_json)


def prepare_market_view(*, symbol: str, timestamp_ms: int,
                        bars_by_tf, params: MarketViewParams) -> PreparedMarketView:
    if (type(symbol) is not str or not _VALID_SYMBOL.fullmatch(symbol)
            or type(timestamp_ms) is not int or timestamp_ms <= 0
            or type(params) is not MarketViewParams):
        raise EvidenceError("invalid_market_snapshot")
    try:
        market = build_market_view(bars_by_tf, timestamp_ms=timestamp_ms, params=params)
    except Exception:
        raise EvidenceError("invalid_market_snapshot") from None
    base = next((tf for tf in market.get("timeframes", ())
                 if tf.get("tf") == market.get("base_tf")), None)
    if (market.get("regime") == "UNKNOWN" or base is None
            or base.get("status") != "ok"):
        raise EvidenceError("market_unavailable")
    market_json = _json(market)
    if len(market_json.encode("utf-8")) > 24000:
        raise EvidenceError("invalid_market_snapshot")
    return PreparedMarketView(symbol, timestamp_ms, params, market_json,
                              sha256(market_json.encode("utf-8")).hexdigest())


@dataclass(frozen=True)
class ObservationReceipt:
    event_id: str
    event_hash: str
    run_id: str
    symbol: str
    observed_at_ms: int
    phase: str


def _assert_meta(journal, run_id, symbol, timestamp, index):
    if (type(journal) is not EventJournal or type(run_id) is not str or not _VALID_ID.fullmatch(run_id)
            or type(symbol) is not str or not _VALID_SYMBOL.fullmatch(symbol)
            or type(timestamp) is not int or timestamp <= 0 or type(index) is not int or index < 0):
        raise EvidenceError("invalid_observation")


def _num(value):
    if type(value) is not Decimal or not value.is_finite() or value < 0:
        raise EvidenceError("invalid_numeric")
    return str(value)


def _json(data):
    try: return json.dumps(data, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    except (ValueError, TypeError, OverflowError): raise EvidenceError("invalid_evidence") from None


def _identity(run, symbol, ts, index):
    return "supervisor." + sha256(_json([run, symbol, ts, index]).encode()).hexdigest()[:40]


def _append(journal, event):
    try: return journal.append(event)
    except Exception: raise EvidenceError("evidence_persist_failed") from None


def _write_obs(journal, run_id, symbol, observed_at_ms, candidate_index, phase, reason, market, portfolio):
    market_json = _json(market) if market is not None else None
    if market_json is not None and len(market_json.encode()) > 24000:
        raise EvidenceError("invalid_market_snapshot")
    event_id = _identity(run_id, symbol, observed_at_ms, candidate_index)
    event = Event(event_id, "brain", run_id, "supervisor_observation", observed_at_ms,
                  "supervisor_s1", {
                      "schema_version": 1, "phase": phase, "reason": reason,
                      "symbol": symbol, "candidate_index": candidate_index,
                      "market": market, "market_sha256": sha256(market_json.encode()).hexdigest() if market_json is not None else None,
                      "regime": market.get("regime") if market else None,
                      "portfolio": portfolio,
                      "memory_references": "not_recorded", "invalidation_rule": "not_recorded",
                  })
    stored = _append(journal, event)
    return ObservationReceipt(event_id, stored.event_hash, run_id, symbol, observed_at_ms, phase)


def record_observation(*, journal: EventJournal, run_id: str, symbol: str,
                       observed_at_ms: int, candidate_index: int,
                       bars_by_tf, market_params: MarketViewParams,
                       price: Decimal, open_position_count: int,
                       equity: Decimal, available_cash: Decimal,
                       margin_used: Decimal, existing_open_risk: Decimal,
                       prepared_market: PreparedMarketView | None = None) -> ObservationReceipt:
    _assert_meta(journal, run_id, symbol, observed_at_ms, candidate_index)
    if type(market_params) is not MarketViewParams or type(open_position_count) is not int or open_position_count < 0:
        raise EvidenceError("invalid_observation")
    values = {k: _num(v) for k, v in {
        "price": price, "equity": equity, "available_cash": available_cash,
        "margin_used": margin_used, "existing_open_risk": existing_open_risk,
    }.items()}
    if price <= 0: raise EvidenceError("invalid_numeric")
    if prepared_market is None:
        prepared = prepare_market_view(symbol=symbol, timestamp_ms=observed_at_ms,
                                       bars_by_tf=bars_by_tf, params=market_params)
    else:
        prepared = prepared_market
        if (type(prepared) is not PreparedMarketView
                or prepared.symbol != symbol or prepared.timestamp_ms != observed_at_ms
                or prepared.params != market_params
                or type(prepared.market_json) is not str
                or len(prepared.market_json.encode("utf-8")) > 24000
                or type(prepared.market_sha256) is not str
                or sha256(prepared.market_json.encode("utf-8")).hexdigest()
                   != prepared.market_sha256):
            raise EvidenceError("invalid_market_snapshot")
    market = prepared.market()
    if (market.get("regime") == "UNKNOWN" or not any(
        tf.get("tf") == market.get("base_tf") and tf.get("status") == "ok"
        for tf in market.get("timeframes", [])
    )):
        raise EvidenceError("market_unavailable")
    return _write_obs(journal, run_id, symbol, observed_at_ms, candidate_index,
                      "ready", "ready", market, {**values, "open_position_count": open_position_count})


def record_skipped_candidate(*, journal: EventJournal, run_id: str, symbol: str,
                             observed_at_ms: int, candidate_index: int, reason: str) -> ObservationReceipt:
    _assert_meta(journal, run_id, symbol, observed_at_ms, candidate_index)
    if type(reason) is not str or reason not in _SKIP:
        raise EvidenceError("invalid_skip_reason")
    return _write_obs(journal, run_id, symbol, observed_at_ms, candidate_index,
                      "skipped", reason, None, None)


def record_resolution(*, journal: EventJournal, receipt: ObservationReceipt, decided_at_ms: int,
                      decision: BrainDecision, allowed_strategy_ids: frozenset[str]):
    if (type(journal) is not EventJournal or type(receipt) is not ObservationReceipt
            or receipt.phase != "ready" or type(decided_at_ms) is not int
            or decided_at_ms < receipt.observed_at_ms or type(allowed_strategy_ids) is not frozenset
            or any(type(x) is not str for x in allowed_strategy_ids)):
        raise EvidenceError("invalid_resolution")
    if type(decision) is not BrainDecision or type(decision.kind) is not DecisionKind or type(decision.status) is not ProposalStatus:
        raise EvidenceError("invalid_decision")
    try:
        events = journal.list_run("brain", receipt.run_id)
    except Exception:
        raise EvidenceError("journal_unavailable") from None
    originals = [e for e in events if e.event.event_id == receipt.event_id
                 and e.event.kind == "supervisor_observation"]
    if (len(originals) != 1 or originals[0].event_hash != receipt.event_hash
            or originals[0].event.payload.get("phase") != "ready"
            or originals[0].event.payload.get("symbol") != receipt.symbol
            or originals[0].event.occurred_at_ms != receipt.observed_at_ms):
        raise EvidenceError("invalid_receipt")
    prop = None
    if decision.kind == DecisionKind.OPEN and decision.status == ProposalStatus.APPROVED:
        p = decision.proposal
        if (type(p) is not OpenProposal or p.symbol != receipt.symbol
                or type(p.side) is not int or p.side not in (-1, 1)
                or type(p.leverage) is not int or p.leverage <= 0
                or any(type(v) is not Decimal or not v.is_finite() or v <= 0 for v in (p.entry_price, p.stop_price))):
            raise EvidenceError("invalid_proposal")
        sid, origin = normalize_label(p.strategy_id, p.strategy_origin, allowed_strategy_ids)
        prop = {"symbol": p.symbol, "side": p.side, "leverage": p.leverage,
                "entry_price": str(p.entry_price), "stop_price": str(p.stop_price),
                "strategy_id": sid or None, "strategy_origin": origin or None,
                "model_context_sha256": p.context_hash if type(p.context_hash) is str and _VALID_SHA.fullmatch(p.context_hash) else None}
    elif decision.proposal is not None or decision.risk_quote is not None:
        raise EvidenceError("invalid_decision")
    q = decision.risk_quote
    risk = None
    if q is not None:
        if type(q) is not RiskQuote or type(q.allowed) is not bool or type(q.reason) is not str or q.reason not in _RISKS:
            raise EvidenceError("invalid_risk_quote")
        risk = {"allowed": q.allowed, "reason": q.reason,
                **{k: _num(getattr(q,k)) for k in ("quantity", "notional", "margin", "worst_case_loss_estimate", "risk_budget")}}
    reason = decision.rationale if type(decision.rationale) is str and decision.rationale in _REASON else "sanitized"
    link = decision.journal_event_id
    if type(link) is not str or not _VALID_ID.fullmatch(link) or not any(
        x.event.event_id == link and x.event.kind == "brain_decision"
        and x.event.payload.get("symbol") == receipt.symbol and x.event.occurred_at_ms >= receipt.observed_at_ms
        for x in events
    ):
        link = None
    event = Event(receipt.event_id + ".result", "brain", receipt.run_id,
                  "supervisor_resolution", decided_at_ms, "supervisor_s1", {
                      "schema_version": 1, "observation_id": receipt.event_id,
                      "observation_hash": receipt.event_hash, "symbol": receipt.symbol,
                      "kind": decision.kind.value, "status": decision.status.value,
                      "reason_code": reason, "proposal": prop, "risk_quote": risk,
                      "decision_event_id": link,
                      "memory_references": "not_recorded", "invalidation_rule": "not_recorded",
                  })
    return _append(journal, event)


def read_evidence(journal: EventJournal, *, run_id: str) -> tuple[dict, ...]:
    if type(journal) is not EventJournal or type(run_id) is not str or not _VALID_ID.fullmatch(run_id):
        raise EvidenceError("invalid_request")
    try:
        journal.verify_chain()
        rows = journal.list_run("brain", run_id)
    except Exception:
        raise EvidenceError("journal_unavailable") from None
    observations, results = {}, {}
    for e in rows:
        if e.event.kind == "supervisor_observation":
            if e.event.event_id in observations: raise EvidenceError("duplicate_observation")
            observations[e.event.event_id] = e
        if e.event.kind == "supervisor_resolution":
            ref = e.event.payload.get("observation_id")
            if type(ref) is not str or ref in results: raise EvidenceError("invalid_evidence_chain")
            results[ref] = e
    if results.keys() - observations.keys(): raise EvidenceError("invalid_evidence_chain")
    cards = []
    for oid, record in observations.items():
        p = record.event.payload
        if type(p) is not dict or p.get("phase") not in ("ready", "skipped"):
            raise EvidenceError("invalid_evidence_chain")
        result = results.get(oid)
        if result is not None:
            d = result.event.payload
            if (p["phase"] != "ready" or d.get("observation_hash") != record.event_hash
                    or d.get("symbol") != p.get("symbol") or result.seq <= record.seq
                    or result.event.occurred_at_ms < record.event.occurred_at_ms):
                raise EvidenceError("invalid_evidence_chain")
        cards.append({
            "observation_id": oid, "event_hash": record.event_hash,
            "at_ms": record.event.occurred_at_ms, "symbol": p.get("symbol"),
            "phase": p["phase"], "reason": p.get("reason"),
            "market": p.get("market"), "market_sha256": p.get("market_sha256"),
            "portfolio": p.get("portfolio"), "regime": p.get("regime"),
            "decision": result.event.payload if result else None,
            "resolution_state": "resolved" if result else ("skipped" if p["phase"] == "skipped" else "pending"),
        })
    return tuple(cards)
