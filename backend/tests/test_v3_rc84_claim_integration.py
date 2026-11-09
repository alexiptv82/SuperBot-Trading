"""RC84: integrazione dei claim contabili nel ciclo operativo PAPER.

(1) recupero dei claim con bot in pausa e senza posizioni (loop_step, riavvio da file di stato reale);
(2) reset rifiutato con claim pendenti o in conflitto, file intatti;
(3) nessuna nuova esposizione con claim irrisolti, uscite protettive e chiusure manuali non coinvolte attive.
Sintetico, nessuna rete.
"""
import json

import pytest

import desk.cli as cli
from backend.tests.test_v3_rc82_active_paper_stops import BAR, BASE, NOW, _entry, _history, _open, _state, desk  # noqa: F401
from backend.tests.test_v3_rc84_telegram_durable_close import (  # noqa: F401
    FLAT, bar_before, Rig, _assert_coherent, _disk, _initial, _learning, _restart, _run, rig,
)


def _files(desk):
    return {p.name: p.read_bytes() for p in desk.iterdir()
            if p.is_file() and p.name in ("trade_history.jsonl", "learning_log.jsonl", "state_v2.json")}


def _pause(desk):
    (desk / "pause.flag").write_text("")


def _break_history(rig):
    real = cli.append_trade_history
    rig.mp.setattr(cli, "append_trade_history", lambda *_a, **_k: None)
    return real


def _plant_conflict_claim(rig, state):
    """Claim ETH in conflitto: nei registri esiste gia' un terminale della stessa posizione con altro netto."""
    ident = {"id": 99, "symbol": "ETH", "side": 1, "open_ms": 1}
    foreign = dict(ident, close_ms=2, why="altro", net=-1.0)
    (rig.desk / "trade_history.jsonl").write_text(json.dumps(foreign) + "\n", encoding="utf-8")
    cli._claim_paper_close(state, dict(ident, close_ms=3, why="x", net=1.0), ("r", "w"))
    cli._commit_paper_closes(state)
    assert state[cli.CLAIMS_KEY][0]["status"] == "conflict"


# ------------------------------------------------------------------ 1. recupero in pausa

def test_paused_flat_pending_claim_is_recovered_by_loop_step_without_a_trade_cycle(rig, monkeypatch):
    _pause(rig.desk)
    state = _initial(rig, "manual")
    real = _break_history(rig)
    _run(rig, "manual", state)                                       # ultima posizione chiusa a mano, in pausa
    assert not _btc_open(rig) and len(_disk(rig.desk)[cli.CLAIMS_KEY]) == 1 and rig.sent == []
    cycles = []
    monkeypatch.setattr(cli, "run_cycle", lambda *a, **k: cycles.append(1))
    # storage ancora rotto: tentativo controllato, nessun crash, claim ancora pendente
    ctl = {}
    cli.loop_step(_disk(rig.desk), ctl)
    assert len(_disk(rig.desk)[cli.CLAIMS_KEY]) == 1 and rig.sent == []
    # rate limit: un secondo giro immediato non ritenta
    calls = []
    real_prove = cli._prove_claimed_close
    monkeypatch.setattr(cli, "_prove_claimed_close", lambda *a: (calls.append(1), real_prove(*a))[1])
    cli.loop_step(_disk(rig.desk), ctl)
    assert calls == []
    # storage di nuovo scrivibile + trascorso l'intervallo: riconciliazione, un solo avviso
    monkeypatch.setattr(cli, "append_trade_history", real)
    ctl["claims_retry_ms"] = 0
    cli.loop_step(_disk(rig.desk), ctl)
    assert cycles == []                                              # nessun ciclo di mercato, nessun trade
    assert len(rig.sent) == 1
    assert not _disk(rig.desk).get(cli.CLAIMS_KEY)
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1)
    ctl["claims_retry_ms"] = 0
    cli.loop_step(_disk(rig.desk), ctl)
    assert len(rig.sent) == 1                                        # nessun duplicato
    _assert_coherent(rig.desk)


