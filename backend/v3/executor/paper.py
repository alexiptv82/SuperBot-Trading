"""PAPER executor for SuperBot V3.

Converts an APPROVED BrainDecision into a simulated PAPER fill and writes an
immutable event to the EventJournal. No live exchange API is called — this module
is intentionally offline-safe and usable in CI without any secrets.

Design constraints
------------------
* Fail-closed: if anything goes wrong before the journal write, we raise
  ExecutionError and nothing is changed. The decision object is updated to
  EXECUTED_PAPER only *after* the journal write succeeds.
* No slippage model: fill_price == entry_price (configurable slippage_bps for
  back-test replay, default 0).
* Only DecisionKind.OPEN is handled here. CLOSE / MODIFY_STOP require a
  separate executor that knows the existing position registry.
* The ExecutionReceipt is immutable and contains the journal event ID so it
  can be traced back to the append-only audit trail.
* Portfolio IDs must be in {'hawk', 'bull', 'brain'} — the EventJournal
  constraint. Callers own the mapping from their domain to these IDs.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any, Mapping

from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, ProposalStatus
from backend.v3.events import Event, EventJournal
from backend.v3.risk import RiskQuote


class ExecutionError(RuntimeError):
    """Raised when a PAPER execution cannot be completed safely.

    The message is a short snake_case code — no fill or balance information
    is embedded to avoid accidental logging of sensitive state.
    """


@dataclass(frozen=True)
class ExecutionReceipt:
    """Immutable record of a completed PAPER execution."""
    position_id: str          # uuid4 hex, unique per fill
    portfolio_id: str
    run_id: str
    symbol: str
    side: int                 # +1 long / -1 short
    fill_price: Decimal
    quantity: Decimal         # contracts / units (from RiskQuote)
    notional: Decimal         # fill_price × quantity
    margin_used: Decimal      # from RiskQuote
    leverage: int
    stop_price: Decimal
    slippage_bps: int
    timestamp_ms: int
    journal_seq: int          # StoredEvent.seq from EventJournal
    journal_event_id: str     # Event.event_id stored in journal


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ExecutionError(code)


def _validate_decision(decision: BrainDecision) -> None:
    _require(isinstance(decision, BrainDecision), "invalid_decision_type")
    _require(decision.kind == DecisionKind.OPEN, "decision_not_open")
    _require(decision.status == ProposalStatus.APPROVED, "decision_not_approved")
    _require(decision.proposal is not None, "missing_proposal")


def _validate_risk_quote(quote: RiskQuote) -> None:
    _require(isinstance(quote, RiskQuote), "invalid_risk_quote_type")
    _require(quote.allowed is True, "risk_quote_not_allowed")
    _require(isinstance(quote.quantity, Decimal) and quote.quantity > 0, "invalid_quantity")
    _require(isinstance(quote.margin, Decimal) and quote.margin > 0, "invalid_margin")
    _require(isinstance(quote.notional, Decimal) and quote.notional > 0, "invalid_notional")


def _apply_slippage(price: Decimal, side: int, slippage_bps: int) -> Decimal:
    """Adjust entry price for simulated slippage.

    Long  (+1): buyer pays slightly more  (price × (1 + bps/10000))
    Short (-1): seller receives slightly less (price × (1 − bps/10000))
    """
    if slippage_bps == 0:
        return price
    factor = Decimal(slippage_bps) / Decimal(10000)
    if side == 1:
        return (price * (1 + factor)).quantize(price, rounding=ROUND_DOWN)
    else:
        return (price * (1 - factor)).quantize(price, rounding=ROUND_DOWN)


def execute_paper(
    decision: BrainDecision,
    *,
    portfolio_id: str,
    run_id: str,
    journal: EventJournal,
    slippage_bps: int = 0,
    now_ms: int | None = None,
) -> ExecutionReceipt:
    """Simulate a PAPER fill for an APPROVED BrainDecision.

    Parameters
    ----------
    decision:
        Must be OPEN + APPROVED with a valid proposal and risk_quote.
    portfolio_id:
        Target portfolio ('hawk', 'bull', 'brain'). Must match the EventJournal constraint.
    run_id:
        Current run identifier. Stored in the journal event.
    journal:
        Initialised EventJournal (init_schema() already called by caller).
    slippage_bps:
        Simulated one-way slippage in basis points (0 = no slippage). Default 0.
    now_ms:
        Override timestamp for deterministic tests. If None, uses current epoch ms.

    Returns
    -------
    ExecutionReceipt
        Immutable record of the fill. The decision's status is set to EXECUTED_PAPER.

    Raises
    ------
    ExecutionError
        On any validation failure or journal write failure. The decision object
        is NOT modified when this exception is raised.
    """
    # --- validation (fail early, before any side-effect) ---
    _require(isinstance(portfolio_id, str) and portfolio_id, "invalid_portfolio_id")
    _require(isinstance(run_id, str) and run_id, "invalid_run_id")
    _require(isinstance(journal, EventJournal), "invalid_journal_type")
    _require(isinstance(slippage_bps, int) and 0 <= slippage_bps <= 500, "invalid_slippage_bps")

    _validate_decision(decision)
    proposal = decision.proposal

    # risk_quote can be on decision.risk_quote (set by BrainEngine)
    quote = decision.risk_quote
    _validate_risk_quote(quote)

    _require(isinstance(proposal.symbol, str) and proposal.symbol, "invalid_symbol")
    _require(proposal.side in (-1, 1), "invalid_side")
    _require(isinstance(proposal.entry_price, Decimal) and proposal.entry_price > 0,
             "invalid_entry_price")
    _require(isinstance(proposal.stop_price, Decimal) and proposal.stop_price > 0,
             "invalid_stop_price")
    _require(isinstance(proposal.leverage, int) and 1 <= proposal.leverage <= 125,
             "invalid_leverage")

    # --- compute fill ---
    timestamp_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    _require(isinstance(timestamp_ms, int) and timestamp_ms > 0, "invalid_timestamp")

    fill_price = _apply_slippage(proposal.entry_price, proposal.side, slippage_bps)
    _require(fill_price > 0, "fill_price_zero")

    quantity = quote.quantity
    notional = (fill_price * quantity).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
    margin_used = quote.margin
    position_id = uuid.uuid4().hex

    # --- build journal event payload (no credentials, no balances) ---
    payload: dict[str, Any] = {
        "position_id": position_id,
        "symbol": proposal.symbol,
        "side": proposal.side,
        "fill_price": str(fill_price),
        "quantity": str(quantity),
        "notional": str(notional),
        "margin_used": str(margin_used),
        "leverage": proposal.leverage,
        "stop_price": str(proposal.stop_price),
        "slippage_bps": slippage_bps,
        "originating_ai": getattr(proposal, "originating_ai", "unknown"),
        "context_hash": getattr(proposal, "context_hash", ""),
        "rationale": decision.rationale,
    }

    event_id = f"paper_open.{position_id}"
    event = Event(
        event_id=event_id,
        portfolio_id=portfolio_id,
        run_id=run_id,
        kind="paper_open",
        occurred_at_ms=timestamp_ms,
        source="executor.paper",
        payload=payload,
    )

    # --- write to journal (the only side-effect) ---
    try:
        stored = journal.append(event)
    except Exception as exc:
        raise ExecutionError("journal_write_failed") from exc

    # --- mark decision as executed only after successful journal write ---
    decision.status = ProposalStatus.EXECUTED_PAPER

    return ExecutionReceipt(
        position_id=position_id,
        portfolio_id=portfolio_id,
        run_id=run_id,
        symbol=proposal.symbol,
        side=proposal.side,
        fill_price=fill_price,
        quantity=quantity,
        notional=notional,
        margin_used=margin_used,
        leverage=proposal.leverage,
        stop_price=proposal.stop_price,
        slippage_bps=slippage_bps,
        timestamp_ms=timestamp_ms,
        journal_seq=stored.seq,
        journal_event_id=stored.event.event_id,
    )
