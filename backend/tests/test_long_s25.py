"""Test della strategia long S25 (EMA9 + VWAP giornaliero, candele da 1 ora) per Falco e Toro.

Gruppi: (1) indicatori contro vettori generati dalle definizioni V3; (2) candele da 1 ora; (3) regola del segnale e
dell'ingresso; (4) filtro `protect`; (5) `step` su un conto vero (tempo massimo, pausa, tetti, riavvio);
(6) non regressione: file del motore classico invariati e modulo mai caricato a interruttore spento;
(7) ciclo completo simulato con `cli.run_cycle`.

Valori di prova tutti distinti: un errore di segno o di scambio fra due valori cambia un risultato.
"""
import hashlib
import json
import os
import sys
import tempfile
from types import SimpleNamespace

import numpy as np
import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.environ.setdefault("DESK_MACRO_FETCH", "0")

from desk import long_s25 as L  # noqa: E402
from desk.engine import Limits, PaperAccount  # noqa: E402

H1, M15, DAY = 3_600_000, 900_000, 86_400_000
FIX = os.path.join(BACKEND, "tests", "fixtures", "s25_v3_golden.json")


# ------------------------------------------------------------------------------------------------ utilita'
def hours(prev_closes, day_closes, vol=100.0, wick=0.1, day=40):
    """Barre da 1 ora contigue: i giorni precedenti finiscono alle 00:00 UTC del giorno `day`, il resto segue."""
    allc = list(prev_closes) + list(day_closes)
    t0 = day * DAY - len(prev_closes) * H1
    rows, o = [], allc[0]
    for i, c in enumerate(allc):
        rows.append([t0 + i * H1, o, max(o, c) + wick, min(o, c) - wick, c, vol])
        o = c
    return np.array(rows, dtype=float)


def cross_series(vol_last=100.0):
    """Giorno precedente in calo 100 -> 90, oggi 12 ore in lieve discesa e poi un rialzo: la EMA9 incrocia il VWAP
    verso l'alto proprio sull'ultima barra. Il test sotto verifica le precondizioni sui numeri veri."""
    prev = list(np.linspace(100.0, 90.0, 24))
    today = [90.0 - 0.1 * i for i in range(12)] + [90.0 - 0.1 * 12 + 2.0]
    h = hours(prev, today)
    h[-1, 5] = vol_last
    return h


def to_15m(h1):
    """Ogni barra da 1 ora diventa 4 barre da 15 minuti coerenti (massimo/minimo nelle barre 2 e 3)."""
    rows = []
    for t, o, hi, lo, c, v in h1:
        q = [o, o + (c - o) * 0.4, o + (c - o) * 0.7, c]
        for k in range(4):
            a = o if k == 0 else q[k - 1]
            b = q[k]
            top = hi if k == 1 else max(a, b)
            bot = lo if k == 2 else min(a, b)
            rows.append([t + k * M15, a, max(top, a, b), min(bot, a, b), b, v / 4])
    return np.array(rows, dtype=float)


def port(name="hawk"):
    # i valori "forzati" del portafoglio NON devono contare: S25 usa i propri (MARGIN, leva dalla forbice)
    return SimpleNamespace(name=name, guardrail_margin_forced=1.0, guardrail_lev_forced=1, limits=Limits())


class Rec:
    def __init__(self):
        self.closed, self.opened, self.notes_c, self.events = [], [], [], []

    def record_close(self, state, rec):
        self.closed.append(rec)

    def notify_open(self, *a):
        self.opened.append(a)

    def notify_close(self, *a):
        self.notes_c.append(a)

    def log_event(self, ev):
        self.events.append(ev)


def run_step(acc, state, cmap, prices, now, portfolio=None, halt="", drain=False, rec=None):
    rec = rec or Rec()
    out = L.step(acc, state, cmap, prices, now, portfolio or port(), halt=halt, drain=drain,
                 record_close=rec.record_close, notify_open=rec.notify_open, notify_close=rec.notify_close,
                 log_event=rec.log_event, echo=lambda s: None)
    return out, rec


# ------------------------------------------------------------------------------------ (1) indicatori
def _golden():
    with open(FIX) as f:
        return json.load(f)["cases"]


@pytest.mark.parametrize("case", _golden(), ids=lambda c: c["name"])
def test_indicators_match_v3_golden_vectors(case):
    h = np.array(case["bars"], dtype=float)
    for got, want in ((L.ema(h[:, 4], 9), case["ema9"]), (L.atr(h), case["atr14"]), (L.vwap_day(h), case["vwap"])):
        want = np.array([np.nan if x is None else x for x in want], dtype=float)
        assert np.array_equal(np.isnan(got), np.isnan(want))
        ok = ~np.isnan(want)
        assert np.allclose(got[ok], want[ok], rtol=1e-9, atol=0)


def test_ema_is_undefined_before_period_and_seeded_with_first_value():
    e = L.ema(np.array([10.0, 20.0, 30.0]), 3)
    assert np.isnan(e[0]) and np.isnan(e[1])
    assert e[2] == pytest.approx(0.5 * 30.0 + 0.5 * (0.5 * 20.0 + 0.5 * 10.0))   # alpha = 2/(3+1)


