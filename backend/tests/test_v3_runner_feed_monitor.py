"""A2 — feed delle candele (cache incrementale) e monitor delle uscite: test offline, senza rete.

``get_json`` finto imita la risposta di Bitget (stesso formato: ``{"code": "00000", "data": [[ts, o, h, l, c, v, q]]}``)
cosi' ``fetch_rows`` vero e' esercitato. Il monitor gira sul journal vero con ``execute_paper`` / ``close_paper`` /
``extract_outcomes`` veri. Verifica snella (colla): casi a mano + un controllo di casualita' sui tratti contigui.
"""
from __future__ import annotations

import os
import random
import re
import tempfile
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from backend.tests.test_brain_f7_outcomes import _hand
from backend.v3.events import EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.features.indicators import Bar
from backend.v3.outcomes import extract_outcomes
from backend.v3.runner.exits import EXIT_STOP, EXIT_TAKE_PROFIT, EXIT_TIMEOUT, ExitPolicy
from backend.v3.runner.feed import (
    CandleStore, contiguous_runs, contiguous_tail, fetch_closed_bars, rows_to_bars,
)
from backend.v3.runner.monitor import MINUTE_MS, run_exit_monitor

D = Decimal
M15 = 900_000
H1 = 3_600_000
T0 = 1_800_000_000_000 // H1 * H1
RUN = "r-a2"


def _bar(ts, o="100", h="101", l="99", c="100", v="5", step=M15):
    return Bar(ts, D(o), D(h), D(l), D(c), D(v))


def _series(first, n, step, start_price=100):
    out, price = [], D(start_price)
    for i in range(n):
        c = price + D((i * 7) % 5 - 2) / 10
        out.append(Bar(first + i * step, price, max(price, c) + D("0.3"), min(price, c) - D("0.3"), c, D(i + 1)))
        price = c
    return out


class FakeBitget:
    """Serve righe nel formato di Bitget; conta le richieste e permette buchi e guasti."""

    def __init__(self, bars_by_gran, *, hole=(), fail=False):
        self.bars, self.hole, self.fail, self.urls = bars_by_gran, set(hole), fail, []

    def __call__(self, url):
        self.urls.append(url)
        if self.fail:
            raise RuntimeError("rete")
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        rows = [[str(b.open_time_ms), str(b.open), str(b.high), str(b.low), str(b.close), str(b.volume), "0"]
                for b in self.bars.get((q["symbol"], q["granularity"]), [])
                if int(q["startTime"]) <= b.open_time_ms <= int(q["endTime"]) and b.open_time_ms not in self.hole]
        rows.sort(key=lambda r: -int(r[0]))
        return {"code": "00000", "data": rows[: int(q["limit"])]}


def _cs(fake):
    return CandleStore(fake, keep={"15m": (M15, 100), "1h": (H1, 30)})


# ----------------------------------------------------------------------------- feed
def test_rows_to_bars_orders_and_uses_decimals():
    rows = {2000: ("2", "3", "1", "2.5", "9"), 1000: ("1", "2", "0.5", "1.5", "4")}
    bars = rows_to_bars(rows)
    assert [b.open_time_ms for b in bars] == [1000, 2000]
    assert all(type(x) is D for b in bars for x in (b.open, b.high, b.low, b.close, b.volume))
    assert bars[0].low == D("0.5")


