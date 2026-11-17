"""Traccia per chiamata delle AI dell'Arena: parametri di ragionamento EFFETTIVAMENTE inviati, token (anche di
ragionamento), latenza ed esito. Serve a rendere misurabile l'asimmetria fra modelli, non a cambiarla.

Append-only (``inference_trace.jsonl`` nella cartella della run). Mai testo dei messaggi, mai chiavi, mai risposte.
Un errore di scrittura della traccia non blocca la chiamata (la contabilita' di spesa resta quella del metering).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from backend.v3.brain_f3.providers import TransportResponse

REASONING_KEYS = ("thinking", "reasoning", "reasoning_effort", "include_reasoning")


def _int(v: Any):
    return v if type(v) is int and v >= 0 else None


def summarize_usage(body: Any) -> dict:
    usage = body.get("usage") if isinstance(body, Mapping) else None
    if not isinstance(usage, Mapping):
        return {"usage_present": False}
    details = usage.get("completion_tokens_details")
    reasoning = details.get("reasoning_tokens") if isinstance(details, Mapping) else None
    choice = (body.get("choices") or [None])[0] if isinstance(body.get("choices"), list) else None
    finish = choice.get("finish_reason") if isinstance(choice, Mapping) else None
    cost = usage.get("cost")
    return {"usage_present": True, "prompt_tokens": _int(usage.get("prompt_tokens")),
            "completion_tokens": _int(usage.get("completion_tokens")), "reasoning_tokens": _int(reasoning),
            "provider_reported_cost": str(cost) if type(cost) in (int, float, str) else None,
            "finish_reason": finish if type(finish) is str and len(finish) <= 32 else None}


class TracedTransport:
    def __init__(self, inner: Callable[[Mapping], TransportResponse], path: Path, *, provider: str,
                 monotonic: Callable[[], float] = time.monotonic, wall_ms: Callable[[], int] = lambda: int(time.time() * 1000)):
        if not callable(inner):
            raise ValueError("invalid_trace_inner")
        self._inner, self._path, self._provider = inner, Path(path), provider
        self._mono, self._wall = monotonic, wall_ms
        self.write_failures = 0

    def _write(self, rec: dict) -> None:
        try:
            fd = os.open(self._path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                os.write(fd, (json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n").encode())
            finally:
                os.close(fd)
        except OSError:
            self.write_failures += 1

    def __call__(self, payload: Mapping) -> TransportResponse:
        base = {"schema": "arena_inference_trace_v1", "provider": self._provider, "ts_ms": self._wall(),
                "model": payload.get("model") if isinstance(payload, Mapping) else None,
                "max_tokens": payload.get("max_tokens") if isinstance(payload, Mapping) else None,
                "reasoning_params_sent": {k: payload[k] for k in REASONING_KEYS
                                          if isinstance(payload, Mapping) and k in payload}}
        start = self._mono()
        try:
            response = self._inner(payload)
        except Exception as exc:
            self._write({**base, "latency_ms": int((self._mono() - start) * 1000), "outcome": "error",
                         "error_code": str(exc)[:48] if str(exc).replace("_", "").isalnum() else "error"})
            raise
        body = response.body if isinstance(response, TransportResponse) else None
        self._write({**base, "latency_ms": int((self._mono() - start) * 1000), "outcome": "response",
                     "status_code": getattr(response, "status_code", None), **summarize_usage(body)})
        return response
