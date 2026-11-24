"""DeepSeek principale + Claude consulente attivo (Brain unico PAPER, 24/11/2026).

DeepSeek analizza ogni giro i 27 mercati e le posizioni aperte e decide le situazioni ordinarie. Claude viene chiamato
SOLO quando scatta un criterio (``entry_triggers`` / ``position_triggers``): incertezza dichiarata, segnali
contrastanti, possibile cambio di trend, apertura rilevante per il rischio complessivo, profitto interessante, profitto
restituito, chiusura parziale/anticipata o stop modificato proposti da DeepSeek. Claude riceve gli stessi dati di
mercato e di portafoglio (non solo la risposta di DeepSeek) e risponde CONFIRM / CONTEST / ALTERNATIVE con un'azione.

Un ARBITRO deterministico (``arbitrate_entry`` / ``arbitrate_position``) confronta le due analisi con dati
quantitativi (R, profitto restituito, regime, confidenze) e puo' adottare la proposta di Claude. Nessuna delle due AI ha
l'ultima parola per definizione. Se le analisi sono inconciliabili e mancano numeri a favore, una NUOVA apertura non si
fa. Se Claude non risponde (chiave, rete, budget, timeout, formato), una NUOVA apertura che richiedeva il consulto non
viene approvata (NO_TRADE); un'azione di DeepSeek che riduce il rischio di una posizione (chiusura, parziale, stop piu'
stretto) si esegue comunque, registrando che il consulto mancava. Dopo l'arbitro restano il
RiskManager (aperture) e il validatore (azioni sulle posizioni). Stop, take-profit e protezioni del servizio delle uscite
non aspettano mai le AI. Nel journal entrano solo codici (azioni, motivi a elenco chiuso, confidenze), mai testo libero.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Callable, Mapping, Optional

from backend.v3.brain_f2.analyst import Analyst
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, OpenProposal
from backend.v3.brain_f3.providers import ProviderUnavailable, _bounded_decimal, _call, _json_object
from backend.v3.events import Event
from backend.v3.unico import REASON_CODES, parse_reasons

CONSULT_KIND = "ai_consultation"
VERDICTS = ("CONFIRM", "CONTEST", "ALTERNATIVE")
POSITION_ACTIONS = ("HOLD", "CLOSE", "PARTIAL_CLOSE", "MODIFY_STOP", "ADD")
# soglie dei criteri (codice, non configurazione: sono regole di quando CHIEDERE, non di rischio)
LOW_CONFIDENCE = 0.65
PORTFOLIO_RISK_TRIGGER = Decimal("0.08")        # rischio aperto dopo l'ingresso oltre l'8 % dell'equity
INTERESTING_R, INTERESTING_ROE = Decimal("1.5"), Decimal("20")
GIVEBACK_TRIGGER, GIVEBACK_MIN_MFE_R = Decimal("0.4"), Decimal("1")
_CONSERVATIVE = {"CLOSE": 3, "PARTIAL_CLOSE": 2, "MODIFY_STOP": 1, "HOLD": 0, "ADD": -1}

_CODES = ", ".join(sorted(REASON_CODES))
ENTRY_PROMPT = (
    'You are a senior trading consultant reviewing ONE proposed PAPER perpetual-futures entry for a 2000 USDT account. '
    'Form your own view from the market object (indicators on closed candles: distances in basis points of the last '
    'close, atr_bp, regime per timeframe) and the portfolio object; the deepseek object is the primary analyst\'s '
    'proposal, for comparison only. Return only JSON: {"verdict":"CONFIRM"} to accept it, {"verdict":"CONTEST"} to '
    'advise no trade, or {"verdict":"ALTERNATIVE","side":1 or -1,"stop_price":"..."} for a different side or stop; '
    'add "confidence" (0 to 1) and "reasons" (up to 6 codes from: ' + _CODES + '). The code sizes the position from '
    'the stop (about 4.3 percent of equity at risk), picks leverage 15x-50x, takes 35 percent at 2R and manages the '
    'rest toward 3.5R; round-trip costs about 16 bp. Contest when the edge after costs is unclear. No orders, no tools.')
POSITION_PROMPT = (
    'You are a senior trading consultant reviewing ONE open PAPER perpetual-futures position. Judge independently from '
    'the market and position objects: net profit and return on margin, maximum profit reached and how much was given '
    'back, trend strength, probability of continuation, reversal risk, volatility, momentum, costs and funding, and '
    'whether the capital could be used better elsewhere. Time alone is never a reason to close. The deepseek object is '
    'the primary analyst\'s proposal, for comparison only. Return only JSON: {"verdict":"CONFIRM"} to agree, or '
    '{"verdict":"CONTEST","action":"HOLD"|"CLOSE"|"PARTIAL_CLOSE"|"MODIFY_STOP"|"ADD","stop_price":"..." (only with '
    'MODIFY_STOP)} for a different action; add "confidence" (0 to 1) and "reasons" (up to 6 codes from: ' + _CODES +
    '). PARTIAL_CLOSE banks about 35 percent of the position; ADD is a second entry at a clearly better price that '
    'must not be blind averaging down (same stop, risk within the approved per-trade budget); a stop may only be '
    'tightened. Deterministic stop and '
    'take-profit orders stay active anyway. No orders, no tools.')


@dataclass(frozen=True)
class ClaudeView:
    status: str                              # ok | unavailable | budget | timeout_or_error | invalid | skipped_limit
    verdict: Optional[str] = None
    action: Optional[str] = None
    side: Optional[int] = None
    stop_price: Optional[Decimal] = None
    confidence: Optional[float] = None
    reasons: tuple = ()

    def payload(self) -> dict:
        return {"status": self.status, "verdict": self.verdict, "action": self.action, "side": self.side,
                "stop_price": None if self.stop_price is None else str(self.stop_price),
                "confidence": self.confidence, "reasons": list(self.reasons)}


class ClaudeConsultant:
    """Chiamata a Claude (Messages API) sul trasporto metrato con tetto proprio. Limite per giro e pausa per posizione."""

    def __init__(self, *, transport, model: str, effort: str, max_tokens: int, spending_gate, max_per_cycle: int,
                 cooldown_ms: int, enabled: bool = True):
        self.transport, self.model, self.effort, self.max_tokens = transport, model, effort, max_tokens
        self.gate, self.max_per_cycle, self.cooldown_ms, self.enabled = spending_gate, max_per_cycle, cooldown_ms, enabled
        self._cycle, self._used = None, 0
        self._last: dict = {}

    def start_cycle(self, cycle_key: int) -> None:
        if cycle_key != self._cycle:
            self._cycle, self._used = cycle_key, 0

    def cooling(self, key: str, now_ms: int) -> bool:
        return key in self._last and now_ms - self._last[key] < self.cooldown_ms

    def ask(self, system: str, info: Mapping, *, key: str, now_ms: int, position: bool) -> ClaudeView:
        if self._used >= self.max_per_cycle:
            return ClaudeView("skipped_limit")
        try:
            if self.gate is None or self.gate("claude") is not True:
                return ClaudeView("budget")               # tetto giornaliero di Claude raggiunto: nessuna chiamata
        except Exception:
            return ClaudeView("budget")
        self._used += 1
        self._last[key] = now_ms
        payload = consult_payload(self.model, self.effort, self.max_tokens, system, info)
        try:
            body = _call(self.transport, self.gate, "claude", self.model, self.enabled, payload)
        except ProviderUnavailable as exc:
            return ClaudeView("budget" if str(exc) == "budget_denied" else
                              "unavailable" if str(exc) == "provider_disabled" else "timeout_or_error")
        try:
            return parse_response(body, position=position)
        except Exception:
            return ClaudeView("invalid")


FALLBACK_BETA = "server-side-fallback-2026-07-01"


def consult_payload(model: str, effort: str, max_tokens: int, system: str, info: Mapping) -> dict:
    """La richiesta a Claude, identica per il Brain e per la verifica della procedura root."""
    return {"model": model, "max_tokens": max_tokens, "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort}, "fallbacks": "default", "system": system,
            "messages": [{"role": "user", "content": json.dumps(info, sort_keys=True, default=str)}]}


def parse_response(body: Mapping, *, position: bool) -> ClaudeView:
    """Risposta della Messages API -> valutazione; ``ValueError`` se non e' una risposta completa e valida."""
    if not isinstance(body, Mapping) or body.get("stop_reason") != "end_turn":
        raise ValueError("stop_reason")
    text = "".join(b.get("text", "") for b in body.get("content") or [] if isinstance(b, Mapping)
                   and b.get("type") == "text")
    return parse_claude(_json_object(text.strip()), position=position)


