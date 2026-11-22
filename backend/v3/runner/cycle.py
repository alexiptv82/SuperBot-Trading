"""Un giro del Brain (ciclo da 15 minuti): vista di mercato -> decisione del motore -> apertura PAPER.

Per ogni simbolo SENZA posizione aperta nel portafoglio ``brain``:
  1. scarica le candele chiuse (15 m / 1 h / 4 h) dalla cache incrementale ``CandleStore``;
  2. costruisce il regime con la STESSA vista che vedra' il modello (``regime_for_context``);
  3. fa decidere il motore (``BrainEngine.step``): analista, controllo del prezzo, risk gate, mandato, journal;
  4. se la decisione e' OPEN approvata, apre in PAPER con ``execute_paper`` (slippage avverso).

Garanzie:
* **Fail-closed.** Dati mancanti/vecchi, regole di mercato assenti, errore dell'analista o del feed: quel simbolo
  non apre niente e l'errore finisce nel rapporto; gli altri simboli proseguono.
* **Niente stato nascosto.** Il motore e' creato nuovo per ogni simbolo con un'istantanea del portafoglio
  ricostruita dal journal (equity = capitale PAPER + PnL realizzato; margine e rischio aperti dalle posizioni):
  una posizione aperta poco prima nello stesso giro conta gia' per il simbolo successivo.
* **Nessuna rete e nessun orologio qui**: ``store``, ``analyst``, ``price_source`` e ``market_rules`` sono
  iniettati; ``now_ms`` lo passa chi chiama.
* **Nessuna revisione di Claude**: soglia di revisione 0.0 (mai) e un revisore che rifiuta. Il mandato di
  rischio resta del motore: senza mandato approvato dall'utente il motore rifiuta ogni apertura
  (``policy_not_authorized``).

``MarketEntryAnalyst`` fa dell'ingresso un ordine a mercato: il prezzo di ingresso diventa il prezzo del
contesto (il motore verifica comunque che lo stop sia dal lato giusto e che il rischio sia nei limiti).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import re
from decimal import Decimal
from typing import Callable, Iterable, Mapping, Optional, Sequence

from backend.v3.brain_f2.analyst import Analyst
from backend.v3.brain_f2.contracts import (
    BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus,
)
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot
from backend.v3.brain_f2.reviewer import Reviewer
from backend.v3.brain_market.params import MarketViewParams
from backend.v3.brain_market.view import regime_for_context
from backend.v3.dashboard import PortfolioSummary, build_summary
from backend.v3.brain_market.classic_peers import validate_peer_signal
from backend.v3.events import EventJournal
from backend.v3.executor.paper import ExecutionError, execute_paper
from backend.v3.features.indicators import Bar
from backend.v3.risk import RiskPolicy, estimated_loss_per_unit
from backend.v3.runner.decision_trace import capture_inputs, journal_tip, record_decision_trace
from backend.v3.runner.thesis import ReentryPolicy, ThesisBook, evaluate as evaluate_reentry

PORTFOLIO_ID = "brain"
MIN_PRICE_PLACES = 8
RULE_KEYS = ("exchange_leverage_limit", "quantity_step", "minimum_notional", "maintenance_fraction")


class CycleBars:
    """Candele del giro in corso, per simbolo: e' la ``bars_source`` dell'analista L5."""

    def __init__(self) -> None:
        self._by_symbol: dict[str, dict[str, list[Bar]]] = {}

    def set(self, symbol: str, bars_by_tf: Mapping[str, list[Bar]]) -> None:
        self._by_symbol[symbol] = {tf: list(b) for tf, b in bars_by_tf.items()}

    def clear(self) -> None:
        self._by_symbol.clear()

    def __call__(self, symbol: str) -> dict[str, list[Bar]]:
        return self._by_symbol[symbol]                    # KeyError se manca: l'analista fallisce chiuso


class MarketEntryAnalyst(Analyst):
    """Avvolge un analista: ogni OPEN entra a mercato, cioe' ``entry_price = context.price``."""

    def __init__(self, inner: Analyst):
        if not isinstance(inner, Analyst):
            raise ValueError("invalid_analyst")
        self.inner = inner

    def analyze(self, context: MarketContext, open_positions: list[Mapping]) -> BrainDecision:
        decision = self.inner.analyze(context, open_positions)
        if (isinstance(decision, BrainDecision) and decision.kind == DecisionKind.OPEN
                and isinstance(decision.proposal, OpenProposal)):
            decision.proposal = replace(decision.proposal, entry_price=context.price)
        return decision


