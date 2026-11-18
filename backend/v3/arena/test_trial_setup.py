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


ALIGNED = {"deepseek": ("0.30", "1.20"), "qwen": ("0.32", "1.28"), "minimax": ("0.15", "0.60")}


def _cfg(provider: str, aligned: bool = True) -> bytes:
    c = json.loads(config_path(provider).read_bytes())
    c["symbols"] = SYMS                                  # mercato sintetico: due simboli, uguali per tutte
    if aligned:                                          # prezzi al listino di picco e tetto uguale (scenario A)
        c["input_usd_per_million_tokens"], c["output_usd_per_million_tokens"] = ALIGNED[provider]
        c["daily_cap_usd"] = "3.50"
    return json.dumps(c).encode()


@pytest.fixture(autouse=True)
def _key_limit(monkeypatch):
    from decimal import Decimal
    from backend.v3.arena import openrouter_transport as ORT
    monkeypatch.setattr(ORT, "KEY_LIMIT", Decimal("60"))   # scenario: limite chiave alzato per 14 giorni


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
                approved_by="utente", approved_total_budget_usd="147")
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


def test_budget_gate_blocks_activation_with_todays_repository_configs(root, tmp_path, monkeypatch):
    """Config di oggi: prezzi Qwen/MiniMax 6-13x sopra listino, tetto 0,75 x 14 > limite chiave 2 USD."""
    from decimal import Decimal
    from backend.v3.arena import openrouter_transport as ORT
    monkeypatch.setattr(ORT, "KEY_LIMIT", Decimal("2"))
    TS.prepare_paused(root, DAY, now_ms=NOW - 60_000, desk_mode="paper", confirm=TS.PREPARE_PHRASE,
                      config_loader=lambda p: _cfg(p, aligned=False))
    exits, _ = _exits(root)
    try:
        with pytest.raises(TS.SetupRefused) as e:
            _activate(root, tmp_path)
        code = str(e.value)
        for b in ("PRICE_ESTIMATE_DISTORTS_COMPARISON:qwen", "PRICE_ESTIMATE_DISTORTS_COMPARISON:minimax",
                  "KEY_LIMIT_BELOW_TRIAL_BUDGET:qwen"):
            assert b in code
        assert "PRICE_ESTIMATE_DISTORTS_COMPARISON:deepseek" not in code      # DeepSeek allineato al listino
        with pytest.raises(TS.SetupRefused, match="TOTAL_BUDGET_NOT_APPROVED"):
            _activate(root, tmp_path, approved_total_budget_usd=None)
        assert TS.inspect(root, DAY, NOW)["stage"] == "PREPARED_PAUSED_NO_T0"
    finally:
        for w in exits.values():
            w.stop()


def test_budget_gate_rules_on_aligned_configs():
    from decimal import Decimal
    from backend.v3.arena.budget_gate import budget_gate, load_evidence
    cfgs = {p: load_runner_config(_cfg(p)) for p in ("deepseek", "qwen", "minimax")}
    ok = budget_gate(cfgs, evidence=load_evidence(), approved_total_usd=Decimal("147"), key_limit_usd=Decimal("60"))
    assert ok["blockers"] == [] and ok["worst_case_trial_usd"] == "147.00"
    low = budget_gate(cfgs, evidence=load_evidence(), approved_total_usd=Decimal("100"), key_limit_usd=Decimal("60"))
    assert low["blockers"] == ["WORST_CASE_EXCEEDS_APPROVED_BUDGET"]
    under = dict(cfgs, qwen=load_runner_config(json.dumps(dict(json.loads(_cfg("qwen")),
                                                                input_usd_per_million_tokens="0.10")).encode()))
    assert "PRICE_BELOW_LISTING:qwen" in budget_gate(under, evidence=load_evidence(), approved_total_usd=Decimal("147"),
                                                      key_limit_usd=Decimal("60"))["blockers"]


# ---------------------------------------------------------------- revisione ChatGPT PR #107 (6970648930)
def _state_files(root):
    plans = TS._plans(root, DAY)
    return {p: ((pl.folder / "mandate.json").read_bytes(), (pl.folder / "pause.flag").exists(),
                (pl.folder / T0_FILE).exists()) for p, pl in plans.items()}


