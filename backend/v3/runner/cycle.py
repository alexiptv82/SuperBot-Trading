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
from backend.v3.events import EventJournal
from backend.v3.executor.paper import ExecutionError, execute_paper
from backend.v3.features.indicators import Bar
from backend.v3.risk import RiskPolicy

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


def snapshot_from_summary(summary: PortfolioSummary, initial_equity: Decimal) -> BrainPortfolioSnapshot:
    """Equity PAPER = capitale iniziale + PnL realizzato; margine e rischio aperto dalle posizioni aperte."""
    equity = initial_equity + summary.realized_pnl
    margin = summary.margin_in_use
    open_risk = sum((abs(p.fill_price - p.stop_price) * p.quantity for p in summary.open_positions),
                    Decimal("0"))
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
                    require_open_commit: bool = False) -> CycleReport:
    """Un giro su tutti i simboli. ``store.refresh(symbol, tf, now_ms)`` -> barre contigue (puo' sollevare)."""
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
    tf_names = [spec.name for spec in view_params.timeframes]
    base_tf = view_params.base_timeframe
    bars_holder.clear()
    for symbol in syms:
        if symbol in {p.symbol for p in summary.open_positions}:
            continue
        try:
            rules = market_rules(symbol)
            if not isinstance(rules, Mapping) or any(k not in rules for k in RULE_KEYS):
                errors.append((symbol, "no_market_rules"))
                continue
            try:
                bars_by_tf = {tf: store.refresh(symbol, tf, now_ms) for tf in tf_names}
            except Exception:
                errors.append((symbol, "feed_error"))
                continue
            try:
                regime = regime_for_context(bars_by_tf, timestamp_ms=now_ms, params=view_params)
            except ValueError:
                errors.append((symbol, "view_error"))
                continue
            base = bars_by_tf.get(base_tf)
            if regime == "UNKNOWN" or not base:
                errors.append((symbol, "data_unavailable"))   # base non ok: nessuna decisione, nessuna spesa
                continue
            try:
                price = base[-1].close if price_source is None else price_source(symbol, now_ms)
            except Exception:
                errors.append((symbol, "price_error"))
                continue
            if type(price) is not Decimal or not price.is_finite() or price <= 0:
                errors.append((symbol, "price_error"))
                continue
            price = price_with_room(price)
            bars_holder.set(symbol, bars_by_tf)
            engine = BrainEngine(
                analyst=analyst, reviewer=NoReviewer(), risk_policy=risk_policy,
                portfolio_snapshot=snapshot_from_summary(summary, initial_equity),
                market_params=_market_params(rules), journal=journal, portfolio_id=PORTFOLIO_ID,
                run_id=run_id, policy_mandate=dict(mandate) if mandate is not None else None,
                policy_verifier=policy_verifier, allowed_strategy_ids=allowed)
            engine.open_positions = [{"symbol": p.symbol, "side": p.side} for p in summary.open_positions]
            context = MarketContext(symbol, price, now_ms, regime)
            decision = engine.step(context, 0.0)
            decisions.append((symbol, decision.kind.value, decision.status.value, decision.rationale))
            if decision.kind == DecisionKind.OPEN and decision.status == ProposalStatus.APPROVED:
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
                                                journal=journal, slippage_bps=slippage_bps, now_ms=now_ms)
                    except ExecutionError as exc:
                        errors.append((symbol, str(exc)))
                        continue
                opened.append((symbol, receipt.position_id))
                summary = build_summary(journal, PORTFOLIO_ID, run_id)   # il prossimo simbolo vede questa posizione
        except Exception:
            errors.append((symbol, "cycle_error"))
    return CycleReport(now_ms, skipped, tuple(decisions), tuple(opened), tuple(errors))
