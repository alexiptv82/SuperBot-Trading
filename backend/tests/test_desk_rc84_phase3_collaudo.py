"""Collaudo Fase 3 (Falco SHORT_ONLY): percorsi non coperti dalle prove iniziali, con il ciclo vero.

Claude con split, nessuno SHORT forzato, uscite delle LONG residue (stop, take profit, chiusura decisa, parziale),
controlli in BOTH (lo stesso DCA/seconda gamba LONG procede), DCA SHORT ammesso, Toro bidirezionale con l'interruttore
attivo, S25 mai su Falco anche con l'autorizzazione di Toro presente nell'ambiente.
"""
import json
import os

import pytest

from test_desk_rc84_phase2 import _proposal, _learning, native_htf
from test_long_s25 import sandbox, _cycle_candles, _with_new_hour, _install  # noqa: F401
from desk import long_s25 as L


def _go(cli, monkeypatch, state, *, rules=(), claude=None, htf=1, portfolio="hawk", now=None):
    """Un ciclo vero. ``claude``: lista di decisioni restituite da Claude (None = Claude non consultato)."""
    a15, sig = _cycle_candles()
    a15b, t, _ = _with_new_hour(a15, sig)
    now = now or t
    _install(cli, monkeypatch, a15b)
    monkeypatch.setattr(cli, "fetch_htf", lambda sym, now_ms, fetch=None: native_htf(now_ms, htf))
    monkeypatch.setattr(cli, "rules_decisions", lambda *a, **k: [dict(d) for d in rules])
    monkeypatch.setattr(cli, "PORTFOLIO", cli._make_hawk_config() if portfolio == "hawk" else cli._make_bull_config())
    if claude is None:
        monkeypatch.setattr(cli, "apply_claude_schedule", lambda *a: False)
    else:
        body = json.dumps({"decisions": [dict(d) for d in claude], "note": "collaudo"})
        monkeypatch.setattr(cli, "apply_claude_schedule", lambda *a: True)
        monkeypatch.setattr(cli, "can_call", lambda *a, **k: True)
        monkeypatch.setattr(cli, "call_claude", lambda *a, **k: (body, {"input_tokens": 10, "output_tokens": 10}))
        state["last_call_ms"] = 0
    cli.run_cycle(state, now)
    return now


def _opens(d):
    return [e for e in _learning(d) if e.get("ev") == "open"]


def _history(d):
    p = os.path.join(d, "trade_history.jsonl")
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


@pytest.mark.parametrize("action", ["open_long", "open_long_split"])
def test_claude_long_and_long_split_are_rejected_in_short_only(sandbox, monkeypatch, action):
    cli, d = sandbox
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "SHORT_ONLY")
    state = {}
    _go(cli, monkeypatch, state, claude=[_proposal(action=action, split_retrace_pct=0.005)])
    assert cli.make_account(state).positions == {} and _opens(d) == []
    cand = [e for e in _learning(d) if e.get("status") == "falco_short_only"]
    assert len(cand) == 1 and cand[0]["source"] == "claude" and cand[0]["side"] == 1


def test_claude_short_split_still_opens_in_short_only(sandbox, monkeypatch):
    cli, d = sandbox
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "SHORT_ONLY")
    state = {}
    _go(cli, monkeypatch, state, claude=[_proposal(action="open_short_split", split_retrace_pct=0.005)], htf=-1)
    pos = cli.make_account(state).positions
    assert list(pos) == ["ETH"] and pos["ETH"].side == -1 and pos["ETH"].source == "claude"


def test_no_short_is_ever_forced(sandbox, monkeypatch):
    """Solo proposte LONG (e un trend 4h ribassista che renderebbe "plausibile" uno SHORT): non si apre nulla, nessun
    LONG viene trasformato in SHORT, i rifiuti restano candidati."""
    cli, d = sandbox
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "SHORT_ONLY")
    state = {}
    _go(cli, monkeypatch, state, rules=[_proposal(), _proposal(symbol="BTC", action="open_long_split")], htf=-1)
    assert cli.make_account(state).positions == {} and _opens(d) == [] and _history(d) == []
    cand = [e for e in _learning(d) if e.get("status") == "falco_short_only"]
    assert {c["side"] for c in cand} == {1} and cli.HB["hawk_short_only_long_candidates"] >= 1


def _legacy_long(cli, monkeypatch, d, retro=True):
    """Una LONG aperta in BOTH (com'era prima dell'interruttore), retrodatata di un'ora cosi' che le candele chiuse
    dopo l'apertura vengano esaminate da on_bar nel ciclo successivo."""
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "BOTH")
    state = {}
    now = _go(cli, monkeypatch, state, rules=[_proposal()])
    acc = cli.make_account(state)
    pos = acc.positions["ETH"]
    if retro:
        pos.open_ms -= 3_600_000
    cli.save_account(acc, state)
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "SHORT_ONLY")
    return state, now, pos


def test_legacy_long_stop_loss_still_closes_in_short_only(sandbox, monkeypatch):
    cli, d = sandbox
    state, now, pos = _legacy_long(cli, monkeypatch, d)
    acc = cli.make_account(state)
    acc.positions["ETH"].sl = pos.entry * 1.5                   # lo stop sta sopra ogni candela: deve scattare
    cli.save_account(acc, state)
    _go(cli, monkeypatch, state, now=now + 60_000)
    assert cli.make_account(state).positions == {}
    last = _history(d)[-1]
    assert last["why"] == "stop loss" and last["side"] == 1 and not last.get("partial")


