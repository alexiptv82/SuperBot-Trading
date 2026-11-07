"""PAPER sidecar safety; all time, market data and AI are synthetic/local."""
from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Event as SyncEvent, Thread

import pytest
from decimal import Decimal as D

from backend.tests.test_v3_runner_feed_monitor import _hand
from backend.v3.events import EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.features.indicators import Bar
from backend.v3.runner.cycle import CycleReport
from backend.v3.runner.exit_service import (
    BEAT_FILE, LOCK_FILE, ExitService, ExitServiceBusy, exit_service_healthy,
)
from backend.v3.runner.exits import ExitPolicy
from backend.v3.runner.manual_close import ManualCloseReport, run_manual_close
from backend.v3.runner.monitor import MonitorReport, run_exit_monitor
from backend.v3.runner.runner import Runner

NOW = 1_800_001_200_000  # minute-aligned synthetic epoch, no actual clock
RUN = "paper-brain-exit"


@pytest.fixture
def d(tmp_path):
    return tmp_path


def _fake_service(d, *, mon=None, cmd=None):
    return ExitService(run_id=RUN, data_dir=d,
                       run_commands=cmd if cmd is not None else lambda _: None,
                       run_monitor=mon if mon is not None else lambda _: MonitorReport(0, (), ()))


def _healthy(d, now=NOW):
    return exit_service_healthy(data_dir=d, run_id=RUN, now_ms=now)


def _journal(d):
    j = EventJournal(d / "journal.db")
    j.init_schema()
    return j


def _open(j, symbol="BTCUSDT", *, now=NOW - 120_000, entry="100", stop="98"):
    decision = _hand(side=1, entry=entry, stop=stop, symbol=symbol)
    return execute_paper(decision, portfolio_id="brain", run_id=RUN, journal=j, now_ms=now).position_id


def _close_events(j):
    return [ev.event for ev in j.list_run("brain", RUN) if ev.event.kind == "paper_close"]


def test_guard_fail_closed_before_start_and_after_stop(d):
    service = _fake_service(d)
    assert not _healthy(d)
    with service:
        assert service.tick(NOW).state == "healthy"
        assert _healthy(d)
        assert not exit_service_healthy(data_dir=d, run_id="other-run", now_ms=NOW)
        assert not _healthy(d, NOW + 15_001)
        assert not _healthy(d, NOW - 1)
    assert not _healthy(d)  # fresh file cannot outlive worker lease
    assert (d / BEAT_FILE).exists() and (d / LOCK_FILE).exists()


def test_second_instance_refused_even_in_same_process(d):
    first, second = _fake_service(d), _fake_service(d)
    with first:
        with pytest.raises(ExitServiceBusy, match="exit_service_already_running"):
            second.start()
        with pytest.raises(ExitServiceBusy):
            first.start()
        assert first.tick(NOW).state == "healthy"
    with second:
        assert second.tick(NOW + 1000).state == "healthy"
        assert _healthy(d, NOW + 1000)


def test_not_started_tick_rejected(d):
    with pytest.raises(ExitServiceBusy, match="exit_service_not_started"):
        _fake_service(d).tick(NOW)


@pytest.mark.parametrize("bad", [0, -1, True, 3.14, "100", None])
def test_invalid_tick_clock(d, bad):
    with _fake_service(d) as service:
        with pytest.raises(ValueError, match="invalid_now"):
            service.tick(bad)


def test_clock_backwards_cannot_extend_health(d):
    with _fake_service(d) as service:
        service.tick(NOW)
        with pytest.raises(ValueError, match="invalid_now"):
            service.tick(NOW-1)
        assert _healthy(d)


def test_monitor_once_per_minute_and_commands_each_tick(d):
    calls = []
    service = _fake_service(d, mon=lambda t: (calls.append(("monitor", t)) or MonitorReport(0, (), ())),
                            cmd=lambda t: (calls.append(("command", t)) or None))
    with service:
        assert service.tick(NOW).state == "healthy"
        assert service.tick(NOW + 5000).state == "healthy"
        assert service.tick(NOW + 60_000).state == "healthy"
    assert calls == [("command", NOW), ("monitor", NOW),
                     ("command", NOW + 5000), ("command", NOW + 60000), ("monitor", NOW + 60000)]


