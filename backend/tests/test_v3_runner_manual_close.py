"""Chiusura manuale del Brain PAPER: file di richiesta -> ``close_paper(reason="manual")`` -> file di esito.

Journal vero, esecutore vero, direttore vero; si finge solo il prezzo (``price_of``) e, per la prova end-to-end,
Bitget e il modello (come in ``test_v3_runner_e2e``). Valori tutti diversi fra loro, nessun controllo di tempi.
"""
from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tests.test_v3_runner_e2e import G, M, RUN as E2E_RUN, _approve, _beat, _events, _setup
from backend.tests.test_v3_runner_feed_monitor import _hand
from backend.v3.events import EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.executor.paper_close import close_paper
from backend.v3.outcomes import extract_outcomes
from backend.v3.runner.cycle import CycleReport
from backend.v3.runner.manual_close import (
    MAX_AGE_MS, MAX_IDS, REQUEST_FILE, RESULT_FILE, WORK_FILE, ManualCloseReport, run_manual_close,
)
from backend.v3.runner.monitor import MonitorReport
from backend.v3.runner.runner import Runner

D = Decimal
RUN = "r-manual"
NOW = 1_800_000_123_456
FEE = 7


def _journal():
    j = EventJournal(os.path.join(tempfile.mkdtemp(), "journal.db"))
    j.init_schema()
    return j


def _open(j, symbol, side=1, entry="30000", stop="29000"):
    d = _hand(side=side, entry=entry, stop=stop, symbol=symbol)
    return execute_paper(d, portfolio_id="brain", run_id=RUN, journal=j, now_ms=NOW - 3_600_000).position_id


def _closes(j):
    return [s.event.payload for s in j.list_run("brain", RUN) if s.event.kind == "paper_close"]


class Rig:
    def __init__(self, prices=None):
        self.j = _journal()
        self.dir = Path(tempfile.mkdtemp())
        self.prices = prices if prices is not None else {}
        self.asked = []

    def price_of(self, symbol, now):
        self.asked.append((symbol, now))
        p = self.prices[symbol]
        if isinstance(p, Exception):
            raise p
        return p

    def ask(self, body, *, raw=None):
        text = raw if raw is not None else json.dumps(body)
        (self.dir / REQUEST_FILE).write_text(text, encoding="utf-8")

    def run(self, now=NOW):
        return run_manual_close(journal=self.j, portfolio_id="brain", run_id=RUN, data_dir=self.dir,
                                price_of=self.price_of, fee_bps=FEE, now_ms=now)

    def result(self):
        return json.loads((self.dir / RESULT_FILE).read_text(encoding="utf-8"))

    def files(self):
        return sorted(p.name for p in self.dir.iterdir())


def test_closing_by_id_closes_only_that_position_at_the_market_price_with_reason_manual():
    r = Rig({"AAAUSDT": D("31234.5"), "BBBUSDT": D("1")})
    a, b = _open(r.j, "AAAUSDT"), _open(r.j, "BBBUSDT")
    r.ask({"ts_ms": NOW - 5_000, "position_ids": [a]})
    rep = r.run()
    assert rep == ManualCloseReport("done", (a,), ())
    (close,) = _closes(r.j)
    assert close["position_id"] == a and close["reason"] == "manual" and close["exit_price"] == "31234.5"
    assert close["fee_bps"] == str(FEE) and close["opened_at_ms"] == NOW - 3_600_000 and close["held_ms"] == 3_600_000
    assert r.asked == [("AAAUSDT", NOW)]                                    # nessun prezzo chiesto per l'altra
    assert r.result() == {"request_ts_ms": NOW - 5_000, "done_ms": NOW, "status": "done",
                          "closed": [a], "failed": []}
    assert r.files() == [RESULT_FILE]                                       # richiesta e .work spariti, niente .tmp
    out = extract_outcomes(r.j, "brain", RUN).outcomes
    assert [o.exit_reason for o in out] == ["manual"]                       # il Brain la riconosce come manuale
    rep2 = r.run()
    assert rep2 is None and len(_closes(r.j)) == 1                          # non si esegue due volte


def test_close_all_closes_every_open_position_and_skips_the_closed_ones():
    r = Rig({"AAAUSDT": D("30100"), "BBBUSDT": D("30200"), "CCCUSDT": D("30300")})
    a, b, c = _open(r.j, "AAAUSDT"), _open(r.j, "BBBUSDT", side=-1), _open(r.j, "CCCUSDT")
    close_paper(portfolio_id="brain", run_id=RUN, position_id=c, exit_price=D("30001"), reason="stop",
                fee_bps=FEE, journal=r.j, now_ms=NOW - 1_000)
    r.ask({"ts_ms": NOW, "all": True})
    rep = r.run()
    assert (rep.status, set(rep.closed), rep.failed) == ("done", {a, b}, ())
    assert {c_["position_id"]: c_["reason"] for c_ in _closes(r.j)} == {a: "manual", b: "manual", c: "stop"}
    assert {s for s, _ in r.asked} == {"AAAUSDT", "BBBUSDT"}                # per la gia' chiusa nessun prezzo


