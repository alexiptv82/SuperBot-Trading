"""HTTP transport factory for DeepSeek and Claude AI providers — F4.

Implements the ``Transport = Callable[[Mapping[str, Any]], TransportResponse]``
interface defined in ``brain_f3.providers``.

Design constraints:
- stdlib only: urllib.request, urllib.error, json, ssl, os — no pip installs.
- Credentials injected via environment variables at call time, never stored.
- On any failure: raise ProviderUnavailable("provider_unavailable") with no
  credential, URL or response-body leakage in the exception message.
- Timeout: 30 s connect + read; non-negotiable.
- Response body read once, size-capped at 64 KiB before JSON parsing.

Usage::

    from backend.v3.transport import deepseek_transport, claude_transport
    from backend.v3.brain_f3.providers import DeepSeekAnalystAdapter

    adapter = DeepSeekAnalystAdapter(
        transport=deepseek_transport(),   # factory returns a callable
        spending_gate=my_gate,
        model="deepseek-chat",
        enabled=True,
    )
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Any, Mapping

from backend.v3.brain_f3.providers import ProviderUnavailable, TransportResponse

# Hard-coded ceiling; never expose response bodies in exceptions.
_MAX_RESPONSE_BYTES = 65_536  # 64 KiB
_TIMEOUT_SECONDS = 30

# Provider endpoint URLs — no credentials embedded here.
_DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
_CLAUDE_URL = "https://api.anthropic.com/v1/messages"

# Anthropic API version header (required for the Messages API).
_ANTHROPIC_VERSION = "2023-06-01"


def _make_ssl_context() -> ssl.SSLContext:
    """Return a strict SSL context (no self-signed, hostname check on)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def _do_post(url: str, headers: dict[str, str], payload: Mapping[str, Any]) -> TransportResponse:
    """
    POST *payload* as JSON to *url* with *headers*.

    Returns TransportResponse on HTTP 200.
    Raises ProviderUnavailable on any other outcome, with no credential leakage.
    """
    try:
        body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        raise ProviderUnavailable("provider_unavailable")

    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )

    ssl_ctx = _make_ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS, context=ssl_ctx) as resp:
            status_code: int = resp.getcode()
            raw = resp.read(_MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        # Intentionally swallow status code and body — do not propagate.
        raise ProviderUnavailable("provider_unavailable") from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise ProviderUnavailable("provider_unavailable") from None
    except Exception:
        raise ProviderUnavailable("provider_unavailable") from None

    if status_code != 200:
        raise ProviderUnavailable("provider_unavailable")

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ProviderUnavailable("provider_unavailable") from None

    if not isinstance(parsed, dict):
        raise ProviderUnavailable("provider_unavailable")

    return TransportResponse(status_code=200, body=parsed)


# ---------------------------------------------------------------------------
# Public factory functions
# ---------------------------------------------------------------------------

def deepseek_transport(
    *,
    api_key_env: str = "DEEPSEEK_API_KEY",
) -> "Callable[[Mapping[str, Any]], TransportResponse]":
    """
    Return a Transport callable that sends requests to the DeepSeek chat
    completions endpoint.

    The API key is read from the environment variable named *api_key_env*
    at **call time** (not at factory time), so it is never stored in the
    closure beyond one function invocation.

    Raises ProviderUnavailable immediately if the env var is unset or empty.
    """
    def _transport(payload: Mapping[str, Any]) -> TransportResponse:
        api_key = os.environ.get(api_key_env, "").strip()
        if not api_key:
            raise ProviderUnavailable("provider_unavailable")
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            return _do_post(_DEEPSEEK_URL, headers, payload)
        finally:
            # Explicitly clear local reference — belt-and-suspenders.
            api_key = ""  # noqa: F841

    return _transport


def claude_transport(
    *,
    api_key_env: str = "ANTHROPIC_API_KEY",
    anthropic_version: str = _ANTHROPIC_VERSION,
) -> "Callable[[Mapping[str, Any]], TransportResponse]":
    """
    Return a Transport callable that sends requests to the Anthropic Messages
    API endpoint.

    The API key is read from the environment variable named *api_key_env*
    at **call time**.

    Raises ProviderUnavailable immediately if the env var is unset or empty.
    """
    def _transport(payload: Mapping[str, Any]) -> TransportResponse:
        api_key = os.environ.get(api_key_env, "").strip()
        if not api_key:
            raise ProviderUnavailable("provider_unavailable")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": anthropic_version,
        }
        try:
            return _do_post(_CLAUDE_URL, headers, payload)
        finally:
            api_key = ""  # noqa: F841

    return _transport