def test_monitor_exception_degrades_heartbeats_and_still_runs_commands(d):
    calls=[]
    def mon(now):
        calls.append("monitor")
        raise RuntimeError("secret data that must not escape")
    def cmd(now):
        calls.append("commands")
        return None
    with _fake_service(d, mon=mon, cmd=cmd) as svc:
        r=svc.tick(NOW)
        assert r.state == "degraded" and r.last_error == "monitor_failed"
        assert not _healthy(d)
        r=svc.tick(NOW+5000)
        assert r.state == "degraded"
        assert not _healthy(d, NOW+5000)
    assert calls == ["commands", "monitor", "commands"]
    assert "secret" not in (d / BEAT_FILE).read_text()


def test_monitor_report_errors_degrade_until_next_successful_minute(d):
    def monitor(t):
        return MonitorReport(1, (), (("pid", "feed_error"),)) if t == NOW else MonitorReport(1, (), ())
    with _fake_service(d, mon=monitor) as svc:
        assert svc.tick(NOW).state == "degraded"
        assert not _healthy(d)
        assert svc.tick(NOW+5000).state == "degraded"
        assert svc.tick(NOW+60000).state == "healthy"
        assert _healthy(d,NOW+60000)


def test_commands_failure_degrades_even_when_monitor_succeeded(d):
    called=[]
    def cmd(t):
        called.append(t)
        if t == NOW: raise ValueError("untrusted")
        return None
    with _fake_service(d, cmd=cmd) as svc:
        assert svc.tick(NOW).last_error == "commands_failed"
        assert not _healthy(d)
        assert svc.tick(NOW+5000).state == "healthy"
        assert _healthy(d,NOW+5000)
    assert called == [NOW,NOW+5000]


def test_manual_report_failures_failclosed_only_that_tick(d):
    def cmd(t):
        return ManualCloseReport("done", (), (("position", "price_unavailable"),)) if t==NOW else None
    with _fake_service(d, cmd=cmd) as svc:
        assert svc.tick(NOW).state == "degraded"
        assert svc.tick(NOW+5000).state == "healthy"


def test_guard_rejects_invalid_beat_shapes(d):
    with _fake_service(d) as svc:
        svc.tick(NOW)
        good = json.loads((d/BEAT_FILE).read_text())
        variants = [
            {**good,"run_id":"wrong"}, {**good,"state":"halted"},
            {**good,"ts_ms":NOW-20000}, {**good,"last_monitor_ms":NOW-66000},
            {**good,"last_commands_ms":NOW-17000},
            {**good,"state":"healthy","last_error":"monitor_failed"},
            {**good,"schema_version":False}, {**good,"ts_ms":True},
            {**good,"last_monitor_ms":None}, {**good,"last_monitor_ms":NOW+1},
            {**good,"unexpected":"x"}, {"state":"healthy"},
        ]
        for variant in variants:
            (d/BEAT_FILE).write_text(json.dumps(variant))
            assert not _healthy(d), variant
        (d/BEAT_FILE).write_text(json.dumps(good))
        assert _healthy(d)


def test_guard_rejects_corrupt_and_symlink_heartbeat(d):
    with _fake_service(d) as svc:
        svc.tick(NOW)
        path=d/BEAT_FILE
        path.write_text("not-json")
        assert not _healthy(d)
        path.write_bytes(b"x"*2500)
        assert not _healthy(d)
        target=d/"target.json"
        target.write_text("{}")
        path.unlink()
        path.symlink_to(target)
        assert not _healthy(d)


def test_lock_symlink_rejected_without_modifying_victim(d):
    victim=d/"victim";victim.write_text("do-not-touch")
    (d/LOCK_FILE).symlink_to(victim)
    with pytest.raises(ExitServiceBusy, match="exit_service_lease_unavailable"):
        _fake_service(d).start()
    assert victim.read_text()=="do-not-touch"


def test_heartbeat_write_failure_does_not_block_close_checks(d,monkeypatch):
    real=os.replace
    def fail(*a): raise OSError("disk full")
    calls=[]
    with _fake_service(d, cmd=lambda t:calls.append(t) or None) as svc:
        assert svc.tick(NOW).state=="healthy"
        assert _healthy(d)
        monkeypatch.setattr(os,"replace",fail)
        assert svc.tick(NOW+16000).state=="healthy"
        assert not _healthy(d,NOW+16000)
        assert calls==[NOW,NOW+16000]
    monkeypatch.setattr(os,"replace",real)


