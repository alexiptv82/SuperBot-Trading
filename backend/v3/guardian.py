"""Smart Profit Guardian: budget di rischio per le NUOVE aperture, dalla contabilita' della sola run (deterministico).

Riferimento: ``docs/v3/BRAIN-UNICO-SMART-PROFIT-GUARDIAN-PROPOSTA-20261119.md`` (politica D, floor mobile; stati
derivati dal budget; sessione 08:00 Europe/Rome; nessuna eccezione per l'AI). Codice comune, stato per run: tutto si
ricostruisce dal journal della run e dalle chiusure da 1 minuto, nessun file di stato, nessuna memoria nascosta.

Equity mark-to-market al minuto ``e`` (fine del minuto, prezzo = chiusura del minuto che termina in ``e``):
    capitale iniziale + PnL realizzato (chiusure fino a ``e``, commissioni incluse)
    + somma sulle posizioni aperte a ``e`` di  lato * (prezzo - ingresso) * qta - (ingresso + prezzo) * qta * fee
(le commissioni di andata e ritorno di una posizione aperta sono gia' dedotte: e' il valore se la si chiudesse ora).

Sessione: dalle ``session_hour`` (ora locale ``session_tz``) alla stessa ora del giorno dopo; con l'ora legale dura 23 o
25 ore. La base della sessione e' l'equity MTM all'inizio: una posizione che attraversa il cambio entra al suo valore
di mercato di quel minuto, senza doppio conteggio. Il cambio di sessione riabilita solo la valutazione delle NUOVE
aperture: non chiude nulla e non azzera i limiti globali.

Floor (politica D): si arma quando il picco MTM della sessione supera ``activation_fraction`` dell'equity d'inizio;
floor = inizio + ``keep_fraction`` * (picco - inizio), solo crescente. Budget = equity - floor - rischio aperto a stop.

Stati (dai numeri, mai da un'etichetta dell'AI):
* NORMAL     floor non armato: rischio ordinario (nessun tetto in piu').
* SELECTIVE  floor armato, budget >= ``protected_below_r`` R: tetto = min(R, ``spend_fraction`` * budget).
* PROTECTED  budget fra ``locked_below_r`` R e ``protected_below_r`` R: stesso tetto, e in piu' l'apertura deve avere
             confidenza >= ``protected_min_confidence`` e non essere un reingresso della stessa tesi.
* LOCKED     budget < ``locked_below_r`` R, oppure (bloccato fino al cambio di sessione) l'equity e' scesa sotto il
             floor o la perdita di sessione ha raggiunto ``session_loss_fraction``, oppure drawdown globale >=
             ``global_drawdown_lock``, oppure prezzi mancanti. Nessuna nuova apertura, nessuna chiamata all'AI.
R = rischio ordinario per trade = equity * ``max_loss_fraction`` della politica di rischio (dimezzato con drawdown
globale >= ``global_drawdown_half``). Drawdown globale = dal massimo dell'equity contabilizzata (solo realizzato).

Il floor limita il rischio delle NUOVE aperture. NON garantisce il profitto finale ne' protegge le posizioni gia'
aperte (gap, slippage e liquidazione possono superare le stime): quelle restano affidate al servizio delle uscite.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, Mapping, Optional
from zoneinfo import ZoneInfo

from backend.v3.unico import ProfitTiers

MINUTE_MS = 60_000
STATES = ("NORMAL", "SELECTIVE", "PROTECTED", "LOCKED")
_BP = Decimal(10000)

CloseAt = Callable[[str, int], Optional[Decimal]]      # (simbolo, apertura del minuto in ms) -> chiusura o None


@dataclass(frozen=True)
class GuardianPolicy:
    activation_fraction: Decimal = Decimal("0.08")      # floor armato dal +8 % di sessione (proposta 19/11)
    keep_fraction: Decimal = Decimal("0.75")            # protegge il 75 % del picco (giveback 25 %)
    session_loss_fraction: Decimal = Decimal("0.08")    # -8 % dall'inizio sessione: LOCKED fino al cambio
    spend_fraction: Decimal = Decimal("0.5")            # una nuova apertura usa al massimo meta' del budget
    protected_below_r: Decimal = Decimal("1")
    locked_below_r: Decimal = Decimal("0.25")
    protected_min_confidence: Decimal = Decimal("0.7")
    global_drawdown_half: Decimal = Decimal("0.10")
    global_drawdown_lock: Decimal = Decimal("0.20")
    session_hour: int = 8
    session_tz: str = "Europe/Rome"
    # Brain unico (24/11): ATTIVO / SELETTIVO / PROTEZIONE dal netto realizzato di sessione. None = spento.
    tiers: Optional["ProfitTiers"] = None

    def __post_init__(self):
        fr = (self.activation_fraction, self.keep_fraction, self.session_loss_fraction, self.spend_fraction,
              self.protected_min_confidence, self.global_drawdown_half, self.global_drawdown_lock)
        if any(type(x) is not Decimal or not x.is_finite() or not 0 < x <= 1 for x in fr):
            raise ValueError("invalid_guardian_policy")
        if (any(type(x) is not Decimal or not x.is_finite() or x <= 0
                for x in (self.locked_below_r, self.protected_below_r))
                or not self.locked_below_r < self.protected_below_r <= 10
                or not self.keep_fraction < 1 or not self.global_drawdown_half < self.global_drawdown_lock
                or type(self.session_hour) is not int or not 0 <= self.session_hour <= 23):
            raise ValueError("invalid_guardian_policy")
        try:
            ZoneInfo(self.session_tz)
        except Exception:
            raise ValueError("invalid_guardian_policy") from None


@dataclass(frozen=True)
class GuardianState:
    state: str
    reasons: tuple[str, ...]
    session_start_ms: int
    session_start_equity: Optional[Decimal]
    equity: Optional[Decimal]                 # MTM all'ultimo minuto chiuso
    realized_session: Optional[Decimal]
    unrealized: Optional[Decimal]
    peak_equity: Optional[Decimal]
    giveback: Optional[Decimal]               # picco - equity attuale (>= 0)
    armed: bool
    floor: Optional[Decimal]
    open_risk: Optional[Decimal]              # perdita stimata a stop delle posizioni aperte, costi inclusi
    budget: Optional[Decimal]                 # equity - floor - rischio aperto (solo se armato)
    r_unit: Optional[Decimal]                 # R ordinario per trade
    risk_cap: Optional[Decimal]               # tetto per la NUOVA apertura (None = solo i limiti ordinari)
    min_confidence: Optional[Decimal]         # PROTECTED: confidenza minima
    allow_reentry: bool                       # PROTECTED: niente reingressi della stessa tesi
    global_drawdown: Optional[Decimal]
    ai_cost_session: Optional[Decimal] = None
    as_of_ms: int = 0

    @property
    def allows_new_opens(self) -> bool:
        return self.state != "LOCKED"

    def to_payload(self) -> dict:
        """Forma per il journal (``guardian_state``): solo numeri in stringa, codici fissi."""
        out = {"state": self.state, "reasons": list(self.reasons), "session_start_ms": self.session_start_ms,
               "armed": self.armed, "allow_reentry": self.allow_reentry, "as_of_ms": self.as_of_ms}
        for k in ("session_start_equity", "equity", "realized_session", "unrealized", "peak_equity", "giveback",
                  "floor", "open_risk", "budget", "r_unit", "risk_cap", "min_confidence", "global_drawdown",
                  "ai_cost_session"):
            v = getattr(self, k)
            out[k] = None if v is None else str(v)
        return out


def session_start_ms(now_ms: int, policy: GuardianPolicy) -> int:
    """Inizio della sessione che contiene ``now_ms`` (ultima ``session_hour`` locale <= ora)."""
    tz = ZoneInfo(policy.session_tz)
    local = datetime.fromtimestamp(now_ms / 1000, tz)
    day = local.date()
    start = datetime.combine(day, time(policy.session_hour), tzinfo=tz)
    if start > local:
        start = datetime.combine(day - timedelta(days=1), time(policy.session_hour), tzinfo=tz)
    return int(start.astimezone(timezone.utc).timestamp() * 1000)


@dataclass
class _Pos:
    symbol: str
    side: int
    fill: Decimal
    qty: Decimal
    stop: Decimal
    opened_ms: int
    closed_ms: Optional[int] = None
    pnl: Decimal = field(default_factory=lambda: Decimal("0"))


def _dec(v) -> Decimal:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("guardian_bad_journal") from None
    if not d.is_finite():
        raise ValueError("guardian_bad_journal")
    return d


def positions_from_events(events) -> tuple[list[_Pos], list[tuple[int, Decimal]]]:
    """Posizioni (aperture con eventuale chiusura) e chiusure senza apertura nota (solo PnL), in ordine di journal."""
    opens: dict[str, _Pos] = {}
    orphan: list[tuple[int, Decimal]] = []
    from backend.v3.executor.paper_scale import expand_scaled
    for ev in expand_scaled(events):          # ingressi aggiuntivi e chiusure parziali come segmenti equivalenti
        p = ev.payload if isinstance(ev.payload, Mapping) else {}
        if ev.kind == "paper_open":
            pid = p.get("position_id")
            opens[pid] = _Pos(str(p.get("symbol")), int(p.get("side")), _dec(p.get("fill_price")),
                              _dec(p.get("quantity")), _dec(p.get("stop_price")), int(ev.occurred_at_ms))
        elif ev.kind == "paper_close":
            pid = p.get("position_id")
            if pid in opens and opens[pid].closed_ms is None:
                opens[pid].closed_ms, opens[pid].pnl = int(ev.occurred_at_ms), _dec(p.get("realized_pnl"))
            else:
                orphan.append((int(ev.occurred_at_ms), _dec(p.get("realized_pnl"))))
    return list(opens.values()), orphan


def evaluate_guardian(*, events, initial_equity: Decimal, close_at: CloseAt, now_ms: int, policy: GuardianPolicy,
                      max_loss_fraction: Decimal, fee_bps: Decimal, roundtrip_cost_bp: Decimal,
                      ai_cost_session: Optional[Decimal] = None) -> GuardianState:
    """Stato del Guardian all'ultimo minuto chiuso prima di ``now_ms``. Pura: journal e prezzi sono passati da fuori."""
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError("invalid_now")
    for x in (initial_equity, max_loss_fraction, fee_bps, roundtrip_cost_bp):
        if type(x) is not Decimal or not x.is_finite() or x < 0:
            raise ValueError("invalid_guardian_input")
    s = session_start_ms(now_ms, policy)
    end = now_ms // MINUTE_MS * MINUTE_MS
    positions, orphan = positions_from_events(events)
    fee = fee_bps / _BP

    def settled_at(e: int) -> Decimal:
        return (initial_equity + sum((p.pnl for p in positions if p.closed_ms is not None and p.closed_ms <= e),
                                     Decimal("0")) + sum((v for t, v in orphan if t <= e), Decimal("0")))

    def mtm(e: int) -> tuple[Optional[Decimal], Decimal]:
        """(equity MTM o None se manca un prezzo, rischio aperto a stop) alla fine del minuto ``e``."""
        eq, risk = settled_at(e), Decimal("0")
        for p in positions:
            if p.opened_ms <= e and (p.closed_ms is None or p.closed_ms > e):
                px = close_at(p.symbol, e - MINUTE_MS)
                if type(px) is not Decimal or not px.is_finite() or px <= 0:
                    return None, risk
                eq += p.side * (px - p.fill) * p.qty - (p.fill + px) * p.qty * fee
                risk += (abs(p.fill - p.stop) + p.fill * roundtrip_cost_bp / _BP) * p.qty
        return eq, risk

    # drawdown globale dal massimo dell'equity contabilizzata (solo chiusure: deterministico e senza prezzi)
    hwm, run = initial_equity, initial_equity
    for t, v in sorted([(p.closed_ms, p.pnl) for p in positions if p.closed_ms is not None] + orphan):
        if t > end:
            break
        run += v
        hwm = max(hwm, run)

    start_eq, _ = mtm(s)
    base = dict(session_start_ms=s, as_of_ms=end, ai_cost_session=ai_cost_session)
    if start_eq is None:
        return _locked(("data_fault",), base)
    peak, armed, floor = start_eq, False, None
    latched: list[str] = []
    eq, risk = start_eq, Decimal("0")
    e = s
    while e < end:
        e += MINUTE_MS
        eq, risk = mtm(e)
        if eq is None:
            return _locked(("data_fault",), base, session_start_equity=start_eq)
        if eq - start_eq <= -policy.session_loss_fraction * start_eq and "session_loss" not in latched:
            latched.append("session_loss")
        if eq > peak:
            peak = eq
        if not armed and peak - start_eq >= policy.activation_fraction * start_eq:
            armed = True
        if armed:
            floor = start_eq + policy.keep_fraction * (peak - start_eq)      # solo crescente: il picco non scende
            if eq < floor and "below_floor" not in latched:
                latched.append("below_floor")
    if s >= end:                                                           # primo minuto della sessione
        eq, risk = start_eq, mtm(s)[1]
    settled_now = settled_at(end)
    gdd = max(Decimal("0"), (hwm - eq) / hwm) if hwm > 0 else Decimal("0")
    r_unit = eq * max_loss_fraction
    reasons = list(latched)
    if gdd >= policy.global_drawdown_lock:
        reasons.append("global_drawdown")
    elif gdd >= policy.global_drawdown_half:
        r_unit = r_unit / 2
    budget = (eq - floor - risk) if armed else None
    common = dict(base, session_start_equity=start_eq, equity=eq, realized_session=settled_now - settled_at(s),
                  unrealized=eq - settled_now, peak_equity=peak, giveback=peak - eq, armed=armed, floor=floor,
                  open_risk=risk, budget=budget, r_unit=r_unit, global_drawdown=gdd)
    if reasons:
        return _locked(tuple(reasons), base, **{k: v for k, v in common.items() if k not in base})
    if not armed:
        cap = r_unit if gdd >= policy.global_drawdown_half else None     # drawdown globale: R dimezzato
        return _apply_tiers(GuardianState(
            state="NORMAL", reasons=("drawdown_half",) if cap is not None else (), risk_cap=cap,
            min_confidence=None, allow_reentry=True, **common), policy)
    if budget < policy.locked_below_r * r_unit:
        return _locked(("floor_budget",), base, **{k: v for k, v in common.items() if k not in base})
    cap = min(r_unit, policy.spend_fraction * budget)
    if budget < policy.protected_below_r * r_unit:
        return _apply_tiers(GuardianState(
            state="PROTECTED", reasons=("floor_budget_low",), risk_cap=cap,
            min_confidence=policy.protected_min_confidence, allow_reentry=False, **common), policy)
    return _apply_tiers(GuardianState(state="SELECTIVE", reasons=("floor_armed",), risk_cap=cap, min_confidence=None,
                                      allow_reentry=True, **common), policy)


