"""Qwen/MiniMax L5 PAPER analyst, reused from the *same* DeepSeek market pipeline.

No runner wiring or API requests when imported. Each analyst receives exactly
its own isolated journal outcomes, market snapshots and provider-specific
transport from the future Arena launcher. No orders, trade authority, retry or
AI-to-AI fallback. Reasoning and output format require real-provider validation
before any 14-day PAPER experiment can start.
"""
from __future__ import annotations

import re
from typing import Any

from backend.v3.arena.openrouter_transport import (
    MODELS, ARENA_SCHEMA_PROPERTIES, ARENA_RESPONSE_FORMAT, ARENA_JSON_OBJECT_FORMAT,
)
from backend.v3.brain_market.deepseek_l5 import DeepSeekL5Analyst, SYSTEM_PROMPT

_Neutral_NO_TRADE = {
    "kind": "NO_TRADE", "side": 0, "entry_price": "0",
    "stop_price": "0", "leverage": 0, "confidence": 0,
    "strategy_id": "", "strategy_origin": "",
}
ARENA_SYSTEM_PROMPT = (
    "Return valid JSON only, with exactly the eight required fields. "
    + SYSTEM_PROMPT[SYSTEM_PROMPT.index("The market object"):]
    + " JSON SCHEMA CONTRACT: return exactly all eight required fields. "
    "For NO_TRADE use kind=NO_TRADE, side=0, entry_price='0', "
    "stop_price='0', leverage=0, confidence=0, strategy_id='', "
    "strategy_origin=''. For OPEN use kind=OPEN, side=1 or -1, "
    "positive decimal prices as strings, integer leverage between 1 and 100, "
    "confidence 0..1; the strategy pair can both be empty, or match an "
    "allowed library strategy, or an AI_ proposed strategy. "
    "Do not hallucinate missing market features. Never output tools or orders."
)


class ArenaL5Analyst(DeepSeekL5Analyst):
    """Provider-labelled analyst; default disabled even with a fake transport."""

    def __init__(
        self, *, provider: str, run_id: str,
        model: str, enabled: bool = False, reasoning_mode: str = "omit",
        max_tokens: int = 2048, **kwargs: Any,
    ):
        if (type(provider) is not str or provider not in MODELS
                or model != MODELS[provider]
                or type(run_id) is not str or re.fullmatch(
                    r"brain-" + provider + r"-paper[0-9]{8}", run_id,
                ) is None
                or type(enabled) is not bool
                or type(max_tokens) is not int or not 1024 <= max_tokens <= 8192
                or reasoning_mode not in ("omit", "disabled")
                or (provider == "minimax" and reasoning_mode == "disabled")):
            raise ValueError("arena_analyst_invalid_scope")
        super().__init__(model=model, enabled=enabled, max_tokens=max_tokens, **kwargs)
        self.arena_provider = provider
        self.arena_run_id = run_id
        self.reasoning_mode = reasoning_mode

    def _identity(self) -> str:
        return self.arena_provider

    def _response_format(self) -> dict:
        return (ARENA_RESPONSE_FORMAT if self.arena_provider == "qwen"
                else ARENA_JSON_OBJECT_FORMAT)

    def _system_prompt(self) -> str:
        return ARENA_SYSTEM_PROMPT

    def _request_extras(self) -> dict:
        if self.arena_provider == "minimax":
            # MiniMax passed json_object with temperature=0 before strict
            # schema routing produced HTTP 400. Keep it separate from Qwen.
            return {"temperature": 0}
        # Qwen supports strict schema. Reasoning-off worked in the prior
        # diagnostic; default reasoning has NOT been certified yet.
        extras: dict = {"provider": {"require_parameters": True}}
        if self.reasoning_mode == "disabled":
            extras["reasoning"] = {"enabled": False}
        return extras

    def _decode_output(self, obj: dict) -> dict:
        """Map strict all-fields schema to historic Brain NO_TRADE/OPEN shape.

        A malformed model response is deliberately *not* repaired into a trade.
        DeepSeekL5Analyst will reject it as invalid_model_output.
        """
        if type(obj) is not dict or set(obj) != set(ARENA_SCHEMA_PROPERTIES):
            raise ValueError("invalid_arena_output")
        if obj["kind"] == "NO_TRADE":
            if obj != _Neutral_NO_TRADE:
                raise ValueError("invalid_arena_no_trade")
            return {"kind": "NO_TRADE"}
        if obj["kind"] != "OPEN":
            raise ValueError("invalid_arena_kind")
        if obj["side"] not in (-1, 1) or type(obj["side"]) is not int:
            raise ValueError("invalid_arena_side")
        if (type(obj["leverage"]) is not int or not 1 <= obj["leverage"] <= 100
                or type(obj["confidence"]) not in (int, float)
                or not 0 <= obj["confidence"] <= 1):
            raise ValueError("invalid_arena_risk_fields")
        sid, sor = obj["strategy_id"], obj["strategy_origin"]
        if type(sid) is not str or type(sor) is not str:
            raise ValueError("invalid_arena_strategy")
        if bool(sid) != bool(sor):
            raise ValueError("invalid_arena_strategy_pair")
        fields = {
            "kind": "OPEN", "side": obj["side"],
            "entry_price": obj["entry_price"], "stop_price": obj["stop_price"],
            "leverage": obj["leverage"], "confidence": obj["confidence"],
        }
        if sid:
            fields.update({"strategy_id": sid, "strategy_origin": sor})
        return fields
