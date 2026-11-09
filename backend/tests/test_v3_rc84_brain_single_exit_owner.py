"""RC84 D2: un solo proprietario delle chiusure PAPER per run Brain e cartella dati.

Processi reali indipendenti (sottoprocessi Python), solo dati sintetici in tmp, nessuna rete, nessun modello.
Proprietari possibili: runner `legacy` aggiornato (tiene il lease con LegacyExitFence per tutta la vita)
ed exit-worker (ExitService). Lo stesso lease kernel `.exit_service.lock` li esclude a vicenda.
Un runner NON aggiornato non conosce il lease: viene solo riconosciuto dal suo heartbeat (difesa in profondita').
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from decimal import Decimal

import pytest

from backend.v3.events import Event, EventJournal
from backend.v3.runner import wiring
from backend.v3.runner.exit_service import ExitService, ExitServiceBusy, exit_service_healthy
from backend.v3.runner.exit_worker import (
    UNPATCHED_RUNNER_WINDOW_MS, acquire_exit_lease, build_exit_worker, foreign_exit_owner, main as worker_main,
)
from backend.v3.runner.config import load_default_config
from backend.v3.runner.monitor import MonitorReport

RUN = "brain-owner-test"
NOW = int(time.time() * 1000)
ROOT = Path(__file__).resolve().parents[2]
ENV = dict(os.environ, PYTHONPATH=f"{ROOT}:{ROOT / 'backend'}")

HOLDER = r"""
import sys, time
from pathlib import Path
from backend.v3.runner.legacy_exit_fence import LegacyExitFence
from backend.v3.runner.exit_service import ExitService, ExitServiceBusy
from backend.v3.runner.monitor import MonitorReport
data, run, release, released, kind = sys.argv[1:6]
try:
    if kind == "legacy":
        owner = LegacyExitFence(run_id=run, data_dir=Path(data)).start()
    else:
        owner = ExitService(run_id=run, data_dir=Path(data), run_commands=lambda t: None,
                            run_monitor=lambda t: MonitorReport(0, (), ())).start()
except ExitServiceBusy:
    print("BUSY", flush=True); sys.exit(0)
print("HELD", flush=True)
while not Path(release).exists():
    time.sleep(0.01)
