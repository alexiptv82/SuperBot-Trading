import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from desk.market_regime import MarketRegimeClassifier, detect_reversal, _reversal
from desk.episode_memory import EpisodeMemory

NOW = 1_800_000_000_000  # aligned UTC hour, synthetic fixtures only


def bars(interval, closes=None):
    c = np.asarray(closes if closes is not None else np.linspace(100, 110, 80), dtype=float)
    t = NOW - np.arange(len(c), 0, -1) * interval
    return np.column_stack((t, c, c + 0.05, c - 0.05, c, np.ones(len(c))))


def trade(i, side=-1, net=-1, **kw):
    return dict(id=i, symbol="TEST", open_ms=NOW-100000, close_ms=NOW-1000,
                side=side, net=net, **kw)


class RegimeTests(unittest.TestCase):
    def test_bull_and_bear_divergence_positions(self):
        for bullish in (True, False):
            h = bars(3600000, np.full(80, 100.0))
            h[-3, 3 if bullish else 2] = 98 if bullish else 102
            rsi = np.full(80, 50.0)
            rsi[-3] = 60 if bullish else 40
            with patch("desk.market_regime._rsi", return_value=rsi):
                result = _reversal(h, bars(900000))
            self.assertTrue(result["bullish_divergence" if bullish else "bearish_divergence"])

    def test_early_extreme_and_wrong_rsi_not_divergence(self):
        for at, value in ((-10, 60), (-3, 40)):
            h = bars(3600000, np.full(80, 100.0))
            h[at, 3] = 98
            rsi = np.full(80, 50.0); rsi[at] = value
            with patch("desk.market_regime._rsi", return_value=rsi):
                self.assertFalse(_reversal(h, bars(900000))["bullish_divergence"])

    def test_fast_reversal_and_short_modifier(self):
        h, m = bars(3600000), bars(900000)
        m[-1, 1:5] += 2; m[-1, 5] = 2
        self.assertEqual(detect_reversal(h, m, now_ms=NOW)["direction"], 1)
        r = MarketRegimeClassifier().classify(h, m, symbol="TEST", now_ms=NOW)
        self.assertEqual((r["regime"], r["short_modifier"]), ("REVERSING_UP", .3))

    def test_bear_reversal(self):
        h, m = bars(3600000), bars(900000)
        m[-1, 1:5] -= 4; m[-1, 5] = 2
        self.assertEqual(detect_reversal(h, m, now_ms=NOW)["direction"], -1)

    def test_invalid_inputs_neutral(self):
        valid = bars(900000)
        for bad in (None, [], valid[::-1], valid[:10], valid * np.nan):
            self.assertFalse(detect_reversal(bars(3600000), bad, now_ms=NOW)["valid"])
        self.assertFalse(detect_reversal(bars(3600000), valid, now_ms=NOW-1)["valid"])
        self.assertFalse(detect_reversal(bars(3600000), valid, now_ms=NOW+900000)["valid"])

    def test_dataframe_nondefault_index(self):
        df = pd.DataFrame(bars(900000), columns=["timestamp", "open", "high", "low", "close", "volume"], index=range(100,180))
        self.assertTrue(detect_reversal(bars(3600000), df, now_ms=NOW)["valid"])

    def test_nan_adx_and_flat_market(self):
        c = MarketRegimeClassifier(confirmations=1)
        for adx in (float("nan"), float("inf"), 0):
            r = c.classify(bars(3600000), bars(900000), symbol=str(adx), now_ms=NOW, adx=adx)
            self.assertEqual(r["regime"], "RANGING")
        r = c.classify(bars(3600000, np.ones(80)*100), bars(900000, np.ones(80)*100), symbol="flat", now_ms=NOW)
        self.assertEqual(r["regime"], "RANGING")

    def test_hysteresis_idempotent_and_symbol_isolation(self):
        c = MarketRegimeClassifier(); h, m = bars(3600000), bars(900000)
        for _ in range(5):
            self.assertEqual(c.classify(h,m,symbol="A",now_ms=NOW)["regime"], "UNKNOWN")
        newer = np.vstack((m[1:], m[-1] + np.array([900000,0,0,0,0,0])))
        self.assertEqual(c.classify(h,newer,symbol="A",now_ms=NOW+900000)["regime"], "TRENDING_UP")
        self.assertEqual(c.classify(h,newer,symbol="B",now_ms=NOW+900000)["regime"], "UNKNOWN")

    def test_threaded_same_bar_does_not_confirm(self):
        c = MarketRegimeClassifier()
        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            results = list(pool.map(lambda _: c.classify(bars(3600000), bars(900000), symbol="A", now_ms=NOW), range(40)))
        self.assertTrue(all(r["regime"] == "UNKNOWN" for r in results))

    def test_corruption_resets_pending(self):
        c = MarketRegimeClassifier()
        c.classify(bars(3600000),bars(900000),symbol="A",now_ms=NOW)
        self.assertFalse(c.classify([],[],symbol="A",now_ms=NOW)["valid"])
        self.assertEqual(c.classify(bars(3600000),bars(900000),symbol="A",now_ms=NOW)["regime"], "UNKNOWN")

    def test_volatility_and_downtrend(self):
        c = MarketRegimeClassifier(confirmations=1)
        m = bars(900000, [100,110]*40)
        self.assertEqual(c.classify(bars(3600000),m,symbol="V",now_ms=NOW)["regime"], "VOLATILE")
        h = bars(3600000, np.linspace(110,100,80))
        self.assertEqual(c.classify(h,bars(900000),symbol="D",now_ms=NOW)["regime"], "TRENDING_DOWN")

    def test_bounded_state_and_gap(self):
        c = MarketRegimeClassifier(max_symbols=2)
        for symbol in ("A","B","C"):
            c.classify(bars(3600000),bars(900000),symbol=symbol,now_ms=NOW)
        self.assertEqual(len(c._states),2)
        m = bars(900000); m[:,0] += 1800000
        self.assertEqual(c.classify(bars(3600000),m,symbol="C",now_ms=NOW+1800000)["regime"], "UNKNOWN")


