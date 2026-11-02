"""Read-only accounting checks on frozen legacy PAPER snapshots.

Classic state contains cash, open margin and closed cash-flow records. We
reconcile book equity excluding unpriced unrealized P&L. This is NOT a claim
that reported cash equals current market equity or that funding is realistic.
Brain Free uses another ledger: audit event structure before ledger replay.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from typing import Any

from .legacy_audit import _MAX_STATE, _source, _parse_doc, _number, _net, open_frozen_sqlite
from .legacy_multirun import audit_classic_multirun


@dataclass(frozen=True)
class ClassicBooks:
    portfolio_id: str
    run_id: str
    closed_count: int
    open_count: int
    start_equity: str
    realized_net: str
    open_entry_fees: str
    reported_cash: str
    open_margin: str
    book_equity: str
    expected_book_equity: str
    residual: str
    cash_formula_pass: bool
    multirun_pass: bool
    issues: tuple[str, ...]


def _cash_positions(account: dict):
    positions = account["positions"]
    if not isinstance(positions, dict):
        raise ValueError("invalid_positions")
    margin = Decimal(0)
    fees = Decimal(0)
    ids = set()
    for symbol, p in positions.items():
        if not isinstance(symbol, str) or not isinstance(p, dict):
            raise ValueError("invalid_position")
        if p.get("symbol") != symbol:
            raise ValueError("position_symbol_mismatch")
        ident = p.get("id")
        if type(ident) is not int or ident <= 0 or ident in ids:
            raise ValueError("position_id_duplicate_or_invalid")
        ids.add(ident)
        m = _number(p.get("total_margin", p.get("margin")))
        f = _number(p.get("fee_open"))
        q = _number(p.get("qty"))
        if m < 0 or f < 0 or q <= 0:
            raise ValueError("invalid_margin_fee_qty")
        margin += m
        fees += f
    return margin, fees


def audit_classic_books(directory: str | Path, portfolio_id: str, *,
                        tolerance: Decimal = Decimal("0.01")) -> ClassicBooks:
    """Strict current-run accounting plus full multirun close reconciliation.

    cash + remaining margin == start + sum(closed net) - remaining entry
    fees, modulo rounding. Partially closed trades are included once as
    net cash flows. No mark prices are present in this equality.
    """
    if tolerance <= 0 or tolerance > Decimal("1"):
        raise ValueError("invalid_tolerance")
    run_report = audit_classic_multirun(directory, portfolio_id)
    raw = _parse_doc(_source(Path(directory) / "state_v2.json", _MAX_STATE))
    acc = raw["main"]
    limits = acc.get("limits")
    if not isinstance(limits, dict):
        raise ValueError("missing_limits")
    start = _number(limits.get("start_equity"))
    cash = _number(acc.get("cash"))
    if start <= 0 or cash < 0:
        raise ValueError("invalid_cash_or_start")
    closed = acc["closed"]
    pnl = _net(closed)
    margin, remaining_fee = _cash_positions(acc)
    booked = cash + margin
    expected = start + pnl - remaining_fee
    residual = booked - expected
    issues = list(run_report.issues)
    if abs(residual) > tolerance:
        issues.append("CURRENT_RUN_CASH_RESIDUAL")
    # mark-to-market requires timestamped market prices: do not claim that
    # book value equals fresh equity when positions are open.
    if start != Decimal("1000"):
        issues.append("UNEXPECTED_START_EQUITY_NOT_AN_IMPORT_ERROR")
    return ClassicBooks(
        portfolio_id=portfolio_id,
        run_id=f"legacy-{portfolio_id}-{run_report.current_run}",
        closed_count=len(closed),
        open_count=run_report.open_positions,
        start_equity=str(start), realized_net=str(pnl),
        open_entry_fees=str(remaining_fee), reported_cash=str(cash),
        open_margin=str(margin), book_equity=str(booked),
        expected_book_equity=str(expected), residual=str(residual),
        cash_formula_pass=abs(residual) <= tolerance,
        multirun_pass=run_report.eligible,
        issues=tuple(issues),
    )


@dataclass(frozen=True)
class BrainStructure:
    paper_valid: bool
    sqlite_valid: bool
    total_events: int
    kind_counts: tuple[tuple[str, int], ...]
    relevant_fields: tuple[tuple[str, tuple[str, ...]], ...]
    cash: str
    open_positions: int
    start_equity_status: str
    import_allowed: bool


def audit_brain_structure(db_path: str | Path) -> BrainStructure:
    """Metadata-only inventory. Never include event values or AI inputs."""
    path = Path(db_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("invalid_brain_db")
    with open_frozen_sqlite(path) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("brain_integrity_failed")
        row = db.execute("SELECT body FROM state WHERE id=1").fetchone()
        if row is None:
            raise ValueError("brain_missing_state")
        state = json.loads(row[0])
        if state.get("account_id") != "brain-free-paper" or state.get("mode") != "paper":
            raise ValueError("foreign_or_live_brain")
        cash = _number(state.get("cash"))
        if cash < 0 or not isinstance(state.get("positions"), dict):
            raise ValueError("brain_invalid_account")
        kinds = Counter()
        fields: dict[str, set[str]] = {}
        count = 0
        relevant = {"open", "dca", "partial_trade", "trade_closed",
                    "funding", "funding_charge", "funding_applied",
                    "experiment_started", "cash_adjusted"}
        for kind, body in db.execute("SELECT kind,body FROM events ORDER BY seq"):
            if not isinstance(kind, str):
                raise ValueError("invalid_kind")
            kinds[kind] += 1
            count += 1
            if kind in relevant:
                item = json.loads(body)
                if not isinstance(item, dict):
                    raise ValueError("invalid_brain_event")
                fields.setdefault(kind, set()).update(item.keys())
    return BrainStructure(
        paper_valid=True, sqlite_valid=True, total_events=count,
        kind_counts=tuple(sorted(kinds.items())),
        relevant_fields=tuple(
            (k, tuple(sorted(v))) for k, v in sorted(fields.items())
        ), cash=str(cash), open_positions=len(state["positions"]),
        start_equity_status="historical_config_2000_requires_replay",
        import_allowed=False,
    )
