"""Step 0 entry replay must not use future bars, orders or live services."""
import unittest
from desk.toro_profit_hunter import Candle, HOUR, FOUR_HOURS
from deploy.scripts.toro_profit_hunter_step0 import backtest, check_complete


class ToroStepZeroTest(unittest.TestCase):
    def test_invalid_ohlcv_and_gaps_rejected(self):
        rows = [Candle(i*HOUR,100,101,99,100,5) for i in range(3)]
        check_complete(rows,HOUR)
        with self.assertRaises(ValueError):
            check_complete(rows[:1]+rows[2:],HOUR)
        with self.assertRaises(ValueError):
            check_complete(rows+[rows[-1]],HOUR)

    def test_no_signal_without_reentry_and_no_random_claim(self):
        # Flat price never touches a 2-sigma lower band.
        h = [Candle(i*HOUR,100,100.1,99.9,100,5) for i in range(1030)]
        f = [Candle(i*FOUR_HOURS,100,100.1,99.9,100,5) for i in range(260)]
        r = backtest(h,f,"BTCUSDT",seeds=5)
        self.assertEqual(r["raw_signals"],0)
        for stats in r["windows"].values():
            self.assertEqual(stats["signals"],0)
            self.assertIsNone(stats["avg_net"])
            self.assertIsNone(stats["share_of_matched_random_beaten"])


if __name__ == "__main__":
    unittest.main()
