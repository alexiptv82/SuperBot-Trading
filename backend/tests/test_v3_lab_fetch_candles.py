"""Caricatore delle candele del laboratorio: prove SENZA rete (get_json sostituito da una storia finta)."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
from decimal import Decimal as D

import pytest

from backend.v3.lab import run as R
from backend.v3.lab_tools import fetch_candles as FC

MS = 900_000
DAY = 86_400_000
NOW = (1_750_000_000_000 // MS) * MS + 123_456          # a meta' di una barra: quella in formazione apre a END


def history(first, last, holes=(), order="desc"):
    """{ts: [ts, o, h, l, c, vol, quote]} come stringhe, per le barre con first <= ts <= last (ogni MS), meno i buchi."""
    h = {}
    for ts in range(first, last + 1, MS):
        if ts in holes:
            continue
        k = (ts // MS) % 1000
        h[ts] = [str(ts), f"{100 + k}.10", f"{101 + k}.50", f"{99 + k}.05", f"{100 + k}.25", f"{k + 1}.5", "123"]
    return h, order


def stub(hist, order="desc", log=None):
    def get_json(url):
        q = dict(re.findall(r"(\w+)=([^&]+)", url.split("?", 1)[1]))
        if log is not None:
            log.append(url)
        lo, hi, lim = int(q["startTime"]), int(q["endTime"]), int(q["limit"])
        rows = [hist[t] for t in sorted(hist) if lo <= t <= hi]
        assert len(rows) <= lim, "la finestra chiede piu' righe del limite"
        if order == "desc":
            rows = rows[::-1]
        return {"code": "00000", "data": rows}
    return get_json


def test_fetch_collects_exactly_the_closed_bars_in_range_in_any_page_order_without_duplicates():
    end = (NOW // MS) * MS
    start = end - 3 * DAY
    hist, _ = history(start - 5 * MS, end + 2 * MS)          # la storia continua oltre i limiti: la barra in formazione e le altre fuori
    for order in ("desc", "asc"):
        rows = FC.fetch_rows("BTCUSDT", start, end, candle_ms=MS, get_json=stub(hist, order))
        assert sorted(rows) == list(range(start, end, MS))
        assert end not in rows and (start - MS) not in rows
        assert rows[start] == ("100.10"[:0] + hist[start][1], hist[start][2], hist[start][3], hist[start][4], hist[start][5])


def test_fetch_keeps_holes_and_never_interpolates():
    end = (NOW // MS) * MS
    start = end - 2 * DAY
    holes = {start + 7 * MS, start + 8 * MS, start + 150 * MS}
    hist, _ = history(start, end - MS, holes=holes)
    rows = FC.fetch_rows("ETHUSDT", start, end, candle_ms=MS, get_json=stub(hist))
    assert set(range(start, end, MS)) - set(rows) == holes


def test_fetch_stops_when_history_ends_and_does_not_loop():
    end = (NOW // MS) * MS
    start = end - 400 * DAY
    hist, _ = history(end - 3 * DAY, end - MS)                # storia di soli 3 giorni
    log = []
    rows = FC.fetch_rows("BTCUSDT", start, end, candle_ms=MS, get_json=stub(hist, log=log))
    assert sorted(rows) == list(range(end - 3 * DAY, end, MS))
    assert len(log) < 60                                       # 3 giorni = 2 finestre piene, poi 6 vuote: niente 192 richieste


def test_fetch_skips_malformed_rows_and_errors_codes():
    end = (NOW // MS) * MS
    start = end - 2 * MS
    good = [str(start), "1", "2", "0.5", "1.5", "7", "9"]
    bad = [["x", "1", "2", "3", "4", "5"], [str(start + MS), "NaN", "2", "3", "4", "5"], [str(start + MS)], "boh"]
    d = {"code": "00000", "data": [good, *bad]}
    rows = FC.fetch_rows("BTCUSDT", start, end, candle_ms=MS, get_json=lambda url: d)
    assert list(rows) == [start]
    rows = FC.fetch_rows("BTCUSDT", start, end, candle_ms=MS, get_json=lambda url: {"code": "40000", "msg": "no"})
    assert rows == {}
    for args in (("btc", start, end), ("BTC/USDT", start, end), ("BTCUSDT", end, start)):
        with pytest.raises(ValueError):
            FC.fetch_rows(*args, candle_ms=MS, get_json=lambda url: d)


def test_csv_is_read_back_by_the_lab_reader_with_exact_strings(tmp_path):
    end = (NOW // MS) * MS
    start = end - DAY
    hist, _ = history(start, end - MS, holes={start + 5 * MS})
    rows = FC.fetch_rows("BTCUSDT", start, end, candle_ms=MS, get_json=stub(hist))
    path = tmp_path / "BTCUSDT_15m.csv"
    sha = FC.write_csv(path, rows)
    assert sha == hashlib.sha256(path.read_bytes()).hexdigest()
    assert path.read_text().splitlines()[0] == "open_time_ms,open,high,low,close,volume"
    bars = R.read_candles_csv(path)
    assert [b.open_time_ms for b in bars] == sorted(rows)
    for b in bars:
        o, h, l, c, v = rows[b.open_time_ms]
        assert (b.open, b.high, b.low, b.close, b.volume) == (D(o), D(h), D(l), D(c), D(v))
    assert len(R.split_contiguous(bars, MS)) == 2                # il buco spezza la serie in due segmenti


def test_main_writes_files_and_meta_and_fails_when_too_few_bars(tmp_path):
    end = (NOW // MS) * MS
    full, _ = history(end - 5 * DAY - MS, end + MS)
    rc = FC.main(["--symbols", "BTCUSDT,ETHUSDT", "--days", "5", "--out-dir", str(tmp_path / "ok")], now_ms=NOW, get_json=stub(full))
    assert rc == 0
    meta = json.loads((tmp_path / "ok" / "fetch_meta.json").read_text())
    assert meta["BTCUSDT"]["n_bars"] == 5 * 96 == meta["BTCUSDT"]["expected_bars"] and meta["BTCUSDT"]["n_missing_bars"] == 0
    assert meta["BTCUSDT"]["sha256"] == hashlib.sha256((tmp_path / "ok" / "BTCUSDT_15m.csv").read_bytes()).hexdigest()
    assert meta["_run"]["end_ms"] == end and meta["_run"]["fetched_at_utc"].endswith("Z")
    sparse, _ = history(end - 5 * DAY, end - MS, holes={t for t in range(end - 5 * DAY, end, MS) if (t // MS) % 2})
    rc = FC.main(["--symbols", "BTCUSDT", "--days", "5", "--out-dir", str(tmp_path / "bad")], now_ms=NOW, get_json=stub(sparse))
    assert rc == 1                                                 # meta' delle barre: non si prosegue in silenzio


def test_http_json_retries_transient_errors_and_not_client_errors(monkeypatch):
    monkeypatch.setattr(FC.time, "sleep", lambda s: None)
    calls = {"n": 0}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"code":"00000","data":[]}'

    def flaky(req, timeout):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise urllib.error.HTTPError(req.full_url, 429, "slow down", {}, None)
        return Resp()

    monkeypatch.setattr(FC.urllib.request, "urlopen", flaky)
    assert FC.http_json("https://x.test/a", min_gap=0)["code"] == "00000" and calls["n"] == 3

    def refused(req, timeout):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, None)

    calls["n"] = 0
    monkeypatch.setattr(FC.urllib.request, "urlopen", refused)
    with pytest.raises(urllib.error.HTTPError):
        FC.http_json("https://x.test/a", min_gap=0)
    assert calls["n"] == 1
