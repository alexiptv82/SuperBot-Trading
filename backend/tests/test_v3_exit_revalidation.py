"""Servizio delle uscite (24/11/2026): candele provvisorie riconvalidate e uscite in ritardo sempre segnalate.

Caso reale del 24/11: stop SHORT BTC a 60.250 toccato dalla candela delle 15:33 (massimo 60.274), che il servizio in
funzione aveva letto provvisoria (massimo sotto lo stop) e mai riletto; la chiusura e' arrivata solo al riavvio."""
from decimal import Decimal as D

from backend.tests.test_brain_f7_outcomes import _hand
from backend.v3.events import EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.features.indicators import Bar
from backend.v3.runner.feed import CandleStore, minute_fetcher
from backend.v3.runner.monitor import LATE_KIND, run_exit_monitor
from backend.v3.runner.exits import ExitPolicy
from backend.v3.runner.telegram_feed import JournalNotifier

M = 60_000
T0 = 1_795_530_900_000 // M * M          # 24/11 14:35 UTC
RUN = "r1"
POLICY = ExitPolicy(D("3.5"), None, D("2"))


def _row(t, o, h, l, c):
    return [str(t), str(o), str(h), str(l), str(c), "1", "1"]


class Source:
    """Finta fonte Bitget ``history-candles``: restituisce le candele chiuse correnti, eventualmente provvisorie."""
    def __init__(self):
        self.bars, self.calls = {}, 0

    def __call__(self, url):
        self.calls += 1
        q = dict(x.split("=") for x in url.split("?")[1].split("&"))
        lo, hi = int(q["startTime"]), int(q["endTime"])
        return {"code": "00000", "data": [_row(t, *v) for t, v in sorted(self.bars.items()) if lo <= t < hi]}


def _flat(src, start, n, price="60180"):
    for i in range(n):
        src.bars[start + i * M] = (price, str(D(price) + 20), str(D(price) - 20), price)


def _journal(tmp_path):
    j = EventJournal(str(tmp_path / "journal.db"))
    j.init_schema()
    return j


def test_overlap_rereads_a_provisional_candle_and_records_the_revision():
    src = Source()
    _flat(src, T0, 10)
    src.bars[T0 + 9 * M] = ("59950", "60200", "59940", "60100")              # provvisoria: massimo 60.200
    store = CandleStore(src, keep={"1m": (M, 1500)}, overlap_bars=60)
    first = store.refresh_raw("BTCUSDT", "1m", T0 + 10 * M + 2_000)
    assert first[-1].high == D("60200")
    src.bars[T0 + 9 * M] = ("59950", "60274", "59940", "60170")              # definitiva: 60.274
    _flat(src, T0 + 10 * M, 1)
    again = store.refresh_raw("BTCUSDT", "1m", T0 + 11 * M + 2_000)
    assert {b.open_time_ms: b.high for b in again}[T0 + 9 * M] == D("60274")
    assert store.revisions[-1][:3] == ("BTCUSDT", "1m", T0 + 9 * M)


def test_full_reload_fixes_a_bar_older_than_the_overlap():
    src = Source()
    _flat(src, T0, 120)
    store = CandleStore(src, keep={"1m": (M, 1500)}, overlap_bars=5, full_reload_ms=30 * M)
    store.refresh_raw("BTCUSDT", "1m", T0 + 120 * M)
    src.bars[T0 + 10 * M] = ("59950", "60300", "59940", "60000")              # corretta molto dopo
    _flat(src, T0 + 120 * M, 40)
    store.refresh_raw("BTCUSDT", "1m", T0 + 125 * M)                        # sovrapposizione: 5 candele, non basta
    assert {b.open_time_ms: b.high for b in store._cache[("BTCUSDT", "1m")]}[T0 + 10 * M] == D("60200")
    bars = store.refresh_raw("BTCUSDT", "1m", T0 + 151 * M)                  # ricarica completa dopo 30 minuti
    assert {b.open_time_ms: b.high for b in bars}[T0 + 10 * M] == D("60300")


