"""One trade only: reject stale IDs, reused symbols, cross-account and wrong run.

Pure stdlib test suite, PAPER data only; no orders and no files touched.
"""
import copy
import unittest

from director.single_trade_close_contract import (
    SCHEMA, CloseRejected, validate_request, validate_target,
    verified_close_lesson,
)

NOW = 1800000000000

def req(**overrides):
    r = {
        "schema": SCHEMA, "request_id": "ab"*16, "action": "close_full",
        "account_id": "hawk", "run_id": 3, "position_id": 12,
        "symbol": "BTCUSDT", "side": 1, "open_ms": NOW-100000,
        "created_ms": NOW-2000, "confirmed_by_user": True,
        "intent": "profit_sufficient", "mode": "paper",
    }
    r.update(overrides)
    return r

def wallet(**overrides):
    s = {"account_id":"hawk", "run_id":3, "as_of_ms":NOW-200,
         "positions":{
            "BTC": {"id":12, "symbol":"BTC", "side":1,
                    "open_ms":NOW-100000, "qty":1.8},
            "ETH": {"id":21, "symbol":"ETH", "side":-1,
                    "open_ms":NOW-200000,"qty":2.4},
            "SOL": {"id":24, "symbol":"SOL", "side":1,
                    "open_ms":NOW-300000,"qty":3.1},
         }}
    s.update(overrides)
    return s

