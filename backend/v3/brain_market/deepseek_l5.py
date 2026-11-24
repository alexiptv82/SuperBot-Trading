"""L5 transport boundary; intentionally reuse F3 private helpers without changing F3.

Only injected bars, outcomes, transport and spending gate; never network or runtime I/O.
Model text never becomes rationale, sources or journal content.
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
from backend.v3.brain_market.params import MarketViewParams
from backend.v3.brain_market.view import build_market_view
from backend.v3.outcomes import REGIMES

SYSTEM_PROMPT = 'Return only JSON. Either {"kind":"NO_TRADE"} or {"kind":"OPEN","side":1 or -1,"entry_price":"100","stop_price":"99","leverage":2,"confidence":0.7,"strategy_id":"S07","strategy_origin":"library"}. strategy_id is an id from the strategies list (strategy_origin library) or your own name starting with AI_ (strategy_origin ai_proposed). The market object gives, for each timeframe, indicators computed on closed candles only: distances are in basis points of the last close, atr_bp is the average true range, regime is the classifier label. A timeframe whose status is not ok has no data. The scoreboard shows the measured net result, in basis points after costs, of your own past closed trades in the current regime, per strategy and side. Status positive or negative means measured with confidence. Status inconclusive or insufficient means not yet known, not bad. Choose a strategy whose conditions the market shows, prefer strategies measured positive, avoid those measured negative, and you may try unmeasured ones to learn. No tools, no market orders, no execution authority.'


class DeepSeekL5Analyst(Analyst):
    """L5 PAPER analyst with market view and L4 scoreboard, no execution authority."""

    def __init__(self, *, transport: Transport, model: str, outcomes_source,
                 bars_source, view_params: ViewParams, market_params: MarketViewParams,
                 menu: tuple[MenuItem, ...], spending_gate: SpendingGate | None = None,
                 enabled: bool = False, max_tokens: int = 256):
        if type(max_tokens) is not int or not 1 <= max_tokens <= 65_536:
            raise ValueError("invalid_max_tokens") from None
        if type(view_params) is not ViewParams:
            raise ValueError("invalid_params") from None
        if type(market_params) is not MarketViewParams:
            raise ValueError("invalid_market_params") from None
        self.allowed_strategy_ids = menu_ids(menu)
        self.transport, self.model = transport, model
        self.outcomes_source, self.bars_source = outcomes_source, bars_source
        self.view_params, self.market_params = view_params, market_params
        self.menu, self.spending_gate, self.enabled = menu, spending_gate, enabled
        self.max_tokens = max_tokens

    def analyze(self, context: MarketContext, open_positions: list[Mapping]) -> BrainDecision:
        if (not isinstance(context, MarketContext) or not _safe_str(context.symbol)
                or not _safe_str(context.regime) or context.regime not in REGIMES
                or type(context.timestamp_ms) is not int or context.timestamp_ms <= 0):
            raise ProviderUnavailable("invalid_market") from None
        try:
            price = _bounded_decimal(str(context.price))
            count = len(open_positions)
        except Exception:
            raise ProviderUnavailable("invalid_market") from None
        if self.enabled is not True:
            raise ProviderUnavailable("provider_disabled") from None
        try:
            market = build_market_view(self.bars_source(context.symbol),
                                       timestamp_ms=context.timestamp_ms,
                                       params=self.market_params)
        except Exception:
            raise ProviderUnavailable("invalid_market_view") from None
        base = next(t for t in market["timeframes"] if t["tf"] == market["base_tf"])
        if base["status"] != "ok":
            raise ProviderUnavailable("market_data_unavailable") from None
        if context.regime != market["regime"]:
            raise ProviderUnavailable("regime_mismatch") from None
        try:
            scoreboard = build_scoreboard(self.outcomes_source(), regime=context.regime,
                                          params=self.view_params)
        except Exception:
            raise ProviderUnavailable("invalid_scoreboard") from None
        info = {
            "symbol": context.symbol, "price": str(price),
            "timestamp_ms": context.timestamp_ms, "regime": context.regime,
            "open_position_count": count, "market": market,
            "scoreboard": scoreboard, "strategies": menu_payload(self.menu),
        }
        info_json = json.dumps(info, sort_keys=True)
        payload = {
            "model": self.model, "stream": False, "max_tokens": self.max_tokens,
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
            keys = {"kind", "side", "entry_price", "stop_price", "leverage", "confidence"}
            labelled_keys = keys | {"strategy_id", "strategy_origin"}
            if (obj.get("kind") != "OPEN" or set(obj) not in (keys, labelled_keys)
                    or type(obj["side"]) is not int or obj["side"] not in (-1, 1)
                    or type(obj["leverage"]) is not int or not 1 <= obj["leverage"] <= 100
                    or type(obj["confidence"]) not in (float, int)
                    or not math.isfinite(obj["confidence"])
                    or not 0 <= obj["confidence"] <= 1):
                raise ValueError()
            labelled = set(obj) == labelled_keys
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
