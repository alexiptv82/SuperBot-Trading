"""Correzioni del 21/10/2026 (richieste dall'utente): trend giornaliero con storia vera e dati di mercato mancanti
(open interest e long/short ratio). Tutte le risposte di Bitget sono finte ma hanno la FORMA VERA, copiata dalle
sonde fatte sul server il 21/10 (vedi OI_SAMPLE e LS_SAMPLE)."""
import io
import json
import os
import sys
import tempfile
import urllib.error
from urllib.parse import parse_qs, urlparse

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DESK_MACRO_FETCH", "0")

from desk import cli, signals  # noqa: E402
from desk import market_context as mc  # noqa: E402

DAY = 86_400_000
H = 3_600_000
BAR = 900_000
T0 = 1_800_000_000_000 // BAR * BAR
NOW = T0 + 20_000

# Forme vere delle risposte (sonda sul server, 21/10/2026)
OI_SAMPLE = ('{"code":"00000","msg":"success","requestTime":1792563373042,"data":{"openInterestList":'
             '[{"symbol":"BTCUSDT","size":"34041.8475999999923"}],"ts":"1792563373043"}}')
LS_SAMPLE = ('{"code":"00000","msg":"success","requestTime":1792563373376,"data":['
             '{"longAccountRatio":"0.6814","shortAccountRatio":"0.3186","longShortAccountRatio":"2.1387","ts":"1792458000000"},'
             '{"longAccountRatio":"0.688","shortAccountRatio":"0.312","longShortAccountRatio":"2.2051","ts":"1792461600000"}]}')


# ---------------------------------------------------------------- Bitget finto per le barre 1d

class _Resp:
    def __init__(self, body):
        self._b = body.encode() if isinstance(body, str) else body

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_history_opener(n_days, last_open_ms, inclusive_start=True, inclusive_end=True, newest_first=False,
                        max_span_days=90, log=None):
    """Imita /history-candles: barre giornaliere dall'apertura piu' vecchia a `last_open_ms` (il giorno in corso),
    massimo 200 righe, finestra larga al massimo `max_span_days` (oltre: HTTP 400, come il vero)."""
    world = {last_open_ms - i * DAY: [last_open_ms - i * DAY, 100 + i, 101 + i, 99 + i, 100 + i, 1000.0, 1.0]
             for i in range(n_days)}

    def opener(req, timeout=10):
        q = parse_qs(urlparse(req.full_url).query)
        assert "history-candles" in req.full_url and q["granularity"] == ["1D"]
        start, end = int(q["startTime"][0]), int(q["endTime"][0])
        if log is not None:
            log.append((start, end))
        if (end - start) > max_span_days * DAY:
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(b"{}"))
        rows = [r for t, r in world.items()
                if (t >= start if inclusive_start else t > start) and (t <= end if inclusive_end else t < end)]
        rows.sort(key=lambda r: r[0], reverse=newest_first)
        rows = rows[:200]
        return _Resp(json.dumps({"code": "00000", "msg": "success",
                                 "data": [[str(int(r[0]))] + [str(x) for x in r[1:]] for r in rows]}))
    return opener


def day_start(ms):
    return ms // DAY * DAY


_REAL_FETCH = cli.fetch_daily_history      # l'originale: i test lo ripassano con un opener finto
NOSLEEP = lambda s: None                    # noqa: E731  (nei test non si aspetta davvero)


def fetch(sym, now_ms, opener):
    return cli.fetch_daily_history(sym, now_ms, opener=opener, sleep=NOSLEEP)


# ---------------------------------------------------------------- trend 1d: scarico a finestre

def test_history_gives_a_regular_series_of_at_least_200_closed_bars():
    """Con 4 finestre da 85 giorni la serie e' regolare e abbastanza lunga: closed_daily la accetta e il trend 1d
    si puo' calcolare. Vale con ogni convenzione di confine di Bitget (estremi inclusi o no) e con l'ordine
    dal piu' recente."""
    today = day_start(NOW)
    for inc_s in (True, False):
        for inc_e in (True, False):
            for newest in (False, True):
                log = []
                op = make_history_opener(400, today, inc_s, inc_e, newest, log=log)
                rows = fetch("SOL", NOW, op)
                arr = signals.closed_daily(rows, NOW)
                assert len(log) == cli.DAILY_WINDOWS == 4
                assert len(arr) >= signals.DAILY_MIN_BARS, (inc_s, inc_e, newest, len(arr))
                assert (np.diff(arr[:, 0]) == DAY).all() and arr[-1, 0] == today - DAY, (inc_s, inc_e, newest)