def parse_claude(obj: Mapping, *, position: bool) -> ClaudeView:
    verdict = obj.get("verdict")
    allowed = {"verdict", "confidence", "reasons"}
    if verdict not in VERDICTS:
        raise ValueError("verdict")
    conf = obj.get("confidence")
    if conf is not None and (type(conf) not in (int, float) or not math.isfinite(conf) or not 0 <= conf <= 1):
        raise ValueError("confidence")
    reasons = parse_reasons(obj.get("reasons"))
    action = side = stop = None
    if position:
        if verdict != "CONFIRM":
            allowed |= {"action", "stop_price"}
            action = obj.get("action")
            if action not in POSITION_ACTIONS or (action == "MODIFY_STOP") != ("stop_price" in obj):
                raise ValueError("action")
            stop = _bounded_decimal(obj["stop_price"]) if action == "MODIFY_STOP" else None
    elif verdict == "ALTERNATIVE":
        allowed |= {"side", "stop_price"}
        side = obj.get("side")
        if type(side) is not int or side not in (-1, 1):
            raise ValueError("side")
        stop = _bounded_decimal(obj["stop_price"])
    if not set(obj) <= allowed:
        raise ValueError("keys")
    return ClaudeView("ok", verdict, action, side, stop, None if conf is None else float(conf), reasons)


