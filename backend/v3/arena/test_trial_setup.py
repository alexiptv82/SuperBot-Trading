"""Tre run PAPER: preparazione atomica in pausa, attivazione simultanea, emergenza con posizioni aperte.
Dati sintetici, servizi uscite veri in processo, modello finto, nessuna rete, nessuna spesa."""
from __future__ import annotations

import json
from datetime import date

import pytest

from backend.tests.test_v3_runner_e2e import G, VIEW, _get_json_factory
from backend.v3.arena import runner as R
from backend.v3.arena import trial_setup as TS
from backend.v3.arena.prepare import config_path
from backend.v3.arena.read_view import read_wallet
from backend.v3.arena.t0 import T0_FILE
from backend.v3.arena.test_arena_runner import ENV, M, PolicyModel, _kinds
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.exit_worker import build_exit_worker

DAY = date(2026, 11, 18)
NOW = G + 25_000
SYMS = ["BTCUSDT", "ETHUSDT"]


def _cfg(provider: str) -> bytes:
    c = json.loads(config_path(provider).read_bytes())
    c["symbols"] = SYMS                                  # mercato sintetico: due simboli, uguali per tutte
    return json.dumps(c).encode()


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "arena"
    r.mkdir(mode=0o700)
    return r


def _prepare(root):
    return TS.prepare_paused(root, DAY, now_ms=NOW - 60_000, desk_mode="paper", confirm=TS.PREPARE_PHRASE,
                             config_loader=_cfg)


def _snapshot(tmp_path, symbols=SYMS, as_of=NOW - 60_000):
    path = tmp_path / f"universe-{as_of}-{len(symbols)}.json"
    path.write_text(json.dumps({"schema": "arena_universe_snapshot_v1", "symbols": symbols,
                                "crypto_target_met": True, "as_of_ms": as_of}))
    return path


def _exits(root):
    gj = _get_json_factory()
    out = {}
    for p, plan in TS._plans(root, DAY).items():
        cfg = load_runner_config((plan.folder / "runner_config.json").read_bytes())
        w = build_exit_worker(data_dir=plan.folder, run_id=plan.run_id, config=cfg, get_json=gj)
        w.start()
        w.tick(NOW)
        out[p] = w
    return out, gj


def _activate(root, tmp_path, **kw):
    args = dict(t0_ms=NOW, now_ms=NOW, desk_mode="paper", confirm=f"{TS.ACTIVATE_PREFIX}{NOW}",
                approved_by="utente")
    args.update(kw)
    if "universe_snapshot" not in args:
        args["universe_snapshot"] = _snapshot(tmp_path)
    return TS.activate(root, DAY, **args)


def test_inspect_on_an_empty_root_is_read_only(root):
    r = TS.inspect(root, DAY, NOW)
    assert r["stage"] == "NOT_PREPARED" and r["read_only"] is True and list(root.iterdir()) == []


def test_prepare_creates_three_identical_paused_runs_without_t0(root):
    with pytest.raises(TS.SetupRefused, match="confirmation_required"):
        TS.prepare_paused(root, DAY, now_ms=NOW, desk_mode="paper", confirm="si", config_loader=_cfg)
    with pytest.raises(TS.SetupRefused, match="paper_only"):
        TS.prepare_paused(root, DAY, now_ms=NOW, desk_mode="live", confirm=TS.PREPARE_PHRASE, config_loader=_cfg)
    rep = _prepare(root)
    assert rep["stage"] == "PREPARED_PAUSED_NO_T0" and rep["blockers"] == []
    assert sorted(x.name for x in root.iterdir()) == ["deepseek", "minimax", "qwen"]     # nessuno staging residuo
    for p, row in rep["providers"].items():
        assert row["paused"] and not row["mandate_approved"] and row["t0_in_manifest"] is None
        assert row["event_kinds"] == ["run_prepared"] and row["capital"] == "2000" and row["budget_db"]
        plan = TS._plans(root, DAY)[p]
        view = read_wallet(plan, NOW)
        assert view["state"] == "not_started" and view["data_status"] == "PREPARED_AWAITING_T0"
        assert view["realized_pnl"] is None                                  # nessun numero inventato
        with pytest.raises(R.ArenaRunnerError, match="arena_t0_not_assigned"):
            R.build_arena_runner(plan, environ=ENV, clock_ms=lambda: NOW, inner_transport=PolicyModel())
    with pytest.raises(TS.SetupRefused, match="run_already_exists"):            # mai sovrascrivere
        _prepare(root)


def test_prepare_failure_leaves_nothing_behind_and_existing_run_blocks_everything(root):
    def broken(p):
        return b"{}" if p == "minimax" else _cfg(p)
    with pytest.raises(Exception):
        TS.prepare_paused(root, DAY, now_ms=NOW, desk_mode="paper", confirm=TS.PREPARE_PHRASE, config_loader=broken)
    assert list(root.iterdir()) == []
    (root / "qwen" / "brain-qwen-paper20261118").mkdir(parents=True)          # una run "di qualcun altro"
    with pytest.raises(TS.SetupRefused, match="run_already_exists"):
        _prepare(root)
    assert sorted(x.name for x in root.iterdir()) == ["qwen"]


