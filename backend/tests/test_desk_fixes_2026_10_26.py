"""Correzioni del 26/10/2026: stagionalita' V2 (formula additiva, curva del ciclo, freno del mercato),
tetto al rischio aperto e veto SHORT in rimbalzo per Bull."""
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DESK_MACRO_FETCH", "0")

from desk import seasonal  # noqa: E402
from desk.seasonal import get_seasonal  # noqa: E402


def ms(y, m, d=15):
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp() * 1000)


# ---------------- stagionalita' V2

def test_october_2026_is_no_longer_inverted_by_the_cycle():
    """Prima: ottobre (+22% storico) x ciclo bear (-1.0) = 5 punti SHORT. Ora il mese storico non viene ribaltato."""
    s = get_seasonal("BTC", ms(2026, 10))
    assert s.halving_phase == "bear market"
    assert s.long_bonus > 0 and s.short_bonus == 0


def test_november_2026_is_long_not_short():
    for sym in ("BTC", "ETH"):
        s = get_seasonal(sym, ms(2026, 11, 1))
        assert s.long_bonus > 0 and s.short_bonus == 0


def test_historically_weak_months_still_lean_short():
    for month in (5, 8, 9):                       # maggio, agosto, settembre
        s = get_seasonal("BTC", ms(2026, month))
        assert s.short_bonus > 0 and s.long_bonus == 0, month


def test_two_arguments_call_is_unchanged():
    s = get_seasonal("BTC", ms(2026, 10))
    assert isinstance(s, seasonal.SeasonalContext)
    assert 0 <= s.long_bonus <= 15 and 0 <= s.short_bonus <= 15
    assert isinstance(get_seasonal("BTC").note, str)        # now_ms assente


def test_bonus_stays_in_range_one_side_only():
    for y in (2024, 2025, 2026, 2027, 2028, 2030):
        for m in range(1, 13):
            for sym in ("BTC", "ETH", "SOL", "XAU", "XAG", "DOGE"):
                s = get_seasonal(sym, ms(y, m))
                assert 0 <= s.long_bonus <= 15 and 0 <= s.short_bonus <= 15
                assert s.long_bonus == 0 or s.short_bonus == 0


def test_cycle_curve_is_continuous_and_bounded():
    prev = seasonal._smooth_cycle_mult(0.0)
    for i in range(1, 700):
        cur = seasonal._smooth_cycle_mult(i / 10)
        assert abs(cur - prev) < 0.2                        # nessun salto brusco tra un valore e il successivo
        assert -1.0 <= cur <= 1.0
        prev = cur
    assert seasonal._smooth_cycle_mult(30.0) == -0.40


def test_commodities_ignore_the_btc_cycle():
    a, b = get_seasonal("XAU", ms(2026, 7)), get_seasonal("XAU", ms(2025, 7))
    assert (a.long_bonus, a.short_bonus) == (b.long_bonus, b.short_bonus)
    assert a.cycle_mult == 1.0


def test_market_brake_halves_and_zeroes_the_prior():
    base = get_seasonal("BTC", ms(2026, 10))
    mild = get_seasonal("BTC", ms(2026, 10), btc_return_3d=-0.02)       # contro il prior LONG, moderato
    strong = get_seasonal("BTC", ms(2026, 10), btc_return_3d=-0.04)     # contro il prior LONG, forte
    same = get_seasonal("BTC", ms(2026, 10), btc_return_3d=0.04)        # a favore: nessun freno
    assert 0 < mild.long_bonus < base.long_bonus
    assert (strong.long_bonus, strong.short_bonus) == (0, 0)
    assert same.long_bonus == base.long_bonus


def test_market_brake_also_works_for_short_prior():
    base = get_seasonal("BTC", ms(2026, 9))
    assert base.short_bonus > 0
    rally = get_seasonal("BTC", ms(2026, 9), btc_return_3d=0.05)
    assert (rally.long_bonus, rally.short_bonus) == (0, 0)


def test_read_symbol_passes_the_market_return_to_the_seasonal_module():
    from desk import signals
    seen = {}
    orig = signals.get_seasonal

    def spy(symbol, now_ms=None, btc_return_3d=None):
        seen["r"] = btc_return_3d
        return SimpleNamespace(long_bonus=0, short_bonus=0, note="")
    signals.get_seasonal = spy
    try:
        n = 1200
        t = 1_800_000_000_000 // 900_000 * 900_000 - n * 900_000
        px = 100 + np.cumsum(np.full(n, 0.01))
        arr = np.column_stack([t + np.arange(n) * 900_000, px, px + 0.1, px - 0.1, px, np.full(n, 10.0)])
        signals.read_symbol("SOL", arr, int(arr[-1, 0]) + 20_000, btc_return_3d=-0.031)
    finally:
        signals.get_seasonal = orig
    assert seen.get("r") == -0.031


