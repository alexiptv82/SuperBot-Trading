"""Contatore di spesa del modello e fermo per tetto giornaliero (A3).

Il ``SpendingGate`` di ``budget.py`` CONTROLLA il tetto ma nessuno scrive quanto si e' speso: senza un contatore
il tetto non scatterebbe mai. ``MeteredTransport`` avvolge il trasporto del fornitore e, dopo ogni chiamata,
scrive nel registro (``BudgetLedger.record_spend``) la spesa in micro-dollari:

* risposta con ``usage`` valido -> ``prompt_tokens`` e ``completion_tokens`` ai prezzi configurati (sempre il prezzo
  del token NON in cache: stima prudente), arrotondata per eccesso;
* risposta senza ``usage`` valido, oppure chiamata fallita (la rete puo' aver fatto lavorare il fornitore): stima
  PRUDENTE dalla dimensione della richiesta (caratteri / 2 come token in ingresso) piu' ``max_tokens`` in uscita.

Se la scrittura nel registro fallisce la risposta viene scartata (fail-closed) e ``accounting_failed`` resta vero:
``BudgetHalt`` ferma allora i nuovi giri del Brain (le uscite proseguono). Nessun testo del modello, nessuna
chiave e nessun contenuto della richiesta entrano nel registro: solo unita' e il tipo di stima.

``extra_payload`` aggiunge campi di primo livello alla richiesta (es. ``{"thinking": {"type": "disabled"}}``) SOLO
se la richiesta non li ha gia': i campi scelti dall'analista restano autorevoli.
"""
from __future__ import annotations

import fcntl
import json
import os
from decimal import ROUND_CEILING, Decimal
from typing import Any, Mapping, Optional

from backend.v3.brain_f3.providers import ProviderUnavailable, Transport, TransportResponse
from backend.v3.budget import BudgetLedger

_MAX_TOKENS = 10_000_000
_DEFAULT_MAX_OUT = 4096
_MAX_OUT_CAP = 65_536


