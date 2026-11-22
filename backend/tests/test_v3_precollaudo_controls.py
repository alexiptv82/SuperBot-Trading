"""Pacchetto di pre-collaudo (deploy/brain-unico/precollaudo): controlli in sola lettura su una run preparata davvero.
Distingue il blocco per mandato assente dal blocco per servizio delle uscite non sano. Nessuna rete, nessun servizio."""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

from backend.v3.runner.prepare_paper_run import main as prepare_main

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("precollaudo_controlli", ROOT / "deploy/brain-unico/precollaudo/controlli.py")
C = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = C
_spec.loader.exec_module(C)
RUN_ID = "brain-unico-paper-rc1"


def _prepared(tmp_path, monkeypatch):
    monkeypatch.setenv("DESK_MODE", "paper")
    cfg = ROOT / "backend/v3/runner/runner_config_brain_unico_paper_b.json"
    assert prepare_main(["--parent", str(tmp_path), "--run-name", "brain-v3-unico-paper-rc1", "--run-id", RUN_ID,
                         "--config", str(cfg), "--prepare-paper-paused", "--expected-initial-equity", "2000"],
                        env={"DESK_MODE": "paper"}) == 0
    return tmp_path / "brain-v3-unico-paper-rc1"


def test_mandate_block_passes_but_unhealthy_exits_fail_the_controls(tmp_path, monkeypatch, capsys):
    run = _prepared(tmp_path, monkeypatch)
    (run / "heartbeat.json").write_text(json.dumps({"ts_ms": int(time.time() * 1000), "state": "halted",
                                                    "last_error": "halted:mandate_not_approved"}))
    rc = C.main(["x", str(run), RUN_ID])
    out = capsys.readouterr().out
    assert rc == 1                                                    # nessun servizio delle uscite: FAIL
    assert "PASS  motivo del runner = mandato" in out                 # il motivo del runner resta il mandato...
    assert "FAIL  uscite sane" in out                                 # ...ma le uscite non sane si vedono comunque
    assert "PASS  mandato approved:false" in out and "PASS  nessuna spesa AI" in out
    assert C.main(["x", str(run), RUN_ID, "uscite"]) == 1


def test_missing_heartbeat_is_a_fail_not_a_crash(tmp_path, monkeypatch, capsys):
    run = _prepared(tmp_path, monkeypatch)
    assert C.main(["x", str(run), RUN_ID]) == 1
    assert "FAIL  runner fermo (halted)" in capsys.readouterr().out
