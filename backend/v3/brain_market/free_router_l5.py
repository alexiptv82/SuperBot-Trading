"""Analista L5 che parla con un router OpenAI-compatibile di soli provider gratuiti.

Il contratto di uscita è quello di DeepSeek L5: NO_TRADE oppure OPEN. Un NO_TRADE
valido del router è una decisione e non scatena il fallback. Il fallback a DeepSeek,
a pagamento, parte solo se il router fallisce e solo una volta per simbolo e ciclo.
Non riprova in modo da non aprire due volte.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import logging
import os
import time
import urllib.parse
from collections.abc import Mapping
from typing import Callable, Optional

from backend.v3.brain_f2.analyst import Analyst
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext
from backend.v3.brain_f3.providers import ProviderUnavailable
from backend.v3.brain_market.deepseek_l5 import SYSTEM_PROMPT, decision_from_chat_body

log = logging.getLogger(__name__)

_FAILURES = frozenset({
    "free_router:timeout", "free_router:connection", "free_router:http_429",
    "free_router:http_5xx", "free_router:invalid_json", "free_router:schema",
    "free_router:missing_key", "free_router:url_rejected",
})


class RouterFailure(Exception):
    """Codice stabile. Il messaggio non contiene URL né chiavi."""

    def __init__(self, code: str, meta: Optional[dict] = None):
        super().__init__(code if code in _FAILURES else "free_router:connection")
        self.code = code if code in _FAILURES else "free_router:connection"
        self.meta = dict(meta or {})


class RouterCall:
    def __init__(self, status: int, headers: Mapping[str, str], raw: bytes, latency_ms: int):
        self.status = status
        self.headers = {str(k).lower(): str(v) for k, v in headers.items()}
        self.raw = raw
        self.latency_ms = latency_ms

    def meta(self) -> dict:
        out: dict = {}
        if type(self.latency_ms) is int and self.latency_ms >= 0:
            out["latency_ms"] = self.latency_ms
        via = self.headers.get("x-routed-via", "")
        if via:
            out["routed_via"] = via[:64]
        attempts = self.headers.get("x-fallback-attempts", "")
        if attempts.isdigit():
            out["fallback_attempts"] = int(attempts)
        try:
            body = json.loads(self.raw.decode("utf-8"))
            usage = body.get("usage") if type(body) is dict else None
            if type(usage) is dict:
                for src, dst in (("prompt_tokens", "prompt_tokens"),
                                 ("completion_tokens", "completion_tokens")):
                    number = usage.get(src)
                    if type(number) is int and number >= 0:
                        out[dst] = number
        except (UnicodeError, ValueError, TypeError):
            pass
        return out


def brain_llm_provider() -> str:
    """Default ``deepseek``: il processo attuale non cambia finché l'utente non lo gira."""
    raw = os.environ.get("BRAIN_LLM_PROVIDER", "deepseek").strip().lower()
    if raw in ("", "deepseek"):
        return "deepseek"
    if raw == "free_router":
        return "free_router"
    raise ValueError("invalid_llm_provider")


def deepseek_fallback_enabled() -> bool:
    """Con il router acceso il fallback a DeepSeek è vero se la variabile manca.

    ``false`` lo spegne. Un NO_TRADE valido del router non è un fallimento e non arriva qui.
    """
    raw = os.environ.get("DEEPSEEK_FALLBACK")
    if raw is None or raw.strip() == "":
        return brain_llm_provider() == "free_router"
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _allow_remote() -> bool:
    return os.environ.get("LLM_ROUTER_ALLOW_REMOTE", "").strip().lower() in ("1", "true", "yes", "on")