def test_a_short_is_closed_with_the_right_sign():
    r = Rig({"AAAUSDT": D("29000")})
    a = _open(r.j, "AAAUSDT", side=-1, entry="30000", stop="31000")
    r.ask({"ts_ms": NOW, "position_ids": [a]})
    r.run()
    (close,) = _closes(r.j)
    assert D(close["gross_pnl"]) > 0 and D(close["realized_pnl"]) == D(close["gross_pnl"]) - D(close["fees"]) > 0


def test_age_limit_is_exactly_ten_minutes():
    assert MAX_AGE_MS == 10 * 60 * 1000
    r = Rig({"AAAUSDT": D("30100")})
    a = _open(r.j, "AAAUSDT")
    r.ask({"ts_ms": NOW - MAX_AGE_MS - 1, "position_ids": [a]})
    assert r.run() == ManualCloseReport("expired", (), ())
    assert _closes(r.j) == [] and r.asked == [] and r.result()["status"] == "expired"
    r.ask({"ts_ms": NOW - MAX_AGE_MS, "position_ids": [a]})
    assert r.run().closed == (a,)


@pytest.mark.parametrize("raw", [
    "non json", "[]", "null", "{}", '{"ts_ms": 5}', '{"position_ids": ["x"]}',
    '{"ts_ms": true, "position_ids": ["x"]}', '{"ts_ms": 1.5e12, "position_ids": ["x"]}',
    '{"ts_ms": "1800000000000", "position_ids": ["x"]}', '{"ts_ms": -1, "all": true}', '{"ts_ms": 0, "all": true}',
    json.dumps({"ts_ms": NOW + MAX_AGE_MS + 1, "all": True}),                 # orologio sbagliato (futuro)
    json.dumps({"ts_ms": NOW, "position_ids": []}),
    json.dumps({"ts_ms": NOW, "position_ids": "abc"}),
    json.dumps({"ts_ms": NOW, "position_ids": ["ok", 7]}),
    json.dumps({"ts_ms": NOW, "position_ids": ["has space"]}),
    json.dumps({"ts_ms": NOW, "position_ids": ["../etc"]}),
    json.dumps({"ts_ms": NOW, "position_ids": ["x" * 65]}),
    json.dumps({"ts_ms": NOW, "position_ids": [f"p{i}" for i in range(MAX_IDS + 1)]}),
    json.dumps({"ts_ms": NOW, "all": False}),
    json.dumps({"ts_ms": NOW, "all": "yes"}),
    json.dumps({"ts_ms": NOW, "all": True, "position_ids": ["x"]}),
    json.dumps({"ts_ms": NOW, "position_ids": ["x"], "all": False}),
])
def test_invalid_requests_close_nothing_and_are_reported_without_echoing_the_content(raw):
    r = Rig({"AAAUSDT": D("30100")})
    _open(r.j, "AAAUSDT")
    r.ask(None, raw=raw)
    assert r.run() == ManualCloseReport("invalid_request", (), ())
    assert _closes(r.j) == [] and r.asked == []
    assert r.result() == {"request_ts_ms": 0, "done_ms": NOW, "status": "invalid_request", "closed": [], "failed": []}
    assert r.files() == [RESULT_FILE]


def test_the_maximum_number_of_ids_is_accepted():
    r = Rig()
    r.ask({"ts_ms": NOW, "position_ids": [f"p{i}" for i in range(MAX_IDS)]})
    rep = r.run()
    assert rep.status == "done" and len(rep.failed) == MAX_IDS and {c for _, c in rep.failed} == {"position_not_open"}


def test_unknown_and_already_closed_ids_are_reported_per_id_and_the_rest_still_closes():
    r = Rig({"AAAUSDT": D("30100"), "BBBUSDT": D("30200")})
    a, b = _open(r.j, "AAAUSDT"), _open(r.j, "BBBUSDT")
    close_paper(portfolio_id="brain", run_id=RUN, position_id=b, exit_price=D("29001"), reason="stop",
                fee_bps=FEE, journal=r.j, now_ms=NOW - 1)
    r.ask({"ts_ms": NOW, "position_ids": ["nope", b, a]})
    rep = r.run()
    assert rep.closed == (a,) and rep.failed == (("nope", "position_not_open"), (b, "position_not_open"))
    assert r.result()["failed"] == [["nope", "position_not_open"], [b, "position_not_open"]]


