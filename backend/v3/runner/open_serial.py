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
_OPT_GUARD = frozenset({"max_decision_age_ms", "max_entry_divergence"})


@dataclass(frozen=True)
class OpenCommit:
    """No secret or model text is returned. Receipt exists ONLY after append."""
    allowed: bool
    code: str
    receipt: ExecutionReceipt | None = None


def commit_paper_open(*, journal: EventJournal, data_dir: Path, run_id: str,
                      decision: BrainDecision, clock_ms: Callable[[], int],
                      guard_inputs: Mapping, slippage_bps: int, desk_mode: str) -> OpenCommit:
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
        receipt = execute_paper(decision, portfolio_id="brain", run_id=run_id,
                                journal=journal, slippage_bps=slippage_bps, now_ms=now_ms)
        return OpenCommit(True, "paper_open_committed", receipt)
    except Exception:
        return deny("open_commit_failed")
    finally:
        if locked:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