def test_atr_first_true_range_is_high_minus_low_and_uses_previous_close():
    h = np.array([[0, 10, 12, 9, 11, 1], [H1, 11, 15, 10, 14, 1], [2 * H1, 14, 14.5, 13, 13.5, 1]], dtype=float)
    a = L.atr(h, 2)
    # TR = [3, max(5, |15-11|, |10-11|)=5, max(1.5, |14.5-14|, |13-14|)=1.5]; RMA(2) seeded 3 -> 4 -> 2.75
    assert np.isnan(a[0])
    assert a[1] == pytest.approx(4.0) and a[2] == pytest.approx(2.75)


def test_vwap_resets_at_midnight_and_weights_typical_price_by_volume():
    t0 = 7 * DAY
    h = np.array([[t0 + 22 * H1, 10, 12, 8, 10, 1.0], [t0 + 23 * H1, 10, 13, 9, 11, 3.0],
                  [t0 + 24 * H1, 20, 23, 17, 20, 2.0], [t0 + 25 * H1, 20, 22, 20, 21, 6.0]], dtype=float)
    v = L.vwap_day(h)
    assert np.isnan(v[0]) and np.isnan(v[1])                   # prima sessione incompleta
    assert v[2] == pytest.approx((23 + 17 + 20) / 3)
    tp3 = (22 + 20 + 21) / 3
    assert v[3] == pytest.approx((20 * 2.0 + tp3 * 6.0) / 8.0)


def test_vwap_is_none_while_cumulative_volume_is_zero():
    t0 = 3 * DAY
    h = np.array([[t0, 10, 11, 9, 10, 0.0], [t0 + H1, 10, 12, 8, 11, 0.0], [t0 + 2 * H1, 11, 14, 10, 12, 5.0]],
                 dtype=float)
    v = L.vwap_day(h)
    assert np.isnan(v[0]) and np.isnan(v[1])
    assert v[2] == pytest.approx((14 + 10 + 12) / 3)


# ------------------------------------------------------------------------------------ (2) candele da 1 ora
def test_closed_hours_drops_the_forming_hour_and_the_forming_quarter():
    h = cross_series()
    a = to_15m(h)
    now_exact = int(a[-1, 0]) + M15 + 20_000            # subito dopo la chiusura dell'ultimo quarto
    assert len(L.closed_hours(a, now_exact)) == len(h)
    now_mid = int(a[-1, 0]) + 20_000                    # l'ultimo quarto e' ancora in formazione
    got = L.closed_hours(a, now_mid)
    assert len(got) == len(h) - 1 and got[-1, 0] == h[-2, 0]


def test_closed_hours_aggregates_ohlcv_correctly():
    t = 5 * DAY
    a = np.array([[t, 10, 11, 9.5, 10.5, 1], [t + M15, 10.5, 14, 10, 12, 2],
                  [t + 2 * M15, 12, 12.5, 7, 8, 3], [t + 3 * M15, 8, 9, 7.5, 8.7, 4]], dtype=float)
    g = L.closed_hours(a, t + H1)
    assert g.shape == (1, 6)
    assert list(g[0]) == [t, 10, 14, 7, 8.7, 10]


def test_closed_hours_skips_incomplete_hours_and_keeps_only_the_latest_contiguous_run():
    h = to_15m(hours([], [1.0 + i * 0.01 for i in range(10)], day=3))
    h = np.delete(h, 17, axis=0)                        # buco dentro l'ora numero 4
    got = L.closed_hours(h, int(h[-1, 0]) + M15)
    assert list(got[:, 0]) == [h[i, 0] for i in range(20, len(h), 4)] or len(got) == 5
    assert len(got) == 5                                # ore 5..9: solo la coda contigua
    assert np.all(np.diff(got[:, 0]) == H1)


def test_closed_hours_discards_bad_rows_and_handles_empty_or_malformed_input():
    assert L.closed_hours(np.empty((0, 6)), 10**13).shape == (0, 6)
    assert L.closed_hours(None, 10**13).shape == (0, 6)
    assert L.closed_hours(np.ones((4, 3)), 10**13).shape == (0, 6)
    a = to_15m(hours([], [100.0, 101.0], day=3))
    bad = a.copy()
    bad[2, 4] = np.nan
    assert len(L.closed_hours(bad, int(bad[-1, 0]) + M15)) == 1
    bad = a.copy()
    bad[1, 3] = 0.0
    assert len(L.closed_hours(bad, int(bad[-1, 0]) + M15)) == 1
    bad = a.copy()
    bad[1, 5] = -1.0
    assert len(L.closed_hours(bad, int(bad[-1, 0]) + M15)) == 1


def test_closed_hours_includes_a_quarter_closing_exactly_now_but_not_one_millisecond_later():
    a = to_15m(hours([], [100.0, 101.0], day=3))
    end = int(a[-1, 0]) + M15
    assert len(L.closed_hours(a, end)) == 2
    assert len(L.closed_hours(a, end - 1)) == 1


def test_closed_hours_keeps_an_hour_whose_quarter_has_zero_volume():
    a = to_15m(hours([], [100.0, 101.0], day=3))
    a[1, 5] = 0.0
    g = L.closed_hours(a, int(a[-1, 0]) + M15)
    assert len(g) == 2 and g[0, 5] == pytest.approx(a[0:4, 5].sum())