def test_history_windows_are_never_wider_than_85_days():
    log = []
    fetch("BTC", NOW, make_history_opener(400, day_start(NOW), log=log))
    assert log and all(end - start <= 85 * DAY for start, end in log)
    # la prima finestra arriva fino a domani (compreso il giorno in corso), le altre scendono senza buchi
    assert log[0][1] == day_start(NOW) + DAY
    for (s0, _e0), (_s1, e1) in zip(log, log[1:]):
        assert e1 >= s0, "tra una finestra e l'altra non deve restare un buco"


def test_history_young_coin_stops_early_and_stays_short():
    log = []
    op = make_history_opener(120, day_start(NOW), log=log)
    rows = fetch("NEWCOIN", NOW, op)
    assert 100 <= len(rows) <= 121 and len(log) == 3          # la terza finestra e' vuota: si smette di scendere
    assert len(signals.closed_daily(rows, NOW)) < signals.DAILY_MIN_BARS     # il trend 1d resta assente


def test_history_bad_answers_raise():
    def bad(req, timeout=10):
        return _Resp('{"code":"40001","msg":"nope","data":[]}')

    def junk(req, timeout=10):
        return _Resp("<html>")

    def http(req, timeout=10):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, io.BytesIO(b""))
    for op in (bad, junk, http):
        try:
            fetch("BTC", NOW, op)
        except Exception:
            continue
        raise AssertionError("una risposta sbagliata non deve diventare una serie vuota silenziosa")


def test_history_gap_inside_series_means_trend_absent():
    today = day_start(NOW)
    rows = fetch("SOL", NOW, make_history_opener(400, today))
    holed = rows[:150] + rows[151:]
    assert len(signals.closed_daily(holed, NOW)) == 0


# ---------------------------------------------------------------- daily_bars: cache, pausa, budget

class _DailyEnv:
    def __enter__(self):
        self.env = os.environ.get("DESK_DAILY_FETCH")
        self.orig = cli.fetch_daily_history
        self.sleep = cli._daily_sleep
        os.environ["DESK_DAILY_FETCH"] = "1"
        cli._daily_sleep = NOSLEEP
        self.reset()
        return self

    @staticmethod
    def reset():
        cli._DAILY_CACHE.clear()
        cli._DAILY_FAILED.clear()
        cli._DAILY_PAUSE.update(until_ms=0, streak=0)
        cli._DAILY_CYCLE.update(now_ms=None, t0=0.0)

    def __exit__(self, *a):
        cli.fetch_daily_history = self.orig
        cli._daily_sleep = self.sleep
        os.environ["DESK_DAILY_FETCH"] = self.env
        self.reset()


def test_daily_bars_env_guard_never_downloads():
    calls = []
    orig, env = cli.fetch_daily_history, os.environ.get("DESK_DAILY_FETCH")
    cli.fetch_daily_history = lambda *a, **k: calls.append(a) or []
    os.environ["DESK_DAILY_FETCH"] = "0"
    try:
        assert len(cli.daily_bars("SOL", NOW)) == 0 and calls == []
    finally:
        cli.fetch_daily_history = orig
        os.environ["DESK_DAILY_FETCH"] = env


def test_daily_bars_one_failing_symbol_does_not_stop_the_others():
    calls = []
    with _DailyEnv():
        good = make_history_opener(400, day_start(NOW))

        def fake(sym, now_ms, **kw):
            calls.append(sym)
            if sym == "BAD":
                raise OSError("rete")
            return _REAL_FETCH(sym, now_ms, opener=good, sleep=NOSLEEP)
        cli.fetch_daily_history = fake
        assert len(cli.daily_bars("BAD", NOW)) == 0
        assert len(cli.daily_bars("ETH", NOW + 1000)) >= 200                  # un solo errore: gli altri vanno avanti
        assert len(cli.daily_bars("BAD", NOW + 2000)) == 0 and calls == ["BAD", "ETH"]   # BAD non si insiste per 5 minuti
        assert len(cli.daily_bars("BAD", NOW + cli.DAILY_PAUSE_MS + 1)) == 0
        assert calls == ["BAD", "ETH", "BAD"]                                 # passati 5 minuti si riprova


