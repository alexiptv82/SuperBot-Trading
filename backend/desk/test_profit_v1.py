import copy
from dataclasses import asdict, replace
import json
import random
import unittest
from desk.profit.features import Bar, extract
from desk.profit.liquidable import Costs, Leg, PositionView, evaluate
from desk.profit.machine import State, step
from desk.profit.policy_hawk import research_policy
from desk.profit.policy_bull import research_policy as bull_policy
from desk.profit.reversal import Reversal, assess
from desk.profit.slot_value import compare
from desk.profit.ledger import evaluation, outcome, serialize
from desk.profit_replay_v1 import replay


def bars(n=30):
    return tuple(Bar((i+1)*60000, 100+i, 102+i, 99+i, 101+i) for i in range(n))


def feature(at=1200000):
    return extract(bars(), asof_ms=at, opened_ms=0, peak_ms=0, interval_ms=60000, max_age_ms=60000)


class ProfitTests(unittest.TestCase):
    def setUp(self):
        self.policy = research_policy()
        self.view = PositionView(1, (Leg(100, 1, .1),), .2, 0, 10)
        self.costs = Costs(.001, .002, .001)
        self.rev = Reversal(0, (), ())

    def advance(self, state=State(), net=20, at=1200000, **kw):
        f = replace(feature(at), atr=1, regime="range")
        liq = replace(evaluate(self.view, 120, self.costs), net_usd=net)
        return step(state, features=kw.get("features", f), liquidation=liq, qty=1, reversal=kw.get("reversal", self.rev), policy=kw.get("policy", self.policy))

    def test_long_costs(self):
        x = evaluate(self.view, 110, self.costs)
        self.assertAlmostEqual(x.net_usd, 109.78-100-.1-.10978-.2)

    def test_short_costs(self):
        x = evaluate(replace(self.view, side=-1), 90, self.costs)
        self.assertAlmostEqual(x.net_usd, 100-90.18-.1-.09018-.2)

    def test_funding_credit(self):
        a = evaluate(self.view, 110, self.costs)
        b = evaluate(replace(self.view, funding_paid=-.2), 110, self.costs)
        self.assertAlmostEqual(b.net_usd-a.net_usd, .4)

    def test_dca_legs_equal_weighted_view(self):
        a = replace(self.view, legs=(Leg(100, 1, .1), Leg(90, 2, .2)))
        b = replace(self.view, legs=(Leg(280/3, 3, .3),))
        self.assertAlmostEqual(evaluate(a, 110, self.costs).net_usd, evaluate(b, 110, self.costs).net_usd)

    def test_partial_no_double_count(self):
        p = PositionView(1, (Leg(100, .5, .05),), .1, 4.8, 10)
        self.assertAlmostEqual(evaluate(p, 110, Costs(0,0,0)).net_usd, 9.65)

    def test_invalid_values(self):
        for bad in (float("nan"), float("inf"), -1, 0):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                evaluate(self.view, bad, self.costs)

    def test_immutable_position(self):
        with self.assertRaises(AttributeError):
            self.view.side = -1

    def test_future_injection(self):
        past = feature()
        future = bars()[:20] + (Bar(9999999, 10000, 20000, 1, 15000),)
        actual = extract(future, asof_ms=1200000, opened_ms=0, peak_ms=0, interval_ms=60000, max_age_ms=60000)
        self.assertEqual(past, actual)

    def test_incomplete_bar_excluded(self):
        self.assertEqual(feature(1199999).bar_close_ms, 1140000)

    def test_mutant_lookahead_detected(self):
        def broken_extract(series, at):
            # Deliberate mutation: replace decision time with final data time.
            return extract(series, asof_ms=series[-1].close_ms, opened_ms=0, peak_ms=0, interval_ms=60000, max_age_ms=60000)
        with self.assertRaises(AssertionError):
            self.assertEqual(broken_extract(bars(),1200000), broken_extract(bars()[:20],1200000))

    def test_reversal_momentum_is_one_family(self):
        f = replace(feature(), ema_slope=-1, rsi=20, lower_break=False)
        self.assertEqual(assess(f,1).families,("momentum",))
        self.assertEqual(assess(replace(f,lower_break=True),1).score,1)

    def test_new_floor_not_retroactive(self):
        d = self.advance(State(name="ARMATO",peak_usd=40),net=20)
        self.assertEqual(d.action,"STRINGI")
        self.assertGreater(d.state.floor_usd,20)
        self.assertEqual(self.advance(d.state,net=20,at=1260000).action,"ESCI")

    def test_time_reversal_rejected(self):
        with self.assertRaises(ValueError):
            self.advance(State(last_bar_ms=1260000))

    def test_pure_package_has_no_io_imports(self):
        import ast
        from pathlib import Path
        root = Path(__file__).parent / "profit"
        forbidden = {"os","pathlib","socket","requests","httpx","subprocess","engine","cli"}
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):
                    self.assertFalse({x.name.split('.')[0] for x in node.names} & forbidden)
                if isinstance(node,ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0],forbidden)
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                    self.assertNotIn(node.func.id,{"open","eval","exec","__import__"})

    def test_gap_freezes(self):
        data = bars()[:18] + bars()[19:]
        f = extract(data, asof_ms=1200000, opened_ms=0, peak_ms=0, interval_ms=60000, max_age_ms=60000)
        self.assertFalse(f.valid)
        self.assertEqual(f.reason, "missing_bar")

    def test_stale_and_warmup(self):
        for data, at, reason in ((bars()[:2], 1200000, "warmup"), (bars(), 2000000, "stale")):
            f = extract(data, asof_ms=at, opened_ms=0, peak_ms=0, interval_ms=60000, max_age_ms=60000)
            self.assertEqual(f.reason, reason)

    def test_duplicate_bars_rejected(self):
        with self.assertRaises(ValueError):
            extract(bars()+bars(), asof_ms=1800000, opened_ms=0, peak_ms=0, interval_ms=60000, max_age_ms=60000)

    def test_state_sequence(self):
        s = self.advance().state
        self.assertEqual(s.name, "OSSERVA")
        s = self.advance(s, at=1260000).state
        self.assertEqual(s.name, "ARMATO")
        d = self.advance(s, at=1320000)
        self.assertEqual((d.state.name, d.action), ("PROTETTO", "STRINGI"))
        d = self.advance(d.state, net=19.5, at=1380000, reversal=Reversal(.5,("momentum",),()))
        self.assertEqual(d.state.name, "STRETTO")
        d = self.advance(d.state, net=0, at=1440000)
        self.assertEqual((d.state.name, d.action), ("USCITA", "ESCI"))
        self.assertEqual(self.advance(d.state, at=1500000).action, "HOLD")

    def test_repeated_bar_no_confirmation(self):
        s = self.advance().state
        self.assertEqual(self.advance(s).state, s)

    def test_confirmation_reset(self):
        s = self.advance().state
        self.assertEqual(self.advance(s, net=-5, at=1260000).state.confirmations, 0)

    def test_freeze_preserves_floor_peak(self):
        s = State(name="PROTETTO", floor_usd=10, peak_usd=20, last_bar_ms=1140000)
        d = self.advance(s, net=-100, features=replace(feature(), valid=False, reason="stale"))
        self.assertEqual((d.state.name, d.state.floor_usd, d.state.peak_usd, d.action), ("CONGELATO",10,20,"HOLD"))
        self.assertEqual(self.advance(d.state, net=9, at=1260000).action, "ESCI")

    def test_reversal_requires_two_families(self):
        s = State(name="ARMATO")
        self.assertNotEqual(self.advance(s, reversal=Reversal(1,("momentum","momentum"),())).action, "ESCI")
        self.assertEqual(self.advance(s, reversal=Reversal(1,("momentum","structure"),())).action, "ESCI")

    def test_random_floor_monotonic(self):
        rng = random.Random(819)
        for _ in range(100):
            s = State(name="PROTETTO", floor_usd=-100, peak_usd=10)
            old = s.floor_usd
            for i in range(10):
                d = self.advance(s, net=rng.uniform(10,100), at=1200000+i*60000)
                self.assertGreaterEqual(d.state.floor_usd, old)
                old, s = d.state.floor_usd, d.state

    def test_partial_proposal_once(self):
        policy = replace(bull_policy(), partial_fraction=.25)
        d = self.advance(State(name="ARMATO"), policy=policy)
        self.assertEqual((d.action,d.fraction), ("PARZIALE",.25))
        self.assertNotEqual(self.advance(d.state, at=1260000, policy=policy).action, "PARZIALE")

    def test_policy_hash(self):
        self.assertEqual(self.policy.config_hash, research_policy().config_hash)
        self.assertNotEqual(self.policy.config_hash, replace(self.policy, arm_atr=2).config_hash)

    def test_slot_strict(self):
        self.assertEqual(compare(10,8,1,1,comparable=True).action,"HOLD")
        self.assertEqual(compare(11,8,1,1,comparable=True).action,"PROPONI_SOSTITUZIONE")
        self.assertEqual(compare(100,1,0,0).action,"HOLD")

    def test_ledger_deterministic_and_separate_outcome(self):
        d = self.advance()
        args = dict(portfolio="hawk",run_no=3,position_key="hawk:3:1:0:BTC",ts_ms=1200000,code_version="test",policy=self.policy,before=State(),decision=d,features=feature(),liquidation=evaluate(self.view,120,self.costs),reversal=self.rev)
        e = evaluation(**args)
        self.assertEqual(serialize(e),serialize(evaluation(**args)))
        self.assertFalse(e["applied"])
        self.assertIsNone(e["p_win"])
        with self.assertRaises(ValueError):
            outcome(e,observed_ms=1200000,metrics={})
        self.assertEqual(outcome(e,observed_ms=1200001,metrics={})["event_id"],e["event_id"])

    def test_replay_nonmutation_and_future_invariance(self):
        data = {"schema":1,"mode":"paper","run_no":3,"policy":asdict(self.policy),"costs":asdict(self.costs),"interval_ms":60000,"max_age_ms":60000,"code_version":"test","positions":[{"position_key":"hawk:3:1:0:BTC","opened_ms":0,"side":1,"reference_margin":10,"bars":[asdict(b) for b in bars()],"snapshots":[{"asof_ms":1200000,"legs":[asdict(Leg(100,1,.1))],"funding_paid":.2,"realized_net":0}]}]}
        before = copy.deepcopy(data)
        result = replay(data)
        self.assertEqual(data,before)
        data["positions"][0]["bars"] = data["positions"][0]["bars"][:20]
        self.assertEqual(result,replay(data))
        data["mode"]="live"
        with self.assertRaises(ValueError): replay(data)


if __name__ == "__main__":
    unittest.main()
