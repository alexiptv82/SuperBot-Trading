"""P0 opt-in PAPER post-model safety recheck; not wired into the runner.

This gate re-examines portfolio and risk AFTER DeepSeek returns. It is only a
pre-execution veto, not a transaction: concurrency with other opening writers
requires a separate single-writer/transactional protocol before production.
Failure always denies; it never resizes or approves the LLM's proposal.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Mapping

from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, ProposalStatus, OpenProposal
from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.risk import RiskRequest, RiskPolicy, RiskQuote, quote_paper_risk
from backend.v3.runner.cycle import snapshot_from_summary


@dataclass(frozen=True)
class OpenGuardResult:
    allowed: bool
    code: str  # closed vocabulary; no market data, keys or PnL in this result


def recheck_paper_open(*, decision: BrainDecision, journal: EventJournal,
                       run_id: str, initial_equity: Decimal, risk_policy: RiskPolicy,
                       now_ms: int, exit_healthy: Callable[[int], bool],
                       mandate_problem: Callable[[], str | None],
                       budget_problem: Callable[[], str | None],
                       daily_loss_halted: Callable[[int], bool],
                       paused: Callable[[], bool],
                       market_rules: Callable[[str], Mapping | None],
                       market_price: Callable[[str,int], Decimal],
                       market_fresh: Callable[[str,int], bool],
                       max_decision_age_ms: int = 120_000,
                       max_entry_divergence: Decimal = Decimal('0.005')) -> OpenGuardResult:
    """Deny stale, re-sized, unsafe or unprotected PAPER opens. No side effects.

    Call the *fresh* clock rather than the `now_ms` recorded before the model
    call. Every provider failure fails closed; approved quote may only shrink
    with fresh portfolio risk, never increase. No trade is opened here.
    """
    deny = lambda code: OpenGuardResult(False, code)
    if (type(journal) is not EventJournal or type(risk_policy) is not RiskPolicy
            or type(run_id) is not str or not run_id
            or type(initial_equity) is not Decimal or not initial_equity.is_finite()
            or initial_equity <= 0 or type(now_ms) is not int or now_ms <= 0
            or type(max_decision_age_ms) is not int or not 1 <= max_decision_age_ms <= 900_000
            or type(max_entry_divergence) is not Decimal or not max_entry_divergence.is_finite()
            or not Decimal('0') <= max_entry_divergence <= Decimal('0.05')):
        return deny('guard_invalid_input')
    if (type(decision) is not BrainDecision or decision.kind != DecisionKind.OPEN
            or decision.status != ProposalStatus.APPROVED
            or type(decision.proposal) is not OpenProposal
            or type(decision.risk_quote) is not RiskQuote
            or decision.risk_quote.allowed is not True):
        return deny('decision_not_executable')
    p, q = decision.proposal, decision.risk_quote
    if (type(decision.occurred_at_ms) is not int or decision.occurred_at_ms <= 0
            or not 0 <= now_ms - decision.occurred_at_ms <= max_decision_age_ms):
        return deny('decision_stale')
    if not all(callable(x) for x in (exit_healthy, mandate_problem, budget_problem,
                                   daily_loss_halted, paused, market_rules, market_price, market_fresh)):
        return deny('guard_invalid_input')
    try:
        # An OPEN must already be recorded by BrainEngine in this exact run.
        # An unchecked decision-event ID from the model is not proof.
        journal.verify_chain()  # journal corruption must veto; no external anchor assumed
        linked = decision.journal_event_id
        if type(linked) is not str or not linked:
            return deny('decision_unjournaled')
        if not any(
            e.event.event_id == linked and e.event.kind == 'brain_decision'
            and e.event.occurred_at_ms == decision.occurred_at_ms
            and type(e.event.payload) is dict and e.event.payload.get('symbol') == p.symbol
            and e.event.payload.get('kind') == 'OPEN'
            and e.event.payload.get('status') == 'APPROVED'
            and e.event.payload.get('rationale') == decision.rationale
            for e in journal.list_run('brain',run_id)
        ):
            return deny('decision_unjournaled')
        if exit_healthy(now_ms) is not True:
            return deny('exit_service_unhealthy')
        if paused() is not False:
            return deny('brain_paused')
        if mandate_problem() is not None:
            return deny('mandate_unavailable')
        if budget_problem() is not None:
            return deny('budget_unavailable')
        if daily_loss_halted(now_ms) is not False:
            return deny('daily_loss_unavailable_or_halted')
        summary = build_summary(journal,'brain',run_id)
        if p.symbol in {x.symbol for x in summary.open_positions}:
            return deny('already_open')
        if market_fresh(p.symbol, now_ms) is not True:
            return deny('market_unavailable')
        price = market_price(p.symbol,now_ms)
        if type(price) is not Decimal or not price.is_finite() or price <= 0:
            return deny('market_unavailable')
        if (type(p.entry_price) is not Decimal or not p.entry_price.is_finite()
                or p.entry_price <= 0 or abs(price-p.entry_price)/p.entry_price > max_entry_divergence):
            return deny('market_price_moved')
        rules = market_rules(p.symbol)
        if not isinstance(rules,Mapping):
            return deny('market_rules_unavailable')
        required=('exchange_leverage_limit','quantity_step','minimum_notional','maintenance_fraction')
        if not all(k in rules for k in required):
            return deny('market_rules_unavailable')
        snap = snapshot_from_summary(summary,initial_equity)
        fresh_quote = quote_paper_risk(risk_policy, RiskRequest(
            equity=snap.equity, available_cash=snap.available_cash,
            margin_used=snap.margin_used, existing_open_risk=snap.existing_open_risk,
            entry_price=price, stop_price=p.stop_price,
            side=p.side, requested_leverage=p.leverage,
            exchange_leverage_limit=rules['exchange_leverage_limit'],
            quantity_step=rules['quantity_step'],minimum_notional=rules['minimum_notional'],
            maintenance_fraction=rules['maintenance_fraction'],
            market_data_fresh=True,paused=False,daily_loss_latched=False))
        if not fresh_quote.allowed:
            return deny('risk_rejected_after_ai')
        # The proposal was approved with an earlier snapshot. If it is now too
        # large, deny; this gate MUST NOT silently resize an approved decision.
        for old,fresh in ((q.quantity,fresh_quote.quantity),(q.notional,fresh_quote.notional),
                          (q.margin,fresh_quote.margin),
                          (q.worst_case_loss_estimate,fresh_quote.risk_budget)):
            if (type(old) is not Decimal or not old.is_finite() or old <= 0
                    or type(fresh) is not Decimal or not fresh.is_finite() or old > fresh):
                return deny('risk_changed_after_ai')
        if (exit_healthy(now_ms) is not True or paused() is not False
                or mandate_problem() is not None or budget_problem() is not None
                or daily_loss_halted(now_ms) is not False
                or market_fresh(p.symbol,now_ms) is not True):
            return deny('safety_changed_after_ai')
    except Exception:
        return deny('recheck_failed')
    return OpenGuardResult(True,'validated_current_paper_risk')