def test_daily_bars_three_failures_in_a_row_pause_everything_and_success_resets_the_count():
    calls = []
    with _DailyEnv():
        good = make_history_opener(400, day_start(NOW))

        def fake(sym, now_ms, **kw):
            calls.append(sym)
            if sym.startswith("BAD"):
                raise OSError("rete")
            return _REAL_FETCH(sym, now_ms, opener=good, sleep=NOSLEEP)
        cli.fetch_daily_history = fake
        cli.daily_bars("BAD1", NOW)
        cli.daily_bars("BAD2", NOW)
        cli.daily_bars("OK", NOW)                                             # un successo azzera la serie di errori
        assert cli._DAILY_PAUSE["streak"] == 0
        cli.daily_bars("BAD3", NOW)
        cli.daily_bars("BAD4", NOW)
        assert cli._DAILY_PAUSE["until_ms"] == 0
        cli.daily_bars("BAD5", NOW)                                           # terzo errore di fila: stop a tutti
        assert cli._DAILY_PAUSE["until_ms"] == NOW + cli.DAILY_PAUSE_MS
        n = len(calls)
        assert len(cli.daily_bars("ETH", NOW + 1000)) == 0 and len(calls) == n
        assert len(cli.daily_bars("ETH", NOW + cli.DAILY_PAUSE_MS)) >= 200


def test_daily_bars_falls_back_to_yesterdays_series_when_the_refresh_fails():
    with _DailyEnv():
        good = make_history_opener(400, day_start(NOW))
        cli.fetch_daily_history = lambda sym, now_ms, **kw: _REAL_FETCH(sym, now_ms, opener=good, sleep=NOSLEEP)
        yesterday = cli.daily_bars("SOL", NOW)
        assert len(yesterday) >= 200

        def boom(sym, now_ms, **kw):
            raise OSError("rete")
        cli.fetch_daily_history = boom
        tomorrow = NOW + DAY
        got = cli.daily_bars("SOL", tomorrow)                                  # l'indomani il rinnovo fallisce
        assert len(got) == len(yesterday) and (got == yesterday).all()
        too_old = NOW + (cli.DAILY_STALE_DAYS + 1) * DAY
        cli._DAILY_FAILED.clear()
        assert len(cli.daily_bars("SOL", too_old)) == 0                        # oltre i giorni ammessi non vale piu'


def test_daily_bars_budget_returns_yesterdays_series_for_deferred_symbols():
    clock = {"t": 1000.0}
    real_mono = cli.time.monotonic
    with _DailyEnv():
        good = make_history_opener(400, day_start(NOW))
        cli.fetch_daily_history = lambda sym, now_ms, **kw: _REAL_FETCH(sym, now_ms, opener=good, sleep=NOSLEEP)
        cli.daily_bars("C", NOW)                                               # serie di "ieri"
        cli.time.monotonic = lambda: clock["t"]
        try:
            nxt = NOW + DAY
            cli.daily_bars("A", nxt)                                           # apre il ciclo e parte il cronometro
            clock["t"] += cli.DAILY_CYCLE_BUDGET_S + 1
            assert len(cli.daily_bars("C", nxt)) >= 200                        # budget finito: resta quella di ieri
            assert "C" in cli._DAILY_CACHE and cli._DAILY_CACHE["C"][0] == day_start(NOW) // DAY
        finally:
            cli.time.monotonic = real_mono


