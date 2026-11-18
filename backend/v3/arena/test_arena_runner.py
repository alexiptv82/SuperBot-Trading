"""Runner PAPER dell'Arena: preparazione, apertura, uscite, ripartenza e lettura per provider. Solo dati sintetici,
modello finto, nessuna rete, nessun ordine."""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from backend.tests.test_v3_runner_e2e import G, VIEW, FakeModel, _get_json_factory
from backend.v3.arena import openrouter_transport as ORT
from backend.v3.arena import prepare as P
from backend.v3.arena import runner as R
from backend.v3.arena.read_view import read_wallet
from backend.v3.brain_f3.providers import ProviderUnavailable
from backend.v3.runner.exit_worker import build_exit_worker
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.wiring import mandate_template

DAY = date(2026, 11, 18)


class PolicyModel(FakeModel):
    """Come FakeModel (BTC LONG, ETH SHORT) ma con stop allo 0,8%: compatibile con leva minima 20x del mandato."""

    def __call__(self, payload):
        from decimal import Decimal as D
        from backend.v3.brain_f3.providers import TransportResponse
        self.payloads.append(json.loads(json.dumps(payload)))
        info = json.loads(payload["messages"][1]["content"])
        price, long_ = D(info["price"]), info["symbol"] == "BTCUSDT"
        content = json.dumps({"kind": "OPEN", "side": 1 if long_ else -1, "entry_price": str(price),
                              "stop_price": str(price * (D("0.992") if long_ else D("1.008"))), "leverage": 20,
                              "confidence": 0.8, "strategy_id": "S25", "strategy_origin": "library"})
        return TransportResponse(200, {"choices": [{"finish_reason": "stop", "message": {"content": content}}],
                                       "usage": {"prompt_tokens": 2500, "completion_tokens": 60}})
M = 60_000
ENV = {"DESK_MODE": "paper"}


def _config_bytes(provider: str) -> bytes:
    """La configurazione vera del provider, ristretta ai due simboli del mercato sintetico."""
    c = json.loads(P.config_path(provider).read_bytes())
    c["symbols"] = ["BTCUSDT", "ETHUSDT"]
    return json.dumps(c).encode()


def _prepare(root: Path, provider: str):
    plan = P.plan_for(provider, DAY, root)
    P.prepare_arena_run(plan, config_bytes=_config_bytes(provider), desk_mode="paper", now_ms=G - 10_000,
                        trial_start_ms=G - 5_000, expected_initial_equity="2000")
    return plan


def _approve_and_unpause(plan):
    cfg = load_runner_config((plan.folder / "runner_config.json").read_bytes())
    m = mandate_template(cfg.risk_policy, plan.run_id)
    m.update(approved=True, approved_by="test")
    (plan.folder / "mandate.json").write_text(json.dumps(m))
    (plan.folder / "pause.flag").unlink()
    return cfg


def _kinds(plan, kind):
    con = sqlite3.connect(plan.journal.as_uri() + "?mode=ro", uri=True)
    try:
        return [json.loads(p) for (p,) in con.execute(
            "SELECT payload_json FROM v3_events WHERE run_id=? AND kind=? ORDER BY seq", (plan.run_id, kind))]
    finally:
        con.close()


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "arena"
    r.mkdir()
    return r


def test_three_configs_share_one_risk_mandate_and_the_capital():
    h = P.shared_policy_hash()
    for p in ("deepseek", "qwen", "minimax"):
        cfg = load_runner_config(P.config_path(p).read_bytes())
        assert cfg.initial_equity == 2000 and cfg.risk_policy.minimum_equity == 450
        assert cfg.model == P.plan_for(p, DAY, Path("/x")).model
    assert len(h) == 16