def test_no_duplicate_close_with_manual_before_monitor(d):
    j=_journal(d)
    pid=_open(j)
    (d/"close_request.json").write_text(json.dumps({"ts_ms":NOW,"position_ids":[pid]}))
    def commands(t):
        return run_manual_close(journal=j,portfolio_id="brain",run_id=RUN,data_dir=d,
                                price_of=lambda s,n:D("100"),fee_bps=6,now_ms=t)
    def monitor(t):
        return run_exit_monitor(journal=j,portfolio_id="brain",run_id=RUN,
                                 fetch_bars=lambda sym, st, end:[Bar(NOW-60000,D("100"),D("101"),D("97"),D("98"),D("100"))],
                                 policy=ExitPolicy(D("2"), 24*3600000, D("0")),
                                 fee_bps=6,now_ms=t)
    with _fake_service(d,cmd=commands,mon=monitor) as svc:
        result=svc.tick(NOW)
        assert result.state=="healthy"
        assert result.manual.closed==(pid,)
        assert result.monitor.closed==()
        assert svc.tick(NOW+5000).manual is None
    events=_close_events(j)
    assert len(events)==1 and events[0].payload["reason"]=="manual"
    assert len(j.list_run("brain",RUN))==2


def test_real_stop_closes_and_never_closes_twice(d):
    j=_journal(d);pid=_open(j)
    bar=Bar(NOW-60000,D("100"),D("100"),D("97"),D("98"),D("100"))
    def mon(t):
        return run_exit_monitor(journal=j,portfolio_id="brain",run_id=RUN,
                                 fetch_bars=lambda sym,start,end:[bar],
                                 policy=ExitPolicy(D("2"),24*3600000,D("0")),
                                 fee_bps=6,now_ms=t)
    with _fake_service(d,mon=mon) as svc:
        assert svc.tick(NOW).monitor.closed==((pid,"stop"),)
        assert svc.tick(NOW+60000).monitor.closed==()
    assert len(_close_events(j))==1
    assert _close_events(j)[0].payload["reason"]=="stop"


def test_analyzer_blocked_but_separate_worker_closes_real_paper_position(d):
    """Barrier proves the independent exit callback advances while AI waits."""
    j=_journal(d);pid=_open(j)
    entered=SyncEvent(); release=SyncEvent(); finished=SyncEvent()
    def slow_ai(now,slot):
        entered.set()
        assert release.wait(2),"test barrier timed out"
        return CycleReport(now,(),(),(),())
    # The real original runner still contains monitor/commands: do NOT put
    # the original handlers there in this experiment (a production cutover
    # needs a reviewed patch to disable them when the sidecar is active).
    runner=Runner(run_id=RUN,data_dir=d,
                  run_monitor=lambda _:MonitorReport(0,(),()),run_cycle=slow_ai,
                  cycle_delay_ms=0)
    def do_ai():
        try: runner.tick(NOW)
        finally: finished.set()
    thread=Thread(target=do_ai)
    thread.start()
    try:
        assert entered.wait(1),"fake AI did not start"
        assert not finished.is_set()
        bar=Bar(NOW-60000,D("100"),D("100"),D("97"),D("98"),D("100"))
        def mon(t):
            return run_exit_monitor(journal=j,portfolio_id="brain",run_id=RUN,
                                     fetch_bars=lambda sym, st,end:[bar],
                                     policy=ExitPolicy(D("2"),24*3600000,D("0")),fee_bps=6,now_ms=t)
        with _fake_service(d,mon=mon) as svc:
            r=svc.tick(NOW+5000)
            assert r.monitor.closed==((pid,"stop"),)
            assert not finished.is_set(),"AI should still be blocked when stop closes"
            assert _healthy(d,NOW+5000)
            assert len(_close_events(j))==1
    finally:
        release.set()
        thread.join(2)
    assert finished.is_set() and len(_close_events(j))==1


def test_manual_button_processed_during_analyzer_block(d):
    j=_journal(d);pid=_open(j)
    entered=SyncEvent(); release=SyncEvent(); finished=SyncEvent()
    def slow(now,slot):
        entered.set();assert release.wait(2)
        return CycleReport(now,(),(),(),())
    runner=Runner(run_id=RUN,data_dir=d,
                  run_monitor=lambda _:MonitorReport(0,(),()),run_cycle=slow,cycle_delay_ms=0)
    thread=Thread(target=lambda:(runner.tick(NOW),finished.set()),daemon=True)
    thread.start()
    try:
        assert entered.wait(1)
        (d/"close_request.json").write_text(json.dumps({"ts_ms":NOW,"all":True}))
        def commands(t):
            return run_manual_close(journal=j,portfolio_id="brain",run_id=RUN,data_dir=d,
                                    price_of=lambda *_:D("100"),fee_bps=6,now_ms=t)
        with _fake_service(d,cmd=commands) as svc:
            report=svc.tick(NOW+5000)
            assert report.manual.closed==(pid,)
            assert not finished.is_set()
            assert (d/"close_result.json").exists()
    finally:
        release.set();thread.join(2)
    assert finished.is_set() and len(_close_events(j))==1


