"""Collaudo Toro gemello LONG_ONLY (PAPER) nel ciclo vero: uscite delle SHORT preesistenti, DCA e seconde gambe,
NO_TRADE esplicito, trend 4h UNKNOWN, S25, configurazione non valida, ritorno a OFF, guardrail uguali a Falco.
Solo candele sintetiche: nessuna rete, nessun ordine."""
import json

import pytest

from test_desk_rc84_phase2 import _proposal, native_htf
from test_desk_rc84_phase3_collaudo import _history, _opens, _dca_ready
from test_long_s25 import sandbox, _cycle_candles, _with_new_hour, _install  # noqa: F401
from desk import long_s25 as L


def _go(cli, mp, state, *, rules=(), claude=None, htf=1, now=None, unknown=False):
    """Un ciclo vero su Toro con la configurazione letta dall'ambiente in quel momento."""
    a15, sig = _cycle_candles()
    a15b, t, _ = _with_new_hour(a15, sig)
    now = now or t
    _install(cli, mp, a15b)
    mp.setattr(cli, "fetch_htf", (lambda sym, now_ms, fetch=None: {"4h": None, "1d": None, "status": {}})
               if unknown else (lambda sym, now_ms, fetch=None: native_htf(now_ms, htf)))
    mp.setattr(cli, "rules_decisions", lambda *a, **k: [dict(d) for d in rules])
    mp.setattr(cli, "PORTFOLIO", cli._make_bull_config())
    if claude is None:
        mp.setattr(cli, "apply_claude_schedule", lambda *a: False)
    else:
        body = json.dumps({"decisions": [dict(d) for d in claude], "note": "collaudo"})
        mp.setattr(cli, "apply_claude_schedule", lambda *a: True)
        mp.setattr(cli, "can_call", lambda *a, **k: True)
        mp.setattr(cli, "call_claude", lambda *a, **k: (body, {"input_tokens": 10, "output_tokens": 10}))
        state["last_call_ms"] = 0
    cli.run_cycle(state, now)
    return now


@pytest.fixture
def toro(sandbox, monkeypatch):
    cli, d = sandbox
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "LONG_ONLY")
    return cli, d


def _legacy_short(cli, mp, retro=True):
    """Una SHORT medio aperta da Toro in modalita' originale (OFF), poi si attiva il gemello LONG_ONLY."""
    mp.setenv("DESK_BULL_TWIN_MODE", "OFF")
    state = {}
    now = _go(cli, mp, state, claude=[_proposal(action="open_short", trade_type="medio", margin_usd=200.0)], htf=-1)
    acc = cli.make_account(state)
    pos = acc.positions["ETH"]
    assert pos.side == -1
    if retro:
        pos.open_ms -= 3_600_000
    cli.save_account(acc, state)
    mp.setenv("DESK_BULL_TWIN_MODE", "LONG_ONLY")
    return state, now, pos


def test_legacy_short_stop_loss_still_closes(toro, monkeypatch):
    cli, d = toro
    state, now, pos = _legacy_short(cli, monkeypatch)
    acc = cli.make_account(state)
    acc.positions["ETH"].sl = pos.entry * 0.5                  # stop SHORT sotto ogni candela: deve scattare
    cli.save_account(acc, state)
    _go(cli, monkeypatch, state, now=now + 60_000, htf=-1)
    assert cli.make_account(state).positions == {}
    assert _history(d)[-1]["why"] == "stop loss" and _history(d)[-1]["side"] == -1


def test_legacy_short_take_profit_still_closes(toro, monkeypatch):
    cli, d = toro
    state, now, pos = _legacy_short(cli, monkeypatch)
    acc = cli.make_account(state)
    acc.positions["ETH"].tp = pos.entry * 1.5                  # target SHORT sopra ogni candela: deve scattare
    acc.positions["ETH"].sl = pos.entry * 10
    cli.save_account(acc, state)
    _go(cli, monkeypatch, state, now=now + 60_000, htf=-1)
    assert cli.make_account(state).positions == {}
    assert _history(d)[-1]["why"] == "take profit"


