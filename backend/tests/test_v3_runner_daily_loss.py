"""Freno di perdita giornaliera del Brain PAPER (decisione dell'utente 5/11: avviso al 35 %, stop al 50 %).

Tre livelli di prova:
* ``evaluate_daily_loss``: journal vero (``execute_paper`` / ``close_paper``), si finge solo il prezzo;
* ``DailyLossGuard`` + ``telegram_sender``: valutatore e invio finti, file di stato veri;
* ``Runner`` (direttore) e ``build_runner`` (end-to-end con candele e modello finti, come ``test_v3_runner_e2e``).
Valori tutti diversi fra loro, nessuna rete, nessun orologio di sistema.
"""
from __future__ import annotations

import dataclasses
import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tests.test_brain_f7_outcomes import _hand
from backend.tests.test_v3_runner_e2e import (
    G, LEGACY, M, RUN as E2E_RUN, VIEW, FakeModel, _approve, _beat, _events, _get_json_factory,
)
from backend.v3.brain_f2.engine import _policy_hash
from backend.v3.events import EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.executor.paper_close import close_paper
from backend.v3.runner import daily_loss as dl
from backend.v3.runner.alerts import TIMEOUT_S, telegram_sender
from backend.v3.runner.config import default_config_path, load_default_config, load_runner_config
from backend.v3.runner.cycle import CycleReport
from backend.v3.runner.daily_loss import (
    DAY_MS, STATE_FILE, DailyLoss, DailyLossGuard, day_start_ms, evaluate_daily_loss, pct_text,
)
from backend.v3.runner.manual_close import ManualCloseReport
from backend.v3.runner.monitor import MonitorReport
from backend.v3.runner.runner import CYCLE_MS, Runner
from backend.v3.runner.wiring import build_runner, mandate_template

D = Decimal
HOUR = 3_600_000
DAY0 = 20_000 * DAY_MS                       # un giorno UTC qualunque, allineato a mezzanotte
NOW = DAY0 + 12 * HOUR                       # mezzogiorno UTC, allineato al minuto
EQUITY = D("1000")
WARN, HALT = D("0.35"), D("0.50")
PF, RUN = "brain", "r-loss"


# ----------------------------------------------------------------------------- evaluate_daily_loss
class Rig:
    def __init__(self, prices=None):
        self.j = EventJournal(os.path.join(tempfile.mkdtemp(), "journal.db"))
        self.j.init_schema()
        self.prices = prices if prices is not None else {}
        self.asked = []

    def open(self, symbol="AAAUSDT", *, side=1, entry="100", qty="10", at=NOW - 3 * HOUR):
        stop = "50" if side == 1 else "150"
        d = _hand(side=side, entry=entry, stop=stop, qty=qty, margin="100", symbol=symbol)
        return execute_paper(d, portfolio_id=PF, run_id=RUN, journal=self.j, now_ms=at).position_id

    def close(self, pid, price, *, at=NOW - 2 * HOUR):
        close_paper(portfolio_id=PF, run_id=RUN, position_id=pid, exit_price=D(price), reason="stop", fee_bps=0,
                    journal=self.j, now_ms=at)

    def lose(self, amount, *, at=NOW - 2 * HOUR, symbol="LOSSUSDT"):
        """Una chiusura realizzata di ``amount`` (negativo = perdita): long 10 pezzi a 100."""
        pid = self.open(symbol, at=at - HOUR)
        self.close(pid, D("100") + D(amount) / 10, at=at)

    def price_of(self, symbol, now):
        self.asked.append((symbol, now))
        p = self.prices[symbol]
        if isinstance(p, Exception):
            raise p
        return p

    def evaluate(self, now=NOW, *, equity=EQUITY, warn=WARN, halt=HALT):
        return evaluate_daily_loss(journal=self.j, portfolio_id=PF, run_id=RUN, initial_equity=equity, now_ms=now,
                                   price_of=self.price_of, warn_fraction=warn, halt_fraction=halt)


def test_day_start_is_utc_midnight_and_pct_text_truncates_to_one_decimal():
    assert day_start_ms(NOW) == DAY0 and day_start_ms(DAY0) == DAY0 and day_start_ms(DAY0 - 1) == DAY0 - DAY_MS
    assert pct_text(D("0")) == "0.0" and pct_text(D("0.35")) == "35.0" and pct_text(D("1")) == "100.0"
    assert pct_text(D("0.34999")) == "34.9"          # mai arrotondata in su: non mostra 35 mentre il livello e' ok
    assert pct_text(D("0.4999999")) == "49.9" and pct_text(D("0.123456")) == "12.3"


def test_no_trades_is_ok_with_zero_loss():
    r = Rig()
    out = r.evaluate()
    assert out == DailyLoss("ok", D("0"), D("0"), DAY0) and r.asked == []


@pytest.mark.parametrize("loss,level", [
    ("-100", "ok"), ("-349", "ok"), ("-349.99", "ok"), ("-350", "warn"), ("-350.01", "warn"), ("-499", "warn"),
    ("-499.99", "warn"), ("-500", "halt"), ("-500.01", "halt"), ("-900", "halt")])
def test_realized_loss_today_levels_have_inclusive_thresholds_at_35_and_50_percent(loss, level):
    r = Rig()
    r.lose(loss)
    out = r.evaluate()
    assert out.level == level and out.loss_usd == -D(loss) and out.loss_fraction == -D(loss) / EQUITY
    assert out.day_start_ms == DAY0


