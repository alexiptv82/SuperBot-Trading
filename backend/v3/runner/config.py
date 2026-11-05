"""Configurazione del runner del Brain PAPER: caricatore rigido di ``runner_config.json``.

**Tutti i valori nel file sono PROPOSTE di Claude, da confermare dall'utente** (regola 3 di CLAUDE.md: limiti di
rischio, soglie e costi si cambiano solo per decisione dell'utente). Si cambiano solo in quel file.
Il caricatore accetta solo i byte esatti: chiavi duplicate, costanti non finite, chiavi mancanti o in piu', tipi
sbagliati, valori fuori intervallo -> ``ValueError("invalid_config")`` (nessun dettaglio: niente valori nei messaggi).

* ``risk_policy``: i limiti del mandato di rischio (vedi ``risk.RiskPolicy``); ``minimum_equity`` >= 450 lo impone il motore.
* ``thinking``: ``"disabled"`` invia ``{"thinking": {"type": "disabled"}}`` al fornitore (il modello potrebbe ragionare
  di default e con ``max_tokens`` 256 non restituirebbe la decisione; **da verificare con una chiamata vera**), ``"omit"``
  non invia nulla.
* ``daily_cap_usd``: tetto di spesa giornaliero (giorno UTC) per il modello; i prezzi per milione di token servono solo
  a stimare la spesa (sempre al prezzo del token NON in cache: stima prudente).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from backend.v3.risk import RiskPolicy

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}USDT$")
_MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_KEYS = {"schema_version", "symbols", "initial_equity", "slippage_bps", "fee_bps", "maintenance_fraction",
         "risk_policy", "model", "thinking", "input_usd_per_million_tokens", "output_usd_per_million_tokens",
         "daily_cap_usd"}
_RISK_KEYS = set(RiskPolicy.__dataclass_fields__)


@dataclass(frozen=True)
class RunnerConfig:
    symbols: tuple[str, ...]
    initial_equity: Decimal
    slippage_bps: int
    fee_bps: Decimal
    maintenance_fraction: Decimal
    risk_policy: RiskPolicy
    model: str
    thinking: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    daily_cap_usd: Decimal

    @property
    def daily_cap_units(self) -> int:
        """Tetto in micro-dollari (1 USD = 1_000_000): e' l'unita' del registro di spesa."""
        return int(self.daily_cap_usd * 1_000_000)


def _fail() -> None:
    raise ValueError("invalid_config") from None


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            _fail()
        out[k] = v
    return out


def _reject_constant(_c):
    _fail()


def _dec(value, lo: Decimal, hi: Decimal, *, lo_open: bool = False, hi_open: bool = False) -> Decimal:
    if type(value) is not str or not value or len(value) > 24 or not value.isascii():
        _fail()
    try:
        d = Decimal(value)
    except InvalidOperation:
        _fail()
    if (not d.is_finite() or d < lo or d > hi or (lo_open and d == lo) or (hi_open and d == hi)):
        _fail()
    return d


def load_runner_config(raw: bytes) -> RunnerConfig:
    if type(raw) is not bytes:
        _fail()
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        _fail()
    if type(data) is not dict or set(data) != _KEYS or type(data["schema_version"]) is not int \
            or data["schema_version"] != 1:
        _fail()
    syms = data["symbols"]
    if (type(syms) is not list or not 1 <= len(syms) <= 40 or len(set(syms)) != len(syms)
            or any(type(s) is not str or not _SYMBOL_RE.match(s) for s in syms)):
        _fail()
    slip = data["slippage_bps"]
    if type(slip) is not int or not 0 <= slip <= 500:
        _fail()
    risk = data["risk_policy"]
    if type(risk) is not dict or set(risk) != _RISK_KEYS:
        _fail()
    policy = RiskPolicy(
        max_loss_fraction=_dec(risk["max_loss_fraction"], Decimal("0"), Decimal("1"), lo_open=True),
        max_open_risk_fraction=_dec(risk["max_open_risk_fraction"], Decimal("0"), Decimal("1"), lo_open=True),
        max_position_margin_fraction=_dec(risk["max_position_margin_fraction"], Decimal("0"), Decimal("1"), lo_open=True),
        max_total_margin_fraction=_dec(risk["max_total_margin_fraction"], Decimal("0"), Decimal("1"), lo_open=True),
        minimum_equity=_dec(risk["minimum_equity"], Decimal("450"), Decimal("1000000")),
        estimated_roundtrip_cost_bp=_dec(risk["estimated_roundtrip_cost_bp"], Decimal("0"), Decimal("1000")),
        liquidation_buffer_fraction=_dec(risk["liquidation_buffer_fraction"], Decimal("0"), Decimal("1"), lo_open=True))
    if not (policy.max_loss_fraction <= policy.max_open_risk_fraction
            and policy.max_position_margin_fraction <= policy.max_total_margin_fraction):
        _fail()
    model, thinking = data["model"], data["thinking"]
    if type(model) is not str or not _MODEL_RE.match(model) or thinking not in ("disabled", "omit"):
        _fail()
    equity = _dec(data["initial_equity"], Decimal("450"), Decimal("1000000"), lo_open=True)
    if equity <= policy.minimum_equity:
        _fail()
    cap = _dec(data["daily_cap_usd"], Decimal("0"), Decimal("1000"), lo_open=True)
    if cap * 1_000_000 != (cap * 1_000_000).to_integral_value():
        _fail()
    return RunnerConfig(
        symbols=tuple(syms), initial_equity=equity, slippage_bps=slip,
        fee_bps=_dec(data["fee_bps"], Decimal("0"), Decimal("100")),
        maintenance_fraction=_dec(data["maintenance_fraction"], Decimal("0"), Decimal("1"), hi_open=True),
        risk_policy=policy, model=model, thinking=thinking,
        input_usd_per_million=_dec(data["input_usd_per_million_tokens"], Decimal("0"), Decimal("1000")),
        output_usd_per_million=_dec(data["output_usd_per_million_tokens"], Decimal("0"), Decimal("1000")),
        daily_cap_usd=cap)


def default_config_path() -> Path:
    return Path(__file__).with_name("runner_config.json")


def load_default_config() -> RunnerConfig:
    return load_runner_config(default_config_path().read_bytes())