# ---------------- cli: tetto al rischio Bull, veto SHORT in rimbalzo

from desk import cli  # noqa: E402
from desk.engine import Limits, PaperAccount  # noqa: E402

NOW = 1_800_000_000_000
BULL = SimpleNamespace(name="bull")
HAWK = SimpleNamespace(name="hawk")


def bull_acc():
    return PaperAccount(Limits(start_equity=1000.0, max_margin_trade=350.0, max_margin_total=1050.0, max_open=3,
                               kill_equity=450.0, daily_stop=0.12), "main")


def open_bull(acc, sym="BTC", side=1, margin=350, lev=15, sl_pct=0.03, px=100.0):
    pos, msg = acc.open(sym, side, margin, lev, px, px * (1 - side * sl_pct), None, NOW, {}, trade_type="medio")
    assert pos is not None, msg
    return pos


def test_open_sl_risk_matches_margin_leverage_stop_distance():
    acc = bull_acc()
    assert cli._open_sl_risk(acc) == 0.0
    open_bull(acc)
    assert abs(cli._open_sl_risk(acc) - 350 * 15 * 0.03) < 3      # il motore applica un po' di slippage all'entry


def test_open_sl_risk_counts_protected_stop_as_zero():
    acc = bull_acc()
    pos = open_bull(acc)
    pos.sl = pos.entry * 1.01                              # stop spostato in profitto
    assert cli._open_sl_risk(acc) == 0.0
    short = open_bull(acc, "ETH", side=-1)
    short.sl = short.entry * 0.99
    assert cli._open_sl_risk(acc) == 0.0


def test_open_sl_risk_short_position():
    acc = bull_acc()
    open_bull(acc, "ETH", side=-1)
    assert abs(cli._open_sl_risk(acc) - 350 * 15 * 0.03) < 3


def dec(margin=350, lev=15):
    return {"margin_usd": margin, "leverage": lev}


def test_bull_first_position_always_passes_even_with_wide_stop():
    acc = bull_acc()
    assert cli.bull_entry_gate(acc, BULL, dec(), 0.05, 1, None) is None      # 350*15*5% = 262$ > soglia, ma e' la prima


def test_bull_second_position_is_refused_above_the_risk_cap():
    acc = bull_acc()
    open_bull(acc)
    out = cli.bull_entry_gate(acc, BULL, dec(), 0.03, 1, None)
    assert out and out[0] == "rifiutata:rischio_aperto_bull"


def test_bull_second_small_position_fits_under_the_cap():
    acc = bull_acc()
    open_bull(acc, margin=100, lev=15, sl_pct=0.03)                            # 45$
    assert cli.bull_entry_gate(acc, BULL, dec(margin=100), 0.03, 1, None) is None   # 45 + 45 = 90 < 160


def test_bull_short_vetoed_when_btc_rallies_but_long_allowed():
    acc = bull_acc()
    out = cli.bull_entry_gate(acc, BULL, dec(), 0.03, -1, 0.025)
    assert out and out[0] == "rifiutata:veto_short_rimbalzo_btc"
    assert cli.bull_entry_gate(acc, BULL, dec(), 0.03, 1, 0.025) is None      # il LONG non e' toccato
    assert cli.bull_entry_gate(acc, BULL, dec(), 0.03, -1, 0.015) is None     # rimbalzo sotto soglia
    assert cli.bull_entry_gate(acc, BULL, dec(), 0.03, -1, None) is None      # dati BTC assenti: non blocca


def test_gate_never_applies_to_hawk():
    acc = bull_acc()
    open_bull(acc)
    assert cli.bull_entry_gate(acc, HAWK, dec(), 0.03, -1, 0.05) is None


def test_bars_return():
    arr = np.zeros((300, 6))
    arr[:, 4] = np.linspace(100, 130, 300)
    assert abs(cli._bars_return(arr, 288) - (130 / arr[-289, 4] - 1)) < 1e-12
    assert cli._bars_return(arr[:100], 288) is None
    assert cli._bars_return(None, 96) is None
    arr[-97, 4] = 0.0
    assert cli._bars_return(arr, 96) is None                # divisione per zero: nessun valore, nessuna eccezione
