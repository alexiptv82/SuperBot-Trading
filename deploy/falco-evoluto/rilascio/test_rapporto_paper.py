"""Rapporto PAPER: sola lettura, nessuna scrittura nelle run, limiti segnalati."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from backend.tests.test_v3_compare_view import _run
from backend.v3.events import Event, EventJournal

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def _tree(d):
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*")) if p.is_file()}


def test_report_reads_copies_only_and_flags_limits(tmp_path):
    f = _run(tmp_path, "brain-v3-falco-evoluto-p1", "runner_config_falco_evoluto_paper.json", [(1, None, None, None)])
    s = _run(tmp_path, "brain-v3-brain-scalp-p1", "runner_config_brain_scalp_paper.json", [])
    for d, rid in ((f, "brain-v3-falco-evoluto-p1"), (s, "brain-v3-brain-scalp-p1")):
        (d / "mandate.json").write_text(json.dumps({"approved": True, "approved_by": "Nome Segreto"}))
    # gli id di run della fixture sono i nomi delle cartelle: il rapporto usa quelli veri, quindi rinomina
    j = EventJournal(str(f / "journal.db"))
    j.append(Event("x.1", "brain", "falco-evoluto-paper-p1", "paper_open", 1_800_000_100_000, "t",
                   {"position_id": "p9", "symbol": "ETHUSDT", "side": -1, "fill_price": "100", "quantity": "1",
                    "margin_used": "300", "leverage": 50, "stop_price": "160"}))
    before = _tree(tmp_path)
    env = dict(os.environ, RAPPORTO_PARENT=str(tmp_path), PYTHONPATH=str(REPO))
    p = subprocess.run([sys.executable, str(HERE / "rapporto_paper.py")], capture_output=True, text=True, env=env,
                       timeout=60)
    assert p.returncode == 0, p.stderr
    out = p.stdout
    assert "catena VERIFICATA" in out and "FINE RAPPORTO" in out and "Nome Segreto" not in out
    assert "LEVA_FUORI_LIMITE" in out and "MARGINE_FUORI_LIMITE" in out and "RISCHIO_OLTRE_4%" in out
    assert "===== rc1" in out and "RUN ASSENTE" in out
    assert _tree(tmp_path) == before                     # nessuna scrittura nelle run
