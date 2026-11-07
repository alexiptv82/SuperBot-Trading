"""Real POSIX lease + PAPER quote recheck integration; no external network."""
from __future__ import annotations

from decimal import Decimal as D

from backend.tests.test_v3_post_ai_guard import _args, NOW, RUN, RULES, POL
from backend.v3.runner.exit_service import ExitService, exit_service_healthy
from backend.v3.runner.monitor import MonitorReport
from backend.v3.runner.post_ai_guard import recheck_paper_open


def _recheck(j, decision, folder, *, now=NOW):
    return recheck_paper_open(
        decision=decision, journal=j, run_id=RUN, initial_equity=D('1000'),
        risk_policy=POL, now_ms=now,
        exit_healthy=lambda t: exit_service_healthy(data_dir=folder,run_id=RUN,now_ms=t),
        mandate_problem=lambda:None,budget_problem=lambda:None,
        daily_loss_halted=lambda _:False,paused=lambda:False,
        market_rules=lambda _:RULES,market_price=lambda *_:D('100'),
        market_fresh=lambda *_:True)


def test_cannot_open_until_owner_is_alive_and_has_monitored(tmp_path):
    j,d,state,_=_args(tmp_path)
    assert _recheck(j,d,tmp_path).code == 'exit_service_unhealthy'
    svc=ExitService(run_id=RUN,data_dir=tmp_path,run_commands=lambda _:None,
                    run_monitor=lambda _:MonitorReport(0,(),()))
    with svc:
        assert _recheck(j,d,tmp_path).code == 'exit_service_unhealthy'
        assert svc.tick(NOW).state=='healthy'
        assert _recheck(j,d,tmp_path).allowed
    assert _recheck(j,d,tmp_path).code=='exit_service_unhealthy'


def test_restart_does_not_inherit_previous_healthy_heartbeat(tmp_path):
    j,d,state,_=_args(tmp_path)
    first=ExitService(run_id=RUN,data_dir=tmp_path,run_commands=lambda _:None,
                      run_monitor=lambda _:MonitorReport(0,(),()))
    second=ExitService(run_id=RUN,data_dir=tmp_path,run_commands=lambda _:None,
                       run_monitor=lambda _:MonitorReport(0,(),()))
    with first:
        first.tick(NOW)
        assert _recheck(j,d,tmp_path).allowed
    with second:
        assert _recheck(j,d,tmp_path).code=='exit_service_unhealthy'
        second.tick(NOW+1000)
        assert _recheck(j,d,tmp_path,now=NOW+1000).allowed


def test_degraded_exit_monitor_does_not_authorize_open(tmp_path):
    j,d,state,_=_args(tmp_path)
    sidecar=ExitService(run_id=RUN,data_dir=tmp_path,
                        run_commands=lambda _:None,
                        run_monitor=lambda _:MonitorReport(1,(),(('pos','no_feed'),)))
    with sidecar:
        assert sidecar.tick(NOW).state=='degraded'
        assert _recheck(j,d,tmp_path).code=='exit_service_unhealthy'
