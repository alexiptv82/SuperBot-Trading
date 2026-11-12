"""RC84 fase 2B: storico giornaliero Bitget paginato (history-candles), cache, limiti di richiesta, coerenza 4h/1d.

Nessuna rete: ``FakeBitget`` imita /api/v2/mix/market/history-candles (pagine con estremi inclusi, righe in ordine
sparso, duplicati ai bordi, candela del giorno in formazione, simboli quotati da poco, errori, giorni mancanti).
"""
import io
import json
import os
import sys

import numpy as np
import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from desk import signals as S  # noqa: E402
from test_desk_rc84_phase2 import NOW, H4, D1, native_bars, m15, sandbox, _run, _proposal, _learning  # noqa: E402,F401


class FakeBitget:
    """Serie giornaliera di `days` giorni fino a oggi (in formazione compresa); pagine con estremi inclusi."""

    def __init__(self, now_ms, days, drift=0.002, missing=(), fail_on=(), seed=7):
        rows = native_bars(now_ms, D1, days, drift, seed=seed)     # ultima riga = giorno in formazione
        self.rows = [r for i, r in enumerate(rows.tolist()) if i not in set(missing)]
        self.calls, self.fail_on = [], set(fail_on)
        self.rng = np.random.default_rng(seed)

    def __call__(self, sym, gran, start, end):
        self.calls.append((gran, start, end))
        if len(self.calls) in self.fail_on:
            return None
        page = [list(r) for r in self.rows if start <= r[0] <= end]   # estremi inclusi: i bordi si ripetono
        page += [list(r) for r in page[:2]]                             # duplicati esatti
        self.rng.shuffle(page)                                          # ordine sparso
        return page


@pytest.fixture
def cli(monkeypatch):
    from desk import cli as c
    c._HTF_CACHE.clear()
    c.htf_budget_reset()
    yield c
    c._HTF_CACHE.clear()
    c.htf_budget_reset()


def _check_series(arr, now_ms):
    ts = arr[:, 0].astype(np.int64)
    assert np.all(np.diff(ts) > 0), "ordine crescente senza duplicati"
    assert np.all(ts % D1 == 0), "allineate alla giornata UTC"
    assert np.all(ts + D1 <= now_ms), "nessuna candela in formazione"


def test_full_history_reaches_the_target_in_three_89_day_pages(cli):
    fb = FakeBitget(NOW, 400)
    out = cli.fetch_daily_history("BTC", NOW, fb)
    arr = out["arr"]
    assert out["status"] == "ok" and len(fb.calls) == 3                 # come sulla VPS: 3 pagine, 267 barre
    assert len(arr) == 3 * cli.DAILY_PAGE_DAYS == 267                     # 3 pagine da 89 giorni, bordi deduplicati
    _check_series(arr, NOW)
    assert all(g == "1Dutc" for g, _s, _e in fb.calls)
    ends = [e for _g, _s, e in fb.calls]
    assert ends == sorted(ends, reverse=True) and ends[0] == NOW - NOW % D1  # all'indietro, a partire da oggi 00:00
    r = S.read_symbol("BTC", m15(NOW, 1000, 0.0), NOW, bars_4h=native_bars(NOW, H4, 400, 0.002), bars_1d=arr)
    assert r.facts["trend1d_state"] == "UP" and r.facts["trend1d_bars"] == len(arr)


def test_recent_symbol_stops_at_the_first_empty_page_and_is_unknown_not_invented(cli):
    fb = FakeBitget(NOW, 120)
    out = cli.fetch_daily_history("SUI", NOW, fb)
    assert out["status"] == "storia_finita" and len(out["arr"]) == 120    # 120 giorni chiusi (quello in formazione escluso)
    _check_series(out["arr"], NOW)
    r = S.read_symbol("SUI", m15(NOW, 1000, 0.0), NOW, bars_4h=native_bars(NOW, H4, 400, 0.002), bars_1d=out["arr"])
    assert r.facts["trend1d_state"] == "UNKNOWN" and "storia insufficiente: 120" in r.facts["trend1d_why"]
    assert r.facts["trend4h_state"] == "UP"                                     # il 1d UNKNOWN non tocca il 4h
    # giorno dopo: storia esaurita -> basta una pagina (niente ricostruzione da capo)
    n = len(fb.calls)
    nxt = NOW + D1
    fb2 = FakeBitget(nxt, 121)
    out2 = cli.fetch_daily_history("SUI", nxt, fb2)
    assert len(fb2.calls) == 1 and len(out2["arr"]) == 121 and n == len(fb.calls)


def test_cache_same_day_no_requests_next_day_one_incremental_page(cli):
    fb = FakeBitget(NOW, 400)
    first = cli.fetch_daily_history("BTC", NOW, fb)["arr"]
    n = len(fb.calls)
    assert cli.fetch_daily_history("BTC", NOW + 6 * 3_600_000, fb)["status"] == "cache" and len(fb.calls) == n
    nxt = NOW + D1
    fb2 = FakeBitget(nxt, 401)                                           # stessa serie piu' un giorno
    out = cli.fetch_daily_history("BTC", nxt, fb2)
    assert len(fb2.calls) == 1 and out["status"] == "ok"
    assert len(out["arr"]) == len(first) + 1 and out["arr"][-1, 0] == first[-1, 0] + D1
    assert np.array_equal(out["arr"][:len(first), 0], first[:, 0])      # nessuna barra vecchia persa