def test_closed_hours_sorts_unordered_input():
    a = to_15m(hours([], [100.0, 101.0, 102.0], day=3))
    shuffled = a[::-1].copy()
    assert np.array_equal(L.closed_hours(shuffled, int(a[-1, 0]) + M15), L.closed_hours(a, int(a[-1, 0]) + M15))


# ------------------------------------------------------------------------------------ (3) segnale e ingresso
def test_cross_series_preconditions_hold_on_real_numbers():
    h = cross_series()
    e, v = L.ema(h[:, 4], 9), L.vwap_day(h)
    assert e[-2] <= v[-2] and e[-1] > v[-1] and h[-1, 4] > e[-1]


def test_signal_fires_on_cross_with_close_above_both():
    h = cross_series()
    s = L.signal(h)
    assert s is not None
    e, v, a = L.ema(h[:, 4], 9), L.vwap_day(h), L.atr(h)
    assert s["signal_open_ms"] == int(h[-1, 0]) and s["trigger"] == h[-1, 2]
    assert s["ema9"] == e[-1] and s["vwap"] == v[-1] and s["atr"] == a[-1] and s["close"] == h[-1, 4]


def test_signal_needs_a_cross_not_just_ema_above_vwap():
    h = cross_series()
    h2 = hours(list(h[:-1, 4]), [h[-1, 4] + 0.5])        # una barra in piu': EMA gia' sopra il VWAP, nessun incrocio
    h2 = np.vstack([h, [h[-1, 0] + H1, h[-1, 4], h[-1, 4] + 1.0, h[-1, 4] - 0.1, h[-1, 4] + 0.6, 100.0]])
    e, v = L.ema(h2[:, 4], 9), L.vwap_day(h2)
    assert e[-2] > v[-2] and e[-1] > v[-1] and h2[-1, 4] > e[-1]
    assert L.signal(h2) is None


def test_signal_needs_close_above_ema():
    lo = cross_series()
    # ultima barra: chiusura appena sotto la EMA, ma un minimo molto basso con volume enorme trascina il VWAP sotto la EMA
    lo[-1, 1:5] = [89.4, 89.5, 80.0, 89.3]
    lo[-1, 5] = 1000.0
    e, v = L.ema(lo[:, 4], 9), L.vwap_day(lo)
    assert e[-2] <= v[-2] and e[-1] > v[-1] and lo[-1, 4] < e[-1]
    assert L.signal(lo) is None


def test_signal_needs_positive_volume_on_the_signal_bar():
    assert L.signal(cross_series(vol_last=0.0)) is None
    assert L.signal(cross_series(vol_last=0.001)) is not None


def test_signal_needs_enough_bars_and_finite_indicators():
    h = cross_series()
    assert L.signal(h[-(L.MIN_HOURS - 1):]) is None
    nanb = h.copy()
    nanb[-1, 3] = np.nan
    assert L.signal(nanb) is None


def test_signal_requires_a_defined_vwap_so_a_partial_first_day_gives_none():
    h = hours([], [90.0 - 0.1 * i for i in range(11)] + [92.0], day=40)
    h[:, 0] += 5 * H1                                    # la serie parte alle 05:00: sessione incompleta
    assert L.signal(h) is None


SIG = {"signal_open_ms": 10 * H1, "trigger": 100.0, "ema9": 99.0, "vwap": 98.5, "atr": 2.0, "close": 99.8}
NOW_IN = 11 * H1 + 20_000                                 # dentro l'ora successiva alla barra di segnale


def test_entry_plan_levels_and_window():
    plan, why = L.entry_plan(SIG, 100.4, NOW_IN)
    assert why == "ok"
    assert plan["sl"] == pytest.approx(100.4 - 1.5 * 2.0) and plan["tp"] == pytest.approx(100.4 + 1.5 * 2.0)
    assert L.entry_plan(SIG, 100.4, 11 * H1)[1] == "ok"                  # primo istante utile
    assert L.entry_plan(SIG, 100.4, 11 * H1 - 1)[1] == "segnale_scaduto"  # la barra di segnale non e' chiusa
    assert L.entry_plan(SIG, 100.4, 12 * H1 - 1)[1] == "ok"
    assert L.entry_plan(SIG, 100.4, 12 * H1)[1] == "segnale_scaduto"


def test_entry_plan_needs_a_break_above_trigger_but_not_a_chase():
    assert L.entry_plan(SIG, 100.0, NOW_IN)[1] == "nessuna_rottura"
    assert L.entry_plan(SIG, 99.0, NOW_IN)[1] == "nessuna_rottura"
    assert L.entry_plan(SIG, 100.0 + 0.5 * 2.0, NOW_IN)[1] == "ok"       # esattamente 0,5 ATR: ammesso
    assert L.entry_plan(SIG, 100.0 + 0.5 * 2.0 + 0.001, NOW_IN)[1] == "troppo_lontano"


def test_entry_plan_rejects_invalid_price_and_non_positive_stop():
    assert L.entry_plan(SIG, float("nan"), NOW_IN)[1] == "prezzo_non_valido"
    assert L.entry_plan(SIG, 0.0, NOW_IN)[1] == "prezzo_non_valido"
    assert L.entry_plan(SIG, float("inf"), NOW_IN)[1] == "prezzo_non_valido"
    big_stop = dict(SIG, trigger=1.0, atr=1.0)
    assert L.entry_plan(big_stop, 1.2, NOW_IN)[1] == "stop_non_valido"   # 1,2 - 1,5 < 0
    zero_stop = dict(SIG, trigger=1.0, atr=1.0)
    assert L.entry_plan(zero_stop, 1.5, NOW_IN)[1] == "stop_non_valido"  # 1,5 - 1,5 = 0: stop non valido
    ok_stop = dict(SIG, trigger=1.0, atr=0.5)
    assert L.entry_plan(ok_stop, 1.2, NOW_IN)[1] == "ok"                 # 1,2 - 0,75 > 0


