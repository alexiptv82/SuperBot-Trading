"""Trade outcomes for the evolving brain (F7, step P3).

Turns the append-only journal into immutable ``TradeOutcome`` records: one per
CLOSED paper position, with costs, net result in basis points, R multiple,
exit reason and a *verified* link to the decision that produced the position.
This is the only input the F7 learning modules are meant to consume.

Design
------
* Pure and read-only: reads the journal, never writes, no clock, no network, no
  randomness. The same journal gives the same report.
* Nothing is dropped silently. A position that cannot be turned into a trusted
  outcome (corrupt payload, open/close that disagree, tampered numbers) goes to
  ``OutcomeReport.skipped`` with an exact code. Positions still open are listed
  in ``open_position_ids``.
* The numbers are re-derived, not trusted: the extractor recomputes gross PnL,
  fees and net PnL from the close payload with the same formula as
  ``close_paper`` and rejects a close whose stored values disagree
  (``inconsistent_close``). A change of formula in ``close_paper`` therefore
  breaks loudly here instead of corrupting what the brain learns.
* The decision link is checked against the journal (``link_status``). Only
  ``"linked"`` is a trustworthy attribution; every other status keeps the outcome
  (the trade really happened) but lets the learner exclude it:

  =====================  ===================================================
  ``linked``             the 'brain_decision' event exists, is an approved
                         OPEN for the same symbol and precedes the open
  ``unlinked``           no decision id (position opened by hand / legacy)
  ``dangling``           an id is present but no such brain_decision exists
  ``wrong_decision``     the event exists but is not an approved OPEN
  ``symbol_mismatch``    the decision was about a different symbol
  ``decision_after_open``  the decision is later than the position it "caused"
  =====================  ===================================================

* ``exit_reason == "manual"`` is kept distinct (``TradeOutcome.is_manual``): a
  manual close is a real trade, but a learner must not imitate it blindly.
* Money and prices are ``Decimal`` (serialised as strings by ``to_dict``);
  ``*_bp`` are basis points of the ENTRY notional, rounded half-even to 1e-4.
* No threshold, limit or strategy parameter lives here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, Mapping, Optional

from backend.v3.events import EventJournal, StoredEvent

SCHEMA_VERSION = 1

EXIT_REASONS = frozenset({"stop", "brain_close", "manual", "liquidation"})
LINK_STATUSES = ("linked", "unlinked", "dangling", "wrong_decision",
                 "symbol_mismatch", "decision_after_open")
REGIMES = frozenset({"TRENDING", "RANGING", "VOLATILE", "UNKNOWN"})

_Q8 = Decimal("0.00000001")
_Q4 = Decimal("0.0001")
_BP = Decimal(10000)
_NUMBER = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$")
_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")


class OutcomeError(RuntimeError):
    """Raised when outcomes cannot be extracted at all. Message = snake_case code."""


class _Bad(Exception):
    """Internal: a single position is not usable; ``args[0]`` is the skip code."""


@dataclass(frozen=True)
class TradeOutcome:
    """Immutable result of one closed paper position."""
    schema_version: int
    position_id: str
    portfolio_id: str
    run_id: str
    symbol: str
    side: int                       # +1 long / -1 short
    originating_ai: str
    leverage: int
    opened_at_ms: int
    closed_at_ms: int
    hold_ms: int
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    notional_entry: Decimal
    margin_used: Decimal
    gross_pnl: Decimal
    fees: Decimal
    realized_pnl: Decimal           # net of fees
    gross_bp: Decimal               # gross result, bp of entry notional
    costs_bp: Decimal               # round-trip fees, bp of entry notional
    net_bp: Decimal                 # net result, bp of entry notional
    stop_distance_bp: Optional[Decimal]   # |entry-stop| / entry, bp (None if stop on the wrong side)
    r_multiple: Optional[Decimal]         # realized_pnl / (|entry-stop| * quantity)
    exit_reason: str                # one of EXIT_REASONS
    loss_exceeds_margin: bool
    decision_event_id: str          # "" if unlinked
    link_status: str                # one of LINK_STATUSES
    decision_regime: str            # regime recorded by the decision, "" if unknown

    @property
    def is_manual(self) -> bool:
        return self.exit_reason == "manual"

    @property
    def is_win(self) -> bool:
        """Net of fees, as decided by the user: a manual close in profit is a win too."""
        return self.realized_pnl > 0

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe, deterministic: Decimals as strings, None kept."""
        out: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            v = getattr(self, name)
            out[name] = str(v) if isinstance(v, Decimal) else v
        return out