def test_fetch_retries_on_429_then_gives_up_and_never_retries_other_errors():
    waits = []
    ok = make_history_opener(400, day_start(NOW))

    def flaky(n_fail, code=429):
        state = {"n": 0}

        def op(req, timeout=10):
            state["n"] += 1
            if state["n"] <= n_fail:
                raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(b"{}"))
            return ok(req, timeout)
        op.state = state
        return op
    rec = lambda w: waits.append(w)                                                # noqa: E731
    op = flaky(2)
    rows = cli.fetch_daily_history("SOL", NOW, opener=op, sleep=rec)
    assert len(signals.closed_daily(rows, NOW)) >= 200
    assert waits[:2] == [2.0, 4.0]                                                 # attese crescenti dopo i due 429
    # tre 429 di fila sulla stessa finestra: si arrende
    waits.clear()
    op = flaky(99)
    try:
        cli.fetch_daily_history("SOL", NOW, opener=op, sleep=rec)
        raise AssertionError("doveva sollevare")
    except urllib.error.HTTPError as e:
        assert e.code == 429 and op.state["n"] == 3 and waits == [2.0, 4.0]
    # un errore diverso (500) non si ritenta
    waits.clear()
    op = flaky(99, code=500)
    try:
        cli.fetch_daily_history("SOL", NOW, opener=op, sleep=rec)
        raise AssertionError("doveva sollevare")
    except urllib.error.HTTPError as e:
        assert e.code == 500 and op.state["n"] == 1 and waits == []


def test_fetch_429_in_the_body_is_retried_too():
    state = {"n": 0}
    ok = make_history_opener(400, day_start(NOW))

    def op(req, timeout=10):
        state["n"] += 1
        if state["n"] == 1:
            return _Resp('{"code":"429","msg":"Too Many Requests","data":null}')
        return ok(req, timeout)
    rows = cli.fetch_daily_history("SOL", NOW, opener=op, sleep=NOSLEEP)
    assert len(signals.closed_daily(rows, NOW)) >= 200


def test_fetch_pauses_between_calls_to_stay_under_the_rate_limit():
    waits = []
    cli.fetch_daily_history("SOL", NOW, opener=make_history_opener(400, day_start(NOW)), sleep=waits.append)
    assert waits == [cli.DAILY_CALL_GAP_S] * (cli.DAILY_WINDOWS - 1)


def test_warm_up_loads_every_symbol_without_time_limit_and_retries_the_failed_ones():
    calls = []
    clock = {"t": 1000.0}
    real_mono = cli.time.monotonic
    with _DailyEnv():
        good = make_history_opener(400, day_start(NOW))
        fails = {"B": 1}

        def fake(sym, now_ms, **kw):
            calls.append(sym)
            clock["t"] += 50.0                                                     # ogni simbolo costa 50 s
            if fails.get(sym, 0) > 0:
                fails[sym] -= 1
                raise OSError("rete")
            return _REAL_FETCH(sym, now_ms, opener=good, sleep=NOSLEEP)
        cli.fetch_daily_history = fake
        cli.time.monotonic = lambda: clock["t"]
        try:
            n = cli.warm_daily_cache(["A", "B", "C", "D"], NOW)
        finally:
            cli.time.monotonic = real_mono
        assert n == 4, "tutti pronti: B dopo la seconda passata"
        assert calls == ["A", "B", "C", "D", "B"]                                  # nessun tetto di tempo, B ritentato
        assert cli.warm_daily_cache(["A", "B", "C", "D"], NOW) == 4 and len(calls) == 5   # niente di nuovo da scaricare


def test_daily_bars_caches_short_series_for_the_day():
    """Una moneta giovane (serie corta) o una serie irregolare non si riscarica a ogni ciclo."""
    calls = []
    with _DailyEnv():
        young = make_history_opener(100, day_start(NOW))
        cli.fetch_daily_history = lambda sym, now_ms, **kw: calls.append(sym) or _REAL_FETCH(sym, now_ms, opener=young)
        assert 0 < len(cli.daily_bars("NEW", NOW)) < signals.DAILY_MIN_BARS
        cli.daily_bars("NEW", NOW + 15 * 60_000)
        cli.daily_bars("NEW", NOW + 2 * H)
        assert calls == ["NEW"]
        cli.daily_bars("NEW", NOW + DAY)                              # giorno nuovo: si riscarica
        assert calls == ["NEW", "NEW"]


