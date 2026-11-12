"""RC84: nessuna nuova esposizione nello STESSO ciclo se una chiusura non protettiva lascia un claim irrisolto.

Sequenze: close(A)+open(B), partial(A)+dca(A), S25 dopo una chiusura a tempo, seconda chiusura non protettiva
della stessa posizione con claim parziale pendente. Percorso sano: nessun cambio di comportamento.
Sintetico, nessuna rete.
"""
import json

import pytest

import desk.cli as cli
from backend.tests.test_v3_rc82_active_paper_stops import BAR, BASE, NOW, _entry, _history, _open, _state, desk  # noqa: F401
from backend.tests.test_v3_rc84_telegram_durable_close import (  # noqa: F401
    Rig, _assert_coherent, _disk, _learning, rig,
)

FRESH = [[BASE, 100, 101, 99.2, 100, 1]]     # barra recente, nessuno stop toccato


def _feed(*symbols):
    from backend.tests.rc84_test_support import with_history
    rows = with_history(FRESH)                      # RC84 fase 2: storia sufficiente per una lettura (vedi supporto)
    cli.fetch_candles = lambda sym, bar="15m", limit=1000: rows if sym in symbols else []


def _held(rig, open_ms=BASE - 3 * BAR):
    state = _state(_open(1, 98.0, 110.0, open_ms))
    rig.real_save(state, cli.STATE_FILE)
    return state


def _decisions(*items):
    cli.rules_decisions = lambda *_a, **_k: [dict(i) for i in items]


def _eth_open():
    return dict(_entry("open_long")[0], symbol="ETH")


def _positions(state):
    return set(cli.make_account(state).positions)


def _break(rig, which="history"):
    real_h, real_l = cli.append_trade_history, cli.log_event
    if which == "history":
        rig.mp.setattr(cli, "append_trade_history", lambda *_a, **_k: None)
    else:
        rig.mp.setattr(cli, "log_event", lambda *_a, **_k: False)

    def heal():
        rig.mp.setattr(cli, "append_trade_history", real_h)
        rig.mp.setattr(cli, "log_event", real_l)
    return heal


# --------------------------------------------------------------- close(A) -> open_long(B)

@pytest.mark.parametrize("which", ["history", "learning"])
def test_close_then_open_is_blocked_same_cycle_when_the_claim_is_unresolved_then_unblocked(rig, which):
    _feed("BTC", "ETH")
    state = _held(rig)
    heal = _break(rig, which)
    _decisions({"symbol": "BTC", "action": "close", "reason": "chiudo A"}, _eth_open())
    cli.run_cycle(state, NOW)
    assert _positions(state) == set()                                  # B NON aperta
    assert len(state[cli.CLAIMS_KEY]) == 1 and rig.sent == []
    _assert_coherent(rig.desk)
    heal()
    _decisions(_eth_open())
    cli.run_cycle(state, NOW + 60_000)                                  # riconciliazione a inizio ciclo, poi B ammessa
    assert not state.get(cli.CLAIMS_KEY) and len(rig.sent) == 1
    assert _positions(state) == {"ETH"}
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1)
    _assert_coherent(rig.desk)


def test_close_then_open_still_happens_in_the_same_cycle_on_the_healthy_path(rig):
    _feed("BTC", "ETH")
    state = _held(rig)
    _decisions({"symbol": "BTC", "action": "close", "reason": "chiudo A"}, _eth_open())
    cli.run_cycle(state, NOW)
    assert _positions(state) == {"ETH"} and len(rig.sent) == 1
    assert not state.get(cli.CLAIMS_KEY)
    assert (len(_history(rig.desk)), len(_learning(rig.desk))) == (1, 1)
    saved = _disk(rig.desk)
    assert set(saved["main"]["positions"]) == {"ETH"}                  # conto su disco coerente col ciclo
    _assert_coherent(rig.desk)


# --------------------------------------------------------------- partial(A) -> dca(A)

