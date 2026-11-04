"""Motore Brain F2 R1.5 — matrice kind/status, rationale allowlist, single append, policy mandate.

- Solo OPEN può essere APPROVED; NO_TRADE/HOLD mai APPROVED.
- Rationale solo da allowlist; testi AI liberi scrubbed.
- complexity_threshold deve essere float finito in [0,1].
- Una sola scrittura journal per decisione approvata.
- Policy mandate versionato e approvato obbligatorio (separato da F1).
"""
from __future__ import annotations

import logging
import hashlib
import uuid
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional

from .analyst import Analyst
from .contracts import (
    BrainDecision, DecisionKind, MarketContext, ProposalStatus, MemoryEpisode,
    OpenProposal, CloseProposal, StopModifyProposal,
)
from .reviewer import Reviewer

try:
    from backend.v3.events import Event, EventJournal
    from backend.v3.risk import RiskPolicy, RiskRequest, RiskQuote, quote_paper_risk
except ImportError:
    Event = EventJournal = RiskPolicy = RiskRequest = RiskQuote = quote_paper_risk = None  # type: ignore


_ALLOWED_RATIONALE = frozenset({
    "ai_unavailable", "reviewer_unavailable", "risk_rejected", "market_gate",
    "missing_journal", "journal_persist_failed", "invalid_input",
    "portfolio_boundary", "malformed_output", "duplicate_request",
    "symbol_mismatch", "price_divergence", "close_modify_not_executable_r1",
    "risk_quote_ok", "sanitized", "policy_not_authorized",
    "deepseek:mock", "claude:mock", "deepseek:analysis", "claude:review",
})
_ALLOWED_SOURCES = frozenset({
    "deepseek:mock", "claude:mock", "engine:fail_closed", "engine:validate",
    "deepseek:analysis", "claude:review", "risk:quote",
})
_MAX_ENTRY_DIVERGENCE = Decimal("0.01")
_SYMBOL_RE = __import__("re").compile(r"^[A-Z0-9][A-Z0-9/_:.-]{0,31}$")
_ALLOWED_REGIMES = frozenset({"TRENDING", "RANGING", "VOLATILE", "UNKNOWN"})
_EVENT_ID_RE = __import__("re").compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")

def _safe_symbol(s):
    if isinstance(s, str) and _SYMBOL_RE.match(s):
        return s
    return "unknown"

def _safe_regime(r):
    if isinstance(r, str) and r in _ALLOWED_REGIMES:
        return r
    return "UNKNOWN"

def _safe_event_id(eid):
    if isinstance(eid, str) and _EVENT_ID_RE.match(eid):
        return eid
    return None

_ALLOWED_ORIGINS = frozenset({"deepseek", "claude", "deepseek:mock", "claude:mock"})
logger = logging.getLogger(__name__)
_TRUSTED_APPROVERS = frozenset({"operator", "system-admin"})  # external trust anchor required

def _policy_hash(policy) -> str:
    if policy is None:
        return ""
    fields = (
        str(policy.max_loss_fraction), str(policy.max_open_risk_fraction),
        str(policy.max_position_margin_fraction), str(policy.max_total_margin_fraction),
        str(policy.minimum_equity), str(policy.estimated_roundtrip_cost_bp),
        str(policy.liquidation_buffer_fraction),
    )
    return hashlib.sha256("|".join(fields).encode()).hexdigest()[:16]


def _finite(value: Any) -> Optional[Decimal]:
    try:
        d = Decimal(str(value))
        if not d.is_finite():
            return None
        return d
    except (InvalidOperation, TypeError, ValueError):
        return None


def _request_id(run_id: str, ts: int, symbol: str, proposal: Any) -> str:
    key = f"{run_id}|{ts}|{symbol}"
    if isinstance(proposal, OpenProposal):
        key += f"|{proposal.symbol}|{proposal.side}|{proposal.entry_price}|{proposal.stop_price}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:32]
    return f"brain-req-{digest}"


class BrainPortfolioSnapshot:
    def __init__(self, equity: Decimal, available_cash: Decimal, margin_used: Decimal, existing_open_risk: Decimal):
        self.equity = equity
        self.available_cash = available_cash
        self.margin_used = margin_used
        self.existing_open_risk = existing_open_risk


