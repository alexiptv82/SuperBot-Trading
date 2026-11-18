"""Lo storico Bitget omette l'ultima candela chiusa (osservato 18/11/2026): il feed la completa da "candles"."""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from backend.v3.runner.feed import fetch_closed_bars

STEP = 900_000
END = 1_800_000_000_000 // STEP * STEP


def _row(t, close="100"):
    c = int(close)
    return [str(t), str(c), str(c + 1), str(c - 1), str(c), "5", "0"]


class Bitget:
    def __init__(self, history_has_last=False, recent_fails=False):
        self.paths, self.h, self.fail = [], history_has_last, recent_fails

    def __call__(self, url):
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        self.paths.append(u.path)
        a, b = int(q["startTime"]), int(q["endTime"])
        if u.path.endswith("/history-candles"):
            last = END - STEP if self.h else END - 2 * STEP          # omette l'ultima chiusa
            ts = [t for t in range(END - 50 * STEP, last + 1, STEP) if a <= t <= b]
            return {"code": "00000", "data": [_row(t, "100") for t in sorted(ts, reverse=True)]}
        if self.fail:
            raise OSError("rete")
        ts = [t for t in range(END - 5 * STEP, END + 1, STEP) if a <= t]   # include la candela in formazione
        return {"code": "00000", "data": [_row(t, "200") for t in sorted(ts, reverse=True)]}


def test_last_closed_bar_is_completed_from_recent_endpoint_never_the_forming_one():
    g = Bitget()
    bars = fetch_closed_bars("BTCUSDT", END - 20 * STEP, END, candle_ms=STEP, get_json=g)
    assert bars[-1].open_time_ms == END - STEP and all(b.open_time_ms < END for b in bars)
    assert any(p.endswith("/candles") for p in g.paths)
    assert [b.close for b in bars[-2:]] == [100, 200]                    # storico dove c'e', recente solo in coda


def test_history_takes_precedence_and_no_extra_call_when_complete():
    g = Bitget(history_has_last=True)
    bars = fetch_closed_bars("BTCUSDT", END - 20 * STEP, END, candle_ms=STEP, get_json=g)
    assert bars[-1].open_time_ms == END - STEP and bars[-1].close == 100
    assert not any(p.endswith("/candles") for p in g.paths)


def test_recent_endpoint_failure_leaves_the_gap_fail_closed():
    bars = fetch_closed_bars("BTCUSDT", END - 20 * STEP, END, candle_ms=STEP, get_json=Bitget(recent_fails=True))
    assert bars[-1].open_time_ms == END - 2 * STEP                       # la vista dira' "stale": nessuna decisione
