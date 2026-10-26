"""Fix B shadow-only unit contracts; no Bot runtime import, no network."""
import copy
import unittest

from desk.profit_guardian import (
    Review, GuardianError, DAILY_SHARED_BUDGET, eligibility, position_key,
    tp_distance_r, build_prompt, residual_breakeven, parse_proposal,
    budget_admission, comparison_event,
)

NOW = 1_800_000_000_000


def position(side=1, roi=24.0):
    return {
        "portfolio":"hawk","run_no":5,"position_id":42,"symbol":"BTC",
        "open_ms":NOW-7200000,"side":side,
        "roi_net_pct":roi,"entry":100.0,"entry0":100.0,"r_dist":.05,
        "qty":2.0,"price":130.0 if side==1 else 80.0,
        "sl":95.0 if side==1 else 105.0,
        "tp":145.0 if side==1 else 70.0,
        "mfe_price_R_upper_bound":4.0,"reference_margin":100,
        "risk_plan_usd":10,"fee_open_remaining":.12,
        "funding_remaining_usd":.02,"fee_rate_side":.0006,"slip_rate_side":.0002,
    }


def market(now=NOW):
    return {"asof_ms":now-60000,"closed_bars_only":True,"valid":True,
            "rsi_15m":68,"rsi_1h":62,"ema20_1h":120,"ema50_1h":115,
            "atr_pct":.015,"volume_ratio":1.9}