owner.stop()
Path(released).write_text(str(time.monotonic_ns()))
print("RELEASED", flush=True)
"""


class Holder:
    """Un processo indipendente che detiene il lease (runner legacy aggiornato o exit-worker)."""

    def __init__(self, data: Path, kind: str = "legacy", run: str = RUN):
        self.release = data.parent / f"release-{kind}-{os.getpid()}-{time.monotonic_ns()}"
        self.released = data.parent / f"released-{self.release.name}"
        self.proc = subprocess.Popen([sys.executable, "-c", HOLDER, str(data), run, str(self.release),
                                      str(self.released), kind], cwd=str(ROOT), env=ENV,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.first = self.proc.stdout.readline().strip()

    def let_go(self):
        self.release.write_text("go")
        self.proc.wait(timeout=20)

    def kill(self):
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait(timeout=20)


def _journal(d: Path) -> EventJournal:
    j = EventJournal(d / "journal.db")
    j.init_schema()
    j.append(Event("checkpoint", "brain", RUN, "heartbeat", NOW - 60_000, "test", {}))
    return j


def _service(d: Path) -> ExitService:
    return ExitService(run_id=RUN, data_dir=d, run_commands=lambda t: None,
                       run_monitor=lambda t: MonitorReport(0, (), ()))


def _beat(d: Path, **beat):
    (d / "heartbeat.json").write_text(json.dumps(dict({"ts_ms": NOW, "cycle": 1, "state": "running",
                                                         "run_id": RUN, "last_error": None}, **beat)))


# ------------------------------------------------------------------ esclusione fra processi indipendenti

def test_exit_worker_cannot_take_ownership_while_a_patched_legacy_runner_holds_it(tmp_path, capsys):
    _journal(tmp_path)
    holder = Holder(tmp_path, "legacy")
    try:
        assert holder.first == "HELD"
        rc = worker_main(["--data-dir", str(tmp_path), "--run-id", RUN, "--start-paper", "--legacy-exits-disabled"],
                         env={"DESK_MODE": "paper"}, get_json=lambda _: [], clock=lambda: NOW,
                         sleep=lambda _: None, should_stop=lambda: True, notify=lambda _: False)
        assert rc == 3 and "exit_owner_busy" in capsys.readouterr().err
        assert not exit_service_healthy(data_dir=tmp_path, run_id=RUN, now_ms=NOW)   # nessuna certificazione
    finally:
        holder.let_go()


def test_legacy_runner_refuses_to_start_while_an_exit_worker_owns_the_run(tmp_path, capsys):
    holder = Holder(tmp_path, "worker")
    try:
        assert holder.first == "HELD"
        rc = wiring.main(["--data-dir", str(tmp_path), "--run-id", RUN, "--once"], env={"DESK_MODE": "paper"},
                         get_json=lambda _: pytest.fail("nessuna rete"), now_fn=lambda: NOW)
        assert rc == 3 and "exit_owner_busy" in capsys.readouterr().err
        assert not (tmp_path / "journal.db").exists()                              # nessun runner costruito
        assert not (tmp_path / "heartbeat.json").exists()
    finally:
        holder.let_go()


def test_a_second_legacy_runner_cannot_start_on_the_same_run(tmp_path, capsys):
    holder = Holder(tmp_path, "legacy")
    try:
        assert holder.first == "HELD"
        assert wiring.main(["--data-dir", str(tmp_path), "--run-id", RUN, "--once"], env={"DESK_MODE": "paper"},
                           get_json=lambda _: pytest.fail("nessuna rete"), now_fn=lambda: NOW) == 3
    finally:
        holder.let_go()


def test_legacy_runner_holds_the_lease_for_its_whole_lifetime_and_releases_it_on_exit(tmp_path):
    seen = []

    def should_stop():
        try:
            _service(tmp_path).start().stop()
            seen.append("acquired")
        except ExitServiceBusy:
            seen.append("busy")
        return True

    rc = wiring.main(["--data-dir", str(tmp_path), "--run-id", RUN], env={"DESK_MODE": "paper"},
                     get_json=lambda _: [], now_fn=lambda: NOW, sleep_fn=lambda _: None, should_stop=should_stop)
    assert rc == 0 and seen == ["busy"]                    # durante la vita del runner: nessun altro proprietario
    _service(tmp_path).start().stop()                      # dopo l'uscita: lease libero


def test_concurrent_acquisition_by_independent_processes_yields_exactly_one_owner(tmp_path):
    holders = [Holder(tmp_path, kind) for kind in ("legacy", "worker", "legacy", "worker", "legacy", "worker")]
    try:
        firsts = sorted(h.first for h in holders)
        assert firsts.count("HELD") == 1 and firsts.count("BUSY") == 5
    finally:
        for h in holders:
            if h.first == "HELD":
                h.let_go()
            else:
                h.proc.wait(timeout=20)


# ------------------------------------------------------------------ crash, riavvio, handover

def test_crash_of_the_legacy_owner_releases_the_lease_and_the_worker_can_take_over(tmp_path):
    holder = Holder(tmp_path, "legacy")
    assert holder.first == "HELD"
    with pytest.raises(ExitServiceBusy):
        _service(tmp_path).start()
    _beat(tmp_path, exit_mode="legacy")                    # ultimo heartbeat del runner aggiornato prima del crash
    holder.kill()
    assert foreign_exit_owner(tmp_path, NOW) is None       # runner aggiornato: decide il lease, non l'heartbeat
    svc = _service(tmp_path).start()                       # il kernel ha liberato il lease alla morte del processo
    try:
        with pytest.raises(ExitServiceBusy):
            _service(tmp_path).start()                     # e ora l'unico proprietario e' il nuovo
    finally:
        svc.stop()


def test_restart_after_crash_never_inherits_a_previous_healthy_certificate(tmp_path):
    holder = Holder(tmp_path, "worker")
    assert holder.first == "HELD"
    holder.kill()
    svc = _service(tmp_path).start()
    try:
        assert not exit_service_healthy(data_dir=tmp_path, run_id=RUN, now_ms=NOW)   # serve un tick nuovo
        svc.tick(NOW)
        assert exit_service_healthy(data_dir=tmp_path, run_id=RUN, now_ms=NOW)
    finally:
        svc.stop()


def test_handover_legacy_to_worker_is_sequential_with_no_overlap(tmp_path):
    holder = Holder(tmp_path, "legacy")
    assert holder.first == "HELD"
    svc = _service(tmp_path)
    attempts = []
    threading.Timer(0.4, lambda: holder.release.write_text("go")).start()

    def sleep(s):
        attempts.append(time.monotonic_ns())
        time.sleep(s)
    acquire_exit_lease(svc, wait_s=10, sleep=sleep)
    acquired_ns = time.monotonic_ns()
    try:
        holder.proc.wait(timeout=20)
        released_ns = int(holder.released.read_text())
        assert attempts, "il worker ha dovuto aspettare: il legacy deteneva il lease"
        assert released_ns <= acquired_ns                  # mai due proprietari: prima rilascio, poi acquisizione
        assert acquired_ns - released_ns < 2_000_000_000   # finestra senza proprietario: al piu' un intervallo di attesa
    finally:
        svc.stop()


def test_handover_wait_is_bounded_and_fails_closed(tmp_path):
    holder = Holder(tmp_path, "legacy")
    try:
        assert holder.first == "HELD"
        t0 = time.monotonic()
        with pytest.raises(ExitServiceBusy):
            acquire_exit_lease(_service(tmp_path), wait_s=0.6, sleep=time.sleep)
        assert time.monotonic() - t0 < 5
    finally:
        holder.let_go()


# ------------------------------------------------------------------ runner non aggiornato, heartbeat obsoleto

@pytest.mark.parametrize("beat, expected", [
    ({}, "unpatched_runner_recent"),                                    # versione precedente, viva
    ({"ts_ms": NOW - UNPATCHED_RUNNER_WINDOW_MS - 1}, None),            # versione precedente, ferma da tempo
    ({"exit_mode": "sidecar"}, None),
    ({"exit_mode": "legacy"}, None),
    ({"exit_mode": "altro"}, "runner_heartbeat_unverifiable"),
    ({"ts_ms": "ieri"}, "runner_heartbeat_unverifiable"),
])
def test_foreign_owner_detection_from_the_runner_heartbeat(tmp_path, beat, expected):
    _beat(tmp_path, **beat)
    assert foreign_exit_owner(tmp_path, NOW) == expected


def test_missing_or_corrupt_runner_heartbeat(tmp_path):
    assert foreign_exit_owner(tmp_path, NOW) is None
    (tmp_path / "heartbeat.json").write_text("{troncato")
    assert foreign_exit_owner(tmp_path, NOW) == "runner_heartbeat_unverifiable"
    (tmp_path / "heartbeat.json").unlink()
    os.symlink("/etc/hostname", tmp_path / "heartbeat.json")
    assert foreign_exit_owner(tmp_path, NOW) == "runner_heartbeat_unverifiable"


def test_worker_refuses_to_start_while_an_unpatched_runner_looks_alive(tmp_path, capsys):
    _journal(tmp_path)
    _beat(tmp_path)                                                     # heartbeat recente senza exit_mode
    rc = worker_main(["--data-dir", str(tmp_path), "--run-id", RUN, "--start-paper", "--legacy-exits-disabled"],
                     env={"DESK_MODE": "paper"}, get_json=lambda _: [], clock=lambda: NOW,
                     sleep=lambda _: None, should_stop=lambda: True, notify=lambda _: False)
    assert rc == 3 and "foreign_exit_owner:unpatched_runner_recent" in capsys.readouterr().err
    assert not (tmp_path / ".exit_service.lock").exists()              # nessun lease preso
    rc = worker_main(["--data-dir", str(tmp_path), "--run-id", RUN, "--validate-only"],
                     env={"DESK_MODE": "paper"}, clock=lambda: NOW)
    assert rc == 3


def test_running_worker_stands_down_while_an_unpatched_runner_reappears(tmp_path):
    _journal(tmp_path)
    svc = build_exit_worker(data_dir=tmp_path, run_id=RUN, config=load_default_config(), get_json=lambda _: [])
    with svc:
        assert svc.tick(NOW).state == "healthy"
        assert exit_service_healthy(data_dir=tmp_path, run_id=RUN, now_ms=NOW)
        _beat(tmp_path, ts_ms=NOW + 60_000)                             # runner vecchio di nuovo vivo
        (tmp_path / "close_request.json").write_text(json.dumps({"ts_ms": NOW + 60_000, "all": True}))
        t = svc.tick(NOW + 60_000)
        assert t.state == "degraded"
        assert (tmp_path / "close_request.json").exists()               # nessuna chiusura eseguita dal worker
        assert not exit_service_healthy(data_dir=tmp_path, run_id=RUN, now_ms=NOW + 60_000)   # aperture bloccate
        _beat(tmp_path, ts_ms=NOW + 120_000, exit_mode="sidecar")       # il runner sidecar riprende il suo posto
        (tmp_path / "close_request.json").unlink()
        assert svc.tick(NOW + 120_000).state == "healthy"


# ------------------------------------------------------------------ worker assente / legacy: nessuna certificazione

def test_lease_held_by_legacy_never_certifies_the_sidecar_and_opens_stay_blocked(tmp_path):
    holder = Holder(tmp_path, "legacy")
    try:
        assert holder.first == "HELD"
        assert not exit_service_healthy(data_dir=tmp_path, run_id=RUN, now_ms=NOW)
    finally:
        holder.let_go()
    assert not exit_service_healthy(data_dir=tmp_path, run_id=RUN, now_ms=NOW)   # nessun worker: aperture bloccate


# ------------------------------------------------------------------ doppia chiusura della stessa posizione

CLOSER = r"""
import sys
from decimal import Decimal
from backend.v3.events import EventJournal
from backend.v3.executor.paper_close import close_paper
from backend.v3.executor.paper import ExecutionError
db, run, pid, price, go = sys.argv[1:6]
from pathlib import Path
import time
while not Path(go).exists():
    time.sleep(0.005)