# ----------------------------------------------------------------------------- criteri di consulto
def entry_triggers(proposal: OpenProposal, regime: str, portfolio: Mapping, policy=None) -> tuple:
    """Criteri del consulto. ``policy`` (EntryPolicy): soglie di confidenza differenziate e regime EXPANSION si'/no;
    None = criteri di prima (soglia 0,65, EXPANSION incluso)."""
    out = []
    low = LOW_CONFIDENCE if policy is None else float(policy.consult_threshold(proposal.symbol))
    expansion = True if policy is None else policy.consult_on_expansion
    if proposal.uncertain or proposal.confidence < low:
        out.append("uncertainty")
    if ({"conflicting_signals", "trend_change", "reversal_risk"} & set(proposal.reasons)
            or (expansion and regime == "EXPANSION")):
        out.append("trend_change_or_conflict")
    try:
        risk_after = Decimal(str(portfolio.get("open_risk_pct", 0))) / 100 + Decimal("0.043")
        if risk_after > PORTFOLIO_RISK_TRIGGER:
            out.append("portfolio_risk")
    except Exception:
        out.append("portfolio_risk")
    if portfolio.get("guardian_mode") in ("SELECTIVE", "PROTECTED"):
        out.append("guardian_mode")
    return tuple(out)


@dataclass(frozen=True)
class PositionMetrics:
    r_now: Decimal
    roe_pct: Decimal
    mfe_r: Optional[Decimal]
    giveback: Optional[Decimal]              # quota del profitto massimo restituita (0-1)
    regime_entry: Optional[str]
    regime_now: Optional[str]

    @property
    def regime_against(self) -> bool:
        return (self.regime_entry is not None and self.regime_now is not None and self.regime_now != self.regime_entry
                and self.regime_now in ("TREND_UP", "TREND_DOWN", "RANGE", "EXPANSION"))

    def payload(self) -> dict:
        q = lambda v: None if v is None else str(v.quantize(Decimal("0.01")))   # noqa: E731
        return {"r_now": q(self.r_now), "roe_pct": q(self.roe_pct), "mfe_r": q(self.mfe_r),
                "giveback": q(self.giveback), "regime_entry": self.regime_entry, "regime_now": self.regime_now}


def position_triggers(ds_action: str, ds_uncertain: bool, m: PositionMetrics) -> tuple:
    out = []
    if ds_action != "HOLD":
        out.append("action_proposed")
    if ds_uncertain:
        out.append("uncertainty")
    if m.r_now >= INTERESTING_R or m.roe_pct >= INTERESTING_ROE:
        out.append("interesting_profit")
    if m.giveback is not None and m.mfe_r is not None and m.mfe_r >= GIVEBACK_MIN_MFE_R and m.giveback >= GIVEBACK_TRIGGER:
        out.append("profit_given_back")
    if m.regime_against:
        out.append("trend_change")
    return tuple(out)


