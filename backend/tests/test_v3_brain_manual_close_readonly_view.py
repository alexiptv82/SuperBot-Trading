"""Chiusura manuale Brain: lo stato "chiusura consentita" deve essere calcolabile da chi vede la cartella della run
in SOLA LETTURA (il container web pubblico), e la catena bridge -> sidecar -> journal -> risultato deve chiudersi.

Solo dati sintetici in cartelle temporanee: nessuna rete, nessun ordine, nessuna run operativa.
"""
from __future__ import annotations

import dataclasses
import errno
import json
import os
import subprocess
from pathlib import Path

import pytest

from backend import v3_api as api
from backend.tests.test_v3_runner_e2e import RUN, G, VIEW, FakeModel, _get_json_factory, mandate_template
from backend.v3.dashboard import build_summary
from backend.v3.runner import exit_service as es
from backend.v3.runner.config import load_default_config
from backend.v3.runner.exit_worker import build_exit_worker
from backend.v3.runner.wiring import build_runner

NOW = G + 25_000
GATES = dict(V3_CUTOVER_READONLY="1", V3_ALLOW_BRAIN_SINGLE_CLOSE="1", TRADING_MODE="paper", DESK_MODE="paper",
             V3_CLOSE_BRIDGE_ONLY="1", V3_CLOSE_BRIDGE_SOCKET="/run/superbot-paper-close/close.sock")


def _paths(root: Path) -> api.V3Paths:
    return api.V3Paths(
        journal_path=str(root / "journal.db"), run_id=RUN, budget_db_path=str(root / "budget.db"),
        heartbeat_path=str(root / "heartbeat.json"), pause_flag_path=str(root / "pause.flag"),
        falco_data_dir="/nonexistent/falco", toro_data_dir="/nonexistent/toro",
        close_request_path=str(root / "close_request.json"), close_result_path=str(root / "close_result.json"),
        brain_config_path=str(root / "runner_config.json"))


@pytest.fixture
def run_with_position(tmp_path, monkeypatch):
    """Una run PAPER sintetica con UNA posizione aperta e il servizio uscite vero (non ancora avviato)."""
    for k, v in GATES.items():
        monkeypatch.setenv(k, v)
    root = tmp_path.resolve()
    conf = dataclasses.replace(load_default_config(), symbols=("BTCUSDT",), cycle_minutes=15,
                               thinking="disabled", reasoning_effort="omit", max_tokens=256)
    get_json = _get_json_factory()
    built = build_runner(data_dir=root, run_id=RUN, config=conf, get_json=get_json, inner_transport=FakeModel(),
                         view_params=VIEW)
    m = mandate_template(conf.risk_policy, RUN)
    m.update(approved=True, approved_by="test")
    (root / "mandate.json").write_text(json.dumps(m))
    built.runner.tick(NOW)
    positions = build_summary(built.journal, "brain", RUN).open_positions
    assert len(positions) == 1
    exits = build_exit_worker(data_dir=root, run_id=RUN, config=conf, get_json=get_json)
    (root / "runner_config.json").write_text("{}")
    return root, built, exits, positions[0].position_id


def _deny_writes(monkeypatch, root: Path):
    """Come un bind mount read-only: ogni apertura in scrittura sotto ``root`` fallisce con EROFS."""
    real_open = os.open

    def ro_open(path, flags, *a, **k):
        if str(path).startswith(str(root)) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            raise OSError(errno.EROFS, "Read-only file system")
        return real_open(path, flags, *a, **k)
    monkeypatch.setattr(os, "open", ro_open)


def test_exit_health_and_close_flag_are_visible_from_a_read_only_view(run_with_position, monkeypatch):
    root, _, exits, _ = run_with_position
    with exits:
        t = NOW + 60_000
        exits.tick(t)
        assert es.exit_service_healthy(data_dir=root, run_id=RUN, now_ms=t) is True
        _deny_writes(monkeypatch, root)
        # prima della correzione: False (O_RDWR -> EROFS) e la dashboard disattivava «Chiudi»
        assert es.exit_service_healthy(data_dir=root, run_id=RUN, now_ms=t) is True
        assert api._brain_single_close_ready(_paths(root), t) is True


def test_read_only_view_still_fails_closed_without_a_live_owner(run_with_position, monkeypatch):
    root, _, exits, _ = run_with_position
    with exits:
        t = NOW + 60_000
        exits.tick(t)
    _deny_writes(monkeypatch, root)                              # servizio fermato: lease rilasciato
    assert es.exit_service_healthy(data_dir=root, run_id=RUN, now_ms=t) is False
    assert api._brain_single_close_ready(_paths(root), t) is False


def test_read_only_view_rejects_a_stale_heartbeat(run_with_position, monkeypatch):
    root, _, exits, _ = run_with_position
    with exits:
        t = NOW + 60_000
        exits.tick(t)
        _deny_writes(monkeypatch, root)
        assert api._brain_single_close_ready(_paths(root), t + es.MAX_BEAT_AGE_MS + 1) is False


def test_full_chain_request_sidecar_journal_result(run_with_position):
    """Cio' che fa il bridge (cartella RW) + sidecar: la posizione viene chiusa UNA volta, motivo ``manual``."""
    root, built, exits, pid = run_with_position
    with exits:
        t1 = NOW + 60_000
        exits.tick(t1)
        queued = api._close_request(_paths(root), {"position_id": pid}, t1)
        assert queued == {"ok": True, "pending": True, "ts_ms": t1}
        with pytest.raises(Exception) as dup:                    # seconda richiesta mentre la prima e' in coda
            api._close_request(_paths(root), {"position_id": pid}, t1 + 1)
        assert dup.value.detail["code"] == "richiesta_in_corso"
        t2 = t1 + 60_000
        tick = exits.tick(t2)
        assert tick.manual.status == "done" and tick.manual.closed == (pid,) and tick.manual.failed == ()
        shown = api._close_result(_paths(root), t2)
        assert shown["pending"] is False and shown["result"]["request_ts_ms"] == t1
        assert shown["result"]["closed"] == [pid]
        closes = [e.event for e in built.journal.list_run("brain", RUN) if e.event.kind == "paper_close"]
        assert len(closes) == 1 and closes[0].payload["reason"] == "manual"
        assert build_summary(built.journal, "brain", RUN).open_positions == ()
        exits.tick(t2 + 60_000)
        with pytest.raises(Exception) as gone:                   # idempotenza: la posizione non e' piu' aperta
            api._close_request(_paths(root), {"position_id": pid}, t2 + 60_000)
        assert gone.value.detail["code"] == "posizione_non_aperta"


def test_real_read_only_bind_mount(run_with_position, tmp_path_factory):
    """Stessa prova su un vero bind mount read-only (saltata se l'ambiente non permette ``mount``)."""
    root, _, exits, _ = run_with_position
    ro = tmp_path_factory.mktemp("ro_view")
    if os.geteuid() != 0 or subprocess.run(["mount", "--bind", str(root), str(ro)], capture_output=True).returncode:
        pytest.skip("mount non disponibile")
    try:
        if subprocess.run(["mount", "-o", "remount,ro,bind", str(ro)], capture_output=True).returncode:
            pytest.skip("remount read-only non disponibile")
        with pytest.raises(OSError):
            (ro / "probe").write_text("x")
        with exits:
            t = NOW + 60_000
            exits.tick(t)
            assert es.exit_service_healthy(data_dir=ro, run_id=RUN, now_ms=t) is True
            assert api._brain_single_close_ready(_paths(ro), t) is True
    finally:
        subprocess.run(["umount", str(ro)], capture_output=True)