class MemoryTests(unittest.TestCase):
    def run_history(self, rows, suffix=b"", **kwargs):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/"history.jsonl"
            content = b"".join((json.dumps(r)+"\n").encode() for r in rows) + suffix
            path.write_bytes(content)
            before = hashlib.sha256(path.read_bytes()).digest()
            result = EpisodeMemory(clock=lambda: NOW/1000, **kwargs).get_bias(path)
            self.assertEqual(before, hashlib.sha256(path.read_bytes()).digest())
            return result

    def test_losses_penalize_only_losing_side(self):
        r = self.run_history([trade(i) for i in range(3)] + [trade(7,side=1,net=3)])
        self.assertEqual((r["long_modifier"],r["short_modifier"]),(1,.5))

    def test_insufficient_and_profitable_samples(self):
        self.assertEqual(self.run_history([trade(1),trade(2)])["short_modifier"],1)
        self.assertEqual(self.run_history([trade(1),trade(2),trade(3,net=10)])["short_modifier"],1)

    def test_partial_closes_and_duplicates_one_position(self):
        rows = [trade(1,net=-i) for i in range(1,5)]
        r = self.run_history(rows+rows)
        self.assertEqual(r["short_positions"],1)
        self.assertEqual(r["short_modifier"],1)

    def test_window_future_invalid_and_truncated(self):
        rows = [trade(1), {**trade(2),"close_ms": NOW+1}, {**trade(3),"close_ms": NOW-10800001},
                {**trade(4),"net":float("nan")}, {}, [], {**trade(5),"side":True}]
        r = self.run_history(rows,b'{"incomplete":')
        self.assertEqual(r["short_positions"],1)

    def test_corrupt_line_then_valid_rows(self):
        suffix = b'garbage\n'+b''.join((json.dumps(trade(i))+"\n").encode() for i in range(3))
        self.assertEqual(self.run_history([],suffix)["short_modifier"],.5)

    def test_missing_oversized_invalid_hours(self):
        memory = EpisodeMemory()
        self.assertFalse(memory.get_bias("/nonexistent/history")["valid"])
        self.assertFalse(memory.get_bias("/nonexistent/history",float("nan"))["valid"])
        self.assertFalse(self.run_history([trade(1)],max_bytes=10)["valid"])
        self.assertFalse(self.run_history([trade(1)],max_line_bytes=10)["valid"])

    def test_window_boundaries_and_distinct_runs(self):
        rows = [{**trade(1,run_no=i),"close_ms":stamp}
                for i,stamp in enumerate((NOW, NOW-10800000, NOW-1000))]
        r = self.run_history(rows)
        self.assertEqual((r["short_positions"],r["short_modifier"]),(3,.5))

    def test_permission_failure_neutral(self):
        with patch("builtins.open", side_effect=PermissionError()):
            self.assertFalse(EpisodeMemory().get_bias("unused")["valid"])


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import desk.brain as brain
        cls.brain = brain
        spec = importlib.util.spec_from_file_location("additions", Path(__file__).parents[2]/"docs/brain_regime_additions.py")
        cls.mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.mod)
        cls.mod.rules_decisions = brain.rules_decisions

    def reading(self):
        from dataclasses import make_dataclass, field
        cls = make_dataclass("Reading", [("symbol",str),("side",int),("score",int),("long_score",int),
                 ("short_score",int),("facts",dict),("why",list),("trade_type",str),("sl_pct",float),("tp_pct",float)])
        return cls("TEST",-1,90,40,90,{},["raw"],"scalp",.01,.02)

    def test_penalty_blocks_entry_preserves_original_and_manage(self):
        r = self.reading()
        class Classifier:
            def classify(self,*a,**kw):
                return dict(regime="REVERSING_UP",long_modifier=1,short_modifier=.3)
        adjusted = self.mod.prepare_entry_readings([r],{"TEST":([],[])},None,Classifier())[0]
        self.assertEqual((adjusted.long_score,adjusted.short_score,adjusted.side,adjusted.score),(40,27,1,40))
        self.assertEqual(r.short_score,90)
        positions = [{"symbol":"TEST","side":1}]
        baseline = self.brain.rules_decisions([r],positions,{"TEST"},only_manage=True)
        result = self.mod.context_rules_decisions([r],positions,{"TEST"},candles_by_symbol={"TEST":([],[])},classifier=Classifier())
        self.assertEqual(result,baseline)

    def test_module_failures_and_hold(self):
        r = self.reading()
        class Broken:
            def get_bias(self,*a,**kw): raise RuntimeError()
            def classify(self,*a,**kw): raise RuntimeError()
        result = self.mod.context_rules_decisions([r],[],set(),classifier=Broken(),memory=Broken())
        self.assertEqual(result,self.brain.rules_decisions([r],[],set()))
        self.assertEqual(self.mod.context_rules_decisions([r],[],set(),only_manage=True),[])


if __name__ == "__main__":
    unittest.main()