# ------------------------------------------------------------------------------------------ (4) protect
def _acc_with(*specs):
    acc = PaperAccount(Limits())
    for sym, src in specs:
        pos, msg = acc.open(sym, 1, 60.0, 15, 100.0, 99.0, 103.0, 1, {}, source=src)
        assert pos, msg
    return acc


def test_protect_removes_close_partial_and_dca_only_on_s25_positions():
    acc = _acc_with(("BTC", L.SOURCE), ("ETH", "rules"))
    decs = [{"symbol": "BTC", "action": "close"}, {"symbol": "BTC", "action": "partial_close"},
            {"symbol": "BTC", "action": "dca"}, {"symbol": "BTC", "action": "hold"},
            {"symbol": "ETH", "action": "close"}, {"symbol": "SOL", "action": "open_long"}]
    out = L.protect(decs, acc.positions)
    assert out == [{"symbol": "BTC", "action": "hold"}, {"symbol": "ETH", "action": "close"},
                   {"symbol": "SOL", "action": "open_long"}]


def test_protect_without_s25_positions_returns_decisions_unchanged():
    acc = _acc_with(("ETH", "rules"))
    decs = [{"symbol": "ETH", "action": "close"}]
    assert L.protect(decs, acc.positions) is decs


def test_enabled_only_with_exactly_one():
    assert L.enabled({"DESK_LONG_S25": "1"}) is True
    for v in ("0", "", "true", "yes", "2", " 1"):
        assert L.enabled({"DESK_LONG_S25": v}) is False
    assert L.enabled({}) is False


# ------------------------------------------------------------------------------------------- (5) step
H = cross_series()
A15 = to_15m(H)
NOW_STEP = int(H[-1, 0]) + H1 + 20_000                   # subito dopo la chiusura della barra di segnale
SIG_TRIGGER = float(H[-1, 2])
SIG_ATR = float(L.atr(H)[-1])


def world(extra=None):
    return {"ETH": A15.copy(), **(extra or {})}


def test_step_opens_long_with_expected_levels_and_records_it():
    acc, state = PaperAccount(Limits()), {}
    px = SIG_TRIGGER + 0.1 * SIG_ATR
    out, rec = run_step(acc, state, world(), {"ETH": px}, NOW_STEP)
    assert out["opened"] == ["ETH"]
    p = acc.positions["ETH"]
    assert p.side == 1 and p.source == L.SOURCE and p.leverage == 15 and p.total_margin == 100.0
    assert p.sl == pytest.approx(px - 1.5 * SIG_ATR) and p.tp == pytest.approx(px + 1.5 * SIG_ATR)
    assert p.trade_type == "medio" and p.open_ms == NOW_STEP
    assert state["last_open_ms"]["ETH"] == NOW_STEP
    assert len(rec.opened) == 1 and rec.opened[0][0] == "ETH" and rec.opened[0][7] == L.SOURCE
    ev = rec.events[0]
    assert ev["ev"] == "open" and ev["symbol"] == "ETH" and ev["side"] == 1 and ev["source"] == L.SOURCE
    assert ev["portfolio"] == "hawk" and ev["features"]["strategy"] == "S25"


def test_step_sizing_is_per_portfolio_from_the_users_values_not_the_forced_guardrail():
    acc = PaperAccount(Limits())
    run_step(acc, {}, world(), {"ETH": SIG_TRIGGER + 0.05}, NOW_STEP, portfolio=port("hawk"))
    assert acc.positions["ETH"].total_margin == 100.0 and acc.positions["ETH"].leverage == 15
    acc = PaperAccount(Limits())
    run_step(acc, {}, world(), {"ETH": SIG_TRIGGER + 0.05}, NOW_STEP, portfolio=port("bull"))
    assert acc.positions["ETH"].total_margin == 350.0 and acc.positions["ETH"].leverage == 15


def test_step_margin_never_exceeds_the_portfolio_trade_cap():
    p = port("bull")
    p.limits = Limits(max_margin_trade=120.0)
    acc = PaperAccount(Limits())
    run_step(acc, {}, world(), {"ETH": SIG_TRIGGER + 0.05}, NOW_STEP, portfolio=p)
    assert acc.positions["ETH"].total_margin == 120.0


def test_leverage_range_is_the_users_and_default_leverage_is_the_minimum():
    assert L.LEV_MIN == 15 and L.LEV_MAX == {"hawk": 35, "bull": 45} and L.MARGIN == {"hawk": 100.0, "bull": 350.0}
    assert L.leverage_for("hawk", SIG, 100.0) == 15 and L.leverage_for("bull", SIG, 100.0) == 15
    for name in ("hawk", "bull"):
        assert L.LEV_MIN <= L.leverage_for(name, SIG, 100.0) <= L.LEV_MAX[name]


