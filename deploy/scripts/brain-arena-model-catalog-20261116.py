#!/usr/bin/env python3
"""Read-only OpenRouter model catalog preflight for SuperBot Brain AI Arena.

Checks the stored model identifiers, prices and endpoint metadata. This script
never calls an inference endpoint, never exposes secrets, and does not touch
SuperBot services, positions, or journals.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import stat
import sys
import urllib.error
import urllib.request

SECRETS = Path("/etc/superbot-brain-ai-arena/openrouter-keys.json")
CATALOG = "https://openrouter.ai/api/v1/models"
PROVIDERS = ("qwen", "minimax")


def read_configuration() -> dict:
    parent = SECRETS.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("secret_directory_invalid")
    if SECRETS.is_symlink():
        raise ValueError("secret_symlink_forbidden")
    st = SECRETS.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or (st.st_mode & 0o077):
        raise ValueError("secret_permissions_invalid")
    # No secret text is displayed, logged or written to a report.
    with SECRETS.open("r", encoding="utf-8") as fd:
        data = json.load(fd)
    if data.get("schema") != "brain_arena_openrouter_keys_v1":
        raise ValueError("secret_schema_mismatch")
    if data.get("mode") != "CREDENTIALS_ONLY_NO_INFERENCE":
        raise ValueError("credentials_unexpectedly_activated")
    if data.get("base_url") != "https://openrouter.ai/api/v1":
        raise ValueError("endpoint_mismatch")
    for provider in PROVIDERS:
        key = data.get("api_keys", {}).get(provider)
        model = data.get("models", {}).get(provider)
        if not isinstance(key, str) or not key.startswith("sk-or-v1-"):
            raise ValueError("invalid_" + provider + "_credential")
        if not isinstance(model, str) or not model.startswith(provider + "/"):
            raise ValueError("invalid_" + provider + "_model")
    if data["api_keys"]["qwen"] == data["api_keys"]["minimax"]:
        raise ValueError("keys_not_independent")
    return data


def get_catalog(key: str) -> list[dict]:
    request = urllib.request.Request(
        CATALOG,
        method="GET",
        headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            "User-Agent": "SuperBot-Paper-Arena-Catalog-Preflight/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:
            raw = resp.read(12_000_001)
    except urllib.error.HTTPError as exc:
        raise ValueError("catalog_http_" + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError("catalog_network_" + type(exc).__name__) from None
    if len(raw) > 12_000_000:
        raise ValueError("catalog_response_too_large")
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("catalog_json_invalid") from None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("data"), list):
        raise ValueError("catalog_schema_invalid")
    return parsed["data"]


def per_million(pricing: dict, key: str) -> str:
    try:
        raw = pricing.get(key)
        value = Decimal(str(raw)) * Decimal(1_000_000)
        if not value.is_finite() or value < 0:
            return "UNKNOWN"
        return str(value.quantize(Decimal("0.0001")))
    except (InvalidOperation, TypeError):
        return "UNKNOWN"


def main() -> int:
    if os.geteuid() != 0:
        print("ARENA_CATALOG RESULT=ROOT_REQUIRED")
        return 2
    try:
        cfg = read_configuration()
        listing = get_catalog(cfg["api_keys"]["qwen"])
        indexed = {row.get("id"): row for row in listing if isinstance(row, dict)}
        missing = 0
        for provider in PROVIDERS:
            model_id = cfg["models"][provider]
            item = indexed.get(model_id)
            if not item:
                missing += 1
                print(f"ARENA_CATALOG {provider.upper()}=NOT_AVAILABLE_IN_CATALOG model={model_id}")
                continue
            pricing = item.get("pricing") or {}
            params = item.get("supported_parameters") or []
            print(f"ARENA_CATALOG {provider.upper()}=FOUND model={model_id}")
            print(f"ARENA_CATALOG {provider.upper()}_pricing_usd_per_1M_input="
                  + per_million(pricing, "prompt"))
            print(f"ARENA_CATALOG {provider.upper()}_pricing_usd_per_1M_output="
                  + per_million(pricing, "completion"))
            print(f"ARENA_CATALOG {provider.upper()}_context_tokens={item.get('context_length')}")
            print(f"ARENA_CATALOG {provider.upper()}_structured_output_supported="
                  + str("response_format" in params or "structured_outputs" in params))
        print("ARENA_CATALOG model_inference_calls=0")
        print("ARENA_CATALOG trading_actions=0")
        print("ARENA_CATALOG services_modified=0")
        print("ARENA_CATALOG RESULT=" + (
            "CATALOG_VERIFIED_NOT_ACTIVATED" if missing == 0 else "MISSING_MODEL_REVIEW_NEEDED"
        ))
        return 0 if missing == 0 else 2
    except (ValueError, OSError) as exc:
        # Sanitize: no Authorization headers, no key values, no API response body.
        print("ARENA_CATALOG RESULT=FAILED_" + str(exc).replace("\n", "_"))
        return 2


if __name__ == "__main__":
    sys.exit(main())