def test_a_gain_is_not_a_loss_and_offsets_a_loss():
    r = Rig()
    r.lose("300", symbol="WINUSDT")
    assert r.evaluate() == DailyLoss("ok", D("0"), D("0"), DAY0)
    r.lose("-340", symbol="LOSSUSDT")                           # netto di oggi: -40
    out = r.evaluate()
    assert (out.level, out.loss_usd, out.loss_fraction) == ("ok", D("40"), D("0.04"))


def test_unrealized_loss_of_open_positions_counts_long_and_short():
    r = Rig({"AAAUSDT": D("65"), "BBBUSDT": D("135")})
    r.open("AAAUSDT", side=1)                                   # long da 100: 10 * (65 - 100) = -350
    out = r.evaluate()
    assert (out.level, out.loss_usd) == ("warn", D("350"))
    r2 = Rig({"BBBUSDT": D("135")})
    r2.open("BBBUSDT", side=-1)                                 # short da 100: -10 * (135 - 100) = -350
    out2 = r2.evaluate()
    assert (out2.level, out2.loss_usd) == ("warn", D("350"))
    assert r2.asked == [("BBBUSDT", NOW)]                       # il prezzo e' chiesto all'ora del controllo


def test_unrealized_gain_on_a_position_compensates_realized_loss():
    r = Rig({"AAAUSDT": D("130")})
    r.open("AAAUSDT", side=1)                                   # +300
    r.lose("-350")                                              # netto -50 -> 5 %
    out = r.evaluate()
    assert (out.level, out.loss_usd, out.loss_fraction) == ("ok", D("50"), D("0.05"))


def test_realized_plus_unrealized_add_up_to_the_halt_level():
    r = Rig({"AAAUSDT": D("75")})
    r.open("AAAUSDT", side=1)                                   # -250
    r.lose("-250")                                              # -250 realizzati: in tutto -500 = 50 %
    out = r.evaluate()
    assert (out.level, out.loss_usd, out.loss_fraction) == ("halt", D("500"), D("0.5"))


def test_loss_before_midnight_lowers_the_start_capital_and_is_not_counted_as_todays_loss():
    r = Rig()
    r.lose("-200", at=NOW - DAY_MS)                             # ieri: il capitale di oggi parte da 800
    r.lose("-280")                                              # oggi: 280 / 800 = 35 %
    out = r.evaluate()
    assert (out.level, out.loss_usd, out.loss_fraction) == ("warn", D("280"), D("0.35"))
    r2 = Rig()
    r2.lose("200", at=NOW - DAY_MS)                             # ieri guadagno: il capitale di oggi parte da 1200
    r2.lose("-420")                                             # 420 / 1200 = 35 %
    out2 = r2.evaluate()
    assert (out2.level, out2.loss_usd, out2.loss_fraction) == ("warn", D("420"), D("0.35"))


def test_yesterdays_loss_alone_is_not_todays_loss():
    r = Rig()
    r.lose("-600", at=NOW - DAY_MS)
    assert r.evaluate() == DailyLoss("ok", D("0"), D("0"), DAY0)


def test_a_close_exactly_at_midnight_belongs_to_the_new_day_and_one_millisecond_before_to_the_old():
    r = Rig()
    r.lose("-350", at=DAY0)                                     # appena dopo mezzanotte: e' di oggi
    assert r.evaluate().level == "warn"
    r2 = Rig()
    r2.lose("-350", at=DAY0 - 1)                                # un millisecondo prima: e' di ieri
    assert r2.evaluate() == DailyLoss("ok", D("0"), D("0"), DAY0)
    last_ms = r2.evaluate(DAY0 - 1)                             # visto dall'ultimo millisecondo di ieri, e' la perdita di ieri
    assert (last_ms.level, last_ms.day_start_ms) == ("warn", DAY0 - DAY_MS)


def test_the_day_boundary_resets_the_count_for_the_same_journal():
    r = Rig()
    r.lose("-400", at=DAY0 + HOUR)
    assert r.evaluate(DAY0 + 2 * HOUR).level == "warn"
    nxt = r.evaluate(DAY0 + DAY_MS + 2 * HOUR)                  # giorno dopo: perdita di ieri -> capitale 600, perdita 0
    assert nxt == DailyLoss("ok", D("0"), D("0"), DAY0 + DAY_MS)


def test_missing_or_invalid_price_counts_only_the_realized_part():
    for bad in (RuntimeError("no_recent_bar"), ValueError("no_recent_bar"), D("0"), D("-5"), D("NaN"), D("Infinity"),
                65.0, "65", None, 65):
        r = Rig({"AAAUSDT": bad})
        r.open("AAAUSDT", side=1)
        r.lose("-100")
        out = r.evaluate()
        assert (out.level, out.loss_usd) == ("ok", D("100")), bad


def test_one_missing_price_does_not_hide_the_loss_of_another_position():
    r = Rig({"AAAUSDT": RuntimeError("down"), "BBBUSDT": D("135")})
    r.open("AAAUSDT", side=1)
    r.open("BBBUSDT", side=-1)                                  # -350
    out = r.evaluate()
    assert (out.level, out.loss_usd) == ("warn", D("350")) and [s for s, _ in r.asked] == ["AAAUSDT", "BBBUSDT"]


