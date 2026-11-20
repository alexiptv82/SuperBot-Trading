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

    def __init__(self, bump=None, missing=(), spill=False):
        self.urls, self.bump, self.missing, self.spill = [], bump, set(missing), spill

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
        if self.spill:          # come una fonte che restituisce anche una candela oltre endTime, con volume diverso
            t = (hi // step + 1) * step
            rows.insert(0, [str(t), "100.0", "100.5", "99.5", "100.0", "99.9", "1"])
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


def test_derivation_follows_the_runtime_even_when_the_source_spills_outside_the_request_window():
    """Caso dell'interruzione del 20/11 (ipotesi): la fonte restituisce candele fuori dalla finestra della richiesta.
    Il filtro per singola richiesta (vecchia regola) diverge dal runtime; il filtro sul periodo complessivo no."""
    from backend.v3.lab_tools.fetch_candles import fetch_rows
    fake = FakeBitget(spill=True)
    recorded = []

    def rec(url):
        body = fake(url)
        recorded.append((url, body))
        return body
    end = END // 900_000 * 900_000
    runtime = fetch_rows("BTCUSDT", START, end, candle_ms=900_000, get_json=rec)
    assert CP.derive_rows(recorded, 900_000, END + 600_000) != runtime                     # vecchia regola
    assert CP.derive_rows(recorded, 900_000, END + 600_000, (START, end)) == runtime       # regola del runtime
    out = Path(tempfile.mkdtemp()) / "arch"
    sha = _acquire(out, get_json=FakeBitget(spill=True))
    mid = json.loads((out / CP.MANIFEST).read_text())["manifest_id"]
    assert CP.check(str(out), {mid: sha})["provenance"] == "attested"


def test_a_divergence_is_explained_in_the_abort_report(monkeypatch):
    real = AQ.CP.derive_rows
    monkeypatch.setattr(AQ.CP, "derive_rows", lambda *a, **k: dict(list(real(*a, **k).items())[1:]))
    base = Path(tempfile.mkdtemp())
    with pytest.raises(ValueError):
        _acquire(base / "arch")
    rep = json.loads((base / "arch.ABORTED.json").read_text())
    assert "only_runtime=1" in rep["reason"] and "only_derived=0" in rep["reason"]


def test_attempt_outcomes_are_counted():
    h = _http(["net", 429, "ok"])
    h("u")
    assert h.outcomes == {"OSError": 1, "http_429": 1, "ok": 1}


# ------------------------------------------------------------------------------------------------ controllo preliminare

def test_probe_compares_both_rules_on_the_same_responses_within_3_attempts():
    rep_path = Path(tempfile.mkdtemp()) / "probe.json"
    r = AQ.probe(BudgetedFake(AQ.PROBE_MAX_ATTEMPTS), now_ms=END + 600_000, report_path=str(rep_path))
    assert r["ok"] is True and r["pages"] == 2 and r["runtime_rows"] == AQ.PROBE_BARS
    assert r["http_attempts"] == 2 and r["outside_request_window_count"] == 0 and r["old_per_request_rule_equal"]
    assert json.loads(rep_path.read_text())["ok"] is True


def test_probe_documents_rows_outside_the_request_window():
    fake = BudgetedFake(3)
    fake.spill = True
    r = AQ.probe(fake, now_ms=END + 600_000, report_path=str(Path(tempfile.mkdtemp()) / "p.json"))
    assert r["ok"] is True                                   # regola corrente = runtime
    assert r["old_per_request_rule_equal"] is False and r["outside_request_window_count"] >= 1
    o = r["outside_request_window"][0]
    assert o["side"] == "after_end" and o["open_ms"] > o["request_end"]
    assert r["old_rule_vs_runtime"]["different_values"]       # la candela "fuori finestra" sovrascrive nel runtime


def test_probe_never_exceeds_its_budget_and_still_reports():
    p = Path(tempfile.mkdtemp()) / "p.json"
    with pytest.raises(AQ.LimitExceeded):
        AQ.probe(BudgetedFake(1), now_ms=END + 600_000, report_path=str(p))
    rep = json.loads(p.read_text())
    assert rep["ok"] is False and rep["http_attempts"] == 1 and "LimitExceeded" in rep["error"]
    with pytest.raises(ValueError, match="report_exists"):
        AQ.probe(BudgetedFake(3), now_ms=END + 600_000, report_path=str(p))


def test_probe_and_budget_arguments_without_network(monkeypatch, capsys):
    import backend.v3.lab_tools.fetch_candles as FC
    monkeypatch.setattr(FC, "http_json", lambda url: (_ for _ in ()).throw(AssertionError("rete")))
    called = []
    monkeypatch.setattr(AQ, "LimitedHttp", lambda *a, **k: called.append(k) or (_ for _ in ()).throw(AssertionError))
    assert AQ.main(["--probe"]) == 0 and called == []                           # senza conferma: niente
    assert AQ.main(["--max-attempts", "351", "--probe"]) == 2
    assert AQ.main(["--start", "2026-10-04", "--end", "2026-11-20", "--out", "/nonexistent/x",
                    "--max-attempts", "100", "--plan"]) == 2                    # stima 272 > budget residuo
    assert "stima oltre i limiti" in capsys.readouterr().out


def test_with_close_time_selection_the_archive_has_no_missing_last_candle():
    """Bitget reale seleziona per chiusura: con le finestre corrette nessuna candela manca (prima: l'ultima di ogni file)."""
    class CloseTimeBitget(FakeBitget):
        def __call__(self, url):
            q = parse_qs(urlsplit(url).query)
            step = GRAN_MS[q["granularity"][0]]
            lo, hi = int(q["startTime"][0]), int(q["endTime"][0])
            shifted = url.replace(f"startTime={lo}", f"startTime={lo - step}").replace(f"endTime={hi}", f"endTime={hi - step}")
            return super().__call__(shifted)
    out = Path(tempfile.mkdtemp()) / "arch"
    _acquire(out, get_json=CloseTimeBitget())
    m = json.loads((out / CP.MANIFEST).read_text())
    assert all(f["missing_rows"] == 0 for f in m["files"]), [(f["path"], f["missing_rows"]) for f in m["files"]]
