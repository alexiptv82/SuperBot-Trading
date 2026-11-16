#!/usr/bin/env python3
"""One diagnostic Qwen response, without touching any SuperBot PAPER service.

Requires --probe and explicit interactive SI. One billable Qwen request MAX,
never retries. No model content or secret is logged. Uses strict JSON schema,
a larger output budget, and temporarily disables reasoning FOR API TEST ONLY.
The real Brain and future benchmark remain entirely unchanged.
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

KEYS_PATH = Path("/etc/superbot-brain-ai-arena/openrouter-keys.json")
GET_KEY_URL = "https://openrouter.ai/api/v1/key"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "qwen/qwen3.7-plus"
MAX_TOKENS = 1024
MAX_RESPONSE = 100_000
SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "superbot_no_market_decision",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["NO_TRADE"]},
                "reason_code": {"type": "string", "enum": ["NO_MARKET_DATA"]},
            },
            "required": ["action", "reason_code"],
            "additionalProperties": False,
        },
    },
}


def api(url: str, key: str, data: dict | None = None) -> dict:
    headers = {
        "Authorization": "Bearer " + key,
        "Accept": "application/json",
        "User-Agent": "SuperBot-Qwen-JSON-Probe/1.0",
    }
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST" if data is not None else "GET",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(
            req, timeout=60, context=ssl.create_default_context()
        ) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as exc:
        raise ValueError("HTTP_" + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError("NETWORK_" + type(exc).__name__) from None
    if len(raw) > MAX_RESPONSE:
        raise ValueError("RESPONSE_TOO_LARGE")
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("INVALID_HTTP_JSON") from None
    if type(parsed) is not dict:
        raise ValueError("INVALID_HTTP_SCHEMA")
    return parsed


def key_from_root_store() -> str:
    if os.geteuid() != 0:
        raise ValueError("ROOT_REQUIRED")
    if KEYS_PATH.parent.is_symlink() or KEYS_PATH.is_symlink():
        raise ValueError("SECRET_SYMLINK")
    st = KEYS_PATH.stat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0
            or stat.S_IMODE(st.st_mode) != 0o600
            or stat.S_IMODE(KEYS_PATH.parent.stat().st_mode) != 0o700):
        raise ValueError("SECRETS_PERMISSIONS")
    with KEYS_PATH.open(encoding="utf-8") as fd:
        conf = json.load(fd)
    if (conf.get("schema") != "brain_arena_openrouter_keys_v1"
            or conf.get("mode") != "CREDENTIALS_ONLY_NO_INFERENCE"
            or conf.get("base_url") != "https://openrouter.ai/api/v1"
            or conf.get("models", {}).get("qwen") != MODEL):
        raise ValueError("CONFIG_MISMATCH")
    key = conf.get("api_keys", {}).get("qwen")
    if type(key) is not str or re.fullmatch(r"sk-or-v1-[A-Za-z0-9_-]{16,}", key) is None:
        raise ValueError("KEY_INVALID")
    return key


def verify_limit(info: dict) -> tuple[Decimal, Decimal]:
    data = info.get("data")
    if type(data) is not dict or data.get("is_management_key"):
        raise ValueError("KEY_INFO_INVALID")
    try:
        limit = Decimal(str(data.get("limit")))
        remaining = Decimal(str(data.get("limit_remaining")))
    except (ValueError, InvalidOperation):
        raise ValueError("KEY_LIMIT_INVALID") from None
    if not limit.is_finite() or not remaining.is_finite():
        raise ValueError("KEY_LIMIT_INVALID")
    if limit < 0 or limit > 2 or remaining < Decimal("0.02"):
        raise ValueError("KEY_LIMIT_NOT_ALLOWED")
    return limit, remaining


def classify_response(res: dict) -> tuple[str, dict]:
    choices = res.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return "NO_CHOICES", {}
    choice = choices[0]
    msg = choice.get("message")
    if not isinstance(msg, dict):
        return "INVALID_MESSAGE", {}
    content = msg.get("content")
    usage = res.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    details = usage.get("completion_tokens_details") or {}
    if not isinstance(details, dict):
        details = {}
    summary = {
        "finish_reason": choice.get("finish_reason"),
        "content_type": type(content).__name__,
        "content_chars": len(content) if isinstance(content, str) else 0,
        "reasoning_present": bool(msg.get("reasoning") or msg.get("reasoning_details")),
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": details.get("reasoning_tokens"),
        "model_reported": res.get("model"),
    }
    if not isinstance(content, str) or not content.strip():
        return "EMPTY_CONTENT", summary
    try:
        obj = json.loads(content)
    except (ValueError, TypeError):
        # Deliberately never show content or snippets, even in error cases.
        return "INVALID_JSON", summary
    if (type(obj) is dict and obj.get("action") == "NO_TRADE"
            and obj.get("reason_code") == "NO_MARKET_DATA"
            and len(obj) == 2):
        return "PASS_NO_TRADE_JSON", summary
    return "SCHEMA_MISMATCH", summary


def main() -> int:
    if sys.argv[1:] != ["--probe"]:
        print("QWEN_JSON_RESULT=REFUSED_EXPLICIT_PROBE_REQUIRED")
        return 2
    try:
        key = key_from_root_store()
        limit, remaining = verify_limit(api(GET_KEY_URL, key))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        code = str(exc)
        if re.fullmatch(r"[A-Z0-9_]+", code) is None:
            code = type(exc).__name__.upper()
        print("QWEN_JSON_RESULT=PRECHECK_FAILED_" + code)
        return 2
    print("QWEN_JSON_TEST=QWEN_ONLY")
    print("QWEN_JSON_key_limit_usd=" + str(limit))
    print("QWEN_JSON_remaining_before_usd=" + str(remaining))
    print("QWEN_JSON_mode=STRICT_SCHEMA_REASONING_OFF_DIAGNOSTIC_ONLY")
    print("QWEN_JSON_max_output_tokens=" + str(MAX_TOKENS))
    print("QWEN_JSON_MiniMax=NOT_CALLED")
    print("QWEN_JSON_Runner=UNCHANGED")
    try:
        confirm = input("Una sola nuova richiesta Qwen a pagamento. Confermi? Scrivi SI: ")
    except (EOFError, KeyboardInterrupt):
        print("\nQWEN_JSON_RESULT=USER_CANCELLED")
        return 130
    if confirm.strip() != "SI":
        print("QWEN_JSON_RESULT=USER_CANCELLED")
        return 0
    payload = {
        "model": MODEL,
        "stream": False,
        "temperature": 0,
        "max_completion_tokens": MAX_TOKENS,
        "reasoning": {"enabled": False},
        "provider": {"require_parameters": True},
        "response_format": SCHEMA,
        "messages": [
            {"role": "system", "content":
             "API JSON test: manca ogni dato di mercato. Niente trade."},
            {"role": "user", "content":
             "Genera esclusivamente JSON: action NO_TRADE; reason_code NO_MARKET_DATA."},
        ],
    }
    try:
        result = api(CHAT_URL, key, data=payload)
    except (ValueError, OSError) as exc:
        code = str(exc)
        if re.fullmatch(r"[A-Z0-9_]+", code) is None:
            code = type(exc).__name__.upper()
        print("QWEN_JSON_RESULT=REQUEST_FAILED_" + code)
        return 2
    status, meta = classify_response(result)
    print("QWEN_JSON_response_status=" + status)
    print("QWEN_JSON_meta=" + json.dumps(meta, ensure_ascii=True, sort_keys=True))
    print("QWEN_JSON_paid_model_calls_max=1")
    print("QWEN_JSON_orders_sent=0")
    print("QWEN_JSON_services_modified=0")
    print("QWEN_JSON_RESULT=" + (
        "QWEN_VERIFIED_NOT_ACTIVATED" if status == "PASS_NO_TRADE_JSON"
        else "REQUIRES_FURTHER_DIAGNOSIS_NOT_ACTIVATED"
    ))
    return 0 if status == "PASS_NO_TRADE_JSON" else 2


if __name__ == "__main__":
    sys.exit(main())