def test_prepare_creates_a_paused_unapproved_isolated_run(root):
    plan = _prepare(root, "qwen")
    assert plan.folder == root / "qwen" / "brain-qwen-paper20261118"
    assert (plan.folder / "pause.flag").is_file()
    assert json.loads((plan.folder / "mandate.json").read_text())["approved"] is False
    man = json.loads((plan.folder / "arena_manifest.json").read_text())
    assert man["provider"] == "qwen" and man["experiment"] == "independent" and man["initial_capital"] == "2000"
    with pytest.raises(P.RunPreparationError):            # mai sovrascrivere una run esistente
        _prepare(root, "qwen")
    with pytest.raises(P.RunPreparationError):            # il config di un altro modello non entra in questa run
        P.prepare_arena_run(P.plan_for("minimax", DAY, root), config_bytes=_config_bytes("qwen"), desk_mode="paper",
                            now_ms=G, trial_start_ms=G, expected_initial_equity="2000")
    with pytest.raises(P.RunPreparationError):
        P.prepare_arena_run(P.plan_for("minimax", DAY, root), config_bytes=_config_bytes("minimax"), desk_mode="live",
                            now_ms=G, trial_start_ms=G, expected_initial_equity="2000")


def test_prepare_refuses_existing_portfolio_roots():
    for bad in (Path("/opt/superbot-v3-paper-runs/arena"), Path("/opt/superbot-desk-data")):
        with pytest.raises(P.RunPreparationError):
            P.prepare_arena_run(P.plan_for("qwen", DAY, bad), config_bytes=_config_bytes("qwen"), desk_mode="paper",
                                now_ms=G, trial_start_ms=G, expected_initial_equity="2000")


def test_qwen_opens_and_exits_with_its_own_provenance_budget_and_journal(root):
    plan = _prepare(root, "qwen")
    _approve_and_unpause(plan)
    gj = _get_json_factory()
    model = PolicyModel()
    built = R.build_arena_runner(plan, environ=ENV, clock_ms=lambda: G + 25_000, get_json=gj,
                                 inner_transport=model, view_params=VIEW)
    cfg = load_runner_config((plan.folder / "runner_config.json").read_bytes())
    exits = build_exit_worker(data_dir=plan.folder, run_id=plan.run_id, config=cfg, get_json=gj)
    with exits:
        exits.tick(G + 25_000)
        t = built.runner.tick(G + 25_000)
        assert t.state == "running" and t.cycle.errors == ()
        assert len(t.cycle.opened) >= 1 and len(model.payloads) == 2
        assert {p["model"] for p in model.payloads} == {"qwen/qwen3.7-plus"}
        decisions = _kinds(plan, "brain_decision")
        assert decisions and all(d["originating_ai"] == "qwen" for d in decisions)
        opens = _kinds(plan, "paper_open")
        assert opens and all(o["originating_ai"] == "qwen" for o in opens)
        for minute in range(1, 26):                         # target BTC al minuto 17, stop ETH al 21
            exits.tick(G + minute * M + 25_000)
    closes = _kinds(plan, "paper_close")
    assert len(closes) == len(opens)
    spent = sqlite3.connect((plan.folder / "budget.db").as_uri() + "?mode=ro", uri=True).execute(
        "SELECT DISTINCT provider FROM spend_events").fetchall()
    assert spent == [("qwen",)]
    trace = [json.loads(x) for x in (plan.folder / "inference_trace.jsonl").read_text().splitlines()]
    assert len(trace) == len(model.payloads) and all(t["model"] == "qwen/qwen3.7-plus" for t in trace)
    assert all(t["prompt_tokens"] == 2500 and t["completion_tokens"] == 60 for t in trace)
    assert all(t["reasoning_params_sent"] == {} for t in trace)          # qwen: "omit" -> nessun parametro
    assert all("content" not in json.dumps(t) and "messages" not in t for t in trace)
    view = read_wallet(plan, G + 30 * M)
    assert view["data_status"] == "VERIFIED" and view["portfolio_id"] == "qwen"
    assert view["total_closed"] == len(closes) and view["open_count"] == 0
    assert view["decision_count"] == len(decisions)


