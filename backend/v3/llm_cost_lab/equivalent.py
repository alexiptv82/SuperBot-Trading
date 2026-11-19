"""Input EQUIVALENTE per il confronto dei modelli: la stessa richiesta che il Brain manderebbe a DeepSeek.

Il primo laboratorio mandava ai modelli solo simbolo, prezzo e regime: non e' l'informazione che il decisore vero
riceve (vista di mercato multi-timeframe, scoreboard, menu delle strategie, osservazioni di Falco/Toro), quindi un
confronto su quell'input non direbbe nulla sul Brain. Qui la richiesta NON viene ricostruita a mano: la costruisce il
vero ``DeepSeekL5Analyst`` (stesso codice di produzione), con un trasporto che la CATTURA e non apre connessioni.
Ogni braccio riceve poi la stessa richiesta, cambiando solo ``model``.

Punto nel tempo: candele e esiti vengono filtrati all'istante della decisione PRIMA di passarli all'analista
(candele chiuse entro ``t``, esiti chiusi entro ``t``), cosi' un dato successivo non puo' entrare nella richiesta.
Nessun importo del conto e' nella richiesta (solo il numero di posizioni aperte): verificato dai test.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Callable, Mapping, Optional, Sequence

from backend.v3.brain_f2.contracts import MarketContext
from backend.v3.brain_market.deepseek_l5 import DeepSeekL5Analyst
from backend.v3.brain_market.view import regime_for_context
from backend.v3.llm_cost_lab.models import ModelSpec, forbid_auto_model
from backend.v3.brain_f3.providers import TransportResponse

_NO_TRADE_BODY = {"choices": [{"finish_reason": "stop", "message": {"content": '{"kind":"NO_TRADE"}'}}]}
FORBIDDEN_KEYS = frozenset({"equity", "balance", "available_cash", "margin", "pnl", "realized_pnl", "api_key",
                            "token", "secret", "account"})


class _Capture:
    """Trasporto locale: registra la richiesta, risponde NO_TRADE, nessuna rete."""

    def __init__(self) -> None:
        self.payloads: list = []

    def __call__(self, payload):
        self.payloads.append(copy.deepcopy(payload))
        return TransportResponse(200, _NO_TRADE_BODY)


def bars_until(bars_by_tf: Mapping[str, Sequence], candle_ms_by_tf: Mapping[str, int], t_ms: int) -> dict:
    """Solo candele CHIUSE entro t: apertura + durata <= t."""
    out = {}
    for tf, rows in bars_by_tf.items():
        step = candle_ms_by_tf[tf]
        out[tf] = [b for b in rows if b.open_time_ms + step <= t_ms]
    return out


def outcomes_until(outcomes: Sequence, t_ms: int) -> list:
    """Solo esiti chiusi entro t: lo scoreboard non puo' conoscere il futuro."""
    return [o for o in outcomes if getattr(o, "closed_at_ms", None) is not None and o.closed_at_ms <= t_ms]


def _walk_keys(value, found: set) -> None:
    if isinstance(value, Mapping):
        for k, v in value.items():
            found.add(str(k).lower())
            _walk_keys(v, found)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _walk_keys(v, found)


def capture_l5_request(*, symbol: str, t_ms: int, bars_by_tf: Mapping[str, Sequence], outcomes: Sequence,
                       open_position_count: int, view_params, market_params, menu,
                       falco_signal: Optional[Mapping] = None, toro_signal: Optional[Mapping] = None,
                       max_tokens: int = 256) -> dict:
    """Richiesta L5 identica a quella di produzione per (simbolo, istante), costruita dal vero analista."""
    if type(open_position_count) is not int or open_position_count < 0:
        raise ValueError("invalid_open_position_count")
    steps = {s.name: s.candle_ms for s in market_params.timeframes}
    bars = bars_until(bars_by_tf, steps, t_ms)
    past = outcomes_until(outcomes, t_ms)
    regime = regime_for_context(bars, timestamp_ms=t_ms, params=market_params)
    base_tf = market_params.timeframes[0].name
    base = bars.get(base_tf) or []
    if not base:
        raise ValueError("market_data_unavailable")
    context = MarketContext(symbol, base[-1].close, t_ms, regime, falco_signal, toro_signal)
    capture = _Capture()
    analyst = DeepSeekL5Analyst(transport=capture, model="deepseek-flash", bars_source=lambda _s: bars,
                                outcomes_source=lambda: past, view_params=view_params,
                                market_params=market_params, menu=menu, spending_gate=lambda _v: True,
                                enabled=True, max_tokens=max_tokens)
    analyst.analyze(context, [{}] * open_position_count)
    if len(capture.payloads) != 1:
        raise ValueError("capture_failed")
    payload = capture.payloads[0]
    assert_no_account_data(payload)
    return payload


def assert_no_account_data(payload: Mapping) -> None:
    """Nessuna chiave da dati del conto nella richiesta che uscirebbe verso un provider esterno."""
    keys: set = set()
    _walk_keys(json.loads(payload["messages"][1]["content"]), keys)
    if keys & FORBIDDEN_KEYS:
        raise ValueError("account_data_in_request")


def request_for(payload: Mapping, spec: ModelSpec) -> dict:
    """La stessa richiesta per un altro braccio: cambia solo ``model``."""
    forbid_auto_model(spec.model_id)
    out = copy.deepcopy(dict(payload))
    out["model"] = spec.model_id
    return out


def request_fingerprint(payload: Mapping) -> str:
    """Impronta di cio' che il modello vede (messaggi + limiti), escluso il nome del modello."""
    body = {k: v for k, v in payload.items() if k != "model"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def context_sha256(payload: Mapping) -> str:
    """SHA-256 del messaggio utente: la stessa formula di ``DeepSeekL5Analyst`` per ``OpenProposal.context_hash``,
    che l'executor PAPER scrive in ``paper_open.context_hash``."""
    return hashlib.sha256(payload["messages"][1]["content"].encode()).hexdigest()


def matches_recorded_context(payload: Mapping, recorded_context_hash: object) -> bool:
    """Prova di equivalenza su dati storici: la richiesta ricostruita e' IDENTICA a quella che DeepSeek vide davvero
    solo se l'hash coincide con quello registrato nel journal. Se non coincide, quel campione non e' confrontabile
    (vista o scoreboard diversi) e va escluso, non approssimato."""
    return type(recorded_context_hash) is str and len(recorded_context_hash) == 64 and \
        context_sha256(payload) == recorded_context_hash
