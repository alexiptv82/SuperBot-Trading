"""RC84 hardening finale: duplicati lungo tutta la catena Bitget -> recupero -> cache -> unione -> indicatori -> decisione.

Duplicati identici (bordi delle pagine, righe ripetute) si uniscono; lo stesso timestamp con valori diversi (nella stessa
risposta, fra pagine diverse, fra cache e Bitget) non viene mai risolto scegliendo una riga: la serie arriva a signals con
le due versioni, la tendenza e' UNKNOWN con il motivo, la cache si svuota e nessuna nuova apertura si basa su quella serie.
"""
import json
import os
import sys

import numpy as np

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from desk import signals as S  # noqa: E402
from test_desk_rc84_phase2 import NOW, H4, D1, native_bars, m15, _proposal, _learning  # noqa: E402
from test_desk_rc84_phase2b import FakeBitget, cli  # noqa: E402,F401
from test_long_s25 import sandbox, _cycle_candles, _with_new_hour  # noqa: E402,F401


def _conflict(rows, i, factor=1.01):
    bad = list(rows[i])
    bad[4] *= factor
    return bad


# --------------------------------------------------------------------------------------------- unita' della catena
def test_identical_duplicates_from_different_pages_are_merged_and_the_series_is_valid(cli):
    fb = FakeBitget(NOW, 400)                                 # bordi inclusi + 2 duplicati esatti per pagina
    out = cli.fetch_daily_history("BTC", NOW, fb)
    assert out["status"] == "ok" and len(out["arr"]) == 267
    t = S.htf_trend(out["arr"], NOW, D1)
    assert t["state"] == "UP"


def test_conflict_between_two_pages_is_not_resolved_and_the_daily_trend_is_unknown(cli):
    fb = FakeBitget(NOW, 400)
    boundary = NOW - NOW % D1 - 89 * D1                       # giorno condiviso fra la pagina 1 e la pagina 2
    orig = fb.__call__

    def page(sym, gran, start, end):
        rows = orig(sym, gran, start, end)
        if len(fb.calls) == 2:                                # la seconda pagina riporta lo stesso giorno diverso
            rows = [(_conflict([r], 0) if r[0] == boundary else r) for r in rows]
        return rows
    out = cli.fetch_daily_history("BTC", NOW, page)
    assert out["status"] == "conflitto_dati"
    assert cli._HTF_CACHE[("BTC", "1d")]["arr"] is None        # niente in cache: si ricostruisce da capo dopo l'attesa
    t = S.htf_trend(out["arr"], NOW, D1)
    assert t["state"] == "UNKNOWN" and "duplicati in conflitto" in t["why"]
    n = len(fb.calls)
    assert cli.fetch_daily_history("BTC", NOW + 60_000, page)["status"] == "attesa_dopo_errore" and len(fb.calls) == n
    later = NOW + cli.HTF_RETRY_MS + 1
    fb2 = FakeBitget(later, 400)
    out = cli.fetch_daily_history("BTC", later, fb2)
    assert out["status"] == "ok" and len(fb2.calls) == 3 and S.htf_trend(out["arr"], later, D1)["state"] == "UP"


def test_conflict_between_cache_and_a_later_download_empties_the_cache(cli):
    cli.fetch_daily_history("ETH", NOW, FakeBitget(NOW, 400))
    nxt = NOW + D1
    fb = FakeBitget(nxt, 401, seed=99)                        # stessa date, prezzi diversi: Bitget "ha rivisto" i giorni
    out = cli.fetch_daily_history("ETH", nxt, fb)
    assert out["status"] == "conflitto_dati" and len(fb.calls) == 1
    assert cli._HTF_CACHE[("ETH", "1d")]["arr"] is None and cli._HTF_CACHE[("ETH", "1d")]["conflicts"] > 0
    assert S.htf_trend(out["arr"], nxt, D1)["state"] == "UNKNOWN"


def test_conflict_inside_one_4h_response_blocks_the_series(cli):
    rows = native_bars(NOW, H4, 400, 0.002).tolist()
    rows.append(_conflict(rows, 350))
    calls = []
    out = cli.fetch_htf("BTC", NOW, lambda s, g, l: (calls.append(g), rows)[1], FakeBitget(NOW, 400))
    assert out["status"]["4h"] == "conflitto_dati"
    r = S.read_symbol("BTC", m15(NOW, 1000, 0.0), NOW, bars_4h=out["4h"], bars_1d=out["1d"])
    assert r.facts["trend4h_state"] == "UNKNOWN" and "duplicati in conflitto" in r.facts["trend4h_why"] and r.side == 0
    cli.fetch_htf("BTC", NOW + 60_000, lambda s, g, l: (calls.append(g), rows)[1], FakeBitget(NOW, 400))
    assert calls == ["4H"]                                    # in attesa: nessuna nuova richiesta per 30 minuti


def test_identical_duplicates_inside_one_4h_response_are_harmless(cli):
    rows = native_bars(NOW, H4, 400, 0.002).tolist()
    rows += [list(rows[10]), list(rows[300])]
    out = cli.fetch_htf("BTC", NOW, lambda s, g, l: rows, FakeBitget(NOW, 400))
    assert out["status"]["4h"] == "ok" and len(out["4h"]) == 400
    assert S.htf_trend(out["4h"], NOW, H4)["state"] == "UP"


