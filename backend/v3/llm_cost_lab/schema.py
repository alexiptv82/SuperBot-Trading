"""Schema della risposta. Un JSON incompleto non è un segnale."""
from __future__ import annotations

import json
import math
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional


def parse_decision(content: str) -> dict:
    """LONG, SHORT o NO_TRADE. Ogni altro testo è invalido e non autorizzato."""
    try:
        obj = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("invalid_json") from None
    if type(obj) is not dict:
        raise ValueError("invalid_schema")
    if obj.get("kind") == "NO_TRADE" and set(obj) == {"kind"}:
        return {
            "action": "NO_TRADE",
            "direction": None,
            "valid": True,
            "reported_confidence_unverified": None,
        }
    keys = {"kind", "side", "entry_price", "stop_price", "leverage", "confidence"}
    labelled = keys | {"strategy_id", "strategy_origin"}
    if obj.get("kind") != "OPEN" or set(obj) not in (keys, labelled):
        raise ValueError("invalid_schema")
    side = obj.get("side")
    if side == 1:
        direction = "LONG"
    elif side == -1:
        direction = "SHORT"
    else:
        raise ValueError("invalid_schema")
    confidence = obj.get("confidence")
    if type(confidence) not in (int, float) or isinstance(confidence, bool):
        raise ValueError("invalid_schema")
    if not math.isfinite(float(confidence)) or not 0 <= float(confidence) <= 1:
        raise ValueError("invalid_schema")
    leverage = obj.get("leverage")
    if type(leverage) is not int or not 1 <= leverage <= 100:
        raise ValueError("invalid_schema")
    for price_key in ("entry_price", "stop_price"):
        if type(obj.get(price_key)) is not str or not obj[price_key]:
            raise ValueError("invalid_schema")
    if set(obj) == labelled:
        for label in ("strategy_id", "strategy_origin"):
            text = obj.get(label)
            if type(text) is not str or not text.isascii() or not 1 <= len(text) <= 64:
                raise ValueError("invalid_schema")
    proposal = {}
    for price_key in ("entry_price", "stop_price"):
        try:
            number = Decimal(obj[price_key])
        except (InvalidOperation, ValueError):
            raise ValueError("invalid_schema") from None
        if not number.is_finite() or number <= 0:
            raise ValueError("invalid_schema")
        proposal[price_key] = format(number, "f")
    proposal["leverage"] = leverage
    # Come in produzione: l'analista accetta, il motore di rischio rifiuta (stop_wrong_side). Qui lo si registra.
    right_side = (direction == "LONG") == (Decimal(proposal["stop_price"]) < Decimal(proposal["entry_price"]))
    proposal["executable"] = right_side
    proposal["not_executable_reason"] = None if right_side else "stop_wrong_side"
    return {
        "action": direction,
        "direction": direction,
        "valid": True,
        # Il numero arriva dal modello: non è una confidenza verificata.
        "reported_confidence_unverified": None,
        # Registrata solo per etichettarla dopo con esiti di mercato; non e' mai un ordine.
        "proposal": proposal,
    }


def chat_content(body: Mapping[str, Any]) -> str:
    choices = body.get("choices")
    if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
        raise ValueError("invalid_schema")
    if choices[0].get("finish_reason") != "stop":
        raise ValueError("invalid_schema")
    message = choices[0].get("message")
    if type(message) is not dict or type(message.get("content")) is not str:
        raise ValueError("invalid_schema")
    return message["content"]


def token_pair(body: Optional[Mapping[str, Any]]) -> tuple[Optional[int], Optional[int]]:
    if not isinstance(body, Mapping):
        return None, None
    usage = body.get("usage")
    if type(usage) is not dict:
        return None, None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if type(prompt) is int and type(completion) is int and prompt >= 0 and completion >= 0:
        return prompt, completion
    return None, None