def test_step_does_nothing_without_break_or_when_too_far():
    for px in (SIG_TRIGGER - 0.01, SIG_TRIGGER + 0.5 * SIG_ATR + 0.01):
        acc = PaperAccount(Limits())
        out, rec = run_step(acc, {}, world(), {"ETH": px}, NOW_STEP)
        assert not acc.positions and not out["opened"] and not rec.events


def test_step_does_not_enter_on_a_stale_signal():
    acc = PaperAccount(Limits())
    run_step(acc, {}, world(), {"ETH": SIG_TRIGGER + 0.05}, NOW_STEP + H1)
    assert not acc.positions


def test_step_respects_cooldown_after_restart_and_does_not_reenter():
    acc, state = PaperAccount(Limits()), {}
    run_step(acc, state, world(), {"ETH": SIG_TRIGGER + 0.05}, NOW_STEP)
    acc.close("ETH", SIG_TRIGGER, NOW_STEP + 2 * M15, "stop loss")
    out, _ = run_step(acc, state, world(), {"ETH": SIG_TRIGGER + 0.05}, NOW_STEP + 3 * M15)
    assert not acc.positions and out["skipped"]["ETH"] == "cooldown"
    out, _ = run_step(acc, {"last_open_ms": {"ETH": NOW_STEP - H1}}, world(), {"ETH": SIG_TRIGGER + 0.05},
                      NOW_STEP)
    assert "ETH" in acc.positions                           # cooldown scaduto: e' ancora dentro la finestra


def test_step_skips_symbols_with_open_positions():
    acc, state = PaperAccount(Limits()), {}
    acc.open("ETH", -1, 60.0, 15, SIG_TRIGGER, SIG_TRIGGER * 1.01, None, 1, {}, source="rules")
    out, _ = run_step(acc, state, world(), {"ETH": SIG_TRIGGER + 0.05}, NOW_STEP)
    assert list(acc.positions) == ["ETH"] and acc.positions["ETH"].side == -1 and not out["opened"]


def test_step_trades_gold_and_silver_like_any_other_symbol():
    assert L.EXCLUDED == frozenset()
    acc = PaperAccount(Limits())
    cmap = {"XAU": A15.copy(), "XAG": A15.copy()}
    out, rec = run_step(acc, {}, cmap, {"XAU": SIG_TRIGGER + 0.05, "XAG": SIG_TRIGGER + 0.05}, NOW_STEP)
    assert out["opened"] == ["XAU", "XAG"]
    assert all(p.source == L.SOURCE and p.leverage == 15 and p.total_margin == 100.0 for p in acc.positions.values())


def test_step_has_no_s25_specific_cap_and_uses_free_slots_up_to_the_engine_limit():
    names = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    cmap = {n: A15.copy() for n in names}
    px = {n: SIG_TRIGGER + 0.05 for n in names}
    acc = PaperAccount(Limits())
    out, _ = run_step(acc, {}, cmap, px, NOW_STEP, portfolio=port("hawk"))
    assert out["opened"] == names                              # piu' di 3: nessun tetto proprio di S25
    p = port("bull")
    p.limits = Limits(max_open=3)
    acc = PaperAccount(p.limits)
    out, _ = run_step(acc, {}, cmap, px, NOW_STEP, portfolio=p)
    assert out["opened"] == ["AAA", "BBB", "CCC"]              # il tetto e' quello del motore
    assert out["skipped"]["DDD"] == "rifiutata:troppe posizioni aperte" and "EEE" in out["skipped"]


def test_step_does_not_have_to_fill_every_slot():
    acc = PaperAccount(Limits())
    out, _ = run_step(acc, {}, {"ETH": A15.copy(), "SOL": to_15m(hours([], [100.0, 99.0, 98.0], day=3))},
                      {"ETH": SIG_TRIGGER + 0.05, "SOL": 98.0}, NOW_STEP)
    assert out["opened"] == ["ETH"] and list(acc.positions) == ["ETH"]


def test_step_other_positions_and_s25_positions_share_the_same_slots():
    acc = PaperAccount(Limits(max_open=3))
    for s in ("P1", "P2"):
        acc.open(s, -1, 60.0, 15, 100.0, 101.0, None, 1, {}, source="rules")
    out, _ = run_step(acc, {}, {"ETH": A15.copy(), "SOL": A15.copy()},
                      {"ETH": SIG_TRIGGER + 0.05, "SOL": SIG_TRIGGER + 0.05}, NOW_STEP, portfolio=port("hawk"))
    assert out["opened"] == ["ETH"] and out["skipped"]["SOL"].startswith("rifiutata:")


def test_step_unknown_portfolio_opens_nothing():
    acc = PaperAccount(Limits())
    out, _ = run_step(acc, {}, world(), {"ETH": SIG_TRIGGER + 0.05}, NOW_STEP, portfolio=port("altro"))
    assert not out["opened"] and out["skipped"]["ETH"] == "portafoglio_sconosciuto"


def test_step_in_pause_or_halt_opens_nothing_but_still_closes_on_time():
    for kw in ({"drain": True}, {"halt": "stop giornaliero raggiunto"}):
        acc = PaperAccount(Limits())
        out, _ = run_step(acc, {}, world(), {"ETH": SIG_TRIGGER + 0.05}, NOW_STEP, **kw)
        assert not acc.positions and not out["opened"]
        acc.open("SOL", 1, 60.0, 15, 100.0, 98.0, 106.0, NOW_STEP - L.MAX_HOLD_MS, {}, source=L.SOURCE)
        out, rec = run_step(acc, {}, {}, {"SOL": 100.5}, NOW_STEP, **kw)
        assert out["closed"] == ["SOL"] and not acc.positions and len(rec.closed) == 1


