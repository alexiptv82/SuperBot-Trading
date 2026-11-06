"""Explicit, one-time creation of a NEW Brain V3 PAPER run.

Does not migrate, reset, or alter previous portfolios. A bootstrap is only
allowed in a directory that does NOT already exist. No services are started,
no orders are opened, and the risk mandate remains unapproved.

An operator must back up prior data and separately approve the final capital,
run identity, and risk mandate before issuing the command on a real machine.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import stat
import sys
import time

from backend.v3.budget import BudgetLedger
from backend.v3.brain_f2.engine import _policy_hash
from backend.v3.events import Event, EventJournal
from backend.v3.runner.config import default_config_path, load_runner_config
from backend.v3.runner.wiring import mandate_template

_RUN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")


class BootstrapRefused(ValueError):
    """Non-secret reason for refusing the new run."""


def initialize_new_paper_run(*, data_dir: Path, run_id: str, config_bytes: bytes,
                             desk_mode: str, confirmed: bool, expected_initial_equity: str,
                             now_ms: int | None = None) -> dict:
    """Create ONLY a fresh directory; never edit any existing run or history.

    Returns a receipt without activating the bot. A partially failed creation
    intentionally stays in place, forcing operator inspection rather than a
    possibly unsafe automatic retry or cleanup.
    """
    if type(desk_mode) is not str or desk_mode != 'paper':
        raise BootstrapRefused('paper_mode_required')
    if confirmed is not True:
        raise BootstrapRefused('explicit_bootstrap_confirmation_required')
    if (not isinstance(data_dir, Path) or not data_dir.is_absolute()
            or data_dir.is_symlink() or type(run_id) is not str
            or _RUN_RE.fullmatch(run_id) is None
            or type(config_bytes) is not bytes):
        raise BootstrapRefused('invalid_bootstrap_scope')
    try:
        config = load_runner_config(config_bytes)
    except (OSError, ValueError):
        raise BootstrapRefused('invalid_bootstrap_config') from None
    if type(expected_initial_equity) is not str or str(config.initial_equity) != expected_initial_equity:
        raise BootstrapRefused('capital_confirmation_mismatch')
    stamp = int(time.time()*1000) if now_ms is None else now_ms
    if type(stamp) is not int or stamp <= 0:
        raise BootstrapRefused('invalid_bootstrap_time')
    try:
        root_parent = data_dir.parent.resolve(strict=True)
        if not root_parent.is_dir() or data_dir.exists() or data_dir.is_symlink():
            raise BootstrapRefused('destination_must_be_new')
        parent_mode = root_parent.stat().st_mode
        # A world-writable parent must be sticky to avoid replacing the run
        # directory after validation (e.g. conventional /tmp in tests).
        if parent_mode & stat.S_IWOTH and not parent_mode & stat.S_ISVTX:
            raise BootstrapRefused('unsafe_parent_directory')
        data_dir.mkdir(mode=0o700)
    except BootstrapRefused:
        raise
    except FileExistsError:
        raise BootstrapRefused('destination_must_be_new') from None
    except (OSError, ValueError):
        raise BootstrapRefused('bootstrap_directory_unavailable') from None
    marker = data_dir / '.bootstrap-incomplete'
    try:
        marker.write_text('incomplete\n', encoding='ascii')
        marker.chmod(0o600)
        journal = EventJournal(data_dir/'journal.db')
        journal.init_schema()
        receipt_id = 'paper-run-initialized:'+run_id
        journal.append(Event(
            event_id=receipt_id, portfolio_id='brain', run_id=run_id,
            kind='paper_run_initialized', occurred_at_ms=stamp,
            source='operator_bootstrap', payload={
                'initial_equity_usdt': str(config.initial_equity),
                'policy_hash': _policy_hash(config.risk_policy),
                'paper_only': True,
                'approved_to_trade': False,
            }))
        ledger = BudgetLedger(str(data_dir/'budget.db'))
        try:
            ledger.all_spend('deepseek')
        finally:
            ledger.close()
        mandate = mandate_template(config.risk_policy, run_id)
        assert mandate['approved'] is False
        (data_dir/'mandate.json').write_text(json.dumps(mandate, sort_keys=True)+'\n', encoding='utf-8')
        (data_dir/'mandate.json').chmod(0o600)
        (data_dir/'pause.flag').write_text('bootstrap paused\n', encoding='ascii')
        (data_dir/'pause.flag').chmod(0o600)
        count, head = journal.verify_chain()
        if count != 1:
            raise BootstrapRefused('bootstrap_invariant_failed')
        receipt = {
            'schema_version': 1, 'portfolio_id': 'brain', 'run_id': run_id,
            'initial_equity_usdt': str(config.initial_equity),
            'policy_hash': _policy_hash(config.risk_policy),
            'journal_count': count, 'journal_head': head,
            'created_at_utc': datetime.fromtimestamp(stamp/1000,timezone.utc).isoformat(),
            'status': 'PAUSED_UNAPPROVED',
        }
        manifest = data_dir/'bootstrap_receipt.json'
        with manifest.open('x',encoding='utf-8') as f:
            json.dump(receipt, f,sort_keys=True,indent=2)
            f.write('\n')
        manifest.chmod(0o600)
        marker.unlink()
        return receipt
    except BootstrapRefused:
        raise
    except Exception:
        raise BootstrapRefused('bootstrap_incomplete_review_required') from None


def main(argv: list[str] | None = None, *, env: dict | None = None) -> int:
    ap=argparse.ArgumentParser(description='Create a NEW PAUSED Brain V3 PAPER run; no restart')
    ap.add_argument('--data-dir', required=True)
    ap.add_argument('--run-id', required=True)
    ap.add_argument('--config', default=str(default_config_path()))
    ap.add_argument('--create-paper', action='store_true')
    ap.add_argument('--expected-initial-equity', required=True, help='USDT exactly as specified in the config')
    ns=ap.parse_args(argv)
    environ=os.environ if env is None else env
    try:
        result=initialize_new_paper_run(
            data_dir=Path(ns.data_dir),run_id=ns.run_id,
            config_bytes=Path(ns.config).read_bytes(),
            desk_mode=environ.get('DESK_MODE', ''),confirmed=ns.create_paper,
            expected_initial_equity=ns.expected_initial_equity)
    except (BootstrapRefused,OSError) as e:
        print(str(e) if isinstance(e,BootstrapRefused) else 'config_unavailable',file=sys.stderr)
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())