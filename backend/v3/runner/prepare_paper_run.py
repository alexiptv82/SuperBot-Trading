"""Explicit, paused-first creation of an isolated Brain V3 PAPER run.

Creates no orders, does not start either worker or touch historical data.
This is NOT an automatic migration, reset, mandate approval or deploy command.
The caller must select a NEW absolute directory below an existing parent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Mapping, Optional

from backend.v3.budget import BudgetLedger
from backend.v3.dashboard import build_summary
from backend.v3.events import Event, EventJournal
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.exit_worker import check_existing_data
from backend.v3.runner.wiring import mandate_template

_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
_RUN_DIR = re.compile(r"brain-v3-[A-Za-z0-9_-]{3,55}\Z")


class RunPreparationError(ValueError):
    """A fixed machine-readable refusal code without paths or secrets."""


def _safe_scope(parent: Path, run_name: str, run_id: str, *, desk_mode: str) -> Path:
    if desk_mode != "paper":
        raise RunPreparationError("paper_only")
    if (not isinstance(parent, Path) or not parent.is_absolute()
            or parent.is_symlink() or not parent.is_dir()
            or not stat.S_ISDIR(parent.lstat().st_mode)
            or type(run_id) is not str or not _RUN_ID.fullmatch(run_id)
            or type(run_name) is not str or not _RUN_DIR.fullmatch(run_name)):
        raise RunPreparationError("invalid_fresh_run_scope")
    # Do not follow symlinks in the final leaf. The parent is a real existing
    # directory; never create anything in a historical portfolio's directory.
    root = parent / run_name
    if root.is_symlink() or root.exists():
        raise RunPreparationError("run_already_exists")
    return root


def prepare_new_paper_run(*, parent: Path, run_name: str, run_id: str,
                          config_bytes: bytes, desk_mode: str,
                          now_ms: int) -> Path:
    """Create a NEW, paused and unapproved Brain run with a verified journal.

    On failure after mkdir, deliberately leave a paused, incomplete directory
    for inspection: it can never pass the final PREPARED marker check. No
    recursive delete and no writes to sibling/historical portfolio directories.
    """
    root = _safe_scope(parent, run_name, run_id, desk_mode=desk_mode)
    if type(now_ms) is not int or now_ms <= 0:
        raise RunPreparationError("invalid_time")
    if type(config_bytes) is not bytes:
        raise RunPreparationError("invalid_config")
    try:
        config = load_runner_config(config_bytes)
    except (ValueError, TypeError):
        raise RunPreparationError("invalid_config") from None

    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        raise RunPreparationError("run_already_exists") from None
    except OSError:
        raise RunPreparationError("cannot_create_run") from None
    # Immediate pause gate: even if a later write fails the new directory is
    # never presented as an unpaused/approved run.
    (root / "pause.flag").write_text("prepared_and_paused\n", encoding="ascii")
    os.chmod(root / "pause.flag", 0o600)
    fingerprint = hashlib.sha256(config_bytes).hexdigest()
    cfg = root / "runner_config.json"
    cfg.write_bytes(config_bytes)
    os.chmod(cfg, 0o600)
    mandate = mandate_template(config.risk_policy, run_id)
    if mandate["approved"] is not False:
        raise RunPreparationError("mandate_must_start_unapproved")
    mfile = root / "mandate.json"
    mfile.write_text(json.dumps(mandate, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.chmod(mfile, 0o600)

    journal = EventJournal(root / "journal.db")
    journal.init_schema()
    ledger = BudgetLedger(str(root / "budget.db"))
    try:
        # BudgetLedger manages an internal SQLite connection and initializes
        # its append-only schema. Close it after provisioning, before any worker.
        ledger._conn.close()
    except Exception:
        raise RunPreparationError("budget_setup_failed") from None
    event = Event(
        event_id="v3-prepared-"+hashlib.sha256(run_id.encode()).hexdigest()[:20],
        portfolio_id="brain", run_id=run_id, kind="run_prepared",
        occurred_at_ms=now_ms, source="rc_setup",
        payload={"paper_only": True, "paused": True, "mandate_approved": False,
                 "initial_equity": str(config.initial_equity),
                 "config_sha256": fingerprint, "schema_version": 1},
    )
    journal.append(event)
    journal.verify_chain()
    check_existing_data(data_dir=root, run_id=run_id)
    summary = build_summary(journal,"brain",run_id)
    if summary.open_positions or summary.closed_trades or summary.brain_steps:
        raise RunPreparationError("new_run_not_empty")
    ready = root / "PREPARED_PAUSED_ONLY.json"
    ready.write_text(json.dumps({
        "run_id":run_id,"portfolio_id":"brain","paper_only":True,
        "paused":True,"mandate_approved":False,"config_sha256":fingerprint,
        "initial_equity":str(config.initial_equity)
    }, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.chmod(ready,0o600)
    return root


def main(argv: Optional[list[str]] = None, *, env: Optional[Mapping[str,str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a NEW paused/unapproved Brain V3 PAPER directory")
    parser.add_argument("--parent", required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--prepare-paper-paused", action="store_true")
    args = parser.parse_args(argv)
    variables = os.environ if env is None else env
    if not args.prepare_paper_paused:
        print("explicit_prepare_required",file=sys.stderr)
        return 2
    if variables.get("DESK_MODE") != "paper":
        print("paper_only",file=sys.stderr)
        return 2
    try:
        config = Path(args.config).read_bytes()
        root = prepare_new_paper_run(
            parent=Path(args.parent),run_name=args.run_name,run_id=args.run_id,
            config_bytes=config,desk_mode="paper",now_ms=int(time.time()*1000))
    except (RunPreparationError,OSError,ValueError) as exc:
        code=str(exc) if isinstance(exc, RunPreparationError) else "setup_failed"
        print(code,file=sys.stderr)
        return 2
    print("RUN_PREPARED_PAUSED="+root.name)
    return 0


if __name__=="__main__":
    sys.exit(main())