def test_daily_bars_caches_irregular_series_as_empty():
    calls = []
    with _DailyEnv():
        rows = _REAL_FETCH("X", NOW, opener=make_history_opener(400, day_start(NOW)))
        holed = rows[:150] + rows[151:]
        cli.fetch_daily_history = lambda sym, now_ms, **kw: calls.append(sym) or holed
        assert len(cli.daily_bars("X", NOW)) == 0
        assert len(cli.daily_bars("X", NOW + 60_000)) == 0
        assert calls == ["X"]


def test_daily_bars_cycle_budget_defers_remaining_symbols_to_next_cycle():
    calls = []
    clock = {"t": 1000.0}
    real_mono = cli.time.monotonic
    with _DailyEnv():
        good = make_history_opener(400, day_start(NOW))

        def fetch(sym, now_ms, **kw):
            calls.append(sym)
            clock["t"] += 50.0                                        # ogni scarico costa 50 s
            return _REAL_FETCH(sym, now_ms, opener=good)
        cli.fetch_daily_history = fetch
        cli.time.monotonic = lambda: clock["t"]
        try:
            assert len(cli.daily_bars("A", NOW)) >= 200               # 50 s spesi
            assert len(cli.daily_bars("B", NOW)) >= 200               # a 50 s si parte ancora (limite 90)
            assert len(cli.daily_bars("C", NOW)) == 0                 # 100 s: budget finito, C aspetta
            assert calls == ["A", "B"]
            nxt = NOW + 15 * 60_000                                   # ciclo successivo: il tempo riparte
            assert len(cli.daily_bars("C", nxt)) >= 200
            assert len(cli.daily_bars("A", nxt)) >= 200               # gia' in cache: nessuna chiamata
            assert calls == ["A", "B", "C"]
        finally:
            cli.time.monotonic = real_mono


def test_daily_trend_now_reaches_the_score_through_daily_bars():
    """Dall'inizio alla fine: serie 1d vera -> daily_bars -> read_symbol -> trend 1d presente e +15 punti."""
    rng = np.random.default_rng(1)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, 1000)))
    o = np.r_[c[0], c[:-1]]
    arr15 = np.c_[T0 - BAR - (999 - np.arange(1000)) * BAR, o, np.maximum(o, c) * 1.001,
                  np.minimum(o, c) * 0.999, c, np.full(1000, 10.0)]
    with _DailyEnv():
        up = make_history_opener(400, day_start(NOW))
        cli.fetch_daily_history = lambda sym, now_ms, **kw: _REAL_FETCH(sym, now_ms, opener=up)
        dly = cli.daily_bars("SOL", NOW)
    none = signals.read_symbol("SOL", arr15, NOW)
    r = signals.read_symbol("SOL", arr15, NOW, daily=dly)
    assert none.facts["daily_trend"] == "" and r.facts["daily_trend"] != ""


# ---------------------------------------------------------------- open interest

def _with_get(mapping):
    """Sostituisce mc._get con un dizionario {pezzo di url: corpo}; restituisce una funzione di ripristino."""
    orig = mc._get
    seen = []

    def fake(url, timeout=8):
        seen.append(url)
        for k, body in mapping.items():
            if k in url:
                return None if body is None else body.encode()
        return None
    mc._get = fake
    return seen, lambda: setattr(mc, "_get", orig)


def test_open_interest_reads_the_real_shape_and_converts_coins_to_usd():
    seen, undo = _with_get({"open-interest": OI_SAMPLE})
    try:
        r = mc.fetch_open_interest("BTC", price=67_000.0)
    finally:
        undo()
    assert r is not None and abs(r.oi_usd - 34041.8475999999923 * 67_000.0) < 1
    assert r.oi_change_24h is None and "n.d." in r.note and "2280.8M" in r.note
    assert "productType=USDT-FUTURES" in seen[0] and "symbol=BTCUSDT" in seen[0]


def test_open_interest_takes_the_price_from_the_ticker_when_not_given():
    tick = '{"code":"00000","data":[{"symbol":"BTCUSDT","lastPr":"50000.5"},{"symbol":"ETHUSDT","lastPr":"2500"}]}'
    _, undo = _with_get({"open-interest": OI_SAMPLE, "tickers": tick})
    try:
        r = mc.fetch_open_interest("BTC")
    finally:
        undo()
    assert r is not None and abs(r.oi_usd - 34041.8475999999923 * 50000.5) < 1