@pytest.mark.parametrize("past", ["-1000", "-1200"])
def test_start_capital_zero_or_negative_is_halt_fail_closed(past):
    r = Rig()
    pid = r.open("LOSSUSDT", qty="30", at=NOW - DAY_MS - HOUR)
    r.close(pid, D("100") + D(past) / 30, at=NOW - DAY_MS)
    out = r.evaluate()
    assert out.level == "halt" and out.loss_fraction == D("1") and out.day_start_ms == DAY0


def test_other_runs_and_portfolios_do_not_count():
    r = Rig({"AAAUSDT": D("1")})

    def hand():
        return _hand(side=1, entry="100", stop="50", qty="10", margin="100", symbol="AAAUSDT")
    execute_paper(hand(), portfolio_id="hawk", run_id=RUN, journal=r.j, now_ms=NOW - HOUR)
    execute_paper(hand(), portfolio_id=PF, run_id="other-run", journal=r.j, now_ms=NOW - HOUR)
    assert r.evaluate() == DailyLoss("ok", D("0"), D("0"), DAY0) and r.asked == []


@pytest.mark.parametrize("now", [0, -1, True, 1.5, "1", None])
def test_evaluate_rejects_a_bad_clock(now):
    with pytest.raises(ValueError, match="invalid_now"):
        Rig().evaluate(now)


@pytest.mark.parametrize("eq", [1000, 1000.0, "1000", D("0"), D("-1"), D("NaN"), D("Infinity"), None])
def test_evaluate_rejects_a_bad_initial_equity(eq):
    with pytest.raises(ValueError, match="invalid_initial_equity"):
        Rig().evaluate(equity=eq)


@pytest.mark.parametrize("warn,halt", [
    (D("0.5"), D("0.35")), (D("0.35"), D("0.35")), (D("0"), D("0.5")), (D("-0.1"), D("0.5")), (D("0.35"), D("1.01")),
    (D("NaN"), D("0.5")), (D("0.35"), D("Infinity")), (0.35, D("0.5")), (D("0.35"), 0.5), ("0.35", "0.5"),
    (None, D("0.5"))])
def test_evaluate_and_guard_reject_bad_fractions(warn, halt):
    with pytest.raises(ValueError, match="invalid_daily_loss_fractions"):
        Rig().evaluate(warn=warn, halt=halt)
    with pytest.raises(ValueError, match="invalid_daily_loss_fractions"):
        DailyLossGuard(data_dir=Path(tempfile.mkdtemp()), evaluate=lambda n: None, warn_fraction=warn,
                       halt_fraction=halt)


def test_halt_at_one_hundred_percent_is_a_valid_setting():
    r = Rig()
    r.lose("-500", symbol="BIG1USDT")
    assert r.evaluate(warn=D("0.9"), halt=D("1")).level == "ok"      # 50 %: sotto l'avviso al 90 %
    r.lose("-500", symbol="BIG2USDT")
    assert r.evaluate(warn=D("0.9"), halt=D("1")).level == "halt"    # 100 %


# ----------------------------------------------------------------------------- DailyLossGuard
def _dl(level, fraction, *, start=DAY0):
    return DailyLoss(level, D(fraction), D(fraction) * 1000, start)


class Stub:
    """Valutatore finto: restituisce ``result`` (o solleva se e' un'eccezione) e ricorda le chiamate."""

    def __init__(self, result):
        self.result, self.calls = result, []

    def __call__(self, now):
        self.calls.append(now)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Sender:
    def __init__(self, reply=True):
        self.reply, self.texts = reply, []

    def __call__(self, text):
        self.texts.append(text)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def _guard(stub, sender=None, *, data_dir=None):
    d = data_dir if data_dir is not None else Path(tempfile.mkdtemp())
    return DailyLossGuard(data_dir=d, evaluate=stub, send=sender, warn_fraction=WARN, halt_fraction=HALT), d


def _state(d):
    return json.loads((d / STATE_FILE).read_text(encoding="utf-8"))


def test_guard_evaluates_at_most_once_per_minute_and_returns_the_cached_result():
    stub = Stub(_dl("ok", "0.1"))
    g, _ = _guard(stub)
    a = g(NOW)
    assert g(NOW + 59_999) is a and stub.calls == [NOW]
    stub.result = _dl("warn", "0.4")
    assert g(NOW + 30_000).level == "ok"                        # ancora la valutazione del minuto
    assert g(NOW + 60_000).level == "warn" and stub.calls == [NOW, NOW + 60_000]


def test_guard_failure_is_not_cached_and_propagates_so_the_runner_halts():
    stub = Stub(RuntimeError("bitget down"))
    g, _ = _guard(stub)
    with pytest.raises(RuntimeError):
        g(NOW)
    with pytest.raises(RuntimeError):
        g(NOW + 1_000)                                           # stesso minuto: si riprova, nessuna cache
    stub.result = _dl("ok", "0.1")
    assert g(NOW + 2_000).level == "ok" and len(stub.calls) == 3


@pytest.mark.parametrize("now", [0, -5, True, 1.5, None, "1"])
def test_guard_rejects_a_bad_clock(now):
    with pytest.raises(ValueError, match="invalid_now"):
        _guard(Stub(_dl("ok", "0")))[0](now)


