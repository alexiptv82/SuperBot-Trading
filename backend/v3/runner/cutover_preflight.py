"""PAPER-only non-destructive preflight for a potential exit-owner handover.

This is NOT a cutover command and NEVER reports that it is safe to deploy.
An external supervisor must separately prove that the legacy AI process is
stopped and cannot reopen positions, and that any required legacy lock was
held for its ENTIRE lifetime. No owner is stopped or started here.
"""
from __future__ import annotations

from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import re
import stat

from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.runner.exit_service import LOCK_FILE
from backend.v3.runner.manual_close import REQUEST_FILE, WORK_FILE

_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")


@dataclass(frozen=True)
class CutoverInspection:
    status: str  # prerequisites_only | blocked
    reason: str
    open_positions: int | None
    lock_observation: str  # owner_active | no_owner_observed | unknown


def _lock_status(folder: Path) -> str:
    """An instantaneous hint, never evidence of future ownership."""
    path=folder / LOCK_FILE
    try:
        fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    except FileNotFoundError:
        return "no_owner_observed"
    except OSError:
        return "unknown"
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            return "unknown"
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return "owner_active"
        except OSError:
            return "unknown"
        else:
            fcntl.flock(fd,fcntl.LOCK_UN)
            return "no_owner_observed"
    finally:
        os.close(fd)


def inspect_paper_cutover(*, journal: EventJournal, data_dir: Path,
                          run_id: str, desk_mode: str) -> CutoverInspection:
    """Read-only check that must pass BEFORE an externally approved cutover.

    'prerequisites_only' means ONLY flat portfolio and no pending manual
    commands at the instant observed. It NEVER authorizes a cutover; callers
    must stop old owner, prove no new opens, and start supervised sidecar.
    """
    deny=lambda code, count=None, lock="unknown":CutoverInspection("blocked",code,count,lock)
    if type(desk_mode) is not str or desk_mode != "paper":
        return deny("paper_mode_required")
    if (type(journal) is not EventJournal or not isinstance(data_dir, Path)
            or not data_dir.is_absolute() or data_dir.is_symlink() or not data_dir.is_dir()
            or type(run_id) is not str or _RUN.fullmatch(run_id) is None):
        return deny("invalid_cutover_scope")
    try:
        root=data_dir.resolve(strict=True)
        journal_path=root / "journal.db"
        if journal.filename.resolve(strict=True)!=journal_path:
            return deny("invalid_cutover_scope")
        if not stat.S_ISREG(journal_path.lstat().st_mode):
            return deny("invalid_cutover_scope")
        journal.verify_chain()
        events=journal.list_run("brain",run_id)
        if not events:
            return deny("run_not_found")
        summary=build_summary(journal,"brain",run_id)
        count=len(summary.open_positions)
        owner=_lock_status(root)
        if count:
            return deny("positions_still_open",count,owner)
        if any(p.exists() or p.is_symlink() for p in (root/REQUEST_FILE,root/WORK_FILE)):
            return deny("manual_close_pending",0,owner)
        if owner=="unknown":
            return deny("owner_unverifiable",0,owner)
        return CutoverInspection("prerequisites_only","external_stop_proof_required",0,owner)
    except Exception:
        return deny("cutover_read_failed")