class SingleTradeContractTests(unittest.TestCase):
    def test_exact_position_is_single_and_non_executable(self):
        w = wallet()
        original = copy.deepcopy(w)
        selection = validate_target(req(), w, now_ms=NOW)
        self.assertEqual(selection["symbol"], "BTC")
        self.assertEqual(selection["position_id"], 12)
        self.assertEqual(selection["other_open_position_count"], 2)
        self.assertEqual(selection["position_count_before"], 3)
        self.assertFalse(selection["may_execute_orders"])
        self.assertFalse(selection["may_change_wallet"])
        self.assertEqual(w, original, "validator must not touch even the target wallet")

    def test_reopened_same_symbol_has_different_id_and_is_rejected(self):
        w = wallet()
        w["positions"]["BTC"]["id"] = 99
        with self.assertRaisesRegex(CloseRejected,"position_identity_changed"):
            validate_target(req(), w, now_ms=NOW)

    def test_reopened_same_id_but_different_open_time_is_rejected(self):
        w=wallet()
        w["positions"]["BTC"]["open_ms"] += 5000
        with self.assertRaisesRegex(CloseRejected,"position_identity_changed"):
            validate_target(req(),w,now_ms=NOW)

    def test_account_and_run_bound_to_request(self):
        for w in (wallet(account_id="bull"), wallet(run_id=4),
                  wallet(run_id="3")):
            with self.subTest(wallet=w):
                with self.assertRaises(CloseRejected):
                    validate_target(req(),w,now_ms=NOW)

    def test_wallet_stale_or_future(self):
        for stamp in (NOW-60000,NOW+8000,True,None):
            with self.subTest(stamp=stamp):
                with self.assertRaisesRegex(CloseRejected,"wallet_stale_or_future"):
                    validate_target(req(),wallet(as_of_ms=stamp),now_ms=NOW)

    def test_confirmed_operator_intent_required(self):
        for v in (False,None,0,"true"):
            with self.subTest(confirmed=v):
                with self.assertRaisesRegex(CloseRejected,"not_user_confirmed"):
                    validate_target(req(confirmed_by_user=v),wallet(),now_ms=NOW)

    def test_reject_expired_or_future_click(self):
        for timestamp in (NOW-100000,NOW+6000):
            with self.subTest(timestamp=timestamp):
                with self.assertRaisesRegex(CloseRejected,"expired_or_future_request"):
                    validate_target(req(created_ms=timestamp,open_ms=NOW-200000),
                                    wallet(),now_ms=NOW)

    def test_duplicate_request_rejected(self):
        with self.assertRaisesRegex(CloseRejected,"duplicate_request_id"):
            validate_target(req(),wallet(),now_ms=NOW,
                            seen_request_ids={"ab"*16})

    def test_cross_position_invalid_side_and_id(self):
        for r in (req(position_id=21),req(side=-1),
                  req(side=True),req(position_id=True)):
            with self.subTest(request=r):
                with self.assertRaises(CloseRejected):
                    validate_target(r,wallet(),now_ms=NOW)

    def test_symbol_not_open(self):
        with self.assertRaisesRegex(CloseRejected,"target_position_not_open"):
            validate_target(req(symbol="DOGE"),wallet(),now_ms=NOW)

    def test_ambiguous_symbol_rejected(self):
        w=wallet()
        w["positions"]["BTCUSDT"]={"id":33,"symbol":"BTCUSDT","side":1,
                                    "open_ms":NOW-5000,"qty":0.5}
        with self.assertRaisesRegex(CloseRejected,"ambiguous_symbol_positions"):
            validate_target(req(),w,now_ms=NOW)

    def test_reject_live_mode_and_non_full(self):
        for r in (req(mode="live"),req(action="close_all"),
                  req(action="partial_close"),req(intent="unknown")):
            with self.subTest(request=r):
                with self.assertRaises(CloseRejected):
                    validate_target(r,wallet(),now_ms=NOW)

    def test_brain_with_independent_run_id(self):
        w=wallet(account_id="brain",run_id="abc9-1234")
        r=req(account_id="brain",run_id="abc9-1234")
        self.assertEqual(validate_target(r,w,now_ms=NOW)["account_id"],"brain")

    def test_verified_closed_trade_generates_draft_not_policy(self):
        r=req()
        after=wallet()
        del after["positions"]["BTC"]
        rec={"persisted":True,"kind":"trade_closed","source":"manual_user",
             "request_id":r["request_id"],"account_id":"hawk","run_id":3,
             "position_id":12,"close_ms":NOW-300,"net_usd":19.5,"margin_usd":100}
        lesson=verified_close_lesson(r,receipt=rec,before_wallet=wallet(),after_wallet=after,now_ms=NOW)
        self.assertEqual(lesson["roi_net_on_margin_pct"],19.5)
        self.assertTrue(lesson["user_confirmation_required"])
        self.assertFalse(lesson["changes_strategy"])

    def test_unverified_close_never_becomes_lesson(self):
        r=req()
        after=wallet()
        del after["positions"]["BTC"]
        receipt={"persisted":False,"kind":"trade_closed","source":"manual_user",
                 "request_id":r["request_id"],"account_id":"hawk","run_id":3,
                 "position_id":12,"close_ms":NOW-300,"net_usd":19.5,"margin_usd":100}
        with self.assertRaisesRegex(CloseRejected,"unattested_manual_close"):
            verified_close_lesson(r,receipt=receipt,before_wallet=wallet(),after_wallet=after,now_ms=NOW)

    def test_open_target_never_becomes_lesson(self):
        r=req()
        receipt={"persisted":True,"kind":"trade_closed","source":"manual_user",
                 "request_id":r["request_id"],"account_id":"hawk","run_id":3,
                 "position_id":12,"close_ms":NOW-300,"net_usd":19.5,"margin_usd":100}
        with self.assertRaisesRegex(CloseRejected,"target_not_yet_closed"):
            verified_close_lesson(r,receipt=receipt,before_wallet=wallet(),after_wallet=wallet(),now_ms=NOW)

    def test_other_positions_must_stay_open_for_attestation(self):
        r=req()
        after=wallet()
        del after["positions"]["BTC"]
        del after["positions"]["ETH"]  # accidental all-close must fail
        receipt={"persisted":True,"kind":"trade_closed","source":"manual_user",
                 "request_id":r["request_id"],"account_id":"hawk","run_id":3,
                 "position_id":12,"close_ms":NOW-300,"net_usd":19.5,"margin_usd":100}
        with self.assertRaisesRegex(CloseRejected,"other_position_changed_or_closed"):
            verified_close_lesson(r,receipt=receipt,before_wallet=wallet(),
                                  after_wallet=after,now_ms=NOW)

    def test_other_trade_reopened_with_same_symbol_is_not_acceptable(self):
        r=req()
        after=wallet()
        del after["positions"]["BTC"]
        after["positions"]["ETH"]["id"]=999
        receipt={"persisted":True,"kind":"trade_closed","source":"manual_user",
                 "request_id":r["request_id"],"account_id":"hawk","run_id":3,
                 "position_id":12,"close_ms":NOW-300,"net_usd":19.5,"margin_usd":100}
        with self.assertRaisesRegex(CloseRejected,"other_position_changed_or_closed"):
            verified_close_lesson(r,receipt=receipt,before_wallet=wallet(),
                                  after_wallet=after,now_ms=NOW)

    def test_learning_rejects_wrong_closed_position(self):
        r=req()
        after=wallet()
        del after["positions"]["BTC"]
        receipt={"persisted":True,"kind":"trade_closed","source":"manual_user",
                 "request_id":r["request_id"],"account_id":"hawk","run_id":3,
                 "position_id":21,"close_ms":NOW-300,"net_usd":19.5,"margin_usd":100}
        with self.assertRaisesRegex(CloseRejected,"unattested_manual_close"):
            verified_close_lesson(r,receipt=receipt,before_wallet=wallet(),after_wallet=after,now_ms=NOW)

    def test_input_is_never_mutated(self):
        r=req();w=wallet()
        r0=copy.deepcopy(r);w0=copy.deepcopy(w)
        validate_target(r,w,now_ms=NOW)
        self.assertEqual(r,r0)
        self.assertEqual(w,w0)

if __name__=="__main__":
    unittest.main()