def test_api_error_mid_pagination_keeps_nothing_invented_and_waits_before_retrying(cli):
    fb = FakeBitget(NOW, 400, fail_on={2})
    out = cli.fetch_daily_history("ETH", NOW, fb)
    assert out == {"arr": None, "status": "errore_api"}
    n = len(fb.calls)
    assert cli.fetch_daily_history("ETH", NOW + 10 * 60_000, fb)["status"] == "attesa_dopo_errore" and len(fb.calls) == n
    fb.fail_on = set()
    out = cli.fetch_daily_history("ETH", NOW + cli.HTF_RETRY_MS + 1, fb)
    assert out["status"] == "ok" and len(out["arr"]) >= 250


def test_expired_cache_with_api_error_returns_the_old_series_and_signals_call_it_stale(cli):
    cli.fetch_daily_history("BTC", NOW, FakeBitget(NOW, 400))
    nxt = NOW + D1
    out = cli.fetch_daily_history("BTC", nxt, lambda *a: None)
    assert out["status"] == "errore_api" and out["arr"] is not None
    r = S.read_symbol("BTC", m15(nxt, 1000, 0.0), nxt, bars_4h=native_bars(nxt, H4, 400, 0.002), bars_1d=out["arr"])
    assert r.facts["trend1d_state"] == "UNKNOWN" and "dati vecchi" in r.facts["trend1d_why"]


def test_missing_days_cut_the_series(cli):
    # un buco di 6 giorni a 150 giorni dalla fine: resta la coda dopo il buco (<200) -> UNKNOWN
    fb = FakeBitget(NOW, 400, missing=range(250, 256))
    arr = cli.fetch_daily_history("XRP", NOW, fb)["arr"]
    r = S.read_symbol("XRP", m15(NOW, 1000, 0.0), NOW, bars_4h=native_bars(NOW, H4, 400, 0.002), bars_1d=arr)
    assert r.facts["trend1d_state"] == "UNKNOWN" and "storia insufficiente" in r.facts["trend1d_why"]
    # fase 2C: i buchi corti non sono piu' tollerati in generale; dipende dal calendario (test_desk_rc84_phase2c.py)


def test_a_daily_page_with_another_granularity_is_an_error_and_is_not_cached(cli):
    bad = lambda sym, gran, start, end: native_bars(NOW, H4, 600, 0.0).tolist()            # noqa: E731
    out = cli.fetch_daily_history("BTC", NOW, bad)
    assert out == {"arr": None, "status": "errore_api"} and cli._HTF_CACHE[("BTC", "1d")]["arr"] is None


def test_request_budget_per_cycle_is_shared_by_all_symbols(cli):
    symbols = ["S%d" % i for i in range(6)]
    fbs = {s: FakeBitget(NOW, 400, seed=i) for i, s in enumerate(symbols)}
    status = {s: cli.fetch_daily_history(s, NOW, fbs[s])["status"] for s in symbols}
    pages = sum(len(f.calls) for f in fbs.values())
    assert pages == cli.HISTORY_PAGES_PER_CYCLE == 12
    assert [status[s] for s in symbols[:4]] == ["ok"] * 4 and status["S4"] == "budget_esaurito"
    assert len(fbs["S5"].calls) == 0
    cli.htf_budget_reset()                                               # ciclo successivo: si completa il resto
    assert cli.fetch_daily_history("S4", NOW + 900_000, fbs["S4"])["status"] == "ok"
    assert cli.fetch_daily_history("S5", NOW + 900_000, fbs["S5"])["status"] == "ok"


def test_merge_drops_open_misaligned_and_invalid_rows_and_counts_conflicts(cli):
    good = native_bars(NOW, D1, 10, 0.0, with_partial=True).tolist()
    bad = [  # le righe non valide si scartano; il conflitto resta visibile
[good[3][0] + 3_600_000, 1, 1, 1, 1, 1],            # non allineata
           [good[4][0], float("nan"), 1, 1, 1, 1],              # non finita
           [good[5][0], -1, 1, 1, 1, 1],                        # prezzo negativo
           [good[6][0], 9, 9, 9, 9, 9]]                         # stesso giorno, valori diversi: vince l'ultimo scaricato
    arr, conflicts = cli.merge_bars(good, bad, D1, NOW)
    # 10 chiuse (quella in formazione esclusa) + la seconda versione del giorno in conflitto, che NON sostituisce la prima
    assert len(arr) == 11 and conflicts == 1
    assert sorted(arr[arr[:, 0] == good[6][0], 4].tolist()) == sorted([good[6][4], 9.0])
    assert arr[4, 4] == good[4][4] and arr[5, 4] == good[5][4]
    t = S.htf_trend(arr, NOW, D1)
    assert t["state"] == "UNKNOWN" and "duplicati in conflitto" in t["why"]