def _ceil(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def usage_units(body: Any, input_per_m: Decimal, output_per_m: Decimal) -> Optional[int]:
    """Micro-dollari dalla ``usage`` della risposta, o ``None`` se manca o e' incoerente."""
    usage = body.get("usage") if isinstance(body, Mapping) else None
    if not isinstance(usage, Mapping):
        return None
    p, c = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if (type(p) is not int or type(c) is not int or not 0 <= p <= _MAX_TOKENS or not 0 <= c <= _MAX_TOKENS):
        return None
    return _ceil(p * input_per_m + c * output_per_m)          # $/M token == micro-dollari per token


def estimate_units(payload: Mapping[str, Any], input_per_m: Decimal, output_per_m: Decimal) -> int:
    """Stima prudente quando la spesa vera non e' nota."""
    try:
        chars = len(json.dumps(payload, sort_keys=True, default=str))
    except Exception:
        chars = 100_000
    max_out = payload.get("max_tokens") if isinstance(payload, Mapping) else None
    out = max_out if type(max_out) is int and 0 <= max_out <= _MAX_OUT_CAP else _DEFAULT_MAX_OUT
    return _ceil((chars // 2 + 1) * input_per_m + out * output_per_m)


def worst_case_units(payload: Mapping[str, Any], input_per_m: Decimal, output_per_m: Decimal) -> int:
    """LIMITE SUPERIORE della spesa di una chiamata (non una stima): nessun tokenizer produce piu' token dei byte
    UTF-8 del testo inviato, e il fornitore tronca l'uscita (ragionamento compreso) a ``max_tokens``. Senza un
    ``max_tokens`` valido si assume il massimo accettato. Usato dalla prenotazione dell'Arena."""
    try:
        raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
        in_tokens = len(raw)
    except Exception:
        in_tokens = 1_000_000                                      # non misurabile: massimo prudente
    max_out = payload.get("max_tokens") if isinstance(payload, Mapping) else None
    out = max_out if type(max_out) is int and 0 < max_out <= _MAX_OUT_CAP else _MAX_OUT_CAP
    return _ceil(in_tokens * input_per_m + out * output_per_m)


class MeteredTransport:
    def __init__(self, inner: Transport, ledger: BudgetLedger, provider: str, *, input_usd_per_million: Decimal,
                 output_usd_per_million: Decimal, extra_payload: Optional[Mapping[str, Any]] = None,
                 reserve: Optional[Mapping[str, Any]] = None):
        """``reserve`` (solo Arena): ``{"daily_cap_units", "total_cap_units", "lock_path"}``. Prima di OGNI chiamata,
        sotto un lock di file esclusivo e non bloccante, si rifiuta se speso + stima MASSIMA della chiamata supera il
        tetto giornaliero o cumulativo: una chiamata non puo' partire sotto il tetto e chiudersi sopra (entro la stima
        massimo POSSIBILE: byte UTF-8 come token in ingresso + max_tokens in uscita, vedi ``worst_case_units``). Un secondo processo concorrente e' rifiutato."""
        if not callable(inner) or not isinstance(ledger, BudgetLedger) or type(provider) is not str or not provider:
            raise ValueError("invalid_meter")
        for p in (input_usd_per_million, output_usd_per_million):
            if type(p) is not Decimal or not p.is_finite() or p < 0:
                raise ValueError("invalid_meter")
        self._inner, self._ledger, self._provider = inner, ledger, provider
        self._in, self._out = input_usd_per_million, output_usd_per_million
        self._extra = dict(extra_payload or {})
        self.accounting_failed = False
        self._reserve = None
        if reserve is not None:
            d, t, lp = reserve.get("daily_cap_units"), reserve.get("total_cap_units"), reserve.get("lock_path")
            if (type(d) is not int or d <= 0 or type(t) is not int or t <= 0 or not isinstance(lp, (str, os.PathLike))
                    or set(reserve) != {"daily_cap_units", "total_cap_units", "lock_path"}):
                raise ValueError("invalid_reserve")
            self._reserve = (d, t, os.fspath(lp))

    def _charge(self, units: int, basis: str) -> None:
        try:
            self._ledger.record_spend(self._provider, units, {"basis": basis})
        except Exception:
            self.accounting_failed = True
            raise

    def __call__(self, payload: Mapping[str, Any]) -> TransportResponse:
        sent = {**{k: v for k, v in self._extra.items() if k not in payload}, **payload}
        if self._reserve is None:
            return self._call(sent)
        daily_cap, total_cap, lock_path = self._reserve
        try:
            fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except OSError:
            raise ProviderUnavailable("budget_reserve_unavailable") from None
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ProviderUnavailable("budget_reserve_busy") from None      # altro processo sulla stessa AI
            try:
                worst = worst_case_units(sent, self._in, self._out)
                total = self._ledger.total_spend(self._provider)
                daily = self._ledger.daily_spend(self._provider)
            except Exception:
                raise ProviderUnavailable("budget_reserve_unavailable") from None
            if type(daily) is not int or total + worst > total_cap or daily + worst > daily_cap:
                raise ProviderUnavailable("budget_reserve_denied")
            return self._call(sent)
        finally:
            os.close(fd)                                                       # rilascia anche il lock

    def _call(self, sent: Mapping[str, Any]) -> TransportResponse:
        try:
            response = self._inner(sent)
        except Exception:
            try:                  # chiamata fallita: forse fatturata. Arena = limite superiore, mai sotto-contare
                bound = worst_case_units if self._reserve is not None else estimate_units
                self._charge(bound(sent, self._in, self._out), "estimate_failed_call")
            except Exception:
                pass                                           # il guasto del registro e' gia' segnato
            raise
        body = response.body if isinstance(response, TransportResponse) else None
        units = usage_units(body, self._in, self._out)
        basis = "usage"
        if units is None:
            bound = worst_case_units if self._reserve is not None else estimate_units
            units, basis = bound(sent, self._in, self._out), "estimate_no_usage"
        try:
            self._charge(units, basis)
        except Exception:
            raise ProviderUnavailable("provider_unavailable") from None
        return response


class BudgetHalt:
    """``halted()`` per il Runner: ``"budget"`` a tetto giornaliero raggiunto, ``"ledger_error"`` se il registro e' rotto."""

    def __init__(self, ledger: BudgetLedger, provider: str, daily_cap_units: int, metered: MeteredTransport,
                 *, trial_cap_units: Optional[int] = None):
        if (not isinstance(ledger, BudgetLedger) or type(provider) is not str or not provider
                or type(daily_cap_units) is not int or daily_cap_units <= 0 or not isinstance(metered, MeteredTransport)):
            raise ValueError("invalid_halt")
        if trial_cap_units is not None and (type(trial_cap_units) is not int or trial_cap_units <= 0):
            raise ValueError("invalid_trial_budget")
        self._ledger, self._provider, self._cap, self._metered = ledger, provider, daily_cap_units, metered
        self._trial_cap = trial_cap_units

    def __call__(self) -> Optional[str]:
        if self._metered.accounting_failed:
            return "ledger_error"
        try:
            if self._trial_cap is not None and self._ledger.total_spend(self._provider) >= self._trial_cap:
                return "trial_budget"
            return "budget" if self._ledger.daily_spend(self._provider) >= self._cap else None
        except Exception:
            return "ledger_error"  # Arena total must never fail open
