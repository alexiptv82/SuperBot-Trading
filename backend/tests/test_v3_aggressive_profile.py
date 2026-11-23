"""Profilo aggressivo 23/11 (Falco Evoluto / Brain Scalp): configurazione schema 2, RiskManager percentuale,
Guardian nel ciclo, politica d'uscita per run e ``stop_kind`` nel journal. Nessuna regressione su schema 1 / RC1."""
from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.tests.test_v3_runner_cycle import (
    NOW, POLICY, RULES, RUN, VIEW, CycleBars, FakeStore, MarketEntryAnalyst, ScriptAnalyst, _events, _journal,
    _mandate, run_brain_cycle,
)
from backend.v3.brain_f2.engine import _policy_hash
from backend.v3.executor.paper import ExecutionError
from backend.v3.executor.paper_close import close_paper
from backend.v3.guardian import GuardianPolicy, GuardianState
from backend.v3.risk import RiskRequest, quote_paper_risk
from backend.v3.runner.config import load_default_config, load_runner_config
from backend.v3.runner.exit_worker import build_exit_worker
from backend.v3.events import Event, EventJournal

RUNNER = Path(__file__).resolve().parents[1] / "v3" / "runner"
FALCO = RUNNER / "runner_config_falco_evoluto_paper.json"
SCALP = RUNNER / "runner_config_brain_scalp_paper.json"
RC1 = RUNNER / "runner_config_brain_unico_paper_b.json"


def cfg(path):
    return load_runner_config(path.read_bytes())


# ------------------------------------------------------------------ configurazioni
def test_rc1_and_default_configs_are_unchanged():
    rc1 = cfg(RC1)
    assert _policy_hash(rc1.risk_policy) == "ba5c074ec2ecfe34"               # mandato RC1 ancora valido
    assert rc1.analyst == "deepseek" and rc1.exit_policy is None and rc1.guardian is None
    assert rc1.risk_policy.min_margin is None and rc1.risk_policy.max_positions is None
    d = load_default_config()
    assert d.exit_policy is None and d.guardian is None


def test_two_paper_configs_carry_exactly_the_requested_parameters():
    f, s = cfg(FALCO), cfg(SCALP)
    for c, equity, mn, mx in ((f, "1000", "100", "250"), (s, "2000", "250", "450")):
        p = c.risk_policy
        assert c.initial_equity == D(equity) and (p.min_leverage, p.max_leverage) == (15, 45)
        assert (p.min_margin, p.max_margin, p.max_positions) == (D(mn), D(mx), 4)
        assert (p.max_loss_fraction, p.max_open_risk_fraction, p.max_loss_margin_fraction) == (
            D("0.04"), D("0.10"), D("0.20"))
        assert c.daily_loss_halt == D("0.08") and c.symbols == cfg(RC1).symbols
        assert (c.fee_bps, c.slippage_bps) == (D("6"), 2)                     # stessi costi per il confronto
        e = c.exit_policy
        assert (e.take_profit_r, e.be_at_r, e.trail_at_r, e.trail_dist_r, e.max_hold_ms) == (
            D("3"), D("1"), D("1.5"), D("1"), 24 * 3_600_000)
        assert c.guardian == GuardianPolicy()
    assert (f.analyst, f.daily_cap_usd, f.cycle_minutes) == ("falco_evoluto", D("0.20"), 15)
    assert (s.analyst, s.daily_cap_usd, s.cycle_minutes) == ("deepseek", D("0.75"), 30)
    # rischio complessivo allineato (proposta 23/11): margine totale 50 % e protezione patrimoniale 80 % per entrambi
    assert (f.risk_policy.minimum_equity, s.risk_policy.minimum_equity) == (D("800"), D("1600"))
    assert f.risk_policy.max_total_margin_fraction == s.risk_policy.max_total_margin_fraction == D("0.50")
    assert _policy_hash(f.risk_policy) != _policy_hash(s.risk_policy) != "ba5c074ec2ecfe34"


def test_schema_2_is_strict():
    base = json.loads(FALCO.read_text())
    bad = [dict(base, analyst="claude"), {k: v for k, v in base.items() if k != "guardian"},
           dict(base, schema_version=1), dict(base, exit_policy={**base["exit_policy"], "trail_dist_r": None}),
           dict(base, guardian={**base["guardian"], "keep_fraction": "1.2"})]
    risk = dict(base["risk_policy"])
    del risk["min_leverage"], risk["max_leverage"], risk["max_loss_margin_fraction"]
    bad.append(dict(base, risk_policy=risk))                                 # profilo aggressivo senza leva
    bad.append(dict(base, risk_policy={**base["risk_policy"], "min_margin_usd": "300"}))   # min > max
    for b in bad:
        with pytest.raises(ValueError, match="invalid_config"):
            load_runner_config(json.dumps(b).encode())


