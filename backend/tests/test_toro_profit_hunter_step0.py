"""Step 0 entry replay must not use future bars, orders or live services."""
import unittest
import tempfile
from pathlib import Path
from desk.toro_profit_hunter import Candle, HOUR, FOUR_HOURS
from deploy.scripts.toro_profit_hunter_step0 import backtest, check_complete, load_csv


class ToroStepZeroTest(unittest.TestCase):
    def test_invalid_ohlcv_and_gaps_rejected(self):
        rows = [Candle(i*HOUR,100,101,99,100,5) for i in range(3)]
        check_complete(rows,HOUR)
        with self.assertRaises(ValueError):
            check_complete(rows[:1]+rows[2:],HOUR)
        with self.assertRaises(ValueError):
            check_complete(rows+[rows[-1]],HOUR)

    def test_bitget_csv_open_time_header_parsed(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/"BTCUSDT_60m.csv"
            source.write_text("open_time_ms,open,high,low,close,volume\\n"
                              "0,100,101,99,100,5\\n", encoding="utf-8")
            bars, sha = load_csv(source)
            self.assertEqual(len(bars), 1)
            self.assertEqual(bars[0].ts, 0)
            self.assertEqual(len(sha), 64)

    def test_historical_gap_skips_window_without_interpolation(self):
        h = [Candle(i*HOUR,100,100.1,99.9,100,5) for i in range(1050)
             if i != 1020]
        f = [Candle(i*FOUR_HOURS,100,100.1,99.9,100,5) for i in range(270)]
        result = backtest(h, f, "BTCUSDT", seeds=5)
        self.assertEqual(result["missing_data_gaps_1h"], 1)
        self.assertGreater(result["skipped_forward_windows_with_gaps"], 0)

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