def test_4h_bars_of_the_wrong_granularity_are_rejected(cli):
    out = cli.fetch_htf("BTC", NOW, lambda s, g, l: m15(NOW, 1000, 0.0).tolist(), FakeBitget(NOW, 400))
    assert out["4h"] is None and out["status"]["4h"] == "errore_api"   # righe 15m: rifiutate in blocco
    r = S.read_symbol("BTC", m15(NOW, 1000, 0.0), NOW, bars_4h=out["4h"], bars_1d=out["1d"])
    assert r.facts["trend4h_state"] == "UNKNOWN" and r.side == 0
    assert r.facts["trend1d_state"] in ("UP", "DOWN")


def test_history_page_url_and_error_handling(cli, monkeypatch):
    seen = {}

    def rows(url):
        seen["url"] = url
        return []
    monkeypatch.setattr(cli, "_bitget_rows", rows)
    assert cli.fetch_history_page("BTC", "1Dutc", 1, 2) == []
    assert seen["url"] == ("https://api.bitget.com/api/v2/mix/market/history-candles?symbol=BTCUSDT"
                           "&productType=USDT-FUTURES&granularity=1Dutc&startTime=1&endTime=2&limit=200")
    monkeypatch.undo()

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    for body, want in ((b'{"code":"00000","data":[["2","1","1","1","1","1","1"],["1","1","1","1","1","1","1"]]}', [[1.0] * 6, [2.0] + [1.0] * 5]),
                       (b'{"code":"00000","data":[]}', []), (b'{"code":"40034","msg":"x"}', None), (b"non json", None)):
        monkeypatch.setattr(cli.urllib.request, "urlopen", lambda *a, **k: Resp(body))
        assert cli._bitget_rows("https://x") == want
    def boom(*a, **k):
        raise OSError("rete")
    monkeypatch.setattr(cli.urllib.request, "urlopen", boom)
    assert cli._bitget_rows("https://x") is None


def test_daily_trend_is_still_not_a_blocking_filter(sandbox, monkeypatch):
    cli_, d = sandbox
    # 4h rialzista, 1d ribassista: il LONG delle regole si apre comunque (politica fase 2 invariata)
    state = {}
    _run(cli_, monkeypatch, state, [_proposal()],
         lambda now: {"4h": native_bars(now, H4, 400, 0.002), "1d": native_bars(now, D1, 300, -0.004)})
    assert list(cli_.make_account(state).positions) == ["ETH"]
    opened = [e for e in _learning(d) if e.get("ev") == "open"]
    assert opened[-1]["features"]["trend1d_state"] == "DOWN" and opened[-1]["features"]["trend4h_state"] == "UP"


def test_end_to_end_chain_fake_bitget_to_cycle(sandbox, monkeypatch):
    """Catena completa senza scorciatoie: 15m e 4H da /market/candles, 1Dutc da history-candles paginato, fetch_htf e
    read_symbol veri, ciclo vero. Il 1d arriva dalla paginazione, il 4h decide il gate, l'apertura registra entrambi."""
    from test_long_s25 import _cycle_candles, _with_new_hour
    cli_, d = sandbox
    cli_._HTF_CACHE.clear()
    a15, sig = _cycle_candles()
    a15b, now, _ = _with_new_hour(a15, sig)
    calls = []

    def candles(sym, bar="15m", limit=1000):
        calls.append(("candles", sym, bar))
        if sym != "ETH":
            return []
        return native_bars(now, H4, 500, 0.002).tolist() if bar == "4H" else a15b[-limit:].tolist()
    fb = FakeBitget(now, 400)
    monkeypatch.setattr(cli_, "fetch_candles", candles)
    monkeypatch.setattr(cli_, "fetch_history_page", lambda sym, gran, s, e: fb(sym, gran, s, e) if sym == "ETH" else [])
    monkeypatch.setattr(cli_, "apply_claude_schedule", lambda *args: False)
    monkeypatch.setattr(cli_, "rules_decisions", lambda *args, **kw: [_proposal()])
    monkeypatch.setattr(cli_, "PORTFOLIO", cli_._make_hawk_config())
    state = {}
    cli_.run_cycle(state, now)
    assert list(cli_.make_account(state).positions) == ["ETH"]
    f = [e for e in _learning(d) if e.get("ev") == "open"][-1]["features"]
    assert f["trend4h_state"] == "UP" and f["trend1d_state"] == "UP"
    assert cli_.HB["htf"]["ETH"]["4h"] == "ok" and cli_.HB["htf"]["ETH"]["1d"] == "ok"
    assert cli_.HB["htf"]["ETH"]["trend1d"] == "UP" and len(fb.calls) == 3
    # ciclo successivo nella stessa barra 4h e nello stesso giorno: nessuna nuova richiesta 4H ne' storica
    n4 = sum(1 for c in calls if c[2] == "4H")
    cli_.run_cycle(state, now + 60_000)
    assert sum(1 for c in calls if c[2] == "4H") == n4 and len(fb.calls) == 3
    cli_._HTF_CACHE.clear()
