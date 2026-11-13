"""Offline tests for Toro Profit Hunter, no network/no trading services."""
import unittest
from desk.toro_profit_hunter import (
    Candle, Guardian, MakerPending, Policy, Quote, Signal, HOUR, FOUR_HOURS, MINUTE,
    _bars, entry_signal, estimated_net_long, profit_guardian, quote_entry, daily_summary
)


class ToroProfitHunterTest(unittest.TestCase):
    def setUp(self):
        self.s = Signal("BTCUSDT", 1000*HOUR, 100.0, 99.0, 103.0, 1.0, "neutral_or_up")

    def _quote(self, **kwargs):
        opts = dict(equity=1000, cash=1000, margin_used=0, notional_used=0,
                    open_risk=0, n_positions=0, daily_pnl=0, equity_peak=1000,
                    exchange_max_leverage=45)
        opts.update(kwargs)
        return quote_entry(self.s, **opts)

    def test_risk_is_derived_from_stop_not_leverage_target(self):
        q, why = self._quote()
        self.assertEqual(why, "accepted")
        self.assertLessEqual(q.worst_case_loss, 16)
        self.assertLessEqual(q.margin, 200)
        self.assertLessEqual(q.leverage, 20)
        self.assertLessEqual(q.notional, 10000)

    def test_total_risk_and_daily_remaining_risk(self):
        self.assertEqual(self._quote(open_risk=40)[1], "no_remaining_risk_budget")
        self.assertEqual(self._quote(daily_pnl=-30)[1], "circuit_breaker")
        q, why = self._quote(daily_pnl=-25, open_risk=25)
        self.assertEqual(why, "accepted")
        self.assertLessEqual(q.worst_case_loss, 5.0)

    def test_equity_dd_and_positions_fail_closed(self):
        self.assertEqual(self._quote(equity=449)[1], "slots_or_equity_halt")
        self.assertEqual(self._quote(n_positions=5)[1], "slots_or_equity_halt")
        self.assertEqual(self._quote(equity=830,equity_peak=1000)[1], "circuit_breaker")
        self.assertEqual(self._quote(margin_used=800)[1], "margin_or_reserve_exhausted")

    def test_bad_economics_rejected(self):
        s = Signal("BTCUSDT",1000*HOUR,100,98,100.2,1,"neutral")
        quote, why = quote_entry(s, equity=1000,cash=1000, margin_used=0,
            notional_used=0,open_risk=0,n_positions=0,daily_pnl=0,
            equity_peak=1000,exchange_max_leverage=45)
        self.assertIsNone(quote)
        self.assertEqual(why, "economic_gate")

    def test_closed_candle_only_and_gaps(self):
        bars=[Candle(i*HOUR,100,101,99,100,1) for i in range(750)]
        f=[Candle(i*FOUR_HOURS,100,101,99,100,1) for i in range(240)]
        asof=750*HOUR
        self.assertIsNotNone(entry_signal("BTCUSDT",bars,f,asof)[1])
        self.assertEqual(entry_signal("BTCUSDT",bars[:30],f,asof)[1],"missing_or_gapped_closed_history")
        self.assertEqual(entry_signal("BTCUSDT",bars[:-1]+[Candle(748*HOUR,100,101,99,100,1)],f,asof)[1],
                         "missing_or_gapped_closed_history")
        # A future candle is invisible to the current decision.
        now=entry_signal("BTCUSDT",bars,f,asof)
        self.assertEqual(now, entry_signal("BTCUSDT",bars+[Candle(asof+HOUR,10,11,9,10,1)],f,asof))

    def test_maker_requires_future_cross_not_touch(self):
        q=Quote("BTCUSDT",200,7,1400,16,100,99,103)
        maker=MakerPending(q,100*MINUTE,115*MINUTE)
        self.assertEqual(maker.on_minute(Candle(99*MINUTE,100,102,99,100,2)),"PENDING")
        self.assertEqual(maker.on_minute(Candle(101*MINUTE,101,102,100,101,2)),"PENDING")
        self.assertEqual(maker.on_minute(Candle(102*MINUTE,101,102,99.9,100,2)),"FILLED")
        self.assertEqual(maker.on_minute(Candle(116*MINUTE,101,102,100,101,2)),"FILLED")

    def test_maker_marketability_cancels_and_expiry(self):
        q=Quote("BTCUSDT",200,7,1400,16,100,99,103)
        self.assertEqual(MakerPending(q,0,15*MINUTE).on_minute(
            Candle(MINUTE,99,100,98,99,2)), "CANCELLED_POST_ONLY")
        self.assertEqual(MakerPending(q,0,15*MINUTE).on_minute(
            Candle(15*MINUTE,101,102,101,102,2)), "EXPIRED")

    def test_guardian_giveback_works_below_current_15(self):
        g=Guardian()
        d=profit_guardian(g,now_ms=MINUTE,opened_ms=0,net_open_now=25,
            atr_price=0.8,entry_price=100,remaining_notional=1500,
            momentum_score=3,structural_room_net=100)
        self.assertEqual(d.action,"HOLD")
        d=profit_guardian(g,now_ms=2*MINUTE,opened_ms=0,net_open_now=12,
            atr_price=0.8,entry_price=100,remaining_notional=1500,
            momentum_score=3,structural_room_net=100)
        self.assertEqual(d.action,"CLOSE")
        self.assertEqual(d.why,"ratchet_profit_floor")

    def test_guardian_momentum_and_partial(self):
        g=Guardian()
        d=profit_guardian(g,now_ms=MINUTE,opened_ms=0,net_open_now=31,
            atr_price=0.2,entry_price=100,remaining_notional=3000,
            momentum_score=3,structural_room_net=100)
        self.assertEqual(d.action,"PARTIAL")
        self.assertEqual(d.fraction,0.5)
        g.partial_done=True
        d=profit_guardian(g,now_ms=2*MINUTE,opened_ms=0,net_open_now=32,
            atr_price=0.2,entry_price=100,remaining_notional=1500,
            momentum_score=3,structural_room_net=100)
        self.assertNotEqual(d.action,"PARTIAL")

    def test_guardian_no_lookahead_or_double_monitoring(self):
        g=Guardian()
        a=profit_guardian(g,now_ms=MINUTE,opened_ms=0,net_open_now=15,
            atr_price=0.2,entry_price=100,remaining_notional=2000,
            momentum_score=2,structural_room_net=0)
        self.assertEqual(a.action,"HOLD")
        self.assertEqual(profit_guardian(g,now_ms=MINUTE,opened_ms=0,net_open_now=100,
            atr_price=0.2,entry_price=100,remaining_notional=2000,
            momentum_score=3,structural_room_net=100).why,"out_of_order_observation")

    def test_net_fee_and_summary(self):
        pnl = estimated_net_long(entry=100,last_bid=101,quantity=10,
                                 maker_fee=0.0002,taker_fee=0.0006,
                                 stop_slippage=0.0002)
        self.assertLess(pnl,10)
        summary=daily_summary([{"net":15},{"net":-5},{"net":25}])
        self.assertEqual(summary["trades"],3)
        self.assertEqual(summary["net"],35)
        self.assertEqual(summary["max_drawdown"],5)


if __name__ == "__main__":
    unittest.main()
