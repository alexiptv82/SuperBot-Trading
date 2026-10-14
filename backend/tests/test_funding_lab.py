"""Test del laboratorio funding: nessuna rete, dati sintetici."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crosssec_lab as cs  # noqa: E402
import funding_lab as fl  # noqa: E402
import strategy_lab as sl  # noqa: E402

D1 = fl.D1
H8 = 8 * 3_600_000


class FakeClient:
    """Pagine di 'limit' record, dalla piu' recente; ignora pageNo se ignore_page=True."""
    def __init__(self, n_records, ignore_page=False, end=sl.ms(2026, 10, 1)):
        self.recs = [{"timestamp": end - i * H8, "fundingRate": 1e-4 * ((i % 5) + 1)} for i in range(n_records)]
        self.ignore = ignore_page
        self.calls = 0

    def fetch_funding_rate_history(self, symbol, limit=None, params=None):
        self.calls += 1
        page = 1 if self.ignore else int((params or {}).get("pageNo", 1))
        chunk = self.recs[(page - 1) * limit: page * limit]
        return list(reversed(chunk))                      # ccxt le restituisce in ordine crescente


def test_fetch_funding_collects_all_pages_and_stops(tmp_path):
    c = FakeClient(250)
    arr = fl.fetch_funding("AAA/USDT:USDT", sl.DATA_END, str(tmp_path), client=c)
    assert len(arr) == 250 and (np.diff(arr[:, 0]) > 0).all()
    assert c.calls == 4                                    # 3 pagine piene + una vuota
    arr2 = fl.fetch_funding("AAA/USDT:USDT", sl.DATA_END, str(tmp_path), client=FakeClient(1))
    assert len(arr2) == 250                                # seconda lettura dalla cache


def test_fetch_funding_stops_when_pages_repeat(tmp_path):
    c = FakeClient(500, ignore_page=True)                  # l'API ignora pageNo: stessa pagina sempre
    arr = fl.fetch_funding("BBB/USDT:USDT", sl.DATA_END, str(tmp_path), client=c)
    assert len(arr) == 100 and c.calls == 2


def test_daily_funding_sums_per_utc_day():
    d0 = sl.ms(2024, 1, 1) // D1
    recs = np.array([[sl.ms(2024, 1, 1) + k * H8, 1e-4] for k in range(6)])   # 3 al giorno per 2 giorni
    F = fl.daily_funding({"A": recs}, ["A", "B"], d0, 4)
    assert np.allclose(F[:2, 0], 3e-4) and np.isnan(F[2:, 0]).all() and np.isnan(F[:, 1]).all()


def panel(n_syms=20, n_days=140, seed=0):
    d0 = sl.ms(2023, 1, 2) // D1                           # lunedi'
    O = np.full((n_days, n_syms), 100.0)
    F = np.tile(1e-4 * (1 + np.arange(n_syms)), (n_days, 1)).astype(float)   # funding crescente con l'indice
    return O, F, d0


def test_short_the_high_funding_and_collect_it():
    O, F, d0 = panel()
    rows = fl.funding_rows(O, F, d0, 7)
    series = fl.run_funding(rows)
    k = max(3, round(0.2 * 20))
    expected = (F[0, -k:].mean() - F[0, :k].mean()) * 7 * 1e4           # short (alto) incassa, long (basso) paga
    assert len(series) > 5
    assert abs(series[1]["fund"] - expected) < 1e-6 and abs(series[1]["price"]) < 1e-9
    w = rows[0][1]
    assert (w[:k] > 0).all() and (w[-k:] < 0).all()                     # long i piu' bassi, short i piu' alti


def test_weights_do_not_depend_on_funding_from_the_rebalance_day_onward():
    rng = np.random.default_rng(3)
    n_syms, n_days = 25, 200
    d0 = sl.ms(2023, 1, 2) // D1
    O = np.full((n_days, n_syms), 100.0)
    F = rng.normal(1e-4, 5e-5, (n_days, n_syms))
    rows = fl.funding_rows(O, F, d0, 30)
    day, w = rows[4][0], rows[4][1]
    d = day - d0
    F2 = F.copy()
    F2[d:] = rng.normal(5e-3, 1e-3, (n_days - d, n_syms))               # il futuro cambia radicalmente
    w2 = [r[1] for r in fl.funding_rows(O, F2, d0, 30) if r[0] == day][0]
    assert np.array_equal(w, w2)


def test_symbols_without_enough_funding_coverage_are_excluded():
    O, F, d0 = panel()
    F[:, 0] = np.nan                                                    # prima coppia senza funding
    rows = fl.funding_rows(O, F, d0, 7)
    assert all(r[1][0] == 0 for r in rows) and all(not r[3][0] for r in rows)


def test_adjusted_rows_charge_longs_and_credit_shorts():
    O, F, d0 = panel()
    rows = fl.funding_rows(O, F, d0, 7)
    adj = fl.adjusted_rows(rows)
    day, w, ret_adj, avail = adj[0]
    series = fl.run_funding(rows)
    spread = (w * np.where(np.isfinite(ret_adj), ret_adj, 0.0)).sum() * 1e4
    assert abs(spread - series[0]["gross"]) < 1e-6


def test_evaluate_requires_testable_periods_and_positive_funding():
    ok = {"weeks": 50, "A": 5.0, "fund": 3.0}
    pp = {"dev": ok, "val": ok, "test": ok}
    assert fl.evaluate(pp, 3.0, 0.005)["pass"]
    assert not fl.evaluate({"dev": None, "val": ok, "test": ok}, 3.0, 0.005)["pass"]
    assert not fl.evaluate({"dev": dict(ok, weeks=10), "val": ok, "test": ok}, 3.0, 0.005)["pass"]
    assert not fl.evaluate({"dev": dict(ok, fund=-1.0), "val": ok, "test": ok}, 3.0, 0.005)["pass"]
    assert not fl.evaluate(pp, 3.0, 0.5)["pass"]