def test_open_interest_bad_data_is_none_never_a_made_up_number():
    for body in ('{"code":"40001","data":{}}', '{"code":"00000","data":{"openInterestList":[]}}',
                 '{"code":"00000","data":{"openInterestList":[{"symbol":"BTCUSDT","size":"0"}]}}',
                 '{"code":"00000","data":[]}', "not json", None):
        _, undo = _with_get({"open-interest": body})
        try:
            assert mc.fetch_open_interest("BTC", price=60_000.0) is None, body
        finally:
            undo()
    _, undo = _with_get({"open-interest": OI_SAMPLE, "tickers": None})
    try:
        assert mc.fetch_open_interest("BTC") is None            # senza prezzo non si inventa il valore in dollari
        assert mc.fetch_open_interest("BTC", price=0) is None
    finally:
        undo()


def test_tickers_one_call_parses_prices():
    _, undo = _with_get({"tickers": '{"code":"00000","data":[{"symbol":"btcusdt","lastPr":"1.5"},{"symbol":"X"},'
                                    '{"symbol":"ETHUSDT","lastPr":"0"}]}'})
    try:
        assert mc.fetch_tickers() == {"BTCUSDT": 1.5}
    finally:
        undo()
    _, undo = _with_get({"tickers": '{"code":"1","data":[]}'})
    try:
        assert mc.fetch_tickers() == {}
    finally:
        undo()


# ---------------------------------------------------------------- long/short ratio

def test_ls_ratio_reads_the_real_endpoint_and_the_latest_row():
    seen, undo = _with_get({"account-long-short": LS_SAMPLE})
    try:
        r = mc.fetch_ls_ratio("BTC")
    finally:
        undo()
    assert r is not None and abs(r.ratio - 2.2051) < 1e-9 and "crowd long" in r.note
    assert "/account-long-short?" in seen[0] and "account-long-short-ratio" not in seen[0]
    # ordine inverso nella risposta: vale comunque la riga col ts piu' recente
    body = json.loads(LS_SAMPLE)
    body["data"].reverse()
    _, undo = _with_get({"account-long-short": json.dumps(body)})
    try:
        assert abs(mc.fetch_ls_ratio("ETH").ratio - 2.2051) < 1e-9
    finally:
        undo()


def test_ls_ratio_edge_cases():
    _, undo = _with_get({"account-long-short": LS_SAMPLE})
    try:
        assert mc.fetch_ls_ratio("XAU") is None and mc.fetch_ls_ratio("XAG") is None
    finally:
        undo()
    for body in ('{"code":"40001","data":[]}', '{"code":"00000","data":[]}', "x", None,
                 '{"code":"00000","data":[{"longShortAccountRatio":"0","ts":"1"}]}'):
        _, undo = _with_get({"account-long-short": body})
        try:
            assert mc.fetch_ls_ratio("SOL") is None, body
        finally:
            undo()
    low = LS_SAMPLE.replace("2.2051", "0.6").replace("2.1387", "0.6")
    _, undo = _with_get({"account-long-short": low})
    try:
        assert "crowd short" in mc.fetch_ls_ratio("SOL").note
    finally:
        undo()


# ---------------------------------------------------------------- variazione 24h dell'OI

def _row(oi):
    return {"oi_usd": oi, "oi_change_24h": None, "note": ""}


def test_oi_change_needs_about_a_day_of_history():
    hist = {}
    rows = {"BTC": _row(1000.0)}
    mc.apply_oi_history(rows, hist, NOW)
    assert rows["BTC"]["oi_change_24h"] is None and "n.d." in rows["BTC"]["note"]
    assert hist["BTC"] == [[NOW, 1000.0]]
    # 10 ore dopo: ancora troppo poco storico
    rows = {"BTC": _row(1100.0)}
    mc.apply_oi_history(rows, hist, NOW + 10 * H)
    assert rows["BTC"]["oi_change_24h"] is None
    # 24 ore dopo la prima lettura: +10%
    rows = {"BTC": _row(1100.0)}
    mc.apply_oi_history(rows, hist, NOW + 24 * H)
    assert rows["BTC"]["oi_change_24h"] == 10.0 and "+10.0%" in rows["BTC"]["note"]
    assert "forte crescita" not in rows["BTC"]["note"]          # esattamente +10% non e' sopra la soglia


