"""Brain unico PAPER (24/11/2026): la sezione ``brain_unico`` di ``runner_config.json`` (schema 3) e le sue funzioni pure.

Decisione del proprietario (24/11): un solo Brain PAPER da 2.000 USDT che usa bene il capitale, incassa e protegge.
Questo modulo NON apre, non chiude e non legge file: definisce la politica e i calcoli deterministici che il runner,
il servizio delle uscite e la dashboard condividono (stesso codice = stessi numeri ovunque).

* ``leverage_selection: "fit"``: la leva non e' quella proposta dall'AI ma la PIU' BASSA, fra minima e massima del
  profilo, con cui la posizione raggiunge la dimensione massima consentita da rischio e margine; il controllo della
  liquidazione del RiskManager resta invariato (vedi ``brain_f2/engine.py``). Lo stop non viene mai stretto.
* ``partial_take_profit``: l'apertura si divide in due quote che sono posizioni PAPER normali con lo stesso stop:
  ``tp1`` (``fraction``, take-profit a ``at_r`` R) e ``runner`` (il resto, take-profit e protezione della politica
  d'uscita della run). Ogni chiusura resta un ``paper_close`` ordinario: nessun nuovo evento contabile.
* ``profit_tiers``: ATTIVO / SELETTIVO / PROTEZIONE dal risultato NETTO REALIZZATO della sessione (commissioni e costo
  AI della sessione dedotti), applicati dal Guardian alle sole NUOVE aperture (tetto di rischio e confidenza minima).
* ``piggy_bank``: a ogni mezzanotte (``tz``) il profitto realizzato sopra il capitale di riferimento passa nel
  salvadanaio; il salvadanaio non torna mai nel capitale operativo. Ricostruito dal journal (nessun file di stato):
  posizioni aperte e P&L non realizzato non si accantonano; una perdita resta nel capitale operativo, senza reintegri.
* ``position_review``: l'AI rivede le posizioni aperte (HOLD, CLOSE, PARTIAL_CLOSE, MODIFY_STOP); un validatore
  deterministico decide cosa si esegue (``runner/position_review.py``).
* ``guidance``: il prompt dell'analista riceve la filosofia operativa e lo stato del portafoglio.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Iterable, Mapping, Optional
from zoneinfo import ZoneInfo

LEG_TP1, LEG_RUNNER = "tp1", "runner"
# Motivi delle due AI: elenco CHIUSO (nel journal entrano solo questi codici, mai testo libero dei modelli).
REASON_CODES = frozenset({
    "trend_up", "trend_down", "trend_weakening", "trend_change", "breakout", "breakdown", "pullback", "range",
    "momentum_strong", "momentum_fading", "volume_confirms", "volume_weak", "volatility_high", "volatility_low",
    "near_support", "near_resistance", "overextended", "conflicting_signals", "reversal_risk", "profit_at_risk",
    "costs_high", "funding_adverse", "better_opportunity", "thesis_intact", "thesis_invalidated", "liquidity_thin",
    "risk_concentration", "setup_strong", "setup_weak"})


def parse_reasons(raw) -> tuple:
    """Codici validi (al massimo 6, senza doppioni); qualunque altra cosa -> ``ValueError``."""
    if raw is None:
        return ()
    if type(raw) is not list or len(raw) > 6 or any(type(x) is not str or x not in REASON_CODES for x in raw):
        raise ValueError("invalid_reasons")
    return tuple(dict.fromkeys(raw))


class UnicoConfigError(ValueError):
    """Sezione ``brain_unico`` non valida (messaggio fisso, nessun valore)."""


def _dec(raw: object, lo: Decimal, hi: Decimal, *, lo_open: bool = True) -> Decimal:
    if type(raw) is not str or not raw or len(raw) > 24 or not raw.isascii():
        raise UnicoConfigError("invalid_brain_unico")
    try:
        d = Decimal(raw)
    except InvalidOperation:
        raise UnicoConfigError("invalid_brain_unico") from None
    if not d.is_finite() or d < lo or d > hi or (lo_open and d == lo):
        raise UnicoConfigError("invalid_brain_unico")
    return d


@dataclass(frozen=True)
class PartialTakeProfit:
    fraction: Decimal          # quota della posizione che esce al primo take-profit (0-1, esclusi)
    at_r: Decimal              # primo take-profit, in R (multipli della distanza dallo stop)


@dataclass(frozen=True)
class ProfitTiers:
    selective_usd: Decimal             # netto realizzato di sessione da cui il Brain diventa SELETTIVO
    protect_usd: Decimal               # ... e da cui passa in PROTEZIONE
    selective_risk_r: Decimal          # tetto di rischio della nuova apertura, in R ordinari
    protect_risk_r: Decimal
    selective_min_confidence: Decimal  # confidenza minima dell'AI per aprire
    protect_min_confidence: Decimal


@dataclass(frozen=True)
class PiggyPolicy:
    reference_equity: Decimal          # capitale operativo di riferimento (2.000)
    tz: str                            # fuso della mezzanotte contabile
    hour: int                          # ora locale dell'accantonamento (0 = mezzanotte)


@dataclass(frozen=True)
class ClaudeConsultPolicy:
    """Claude consulente (24/11): chiamato solo quando scatta un criterio (``runner/consult.py``)."""
    model: str
    effort: str                        # sforzo di ragionamento (low | medium | high)
    max_tokens: int
    timeout_s: int
    daily_cap_usd: Decimal             # tetto PROPRIO di Claude, separato da DeepSeek
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    max_per_cycle: int                 # consulti al massimo per giro (aperture + posizioni)
    cooldown_minutes: int              # stessa posizione: non piu' spesso, salvo un'azione proposta da DeepSeek

    @property
    def daily_cap_units(self) -> int:
        return int(self.daily_cap_usd * 1_000_000)


@dataclass(frozen=True)
class UnicoPolicy:
    leverage_fit: bool
    partial: Optional[PartialTakeProfit]
    tiers: Optional[ProfitTiers]
    piggy: Optional[PiggyPolicy]
    position_review: bool
    guidance: bool
    claude: Optional[ClaudeConsultPolicy] = None


_TOP = {"leverage_selection", "partial_take_profit", "profit_tiers", "piggy_bank", "position_review", "guidance",
        "claude_consult"}
_CLAUDE = {"model", "effort", "max_tokens", "timeout_s", "daily_cap_usd", "input_usd_per_million_tokens",
           "output_usd_per_million_tokens", "max_per_cycle", "cooldown_minutes"}


def _claude_from(c) -> ClaudeConsultPolicy:
    import re
    if not isinstance(c, Mapping) or set(c) != _CLAUDE:
        raise UnicoConfigError("invalid_brain_unico")
    if (type(c["model"]) is not str or not re.fullmatch(r"claude-[a-z0-9-]{1,40}", c["model"])
            or c["effort"] not in ("low", "medium", "high")
            or any(type(c[k]) is not int for k in ("max_tokens", "timeout_s", "max_per_cycle", "cooldown_minutes"))
            or not 256 <= c["max_tokens"] <= 16_000 or not 10 <= c["timeout_s"] <= 300
            or not 1 <= c["max_per_cycle"] <= 20 or not 0 <= c["cooldown_minutes"] <= 1440):
        raise UnicoConfigError("invalid_brain_unico")
    cap = _dec(c["daily_cap_usd"], Decimal("0"), Decimal("100"))
    if cap * 1_000_000 != (cap * 1_000_000).to_integral_value():
        raise UnicoConfigError("invalid_brain_unico")
    return ClaudeConsultPolicy(c["model"], c["effort"], c["max_tokens"], c["timeout_s"], cap,
                               _dec(c["input_usd_per_million_tokens"], Decimal("0"), Decimal("1000")),
                               _dec(c["output_usd_per_million_tokens"], Decimal("0"), Decimal("1000")),
                               c["max_per_cycle"], c["cooldown_minutes"])
_TIERS = {"selective_usd", "protect_usd", "selective_risk_r", "protect_risk_r", "selective_min_confidence",
          "protect_min_confidence"}


def unico_policy_from_config(raw: object) -> UnicoPolicy:
    """Dal blocco ``brain_unico`` (chiavi esatte; sezioni facoltative = ``null``)."""
    if not isinstance(raw, Mapping) or set(raw) != _TOP:
        raise UnicoConfigError("invalid_brain_unico")
    if raw["leverage_selection"] not in ("fit", "proposed"):
        raise UnicoConfigError("invalid_brain_unico")
    if type(raw["position_review"]) is not bool or type(raw["guidance"]) is not bool:
        raise UnicoConfigError("invalid_brain_unico")
    partial = None
    if raw["partial_take_profit"] is not None:
        p = raw["partial_take_profit"]
        if not isinstance(p, Mapping) or set(p) != {"fraction", "at_r"}:
            raise UnicoConfigError("invalid_brain_unico")
        frac = _dec(p["fraction"], Decimal("0"), Decimal("1"))
        if frac >= 1:
            raise UnicoConfigError("invalid_brain_unico")
        partial = PartialTakeProfit(frac, _dec(p["at_r"], Decimal("0"), Decimal("20")))
    tiers = None
    if raw["profit_tiers"] is not None:
        t = raw["profit_tiers"]
        if not isinstance(t, Mapping) or set(t) != _TIERS:
            raise UnicoConfigError("invalid_brain_unico")
        tiers = ProfitTiers(
            selective_usd=_dec(t["selective_usd"], Decimal("0"), Decimal("1000000")),
            protect_usd=_dec(t["protect_usd"], Decimal("0"), Decimal("1000000")),
            selective_risk_r=_dec(t["selective_risk_r"], Decimal("0"), Decimal("1")),
            protect_risk_r=_dec(t["protect_risk_r"], Decimal("0"), Decimal("1")),
            selective_min_confidence=_dec(t["selective_min_confidence"], Decimal("0"), Decimal("1")),
            protect_min_confidence=_dec(t["protect_min_confidence"], Decimal("0"), Decimal("1")))
        if not (tiers.selective_usd < tiers.protect_usd and tiers.protect_risk_r <= tiers.selective_risk_r
                and tiers.selective_min_confidence <= tiers.protect_min_confidence):
            raise UnicoConfigError("invalid_brain_unico")
    piggy = None
    if raw["piggy_bank"] is not None:
        b = raw["piggy_bank"]
        if not isinstance(b, Mapping) or set(b) != {"reference_equity", "tz", "hour"}:
            raise UnicoConfigError("invalid_brain_unico")
        if type(b["tz"]) is not str or type(b["hour"]) is not int or not 0 <= b["hour"] <= 23:
            raise UnicoConfigError("invalid_brain_unico")
        try:
            ZoneInfo(b["tz"])
        except Exception:
            raise UnicoConfigError("invalid_brain_unico") from None
        piggy = PiggyPolicy(_dec(b["reference_equity"], Decimal("450"), Decimal("1000000")), b["tz"], b["hour"])
    claude = None if raw["claude_consult"] is None else _claude_from(raw["claude_consult"])
    return UnicoPolicy(raw["leverage_selection"] == "fit", partial, tiers, piggy, raw["position_review"],
                       raw["guidance"], claude)


# ----------------------------------------------------------------------------- quote dell'apertura
def split_legs(quantity: Decimal, *, step: Decimal, price: Decimal, minimum_notional: Decimal,
               partial: Optional[PartialTakeProfit]) -> tuple[tuple[str, Decimal, Optional[Decimal]], ...]:
    """Quote ``(nome, quantita', take_profit_r)`` della posizione approvata; somma = ``quantity``.

    Una sola quota (``("", quantity, None)``: posizione unica con la politica della run) se la presa parziale e'
    spenta o se una delle due quote sarebbe sotto il passo o il nozionale minimo della borsa."""
    single = (("", quantity, None),)
    if partial is None:
        return single
    for x in (quantity, step, price):
        if type(x) is not Decimal or not x.is_finite() or x <= 0:
            raise ValueError("invalid_leg_input")
    if type(minimum_notional) is not Decimal or not minimum_notional.is_finite() or minimum_notional < 0:
        raise ValueError("invalid_leg_input")
    first = (quantity * partial.fraction / step).to_integral_value(rounding=ROUND_DOWN) * step
    rest = quantity - first
    if first <= 0 or rest <= 0 or first * price < minimum_notional or rest * price < minimum_notional:
        return single
    return ((LEG_TP1, first, partial.at_r), (LEG_RUNNER, rest, None))


# ----------------------------------------------------------------------------- salvadanaio
@dataclass(frozen=True)
class PiggyState:
    total: Decimal                                  # accantonato finora
    sweeps: tuple[tuple[int, Decimal], ...]         # (istante della mezzanotte, importo) solo quelli > 0
    operating_equity: Decimal                       # capitale + realizzato - salvadanaio (cio' che il Brain usa)
    next_sweep_ms: int                              # prossima mezzanotte contabile


def _boundaries(start_ms: int, now_ms: int, policy: PiggyPolicy) -> list[int]:
    tz = ZoneInfo(policy.tz)
    local = datetime.fromtimestamp(start_ms / 1000, tz)
    day = local.date()
    out: list[int] = []
    while True:
        at = datetime.combine(day, time(policy.hour), tzinfo=tz)
        ms = int(at.astimezone(timezone.utc).timestamp() * 1000)
        if ms > now_ms:
            out.append(ms)                          # l'ultimo e' la prossima mezzanotte (non ancora avvenuta)
            return out
        if ms > start_ms:
            out.append(ms)
        day += timedelta(days=1)


def piggy_bank(closed: Iterable[tuple[int, Decimal]], *, initial_equity: Decimal, start_ms: int, now_ms: int,
               policy: PiggyPolicy) -> PiggyState:
    """Ricostruisce il salvadanaio dalle chiusure ``(istante, P&L netto di commissioni)``.

    A ogni mezzanotte ``M`` (dopo ``start_ms``, fino a ``now_ms``): capitale operativo = capitale iniziale + realizzato
    fino a ``M`` - salvadanaio; se supera il riferimento, l'eccedenza passa nel salvadanaio. Deterministico, senza
    stato: un riavvio o la dashboard ottengono gli stessi numeri."""
    for x in (initial_equity, policy.reference_equity):
        if type(x) is not Decimal or not x.is_finite() or x <= 0:
            raise ValueError("invalid_piggy_input")
    if type(start_ms) is not int or type(now_ms) is not int or start_ms <= 0 or now_ms < start_ms:
        raise ValueError("invalid_piggy_input")
    events = sorted((int(t), Decimal(v)) for t, v in closed)
    marks = _boundaries(start_ms, now_ms, policy)
    total, sweeps, realized, i = Decimal("0"), [], Decimal("0"), 0
    for m in marks[:-1]:
        while i < len(events) and events[i][0] <= m:
            realized += events[i][1]
            i += 1
        excess = initial_equity + realized - total - policy.reference_equity
        if excess > 0:
            total += excess
            sweeps.append((m, excess))
    realized_now = sum((v for t, v in events if t <= now_ms), Decimal("0"))
    return PiggyState(total, tuple(sweeps), initial_equity + realized_now - total, marks[-1])


def piggy_from_closed(closed, *, initial_equity: Decimal, now_ms: int, policy: PiggyPolicy) -> PiggyState:
    """Come ``piggy_bank`` ma dalle ``ClosedTrade`` del riepilogo. L'inizio non serve: il riferimento coincide con il
    capitale iniziale (lo impone la configurazione), quindi prima della prima chiusura non c'e' nulla da accantonare."""
    pairs = [(c.closed_at_ms, c.realized_pnl) for c in closed]
    start = min([t for t, _ in pairs if t <= now_ms] + [now_ms]) - 1
    return piggy_bank(pairs, initial_equity=initial_equity, start_ms=max(start, 1), now_ms=now_ms, policy=policy)
