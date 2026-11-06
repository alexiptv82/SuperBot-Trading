"""Cutover inspection is read-only and never claims it has stopped old owner."""
from __future__ import annotations

from pathlib import Path

from backend.tests.test_v3_post_ai_guard import _args, NOW, RUN
from backend.v3.executor.paper import execute_paper
from backend.v3.runner.cutover_preflight import inspect_paper_cutover
from backend.v3.runner.legacy_exit_fence import LegacyExitFence


def inspect(j,dir,**k):
    return inspect_paper_cutover(journal=j,data_dir=dir,run_id=RUN,
                                  desk_mode='paper',**k)


def test_empty_run_never_reported_ready(tmp_path):
    from backend.v3.events import EventJournal
    j=EventJournal(tmp_path/'journal.db');j.init_schema()
    assert inspect(j,tmp_path).reason=='run_not_found'


def test_flat_portfolio_still_needs_external_proof(tmp_path):
    j,d,_,_=_args(tmp_path)
    before=j.verify_chain()
    result=inspect(j,tmp_path)
    assert result.status=='prerequisites_only'
    assert result.reason=='external_stop_proof_required'
    assert result.open_positions==0
    assert j.verify_chain()==before
    assert not (tmp_path/'.exit_service.lock').exists()


def test_no_handover_with_open_position(tmp_path):
    j,d,_,_=_args(tmp_path)
    execute_paper(d,portfolio_id='brain',run_id=RUN,journal=j,now_ms=NOW)
    r=inspect(j,tmp_path)
    assert r.status=='blocked' and r.reason=='positions_still_open' and r.open_positions==1


def test_pending_manual_request_blocks_cutover(tmp_path):
    j,d,_,_=_args(tmp_path)
    for name in ('close_request.json','.close_request.work'):
        p=tmp_path/name;p.write_text('{}')
        assert inspect(j,tmp_path).reason=='manual_close_pending'
        p.unlink()


def test_legacy_owner_active_report_is_honest(tmp_path):
    j,d,_,_=_args(tmp_path)
    with LegacyExitFence(run_id=RUN,data_dir=tmp_path):
        r=inspect(j,tmp_path)
        assert r.lock_observation=='owner_active'
        assert r.status=='prerequisites_only'  # NOT authorization for deploy
    assert inspect(j,tmp_path).lock_observation=='no_owner_observed'


def test_invalid_mode_and_scope_fail_closed(tmp_path):
    j,d,_,_=_args(tmp_path)
    assert inspect_paper_cutover(journal=j,data_dir=tmp_path,run_id=RUN,
                                 desk_mode='live').reason=='paper_mode_required'
    assert inspect_paper_cutover(journal=j,data_dir=tmp_path,run_id='../other',
                                 desk_mode='paper').reason=='invalid_cutover_scope'
    assert inspect(j,Path('/tmp')).reason=='invalid_cutover_scope'


def test_bad_journal_chain_denied(tmp_path):
    import sqlite3
    j,d,_,_=_args(tmp_path)
    with sqlite3.connect(j.filename) as c:
        c.execute('DROP TRIGGER v3_no_update')
        c.execute('UPDATE v3_events SET payload_json=?',('{}',))
    assert inspect(j,tmp_path).reason=='cutover_read_failed'
