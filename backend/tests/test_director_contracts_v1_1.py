"""Director v1.1 contract and delayed-entry tests, unittest (no network/pytest)."""
import copy
import json
from pathlib import Path
import sys
import unittest
from dataclasses import FrozenInstanceError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from director.contracts import v1_1
from director.contracts.outcomes import OHLC
from director.contracts.outcomes_v1_1 import evaluate_candidate_path

FX = Path(__file__).resolve().parents[1] / "director" / "contracts" / "fixtures" / "contract_cases_v1_1.json"


class Contract11Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = json.loads(FX.read_text())

    def test_seven_fixture_cases_roundtrip_and_version(self):
        kinds = [("market_frame", v1_1.MarketFrame), ("candidate", v1_1.Candidate),
                 ("director_hold", v1_1.DirectorAdvice), ("director_open", v1_1.DirectorAdvice),
                 ("director_partial", v1_1.DirectorAdvice), ("director_no_trade", v1_1.DirectorAdvice),
                 ("portfolio_bull", v1_1.PortfolioSnapshot)]
        for name, typ in kinds:
            with self.subTest(name=name):
                item = typ.from_payload(self.fx[name])
                self.assertEqual(item.contract_version, "1.1")
                self.assertEqual(item, typ.from_payload(item.as_payload()))

    def test_partial_fraction_required_and_forbidden_elsewhere(self):
        x = copy.deepcopy(self.fx["director_partial"])
        for bad in (None, 0.0, 1.0, -0.1, 1.1, float("nan")):
            with self.subTest(bad=bad):
                x["close_fraction"] = bad
                with self.assertRaisesRegex(ValueError, "close_fraction"):
                    v1_1.DirectorAdvice.from_payload(x)
        y = copy.deepcopy(self.fx["director_open"])
        y["close_fraction"] = 0.5
        with self.assertRaisesRegex(ValueError, "close_fraction"):
            v1_1.DirectorAdvice.from_payload(y)

    def test_selected_candidate_only_open_and_required_conviction(self):
        x = copy.deepcopy(self.fx["director_no_trade"])
        x["evaluated_candidate_ids"] = [self.fx["candidate"]["candidate_id"]]
        x["selected_candidate_id"] = self.fx["candidate"]["candidate_id"]
        with self.assertRaisesRegex(ValueError, "selected_candidate_id"):
            v1_1.DirectorAdvice.from_payload(x)
        z = copy.deepcopy(self.fx["director_partial"])
        z["evaluated_candidate_ids"] = [self.fx["candidate"]["candidate_id"]]
        z["selected_candidate_id"] = self.fx["candidate"]["candidate_id"]
        with self.assertRaisesRegex(ValueError, "selected_candidate_id"):
            v1_1.DirectorAdvice.from_payload(z)
        y = copy.deepcopy(self.fx["director_open"])
        for invalid in (None, -1, 101, 50.5, True):
            with self.subTest(invalid=invalid):
                y["open_conviction_0_100"] = invalid
                with self.assertRaisesRegex(ValueError, "open_conviction"):
                    v1_1.DirectorAdvice.from_payload(y)

    def test_deep_immutable_features_and_stable_hash(self):
        x = copy.deepcopy(self.fx["market_frame"])
        x["features"] = {"adx": 16.0, "nested": {"x": [1, {"y": 2}]}}
        frame = v1_1.MarketFrame.from_payload(x)
        twin = v1_1.MarketFrame.from_payload(x)
        self.assertEqual(hash(frame), hash(twin))
        self.assertEqual(frame, twin)
        self.assertEqual(frame.as_payload()["features"], x["features"])
        with self.assertRaises(TypeError):
            frame.features["adx"] = 99
        with self.assertRaises(TypeError):
            frame.features["nested"]["x"][1]["y"] = 98
        with self.assertRaises(TypeError):
            frame.features["nested"]["x"][0] = 97
        x["features"]["nested"]["x"][0] = 999
        self.assertEqual(frame.features["nested"]["x"][0], 1)
        payload = frame.as_payload()
        payload["features"]["nested"]["x"][0] = 123
        self.assertEqual(frame.features["nested"]["x"][0], 1)
        self.assertIn(frame, {twin})

    def test_numpy_scalars_require_explicit_boundary_normalization(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed")
        x = copy.deepcopy(self.fx["market_frame"])
        x["observed_price"] = np.float64(100)
        x["asof_ms"] = np.int64(x["asof_ms"])
        with self.assertRaises(ValueError):
            v1_1.MarketFrame.from_payload(x)
        norm = v1_1.normalize_boundary(x)
        f = v1_1.MarketFrame.from_payload(norm)
        self.assertEqual(f.observed_price, 100)
        self.assertIs(type(f.asof_ms), int)
        with self.assertRaises(ValueError):
            v1_1.MarketFrame.from_payload({**norm, "features": {"bad": float("nan")}})

    def test_delayed_candidate_enters_first_eligible_open_not_signal_open(self):
        x = copy.deepcopy(self.fx["candidate"])
        x["earliest_entry_ms"] += 600_000  # two bars wait
        x["target"] = 103
        candidate = v1_1.Candidate.from_payload(x)
        b = [OHLC(1800000300000, 100, 105, 99.5, 104),
             OHLC(1800000600000, 104, 107, 103.5, 106),
             OHLC(1800000900000, 100, 101, 99.1, 100.5),
             OHLC(1800001200000, 100.5, 103.5, 100.4, 103.1)]
        # First two bars would have hit target, but we were not yet in trade.
        o = evaluate_candidate_path(candidate, b)
        self.assertEqual((o.entry_ms, o.entry, o.reason, o.exit),
                         (1800000900000, 100, "TARGET", 103))
        self.assertEqual(candidate.signal_bar_open_ms, 1800000000000)

    def test_delayed_candidate_rejects_source_gap_even_before_entry(self):
        x = copy.deepcopy(self.fx["candidate"])
        x["earliest_entry_ms"] += 600_000
        candidate = v1_1.Candidate.from_payload(x)
        bars = [OHLC(1800000300000,100,101,99.5,100),OHLC(1800000900000,100,101,99.5,100)]
        with self.assertRaisesRegex(ValueError, "GAP"):
            evaluate_candidate_path(candidate, bars)

    def test_old_v1_contracts_and_shared_outcomes_remain_stable(self):
        from director.contracts.v1 import MarketFrame as OldFrame
        from director.contracts.outcomes import evaluate_path
        old = copy.deepcopy(self.fx["market_frame"])
        old.pop("contract_version")
        self.assertEqual(OldFrame.from_payload(old).schema_version, 1)
        b = [OHLC(1800000300000,100,103,99.8,102)]
        self.assertEqual(evaluate_path(signal_open_ms=1800000000000,bar_ms=300000,
                                       side="LONG",stop=99,target=102,bars=b,
                                       max_hold_bars=1,cost_bp_roundtrip=16,
                                       funding_bp_8h_long=0).reason, "TARGET")

if __name__ == "__main__":
    unittest.main()
