"""Standalone offline advisory tests: NEVER submit any exchange order."""
import numpy as np
from desk.long_mirror_15m import inspect_long_mirror_15m, BAR_MS

NOW = 1_794_550_000_000


def sample(n=110, base=100, drift=0.0007, amp=0.004, end_force=0.005):
    last = NOW - NOW % BAR_MS - BAR_MS
    ts = last - (n - 1 - np.arange(n)) * BAR_MS
    changes = drift + amp * np.sin(np.arange(n) * 1.3)
    changes[-2:] = end_force
    close = base * np.exp(np.cumsum(changes))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) * 1.0005
    lo = np.minimum(op, close) * 0.9995
    vol = np.ones(n) * 100
    vol[-1] = 180
    return np.column_stack([ts, op, hi, lo, close, vol])


def test_uptrend_can_emit_only_a_long_candidate():
    r = inspect_long_mirror_15m("BTC", sample(), NOW, trend4h_state="UP")
    assert r.state == "LONG_CONTINUATION_CANDIDATE" and r.score == 69
    assert r.features["last_two_closed_green"] is True
    assert r.features["last_closed_ms"] <= NOW


def test_unknown_never_approves_a_long():
    r = inspect_long_mirror_15m("BTC", sample(), NOW, trend4h_state="UNKNOWN")
    assert r.state == "NO_TRADE" and r.reason == "trend_4h_unknown"


def test_metal_is_held_until_calendar_is_verified():
    assert inspect_long_mirror_15m("XAUUSDT", sample(), NOW, trend4h_state="UP").state == "NO_TRADE"


def test_open_candle_spike_cannot_flip_result():
    a = sample()
    partial = a[-1].copy()
    partial[0] += BAR_MS
    partial[1:5] = [100, 300, 90, 290]
    r0 = inspect_long_mirror_15m("BTC", a, NOW, trend4h_state="UP")
    r1 = inspect_long_mirror_15m("BTC", np.vstack([a, partial]), NOW, trend4h_state="UP")
    assert (r0.state, r0.score, r0.features) == (r1.state, r1.score, r1.features)


def test_missing_recent_bar_never_approves_a_long():
    a = sample()
    r = inspect_long_mirror_15m("BTC", np.delete(a, -30, axis=0), NOW, trend4h_state="UP")
    assert r.state == "NO_TRADE" and r.reason == "storia_15m_insufficiente"


def test_conflicting_duplicate_is_rejected():
    a = sample()
    bad = a[-2].copy()
    bad[4] += .01
    bad[2] += 1
    r = inspect_long_mirror_15m("BTC", np.vstack([a, bad]), NOW, trend4h_state="UP")
    assert r.state == "NO_TRADE" and r.reason == "duplicati_15m_in_conflitto"


def test_identical_duplicate_does_not_change_the_score():
    a = sample()
    extra = np.vstack([a, a[[-20]]])
    x = inspect_long_mirror_15m("BTC", a, NOW, trend4h_state="UP")
    y = inspect_long_mirror_15m("BTC", extra, NOW, trend4h_state="UP")
    assert (x.state, x.score, x.features) == (y.state, y.score, y.features)


def test_no_trade_when_15m_history_is_old():
    a = sample()
    r = inspect_long_mirror_15m("BTC", a, NOW + 3*BAR_MS, trend4h_state="UP")
    assert r.state == "NO_TRADE" and r.reason == "dati_15m_vecchi"


def test_negative_or_inconsistent_ohlcv_rejected():
    a = sample()
    a[-4, 2] = min(a[-4, 1], a[-4, 4]) * .9
    r = inspect_long_mirror_15m("BTC", a, NOW, trend4h_state="UP")
    assert r.state == "NO_TRADE" and r.reason == "ohlcv_non_valide"


def test_does_not_open_or_close_or_choose_a_leverage():
    r = inspect_long_mirror_15m("BTC", sample(), NOW, trend4h_state="UP")
    assert not hasattr(r, "action") and not hasattr(r, "leverage")
    assert r.state in {"NO_TRADE", "LONG_CONTINUATION_CANDIDATE", "LONG_BOUNCE_CANDIDATE"}


def test_risk_context_downtrend_never_becomes_continuation():
    r = inspect_long_mirror_15m("BTC", sample(), NOW, trend4h_state="DOWN")
    assert r.state != "LONG_CONTINUATION_CANDIDATE"


def test_downtrend_confirmed_bounce_is_a_distinct_nonexecuting_candidate():
    r = inspect_long_mirror_15m("BTC", sample(drift=0.0003, end_force=0.003), NOW, trend4h_state="DOWN")
    assert r.state == "LONG_BOUNCE_CANDIDATE" and r.score == 57
    assert r.reason == "rimbalzo_contro_trend_da_validare"


def test_two_red_candles_cannot_produce_a_long_candidate():
    r = inspect_long_mirror_15m("BTC", sample(end_force=-0.005), NOW, trend4h_state="UP")
    assert r.state == "NO_TRADE" and r.reason == "conferme_15m_non_sufficienti"


def test_gap_inside_the_used_window_is_rejected_even_with_long_history():
    """With 200 bars the history is sufficient: the missing bar must be detected as a gap, not as short history."""
    a = sample(n=200)
    assert inspect_long_mirror_15m("BTC", a, NOW, trend4h_state="UP").state == "LONG_CONTINUATION_CANDIDATE"
    r = inspect_long_mirror_15m("BTC", np.delete(a, -30, axis=0), NOW, trend4h_state="UP")
    assert r.state == "NO_TRADE" and r.reason == "storia_15m_interrotta"


def test_shooting_star_keeps_the_original_precedence_and_earns_no_long_points():
    """The frozen 1h classifier checks shooting_star before engulfing; the 15m mirror must not turn it bullish."""
    from desk.long_mirror_15m import _long_pattern
    from desk.signals import doji_pattern
    a = sample(n=200)
    pc = a[-2, 4]
    a[-2, 1:5] = [pc * 1.002, pc * 1.002 * 1.0005, pc * 0.9995, pc]        # previous candle red
    o, c = pc * 0.999, pc * 1.002 * 1.001                                   # engulfs the previous body
    a[-1, 1:5] = [o, c + 3 * (c - o), o * 0.99999, c]                       # long upper wick: shooting star
    assert doji_pattern(a[-3:]) == "shooting_star"
    assert _long_pattern(a) == "shooting_star"


def test_no_future_information_reaches_a_past_decision():
    """Replaying bar by bar: a decision at time t is identical whether or not later bars are supplied."""
    a = sample(n=200)
    for k in (150, 170, 199):
        now = int(a[k - 1, 0]) + BAR_MS + 1
        past = inspect_long_mirror_15m("BTC", a[:k], now, trend4h_state="UP")
        full = inspect_long_mirror_15m("BTC", a, now, trend4h_state="UP")
        assert (past.state, past.reason, past.score, past.features) == (full.state, full.reason, full.score, full.features)
