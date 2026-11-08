"""RC82: stop, take-profit e liquidazione del PAPER attivo di Falco/Toro.

Dati sintetici, nessun feed reale, nessuna chiave, nessun ordine. Il motore di prezzo
resta quello di engine.on_bar: questi test fissano solo il ciclo che lo alimenta.
"""
import json
import os
import subprocess
import sys
import time

import pytest

import desk.cli as cli
from desk.engine import PaperAccount
from desk.schedule import reset_cache

BAR = cli.PAPER_BAR_MS
NOW = int(time.time() * 1000)
BASE = (NOW // BAR) * BAR


def _open(side, sl, tp, open_ms, px=100.0):
    account = PaperAccount(cli.PORTFOLIO.limits, "main")
    pos, msg = account.open("BTC", side, 60, 10, px, sl, tp, open_ms, {"BTC": px})
    assert pos is not None, msg
    return account


def _state(account):
    return {"main": account.to_dict(), "last_call_ms": NOW,
            "budget": {"day": "2099-01-01", "spent": 0.0, "calls": 0}}


def _rows_for(btc):
    def fetch(sym, bar="15m", limit=1000):
        return btc if sym == "BTC" else []
    return fetch


@pytest.fixture
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "STATE_FILE", str(tmp_path / "state_v2.json"))
    monkeypatch.setattr(cli.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(cli, "fetch_all_context", lambda *_a, **_k: {"funding": {}, "oi": {}, "news": [], "ts": NOW})
    monkeypatch.setattr(cli, "rules_decisions", lambda *_a, **_k: [])
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    reset_cache()
    return tmp_path


def _cycle(desk, account, rows, decisions=None):
    cli.fetch_candles = lambda sym, bar="15m", limit=1000: rows if sym == "BTC" else []
    if decisions is not None:
        cli.rules_decisions = lambda *_a, **_k: decisions
    state = _state(account)
    cli.run_cycle(state, NOW)
    return cli.make_account(state), state


def _history(desk):
    path = desk / "trade_history.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_missing_feed_keeps_the_position_and_alarms_without_a_certificate(desk):
    acc, _state_out = _cycle(desk, _open(1, 98.0, 110.0, BASE - 3 * BAR), [])
    feed = cli.HB["stop_feed"]
    assert "BTC" in acc.positions
    assert feed["symbols"]["BTC"]["status"] == "missing"
    assert feed["alarm"] is True and feed["stop_certified"] is False
    assert cli.HB["stop_certified"] is False
    assert _history(desk) == []


def test_future_bar_and_zero_low_do_not_liquidate(desk):
    future, _ = _cycle(desk, _open(1, 98.0, 110.0, BASE - 3 * BAR), [[NOW + BAR, 100, 100, 90, 99, 1]])
    assert "BTC" in future.positions and future.closed == []
    assert cli.HB["stop_feed"]["symbols"]["BTC"]["status"] == "future"
    zero, _ = _cycle(desk, _open(1, 98.0, 110.0, BASE - 3 * BAR), [[BASE - BAR, 100, 100, 0, 99, 1]])
    assert "BTC" in zero.positions and zero.closed == []
    assert cli.HB["stop_feed"]["symbols"]["BTC"]["status"] == "unusable"
    assert _history(desk) == []


def test_stale_feed_alarms_but_a_printed_stop_still_closes_once(desk):
    quiet = [[NOW - 6 * 3_600_000, 100, 101, 99.5, 100, 1]]
    acc, _ = _cycle(desk, _open(1, 98.0, 110.0, NOW - 9 * 3_600_000), quiet)
    assert "BTC" in acc.positions
    assert cli.HB["stop_feed"]["symbols"]["BTC"]["status"] == "stale"
    assert cli.HB["stop_feed"]["alarm"] is True
    hit = [[NOW - 6 * 3_600_000, 100, 101, 97, 100, 1]]
    closed, _ = _cycle(desk, _open(1, 98.0, 110.0, NOW - 9 * 3_600_000), hit)
    assert "BTC" not in closed.positions
    assert closed.closed[-1]["why"] == "stop loss"
    assert cli.HB["stop_feed"]["alarm"] is True
    assert len(_history(desk)) == 1


def test_closed_bar_stop_beats_a_same_cycle_dca_that_would_widen_it(desk):
    decisions = [{"symbol": "BTC", "action": "dca", "confidence": 80, "leverage": 10,
                  "margin_usd": 60, "stop_loss_pct": 0.05, "take_profit_pct": 0.2,
                  "dca_sl_pct": 0.05, "dca_tp_pct": 0.2, "reason": "allarga", "trade_type": "medio"}]
    bar = [[BASE - BAR, 100, 101, 97, 100, 1]]
    acc, _ = _cycle(desk, _open(1, 98.0, 120.0, BASE - 3 * BAR), bar, decisions)
    assert "BTC" not in acc.positions
    assert acc.closed[-1]["why"] == "stop loss"
    assert acc.closed[-1]["dca_count"] == 0
    assert len(_history(desk)) == 1


def test_a_stop_tightened_in_the_same_cycle_is_checked_on_the_second_pass(desk):
    decisions = [{"symbol": "BTC", "action": "dca", "confidence": 80, "leverage": 10,
                  "margin_usd": 60, "stop_loss_pct": 0.02, "take_profit_pct": 0.2,
                  "dca_sl_pct": 0.02, "dca_tp_pct": 0.2, "reason": "stringe", "trade_type": "medio"}]
    bar = [[BASE - BAR, 100, 101, 97, 100, 1]]
    acc, _ = _cycle(desk, _open(1, 94.0, 120.0, BASE - 3 * BAR), bar, decisions)
    assert acc.closed[-1]["why"] == "stop loss"
    assert acc.closed[-1]["dca_count"] == 1


def test_valid_short_stop_and_long_take_profit_still_use_the_bar(desk):
    short, _ = _cycle(desk, _open(-1, 103.0, 90.0, BASE - 3 * BAR), [[BASE - BAR, 100, 104, 99, 101, 1]])
    assert short.closed[-1]["why"] == "stop loss"
    assert short.closed[-1]["exit"] > 103.0
    long, _ = _cycle(desk, _open(1, 94.0, 103.0, BASE - 3 * BAR), [[BASE - BAR, 100, 104, 99, 101, 1]])
    assert long.closed[-1]["why"] == "take profit"


def test_forming_15m_wick_still_stops_and_the_entry_candle_does_not(desk):
    forming, _ = _cycle(desk, _open(1, 98.0, 110.0, BASE - 2 * BAR), [[BASE, 100, 101, 97, 100.4, 1]])
    assert forming.closed[-1]["why"] == "stop loss"
    entry = _open(1, 98.0, 110.0, BASE + 60_000)
    kept, _ = _cycle(desk, entry, [[BASE, 100, 101, 90, 100, 1]])
    assert "BTC" in kept.positions and kept.closed == []


def test_failed_save_then_restart_does_not_duplicate_paper_history(desk, monkeypatch):
    account = _open(1, 98.0, 110.0, BASE - 3 * BAR)
    original = account.to_dict()
    real_save = cli.save_state
    cli.fetch_candles = lambda sym, bar="15m", limit=1000: (
        [[BASE - BAR, 100, 101, 97, 99, 1]] if sym == "BTC" else [])

    def boom(*_a, **_k):
        raise OSError("disk")

    monkeypatch.setattr(cli, "save_state", boom)
    with pytest.raises(OSError):
        cli.run_cycle(_state(account), NOW)
    assert len(_history(desk)) == 1
    monkeypatch.setattr(cli, "save_state", real_save)
    fresh = {"main": original, "last_call_ms": NOW}
    cli.run_cycle(fresh, NOW)
    rows = _history(desk)
    assert len(rows) == 1 and rows[0]["why"] == "stop loss"
    assert "BTC" not in cli.make_account(fresh).positions
    learning = [json.loads(line) for line in (desk / "learning_log.jsonl").read_text().splitlines()]
    assert [row.get("ev") for row in learning].count("close") == 1


def test_scalp_cycle_is_15_minutes_and_medio_is_30():
    account = _open(1, 98.0, 110.0, BASE - 3 * BAR)
    account.positions["BTC"].trade_type = "scalp"
    assert cli.cycle_interval_s({"main": account.to_dict()}, False) == cli.CYCLE_FAST_S == 900
    account.positions["BTC"].trade_type = "medio"
    assert cli.cycle_interval_s({"main": account.to_dict()}, False) == cli.CYCLE_S == 1800


def test_classics_still_call_claude_only_when_the_schedule_and_key_allow_it(desk, monkeypatch):
    calls = []

    def stub(*_a, **_k):
        calls.append(1)
        body = {"decisions": [{"symbol": "BTC", "action": "hold", "confidence": 80, "leverage": 10,
                               "margin_usd": 60, "stop_loss_pct": 0.02, "take_profit_pct": 0.05,
                               "reason": "tieni", "trade_type": "medio"}], "note": ""}
        return json.dumps(body), {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(cli, "build_prompt", lambda *_a, **_k: "prompt")
    monkeypatch.setattr(cli, "call_claude", stub)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-not-a-secret")
    account = _open(1, 94.0, 120.0, BASE - 3 * BAR)
    cli.fetch_candles = lambda sym, bar="15m", limit=1000: (
        [[BASE - BAR, 100, 101, 99, 100, 1]] if sym == "BTC" else [])
    state = _state(account)
    state["last_call_ms"] = 0
    cli.run_cycle(state, NOW)
    assert calls == [1]
    reset_cache()
    (desk / "claude_schedule.json").write_text(json.dumps({
        "version": 1,
        "windows": [{"start": "2030-01-01T00:00:00Z", "end": "2030-01-01T01:00:00Z"}],
    }), encoding="utf-8")
    state["last_call_ms"] = 0
    cli.run_cycle(state, NOW)
    assert calls == [1]


def test_bull_rejects_the_same_future_bar(tmp_path):
    script = r"""
import json, os, tempfile
os.environ["DESK_MODE"] = "paper"
os.environ["DESK_PORTFOLIO"] = "bull"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["DESK_DATA_DIR"] = tempfile.mkdtemp(prefix="rc82-bull-")
import desk.cli as cli
from desk.engine import PaperAccount
BAR = cli.PAPER_BAR_MS
now = 1_700_000_100_000
base = (now // BAR) * BAR
acc = PaperAccount(cli.PORTFOLIO.limits, "main")
pos, msg = acc.open("BTC", 1, 200, 10, 100.0, 98.0, 110.0, base - 3 * BAR, {"BTC": 100.0})
assert pos, msg
cli.DATA_DIR = os.environ["DESK_DATA_DIR"]
cli.STATE_FILE = os.path.join(cli.DATA_DIR, "state_v2.json")
cli.time.sleep = lambda *_a, **_k: None
cli.fetch_all_context = lambda *_a, **_k: {"funding": {}, "oi": {}, "news": [], "ts": now}
cli.rules_decisions = lambda *_a, **_k: []
cli.fetch_candles = lambda sym, bar="15m", limit=1000: ([[now + BAR, 100, 100, 90, 99, 1]] if sym == "BTC" else [])
state = {"main": acc.to_dict(), "last_call_ms": now}
cli.run_cycle(state, now)
out = cli.make_account(state)
print(json.dumps({"portfolio": cli.PORTFOLIO.name, "open": "BTC" in out.positions,
                  "status": cli.HB["stop_feed"]["symbols"]["BTC"]["status"],
                  "certified": cli.HB["stop_certified"]}))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = "backend"
    env["DESK_MODE"] = "paper"
    env.pop("ANTHROPIC_API_KEY", None)
    proc = subprocess.run([sys.executable, "-c", script], cwd=_repo(),
                          env=env, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    line = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")][-1]
    got = json.loads(line)
    assert got == {"portfolio": "bull", "open": True, "status": "future", "certified": False}


def _repo() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
