#!/usr/bin/env python3
"""SuperBot AI Arena: TWO provider-specific bounded JSON API diagnostics.

Purpose: verify that Qwen and MiniMax can each return the exact eight-field
Arena Brain decision schema. No live candles or account data are transmitted;
the single synthetic NO_MARKET_DATA case must produce NO_TRADE. One paid
request maximum per provider. No retry, no journal modification, no orders,
no systemd/docker actions. Requires root-only keys already installed.
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

SECRETS = Path("/etc/superbot-brain-ai-arena/openrouter-keys.json")
BASE_URL = "https://openrouter.ai/api/v1"
KEY_URL = BASE_URL + "/key"
CHAT_URL = BASE_URL + "/chat/completions"
MODELS = {
    "qwen": "qwen/qwen3.7-plus",
    "minimax": "minimax/minimax-m3.1-flash",
}
EXPECTED_NO_TRADE = {
    "kind": "NO_TRADE", "side": 0,
    "entry_price": "0", "stop_price": "0",
    "leverage": 0, "confidence": 0,
    "strategy_id": "", "strategy_origin": "",
}
JSON_OBJECT = {"type": "json_object"}

OUTPUT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "superbot_arena_brain_decision_v1",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["NO_TRADE", "OPEN"]},
                "side": {"type": "integer", "enum": [-1, 0, 1]},
                "entry_price": {"type": "string"},
                "stop_price": {"type": "string"},
                "leverage": {"type": "integer"},
                "confidence": {"type": "number"},
                "strategy_id": {"type": "string"},
                "strategy_origin": {"type": "string", "enum": ["", "library", "ai_proposed"]},
            },
            "required": list(EXPECTED_NO_TRADE),
            "additionalProperties": False,
        },
    },
}
MAX_KEY_USD = Decimal("2")
MIN_REMAINING_USD = Decimal("0.10")
MAX_COMPLETION_TOKENS = 1024
MAX_HTTP_RESPONSE_BYTES = 100_000
TOKEN_FMT = re.compile(r"sk-or-v1-[A-Za-z0-9_-]{16,}\Z")


def _money(value: object) -> Decimal:
    if type(value) not in (str, int, float):
        raise ValueError("INVALID_BUDGET_FORMAT")
    try:
        num = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("INVALID_BUDGET_FORMAT") from None
    if not num.is_finite() or num < 0:
        raise ValueError("INVALID_BUDGET_FORMAT")
    return num


def validate_budget(data: dict) -> tuple[Decimal, Decimal]:
    details = data.get("data") if type(data) is dict else None
    if type(details) is not dict or details.get("is_management_key"):
        raise ValueError("INVALID_KEY_DETAILS")
    limit = _money(details.get("limit"))
    remaining = _money(details.get("limit_remaining"))
    if limit > MAX_KEY_USD:
        raise ValueError("KEY_LIMIT_EXCEEDS_2_USD")
    if remaining < MIN_REMAINING_USD:
        raise ValueError("INSUFFICIENT_KEY_ALLOWANCE")
    return limit, remaining


def read_keys() -> dict[str, str]:
    if os.geteuid() != 0:
        raise ValueError("ROOT_REQUIRED")
    if SECRETS.is_symlink() or SECRETS.parent.is_symlink():
        raise ValueError("UNSAFE_SECRET_PATH")
    mode = SECRETS.stat()
    folder = SECRETS.parent.stat()
    if (not stat.S_ISREG(mode.st_mode) or mode.st_uid != 0
            or stat.S_IMODE(mode.st_mode) != 0o600
            or not stat.S_ISDIR(folder.st_mode) or folder.st_uid != 0
            or stat.S_IMODE(folder.st_mode) != 0o700):
        raise ValueError("UNSAFE_SECRET_PERMISSIONS")
    with SECRETS.open(encoding="utf-8") as f:
        config = json.load(f)
    if (type(config) is not dict
            or config.get("schema") != "brain_arena_openrouter_keys_v1"
            or config.get("mode") != "CREDENTIALS_ONLY_NO_INFERENCE"
            or config.get("base_url") != BASE_URL
            or config.get("models") != MODELS):
        raise ValueError("UNEXPECTED_CREDENTIAL_CONFIG")
    keys = config.get("api_keys")
    if (type(keys) is not dict or set(keys) != set(MODELS)
            or any(type(x) is not str or not TOKEN_FMT.fullmatch(x)
                   for x in keys.values())
            or keys["qwen"] == keys["minimax"]):
        raise ValueError("KEYS_NOT_INDEPENDENT")
    return keys


def call_api(url: str, key: str, data: dict | None = None) -> dict:
    request = urllib.request.Request(
        url,
        data=None if data is None else json.dumps(
            data, ensure_ascii=True, allow_nan=False,
        ).encode("utf-8"),
        method="GET" if data is None else "POST",
        headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            "User-Agent": "SuperBot-Arena-Funded-Schema-Preflight/1.0",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=60, context=ssl.create_default_context(),
        ) as response:
            raw = response.read(MAX_HTTP_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # Never print provider body: it may contain partial request and secrets.
        raise ValueError("HTTP_" + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError("NETWORK_" + type(exc).__name__) from None
    if len(raw) > MAX_HTTP_RESPONSE_BYTES:
        raise ValueError("HTTP_RESPONSE_TOO_LARGE")
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        raise ValueError("HTTP_RESPONSE_NOT_JSON") from None
    if type(result) is not dict:
        raise ValueError("HTTP_RESPONSE_NOT_OBJECT")
    return result


def parse_decision(result: dict) -> tuple[str, dict]:
    choices = result.get("choices")
    if type(choices) is not list or len(choices) != 1:
        return "CHOICES_INVALID", {}
    c = choices[0]
    if type(c) is not dict or type(c.get("message")) is not dict:
        return "MESSAGE_INVALID", {}
    msg = c["message"]
    usage = result.get("usage") or {}
    if type(usage) is not dict:
        usage = {}
    meta = {
        "model": result.get("model") if result.get("model") in MODELS.values() else "unknown",
        "finish_reason": c.get("finish_reason"),
        "input_tokens": usage.get("prompt_tokens") if type(usage.get("prompt_tokens")) is int else None,
        "output_tokens": usage.get("completion_tokens") if type(usage.get("completion_tokens")) is int else None,
        "reasoning_present": bool(msg.get("reasoning") or msg.get("reasoning_details")),
    }
    content = msg.get("content")
    if type(content) is not str:
        return "CONTENT_ABSENT", meta
    try:
        obj = json.loads(content)
    except ValueError:
        return "OUTPUT_NOT_JSON", meta
    # Print only fixed category codes and safe field names, never model text
    # (which could contain free-form material from an upstream provider).
    if type(obj) is not dict:
        return "DECISION_NOT_OBJECT", meta
    expected = set(EXPECTED_NO_TRADE)
    observed = set(obj)
    meta["missing_fields"] = sorted(expected - observed)
    meta["extra_field_count"] = len(observed - expected)
    issues = []
    for name in EXPECTED_NO_TRADE:
        if name not in obj:
            continue
        value = obj[name]
        expected_type = {
            "kind": str, "side": int, "entry_price": str,
            "stop_price": str, "leverage": int, "confidence": (int, float),
            "strategy_id": str, "strategy_origin": str,
        }[name]
        if type(value) not in (expected_type if type(expected_type) is tuple else (expected_type,)):
            issues.append(name + "_TYPE")
        elif value != EXPECTED_NO_TRADE[name]:
            issues.append(name + "_VALUE")
    meta["field_issues"] = issues
    if meta["missing_fields"] or meta["extra_field_count"] or issues:
        return "SCHEMA_OR_DECISION_MISMATCH", meta
    if c.get("finish_reason") != "stop":
        return "INCOMPLETE_GENERATION", meta
    return "PASS_NO_TRADE_EIGHT_FIELDS", meta


def payload(model: str) -> dict:
    # Qwen's strict schema request reaches the endpoint, but its previous
    # NO_TRADE data differed from our expected neutral values.
    # MiniMax previously returned HTTP400 with strict routing and succeeded
    # earlier using plain JSON Object + temperature 0; test the known shape.
    is_qwen = model == MODELS["qwen"]
    if model not in MODELS.values():
        raise ValueError("UNEXPECTED_MODEL")
    result = {
        "model": model,
        "stream": False,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "response_format": OUTPUT_SCHEMA if is_qwen else JSON_OBJECT,
        "messages": [
            {"role": "system", "content": (
                "This is a synthetic API JSON-only format test with NO market "
                "data. Return ONLY the exact eight fields kind, side, entry_price, "
                "stop_price, leverage, confidence, strategy_id, strategy_origin. "
                "Do NOT open a trade. kind MUST be NO_TRADE, side MUST be 0, "
                "entry_price and stop_price MUST be strings '0', leverage MUST "
                "be numeric 0, confidence MUST be numeric 0, strategy_id and "
                "strategy_origin MUST be empty strings. Do not add commentary."
            )},
            {"role": "user", "content": (
                "JSON diagnostic, no prices, no candles, no trade. "
                "Output exactly: "
                '{"kind":"NO_TRADE","side":0,"entry_price":"0",'
                '"stop_price":"0","leverage":0,"confidence":0,'
                '"strategy_id":"","strategy_origin":""}'
            )},
        ],
    }
    if is_qwen:
        result["provider"] = {"require_parameters": True}
        result["reasoning"] = {"enabled": False}
    else:
        result["temperature"] = 0
    return result


def selftest() -> int:
    """Fully offline assertions: no file, key or internet access."""
    fixture = lambda obj, reason="stop": {
        "model": MODELS["qwen"],
        "choices": [{"finish_reason": reason,
                     "message": {"content": json.dumps(obj)}}],
        "usage": {"prompt_tokens": 31, "completion_tokens": 18},
    }
    assert parse_decision(fixture(EXPECTED_NO_TRADE))[0] == "PASS_NO_TRADE_EIGHT_FIELDS"
    assert parse_decision(fixture({**EXPECTED_NO_TRADE, "side": -1}))[0] == "SCHEMA_OR_DECISION_MISMATCH"
    assert parse_decision(fixture({**EXPECTED_NO_TRADE, "leverage": True}))[0] == "SCHEMA_OR_DECISION_MISMATCH"
    assert parse_decision(fixture({**EXPECTED_NO_TRADE, "entry_price": 0}))[0] == "SCHEMA_OR_DECISION_MISMATCH"
    assert parse_decision(fixture({**EXPECTED_NO_TRADE, "extra": 1}))[0] == "SCHEMA_OR_DECISION_MISMATCH"
    assert parse_decision(fixture(EXPECTED_NO_TRADE, "length"))[0] == "INCOMPLETE_GENERATION"
    assert parse_decision({"choices":[{"message":{"content":"not-json"}}]})[0] == "OUTPUT_NOT_JSON"
    assert validate_budget({"data":{"limit":2, "limit_remaining":1.50}}) == (
        Decimal(2), Decimal("1.50")
    )
    for disallowed in (
        {"data":{"limit":50,"limit_remaining":50}},
        {"data":{"limit":2,"limit_remaining":0}},
        {"data":{"limit":None,"limit_remaining":None}},
        {"data":{"limit":2,"limit_remaining":2,"is_management_key":True}},
    ):
        try:
            validate_budget(disallowed)
            raise AssertionError("budget gate allowed invalid source")
        except ValueError:
            pass
    assert set(OUTPUT_SCHEMA["json_schema"]["schema"]["properties"]) == set(EXPECTED_NO_TRADE)
    assert OUTPUT_SCHEMA["json_schema"]["schema"]["required"] == list(EXPECTED_NO_TRADE)
    assert payload(MODELS["qwen"])["model"] == MODELS["qwen"]
    assert payload(MODELS["qwen"])["response_format"] == OUTPUT_SCHEMA
    assert payload(MODELS["minimax"])["response_format"] == JSON_OBJECT
    assert payload(MODELS["minimax"])["temperature"] == 0
    assert "provider" not in payload(MODELS["minimax"])
    assert "reasoning" not in payload(MODELS["minimax"])
    print("ARENA_JSON_COMPAT SELFTEST=PASS_OFFLINE")
    print("ARENA_JSON_COMPAT SELFTEST api_calls=0 secrets_read=0 orders=0")
    return 0


def main() -> int:
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    if sys.argv[1:] != ["--probe"]:
        print("ARENA_JSON_COMPAT RESULT=NOT_RUN_USE_PROBE_FLAG")
        return 2
    try:
        keys = read_keys()
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print("ARENA_JSON_COMPAT RESULT=NOT_RUN_" + type(exc).__name__)
        return 2
    print("=== Brain AI Arena — Qwen strict + MiniMax JSON object ===", flush=True)
    print("ARENA_JSON_COMPAT max_paid_requests=2 (one per provider)")
    print("ARENA_JSON_COMPAT synthetic_only=YES")
    print("ARENA_JSON_COMPAT orders=0 journals=0 services=0")
    try:
        confirmation = input("Autorizzi massimo DUE piccole chiamate API a pagamento? Scrivi SI: ")
    except (EOFError, KeyboardInterrupt):
        print("\nARENA_JSON_COMPAT RESULT=CANCELLED")
        return 130
    if confirmation.strip() != "SI":
        print("ARENA_JSON_COMPAT RESULT=CANCELLED")
        return 0
    passed = 0
    for provider, model in MODELS.items():
        try:
            limit, before = validate_budget(call_api(KEY_URL, keys[provider]))
            print(f"ARENA_JSON_COMPAT {provider.upper()}_key_limit_usd={limit}"
                  f" remaining_before_usd={before}", flush=True)
            # No automatic retry on failed/uncertain billable request.
            result = call_api(CHAT_URL, keys[provider], payload(model))
            status, meta = parse_decision(result)
            # Summarize only numeric metadata; never display model text.
            print(f"ARENA_JSON_COMPAT {provider.upper()}={status}", flush=True)
            print(f"ARENA_JSON_COMPAT {provider.upper()}_meta="
                  + json.dumps(meta, sort_keys=True, ensure_ascii=True), flush=True)
            if status == "PASS_NO_TRADE_EIGHT_FIELDS":
                passed += 1
        except ValueError as exc:
            code = str(exc)
            if re.fullmatch("[A-Z0-9_]+", code) is None:
                code = type(exc).__name__.upper()
            print(f"ARENA_JSON_COMPAT {provider.upper()}=FAILED_{code}", flush=True)
    print("ARENA_JSON_COMPAT passed=" + str(passed) + "/2")
    print("ARENA_JSON_COMPAT orders=0 services_changed=0")
    print("ARENA_JSON_COMPAT RESULT=" + (
        "BOTH_PROVIDER_FORMATS_PASSED_NO_DEPLOY" if passed == 2
        else "REVIEW_PROVIDER_DIAGNOSTICS_NO_DEPLOY"
    ), flush=True)
    return 0 if passed == 2 else 2


if __name__ == "__main__":
    sys.exit(main())
