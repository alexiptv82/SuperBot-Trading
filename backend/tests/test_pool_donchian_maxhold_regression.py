"""Regression for real CTL_S2_top10/XRP PAPER immutable exit_t conflict.

Recorded trade: entry 2026-10-20 02:00 UTC, time exit 2026-10-22
01:00 UTC. Before fix, downloading the 02:00 candle can change the
same trade into a Donchian next-open exit at 02:00, beyond 48h max_hold.

Synthetic price data only; NO VPS database, Bitget API or orders.
"""
import numpy as np
import pytest

import strategy_lab as sl
from rule_pool.journal import Journal

ENTRY_MS = 1792461600000  # 2026-10-20 02:00 UTC
MAX_HOLD = 48


def case(side, trigger_bar, length):
    # index 1 is the XRP entry, index 48 is the 48th and LAST held 1h
    # candle, index 49 is the forbidden 49th candle.
    t = ENTRY_MS + (np.arange(length, dtype=np.int64) - 1) * sl.H1
    price = np.full(length, 100.0)
    b = sl.Bars(t=t, o=price.copy(), h=price + 1, l=price - 1,
                c=price.copy(), v=np.full(length, 1.0))
    sig = sl.Sig(side=np.zeros(length, dtype=np.int8),
                 atr=np.ones(length), tgt=np.full(length, np.nan))
    dlow, dhigh = np.full(length, 90.0), np.full(length, 110.0)
    if side == 1:
        dlow[trigger_bar] = 101.0  # 100 < 101 => Donchian LONG
    else:
        dhigh[trigger_bar] = 99.0  # 100 > 99 => Donchian SHORT
    cfg = sl.ExitCfg(stop_mult=2.5, donch_exit=10, max_hold=MAX_HOLD)
    idx, px, reason = sl.simulate_exit(
        b, e=1, side=side, d=10.0, cfg=cfg, sig=sig,
        tgt=float('nan'), dlow=dlow, dhigh=dhigh)
    return b, idx, px, reason


@pytest.mark.parametrize('side', [1, -1])
def test_donchian_on_final_allowed_bar_does_not_steal_time_exit(side):
    # Initially, only the last permitted candle is known.
    prefix, pi, ppx, preason = case(side, trigger_bar=48, length=49)
    assert preason == 'time'
    assert pi == 48
    assert int(prefix.t[pi]) == ENTRY_MS + 47 * sl.H1

    # After one more 1h bar arrives, the exit must remain EXACTLY identical.
    # On the old code, this changes to 'donchian' at index 49 (+1 hour).
    full, fi, fpx, freason = case(side, trigger_bar=48, length=50)
    assert freason == preason == 'time'
    assert fi == pi == 48
    assert int(full.t[fi]) == int(prefix.t[pi])
    assert fpx == ppx


@pytest.mark.parametrize('side', [1, -1])
def test_donchian_next_open_within_max_hold_remains_legal(side):
    # Signal on the 47th held candle -> exit on the 48th: still allowed.
    b, i, _, reason = case(side, trigger_bar=47, length=50)
    assert reason == 'donchian'
    assert i == 48
    assert int(b.t[i]) == ENTRY_MS + 47 * sl.H1


@pytest.mark.parametrize('side', [1, -1])
def test_immutable_journal_closed_trade_can_be_replayed_after_new_bar(side):
    prefix, pi, ppx, preason = case(side, trigger_bar=48, length=49)
    full, fi, fpx, freason = case(side, trigger_bar=48, length=50)
    journal = Journal(':memory:')

    def record(b, index, price, reason):
        return {
            'rule_id': 'CTL_S2_top10', 'version': 1, 'venue': 'paper',
            'symbol': 'XRP/USDT:USDT', 'side': side,
            'entry_t': ENTRY_MS, 'entry_px': 100.0, 'status': 'closed',
            'exit_t': int(b.t[index]), 'exit_px': float(price),
            'why': reason, 'hold_h': MAX_HOLD,
            'gross_bp': 0.0, 'cost_bp': 16.0, 'funding_bp': 0.0,
            'net_bp': -16.0, 'mae_bp': -100.0, 'mfe_bp': 100.0,
        }

    assert journal.upsert_trade(record(prefix, pi, ppx, preason)) == 'inserted'
    assert journal.upsert_trade(record(full, fi, fpx, freason)) == 'unchanged'
