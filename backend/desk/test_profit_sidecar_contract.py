"""Synthetic characterization of engine data; does not modify the engine."""
import unittest
from desk.engine import PaperAccount, Position


class SidecarContractTests(unittest.TestCase):
    def test_id_and_close_time_do_not_identify_a_unique_partial(self):
        account = PaperAccount()
        account.positions["BTC"] = Position(
            id=1, symbol="BTC", side=1, margin=100, leverage=10,
            entry=100, qty=10, sl=95, tp=120, open_ms=1000,
            liq=90, fee_open=.6, total_margin=100,
        )
        first = account.partial_close("BTC", 110, 2000, .25)
        second = account.partial_close("BTC", 110, 2000, .25)
        self.assertEqual((first["id"], first["close_ms"]),
                         (second["id"], second["close_ms"]))
        self.assertEqual(len(account.closed), 2)
        total = sum(row["net"] for row in account.closed)
        lossy = {(row["id"], row["close_ms"]): row for row in account.closed}
        self.assertAlmostEqual(total, 43.1025)
        self.assertNotEqual(total, sum(row["net"] for row in lossy.values()))
        self.assertAlmostEqual(account.positions["BTC"].qty, 5.625)


if __name__ == "__main__":
    unittest.main()