def test_restart_continues_from_the_persistent_journal_without_duplicates(root):
    plan = _prepare(root, "minimax")
    _approve_and_unpause(plan)
    gj = _get_json_factory()
    cfg = load_runner_config((plan.folder / "runner_config.json").read_bytes())
    exits = build_exit_worker(data_dir=plan.folder, run_id=plan.run_id, config=cfg, get_json=gj)
    with exits:
        exits.tick(G + 25_000)
        first = R.build_arena_runner(plan, environ=ENV, clock_ms=lambda: G + 25_000, get_json=gj,
                                     inner_transport=PolicyModel(), view_params=VIEW)
        first.runner.tick(G + 25_000)
        opened = len(_kinds(plan, "paper_open"))
        assert opened >= 1
        # crash e ripartenza: nuovo processo sulla stessa cartella, stesso minuto e minuto dopo
        again = R.build_arena_runner(plan, environ=ENV, clock_ms=lambda: G + 85_000, get_json=gj,
                                     inner_transport=PolicyModel(), view_params=VIEW)
        exits.tick(G + 85_000)
        again.runner.tick(G + 85_000)
    assert len(_kinds(plan, "paper_open")) == opened       # nessuna seconda apertura sugli stessi simboli
    assert all(d["originating_ai"] == "minimax" for d in _kinds(plan, "brain_decision"))


def test_runner_refuses_live_mode_foreign_manifest_and_missing_run(root):
    plan = _prepare(root, "qwen")
    with pytest.raises(R.ArenaRunnerError):
        R.build_arena_runner(plan, environ={"DESK_MODE": "live"}, clock_ms=lambda: G, inner_transport=FakeModel())
    man = json.loads((plan.folder / "arena_manifest.json").read_text())
    (plan.folder / "arena_manifest.json").write_text(json.dumps(dict(man, provider="deepseek")))
    with pytest.raises(R.ArenaRunnerError):
        R.build_arena_runner(plan, environ=ENV, clock_ms=lambda: G, inner_transport=FakeModel())
    with pytest.raises(R.ArenaRunnerError):
        R.build_arena_runner(P.plan_for("minimax", DAY, root), environ=ENV, clock_ms=lambda: G,
                             inner_transport=FakeModel())


def test_paused_or_unapproved_run_never_calls_the_model(root):
    plan = _prepare(root, "qwen")
    model = FakeModel()
    built = R.build_arena_runner(plan, environ=ENV, clock_ms=lambda: G + 25_000, get_json=_get_json_factory(),
                                 inner_transport=model, view_params=VIEW)
    t = built.runner.tick(G + 25_000)
    assert t.state == "halted" and model.payloads == []
    assert _kinds(plan, "paper_open") == []


def test_openrouter_inference_is_off_unless_explicitly_allowed(root, monkeypatch):
    plan = _prepare(root, "qwen")
    cfg = _approve_and_unpause(plan)

    def no_network(*_a, **_k):
        raise AssertionError("rete chiamata senza autorizzazione")
    monkeypatch.setattr(ORT, "_request", no_network)
    send = R.provider_transport(plan, cfg, ENV)
    with pytest.raises(ProviderUnavailable) as exc:
        send({"model": "qwen/qwen3.7-plus"})
    assert str(exc.value) == "provider_disabled"


def test_cli_once_prints_state_without_secrets(root, capsys):
    plan = _prepare(root, "qwen")
    rc = R.main(["--provider", "qwen", "--root", str(root), "--day", "2026-11-18", "--once"], env=ENV,
                now_fn=lambda: G + 25_000, get_json=_get_json_factory(), inner_transport=FakeModel())
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["provider"] == "qwen" and out["state"] == "halted"
    assert plan.folder.is_dir()
    assert R.main(["--provider", "qwen", "--root", str(root), "--day", "2026-11-18", "--once"],
                  env={"DESK_MODE": "live"}) == 2