def test_step_closes_on_time_after_exactly_twelve_hours_not_before():
    acc = PaperAccount(Limits())
    acc.open("SOL", 1, 60.0, 15, 100.0, 98.0, 106.0, 5_000, {}, source=L.SOURCE)
    out, rec = run_step(acc, {}, {}, {"SOL": 100.5}, 5_000 + L.MAX_HOLD_MS - 1)
    assert "SOL" in acc.positions and not out["closed"]
    out, rec = run_step(acc, {}, {}, {"SOL": 100.5}, 5_000 + L.MAX_HOLD_MS)
    assert out["closed"] == ["SOL"] and not acc.positions
    r = rec.closed[0]
    assert r["why"] == "chiusura a tempo S25" and r["source"] == L.SOURCE and r["symbol"] == "SOL"
    assert rec.notes_c[0][0] == "SOL" and rec.notes_c[0][1] == r["net"] and rec.notes_c[0][3] == r["why"]


def test_time_exit_is_twelve_real_hours():
    twelve_h = 12 * 3_600_000
    assert L.MAX_HOLD_MS == twelve_h
    acc = PaperAccount(Limits())
    acc.open("SOL", 1, 60.0, 15, 100.0, 98.0, 106.0, 7_000, {}, source=L.SOURCE)
    run_step(acc, {}, {}, {"SOL": 100.5}, 7_000 + twelve_h - 1)
    assert "SOL" in acc.positions
    run_step(acc, {}, {}, {"SOL": 100.5}, 7_000 + twelve_h)
    assert "SOL" not in acc.positions


def test_step_time_close_leaves_positions_of_other_sources_alone():
    acc = PaperAccount(Limits())
    acc.open("SOL", 1, 60.0, 15, 100.0, 98.0, 106.0, 1, {}, source="rules")
    out, _ = run_step(acc, {}, {}, {"SOL": 100.5}, 1 + 10 * L.MAX_HOLD_MS)
    assert "SOL" in acc.positions and not out["closed"]


def test_step_time_close_without_a_price_skips_and_keeps_the_position():
    acc = PaperAccount(Limits())
    acc.open("SOL", 1, 60.0, 15, 100.0, 98.0, 106.0, 1, {}, source=L.SOURCE)
    out, _ = run_step(acc, {}, {}, {}, 1 + L.MAX_HOLD_MS)
    assert "SOL" in acc.positions and out["skipped"]["SOL"] == "prezzo_assente"


def test_step_engine_refusal_is_reported_and_does_not_stop_other_symbols():
    cmap = {"AAA": A15.copy(), "BBB": A15.copy()}
    acc = PaperAccount(Limits())
    acc.cash = 10.0                                         # cassa insufficiente: il motore rifiuta
    out, _ = run_step(acc, {}, cmap, {"AAA": SIG_TRIGGER + 0.05, "BBB": SIG_TRIGGER + 0.05}, NOW_STEP)
    assert not acc.positions and out["skipped"]["AAA"].startswith("rifiutata:")
    assert out["skipped"]["BBB"].startswith("rifiutata:")


def test_step_never_raises_for_a_broken_symbol_and_continues_with_the_others():
    bad = np.array([[1, 2, 3]])
    cmap = {"BAD": bad, "ETH": A15.copy()}
    acc = PaperAccount(Limits())
    out, _ = run_step(acc, {}, cmap, {"BAD": 1.0, "ETH": SIG_TRIGGER + 0.05}, NOW_STEP)
    assert out["opened"] == ["ETH"]
    out, _ = run_step(PaperAccount(Limits()), {}, {"ETH": A15.copy()}, {"ETH": None}, NOW_STEP)
    assert "ETH" not in out["opened"]


def test_step_notification_and_log_failures_do_not_block_the_trade():
    acc = PaperAccount(Limits())

    def boom(*a):
        raise RuntimeError("telegram giu'")

    out = L.step(acc, {}, world(), {"ETH": SIG_TRIGGER + 0.05}, NOW_STEP, port(), halt="", drain=False,
                 record_close=lambda s, r: None, notify_open=boom, notify_close=boom,
                 log_event=boom, echo=lambda s: None)
    assert out["opened"] == ["ETH"] and "ETH" in acc.positions


def test_step_failing_open_notification_does_not_skip_the_learning_log():
    acc, rec = PaperAccount(Limits()), Rec()

    def boom(*a):
        raise RuntimeError("telegram giu'")

    L.step(acc, {}, world(), {"ETH": SIG_TRIGGER + 0.05}, NOW_STEP, port(), halt="", drain=False,
           record_close=rec.record_close, notify_open=boom, notify_close=boom, log_event=rec.log_event,
           echo=lambda s: None)
    assert "ETH" in acc.positions and len(rec.events) == 1 and rec.events[0]["ev"] == "open"