def test_legacy_short_partial_and_decided_close_still_work(toro, monkeypatch):
    cli, d = toro
    state, now, _ = _legacy_short(cli, monkeypatch, retro=False)
    _go(cli, monkeypatch, state, now=now + 60_000, htf=-1,
        claude=[{"symbol": "ETH", "action": "partial_close", "reason": "p", "partial_close_fraction": 0.5}])
    assert "ETH" in cli.make_account(state).positions and _history(d)[-1].get("partial")
    _go(cli, monkeypatch, state, now=now + 120_000, htf=-1,
        rules=[{"symbol": "ETH", "action": "close", "reason": "chiudo"}])
    assert cli.make_account(state).positions == {}
    assert _history(d)[-1]["side"] == -1 and not _history(d)[-1].get("partial")


def test_short_dca_is_blocked_but_long_dca_is_allowed(toro, monkeypatch):
    cli, d = toro
    state, now, _ = _legacy_short(cli, monkeypatch, retro=False)
    _dca_ready(cli, state, worse=0.98)
    _go(cli, monkeypatch, state, now=now + 60_000, htf=-1,
        rules=[{"symbol": "ETH", "action": "dca", "dca_sl_pct": 0.01, "dca_tp_pct": 0.02, "reason": "dca"}])
    assert cli.make_account(state).positions["ETH"].dca_count == 0
    assert cli.HB["bull_twin_short_dca_blocked"] == 1
    # LONG: lo stesso DCA procede
    state2 = {}
    now2 = _go(cli, monkeypatch, state2, rules=[_proposal(margin_usd=60.0)])
    _dca_ready(cli, state2, worse=1.02)
    _go(cli, monkeypatch, state2, now=now2 + 60_000,
        rules=[{"symbol": "ETH", "action": "dca", "dca_sl_pct": 0.01, "dca_tp_pct": 0.02, "reason": "dca"}])
    assert cli.make_account(state2).positions["ETH"].dca_count == 1
    assert cli.HB["bull_twin_short_dca_blocked"] == 0


def test_pending_long_second_leg_is_kept(toro, monkeypatch):
    cli, d = toro
    state = {}
    now = _go(cli, monkeypatch, state, rules=[_proposal(margin_usd=60.0)])
    acc = cli.make_account(state)
    acc.positions["ETH"].pending_split = {"trigger": acc.positions["ETH"].entry * 0.5, "margin": 30,
                                          "retrace_pct": 0.003, "created_ms": now, "expire_ms": now + 86_400_000}
    cli.save_account(acc, state)
    _go(cli, monkeypatch, state, now=now + 60_000)
    assert cli.make_account(state).positions["ETH"].pending_split is not None
    assert cli.HB["bull_twin_short_splits_cancelled"] == 0


def test_explicit_claude_no_trade_is_not_replaced_by_rules_long(toro, monkeypatch):
    cli, d = toro
    state = {}
    _go(cli, monkeypatch, state, claude=[], rules=[_proposal()])
    assert cli.make_account(state).positions == {} and _opens(d) == []


def test_claude_short_only_reply_is_not_replaced_by_rules_long(toro, monkeypatch):
    """Claude propone solo SHORT (rifiutati): le regole non vengono usate al loro posto e nulla si apre."""
    cli, d = toro
    state = {}
    _go(cli, monkeypatch, state, claude=[_proposal(action="open_short")], rules=[_proposal()], htf=-1)
    assert cli.make_account(state).positions == {} and _opens(d) == []


def test_unknown_4h_trend_blocks_a_twin_long(toro, monkeypatch, capsys):
    cli, d = toro
    state = {}
    _go(cli, monkeypatch, state, rules=[_proposal()], unknown=True)
    assert cli.make_account(state).positions == {}
    assert "[TREND_UNKNOWN] ETH" in capsys.readouterr().out


def test_twin_long_uses_falco_sizing_caps_and_guardrails(toro, monkeypatch):
    cli, d = toro
    state = {}
    _go(cli, monkeypatch, state, claude=[_proposal(margin_usd=300.0, leverage=20)])
    assert cli.make_account(state).positions["ETH"].margin <= 100.0      # tetto per operazione di Falco
    state2 = {}
    _go(cli, monkeypatch, state2, claude=[_proposal(margin_usd=30.0, leverage=5)])
    p = cli.make_account(state2).positions["ETH"]                          # guardrail come Falco: 60$ 15x scalp
    assert (p.margin, p.leverage, p.trade_type) == (60.0, 15, "scalp")


