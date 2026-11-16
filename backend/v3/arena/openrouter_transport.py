"""Isolated OpenRouter transport for future Qwen/MiniMax Brain PAPER lanes.

No integration with the running Brain. Importing this module does not read
secrets, connect to providers or create a portfolio. Explicit allow_inference
and DESK_MODE=paper are necessary but NOT sufficient for eventual deployment:
each provider still requires a separate approved mandate, journal, budget,
execution writer and healthy exit service.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import ssl
import stat
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Callable

from backend.v3.brain_f3.providers import ProviderUnavailable, TransportResponse

MODELS = {
    "qwen": "qwen/qwen3.7-plus",
    "minimax": "minimax/minimax-m3.1-flash",
}
RUN_IDS = {
    "qwen": "brain-qwen-paper20261116",
    "minimax": "brain-minimax-paper20261116",
}
INITIAL_EQUITY = Decimal("2000")
CREDENTIALS = Path("/etc/superbot-brain-ai-arena/openrouter-keys.json")
BASE = "https://openrouter.ai/api/v1"
MAX_BYTES = 65536
MAX_TOKENS = 8192
KEY_LIMIT = Decimal("2")
KEY_MIN_REMAINING = Decimal("0.03")
_KEY_RE = re.compile(r"sk-or-v1-[A-Za-z0-9_-]{16,}\Z")


def _error(code: str = "provider_unavailable") -> ProviderUnavailable:
    # No secrets, response body, path or free-form HTTP error messages.
    return ProviderUnavailable(code)


def _read_key(provider: str) -> str:
    if provider not in MODELS or os.geteuid() != 0:
        raise _error("provider_disabled")
    try:
        if CREDENTIALS.is_symlink() or CREDENTIALS.parent.is_symlink():
            raise ValueError()
        d = CREDENTIALS.parent.stat()
        f = CREDENTIALS.stat()
        if (not stat.S_ISDIR(d.st_mode) or stat.S_IMODE(d.st_mode) != 0o700
                or not stat.S_ISREG(f.st_mode) or f.st_uid != 0
                or stat.S_IMODE(f.st_mode) != 0o600):
            raise ValueError()
        with CREDENTIALS.open(encoding="utf-8") as stream:
            data = json.load(stream)
        if (type(data) is not dict
                or data.get("schema") != "brain_arena_openrouter_keys_v1"
                or data.get("base_url") != BASE
                or data.get("mode") != "CREDENTIALS_ONLY_NO_INFERENCE"
                or data.get("models") != MODELS):
            raise ValueError()
        keys = data.get("api_keys")
        if (type(keys) is not dict or set(keys) != set(MODELS)
                or any(type(v) is not str or _KEY_RE.fullmatch(v) is None
                       for v in keys.values())
                or keys["qwen"] == keys["minimax"]):
            raise ValueError()
        return keys[provider]
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        raise _error("provider_unavailable") from None


def _request(path: str, key: str, payload: dict | None) -> dict:
    if path not in ("/key", "/chat/completions"):
        raise _error()
    if (path == "/key") != (payload is None):
        raise _error()
    body = None if payload is None else json.dumps(
        payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
        allow_nan=False,
    ).encode()
    req = urllib.request.Request(
        BASE + path,
        method="GET" if payload is None else "POST",
        data=body,
        headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            "User-Agent": "SuperBot-PAPER-Arena-Provider/1.0",
            **({"Content-Type": "application/json"} if payload is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45, context=ssl.create_default_context()) as stream:
            if stream.getcode() != 200:
                raise ValueError()
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError()
        response = json.loads(raw)
        if type(response) is not dict:
            raise ValueError()
        return response
    except (urllib.error.HTTPError, urllib.error.URLError,
            OSError, ValueError, TypeError, UnicodeError, TimeoutError):
        raise _error() from None


def _decimal(value: object) -> Decimal:
    if type(value) not in (str, int, float):
        raise ValueError()
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError() from None
    if not d.is_finite() or d < 0:
        raise ValueError()
    return d


def _verify_key_budget(body: dict) -> None:
    details = body.get("data")
    if type(details) is not dict or details.get("is_management_key"):
        raise _error("budget_denied")
    try:
        max_usd = _decimal(details.get("limit"))
        remaining = _decimal(details.get("limit_remaining"))
    except ValueError:
        raise _error("budget_denied") from None
    if max_usd > KEY_LIMIT or remaining < KEY_MIN_REMAINING:
        raise _error("budget_denied")


def _validate_payload(payload: Mapping, model: str) -> dict:
    if (not isinstance(payload, Mapping)
            or payload.get("model") != model
            or payload.get("stream") is not False
            or type(payload.get("max_tokens")) is not int
            or not 1 <= payload["max_tokens"] <= MAX_TOKENS
            or payload.get("response_format") not in (
                {"type": "json_object"},  # compared below without requiring dict hash
            )):
        # The above response_format membership uses a tuple of dicts, not a set.
        raise _error("invalid_model_payload")
    forbidden = {"tools", "tool_choice", "functions", "function_call",
                 "user_api_key", "api_key", "web_search", "plugins"}
    if any(key in payload for key in forbidden):
        raise _error("invalid_model_payload")
    messages = payload.get("messages")
    if (type(messages) is not list or len(messages) != 2
            or any(type(m) is not dict or set(m) != {"role", "content"}
                   for m in messages)
            or [m["role"] for m in messages] != ["system", "user"]
            or any(type(m["content"]) is not str or
                   not 0 < len(m["content"]) <= 25000 for m in messages)):
        raise _error("invalid_model_payload")
    result = dict(payload)
    # No inference-specific defaults added here: the benchmark must decide
    # the same reasoning settings for each AI and document differences.
    return result


def openrouter_transport(
    provider: str, *, allow_inference: bool = False,
    request: Callable[[str, str, dict | None], dict] = _request,
    key_reader: Callable[[str], str] = _read_key,
) -> Callable[[Mapping], TransportResponse]:
    """Make a disabled-by-default callable; never touch other provider keys."""
    if provider not in MODELS or type(allow_inference) is not bool:
        raise ValueError("invalid_arena_provider")
    model = MODELS[provider]

    def send(payload: Mapping) -> TransportResponse:
        if allow_inference is not True or os.environ.get("DESK_MODE") != "paper":
            raise _error("provider_disabled")
        clean = _validate_payload(payload, model)
        try:
            key = key_reader(provider)
            _verify_key_budget(request("/key", key, None))
            result = request("/chat/completions", key, clean)
        except ProviderUnavailable:
            raise
        except Exception:
            raise _error() from None
        if type(result) is not dict or type(result.get("choices")) is not list:
            raise _error()
        return TransportResponse(status_code=200, body=result)

    return send