def validate_router_url(url: str, *, allow_remote: bool = False) -> str:
    """Accetta solo loopback o rete privata, salvo override esplicito."""
    if type(url) is not str or not url or len(url) > 200:
        raise RouterFailure("free_router:url_rejected")
    parts = urllib.parse.urlsplit(url.strip())
    host = parts.hostname
    if parts.scheme not in ("http", "https") or not host or parts.username or parts.password:
        raise RouterFailure("free_router:url_rejected")
    if allow_remote:
        return url.strip().rstrip("/")
    if host.lower() == "localhost":
        return url.strip().rstrip("/")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise RouterFailure("free_router:url_rejected") from None
    if not (ip.is_loopback or ip.is_private or ip.is_link_local):
        raise RouterFailure("free_router:url_rejected")
    return url.strip().rstrip("/")


def router_settings_from_env() -> dict:
    timeout_raw = os.environ.get("LLM_ROUTER_TIMEOUT_S", "30").strip()
    try:
        timeout_s = float(timeout_raw)
    except ValueError:
        timeout_s = 30.0
    if not 1 <= timeout_s <= 120:
        timeout_s = 30.0
    return {
        "url": os.environ.get("LLM_ROUTER_URL", "http://127.0.0.1:3001/v1").strip(),
        "key": os.environ.get("LLM_ROUTER_KEY", ""),
        "model": os.environ.get("LLM_ROUTER_MODEL", "auto:smart").strip() or "auto:smart",
        "timeout_s": timeout_s,
        "allow_remote": _allow_remote(),
    }