def test_duplicate_ids_are_collapsed():
    r = Rig({"AAAUSDT": D("30100")})
    a = _open(r.j, "AAAUSDT")
    r.ask({"ts_ms": NOW, "position_ids": [a, a, a]})
    rep = r.run()
    assert rep.closed == (a,) and rep.failed == () and len(r.asked) == 1


def test_a_missing_price_leaves_the_position_open_and_the_request_is_consumed():
    r = Rig({"AAAUSDT": ValueError("no_recent_bar"), "BBBUSDT": D("30200")})
    a, b = _open(r.j, "AAAUSDT"), _open(r.j, "BBBUSDT")
    r.ask({"ts_ms": NOW, "all": True})
    rep = r.run()
    assert rep.closed == (b,) and rep.failed == ((a, "price_unavailable"),)
    assert [c["position_id"] for c in _closes(r.j)] == [b]
    assert r.files() == [RESULT_FILE] and r.run() is None                    # niente nuovi tentativi da soli


def test_a_close_that_loses_the_race_against_the_monitor_is_reported_not_raised():
    r = Rig()
    a = _open(r.j, "AAAUSDT")

    def racing(symbol, now):                                                # il monitor chiude mentre si chiede il prezzo
        close_paper(portfolio_id="brain", run_id=RUN, position_id=a, exit_price=D("29000"), reason="stop",
                    fee_bps=FEE, journal=r.j, now_ms=NOW - 2)
        return D("30100")
    r.ask({"ts_ms": NOW, "position_ids": [a]})
    rep = run_manual_close(journal=r.j, portfolio_id="brain", run_id=RUN, data_dir=r.dir, price_of=racing,
                           fee_bps=FEE, now_ms=NOW)
    assert rep.closed == () and rep.failed == ((a, "position_already_closed"),)
    assert [c["reason"] for c in _closes(r.j)] == ["stop"]


def test_an_engine_refusal_carries_its_short_code_and_does_not_stop_the_others():
    r = Rig({"AAAUSDT": D("-1"), "BBBUSDT": D("30200")})                      # prezzo non valido per l'esecutore
    a, b = _open(r.j, "AAAUSDT"), _open(r.j, "BBBUSDT")
    r.ask({"ts_ms": NOW, "all": True})
    rep = r.run()
    assert rep.closed == (b,) and rep.failed == ((a, "invalid_exit_price"),)


def test_a_broken_journal_read_is_reported_and_closes_nothing():
    r = Rig()
    r.ask({"ts_ms": NOW, "all": True})
    r.j = object()                                                           # build_summary non sa leggerlo
    rep = r.run()
    assert rep == ManualCloseReport("done", (), (("*", "journal_read_failed"),))


def test_no_request_is_a_cheap_no_op_that_asks_for_no_price_and_writes_nothing():
    r = Rig({"AAAUSDT": D("30100")})
    _open(r.j, "AAAUSDT")
    assert r.run() is None and r.files() == [] and r.asked == []


def test_leftover_work_file_is_resumed_without_losing_a_second_request():
    r = Rig({"AAAUSDT": D("30100"), "BBBUSDT": D("30200")})
    a, b = _open(r.j, "AAAUSDT"), _open(r.j, "BBBUSDT")
    (r.dir / WORK_FILE).write_text(json.dumps({"ts_ms": NOW - 1, "position_ids": [a]}), encoding="utf-8")
    assert r.run().closed == (a,) and WORK_FILE not in r.files()
    (r.dir / WORK_FILE).write_text(json.dumps({"ts_ms": NOW - 1, "position_ids": [a]}), encoding="utf-8")
    r.ask({"ts_ms": NOW, "position_ids": [b]})
    assert r.run().failed == ((a, "position_not_open"),)
    assert REQUEST_FILE in r.files()    # request b never overwrote the prior .work
    assert r.run().closed == (b,)
    assert r.files() == [RESULT_FILE]
    assert [event["position_id"] for event in _closes(r.j)] == [a, b]


def test_a_binary_request_file_is_invalid_not_a_crash():
    r = Rig()
    (r.dir / REQUEST_FILE).write_bytes(b"\xff\xfe\x00garbage")
    assert r.run() == ManualCloseReport("invalid_request", (), ())
    assert r.files() == [RESULT_FILE]


@pytest.mark.parametrize("now", [0, -5, 1.5, "1", None, True])
def test_bad_now_is_refused(now):
    r = Rig()
    with pytest.raises(ValueError, match="invalid_now"):
        r.run(now)


