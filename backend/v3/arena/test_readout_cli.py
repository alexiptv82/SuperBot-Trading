"""Readout da riga di comando: stessi dati verificati della dashboard, mai scritture, nessun numero inventato."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.v3.arena import readout_cli as RC
from backend.v3.arena import trial_setup as TS
from backend.v3.arena.test_trial_setup import (  # noqa: F401  (fixture condivise)
    DAY, NOW, _activate, _exits, _key_limit, _prepare, root)


def _tree_hash(base: Path) -> dict:
    return {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(base.rglob("*")) if p.is_file()}


def test_readout_before_t0_shows_no_numbers(root, capsys):
    _prepare(root)
    before = _tree_hash(root)
    assert RC.main(["--day", "2026-11-18", "--root", str(root), "--now-ms", str(NOW)]) == 0
    out = capsys.readouterr().out
    for name in ("deepseek", "qwen", "minimax"):
        assert f"== {name}" in out
    assert out.count("nessun numero mostrato") == 3
    assert "PnL realizzato" not in out
    assert _tree_hash(root) == before


def test_readout_after_activation_is_read_only_and_marks_open_pnl_as_unavailable(root, tmp_path, capsys):
    _prepare(root)
    exits, _ = _exits(root)
    try:
        _activate(root, tmp_path)
    finally:
        for w in exits.values():
            w.stop()
    before = _tree_hash(root)
    assert RC.main(["--day", "2026-11-18", "--root", str(root), "--now-ms", str(NOW + 60_000)]) == 0
    out = capsys.readouterr().out
    assert out.count("dati=VERIFIED") == 3 and out.count("capitale iniziale 2000") == 3
    assert out.count("PnL non realizzato: n.d.") == 3
    assert _tree_hash(root) == before


def test_readout_json_and_failures(root, tmp_path, capsys):
    _prepare(root)
    assert RC.main(["--day", "2026-11-18", "--root", str(root), "--json", "--now-ms", str(NOW)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["schema"] == "brain_arena_readonly_v1" and set(data["portfolios"]) == {"deepseek", "qwen", "minimax"}
    assert RC.main(["--day", "18-11-2026", "--root", str(root)]) == 2
    assert "ARENA_READOUT RESULT=FAILED_ValueError" in capsys.readouterr().out
    assert RC.main(["--day", "2026-11-18", "--root", str(tmp_path / "missing"), "--now-ms", str(NOW)]) == 0
    assert "nessun numero mostrato" in capsys.readouterr().out
