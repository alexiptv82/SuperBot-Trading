"""Strumento di acquisizione delle candele: SOLO offline, con un finto endpoint Bitget (nessuna rete).

Si verifica: archivio attestabile e leggibile dal validatore, nessuna candela aperta, coerenza con la funzione di
scaricamento del runtime (altrimenti nessuna scrittura), nessuna sovrascrittura, nessuna rete senza conferma,
controllo incrociato con un secondo scaricamento.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("acquire_candles", ROOT / "ops/brain-unico/candles/acquire_candles.py")
AQ = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AQ)
CP = AQ.CP
GRAN_MS = {"15m": 900_000, "1H": 3_600_000, "4H": 14_400_000}
START = 1_780_000_000_000 // 14_400_000 * 14_400_000
END = START + 3 * 86_400_000


class FakeBitget:
    """Risponde come history-candles: righe [ts, o, h, l, c, baseVol, quoteVol] nella finestra, al massimo `limit`,
    le piu' recenti per prime; prezzo funzione dell'istante. ``bump``: candela da alterare (secondo scaricamento)."""

    def __init__(self, bump=None, missing=()):
        self.urls, self.bump, self.missing = [], bump, set(missing)

    def __call__(self, url):
        self.urls.append(url)
        q = parse_qs(urlsplit(url).query)
        step = GRAN_MS[q["granularity"][0]]
        lo, hi, limit = int(q["startTime"][0]), int(q["endTime"][0]), int(q["limit"][0])
        first = -(-lo // step) * step
        ts = list(range(first, hi + 1, step))[-limit:]
        rows = []
        for t in reversed(ts):
            if t in self.missing:
                continue
            c = 100 + (t // 900_000) % 17 / 10
            if self.bump == t:
                c += 0.05
            rows.append([str(t), "100.0", f"{max(100, c) + 0.3:.2f}", f"{min(100, c) - 0.3:.2f}", f"{c:.2f}",
                         "12.5", "1250"])
        return {"code": "00000", "data": rows}


def _acquire(out, now=END + 600_000, end=END, **kw):
    return AQ.acquire(str(out), start_ms=START, end_ms=end, get_json=kw.pop("get_json", FakeBitget()), now_ms=now,
                      symbols=("BTCUSDT", "ETHUSDT"), **kw)


def test_the_archive_is_attestable_and_readable_by_the_validator():
    out = Path(tempfile.mkdtemp()) / "arch"
    sha = _acquire(out)
    with open(out / CP.MANIFEST) as fh:
        mid = json.load(fh)["manifest_id"]
    r = CP.check(str(out), {mid: sha})
    assert (r["integrity"], r["provenance"]) == ("intact", "attested")
    sys.path.insert(0, str(ROOT / "ops/brain-unico/training"))
    try:
        import snapshot_verify as SV
    finally:
        sys.path.pop(0)
    dc = SV.DecisionCandles(str(out))
    assert set(dc.meta_ids) == {"15m", "1h", "4h"} and len(dc.bars("15m", "BTCUSDT")) == 3 * 96
    assert len(dc.bars("4h", "ETHUSDT")) == 3 * 6


def test_only_closed_candles_are_archived():
    out = Path(tempfile.mkdtemp()) / "arch"
    now = START + 86_400_000 + 450_000                       # a meta' di una candela da 15 m
    _acquire(out, now=now, end=now)
    ts = [json.loads(x)["t"] for x in (out / "15m" / "BTCUSDT.jsonl").read_text().splitlines()]
    assert max(ts) + 900_000 <= now and len(ts) == 96


def test_a_derivation_that_differs_from_the_runtime_writes_nothing(monkeypatch):
    monkeypatch.setattr(AQ.CP, "derive_rows", lambda *a, **k: {})
    out = Path(tempfile.mkdtemp()) / "arch"
    with pytest.raises(ValueError, match="derivation_differs_from_runtime"):
        _acquire(out)
    assert not out.exists()


def test_never_overwrite_an_existing_destination():
    out = Path(tempfile.mkdtemp())
    with pytest.raises(ValueError, match="destination_exists"):
        _acquire(out)


def test_without_confirmation_no_request_is_sent(monkeypatch, capsys):
    import backend.v3.lab_tools.fetch_candles as FC

    def boom(url):
        raise AssertionError("rete usata")
    monkeypatch.setattr(FC, "http_json", boom)
    out = Path(tempfile.mkdtemp()) / "arch"
    for extra in ([], ["--plan"], ["--plan", "--confirm-network"]):
        assert AQ.main(["--start", "2026-10-01", "--end", "2026-11-15", "--out", str(out)] + extra) == 0
    assert not out.exists() and "PLAN ONLY" in capsys.readouterr().out


def test_plan_estimates_are_bounded():
    p = AQ.plan(AQ._ms("2026-10-15"), AQ._ms("2026-12-01"))
    assert p["files"] == 24 and p["network"] is False
    # 47 giorni: 15m 4512 barre -> 24 richieste, 1h 1128 -> 7, 4h 282 -> 3; per 8 simboli = 272
    assert p["requests_estimate"] == 272 and p["rows_estimate"] == (4512 + 1128 + 282) * 8
    assert p["bytes_estimate"] == p["rows_estimate"] * 250 < 15_000_000


def test_a_second_download_is_compared_and_recorded():
    base = Path(tempfile.mkdtemp())
    _acquire(base / "a")
    _acquire(base / "b", compare_with=str(base / "a"))
    cc = json.loads((base / "b" / CP.MANIFEST).read_text())["cross_check"]
    assert cc["files_compared"] == 6 and cc["mismatches"] == 0 and cc["declared_only"] is True
    _acquire(base / "c", compare_with=str(base / "a"), get_json=FakeBitget(bump=START + 10 * 900_000))
    cc = json.loads((base / "c" / CP.MANIFEST).read_text())["cross_check"]
    assert cc["mismatches"] == 2                                     # la stessa candela per i due simboli


def test_requests_use_the_runtime_public_endpoint_only():
    fake = FakeBitget()
    _acquire(Path(tempfile.mkdtemp()) / "arch", get_json=fake)
    for u in fake.urls:
        parts = urlsplit(u)
        assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://api.bitget.com/api/v2/mix/market/history-candles"
        assert parse_qs(parts.query)["productType"] == ["USDT-FUTURES"]


# ------------------------------------------------------------------------------------------------ limiti rigidi

class Opener:
    """Finta rete per LimitedHttp: ``script`` = lista di esiti per tentativo ("ok", "net", 429, 404)."""

    def __init__(self, script, body=b'{"code":"00000","data":[]}'):
        self.script, self.body, self.calls = list(script), body, 0

    def __call__(self, url):
        import urllib.error
        self.calls += 1
        step = self.script.pop(0) if self.script else "ok"
        if step == "net":
            raise OSError("down")
        if isinstance(step, int):
            raise urllib.error.HTTPError(url, step, "x", {}, None)
        return self.body


def _http(script, max_attempts=350):
    return AQ.LimitedHttp(max_attempts=max_attempts, opener=Opener(script), sleep=lambda s: None, min_gap=0)


def test_every_attempt_counts_including_retries():
    h = _http(["net", 429, "ok"])
    assert h("u") == {"code": "00000", "data": []} and h.attempts == 3


def test_the_budget_stops_before_sending_the_next_attempt():
    h = _http(["net", "net", "net"], max_attempts=2)
    with pytest.raises(AQ.LimitExceeded, match="http_attempts_exceeded"):
        h("u")
    assert h.attempts == 2 and h._open.calls == 2


def test_a_non_retryable_error_is_not_retried_and_a_dead_source_gives_up():
    h = _http([404])
    with pytest.raises(Exception):
        h("u")
    assert h.attempts == 1
    h2 = _http(["net", "net", "net", "net"])
    with pytest.raises(RuntimeError, match="source_unavailable"):
        h2("u")
    assert h2.attempts == AQ.TRIES_PER_URL


class BudgetedFake(FakeBitget):
    def __init__(self, max_attempts):
        super().__init__()
        self.attempts, self.max_attempts = 0, max_attempts

    def __call__(self, url):
        if self.attempts >= self.max_attempts:
            raise AQ.LimitExceeded("http_attempts_exceeded")
        self.attempts += 1
        return super().__call__(url)


def _no_partial(base: Path):
    return not [p for p in base.iterdir() if ".partial-" in p.name]


def test_exceeding_the_attempt_budget_leaves_no_archive_only_a_report():
    base = Path(tempfile.mkdtemp())
    with pytest.raises(AQ.LimitExceeded):
        _acquire(base / "arch", get_json=BudgetedFake(5))
    assert not (base / "arch").exists() and _no_partial(base)
    rep = json.loads((base / "arch.ABORTED.json").read_text())
    assert rep["archive_written"] is False and rep["http_attempts"] == 5
    with pytest.raises(ValueError, match="destination_exists"):        # una sola acquisizione per destinazione
        _acquire(base / "arch")


def test_an_estimate_over_the_size_limit_is_refused_before_any_network():
    fake, base = FakeBitget(), Path(tempfile.mkdtemp())
    with pytest.raises(ValueError, match="archive_over_size_limit"):
        _acquire(base / "arch", get_json=fake, max_bytes=100_000)
    assert fake.urls == [] and not (base / "arch").exists()


def test_a_real_size_over_the_limit_leaves_no_archive(monkeypatch):
    monkeypatch.setattr(AQ, "ROW_BYTES", 1)                  # stima ottimista: il controllo vero e' sull'archivio
    monkeypatch.setattr(AQ, "RAW_BYTES", 1)
    base = Path(tempfile.mkdtemp())
    with pytest.raises(AQ.LimitExceeded, match="archive_over_size_limit"):
        _acquire(base / "arch", max_bytes=50_000)
    assert not (base / "arch").exists() and _no_partial(base) and (base / "arch.ABORTED.json").exists()


@pytest.mark.parametrize("kw, code", [
    (dict(end_ms=END + 1, now=END), "future_dates_not_allowed"),
    (dict(start_ms=END - 48 * 86_400_000), "period_over_47_days"),
    (dict(symbols=("BTCUSDT", "PEPEUSDT")), "symbol_not_authorized"),
    (dict(timeframes={"1m": 60_000}), "timeframe_not_authorized"),
])
def test_requests_outside_the_authorization_are_refused_before_any_network(kw, code):
    fake = FakeBitget()
    now = kw.pop("now", END + 600_000)
    args = dict(start_ms=START, end_ms=END, get_json=fake, now_ms=now, symbols=("BTCUSDT",))
    args.update(kw)
    base = Path(tempfile.mkdtemp())
    with pytest.raises(ValueError, match=code):
        AQ.acquire(str(base / "arch"), **args)
    assert fake.urls == [] and not (base / "arch").exists()


def test_missing_candles_are_documented_never_filled():
    gap = {START + k * 900_000 for k in range(10, 14)}
    out = Path(tempfile.mkdtemp()) / "arch"
    sha = _acquire(out, get_json=FakeBitget(missing=gap))
    m = json.loads((out / CP.MANIFEST).read_text())
    e = next(f for f in m["files"] if f["path"] == "15m/BTCUSDT.jsonl")
    assert (e["expected_rows"], e["rows"], e["missing_rows"]) == (288, 284, 4)
    assert set(e["missing_open_ms_sample"]) == gap
    assert CP.check(str(out), {m["manifest_id"]: sha})["provenance"] == "attested"


def test_the_47_day_plan_fits_the_authorization():
    p = AQ.plan(AQ._ms("2026-10-04"), AQ._ms("2026-11-20"))
    assert p["requests_estimate"] <= AQ.MAX_HTTP_ATTEMPTS and p["bytes_estimate"] <= AQ.MAX_BYTES


def test_the_limits_are_those_of_the_owner_authorization():
    assert (AQ.MAX_HTTP_ATTEMPTS, AQ.MAX_BYTES, AQ.MAX_DAYS) == (350, 100 * 1024 * 1024, 47)
    assert AQ.LimitedHttp().max_attempts == 350
    assert set(AQ.TIMEFRAMES) == {"15m", "1h", "4h"} and len(AQ.SYMBOLS) == 8
