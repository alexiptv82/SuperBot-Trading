"""F3 isolated tests. Ephemeral synthetic keys only; no provider calls or live data."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from backend.v3.brain_f2.engine import _policy_hash
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus
from backend.v3.brain_f3.authorization import (
    TrustedOperatorKey, SignedPolicyVerifier, canonical_policy_sha256, receipt_payload,
)
from backend.v3.brain_f3.providers import (
    DeepSeekAnalystAdapter, ClaudeReviewerAdapter, ProviderUnavailable, TransportResponse,
)

NOW = 1_800_000_000_000


@dataclass(frozen=True)
class PolicyFixture:
    max_loss_fraction: Decimal = Decimal(".02")
    max_open_risk_fraction: Decimal = Decimal(".05")
    max_position_margin_fraction: Decimal = Decimal(".1")
    max_total_margin_fraction: Decimal = Decimal(".3")
    minimum_equity: Decimal = Decimal("450")
    estimated_roundtrip_cost_bp: Decimal = Decimal("16")
    liquidation_buffer_fraction: Decimal = Decimal(".5")
    max_loss_margin_fraction: object = None
    min_leverage: int = 1
    max_leverage: int = 125


POLICY = PolicyFixture()
CTX = MarketContext("BTCUSDT", Decimal("100"), NOW, "TRENDING")


def sign_fixture(*, operator="operator", policy=POLICY):
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw,
                                         serialization.PublicFormat.Raw).hex()
    trusted = TrustedOperatorKey("key-1", operator, pub)
    r = {"purpose": "superbot.v3.brain.paper.risk_policy", "version": "v1",
         "approved": True, "approved_by": operator, "portfolio_id": "brain",
         "run_id": "f3-run-01", "policy_hash": _policy_hash(policy),
         "policy_sha256": canonical_policy_sha256(policy),
         "approval_id": "receipt-1", "key_id": "key-1",
         "issued_at_ms": NOW - 1000, "expires_at_ms": NOW + 60000,
         "signature": "0" * 128}
    r["signature"] = priv.sign(receipt_payload(r)).hex()
    return r, trusted


def verifier(key=None, *, revoked=(), clock=NOW):
    return SignedPolicyVerifier([key] if key else (), revoked_approvals=revoked,
                                clock_ms=lambda: clock)


def test_valid_operator_signature_verifies_without_private_key():
    receipt, key = sign_fixture()
    assert verifier(key)(receipt, POLICY) is True
    assert verifier()(receipt, POLICY) is False


@pytest.mark.parametrize("field,bad", [
    ("approved", False), ("approved", 1), ("approved_by", "system-admin"),
    ("portfolio_id", "hawk"), ("run_id", "other"), ("policy_hash", "0" * 16),
    ("policy_sha256", "0" * 64), ("key_id", "foreign"),
    ("approval_id", "replay-1"), ("version", "v2"),
    ("purpose", "other"), ("issued_at_ms", NOW + 1),
    ("expires_at_ms", NOW), ("issued_at_ms", True),
    ("signature", "0" * 128),
])
def test_tampering_any_signed_field_fails_closed(field, bad):
    receipt, key = sign_fixture()
    receipt[field] = bad
    assert verifier(key)(receipt, POLICY) is False


def test_expiration_revocation_wrong_policy_and_extra_field():
    receipt, key = sign_fixture()
    assert verifier(key, clock=NOW + 60000)(receipt, POLICY) is False
    assert verifier(key, revoked=["receipt-1"])(receipt, POLICY) is False
    wrong = PolicyFixture(minimum_equity=Decimal("451"))
    assert verifier(key)(receipt, wrong) is False
    receipt["untrusted_extra"] = "token"
    assert verifier(key)(receipt, POLICY) is False


def test_foreign_operator_approval_and_duplicate_anchor_rejected():
    receipt, key = sign_fixture(operator="system-admin")
    assert verifier(key)(receipt, POLICY) is True
    with pytest.raises(ValueError):
        SignedPolicyVerifier([key, key])
    with pytest.raises(ValueError):
        SignedPolicyVerifier([TrustedOperatorKey("k", "visitor", "0" * 64)])


def test_nonfinite_policy_and_untrusted_clock_fail_closed():
    receipt, key = sign_fixture()
    assert verifier(key, clock=1.5)(receipt, POLICY) is False
    broken = PolicyFixture(max_loss_fraction=Decimal("NaN"))
    assert verifier(key)(receipt, broken) is False


def test_oversized_ttl_fails_even_with_valid_signature():
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw,
                                         serialization.PublicFormat.Raw).hex()
    key = TrustedOperatorKey("key-1", "operator", pub)
    r, _ = sign_fixture()
    r["expires_at_ms"] = NOW + 25 * 3600000
    r["signature"] = priv.sign(receipt_payload(r)).hex()
    assert verifier(key)(r, POLICY) is False


def deepseek_response(obj, *, status=200, finish="stop"):
    return TransportResponse(status, {"choices": [
        {"finish_reason": finish, "message": {"content": json.dumps(obj)}}
    ]})


def claude_response(obj, *, status=200, stop="end_turn"):
    return TransportResponse(status, {"stop_reason": stop, "content": [
        {"type": "text", "text": json.dumps(obj)}]})


def test_deepseek_disabled_by_default_no_transport_call():
    calls = []
    a = DeepSeekAnalystAdapter(model="deepseek-flash", transport=lambda p: calls.append(p))
    with pytest.raises(ProviderUnavailable):
        a.analyze(CTX, [])
    assert calls == []


def test_deepseek_budget_gate_must_return_exact_true():
    calls = []
    a = DeepSeekAnalystAdapter(model="deepseek-flash", enabled=True,
                               spending_gate=lambda _: 1,
                               transport=lambda p: calls.append(p))
    with pytest.raises(ProviderUnavailable):
        a.analyze(CTX, [])
    assert calls == []


def test_deepseek_no_trade_and_non_executable_open():
    calls = []
    def transport(p):
        calls.append(p)
        return deepseek_response({"kind": "NO_TRADE"} if len(calls) == 1 else {
            "kind": "OPEN", "side": -1, "entry_price": "100", "stop_price": "101",
            "leverage": 20, "confidence": 0.6})
    a = DeepSeekAnalystAdapter(model="deepseek-flash", enabled=True,
                               spending_gate=lambda _: True, transport=transport)
    assert a.analyze(CTX, []).kind == DecisionKind.NO_TRADE
    second = a.analyze(CTX, [{"private_wallet": "SYNTHETIC_SECRET"}])
    assert second.kind == DecisionKind.OPEN
    assert second.status == ProposalStatus.DRAFT
    assert second.proposal.originating_ai == "deepseek"
    assert second.proposal.side == -1
    assert "SYNTHETIC_SECRET" not in repr(calls)
    assert "SYNTHETIC_SECRET" not in repr(second)
    assert calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("response", [
    deepseek_response({"kind": "OPEN", "side": 1, "entry_price": "100", "stop_price": "99", "leverage": 2, "confidence": "0.9"}),
    deepseek_response({"kind": "OPEN", "side": True, "entry_price": "100", "stop_price": "99", "leverage": 2, "confidence": 0.9}),
    deepseek_response({"kind": "CLOSE"}),
    deepseek_response({"kind": "NO_TRADE", "raw": "SYNTHETIC_SECRET"}),
    deepseek_response({"kind": "NO_TRADE"}, status=402),
    deepseek_response({"kind": "NO_TRADE"}, finish="length"),
    TransportResponse(200, {"choices": [{"finish_reason": "stop", "message": {"content": "{\"kind\":\"NO_TRADE\",\"kind\":\"OPEN\"}"}}]}),
])
def test_deepseek_fails_closed_on_untrusted_or_incomplete_response(response):
    a = DeepSeekAnalystAdapter(model="deepseek-flash", enabled=True,
                               spending_gate=lambda _: True, transport=lambda _: response)
    with pytest.raises(ProviderUnavailable) as exc:
        a.analyze(CTX, [])
    assert "SYNTHETIC_SECRET" not in str(exc.value)


def mk_open_decision():
    return BrainDecision(DecisionKind.OPEN, proposal=OpenProposal(
        "BTCUSDT", 1, Decimal("100"), Decimal("99"), 2, "sanitized",
        0.4, "deepseek", "a" * 64), occurred_at_ms=NOW)


def test_claude_review_selective_approve_never_bypasses_risk():
    calls = []
    r = ClaudeReviewerAdapter(model="claude-test", enabled=True,
                              spending_gate=lambda _: True,
                              transport=lambda p: (calls.append(p), claude_response({"verdict": "APPROVE"}))[1])
    decision = r.review(mk_open_decision(), "complex_case")
    assert decision.kind == DecisionKind.OPEN
    assert decision.status == ProposalStatus.DRAFT
    assert decision.rationale == "claude:review"
    assert calls[0]["max_tokens"] == 128


def test_claude_reject_clears_proposal():
    r = ClaudeReviewerAdapter(model="claude-test", enabled=True,
                              spending_gate=lambda _: True,
                              transport=lambda p: claude_response({"verdict": "REJECT"}))
    d = r.review(mk_open_decision(), "complex_case")
    assert d.kind == DecisionKind.NO_TRADE and d.proposal is None
    assert d.status == ProposalStatus.REJECTED


@pytest.mark.parametrize("response", [
    claude_response({"verdict": "APPROVE"}, status=429),
    claude_response({"verdict": "APPROVE", "secret": "SYNTHETIC_SECRET"}),
    claude_response({"verdict": "APPROVE"}, stop="max_tokens"),
    TransportResponse(200, {"stop_reason": "end_turn", "content": []}),
])
def test_claude_fails_closed_on_bad_responses(response):
    r = ClaudeReviewerAdapter(model="claude-test", enabled=True,
                              spending_gate=lambda _: True, transport=lambda p: response)
    with pytest.raises(ProviderUnavailable) as exc:
        r.review(mk_open_decision(), "complex_case")
    assert "SYNTHETIC_SECRET" not in str(exc.value)


def test_transport_exception_redacted():
    def transport(_):
        raise RuntimeError("API_KEY=SYNTHETIC_SECRET")
    a = DeepSeekAnalystAdapter(model="deepseek-flash", enabled=True,
                               spending_gate=lambda _: True, transport=transport)
    with pytest.raises(ProviderUnavailable) as exc:
        a.analyze(CTX, [])
    assert "SYNTHETIC_SECRET" not in str(exc.value)
