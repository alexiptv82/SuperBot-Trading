"""RC84 fase 2C: continuita' esatta delle serie 4h/1d. Crypto 24/7: ogni barra segue la precedente di esattamente un
periodo. Metalli (XAU, XAG): ammesse solo le barre mancanti di sabato/domenica UTC. Mai barre inventate o interpolate:
una serie interrotta si accorcia alla coda continua e, se non bastano 200 barre, la tendenza e' UNKNOWN con il motivo."""
import os
import sys
import time

import numpy as np
import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from desk import signals as S  # noqa: E402
from test_desk_rc84_phase2 import NOW, H4, D1, native_bars, m15  # noqa: E402


def drop(bars, idx):
    keep = np.ones(len(bars), dtype=bool)
    keep[list(idx)] = False
    return bars[keep]


def weekend_idx(bars):
    return [i for i, t in enumerate(bars[:, 0]) if time.gmtime(t / 1000).tm_wday in (5, 6)]


@pytest.mark.parametrize("period,n", [(H4, 400), (D1, 300)])
def test_crypto_complete_series_is_valid(period, n):
    t = S.htf_trend(native_bars(NOW, period, n, 0.002), NOW, period)
    assert t["state"] == "UP" and t["gaps"] == 0 and t["bars"] == n and t["calendar"] == S.CALENDAR_CRYPTO


@pytest.mark.parametrize("period,n", [(H4, 400), (D1, 300)])
def test_crypto_one_missing_recent_bar_makes_the_trend_unknown_with_a_verifiable_reason(period, n):
    b = drop(native_bars(NOW, period, n, 0.002), [n - 50])           # una barra mancante 50 barre fa
    t = S.htf_trend(b, NOW, period)
    assert t["state"] == "UNKNOWN" and t["gaps"] == 1
    assert "storia insufficiente: 49 barre chiuse < 200" in t["why"]
    assert "serie interrotta: 1 barre mancanti dopo" in t["why"]


def test_crypto_old_gap_keeps_only_the_continuous_tail():
    b = drop(native_bars(NOW, H4, 600, 0.002), [100])               # buco 500 barre fa: coda di 499 >= 200
    t = S.htf_trend(b, NOW, H4)
    assert t["state"] == "UP" and t["bars"] == 499 and t["gaps"] == 1 and "dopo" in t["last_gap"]
    # nessuna barra inventata: il risultato coincide con quello della sola coda
    tail = native_bars(NOW, H4, 600, 0.002)[101:]
    assert S.htf_trend(tail, NOW, H4)["gap"] == t["gap"]


def test_crypto_weekend_missing_bars_are_a_real_gap():
    b = native_bars(NOW, D1, 300, 0.002)
    t = S.htf_trend(drop(b, weekend_idx(b[:-1])), NOW, D1)          # crypto non chiude nel weekend
    assert t["state"] == "UNKNOWN" and t["gaps"] > 0


@pytest.mark.parametrize("period,n", [(H4, 600), (D1, 360)])
def test_metals_weekend_closure_is_allowed_by_the_calendar(period, n):
    b = native_bars(NOW, period, n, 0.002)
    wk = [i for i in weekend_idx(b[:-1])]
    t = S.htf_trend(drop(b, wk), NOW, period, S.CALENDAR_WEEKEND)
    assert t["state"] == "UP" and t["gaps"] == 0 and t["calendar"] == S.CALENDAR_WEEKEND
    assert S.calendar_for("XAUUSDT") == S.calendar_for("XAG") == S.CALENDAR_WEEKEND
    assert S.calendar_for("BTC") == S.CALENDAR_CRYPTO


def test_metals_missing_weekday_bar_is_a_gap():
    b = native_bars(NOW, D1, 300, 0.002)
    weekday = [i for i, t in enumerate(b[:-1, 0]) if time.gmtime(t / 1000).tm_wday == 2][-2]    # un mercoledi' recente
    t = S.htf_trend(drop(b, weekend_idx(b[:-1]) + [weekday]), NOW, D1, S.CALENDAR_WEEKEND)
    assert t["state"] == "UNKNOWN" and t["gaps"] == 1 and "serie interrotta" in t["why"]


def test_identical_duplicates_are_merged_conflicting_duplicates_reject_the_series():
    b = native_bars(NOW, D1, 300, 0.002)
    dup = np.vstack([b, b[[10, 20]]])
    t = S.htf_trend(dup, NOW, D1)
    assert t["state"] == "UP" and t["bars"] == 300
    bad = b[20].copy()
    bad[4] *= 1.01
    t = S.htf_trend(np.vstack([b, bad]), NOW, D1)
    assert t["state"] == "UNKNOWN" and "duplicati in conflitto" in t["why"]


def test_irregular_intervals_and_unsorted_rows():
    b = native_bars(NOW, H4, 400, 0.002)
    shifted = b.copy()
    shifted[200, 0] += 3_600_000                                    # un'apertura fuori dalla griglia 4h
    t = S.htf_trend(shifted, NOW, H4)
    assert t["state"] == "UNKNOWN" and "non allineate" in t["why"]
    rng = np.random.default_rng(1)
    t = S.htf_trend(b[rng.permutation(len(b))], NOW, H4)           # ordine sparso: si ordina, nessuna perdita
    assert t["state"] == "UP" and t["bars"] == 400


def test_future_and_open_bars_are_never_used():
    b = native_bars(NOW, H4, 400, 0.002)
    future = b[-1].copy()
    future[0] += 10 * H4
    future[1:5] = 1.0
    t1 = S.htf_trend(np.vstack([b, future]), NOW, H4)
    t0 = S.htf_trend(b, NOW, H4)
    assert t1["state"] == t0["state"] == "UP" and t1["gap"] == t0["gap"] and t1["bars"] == 400


def test_read_symbol_uses_the_symbol_calendar_and_reports_it():
    b4 = native_bars(NOW, H4, 600, 0.002)
    b4w = drop(b4, weekend_idx(b4[:-1]))
    a = m15(NOW, 1000, 0.0)
    xau = S.read_symbol("XAU", a, NOW, bars_4h=b4w)
    btc = S.read_symbol("BTC", a, NOW, bars_4h=b4w)
    assert xau.facts["market_calendar"] == S.CALENDAR_WEEKEND and xau.facts["trend4h_state"] == "UP"
    assert btc.facts["market_calendar"] == S.CALENDAR_CRYPTO and btc.facts["trend4h_state"] == "UNKNOWN" and btc.side == 0