def test_prepare_refuses_different_universe_or_risk_between_ais(root):
    def other(p):
        c = json.loads(_cfg(p))
        if p == "qwen":
            c["symbols"] = ["BTCUSDT"]
        return json.dumps(c).encode()
    with pytest.raises(TS.SetupRefused, match="universe_differs"):
        TS.prepare_paused(root, DAY, now_ms=NOW, desk_mode="paper", confirm=TS.PREPARE_PHRASE, config_loader=other)


def test_activate_refuses_without_authorization_healthy_exits_fresh_universe_or_current_t0(root, tmp_path):
    _prepare(root)
    with pytest.raises(TS.SetupRefused, match="confirmation_required"):
        _activate(root, tmp_path, confirm="AVVIA")
    with pytest.raises(TS.SetupRefused, match="exit_service_not_healthy"):
        _activate(root, tmp_path)                                            # servizi uscite spenti
    exits, _ = _exits(root)
    try:
        with pytest.raises(TS.SetupRefused, match="t0_must_be_now"):
            _activate(root, tmp_path, t0_ms=NOW - 3_600_000, confirm=f"{TS.ACTIVATE_PREFIX}{NOW - 3_600_000}")
        with pytest.raises(TS.SetupRefused, match="universe_snapshot"):
            _activate(root, tmp_path, universe_snapshot=_snapshot(tmp_path, as_of=NOW - 7 * 3_600_000))
        with pytest.raises(TS.SetupRefused, match="universe_snapshot"):
            _activate(root, tmp_path, universe_snapshot=_snapshot(tmp_path, symbols=["BTCUSDT"]))
        assert TS.inspect(root, DAY, NOW)["stage"] == "PREPARED_PAUSED_NO_T0"   # niente e' cambiato
    finally:
        for w in exits.values():
            w.stop()


def test_activation_failure_midway_rolls_everything_back(root, tmp_path, monkeypatch):
    _prepare(root)
    exits, _ = _exits(root)
    real = TS._atomic_write
    calls = {"n": 0}

    def flaky(path, data):
        calls["n"] += 1
        if path.name == "mandate.json" and calls["n"] == 6:                   # terzo mandato
            raise OSError("disk_full")
        return real(path, data)
    monkeypatch.setattr(TS, "_atomic_write", flaky)
    try:
        with pytest.raises(OSError):
            _activate(root, tmp_path)
    finally:
        for w in exits.values():
            w.stop()
    rep = TS.inspect(root, DAY, NOW)
    assert rep["stage"] == "PREPARED_PAUSED_NO_T0"
    assert all(not (TS._plans(root, DAY)[p].folder / T0_FILE).exists() for p in rep["providers"])


def test_simultaneous_activation_then_emergency_stop_keeps_exits_running(root, tmp_path):
    """P0 ChatGPT: in emergenza si fermano le NUOVE aperture (pausa), mai i servizi uscite con posizioni aperte."""
    _prepare(root)
    exits, gj = _exits(root)
    try:
        rep = _activate(root, tmp_path)
        assert rep["stage"] == "ACTIVE"
        t0s = {json.loads((p.folder / T0_FILE).read_text())["trial_start_ms"] for p in TS._plans(root, DAY).values()}
        assert t0s == {NOW}
        plans = TS._plans(root, DAY)
        models = {p: PolicyModel() for p in plans}
        for p, plan in plans.items():                                       # stesso minuto per le tre AI
            built = R.build_arena_runner(plan, environ=ENV, clock_ms=lambda: NOW, get_json=gj,
                                         inner_transport=models[p], view_params=VIEW)
            assert built.runner.tick(NOW).cycle.opened
            assert read_wallet(plan, NOW + 1)["trial_start_ms"] == NOW
        # emergenza: pausa alle tre run (stop delle nuove aperture), servizi uscite ancora vivi
        for plan in plans.values():
            (plan.folder / "pause.flag").write_text("emergency\n")
        before = {p: len(m.payloads) for p, m in models.items()}
        for p, plan in plans.items():
            again = R.build_arena_runner(plan, environ=ENV, clock_ms=lambda: NOW + 60 * M, get_json=gj,
                                         inner_transport=models[p], view_params=VIEW)
            assert again.runner.tick(NOW + 60 * M).state == "halted"
        assert {p: len(m.payloads) for p, m in models.items()} == before   # nessuna chiamata al modello
        for minute in range(1, 26):                                         # stop/target gestiti lo stesso
            for w in exits.values():
                w.tick(NOW + minute * M)
        for plan in plans.values():
            assert len(_kinds(plan, "paper_close")) == len(_kinds(plan, "paper_open")) > 0
    finally:
        for w in exits.values():
            w.stop()


def test_cli_defaults_to_read_only_inspect(root, capsys):
    rc = TS.main(["--root", str(root), "--day", "2026-11-18"], env={}, now_fn=lambda: NOW)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["command"] == "inspect" and out["stage"] == "NOT_PREPARED"
    assert TS.main(["prepare-paused", "--root", str(root), "--day", "2026-11-18"], env={"DESK_MODE": "paper"},
                   now_fn=lambda: NOW) == 2                                  # senza frase di conferma
    assert list(root.iterdir()) == []