# ----------------------------------------------------------------------------- arbitro
@dataclass(frozen=True)
class EntryVerdict:
    open: bool
    side: Optional[int]
    stop: Optional[Decimal]
    source: str                              # deepseek | claude | agreed | none
    code: str


def arbitrate_entry(ds: OpenProposal, claude: Optional[ClaudeView], regime: str, policy=None) -> EntryVerdict:
    """Apertura. Senza consulto: DeepSeek. Con consulto: conferma -> si'; contestazione -> no; alternativa -> stesso
    lato con lo stop di Claude, lato opposto solo con numeri a favore (Claude piu' sicuro e regime coerente), altrimenti
    nessuna apertura. Claude non disponibile su una decisione che lo richiedeva -> nessuna apertura."""
    if claude is None:
        return EntryVerdict(True, ds.side, ds.stop_price, "deepseek", "no_consult_needed")
    if claude.status != "ok":
        # Politica ``half_risk`` (non attiva per impostazione): Claude non ha giudicato (limite, budget, errore) ->
        # apertura di DeepSeek a rischio dimezzato, solo con confidenza sopra la soglia dello strumento.
        from backend.v3.entry_policy import NOT_CONSULTED
        if (policy is not None and policy.consult_limit_fallback == "half_risk" and claude.status in NOT_CONSULTED
                and not ds.uncertain and ds.confidence >= float(policy.consult_threshold(ds.symbol))):
            return EntryVerdict(True, ds.side, ds.stop_price, "deepseek", "claude_missing_half_risk")
        return EntryVerdict(False, None, None, "none", "claude_unavailable_critical")
    if claude.verdict == "CONFIRM":
        return EntryVerdict(True, ds.side, ds.stop_price, "agreed", "claude_confirmed")
    if claude.verdict == "CONTEST":
        return EntryVerdict(False, None, None, "claude", "claude_contested")
    cconf = claude.confidence if claude.confidence is not None else 0.0
    if claude.side == ds.side:
        return EntryVerdict(True, ds.side, claude.stop_price, "claude", "claude_stop_adopted")
    regime_ok = (claude.side == 1 and regime == "TREND_UP") or (claude.side == -1 and regime == "TREND_DOWN")
    if cconf >= 0.75 and ds.confidence <= 0.6 and regime_ok:
        return EntryVerdict(True, claude.side, claude.stop_price, "claude", "claude_alternative_adopted")
    return EntryVerdict(False, None, None, "none", "irreconcilable_no_trade")


@dataclass(frozen=True)
class PositionVerdict:
    action: str
    stop: Optional[Decimal]
    source: str                              # deepseek | claude | agreed
    code: str


def _score(action: str, m: PositionMetrics) -> float:
    s = 0.0
    if m.giveback is not None and m.mfe_r is not None and m.mfe_r >= GIVEBACK_MIN_MFE_R and m.giveback >= GIVEBACK_TRIGGER:
        s += {"CLOSE": 0.3, "PARTIAL_CLOSE": 0.3, "MODIFY_STOP": 0.2}.get(action, 0.0)
    if m.regime_against:
        s += {"CLOSE": 0.3, "PARTIAL_CLOSE": 0.2, "MODIFY_STOP": 0.1}.get(action, 0.0)
    elif m.r_now >= INTERESTING_R:
        s += {"HOLD": 0.15, "MODIFY_STOP": 0.15, "PARTIAL_CLOSE": 0.1}.get(action, 0.0)
    elif m.r_now >= 0:
        s += {"HOLD": 0.1}.get(action, 0.0)
    return s