_RANK = {"NORMAL": 0, "SELECTIVE": 1, "PROTECTED": 2}


def session_net_realized(state: GuardianState) -> Optional[Decimal]:
    """Netto realizzato della sessione: chiusure (commissioni incluse) meno il costo AI della sessione."""
    if state.realized_session is None:
        return None
    return state.realized_session - (state.ai_cost_session or Decimal("0"))


def _apply_tiers(state: GuardianState, policy: GuardianPolicy) -> GuardianState:
    """Brain unico: SELETTIVO / PROTEZIONE dal netto realizzato di sessione. Vince sempre il vincolo piu' severo
    (stato, tetto di rischio, confidenza minima, reingressi); senza ``tiers`` lo stato e' invariato."""
    t = policy.tiers
    net = session_net_realized(state)
    if t is None or net is None or state.r_unit is None:
        return state
    if net >= t.protect_usd:
        tier, why, r_mult, conf, reentry = "PROTECTED", "profit_protect", t.protect_risk_r, t.protect_min_confidence, False
    elif net >= t.selective_usd:
        tier, why, r_mult, conf, reentry = "SELECTIVE", "profit_selective", t.selective_risk_r, \
            t.selective_min_confidence, True
    else:
        return state
    cap = state.r_unit * r_mult if state.risk_cap is None else min(state.risk_cap, state.r_unit * r_mult)
    conf = conf if state.min_confidence is None else max(conf, state.min_confidence)
    new_state = tier if _RANK[tier] > _RANK[state.state] else state.state
    return replace(state, state=new_state, reasons=state.reasons + (why,), risk_cap=cap, min_confidence=conf,
                   allow_reentry=state.allow_reentry and reentry)