def test_restart_from_a_real_state_file_recovers_a_pending_claim_when_paused_and_flat(rig, monkeypatch):
    _pause(rig.desk)
    state = _initial(rig, "rules")
    real = _break_history(rig)
    _run(rig, "rules", state)
    assert len(_disk(rig.desk)[cli.CLAIMS_KEY]) == 1
    monkeypatch.setattr(cli, "append_trade_history", real)
    monkeypatch.setattr(cli, "run_cycle", lambda *a, **k: pytest.fail("nessun ciclo di mercato"))
    restarted = cli.load_state(cli.STATE_FILE)                       # nuovo processo: solo il disco
    cli.loop_step(restarted, {})
    assert len(rig.sent) == 1 and not _disk(rig.desk).get(cli.CLAIMS_KEY)
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1)
    _assert_coherent(rig.desk)


def test_recovery_survives_a_crash_in_the_final_save_without_duplicates(rig, monkeypatch):
    _pause(rig.desk)
    state = _initial(rig, "manual")
    real = _break_history(rig)
    _run(rig, "manual", state)
    monkeypatch.setattr(cli, "append_trade_history", real)
    monkeypatch.setattr(cli, "run_cycle", lambda *a, **k: None)
    rig.fail_saves(2)                                                # 1: checkpoint ok, 2: salvataggio finale KO
    ctl = {}
    cli.loop_step(_disk(rig.desk), ctl)
    assert rig.sent == [] and len(_disk(rig.desk)[cli.CLAIMS_KEY]) == 1
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1)
    rig.heal()
    ctl["claims_retry_ms"] = 0
    cli.loop_step(_disk(rig.desk), ctl)
    assert len(rig.sent) == 1 and not _disk(rig.desk).get(cli.CLAIMS_KEY)
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1)
    _assert_coherent(rig.desk)


def _btc_open(rig):
    return "BTC" in (_disk(rig.desk)["main"]["positions"] or {})


# ------------------------------------------------------------------ 2. reset

@pytest.mark.parametrize("kind", ["pending", "conflict"])
def test_reset_is_refused_with_unresolved_claims_and_every_file_stays_intact(rig, kind):
    _pause(rig.desk)
    state = _initial(rig, "manual")
    if kind == "pending":
        _break_history(rig)
        _run(rig, "manual", state)
        state = _disk(rig.desk)
    else:
        state = {"run_no": 1, "main": cli.PaperAccount(cli.PORTFOLIO.limits, "main").to_dict()}
        _plant_conflict_claim(rig, state)
        rig.real_save(state, cli.STATE_FILE)
    before = _files(rig.desk)
    flag = rig.desk / "reset_portfolio.flag"
    flag.write_text(json.dumps({"clear_lessons": True}))
    assert cli._check_portfolio_reset_flag(state) is False
    after = _files(rig.desk)
    assert {k: v for k, v in after.items() if k != "state_v2.json"} == \
           {k: v for k, v in before.items() if k != "state_v2.json"}
    assert not (rig.desk / "archive").exists() and not flag.exists()
    disk = _disk(rig.desk)
    assert disk[cli.CLAIMS_KEY] and disk.get("run_no", 1) == 1
    action = json.dumps(disk["last_action"])
    assert "rifiutato" in action and "da riconciliare" in action and "non toccati" in action
    if kind == "conflict":
        assert "in conflitto" in action


def test_reset_works_again_after_the_claim_is_reconciled(rig, monkeypatch):
    _pause(rig.desk)
    state = _initial(rig, "manual")
    real = _break_history(rig)
    _run(rig, "manual", state)
    monkeypatch.setattr(cli, "append_trade_history", real)
    state = _disk(rig.desk)
    cli._commit_paper_closes(state)
    assert not state.get(cli.CLAIMS_KEY)
    (rig.desk / "reset_portfolio.flag").write_text("{}")
    assert cli._check_portfolio_reset_flag(state) is True
    assert (rig.desk / "archive").exists() and _disk(rig.desk)["run_no"] == 2


# ------------------------------------------------------------------ 3. nessuna nuova esposizione

def _flat_state(rig):
    state = {"run_no": 1, "last_call_ms": NOW, "budget": {"day": "2099-01-01", "spent": 0.0, "calls": 0},
             "main": cli.PaperAccount(cli.PORTFOLIO.limits, "main").to_dict()}
    return state