def test_step_failing_close_notification_does_not_lose_the_trade_record():
    acc, rec = PaperAccount(Limits()), Rec()
    acc.open("SOL", 1, 60.0, 15, 100.0, 98.0, 106.0, 1, {}, source=L.SOURCE)

    def boom(*a):
        raise RuntimeError("telegram giu'")

    L.step(acc, {}, {}, {"SOL": 100.5}, 1 + L.MAX_HOLD_MS, port(), halt="", drain=False,
           record_close=rec.record_close, notify_open=boom, notify_close=boom, log_event=rec.log_event,
           echo=lambda s: None)
    assert "SOL" not in acc.positions and len(rec.closed) == 1 and rec.closed[0]["why"] == "chiusura a tempo S25"


def test_step_position_survives_state_roundtrip_with_source():
    acc = PaperAccount(Limits())
    run_step(acc, {}, world(), {"ETH": SIG_TRIGGER + 0.05}, NOW_STEP)
    back = PaperAccount.from_dict(json.loads(json.dumps(acc.to_dict())))
    assert back.positions["ETH"].source == L.SOURCE and L.owned(back.positions) == {"ETH"}


# --------------------------------------------------------------------------------------- (6) non regressione
# Pin aggiornati SOLO dopo l'estensione approvata del segnale trend consultivo:
# nessuna modifica a punteggi LONG/SHORT, call_claude o strategie. Il test
# test_desk_trend_change_advisory.py verifica anche l'assenza di effetti sullo scoring.

PINNED = {
    "signals.py": "488798a3a01792f8a158f667008643339ec691fa8e57d746bb88bb926ed23665",
    "seasonal.py": "47c12da1abbe51be0c826fc03b7609af40407e2e101911ded3444def5d6912c7",
}


