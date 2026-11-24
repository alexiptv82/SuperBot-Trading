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
from backend.v3.brain_market.classic_peers import validate_peer_signal

SYSTEM_PROMPT = 'Return only JSON. Either {"kind":"NO_TRADE"} or {"kind":"OPEN","side":1 or -1,"entry_price":"100","stop_price":"99","leverage":2,"confidence":0.7,"strategy_id":"S07","strategy_origin":"library"}. strategy_id is an id from the strategies list (strategy_origin library) or your own name starting with AI_ (strategy_origin ai_proposed). The market object gives, for each timeframe, indicators computed on closed candles only: distances are in basis points of the last close, atr_bp is the average true range, regime is the classifier label. A timeframe whose status is not ok has no data. The scoreboard shows the measured net result, in basis points after costs, of your own past closed trades in the current regime, per strategy and side. Status positive or negative means measured with confidence. Status inconclusive or insufficient means not yet known, not bad. Choose a strategy whose conditions the market shows, prefer strategies measured positive, avoid those measured negative, and you may try unmeasured ones to learn. If the optional peer_paper_positions field is present, it contains read-only observations of Falco and Toro PAPER positions, NOT recommendations, predictions or orders. A position may be stale or absent. Do not copy a peer trade automatically; derive your own LONG/SHORT/NO_TRADE from verified market data and strategy evidence. No tools, no market orders, no execution authority.'


# Brain unico PAPER (24/11/2026): filosofia operativa aggiunta al prompt solo con ``guidance`` (schema 3). I numeri
# sono quelli della configurazione approvata dal proprietario; la dimensione e la leva le decide il codice.
UNICO_GUIDANCE = (
    'Operating style (single PAPER Brain, 2000 USDT): intraday scalping and short swings on liquid perpetuals, '
    'including gold (XAUUSDT) and silver (XAGUSDT). Treat LONG and SHORT symmetrically: take the side the market '
    'shows. Put the stop where the setup is invalidated, coherent with volatility (atr_bp): scalp stops are often '
    '20 to 60 basis points and first targets 30 to 100, wider only when volatility requires it. Propose a trade only '
    'if the first target is at least 2R away and plausibly reachable within hours. The code sizes the position from '
    'the stop (about 4.3 percent of equity at risk), chooses the leverage between 15x and 50x by itself (your '
    'leverage field is ignored), banks about 35 percent at 2R and manages the rest toward 3.5R with a protective '
    'stop. NO_TRADE is correct when the edge after about 16 bp round-trip costs is unclear. The optional portfolio '
    'object gives the guardian mode (NORMAL = active, SELECTIVE = be pickier, PROTECTED = only exceptional setups) '
    'and the free slots. With OPEN you may add "reasons" (up to 6 codes from: trend_up, trend_down, trend_weakening, '
    'trend_change, breakout, breakdown, pullback, range, momentum_strong, momentum_fading, volume_confirms, '
    'volume_weak, volatility_high, volatility_low, near_support, near_resistance, overextended, conflicting_signals, '
    'reversal_risk, costs_high, funding_adverse, liquidity_thin, risk_concentration, setup_strong, setup_weak) and '
    '"uncertain": true when signals conflict or LONG and SHORT are hard to tell apart; a senior consultant may then '
    'review the trade.')


class DeepSeekL5Analyst(Analyst):
    """L5 PAPER analyst with market view and L4 scoreboard, no execution authority."""

    def __init__(self, *, transport: Transport, model: str, outcomes_source,
                 bars_source, view_params: ViewParams, market_params: MarketViewParams,
                 menu: tuple[MenuItem, ...], spending_gate: SpendingGate | None = None,
                 enabled: bool = False, max_tokens: int = 256, guidance: str | None = None,
                 portfolio_state=None, reasons_parser=None):
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
        self.guidance, self.portfolio_state = guidance, portfolio_state
        # Brain unico: lettore dei motivi a elenco chiuso (iniettato: ``unico.parse_reasons``); None = motivi rifiutati
        self.reasons_parser = reasons_parser

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
        peer_positions = {}
        for key, item in (("falco", context.falco_signal), ("toro", context.toro_signal)):
            valid = validate_peer_signal(item, key, context.symbol, context.timestamp_ms)
            if valid is not None:
                peer_positions[key] = valid
        if peer_positions:
            info["peer_paper_positions"] = peer_positions
        if self.portfolio_state is not None:
            try:
                state = self.portfolio_state()
            except Exception:
                state = None
            if isinstance(state, dict):
                info["portfolio"] = state
        info_json = json.dumps(info, sort_keys=True)
        sources = ["deepseek:analysis"] + [
            key + ":paper_position_observation" for key in ("falco", "toro")
            if key in peer_positions]
        payload = {
            "model": self.model, "stream": False, "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT if self.guidance is None
                 else SYSTEM_PROMPT + " " + self.guidance},
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
            extra_ok = {"reasons", "uncertain"} if self.guidance is not None else set()
            if obj.get("kind") == "NO_TRADE" and {"kind"} <= set(obj) <= {"kind"} | extra_ok:
                return BrainDecision(kind=DecisionKind.NO_TRADE, rationale="deepseek:analysis",
                                     sources=sources,
                                     occurred_at_ms=context.timestamp_ms)
            keys = {"kind", "side", "entry_price", "stop_price", "leverage", "confidence"}
            labelled_keys = keys | {"strategy_id", "strategy_origin"}
            # Brain unico: motivi e incertezza facoltativi, validati su elenco chiuso
            if "reasons" in obj and (self.guidance is None or self.reasons_parser is None):
                raise ValueError()
            reasons = self.reasons_parser(obj.pop("reasons", None)) if self.reasons_parser is not None else ()
            uncertain = obj.pop("uncertain", False) if self.guidance is not None else False
            if type(uncertain) is not bool:
                raise ValueError()
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
                reasons=reasons, uncertain=uncertain,
            )
            return BrainDecision(kind=DecisionKind.OPEN, proposal=proposal,
                                 rationale="deepseek:analysis", sources=sources,
                                 occurred_at_ms=context.timestamp_ms)
        except Exception:
            raise ProviderUnavailable("invalid_model_output") from None