def test_result_write_failure_does_not_raise_and_the_work_is_still_done(monkeypatch):
    r = Rig({"AAAUSDT": D("30100")})
    a = _open(r.j, "AAAUSDT")
    r.ask({"ts_ms": NOW, "position_ids": [a]})

    def boom(*a_, **k_):
        raise OSError("disk full")
    monkeypatch.setattr("backend.v3.runner.manual_close.tempfile.mkstemp", boom)
    assert r.run().closed == (a,)
    assert r.files() == []                                                   # nessun .tmp e nessun .work rimasti


# ----------------------------------------------------------------------------- direttore
class Beat:
    """Un direttore con monitor e ciclo finti e un comando finto: serve a vedere QUANDO il comando gira."""

    def __init__(self, commands, *, halted=lambda: None):
        self.dir = Path(tempfile.mkdtemp())
        self.order = []

        def mon(now):
            self.order.append(("monitor", now))
            return MonitorReport(0, (), ())

        def cyc(now, slot):
            self.order.append(("cycle", now))
            return CycleReport(now, (), (), (), ())

        def cmd(now):
            self.order.append(("commands", now))
            return commands(now)
        self.runner = Runner(run_id="run-1", data_dir=self.dir, run_monitor=mon, run_cycle=cyc, halted=halted,
                             run_commands=cmd)


def test_commands_run_on_every_tick_before_the_monitor_even_when_paused_or_halted():
    b = Beat(lambda now: None, halted=lambda: "no_mandate")
    (b.dir / "pause.flag").write_text("")
    b.runner.tick(G + 5_000)
    b.runner.tick(G + 10_000)                                               # stesso minuto: il monitor non ripete
    b.runner.tick(G + 70_000)
    assert b.order == [("commands", G + 5_000), ("monitor", G + 5_000), ("commands", G + 10_000),
                       ("commands", G + 70_000), ("monitor", G + 70_000)]


def test_the_report_is_exposed_and_a_failure_code_reaches_the_heartbeat():
    rep = ManualCloseReport("done", ("p1",), (("p2", "price_unavailable"),))
    b = Beat(lambda now: rep)
    t = b.runner.tick(G + 5_000)
    assert t.manual is rep and t.last_error == "manual:price_unavailable"
    assert json.loads((b.dir / "heartbeat.json").read_text())["last_error"] == "manual:price_unavailable"
    ok = Beat(lambda now: ManualCloseReport("done", ("p1",), ()))
    assert ok.runner.tick(G + 5_000).last_error is None


def test_a_crashing_command_does_not_stop_the_monitor():
    def boom(now):
        raise RuntimeError("boom")
    b = Beat(boom)
    t = b.runner.tick(G + 5_000)
    assert t.last_error == "commands_failed" and t.manual is None and ("monitor", G + 5_000) in b.order


def test_a_runner_without_commands_behaves_as_before():
    d = Path(tempfile.mkdtemp())
    run = Runner(run_id="run-1", data_dir=d, run_monitor=lambda n: MonitorReport(0, (), ()),
                 run_cycle=lambda n, s: CycleReport(n, (), (), (), ()))
    t = run.tick(G + 5_000)
    assert t.manual is None and t.last_error is None


# ----------------------------------------------------------------------------- tutto insieme
def test_end_to_end_the_user_closes_a_position_while_the_brain_is_paused_and_the_brain_learns_from_it():
    built, model, data_dir, config = _setup()
    _approve(built, data_dir, config)
    built.runner.tick(G + 25_000)                                           # il Brain apre BTC (long) ed ETH (short)
    opens = {e.payload["symbol"]: e.payload["position_id"] for e in _events(built, "paper_open")}
    assert set(opens) == {"BTCUSDT", "ETHUSDT"}
    (data_dir / "pause.flag").write_text("")
    (data_dir / REQUEST_FILE).write_text(json.dumps({"ts_ms": G + 6 * M, "position_ids": [opens["ETHUSDT"]]}))
    t = built.runner.tick(G + 6 * M + 5_000)
    assert t.state == "paused" and t.manual.closed == (opens["ETHUSDT"],)
    (close,) = _events(built, "paper_close")
    assert close.payload["symbol"] == "ETHUSDT" and close.payload["reason"] == "manual"
    assert close.payload["exit_price"] == "100"                    # ultimo minuto chiuso del feed
    assert close.payload["fee_bps"] == "6"
    res = json.loads((data_dir / RESULT_FILE).read_text())
    assert res["status"] == "done" and res["closed"] == [opens["ETHUSDT"]] and res["failed"] == []
    assert _beat(data_dir)["last_error"] is None
    out = extract_outcomes(built.journal, "brain", E2E_RUN).outcomes
    assert [(o.symbol, o.exit_reason) for o in out] == [("ETHUSDT", "manual")]
    t = built.runner.tick(G + 19 * M)                                       # BTC resta sotto il monitor: take-profit
    assert [r for _, r in t.monitor.closed] == ["take_profit"]
