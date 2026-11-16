#!/usr/bin/env python3
"""Synthetic OPEN format diagnostic for Qwen and MiniMax, not a trade simulator.

Two immutable fictional examples: Qwen receives LONG 100/99; MiniMax receives
SHORT 100/101. One HTTP model call per provider maximum, with explicit SI.
Never touches orders, Bitget, trading journals, services, or real market data.
The probe only certifies ability to serialize an OPEN example. It does NOT
certify market judgment, risk approval, production inference or profitability.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
import urllib.error
import urllib.request

KEY_FILE = Path("/etc/superbot-brain-ai-arena/openrouter-keys.json")
API_BASE = "https://openrouter.ai/api/v1"
MODELS = {
    "qwen": "qwen/qwen3.7-plus",
    "minimax": "minimax/minimax-m3.1-flash",
}
KEY_LIMIT = Decimal("2")
MIN_KEY_REMAINING = Decimal("0.10")
TOKEN_LIMIT = 1024
BODY_LIMIT = 100_000
VALID_KEY = re.compile(r"sk-or-v1-[A-Za-z0-9_-]{16,}\Z")
COLUMNS = (
    "kind", "side", "entry_price", "stop_price",
    "leverage", "confidence", "strategy_id", "strategy_origin",
)
STRICT = {
    "type": "json_schema",
    "json_schema": {
        "name": "superbot_arena_brain_decision_v1",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["OPEN", "NO_TRADE"]},
                "side": {"type": "integer", "enum": [-1, 0, 1]},
                "entry_price": {"type": "string"},
                "stop_price": {"type": "string"},
                "leverage": {"type": "integer"},
                "confidence": {"type": "number"},
                "strategy_id": {"type": "string"},
                "strategy_origin": {
                    "type": "string", "enum": ["", "library", "ai_proposed"],
                },
            },
            "required": list(COLUMNS),
            "additionalProperties": False,
        },
    },
}


def fictional_open(provider: str) -> dict:
    if provider not in MODELS:
        raise ValueError("UNKNOWN_PROVIDER")
    side = 1 if provider == "qwen" else -1
    return {
        "kind": "OPEN", "side": side,
        "entry_price": "100", "stop_price": "99" if side == 1 else "101",
        "leverage": 20, "confidence": 0.8,
        "strategy_id": "", "strategy_origin": "",
    }


def payload(provider: str) -> dict:
    expected = fictional_open(provider)
    output = {
        "model": MODELS[provider],
        "stream": False,
        "max_completion_tokens": TOKEN_LIMIT,
        "response_format": STRICT if provider == "qwen" else {"type": "json_object"},
        "messages": [
            {"role": "system", "content": (
                "This is a fictional serialization unit test, not a market "
                "analysis. The data below are invented, not live. Do not "
                "access tools or provide financial advice. Reproduce the "
                "provided JSON object exactly with all eight fields. "
                "No additional fields or text."
            )},
            {"role": "user", "content": (
                "SYNTHETIC OPEN CONTRACT TEST ONLY, NOT A TRADE. "
                "Return exactly this JSON object and nothing else: "
                + json.dumps(expected, separators=(",", ":"), sort_keys=True)
            )},
        ],
    }
    if provider == "qwen":
        output["provider"] = {"require_parameters": True}
        output["reasoning"] = {"enabled": False}
    else:
        output["temperature"] = 0
    return output


def validate_response(provider: str, data: dict) -> tuple[str, dict]:
    """Report only fixed issue categories and safe field names, never AI text."""
    if provider not in MODELS or type(data) is not dict:
        return "INVALID_RESULT", {}
    choices = data.get("choices")
    if type(choices) is not list or len(choices) != 1:
        return "INVALID_CHOICES", {}
    choice = choices[0]
    if type(choice) is not dict or type(choice.get("message")) is not dict:
        return "INVALID_MESSAGE", {}
    message = choice["message"]
    usage = data.get("usage") if type(data.get("usage")) is dict else {}
    stop = choice.get("finish_reason")
    meta = {
        "finish_reason": stop if stop in ("stop", "length", "content_filter", None) else "other",
        "model_match": data.get("model") == MODELS[provider],
        "input_tokens": usage.get("prompt_tokens") if type(usage.get("prompt_tokens")) is int else None,
        "output_tokens": usage.get("completion_tokens") if type(usage.get("completion_tokens")) is int else None,
        "reasoning_present": bool(message.get("reasoning") or message.get("reasoning_details")),
    }
    content = message.get("content")
    if type(content) is not str:
        return "MISSING_CONTENT", meta
    try:
        obj = json.loads(content)
    except (ValueError, TypeError):
        return "NOT_JSON", meta
    if type(obj) is not dict:
        return "NOT_OBJECT", meta
    expected = fictional_open(provider)
    meta["missing_fields"] = sorted(set(COLUMNS) - set(obj))
    meta["extra_field_count"] = len(set(obj) - set(COLUMNS))
    typechecks = {
        "kind": str, "side": int, "entry_price": str, "stop_price": str,
        "leverage": int, "confidence": (int, float),
        "strategy_id": str, "strategy_origin": str,
    }
    issues = []
    for name in COLUMNS:
        if name not in obj:
            continue
        acceptable = typechecks[name]
        acceptable = acceptable if type(acceptable) is tuple else (acceptable,)
        if type(obj[name]) not in acceptable:
            issues.append(name + "_TYPE")
        elif obj[name] != expected[name]:
            issues.append(name + "_VALUE")
    meta["field_issues"] = issues
    if meta["missing_fields"] or meta["extra_field_count"] or issues:
        return "OPEN_FORMAT_MISMATCH", meta
    if not meta["model_match"] or stop != "stop":
        return "MODEL_OR_FINISH_MISMATCH", meta
    return "PASS_SYNTHETIC_OPEN_FORMAT", meta


def _money(value: object) -> Decimal:
    if type(value) not in (int, float, str):
        raise ValueError("INVALID_LIMIT")
    try:
        num = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("INVALID_LIMIT") from None
    if not num.is_finite() or num < 0:
        raise ValueError("INVALID_LIMIT")
    return num


def validate_limit(data: dict) -> Decimal:
    detail = data.get("data") if type(data) is dict else None
    if type(detail) is not dict or detail.get("is_management_key"):
        raise ValueError("INVALID_KEY_SCOPE")
    limit = _money(detail.get("limit"))
    remaining = _money(detail.get("limit_remaining"))
    if limit > KEY_LIMIT or remaining < MIN_KEY_REMAINING:
        raise ValueError("KEY_SPENDING_GATE")
    return remaining


def load_keys() -> dict[str, str]:
    if os.geteuid() != 0:
        raise ValueError("ROOT_REQUIRED")
    if KEY_FILE.is_symlink() or KEY_FILE.parent.is_symlink():
        raise ValueError("KEY_PATH_INVALID")
    m, d = KEY_FILE.stat(), KEY_FILE.parent.stat()
    if (not stat.S_ISREG(m.st_mode) or m.st_uid != 0
            or stat.S_IMODE(m.st_mode) != 0o600
            or not stat.S_ISDIR(d.st_mode) or d.st_uid != 0
            or stat.S_IMODE(d.st_mode) != 0o700):
        raise ValueError("KEY_PERMISSIONS_INVALID")
    with KEY_FILE.open(encoding="utf-8") as stream:
        settings = json.load(stream)
    if (type(settings) is not dict
            or settings.get("schema") != "brain_arena_openrouter_keys_v1"
            or settings.get("mode") != "CREDENTIALS_ONLY_NO_INFERENCE"
            or settings.get("base_url") != API_BASE
            or settings.get("models") != MODELS):
        raise ValueError("UNEXPECTED_KEY_CONFIG")
    keys = settings.get("api_keys")
    if (type(keys) is not dict or set(keys) != set(MODELS)
            or any(type(k) is not str or VALID_KEY.fullmatch(k) is None
                   for k in keys.values())
            or keys["qwen"] == keys["minimax"]):
        raise ValueError("INVALID_KEY_PAIR")
    return keys


def http_json(endpoint: str, key: str, body: dict | None = None) -> dict:
    if endpoint not in ("/key", "/chat/completions"):
        raise ValueError("INVALID_ENDPOINT")
    req = urllib.request.Request(
        API_BASE + endpoint,
        method="GET" if body is None else "POST",
        data=None if body is None else json.dumps(
            body, allow_nan=False, ensure_ascii=True,
        ).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key, "Accept": "application/json",
            **({} if body is None else {"Content-Type": "application/json"}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60,
                                    context=ssl.create_default_context()) as resp:
            raw = resp.read(BODY_LIMIT + 1)
    except urllib.error.HTTPError as exc:
        raise ValueError("HTTP_" + str(exc.code)) from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise ValueError("NETWORK_" + type(exc).__name__) from None
    if len(raw) > BODY_LIMIT:
        raise ValueError("RESPONSE_TOO_LARGE")
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        raise ValueError("INVALID_HTTP_JSON") from None
    if type(data) is not dict:
        raise ValueError("INVALID_HTTP_OBJECT")
    return data


def selftest() -> int:
    for provider in MODELS:
        expected = fictional_open(provider)
        response = {"model": MODELS[provider], "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps(expected)},
        }], "usage": {"prompt_tokens": 20, "completion_tokens": 20}}
        assert validate_response(provider, response)[0] == "PASS_SYNTHETIC_OPEN_FORMAT"
        for bad in (
            {**expected, "side": 0},
            {**expected, "leverage": True},
            {**expected, "stop_price": "100"},
            {**expected, "confidence": "0.8"},
            {**expected, "extra": "untrusted"},
        ):
            tampered = dict(response)
            tampered["choices"] = [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(bad)},
            }]
            assert validate_response(provider, tampered)[0] == "OPEN_FORMAT_MISMATCH"
    assert payload("qwen")["response_format"] == STRICT
    assert payload("minimax")["response_format"] == {"type": "json_object"}
    assert "provider" not in payload("minimax")
    assert "reasoning" not in payload("minimax")
    assert validate_limit({"data": {"limit":2,"limit_remaining":"1.9"}}) == Decimal("1.9")
    for invalid in ({"data":{"limit":50,"limit_remaining":40}},
                    {"data":{"limit":2,"limit_remaining":0}},
                    {"data":{"limit":None,"limit_remaining":None}}):
        try:
            validate_limit(invalid)
        except ValueError:
            continue
        raise AssertionError("invalid budget passed")
    print("ARENA_OPEN_FORMAT SELFTEST=PASS_OFFLINE")
    print("ARENA_OPEN_FORMAT api_calls=0 orders=0 services_changed=0")
    return 0


def main() -> int:
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    if sys.argv[1:] != ["--probe"]:
        print("ARENA_OPEN_FORMAT RESULT=NOT_RUN_USE_SELFTEST_OR_PROBE")
        return 2
    try:
        keys = load_keys()
    except (ValueError, OSError, KeyError, TypeError):
        print("ARENA_OPEN_FORMAT RESULT=KEYS_NOT_VERIFIED")
        return 2
    print("=== AI Arena: serialization-only OPEN dry run ===", flush=True)
    print("ARENA_OPEN_FORMAT synthetic_examples_only=YES")
    print("ARENA_OPEN_FORMAT max_billable_requests=2")
    print("ARENA_OPEN_FORMAT no_paper_or_live_orders=YES")
    print("ARENA_OPEN_FORMAT no_journal_or_services_changed=YES")
    try:
        confirmation = input("Autorizzi massimo due richieste API per il SOLO formato OPEN? Scrivi SI: ")
    except (EOFError, KeyboardInterrupt):
        print("\nARENA_OPEN_FORMAT RESULT=CANCELLED")
        return 130
    if confirmation.strip() != "SI":
        print("ARENA_OPEN_FORMAT RESULT=CANCELLED")
        return 0
    successes = 0
    for provider in MODELS:
        try:
            before = validate_limit(http_json("/key", keys[provider]))
            print(f"ARENA_OPEN_FORMAT {provider.upper()}_key_remaining_limit_usd={before}", flush=True)
            result = http_json("/chat/completions", keys[provider], payload(provider))
            outcome, safe_meta = validate_response(provider, result)
            print(f"ARENA_OPEN_FORMAT {provider.upper()}={outcome}", flush=True)
            print(f"ARENA_OPEN_FORMAT {provider.upper()}_meta="
                  + json.dumps(safe_meta, sort_keys=True), flush=True)
            if outcome == "PASS_SYNTHETIC_OPEN_FORMAT":
                successes += 1
        except ValueError as err:
            code = str(err)
            if re.fullmatch(r"[A-Z0-9_]+", code) is None:
                code = "UNCLASSIFIED_ERROR"
            print(f"ARENA_OPEN_FORMAT {provider.upper()}=FAILED_{code}", flush=True)
    print(f"ARENA_OPEN_FORMAT passed={successes}/2", flush=True)
    print("ARENA_OPEN_FORMAT orders=0 services_changed=0", flush=True)
    print("ARENA_OPEN_FORMAT RESULT=" + (
        "BOTH_SYNTHETIC_OPEN_FORMATS_VERIFIED_NO_DEPLOY" if successes == 2
        else "REVIEW_FORMAT_RESULTS_NO_DEPLOY"
    ), flush=True)
    return 0 if successes == 2 else 2


if __name__ == "__main__":
    sys.exit(main())