def _short_btc(j):
    d = _hand(side=-1, entry="60200", stop="60250", qty="0.1", margin="200", lev=30, symbol="BTCUSDT",
              link="brain-req-btc")
    return execute_paper(d, portfolio_id="brain", run_id=RUN, journal=j, now_ms=T0).position_id


def test_btc_case_closes_within_a_minute_of_the_correction_and_flags_the_delay(tmp_path):
    j = _journal(tmp_path)
    pid = _short_btc(j)
    src = Source()
    _flat(src, T0, 58)
    src.bars[T0 + 58 * M] = ("60100", "60240", "60090", "60170")             # 15:33 provvisoria: sotto lo stop
    store = CandleStore(src, keep={"1m": (M, 1500)}, overlap_bars=60, full_reload_ms=30 * M)
    fetch = minute_fetcher(store)
    r1 = run_exit_monitor(journal=j, portfolio_id="brain", run_id=RUN, fetch_bars=fetch, policy=POLICY,
                          fee_bps=6, now_ms=T0 + 59 * M + 3_000)
    assert r1.closed == ()                                                    # il servizio non vede il tocco
    src.bars[T0 + 58 * M] = ("60100", "60274", "60090", "60170")             # la fonte la corregge
    _flat(src, T0 + 59 * M, 1)
    r2 = run_exit_monitor(journal=j, portfolio_id="brain", run_id=RUN, fetch_bars=fetch, policy=POLICY,
                          fee_bps=6, now_ms=T0 + 60 * M + 3_000)
    assert r2.closed == ((pid, "stop"),)
    close = [r.event.payload for r in j.list_run("brain", RUN) if r.event.kind == "paper_close"][0]
    meta = close["exit_meta"]
    assert meta["signal_bar_ms"] == T0 + 58 * M and meta["detected_ms"] == T0 + 60 * M + 3_000
    assert meta["delay_ms"] == 63_000 and meta["late"] is False               # un minuto: entro la tolleranza
    assert D(meta["theoretical_price"]) == D(close["exit_price"]) and D(meta["market_price"]) == D("60180")


def test_a_stop_found_only_at_restart_is_closed_but_never_silently(tmp_path):
    j = _journal(tmp_path)
    pid = _short_btc(j)
    src = Source()
    _flat(src, T0, 140)
    src.bars[T0 + 58 * M] = ("60100", "60274", "60090", "60170")             # tocco alle 15:33
    for i in range(59, 140):
        src.bars[T0 + i * M] = ("59600", "59620", "59580", "59600")
    store = CandleStore(src, keep={"1m": (M, 1500)}, overlap_bars=60, full_reload_ms=30 * M)  # servizio appena riavviato
    now = T0 + 138 * M + 52_000                                                # 16:53:52
    r = run_exit_monitor(journal=j, portfolio_id="brain", run_id=RUN, fetch_bars=minute_fetcher(store),
                         policy=POLICY, fee_bps=6, now_ms=now)
    assert r.closed == ((pid, "stop"),) and r.late == ((pid, "stop"),)
    rows = [x.event for x in j.list_run("brain", RUN)]
    late = [e for e in rows if e.kind == LATE_KIND]
    assert len(late) == 1 and late[0].payload["late"] is True and late[0].payload["delay_ms"] == now - (T0 + 59 * M)
    assert late[0].payload["theoretical_price"] != late[0].payload["market_price"]   # prezzo storico vs attuale
    msgs = JournalNotifier._late([late[0]])
    assert msgs and "in ritardo" in msgs[0] and "15:33" in msgs[0]


def test_on_time_exits_are_not_flagged(tmp_path):
    j = _journal(tmp_path)
    pid = _short_btc(j)
    src = Source()
    _flat(src, T0, 3)
    src.bars[T0 + 3 * M] = ("60100", "60274", "60090", "60170")
    store = CandleStore(src, keep={"1m": (M, 1500)}, overlap_bars=60)
    r = run_exit_monitor(journal=j, portfolio_id="brain", run_id=RUN, fetch_bars=minute_fetcher(store),
                         policy=POLICY, fee_bps=6, now_ms=T0 + 4 * M + 2_000)
    assert r.closed == ((pid, "stop"),) and r.late == ()
    assert not [x for x in j.list_run("brain", RUN) if x.event.kind == LATE_KIND]
