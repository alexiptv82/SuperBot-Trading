"""Closed-form PAPER lease tests for OPEN vs actual exit worker CLOSE callbacks."""
from __future__ import annotations

import fcntl
import multiprocessing
import os
from pathlib import Path
import threading
import time

import pytest

from backend.v3.events import Event, EventJournal
from backend.v3.runner.config import load_default_config
from backend.v3.runner.exit_worker import build_exit_worker
from backend.v3.runner.exit_service import exit_service_healthy
from backend.v3.runner.paper_close_fence import PaperCloseFenceBusy, paper_close_fence
from backend.v3.runner.monitor import MonitorReport

RUN='split-fenced'
NOW=1_800_001_200_000


def _existing(folder):
    j=EventJournal(folder/'journal.db');j.init_schema()
    j.append(Event('seed','brain',RUN,'startup',NOW-1000,'test',{}))
    return j


def test_fence_creates_secure_shared_lock(tmp_path):
    with paper_close_fence(tmp_path):
        lock=tmp_path/'.brain-paper-open.lock'
        assert lock.is_file() and lock.stat().st_nlink==1
        assert (lock.stat().st_mode & 0o077)==0
        with open(lock,'rb') as peer:
            with pytest.raises(BlockingIOError):
                fcntl.flock(peer,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with open(tmp_path/'.brain-paper-open.lock','rb') as peer:
        fcntl.flock(peer,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fcntl.flock(peer,fcntl.LOCK_UN)


@pytest.mark.parametrize('scope', [None,True,Path('relative')])
def test_invalid_scope_rejected(scope):
    with pytest.raises(PaperCloseFenceBusy,match='^invalid_paper_close_scope$'):
        with paper_close_fence(scope): pass


def test_symlink_lock_fails_closed_without_touching_target(tmp_path):
    victim=tmp_path/'victim';victim.write_text('safe')
    (tmp_path/'.brain-paper-open.lock').symlink_to(victim)
    with pytest.raises(PaperCloseFenceBusy):
        with paper_close_fence(tmp_path):pass
    assert victim.read_text()=='safe'


def test_insecure_permissions_fail_closed(tmp_path):
    lock=tmp_path/'.brain-paper-open.lock';lock.write_bytes(b'')
    os.chmod(lock,0o666)
    with pytest.raises(PaperCloseFenceBusy,match='^unsafe_paper_close_lease$'):
        with paper_close_fence(tmp_path):pass


def test_hardlinked_lock_fails_closed(tmp_path):
    p=tmp_path/'.brain-paper-open.lock';p.write_text('')
    os.chmod(p,0o600)
    os.link(p,tmp_path/'other')
    with pytest.raises(PaperCloseFenceBusy,match='^unsafe_paper_close_lease$'):
        with paper_close_fence(tmp_path):pass


def test_callback_exception_releases_lock(tmp_path):
    with pytest.raises(ZeroDivisionError):
        with paper_close_fence(tmp_path):
            1/0
    with paper_close_fence(tmp_path):
        pass


def _other_process(path, ready, done, result):
    from backend.v3.runner.paper_close_fence import paper_close_fence
    ready.wait(10)
    try:
        with paper_close_fence(Path(path)):
            result.put('acquired')
    except PaperCloseFenceBusy:
        result.put('busy')
    done.set()


def test_real_two_process_close_cannot_cross_open_critical_section(tmp_path):
    ctx=multiprocessing.get_context('spawn')
    ready=ctx.Event();done=ctx.Event();q=ctx.Queue()
    p=ctx.Process(target=_other_process,args=(str(tmp_path),ready,done,q))
    with paper_close_fence(tmp_path):
        p.start(); ready.set()
        assert not done.wait(0.5)  # CLOSE is waiting while OPEN lock held
    assert done.wait(7)
    p.join(10)
    assert p.exitcode==0 and q.get_nowait()=='acquired'


def test_real_exit_worker_commands_and_monitor_share_open_lock(tmp_path,monkeypatch):
    _existing(tmp_path)
    import backend.v3.runner.exit_worker as worker
    trace=[]
    def commands(**kwargs):
        lock=tmp_path/'.brain-paper-open.lock'
        with open(lock,'rb') as peer:
            try:fcntl.flock(peer,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:trace.append('commands_fenced')
            else:trace.append('commands_unfenced');fcntl.flock(peer,fcntl.LOCK_UN)
        return None
    def monitor(**kwargs):
        lock=tmp_path/'.brain-paper-open.lock'
        with open(lock,'rb') as peer:
            try:fcntl.flock(peer,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:trace.append('monitor_fenced')
            else:trace.append('monitor_unfenced');fcntl.flock(peer,fcntl.LOCK_UN)
        return MonitorReport(0,(),())
    monkeypatch.setattr(worker,'run_manual_close',commands)
    monkeypatch.setattr(worker,'run_exit_monitor',monitor)
    service=build_exit_worker(data_dir=tmp_path,run_id=RUN,config=load_default_config(),get_json=lambda _:[])
    with service:
        assert service.tick(NOW).state=='healthy'
        assert exit_service_healthy(data_dir=tmp_path,run_id=RUN,now_ms=NOW)
    assert trace==['commands_fenced','monitor_fenced']


def test_exit_worker_degrades_when_writer_fence_unavailable(tmp_path,monkeypatch):
    _existing(tmp_path)
    import backend.v3.runner.exit_service as exit_mod
    from contextlib import contextmanager
    @contextmanager
    def fail(_):
        raise PaperCloseFenceBusy('paper_close_writer_busy')
        yield
    monkeypatch.setattr(exit_mod,'paper_close_fence',fail)
    service=build_exit_worker(data_dir=tmp_path,run_id=RUN,config=load_default_config(),get_json=lambda _:[])
    with service:
        r=service.tick(NOW)
        assert r.state=='degraded'
        assert r.last_error == 'writer_fence_unavailable' 
        assert exit_service_healthy(data_dir=tmp_path,run_id=RUN,now_ms=NOW) is False


def test_raw_exit_service_callbacks_also_hold_writer_fence(tmp_path):
    from backend.v3.runner.exit_service import ExitService
    calls=[]
    def assert_fenced(label):
        with open(tmp_path/'.brain-paper-open.lock','rb') as peer:
            with pytest.raises(BlockingIOError):
                fcntl.flock(peer,fcntl.LOCK_EX|fcntl.LOCK_NB)
        calls.append(label)
    s=ExitService(run_id=RUN,data_dir=tmp_path,
                  run_commands=lambda _:assert_fenced('commands'),
                  run_monitor=lambda _:assert_fenced('monitor') or MonitorReport(0,(),()))
    with s:
        assert s.tick(NOW).state=='healthy'
    assert calls==['commands','monitor']
