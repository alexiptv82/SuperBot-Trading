"""Offline tests for F4: HTTP transport factory + budget ledger.

No real HTTP calls, no real API keys, no network.
All transports are injected mocks; budget ledger uses :memory: SQLite.
"""
from __future__ import annotations

import os
import tempfile
import threading
import unittest
from decimal import Decimal
from typing import Any, Mapping
from unittest.mock import patch

import pytest

from backend.v3.brain_f3.providers import (
    ClaudeReviewerAdapter,
    DeepSeekAnalystAdapter,
    ProviderUnavailable,
    TransportResponse,
)
from backend.v3.budget import BudgetLedger
from backend.v3.transport import claude_transport, deepseek_transport


# ---------------------------------------------------------------------------
# Mock transport helpers
# ---------------------------------------------------------------------------

def _ok_deepseek_response(kind: str = "NO_TRADE") -> TransportResponse:
    if kind == "NO_TRADE":
        body = {
            "choices": [{"finish_reason": "stop", "message": {"content": '{"kind":"NO_TRADE"}'}}]
        }
    else:
        body = {
            "choices": [{"finish_reason": "stop", "message": {"content": (
                '{"kind":"OPEN","side":1,"entry_price":"50000","stop_price":"49000",'
                '"leverage":2,"confidence":0.75}'
            )}}]
        }
    return TransportResponse(status_code=200, body=body)


def _ok_claude_response(verdict: str = "APPROVE") -> TransportResponse:
    return TransportResponse(
        status_code=200,
        body={
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": f'{{"verdict":"{verdict}"}}'}],
        },
    )


def _error_transport(_payload: Mapping[str, Any]) -> TransportResponse:
    raise ProviderUnavailable("provider_unavailable")


def _bad_status_transport(_payload: Mapping[str, Any]) -> TransportResponse:
    return TransportResponse(status_code=500, body={})


def _make_gate(allow: bool = True):
    def gate(provider: str) -> bool:
        return allow
    return gate


# ---------------------------------------------------------------------------
# BudgetLedger tests
# ---------------------------------------------------------------------------