def _locked(reasons: tuple, base: dict, **values) -> GuardianState:
    fields = dict(session_start_equity=None, equity=None, realized_session=None, unrealized=None, peak_equity=None,
                  giveback=None, armed=False, floor=None, open_risk=None, budget=None, r_unit=None,
                  global_drawdown=None)
    fields.update(values)
    return GuardianState(state="LOCKED", reasons=reasons, risk_cap=Decimal("0"), min_confidence=None,
                         allow_reentry=False, **base, **fields)


def guardian_policy_from_config(raw: Mapping) -> GuardianPolicy:
    """Dal blocco ``guardian`` di ``runner_config.json`` (schema 2): chiavi esatte, decimali in stringa."""
    keys = {"activation_fraction", "keep_fraction", "session_loss_fraction", "spend_fraction", "protected_below_r",
            "locked_below_r", "protected_min_confidence", "global_drawdown_half", "global_drawdown_lock",
            "session_hour", "session_tz"}
    if not isinstance(raw, Mapping) or set(raw) != keys:
        raise ValueError("invalid_guardian_policy")
    vals = {}
    for k in keys - {"session_hour", "session_tz"}:
        if type(raw[k]) is not str:
            raise ValueError("invalid_guardian_policy")
        try:
            vals[k] = Decimal(raw[k])
        except InvalidOperation:
            raise ValueError("invalid_guardian_policy") from None
    if type(raw["session_tz"]) is not str:
        raise ValueError("invalid_guardian_policy")
    return GuardianPolicy(session_hour=raw["session_hour"], session_tz=raw["session_tz"], **vals)
