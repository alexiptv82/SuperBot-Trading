"""Offline-only regression for new PAPER notifications; never contact Telegram."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2] / "deploy/scripts/rc84-paper-telegram-alert-relay.py"
spec = importlib.util.spec_from_file_location("paper_alert_relay_under_test", SRC)
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


class AlertRelayTests(unittest.TestCase):
    def sample(self):
        ms = 1794416100000
        state = {"run_no": 1, "main": {"positions": {
            "BTCUSDT": {"id": 7, "symbol": "BTCUSDT", "open_ms": ms, "side": 1,
                        "entry": 95000, "total_margin": 350, "leverage": 25, "sl": 94000},
            "ARBUSDT": {"id": 8, "symbol": "ARBUSDT", "open_ms": ms, "side": -1,
                        "entry": 0.19, "total_margin": 250, "leverage": 25, "sl": 0.20},
        }}}
        return ms, state

    def test_existing_two_opens_are_labeled_recovered_paper(self):
        ms, state = self.sample()
        notices = relay._open_events(state, wallet="FALCO", icon="🦅",
                                     now_ms=ms + 100000, observer_started_ms=ms + 50000)
        self.assertEqual(len(notices), 2)
        self.assertTrue(all("AVVISO RECUPERATO" in a[2] and "PAPER" in a[2] for a in notices))
        self.assertEqual(len(set(a[0] for a in notices)), 2)

    def test_new_open_not_recovered(self):
        ms, state = self.sample()
        notices = relay._open_events(state, wallet="TORO", icon="🐂",
                                     now_ms=ms + 50000, observer_started_ms=ms - 100000)
        self.assertEqual(len(notices), 2)
        self.assertTrue(all("TRADE APERTO" in a[2] for a in notices))

    def test_live_malformed_and_pathlike_symbols_skipped(self):
        ms, state = self.sample()
        state["main"]["positions"]["../test"] = state["main"]["positions"]["BTCUSDT"]
        state["main"]["positions"]["X"] = dict(state["main"]["positions"]["BTCUSDT"], open_ms=ms+10**8)
        self.assertEqual(len(relay._open_events(
            state, wallet="FALCO", icon="🦅", now_ms=ms, observer_started_ms=ms)), 2)

    def test_open_durable_dedup_and_retry_not_fake_success(self):
        ms, state = self.sample()
        notices = relay._open_events(state, wallet="FALCO", icon="🦅", now_ms=ms+1000,
                                     observer_started_ms=ms+2000)
        with tempfile.TemporaryDirectory() as tmp:
            db = sqlite3.connect(Path(tmp) / "db", isolation_level=None)
            db.execute("""CREATE TABLE notice(event_id TEXT PRIMARY KEY, wallet TEXT NOT NULL,
                          last_attempt_ms INTEGER NOT NULL DEFAULT 0,
                          delivered_ms INTEGER NOT NULL DEFAULT 0,
                          attempts INTEGER NOT NULL DEFAULT 0)""")
            with patch.object(relay, "_api_call", return_value=True) as net:
                self.assertEqual(relay._dispatch(db, "fake", "fake", notices), 2)
                self.assertEqual(relay._dispatch(db, "fake", "fake", notices), 0)
                self.assertEqual(net.call_count, 2)
            db.close()
            db = sqlite3.connect(Path(tmp) / "db", isolation_level=None)
            with patch.object(relay, "_api_call", return_value=True) as net:
                self.assertEqual(relay._dispatch(db, "fake", "fake", notices), 0)
                net.assert_not_called()
            db.close()

    def test_failure_cannot_claim_notification_delivered(self):
        ms, state = self.sample()
        event = relay._open_events(state, wallet="FALCO", icon="🦅",
                                   now_ms=ms+1000, observer_started_ms=ms+2000)[:1]
        with sqlite3.connect(":memory:", isolation_level=None) as db:
            db.execute("""CREATE TABLE notice(event_id TEXT PRIMARY KEY, wallet TEXT NOT NULL,
                          last_attempt_ms INTEGER NOT NULL DEFAULT 0,
                          delivered_ms INTEGER NOT NULL DEFAULT 0,
                          attempts INTEGER NOT NULL DEFAULT 0)""")
            with patch.object(relay, "_api_call", return_value=False):
                self.assertEqual(relay._dispatch(db, "fake", "fake", event), 0)
            result = db.execute("SELECT delivered_ms, attempts FROM notice").fetchone()
            self.assertEqual(result[0], 0)
            self.assertEqual(result[1], 1)

    def test_close_only_new_records_and_exact_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            history=root/"trade_history.jsonl"
            rec={"id":7,"symbol":"BTCUSDT","open_ms":1794416100000,
                 "close_ms":1794416400000,"side":1,"net":12.8}
            history.write_text(json.dumps(rec)+"\n")
            a=relay._close_events(root,wallet="FALCO",icon="🦅",
                                  since_ms=1794416300000,now_ms=1794416500000)
            self.assertEqual(len(a),1)
            self.assertIn("P&amp;L",a[0][2])
            self.assertEqual(relay._close_events(root,wallet="FALCO",icon="🦅",
                             since_ms=1794416500001,now_ms=1794416600000),[])

    def test_invalid_telegram_credentials_refused_without_network(self):
        with patch.dict(relay.os.environ, {"TELEGRAM_BOT_TOKEN":"bogus",
                                           "TELEGRAM_CHAT_ID":"42"}):
            with self.assertRaisesRegex(RuntimeError,"TELEGRAM_CREDENTIALS"):
                relay._credentials()

    def test_scope_is_exactly_two_paper_classics(self):
        self.assertEqual([a[0] for a in relay.WALLETS], ["FALCO","TORO"])
        self.assertTrue(all("paper20261111" in str(a[2]) for a in relay.WALLETS))


if __name__ == "__main__":
    unittest.main()