@pytest.mark.parametrize("times,tail,runs", [
    ([], [], []),
    ([1], [1], [[1]]),
    ([1, 2, 3], [1, 2, 3], [[1, 2, 3]]),
    ([1, 2, 4, 5], [4, 5], [[1, 2], [4, 5]]),
    ([1, 3, 5], [5], [[1], [3], [5]]),
    ([1, 2, 3, 5], [5], [[1, 2, 3], [5]]),
])
def test_contiguous_tail_and_runs(times, tail, runs):
    bars = [_bar(t * M15) for t in times]
    assert [b.open_time_ms // M15 for b in contiguous_tail(bars, M15)] == tail
    assert [[b.open_time_ms // M15 for b in r] for r in contiguous_runs(bars, M15)] == runs


def test_contiguous_tail_random_against_a_simple_oracle():
    rnd = random.Random(3)
    for _ in range(200):
        idx = sorted(rnd.sample(range(40), rnd.randint(0, 25)))
        bars = [_bar(i * M15) for i in idx]
        want = []
        for i in reversed(idx):
            if want and want[0] - i != 1:
                break
            want.insert(0, i)
        assert [b.open_time_ms // M15 for b in contiguous_tail(bars, M15)] == want
        assert [b for r in contiguous_runs(bars, M15) for b in r] == bars


def test_fetch_closed_bars_excludes_forming_bar_and_goes_through_real_fetch_rows():
    series = _series(T0, 30, M15)
    fake = FakeBitget({("BTCUSDT", "15m"): series})
    end = T0 + 20 * M15
    got = fetch_closed_bars("BTCUSDT", T0 + 5 * M15, end, candle_ms=M15, get_json=fake)
    assert [b.open_time_ms for b in got] == [T0 + i * M15 for i in range(5, 20)]
    assert got == series[5:20]


def test_store_first_load_then_only_new_bars():
    series = _series(T0, 120, M15)
    fake = FakeBitget({("BTCUSDT", "15m"): series})
    cs = _cs(fake)
    now = T0 + 60 * M15 + 5 * 60_000                           # 5 minuti dopo la chiusura della barra 59
    first = cs.refresh("BTCUSDT", "15m", now)
    assert first == series[:60] and len(fake.urls) >= 1
    n = len(fake.urls)
    assert cs.refresh("BTCUSDT", "15m", now + 60_000) == series[:60] and len(fake.urls) == n   # nessuna barra nuova
    later = now + 2 * M15
    got = cs.refresh("BTCUSDT", "15m", later)
    assert got == series[:62]
    new_urls = fake.urls[n:]
    assert len(new_urls) == 1 and int(re.search(r"startTime=(\d+)", new_urls[0]).group(1)) == T0 + 60 * M15


def test_store_keeps_only_the_last_keep_bars_and_symbols_are_independent():
    series = _series(T0, 140, M15)
    other = _series(T0, 140, M15, start_price=500)
    fake = FakeBitget({("BTCUSDT", "15m"): series, ("ETHUSDT", "15m"): other})
    cs = _cs(fake)
    now = T0 + 130 * M15
    a, b = cs.refresh("BTCUSDT", "15m", now), cs.refresh("ETHUSDT", "15m", now)
    assert a == series[30:130] and b == other[30:130] and len(a) == 100


def test_store_returns_only_the_contiguous_tail_and_retries_a_hole_at_most_once_per_gap():
    series = _series(T0, 140, M15)
    fake = FakeBitget({("BTCUSDT", "15m"): series}, hole={T0 + 50 * M15})
    cs = _cs(fake)
    got = cs.refresh("BTCUSDT", "15m", T0 + 80 * M15)
    assert got == series[51:80]                                # buco a 50: solo la coda contigua
    n = len(fake.urls)
    fake.hole.clear()                                          # il buco si chiude, ma il riprovo non e' ancora dovuto
    got = cs.refresh("BTCUSDT", "15m", T0 + 82 * M15)
    assert got == series[51:82] and len(fake.urls) == n + 1    # solo la barra nuova, nessun ricaricamento
    got = cs.refresh("BTCUSDT", "15m", T0 + 80 * M15 + H1 + M15)
    assert got == series[:85]                                  # ricaricamento completo: la storia e' riparata


def test_store_a_hole_that_persists_is_retried_hourly_not_every_cycle():
    series = _series(T0, 140, M15)
    fake = FakeBitget({("BTCUSDT", "15m"): series}, hole={T0 + 50 * M15})
    cs = _cs(fake)
    cs.refresh("BTCUSDT", "15m", T0 + 80 * M15)
    n = len(fake.urls)
    for k in range(1, 4):                                      # tre cicli entro l'ora: una richiesta ciascuno (la barra nuova)
        cs.refresh("BTCUSDT", "15m", T0 + (80 + k) * M15)
    assert len(fake.urls) == n + 3
    got = cs.refresh("BTCUSDT", "15m", T0 + 80 * M15 + H1)
    assert got == series[51:84] and len(fake.urls) == n + 4      # un ricaricamento in piu, il buco c e ancora


def test_store_network_failure_raises_and_keeps_the_cache():
    series = _series(T0, 80, M15)
    fake = FakeBitget({("BTCUSDT", "15m"): series})
    cs = _cs(fake)
    ok = cs.refresh("BTCUSDT", "15m", T0 + 50 * M15)
    fake.fail = True
    with pytest.raises(RuntimeError):
        cs.refresh("BTCUSDT", "15m", T0 + 60 * M15)
    fake.fail = False
    assert cs.refresh("BTCUSDT", "15m", T0 + 50 * M15) == ok   # la cache era intatta


@pytest.mark.parametrize("keep", [None, {}, {"15m": (M15, 0)}, {"15m": (M15 + 1, 5)}, {"15m": (True, 5)},
                                  {"15m": [M15, 5]}, {1: (M15, 5)}, {"15m": (M15, "5")}])
def test_store_rejects_bad_config(keep):
    with pytest.raises(ValueError) as e:
        CandleStore(lambda u: {}, keep=keep)
    assert str(e.value) == "invalid_keep"


@pytest.mark.parametrize("tf,now", [("5m", T0), ("15m", 0), ("15m", True), ("15m", 1.5)])
def test_store_rejects_bad_requests(tf, now):
    with pytest.raises(ValueError) as e:
        _cs(FakeBitget({})).refresh("BTCUSDT", tf, now)
    assert str(e.value) == "invalid_request"


# ----------------------------------------------------------------------------- monitor
POLICY = ExitPolicy(D("2"), 3 * 3_600_000, D("0"))              # target 2R, durata 3 h, nessuna slippage sullo stop
T_OPEN = T0 + 17_000                                            # aperta 17 s dopo l'inizio del minuto


def _journal():
    j = EventJournal(os.path.join(tempfile.mkdtemp(), "journal.db"))
    j.init_schema()
    return j


def _open(j, *, side=1, entry="30000", stop="29000", symbol="BTCUSDT", now=T_OPEN):
    d = _hand(side=side, entry=entry, stop=stop, symbol=symbol)
    return execute_paper(d, portfolio_id="brain", run_id=RUN, journal=j, now_ms=now).position_id


def _mbar(i, o, h, l, c, first=T0 + MINUTE_MS):
    return Bar(first + i * MINUTE_MS, D(str(o)), D(str(h)), D(str(l)), D(str(c)), D("1"))


def _feed(per_symbol):
    calls = []

    def fetch(symbol, start, end):
        calls.append((symbol, start, end))
        out = per_symbol[symbol]
        if isinstance(out, Exception):
            raise out
        return [b for b in out if start <= b.open_time_ms < end]
    fetch.calls = calls
    return fetch


def _run(j, fetch, now, policy=POLICY):
    return run_exit_monitor(journal=j, portfolio_id="brain", run_id=RUN, fetch_bars=fetch,
                            policy=policy, fee_bps=6, now_ms=now)


def _closes(j):
    return [s.event.payload for s in j.list_run("brain", RUN) if s.event.kind == "paper_close"]


def test_take_profit_closes_the_position_and_the_outcome_carries_the_reason():
    j = _journal()
    pid = _open(j)
    quiet = [_mbar(i, 30000, 30100, 29900, 30050) for i in range(3)]
    hit = [_mbar(3, 30050, 32100, 30000, 32000)]
    feed = _feed({"BTCUSDT": quiet + hit})
    rep = _run(j, feed, T0 + 10 * MINUTE_MS)
    assert (rep.checked, rep.closed, rep.errors) == (1, ((pid, EXIT_TAKE_PROFIT),), ())
    (close,) = _closes(j)
    assert close["reason"] == "take_profit" and close["exit_price"] == "32000.00000000"
    out = extract_outcomes(j, "brain", RUN).outcomes
    assert [(o.exit_reason, o.exit_price) for o in out] == [("take_profit", D("32000"))]
    rep2 = _run(j, feed, T0 + 11 * MINUTE_MS)                    # la posizione non e' piu' aperta
    assert (rep2.checked, rep2.closed, rep2.errors) == (0, (), ()) and len(_closes(j)) == 1


def test_stop_and_timeout_and_nothing():
    j = _journal()
    stop_id = _open(j, symbol="AAAUSDT")
    time_id = _open(j, symbol="BBBUSDT", now=T_OPEN + 1)
    calm_id = _open(j, symbol="CCCUSDT", now=T_OPEN + 2)
    calm = [_mbar(i, 30000, 30100, 29900, 30000) for i in range(100)]
    feed = _feed({
        "AAAUSDT": [_mbar(0, 30000, 30100, 29900, 30000), _mbar(1, 29500, 29600, 28900, 29000)],
        "BBBUSDT": calm,
        "CCCUSDT": calm[:20],
    })
    rep = _run(j, feed, T0 + 100 * MINUTE_MS)                    # 100 minuti: nessuna durata massima (3 h) superata
    assert dict(rep.closed) == {stop_id: EXIT_STOP} and rep.errors == ()
    stop_close = next(c for c in _closes(j) if c["position_id"] == stop_id)
    assert stop_close["exit_price"] == "29000.00000000"
    short = ExitPolicy(D("2"), 90 * MINUTE_MS, D("0"))
    rep = _run(j, feed, T0 + 100 * MINUTE_MS, policy=short)
    assert dict(rep.closed) == {time_id: EXIT_TIMEOUT, calm_id: EXIT_TIMEOUT} or dict(rep.closed) == {time_id: EXIT_TIMEOUT}
    assert all(c["reason"] in ("stop", "timeout") for c in _closes(j))


def test_a_position_opened_in_the_current_minute_is_skipped_and_no_fetch_happens():
    j = _journal()
    _open(j)
    feed = _feed({"BTCUSDT": []})
    rep = _run(j, feed, T_OPEN + 20_000)                          # ancora dentro il minuto d'apertura
    assert (rep.checked, rep.closed, rep.errors) == (1, (), ()) and feed.calls == []


def test_the_first_minute_requested_is_the_opening_minute_and_the_end_is_aligned():
    j = _journal()
    _open(j)
    feed = _feed({"BTCUSDT": []})
    _run(j, feed, T0 + 5 * MINUTE_MS + 33_000)
    assert feed.calls == [("BTCUSDT", T0, T0 + 5 * MINUTE_MS)]


def test_a_missing_minute_does_not_hide_a_stop_in_the_other_minutes():
    j = _journal()
    pid = _open(j)
    bars = [_mbar(0, 30000, 30100, 29900, 30000), _mbar(1, 30000, 30100, 29900, 30000),
            _mbar(5, 29500, 29600, 28900, 29000)]                # i minuti 2-4 mancano
    rep = _run(j, _feed({"BTCUSDT": bars}), T0 + 10 * MINUTE_MS)
    assert dict(rep.closed) == {pid: EXIT_STOP}


def test_errors_are_isolated_per_position():
    j = _journal()
    bad = _open(j, symbol="BADUSDT")
    ok = _open(j, symbol="OKUSDT", now=T_OPEN + 1)
    feed = _feed({"BADUSDT": RuntimeError("rete"), "OKUSDT": [_mbar(0, 30000, 32100, 29900, 32000)]})
    rep = _run(j, feed, T0 + 10 * MINUTE_MS)
    assert dict(rep.closed) == {ok: EXIT_TAKE_PROFIT} and rep.errors == ((bad, "feed_error"),)
    assert rep.checked == 2


def test_a_corrupt_stop_is_reported_not_crashing():
    j = _journal()
    pid = _open(j)
    # stop non valido sul lato sbagliato (long con stop sopra il prezzo): codice dal modulo delle uscite
    from backend.v3.events import Event
    ev = [s.event for s in j.list_run("brain", RUN) if s.event.kind == "paper_open"][0]
    j2 = _journal()
    p = dict(ev.payload, stop_price="31000")
    j2.append(Event(ev.event_id, "brain", RUN, "paper_open", ev.occurred_at_ms, ev.source, p))
    rep = _run(j2, _feed({"BTCUSDT": [_mbar(0, 30000, 30100, 29900, 30000)]}), T0 + 10 * MINUTE_MS)
    assert rep.closed == () and rep.errors == ((pid, "invalid_position"),)


@pytest.mark.parametrize("now", [0, -1, True, 1.5, None])
def test_bad_now_is_refused(now):
    with pytest.raises(ValueError) as e:
        _run(_journal(), _feed({}), now)
    assert str(e.value) == "invalid_now"


# ----------------------------------------------------------------------------- refresh_raw, minute_fetcher, last_minute_close
from backend.v3.runner.feed import last_minute_close, minute_fetcher   # noqa: E402

M1 = 60_000


def _cs1(fake):
    return CandleStore(fake, keep={"1m": (M1, 200), "15m": (M15, 100)})


def test_refresh_raw_keeps_the_history_before_a_hole_while_refresh_does_not():
    series = _series(T0, 140, M15)
    fake = FakeBitget({("BTCUSDT", "15m"): series}, hole={T0 + 50 * M15})
    cs = _cs(fake)
    raw = cs.refresh_raw("BTCUSDT", "15m", T0 + 80 * M15)
    assert [b.open_time_ms for b in raw] == [b.open_time_ms for b in series[:80] if b.open_time_ms != T0 + 50 * M15]
    assert cs.refresh("BTCUSDT", "15m", T0 + 80 * M15) == series[51:80]
    raw.clear()                                                # una copia: la cache non si altera da fuori
    assert len(cs.refresh_raw("BTCUSDT", "15m", T0 + 80 * M15)) == 79


def test_refresh_raw_rejects_bad_requests_like_refresh():
    for tf, now in [("5m", T0), ("15m", 0), ("15m", True)]:
        with pytest.raises(ValueError) as e:
            _cs(FakeBitget({})).refresh_raw("BTCUSDT", tf, now)
        assert str(e.value) == "invalid_request"


def test_minute_fetcher_filters_by_window_and_keeps_holes():
    series = _series(T0, 150, M1)
    fake = FakeBitget({("BTCUSDT", "1m"): series}, hole={T0 + 40 * M1})
    fetch = minute_fetcher(_cs1(fake))
    got = fetch("BTCUSDT", T0 + 30 * M1, T0 + 60 * M1)
    assert [b.open_time_ms for b in got] == [T0 + i * M1 for i in range(30, 60) if i != 40]
    again = fetch("BTCUSDT", T0 + 30 * M1, T0 + 61 * M1)         # un minuto in piu': solo la barra nuova in rete
    assert again[-1].open_time_ms == T0 + 60 * M1 and len(again) == 30


def test_minute_fetcher_feeds_the_monitor_so_a_stop_before_a_hole_is_still_seen():
    j = _journal()
    pid = _open(j)                                             # long 30000, stop 29000, aperta a T0 + 17 s
    bars = [_mbar(i, 30000, 30100, 29900, 30000) for i in range(30)]
    bars[5] = _mbar(5, 30000, 30050, 28900, 29000)             # minuto 5: tocca lo stop
    fake = FakeBitget({("BTCUSDT", "1m"): bars}, hole={bars[10].open_time_ms})   # buco dopo
    rep = _run(j, minute_fetcher(_cs1(fake)), T0 + 40 * MINUTE_MS)
    assert rep.closed == ((pid, EXIT_STOP),) and rep.errors == ()
    assert _closes(j)[0]["reason"] == "stop"


def test_last_minute_close_is_the_last_closed_minute():
    series = _series(T0, 40, M1)
    fake = FakeBitget({("BTCUSDT", "1m"): series})
    now = T0 + 30 * M1 + 25_000                                # il minuto 30 e' ancora in formazione
    assert last_minute_close("BTCUSDT", now, fake) == series[29].close


def test_last_minute_close_raises_when_there_is_no_recent_bar():
    fake = FakeBitget({("BTCUSDT", "1m"): _series(T0, 5, M1)})
    with pytest.raises(ValueError) as e:
        last_minute_close("BTCUSDT", T0 + 500 * M1, fake)
    assert str(e.value) == "no_recent_bar"
    with pytest.raises(RuntimeError):
        last_minute_close("BTCUSDT", T0 + 3 * M1, FakeBitget({}, fail=True))


# ----------------------------------------------------------------------------- nomi di granularita' verso Bitget
@pytest.mark.parametrize("candle_ms,name", [(60_000, "1m"), (180_000, "3m"), (300_000, "5m"), (900_000, "15m"),
                                            (1_800_000, "30m"), (3_600_000, "1H"), (14_400_000, "4H"),
                                            (21_600_000, "6H"), (43_200_000, "12H"), (86_400_000, "1D"),
                                            (120_000, "2m")])                  # fuori tabella: vecchio "<n>m"
def test_granularity_sent_to_bitget_uses_the_documented_names(candle_ms, name):
    seen = []

    def get(url):
        seen.append(parse_qs(urlparse(url).query)["granularity"][0])
        return {"code": "00000", "data": []}
    fetch_closed_bars("BTCUSDT", 10 * candle_ms, 20 * candle_ms, candle_ms=candle_ms, get_json=get)
    assert seen and set(seen) == {name}


def test_hourly_and_four_hourly_stores_read_the_bitget_names():
    s1 = _series(T0, 40, H1)
    s4 = _series(T0, 40, 4 * H1)
    fake = FakeBitget({("BTCUSDT", "1H"): s1, ("BTCUSDT", "4H"): s4})
    cs = CandleStore(fake, keep={"1h": (H1, 30), "4h": (4 * H1, 20)})
    assert cs.refresh("BTCUSDT", "1h", T0 + 40 * H1) == s1[10:40]
    assert cs.refresh("BTCUSDT", "4h", T0 + 40 * 4 * H1) == s4[20:40]