class TestBudgetLedger:
    def test_record_and_read_daily_spend(self):
        ledger = BudgetLedger(":memory:")
        assert ledger.daily_spend("deepseek") == 0
        ledger.record_spend("deepseek", units=5)
        ledger.record_spend("deepseek", units=3)
        assert ledger.daily_spend("deepseek") == 8

    def test_session_spend_independent_of_daily(self):
        ledger = BudgetLedger(":memory:")
        ledger.record_spend("claude", units=2)
        assert ledger.session_spend("claude") == 2
        assert ledger.session_spend("deepseek") == 0

    def test_gate_allows_below_limit(self):
        ledger = BudgetLedger(":memory:")
        gate = ledger.spending_gate(
            daily_limits={"deepseek": 100},
            session_limits={"deepseek": 10},
        )
        assert gate("deepseek") is True

    def test_gate_denies_at_daily_limit(self):
        ledger = BudgetLedger(":memory:")
        gate = ledger.spending_gate(daily_limits={"deepseek": 3})
        ledger.record_spend("deepseek", units=3)
        assert gate("deepseek") is False

    def test_gate_denies_exceeds_daily_limit(self):
        ledger = BudgetLedger(":memory:")
        gate = ledger.spending_gate(daily_limits={"deepseek": 3})
        ledger.record_spend("deepseek", units=10)
        assert gate("deepseek") is False

    def test_gate_denies_at_session_limit(self):
        ledger = BudgetLedger(":memory:")
        gate = ledger.spending_gate(
            daily_limits={"deepseek": 1000},
            session_limits={"deepseek": 2},
        )
        ledger.record_spend("deepseek", units=2)
        assert gate("deepseek") is False

    def test_gate_denies_missing_provider(self):
        ledger = BudgetLedger(":memory:")
        gate = ledger.spending_gate(daily_limits={"claude": 100})
        # "deepseek" not in daily_limits → denied
        assert gate("deepseek") is False

    def test_gate_denies_no_limits_configured(self):
        ledger = BudgetLedger(":memory:")
        gate = ledger.spending_gate()
        assert gate("deepseek") is False
        assert gate("claude") is False

    def test_gate_invalid_provider_string(self):
        ledger = BudgetLedger(":memory:")
        gate = ledger.spending_gate(daily_limits={"": 100})
        assert gate("") is False
        assert gate(None) is False  # type: ignore[arg-type]

    def test_separate_providers_independent(self):
        ledger = BudgetLedger(":memory:")
        gate = ledger.spending_gate(
            daily_limits={"deepseek": 10, "claude": 10},
        )
        ledger.record_spend("deepseek", units=10)
        assert gate("deepseek") is False
        assert gate("claude") is True  # untouched

    def test_all_spend_diagnostic(self):
        ledger = BudgetLedger(":memory:")
        ledger.record_spend("deepseek", units=1, metadata={"model": "deepseek-chat"})
        ledger.record_spend("deepseek", units=2)
        rows = ledger.all_spend("deepseek")
        assert len(rows) == 2
        assert rows[0]["units"] == 1
        assert rows[0]["metadata"] == {"model": "deepseek-chat"}
        assert rows[1]["units"] == 2

    def test_record_spend_bad_units_raises(self):
        ledger = BudgetLedger(":memory:")
        with pytest.raises(ValueError):
            ledger.record_spend("deepseek", units=-1)
        with pytest.raises(ValueError):
            ledger.record_spend("deepseek", units=1.5)  # type: ignore[arg-type]

    def test_record_spend_bad_provider_raises(self):
        ledger = BudgetLedger(":memory:")
        with pytest.raises(ValueError):
            ledger.record_spend("", units=1)

    def test_persist_across_instances(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            l1 = BudgetLedger(db_path)
            l1.record_spend("deepseek", units=7)
            l1.close()

            l2 = BudgetLedger(db_path)
            assert l2.daily_spend("deepseek") == 7
            l2.close()
        finally:
            os.unlink(db_path)

    def test_thread_safety(self):
        """Concurrent record_spend from multiple threads must not corrupt totals."""
        ledger = BudgetLedger(":memory:")
        errors = []

        def worker():
            try:
                for _ in range(10):
                    ledger.record_spend("deepseek", units=1)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert ledger.daily_spend("deepseek") == 50


# ---------------------------------------------------------------------------
# transport.py factory tests (using mocked urllib)
# ---------------------------------------------------------------------------

class TestTransportFactory:
    """Test the transport factory functions without hitting the network."""

    def test_deepseek_transport_no_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DEEPSEEK_API_KEY", None)
            transport = deepseek_transport()
            with pytest.raises(ProviderUnavailable):
                transport({})

    def test_claude_transport_no_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            transport = claude_transport()
            with pytest.raises(ProviderUnavailable):
                transport({})

    def test_deepseek_transport_custom_env_var(self):
        """Custom env var name is read at call time."""
        with patch.dict(os.environ, {"MY_DS_KEY": "sk-test"}):
            transport = deepseek_transport(api_key_env="MY_DS_KEY")
            # Should raise ProviderUnavailable from HTTP (not from missing key)
            with patch("urllib.request.urlopen") as mock_open:
                mock_open.side_effect = Exception("simulated network error")
                with pytest.raises(ProviderUnavailable, match="provider_unavailable"):
                    transport({"model": "deepseek-chat"})

    def test_claude_transport_custom_env_var(self):
        with patch.dict(os.environ, {"MY_AN_KEY": "sk-ant-test"}):
            transport = claude_transport(api_key_env="MY_AN_KEY")
            with patch("urllib.request.urlopen") as mock_open:
                mock_open.side_effect = Exception("simulated network error")
                with pytest.raises(ProviderUnavailable, match="provider_unavailable"):
                    transport({"model": "claude-3-haiku-20240307"})

    def test_transport_http_error_raises_provider_unavailable(self):
        import urllib.error
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            transport = deepseek_transport()
            with patch("urllib.request.urlopen") as mock_open:
                mock_open.side_effect = urllib.error.HTTPError(
                    url=None, code=429, msg="Too Many Requests", hdrs=None, fp=None
                )
                with pytest.raises(ProviderUnavailable, match="provider_unavailable"):
                    transport({"model": "deepseek-chat"})

    def test_transport_non_200_raises_provider_unavailable(self):
        """A 200-looking response from urlopen but actually non-200 body raises."""
        # Simulate urlopen returning a non-200 status (unusual but testable)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            transport = deepseek_transport()
            mock_resp = unittest.mock.MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = unittest.mock.MagicMock(return_value=False)
            mock_resp.getcode.return_value = 403
            mock_resp.read.return_value = b'{"error":"forbidden"}'
            with patch("urllib.request.urlopen", return_value=mock_resp):
                with pytest.raises(ProviderUnavailable, match="provider_unavailable"):
                    transport({"model": "deepseek-chat"})

    def test_transport_ok_response(self):
        """200 + valid JSON body → TransportResponse returned."""
        import io, http.client

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            transport = deepseek_transport()
            mock_resp = unittest.mock.MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = unittest.mock.MagicMock(return_value=False)
            mock_resp.getcode.return_value = 200
            mock_resp.read.return_value = b'{"choices":[{"finish_reason":"stop","message":{"content":"{\\"kind\\":\\"NO_TRADE\\"}"}}]}'
            with patch("urllib.request.urlopen", return_value=mock_resp):
                result = transport({"model": "deepseek-chat"})

        assert isinstance(result, TransportResponse)
        assert result.status_code == 200
        assert "choices" in result.body


# ---------------------------------------------------------------------------
# Integration: adapters + mock transport + budget gate
# ---------------------------------------------------------------------------

class TestAdapterWithMockTransport:
    """Verifies that providers.py adapters work correctly with injected transports."""

    def _deepseek_adapter(self, transport, gate=None, enabled=True):
        from backend.v3.brain_f2.contracts import MarketContext
        return DeepSeekAnalystAdapter(
            transport=transport,
            spending_gate=gate or _make_gate(True),
            model="deepseek-chat",
            enabled=enabled,
        )

    def _market_context(self):
        from backend.v3.brain_f2.contracts import MarketContext
        return MarketContext("BTCUSDT", Decimal("50000"), 1700000000000, "TRENDING")

    def test_no_trade_response_parsed(self):
        transport = lambda p: _ok_deepseek_response("NO_TRADE")
        adapter = self._deepseek_adapter(transport)
        from backend.v3.brain_f2.contracts import DecisionKind
        decision = adapter.analyze(self._market_context(), [])
        assert decision.kind == DecisionKind.NO_TRADE
        assert decision.rationale == "deepseek:analysis"

    def test_open_response_parsed(self):
        transport = lambda p: _ok_deepseek_response("OPEN")
        adapter = self._deepseek_adapter(transport)
        from backend.v3.brain_f2.contracts import DecisionKind
        decision = adapter.analyze(self._market_context(), [])
        assert decision.kind == DecisionKind.OPEN
        assert decision.proposal is not None
        assert decision.proposal.side == 1

    def test_budget_gate_deny_raises_provider_unavailable(self):
        transport = lambda p: _ok_deepseek_response()
        gate = _make_gate(False)
        adapter = self._deepseek_adapter(transport, gate=gate)
        with pytest.raises(ProviderUnavailable):
            adapter.analyze(self._market_context(), [])

    def test_disabled_adapter_raises(self):
        transport = lambda p: _ok_deepseek_response()
        adapter = self._deepseek_adapter(transport, enabled=False)
        with pytest.raises(ProviderUnavailable):
            adapter.analyze(self._market_context(), [])

    def test_transport_error_raises_provider_unavailable(self):
        adapter = self._deepseek_adapter(_error_transport)
        with pytest.raises(ProviderUnavailable):
            adapter.analyze(self._market_context(), [])

    def test_claude_reviewer_approve(self):
        from backend.v3.brain_f2.contracts import (
            BrainDecision, DecisionKind, OpenProposal, ProposalStatus,
        )
        transport = lambda p: _ok_claude_response("APPROVE")
        adapter = ClaudeReviewerAdapter(
            transport=transport,
            spending_gate=_make_gate(True),
            model="claude-3-haiku-20240307",
            enabled=True,
        )
        proposal = OpenProposal(
            symbol="BTCUSDT", side=1, entry_price=Decimal("50000"),
            stop_price=Decimal("49000"), leverage=2, rationale="deepseek:analysis",
            confidence=0.8, originating_ai="deepseek", context_hash="abc",
        )
        decision = BrainDecision(
            kind=DecisionKind.OPEN, proposal=proposal,
            rationale="deepseek:analysis", occurred_at_ms=1700000000000,
        )
        result = adapter.review(decision, "test")
        assert result.rationale == "claude:review"
        assert result.kind == DecisionKind.OPEN

    def test_claude_reviewer_reject(self):
        from backend.v3.brain_f2.contracts import (
            BrainDecision, DecisionKind, OpenProposal,
        )
        transport = lambda p: _ok_claude_response("REJECT")
        adapter = ClaudeReviewerAdapter(
            transport=transport,
            spending_gate=_make_gate(True),
            model="claude-3-haiku-20240307",
            enabled=True,
        )
        proposal = OpenProposal(
            symbol="BTCUSDT", side=1, entry_price=Decimal("50000"),
            stop_price=Decimal("49000"), leverage=2, rationale="deepseek:analysis",
            confidence=0.8, originating_ai="deepseek", context_hash="abc",
        )
        decision = BrainDecision(
            kind=DecisionKind.OPEN, proposal=proposal,
            rationale="deepseek:analysis", occurred_at_ms=1700000000000,
        )
        result = adapter.review(decision, "test")
        assert result.kind == DecisionKind.NO_TRADE
        assert result.proposal is None

    def test_budget_ledger_integration_with_adapter(self):
        """Gate from BudgetLedger correctly blocks after session limit reached."""
        ledger = BudgetLedger(":memory:")
        gate = ledger.spending_gate(
            daily_limits={"deepseek": 1000},
            session_limits={"deepseek": 1},
        )
        ledger.record_spend("deepseek", units=1)  # session limit now hit

        transport = lambda p: _ok_deepseek_response()
        adapter = self._deepseek_adapter(transport, gate=gate)
        with pytest.raises(ProviderUnavailable):
            adapter.analyze(self._market_context(), [])