# ------------------------------------------------------------------ RiskManager percentuale
def _req(**kw):
    d = dict(equity=D("1000"), available_cash=D("1000"), margin_used=D(0), existing_open_risk=D(0),
             entry_price=D(100), stop_price=D("99.5"), side=1, requested_leverage=30, exchange_leverage_limit=50,
             quantity_step=D("0.0001"), minimum_notional=D(5), maintenance_fraction=D("0.005"),
             market_data_fresh=True, paused=False, daily_loss_latched=False)
    d.update(kw)
    return RiskRequest(**d)


def test_authorized_risk_is_the_smallest_of_all_limits():
    p = cfg(FALCO).risk_policy
    q = quote_paper_risk(p, _req())
    assert q.allowed and q.risk_budget == D("40.00") and D("100") <= q.margin <= D("250")
    assert quote_paper_risk(p, _req(external_risk_cap=D("15"), requested_leverage=20)).risk_budget == D("15")
    # stesso tetto a 30x: margine 75 < 100 -> rifiuto; il motore riprova con una leva piu' bassa (vedi sotto)
    assert quote_paper_risk(p, _req(external_risk_cap=D("15"))).reason == "below_min_margin"
    assert quote_paper_risk(p, _req(same_side_open_risk=D("70"), requested_leverage=15)).risk_budget == D("10.00")
    assert quote_paper_risk(p, _req(existing_open_risk=D("80"), same_side_open_risk=D(0))).risk_budget == D("20.00")
    assert quote_paper_risk(p, _req(open_positions=4)).reason == "max_positions_reached"
    assert quote_paper_risk(p, _req(external_risk_cap=D("0"))).reason == "guardian_budget_exhausted"


def test_small_budget_never_raises_risk_to_reach_the_minimum_margin():
    p = cfg(FALCO).risk_policy
    q = quote_paper_risk(p, _req(external_risk_cap=D("3"), requested_leverage=15))
    assert not q.allowed and q.reason == "below_min_margin"
    assert quote_paper_risk(p, _req(requested_leverage=14)).reason == "leverage_outside_profile"
    # stop largo: anche a 15x la perdita supera il 20 % del margine -> rifiuto (mai stop stretto o leva < 15)
    assert quote_paper_risk(p, _req(stop_price=D("98.5"), requested_leverage=15)).reason == "margin_loss_ratio_exceeded"


def test_engine_lowers_leverage_to_reach_the_minimum_margin(tmp_path):
    from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus
    from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot
    from backend.v3.brain_f2.reviewer import MockClaudeReviewer
    j = EventJournal(str(tmp_path / "j.db"))
    j.init_schema()
    eng = BrainEngine(ScriptAnalyst(), MockClaudeReviewer(), risk_policy=cfg(FALCO).risk_policy,
                      portfolio_snapshot=BrainPortfolioSnapshot(D(1000), D(1000), D(0), D(0), risk_cap=D("15")),
                      market_params={"exchange_leverage_limit": 50, "quantity_step": D("0.0001"),
                                     "minimum_notional": D(5), "maintenance_fraction": D("0.005"),
                                     "market_data_fresh": True, "paused": False, "daily_loss_latched": False},
                      journal=j, run_id="falco-evoluto-test")
    prop = OpenProposal("BTCUSDT", 1, D(100), D("99.5"), 45, "sanitized", .8, "falco:rules", "ab12")
    d = BrainDecision(kind=DecisionKind.OPEN, proposal=prop, occurred_at_ms=NOW, status=ProposalStatus.DRAFT)
    out = eng._apply_risk_gate(d, MarketContext("BTCUSDT", D(100), NOW, "TREND_UP"))
    assert out.status == ProposalStatus.APPROVED and 15 <= out.proposal.leverage < 30
    assert out.risk_quote.margin >= D("100") and out.risk_quote.worst_case_loss_estimate <= D("15")


