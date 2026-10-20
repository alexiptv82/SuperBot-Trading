"""Independent deterministic tests, no pytest / network / exchange required.

Run: PYTHONPATH=backend python -m unittest backend.tests.test_director_contracts_v1 -v
"""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from director.contracts.v1 import (Candidate, DirectorAdvice, MarketFrame, PortfolioSnapshot)
from director.contracts.outcomes import OHLC, evaluate_path

FIXTURES = Path(__file__).resolve().parents[1] / "director" / "contracts" / "fixtures"


class ContractFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((FIXTURES / "contract_cases_v1.json").read_text(encoding="utf-8"))

    def test_valid_fixtures_and_roundtrip(self):
        for name, cls in (("market_frame", MarketFrame), ("candidate", Candidate),
                          ("director_hold", DirectorAdvice), ("portfolio_bull", PortfolioSnapshot)):
            with self.subTest(name=name):
                original = self.cases[name]
                parsed = cls.from_payload(original)
                self.assertEqual(json.loads(json.dumps(parsed.as_payload())),
                                 {**original, **({"schema_version": 1} if "schema_version" not in original else {}),
                                  **({"selected_candidate_id": None, "no_trade_reason": None} if name == "director_hold" else {})})
                self.assertEqual(cls.from_payload(parsed.as_payload()).as_payload(), parsed.as_payload())

    def test_market_frame_rejects_open_bar_and_future_level(self):
        x = copy.deepcopy(self.cases["market_frame"])
        x["last_closed_open_ms"] = x["asof_ms"]
        with self.assertRaisesRegex(ValueError, "LOOKAHEAD"):
            MarketFrame.from_payload(x)
        y = copy.deepcopy(self.cases["market_frame"])
        y["levels"][0]["confirmed_at_ms"] = y["asof_ms"] + 1
        with self.assertRaisesRegex(ValueError, "LOOKAHEAD"):
            MarketFrame.from_payload(y)

    def test_candidate_requires_next_bar_and_stop_on_correct_side(self):
        x = copy.deepcopy(self.cases["candidate"])
        x["earliest_entry_ms"] -= 1
        with self.assertRaisesRegex(ValueError, "LOOKAHEAD"):
            Candidate.from_payload(x)
        y = copy.deepcopy(self.cases["candidate"])
        y["stop"] = y["proposed_entry"] + 1
        with self.assertRaisesRegex(ValueError, "stop on wrong side"):
            Candidate.from_payload(y)

    def test_hold_fields_are_advice_not_probabilities(self):
        a = DirectorAdvice.from_payload(self.cases["director_hold"])
        self.assertEqual(a.proposed_review_not_before_ms, 1800000900000)
        x = copy.deepcopy(self.cases["director_hold"])
        del x["hold_conviction_0_100"]
        with self.assertRaisesRegex(ValueError, "hold_conviction"):
            DirectorAdvice.from_payload(x)
        y = copy.deepcopy(self.cases["director_hold"])
        y["review_timeframe_ms"] = None
        with self.assertRaisesRegex(ValueError, "review_timeframe"):
            DirectorAdvice.from_payload(y)

    def test_portfolio_snapshot_is_observation_not_trade_permission(self):
        x = copy.deepcopy(self.cases["portfolio_bull"])
        x["max_open"] = 1
        x["margin_used_usd"] = 1100
        self.assertEqual(PortfolioSnapshot.from_payload(x).max_open, 1)  # old states can exceed changed limits
        y = copy.deepcopy(self.cases["portfolio_bull"])
        y["positions"].append(copy.deepcopy(y["positions"][0]))
        with self.assertRaisesRegex(ValueError, "same symbol"):
            PortfolioSnapshot.from_payload(y)


class OutcomeConventionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = json.loads((FIXTURES / "outcome_cases_v1.json").read_text(encoding="utf-8"))

    def test_shared_outcome_fixture(self):
        fx = self.fx
        for case in fx["cases"]:
            with self.subTest(id=case["id"]):
                bars = [OHLC(*b) for b in case["bars"]]
                result = evaluate_path(signal_open_ms=fx["signal_open_ms"], bar_ms=fx["bar_ms"],
                                       side=case["side"], stop=case["stop"], target=case["target"],
                                       bars=bars, max_hold_bars=case["max_hold_bars"],
                                       cost_bp_roundtrip=fx["cost_bp_roundtrip"],
                                       funding_bp_8h_long=fx["funding_bp_8h_long"])
                for key, want in case["expected"].items():
                    got = getattr(result, key)
                    if isinstance(want, (float, int)) and not isinstance(want, bool):
                        self.assertAlmostEqual(got, want, places=5)
                    else:
                        self.assertEqual(got, want)

    def test_non_consecutive_bars_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "GAP"):
            evaluate_path(signal_open_ms=1_800_000_000_000, bar_ms=300_000, side="LONG",
                          stop=99, target=102, max_hold_bars=2, cost_bp_roundtrip=16,
                          bars=[OHLC(1800000300000,100,101,99.2,100),OHLC(1800000900000,100,101,99.2,100)])

    def test_funding_only_on_long_and_costs_not_charged_twice(self):
        b = [OHLC(1800000300000,100,101,99.5,100.1),OHLC(1800000600000,100.1,101,100.1,100.5)]
        base = {"signal_open_ms":1800000000000,"bar_ms":300000,"stop":99,"target":102,
                "bars":b,"max_hold_bars":2,"cost_bp_roundtrip":16,"funding_bp_8h_long":1}
        a=evaluate_path(side="LONG", **base)
        self.assertAlmostEqual(a.net_bp, 50-16-1*(600000/3600000)/8, places=5)
        sb = [OHLC(1800000300000,100,100.8,99.5,100.1),OHLC(1800000600000,100.1,100.8,100.1,100.5)]
        s=evaluate_path(side="SHORT", **{**base, "bars":sb, "stop":101,"target":98})
        self.assertAlmostEqual(s.net_bp, -50-16, places=5)


if __name__ == "__main__":
    unittest.main()