@pytest.mark.parametrize("name", sorted(PINNED))
def test_scorer_files_are_unchanged(name):
    with open(os.path.join(BACKEND, "desk", name), "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == PINNED[name]


def test_engine_and_brain_files_are_unchanged_by_this_work():
    # brain.py: pin aggiornato dopo RC82 (dfc7059), che ha reso la scrittura dello storico/learning append-only
    # robusta a righe troncate (_append_json_line). engine.py (formule economiche) resta quello originale.
    for name, want in (("engine.py", "77836e4e84acccd256492708754a3bd72d8ecdb5a98c39456e9a6fb649787010"),
                       ("brain.py", "4f040c142909d3369fef81a2f7ef3307eab65421db1958e98d6153230f38884e")):
        with open(os.path.join(BACKEND, "desk", name), "rb") as f:
            assert hashlib.sha256(f.read()).hexdigest() == want


def test_module_imports_only_numpy_and_stdlib():
    src = open(os.path.join(BACKEND, "desk", "long_s25.py"), encoding="utf-8").read()
    imports = [ln.split()[1].split(".")[0] for ln in src.splitlines()
               if ln.startswith(("import ", "from ")) and "__future__" not in ln]
    assert set(imports) <= {"os", "typing", "numpy"}


def test_importing_the_module_has_no_side_effects_and_switch_default_is_off():
    assert "DESK_LONG_S25" not in os.environ or os.environ["DESK_LONG_S25"] != "1"
    assert L.enabled() is False


# --------------------------------------------------------------------------------- (7) ciclo completo simulato
def _cycle_candles():
    """ETH: 1200 ore di storia (per i punteggi delle regole) + la serie dell'incrocio, scalata al livello della storia.
    Ritorna le candele da 15 minuti fino alla fine della barra di segnale e il suo segnale."""
    rng = np.random.default_rng(5)
    px, base = 80.0, []
    for _ in range(1200):
        px *= 1 + rng.uniform(-0.002, 0.0015)
        base.append(px)
    tail = cross_series()
    tail[:, 1:5] *= base[-1] / 100.0
    pad = hours([], base, day=0)
    pad[:, 0] = tail[0, 0] - (len(base) - np.arange(len(base))) * H1
    h1 = np.vstack([pad, tail])
    a15 = to_15m(h1)
    sig = L.signal(L.closed_hours(a15, int(a15[-1, 0]) + M15))
    assert sig is not None, "la serie del test deve produrre il segnale"
    return a15, sig


def _with_new_hour(a15, sig, frac=0.1):
    """Aggiunge il primo quarto d'ora chiuso della nuova ora e quello in formazione, a un prezzo sopra il massimo del
    segnale (come li darebbe la Bitget: l'ultima riga e' sempre la candela in formazione)."""
    px = sig["trigger"] + frac * sig["atr"]
    t = int(a15[-1, 0]) + M15
    new = np.array([[t, px, px, px, px, 1.0], [t + M15, px, px, px, px, 1.0]], dtype=float)
    return np.vstack([a15, new]), t + M15 + 20_000, px


@pytest.fixture
def sandbox(monkeypatch):
    from desk import cli
    import desk.market_context as mc
    ctx = lambda s, n: {"funding": {}, "oi": {}, "news": [], "ts": n}    # noqa: E731
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(cli, "DATA_DIR", d)
        monkeypatch.setattr(cli, "STATE_FILE", os.path.join(d, "state_v2.json"))
        monkeypatch.setattr(mc, "fetch_all_context", ctx)
        monkeypatch.setattr(cli, "fetch_all_context", ctx)
        monkeypatch.setattr(cli.time, "sleep", lambda _: None)
        monkeypatch.setattr(cli, "rules_decisions", lambda *a, **k: [])
        monkeypatch.setenv("DESK_DEEPSEEK_CLASSICS", "0")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("DESK_LONG_S25", raising=False)
        cli.HB.update(last_ok=None, last_error="", cycles=0)
        yield cli, d


def _install(cli, monkeypatch, a15):
    monkeypatch.setattr(cli, "fetch_candles",
                        lambda sym, bar="15m", limit=1000: a15[-limit:].tolist() if sym == "ETH" else [])


def test_full_cycle_with_switch_on_opens_s25_long(sandbox, monkeypatch):
    cli, d = sandbox
    a15, sig = _cycle_candles()
    a15b, now, px = _with_new_hour(a15, sig)
    _install(cli, monkeypatch, a15b)
    monkeypatch.setenv("DESK_LONG_S25", "1")
    state = {}
    cli.run_cycle(state, now)
    acc = cli.make_account(state)
    assert list(acc.positions) == ["ETH"], f"S25 non ha aperto: {list(acc.positions)}"
    p = acc.positions["ETH"]
    assert p.source == L.SOURCE and p.side == 1 and p.open_ms == now
    assert p.sl < p.entry < p.tp
    assert p.sl == pytest.approx(px - 1.5 * sig["atr"]) and p.tp == pytest.approx(px + 1.5 * sig["atr"])
    assert p.total_margin == L.MARGIN[cli.PORTFOLIO.name] and p.leverage == L.LEV_MIN
    log = open(os.path.join(d, "learning_log.jsonl")).read().splitlines()
    assert any(json.loads(r).get("ev") == "open" and json.loads(r).get("source") == L.SOURCE for r in log)
    # secondo giro nello stesso quarto d'ora: nessun secondo ingresso (la posizione esiste ed e' in cooldown)
    cli.run_cycle(state, now + 1_000)
    assert len(cli.make_account(state).positions) == 1 and not cli.make_account(state).closed


def test_full_cycle_with_switch_off_never_opens_and_never_loads_the_module(sandbox, monkeypatch):
    cli, d = sandbox
    a15, sig = _cycle_candles()
    a15b, now, _ = _with_new_hour(a15, sig)
    _install(cli, monkeypatch, a15b)
    sys.modules.pop("desk.long_s25", None)
    state = {}
    cli.run_cycle(state, now)
    assert not cli.make_account(state).positions
    assert "desk.long_s25" not in sys.modules
    sys.modules["desk.long_s25"] = L                      # lo rimettiamo: gli altri test usano il modulo


def test_full_cycle_in_pause_does_not_open_s25(sandbox, monkeypatch):
    cli, d = sandbox
    a15, sig = _cycle_candles()
    a15b, now, _ = _with_new_hour(a15, sig)
    _install(cli, monkeypatch, a15b)
    monkeypatch.setenv("DESK_LONG_S25", "1")
    state = {}
    cli.run_cycle(state, now, drain=True)
    assert not cli.make_account(state).positions


def test_full_cycle_rules_close_cannot_close_an_s25_position_only_when_switch_on(sandbox, monkeypatch):
    cli, d = sandbox
    a15, sig = _cycle_candles()
    _install(cli, monkeypatch, a15)
    now = int(a15[-1, 0]) + M15 + 20_000
    px = float(a15[-1, 4])

    def fresh_state():
        acc = PaperAccount(cli.PORTFOLIO.limits, "main")
        pos, msg = acc.open("ETH", 1, 60.0, 15, px, px * 0.97, px * 1.2, now - 2 * H1, {}, source=L.SOURCE)
        assert pos, msg
        return {"main": acc.to_dict()}

    monkeypatch.setattr(cli, "rules_decisions",
                        lambda *a, **k: [{"symbol": "ETH", "action": "close", "reason": "punteggio basso",
                                          "confidence": 0, "leverage": 0, "margin_usd": 0}])
    monkeypatch.setenv("DESK_LONG_S25", "1")
    on = fresh_state()
    cli.run_cycle(on, now)
    assert "ETH" in cli.make_account(on).positions, "la regola non deve poter chiudere una posizione S25"
    monkeypatch.delenv("DESK_LONG_S25")
    off = fresh_state()
    cli.run_cycle(off, now)
    acc = cli.make_account(off)
    assert "ETH" not in acc.positions and acc.closed[-1]["why"] == "chiusura Claude"


def test_full_cycle_time_exit_closes_s25_position_after_twelve_hours(sandbox, monkeypatch):
    cli, d = sandbox
    a15, sig = _cycle_candles()
    _install(cli, monkeypatch, a15)
    now = int(a15[-1, 0]) + M15 + 20_000
    px = float(a15[-1, 4])
    acc = PaperAccount(cli.PORTFOLIO.limits, "main")
    pos, msg = acc.open("ETH", 1, 60.0, 15, px, px * 0.97, px * 1.2, now - L.MAX_HOLD_MS, {}, source=L.SOURCE)
    assert pos, msg
    state = {"main": acc.to_dict()}
    monkeypatch.setenv("DESK_LONG_S25", "1")
    cli.run_cycle(state, now)
    acc = cli.make_account(state)
    assert "ETH" not in acc.positions and acc.closed[-1]["why"] == "chiusura a tempo S25"
    hist = open(os.path.join(d, "trade_history.jsonl")).read()
    assert "chiusura a tempo S25" in hist