def test_invalid_constructor_and_guard_values(d):
    for run_id in ("", " bad", "../x", "a"*65, None, True):
        with pytest.raises(ValueError,match="invalid_run_id"):
            ExitService(run_id=run_id,data_dir=d,run_commands=lambda _:None,run_monitor=lambda _:MonitorReport(0,(),()))
    with pytest.raises(ValueError,match="invalid_data_dir"):
        ExitService(run_id=RUN,data_dir=d/"missing",run_commands=lambda _:None,run_monitor=lambda _:MonitorReport(0,(),()))
    for f in (None, 9, "x"):
        with pytest.raises(ValueError,match="invalid_callbacks"):
            ExitService(run_id=RUN,data_dir=d,run_commands=f,run_monitor=lambda _:MonitorReport(0,(),()))
    for bad in (None, True, 0, 1.5, "now"):
        assert not exit_service_healthy(data_dir=d,run_id=RUN,now_ms=bad)


def test_run_loop_calls_commands_and_monitor_without_external_clock(d):
    called=[];now=iter([NOW,NOW+5000,NOW+60000]);stop=iter([False,False,False,True])
    svc=_fake_service(d,cmd=lambda t:called.append(t) or None)
    svc.run(now_fn=lambda:next(now),sleep_fn=lambda _:None,should_stop=lambda:next(stop))
    assert called==[NOW,NOW+5000,NOW+60000]
    assert not _healthy(d,NOW+60000)  # process released ownership


def _lease_child(path, conn):
    with _fake_service(Path(path)) as s:
        s.tick(NOW)
        conn.send("READY")
        conn.recv()


def _manual_child(path, conn):
    d=Path(path)
    other_j=EventJournal(d/"journal.db")
    def cmd(t):
        return run_manual_close(journal=other_j,portfolio_id="brain",run_id=RUN,
                                data_dir=d,price_of=lambda *_:D("100"),fee_bps=6,now_ms=t)
    with _fake_service(d,cmd=cmd) as svc:
        conn.send("READY")
        while True:
            job=conn.recv()
            if job=="EXIT":return
            report=svc.tick(job)
            conn.send((report.state, report.manual.closed if report.manual else ()))


def test_posix_lease_is_exclusive_across_real_processes(d):
    import multiprocessing
    ctx=multiprocessing.get_context("spawn")
    parent,child=ctx.Pipe()
    proc=ctx.Process(target=_lease_child,args=(str(d),child))
    proc.start();child.close()
    try:
        assert parent.poll(3) and parent.recv()=="READY"
        assert _healthy(d)
        with pytest.raises(ExitServiceBusy,match="exit_service_already_running"):
            _fake_service(d).start()
        parent.send("STOP")
        proc.join(3)
        assert proc.exitcode==0
        assert not _healthy(d)
    finally:
        if proc.is_alive():
            proc.terminate();proc.join(3)
        parent.close()


def test_separate_process_handles_manual_close_while_parent_ai_blocked(d):
    import multiprocessing
    ctx=multiprocessing.get_context("spawn")
    j=_journal(d);pid=_open(j)
    parent,child=ctx.Pipe()
    proc=ctx.Process(target=_manual_child,args=(str(d),child))
    proc.start();child.close()
    entered=SyncEvent();release=SyncEvent();finished=SyncEvent()
    def fake_ai(now,slot):
        entered.set()
        assert release.wait(3)
        return CycleReport(now,(),(),(),())
    runner=Runner(run_id=RUN,data_dir=d,run_monitor=lambda _:MonitorReport(0,(),()),
                  run_cycle=fake_ai,cycle_delay_ms=0)
    ai=Thread(target=lambda:(runner.tick(NOW),finished.set()),daemon=True)
    try:
        assert parent.poll(3) and parent.recv()=="READY"
        ai.start();assert entered.wait(1)
        (d/"close_request.json").write_text(json.dumps({"ts_ms":NOW,"position_ids":[pid]}))
        parent.send(NOW+5000)
        assert parent.poll(3),"worker did not service manual close"
        state,closed=parent.recv()
        assert state=="healthy" and closed==(pid,)
        assert not finished.is_set(),"AI unexpectedly unblocked before close"
        assert len(_close_events(j))==1
        parent.send("EXIT")
        proc.join(3)
        assert proc.exitcode==0
    finally:
        release.set();ai.join(3)
        if proc.is_alive():proc.terminate();proc.join(3)
        parent.close()
    assert finished.is_set() and len(_close_events(j))==1


