"""Input equivalente nel laboratorio LLM: la richiesta e' quella del vero analista L5, uguale per ogni braccio,
costruita solo con dati noti all'istante della decisione e senza dati del conto. Offline, nessun provider."""
from __future__ import annotations

import copy
import json
from decimal import Decimal

import pytest

from backend.tests.test_v3_brain_market_l5 import T, make_bars, small_params
from backend.tests.test_v3_llm_cost_lab import Script, chat, sample
from backend.v3.brain_market.deepseek_l5 import SYSTEM_PROMPT
from backend.v3.brain_view.menu import build_menu
from backend.v3.brain_view.params import ViewParams
from backend.v3.features.indicators import Bar
from backend.v3.knowledge.library import load_library
from backend.v3.llm_cost_lab import equivalent as EQ
from backend.v3.llm_cost_lab.equivalent import (
    assert_no_account_data, bars_until, capture_l5_request, outcomes_until, request_fingerprint, request_for,
)
from backend.v3.llm_cost_lab.models import CANDIDATES, ModelSpec
from backend.v3.llm_cost_lab.shadow import ShadowSession
from backend.v3.llm_cost_lab.store import ShadowStore

D = Decimal
VIEW = ViewParams(3, 2, D("0.90"), 200, 20261105, 12)


@pytest.fixture(scope="module")
def world():
    p = small_params()
    bars = {s.name: make_bars(40, s.candle_ms, seed=90 + j) for j, s in enumerate(p.timeframes)}
    return p, bars, build_menu(load_library())


def capture(world, t=T, bars=None, outcomes=(), count=0, **kw):
    p, b, menu = world
    return capture_l5_request(symbol="BTCUSDT", t_ms=t, bars_by_tf=b if bars is None else bars, outcomes=list(outcomes),
                              open_position_count=count, view_params=VIEW, market_params=p, menu=menu, **kw)


def user(payload):
    return json.loads(payload["messages"][1]["content"])