def test_scalp_margin_stays_within_250_and_450():
    p = cfg(SCALP).risk_policy
    for stop in ("99.8", "99.5", "99.2"):
        for lev in range(15, 46):
            q = quote_paper_risk(p, _req(equity=D("2000"), available_cash=D("2000"), stop_price=D(stop),
                                         requested_leverage=lev))
            if q.allowed:
                assert D("250") <= q.margin <= D("450") and q.worst_case_loss_estimate <= D("80")
                assert q.worst_case_loss_estimate <= q.margin * D("0.20")


# ------------------------------------------------------------------ Guardian nel ciclo
def _state(state, cap=None, min_conf=None, reentry=True):
    z = D("0")
    return GuardianState(state=state, reasons=("test",), session_start_ms=NOW - 3_600_000,
                         session_start_equity=D("1000"), equity=D("1000"), realized_session=z, unrealized=z,
                         peak_equity=D("1000"), giveback=z, armed=state != "NORMAL", floor=None, open_risk=z,
                         budget=None, r_unit=D("20"), risk_cap=cap, min_confidence=min_conf, allow_reentry=reentry,
                         global_drawdown=z, as_of_ms=NOW)


def _run(j, analyst, guardian):
    return run_brain_cycle(now_ms=NOW, journal=j, run_id=RUN, symbols=("AAAUSDT", "BBBUSDT"), store=FakeStore(NOW),
                           bars_holder=CycleBars(), analyst=MarketEntryAnalyst(analyst), view_params=VIEW,
                           risk_policy=POLICY, mandate=_mandate(), policy_verifier=lambda m, p: True,
                           market_rules=lambda s: RULES, initial_equity=D("1000"), slippage_bps=2,
                           allowed_strategy_ids=("S25",), guardian=guardian)


def test_locked_guardian_opens_nothing_and_never_calls_the_ai():
    j, a = _journal(), ScriptAnalyst()
    rep = _run(j, a, lambda t: _state("LOCKED", D("0")))
    assert a.calls == [] and rep.opened == () and {e for _, e in rep.errors} == {"guardian_locked"}
    ev = _events(j, "guardian_state")
    assert len(ev) == 1 and ev[0].payload["state"] == "LOCKED" and rep.guardian[0][1] == "LOCKED"


def test_guardian_error_is_locked_and_recorded():
    j, a = _journal(), ScriptAnalyst()
    rep = _run(j, a, lambda t: (_ for _ in ()).throw(RuntimeError("feed")))
    assert a.calls == [] and rep.opened == ()
    assert _events(j, "guardian_state")[0].payload["reasons"] == ["guardian_error"]


def test_guardian_cap_limits_the_size_and_is_reevaluated_after_each_open():
    j, a = _journal(), ScriptAnalyst()
    calls = []
    rep = _run(j, a, lambda t: calls.append(t) or _state("SELECTIVE", D("5")))
    assert len(rep.opened) == 2 and len(calls) == 3                         # inizio giro + dopo ogni apertura
    for o in _events(j, "paper_open"):
        loss = (D(o.payload["fill_price"]) - D(o.payload["stop_price"])).copy_abs() * D(o.payload["quantity"])
        assert loss <= D("5")                                                 # rischio a stop entro il tetto
    plain_j = _journal()
    _run(plain_j, ScriptAnalyst(), None)
    assert _events(plain_j, "guardian_state") == []                           # Guardian spento: come prima


def test_protected_requires_confidence_and_a_new_thesis():
    j = _journal()
    rep = _run(j, ScriptAnalyst(confidence=0.6), lambda t: _state("PROTECTED", D("5"), D("0.7"), False))
    assert rep.opened == () and {e for _, e in rep.errors} == {"guardian_low_confidence"}
    rep = _run(_journal(), ScriptAnalyst(confidence=0.8), lambda t: _state("PROTECTED", D("5"), D("0.7"), False))
    assert len(rep.opened) == 2                                              # prime entrate delle tesi: consentite


# ------------------------------------------------------------------ uscite per run e stop_kind persistente
def _open_position(j):
    from backend.tests.test_v3_exit_service import _open
    return _open(j, now=NOW - 120_000, entry="100", stop="98")


