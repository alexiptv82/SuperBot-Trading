"""Isolated L4 DeepSeek analyst: no network I/O; transport and outcomes injected.

Intentionally reuse internal ``_call``, ``_json_object``, ``_safe_str`` and
``_bounded_decimal`` from brain_f3.providers: modifying that module is forbidden.
Its spending gate and transport are mandatory at invocation, as in F3.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping

from backend.v3.brain_f2.analyst import Analyst
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, OpenProposal
from backend.v3.brain_f3.providers import (
    _call, _json_object, _safe_str, _bounded_decimal,
    ProviderUnavailable, SpendingGate, Transport,
)
from backend.v3.brain_view.params import ViewParams
from backend.v3.brain_view.menu import MenuItem, menu_ids, menu_payload
from backend.v3.brain_view.view import build_scoreboard
from backend.v3.outcomes import REGIMES

SYSTEM_PROMPT = 'Return only JSON. Either {"kind":"NO_TRADE"} or {"kind":"OPEN","side":1 or -1,"entry_price":"100","stop_price":"99","leverage":2,"confidence":0.7,"strategy_id":"S07","strategy_origin":"library"}. strategy_id is an id from the strategies list (strategy_origin library) or your own name starting with AI_ (strategy_origin ai_proposed). The scoreboard shows the measured net result, in basis points after costs, of your own past closed trades in the current regime, per strategy and side. Status positive or negative means measured with confidence. Status inconclusive or insufficient means not yet known, not bad. Prefer strategies measured positive, avoid those measured negative, and you may try unmeasured ones to learn. No tools, no market orders, no execution authority.'


class DeepSeekL4Analyst(Analyst):
    """Decision interface with a journal-derived performance context, PAPER only."""

    def __init__(self, *, transport: Transport, model: str, outcomes_source,
                 params: ViewParams, menu: tuple[MenuItem, ...],
                 spending_gate: SpendingGate | None = None, enabled: bool = False):
        if type(params) is not ViewParams:
            raise ValueError("invalid_params") from None
        self.allowed_strategy_ids = menu_ids(menu)
        self.transport = transport
        self.model = model
        self.outcomes_source = outcomes_source
        self.params = params
        self.menu = menu
        self.spending_gate = spending_gate
        self.enabled = enabled

    def analyze(self, context: MarketContext, open_positions: list[Mapping]) -> BrainDecision:
        if (not isinstance(context, MarketContext) or not _safe_str(context.symbol)
                or not _safe_str(context.regime) or context.regime not in REGIMES
                or type(context.timestamp_ms) is not int or context.timestamp_ms <= 0):
            raise ProviderUnavailable("invalid_market") from None
        try:
            price = _bounded_decimal(str(context.price))
            position_count = len(open_positions)
        except Exception:
            raise ProviderUnavailable("invalid_market") from None
        if self.enabled is not True:
            raise ProviderUnavailable("provider_disabled") from None
        try:
            scoreboard = build_scoreboard(self.outcomes_source(), regime=context.regime,
                                          params=self.params)
        except Exception:
            raise ProviderUnavailable("invalid_scoreboard") from None

        info = {
            "symbol": context.symbol, "price": str(price),
            "timestamp_ms": context.timestamp_ms, "regime": context.regime,
            "open_position_count": position_count, "scoreboard": scoreboard,
            "strategies": menu_payload(self.menu),
        }
        info_json = json.dumps(info, sort_keys=True)
        payload = {
            "model": self.model, "stream": False, "max_tokens": 256,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": info_json},
            ],
        }
        body = _call(self.transport, self.spending_gate, "deepseek", self.model,
                     self.enabled, payload)
        try:
            choices = body["choices"]
            if type(choices) is not list or len(choices) != 1:
                raise ValueError()
            choice = choices[0]
            if choice["finish_reason"] != "stop":
                raise ValueError()
            obj = _json_object(choice["message"]["content"])
            if obj.get("kind") == "NO_TRADE" and set(obj) == {"kind"}:
                return BrainDecision(kind=DecisionKind.NO_TRADE, rationale="deepseek:analysis",
                                     sources=["deepseek:analysis"],
                                     occurred_at_ms=context.timestamp_ms)
            base_keys = {"kind", "side", "entry_price", "stop_price", "leverage", "confidence"}
            with_label = base_keys | {"strategy_id", "strategy_origin"}
            if (obj.get("kind") != "OPEN" or set(obj) not in (base_keys, with_label)
                    or type(obj["side"]) is not int or obj["side"] not in (-1, 1)
                    or type(obj["leverage"]) is not int or not 1 <= obj["leverage"] <= 100
                    or type(obj["confidence"]) not in (float, int)
                    or not math.isfinite(obj["confidence"])
                    or not 0 <= obj["confidence"] <= 1):
                raise ValueError()
            labelled = set(obj) == with_label
            if labelled and (not _safe_str(obj["strategy_id"], max_len=64)
                             or not _safe_str(obj["strategy_origin"], max_len=64)):
                raise ValueError()
            proposal = OpenProposal(
                symbol=context.symbol, side=obj["side"],
                entry_price=_bounded_decimal(obj["entry_price"]),
                stop_price=_bounded_decimal(obj["stop_price"]),
                leverage=obj["leverage"], rationale="deepseek:analysis",
                confidence=float(obj["confidence"]), originating_ai="deepseek",
                context_hash=hashlib.sha256(info_json.encode()).hexdigest(),
                strategy_id=obj["strategy_id"] if labelled else None,
                strategy_origin=obj["strategy_origin"] if labelled else None,
            )
            return BrainDecision(kind=DecisionKind.OPEN, proposal=proposal,
                                 rationale="deepseek:analysis", sources=["deepseek:analysis"],
                                 occurred_at_ms=context.timestamp_ms)
        except Exception:
            raise ProviderUnavailable("invalid_model_output") from None