def arbitrate_position(ds_action: str, ds_stop: Optional[Decimal], ds_conf: Optional[float],
                       claude: Optional[ClaudeView], m: PositionMetrics, side: int = 1) -> PositionVerdict:
    """Posizione. Senza consulto: DeepSeek. Claude non disponibile su un'azione che lo richiedeva -> HOLD (le uscite
    deterministiche restano attive). Accordo -> l'azione. Disaccordo -> punteggio = confidenza di chi la propone + dati
    (profitto restituito, regime, R); a parita' vince l'azione che riduce di piu' il rischio."""
    if claude is None:
        if ds_action == "ADD":                                  # un secondo ingresso non passa mai senza consulto
            return PositionVerdict("HOLD", None, "none", "add_needs_consult")
        return PositionVerdict(ds_action, ds_stop, "deepseek", "no_consult_needed")
    if ds_action == "ADD" or (claude.status == "ok" and claude.action == "ADD"):
        # secondo ingresso = piu' rischio: solo con le DUE analisi d'accordo, mai senza Claude
        if claude.status != "ok":
            return PositionVerdict("HOLD", None, "none", "claude_unavailable_critical")
        if ds_action == "ADD" and (claude.verdict == "CONFIRM" or claude.action == "ADD"):
            return PositionVerdict("ADD", None, "agreed", "claude_confirmed")
        if ds_action == "ADD":
            return PositionVerdict(claude.action or "HOLD", claude.stop_price, "claude", "claude_rejected_add")
        return PositionVerdict(ds_action, ds_stop, "deepseek", "add_needs_both")
    if claude.status != "ok":
        # Consulto richiesto ma Claude assente (chiave, rete, tetto giornaliero, limite per giro, formato): un'azione
        # che RIDUCE il rischio (chiusura, presa parziale, stop piu' stretto) si esegue comunque; il validatore
        # deterministico controlla poi che lo stop sia davvero piu' protettivo. Nessuna azione nuova inventata.
        if ds_action in ("CLOSE", "PARTIAL_CLOSE", "MODIFY_STOP"):
            return PositionVerdict(ds_action, ds_stop, "deepseek", "claude_unavailable_risk_reducing")
        return PositionVerdict("HOLD", None, "none", "claude_unavailable_hold")
    if claude.verdict == "CONFIRM" or claude.action == ds_action and (ds_action != "MODIFY_STOP"):
        return PositionVerdict(ds_action, ds_stop, "agreed", "claude_confirmed")
    c_action, c_stop = claude.action, claude.stop_price
    if c_action == ds_action == "MODIFY_STOP":           # stessa azione, stop diversi: il piu' prudente (piu' stretto)
        tighter = max(ds_stop, c_stop) if side == 1 else min(ds_stop, c_stop)
        return PositionVerdict("MODIFY_STOP", tighter, "agreed", "both_tighten_stop")   # il validatore controlla
    s_ds = (ds_conf if ds_conf is not None else 0.5) + _score(ds_action, m)
    s_cl = (claude.confidence if claude.confidence is not None else 0.5) + _score(c_action, m)
    if s_cl > s_ds or (s_cl == s_ds and _CONSERVATIVE[c_action] > _CONSERVATIVE[ds_action]):
        return PositionVerdict(c_action, c_stop, "claude", "claude_adopted")
    return PositionVerdict(ds_action, ds_stop, "deepseek", "deepseek_kept")