def test_legacy_long_take_profit_still_closes_in_short_only(sandbox, monkeypatch):
    cli, d = sandbox
    state, now, pos = _legacy_long(cli, monkeypatch, d)
    acc = cli.make_account(state)
    acc.positions["ETH"].tp = pos.entry * 0.5                   # target sotto ogni candela: deve scattare
    acc.positions["ETH"].sl = pos.entry * 0.1
    cli.save_account(acc, state)
    _go(cli, monkeypatch, state, now=now + 60_000)
    assert cli.make_account(state).positions == {}
    assert _history(d)[-1]["why"] == "take profit"


def test_legacy_long_decided_close_and_partial_still_work_in_short_only(sandbox, monkeypatch):
    cli, d = sandbox
    state, now, pos = _legacy_long(cli, monkeypatch, d, retro=False)
    _go(cli, monkeypatch, state, now=now + 60_000,
        rules=[{"symbol": "ETH", "action": "partial_close", "reason": "p", "partial_close_fraction": 0.5}])
    assert "ETH" in cli.make_account(state).positions and _history(d)[-1].get("partial")
    _go(cli, monkeypatch, state, now=now + 120_000, rules=[{"symbol": "ETH", "action": "close", "reason": "chiudo"}])
    assert cli.make_account(state).positions == {}
    assert not _history(d)[-1].get("partial") and _history(d)[-1]["side"] == 1


def _dca_ready(cli, state, worse):
    """Il motore ammette il DCA solo su posizioni "medio" e con prezzo sfavorevole: la posizione di prova diventa una
    medio con ingresso piu' alto (LONG) o piu' basso (SHORT) del prezzo, come una posizione storica in perdita."""
    acc = cli.make_account(state)
    p = acc.positions["ETH"]
    p.trade_type = "medio"
    p.entry *= worse
    p.sl = p.entry * (0.9 if p.side == 1 else 1.1)
    cli.save_account(acc, state)


def test_control_both_mode_still_allows_long_dca(sandbox, monkeypatch):
    """Controllo: nelle stesse condizioni, in BOTH il DCA LONG avviene. Il blocco SHORT_ONLY e' quindi la causa."""
    cli, d = sandbox
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "BOTH")
    state = {}
    now = _go(cli, monkeypatch, state, rules=[_proposal()])
    _dca_ready(cli, state, worse=1.02)
    _go(cli, monkeypatch, state, now=now + 60_000,
        rules=[{"symbol": "ETH", "action": "dca", "dca_sl_pct": 0.01, "dca_tp_pct": 0.02, "reason": "dca"}])
    assert cli.make_account(state).positions["ETH"].dca_count == 1
    assert cli.HB["hawk_short_only_long_dca_blocked"] == 0


def test_short_dca_is_allowed_in_short_only(sandbox, monkeypatch):
    cli, d = sandbox
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "SHORT_ONLY")
    state = {}
    now = _go(cli, monkeypatch, state, rules=[_proposal(action="open_short")], htf=-1)
    _dca_ready(cli, state, worse=0.98)
    _go(cli, monkeypatch, state, now=now + 60_000, htf=-1,
        rules=[{"symbol": "ETH", "action": "dca", "dca_sl_pct": 0.01, "dca_tp_pct": 0.02, "reason": "dca"}])
    pos = cli.make_account(state).positions["ETH"]
    assert pos.side == -1 and pos.dca_count == 1 and cli.HB["hawk_short_only_long_dca_blocked"] == 0


def test_control_both_mode_keeps_a_pending_long_second_leg(sandbox, monkeypatch):
    cli, d = sandbox
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "BOTH")
    state = {}
    now = _go(cli, monkeypatch, state, rules=[_proposal()])
    acc = cli.make_account(state)
    acc.positions["ETH"].pending_split = {"trigger": acc.positions["ETH"].entry * 0.5, "margin": 20,
                                          "retrace_pct": 0.003, "created_ms": now, "expire_ms": now + 86_400_000}
    cli.save_account(acc, state)
    _go(cli, monkeypatch, state, now=now + 60_000)
    assert cli.make_account(state).positions["ETH"].pending_split is not None
    assert cli.HB["hawk_short_only_long_splits_cancelled"] == 0


def test_toro_stays_bidirectional_with_the_falco_switch_set(sandbox, monkeypatch):
    cli, d = sandbox
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "SHORT_ONLY")
    state = {}
    _go(cli, monkeypatch, state, portfolio="bull", claude=[_proposal(trade_type="medio", margin_usd=200.0)])
    pos = cli.make_account(state).positions
    assert list(pos) == ["ETH"] and pos["ETH"].side == 1 and pos["ETH"].trade_type == "medio"
    assert not [e for e in _learning(d) if e.get("status") == "falco_short_only"]


def test_s25_never_opens_on_falco_even_with_toro_authorization_in_the_environment(sandbox, monkeypatch):
    cli, d = sandbox
    monkeypatch.setenv("DESK_HAWK_ENTRY_MODE", "SHORT_ONLY")
    monkeypatch.setenv("DESK_LONG_S25", "1")
    monkeypatch.setenv("DESK_S25_TORO_ENTRY_APPROVED", "1")
    state = {}
    _go(cli, monkeypatch, state)
    assert cli.make_account(state).positions == {}
    assert not [e for e in _opens(d) if e.get("source") == L.SOURCE]
