"""Candidate P0 protocol: *cooperating* single-writer PAPER OPEN, NOT enabled.

It protects the sequence "fresh post-model check -> paper_open journal append"
with a per-run POSIX flock. A second participating worker cannot read the
same risk budget and open concurrently. Existing legacy/non-cooperating
writers ignore this lock; those MUST be stopped or migrated before enabling.

This is deliberately NOT called a SQLite transaction across two connections:
EventJournal.append has its own transaction while flock provides the larger
cooperating-writer critical section. External mandate/market/exit state can
still change between reading and append; only serialized journal writes by
cooperating writers are proven. No real exchange orders are possible.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping
import fcntl
import os
import re
import stat

from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, ProposalStatus
from backend.v3.events import EventJournal
from backend.v3.executor.paper import ExecutionReceipt, execute_paper
from backend.v3.runner.post_ai_guard import OpenGuardResult, recheck_paper_open
from backend.v3.runner.exit_service import exit_service_healthy

_OPEN_LOCK = ".brain-paper-open.lock"
_RUN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
_REQ_GUARD = frozenset({
    "initial_equity", "risk_policy", "exit_healthy", "mandate_problem",
    "budget_problem", "daily_loss_halted", "paused", "market_rules",
    "market_price", "market_fresh",
})
_OPT_GUARD = frozenset({"max_decision_age_ms", "max_entry_divergence", "equity_reserve"})


@dataclass(frozen=True)
class OpenCommit:
    """No secret or model text is returned. Receipt exists ONLY after append."""
    allowed: bool
    code: str
    receipt: ExecutionReceipt | None = None


def commit_paper_open(*, journal: EventJournal, data_dir: Path, run_id: str,
                      decision: BrainDecision, clock_ms: Callable[[], int],
                      guard_inputs: Mapping, slippage_bps: int, desk_mode: str,
                      partial=None, strategy: dict | None = None) -> OpenCommit:
    """Serialize *cooperating* PAPER OPEN writers, then recheck under lease.

    Safety precedence: scope/mode, lease, decision replay, official risk veto,
    official execute_paper. No callbacks are permitted between validation
    and append; no analytics or free-form model text in this module.
    """
    deny = lambda code: OpenCommit(False, code)
    if desk_mode != "paper" or type(desk_mode) is not str:
        return deny("paper_mode_required")
    if (type(journal) is not EventJournal or not isinstance(data_dir, Path)
            or not data_dir.is_absolute() or data_dir.is_symlink() or not data_dir.is_dir()
            or type(run_id) is not str or _RUN_RE.fullmatch(run_id) is None
            or not callable(clock_ms)
            or type(slippage_bps) is not int or not 0 <= slippage_bps <= 500
            or type(guard_inputs) is not dict or not _REQ_GUARD <= set(guard_inputs)
            or bool(set(guard_inputs) - _REQ_GUARD - _OPT_GUARD)):
        return deny("open_scope_invalid")
    if (type(decision) is not BrainDecision or decision.kind != DecisionKind.OPEN
            or decision.status != ProposalStatus.APPROVED or decision.proposal is None
            or type(decision.journal_event_id) is not str or not decision.journal_event_id):
        return deny("decision_not_executable")
    try:
        # Resolve exactly the pre-existing journal in the configured PAPER directory.
        root = data_dir.resolve(strict=True)
        target = root / "journal.db"
        if journal.filename.resolve(strict=True) != target:
            return deny("open_scope_invalid")
        st = target.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            return deny("open_scope_invalid")
        flags = os.O_RDWR | os.O_CREAT | getattr(os,"O_NOFOLLOW",0) | getattr(os,"O_CLOEXEC",0)
        fd = os.open(root / _OPEN_LOCK, flags, 0o600)
    except (OSError, ValueError):
        return deny("open_scope_invalid")
    locked = False
    try:
        st = os.fstat(fd)
        # A replaced/symlink/hardlinked lock file cannot prove exclusion.
        lockst = (root / _OPEN_LOCK).lstat()
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or (st.st_mode & 0o077) != 0
                or (st.st_dev, st.st_ino) != (lockst.st_dev, lockst.st_ino)):
            return deny("open_lease_invalid")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except (BlockingIOError, OSError):
            return deny("open_lease_busy")
        # Avoid reusing an already executed decision even after it was closed.
        journal.verify_chain()
        existing = journal.list_run("brain",run_id)
        if any(e.event.kind == "paper_open" and e.event.payload.get("decision_event_id")
               == decision.journal_event_id for e in existing):
            return deny("decision_already_executed")
        now_ms = clock_ms()
        if type(now_ms) is not int or now_ms <= 0:
            return deny("open_clock_invalid")
        res = recheck_paper_open(decision=decision, journal=journal, run_id=run_id,
                                 now_ms=now_ms, **dict(guard_inputs))
        if type(res) is not OpenGuardResult or res.allowed is not True:
            return deny(res.code if type(res) is OpenGuardResult else "guard_invalid_result")
        # The real on-disk lease/heartbeat is MANDATORY, regardless of injected
        # callbacks. A test-only lambda returning True must not authorize OPEN.
        if exit_service_healthy(data_dir=root, run_id=run_id, now_ms=now_ms) is not True:
            return deny("exit_service_unhealthy")
        # Guard and append protected by the SAME cooperating-writer lock.
        legs = None
        if partial is not None:
            # Brain unico: due quote (tp1 + runner) se entrambe rispettano passo e nozionale minimo della borsa
            from backend.v3.unico import split_legs
            rules = guard_inputs["market_rules"](decision.proposal.symbol)
            legs = split_legs(decision.risk_quote.quantity, step=Decimal(str(rules["quantity_step"])),
                              price=decision.proposal.entry_price,
                              minimum_notional=Decimal(str(rules["minimum_notional"])), partial=partial)
        receipt = execute_paper(decision, portfolio_id="brain", run_id=run_id,
                                journal=journal, slippage_bps=slippage_bps, now_ms=now_ms, legs=legs,
                                strategy=strategy)
        return OpenCommit(True, "paper_open_committed", receipt)
    except Exception:
        return deny("open_commit_failed")
    finally:
        if locked:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def commit_paper_add(*, journal: EventJournal, data_dir: Path, run_id: str, position_id: str,
                     clock_ms: Callable[[], int], guard_inputs: Mapping, desk_mode: str,
                     decision_ref: str = "") -> OpenCommit:
    """Secondo ingresso della posizione unica (Brain unico, 24/11), con lo STESSO blocco e gli stessi controlli di
    un'apertura: modalita' PAPER, blocco esclusivo, catena del journal, servizio delle uscite sano, pausa, mandato,
    budget, perdita giornaliera, prezzo fresco. Dimensione da ``paper_scale.add_quantity`` sui limiti approvati;
    prezzo da ``paper_scale.add_price_ok``. Nessun allargamento dello stop, nessun aumento del rischio per trade."""
    from backend.v3.dashboard import build_summary
    from backend.v3.executor.paper_scale import add_paper, add_price_ok, add_quantity, position_state
    from backend.v3.runner.cycle import snapshot_from_summary
    deny = lambda code: OpenCommit(False, code)          # noqa: E731
    if desk_mode != "paper" or type(desk_mode) is not str:
        return deny("paper_mode_required")
    if (type(journal) is not EventJournal or not isinstance(data_dir, Path) or not data_dir.is_absolute()
            or not data_dir.is_dir() or type(run_id) is not str or _RUN_RE.fullmatch(run_id) is None
            or not callable(clock_ms) or type(guard_inputs) is not dict or not _REQ_GUARD <= set(guard_inputs)):
        return deny("add_scope_invalid")
    g = guard_inputs
    try:
        root = data_dir.resolve(strict=True)
        if journal.filename.resolve(strict=True) != root / "journal.db":
            return deny("add_scope_invalid")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(root / _OPEN_LOCK, flags, 0o600)
    except (OSError, ValueError):
        return deny("add_scope_invalid")
    locked = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except (BlockingIOError, OSError):
            return deny("open_lease_busy")
        journal.verify_chain()
        now_ms = clock_ms()
        if type(now_ms) is not int or now_ms <= 0:
            return deny("open_clock_invalid")
        if exit_service_healthy(data_dir=root, run_id=run_id, now_ms=now_ms) is not True or g["exit_healthy"](now_ms) is not True:
            return deny("exit_service_unhealthy")
        if g["paused"]() is not False or g["mandate_problem"]() is not None or g["budget_problem"]() is not None \
                or g["daily_loss_halted"](now_ms) is not False:
            return deny("safety_gate_closed")
        events = [se.event for se in journal.list_run("brain", run_id)]
        st = position_state(events, position_id)
        if st is None or st.closed or st.adds or st.reduces or st.open_event.payload.get("scale_in_reserved") is not True:
            return deny("add_not_allowed")
        if g["market_fresh"](st.symbol, now_ms) is not True:
            return deny("market_unavailable")
        price = g["market_price"](st.symbol, now_ms)
        rules = g["market_rules"](st.symbol)
        initial_risk = abs(Decimal(str(st.open_event.payload["fill_price"])) - st.stop)
        if (type(price) is not Decimal or not price.is_finite() or price <= 0 or not isinstance(rules, Mapping)
                or not add_price_ok(side=st.side, avg_price=st.avg_price, initial_risk=initial_risk, stop=st.stop,
                                    price=price, **_scale_in_rules(st.open_event.payload))):
            return deny("add_price_not_better")
        pol = g["risk_policy"]
        summary = build_summary(journal, "brain", run_id)
        reserve = Decimal("0") if g.get("equity_reserve") is None else g["equity_reserve"](summary, now_ms)
        snap = snapshot_from_summary(summary, g["initial_equity"], pol.estimated_roundtrip_cost_bp, reserve=reserve)
        cost = pol.estimated_roundtrip_cost_bp / Decimal(10000)
        e = snap.equity
        max_margin = min(x for x in (e * pol.max_position_margin_fraction, pol.max_margin) if x is not None)
        q = add_quantity(
            side=st.side, quantity=st.quantity, avg_price=st.avg_price, stop=st.stop, price=price, cost_fraction=cost,
            risk_budget=e * pol.max_loss_fraction, open_risk_room=e * pol.max_open_risk_fraction - snap.existing_open_risk,
            side_risk_room=(e * pol.max_same_side_risk_fraction - snap.side_open_risk.get(st.side, Decimal(0))
                            if pol.max_same_side_risk_fraction is not None else e),
            margin_room=min(max_margin - st.margin, e * pol.max_total_margin_fraction - snap.margin_used,
                            snap.available_cash),
            leverage=st.leverage, step=Decimal(str(rules["quantity_step"])),
            minimum_notional=Decimal(str(rules["minimum_notional"])))
        if q <= 0:
            return deny("add_no_risk_room")
        add_paper(portfolio_id="brain", run_id=run_id, position_id=position_id, fill_price=price, quantity=q,
                  journal=journal, decision_event_id=decision_ref, now_ms=now_ms)
        return OpenCommit(True, "paper_add_committed")
    except Exception:
        return deny("add_commit_failed")
    finally:
        if locked:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _scale_in_rules(open_payload) -> dict:
    """Condizioni del secondo ingresso della versione con cui la posizione e' nata (predefinite senza fotografia)."""
    from backend.v3.entry_policy import of_open_payload
    p = of_open_payload(open_payload)
    return {"min_gap_r": p.scale_in_min_gap_r, "min_stop_room_r": p.scale_in_min_stop_room_r}
