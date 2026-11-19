"""Valutazione SHADOW: registra, non ordina, non fa fallback."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from backend.v3.brain_market.deepseek_l5 import SYSTEM_PROMPT
from backend.v3.llm_cost_lab.models import ModelSpec, forbid_auto_model
from backend.v3.llm_cost_lab.schema import chat_content, parse_decision, token_pair
from backend.v3.llm_cost_lab.store import ShadowStore
from backend.v3.llm_cost_lab.equivalent import request_fingerprint, request_for
from backend.v3.runner.metering import estimate_units, usage_units

log = logging.getLogger(__name__)

_MAX_AGE_MS = 15 * 60 * 1000


@dataclass(frozen=True)
class MarketSample:
    sample_id: str
    symbol: str
    price: str
    regime: str
    asof_ms: int
    received_ms: int
    now_ms: int


@dataclass(frozen=True)
class LabResponse:
    status: int
    body: Optional[dict]
    latency_ms: int


class LiveCallsDisabled(RuntimeError):
    """Il laboratorio offline non apre socket verso provider."""


def post_once(*_args, **_kwargs):
    raise LiveCallsDisabled("live_calls_disabled")


class ShadowSession:
    """Un tentativo per modello. I modelli sono bracci del confronto, non una catena."""

    def __init__(self, *, models: Sequence[ModelSpec], store: ShadowStore,
                 poster: Callable[[str, Mapping], LabResponse],
                 max_requests_per_model: int = 1,
                 max_micro_usd: int = 1_000_000,
                 max_age_ms: int = _MAX_AGE_MS):
        if not models or any(not isinstance(item, ModelSpec) for item in models):
            raise ValueError("invalid_models")
        self.models = tuple(forbid_auto_model(item.model_id) for item in models)
        if not isinstance(store, ShadowStore) or not callable(poster):
            raise ValueError("invalid_session")
        if type(max_requests_per_model) is not int or max_requests_per_model < 1:
            raise ValueError("invalid_budget")
        if type(max_micro_usd) is not int or max_micro_usd < 0:
            raise ValueError("invalid_budget")
        self.store = store
        self.poster = poster
        self.max_requests_per_model = max_requests_per_model
        self.max_micro_usd = max_micro_usd
        self.max_age_ms = max_age_ms
        self._calls = {item.model_id: 0 for item in self.models}
        self._spent_micro = 0
        self.calls_made: list[str] = []

    def evaluate(self, sample: MarketSample, request: Optional[Mapping] = None) -> list[dict]:
        """``request``: richiesta equivalente a quella del Brain (``equivalent.capture_l5_request``). Ogni braccio
        riceve la stessa, cambiando solo ``model``. Senza, si usa il vecchio input semplificato (solo test)."""
        records = []
        for spec in self.models:
            record = self._one(spec, sample, request)
            self.store.append(record)
            records.append(record)
        return records

    def _one(self, spec: ModelSpec, sample: MarketSample, request: Optional[Mapping] = None) -> dict:
        base = self._base(spec, sample)
        base["input_kind"] = "equivalent_l5" if request is not None else "simplified"
        problem = self._sample_problem(sample)
        if problem:
            base.update(action="NO_TRADE", direction=None, valid=False, failure=problem,
                        reason=problem, attempts=0, may_open=False)
            self._log(base)
            return base
        if self._calls[spec.model_id] >= self.max_requests_per_model:
            base.update(action="NO_TRADE", direction=None, valid=False, failure="rate_limit",
                        reason="rate_limit", attempts=0, may_open=False)
            self._log(base)
            return base
        payload = request_for(request, spec) if request is not None else self._payload(spec, sample)
        base["request_sha256"] = request_fingerprint(payload)
        estimate = estimate_units(
            payload, spec.input_usd_per_million, spec.output_usd_per_million)
        if self._spent_micro + estimate > self.max_micro_usd:
            base.update(action="NO_TRADE", direction=None, valid=False, failure="budget",
                        reason="budget", attempts=0, may_open=False, cost_micro_usd=None,
                        cost_origin="not_measured")
            self._log(base)
            return base
        self._calls[spec.model_id] += 1
        self.calls_made.append(spec.model_id)
        try:
            response = self.poster(spec.model_id, payload)
        except TimeoutError:
            base.update(action="NO_TRADE", direction=None, valid=False, failure="timeout",
                        reason="timeout", attempts=1, may_open=False)
            self._log(base)
            return base
        except OSError:
            base.update(action="NO_TRADE", direction=None, valid=False, failure="connection",
                        reason="connection", attempts=1, may_open=False)
            self._log(base)
            return base
        except Exception:
            base.update(action="NO_TRADE", direction=None, valid=False, failure="transport",
                        reason="transport", attempts=1, may_open=False)
            self._log(base)
            return base
        return self._from_response(base, spec, payload, response)

    def _from_response(self, base: dict, spec: ModelSpec, payload: Mapping,
                       response: LabResponse) -> dict:
        latency = response.latency_ms if type(getattr(response, "latency_ms", None)) is int else None
        base["latency_ms"] = latency if latency is not None and latency >= 0 else None
        base["attempts"] = 1
        base["may_open"] = False
        status = getattr(response, "status", None)
        body = getattr(response, "body", None)
        if not isinstance(body, dict):
            base.update(action="NO_TRADE", direction=None, valid=False, failure="malformed",
                        reason="malformed")
            self._log(base)
            return base
        if status == 429:
            base.update(action="NO_TRADE", direction=None, valid=False, failure="rate_limit",
                        reason="rate_limit")
            self._charge(base, spec, payload, body)
            self._log(base)
            return base
        if status != 200:
            base.update(action="NO_TRADE", direction=None, valid=False, failure="http_error",
                        reason="http_error")
            self._charge(base, spec, payload, body if isinstance(body, dict) else None)
            self._log(base)
            return base
        try:
            parsed = parse_decision(chat_content(body))
        except ValueError as exc:
            code = exc.args[0] if exc.args else "invalid_schema"
            base.update(action="NO_TRADE", direction=None, valid=False, failure=code, reason=code)
            self._charge(base, spec, payload, body)
            self._log(base)
            return base
        if parsed.get("proposal"):
            base["proposal"] = dict(parsed["proposal"])
        base.update(action=parsed["action"], direction=parsed["direction"], valid=True,
                    failure=None, confidence=None,
                    reason="schema_no_trade" if parsed["action"] == "NO_TRADE" else "schema_open")
        self._charge(base, spec, payload, body)
        self._log(base)
        return base

    def _charge(self, record: dict, spec: ModelSpec, payload: Mapping, body: Optional[dict]) -> None:
        prompt, completion = token_pair(body)
        record["prompt_tokens"] = prompt
        record["completion_tokens"] = completion
        measured = usage_units(body, spec.input_usd_per_million, spec.output_usd_per_million) if body else None
        if measured is not None:
            record["cost_micro_usd"] = measured
            record["cost_origin"] = "simulated_usage"
            self._spent_micro += measured
            return
        record["cost_micro_usd"] = None
        record["cost_origin"] = "not_measured"

    def _payload(self, spec: ModelSpec, sample: MarketSample) -> dict:
        user = {
            "symbol": sample.symbol,
            "price": sample.price,
            "regime": sample.regime,
            "asof_ms": sample.asof_ms,
            "received_ms": sample.received_ms,
        }
        return {
            "model": spec.model_id,
            "stream": False,
            "max_tokens": 256,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user, sort_keys=True)},
            ],
        }

    def _sample_problem(self, sample: MarketSample) -> Optional[str]:
        if not isinstance(sample, MarketSample):
            return "data_missing"
        if (type(sample.symbol) is not str or not sample.symbol
                or type(sample.price) is not str or not sample.price
                or type(sample.regime) is not str or not sample.regime
                or type(sample.sample_id) is not str or not sample.sample_id):
            return "data_missing"
        for stamp in (sample.asof_ms, sample.received_ms, sample.now_ms):
            if type(stamp) is not int or stamp <= 0:
                return "data_missing"
        if sample.asof_ms > sample.now_ms or sample.received_ms > sample.now_ms:
            return "data_future"
        if sample.asof_ms > sample.received_ms:
            return "data_future"
        age = sample.now_ms - sample.asof_ms
        if age > self.max_age_ms:
            return "data_stale"
        return None

    def _base(self, spec: ModelSpec, sample: MarketSample) -> dict:
        now = sample.now_ms if isinstance(sample, MarketSample) and type(sample.now_ms) is int else 0
        asof = sample.asof_ms if isinstance(sample, MarketSample) and type(sample.asof_ms) is int else None
        return {
            "sample_id": getattr(sample, "sample_id", None),
            "symbol": getattr(sample, "symbol", None),
            "action": "NO_TRADE",
            "direction": None,
            "confidence": None,
            "confidence_verified": False,
            "reason": None,
            "regime": getattr(sample, "regime", None),
            "decision_ms": now,
            "data_asof_ms": asof,
            "freshness_ms": (now - asof) if type(asof) is int and type(now) is int else None,
            "latency_ms": None,
            "model_id": spec.model_id,
            "model_version": spec.version,
            "provider": spec.provider,
            "prompt_tokens": None,
            "completion_tokens": None,
            "cost_micro_usd": None,
            "cost_origin": "not_measured",
            "price_basis": spec.price_basis,
            "valid": False,
            "failure": None,
            "attempts": 0,
            "may_open": False,
            "shadow": True,
            "promoted": False,
            "fallback": False,
        }

    def _log(self, record: dict) -> None:
        log.info(
            "shadow model=%s action=%s failure=%s latency_ms=%s cost_micro_usd=%s",
            record.get("model_id"), record.get("action"), record.get("failure"),
            record.get("latency_ms"), record.get("cost_micro_usd"))


def open_store(directory: Path) -> ShadowStore:
    return ShadowStore(directory)