def test_oi_change_picks_the_reading_closest_to_24h_and_flags_big_moves():
    hist = {"BTC": [[NOW - 25 * H, 800.0], [NOW - 22 * H, 900.0], [NOW - 3 * H, 1000.0]]}
    rows = {"BTC": _row(1000.0)}
    mc.apply_oi_history(rows, hist, NOW)
    assert rows["BTC"]["oi_change_24h"] == 25.0                 # riferimento: 25 h fa (a 1 h da 24) -> 800 -> +25%
    assert "forte crescita" in rows["BTC"]["note"]
    hist = {"ETH": [[NOW - 24 * H, 1000.0]]}
    rows = {"ETH": _row(800.0)}
    mc.apply_oi_history(rows, hist, NOW)
    assert rows["ETH"]["oi_change_24h"] == -20.0 and "calo" in rows["ETH"]["note"]


def test_oi_history_is_pruned_capped_and_survives_garbage():
    hist = {"BTC": [[NOW - 40 * H, 5.0], [NOW - 30 * H, 6.0], "x", [NOW + H, 7.0], [NOW - 2 * H, -1.0]],
            "GONE": [[NOW - H, 1.0]]}
    rows = {"BTC": _row(100.0), "BAD": {"oi_usd": "x"}, "ZERO": _row(0.0)}
    mc.apply_oi_history(rows, hist, NOW)
    assert "GONE" not in hist and "BAD" not in hist and "ZERO" not in hist
    assert hist["BTC"] == [[NOW, 100.0]]                         # vecchie, future e non valide scartate
    for i in range(200):
        mc.apply_oi_history({"BTC": _row(100.0)}, hist, NOW + (i + 1) * 60_000)
    assert len(hist["BTC"]) == mc.OI_HIST_MAX_POINTS


def test_fetch_all_context_uses_one_ticker_call_for_all_symbols():
    seen, undo = _with_get({"tickers": '{"code":"00000","data":[{"symbol":"BTCUSDT","lastPr":"60000"},'
                                       '{"symbol":"ETHUSDT","lastPr":"3000"}]}',
                            "open-interest": OI_SAMPLE.replace("34041.8475999999923", "10"),
                            "account-long-short": LS_SAMPLE, "current-fund-rate": None, "cryptopanic": None})
    orig_news = mc.fetch_cryptopanic
    mc.fetch_cryptopanic = lambda syms, limit=6: []
    try:
        ctx = mc.fetch_all_context(["BTC", "ETH"], NOW)
    finally:
        mc.fetch_cryptopanic = orig_news
        undo()
    assert sum("tickers" in u for u in seen) == 1
    assert abs(ctx["oi"]["BTC"].oi_usd - 600_000.0) < 1 and abs(ctx["oi"]["ETH"].oi_usd - 30_000.0) < 1
    assert ctx["ls_ratio"]["BTC"].ratio > 2


# ---------------------------------------------------------------- nel ciclo vero

