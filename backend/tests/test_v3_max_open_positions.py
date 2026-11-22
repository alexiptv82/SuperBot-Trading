"""Tetto numerico di 4 posizioni aperte (vincolo del proprietario, 21/11/2026), nel percorso serializzato di conferma.
Politica di prova con budget di rischio AMPIO: qui conta solo il tetto numerico, non il rischio aperto. Solo PAPER."""
from __future__ import annotations

import fcntl
import os
from decimal import Decimal as D

from backend.tests.test_brain_f7_outcomes import _hand
from backend.tests.test_v3_open_serial import _real_sidecar
from backend.tests.test_v3_post_ai_guard import NOW, RULES, RUN
from backend.v3.events import Event, EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.executor.paper_close import close_paper
from backend.v3.risk import RiskPolicy, RiskRequest, quote_paper_risk
from backend.v3.runner.open_serial import commit_paper_open
from backend.v3.runner.post_ai_guard import MAX_OPEN_POSITIONS, recheck_paper_open

ROOMY = RiskPolicy(D(".01"), D(".5"), D(".10"), D(".9"), D("450"), D("16"), D(".5"))
OTHERS = ("ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT")


def _journal(tmp_path):
    j = EventJournal(tmp_path / "journal.db")
    j.init_schema()
    return j


def _open_other(j, symbol):
    d = _hand(side=1, entry="100", stop="99", qty="0.5", margin="10", lev=5, symbol=symbol)
    return execute_paper(d, portfolio_id="brain", run_id=RUN, journal=j, now_ms=NOW - 5000).position_id


def _candidate(j, symbol="BTCUSDT", eid="brain-decision-cap", ts=NOW - 1000):
    d = _hand(side=1, entry="100", stop="99", symbol=symbol, lev=5)
    d.occurred_at_ms = ts
    d.risk_quote = quote_paper_risk(ROOMY, RiskRequest(
        D("1000"), D("1000"), D("0"), D("0"), D("100"), D("99"), 1, 5, RULES["exchange_leverage_limit"],
        RULES["quantity_step"], RULES["minimum_notional"], RULES["maintenance_fraction"], True, False, False))
    assert d.risk_quote.allowed
    d.journal_event_id = eid
    j.append(Event(eid, "brain", RUN, "brain_decision", ts, "test",
                   {"symbol": symbol, "kind": "OPEN", "status": "APPROVED", "rationale": d.rationale}))
    return d


def _inputs():
    return dict(initial_equity=D("1000"), risk_policy=ROOMY, exit_healthy=lambda _: True,
                mandate_problem=lambda: None, budget_problem=lambda: None, daily_loss_halted=lambda _: False,
                paused=lambda: False, market_rules=lambda _: RULES, market_price=lambda *_: D("100"),
                market_fresh=lambda *_: True)


def _recheck(j, d):
    return recheck_paper_open(decision=d, journal=j, run_id=RUN, now_ms=NOW, **_inputs())


def _commit(j, d, folder):
    return commit_paper_open(journal=j, data_dir=folder, run_id=RUN, decision=d, clock_ms=lambda: NOW,
                             guard_inputs=_inputs(), slippage_bps=0, desk_mode="paper")


def test_the_cap_is_four():
    assert MAX_OPEN_POSITIONS == 4


def test_zero_and_three_open_positions_allow_a_new_open(tmp_path):
    for n in (0, 3):
        folder = tmp_path / str(n)
        folder.mkdir()
        j = _journal(folder)
        for s in OTHERS[:n]:
            _open_other(j, s)
        res = _recheck(j, _candidate(j))
        assert (res.allowed, res.code) == (True, "validated_current_paper_risk"), n


def test_four_open_positions_refuse_a_fifth(tmp_path):
    j = _journal(tmp_path)
    for s in OTHERS[:4]:
        _open_other(j, s)
    res = _recheck(j, _candidate(j))
    assert (res.allowed, res.code) == (False, "max_open_positions")


def test_closing_one_of_four_allows_a_new_open(tmp_path):
    j = _journal(tmp_path)
    ids = [_open_other(j, s) for s in OTHERS[:4]]
    d = _candidate(j)
    assert _recheck(j, d).code == "max_open_positions"
    close_paper(portfolio_id="brain", run_id=RUN, position_id=ids[0], exit_price=D("102"), reason="manual",
                fee_bps=6, journal=j, now_ms=NOW - 2000)
    assert _recheck(j, d).allowed is True


def test_after_a_restart_the_state_is_rebuilt_from_the_journal(tmp_path):
    j = _journal(tmp_path)
    ids = [_open_other(j, s) for s in OTHERS[:4]]
    _candidate(j)
    j.close() if hasattr(j, "close") else None
    j2 = EventJournal(tmp_path / "journal.db")                       # nuovo processo: nessuno stato in memoria
    d2 = _candidate(j2, eid="brain-decision-cap-2", ts=NOW - 900)
    assert _recheck(j2, d2).code == "max_open_positions"
    close_paper(portfolio_id="brain", run_id=RUN, position_id=ids[1], exit_price=D("102"), reason="manual",
                fee_bps=6, journal=j2, now_ms=NOW - 800)
    j3 = EventJournal(tmp_path / "journal.db")
    assert _recheck(j3, d2).allowed is True


def test_the_serialized_commit_path_enforces_the_cap(tmp_path):
    j = _journal(tmp_path)
    for s in OTHERS[:3]:
        _open_other(j, s)
    a = _candidate(j, "BTCUSDT", "dec-a", NOW - 1000)
    b = _candidate(j, "ADAUSDT", "dec-b", NOW - 999)
    with _real_sidecar(tmp_path) as svc:
        svc.tick(NOW)
        assert _commit(j, a, tmp_path).code == "paper_open_committed"           # quarta
        res = _commit(j, b, tmp_path)
    assert (res.allowed, res.code) == (False, "max_open_positions")               # quinta: rifiutata
    assert sum(1 for e in j.list_run("brain", RUN) if e.event.kind == "paper_open") == 4


def test_concurrent_openers_are_serialized_and_the_cap_still_holds(tmp_path):
    """Un'apertura concorrente non puo' passare mentre un'altra tiene il lock; dopo, vede lo stato aggiornato."""
    j = _journal(tmp_path)
    for s in OTHERS[:3]:
        _open_other(j, s)
    a = _candidate(j, "BTCUSDT", "dec-a", NOW - 1000)
    b = _candidate(j, "ADAUSDT", "dec-b", NOW - 999)
    with _real_sidecar(tmp_path) as svc:
        svc.tick(NOW)
        fd = os.open(tmp_path / ".brain-paper-open.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)                     # un altro writer sta aprendo
            assert _commit(j, b, tmp_path).code == "open_lease_busy"
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        assert _commit(j, a, tmp_path).code == "paper_open_committed"
        assert _commit(j, b, tmp_path).code == "max_open_positions"
    assert sum(1 for e in j.list_run("brain", RUN) if e.event.kind == "paper_open") == 4
