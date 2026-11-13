"""Brain PAPER exit feed: error handling with synthetic candles only, no API and no bot changes."""
from __future__ import annotations

from decimal import Decimal as D

import pytest

from backend.tests.test_v3_runner_feed_monitor import (
    FakeBitget, _feed, _journal, _mbar, _open, _run, _series,
    T0, T_OPEN, RUN, MINUTE_MS, M1,
)
from backend.v3.runner.exit_service import ExitService, exit_service_healthy
from backend.v3.runner.feed import last_minute_close


def test_empty_1m_feed_with_open_position_degrades_sidecar(tmp_path):
    j = _journal()
    pid = _open(j)
    feed = _feed({"BTCUSDT": []})
    now = T0 + 4 * MINUTE_MS
    with ExitService(
        run_id=RUN, data_dir=tmp_path, run_commands=lambda _: None,
        run_monitor=lambda t: _run(j, feed, t)
    ) as service:
        tick = service.tick(now)
        assert tick.state == "degraded"
        assert tick.last_error == "monitor_reported_errors"
        assert tick.monitor.checked == 1
        assert tick.monitor.errors == ((pid, "exit_feed_incomplete"),)
        assert not exit_service_healthy(data_dir=tmp_path, run_id=RUN, now_ms=now)
    assert not [e for e in j.list_run("brain", RUN) if e.event.kind == "paper_close"]


def test_opening_partial_minute_is_not_a_false_feed_failure():
    j = _journal()
    _open(j)
    report = _run(j, _feed({"BTCUSDT": []}), T_OPEN + 20_000)
    assert (report.checked, report.closed, report.errors) == (1, (), ())
    # The opening candle closes but cannot be evaluated; its intra-minute
    # OHLC would include price action before the position existed.
    report = _run(j, _feed({"BTCUSDT": [_mbar(-1, 30000, 30100, 29900, 30000)]}),
                  T0 + MINUTE_MS + 5_000)
    assert report.errors == ()


def test_missing_latest_minute_degrades_even_if_older_bars_exist():
    j = _journal()
    pid = _open(j)
    older = [_mbar(0, 30000, 30100, 29900, 30000)]
    report = _run(j, _feed({"BTCUSDT": older}), T0 + 3 * MINUTE_MS)
    assert report.errors == ((pid, "exit_feed_incomplete"),)
    assert not report.closed


def test_internal_missing_minute_degrades_even_if_latest_is_fresh():
    j = _journal()
    pid = _open(j)
    bars = [_mbar(0, 30000, 30100, 29900, 30000),
            _mbar(2, 30000, 30100, 29900, 30000)]
    report = _run(j, _feed({"BTCUSDT": bars}), T0 + 4 * MINUTE_MS)
    assert report.errors == ((pid, "exit_feed_incomplete"),)
    assert not report.closed


def test_full_closed_1m_coverage_is_healthy():
    j = _journal()
    _open(j)
    bars = [_mbar(i, 30000, 30100, 29900, 30000) for i in range(3)]
    report = _run(j, _feed({"BTCUSDT": bars}), T0 + 4 * MINUTE_MS)
    assert report.errors == () and report.closed == ()


def test_stop_still_closes_when_following_candles_have_gap():
    j = _journal()
    pid = _open(j)
    bars = [_mbar(0, 30000, 30100, 29900, 30000),
            _mbar(1, 30000, 30100, 28900, 29000)]
    report = _run(j, _feed({"BTCUSDT": bars}), T0 + 8 * MINUTE_MS)
    assert dict(report.closed) == {pid: "stop"}
    assert len([e for e in j.list_run("brain", RUN) if e.event.kind == "paper_close"]) == 1


def test_last_minute_close_rejects_stale_1m_quote():
    # The five-minute lookback is for network retries, not price validity.
    bars = _series(T0, 4, M1)
    fake = FakeBitget({("BTCUSDT", "1m"): bars})
    with pytest.raises(ValueError, match="stale_minute_bar"):
        last_minute_close("BTCUSDT", T0 + 5 * M1 + 10_000, fake)


def test_last_minute_close_accepts_only_immediately_previous_closed_minute():
    bars = _series(T0, 5, M1)
    fake = FakeBitget({("BTCUSDT", "1m"): bars})
    assert last_minute_close("BTCUSDT", T0 + 5 * M1 + 10_000, fake) == bars[-1].close
