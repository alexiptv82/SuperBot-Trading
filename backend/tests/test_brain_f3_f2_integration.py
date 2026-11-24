"""Signed policy receipts plugged into real F2 engine with a temporary F1 journal."""
from decimal import Decimal
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from backend.v3.events import EventJournal
from backend.v3.risk import RiskPolicy
from backend.v3.brain_f2.analyst import MockDeepSeekAnalyst
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.brain_f2.contracts import MarketContext, DecisionKind, ProposalStatus
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot, _policy_hash
from backend.v3.brain_f3.authorization import (
    SignedPolicyVerifier, TrustedOperatorKey, canonical_policy_sha256, receipt_payload,
)

NOW = 1_800_000_000_000
POLICY = RiskPolicy(Decimal(".02"), Decimal(".05"), Decimal(".1"), Decimal(".3"),
                    Decimal("450"), Decimal("16"), Decimal(".5"))
MARKET = dict(exchange_leverage_limit=10, quantity_step=Decimal(".001"),
              minimum_notional=Decimal("5"), maintenance_fraction=Decimal(".004"),
              market_data_fresh=True, paused=False, daily_loss_latched=False)


def setup(tmp_path):
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw,
                                         serialization.PublicFormat.Raw).hex()
    m = {"purpose":"superbot.v3.brain.paper.risk_policy", "version":"v1",
         "approved":True, "approved_by":"operator", "portfolio_id":"brain",
         "run_id":"f3-integration", "policy_hash":_policy_hash(POLICY),
         "policy_sha256":canonical_policy_sha256(POLICY), "approval_id":"f3-approval-1",
         "key_id":"key-one", "issued_at_ms":NOW-100, "expires_at_ms":NOW+60000,
         "signature":"0" * 128}
    m["signature"] = priv.sign(receipt_payload(m)).hex()
    j = EventJournal(Path(tmp_path) / "v3-f3.sqlite")
    j.init_schema()
    v = SignedPolicyVerifier([TrustedOperatorKey("key-one", "operator", pub)],
                             clock_ms=lambda: NOW)
    return m, j, v


def engine(m, j, v, run_id="f3-integration"):
    return BrainEngine(MockDeepSeekAnalyst(), MockClaudeReviewer(always_approve=True),
            risk_policy=POLICY, portfolio_snapshot=BrainPortfolioSnapshot(
                Decimal("1000"), Decimal("1000"), Decimal("0"), Decimal("0")),
            market_params=MARKET, journal=j, run_id=run_id, policy_mandate=m,
            policy_verifier=v)


def test_signed_receipt_allows_only_offline_proposal_and_one_journal_event(tmp_path):
    m, j, v = setup(tmp_path)
    decision = engine(m, j, v).step(MarketContext("BTCUSDT", Decimal("50000"), NOW, "TRENDING"))
    assert decision.kind == DecisionKind.OPEN
    assert decision.status == ProposalStatus.APPROVED
    assert len(j.list_run("brain", "f3-integration")) == 1
    assert j.verify_chain()[0] == 1
    assert decision.status != ProposalStatus.EXECUTED_PAPER


def test_signed_receipt_cannot_escape_run_or_revoked_approval(tmp_path):
    m, j, v = setup(tmp_path)
    ctx = MarketContext("BTCUSDT", Decimal("50000"), NOW, "TRENDING")
    d = engine(m, j, v, run_id="other-run").step(ctx)
    assert d.kind == DecisionKind.NO_TRADE and d.proposal is None
    revoked = SignedPolicyVerifier([next(iter(v._keys.values()))],
                                    revoked_approvals=["f3-approval-1"], clock_ms=lambda: NOW)
    d2 = engine(m, j, revoked).step(ctx)
    assert d2.kind == DecisionKind.NO_TRADE and d2.proposal is None