def test_arena_expired_blocks_new_model_requests_and_opens(root):
    """No new AI call after T0+72 hours, without stopping the exit service."""
    from backend.v3.arena.budget_gate import TRIAL_DAYS
    plan = _prepare(root, "qwen")
    _approve_and_unpause(plan)
    t0 = json.loads((plan.folder / "arena_manifest.json").read_text())["trial_start_ms"]
    expiry = t0 + TRIAL_DAYS * 86_400_000
    model = PolicyModel()
    built = R.build_arena_runner(
        plan, environ=ENV, clock_ms=lambda: expiry + 1, inner_transport=model,
        get_json=_get_json_factory(), view_params=VIEW)
    result = built.runner.tick(expiry + 1)
    assert result.state == "halted"
    assert model.payloads == []
    assert _kinds(plan, "paper_open") == []


def test_arena_inflight_ai_cannot_open_after_72h(root):
    """Decision started before T0 deadline must not commit OPEN after it."""
    from backend.v3.arena.budget_gate import TRIAL_DAYS
    plan = _prepare(root, "qwen")
    _approve_and_unpause(plan)
    t0 = json.loads((plan.folder / "arena_manifest.json").read_text())["trial_start_ms"]
    expiry = t0 + TRIAL_DAYS * 86_400_000
    clock = {"now": G + 25_000}

    class SlowModel(PolicyModel):
        def __call__(self, payload):
            result = super().__call__(payload)
            clock["now"] = expiry + 1
            return result

    model = SlowModel()
    get_json = _get_json_factory()
    built = R.build_arena_runner(
        plan, environ=ENV, clock_ms=lambda: clock["now"], inner_transport=model,
        get_json=get_json, view_params=VIEW)
    cfg = load_runner_config((plan.folder / "runner_config.json").read_bytes())
    exits = build_exit_worker(data_dir=plan.folder, run_id=plan.run_id, config=cfg, get_json=get_json)
    with exits:
        exits.tick(G + 25_000)
        built.runner.tick(G + 25_000)
    assert model.payloads  # Inference began while trial was open
    assert _kinds(plan, "paper_open") == []  # But cannot commit after deadline


def test_arena_total_budget_survives_midnight_and_restart(tmp_path):
    """Four UTC calendar dates cannot multiply the authorized three-day spend."""
    from backend.v3.budget import BudgetLedger
    db = tmp_path / "budget.db"
    ledger = BudgetLedger(str(db))
    ledger.close()
    # Test-only synthetic rows from prior UTC days; never mutates live journals.
    with sqlite3.connect(db) as conn:
        conn.executemany(
            "INSERT INTO spend_events(occurred_at,provider,units,metadata) VALUES(?,?,?,?)",
            [("2026-11-15T18:00:00+00:00", "qwen", 1_900_000, "{}"),
             ("2026-11-16T18:00:00+00:00", "qwen", 1_900_000, "{}"),
             ("2026-11-17T18:00:00+00:00", "qwen", 1_900_000, "{}"),
             ("2026-11-17T18:00:00+00:00", "minimax", 5_900_000, "{}")])
    second = BudgetLedger(str(db))
    gate = second.spending_gate(
        daily_limits={"qwen": 2_000_000, "minimax": 2_000_000},
        total_limits={"qwen": 6_000_000, "minimax": 6_000_000})
    assert second.total_spend("qwen") == 5_700_000
    assert gate("qwen") is True
    assert gate("minimax") is True
    second.record_spend("qwen", 300_000)
    second.close()
    third = BudgetLedger(str(db))
    gate2 = third.spending_gate(
        daily_limits={"qwen": 2_000_000, "minimax": 2_000_000},
        total_limits={"qwen": 6_000_000, "minimax": 6_000_000})
    assert third.total_spend("qwen") == 6_000_000
    assert gate2("qwen") is False
    third.close()