@dataclass(frozen=True)
class SkippedRecord:
    position_id: str
    code: str


@dataclass(frozen=True)
class OutcomeReport:
    portfolio_id: str
    run_id: str
    brain_run_id: str
    outcomes: tuple[TradeOutcome, ...]        # in order of closing
    open_position_ids: tuple[str, ...]        # opened, not yet closed
    skipped: tuple[SkippedRecord, ...]        # unusable records, with a reason

    @property
    def linked_outcomes(self) -> tuple[TradeOutcome, ...]:
        """Outcomes whose decision attribution is verified."""
        return tuple(o for o in self.outcomes if o.link_status == "linked")

    def link_counts(self) -> dict[str, int]:
        counts = {s: 0 for s in LINK_STATUSES}
        for o in self.outcomes:
            counts[o.link_status] += 1
        return counts


# ---------------------------------------------------------------------------
# payload parsing (strict: wrong type or shape => the position is skipped)
# ---------------------------------------------------------------------------

def _num(payload: Mapping[str, Any], key: str, code: str) -> Decimal:
    v = payload.get(key)
    if not isinstance(v, str) or not _NUMBER.match(v):
        raise _Bad(code)
    d = Decimal(v)
    if not d.is_finite():
        raise _Bad(code)
    return d


def _int(payload: Mapping[str, Any], key: str, code: str, lo: int, hi: int) -> int:
    v = payload.get(key)
    if type(v) is not int or not lo <= v <= hi:
        raise _Bad(code)
    return v


def _str(payload: Mapping[str, Any], key: str, code: str) -> str:
    v = payload.get(key)
    if not isinstance(v, str) or not v or len(v) > 128:
        raise _Bad(code)
    return v


def _q8(v: Decimal) -> Decimal:
    return v.quantize(_Q8, rounding=ROUND_HALF_EVEN)


def _q4(v: Decimal) -> Decimal:
    return v.quantize(_Q4, rounding=ROUND_HALF_EVEN)


def _parse_open(se: StoredEvent, pid: str) -> dict[str, Any]:
    p = se.event.payload
    if not isinstance(p, Mapping) or se.event.event_id != f"paper_open.{pid}":
        raise _Bad("corrupt_open")
    side = _int(p, "side", "corrupt_open", -1, 1)
    if side == 0:
        raise _Bad("corrupt_open")
    fill = _num(p, "fill_price", "corrupt_open")
    qty = _num(p, "quantity", "corrupt_open")
    margin = _num(p, "margin_used", "corrupt_open")
    stop = _num(p, "stop_price", "corrupt_open")
    if fill <= 0 or qty <= 0 or margin <= 0 or stop <= 0:
        raise _Bad("corrupt_open")
    ai = p.get("originating_ai", "unknown")
    if not isinstance(ai, str) or len(ai) > 128:
        raise _Bad("corrupt_open")
    did = p.get("decision_event_id", "")
    if not isinstance(did, str) or (did and not _ID.match(did)):
        raise _Bad("corrupt_open")
    return {"symbol": _str(p, "symbol", "corrupt_open"), "side": side, "fill": fill,
            "qty": qty, "margin": margin, "stop": stop,
            "leverage": _int(p, "leverage", "corrupt_open", 1, 125),
            "ai": ai, "decision_event_id": did, "opened_at_ms": se.event.occurred_at_ms}


def _parse_close(se: StoredEvent, pid: str) -> dict[str, Any]:
    p = se.event.payload
    if not isinstance(p, Mapping) or se.event.event_id != f"paper_close.{pid}":
        raise _Bad("corrupt_close")
    reason = p.get("reason")
    if not isinstance(reason, str) or reason not in EXIT_REASONS:
        raise _Bad("corrupt_close")
    flag = p.get("loss_exceeds_margin")
    if type(flag) is not bool:
        raise _Bad("corrupt_close")
    did = p.get("decision_event_id", "")
    if not isinstance(did, str) or len(did) > 128:
        raise _Bad("corrupt_close")
    side = _int(p, "side", "corrupt_close", -1, 1)
    if side == 0:
        raise _Bad("corrupt_close")
    return {
        "symbol": _str(p, "symbol", "corrupt_close"), "side": side,
        "entry": _num(p, "entry_price", "corrupt_close"),
        "exit": _num(p, "exit_price", "corrupt_close"),
        "qty": _num(p, "quantity", "corrupt_close"),
        "n_entry": _num(p, "notional_entry", "corrupt_close"),
        "n_exit": _num(p, "notional_exit", "corrupt_close"),
        "gross": _num(p, "gross_pnl", "corrupt_close"),
        "fees": _num(p, "fees", "corrupt_close"),
        "realized": _num(p, "realized_pnl", "corrupt_close"),
        "margin": _num(p, "margin_used", "corrupt_close"),
        "fee_bps": _num(p, "fee_bps", "corrupt_close"),
        "leverage": _int(p, "leverage", "corrupt_close", 1, 125),
        "opened_at_ms": _int(p, "opened_at_ms", "corrupt_close", 0, 2**62),
        "held_ms": _int(p, "held_ms", "corrupt_close", 0, 2**62),
        "reason": reason, "loss_exceeds_margin": flag, "decision_event_id": did,
        "closed_at_ms": se.event.occurred_at_ms,
    }


