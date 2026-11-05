"""Configurazione del runner del Brain PAPER: caricatore rigido di ``runner_config.json``.

**Tutti i valori nel file sono PROPOSTE di Claude, da confermare dall'utente** (regola 3 di CLAUDE.md: limiti di
rischio, soglie e costi si cambiano solo per decisione dell'utente). Si cambiano solo in quel file.
Il caricatore accetta solo i byte esatti: chiavi duplicate, costanti non finite, chiavi mancanti o in piu', tipi
sbagliati, valori fuori intervallo -> ``ValueError("invalid_config")`` (nessun dettaglio: niente valori nei messaggi).

* ``risk_policy``: i limiti del mandato di rischio (vedi ``risk.RiskPolicy``); ``minimum_equity`` >= 450 lo impone il motore.
* ``thinking``: ``"enabled"`` (RAGIONAMENTO ESTESO, scelta dell'utente 5/11) invia ``{"thinking": {"type": "enabled"}}`` e,
  se ``reasoning_effort`` non e' ``"omit"``, ``"reasoning_effort": "low"|"high"|"max"`` (documentazione DeepSeek, parametri
  non ancora provati dal vivo); ``"disabled"`` invia ``{"thinking": {"type": "disabled"}}``; ``"omit"`` non invia nulla (il
  modello ragiona di default). ``max_tokens`` e' il tetto di token generati PER CHIAMATA e con il ragionamento **include i
  token di ragionamento** (se non basta la risposta e' troncata, ``finish_reason`` ``length``, nessuna decisione).
* ``cycle_minutes``: ogni quanti minuti il Brain decide (multiplo di 15; 60 = ogni ora, scelta dell'utente 5/11). Le uscite
  si controllano comunque ogni minuto.
* ``daily_loss_warn_fraction`` / ``daily_loss_halt_fraction``: perdita giornaliera (giorno UTC, sul capitale di inizio
  giornata) a cui il Brain avvisa e a cui smette di aprire (decisione dell'utente 5/11: 35 % e 50 %; vedi ``daily_loss.py``).
  Fuori dal mandato di rischio (non cambiano il suo ``policy_hash``).
* ``daily_cap_usd``: tetto di spesa giornaliero (giorno UTC) per il modello; i prezzi per milione di token servono solo
  a stimare la spesa (sempre al prezzo del token NON in cache: stima prudente).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from backend.v3.risk import RiskPolicy

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}USDT$")
_MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_KEYS = {"schema_version", "symbols", "initial_equity", "slippage_bps", "fee_bps", "maintenance_fraction",
         "risk_policy", "model", "thinking", "reasoning_effort", "max_tokens", "cycle_minutes",
         "input_usd_per_million_tokens", "output_usd_per_million_tokens", "daily_cap_usd",
         "daily_loss_warn_fraction", "daily_loss_halt_fraction"}
_THINKING = ("disabled", "omit", "enabled")
_EFFORTS = ("omit", "low", "high", "max")
MIN_REASONING_TOKENS = 1024          # con il ragionamento un tetto piu' basso troncherebbe sempre la risposta
MAX_OUTPUT_TOKENS = 65_536
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
    reasoning_effort: str
    max_tokens: int
    cycle_minutes: int
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    daily_cap_usd: Decimal
    daily_loss_warn: Decimal = Decimal("0.35")
    daily_loss_halt: Decimal = Decimal("0.50")

    @property
    def cycle_ms(self) -> int:
        return self.cycle_minutes * 60_000

    @property
    def model_extra_payload(self) -> Optional[dict]:
        """Campi di primo livello aggiunti alla richiesta del modello (``None`` = nessuno)."""
        if self.thinking == "disabled":
            return {"thinking": {"type": "disabled"}}
        if self.thinking == "enabled":
            extra: dict = {"thinking": {"type": "enabled"}}
            if self.reasoning_effort != "omit":
                extra["reasoning_effort"] = self.reasoning_effort
            return extra
        return None

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
    model, thinking, effort = data["model"], data["thinking"], data["reasoning_effort"]
    max_tokens, cycle = data["max_tokens"], data["cycle_minutes"]
    if (type(model) is not str or not _MODEL_RE.match(model) or type(thinking) is not str or thinking not in _THINKING
            or type(effort) is not str or effort not in _EFFORTS or (thinking != "enabled" and effort != "omit")):
        _fail()
    if (type(max_tokens) is not int or not 1 <= max_tokens <= MAX_OUTPUT_TOKENS
            or (thinking == "enabled" and max_tokens < MIN_REASONING_TOKENS)):
        _fail()
    if type(cycle) is not int or not 15 <= cycle <= 1440 or cycle % 15:
        _fail()
    equity = _dec(data["initial_equity"], Decimal("450"), Decimal("1000000"), lo_open=True)
    if equity <= policy.minimum_equity:
        _fail()
    cap = _dec(data["daily_cap_usd"], Decimal("0"), Decimal("1000"), lo_open=True)
    if cap * 1_000_000 != (cap * 1_000_000).to_integral_value():
        _fail()
    warn = _dec(data["daily_loss_warn_fraction"], Decimal("0"), Decimal("1"), lo_open=True, hi_open=True)
    halt = _dec(data["daily_loss_halt_fraction"], Decimal("0"), Decimal("1"), lo_open=True)
    if not warn < halt:
        _fail()
    return RunnerConfig(
        symbols=tuple(syms), initial_equity=equity, slippage_bps=slip,
        fee_bps=_dec(data["fee_bps"], Decimal("0"), Decimal("100")),
        maintenance_fraction=_dec(data["maintenance_fraction"], Decimal("0"), Decimal("1"), hi_open=True),
        risk_policy=policy, model=model, thinking=thinking, reasoning_effort=effort,
        max_tokens=max_tokens, cycle_minutes=cycle,
        input_usd_per_million=_dec(data["input_usd_per_million_tokens"], Decimal("0"), Decimal("1000")),
        output_usd_per_million=_dec(data["output_usd_per_million_tokens"], Decimal("0"), Decimal("1000")),
        daily_cap_usd=cap, daily_loss_warn=warn, daily_loss_halt=halt)


def default_config_path() -> Path:
    return Path(__file__).with_name("runner_config.json")


def load_default_config() -> RunnerConfig:
    return load_runner_config(default_config_path().read_bytes())
