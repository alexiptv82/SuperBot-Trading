"""Backup a caldo durante la gara: servizi uscite attivi, scritture concorrenti, ripristino verificato e memoria."""
from __future__ import annotations

import json
import shutil
import sqlite3
import threading

import pytest

from backend.v3.arena import backup as B
from backend.v3.arena import manual_close as MC
from backend.v3.arena import runner as R
from backend.v3.arena import trial_setup as TS
from backend.v3.arena.learning_evidence import collect_arena_learning_evidence
from backend.v3.arena.read_view import read_wallet
from backend.v3.arena.test_arena_runner import ENV, PolicyModel
from backend.v3.arena.test_trial_setup import DAY, NOW, VIEW, _activate, _exits, _key_limit, _prepare  # noqa: F401
from backend.v3.budget import BudgetLedger


@pytest.fixture
def live(tmp_path):
    root = tmp_path / "arena"
    root.mkdir(mode=0o700)
    _prepare(root)
    exits, gj = _exits(root)
    _activate(root, tmp_path)
    plans = TS._plans(root, DAY)
    for p, plan in plans.items():
        R.build_arena_runner(plan, environ=ENV, clock_ms=lambda: NOW, get_json=gj, inner_transport=PolicyModel(),
                             view_params=VIEW).runner.tick(NOW)
    pid = read_wallet(plans["qwen"], NOW + 1)["open_positions"][0]["position_id"]
    MC.request_close(plans["qwen"], position_id=pid, request_id="req-0000000000000001", now_ms=NOW + 1)
    exits["qwen"].tick(NOW + 5_000)
    MC.annotate(plans["qwen"], request_id="req-0000000000000001", reason="trend_change", note="privata",
                now_ms=NOW + 6_000)
    yield root, plans, exits
    for w in exits.values():
        w.stop()


def test_hot_snapshot_with_wal_and_concurrent_writers_restores_identically(live, tmp_path):
    root, plans, exits = live
    # budget.db e' in WAL: una scrittura confermata ma non ancora riversata deve finire nella copia
    led = BudgetLedger(str(plans["minimax"].folder / "budget.db"))
    led.record_spend("minimax", 1234, {"basis": "test"})
    assert (plans["minimax"].folder / "budget.db-wal").exists()
    stop = threading.Event()

    def writer():                                       # scritture concorrenti sul registro e sul budget
        n = 0
        while not stop.is_set() and n < 200:
            led.record_spend("minimax", 1, {"basis": "concurrent"})
            n += 1
    t = threading.Thread(target=writer)
    t.start()
    try:
        out = B.snapshot_all(root, DAY, tmp_path / "bk")
    finally:
        stop.set()
        t.join()
        led.close()
    assert set(out) == {"deepseek", "qwen", "minimax"}
    copy = tmp_path / "bk" / "minimax" / plans["minimax"].run_id
    assert not (copy / "budget.db-wal").exists()
    spent = sqlite3.connect(copy / "budget.db").execute("SELECT units FROM spend_events WHERE units=1234").fetchall()
    assert spent == [(1234,)]
    # ripristino: la copia diventa una radice Arena e la memoria si estrae uguale all'originale
    restored = tmp_path / "restored"
    shutil.copytree(tmp_path / "bk", restored)
    rplans = TS._plans(restored, DAY)
    for p in plans:
        assert read_wallet(rplans[p], NOW + 7_000)["realized_pnl"] == read_wallet(plans[p], NOW + 7_000)["realized_pnl"]
    a = collect_arena_learning_evidence(tuple(plans.values()), NOW + 7_000)
    b = collect_arena_learning_evidence(tuple(rplans.values()), NOW + 7_000)
    diff = {p: [k for k in a["providers"][p] if k != "source_journal"   # solo il percorso cambia
                and a["providers"][p][k] != b["providers"][p][k]] for p in a["providers"]}
    assert diff == {p: [] for p in a["providers"]}, diff
    assert "privata" not in json.dumps(b)
    assert b["providers"]["qwen"]["verified_human_annotation_count"] == 1


def test_tampered_or_incomplete_backup_is_refused(live, tmp_path):
    root, plans, exits = live
    B.snapshot_all(root, DAY, tmp_path / "bk")
    with pytest.raises(B.BackupError, match="destination_exists"):     # mai sovrascrivere un backup
        B.snapshot_all(root, DAY, tmp_path / "bk")
    copy = tmp_path / "bk" / "qwen" / plans["qwen"].run_id
    with (copy / MC.ANNOTATIONS_FILE).open("a") as fh:
        fh.write("{}\n")
    with pytest.raises(B.BackupError, match="hash_mismatch"):
        B.verify_run_backup(copy)
    (copy / MC.ANNOTATIONS_FILE).unlink()
    with pytest.raises(B.BackupError, match="file_set_changed"):
        B.verify_run_backup(copy)


def test_cli_snapshot_and_verify(live, tmp_path, capsys):
    root, plans, exits = live
    assert B.main(["snapshot", "--root", str(root), "--day", "2026-11-18", "--dest", str(tmp_path / "c")]) == 0
    assert B.main(["verify", "--dest", str(tmp_path / "c")]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert all(json.loads(x)["ok"] for x in out)
