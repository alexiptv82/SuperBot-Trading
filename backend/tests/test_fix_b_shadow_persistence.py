"""Fix B shadow append-only journal and shared budget are independent of bot data."""
import json
import tempfile
import unittest
from pathlib import Path

from desk.profit_guardian import (
    GuardianError, ShadowBudgetLedger, append_shadow_record,
    comparison_portfolio_alert, comparison_event, eligibility, position_key,
)

NOW=1_800_000_000_000


def p(n=1,side=-1,roi=4):
    return {"portfolio":"bull","run_no":4,"position_id":n,"symbol":"BTC" if n==1 else "ETH",
            "open_ms":NOW-7200000,"side":side,"roi_net_pct":roi}


class ShadowJournalTests(unittest.TestCase):
    def test_append_three_lane_once_and_fail_on_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=str(Path(temporary)/"fix-b-shadow-data")
            position=p()
            record=comparison_event(position,now_ms=NOW,
                                    review=eligibility(position,now_ms=NOW))
            self.assertTrue(append_shadow_record(root,record))
            self.assertFalse(append_shadow_record(root,record))
            rows=(Path(root)/"fix-b-decisions.jsonl").read_text().splitlines()
            self.assertEqual(len(rows),1)
            self.assertEqual(json.loads(rows[0])["executed"],False)
            with (Path(root)/"fix-b-decisions.jsonl").open("a") as out:
                out.write("{corruption\n")
            with self.assertRaises(GuardianError):
                append_shadow_record(root,{**record,"event_id":"new-id"})

    def test_refuses_bot_directories_and_any_executed_event(self):
        record=comparison_event(p(),now_ms=NOW,
                                review=eligibility(p(),now_ms=NOW))
        with self.assertRaises(GuardianError):
            append_shadow_record("/opt/superbot-desk-data/hawk",record)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(GuardianError):
                append_shadow_record(str(Path(temporary)/"fix-b-shadow-data"),
                                     {**record,"applied":True})

    def test_shared_budget_reservations_settlements_and_utc_reset(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger=ShadowBudgetLedger(str(Path(temporary)/"fix-b-shadow-data"))
            self.assertTrue(ledger.reserve(ts_ms=NOW,event_id="hawk:123",worst_usd=.06))
            self.assertFalse(ledger.reserve(ts_ms=NOW,event_id="hawk:123",worst_usd=.06))
            self.assertFalse(ledger.reserve(ts_ms=NOW,event_id="bull:234",worst_usd=.05))
            self.assertAlmostEqual(ledger.remaining(ts_ms=NOW),.04)
            with self.assertRaises(GuardianError):
                ledger.settle(ts_ms=NOW,event_id="hawk:123",actual_usd=.07)
            self.assertTrue(ledger.settle(ts_ms=NOW,event_id="hawk:123",actual_usd=.025))
            self.assertFalse(ledger.settle(ts_ms=NOW,event_id="hawk:123",actual_usd=.025))
            self.assertAlmostEqual(ledger.remaining(ts_ms=NOW),.075)
            self.assertTrue(ledger.reserve(ts_ms=NOW,event_id="bull:234",worst_usd=.05))
            self.assertAlmostEqual(ledger.remaining(ts_ms=NOW),.025)
            # Existing reservations are never erased; new UTC day gets own cap.
            next_day=NOW+24*3600*1000
            self.assertAlmostEqual(ledger.remaining(ts_ms=next_day),.10)
            self.assertTrue(ledger.reserve(ts_ms=next_day,event_id="hawk:next",worst_usd=.10))

    def test_portfolio_alert_record_has_three_lanes_per_short(self):
        positions=[p(1),p(2)]
        alarm={"applied":False,"active":True,"event_id":"alert-one",
               "position_keys":[position_key(x) for x in positions]}
        report=comparison_portfolio_alert(alarm,positions,now_ms=NOW,
            operational_by_key={position_key(positions[0]):{"action":"HOLD_TP","reason":"safe"}},
            shadow_by_key={position_key(positions[0]):{"action":"CLOSE_FULL","reason":"risk"}},
            deepseek_by_symbol={"BTC":{"symbol":"BTC","action":"HOLD","ts_ms":NOW,
                                       "same_position_context":False}})
        self.assertFalse(report["applied"])
        self.assertFalse(report["executed"])
        self.assertEqual(len(report["position_comparisons"]),2)
        self.assertEqual(report["position_comparisons"][0]["claude_self_comparison"],"diverge")
        self.assertEqual(report["position_comparisons"][1]["claude_self_comparison"],"unknown")
        self.assertFalse(report["position_comparisons"][0]["deepseek_shadow"]["present"])

if __name__=="__main__":unittest.main()