class BrainEngine:
    def __init__(
        self,
        analyst: Analyst,
        reviewer: Reviewer,
        risk_policy: Optional[RiskPolicy] = None,
        portfolio_snapshot: Optional[BrainPortfolioSnapshot] = None,
        market_params: Optional[dict] = None,
        journal: Optional[Any] = None,
        portfolio_id: str = "brain",
        run_id: Optional[str] = None,
        policy_mandate: Optional[dict] = None,
        policy_verifier: Optional[Callable[[dict, Any], bool]] = None,
    ):
        # P0-1: required dependencies
        if risk_policy is None:
            raise ValueError("risk_policy is required")
        if portfolio_snapshot is None:
            raise ValueError("portfolio_snapshot is required")
        # P0-3: journal required (NullJournal pattern alternative would still fail-closed)
        if journal is None:
            raise ValueError("journal is required")
        self.analyst = analyst
        self.reviewer = reviewer
        self.risk_policy = risk_policy
        self.portfolio_snapshot = portfolio_snapshot
        self.market_params = market_params or {}
        self.journal = journal
        self.portfolio_id = portfolio_id
        self.run_id = run_id
        self.policy_mandate = policy_mandate
        self.policy_verifier = policy_verifier
        self.open_positions: list[dict] = []
        self.memory: list[MemoryEpisode] = []
        self.cycle = 0

    def step(self, context: MarketContext, complexity_threshold: float = 0.7) -> BrainDecision:
        self.cycle += 1

        if self.portfolio_id != "brain":
            return self._no_trade("portfolio_boundary", context)
        if not self.run_id or not isinstance(self.run_id, str) or not self.run_id.strip():
            return self._no_trade("invalid_input", context)

        price = _finite(getattr(context, "price", None))
        symbol = getattr(context, "symbol", None)
        if not isinstance(context, MarketContext) or price is None or price <= 0 or not isinstance(context.timestamp_ms, int) or not isinstance(symbol, str) or not symbol:
            return self._no_trade("invalid_input", context if isinstance(context, MarketContext) else MarketContext("?", Decimal("1"), 1, "UNKNOWN"))

        # Validate review threshold
        thr = self._valid_threshold(complexity_threshold)
        if thr is None:
            return self._no_trade("invalid_input", context)

        try:
            decision = self.analyst.analyze(context, self.open_positions)
        except Exception:
            return self._no_trade("ai_unavailable", context)

        decision = self._validate_decision(decision, context)
        if decision.kind == DecisionKind.NO_TRADE:
            return self._persist_and_return(decision, context, write_journal=True)

        if self._needs_review(decision, thr):
            try:
                reviewed = self.reviewer.review(decision, "complex_case")
            except Exception:
                return self._no_trade("reviewer_unavailable", context)
            decision = self._validate_decision(reviewed, context)
            if decision.kind == DecisionKind.NO_TRADE:
                return self._persist_and_return(decision, context, write_journal=True)

        if decision.kind in (DecisionKind.CLOSE, DecisionKind.MODIFY_STOP):
            decision.kind = DecisionKind.NO_TRADE
            decision.status = ProposalStatus.REJECTED
            decision.rationale = "close_modify_not_executable_r1"
            decision.proposal = None
            return self._persist_and_return(decision, context, write_journal=True)

        if decision.kind == DecisionKind.OPEN:
            decision = self._apply_risk_gate(decision, context)
            if decision.kind != DecisionKind.OPEN or decision.status != ProposalStatus.APPROVED:
                return self._persist_and_return(decision, context, write_journal=True)

            # Policy mandate required
            if not self._mandate_ok():
                decision.kind = DecisionKind.NO_TRADE
                decision.status = ProposalStatus.REJECTED
                decision.rationale = "policy_not_authorized"
                return self._persist_and_return(decision, context, write_journal=True)

            if not isinstance(self.journal, EventJournal):
                decision.kind = DecisionKind.NO_TRADE
                decision.status = ProposalStatus.REJECTED
                decision.rationale = "missing_journal"
                return self._persist_and_return(decision, context, write_journal=False)

            eid = self._append_durable(decision, context)
            if not eid:
                decision.kind = DecisionKind.NO_TRADE
                decision.status = ProposalStatus.REJECTED
                decision.rationale = "journal_persist_failed"
                return self._persist_and_return(decision, context, write_journal=False)
            decision.journal_event_id = _safe_event_id(eid)
            # Already written; do not write again
            return self._persist_and_return(decision, context, write_journal=False)

        return self._persist_and_return(decision, context, write_journal=True)

    def _valid_threshold(self, thr: Any) -> Optional[float]:
        if type(thr) is not float:
            return None
        if thr != thr or not (0.0 <= thr <= 1.0):
            return None
        return thr

    def _mandate_ok(self) -> bool:
        m = self.policy_mandate
        if not isinstance(m, dict):
            return False
        if m.get("approved") is not True:
            return False
        if not isinstance(m.get("version"), str) or not m.get("version"):
            return False
        # External verifier required — self-attestation is not enough
        if self.policy_verifier is None or not callable(self.policy_verifier):
            return False
        try:
            result = self.policy_verifier(m, self.risk_policy)
            if result is not True:  # strict boolean
                return False
        except Exception:
            return False
        # Scope: must be explicitly brain portfolio and matching run
        if m.get("portfolio_id") != "brain":
            return False
        if m.get("run_id") != self.run_id:
            return False
        # Operator identity required
        if not isinstance(m.get("approved_by"), str) or not m.get("approved_by"):
            return False
        # Must bind to the exact policy hash
        expected = _policy_hash(self.risk_policy)
        if m.get("policy_hash") != expected:
            return False
        return True

    def _no_trade(self, code: str, context: MarketContext) -> BrainDecision:
        d = BrainDecision(
            kind=DecisionKind.NO_TRADE,
            rationale=code if code in _ALLOWED_RATIONALE else "invalid_input",
            sources=["engine:fail_closed"],
            occurred_at_ms=getattr(context, "timestamp_ms", 0),
            status=ProposalStatus.REJECTED,
        )
        return self._persist_and_return(d, context, write_journal=True)

    def _sanitize_sources(self, sources: Any) -> list[str]:
        if not isinstance(sources, list):
            return []
        return [s for s in sources if isinstance(s, str) and s in _ALLOWED_SOURCES]

    def _sanitize_rationale(self, rationale: Any) -> str:
        if not isinstance(rationale, str) or rationale not in _ALLOWED_RATIONALE:
            return "sanitized"
        return rationale

    def _validate_decision(self, decision: Any, context: MarketContext) -> BrainDecision:
        if decision is None or not isinstance(decision, BrainDecision):
            return BrainDecision(
                kind=DecisionKind.NO_TRADE,
                rationale="malformed_output",
                sources=["engine:validate"],
                occurred_at_ms=context.timestamp_ms,
                status=ProposalStatus.REJECTED,
            )
        decision.sources = self._sanitize_sources(decision.sources)
        decision.rationale = self._sanitize_rationale(decision.rationale)
        if decision.status == ProposalStatus.EXECUTED_PAPER:
            decision.status = ProposalStatus.REJECTED
            decision.kind = DecisionKind.NO_TRADE
            decision.rationale = "malformed_output"
        if not isinstance(decision.kind, DecisionKind):
            decision.kind = DecisionKind.NO_TRADE
            decision.status = ProposalStatus.REJECTED
            decision.rationale = "malformed_output"
        # Matrix: only OPEN may be APPROVED; strip proposal from non-actionable
        if decision.kind != DecisionKind.OPEN:
            decision.proposal = None
            if decision.status == ProposalStatus.APPROVED:
                decision.status = ProposalStatus.REJECTED
                decision.rationale = "malformed_output"
        if decision.kind == DecisionKind.OPEN and isinstance(decision.proposal, OpenProposal):
            # Reconstruct proposal with only validated fields
            prop = decision.proposal
            # Rationale: only allowlisted strings
            rat = prop.rationale if isinstance(prop.rationale, str) and prop.rationale in _ALLOWED_RATIONALE else "sanitized"
            # Origin: only allowlisted strings
            origin = prop.originating_ai if isinstance(prop.originating_ai, str) and prop.originating_ai in _ALLOWED_ORIGINS else None
            # Context hash: only allow short hex or None
            ctx_hash = prop.context_hash if isinstance(prop.context_hash, str) and len(prop.context_hash) <= 64 and all(c in "0123456789abcdef" for c in prop.context_hash) else None
            decision.proposal = replace(prop, rationale=rat, originating_ai=origin or "sanitized", context_hash=ctx_hash)
            if origin is None:
                decision.kind = DecisionKind.NO_TRADE
                decision.status = ProposalStatus.REJECTED
                decision.rationale = "malformed_output"
            # Timestamp must match context
            if decision.occurred_at_ms != context.timestamp_ms:
                decision.kind = DecisionKind.NO_TRADE
                decision.status = ProposalStatus.REJECTED
                decision.rationale = "malformed_output"
            if decision.proposal.symbol != context.symbol:
                decision.kind = DecisionKind.NO_TRADE
                decision.status = ProposalStatus.REJECTED
                decision.rationale = "symbol_mismatch"
            conf = _finite(decision.proposal.confidence)
            if conf is None or not (Decimal("0") <= conf <= Decimal("1")):
                decision.kind = DecisionKind.NO_TRADE
                decision.status = ProposalStatus.REJECTED
                decision.rationale = "invalid_input"
            entry = _finite(decision.proposal.entry_price)
            if entry is None or entry <= 0:
                decision.kind = DecisionKind.NO_TRADE
                decision.status = ProposalStatus.REJECTED
                decision.rationale = "invalid_input"
            else:
                rel = abs(entry - context.price) / context.price
                if rel > _MAX_ENTRY_DIVERGENCE:
                    decision.kind = DecisionKind.NO_TRADE
                    decision.status = ProposalStatus.REJECTED
                    decision.rationale = "price_divergence"
        return decision

    def _apply_risk_gate(self, decision: BrainDecision, context: MarketContext) -> BrainDecision:
        if not isinstance(decision.proposal, OpenProposal):
            decision.kind = DecisionKind.NO_TRADE
            decision.status = ProposalStatus.RISK_REJECTED
            decision.rationale = "invalid_input"
            return decision

        mp = self.market_params
        required = ("exchange_leverage_limit", "quantity_step", "minimum_notional", "maintenance_fraction", "market_data_fresh", "paused", "daily_loss_latched")
        if any(k not in mp for k in required):
            decision.kind = DecisionKind.NO_TRADE
            decision.status = ProposalStatus.RISK_REJECTED
            decision.rationale = "invalid_input"
            return decision
        if type(mp["paused"]) is not bool or type(mp["daily_loss_latched"]) is not bool or type(mp["market_data_fresh"]) is not bool:
            decision.kind = DecisionKind.NO_TRADE
            decision.status = ProposalStatus.RISK_REJECTED
            decision.rationale = "invalid_input"
            return decision

        if self.risk_policy is None or self.portfolio_snapshot is None:
            decision.kind = DecisionKind.NO_TRADE
            decision.status = ProposalStatus.RISK_REJECTED
            decision.rationale = "invalid_input"
            return decision

        nums = {
            "floor": _finite(self.risk_policy.minimum_equity),
            "equity": _finite(self.portfolio_snapshot.equity),
            "cash": _finite(self.portfolio_snapshot.available_cash),
            "margin": _finite(self.portfolio_snapshot.margin_used),
            "open_risk": _finite(self.portfolio_snapshot.existing_open_risk),
            "entry": _finite(decision.proposal.entry_price),
            "stop": _finite(decision.proposal.stop_price),
            "step": _finite(mp["quantity_step"]),
            "min_notional": _finite(mp["minimum_notional"]),
            "maint": _finite(mp["maintenance_fraction"]),
        }
        if any(v is None for v in nums.values()):
            decision.kind = DecisionKind.NO_TRADE
            decision.status = ProposalStatus.RISK_REJECTED
            decision.rationale = "invalid_input"
            return decision
        if nums["floor"] < Decimal("450"):
            decision.kind = DecisionKind.NO_TRADE
            decision.status = ProposalStatus.RISK_REJECTED
            decision.rationale = "invalid_input"
            return decision

        # P1: early-return for locked/stale state (defense-in-depth, independent of F1)
        if mp["paused"] or not mp["market_data_fresh"] or mp["daily_loss_latched"]:
            decision.kind = DecisionKind.NO_TRADE
            decision.status = ProposalStatus.RISK_REJECTED
            decision.rationale = "market_gate"
            return decision

        try:
            request = RiskRequest(
                equity=nums["equity"],
                available_cash=nums["cash"],
                margin_used=nums["margin"],
                existing_open_risk=nums["open_risk"],
                entry_price=nums["entry"],
                stop_price=nums["stop"],
                side=decision.proposal.side,
                requested_leverage=decision.proposal.leverage,
                exchange_leverage_limit=mp["exchange_leverage_limit"],
                quantity_step=nums["step"],
                minimum_notional=nums["min_notional"],
                maintenance_fraction=nums["maint"],
                market_data_fresh=mp["market_data_fresh"],
                paused=mp["paused"],
                daily_loss_latched=mp["daily_loss_latched"],
            )
            quote = quote_paper_risk(self.risk_policy, request)
            decision.risk_quote = quote
            if not quote.allowed:
                decision.kind = DecisionKind.NO_TRADE
                decision.status = ProposalStatus.RISK_REJECTED
                decision.rationale = "risk_rejected"
            else:
                decision.status = ProposalStatus.APPROVED
                decision.rationale = "risk_quote_ok"
        except Exception as exc:
            logger.error("quote_paper_risk failed: %s", type(exc).__name__)
            decision.kind = DecisionKind.NO_TRADE
            decision.status = ProposalStatus.RISK_REJECTED
            decision.rationale = "risk_rejected"
            decision.risk_quote = None
        return decision

    def _append_durable(self, decision: BrainDecision, context: MarketContext) -> Optional[str]:
        if not isinstance(self.journal, EventJournal) or Event is None:
            return None
        eid = _request_id(self.run_id, context.timestamp_ms, context.symbol, decision.proposal)
        claim = uuid.uuid4().hex
        try:
            event = Event(
                event_id=eid,
                portfolio_id="brain",
                run_id=self.run_id,
                kind="brain_decision",
                occurred_at_ms=context.timestamp_ms,
                source="brain_f2_engine",
                payload={
                    "kind": decision.kind.value,
                    "status": decision.status.value,
                    "rationale": decision.rationale,
                    "sources": self._sanitize_sources(decision.sources),
                    "claim": claim,
                    "symbol": _safe_symbol(getattr(context, "symbol", None)),
                    "regime": _safe_regime(getattr(context, "regime", None)),
                },
            )
            stored = self.journal.append(event)
            after = self.journal.list_run("brain", self.run_id)
            match = [r for r in after if r.event.event_id == eid]
            if not match or match[0].event.payload.get("claim") != claim:
                return None
            return eid
        except Exception:
            return None

    def _normalize(self, decision: BrainDecision) -> BrainDecision:
        """Single boundary: rebuild a clean decision before return/memory/journal."""
        # Kind must be enum
        kind = decision.kind if isinstance(decision.kind, DecisionKind) else DecisionKind.NO_TRADE
        # Status must be enum
        status = decision.status if isinstance(decision.status, ProposalStatus) else ProposalStatus.REJECTED
        # Matrix: only OPEN can be APPROVED
        if kind != DecisionKind.OPEN:
            status = ProposalStatus.REJECTED if status == ProposalStatus.APPROVED else status
        # Strip proposal and risk_quote from non-actionable
        proposal = decision.proposal if kind == DecisionKind.OPEN and status == ProposalStatus.APPROVED else None
        risk_quote = decision.risk_quote if kind == DecisionKind.OPEN and status == ProposalStatus.APPROVED else None
        # Rationale allowlist
        rationale = decision.rationale if isinstance(decision.rationale, str) and decision.rationale in _ALLOWED_RATIONALE else "sanitized"
        # Sources allowlist
        sources = self._sanitize_sources(decision.sources)
        return BrainDecision(
            kind=kind,
            proposal=proposal,
            risk_quote=risk_quote,
            rationale=rationale,
            sources=sources,
            occurred_at_ms=decision.occurred_at_ms if isinstance(decision.occurred_at_ms, int) else 0,
            status=status,
            journal_event_id=_safe_event_id(getattr(decision, "journal_event_id", None)),
        )

    def _persist_and_return(self, decision: BrainDecision, context: MarketContext, write_journal: bool = True) -> BrainDecision:
        decision = self._normalize(decision)
        episode = MemoryEpisode(
            episode_id=f"brain-{self.cycle}-{context.timestamp_ms}",
            decision=decision,
            provenance=decision.sources + [f"cycle:{self.cycle}"],
        )
        self.memory.append(episode)
        if write_journal and isinstance(self.journal, EventJournal):
            self._append_durable(decision, context)
        return decision

    def _needs_review(self, decision: BrainDecision, threshold: float) -> bool:
        if decision.kind == DecisionKind.NO_TRADE:
            return False
        conf = getattr(decision.proposal, "confidence", 1.0) if decision.proposal else 1.0
        try:
            conf_f = float(conf)
            if conf_f != conf_f:
                return True
        except (TypeError, ValueError):
            return True
        return conf_f < threshold or "regime_change" in (decision.rationale or "")

    def _reevaluate_positions(self, context: MarketContext, decision: BrainDecision) -> BrainDecision:
        """Minimal reevaluation: review open positions and journal the outcome."""
        if not self.open_positions:
            return decision
        try:
            for pos in self.open_positions:
                reviewed = self.reviewer.review(decision, f"reevaluate:{pos.get('id', '?')}")
                if isinstance(self.journal, EventJournal):
                    self._append_durable(reviewed, context)
        except Exception as exc:
            logger.error("reevaluate failed: %s", type(exc).__name__)
        return decision

    def propose_adaptive_strategy(self, regime: str) -> dict:
        return {
            "type": "adaptive_proposal",
            "regime": regime,
            "status": "requires_evaluation",
            "note": "Non promuovere a operativo senza walk-forward e OK utente",
        }