def test_s25_never_opens_in_twin_but_does_in_the_legacy_control(sandbox, monkeypatch):
    cli, d = sandbox
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.setenv("DESK_LONG_S25", "1")
    monkeypatch.setenv("DESK_S25_TORO_ENTRY_APPROVED", "1")
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "OFF")
    _go(cli, monkeypatch, {})
    assert [e for e in _opens(d) if e.get("source") == L.SOURCE], "controllo: Toro legacy autorizzato apre S25"
    with open(d + "/learning_log.jsonl", "w"):
        pass
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "LONG_ONLY")
    state = {}
    _go(cli, monkeypatch, state)
    assert cli.make_account(state).positions == {}
    assert not [e for e in _opens(d) if e.get("source") == L.SOURCE]


def test_invalid_mode_blocks_every_new_exposure_but_keeps_exits(sandbox, monkeypatch):
    cli, d = sandbox
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "LONG_ONLY")
    state = {}
    now = _go(cli, monkeypatch, state, rules=[_proposal(margin_usd=60.0)])
    acc = cli.make_account(state)
    acc.positions["ETH"].pending_split = {"trigger": acc.positions["ETH"].entry * 0.5, "margin": 30,
                                          "retrace_pct": 0.003, "created_ms": now, "expire_ms": now + 86_400_000}
    cli.save_account(acc, state)
    _dca_ready(cli, state, worse=1.02)
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "long-onli")             # refuso: BLOCK_NEW
    _go(cli, monkeypatch, state, now=now + 60_000,
        rules=[{"symbol": "ETH", "action": "dca", "dca_sl_pct": 0.01, "dca_tp_pct": 0.02, "reason": "dca"},
               _proposal(symbol="BTC")])
    p = cli.make_account(state).positions["ETH"]
    assert p.pending_split is None and p.dca_count == 0 and list(cli.make_account(state).positions) == ["ETH"]
    assert cli.HB["bull_twin_mode"] == "BLOCK_NEW"
    _go(cli, monkeypatch, state, now=now + 120_000, rules=[{"symbol": "ETH", "action": "close", "reason": "c"}])
    assert cli.make_account(state).positions == {}


def test_off_restores_the_legacy_toro_rules_in_the_full_cycle(sandbox, monkeypatch):
    cli, d = sandbox
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "OFF")
    s1 = {}
    _go(cli, monkeypatch, s1, rules=[_proposal()])                        # regole scalp: rifiutate come prima
    assert cli.make_account(s1).positions == {}
    s2 = {}
    _go(cli, monkeypatch, s2, claude=[_proposal(action="open_short", trade_type="medio", margin_usd=300.0)], htf=-1)
    p = cli.make_account(s2).positions["ETH"]                             # SHORT medio da Claude: aperto come prima
    assert p.side == -1 and p.trade_type == "medio" and p.margin == 300.0
    assert cli.HB["bull_twin_mode"] == "OFF"


def test_shadow_audit_uses_the_falco_contract_in_twin_and_the_toro_contract_when_off(monkeypatch):
    """Solo registro: il gemello usa il prompt di Falco, quindi non va confrontato con TP>=5%/confidenza di Toro."""
    from desk import cli
    d = _proposal(symbol="SOL", confidence=70, take_profit_pct=0.02, stop_loss_pct=0.01)
    monkeypatch.setenv("DESK_MODE", "paper")
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "LONG_ONLY")
    twin = cli._make_bull_config()
    assert cli.policy_shadow_violations(d, twin, "SOL") == cli.policy_shadow_violations(d, cli._make_hawk_config(), "SOL")
    monkeypatch.setenv("DESK_BULL_TWIN_MODE", "OFF")
    legacy = cli.policy_shadow_violations(d, cli._make_bull_config(), "SOL")
    assert "tp_2.00%_sotto_5%_del_prompt_toro" in legacy and "confidenza_70_sotto_75_del_prompt_toro" in legacy
