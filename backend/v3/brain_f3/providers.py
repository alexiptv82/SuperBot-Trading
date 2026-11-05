"""DeepSeek/Claude *offline transport boundaries* for Brain F2.

No HTTP client, credentials, background scheduler, position execution or live
provider call is instantiated here. Every invocation requires explicit opt-in,
an external spending gate, and an injected transport (mocked in tests).
Untrusted model text is never carried into decision rationale or journal.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from typing import Any, Callable, Mapping

from backend.v3.brain_f2.analyst import Analyst
from backend.v3.brain_f2.reviewer import Reviewer
from backend.v3.brain_f2.contracts import (
    BrainDecision, DecisionKind, OpenProposal, ProposalStatus, MarketContext,
)


class ProviderUnavailable(RuntimeError):
    """Generic failure; never contain credentials, response bodies or URLs."""


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    body: Mapping[str, Any]


Transport = Callable[[Mapping[str, Any]], TransportResponse]
SpendingGate = Callable[[str], bool]


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate_json_key")
        out[k] = v
    return out


def _json_object(text: Any) -> dict:
    if type(text) is not str or len(text) > 4096 or not text.strip():
        raise ProviderUnavailable("invalid_model_output")
    try:
        out = json.loads(text, object_pairs_hook=_unique_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError) as exc:
        raise ProviderUnavailable("invalid_model_output") from None
    if type(out) is not dict:
        raise ProviderUnavailable("invalid_model_output")
    return out


def _safe_str(value: Any, *, max_len: int = 128) -> bool:
    return type(value) is str and 0 < len(value) <= max_len and all(32 <= ord(c) < 127 for c in value)


def _bounded_decimal(value: Any) -> Decimal:
    if type(value) not in (int, str) or (type(value) is str and len(value) > 50):
        raise ValueError("invalid_decimal")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid_decimal") from exc
    if not d.is_finite() or d <= 0:
        raise ValueError("invalid_decimal")
    return d


def _call(transport: Transport, budget_gate: SpendingGate | None,
          provider: str, model: str, enabled: bool, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if (enabled is not True or not _safe_str(model)
            or budget_gate is None or not callable(budget_gate)
            or not callable(transport)):
        raise ProviderUnavailable("provider_disabled")
    try:
        if budget_gate(provider) is not True:
            raise ProviderUnavailable("budget_denied")
        result = transport(payload)
    except Exception:
        raise ProviderUnavailable("provider_unavailable") from None
    if (not isinstance(result, TransportResponse) or type(result.status_code) is not int
            or result.status_code != 200 or not isinstance(result.body, Mapping)):
        raise ProviderUnavailable("provider_unavailable")
    return result.body


class DeepSeekAnalystAdapter(Analyst):
    def __init__(self, *, transport: Transport, model: str,
                 spending_gate: SpendingGate | None = None, enabled: bool = False):
        self.transport, self.model = transport, model
        self.spending_gate, self.enabled = spending_gate, enabled

    def analyze(self, context: MarketContext, open_positions: list[Mapping]) -> BrainDecision:
        if (not isinstance(context, MarketContext) or not _safe_str(context.symbol)
                or not _safe_str(context.regime) or type(context.timestamp_ms) is not int
                or context.timestamp_ms <= 0):
            raise ProviderUnavailable("invalid_market")
        try:
            price = _bounded_decimal(str(context.price))
        except ValueError:
            raise ProviderUnavailable("invalid_market") from None
        # Deliberately do not expose wallets/positions, credentials or free-form signals.
        info = {"symbol": context.symbol, "price": str(price),
                "timestamp_ms": context.timestamp_ms, "regime": context.regime,
                "open_position_count": len(open_positions)}
        payload = {"model": self.model, "stream": False, "max_tokens": 256,
                   "response_format": {"type": "json_object"},
                   "messages": [
                       {"role": "system", "content": (
                           'Return only JSON {"kind":"NO_TRADE"} or '
                           '{"kind":"OPEN","side":1 or -1,"entry_price":"100",'
                           '"stop_price":"99","leverage":2,"confidence":0.7}. '
                           'No tools, no market orders, no execution authority.')},
                       {"role": "user", "content": json.dumps(info, sort_keys=True)},
                   ]}
        body = _call(self.transport, self.spending_gate, "deepseek", self.model,
                     self.enabled, payload)
        try:
            choices = body["choices"]
            choice = choices[0]
            if (type(choices) is not list or len(choices) != 1
                    or choice["finish_reason"] != "stop"):
                raise ValueError()
            obj = _json_object(choice["message"]["content"])
            kind = obj.get("kind")
            if kind == "NO_TRADE" and set(obj) == {"kind"}:
                return BrainDecision(DecisionKind.NO_TRADE, rationale="deepseek:analysis",
                                     sources=["deepseek:analysis"], occurred_at_ms=context.timestamp_ms)
            if (kind != "OPEN" or set(obj) != {"kind", "side", "entry_price",
                                               "stop_price", "leverage", "confidence"}
                    or type(obj["side"]) is not int or obj["side"] not in (-1, 1)
                    or type(obj["leverage"]) is not int or not 1 <= obj["leverage"] <= 100
                    or type(obj["confidence"]) not in (float, int)
                    or not math.isfinite(obj["confidence"])
                    or not 0 <= obj["confidence"] <= 1):
                raise ValueError()
            proposal = OpenProposal(
                symbol=context.symbol, side=obj["side"],
                entry_price=_bounded_decimal(obj["entry_price"]),
                stop_price=_bounded_decimal(obj["stop_price"]),
                leverage=obj["leverage"], rationale="deepseek:analysis",
                confidence=float(obj["confidence"]), originating_ai="deepseek",
                context_hash=hashlib.sha256(json.dumps(info, sort_keys=True).encode()).hexdigest(),
            )
            return BrainDecision(DecisionKind.OPEN, proposal=proposal,
                                 rationale="deepseek:analysis", sources=["deepseek:analysis"],
                                 occurred_at_ms=context.timestamp_ms)
        except Exception:
            raise ProviderUnavailable("invalid_model_output") from None


class ClaudeReviewerAdapter(Reviewer):
    def __init__(self, *, transport: Transport, model: str,
                 spending_gate: SpendingGate | None = None, enabled: bool = False):
        self.transport, self.model = transport, model
        self.spending_gate, self.enabled = spending_gate, enabled

    def review(self, decision: BrainDecision, complexity_reason: str) -> BrainDecision:
        proposal = getattr(decision, "proposal", None)
        if (not isinstance(decision, BrainDecision) or decision.kind != DecisionKind.OPEN
                or not isinstance(proposal, OpenProposal)
                or not _safe_str(proposal.symbol)):
            raise ProviderUnavailable("invalid_candidate")
        summary = {"symbol": proposal.symbol, "side": proposal.side,
                   "entry_price": str(proposal.entry_price),
                   "stop_price": str(proposal.stop_price),
                   "leverage": proposal.leverage}
        payload = {"model": self.model, "max_tokens": 128,
                   "system": ('Review a non-executable synthetic trading proposal. '
                              'Return only JSON {"verdict":"APPROVE"} or '
                              '{"verdict":"REJECT"}. No orders or tools.'),
                   "messages": [{"role": "user", "content": json.dumps(summary, sort_keys=True)}]}
        body = _call(self.transport, self.spending_gate, "claude", self.model,
                     self.enabled, payload)
        try:
            if body["stop_reason"] != "end_turn":
                raise ValueError()
            blocks = body["content"]
            if type(blocks) is not list or len(blocks) != 1 or blocks[0]["type"] != "text":
                raise ValueError()
            obj = _json_object(blocks[0]["text"])
            if set(obj) != {"verdict"} or obj["verdict"] not in ("APPROVE", "REJECT"):
                raise ValueError()
        except Exception:
            raise ProviderUnavailable("invalid_model_output") from None
        if obj["verdict"] == "APPROVE":
            # Approval is review-only: F2 must *still* apply risk, signed policy and journal.
            decision.status = ProposalStatus.DRAFT
            decision.rationale = "claude:review"
            decision.sources = ["deepseek:analysis", "claude:review"]
        else:
            decision.kind = DecisionKind.NO_TRADE
            decision.status = ProposalStatus.REJECTED
            decision.proposal = None
            decision.risk_quote = None
            decision.rationale = "claude:review"
            decision.sources = ["deepseek:analysis", "claude:review"]
        return decision