@pytest.mark.parametrize("which", ["history", "learning"])
def test_partial_then_dca_is_blocked_same_cycle_when_unresolved_then_unblocked(rig, which):
    _feed("BTC")
    state = _held(rig)
    heal = _break(rig, which)
    _decisions({"symbol": "BTC", "action": "partial_close", "reason": "p", "partial_close_fraction": 0.5},
               dict(_entry("dca")[0]))
    cli.run_cycle(state, NOW)
    held = cli.make_account(state).positions["BTC"]
    assert held.dca_count == 0                                         # nessun DCA
    assert len(state[cli.CLAIMS_KEY]) == 1 and rig.sent == []
    margin_after_partial = held.total_margin
    heal()
    _decisions(dict(_entry("dca")[0]))
    cli.run_cycle(state, NOW + 60_000)
    held = cli.make_account(state).positions["BTC"]
    assert held.dca_count == 1 and held.total_margin > margin_after_partial
    assert not state.get(cli.CLAIMS_KEY) and len(rig.sent) == 1
    assert len([r for r in _history(rig.desk) if r.get("partial")]) == 1
    _assert_coherent(rig.desk)


def test_partial_then_dca_still_happens_in_the_same_cycle_on_the_healthy_path(rig):
    _feed("BTC")
    state = _held(rig)
    _decisions({"symbol": "BTC", "action": "partial_close", "reason": "p", "partial_close_fraction": 0.5},
               dict(_entry("dca")[0]))
    cli.run_cycle(state, NOW)
    assert cli.make_account(state).positions["BTC"].dca_count == 1
    assert len(rig.sent) == 1 and not state.get(cli.CLAIMS_KEY)
    _assert_coherent(rig.desk)


# --------------------------------------------------------------- S25 dopo una chiusura nello stesso ciclo

def _s25_setup(rig, monkeypatch, toro_opt_in=True):
    """RC84: i nuovi ingressi S25 esistono solo su Toro con l'autorizzazione esplicita. Queste prove (blocco con claim
    irrisolto, percorso sano) girano quindi su Toro con l'opt-in; senza opt-in si prova che S25 non apre nulla."""
    from desk import long_s25
    monkeypatch.setattr(cli, "PORTFOLIO", cli._make_bull_config())
    monkeypatch.setenv("DESK_LONG_S25", "1")
    if toro_opt_in:
        monkeypatch.setenv("DESK_S25_TORO_ENTRY_APPROVED", "1")
    else:
        monkeypatch.delenv("DESK_S25_TORO_ENTRY_APPROVED", raising=False)
    monkeypatch.setattr(long_s25, "closed_hours", lambda arr, now: arr)
    monkeypatch.setattr(long_s25, "signal", lambda h: {"ema9": 1.0, "vwap": 1.0, "atr": 1.0,
                                                       "trigger": 1.0, "signal_open_ms": 1})
    monkeypatch.setattr(long_s25, "entry_plan", lambda sig, px, now: ({"sl": px * 0.985, "tp": px * 1.04}, ""))
    monkeypatch.setattr(long_s25, "leverage_for", lambda name, sig, px: 5)
    account = _open(1, 98.0, 110.0, NOW - 13 * 3_600_000)
    account.positions["BTC"].source = long_s25.SOURCE
    state = _state(account)
    rig.real_save(state, cli.STATE_FILE)
    return state


@pytest.mark.parametrize("which", ["history", "learning"])
def test_s25_entry_after_a_time_close_is_blocked_while_the_claim_is_unresolved(rig, monkeypatch, which):
    _feed("BTC", "ETH")
    state = _s25_setup(rig, monkeypatch)
    heal = _break(rig, which)
    _decisions()
    cli.run_cycle(state, NOW)
    assert _positions(state) == set()                                  # chiusa a tempo, ETH NON aperta da S25
    assert len(state[cli.CLAIMS_KEY]) == 1 and rig.sent == []
    heal()
    cli.run_cycle(state, NOW + 60_000)
    assert not state.get(cli.CLAIMS_KEY) and len(rig.sent) == 1
    assert "ETH" in _positions(state) or "BTC" in _positions(state)    # sbloccato: S25 torna operativa
    _assert_coherent(rig.desk)


