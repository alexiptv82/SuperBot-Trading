"""L'esportatore legge una run vera (motore reale, modello finto) senza scrivere nulla nella cartella."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from backend.tests.test_v3_runner_e2e import G, VIEW, _get_json_factory
from backend.v3.arena import runner as R
from backend.v3.arena.test_arena_runner import ENV, M, PolicyModel, _approve_and_unpause, _prepare
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.exit_worker import build_exit_worker
from research.brain_guardian import journal_export as JE


def _fingerprint(folder: Path):
    # "-shm" e' l'indice di memoria condivisa del WAL: qualunque lettore SQLite (anche mode=ro) lo aggiorna.
    # Non contiene dati; tutti gli altri file devono restare identici byte per byte.
    # Leggere un DB in WAL puo' anche creare un "-wal" VUOTO se mancava: ammesso solo se di 0 byte.
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())
            if p.is_file() and not p.name.endswith("-shm")
            and not (p.name.endswith("-wal") and p.stat().st_size == 0)}


def _run_with_trades(tmp_path):
    root = tmp_path / "arena"
    root.mkdir()
    plan = _prepare(root, "qwen")
    _approve_and_unpause(plan)
    gj = _get_json_factory()
    cfg = load_runner_config((plan.folder / "runner_config.json").read_bytes())
    exits = build_exit_worker(data_dir=plan.folder, run_id=plan.run_id, config=cfg, get_json=gj)
    with exits:
        exits.tick(G + 25_000)
        R.build_arena_runner(plan, environ=ENV, clock_ms=lambda: G + 25_000, get_json=gj,
                             inner_transport=PolicyModel(), view_params=VIEW).runner.tick(G + 25_000)
        for minute in range(1, 26):
            exits.tick(G + minute * M + 25_000)
    return plan


def test_export_is_trade_level_read_only_and_text_free(tmp_path):
    plan = _run_with_trades(tmp_path)
    before = _fingerprint(plan.folder)
    out = tmp_path / "export.json"
    rc = subprocess.run([sys.executable, "-I", JE.__file__, "--run-dir", str(plan.folder), "--run-id", plan.run_id,
                         "--out", str(out)], capture_output=True, text=True)
    assert rc.returncode == 0, rc.stderr
    assert _fingerprint(plan.folder) == before                     # nessuna scrittura nella run
    data = json.loads(out.read_text())
    assert data["schema"] == "brain_journal_export_v1" and len(data["trades"]) == 2
    for t in data["trades"]:
        assert t["close"] and t["close"]["reason"] in ("stop", "take_profit")
        assert t["decision"]["regime"] and t["decision"]["status"] == "APPROVED"
        assert t["decision"]["confidence_journaled"] is False      # lacuna reale: confidenza non registrata
        assert float(t["close"]["fees"]) > 0
    assert data["orphan_closes"] == [] and data["decisions_by_hour"]
    again = subprocess.run([sys.executable, "-I", JE.__file__, "--run-dir", str(plan.folder), "--run-id", plan.run_id,
                            "--out", str(out)], capture_output=True, text=True)
    assert again.returncode == 2 and "output_exists" in again.stdout


def test_free_text_is_never_exported():
    assert JE._code("risk_quote_ok") == "risk_quote_ok"
    assert JE._code("Il prezzo sale perche' ...") is None and JE._code("x" * 65) is None


def test_replay_reproduces_the_real_exit_engine_on_the_same_bars(tmp_path):
    """Fedelta': il replay A sugli ingressi esportati riproduce motivo, minuto e PnL netto del servizio uscite vero."""
    from backend.tests.test_v3_runner_e2e import _world
    from research.brain_guardian import experiment as X
    plan = _run_with_trades(tmp_path)
    out = tmp_path / "export.json"
    JE.main(["--run-dir", str(plan.folder), "--run-id", plan.run_id, "--out", str(out)])
    bars_dir = tmp_path / "bars"
    bars_dir.mkdir()
    for sym, per in _world().items():
        (bars_dir / f"{sym}_1m.csv").write_text("ts,o,h,l,c,v\n" + "".join(
            f"{b.open_time_ms},{b.open},{b.high},{b.low},{b.close},{b.volume}\n" for b in per["1m"]))
    rep = tmp_path / "rep.json"
    assert X.main(["brain", "--bars", str(bars_dir), "--export", str(out), "--out", str(rep)]) == 0
    r = json.loads(rep.read_text())
    assert r["fidelity_reason_match"] == 1.0 and len(r["fidelity"]) == 2
    for f in r["fidelity"]:
        assert abs(f["pnl_real"] - f["pnl_replay"]) < 1e-6 * max(1, abs(f["pnl_real"])) + 0.01, f
        assert f["close_delay_min"] == 0, f                         # stessa candela d'uscita, nessun ritardo
    assert r["late_exits"] == 0