try:
    close_paper(portfolio_id="brain", run_id=run, position_id=pid, exit_price=Decimal(price), reason="manual",
                fee_bps=Decimal("6"), journal=EventJournal(db), now_ms=int(sys.argv[6]))
    print("CLOSED")
except (ExecutionError, ValueError) as exc:
    print("REFUSED " + str(exc))
"""


def test_two_processes_closing_the_same_open_position_produce_one_close(tmp_path):
    from backend.tests.test_v3_runner_feed_monitor import _hand
    from backend.v3.executor.paper import execute_paper
    j = _journal(tmp_path)
    pid = execute_paper(_hand(side=1, entry="30000", stop="29000", symbol="BTCUSDT"), portfolio_id="brain",
                        run_id=RUN, journal=j, now_ms=NOW - 3_600_000).position_id
    go = tmp_path / "go"
    procs = [subprocess.Popen([sys.executable, "-c", CLOSER, str(tmp_path / "journal.db"), RUN, pid, price, str(go),
                               str(NOW + i)], cwd=str(ROOT), env=ENV, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
             for i, price in enumerate(("31000", "29500"))]
    time.sleep(0.3)
    go.write_text("go")
    outs = [p.communicate(timeout=60)[0].strip() for p in procs]
    assert sorted(o.split()[0] for o in outs) == ["CLOSED", "REFUSED"], outs
    closes = [e for e in EventJournal(tmp_path / "journal.db").list_run("brain", RUN) if e.event.kind == "paper_close"]
    assert len(closes) == 1


# ------------------------------------------------------------------ LIVE e modalita' non PAPER

def test_non_paper_mode_is_refused_before_any_lease_or_file(tmp_path):
    d = tmp_path / "d"
    assert wiring.main(["--data-dir", str(d), "--run-id", RUN, "--once"], env={"DESK_MODE": "live"},
                       get_json=lambda _: pytest.fail("nessuna rete")) == 2
    assert not d.exists()
    assert worker_main(["--data-dir", str(tmp_path), "--run-id", RUN, "--start-paper", "--legacy-exits-disabled"],
                       env={"DESK_MODE": "live"}) == 2
    assert not (tmp_path / ".exit_service.lock").exists()
