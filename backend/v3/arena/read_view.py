"""Authenticated Arena dashboard input: read three independent PAPER journals.

Does not create directories, initialize SQLite, write a heartbeat, fetch marks,
contact OpenRouter or place/close orders. If there is no valid run manifest and
journal, all performance values remain unknown (never fabricate 2,000 equity).

The authenticated HTTP route lives in arena/read_router.py, not in the active
V3 routing module. Explicit future release approval is needed to mount it.
"""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import re
import sqlite3
import stat

from backend.v3.arena.t0 import trial_start
from backend.v3.arena.trial_plan import WalletPlan
from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.outcomes import OutcomeError, extract_outcomes

MAX_MANIFEST_BYTES = 8192
MAX_HEARTBEAT_BYTES = 8192
HEARTBEAT_STALE_MS = 180_000
SYMBOL = re.compile(r"^[A-Z0-9]{3,24}$")
STATES = ("running", "paused", "halted", "stale", "not_started")


def _blocked(p: Path, max_len: int) -> dict | None:
    """Load only small non-secret metadata and reject symlinks."""
    if p.is_symlink() or not p.is_file():
        return None
    try:
        if p.stat().st_size > max_len:
            return None
        with p.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
        return value if type(value) is dict else None
    except (OSError, ValueError, UnicodeError):
        return None


def _safe_scope(plan: WalletPlan) -> bool:
    if type(plan) is not WalletPlan or plan.provider not in ("deepseek", "qwen", "minimax"):
        return False
    if (plan.folder.name != plan.run_id or plan.folder.parent.name != plan.provider
            or plan.journal != plan.folder / "journal.db"
            or plan.heartbeat != plan.folder / "heartbeat.json"
            or not plan.folder.is_absolute()
            or plan.capital_usdt != Decimal("2000")
            or plan.internal_portfolio_id != "brain"):
        return False
    # All path components from the trial root down must be real directories,
    # not aliases pointing into Falco/Toro or the historical Brain.
    trial_root = plan.folder.parent.parent
    if trial_root.is_symlink() or plan.folder.parent.is_symlink() or plan.folder.is_symlink():
        return False
    if any(".." == part for part in plan.folder.parts):
        return False
    for path in (trial_root, plan.folder.parent, plan.folder):
        if not path.is_dir():
            return False
    return True


def _empty(plan: WalletPlan, reason: str) -> dict:
    return {
        "portfolio_id": plan.provider,
        "model": plan.model,
        "run_id": plan.run_id,
        "source": "arena_independent_journal_v1",
        "mode": "paper",
        "state": "not_started",
        "initial_capital": 2000,
        "trial_start_ms": None,
        "trial_comparable": False,
        "data_status": reason,
        "equity": None,
        "settled_equity": None,
        "equity_basis": "unavailable",
        "realized_pnl": None,
        "unrealized_pnl": None,
        "day_pnl": None,
        "margin_in_use": None,
        "total_closed": None,
        "win_rate": None,
        "open_count": None,
        "open_positions": None,
        "closed_trades": None,
        "last_decision": None,
        "decision_count": None,
        "no_trade_count": None,
        "manual_close_count": None,
        "verified_outcome_count": None,
        "learning_status": "NOT_CONFIGURED",
        "updated_ms": None,
    }


def _trial_manifest(plan: WalletPlan, now_ms: int) -> int | None:
    raw = _blocked(plan.folder / "arena_manifest.json", MAX_MANIFEST_BYTES)
    if raw is None:
        return None
    expected = {
        "schema": "brain_arena_trial_v1",
        "provider": plan.provider,
        "run_id": plan.run_id,
        "initial_capital": "2000",
        "mode": "paper",
        "model": plan.model,
        "experiment": "independent",
    }
    if any(raw.get(key) != value for key, value in expected.items()):
        return None
    started = trial_start(plan.folder, plan.provider, plan.run_id, raw.get("trial_start_ms"))
    if type(started) is not int or not 0 < started <= now_ms:
        return None
    return started


