"""Issue #124 (P0): il blocco giornaliero non si perde con file mancante/corrotto, scrittura fallita o riavvio.

Test offline: journal V3 vero (SQLite temporaneo), prezzi e candele sintetici, nessuna rete, nessun runner reale.
I test marcati «baseline» non passano ``audit``: sul codice precedente alla correzione restituiscono ``ok`` (rossi).
"""
from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tests.test_brain_f7_outcomes import _hand
from backend.v3.events import EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.runner import daily_loss as dl
from backend.v3.runner.daily_loss import (
    DAY_MS, MINUTE_MS, STATE_FILE, DailyLossGuard, evaluate_daily_loss, max_daily_loss_between,
)
from backend.v3.runner.runner import Runner

D = Decimal
HOUR = 3_600_000
DAY0 = 20_000 * DAY_MS
NOW = DAY0 + 12 * HOUR
EQUITY = D("1000")
WARN, HALT = D("0.35"), D("0.50")
PF, RUN = "brain", "r-latch"
CRASH = (NOW - HOUR, NOW - HOUR + 5 * MINUTE_MS)      # minuti in cui il prezzo crolla a 45 (perdita 55 %)


class World:
    """Un long 10 pezzi a 100 aperto alle 09:00 UTC; prezzo 100, crollo a 45 per cinque minuti alle 11:00, poi 100."""

    def __init__(self, *, with_position=True):
        self.dir = Path(tempfile.mkdtemp())
        self.j = EventJournal(str(self.dir / "journal.db"))
        self.j.init_schema()
        self.closes_calls = []
        if with_position:
            h = _hand(side=1, entry="100", stop="40", qty="10", margin="100", symbol="AAAUSDT")
            execute_paper(h, portfolio_id=PF, run_id=RUN, journal=self.j, now_ms=NOW - 3 * HOUR)

    @staticmethod
    def price_at(mark_ms):
        """Chiusura della barra [mark-1m, mark)."""
        return D("45") if CRASH[0] <= mark_ms < CRASH[1] else D("100")

    def evaluate(self, now):
        return evaluate_daily_loss(journal=self.j, portfolio_id=PF, run_id=RUN, initial_equity=EQUITY, now_ms=now,
                                   price_of=lambda _s, t: self.price_at(t // MINUTE_MS * MINUTE_MS),
                                   warn_fraction=WARN, halt_fraction=HALT)

    def closes_of(self, sym, lo, hi):
        self.closes_calls.append((sym, lo, hi))
        return {t: self.price_at(t + MINUTE_MS) for t in range(lo, hi, MINUTE_MS)}

    def audit(self, from_ms, now_ms):
        return max_daily_loss_between(journal=self.j, portfolio_id=PF, run_id=RUN, initial_equity=EQUITY,
                                      from_ms=from_ms, now_ms=now_ms, closes_of=self.closes_of)

    def guard(self, *, audit=True, send=None):
        kw = {"audit": self.audit} if audit is True else ({} if audit is None else {"audit": audit})
        return DailyLossGuard(data_dir=self.dir, evaluate=self.evaluate, send=send,
                              warn_fraction=WARN, halt_fraction=HALT, **kw)

    def state(self):
        return json.loads((self.dir / STATE_FILE).read_text(encoding="utf-8"))


@pytest.fixture
def broken_disk(monkeypatch):
    def boom(*_a, **_k):
        raise OSError("disk full")
    on = {"v": False}
    real = dl.tempfile.mkstemp
    monkeypatch.setattr(dl.tempfile, "mkstemp", lambda *a, **k: boom() if on["v"] else real(*a, **k))
    return on


def _halt_while_disk_is_broken(w, broken_disk):
    g = w.guard()
    assert g(NOW - 2 * HOUR).level == "ok"                     # stato v2 su disco: ok, controllato alle 10:00
    broken_disk["v"] = True
    assert g(CRASH[0] + 30_000).level == "halt"                # stop in memoria, ma il disco rifiuta la scrittura
    with pytest.raises(ValueError, match="^daily_loss_latch_not_persisted$"):
        g.recheck(CRASH[0] + 40_000)                           # percorso post-AI: apertura negata
    broken_disk["v"] = False
    return g


# ----------------------------------------------------------------------------- casi della Issue #124
def test_restart_after_unpersisted_halt_with_recovery_stays_halted_by_reconstruction(broken_disk):
    w = World()
    _halt_while_disk_is_broken(w, broken_disk)
    assert w.state()["halt_latched"] is False                  # su disco e' rimasto «ok delle 10:00»
    out = w.guard()(NOW)                                       # riavvio alle 12:00, prezzo risalito
    assert out.level == "halt" and out.loss_fraction == D("0")
    st = w.state()
    assert (st["halt_latched"], st["latch_reason"], st["checked_through_ms"]) == (True, "loss", NOW)
    assert w.closes_calls and w.closes_calls[0][1] <= NOW - 2 * HOUR   # ricostruito dall'ultimo istante dimostrato


def test_baseline_restart_after_unpersisted_halt_without_reconstruction_is_fail_closed(broken_disk):
    w = World()
    _halt_while_disk_is_broken(w, broken_disk)
    out = w.guard(audit=None)(NOW)
    assert out.level == "halt" and w.state()["latch_reason"] == "unverified"


@pytest.mark.parametrize("content", ["{corrotto", "", "[]", '{"version": 2}',
                                     json.dumps({"day_start_ms": DAY0, "warn_sent": "no", "halt_sent": False,
                                                 "halt_latched": False})])
def test_corrupt_file_after_activity_reconstructs_the_day(content):
    w = World()
    g = w.guard()
    assert g(CRASH[0] + 30_000).level == "halt"
    (w.dir / STATE_FILE).write_text(content, encoding="utf-8")
    assert w.guard()(NOW).level == "halt" and w.state()["latch_reason"] == "loss"


@pytest.mark.parametrize("content", ["{corrotto", "[]"])
def test_baseline_corrupt_file_after_activity_without_reconstruction_is_fail_closed(content):
    w = World()
    assert w.guard(audit=None)(CRASH[0] + 30_000).level == "halt"
    (w.dir / STATE_FILE).write_text(content, encoding="utf-8")
    assert w.guard(audit=None)(NOW).level == "halt"


def test_deleted_file_after_activity_reconstructs_the_day():
    w = World()
    assert w.guard()(CRASH[0] + 30_000).level == "halt"
    (w.dir / STATE_FILE).unlink()
    assert w.guard()(NOW).level == "halt" and w.state()["latch_reason"] == "loss"


def test_baseline_deleted_file_after_activity_without_reconstruction_is_fail_closed():
    w = World()
    assert w.guard(audit=None)(CRASH[0] + 30_000).level == "halt"
    (w.dir / STATE_FILE).unlink()
    assert w.guard(audit=None)(NOW).level == "halt"


def test_first_start_of_a_virgin_run_is_ok_and_asks_no_price():
    w = World(with_position=False)
    assert not (w.dir / STATE_FILE).exists()
    assert w.guard()(NOW).level == "ok" and w.closes_calls == []
    assert w.state()["halt_latched"] is False


def test_first_start_without_any_reconstruction_is_fail_closed_until_proven():
    w = World(with_position=False)
    assert w.guard(audit=None)(NOW).level == "halt"            # nessuna prova: niente aperture (uscite libere)


def test_unwritable_disk_denies_new_openings_even_when_the_loss_is_ok(broken_disk):
    w = World()
    g = w.guard()
    assert g(NOW - 2 * HOUR).level == "ok"
    broken_disk["v"] = True
    with pytest.raises(ValueError, match="^daily_loss_state_not_persisted$"):
        g.recheck(NOW - 2 * HOUR + MINUTE_MS)


def test_restart_at_utc_midnight_releases_yesterdays_halt_and_checks_only_the_new_day():
    w = World()
    assert w.guard()(CRASH[0] + 30_000).level == "halt"
    tomorrow = DAY0 + DAY_MS + 2 * MINUTE_MS
    w.closes_calls.clear()
    out = w.guard()(tomorrow)
    assert out.level == "ok" and w.state()["day_start_ms"] == DAY0 + DAY_MS
    assert all(lo >= DAY0 + DAY_MS - MINUTE_MS for _s, lo, _hi in w.closes_calls)


def test_a_state_file_of_the_previous_day_does_not_hide_a_crash_of_today():
    w = World()
    st = DailyLossGuard._blank(DAY0 - DAY_MS)
    st["checked_through_ms"] = DAY0 - 1
    (w.dir / STATE_FILE).write_text(json.dumps(st), encoding="utf-8")
    assert w.guard()(NOW).level == "halt"


def test_restarts_are_idempotent():
    w = World()
    assert w.guard()(CRASH[0] + 30_000).level == "halt"
    snaps = []
    for _ in range(3):
        assert w.guard()(NOW).level == "halt"
        snaps.append(w.state())
    assert snaps[0] == snaps[1] == snaps[2]


def test_clock_going_backwards_is_fail_closed():
    w = World()
    assert w.guard()(NOW - 2 * HOUR).level == "ok"                # prima del crollo delle 11:00
    out = w.guard()(NOW - 2 * HOUR - 10 * MINUTE_MS)
    assert out.level == "halt" and w.state()["latch_reason"] == "unverified"


def test_unverified_block_is_lifted_only_by_a_later_successful_reconstruction():
    w = World(with_position=False)
    calls = {"n": 0}

    def flaky(from_ms, now_ms):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("history unavailable")
        return w.audit(from_ms, now_ms)

    g = w.guard(audit=flaky)
    assert g(NOW).level == "halt" and w.state()["latch_reason"] == "unverified"
    assert g(NOW + MINUTE_MS).level == "halt" and calls["n"] == 1        # non si riprova prima di 5 minuti
    assert g(NOW + 5 * MINUTE_MS).level == "ok" and calls["n"] == 2
    assert w.state()["halt_latched"] is False


def test_a_loss_block_is_never_lifted_before_midnight_even_by_a_clean_reconstruction():
    w = World()
    g = w.guard(audit=lambda f, n: D("0"))
    assert g(CRASH[0] + 30_000).level == "halt"
    for t in (NOW, NOW + HOUR, DAY0 + DAY_MS - MINUTE_MS):
        assert w.guard(audit=lambda f, n: D("0"))(t).level == "halt"


def test_legacy_v1_state_is_migrated_conservatively():
    w = World()
    legacy = {"day_start_ms": DAY0, "warn_sent": False, "halt_sent": True, "halt_latched": True}
    (w.dir / STATE_FILE).write_text(json.dumps(legacy), encoding="utf-8")
    assert w.guard(audit=None)(NOW).level == "halt"            # latch v1 rispettato senza bisogno di prove
    assert w.state()["latch_reason"] == "loss"                 # migrato come blocco per perdita, non «unverified»
    legacy["halt_latched"] = False
    (w.dir / STATE_FILE).write_text(json.dumps(legacy), encoding="utf-8")
    assert w.guard()(NOW).level == "halt"                      # v1 non bloccato: si ricostruisce e si trova il crollo
    assert w.state()["version"] == 2


def test_a_missing_bar_in_the_reconstruction_is_fail_closed():
    w = World()
    assert w.guard()(NOW - 2 * HOUR).level == "ok"
    w.closes_of = lambda sym, lo, hi: {}
    assert w.guard()(NOW).level == "halt" and w.state()["latch_reason"] == "unverified"


def test_a_fresh_state_of_yesterday_does_not_skip_the_first_minutes_of_today():
    """Controllo persistito alle 23:59 (giorno DAY0), riavvio alle 00:02 del giorno dopo: il crollo delle 00:01 conta."""
    w = World()                                                # long aperto alle 09:00 di DAY0, ancora aperto
    day1 = DAY0 + DAY_MS
    st = DailyLossGuard._blank(DAY0)
    st["checked_through_ms"] = day1 - MINUTE_MS
    (w.dir / STATE_FILE).write_text(json.dumps(st), encoding="utf-8")
    w.price_at = staticmethod(lambda m: D("45") if day1 < m <= day1 + MINUTE_MS else D("100"))
    out = w.guard()(day1 + 2 * MINUTE_MS)                     # entro pochi minuti, ma di un altro giorno UTC
    assert out.level == "halt" and w.state()["day_start_ms"] == day1 and w.state()["latch_reason"] == "loss"


def test_clock_going_backwards_keeps_a_loss_block_as_a_loss_block():
    w = World()
    assert w.guard()(CRASH[0] + 30_000).level == "halt"
    assert w.guard(audit=lambda f, n: D("0"))(CRASH[0] - 30 * MINUTE_MS).level == "halt"
    assert w.state()["latch_reason"] == "loss"


def test_continuous_operation_in_the_same_process_does_not_reconstruct():
    w = World()
    g = w.guard()
    g(NOW - 2 * HOUR)                                          # primo controllo dopo l'avvio: ricostruisce (vedi sotto)
    first = len(w.closes_calls)
    for k in range(1, 5):
        g(NOW - 2 * HOUR + k * MINUTE_MS)                     # un controllo per minuto, nessun minuto saltato
    assert len(w.closes_calls) == first


# ----------------------------------------------------------------------------- Issue #124, verifica 10:00/10:01/10:02
T10 = NOW - 2 * HOUR                                           # 10:00 UTC


def _crash_only_at_1001(w):
    w.price_at = staticmethod(lambda m: D("45") if m == T10 + MINUTE_MS else D("100"))


def test_owner_scenario_failed_latch_write_then_restart_within_minutes_stays_halted(broken_disk):
    """Ok persistito alle 10:00; alle 10:01 la perdita supera lo stop ma il latch non si scrive; il PnL rientra;
    riavvio alle 10:02. Prima della correzione: ``ok`` (fail-open)."""
    w = World()
    _crash_only_at_1001(w)
    g = w.guard()
    assert g(T10).level == "ok"
    broken_disk["v"] = True
    assert g(T10 + MINUTE_MS).level == "halt"
    broken_disk["v"] = False
    assert w.state()["halt_latched"] is False and w.state()["checked_through_ms"] == T10
    out = w.guard()(T10 + 2 * MINUTE_MS)
    assert out.level == "halt" and w.state()["latch_reason"] == "loss"


@pytest.mark.parametrize("restart_at", [T10 + MINUTE_MS + 50_000, T10 + 2 * MINUTE_MS, T10 + 2 * MINUTE_MS + 59_000,
                                        T10 + 3 * MINUTE_MS])
def test_any_restart_after_an_unpersisted_crash_minute_reconstructs_it(broken_disk, restart_at):
    w = World()
    _crash_only_at_1001(w)
    g = w.guard()
    g(T10)
    broken_disk["v"] = True
    g(T10 + MINUTE_MS)
    broken_disk["v"] = False
    assert w.guard()(restart_at).level == "halt"


def test_a_minute_skipped_for_missing_prices_in_the_same_process_is_reconstructed():
    """Nessun riavvio: alle 10:01 il prezzo manca (la valutazione fallisce, nessuna apertura), proprio nel minuto del
    crollo; alle 10:02 il prezzo c'e' ed e' risalito. Il minuto saltato va ricostruito."""
    w = World()
    _crash_only_at_1001(w)
    g = w.guard()
    assert g(T10).level == "ok"
    live = w.evaluate
    w.evaluate = lambda now: (_ for _ in ()).throw(ValueError("daily_loss_price_unavailable")) if now // MINUTE_MS == (T10 + MINUTE_MS) // MINUTE_MS else live(now)
    g._evaluate = w.evaluate
    with pytest.raises(ValueError):
        g(T10 + MINUTE_MS)
    assert g(T10 + 2 * MINUTE_MS).level == "halt" and w.state()["latch_reason"] == "loss"


def test_a_normal_restart_without_any_crash_is_not_blocked():
    w = World()
    g = w.guard()
    for k in range(3):
        assert g(T10 + k * MINUTE_MS).level == "ok"
    assert w.guard()(T10 + 4 * MINUTE_MS).level == "ok"       # riavvio: ricostruisce 10:03-10:04, nessun crollo
    assert w.state()["halt_latched"] is False


def test_restart_reconstruction_failing_is_not_a_permanent_block():
    w = World()
    w.guard()(T10)
    calls = {"n": 0}

    def flaky(from_ms, now_ms):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("history unavailable")
        return w.audit(from_ms, now_ms)

    g = w.guard(audit=flaky)
    assert g(T10 + 2 * MINUTE_MS).level == "halt" and w.state()["latch_reason"] == "unverified"
    assert g(T10 + 7 * MINUTE_MS).level == "ok" and w.state()["halt_latched"] is False


def test_halt_alert_text_distinguishes_unverified_from_a_real_loss():
    texts = []
    w = World(with_position=False)
    w.guard(audit=None, send=lambda t: texts.append(t) or True)(NOW)
    assert len(texts) == 1 and "non riesco a dimostrare" in texts[0]


# ----------------------------------------------------------------------------- ricostruzione
def test_reconstruction_matches_the_live_formula_at_each_minute():
    w = World()
    for mark in (CRASH[0] - MINUTE_MS, CRASH[0], CRASH[0] + 2 * MINUTE_MS, CRASH[1], NOW):
        live = w.evaluate(mark).loss_fraction
        rebuilt = max_daily_loss_between(journal=w.j, portfolio_id=PF, run_id=RUN, initial_equity=EQUITY,
                                         from_ms=mark - MINUTE_MS, now_ms=mark, closes_of=w.closes_of)
        assert rebuilt == live, mark


def test_reconstruction_counts_a_realized_close_from_the_first_minute_after_it():
    """Chiusura in perdita alle 11:00:30 e chiusura in guadagno alle 11:01:30: il picco del minuto 11:01 conta."""
    w = World(with_position=False)
    from backend.v3.executor.paper_close import close_paper
    for sym, exit_px, at in (("BBBUSDT", "40", CRASH[0] + 30_000), ("CCCUSDT", "130", CRASH[0] + 90_000)):
        h = _hand(side=1, entry="100", stop="30", qty="10", margin="100", symbol=sym)
        pid = execute_paper(h, portfolio_id=PF, run_id=RUN, journal=w.j, now_ms=NOW - 3 * HOUR).position_id
        close_paper(portfolio_id=PF, run_id=RUN, position_id=pid, exit_price=D(exit_px), reason="stop", fee_bps=0,
                    journal=w.j, now_ms=at)
    w.price_at = staticmethod(lambda m: D("100"))
    for mark, expected in ((CRASH[0], D("0")), (CRASH[0] + MINUTE_MS, D("0.6")), (CRASH[0] + 2 * MINUTE_MS, D("0.3"))):
        rebuilt = max_daily_loss_between(journal=w.j, portfolio_id=PF, run_id=RUN, initial_equity=EQUITY,
                                         from_ms=mark - MINUTE_MS, now_ms=mark, closes_of=w.closes_of)
        assert rebuilt == expected, mark                       # -600 a 11:00:30, +300 a 11:01:30
    assert max_daily_loss_between(journal=w.j, portfolio_id=PF, run_id=RUN, initial_equity=EQUITY,
                                  from_ms=CRASH[0], now_ms=NOW, closes_of=w.closes_of) == D("0.6")


def test_reconstruction_rejects_bad_inputs():
    w = World()
    for bad in (0, -1, True, "1"):
        with pytest.raises(ValueError):
            max_daily_loss_between(journal=w.j, portfolio_id=PF, run_id=RUN, initial_equity=EQUITY,
                                   from_ms=0, now_ms=bad, closes_of=w.closes_of)


# ----------------------------------------------------------------------------- uscite indipendenti
def test_sidecar_exits_stay_owned_elsewhere_while_new_openings_are_blocked():
    w = World(with_position=False)
    opened, health = [], []
    guard = w.guard(audit=None)
    runner = Runner(run_id=RUN, data_dir=w.dir, run_monitor=None,
                    run_cycle=lambda now, slot: opened.append(now), cycle_delay_ms=0, exit_mode="sidecar",
                    exit_healthy=lambda now: health.append(now) or True, fresh_clock_ms=lambda: NOW + 1_000,
                    daily_loss=guard)
    res = runner.tick(NOW)
    assert res.state == "halted" and opened == [] and health == [NOW] and res.monitor is None


def test_legacy_mode_monitor_keeps_running_while_new_openings_are_blocked():
    w = World(with_position=False)
    mon, opened = [], []
    runner = Runner(run_id=RUN, data_dir=w.dir, run_monitor=lambda n: mon.append(n) or None,
                    run_cycle=lambda now, slot: opened.append(now), cycle_delay_ms=0, daily_loss=w.guard(audit=None))
    res = runner.tick(NOW)
    assert res.state == "halted" and opened == [] and mon == [NOW]


def test_no_amounts_in_the_state_file():
    w = World()
    w.guard()(NOW)
    raw = (w.dir / STATE_FILE).read_text(encoding="utf-8")
    assert "1000" not in raw and "100" not in raw.replace(str(NOW), "").replace(str(DAY0), "")
    assert sorted(os.listdir(w.dir)) == ["journal.db", STATE_FILE] or set(os.listdir(w.dir)) >= {STATE_FILE}