@pytest.mark.parametrize("fail_at", [2, 3, "post_check"])
def test_activation_compensates_completely_on_pause_removal_or_post_check_failure(root, tmp_path, monkeypatch,
                                                                                   fail_at):
    _prepare(root)
    before = _state_files(root)
    exits, _ = _exits(root)
    if fail_at == "post_check":
        real_inspect, calls = TS.inspect, {"n": 0}

        def flaky_inspect(*a, **k):
            calls["n"] += 1
            r = real_inspect(*a, **k)
            return dict(r, stage="INCONSISTENT") if calls["n"] == 2 else r     # la 2a chiamata e' il post-check
        monkeypatch.setattr(TS, "inspect", flaky_inspect)
    else:
        real_remove, n = TS._remove_pause, {"n": 0}

        def flaky_remove(path):
            n["n"] += 1
            if n["n"] == fail_at:
                raise OSError("io_error")
            real_remove(path)
        monkeypatch.setattr(TS, "_remove_pause", flaky_remove)
    try:
        with pytest.raises((OSError, TS.SetupRefused)):
            _activate(root, tmp_path)
    finally:
        for w in exits.values():
            w.stop()
    assert _state_files(root) == before                       # mandati originali, tre pause, nessun T0
    monkeypatch.undo()
    assert TS.inspect(root, DAY, NOW)["stage"] == "PREPARED_PAUSED_NO_T0"


@pytest.mark.parametrize("which", ["staging", "final"])
def test_prepare_check_failure_moves_back_only_its_own_runs(root, monkeypatch, which):
    real = TS.inspect

    def bad(r, day, now_ms):
        out = real(r, day, now_ms)
        hit = (".staging-" in str(r)) if which == "staging" else (r == root)
        return dict(out, stage="INCONSISTENT") if hit else out
    monkeypatch.setattr(TS, "inspect", bad)
    with pytest.raises(TS.SetupRefused):
        _prepare(root)
    runs = [x for x in root.rglob("brain-*-paper*")]
    assert runs == [] and not any(x.name.startswith(".staging-") for x in root.iterdir())
    monkeypatch.undo()
    assert _prepare(root)["stage"] == "PREPARED_PAUSED_NO_T0"          # riesecuzione possibile


def test_open_positions_count_and_exit_stop_gate(root, tmp_path):
    _prepare(root)
    assert all(TS.exit_stop_check(root, DAY, p)["open_positions"] == 0 for p in ("deepseek", "qwen", "minimax"))
    exits, gj = _exits(root)
    try:
        _activate(root, tmp_path)
        plan = TS._plans(root, DAY)["qwen"]
        R.build_arena_runner(plan, environ=ENV, clock_ms=lambda: NOW, get_json=gj, inner_transport=PolicyModel(),
                             view_params=VIEW).runner.tick(NOW)
        chk = TS.exit_stop_check(root, DAY, "qwen")
        assert chk == {"provider": "qwen", "run_id": plan.run_id, "open_positions": 2, "exit_stop_allowed": False}
        assert TS.main(["can-stop-exit", "--provider", "qwen", "--root", str(root), "--day", "2026-11-18"],
                       env={}, now_fn=lambda: NOW) == 2
        assert TS.inspect(root, DAY, NOW)["providers"]["qwen"]["open_positions"] == 2
        for minute in range(1, 26):
            exits["qwen"].tick(NOW + minute * M)
        assert TS.exit_stop_check(root, DAY, "qwen")["exit_stop_allowed"] is True
        assert TS.main(["can-stop-exit", "--provider", "qwen", "--root", str(root), "--day", "2026-11-18"],
                       env={}, now_fn=lambda: NOW) == 0
    finally:
        for w in exits.values():
            w.stop()
    # journal manomesso: conteggio sconosciuto, stop delle uscite NON consentito
    import sqlite3
    con = sqlite3.connect(plan.journal)
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
        con.execute(f"DROP TRIGGER {name}")                     # manomissione diretta del file, non via codice
    con.execute("UPDATE v3_events SET payload_json = replace(payload_json, 'BTCUSDT', 'XXXUSDT') WHERE kind='paper_open'")
    con.commit()
    con.close()
    chk = TS.exit_stop_check(root, DAY, "qwen")
    assert chk["open_positions"] == "UNKNOWN" and chk["exit_stop_allowed"] is False
    assert "qwen:OPEN_POSITIONS_UNKNOWN" in TS.inspect(root, DAY, NOW)["blockers"]


def test_runner_refuses_when_t0_files_disagree_between_runs(root, tmp_path):
    _prepare(root)
    exits, gj = _exits(root)
    try:
        _activate(root, tmp_path)
    finally:
        for w in exits.values():
            w.stop()
    plans = TS._plans(root, DAY)
    t0 = json.loads((plans["minimax"].folder / T0_FILE).read_text())
    (plans["minimax"].folder / T0_FILE).write_text(json.dumps(dict(t0, trial_start_ms=NOW + 1), sort_keys=True,
                                                              separators=(",", ":")))
    for p in ("qwen", "minimax"):                             # anche la run "intatta" rifiuta: discordanza nel trio
        with pytest.raises(R.ArenaRunnerError, match="arena_t0_inconsistent"):
            R.build_arena_runner(plans[p], environ=ENV, clock_ms=lambda: NOW, inner_transport=PolicyModel())