def test_restart_does_not_inherit_previous_healthy_lease(d):
    first=_fake_service(d)
    with first:
        first.tick(NOW)
        token1=json.loads((d/BEAT_FILE).read_text())["lease_token"]
        assert _healthy(d)
    second=_fake_service(d)
    with second:
        # The old file remains on disk but its fencing token must not match.
        assert not _healthy(d)
        second.tick(NOW+5000)
        token2=json.loads((d/BEAT_FILE).read_text())["lease_token"]
        assert token1 != token2
        assert _healthy(d,NOW+5000)
    assert not _healthy(d,NOW+5000)


def test_forged_heartbeat_token_cannot_authorize_open(d):
    with _fake_service(d) as svc:
        svc.tick(NOW)
        path=d/BEAT_FILE
        valid=json.loads(path.read_text())
        assert _healthy(d)
        valid["lease_token"]="0"*32
        path.write_text(json.dumps(valid))
        assert not _healthy(d)


def test_same_owner_serializes_ticks_and_stop_waits_for_inflight_close(d):
    started=SyncEvent();release=SyncEvent();finished=SyncEvent();calls=[]
    def cmd(t):
        started.set()
        assert release.wait(2)
        calls.append(t)
        return None
    service=_fake_service(d,cmd=cmd)
    service.start()
    t=Thread(target=lambda:(service.tick(NOW),finished.set()))
    t.start()
    try:
        assert started.wait(1)
        with pytest.raises(ExitServiceBusy,match="exit_service_tick_in_progress"):
            service.tick(NOW+1000)
        shutdown_done=SyncEvent()
        closer=Thread(target=lambda:(service.stop(),shutdown_done.set()))
        closer.start()
        assert not shutdown_done.wait(0.01)
        assert not finished.is_set()
    finally:
        release.set()
        t.join(2)
        closer.join(2)
        service.stop()
    assert finished.is_set() and shutdown_done.is_set()
    assert calls==[NOW]
    assert not _healthy(d)


def _stop_child(path, conn):
    d=Path(path)
    other_j=EventJournal(d/"journal.db")
    bar=Bar(NOW-60000,D("100"),D("100"),D("97"),D("98"),D("100"))
    def monitor(t):
        return run_exit_monitor(journal=other_j,portfolio_id="brain",run_id=RUN,
                                fetch_bars=lambda sym,start,end:[bar],
                                policy=ExitPolicy(D("2"),24*3600000,D("0")),
                                fee_bps=6,now_ms=t)
    with _fake_service(d,mon=monitor) as svc:
        conn.send("READY")
        tick=conn.recv()
        result=svc.tick(tick)
        conn.send((result.state,result.monitor.closed))
        conn.recv()


def test_real_stop_across_processes_while_parent_model_blocked(d):
    import multiprocessing
    ctx=multiprocessing.get_context("spawn")
    j=_journal(d);pid=_open(j)
    parent,child=ctx.Pipe()
    proc=ctx.Process(target=_stop_child,args=(str(d),child))
    proc.start();child.close()
    entered=SyncEvent();release=SyncEvent();finished=SyncEvent()
    def ai(now,slot):
        entered.set();assert release.wait(3)
        return CycleReport(now,(),(),(),())
    runner=Runner(run_id=RUN,data_dir=d,run_monitor=lambda _:MonitorReport(0,(),()),
                  run_cycle=ai,cycle_delay_ms=0)
    ai_thread=Thread(target=lambda:(runner.tick(NOW),finished.set()),daemon=True)
    try:
        assert parent.poll(3) and parent.recv()=="READY"
        ai_thread.start();assert entered.wait(1)
        parent.send(NOW+5000)
        assert parent.poll(3),"sidecar did not perform stop while AI blocked"
        state,closed=parent.recv()
        assert state=="healthy" and closed==((pid,"stop"),)
        assert not finished.is_set()
        assert len(_close_events(j))==1
        assert _close_events(j)[0].payload["reason"]=="stop"
        parent.send("EXIT")
        proc.join(3)
        assert proc.exitcode==0
    finally:
        release.set();ai_thread.join(3)
        if proc.is_alive():proc.terminate();proc.join(3)
        parent.close()
    assert finished.is_set() and len(_close_events(j))==1