def test_guard_rejects_a_bad_data_dir():
    for bad in (None, str(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "missing"):
        with pytest.raises(ValueError, match="invalid_data_dir"):
            DailyLossGuard(data_dir=bad, evaluate=lambda n: None, warn_fraction=WARN, halt_fraction=HALT)


def test_halt_is_latched_for_the_rest_of_the_utc_day_even_if_the_loss_recovers():
    stub = Stub(_dl("halt", "0.52"))
    g, _ = _guard(stub)
    assert g(NOW).level == "halt"
    stub.result = _dl("ok", "0.10")                              # il prezzo e' risalito
    out = g(NOW + 60_000)
    assert out.level == "halt" and out.loss_fraction == D("0.10")    # resta fermo, ma la perdita mostrata e' quella vera
    stub.result = _dl("warn", "0.40")
    assert g(NOW + 5 * HOUR).level == "halt"
    stub.result = _dl("ok", "0.0", start=DAY0 + DAY_MS)          # mezzanotte UTC: si riparte
    nxt = g(DAY0 + DAY_MS + 60_000)
    assert nxt.level == "ok" and _state(g._path.parent) == {
        "day_start_ms": DAY0 + DAY_MS, "warn_sent": False, "halt_sent": False, "halt_latched": False}


def test_halt_latch_survives_a_restart_and_is_released_by_the_next_day():
    d = Path(tempfile.mkdtemp())
    g1, _ = _guard(Stub(_dl("halt", "0.55")), data_dir=d)
    assert g1(NOW).level == "halt"
    g2, _ = _guard(Stub(_dl("ok", "0.01")), data_dir=d)          # processo riavviato nello stesso giorno
    assert g2(NOW + 10 * 60_000).level == "halt"
    g3, _ = _guard(Stub(_dl("ok", "0.01")), data_dir=d)          # riavviato il giorno dopo
    assert g3(NOW + DAY_MS).level == "ok"


def test_warn_alert_is_sent_once_per_day_with_percentages_only():
    stub, send = Stub(_dl("warn", "0.352")), Sender()
    g, d = _guard(stub, send)
    for k in range(6):
        assert g(NOW + k * 60_000).level == "warn"
    assert len(send.texts) == 1
    text = send.texts[0]
    assert "35.2%" in text and "35.0%" in text and "50.0%" in text and "puoi fermarlo tu" in text
    assert "$" not in text and "USD" not in text                 # nessun importo, solo percentuali
    assert _state(d) == {"day_start_ms": DAY0, "warn_sent": True, "halt_sent": False, "halt_latched": False}
    stub.result = _dl("warn", "0.40", start=DAY0 + DAY_MS)       # il giorno dopo l'avviso puo' ripartire
    g(DAY0 + DAY_MS + HOUR)
    assert len(send.texts) == 2 and "40.0%" in send.texts[1]


def test_warn_then_halt_sends_one_message_per_level_in_order_and_never_again():
    stub, send = Stub(_dl("warn", "0.36")), Sender()
    g, d = _guard(stub, send)
    g(NOW)
    stub.result = _dl("halt", "0.51")
    for k in range(1, 5):
        g(NOW + k * 60_000)
    assert len(send.texts) == 2
    assert "avviso" in send.texts[0] and "50.0%" in send.texts[0]
    assert "51.0%" in send.texts[1] and "mezzanotte UTC" in send.texts[1] and "stop" in send.texts[1]
    assert "$" not in send.texts[1] and "USD" not in send.texts[1]
    assert _state(d) == {"day_start_ms": DAY0, "warn_sent": True, "halt_sent": True, "halt_latched": True}


def test_jumping_straight_to_halt_sends_only_the_halt_message():
    send = Sender()
    g, _ = _guard(Stub(_dl("halt", "0.60")), send)
    g(NOW)
    assert len(send.texts) == 1 and "mezzanotte UTC" in send.texts[0] and "60.0%" in send.texts[0]
    assert "Si ferma da solo" not in send.texts[0]               # sarebbe falso: e' gia' fermo


def test_recovery_under_the_latch_does_not_send_a_warn_or_a_second_halt():
    stub, send = Stub(_dl("halt", "0.55")), Sender()
    g, _ = _guard(stub, send)
    g(NOW)
    stub.result = _dl("warn", "0.40")                             # sotto il latch il livello resta halt
    g(NOW + 60_000)
    stub.result = _dl("ok", "0.05")
    g(NOW + 120_000)
    assert len(send.texts) == 1


@pytest.mark.parametrize("reply", [False, None, 1, "ok", RuntimeError("telegram down")])
def test_a_failed_send_is_retried_the_next_minute_and_marked_only_after_a_real_true(reply):
    send = Sender(reply)
    g, d = _guard(Stub(_dl("warn", "0.40")), send)
    assert g(NOW).level == "warn"                                # l'invio fallito non ferma e non rompe nulla
    assert len(send.texts) == 1 and _state(d)["warn_sent"] is False
    g(NOW + 60_000)
    assert len(send.texts) == 2                                  # riprova al minuto dopo
    send.reply = True
    g(NOW + 120_000)
    assert len(send.texts) == 3 and _state(d)["warn_sent"] is True
    g(NOW + 180_000)
    assert len(send.texts) == 3                                  # una volta ricevuto, basta


def test_a_failed_send_is_retried_within_the_same_minute_only_after_the_cache_expires():
    send = Sender(False)
    g, _ = _guard(Stub(_dl("warn", "0.40")), send)
    g(NOW)
    g(NOW + 30_000)
    assert len(send.texts) == 1                                  # nessuna raffica: al massimo un tentativo al minuto


def test_alert_state_survives_a_restart_so_nothing_is_sent_twice():
    d = Path(tempfile.mkdtemp())
    s1 = Sender()
    g1, _ = _guard(Stub(_dl("warn", "0.40")), s1, data_dir=d)
    g1(NOW)
    s2 = Sender()
    g2, _ = _guard(Stub(_dl("warn", "0.41")), s2, data_dir=d)
    g2(NOW + 10 * 60_000)
    assert len(s1.texts) == 1 and s2.texts == []
    g3, _ = _guard(Stub(_dl("halt", "0.52")), s2, data_dir=d)    # il livello nuovo (halt) invece parte
    g3(NOW + 20 * 60_000)
    assert len(s2.texts) == 1 and "mezzanotte UTC" in s2.texts[0]
    s3 = Sender()
    g4, _ = _guard(Stub(_dl("halt", "0.52")), s3, data_dir=d)
    g4(NOW + 30 * 60_000)
    assert s3.texts == []


def test_without_a_sender_nothing_is_sent_or_marked_and_the_levels_still_work():
    g, d = _guard(Stub(_dl("warn", "0.40")), None)
    assert g(NOW).level == "warn"
    assert not (d / STATE_FILE).exists() or _state(d)["warn_sent"] is False


@pytest.mark.parametrize("content", [
    "not json", "[]", "{}", '{"day_start_ms": 1}',
    json.dumps({"day_start_ms": DAY0, "warn_sent": 1, "halt_sent": False, "halt_latched": False}),
    json.dumps({"day_start_ms": True, "warn_sent": False, "halt_sent": False, "halt_latched": False}),
    json.dumps({"day_start_ms": DAY0, "warn_sent": False, "halt_sent": False, "halt_latched": False, "x": 1}),
    json.dumps({"day_start_ms": "x", "warn_sent": False, "halt_sent": False, "halt_latched": False})])
def test_a_corrupt_state_file_is_ignored_not_trusted_and_does_not_crash(content):
    d = Path(tempfile.mkdtemp())
    (d / STATE_FILE).write_text(content, encoding="utf-8")
    send = Sender()
    g, _ = _guard(Stub(_dl("warn", "0.40")), send, data_dir=d)
    assert g(NOW).level == "warn" and len(send.texts) == 1       # parte da zero: l'avviso (non ancora provato) va
    assert _state(d) == {"day_start_ms": DAY0, "warn_sent": True, "halt_sent": False, "halt_latched": False}


def test_state_file_has_exactly_four_keys_and_no_amounts():
    send = Sender()
    g, d = _guard(Stub(_dl("halt", "0.53")), send)
    g(NOW)
    state = _state(d)
    assert set(state) == {"day_start_ms", "warn_sent", "halt_sent", "halt_latched"}
    assert [p.name for p in d.iterdir()] == [STATE_FILE]         # nessun file temporaneo rimasto


def test_a_disk_error_on_save_is_swallowed_and_memory_still_holds_the_latch(monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(dl.tempfile, "mkstemp", boom)
    stub = Stub(_dl("halt", "0.55"))
    g, d = _guard(stub, Sender())
    assert g(NOW).level == "halt"
    stub.result = _dl("ok", "0.0")
    assert g(NOW + 60_000).level == "halt" and list(d.iterdir()) == []


# ----------------------------------------------------------------------------- telegram_sender
class FakeResp:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Opener:
    def __init__(self, status=200, boom=None):
        self.status, self.boom, self.calls = status, boom, []

    def __call__(self, req, timeout=None):
        self.calls.append((req, timeout))
        if self.boom:
            raise self.boom
        return FakeResp(self.status)


ENV = {"TELEGRAM_BOT_TOKEN": "tok-123", "TELEGRAM_CHAT_ID": "chat-9"}


@pytest.mark.parametrize("env", [
    {}, {"TELEGRAM_BOT_TOKEN": "t"}, {"TELEGRAM_CHAT_ID": "c"}, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "c"},
    {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": ""}, {"TELEGRAM_BOT_TOKEN": 5, "TELEGRAM_CHAT_ID": "c"}])
def test_sender_without_both_variables_is_a_no_op_that_never_touches_the_network(env):
    op = Opener()
    send = telegram_sender(env, opener=op)
    assert send("ciao") is False and op.calls == []


def test_sender_posts_json_to_the_bot_api_with_a_timeout_and_returns_true_only_on_200():
    op = Opener(200)
    send = telegram_sender(ENV, opener=op)
    assert send("perdita al 35%") is True
    (req, timeout), = op.calls
    assert req.full_url == "https://api.telegram.org/bottok-123/sendMessage" and timeout == TIMEOUT_S == 8
    assert req.get_method() == "POST" and req.get_header("Content-type") == "application/json"
    assert json.loads(req.data.decode("utf-8")) == {"chat_id": "chat-9", "text": "perdita al 35%"}


@pytest.mark.parametrize("status", [201, 204, 400, 401, 403, 429, 500, None])
def test_sender_is_false_for_anything_but_200(status):
    assert telegram_sender(ENV, opener=Opener(status))("x") is False


@pytest.mark.parametrize("boom", [OSError("net"), TimeoutError(), RuntimeError("x"), ValueError("y")])
def test_sender_never_raises(boom):
    assert telegram_sender(ENV, opener=Opener(boom=boom))("x") is False


def test_sender_truncates_long_text_and_rejects_empty_or_non_text():
    op = Opener(200)
    send = telegram_sender(ENV, opener=op)
    assert send("a" * 5000) is True
    assert len(json.loads(op.calls[0][0].data.decode("utf-8"))["text"]) == 1000
    for bad in ("", None, 5, b"x", ["x"]):
        assert send(bad) is False
    assert len(op.calls) == 1


def test_sender_does_not_use_the_network_by_default_when_unconfigured(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("rete usata senza configurazione")
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    assert telegram_sender({})("x") is False


# ----------------------------------------------------------------------------- Runner
class RRig:
    def __init__(self, daily_loss=None, halted=lambda: None, commands=True):
        self.dir = Path(tempfile.mkdtemp())
        self.mon, self.cyc, self.cmd, self.loss_calls = [], [], [], []
        self.result = _dl("ok", "0") if daily_loss is None else daily_loss
        self.fail = False

        def loss(now):
            self.loss_calls.append(now)
            if self.fail:
                raise RuntimeError("bitget down")
            return self.result

        def monitor(now):
            self.mon.append(now)
            return MonitorReport(0, (), ())

        def cycle(now, slot):
            self.cyc.append(now)
            return CycleReport(now, (), (), (), ())

        def commands_fn(now):
            self.cmd.append(now)
            return None
        self.runner = Runner(run_id="run-1", data_dir=self.dir, run_monitor=monitor, run_cycle=cycle, halted=halted,
                             run_commands=commands_fn if commands else None, daily_loss=loss)

    def beat(self):
        return json.loads((self.dir / "heartbeat.json").read_text(encoding="utf-8"))


T0 = G + 20_000


def test_runner_ok_level_runs_the_cycle_and_writes_the_loss_fields_in_the_heartbeat():
    r = RRig(_dl("ok", "0.1234"))
    t = r.runner.tick(T0)
    assert t.state == "running" and t.last_error is None and r.cyc == [T0]
    # contratto del heartbeat aggiornato da d8130a9 (11/11): esito dell'ultimo ciclo Brain in "last_cycle"
    assert r.beat() == {"ts_ms": T0, "cycle": 1, "state": "running", "run_id": "run-1", "last_error": None,
                        "daily_loss_level": "ok", "daily_loss_pct": "12.3", "exit_mode": "legacy",
                        "last_cycle": {"at_ms": T0, "decisions": 0, "opened": 0, "errors": []}}


def test_runner_warn_level_keeps_running_and_only_reports():
    r = RRig(_dl("warn", "0.351"))
    t = r.runner.tick(T0)
    assert t.state == "running" and t.last_error is None and r.cyc == [T0]
    assert (r.beat()["daily_loss_level"], r.beat()["daily_loss_pct"]) == ("warn", "35.1")


def test_runner_halt_level_stops_the_brain_but_not_commands_or_the_monitor():
    r = RRig(_dl("halt", "0.512"))
    t = r.runner.tick(T0)
    assert t.state == "halted" and t.last_error == "halted:daily_loss" and t.cycle is None and r.cyc == []
    assert r.cmd == [T0] and r.mon == [T0]                         # chiusura manuale e uscite proseguono
    assert r.beat() == {"ts_ms": T0, "cycle": 0, "state": "halted", "run_id": "run-1",
                        "last_error": "halted:daily_loss", "daily_loss_level": "halt", "daily_loss_pct": "51.2",
                        "exit_mode": "legacy"}


def test_runner_halt_keeps_monitoring_and_commands_on_every_following_tick():
    r = RRig(_dl("halt", "0.6"))
    r.runner.tick(T0)
    r.runner.tick(T0 + 5_000)
    r.runner.tick(G + 60_000 + 3_000)
    assert r.cyc == [] and r.cmd == [T0, T0 + 5_000, G + 63_000] and r.mon == [T0, G + 63_000]


def test_runner_resumes_the_candle_when_the_halt_is_lifted_before_it_was_served():
    r = RRig(_dl("halt", "0.6"))
    r.runner.tick(T0)
    r.result = _dl("ok", "0")
    t = r.runner.tick(T0 + 5_000)
    assert t.state == "running" and r.cyc == [T0 + 5_000]


def test_runner_halt_wins_over_pause_and_pause_flag_still_works_alone():
    r = RRig(_dl("halt", "0.6"))
    (r.dir / "pause.flag").write_text("")
    assert r.runner.tick(T0).state == "halted"
    r2 = RRig(_dl("warn", "0.4"))
    (r2.dir / "pause.flag").write_text("")
    t = r2.runner.tick(T0)
    assert t.state == "paused" and t.last_error is None and r2.cyc == []


def test_runner_halted_hook_reason_comes_first_over_the_loss_reason():
    r = RRig(_dl("halt", "0.6"), halted=lambda: "budget")
    t = r.runner.tick(T0)
    assert t.state == "halted" and t.last_error == "halted:budget"
    assert r.beat()["daily_loss_level"] == "halt"


def test_runner_loss_check_failure_halts_new_openings_with_a_short_code_and_unknown_level():
    r = RRig()
    r.fail = True
    t = r.runner.tick(T0)
    assert t.state == "halted" and t.last_error == "halted:daily_loss_check_failed" and r.cyc == []
    assert r.cmd == [T0] and r.mon == [T0]
    assert r.beat()["daily_loss_level"] == "unknown" and "daily_loss_pct" not in r.beat()
    assert "bitget" not in json.dumps(r.beat()).lower()            # nessun testo libero dell'errore nel battito
    r.fail = False
    assert r.runner.tick(T0 + 5_000).state == "running"            # appena la valutazione torna, si riparte


def test_runner_evaluates_the_loss_after_the_monitor_so_a_fresh_stop_blocks_the_cycle_in_the_same_tick():
    r = RRig()
    order = []
    closed = {"yes": False}
    r.runner._monitor = lambda now: (order.append("monitor"), closed.update(yes=True), MonitorReport(1, (("p", "stop"),), ()))[2]
    r.runner._commands = lambda now: (order.append("commands"), None)[1]
    r.runner._daily_loss = lambda now: (order.append("loss"), _dl("halt" if closed["yes"] else "ok", "0.6"))[1]
    r.runner._cycle = lambda now, slot: (order.append("cycle"), CycleReport(now, (), (), (), ()))[1]
    t = r.runner.tick(T0)
    assert order == ["commands", "monitor", "loss"]                # nessun giro: la chiusura appena fatta e' gia' contata
    assert t.state == "halted" and t.cycle is None and t.monitor.closed == (("p", "stop"),)
    r2 = RRig(_dl("ok", "0"))
    order2 = []
    r2.runner._commands = lambda now: (order2.append("commands"), None)[1]
    r2.runner._monitor = lambda now: (order2.append("monitor"), MonitorReport(0, (), ()))[1]
    r2.runner._daily_loss = lambda now: (order2.append("loss"), _dl("ok", "0"))[1]
    r2.runner._cycle = lambda now, slot: (order2.append("cycle"), CycleReport(now, (), (), (), ()))[1]
    r2.runner.tick(T0)
    assert order2 == ["commands", "monitor", "loss", "cycle"]


def test_runner_halt_reason_stays_first_in_last_error_before_monitor_and_manual_errors():
    r = RRig(_dl("halt", "0.6"))
    r.runner._monitor = lambda now: MonitorReport(0, (), (("p", "no_price"),))
    t = r.runner.tick(T0)
    assert t.last_error == "halted:daily_loss;monitor:no_price"


def test_runner_asks_the_loss_check_at_every_tick_with_the_tick_time():
    r = RRig(_dl("ok", "0"))
    r.runner.tick(T0)
    r.runner.tick(T0 + 5_000)
    assert r.loss_calls == [T0, T0 + 5_000]


def test_runner_without_the_loss_hook_keeps_the_old_heartbeat_exactly():
    d = Path(tempfile.mkdtemp())
    run = Runner(run_id="run-1", data_dir=d, run_monitor=lambda n: MonitorReport(0, (), ()),
                 run_cycle=lambda n, s: CycleReport(n, (), (), (), ()))
    run.tick(T0)
    # senza il gancio delle perdite il heartbeat resta quello di prima, piu' solo l'esito dell'ultimo ciclo (d8130a9):
    # nessun campo daily_loss_* compare
    assert json.loads((d / "heartbeat.json").read_text(encoding="utf-8")) == {
        "ts_ms": T0, "cycle": 1, "state": "running", "run_id": "run-1", "last_error": None,
        "exit_mode": "legacy", "last_cycle": {"at_ms": T0, "decisions": 0, "opened": 0, "errors": []}}


# ----------------------------------------------------------------------------- config
def _raw(**over):
    d = json.loads(default_config_path().read_bytes())
    d.update(over)
    return json.dumps(d).encode()


def test_default_config_has_the_users_35_and_50_percent():
    c = load_default_config()
    assert (c.daily_loss_warn, c.daily_loss_halt) == (D("0.35"), D("0.50"))
    raw = json.loads(default_config_path().read_bytes())
    assert (raw["daily_loss_warn_fraction"], raw["daily_loss_halt_fraction"]) == ("0.35", "0.50")


def test_both_loss_keys_are_required():
    for key in ("daily_loss_warn_fraction", "daily_loss_halt_fraction"):
        raw = json.loads(default_config_path().read_bytes())
        del raw[key]
        with pytest.raises(ValueError, match="invalid_config"):
            load_runner_config(json.dumps(raw).encode())


def test_loss_fractions_are_accepted_when_valid_and_change_nothing_in_the_risk_mandate():
    base = load_default_config()
    c = load_runner_config(_raw(daily_loss_warn_fraction="0.2", daily_loss_halt_fraction="1"))
    assert (c.daily_loss_warn, c.daily_loss_halt) == (D("0.2"), D("1"))
    assert c.risk_policy == base.risk_policy and _policy_hash(c.risk_policy) == _policy_hash(base.risk_policy)
    assert mandate_template(c.risk_policy, "x") == mandate_template(base.risk_policy, "x")


@pytest.mark.parametrize("warn,halt", [
    ("0.5", "0.35"), ("0.5", "0.5"), ("0", "0.5"), ("-0.1", "0.5"), ("1", "1"), ("0.35", "1.01"), ("0.35", "0"),
    ("0.35", "-0.5"), ("NaN", "0.5"), ("0.35", "Infinity"), ("abc", "0.5"), ("0.35", ""), ("", "0.5"),
    ("0.35", "0.5" + "0" * 30), (0.35, "0.5"), ("0.35", 0.5), (None, "0.5"), ("0.35", None), ("0.35", True),
    ("٣", "0.5")])
def test_loss_fractions_out_of_range_or_wrong_type_are_rejected(warn, halt):
    with pytest.raises(ValueError, match="invalid_config"):
        load_runner_config(_raw(daily_loss_warn_fraction=warn, daily_loss_halt_fraction=halt))


# ----------------------------------------------------------------------------- wiring + end-to-end
def _setup(alert_send=None, **cfg):
    data_dir = Path(tempfile.mkdtemp())
    config = dataclasses.replace(load_default_config(), symbols=("ETHUSDT",), **{**LEGACY, **cfg})
    built = build_runner(data_dir=data_dir, run_id=E2E_RUN, config=config, get_json=_get_json_factory(),
                         inner_transport=FakeModel(), view_params=VIEW, alert_send=alert_send)
    _approve(built, data_dir, config)
    return built, data_dir


# In questo mondo finto lo stop di ETH (short da 3 pezzi a ~100, stop a +1 %) costa circa 3,5 dollari su 1000: 0,35 %.
# Le soglie dei test sono quindi 0,1 % (avviso) e 0,3 % (stop); quelle vere (35 % / 50 %) sono provate sopra.
def test_end_to_end_a_stop_loss_over_the_halt_level_stops_openings_until_midnight_utc():
    send = Sender()
    built, data_dir = _setup(send, daily_loss_warn=D("0.001"), daily_loss_halt=D("0.003"))
    run = built.runner
    t = run.tick(G + 25_000)                                       # ETH short aperto
    assert [s for s, _ in t.cycle.opened] == ["ETHUSDT"] and _beat(data_dir)["daily_loss_level"] == "ok"
    assert send.texts == []
    # minuto 21: lo stop colpisce. E' anche l'inizio di una nuova candela: senza la valutazione DOPO il monitor il Brain
    # riaprirebbe subito nello stesso tick; con il freno la perdita appena realizzata conta e non apre.
    t = run.tick(G + 23 * M)
    assert [r for _, r in t.monitor.closed] == ["stop"]
    assert t.state == "halted" and t.last_error == "halted:daily_loss" and t.cycle is None
    beat = _beat(data_dir)
    assert beat["daily_loss_level"] == "halt" and D("0.3") <= D(beat["daily_loss_pct"]) < D("1")
    assert len(send.texts) == 1 and "mezzanotte UTC" in send.texts[0]       # da ok a halt: un solo messaggio, quello giusto
    assert len(_events(built, "paper_open")) == 1
    spent = built.ledger.daily_spend("deepseek")
    for k in (2, 3, 8):                                            # candele successive dello stesso giorno: nessun giro
        t = run.tick(G + k * CYCLE_MS + 20_000)
        assert t.state == "halted" and t.cycle is None
    assert built.ledger.daily_spend("deepseek") == spent and len(_events(built, "paper_open")) == 1
    assert len(send.texts) == 1                                    # niente messaggi ripetuti
    midnight = (G // DAY_MS + 1) * DAY_MS
    t = run.tick(midnight + 30_000)                                # mezzanotte UTC: lo stop e' tolto
    assert t.state == "running" and "halted" not in (t.last_error or "")
    assert _beat(data_dir)["daily_loss_level"] == "ok"
    assert json.loads((data_dir / STATE_FILE).read_text(encoding="utf-8"))["day_start_ms"] == midnight


def test_end_to_end_warn_level_alerts_once_but_the_brain_keeps_working():
    send = Sender()
    built, data_dir = _setup(send, daily_loss_warn=D("0.001"), daily_loss_halt=D("0.9"))
    run = built.runner
    run.tick(G + 25_000)
    t = run.tick(G + 23 * M)                                       # stop: perdita sopra l'avviso, molto sotto lo stop
    assert t.state == "running" and _beat(data_dir)["daily_loss_level"] == "warn"
    assert [s for s, _ in t.cycle.opened] == ["ETHUSDT"]           # il Brain continua e puo' riaprire
    assert len(send.texts) == 1 and "avviso" in send.texts[0]
    for k in (24, 25, 40, 70):
        t = run.tick(G + k * M)
        assert t.state == "running" and _beat(data_dir)["daily_loss_level"] == "warn"
    assert len(send.texts) == 1                                    # un solo avviso al giorno


def test_end_to_end_default_thresholds_do_not_trigger_on_a_normal_stop():
    built, data_dir = _setup(Sender())
    run = built.runner
    run.tick(G + 25_000)
    t = run.tick(G + 23 * M)
    beat = _beat(data_dir)
    assert t.state == "running" and beat["daily_loss_level"] == "ok" and D("0") < D(beat["daily_loss_pct"]) < D("3")


def test_end_to_end_a_loss_check_failure_does_not_block_the_exit_monitor():
    built, data_dir = _setup(Sender())
    run = built.runner
    run.tick(G + 25_000)

    def broken(now):
        raise RuntimeError("boom")
    run._daily_loss = broken                                       # il guasto e' sul valutatore, non sul feed del monitor
    t = run.tick(G + 19 * M)
    assert t.state == "halted" and t.last_error.startswith("halted:daily_loss_check_failed")
    assert t.monitor is not None and t.monitor.errors == ()


def test_wiring_main_builds_the_telegram_sender_from_the_environment(monkeypatch, tmp_path):
    from backend.v3.runner import wiring
    seen = {}

    def spy(env, **kw):
        seen["env"] = env
        return Sender()
    monkeypatch.setattr(wiring, "telegram_sender", spy)
    env = {"DESK_MODE": "paper"}
    rc = wiring.main(["--data-dir", str(tmp_path / "d"), "--run-id", E2E_RUN, "--once"], env=env,
                     now_fn=lambda: G + 20_000, get_json=_get_json_factory(), inner_transport=FakeModel())
    assert rc == 0 and seen["env"] is env
