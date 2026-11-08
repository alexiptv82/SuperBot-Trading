"""Claude RC84 probe (not committed): Telegram on non-protective PAPER close paths."""
import json
import time

import pytest

import desk.cli as cli
from backend.tests.test_v3_rc82_active_paper_stops import BAR, BASE, NOW, _history, _open, _state, desk  # noqa: F401


def _flat_rows():
    # bar inside SL/TP: no protective exit
    return [[BASE - BAR, 100, 100.5, 99.5, 100, 1]]


def test_probe_rule_close_announces_even_if_state_save_fails(desk, monkeypatch):
    sent = []
    monkeypatch.setattr(cli, "notify_close", lambda *a: sent.append(a))
    cli.fetch_candles = lambda sym, bar="15m", limit=1000: _flat_rows() if sym == "BTC" else []
    cli.rules_decisions = lambda *_a, **_k: [{"symbol": "BTC", "action": "close", "reason": "probe"}]
    state = _state(_open(1, 98.0, 110.0, BASE - 3 * BAR))
    monkeypatch.setattr(cli, "save_state", lambda *_a: (_ for _ in ()).throw(OSError("save_fail")))
    try:
        cli.run_cycle(state, NOW)
    except Exception:
        pass
    print("RULE_CLOSE save_fail -> telegram sent:", len(sent))
    assert sent == [], "Telegram announced a close whose state save failed"


def test_probe_rule_close_announces_even_if_history_not_written(desk, monkeypatch):
    sent = []
    monkeypatch.setattr(cli, "notify_close", lambda *a: sent.append(a))
    monkeypatch.setattr(cli, "append_trade_history", lambda *_a, **_k: None)
    cli.fetch_candles = lambda sym, bar="15m", limit=1000: _flat_rows() if sym == "BTC" else []
    cli.rules_decisions = lambda *_a, **_k: [{"symbol": "BTC", "action": "close", "reason": "probe"}]
    state = _state(_open(1, 98.0, 110.0, BASE - 3 * BAR))
    try:
        cli.run_cycle(state, NOW)
    except Exception:
        pass
    print("RULE_CLOSE history_absent -> telegram sent:", len(sent), "history rows:", len(_history(desk)))
    assert not (sent and not _history(desk)), "Telegram announced a close absent from trade history"


def test_probe_manual_close_announces_even_if_state_save_fails(desk, monkeypatch):
    sent = []
    monkeypatch.setattr(cli, "notify_close", lambda *a: sent.append(a))
    state = _state(_open(1, 98.0, 110.0, BASE - 3 * BAR))
    (desk / "close_position.flag").write_text(json.dumps({"symbols": ["BTC"], "ts": int(time.time() * 1000)}))
    monkeypatch.setattr(cli, "save_state", lambda *_a: (_ for _ in ()).throw(OSError("save_fail")))
    cli._check_close_position_flag(state, price_provider=lambda syms, st, now: {"BTC": 101.0})
    print("MANUAL_CLOSE save_fail -> telegram sent:", len(sent))
    assert sent == [], "Telegram announced a manual close whose state save failed"