def test_s25_entry_after_a_time_close_still_happens_on_the_healthy_path(rig, monkeypatch):
    _feed("BTC", "ETH")
    state = _s25_setup(rig, monkeypatch)
    _decisions()
    cli.run_cycle(state, NOW)
    assert _positions(state) and len(rig.sent) == 1 and not state.get(cli.CLAIMS_KEY)
    _assert_coherent(rig.desk)


@pytest.mark.parametrize("portfolio", ["hawk", "bull"])
def test_s25_never_opens_without_the_toro_authorization_but_still_closes_on_time(rig, monkeypatch, portfolio):
    _feed("BTC", "ETH")
    state = _s25_setup(rig, monkeypatch, toro_opt_in=False)
    if portfolio == "hawk":
        monkeypatch.setattr(cli, "PORTFOLIO", cli._make_hawk_config())
    _decisions()
    cli.run_cycle(state, NOW)
    assert _positions(state) == set()                                  # chiusa a tempo, nessun nuovo ingresso S25
    assert len(rig.sent) == 1 and not state.get(cli.CLAIMS_KEY)
    _assert_coherent(rig.desk)


# --------------------------------------------------------------- seconda chiusura con claim parziale pendente

def test_second_non_protective_close_of_the_same_position_with_a_pending_partial_claim(rig):
    _feed("BTC")
    state = _held(rig)
    heal = _break(rig, "history")
    _decisions({"symbol": "BTC", "action": "partial_close", "reason": "p", "partial_close_fraction": 0.5})
    cli.run_cycle(state, NOW)
    assert len(state[cli.CLAIMS_KEY]) == 1 and "BTC" in _positions(state)
    _decisions({"symbol": "BTC", "action": "close", "reason": "chiudo il resto"})
    cli.run_cycle(state, NOW + 60_000)                                  # uscita non protettiva: ammessa
    assert "BTC" not in _positions(state)
    kinds = sorted(bool(c["rec"].get("partial")) for c in state[cli.CLAIMS_KEY])
    assert kinds == [False, True] and rig.sent == []                    # due claim distinti, nessun terminale duplicato
    heal()
    cli.run_cycle(state, NOW + 120_000)
    assert not state.get(cli.CLAIMS_KEY) and len(rig.sent) == 2
    rows = _history(rig.desk)
    assert sorted(bool(r.get("partial")) for r in rows) == [False, True]
    assert len(_learning(rig.desk)) == 2
    realized = sum(r["net"] for r in rows)
    assert realized == pytest.approx(sum(c["net"] for c in _disk(rig.desk)["main"]["closed"]))
    _assert_coherent(rig.desk)


# --------------------------------------------------------------- uscite protettive e manuali non coinvolte

def test_protective_stop_and_uninvolved_manual_close_work_in_the_cycle_that_creates_the_claim(rig):
    _feed("BTC")
    account = _open(1, 98.0, 110.0, BASE - 3 * BAR)
    state = _state(account)
    rig.real_save(state, cli.STATE_FILE)
    heal = _break(rig, "history")
    _decisions({"symbol": "BTC", "action": "partial_close", "reason": "p", "partial_close_fraction": 0.5})
    cli.run_cycle(state, NOW)
    assert len(state[cli.CLAIMS_KEY]) == 1
    heal()
    # stop protettivo sulla stessa posizione con claim parziale pendente: l'uscita resta attiva
    cli.fetch_candles = lambda sym, bar="15m", limit=1000: [[BASE - BAR, 100, 101, 97, 99, 1]] if sym == "BTC" else []
    _decisions()
    cli.run_cycle(state, NOW + 60_000)
    assert "BTC" not in _positions(state) and not state.get(cli.CLAIMS_KEY)
    assert [r["why"] for r in _history(rig.desk) if not r.get("partial")] == ["stop loss"]
    _assert_coherent(rig.desk)