def test_open_is_blocked_while_a_claim_is_unresolved_and_allowed_after_reconciliation(rig):
    fresh = [[BASE, 100, 101, 99.2, 100, 1]]
    cli.fetch_candles = lambda sym, bar="15m", limit=1000: fresh if sym == "BTC" else []
    state = _flat_state(rig)
    _plant_conflict_claim(rig, state)
    cli.rules_decisions = lambda *_a, **_k: _entry("open_long")
    cli.run_cycle(state, NOW)
    assert cli.make_account(state).positions == {}
    assert state[cli.CLAIMS_KEY]                                      # ancora segnalato, non cancellato
    state[cli.CLAIMS_KEY] = []                                        # riconciliato
    cli.run_cycle(state, NOW)
    assert "BTC" in cli.make_account(state).positions


def test_dca_is_blocked_while_a_partial_claim_is_pending_and_resumes_after_recovery(rig, monkeypatch):
    state = _initial(rig, "partial")
    real = _break_history(rig)
    _run(rig, "partial", state)
    state = _disk(rig.desk)
    assert len(state[cli.CLAIMS_KEY]) == 1 and "BTC" in state["main"]["positions"]
    before = state["main"]["positions"]["BTC"]
    cli.rules_decisions = lambda *_a, **_k: _entry("dca")
    cli.fetch_candles = lambda sym, bar="15m", limit=1000: bar_before(NOW + 120_000) if sym == "BTC" else []
    cli.run_cycle(state, NOW + 60_000)
    held = cli.make_account(state).positions["BTC"]
    assert held.dca_count == 0 and held.total_margin == pytest.approx(before["total_margin"])
    monkeypatch.setattr(cli, "append_trade_history", real)            # storage tornato scrivibile
    cli.run_cycle(state, NOW + 120_000)                               # il ciclo riconcilia, poi il DCA e' ammesso
    assert not state.get(cli.CLAIMS_KEY)
    assert cli.make_account(state).positions["BTC"].dca_count == 1
    assert len(rig.sent) == 1                                         # l'avviso della parziale parte solo alla riconciliazione
    assert len([r for r in _history(rig.desk) if r.get("partial")]) == 1
    _assert_coherent(rig.desk)


def test_s25_receives_no_new_entries_flag_with_unresolved_claims(rig, monkeypatch):
    from desk import long_s25
    monkeypatch.setenv("DESK_LONG_S25", "1")
    seen = []
    monkeypatch.setattr(long_s25, "step", lambda *a, **k: seen.append(k["drain"]) or {})
    cli.fetch_candles = lambda sym, bar="15m", limit=1000: FLAT if sym == "BTC" else []
    state = _flat_state(rig)
    _plant_conflict_claim(rig, state)
    cli.run_cycle(state, NOW)
    state[cli.CLAIMS_KEY] = []
    cli.run_cycle(state, NOW)
    assert seen == [True, False]


def test_protective_stop_and_uninvolved_manual_close_stay_active_with_a_claim(rig):
    state = _initial(rig, "rules")
    _plant_conflict_claim(rig, state)
    cli.fetch_candles = lambda sym, bar="15m", limit=1000: [[BASE - BAR, 100, 101, 97, 99, 1]] if sym == "BTC" else []
    cli.rules_decisions = lambda *_a, **_k: []
    cli.run_cycle(state, NOW)                                         # SL 98 toccato: uscita protettiva
    assert "BTC" not in cli.make_account(state).positions
    assert [r["why"] for r in _history(rig.desk) if r["symbol"] == "BTC"] == ["stop loss"]
    assert state[cli.CLAIMS_KEY][0]["rec"]["symbol"] == "ETH"        # claim estraneo intatto
    # chiusura manuale di una posizione non coinvolta
    state2 = _state(_open(1, 98.0, 110.0, BASE - 5 * BAR))           # altra posizione (altra identita')
    state2[cli.CLAIMS_KEY] = state[cli.CLAIMS_KEY]
    rig.real_save(state2, cli.STATE_FILE)
    _run(rig, "manual", state2)
    assert not _btc_open(rig)
    assert [r for r in _history(rig.desk) if r["symbol"] == "BTC" and r["why"] == "chiusura manuale"]


# ------------------------------------------------------------------ LIVE invariato

def test_live_mode_ignores_claims_entirely(rig, monkeypatch):
    monkeypatch.setattr(cli.LIVE, "_live", True)
    state = {"run_no": 1, cli.CLAIMS_KEY: [{"claim_id": "x", "run_no": 1, "rec": {}, "notice": None}]}
    assert cli._unresolved_claims(state) == []
    saves = []
    monkeypatch.setattr(cli, "save_state", lambda *a: saves.append(1))
    assert cli._recover_paper_claims(state, {}) is False and saves == []