def test_stop_kind_is_persisted_only_for_moved_stops(tmp_path):
    from backend.tests.test_v3_exit_service import RUN as XRUN, _journal as xjournal
    j = xjournal(tmp_path)
    pid = _open_position(j)
    close_paper(portfolio_id="brain", run_id=XRUN, position_id=pid, exit_price=D("101"), reason="stop", fee_bps=6,
                journal=j, now_ms=NOW, stop_kind="trailing")
    ev = [r.event for r in j.list_run("brain", XRUN) if r.event.kind == "paper_close"][0]
    assert ev.payload["stop_kind"] == "trailing"
    other = tmp_path / "b"
    other.mkdir()
    j2 = xjournal(other)
    pid2 = _open_position(j2)
    close_paper(portfolio_id="brain", run_id=XRUN, position_id=pid2, exit_price=D("98"), reason="stop", fee_bps=6,
                journal=j2, now_ms=NOW)
    assert "stop_kind" not in [r.event for r in j2.list_run("brain", XRUN) if r.event.kind == "paper_close"][0].payload
    for reason, kind in (("take_profit", "trailing"), ("stop", "initial"), ("stop", "moon")):
        third = tmp_path / f"c-{reason}-{kind}"
        third.mkdir()
        j3 = xjournal(third)
        with pytest.raises(ExecutionError, match="invalid_stop_kind"):
            close_paper(portfolio_id="brain", run_id=XRUN, position_id=_open_position(j3), exit_price=D("101"),
                        reason=reason, fee_bps=6, journal=j3, now_ms=NOW, stop_kind=kind)


def test_exit_worker_uses_the_run_policy(tmp_path, monkeypatch):
    import backend.v3.runner.exit_worker as w
    seen = []
    monkeypatch.setattr(w, "verify_prepared_run_config", lambda **kw: None)
    monkeypatch.setattr(w, "run_exit_monitor", lambda **kw: seen.append(kw["policy"]))
    j = EventJournal(tmp_path / "journal.db")
    j.init_schema()
    j.append(Event("checkpoint", "brain", "falco-evoluto-test", "heartbeat", NOW - 60_000, "test", {}))
    for config, expect_protects in ((cfg(FALCO), True), (load_default_config(), False)):
        svc = build_exit_worker(data_dir=tmp_path, run_id="falco-evoluto-test", config=config, get_json=lambda u: [])
        svc._monitor(NOW)
        assert seen[-1].protects is expect_protects


def test_precise_risk_rejection_reason_is_journaled_only_for_the_aggressive_profile(tmp_path):
    from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot
    from backend.v3.brain_f2.reviewer import MockClaudeReviewer
    from backend.v3.brain_f2.contracts import MarketContext

    def decide(policy, name):
        j = EventJournal(str(tmp_path / f"{name}.db"))
        j.init_schema()
        eng = BrainEngine(ScriptAnalyst(stop_factor=D("0.97")), MockClaudeReviewer(), risk_policy=policy,
                          portfolio_snapshot=BrainPortfolioSnapshot(D(1000), D(1000), D(0), D(0)),
                          market_params={"exchange_leverage_limit": 50, "quantity_step": D("0.0001"),
                                         "minimum_notional": D(5), "maintenance_fraction": D("0.005"),
                                         "market_data_fresh": True, "paused": False, "daily_loss_latched": False},
                          journal=j, run_id="risk-reason-test", policy_mandate={**_mandate(run="risk-reason-test"),
                                                                                "policy_hash": _policy_hash(policy)},
                          policy_verifier=lambda m, p: True)
        eng.step(MarketContext("BTCUSDT", D(100), NOW, "TREND_UP"), 0.0)
        return [r.event.payload for r in j.list_run("brain", "risk-reason-test") if r.event.kind == "brain_decision"]
    aggressive = decide(cfg(FALCO).risk_policy, "a")
    assert aggressive[-1]["rationale"] == "risk_rejected" and aggressive[-1]["risk_reason"] == "margin_loss_ratio_exceeded"
    legacy = decide(cfg(RC1).risk_policy, "b")
    assert all("risk_reason" not in p for p in legacy)