def test_cycle_stores_oi_history_and_computes_the_change():
    import desk.brain as _brain

    now = T0 + 4 * BAR + 20_000
    rows = {s: np.array([[T0 - (60 - i) * BAR, 100, 100.1, 99.9, 100, 1] for i in range(65)]) for s in cli.SYMBOLS}

    def call(system, user, max_tokens=1100, timeout=60):
        return json.dumps({"decisions": [], "note": "test"}), {"input_tokens": 10, "output_tokens": 10}

    saved = (cli.fetch_candles, cli.fetch_all_context, _brain.call_claude, cli.call_claude, cli.STATE_FILE,
             cli.DATA_DIR)
    cli.fetch_candles = lambda sym, bar="15m", limit=300: rows.get(sym, np.zeros((0, 6)))[-limit:].tolist()
    cli.fetch_all_context = lambda syms, n: {
        "funding": {}, "oi": {"BTC": mc.OIInfo("BTC", 1100.0, None, "")}, "ls_ratio": {}, "news": [], "ts": n}
    _brain.call_claude = call
    cli.call_claude = call
    os.environ["ANTHROPIC_API_KEY"] = "test"
    try:
        with tempfile.TemporaryDirectory() as d:
            cli.STATE_FILE = os.path.join(d, "state_v2.json")
            cli.DATA_DIR = d
            state = cli.load_state(cli.STATE_FILE)
            state["oi_hist"] = {"BTC": [[now - 24 * H, 1000.0]]}
            cli.run_cycle(state, now)
            assert state["market_ctx"]["oi"]["BTC"]["oi_change_24h"] == 10.0
            assert state["oi_hist"]["BTC"][-1] == [now, 1100.0] and len(state["oi_hist"]["BTC"]) == 2
            json.dumps(state, default=str)                       # lo stato resta serializzabile
    finally:
        (cli.fetch_candles, cli.fetch_all_context, _brain.call_claude, cli.call_claude, cli.STATE_FILE,
         cli.DATA_DIR) = saved


def test_features_log_oi_and_ls_with_none_when_unknown():
    from desk.learning import build_features
    ctx = {"oi": {"BTC": {"oi_usd": 1234567.0, "oi_change_24h": None, "note": "x"}},
           "ls_ratio": {"BTC": {"ratio": 2.2051, "note": "y"}}, "funding": {}}
    f = build_features("BTC", None, ctx, None, NOW)
    assert f["oi_usd"] == 1234567.0 and f["oi_change_24h"] is None and f["ls_ratio"] == 2.205


def test_portfolio_reset_keeps_the_oi_history():
    """L'azzeramento del conto non deve buttare le letture dell'OI: servono 24 ore per calcolare la variazione."""
    saved = (cli.DATA_DIR, cli.STATE_FILE)
    try:
        with tempfile.TemporaryDirectory() as d:
            cli.DATA_DIR = d
            cli.STATE_FILE = os.path.join(d, "state_v2.json")
            state = {}
            acc = cli.make_account(state)
            acc.open("BTC", 1, 100, 10, 100.0, 95.0, None, NOW, {})
            cli.append_trade_history(d, acc.close("BTC", 101.0, NOW + 500, "take profit"))
            cli.save_account(acc, state)
            state["run_no"] = 1
            state["oi_hist"] = {"BTC": [[NOW, 5.0]]}
            cli.save_state(state, cli.STATE_FILE)
            open(os.path.join(d, "pause.flag"), "w").close()
            open(os.path.join(d, "reset_portfolio.flag"), "w").write("{}")
            assert cli._check_portfolio_reset_flag(state) is True and state["run_no"] == 2
            assert state["oi_hist"] == {"BTC": [[NOW, 5.0]]}
    finally:
        cli.DATA_DIR, cli.STATE_FILE = saved


def test_main_warms_the_daily_cache_before_the_first_cycle_and_survives_its_failure():
    order = []
    saved = (cli.warm_daily_cache, cli.loop_step, cli.DATA_DIR, cli.STATE_FILE, sys.argv[:])

    def stop(state, ctl):
        order.append("ciclo")
        raise SystemExit(0)
    try:
        with tempfile.TemporaryDirectory() as d:
            cli.DATA_DIR = d
            cli.STATE_FILE = os.path.join(d, "state_v2.json")
            sys.argv = ["cli"]
            cli.loop_step = stop
            cli.warm_daily_cache = lambda syms, now: order.append("caldo") or 26
            try:
                cli.main()
            except SystemExit:
                pass
            assert order == ["caldo", "ciclo"], order
            order.clear()

            def broken(syms, now):
                order.append("caldo")
                raise RuntimeError("rete")
            cli.warm_daily_cache = broken
            try:
                cli.main()
            except SystemExit:
                pass
            assert order == ["caldo", "ciclo"], "un guasto del precaricamento non deve fermare l'avvio"
    finally:
        cli.warm_daily_cache, cli.loop_step, cli.DATA_DIR, cli.STATE_FILE, sys.argv[:] = saved