def _state(plan: WalletPlan, now_ms: int) -> str:
    hb = _blocked(plan.heartbeat, MAX_HEARTBEAT_BYTES)
    if not hb:
        return "stale"
    if (hb.get("run_id") != plan.run_id or type(hb.get("ts_ms")) is not int
            or type(hb.get("cycle")) is not int or hb["cycle"] < 0
            or hb["ts_ms"] <= 0 or hb["ts_ms"] > now_ms + 60_000
            or hb.get("state") not in ("running", "paused", "halted")):
        return "stale"
    if hb["state"] == "halted":
        return "halted"
    if hb["state"] == "paused" or (plan.folder / "pause.flag").is_file():
        return "paused"
    return "stale" if now_ms - hb["ts_ms"] > HEARTBEAT_STALE_MS else "running"


def _open_positions(summary) -> list[dict] | None:
    positions = []
    for pos in summary.open_positions:
        if (not SYMBOL.fullmatch(pos.symbol) or pos.side not in (-1, 1)
                or pos.fill_price <= 0 or pos.quantity <= 0
                or pos.margin_used <= 0 or pos.stop_price <= 0
                or pos.leverage < 1):
            return None
        positions.append({
            "position_id": pos.position_id, "symbol": pos.symbol,
            "side": pos.side, "entry": str(pos.fill_price),
            "stop": str(pos.stop_price), "quantity": str(pos.quantity),
            "margin": str(pos.margin_used), "leverage": pos.leverage,
            "opened_at_ms": pos.opened_at_ms,
            "unrealized_pnl": None,  # No verified latest mark.
            "take_profit": None,  # Not stored in PortfolioSummary.
        })
    return positions