def http_post(settings: Mapping, payload: Mapping) -> RouterCall:
    """Una sola richiesta. Nessun redirect e nessun secondo tentativo."""
    key = settings.get("key") if isinstance(settings, Mapping) else ""
    if type(key) is not str or not key.strip():
        raise RouterFailure("free_router:missing_key")
    try:
        base = validate_router_url(str(settings.get("url", "")),
                                   allow_remote=bool(settings.get("allow_remote")))
    except RouterFailure:
        raise
    parts = urllib.parse.urlsplit(base)
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    path = (parts.path or "") + "/chat/completions"
    path = path.replace("//", "/")
    if parts.query:
        path += "?" + parts.query
    timeout = settings.get("timeout_s") if isinstance(settings.get("timeout_s"), (int, float)) else 30
    body = json.dumps(payload).encode("utf-8")
    conn_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    started = time.monotonic()
    conn = conn_cls(host, port, timeout=timeout)
    try:
        conn.request("POST", path, body=body, headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        resp = conn.getresponse()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        raw = resp.read(1_000_000)
        status = resp.status
    except TimeoutError:
        raise RouterFailure("free_router:timeout") from None
    except OSError:
        raise RouterFailure("free_router:connection") from None
    finally:
        conn.close()
    return RouterCall(status, headers, raw, int((time.monotonic() - started) * 1000))


def _no_trade(context: MarketContext, rationale: str, route: dict) -> BrainDecision:
    return BrainDecision(
        kind=DecisionKind.NO_TRADE, rationale=rationale, sources=["free_router:analysis"],
        occurred_at_ms=context.timestamp_ms, llm_route=route)


def _log_route(route: dict) -> None:
    log.info(
        "llm_route source=%s failure=%s routed_via=%s latency_ms=%s cost_units=%s",
        route.get("source"), route.get("router_failure"), route.get("routed_via"),
        route.get("latency_ms"), route.get("deepseek_cost_units"))


class FreeRouterL5Analyst(Analyst):
    """Stesso analista L5, con router gratuito e al massimo un fallback DeepSeek."""

    def __init__(self, *, template, fallback: Optional[object],
                 fallback_enabled: bool, settings: Optional[Mapping] = None,
                 poster: Optional[Callable[[Mapping, Mapping], RouterCall]] = None,
                 ledger=None):
        if not callable(getattr(template, "l5_packet", None)) or not hasattr(template, "max_tokens"):
            raise ValueError("invalid_template")
        if fallback is not None and not callable(getattr(fallback, "analyze", None)):
            raise ValueError("invalid_fallback")
        if type(fallback_enabled) is not bool:
            raise ValueError("invalid_fallback_flag")
        self.template = template
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled
        self.settings = dict(settings if settings is not None else router_settings_from_env())
        self.poster = poster or http_post
        self.ledger = ledger
        self._fallback_used: set[tuple[str, int]] = set()

    def _spend(self) -> int:
        if self.ledger is None:
            return 0
        try:
            return int(self.ledger.daily_spend("deepseek"))
        except Exception:
            return 0

    def _fallback_once(self, context: MarketContext, open_positions: list[Mapping],
                       code: str, meta: dict) -> BrainDecision:
        key = (context.symbol, context.timestamp_ms)
        route = dict(meta)
        route["router_failure"] = code
        if key in self._fallback_used or not self.fallback_enabled or self.fallback is None:
            route["source"] = "free_router"
            rationale = code if not self.fallback_enabled or self.fallback is None else "free_router:fallback_used"
            if key in self._fallback_used:
                rationale = "free_router:fallback_used"
            decision = _no_trade(context, rationale, route)
            _log_route(route)
            return decision
        self._fallback_used.add(key)
        before = self._spend()
        try:
            decision = self.fallback.analyze(context, open_positions)
        except ProviderUnavailable as exc:
            after = self._spend()
            message = exc.args[0] if exc.args and type(exc.args[0]) is str else ""
            rationale = "free_router:deepseek_cap" if message == "budget_denied" else "free_router:deepseek_failed"
            route["source"] = "deepseek_fallback"
            route["deepseek_cost_units"] = max(0, after - before)
            decision = _no_trade(context, rationale, route)
            _log_route(route)
            return decision
        except Exception:
            route["source"] = "deepseek_fallback"
            route["deepseek_cost_units"] = max(0, self._spend() - before)
            decision = _no_trade(context, "free_router:deepseek_failed", route)
            _log_route(route)
            return decision
        after = self._spend()
        route["source"] = "deepseek_fallback"
        route["deepseek_cost_units"] = max(0, after - before)
        decision.llm_route = route
        _log_route(route)
        return decision

    def analyze(self, context: MarketContext, open_positions: list[Mapping]) -> BrainDecision:
        try:
            info_json, sources = self.template.l5_packet(context, open_positions)
        except ProviderUnavailable:
            route = {"source": "free_router", "router_failure": "free_router:invalid_market"}
            _log_route(route)
            return _no_trade(context, "free_router:invalid_market", route)
        sources = ["free_router:analysis" if item == "deepseek:analysis" else item for item in sources]
        model = self.settings.get("model") if type(self.settings.get("model")) is str else "auto:smart"
        payload = {
            "model": model or "auto:smart", "stream": False,
            "max_tokens": self.template.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": info_json},
            ],
        }
        try:
            call = self.poster(self.settings, payload)
        except RouterFailure as exc:
            return self._fallback_once(context, open_positions, exc.code, exc.meta)
        except Exception:
            return self._fallback_once(context, open_positions, "free_router:connection", {})
        if not isinstance(call, RouterCall):
            return self._fallback_once(context, open_positions, "free_router:connection", {})
        meta = call.meta()
        if call.status == 429:
            return self._fallback_once(context, open_positions, "free_router:http_429", meta)
        if type(call.status) is int and 500 <= call.status <= 599:
            return self._fallback_once(context, open_positions, "free_router:http_5xx", meta)
        if call.status != 200:
            return self._fallback_once(context, open_positions, "free_router:connection", meta)
        try:
            body = json.loads(call.raw.decode("utf-8"))
        except (UnicodeError, ValueError, TypeError):
            return self._fallback_once(context, open_positions, "free_router:invalid_json", meta)
        if type(body) is not dict:
            return self._fallback_once(context, open_positions, "free_router:invalid_json", meta)
        try:
            decision = decision_from_chat_body(
                body, context=context, info_json=info_json, sources=sources,
                rationale="free_router:analysis", originating_ai="free_router")
        except ProviderUnavailable:
            return self._fallback_once(context, open_positions, "free_router:schema", meta)
        route = dict(meta)
        route["source"] = "free_router"
        decision.llm_route = route
        _log_route(route)
        return decision
