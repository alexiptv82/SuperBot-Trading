"""F6 — Dashboard unificata (read-only, offline).

Legge eventi da EventJournal e produce PortfolioSummary per ogni
portafoglio (hawk/bull/brain). Nessuna API esterna, nessuna scrittura.

Flusso:
    journal = EventJournal(path)
    summaries = build_all_summaries(journal, run_id)
    for s in summaries:
        print(format_summary(s))

Tipi di evento riconosciuti:
    paper_open   — apertura posizione PAPER
    paper_close  — chiusura posizione PAPER (payload: realized_pnl)
    brain_step   — decisione del cervello (kind in payload: NO_TRADE/OPEN/APPROVED)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from backend.v3.events import EventJournal, StoredEvent


# ---------------------------------------------------------------------------
# Dataclasses output (frozen — solo lettura)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OpenPosition:
    position_id: str
    symbol: str
    side: int           # +1 long / -1 short
    fill_price: Decimal
    quantity: Decimal
    margin_used: Decimal
    leverage: int
    stop_price: Decimal
    opened_at_ms: int


@dataclass(frozen=True)
class ClosedTrade:
    position_id: str
    symbol: str
    realized_pnl: Decimal
    closed_at_ms: int


@dataclass(frozen=True)
class PortfolioSummary:
    portfolio_id: str
    run_id: str
    total_events: int
    open_positions: tuple[OpenPosition, ...]
    closed_trades: tuple[ClosedTrade, ...]
    brain_steps: int            # numero totale di decisioni Brain
    brain_approvals: int        # decisioni APPROVED
    realized_pnl: Decimal       # somma PnL dai paper_close
    margin_in_use: Decimal      # somma margin_used posizioni aperte
    last_event_ms: int | None   # timestamp ultimo evento (o None se vuoto)


# ---------------------------------------------------------------------------
# Helpers interni
# ---------------------------------------------------------------------------

def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Converte un valore di payload in Decimal; usa default se non convertibile."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _int_field(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _str_field(value: Any, default: str = "") -> str:
    return str(value) if value is not None else default


# ---------------------------------------------------------------------------
# Builder principale
# ---------------------------------------------------------------------------

def build_summary(
    journal: EventJournal,
    portfolio_id: str,
    run_id: str,
) -> PortfolioSummary:
    """Legge tutti gli eventi del run e restituisce un PortfolioSummary.

    Fail-safe: eventi malformati vengono ignorati (il journal è già
    validato in append, ma i payload custom potrebbero variare).
    """
    events: list[StoredEvent] = journal.list_run(portfolio_id, run_id)

    open_map: dict[str, OpenPosition] = {}      # position_id → OpenPosition
    closed: list[ClosedTrade] = []
    brain_steps = 0
    brain_approvals = 0
    realized_pnl = Decimal("0")
    last_ms: int | None = None

    for se in events:
        ev = se.event
        ts = ev.occurred_at_ms
        if last_ms is None or ts > last_ms:
            last_ms = ts

        p: Mapping = ev.payload if isinstance(ev.payload, Mapping) else {}

        if ev.kind == "paper_open":
            pid = _str_field(p.get("position_id"))
            if not pid:
                continue
            pos = OpenPosition(
                position_id=pid,
                symbol=_str_field(p.get("symbol")),
                side=_int_field(p.get("side"), 1),
                fill_price=_decimal(p.get("fill_price")),
                quantity=_decimal(p.get("quantity")),
                margin_used=_decimal(p.get("margin_used")),
                leverage=_int_field(p.get("leverage"), 1),
                stop_price=_decimal(p.get("stop_price")),
                opened_at_ms=ts,
            )
            open_map[pid] = pos

        elif ev.kind == "paper_close":
            pid = _str_field(p.get("position_id"))
            pnl = _decimal(p.get("realized_pnl"))
            realized_pnl += pnl
            if pid in open_map:
                del open_map[pid]
            closed.append(ClosedTrade(
                position_id=pid,
                symbol=_str_field(p.get("symbol")),
                realized_pnl=pnl,
                closed_at_ms=ts,
            ))

        elif ev.kind == "brain_step":
            brain_steps += 1
            decision_kind = _str_field(p.get("kind"))
            decision_status = _str_field(p.get("status"))
            if decision_kind == "OPEN" and decision_status == "APPROVED":
                brain_approvals += 1

    margin_in_use = sum(
        (pos.margin_used for pos in open_map.values()), Decimal("0")
    )

    return PortfolioSummary(
        portfolio_id=portfolio_id,
        run_id=run_id,
        total_events=len(events),
        open_positions=tuple(open_map.values()),
        closed_trades=tuple(closed),
        brain_steps=brain_steps,
        brain_approvals=brain_approvals,
        realized_pnl=realized_pnl,
        margin_in_use=margin_in_use,
        last_event_ms=last_ms,
    )


def build_all_summaries(
    journal: EventJournal,
    run_id: str,
    portfolios: tuple[str, ...] = ("hawk", "bull", "brain"),
) -> list[PortfolioSummary]:
    """Costruisce PortfolioSummary per ogni portafoglio elencato."""
    return [build_summary(journal, pid, run_id) for pid in portfolios]


# ---------------------------------------------------------------------------
# Formatter testuale (per CLI / diario)
# ---------------------------------------------------------------------------

def format_summary(s: PortfolioSummary) -> str:
    """Restituisce una stringa leggibile del summary."""
    lines = [
        f"=== {s.portfolio_id.upper()} | run={s.run_id} ===",
        f"  eventi totali : {s.total_events}",
        f"  posizioni aperte : {len(s.open_positions)}",
        f"  trades chiusi : {len(s.closed_trades)}",
        f"  PnL realizzato : {s.realized_pnl:+.4f} USDT",
        f"  margine in uso : {s.margin_in_use:.4f} USDT",
    ]
    if s.brain_steps > 0:
        lines.append(
            f"  brain steps : {s.brain_steps} ({s.brain_approvals} approvati)"
        )
    if s.last_event_ms is not None:
        lines.append(f"  ultimo evento : {s.last_event_ms} ms")
    for pos in s.open_positions:
        side_str = "LONG" if pos.side == 1 else "SHORT"
        lines.append(
            f"  [OPEN] {pos.symbol} {side_str} x{pos.leverage} "
            f"@ {pos.fill_price} qty={pos.quantity}"
        )
    for t in s.closed_trades:
        lines.append(
            f"  [CLOSED] {t.symbol} pnl={t.realized_pnl:+.4f}"
        )
    return "\n".join(lines)