class FixBDecisionTests(unittest.TestCase):
    def test_three_decisions_are_shadow_proposals(self):
        p=position()
        self.assertEqual(parse_proposal({"action":"CLOSE_FULL","reason":"reversal","new_stop":None},p)["action"],"CLOSE_FULL")
        self.assertEqual(parse_proposal({"action":"HOLD_TP","reason":"strong trend"},p)["action"],"HOLD_TP")
        half=parse_proposal({"action":"TAKE_PARTIAL","reason":"bank half",
                             "partial_close_fraction":.5,"new_stop":105},p)
        self.assertEqual((half["fraction"],half["new_stop"]),(.5,105.0))
        self.assertEqual(p["qty"],2.0)

    def test_partial_is_atomic_fail_closed(self):
        p=position()
        for bad in [
            {"action":"TAKE_PARTIAL","reason":"no stop"},
            {"action":"TAKE_PARTIAL","reason":"widen risk","new_stop":94},
            {"action":"TAKE_PARTIAL","reason":"below breakeven","new_stop":96},
            {"action":"TAKE_PARTIAL","reason":"wrong side","new_stop":131},
            {"action":"TAKE_PARTIAL","reason":"wrong fraction","new_stop":104,"partial_close_fraction":.7},
            {"action":"TAKE_PARTIAL","reason":"NaN","new_stop":float("nan")},
        ]:
            with self.subTest(bad=bad):
                before=copy.deepcopy(p)
                with self.assertRaises(GuardianError):parse_proposal(bad,p)
                self.assertEqual(p,before)

    def test_short_protection_direction_and_costs(self):
        p=position(-1)
        be=residual_breakeven(p)
        self.assertLess(be,100)
        ok=parse_proposal({"action":"TAKE_PARTIAL","reason":"short protect","new_stop":98},p)
        self.assertEqual(ok["fraction"],.5)
        for stop in (101,79,105,100):
            with self.subTest(stop=stop),self.assertRaises(GuardianError):
                parse_proposal({"action":"TAKE_PARTIAL","reason":"unsafe","new_stop":stop},p)

    def test_threshold_watch_and_peak(self):
        low=eligibility(position(roi=11.9),now_ms=NOW)
        self.assertFalse(low.eligible)
        self.assertEqual(low.priority,"NONE")
        watch=eligibility(position(roi=12),now_ms=NOW)
        self.assertFalse(watch.eligible)
        self.assertEqual(watch.priority,"WATCH")
        high=eligibility(position(roi=20),now_ms=NOW)
        self.assertTrue(high.eligible)
        self.assertEqual(high.priority,"HIGH")
        giveback=eligibility(position(roi=8),now_ms=NOW,previous={"peak_roi_net_pct":27})
        self.assertTrue(giveback.eligible)

    def test_30_min_cooldown_even_high_priority_portfolio_alert(self):
        p=position(-1,roi=5)
        alert={"active":True,"position_keys":[position_key(p)]}
        ready=eligibility(p,now_ms=NOW,alert=alert)
        self.assertTrue(ready.eligible)
        self.assertEqual(ready.priority,"MAX")
        paused=eligibility(p,now_ms=NOW,previous={"last_review_ms":NOW-120000},
                           alert=alert)
        self.assertFalse(paused.eligible)
        self.assertEqual(paused.reason,"cooldown")
        self.assertEqual(paused.next_ms,NOW+28*60_000)
        exactly=eligibility(p,now_ms=NOW,previous={"last_review_ms":NOW-30*60_000},
                            alert=alert)
        self.assertTrue(exactly.eligible)

    def test_urgent_distinct_prompt_has_required_financial_context(self):
        p=position()
        prompt=build_prompt(p,market(),eligibility(p,now_ms=NOW),now_ms=NOW)
        for key in ("QUESTA POSIZIONE HA SUPERATO LA SOGLIA DI PROFITTO",
                    "mfe_price_R_upper_bound","tp_distance_from_current_price_R",
                    "roi_net_pct","rsi_1h","ema20_1h","volume_ratio","FIX B"):
            self.assertIn(key,prompt)
        self.assertAlmostEqual(tp_distance_r(p),3)
        stale=market();stale["asof_ms"]=NOW-16*60_000
        with self.assertRaises(GuardianError):
            build_prompt(p,stale,eligibility(p,now_ms=NOW),now_ms=NOW)
        with self.assertRaises(GuardianError):
            build_prompt(p,{**market(),"closed_bars_only":False},
                         eligibility(p,now_ms=NOW),now_ms=NOW)

    def test_no_false_profit_claim_for_alert_below_threshold(self):
        p=position(-1,roi=-2)
        review=eligibility(p,now_ms=NOW,alert={"active":True,"position_keys":[position_key(p)]})
        prompt=build_prompt(p,market(),review,now_ms=NOW)
        self.assertIn("ALERT PORTAFOGLIO",prompt)
        self.assertNotIn("HA SUPERATO LA SOGLIA",prompt)

    def test_dedicated_global_budget_guard(self):
        self.assertEqual(DAILY_SHARED_BUDGET,.10)
        self.assertTrue(budget_admission(spent_usd=.03,reserved_usd=.02,worst_case_call_usd=.05))
        self.assertFalse(budget_admission(spent_usd=.03,reserved_usd=.02,worst_case_call_usd=.051))
        with self.assertRaises(GuardianError):
            budget_admission(spent_usd=-1,reserved_usd=0,worst_case_call_usd=.01)

    def test_three_lanes_independent_and_never_executed(self):
        p=position()
        r=eligibility(p,now_ms=NOW)
        a={"action":"HOLD_TP","reason":"momentum"}
        event=comparison_event(p,now_ms=NOW,review=r,operational_claude=a,
                               claude_shadow=a,
                               deepseek_record={"symbol":"BTC","action":"HOLD",
                                                "ts_ms":NOW,"same_position_context":False})
        self.assertFalse(event["applied"])
        self.assertFalse(event["executed"])
        self.assertIsNone(event["execution_result"])
        self.assertEqual(event["claude_self_comparison"],"agree")
        self.assertFalse(event["deepseek_shadow"]["present"])
        b=comparison_event(p,now_ms=NOW,review=r,operational_claude=a,
                           claude_shadow={"action":"CLOSE_FULL","reason":"reversal"})
        self.assertEqual(b["claude_self_comparison"],"diverge")
        self.assertEqual(event["event_id"],b["event_id"])
        self.assertEqual(b["status"],"PROPOSAL_ONLY_NO_EXECUTOR")

    def test_missing_models_remain_missing_not_fabricated(self):
        p=position()
        ev=comparison_event(p,now_ms=NOW,review=eligibility(p,now_ms=NOW))
        self.assertFalse(ev["claude_operational_candidate"]["present"])
        self.assertFalse(ev["claude_shadow"]["present"])
        self.assertFalse(ev["deepseek_shadow"]["present"])
        self.assertEqual(ev["claude_self_comparison"],"unknown")

if __name__=="__main__":unittest.main()