def read_wallet(plan: WalletPlan, now_ms: int) -> dict:
    """Fail closed; no cross-portfolio or cross-run data substitution."""
    unknown = _empty(plan, "NOT_CONFIGURED")
    if type(now_ms) is not int or now_ms <= 0 or not _safe_scope(plan):
        unknown["data_status"] = "INVALID_SCOPE"
        return unknown
    t0 = _trial_manifest(plan, now_ms)
    if t0 is None:
        # Run preparata in pausa ma gara non assegnata: stato autentico "non avviato", nessun numero mostrato.
        raw = _blocked(plan.folder / "arena_manifest.json", MAX_MANIFEST_BYTES)
        if (raw and raw.get("provider") == plan.provider and raw.get("run_id") == plan.run_id
                and raw.get("trial_start_ms") is None and (plan.folder / "pause.flag").is_file()):
            unknown["data_status"] = "PREPARED_AWAITING_T0"
        return unknown
    if plan.journal.is_symlink() or not plan.journal.is_file():
        unknown["data_status"] = "JOURNAL_NOT_AVAILABLE"
        return unknown
    try:
        journal = EventJournal(plan.journal)
        events = journal.list_run("brain", plan.run_id)
        # A separate journal must not contain events from another provider/run.
        chain_count, _ = journal.verify_chain()
        if chain_count != len(events):
            raise ValueError("foreign_events_in_isolated_db")
        if not events and _state(plan, now_ms) == "stale":
            raise ValueError("uninitialized_inactive_wallet")
        summary = build_summary(journal, "brain", plan.run_id)
        outcome_report = extract_outcomes(journal, "brain", plan.run_id)
        if outcome_report.skipped or len(outcome_report.outcomes) != len(summary.closed_trades):
            raise ValueError("outcomes_incomplete")
        open_ids = {p.position_id for p in summary.open_positions}
        if open_ids != set(outcome_report.open_position_ids):
            raise ValueError("open_position_mismatch")
        # The entire journal must belong to the provider. A copied DeepSeek
        # journal under Qwen's folder must not become fake Qwen performance.
        for stored in events:
            ev = stored.event
            if ev.kind == "brain_decision":
                if ev.payload.get("originating_ai") != plan.provider:
                    raise ValueError("wrong_decision_provider")
            if ev.kind == "paper_open":
                if ev.payload.get("originating_ai") != plan.provider:
                    raise ValueError("wrong_originating_ai")
            if ev.kind == "paper_close":
                if ev.payload.get("originating_ai", plan.provider) != plan.provider:
                    raise ValueError("wrong_originating_ai")
        if any(o.originating_ai != plan.provider or o.link_status != "linked"
               for o in outcome_report.outcomes):
            raise ValueError("unverified_provenance")
        positions = _open_positions(summary)
        if positions is None:
            raise ValueError("invalid_positions")
        realized = sum((o.realized_pnl for o in outcome_report.outcomes), Decimal("0"))
        if realized != summary.realized_pnl or not realized.is_finite():
            raise ValueError("pnl_not_reconciled")
        capital = plan.capital_usdt
        settled = capital + realized
        if not settled.is_finite():
            raise ValueError("invalid_equity")
        closes = sorted(outcome_report.outcomes, key=lambda o: o.closed_at_ms, reverse=True)
        day_start = now_ms // 86_400_000 * 86_400_000
        day_pnl = sum((o.realized_pnl for o in closes
                       if day_start <= o.closed_at_ms <= now_ms), Decimal("0"))
        last = next((se.event for se in reversed(events)
                     if se.event.kind == "brain_decision"), None)
        last_decision = None if last is None else {
            "symbol": last.payload.get("symbol") if
                type(last.payload.get("symbol")) is str and
                SYMBOL.fullmatch(last.payload["symbol"]) else None,
            "status": last.payload.get("status") if
                last.payload.get("status") in ("APPROVED", "REJECTED", "RISK_REJECTED", "DRAFT") else None,
            "kind": last.payload.get("kind") if
                last.payload.get("kind") in ("OPEN", "NO_TRADE") else None,
        }
        win_count = sum(1 for o in closes if o.realized_pnl > 0)
        decisions = [stored.event for stored in events if stored.event.kind == "brain_decision"]
        no_trades = sum(ev.payload.get("kind") == "NO_TRADE" for ev in decisions)
        manual_exits = sum(o.is_manual for o in closes)
        total = len(closes)
        result = _empty(plan, "VERIFIED")
        result.update({
            "state": _state(plan, now_ms),
            "trial_start_ms": t0,
            "trial_comparable": True,
            "equity": str(settled) if not positions else None,
            "settled_equity": str(settled),
            "equity_basis": "settled" if not positions else "open_unmarked",
            "realized_pnl": str(realized),
            "day_pnl": str(day_pnl),
            "margin_in_use": str(summary.margin_in_use),
            "total_closed": total,
            "win_rate": str(Decimal(win_count) * 100 / total) if total else None,
            "open_count": len(positions),
            "open_positions": positions[:100],
            "closed_trades": [{
                "position_id": o.position_id, "symbol": o.symbol,
                "side": o.side, "leverage": o.leverage,
                "entry": str(o.entry_price), "exit": str(o.exit_price),
                "margin": str(o.margin_used), "fees": str(o.fees),
                "realized_pnl": str(o.realized_pnl),
                "exit_reason": o.exit_reason, "closed_at_ms": o.closed_at_ms,
            } for o in closes[:100]],
            "last_decision": last_decision,
            "decision_count": len(decisions),
            "no_trade_count": no_trades,
            "manual_close_count": manual_exits,
            "verified_outcome_count": len(outcome_report.linked_outcomes),
            "learning_status": "JOURNAL_EVIDENCE_ONLY_NOT_MODEL_TRAINING",
            "updated_ms": summary.last_event_ms,
        })
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError,
            ArithmeticError, sqlite3.Error, OutcomeError):
        unknown["data_status"] = "UNVERIFIED_JOURNAL"
        return unknown


def read_arena(
    plans: tuple[WalletPlan, ...], now_ms: int,
) -> dict:
    """Same contract for a future session-gated GET /api/v3/arena."""
    if type(plans) is not tuple or len(plans) != 3 or (
        any(type(p) is not WalletPlan for p in plans) or
        tuple(p.provider for p in plans) != ("deepseek", "qwen", "minimax")
    ) or len({p.journal for p in plans}) != 3:
        raise ValueError("invalid_arena_plan")
    return {
        "schema": "brain_arena_readonly_v1",
        "mode": "paper",
        "generated_at_ms": now_ms,
        "portfolios": {p.provider: read_wallet(p, now_ms) for p in plans},
    }
