"""Offline-only tests: never call Claude or exchange endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import threading
import time

from backend.v3.brain_f2.analyst import Analyst
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, OpenProposal
from backend.v3.brain_f3.providers import TransportResponse
from backend.v3.runner.fable_shadow import (
    FableLedger, FableShadowAdviser, ShadowFableAnalyst, MONTHLY_CAP_MICRO,
    MAX_TOKENS, MODEL, _read_opinion, _usage_cost_micro,
)


def clock_at(day: int, hour: int = 10) -> int:
    return int(datetime(2026, 11, day, hour, tzinfo=timezone.utc).timestamp() * 1000)


def decision(ts: int, *, leverage: int = 45) -> BrainDecision:
    return BrainDecision(
        kind=DecisionKind.OPEN,
        proposal=OpenProposal(
            symbol="BTCUSDT", side=1, entry_price=Decimal("100"),
            stop_price=Decimal("98"), leverage=leverage,
            rationale="deepseek:analysis", confidence=0.8,
            originating_ai="deepseek", context_hash="abc",
        ),
        occurred_at_ms=ts,
    )


def market(ts: int, symbol: str = "BTCUSDT", regime: str = "TRENDING") -> MarketContext:
    return MarketContext(symbol=symbol, price=Decimal("100"), timestamp_ms=ts, regime=regime)


def successful(_payload) -> TransportResponse:
    body = {
        "usage": {"input_tokens": 480, "output_tokens": 330},
        "content": [{
            "type": "text",
            "text": json.dumps({"assessment": "caution",
                                "risk_code": "leverage",
                                "summary": "High leverage increases liquidation sensitivity."}),
        }],
    }
    return TransportResponse(status_code=200, body=body)


def _drain(shadow: ShadowFableAnalyst) -> None:
    """Wait for a mocked shadow worker, never for a real provider."""
    assert shadow._pending.acquire(timeout=3)
    shadow._pending.release()


def ledger(tmp_path, *, run="brain-001", clock=None) -> FableLedger:
    return FableLedger(
        tmp_path / "shared" / "fable_budget.db", run,
        clock_ms=clock or (lambda: clock_at(11)),
    )


def test_fable_id_and_monthly_cap_are_explicit():
    assert MODEL == "claude-fable-5-2"
    assert MONTHLY_CAP_MICRO == 5_000_000
    assert MAX_TOKENS <= 1536


def test_off_by_default_no_calls_or_reservations(tmp_path):
    l = ledger(tmp_path)
    calls = []
    def fake(payload):
        calls.append(payload)
        return successful(payload)
    adviser = FableShadowAdviser(ledger=l, transport=fake, enabled=False)
    adviser.observe(market(clock_at(11)), decision(clock_at(11)))
    assert calls == []
    assert l.monthly_reserved_micro() == 0
    l.close()


def test_shadow_returns_exact_same_deepseek_object_and_only_saves_advice(tmp_path):
    l = ledger(tmp_path)
    original = decision(clock_at(11))
    class DeepSeek(Analyst):
        def analyze(self, context, positions):
            return original
    calls = []
    def fake(payload):
        calls.append(payload)
        return successful(payload)
    shadow = ShadowFableAnalyst(DeepSeek(),
                               FableShadowAdviser(ledger=l, transport=fake, enabled=True))
    result = shadow.analyze(market(clock_at(11)), [])
    _drain(shadow)
    assert result is original  # ZERO influence on execution/risk gate/decision
    assert len(calls) == 1
    assert calls[0]["model"] == MODEL
    assert calls[0]["max_tokens"] <= 1536
    assert calls[0]["output_config"]["effort"] == "low"
    assert l.monthly_reserved_micro() > 0
    row = l._db.execute("SELECT status, assessment, risk_code, actual_micro FROM fable_results").fetchone()
    assert row == ("ok", "caution", "leverage", (480*8 + 330*40))
    l.close()


def test_budget_atomic_across_restarts_and_different_brain_run_ids(tmp_path):
    now = [clock_at(11)]
    db = tmp_path / "fable-shared.db"
    l1 = FableLedger(db, "brain-20261111", clock_ms=lambda: now[0])
    l2 = FableLedger(db, "brain-future", clock_ms=lambda: now[0])
    def reserve(l, n):
        return l.eligible_and_reserve(
            symbol="BTCUSDT", market_ms=now[0], regime="VOLATILE",
            decision=decision(now[0]), reserve_micro=1_000_000,
            request_id="different-" + str(n),
        )
    assert reserve(l1, 0) == "volatile_open"
    # 6-hour cooldown prevents another immediate request even with new run.
    assert reserve(l2, 1) is None
    for i,day in enumerate((12, 13, 14, 15), start=1):
        now[0] = clock_at(day)
        assert reserve(l2 if i % 2 else l1, i) == "volatile_open"
    assert l1.monthly_reserved_micro() == MONTHLY_CAP_MICRO
    l1.close()
    l2.close()
    l3 = FableLedger(db, "brain-third", clock_ms=lambda: clock_at(16))
    now[0] = clock_at(16)
    assert reserve(l3, 7) is None
    assert l3.monthly_reserved_micro() == MONTHLY_CAP_MICRO
    l3.close()


def test_next_month_resets_only_calendar_month(tmp_path):
    now = [clock_at(11)]
    l = ledger(tmp_path, clock=lambda: now[0])
    assert l.eligible_and_reserve(
        symbol="BTCUSDT", market_ms=now[0], regime="VOLATILE",
        decision=decision(now[0]), reserve_micro=1_000_000,
        request_id="november",
    ) == "volatile_open"
    now[0] = int(datetime(2026,12,1,tzinfo=timezone.utc).timestamp()*1000)
    assert l.monthly_reserved_micro() == 0
    l.close()


def test_duplicate_request_never_calls_provider_twice(tmp_path):
    l=ledger(tmp_path)
    calls = []
    def fake(payload):
        calls.append(1)
        return successful(payload)
    adviser=FableShadowAdviser(ledger=l, transport=fake, enabled=True)
    context=market(clock_at(11))
    dec=decision(clock_at(11))
    adviser.observe(context,dec)
    adviser.observe(context,dec)
    assert len(calls)==1
    assert l._db.execute("SELECT COUNT(*) FROM fable_reservations").fetchone()[0]==1
    l.close()


def test_provider_error_consumes_reserved_allowance_and_never_changes_decision(tmp_path):
    l=ledger(tmp_path)
    d=decision(clock_at(11))
    class Primary(Analyst):
        def analyze(self,context,open_positions):
            return d
    def fail(_):
        raise RuntimeError("fake_network_error")
    wrapped=ShadowFableAnalyst(
        Primary(),FableShadowAdviser(ledger=l,transport=fail,enabled=True))
    assert wrapped.analyze(market(clock_at(11)),[]) is d
    _drain(wrapped)
    assert l.monthly_reserved_micro()>0
    assert l._db.execute("SELECT status FROM fable_results").fetchone()[0]=="provider_error"
    l.close()


def test_opinion_json_strict_and_token_accounting_fails_closed():
    assert _read_opinion({"content":[{"type":"text","text":'{"assessment":"support","risk_code":"none","summary":"OK"}'}]}) == ("support","none","OK")
    assert _read_opinion({"content":[{"type":"text","text":'{"assessment":"support","risk_code":"none","summary":"OK","assessment":"caution"}'}]}) is None
    assert _read_opinion({"content":[{"type":"text","text":'{"assessment":"DROP","risk_code":"none","summary":"NO"}'}]}) is None
    assert _usage_cost_micro({"usage":{"input_tokens":100,"output_tokens":100}})==4800
    assert _usage_cost_micro({"usage":{"input_tokens":100,"output_tokens":100000}}) is None


def test_no_trade_does_not_spend_without_a_true_regime_transition(tmp_path):
    l=ledger(tmp_path)
    calls=[]
    def fake(payload):
        calls.append(1)
        return successful(payload)
    adviser=FableShadowAdviser(ledger=l,transport=fake,enabled=True)
    timestamp=clock_at(11)
    no_trade=BrainDecision(kind=DecisionKind.NO_TRADE,occurred_at_ms=timestamp)
    adviser.observe(market(timestamp,regime="TRENDING"),no_trade)
    adviser.observe(market(timestamp + 1,regime="TRENDING"),no_trade)
    assert calls==[]
    adviser.observe(market(timestamp+2,regime="VOLATILE"),no_trade)
    assert calls==[1]
    l.close()

def test_slow_fable_never_blocks_deepseek_and_skips_concurrent_calls(tmp_path):
    l = ledger(tmp_path)
    ready, release = threading.Event(), threading.Event()
    calls = []
    d = decision(clock_at(11))
    class Primary(Analyst):
        def analyze(self, context, positions):
            return d
    def deliberately_slow(payload):
        calls.append(1)
        ready.set()
        assert release.wait(3)
        return successful(payload)
    wrapper = ShadowFableAnalyst(
        Primary(), FableShadowAdviser(ledger=l, transport=deliberately_slow, enabled=True))
    started = time.monotonic()
    assert wrapper.analyze(market(clock_at(11)), []) is d
    assert time.monotonic() - started < 0.2
    assert ready.wait(2)
    # Previous consultation is still running. Brain must continue immediately.
    started = time.monotonic()
    assert wrapper.analyze(market(clock_at(11)+1), []) is d
    assert time.monotonic() - started < 0.2
    assert calls == [1]
    release.set()
    _drain(wrapper)
    assert l.monthly_reserved_micro() > 0
    l.close()
