"""Fix B portfolio multi-symbol 1h alert; closed candles only."""
import copy
import unittest
from desk.profit_guardian import eligibility, position_key
from desk.portfolio_alert import reversal_evidence, detect_portfolio_alert, HOUR_MS

CLOSE = 1_800_000_000_000 // HOUR_MS * HOUR_MS
NOW = CLOSE + 120000


def bars(up=True, last_close=CLOSE):
    closes=[200-i*.2 for i in range(59)]+[230 if up else 188.2]
    return [{"close_ms":last_close-(59-i)*HOUR_MS,
             "close":price,"volume":60.0 if up and i==59 else 10.0}
            for i,price in enumerate(closes)]


def pos(symbol,n):
    return {"portfolio":"hawk","run_no":5,"position_id":n,"open_ms":NOW-7200000,
            "symbol":symbol,"side":-1,"roi_net_pct":2.0}


class PortfolioAlertTests(unittest.TestCase):
    def test_bullish_reclaim_rsi_volume_confirmed(self):
        e=reversal_evidence(bars(),now_ms=NOW)
        self.assertTrue(e["signal"],e)
        self.assertTrue(e["ema_reclaim"])
        self.assertGreaterEqual(e["rsi"],55)
        self.assertGreaterEqual(e["volume_ratio"],1.5)

    def test_three_unique_symbols_trigger_all_shorts_not_only_winners(self):
        shorts=[pos("SOL",1),pos("LTC",2),pos("BTC",3)]
        obs={"SOL":bars(),"BTC":bars(),"ETH":bars(),"LTC":bars(up=False)}
        old=copy.deepcopy(obs)
        alert=detect_portfolio_alert(short_positions=shorts,hourly_closed_candles=obs,now_ms=NOW)
        self.assertTrue(alert["active"])
        self.assertFalse(alert["applied"])
        self.assertEqual(alert["priority"],"MAX")
        self.assertEqual(alert["triggering_symbols"],["BTC","ETH","SOL"])
        self.assertEqual(set(alert["position_keys"]),{position_key(p) for p in shorts})
        self.assertEqual(obs,old)
        review=eligibility(shorts[1],now_ms=NOW,alert=alert)
        self.assertTrue(review.eligible)
        self.assertEqual(review.reason,"portfolio_reversal")

    def test_below_three_no_alert(self):
        shorts=[pos("SOL",1)]
        a=detect_portfolio_alert(short_positions=shorts,
                                 hourly_closed_candles={"SOL":bars(),"BTC":bars(),"ETH":bars(False)},
                                 now_ms=NOW)
        self.assertFalse(a["active"])
        self.assertEqual(a["action"],"NO_ALERT")
        self.assertEqual(a["position_keys"],[])

    def test_stale_future_or_incomplete_bar_fails_closed(self):
        self.assertFalse(reversal_evidence(bars(last_close=CLOSE-2*HOUR_MS),now_ms=NOW)["signal"])
        self.assertFalse(reversal_evidence(bars(last_close=CLOSE+HOUR_MS),now_ms=NOW)["signal"])
        data=bars()
        data[-1]["close_ms"]+=1000
        self.assertFalse(reversal_evidence(data,now_ms=NOW)["signal"])
        self.assertFalse(reversal_evidence(bars()[:40],now_ms=NOW)["signal"])

    def test_no_mixed_hours_no_false_simultaneous_alert(self):
        shorts=[pos("SOL",1),pos("LTC",2)]
        evt=detect_portfolio_alert(short_positions=shorts,
            hourly_closed_candles={"BTC":bars(),"ETH":bars(),
                                   "SOL":bars(last_close=CLOSE-HOUR_MS),
                                   "LTC":bars(False)},now_ms=NOW)
        self.assertFalse(evt["active"])

    def test_missing_bars_or_zero_short_positions_do_not_trigger(self):
        evt=detect_portfolio_alert(short_positions=[],
                                   hourly_closed_candles={"BTC":bars(),"ETH":bars()},
                                   now_ms=NOW)
        self.assertFalse(evt["active"])
        self.assertFalse(detect_portfolio_alert(short_positions=[pos("SOL",1)],
                         hourly_closed_candles={},now_ms=NOW)["active"])

    def test_identity_deduplicates_bitcoin_monitoring(self):
        x=detect_portfolio_alert(short_positions=[pos("BTC",1)],
                                 hourly_closed_candles={"BTC":bars(),"ETH":bars()},
                                 now_ms=NOW)
        self.assertEqual(x["monitored_symbols"],["BTC","ETH"])
        self.assertFalse(x["active"])

if __name__=="__main__": unittest.main()