def test_the_request_is_the_production_l5_request(world):
    payload = capture(world)
    assert payload["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    info = user(payload)
    assert set(info) >= {"symbol", "price", "timestamp_ms", "regime", "open_position_count", "market", "scoreboard",
                         "strategies"}
    assert info["timestamp_ms"] == T and info["market"]["timeframes"] and info["strategies"]


def test_every_arm_receives_the_same_request_except_the_model_name(world):
    payload = capture(world)
    reqs = [request_for(payload, spec) for spec in CANDIDATES]
    assert [r["model"] for r in reqs] == [s.model_id for s in CANDIDATES]
    assert len({request_fingerprint(r) for r in reqs}) == 1
    assert all({k: v for k, v in r.items() if k != "model"} == {k: v for k, v in payload.items() if k != "model"}
               for r in reqs)


def test_future_bars_cannot_enter_the_request(world):
    p, bars, _ = world
    base = capture(world)
    later = copy.deepcopy(bars)
    for spec in p.timeframes:
        last = later[spec.name][-1]
        later[spec.name].append(Bar(last.open_time_ms + spec.candle_ms, last.close, last.close * 2, last.close / 2,
                                    last.close * 2, D("9")))                    # candela che chiude DOPO t
    assert capture(world, bars=later) == base


def test_bars_until_keeps_only_closed_bars():
    rows = [Bar(0, D(1), D(1), D(1), D(1), D(1)), Bar(60_000, D(1), D(1), D(1), D(1), D(1))]
    assert [b.open_time_ms for b in bars_until({"1m": rows}, {"1m": 60_000}, 119_999)["1m"]] == [0]
    assert len(bars_until({"1m": rows}, {"1m": 60_000}, 120_000)["1m"]) == 2


def test_outcomes_closed_after_the_decision_are_excluded():
    class O:
        def __init__(self, closed):
            self.closed_at_ms = closed
    got = outcomes_until([O(T - 1), O(T), O(T + 1), O(None)], T)
    assert [o.closed_at_ms for o in got] == [T - 1, T]


def test_no_account_amounts_in_the_request(world):
    info = user(capture(world, count=3))
    assert info["open_position_count"] == 3
    text = json.dumps(info).lower()
    for word in ("equity", "balance", "available_cash", "realized_pnl", "api_key", "secret"):
        assert word not in text


def test_shadow_session_with_equivalent_request_records_fingerprint_and_proposal(tmp_path, world):
    payload = capture(world)
    body = chat(json.dumps({"kind": "OPEN", "side": -1, "entry_price": "50000", "stop_price": "50500",
                            "leverage": 3, "confidence": 0.9}))
    poster = Script([body, chat(json.dumps({"kind": "NO_TRADE"})), body])
    seen = []
    def spy(model_id, req):
        seen.append(req)
        return poster(model_id, req)
    lab = ShadowSession(models=CANDIDATES, store=ShadowStore(tmp_path), poster=spy, max_micro_usd=10_000_000)
    rows = lab.evaluate(sample(now=T, asof=T - 60_000, received=T - 30_000), request=payload)
    assert len({r["request_sha256"] for r in rows}) == 1 and all(r["input_kind"] == "equivalent_l5" for r in rows)
    assert [r["messages"] for r in seen] == [payload["messages"]] * 3
    assert rows[0]["proposal"] == {"entry_price": "50000", "stop_price": "50500", "leverage": 3, "executable": True,
                                   "not_executable_reason": None}
    assert "proposal" not in rows[1]
    assert all(r["may_open"] is False and r["shadow"] is True and r["fallback"] is False for r in rows)


def test_wrong_side_stop_is_recorded_as_not_executable(tmp_path, world):
    payload = capture(world)
    body = chat(json.dumps({"kind": "OPEN", "side": 1, "entry_price": "50000", "stop_price": "50500",
                            "leverage": 3, "confidence": 0.9}))
    lab = ShadowSession(models=CANDIDATES[:1], store=ShadowStore(tmp_path), poster=Script([body]),
                        max_micro_usd=10_000_000)
    row = lab.evaluate(sample(now=T, asof=T - 60_000, received=T - 30_000), request=payload)[0]
    assert row["action"] == "LONG" and row["proposal"]["executable"] is False
    assert row["proposal"]["not_executable_reason"] == "stop_wrong_side"


def test_auto_models_cannot_receive_the_request(world):
    payload = capture(world)
    with pytest.raises(ValueError):
        request_for(payload, ModelSpec("X", "auto:smart", "x", "x", D(0), D(0), "x", "x"))


def test_capture_opens_no_socket(world, monkeypatch):
    import socket
    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    assert capture(world)["messages"]


def test_account_data_guard_rejects_amount_keys_anywhere():
    for info in ({"equity": "1"}, {"market": {"x": [{"balance": 2}]}}, {"Available_Cash": 3}):
        with pytest.raises(ValueError, match="account_data_in_request"):
            assert_no_account_data({"messages": [{}, {"content": json.dumps(info)}]})
    assert_no_account_data({"messages": [{}, {"content": json.dumps({"open_position_count": 2})}]})


def test_the_analyst_only_sees_outcomes_closed_by_the_decision_time(world, monkeypatch):
    seen = {}
    real = EQ.DeepSeekL5Analyst

    class Spy(real):
        def __init__(self, **kw):
            seen["outcomes"] = kw["outcomes_source"]()
            seen["bars"] = kw["bars_source"]("BTCUSDT")
            super().__init__(**kw)

    class O:
        def __init__(self, closed):
            self.closed_at_ms = closed
    monkeypatch.setattr(EQ, "DeepSeekL5Analyst", Spy)
    monkeypatch.setattr(EQ, "outcomes_until", lambda outs, t: [o for o in outs if o.closed_at_ms <= t])
    p, bars, menu = world
    try:
        capture(world, outcomes=[O(T - 5), O(T + 5)])
    except Exception:
        pass                                   # oggetti finti: lo scoreboard puo' rifiutarli dopo il filtro
    assert [o.closed_at_ms for o in seen["outcomes"]] == [T - 5]
    step = {s.name: s.candle_ms for s in p.timeframes}
    assert all(b.open_time_ms + step[tf] <= T for tf, rows in seen["bars"].items() for b in rows)


def test_reconstruction_is_verifiable_against_the_hash_the_real_analyst_records(world):
    """Il vero analista calcola context_hash sul messaggio che invia (finisce in paper_open.context_hash)."""
    import hashlib
    from backend.tests.test_v3_brain_market_l5 import OPEN_JSON, TransportRecorder
    from backend.v3.brain_f2.contracts import MarketContext
    from backend.v3.brain_market.deepseek_l5 import DeepSeekL5Analyst
    from backend.v3.brain_market.view import regime_for_context
    p, bars, menu = world
    rec = TransportRecorder(OPEN_JSON)
    real = DeepSeekL5Analyst(transport=rec, model="deepseek-flash", bars_source=lambda s: bars, outcomes_source=lambda: [],
                             view_params=VIEW, market_params=p, menu=menu, spending_gate=lambda v: True, enabled=True)
    ctx = MarketContext("BTCUSDT", bars[p.timeframes[0].name][-1].close, T, regime_for_context(bars, timestamp_ms=T, params=p))
    decision = real.analyze(ctx, [])
    rebuilt = capture(world)
    assert EQ.matches_recorded_context(rebuilt, decision.proposal.context_hash)
    assert EQ.context_sha256(rebuilt) == hashlib.sha256(rec.calls[0]["messages"][1]["content"].encode()).hexdigest()
    later = capture(world, count=1)                           # un'informazione diversa -> hash diverso -> escluso
    assert not EQ.matches_recorded_context(later, decision.proposal.context_hash)
    for bad in (None, "", "x" * 64, 5):
        assert not EQ.matches_recorded_context(rebuilt, bad)
