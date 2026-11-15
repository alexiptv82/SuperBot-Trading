"""Synthetic FRRD checks: causality, closed bars, no retrofit to Brain runner.

Run locally from repository root:
    python -m pytest -q research/brain_frrd/test_detector.py
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.v3.features.indicators import Bar
from research.brain_frrd.detector import H1, H4, M15, observe

END = 1_800_000_000_000  # divisible by 15m, 1h and 4h


def _bars(values, step, end=END):
    result = []
    for i, val in enumerate(values):
        v = Decimal(str(val))
        result.append(Bar(
            end - (len(values) - i) * step,
            v, v + Decimal("0.4"), v - Decimal("0.4"), v,
            Decimal("10"),
        ))
    return result


def _down():
    m15 = _bars([130 - i for i in range(32)], M15)
    h1 = _bars([150 - i for i in range(18)], H1)
    h4 = _bars([200 - i for i in range(16)], H4)
    return m15, h1, h4


def _up():
    m15, _h1, _h4 = _down()
    h1 = _bars([150 + i for i in range(18)], H1)
    h4 = _bars([200 + i for i in range(16)], H4)
    return m15, h1, h4


def _replace_last_closes(m15, values):
    closes = [b.close for b in m15]
    closes[-len(values):] = [Decimal(str(v)) for v in values]
    return _bars(closes, M15)


def test_bearish_continuation_requires_two_closed_breakdown_bars():
    m15, h1, h4 = _down()
    obs = observe(m15, h1, bars_4h=h4, as_of_ms=END, regime="EXPANSION")
    assert obs.state == "CONTINUAZIONE_SHORT"
    assert obs.break_down is True
    assert obs.trend_1h == "DOWN"
    assert obs.as_dict()["advisory_only"] is True


def test_local_bounce_does_not_claim_4h_reversal():
    m15, h1, h4 = _down()
    m15 = _replace_last_closes(m15, [102, 104])
    obs = observe(m15, h1, bars_4h=h4, as_of_ms=END)
    assert obs.state == "RIMBALZO_LOCALE"
    assert obs.break_up is False
    assert obs.trend_4h == "DOWN"


def test_candidate_reversal_requires_broken_swing_and_upward_hourly_context():
    m15, h1, h4 = _up()
    m15 = _replace_last_closes(m15, [115, 117])
    obs = observe(m15, h1, bars_4h=h4, as_of_ms=END)
    assert obs.break_up
    assert obs.state == "INVERSIONE_CANDIDATA"
    assert obs.trend_1h == "UP"


def test_higher_tf_down_downgrades_15m_breakout_to_local_bounce():
    m15, _h1, h4 = _down()
    h1 = _bars([150 + i for i in range(18)], H1)
    m15 = _replace_last_closes(m15, [115, 117])
    obs = observe(m15, h1, bars_4h=h4, as_of_ms=END)
    assert obs.state == "RIMBALZO_LOCALE"
    assert obs.trend_4h == "DOWN"


def test_two_bar_hysteresis_avoids_immediate_short_flip_after_bounce():
    m15, h1, h4 = _down()
    m15 = _replace_last_closes(m15, [102, 104])
    assert observe(m15, h1, bars_4h=h4, as_of_ms=END).state == "RIMBALZO_LOCALE"
    # A single further falling closed bar is NOT two confirmed downside breaks.
    next_15m = m15 + _bars([102], M15, END + M15)
    h1_more = h1 + _bars([131], H1, END + H1)
    h4_more = h4 + _bars([183], H4, END + H4)
    later = observe(next_15m, h1_more, bars_4h=h4_more, as_of_ms=END + M15)
    assert later.state != "CONTINUAZIONE_SHORT"


def test_no_repaint_when_future_closed_bars_are_appended():
    m15, h1, h4 = _down()
    original = observe(m15, h1, bars_4h=h4, as_of_ms=END, regime="TREND_DOWN")
    after = observe(
        m15 + _bars([300, 310, 320], M15, END + 3 * M15),
        h1 + _bars([300], H1, END + H1),
        bars_4h=h4 + _bars([300], H4, END + H4),
        as_of_ms=END, regime="TREND_DOWN",
    )
    assert after == original


def test_unfinished_15m_candle_is_ignored():
    m15, h1, h4 = _down()
    forming = _bars([999], M15, END + M15)
    assert observe(m15 + forming, h1, bars_4h=h4, as_of_ms=END) == observe(
        m15, h1, bars_4h=h4, as_of_ms=END
    )


def test_gap_in_15m_history_fails_uncertain():
    m15, h1, h4 = _down()
    broken = m15[:15] + m15[16:]
    result = observe(broken, h1, bars_4h=h4, as_of_ms=END)
    assert result.state == "INCERTO"
    assert "15m" in result.reason


def test_missing_or_stale_hourly_data_is_uncertain():
    m15, h1, h4 = _down()
    assert observe(m15, None, bars_4h=h4, as_of_ms=END).state == "INCERTO"
    assert observe(m15, h1[:-1], bars_4h=h4, as_of_ms=END).state == "INCERTO"


def test_optional_4h_can_be_absent_but_invalid_4h_is_uncertain():
    m15, h1, h4 = _down()
    assert observe(m15, h1, as_of_ms=END).state == "CONTINUAZIONE_SHORT"
    invalid = h4[:7] + h4[8:]
    obs = observe(m15, h1, bars_4h=invalid, as_of_ms=END)
    assert obs.state == "INCERTO"
    assert "4h" in obs.reason


def test_bullish_4h_conflicts_with_bearish_15m_break():
    m15, h1, _h4 = _down()
    h4up = _bars([200 + i for i in range(16)], H4)
    obs = observe(m15, h1, bars_4h=h4up, as_of_ms=END)
    assert obs.state == "INCERTO"
    assert obs.reason == "higher_tf_conflict_against_short"


def test_side_effect_free_repeated_evaluation():
    m15, h1, h4 = _down()
    copy = (tuple(m15), tuple(h1), tuple(h4))
    x = observe(m15, h1, bars_4h=h4, as_of_ms=END).as_dict()
    y = observe(m15, h1, bars_4h=h4, as_of_ms=END).as_dict()
    assert x == y
    assert (tuple(m15), tuple(h1), tuple(h4)) == copy


@pytest.mark.parametrize("invalid", [0, -1, 1.0, True, "1800000000000"])
def test_invalid_timestamp_is_rejected(invalid):
    m15, h1, h4 = _down()
    with pytest.raises(ValueError, match="invalid_as_of_ms"):
        observe(m15, h1, bars_4h=h4, as_of_ms=invalid)


def test_invalid_regime_is_rejected():
    m15, h1, h4 = _down()
    with pytest.raises(ValueError, match="invalid_regime"):
        observe(m15, h1, bars_4h=h4, as_of_ms=END, regime="BUY_NOW")