def test_both_runs_are_prepared_paused_unapproved_and_wired_to_the_right_analyst(tmp_path, monkeypatch):
    import backend.v3.falco_evoluto as fe
    import backend.v3.runner.wiring as w
    from backend.v3.runner.prepare_paper_run import prepare_new_paper_run
    built = []
    real_falco, real_deepseek = fe.FalcoEvolutoAnalyst, w.DeepSeekL5Analyst
    monkeypatch.setattr(fe, "FalcoEvolutoAnalyst", lambda **kw: built.append(("falco", kw)) or real_falco(**kw))
    monkeypatch.setattr(w, "DeepSeekL5Analyst", lambda **kw: built.append(("deepseek", kw)) or real_deepseek(**kw))
    keeps = []
    real_store = w.CandleStore
    monkeypatch.setattr(w, "CandleStore", lambda get_json, keep: keeps.append(dict(keep)) or real_store(get_json, keep=keep))
    for name, path, equity in (("brain-v3-falco-evoluto-t1", FALCO, "1000"), ("brain-v3-brain-scalp-t1", SCALP, "2000")):
        root = prepare_new_paper_run(parent=tmp_path, run_name=name, run_id=name, config_bytes=path.read_bytes(),
                                     desk_mode="paper", now_ms=NOW, expected_initial_equity=equity)
        mandate = json.loads((root / "mandate.json").read_text())
        assert mandate["approved"] is False and (root / "pause.flag").exists()
        assert mandate["policy_hash"] == _policy_hash(cfg(path).risk_policy)
        calls = []
        b = w.build_runner(data_dir=root, run_id=name, config=cfg(path), get_json=lambda url: [],
                           inner_transport=lambda payload: calls.append(payload), desk_mode="paper")
        # un giro vero con mandato approved:false: fermo per il mandato, nessuna AI, nessuna spesa, nessuna apertura
        t = b.runner.tick(NOW + 3_600_000)
        assert t.state == "halted" and "mandate" in (t.last_error or "") and t.cycle is None
        assert calls == [] and b.ledger.daily_spend("deepseek") == 0
        assert not [r for r in b.journal.list_run("brain", name) if r.event.kind == "paper_open"]
    assert [b[0] for b in built] == ["falco", "deepseek"]
    falco_kw = built[0][1]
    assert falco_kw["max_leverage"] == 45 and falco_kw["ai_enabled"] is True
    four = [k["4h"][1] for k in keeps if "4h" in k]                       # la cache 1m non ha il 4h
    assert len(four) == 2 and four[0] >= fe.EMA200_MIN_BARS and four[1] < four[0]


def test_how_many_full_risk_positions_fit_under_the_aligned_limits(tmp_path):
    """Misura (23/11) per il proprietario: a rischio pieno entrano 2 posizioni, la terza e' rifiutata per margine;
    4 posizioni non sono raggiungibili con 4 % per trade, 10 % aperto e 50 % di margine totale."""
    from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus
    from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot
    from backend.v3.brain_f2.reviewer import MockClaudeReviewer
    mp = {"exchange_leverage_limit": 50, "quantity_step": D("0.0001"), "minimum_notional": D(5),
          "maintenance_fraction": D("0.005"), "market_data_fresh": True, "paused": False, "daily_loss_latched": False}
    for path, equity, risk in ((FALCO, D(1000), D(40)), (SCALP, D(2000), D(80))):
        policy = cfg(path).risk_policy
        for stop_pct in ("0.3", "0.5", "1.0"):
            margin = open_risk = D(0)
            opened, last = 0, None
            for i in range(4):
                side = 1 if i % 2 == 0 else -1
                j = EventJournal(str(tmp_path / f"{path.stem}-{stop_pct}-{i}.db"))
                j.init_schema()
                eng = BrainEngine(ScriptAnalyst(), MockClaudeReviewer(), risk_policy=policy, market_params=mp,
                                  portfolio_snapshot=BrainPortfolioSnapshot(equity, equity - margin, margin, open_risk,
                                                                            open_positions=opened),
                                  journal=j, run_id="cap")
                prop = OpenProposal("BTCUSDT", side, D(100), D(100) * (1 - side * D(stop_pct) / 100), 45,
                                    "sanitized", .8, "falco:rules", "ab")
                out = eng._apply_risk_gate(BrainDecision(kind=DecisionKind.OPEN, proposal=prop, occurred_at_ms=NOW,
                                                         status=ProposalStatus.DRAFT),
                                           MarketContext("BTCUSDT", D(100), NOW, "TREND_UP"))
                if out.status != ProposalStatus.APPROVED:
                    last = eng._last_risk_reason
                    break
                assert out.risk_quote.worst_case_loss_estimate <= risk
                margin += out.risk_quote.margin
                open_risk += out.risk_quote.worst_case_loss_estimate
                opened += 1
            assert opened == 2 and last == "below_min_margin", (path.stem, stop_pct, opened, last)
            assert margin <= equity * D("0.50")
