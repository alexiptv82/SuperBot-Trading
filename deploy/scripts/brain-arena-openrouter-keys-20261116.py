#!/usr/bin/env python3
"""Private OpenRouter key enrollment for SuperBot AI Arena (NO model inference).

Run interactively as root on the SuperBot VPS from a pinned Git commit. The
password-style prompts do not echo or store keys in terminal command history.
Uses only OpenRouter GET /api/v1/key, which does not call a model or bill tokens.
Does not start any bot, change a runner, or access a trading endpoint.
"""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import re
import ssl
import sys
import urllib.error
import urllib.request

KEY_INFO_URL = "https://openrouter.ai/api/v1/key"
STORE = Path("/etc/superbot-brain-ai-arena/openrouter-keys.json")
MODEL_IDS = {
    "qwen": "qwen/qwen3.7-plus",
    "minimax": "minimax/minimax-m3.1-flash",
}
KEY_PATTERN = re.compile(r"^sk-or-v1-[A-Za-z0-9_-]{16,}$")


def check_key(value: str) -> dict:
    if not KEY_PATTERN.fullmatch(value):
        raise ValueError("formato_chiave_non_valido")
    request = urllib.request.Request(
        KEY_INFO_URL,
        method="GET",
        headers={
            "Authorization": "Bearer " + value,
            "Accept": "application/json",
            "User-Agent": "SuperBot-Brain-Arena-Preflight/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15, context=ssl.create_default_context()) as resp:
            info = json.load(resp)
    except urllib.error.HTTPError as exc:
        # Do not print request, response body, auth headers, or the key.
        raise ValueError("autenticazione_fallita_HTTP_" + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError("connessione_OpenRouter_" + type(exc).__name__) from None
    if not isinstance(info, dict) or not isinstance(info.get("data"), dict):
        raise ValueError("risposta_API_non_valida")
    data = info["data"]
    if data.get("is_management_key"):
        raise ValueError("non_usare_chiave_di_gestione")
    return {
        "limit": data.get("limit"),
        "limit_remaining": data.get("limit_remaining"),
        "limit_reset": data.get("limit_reset"),
        "expires_at": data.get("expires_at"),
    }


def store_private(keys: dict) -> None:
    parent = STORE.parent
    if parent.is_symlink():
        raise ValueError("cartella_segreti_link_simbolico")
    if parent.exists() and not parent.is_dir():
        raise ValueError("cartella_segreti_non_valida")
    parent.mkdir(mode=0o700, parents=False, exist_ok=True)
    os.chmod(parent, 0o700)
    if STORE.exists() or STORE.is_symlink():
        raise ValueError("file_gia_presente_non_sovrascrivo")
    # Create exclusive root-only file after both keys have passed validation.
    fd = os.open(STORE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            payload = {
                "schema": "brain_arena_openrouter_keys_v1",
                "provider": "openrouter",
                "mode": "CREDENTIALS_ONLY_NO_INFERENCE",
                "base_url": "https://openrouter.ai/api/v1",
                "models": MODEL_IDS,
                "api_keys": keys,
            }
            json.dump(payload, f, ensure_ascii=True, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        # A failed write must never leave a partial config.
        try:
            STORE.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def main() -> int:
    if os.geteuid() != 0:
        print("ARENA_KEYS RESULT=ROOT_REQUIRED")
        return 2
    os.umask(0o077)
    print("=== SuperBot AI Arena — verifica OpenRouter ===", flush=True)
    print("Due chiavi, inserimento nascosto. Nessuna richiesta a modelli AI, nessun costo API.", flush=True)
    if STORE.exists() or STORE.is_symlink():
        print("ARENA_KEYS RESULT=REFUSED_CONFIG_ALREADY_EXISTS")
        return 2
    keys = {}
    for name in ("qwen", "minimax"):
        key = getpass.getpass("Incolla chiave OpenRouter " + name.upper() + " (non visibile): ").strip()
        if key in keys.values():
            print("ARENA_KEYS RESULT=REFUSED_DUPLICATE_KEYS")
            return 2
        try:
            info = check_key(key)
        except ValueError as exc:
            print("ARENA_KEYS " + name.upper() + "=FAILED_" + str(exc), flush=True)
            print("ARENA_KEYS RESULT=NOT_SAVED")
            return 2
        keys[name] = key
        print(
            "ARENA_KEYS " + name.upper() + "=VALID"
            + " limit_usd=" + str(info["limit"])
            + " remaining_limit_usd=" + str(info["limit_remaining"])
            + " reset=" + str(info["limit_reset"])
            + " expires=" + str(info["expires_at"]),
            flush=True,
        )
        if info["limit"] is None or (
            isinstance(info["limit"], (int, float)) and info["limit"] > 2
        ):
            print("ARENA_KEYS " + name.upper()
                  + "_WARNING=limite_superiore_a_2_USD_o_assente", flush=True)
    try:
        store_private(keys)
    except (OSError, ValueError) as exc:
        print("ARENA_KEYS RESULT=NOT_SAVED_" + type(exc).__name__, flush=True)
        return 2
    print("ARENA_KEYS secret_file=" + str(STORE))
    print("ARENA_KEYS file_mode=0600 directory_mode=0700")
    print("ARENA_KEYS qwen_model=" + MODEL_IDS["qwen"])
    print("ARENA_KEYS minimax_model=" + MODEL_IDS["minimax"])
    print("ARENA_KEYS api_calls_paid=0")
    print("ARENA_KEYS runner_changes=0")
    print("ARENA_KEYS trading_orders=0")
    print("ARENA_KEYS RESULT=KEYS_VERIFIED_AND_STORED_NOT_ACTIVATED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nARENA_KEYS RESULT=USER_ABORTED_NOT_SAVED")
        sys.exit(130)