def _check_close_against_open(o: dict[str, Any], c: dict[str, Any]) -> None:
    same = (o["symbol"] == c["symbol"] and o["side"] == c["side"]
            and o["fill"] == c["entry"] and o["qty"] == c["qty"]
            and o["margin"] == c["margin"] and o["leverage"] == c["leverage"]
            and o["opened_at_ms"] == c["opened_at_ms"]
            and o["decision_event_id"] == c["decision_event_id"]
            and c["held_ms"] == c["closed_at_ms"] - o["opened_at_ms"]
            and c["closed_at_ms"] >= o["opened_at_ms"])
    if not same:
        raise _Bad("close_open_mismatch")


def _recompute(c: dict[str, Any]) -> None:
    """Same formula as close_paper; any disagreement means the record is not trusted."""
    if c["exit"] <= 0 or c["entry"] <= 0 or c["qty"] <= 0 or not 0 <= c["fee_bps"] <= 100:
        raise _Bad("inconsistent_close")
    gross = _q8(Decimal(c["side"]) * (c["exit"] - c["entry"]) * c["qty"])
    n_entry = _q8(c["entry"] * c["qty"])
    n_exit = _q8(c["exit"] * c["qty"])
    fees = _q8((n_entry + n_exit) * c["fee_bps"] / Decimal(10000))
    realized = _q8(gross - fees)
    exceeds = bool(realized < 0 and -realized > c["margin"])
    if not (gross == c["gross"] and n_entry == c["n_entry"] and n_exit == c["n_exit"]
            and fees == c["fees"] and realized == c["realized"]
            and exceeds == c["loss_exceeds_margin"]):
        raise _Bad("inconsistent_close")


def _link(did: str, symbol: str, opened_at_ms: int,
          brain: Mapping[str, StoredEvent]) -> tuple[str, str]:
    """-> (link_status, decision_regime)."""
    if not did:
        return "unlinked", ""
    se = brain.get(did)
    if se is None:
        return "dangling", ""
    p = se.event.payload if isinstance(se.event.payload, Mapping) else {}
    regime = p.get("regime")
    regime = regime if isinstance(regime, str) and regime in REGIMES else ""
    if p.get("kind") != "OPEN" or p.get("status") != "APPROVED":
        return "wrong_decision", regime
    if p.get("symbol") != symbol:
        return "symbol_mismatch", regime
    if se.event.occurred_at_ms > opened_at_ms:
        return "decision_after_open", regime
    return "linked", regime


def _build(pid: str, portfolio_id: str, run_id: str, o: dict[str, Any], c: dict[str, Any],
           brain: Mapping[str, StoredEvent]) -> TradeOutcome:
    _check_close_against_open(o, c)
    try:
        _recompute(c)
    except ArithmeticError:           # finite but extreme values (huge exponents)
        raise _Bad("numeric_out_of_range") from None
    try:
        n_entry = c["n_entry"]
        gross_bp = _q4(c["gross"] / n_entry * _BP)
        costs_bp = _q4(c["fees"] / n_entry * _BP)
        net_bp = _q4(c["realized"] / n_entry * _BP)
        stop_dist = abs(o["fill"] - o["stop"])
        right_side = o["stop"] < o["fill"] if o["side"] == 1 else o["stop"] > o["fill"]
        stop_bp: Optional[Decimal] = None
        r_mult: Optional[Decimal] = None
        if right_side:
            stop_bp = _q4(stop_dist / o["fill"] * _BP)
            r_mult = _q4(c["realized"] / (stop_dist * o["qty"]))
    except ArithmeticError:
        raise _Bad("numeric_out_of_range") from None
    status, regime = _link(o["decision_event_id"], o["symbol"], o["opened_at_ms"], brain)
    return TradeOutcome(
        schema_version=SCHEMA_VERSION, position_id=pid, portfolio_id=portfolio_id, run_id=run_id,
        symbol=o["symbol"], side=o["side"], originating_ai=o["ai"], leverage=o["leverage"],
        opened_at_ms=o["opened_at_ms"], closed_at_ms=c["closed_at_ms"], hold_ms=c["held_ms"],
        entry_price=c["entry"], exit_price=c["exit"], quantity=c["qty"], notional_entry=n_entry,
        margin_used=c["margin"], gross_pnl=c["gross"], fees=c["fees"], realized_pnl=c["realized"],
        gross_bp=gross_bp, costs_bp=costs_bp, net_bp=net_bp,
        stop_distance_bp=stop_bp, r_multiple=r_mult, exit_reason=c["reason"],
        loss_exceeds_margin=c["loss_exceeds_margin"], decision_event_id=o["decision_event_id"],
        link_status=status, decision_regime=regime)