def test_end_to_end_with_cached_synthetic_data(tmp_path):
    cache = str(tmp_path)
    syms = [f"S{i}/USDT:USDT" for i in range(16)]
    json.dump(syms, open(os.path.join(cache, "universe.json"), "w"))
    n = (sl.DATA_END - sl.DATA_START) // sl.H1
    for i, s in enumerate(syms):
        rng = np.random.default_rng(300 + i)
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
        o = np.r_[100.0, c[:-1]]
        t = sl.DATA_START + np.arange(n) * sl.H1
        name = s.split("/")[0]
        np.save(os.path.join(cache, f"{name}_1h_{sl.DATA_END}.npy"),
                np.column_stack([t, o, np.maximum(o, c), np.minimum(o, c), c, np.ones(n)]))
        ts = np.arange(sl.DATA_START, sl.DATA_END, H8)
        rate = rng.normal(1e-4, 5e-5, len(ts))
        np.save(os.path.join(cache, f"{name}_fund_{sl.DATA_END}.npy"), np.column_stack([ts, rate]))

    class A:
        pass
    a = A()
    a.cache_dir, a.out, a.top_n, a.workers, a.annotate = cache, os.path.join(cache, "o.json"), 80, 2, False
    a.source = "bitget"
    res = fl.run(a)
    assert set(res) == {"F7", "F30"}
    assert not any(r["checks"]["pass"] for r in res.values())          # funding casuale, prezzi casuali
    assert all(r["overall"]["weeks"] > 200 for r in res.values())


def test_parse_vision_csv_skips_header_and_bad_lines():
    text = "calc_time,funding_interval_hours,last_funding_rate\n1577836800000,8,-0.00012359\nxx,8,1\n1577865600000,8,0.0001\n"
    assert fl.parse_vision_csv(text) == [(1577836800000, -0.00012359), (1577865600000, 0.0001)]


def test_months_range_and_symbol_candidates():
    m = fl.months(sl.ms(2019, 10, 1), sl.ms(2020, 2, 15))
    assert m == ["2019-10", "2019-11", "2019-12", "2020-01", "2020-02"]
    assert fl.vision_candidates("PEPE/USDT:USDT") == ["PEPEUSDT", "1000PEPEUSDT"]


def test_fetch_funding_vision_uses_scaled_symbol_and_skips_missing_months(tmp_path):
    seen = []

    def getter(url):
        seen.append(url)
        if "/1000PEPEUSDT/" not in url:
            return None                                             # PEPEUSDT non esiste, 1000PEPEUSDT si'
        ym = url.rsplit("-fundingRate-", 1)[1][:7]
        if ym < "2023-05":
            return None                                             # non ancora quotato
        y, m = int(ym[:4]), int(ym[5:7])
        t0 = sl.ms(y, m, 1)
        return "calc_time,funding_interval_hours,last_funding_rate\n" + "\n".join(
            f"{t0 + k * 8 * 3_600_000},8,0.0001" for k in range(3))

    arr = fl.fetch_funding_vision("PEPE/USDT:USDT", sl.DATA_END, str(tmp_path), getter=getter)
    assert len(arr) == 3 * len(fl.months(sl.ms(2023, 5, 1), sl.DATA_END - 31 * 86_400_000))
    assert (np.diff(arr[:, 0]) > 0).all() and arr[0, 0] == sl.ms(2023, 5, 1)
    assert any("/PEPEUSDT/" in u for u in seen) and any("/1000PEPEUSDT/" in u for u in seen)
    absent = fl.fetch_funding_vision("ZZZ/USDT:USDT", sl.DATA_END, str(tmp_path), getter=lambda u: None)
    assert len(absent) == 0


def test_end_to_end_vision_source_drops_pairs_without_funding(tmp_path):
    cache = str(tmp_path)
    syms = [f"S{i}/USDT:USDT" for i in range(24)]
    json.dump(syms, open(os.path.join(cache, "universe.json"), "w"))
    n = (sl.DATA_END - sl.DATA_START) // sl.H1
    for i, s in enumerate(syms):
        rng = np.random.default_rng(500 + i)
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
        o = np.r_[100.0, c[:-1]]
        t = sl.DATA_START + np.arange(n) * sl.H1
        name = s.split("/")[0]
        np.save(os.path.join(cache, f"{name}_1h_{sl.DATA_END}.npy"),
                np.column_stack([t, o, np.maximum(o, c), np.minimum(o, c), c, np.ones(n)]))
        if i < 22:                                                  # due coppie senza funding su Binance
            ts = np.arange(sl.DATA_START, sl.DATA_END, H8)
            np.save(os.path.join(cache, f"{name}_fundvis_{sl.DATA_END}.npy"),
                    np.column_stack([ts, rng.normal(1e-4, 5e-5, len(ts))]))
        else:
            np.save(os.path.join(cache, f"{name}_fundvis_{sl.DATA_END}.npy"), np.zeros((0, 2)))

    class A:
        pass
    a = A()
    a.cache_dir, a.out, a.top_n, a.workers, a.annotate, a.source = cache, os.path.join(cache, "o.json"), 80, 2, False, "vision"
    res = fl.run(a)
    assert len(json.load(open(a.out))["symbols"]) == 22
    assert not any(r["checks"]["pass"] for r in res.values())
