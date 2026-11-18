"""Prova a secco: un ciclo per AI sulle copie, NO_TRADE, run vere intatte byte per byte."""
from __future__ import annotations

import hashlib

from backend.tests.test_v3_runner_e2e import G, VIEW, _get_json_factory
from backend.v3.arena import smoke as S
from backend.v3.arena import trial_setup as TS
from backend.v3.arena.test_trial_setup import DAY, _key_limit, _prepare  # noqa: F401


def _fp(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*"))
            if p.is_file() and not p.name.endswith(("-shm", "-wal"))}


def test_smoke_runs_one_cycle_per_ai_on_copies_without_touching_the_race(tmp_path):
    root = tmp_path / "arena"
    root.mkdir(mode=0o700)
    _prepare(root)
    before = _fp(root)
    res = S.run_smoke(root, DAY, now_fn=lambda: G + 25_000, get_json=_get_json_factory(), view_params=VIEW,
                      workdir=tmp_path)
    assert _fp(root) == before and res["real_runs_untouched"] is True
    for p, r in res["providers"].items():
        assert r["state"] == "running" and r["opened"] == 0, (p, r)
        assert r["model_calls"] == r["decisions"] == 2 and r["errors_by_code"] == {}
    assert TS.inspect(root, DAY, G + 25_000)["stage"] == "PREPARED_PAUSED_NO_T0"
    assert not list(tmp_path.glob("arena-smoke-*"))                     # copia eliminata