def _read(journal: EventJournal, portfolio_id: str, run_id: str) -> list[StoredEvent]:
    try:
        return journal.list_run(portfolio_id, run_id)
    except ValueError:
        raise OutcomeError("invalid_scope") from None
    except Exception as exc:
        raise OutcomeError("journal_read_failed") from exc


def extract_outcomes(journal: EventJournal, portfolio_id: str, run_id: str, *,
                     brain_run_id: Optional[str] = None) -> OutcomeReport:
    """Build the outcome report of one portfolio/run from the journal (read-only).

    ``brain_run_id`` is the run of the engine that wrote the 'brain_decision'
    events (portfolio 'brain'); it defaults to ``run_id``.
    """
    if not (isinstance(portfolio_id, str) and portfolio_id):
        raise OutcomeError("invalid_portfolio_id")
    if not (isinstance(run_id, str) and run_id):
        raise OutcomeError("invalid_run_id")
    if brain_run_id is not None and not (isinstance(brain_run_id, str) and brain_run_id):
        raise OutcomeError("invalid_brain_run_id")
    if not isinstance(journal, EventJournal):
        raise OutcomeError("invalid_journal_type")
    brain_run = brain_run_id if brain_run_id is not None else run_id

    events = _read(journal, portfolio_id, run_id)
    brain = {se.event.event_id: se for se in _read(journal, "brain", brain_run)
             if se.event.kind == "brain_decision"}

    opens: dict[str, StoredEvent] = {}
    closes: dict[str, list[StoredEvent]] = {}
    skipped: list[tuple[int, str, str]] = []          # (seq, position_id, code)
    for se in events:
        kind = se.event.kind
        if kind not in ("paper_open", "paper_close"):
            continue
        pid = se.event.payload.get("position_id") if isinstance(se.event.payload, Mapping) else None
        if not isinstance(pid, str) or not pid or len(pid) > 128:
            skipped.append((se.seq, "?", "corrupt_" + kind.split("_")[1]))
            continue
        if kind == "paper_open":
            if pid in opens:
                skipped.append((se.seq, pid, "duplicate_open"))
            else:
                opens[pid] = se
        else:
            closes.setdefault(pid, []).append(se)

    outcomes: list[tuple[int, TradeOutcome]] = []
    open_ids: list[str] = []
    for pid, op in opens.items():
        cl = closes.get(pid)
        if not cl:
            open_ids.append(pid)
            continue
        if len(cl) > 1:
            skipped.append((cl[1].seq, pid, "multiple_closes"))
            continue
        try:
            outcome = _build(pid, portfolio_id, run_id, _parse_open(op, pid),
                             _parse_close(cl[0], pid), brain)
        except _Bad as bad:
            skipped.append((cl[0].seq, pid, str(bad.args[0])))
        else:
            outcomes.append((cl[0].seq, outcome))
    for pid, cl in closes.items():
        if pid not in opens:
            skipped.append((cl[0].seq, pid, "close_without_open"))

    outcomes.sort(key=lambda t: t[0])
    skipped.sort(key=lambda t: (t[0], t[1], t[2]))
    return OutcomeReport(
        portfolio_id=portfolio_id, run_id=run_id, brain_run_id=brain_run,
        outcomes=tuple(o for _, o in outcomes),
        open_position_ids=tuple(open_ids),
        skipped=tuple(SkippedRecord(pid, code) for _, pid, code in skipped))
