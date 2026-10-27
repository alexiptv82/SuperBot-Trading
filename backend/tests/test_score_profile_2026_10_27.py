"""Profilo dei pesi del punteggio (desk/signals.py): "classic" (predefinito, pesi di prima della modifica P1 del 25/10) e "p1"."""
import importlib
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DESK_MACRO_FETCH", "0")

from desk import signals  # noqa: E402


def _reload(monkeypatch, profile):
    if profile is None:
        monkeypatch.delenv("DESK_SCORE_PROFILE", raising=False)
    else:
        monkeypatch.setenv("DESK_SCORE_PROFILE", profile)
    return importlib.reload(signals)


def test_default_is_classic(monkeypatch):
    m = _reload(monkeypatch, None)
    try:
        assert (m.SCORE_PROFILE, m.W_TREND_4H, m.W_TREND_1D, m.BOUNCE_LONG_ON) == ("classic", 20, 15, False)
    finally:
        _reload(monkeypatch, None)


def test_p1_profile_keeps_the_oct_25_weights(monkeypatch):
    m = _reload(monkeypatch, "p1")
    try:
        assert (m.SCORE_PROFILE, m.W_TREND_4H, m.W_TREND_1D, m.BOUNCE_LONG_ON) == ("p1", 14, 10, True)
    finally:
        _reload(monkeypatch, None)


def test_classic_scores_equal_the_frozen_pre_p1_copy(monkeypatch):
    """La copia congelata (signals_pre_p1, usata dai banchi) e il profilo classico danno gli stessi punteggi."""
    import test_desk as td
    from desk import seasonal, signals_pre_p1 as old
    m = _reload(monkeypatch, None)
    monkeypatch.setattr(old, "get_seasonal", lambda sym, now_ms=None, btc_return_3d=None: seasonal.get_seasonal(sym, now_ms))
    world = td._world(drift=-0.0002, n=4500)
    seen = 0
    for sym, a in list(world.items())[:8]:
        a = np.asarray(a)
        for cut in (0, 100, 600):
            arr = a[: len(a) - cut] if cut else a
            now = int(arr[-1, 0]) + 900_000
            r1 = m.read_symbol(sym, arr[-1000:], now, price=float(arr[-1, 4]))
            r2 = old.read_symbol(sym, arr[-1000:], now, price=float(arr[-1, 4]))
            assert (r1 is None) == (r2 is None)
            if r1 is not None:
                assert (r1.long_score, r1.short_score) == (r2.long_score, r2.short_score)
                seen += 1
    assert seen >= 10
