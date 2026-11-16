#!/usr/bin/env python3
"""SuperBot AI Arena: one controlled, tiny paid OpenRouter response per model.

NO deployment, NO trading, NO live market data, NO bot/journal writes.
Two existing secret keys are read only from root-protected VPS config.
Explicit --probe and interactive confirmation are required before ANY
billable inference call. Exactly one POST per provider, no retries.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import getpass
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
KEY_ENDPOINT = "https://openrouter.ai/api/v1/key"
CHAT_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
EXPECTED_MODELS = {
    "qwen": "qwen/qwen3.7-plus",
    "minimax": "minimax/minimax-m3.1-flash",
}
MAX_COMPLETION_TOKENS = 512
MIN_AVAILABLE_KEY_LIMIT_USD = Decimal("0.02")
MAX_ALLOWED_KEY_LIMIT_USD = Decimal("2")
MAX_HTTP_BODY_BYTES = 100_000

SYSTEM_TEXT = (
    "Sei un verificatore di dati per un laboratorio PAPER di trading. "
    "Non generare mai operazioni con dati mancanti. "
    "Rispondi SOLO con JSON con action e reason_code."
)
USER_TEXT = (
    "TEST TECNICO. Non vengono forniti ticker, prezzi, indicatori o "
    "informazioni di mercato. Rispondi con action=NO_TRADE e "
    "reason_code=NO_MARKET_DATA. Nessun consiglio finanziario."
)


def fail(code: str) -> None:
    # Do not print API response body, credentials or response headers.
    print("ARENA_PROBE RESULT=FAILED_" + code, flush=True)
    raise SystemExit(2)


def load_secrets() -> dict:
    if os.geteuid() != 0:
        fail("ROOT_REQUIRED")
    if SECRETS.is_symlink() or SECRETS.parent.is_symlink():
        fail("SECRETS_SYMLINK")
    st = SECRETS.stat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0
            or stat.S_IMODE(st.st_mode) != 0o600):
        fail("SECRETS_PERMISSIONS")
    if stat.S_IMODE(SECRETS.parent.stat().st_mode) != 0o700:
        fail("SECRET_DIRECTORY_PERMISSIONS")
    with SECRETS.open(encoding="utf-8") as f:
        cfg = json.load(f)
    if (cfg.get("schema") != "brain_arena_openrouter_keys_v1"
            or cfg.get("mode") != "CREDENTIALS_ONLY_NO_INFERENCE"
            or cfg.get("base_url") != "https://openrouter.ai/api/v1"):
        fail("CREDENTIALS_CONFIG")
    if cfg.get("models") != EXPECTED_MODELS:
        fail("MODELS_CONFIG")
    keys = cfg.get("api_keys") or {}
    if not isinstance(keys, dict) or set(keys) != set(EXPECTED_MODELS):
        fail("KEYS_CONFIG")
    if any(not isinstance(keys[p], str) or
           not re.fullmatch(r"sk-or-v1-[A-Za-z0-9_-]{16,}", keys[p])
           for p in EXPECTED_MODELS):
        fail("KEYS_FORMAT")
    if keys["qwen"] == keys["minimax"]:
        fail("DUPLICATE_KEYS")
    return keys


def public_request(url: str, key: str, *, payload: dict | None = None) -> dict:
    headers = {
        "Authorization": "Bearer " + key,
        "Accept": "application/json",
        "User-Agent": "SuperBot-Brain-Arena-OneShot-Probe/1.0",
    }
    data = None
    method = "GET"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        method = "POST"
    req = urllib.request.Request(
        url, headers=headers, data=data, method=method
    )
    try:
        with urllib.request.urlopen(
            req, timeout=50, context=ssl.create_default_context()
        ) as resp:
            body = resp.read(MAX_HTTP_BODY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # No error body: API could echo request details.
        raise ValueError("HTTP_" + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError("NETWORK_" + type(exc).__name__) from None
    if len(body) > MAX_HTTP_BODY_BYTES:
        raise ValueError("RESPONSE_TOO_LARGE")
    try:
        result = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("INVALID_RESPONSE_JSON") from None
    if not isinstance(result, dict):
        raise ValueError("INVALID_RESPONSE_OBJECT")
    return result


def money(value: object) -> Decimal:
    try:
        v = Decimal(str(value))
    except (TypeError, InvalidOperation, ValueError):
        raise ValueError("INVALID_KEY_LIMIT") from None
    if not v.is_finite() or v < 0:
        raise ValueError("INVALID_KEY_LIMIT")
    return v


def key_limit_verified(key: str) -> tuple[Decimal, Decimal]:
    data = public_request(KEY_ENDPOINT, key).get("data")
    if not isinstance(data, dict) or data.get("is_management_key"):
        raise ValueError("INVALID_KEY_TYPE")
    limit = money(data.get("limit"))
    remaining = money(data.get("limit_remaining"))
    if limit > MAX_ALLOWED_KEY_LIMIT_USD:
        raise ValueError("KEY_LIMIT_OVER_2_USD")
    if remaining < MIN_AVAILABLE_KEY_LIMIT_USD:
        raise ValueError("LOW_KEY_LIMIT_REMAINING")
    return limit, remaining


def single_probe(model: str, key: str) -> tuple[str, dict]:
    payload = {
        "model": model,
        "stream": False,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_TEXT},
            {"role": "user", "content": USER_TEXT},
        ],
    }
    result = public_request(CHAT_ENDPOINT, key, payload=payload)
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("NO_CHOICES")
    msg = choices[0].get("message")
    if not isinstance(msg, dict):
        raise ValueError("NO_ASSISTANT_MESSAGE")
    text = msg.get("content")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("NO_TEXT_RESPONSE")
    try:
        value = json.loads(text)
    except ValueError:
        raise ValueError("INVALID_MODEL_JSON") from None
    if (not isinstance(value, dict)
            or value.get("action") != "NO_TRADE"
            or value.get("reason_code") != "NO_MARKET_DATA"):
        raise ValueError("UNEXPECTED_RESPONSE_FIELDS")
    usage = result.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    public_usage = {
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "finish_reason": choices[0].get("finish_reason"),
        "model_reported": result.get("model"),
    }
    # No model response content, reasons, raw error or secrets are printed.
    return "PASS_NO_TRADE_JSON", public_usage


def main() -> None:
    if sys.argv[1:] != ["--probe"]:
        fail("USE_EXPLICIT_PROBE_FLAG")
    keys = load_secrets()
    print("=== SuperBot AI Arena — test API controllato ===", flush=True)
    print("Una richiesta AI a pagamento per Qwen e una per MiniMax, massimo "
          + str(MAX_COMPLETION_TOKENS) + " token di risposta ciascuna.", flush=True)
    print("Nessun ordine, nessuna scrittura ai journal, nessun bot riavviato.", flush=True)
    if input("Confermi le due piccole richieste a pagamento? Scrivi SI: ").strip() != "SI":
        fail("USER_CANCELLED")

    passed = 0
    for provider, model in EXPECTED_MODELS.items():
        # No automated retries on paid requests, including network errors.
        try:
            limit, remaining = key_limit_verified(keys[provider])
            print("ARENA_PROBE " + provider.upper() + "_limit_usd=" + str(limit)
                  + " remaining_before_usd=" + str(remaining), flush=True)
            status, usage = single_probe(model, keys[provider])
            print("ARENA_PROBE " + provider.upper() + "=" + status, flush=True)
            print("ARENA_PROBE " + provider.upper() + "_usage="
                  + json.dumps(usage, sort_keys=True), flush=True)
            passed += 1
        except (ValueError, OSError) as exc:
            # Class-only diagnostics. Never echo arbitrary provider response.
            message = str(exc)
            if not re.fullmatch(r"[A-Z0-9_]+", message):
                message = type(exc).__name__.upper()
            print("ARENA_PROBE " + provider.upper() + "=FAILED_" + message, flush=True)
            # Continue to test other independent provider only if prior call
            # could not yield a usable structured response.
    print("ARENA_PROBE models_verified=" + str(passed) + "/2")
    print("ARENA_PROBE model_inference_calls_max=2")
    print("ARENA_PROBE runner_changes=0")
    print("ARENA_PROBE trading_orders=0")
    print("ARENA_PROBE RESULT=" + (
        "BOTH_MODELS_RESPONDED_NOT_ACTIVATED" if passed == 2
        else "REVIEW_PROVIDER_RESULTS_NOT_ACTIVATED"
    ))


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print("\nARENA_PROBE RESULT=USER_CANCELLED")
        sys.exit(130)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print("ARENA_PROBE RESULT=FAILED_PRECHECK_" + type(exc).__name__)
        sys.exit(2)