class NoReviewer(Reviewer):
    """Nessuna revisione in questa fase: se il motore la chiedesse, rifiuta (fail-closed)."""

    def review(self, decision: BrainDecision, complexity_reason: str) -> BrainDecision:
        raise RuntimeError("review_not_available")


@dataclass(frozen=True)
class CycleReport:
    now_ms: int
    skipped_open: tuple[str, ...]                          # simboli con posizione gia' aperta
    decisions: tuple[tuple[str, str, str, str], ...]       # (simbolo, tipo, stato, motivo)
    opened: tuple[tuple[str, str], ...]                    # (simbolo, position_id)
    errors: tuple[tuple[str, str], ...]                    # (simbolo, codice)
    # (simbolo, esito, id decisione, id snapshot) per ogni decisione tracciata; vuoto se la traccia e' spenta
    traces: tuple[tuple[str, str, str, str], ...] = ()
    # (simbolo, thesis_id, indice di reingresso, regola che bloccherebbe o "") per ogni OPEN approvata
    theses: tuple[tuple[str, str, int, str], ...] = ()
    # (simbolo, istante di riferimento della decisione): uguale a now_ms in modalita' "cycle"
    instants: tuple[tuple[str, int], ...] = ()


def snapshot_from_summary(summary: PortfolioSummary, initial_equity: Decimal,
                          roundtrip_cost_bp: Decimal) -> BrainPortfolioSnapshot:
    """Equity PAPER = capitale iniziale + PnL realizzato; margine e rischio aperto dalle posizioni aperte.

    Rischio aperto = perdita STIMATA allo stop delle posizioni aperte, costi stimati inclusi, con la STESSA formula
    del RiskManager (``risk.estimated_loss_per_unit``) sul prezzo di riempimento. Senza i costi ogni posizione era
    contata meno della sua stima (21/11/2026: con il profilo B 15,15 invece di 20 USDT a stop 0,5 %). Il journal
    non cambia: si cambia solo come lo si legge."""
    if type(roundtrip_cost_bp) is not Decimal or not roundtrip_cost_bp.is_finite() or roundtrip_cost_bp < 0:
        raise ValueError("invalid_cost_bp")
    equity = initial_equity + summary.realized_pnl
    margin = summary.margin_in_use
    open_risk = sum((estimated_loss_per_unit(p.fill_price, p.stop_price, roundtrip_cost_bp) * p.quantity
                     for p in summary.open_positions), Decimal("0"))
    cash = max(equity - margin, Decimal("0"))
    return BrainPortfolioSnapshot(equity, cash, margin, open_risk)


def price_with_room(price: Decimal) -> Decimal:
    """Il prezzo con almeno ``MIN_PRICE_PLACES`` decimali. ``execute_paper`` arrotonda il prezzo di riempimento a
    ZERO (ROUND_DOWN) alla precisione del prezzo di ingresso: con "0.18234" una slippage di 2 bp (0,0000036) sparirebbe
    sul long e diventerebbe un tick intero (5,5 bp) sullo short. Con 8 decimali l'errore e' trascurabile."""
    return price.quantize(Decimal(1).scaleb(min(price.as_tuple().exponent, -MIN_PRICE_PLACES)))


def _market_params(rules: Mapping) -> dict:
    params = {k: rules[k] for k in RULE_KEYS}
    params.update(market_data_fresh=True, paused=False, daily_loss_latched=False)
    return params