# --------------------------------------------------------------------------------------------- ciclo vero
def _cycle(cli_, monkeypatch, h4_rows, page=None):
    a15, sig = _cycle_candles()
    a15b, now, _ = _with_new_hour(a15, sig)
    monkeypatch.setattr(cli_, "fetch_candles",
                        lambda sym, bar="15m", limit=1000: (h4_rows(now) if bar == "4H" else a15b[-limit:].tolist())
                        if sym == "ETH" else [])
    monkeypatch.setattr(cli_, "fetch_history_page", page or FakeBitget(now, 400))
    monkeypatch.setattr(cli_, "apply_claude_schedule", lambda *args: False)
    monkeypatch.setattr(cli_, "rules_decisions", lambda *args, **kw: [_proposal()])
    monkeypatch.setattr(cli_, "PORTFOLIO", cli_._make_hawk_config())
    return now


def test_cycle_with_a_conflicting_4h_series_opens_nothing_and_says_why(sandbox, monkeypatch, capsys):
    cli_, d = sandbox

    def h4(now):
        rows = native_bars(now, H4, 500, 0.002).tolist()
        return rows + [_conflict(rows, 480)]
    now = _cycle(cli_, monkeypatch, h4)
    state = {}
    cli_.run_cycle(state, now)
    assert cli_.make_account(state).positions == {}
    out = capsys.readouterr().out
    assert "[TREND_UNKNOWN] ETH" in out and "duplicati in conflitto" in out
    assert cli_.HB["htf"]["ETH"]["4h"] == "conflitto_dati"
    assert any(e.get("ev") == "candidate" and e.get("status") == "trend_sconosciuto" for e in _learning(d))


def test_cycle_with_identical_duplicates_opens_normally(sandbox, monkeypatch):
    cli_, d = sandbox

    def h4(now):
        rows = native_bars(now, H4, 500, 0.002).tolist()
        return rows + [list(rows[100]), list(rows[499])]
    now = _cycle(cli_, monkeypatch, h4)
    state = {}
    cli_.run_cycle(state, now)
    assert list(cli_.make_account(state).positions) == ["ETH"]


def test_cycle_with_a_conflicting_daily_series_keeps_the_phase2_policy(sandbox, monkeypatch):
    """Il 1d non autorizza mai aperture (0 punti, nessun gate): con un conflitto e' UNKNOWN e non viene usato; la
    decisione dipende solo dal 4h valido, esattamente come con un 1d mancante."""
    cli_, d = sandbox
    calls = {"n": 0}

    def page(sym, gran, start, end):
        calls["n"] += 1
        rows = [r for r in native_bars(now_box[0], D1, 400, 0.002).tolist() if start <= r[0] <= end]
        return rows + ([_conflict(rows, 0)] if calls["n"] == 2 and rows else [])
    now_box = [0]
    now = _cycle(cli_, monkeypatch, lambda n: native_bars(n, H4, 500, 0.002).tolist(), page)
    now_box[0] = now
    state = {}
    cli_.run_cycle(state, now)
    assert list(cli_.make_account(state).positions) == ["ETH"]
    f = [e for e in _learning(d) if e.get("ev") == "open"][-1]["features"]
    assert f["trend4h_state"] == "UP" and f["trend1d_state"] == "UNKNOWN"
    assert cli_.HB["htf"]["ETH"]["1d"] == "conflitto_dati"


# --------------------------------------------------------------------------------------------- validazione finale
def test_ema200_4h_and_1d_match_an_independent_reference():
    import pandas as pd
    for period, n in ((H4, 400), (D1, 300)):
        b = native_bars(NOW, period, n, 0.001, seed=5)
        closed = b[:-1]                                         # l'ultima e' in formazione
        c = pd.Series(closed[:, 4])
        e50 = c.ewm(span=50, adjust=False).mean().iloc[-1]
        e200 = c.ewm(span=200, adjust=False).mean().iloc[-1]
        t = S.htf_trend(b, NOW, period)
        assert t["bars"] == n and abs(t["gap"] - round((e50 - e200) / e200, 6)) < 1e-9
        assert t["state"] == ("UP" if e50 > e200 else "DOWN")


def test_incomplete_4h_and_15m_candles_cannot_flip_the_reading():
    a = m15(NOW, 1000, 0.0, seed=8)
    b4 = native_bars(NOW, H4, 400, -0.002)                      # tendenza 4h chiusa ribassista
    base = S.read_symbol("BTC", a, NOW, bars_4h=b4)
    b4x, ax = b4.copy(), a.copy()
    b4x[-1, 1:5] = [b4[-2, 4], b4[-2, 4] * 3, b4[-2, 4], b4[-2, 4] * 3]   # barra 4h in formazione: +200%
    ax[-1, 2] = ax[-1, 4] = a[:-1, 2].max() * 1.10                          # 15m in formazione oltre ogni massimo
    r = S.read_symbol("BTC", ax, NOW, bars_4h=b4x)
    assert base.facts["trend4h_state"] == r.facts["trend4h_state"] == "DOWN"
    assert (r.long_score, r.short_score, r.side) == (base.long_score, base.short_score, base.side)


def test_no_duplicate_exposure_same_signal_twice_and_no_toro_clone(sandbox, monkeypatch):
    cli_, d = sandbox
    now = _cycle(cli_, monkeypatch, lambda n: native_bars(n, H4, 500, 0.002).tolist())
    state = {}
    cli_.run_cycle(state, now)
    cli_.run_cycle(state, now + 11 * 60_000)                    # stesso segnale al ciclo dopo, oltre il cooldown scalp
    acc = cli_.make_account(state)
    assert list(acc.positions) == ["ETH"] and acc.positions["ETH"].dca_count == 0
    assert len([e for e in _learning(d) if e.get("ev") == "open"]) == 1
    monkeypatch.setattr(cli_, "PORTFOLIO", cli_._make_bull_config())
    bull = {}
    cli_.run_cycle(bull, now)                                   # stesso segnale delle regole su Toro: nessun clone
    assert cli_.make_account(bull).positions == {}