# ----------------------------------------------------------------------------- analista collaborativo (aperture)
class CollaborativeAnalyst(Analyst):
    """DeepSeek propone; se scatta un criterio Claude valuta; l'arbitro decide. Registra ogni consulto nel journal."""

    def __init__(self, inner: Analyst, consultant: ClaudeConsultant, *, journal, run_id: str,
                 market_view: Callable[[str, int], dict], portfolio_state: Callable[[], dict],
                 policy=None, roundtrip_cost_bp=None):
        if not isinstance(inner, Analyst):
            raise ValueError("invalid_analyst")
        self.inner, self.consultant, self.journal, self.run_id = inner, consultant, journal, run_id
        self.market_view, self.portfolio_state = market_view, portfolio_state
        self.policy, self.cost_bp = policy, roundtrip_cost_bp      # EntryPolicy della versione attiva (o None)

    def analyze(self, context: MarketContext, open_positions: list) -> BrainDecision:
        decision = self.inner.analyze(context, open_positions)
        prop = decision.proposal if isinstance(decision, BrainDecision) else None
        if decision.kind != DecisionKind.OPEN or not isinstance(prop, OpenProposal):
            return decision
        try:
            portfolio = self.portfolio_state()
        except Exception:
            portfolio = {}
        market, fetched = None, False
        if self.policy is not None and (self.policy.long_trend_filter or self.policy.max_cost_fraction_r is not None
                                        or self.policy.min_confidence is not None):
            from backend.v3.entry_policy import entry_block
            try:
                market = self.market_view(context.symbol, context.timestamp_ms)
            except Exception:
                market = None
            fetched = True
            block = entry_block(self.policy, side=prop.side, entry=Decimal(str(context.price)),
                                stop=prop.stop_price, market=market, roundtrip_cost_bp=Decimal(str(self.cost_bp or 16)),
                                confidence=prop.confidence)
            if block is not None:                         # filtro deterministico, prima del consulto (nessuna spesa)
                self._record_filter(context, prop, block)
                return BrainDecision(DecisionKind.NO_TRADE, rationale=decision.rationale,
                                     sources=list(decision.sources), occurred_at_ms=decision.occurred_at_ms)
        triggers = entry_triggers(prop, context.regime, portfolio, self.policy)
        claude = None
        if triggers:
            self.consultant.start_cycle(context.timestamp_ms // 900_000)
            if not fetched:
                try:
                    market = self.market_view(context.symbol, context.timestamp_ms)
                except Exception:
                    market = None
            info = {"symbol": context.symbol, "price": str(context.price), "regime": context.regime,
                    "timestamp_ms": context.timestamp_ms, "market": market, "portfolio": portfolio,
                    "deepseek": {"side": prop.side, "stop_price": str(prop.stop_price), "confidence": prop.confidence,
                                 "reasons": list(prop.reasons), "uncertain": prop.uncertain}}
            claude = (self.consultant.ask(ENTRY_PROMPT, info, key=f"entry:{context.symbol}", now_ms=context.timestamp_ms,
                                          position=False) if market is not None else ClaudeView("invalid"))
        verdict = arbitrate_entry(prop, claude, context.regime, self.policy)
        self._record(context, prop, triggers, claude, verdict)
        if verdict.code == "claude_missing_half_risk":
            from backend.v3.entry_policy import HALF_RISK
            decision.proposal = replace(prop, risk_scale=HALF_RISK)
            return decision
        if not verdict.open:
            return BrainDecision(DecisionKind.NO_TRADE, rationale=decision.rationale, sources=list(decision.sources),
                                 occurred_at_ms=decision.occurred_at_ms)
        if verdict.source == "claude":
            decision.proposal = replace(prop, side=verdict.side, stop_price=verdict.stop,
                                        originating_ai="claude" if verdict.side != prop.side else prop.originating_ai)
        if claude is not None and claude.status == "ok":
            decision.sources = list(decision.sources) + ["claude:review"]
        return decision

    def _record_filter(self, context, prop, code: str) -> None:
        try:
            self.journal.append(Event(
                event_id=f"entry_filter.{context.symbol}.{context.timestamp_ms}.{time.monotonic_ns() % 1_000_000}",
                portfolio_id="brain", run_id=self.run_id, kind="entry_filter", occurred_at_ms=context.timestamp_ms,
                source="runner.entry_policy",
                payload={"symbol": context.symbol, "side": prop.side, "price": str(context.price),
                         "stop_price": str(prop.stop_price), "confidence": prop.confidence, "code": code}))
        except Exception:
            pass

    def _record(self, context, prop, triggers, claude, verdict) -> None:
        try:
            self.journal.append(Event(
                event_id=f"{CONSULT_KIND}.{context.symbol}.{context.timestamp_ms}.{time.monotonic_ns() % 1_000_000}",
                portfolio_id="brain", run_id=self.run_id, kind=CONSULT_KIND, occurred_at_ms=context.timestamp_ms,
                source="runner.consult",
                payload={"scope": "entry", "symbol": context.symbol, "regime": context.regime,
                         "deepseek": {"action": "OPEN", "side": prop.side, "stop_price": str(prop.stop_price),
                                      "confidence": prop.confidence, "reasons": list(prop.reasons),
                                      "uncertain": prop.uncertain},
                         "triggers": list(triggers), "claude": None if claude is None else claude.payload(),
                         "final": {"open": verdict.open, "side": verdict.side,
                                   "stop_price": None if verdict.stop is None else str(verdict.stop),
                                   "source": verdict.source},
                         "code": verdict.code, "disagreement": bool(claude is not None and claude.status == "ok"
                                                                   and claude.verdict != "CONFIRM")}))
        except Exception:
            pass                                       # la registrazione non blocca la decisione (gia' prudente)