def run_brain_cycle(*, now_ms: int, journal: EventJournal, run_id: str, symbols: Sequence[str],
                    store, bars_holder: CycleBars, analyst: Analyst, view_params: MarketViewParams,
                    risk_policy: RiskPolicy, mandate: Optional[Mapping], policy_verifier: Callable,
                    market_rules: Callable[[str], Optional[Mapping]], initial_equity: Decimal,
                    slippage_bps: int, allowed_strategy_ids: Iterable[str] = (),
                    price_source: Optional[Callable[[str, int], Decimal]] = None,
                    rotate: int = 0, open_commit: Optional[Callable[[BrainDecision], object]] = None,
                    require_open_commit: bool = False,
                    peer_source: Optional[Callable[[str, int], Mapping]] = None,
                    trace: str = "off", wall_ms: Optional[Callable[[], int]] = None,
                    reentry_policy: Optional[ReentryPolicy] = None, instant: str = "cycle",
                    slot_start_ms: Optional[int] = None, slot_end_ms: Optional[int] = None) -> CycleReport:
    """Un giro su tutti i simboli. ``store.refresh(symbol, tf, now_ms)`` -> barre contigue (puo' sollevare).

    ``trace="required"``: ogni decisione scritta dal motore (anche NO_TRADE) riceve subito uno snapshot v2
    (``decision_trace``), prima di qualunque apertura. Se la traccia fallisce l'errore va nel rapporto e una OPEN
    approvata NON si apre (``open_blocked_untraced``): nessuna apertura senza evidenza. Le uscite e il controllo
    della perdita giornaliera non passano dal ciclo e non dipendono dalla traccia. Le feature si catturano PRIMA della
    chiamata al modello, dalle stesse candele; ``wall_ms`` (facoltativo) e' l'orologio di parete per le sole
    dichiarazioni di cattura/scrittura.

    ``reentry_policy`` (``thesis.py``): per ogni OPEN approvata calcola tesi e indice di reingresso dal journal (una
    query filtrata per giro) e li scrive nello snapshot. In ``observe`` registra che cosa bloccherebbe senza bloccare;
    in ``enforce`` una OPEN che viola la regola non si apre (``anti_reentry_blocked``). ``None`` = spento.

    ``instant`` (LABORATORIO): ``"cycle"`` (predefinito, comportamento attuale) usa ``now_ms`` per ogni simbolo;
    ``"per_symbol"`` da' a ogni simbolo il PROPRIO istante di riferimento, letto da ``wall_ms`` quando il simbolo
    comincia (candele, prezzo, decisione, snapshot e tesi a quell'istante: dati piu' freschi e decisione scritta
    subito dopo). Richiede ``wall_ms``, ``slot_start_ms <= now_ms < slot_end_ms``; l'istante deve essere >= ``now_ms``,
    non decrescente e < ``slot_end_ms`` (altrimenti ``instant_out_of_slot``, nessuna decisione). Deduplicazione per
    slot: un simbolo che ha gia' una decisione nel journal con istante in [slot_start_ms, slot_end_ms) non viene
    deciso di nuovo (``already_decided_in_slot``), anche dopo un riavvio a meta' slot.

    Deduplicazione per slot anche in modalita' ``"cycle"``: basta passare ``slot_start_ms``/``slot_end_ms`` (il runner
    cablato lo fa). Corregge il difetto per cui un riavvio nello stesso slot ridecideva tutti i simboli con un nuovo
    ``now_ms`` (nuovi id, chiamate AI e campioni duplicati). Senza i limiti dello slot: comportamento precedente.
    """
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError("invalid_now")
    if type(rotate) is not int or rotate < 0:
        raise ValueError("invalid_rotate")
    if type(require_open_commit) is not bool:
        raise ValueError("invalid_open_commit_mode")
    if require_open_commit and not callable(open_commit):
        raise ValueError("split_open_commit_required")
    if not require_open_commit and open_commit is not None:
        raise ValueError("open_commit_requires_split_mode")
    if type(trace) is not str or trace not in ("off", "required"):
        raise ValueError("invalid_trace_mode")
    if reentry_policy is not None and type(reentry_policy) is not ReentryPolicy:
        raise ValueError("invalid_reentry_policy")
    if instant not in ("cycle", "per_symbol"):
        raise ValueError("invalid_instant_mode")
    if instant == "per_symbol" and (not callable(wall_ms) or type(slot_start_ms) is not int
                                    or type(slot_end_ms) is not int or not slot_start_ms <= now_ms < slot_end_ms):
        raise ValueError("per_symbol_requires_clock_and_slot")
    slot_given = slot_start_ms is not None or slot_end_ms is not None
    if slot_given and (type(slot_start_ms) is not int or type(slot_end_ms) is not int
                       or not slot_start_ms <= now_ms < slot_end_ms):
        raise ValueError("invalid_slot")
    reentry_on = reentry_policy is not None and reentry_policy.mode != "off"
    if reentry_on and trace == "off":
        raise ValueError("reentry_requires_trace")       # una tesi non registrata non e' verificabile
    syms = list(symbols)
    if syms:
        k = rotate % len(syms)
        syms = syms[k:] + syms[:k]                         # a rotazione: nessun simbolo e' sempre il primo
    allowed = tuple(allowed_strategy_ids)
    summary = build_summary(journal, PORTFOLIO_ID, run_id)
    skipped = tuple(s for s in syms if s in {p.symbol for p in summary.open_positions})
    decisions: list[tuple[str, str, str, str]] = []
    opened: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    traces: list[tuple[str, str, str, str]] = []
    theses: list[tuple[str, str, int, str]] = []
    instants: list[tuple[str, int]] = []
    decided_in_slot: set = set()
    if slot_given:
        decided_in_slot = {r.event.payload.get("symbol") for r in journal.list_run_kinds_since(
            PORTFOLIO_ID, run_id, ("brain_decision",), slot_start_ms)
            if r.event.occurred_at_ms < slot_end_ms and isinstance(r.event.payload, Mapping)}
    last_t = now_ms
    book = (ThesisBook.from_journal(journal, run_id, now_ms=now_ms, window_ms=reentry_policy.window_ms)
            if reentry_on else None)
    tf_names = [spec.name for spec in view_params.timeframes]
    base_tf = view_params.base_timeframe
    bars_holder.clear()
    for symbol in syms:
        if symbol in {p.symbol for p in summary.open_positions}:
            continue
        if symbol in decided_in_slot:
            errors.append((symbol, "already_decided_in_slot"))
            continue
        t = now_ms
        if instant == "per_symbol":
            try:
                t = wall_ms()
            except Exception:
                t = None
            if type(t) is not int or t < last_t or t >= slot_end_ms:
                errors.append((symbol, "instant_out_of_slot"))
                continue
            last_t = t
        instants.append((symbol, t))
        try:
            rules = market_rules(symbol)
            if not isinstance(rules, Mapping) or any(k not in rules for k in RULE_KEYS):
                errors.append((symbol, "no_market_rules"))
                continue
            try:
                bars_by_tf = {tf: store.refresh(symbol, tf, t) for tf in tf_names}
            except Exception:
                errors.append((symbol, "feed_error"))
                continue
            try:
                regime = regime_for_context(bars_by_tf, timestamp_ms=t, params=view_params)
            except ValueError:
                errors.append((symbol, "view_error"))
                continue
            base = bars_by_tf.get(base_tf)
            if regime == "UNKNOWN" or not base:
                errors.append((symbol, "data_unavailable"))   # base non ok: nessuna decisione, nessuna spesa
                continue
            try:
                price = base[-1].close if price_source is None else price_source(symbol, t)
            except Exception:
                errors.append((symbol, "price_error"))
                continue
            if type(price) is not Decimal or not price.is_finite() or price <= 0:
                errors.append((symbol, "price_error"))
                continue
            price = price_with_room(price)
            bars_holder.set(symbol, bars_by_tf)
            portfolio = snapshot_from_summary(summary, initial_equity, risk_policy.estimated_roundtrip_cost_bp)
            engine = BrainEngine(
                analyst=analyst, reviewer=NoReviewer(), risk_policy=risk_policy,
                portfolio_snapshot=portfolio,
                market_params=_market_params(rules), journal=journal, portfolio_id=PORTFOLIO_ID,
                run_id=run_id, policy_mandate=dict(mandate) if mandate is not None else None,
                policy_verifier=policy_verifier, allowed_strategy_ids=allowed)
            engine.open_positions = [{"symbol": p.symbol, "side": p.side} for p in summary.open_positions]
            peers: Mapping = {}
            if peer_source is not None:
                try:
                    candidate = peer_source(symbol, t)
                    if type(candidate) is dict:
                        peers = candidate
                except Exception:
                    peers = {}  # no data, never an AI override
            context = MarketContext(
                symbol, price, t, regime,
                falco_signal=validate_peer_signal(peers.get("falco"), "falco", symbol, t),
                toro_signal=validate_peer_signal(peers.get("toro"), "toro", symbol, t))

            capture = None
            tip = 0
            if trace != "off":
                try:
                    capture = capture_inputs(bars_by_tf, view_params.timeframes, now_ms=t, wall_ms=wall_ms)
                except Exception:
                    capture = None                      # registrato come capture_missing dopo la decisione
                tip = journal_tip(journal, run_id)
            decision = engine.step(context, 0.0)
            decisions.append((symbol, decision.kind.value, decision.status.value, decision.rationale))
            approved_open = decision.kind == DecisionKind.OPEN and decision.status == ProposalStatus.APPROVED
            thesis = reentry = None
            blocked_by = None
            if approved_open and book is not None:
                side = decision.proposal.side
                info = book.assess(symbol, side, t, decision.journal_event_id)
                would, rule = evaluate_reentry(info, reentry_policy, t)
                thesis = {"thesis_id": info.thesis_id, "reentry_index": info.reentry_index,
                          "prev_outcome": info.prev_outcome, "truncated": info.truncated}
                reentry = {"mode": reentry_policy.mode, "would_block": would, "rule": rule,
                           "window_ms": reentry_policy.window_ms,
                           "max_reentry_index": reentry_policy.max_reentry_index,
                           "loss_cooldown_ms": reentry_policy.loss_cooldown_ms}
                theses.append((symbol, info.thesis_id, info.reentry_index, rule or ""))
                if would and reentry_policy.mode == "enforce":
                    blocked_by = rule
            if trace != "off":
                tr = record_decision_trace(
                    journal=journal, run_id=run_id, symbol=symbol, now_ms=t, after_seq=tip,
                    expected_event_id=decision.journal_event_id if approved_open else None,
                    capture=capture, portfolio=portfolio, wall_ms=wall_ms, thesis=thesis, anti_reentry=reentry)
                traces.append((symbol, tr.code, tr.decision_event_id or "", tr.snapshot_event_id or ""))
                if not tr.ok:
                    errors.append((symbol, tr.code))
                    if approved_open:
                        errors.append((symbol, "open_blocked_untraced"))
                        continue
            if blocked_by is not None:
                errors.append((symbol, "anti_reentry_blocked"))       # registrato nello snapshot, nessuna apertura
                continue
            if approved_open:
                if require_open_commit:
                    # No fallback to execute_paper. The cooperating writer rechecks
                    # current equity, mandate, pause and exit ownership *after* AI.
                    try:
                        from backend.v3.runner.open_serial import OpenCommit
                        outcome = open_commit(decision)
                        if type(outcome) is not OpenCommit:
                            errors.append((symbol, "split_open_result_invalid"))
                            continue
                        if outcome.allowed is not True:
                            code = outcome.code
                            errors.append((symbol, code if type(code) is str and
                                           re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code)
                                           else "split_open_denied"))
                            continue
                        receipt = outcome.receipt
                        # Never claim an OPEN from a forged/partial callback
                        # result; require the official journal record.
                        if (receipt is None or receipt.portfolio_id != PORTFOLIO_ID
                                or receipt.run_id != run_id or receipt.symbol != symbol
                                or receipt.decision_event_id != decision.journal_event_id
                                or not any(
                                    r.event.kind == "paper_open"
                                    and r.event.event_id == receipt.journal_event_id
                                    and r.event.payload.get("position_id") == receipt.position_id
                                    and r.event.payload.get("decision_event_id") == decision.journal_event_id
                                    for r in journal.list_run(PORTFOLIO_ID, run_id))):
                            errors.append((symbol, "split_open_receipt_unverified"))
                            continue
                    except Exception:
                        errors.append((symbol, "split_open_failed"))
                        continue
                else:
                    try:
                        receipt = execute_paper(decision, portfolio_id=PORTFOLIO_ID, run_id=run_id,
                                                journal=journal, slippage_bps=slippage_bps, now_ms=t)
                    except ExecutionError as exc:
                        errors.append((symbol, str(exc)))
                        continue
                opened.append((symbol, receipt.position_id))   # la tesi si ricostruisce dal journal al giro dopo
                summary = build_summary(journal, PORTFOLIO_ID, run_id)   # il prossimo simbolo vede questa posizione
        except Exception:
            errors.append((symbol, "cycle_error"))
    return CycleReport(now_ms, skipped, tuple(decisions), tuple(opened), tuple(errors), tuple(traces),
                       tuple(theses), tuple(instants))
