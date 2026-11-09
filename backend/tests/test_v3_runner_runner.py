"""A2c - il direttore (Runner): scheduling, pausa, fermo, battito, guasti. Orologio finto, nessuna rete."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from backend.v3.runner.cycle import CycleReport
from backend.v3.runner.monitor import MonitorReport
from backend.v3.runner.runner import CYCLE_MS, MINUTE_MS, Runner, TickResult

G = 1_800_000_000_000 // CYCLE_MS * CYCLE_MS               # inizio di una candela da 15 minuti
DELAY = 20_000


class Rig:
    def __init__(self, *, halted=lambda: None, monitor_errors=(), cycle_errors=(), delay=DELAY, cycle_ms=CYCLE_MS):
        self.dir = Path(tempfile.mkdtemp())
        self.monitor_calls, self.cycle_calls = [], []
        self.monitor_fail = self.cycle_fail = False
        self.monitor_errors, self.cycle_errors = monitor_errors, cycle_errors

        def mon(now):
            self.monitor_calls.append(now)
            if self.monitor_fail:
                raise RuntimeError("boom")
            return MonitorReport(0, (), tuple(self.monitor_errors))

        def cyc(now, slot):
            self.cycle_calls.append((now, slot))
            if self.cycle_fail:
                raise RuntimeError("boom")
            return CycleReport(now, (), (), (), tuple(self.cycle_errors))
        self.runner = Runner(run_id="run-1", data_dir=self.dir, run_monitor=mon, run_cycle=cyc,
                             halted=halted, cycle_delay_ms=delay, cycle_ms=cycle_ms)

    def beat(self):
        return json.loads((self.dir / "heartbeat.json").read_text(encoding="utf-8"))


def test_schedule_monitor_every_minute_cycle_once_per_slot_after_the_delay():
    r = Rig()
    t = r.runner.tick(G + 19_999)
    assert r.monitor_calls == [G + 19_999] and r.cycle_calls == [] and t.cycle is None      # troppo presto
    t = r.runner.tick(G + 20_000)
    assert r.cycle_calls == [(G + 20_000, G // CYCLE_MS)] and t.cycle is not None and t.monitor is None
    r.runner.tick(G + 25_000)
    r.runner.tick(G + 59_000)
    assert len(r.monitor_calls) == 1 and len(r.cycle_calls) == 1                           # niente doppioni
    r.runner.tick(G + MINUTE_MS)
    assert r.monitor_calls == [G + 19_999, G + MINUTE_MS] and len(r.cycle_calls) == 1
    for k in range(2, 15):
        r.runner.tick(G + k * MINUTE_MS + 30_000)
    assert len(r.cycle_calls) == 1 and len(r.monitor_calls) == 15                          # minuti 0..14: un monitor ciascuno
    r.runner.tick(G + CYCLE_MS + DELAY)
    assert r.cycle_calls[-1] == (G + CYCLE_MS + DELAY, G // CYCLE_MS + 1) and len(r.cycle_calls) == 2


def test_starting_mid_slot_runs_the_cycle_immediately_once():
    r = Rig()
    r.runner.tick(G + 7 * MINUTE_MS)
    r.runner.tick(G + 8 * MINUTE_MS)
    assert r.cycle_calls == [(G + 7 * MINUTE_MS, G // CYCLE_MS)]


def test_delay_zero_runs_at_the_close():
    r = Rig(delay=0)
    r.runner.tick(G)
    assert r.cycle_calls == [(G, G // CYCLE_MS)]


def test_heartbeat_content_and_counter():
    r = Rig()
    r.runner.tick(G + DELAY)
    assert r.beat() == {"ts_ms": G + DELAY, "cycle": 1, "state": "running", "run_id": "run-1", "last_error": None,
                        "exit_mode": "legacy"}
    r.runner.tick(G + CYCLE_MS + DELAY)
    assert r.beat()["cycle"] == 2 and r.beat()["ts_ms"] == G + CYCLE_MS + DELAY
    assert sorted(os.listdir(r.dir)) == ["heartbeat.json"]                                 # nessun file temporaneo


def test_pause_flag_blocks_cycles_but_not_the_monitor_and_resumes_in_the_same_slot():
    r = Rig()
    (r.dir / "pause.flag").write_text("")
    t = r.runner.tick(G + DELAY)
    assert t.state == "paused" and r.cycle_calls == [] and r.monitor_calls == [G + DELAY]
    assert r.beat()["state"] == "paused" and r.beat()["cycle"] == 0
    r.runner.tick(G + MINUTE_MS)
    assert r.cycle_calls == [] and len(r.monitor_calls) == 2                               # le uscite proseguono
    (r.dir / "pause.flag").unlink()
    t = r.runner.tick(G + 2 * MINUTE_MS)
    assert t.state == "running" and r.cycle_calls == [(G + 2 * MINUTE_MS, G // CYCLE_MS)]  # candela non consumata


def test_halted_blocks_cycles_keeps_the_monitor_and_reports_the_reason():
    r = Rig(halted=lambda: "budget")
    t = r.runner.tick(G + DELAY)
    assert t.state == "halted" and r.cycle_calls == [] and r.monitor_calls == [G + DELAY]
    assert r.beat()["state"] == "halted" and r.beat()["last_error"] == "halted:budget"


def test_halted_wins_over_pause_and_a_crashing_halt_check_means_halted():
    r = Rig(halted=lambda: "x")
    (r.dir / "pause.flag").write_text("")
    assert r.runner.tick(G + DELAY).state == "halted"

    def boom():
        raise RuntimeError("no")
    r2 = Rig(halted=boom)
    t = r2.runner.tick(G + DELAY)
    assert t.state == "halted" and r2.cycle_calls == [] and t.last_error == "halted:halt_check_failed"


def test_monitor_failure_is_reported_and_the_cycle_still_runs():
    r = Rig()
    r.monitor_fail = True
    t = r.runner.tick(G + DELAY)
    assert t.last_error == "monitor_failed" and len(r.cycle_calls) == 1 and r.beat()["last_error"] == "monitor_failed"
    r.monitor_fail = False
    t = r.runner.tick(G + MINUTE_MS)                                                       # il minuto dopo riprova
    assert t.last_error is None and len(r.monitor_calls) == 2


def test_cycle_failure_is_reported_not_retried_in_the_same_slot_and_not_counted():
    r = Rig()
    r.cycle_fail = True
    t = r.runner.tick(G + DELAY)
    assert t.last_error == "cycle_failed" and r.runner.cycles == 0
    r.cycle_fail = False
    r.runner.tick(G + 5 * MINUTE_MS)
    assert len(r.cycle_calls) == 1                                                         # stessa candela: nessun riprovo
    t = r.runner.tick(G + CYCLE_MS + DELAY)
    assert t.last_error is None and len(r.cycle_calls) == 2 and r.runner.cycles == 1


def test_error_codes_from_reports_reach_the_heartbeat():
    r = Rig(monitor_errors=[("pos1", "feed_error"), ("pos2", "x")],
            cycle_errors=[("AAAUSDT", "feed_error"), ("BBBUSDT", "data_unavailable"), ("CCCUSDT", "a"), ("DDDUSDT", "b")])
    t = r.runner.tick(G + DELAY)
    assert t.last_error == "monitor:feed_error;cycle:AAAUSDT:feed_error,BBBUSDT:data_unavailable,CCCUSDT:a"
    assert r.beat()["last_error"] == t.last_error


def test_error_text_is_sanitised_and_bounded():
    r = Rig(monitor_errors=[("p", "bad text with spaces/and\nnewline")], cycle_errors=[("S" * 300, "c")])
    t = r.runner.tick(G + DELAY)
    assert " " not in t.last_error and "\n" not in t.last_error and "/" not in t.last_error
    assert len(t.last_error) <= 200


def test_each_error_part_is_capped_so_none_hides_the_others_and_the_whole_is_capped():
    r = Rig(halted=lambda: "h" * 300, monitor_errors=[("p", "m" * 300)], cycle_errors=[("S", "c" * 300)])
    t = r.runner.tick(G + DELAY)
    parts = t.last_error.split(";")
    assert parts[0] == "halted:" + "h" * 113 and parts[1].startswith("monitor:m")        # 120 caratteri a parte
    assert len(parts[0]) == 120 and len(t.last_error) == 200
    assert r.beat()["last_error"] == t.last_error


def test_heartbeat_write_failure_does_not_stop_the_tick(monkeypatch):
    r = Rig()

    def fail(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", fail)
    t = r.runner.tick(G + DELAY)
    assert isinstance(t, TickResult) and len(r.cycle_calls) == 1
    assert sorted(os.listdir(r.dir)) == []                                                 # il temporaneo e' stato tolto


def test_run_loop_survives_a_tick_exception_and_stops_on_request():
    r = Rig()
    clock = iter([G + DELAY, 0, G + MINUTE_MS + 1, G + 2 * MINUTE_MS])
    sleeps, stops = [], iter([False, False, False, False, True])
    r.runner.run(now_fn=lambda: next(clock), sleep_fn=sleeps.append, should_stop=lambda: next(stops), poll_s=3.0)
    assert sleeps == [3.0] * 4
    assert len(r.monitor_calls) == 3 and len(r.cycle_calls) == 1                           # il tick con now=0 e' stato isolato
    assert r.beat()["ts_ms"] == G + 2 * MINUTE_MS and r.beat()["last_error"] is None


def test_run_loop_marks_tick_failed_in_the_heartbeat():
    r = Rig()
    r.runner.run(now_fn=lambda: 0, sleep_fn=lambda s: None, should_stop=iter([False, True]).__next__)
    assert r.beat() == {"ts_ms": 0, "cycle": 0, "state": "running", "run_id": "run-1", "last_error": "tick_failed",
                        "exit_mode": "legacy"}


@pytest.mark.parametrize("now", [0, -1, True, 1.5, None, "1"])
def test_bad_now_is_refused(now):
    with pytest.raises(ValueError, match="invalid_now"):
        Rig().runner.tick(now)


@pytest.mark.parametrize("run_id", ["", " ", "a b", "x" * 65, None, 5, "../x", "-x"])
def test_bad_run_id(run_id):
    with pytest.raises(ValueError, match="invalid_run_id"):
        Runner(run_id=run_id, data_dir=Path(tempfile.mkdtemp()), run_monitor=lambda n: None, run_cycle=lambda n, s: None)


def test_bad_data_dir_and_delay():
    d = Path(tempfile.mkdtemp())
    for bad in (str(d), d / "missing", None):
        with pytest.raises(ValueError, match="invalid_data_dir"):
            Runner(run_id="r", data_dir=bad, run_monitor=lambda n: None, run_cycle=lambda n, s: None)
    for delay in (-1, CYCLE_MS, True, 1.5, "20"):
        with pytest.raises(ValueError, match="invalid_cycle_delay"):
            Runner(run_id="r", data_dir=d, run_monitor=lambda n: None, run_cycle=lambda n, s: None, cycle_delay_ms=delay)


def test_on_tick_receives_each_successful_tick_and_its_failures_are_contained():
    r = Rig()
    seen = []

    def cb(now, result):
        seen.append((now, result.state))
        raise RuntimeError("log broke")
    clock = iter([G + DELAY, 0, G + MINUTE_MS])
    stops = iter([False, False, False, True])
    r.runner.run(now_fn=lambda: next(clock), sleep_fn=lambda s: None, should_stop=lambda: next(stops), on_tick=cb)
    assert seen == [(G + DELAY, "running"), (G + MINUTE_MS, "running")]          # il tick con now=0 non arriva al log
    assert len(r.monitor_calls) == 2


# ----------------------------------------------------------------------------- giro a intervallo lungo (1 ora)
HOUR = 4 * CYCLE_MS
H0 = 1_800_000_000_000 // HOUR * HOUR                       # inizio di un'ora


def test_hourly_cycle_runs_once_per_hour_while_the_monitor_still_runs_every_minute():
    r = Rig(cycle_ms=HOUR)
    r.runner.tick(H0 + DELAY - 1)
    assert r.cycle_calls == []                                                  # troppo presto
    r.runner.tick(H0 + DELAY)
    assert r.cycle_calls == [(H0 + DELAY, H0 // HOUR)]
    for k in range(1, 60):                                                      # minuti 1..59: solo il monitor
        r.runner.tick(H0 + k * MINUTE_MS + 30_000)
    assert len(r.cycle_calls) == 1 and len(r.monitor_calls) == 60               # il primo tick e i 59 minuti dopo
    r.runner.tick(H0 + CYCLE_MS + DELAY)                                         # un quarto d'ora dopo: NON e' un nuovo giro
    r.runner.tick(H0 + HOUR + DELAY)
    assert r.cycle_calls[-1] == (H0 + HOUR + DELAY, H0 // HOUR + 1) and len(r.cycle_calls) == 2


def test_hourly_cycle_started_mid_hour_runs_at_once_then_at_the_next_hour():
    r = Rig(cycle_ms=HOUR)
    r.runner.tick(H0 + 37 * MINUTE_MS)
    assert len(r.cycle_calls) == 1
    r.runner.tick(H0 + 59 * MINUTE_MS)
    assert len(r.cycle_calls) == 1
    r.runner.tick(H0 + HOUR + DELAY)
    assert len(r.cycle_calls) == 2


def test_hourly_cycle_does_not_spend_in_pause_and_resumes_in_the_same_hour():
    r = Rig(cycle_ms=HOUR)
    (r.dir / "pause.flag").write_text("")
    r.runner.tick(H0 + DELAY)
    assert r.cycle_calls == [] and r.beat()["state"] == "paused"
    (r.dir / "pause.flag").unlink()
    r.runner.tick(H0 + 40 * MINUTE_MS)
    assert len(r.cycle_calls) == 1


@pytest.mark.parametrize("bad", [0, -900_000, 450_000, 900_001, 1_800_001, 86_400_000 + 900_000, True, 3_600_000.0, "3600000", None])
def test_invalid_cycle_ms_is_refused(bad):
    with pytest.raises(ValueError, match="invalid_cycle_ms"):
        Rig(cycle_ms=bad)


def test_cycle_ms_boundaries_and_the_delay_must_fit_inside_the_interval():
    Rig(cycle_ms=CYCLE_MS)
    Rig(cycle_ms=86_400_000)
    Rig(cycle_ms=HOUR, delay=HOUR - 1)
    with pytest.raises(ValueError, match="invalid_cycle_delay"):
        Rig(cycle_ms=HOUR, delay=HOUR)
    with pytest.raises(ValueError, match="invalid_cycle_delay"):
        Rig(cycle_ms=CYCLE_MS, delay=CYCLE_MS)
