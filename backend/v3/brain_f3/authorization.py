"""Verify operator-signed PAPER risk-policy receipts (F3 offline boundary).

Verifier holds only pinned Ed25519 *public* keys. The private key must live in a
separate operator-controlled signing environment, never in Brain, GitHub, a model
prompt, or the trading VPS. This module does not mint approvals or execute trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import time
from typing import Callable, Iterable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from backend.v3.brain_f2.engine import _policy_hash

_POLICY_FIELDS = (
    "max_loss_fraction", "max_open_risk_fraction", "max_position_margin_fraction",
    "max_total_margin_fraction", "minimum_equity",
    "estimated_roundtrip_cost_bp", "liquidation_buffer_fraction",
)
_RECEIPT_FIELDS = frozenset({
    "purpose", "version", "approved", "approved_by", "portfolio_id",
    "run_id", "policy_hash", "policy_sha256", "approval_id", "key_id",
    "issued_at_ms", "expires_at_ms", "signature",
})
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX128 = re.compile(r"^[0-9a-f]{128}$")
_PURPOSE = "superbot.v3.brain.paper.risk_policy"
_MAX_TTL_MS = 24 * 60 * 60 * 1000


def canonical_policy_sha256(policy: object) -> str:
    """Bind *all* F1 policy values, not only F2's shortened legacy hash."""
    fields = {}
    for name in _POLICY_FIELDS:
        raw = getattr(policy, name)
        if isinstance(raw, bool):
            raise ValueError("invalid_policy")
        try:
            num = Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("invalid_policy") from exc
        if not num.is_finite():
            raise ValueError("invalid_policy")
        fields[name] = format(num, "f")
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()


def receipt_payload(receipt: dict) -> bytes:
    """Canonical bytes for an external operator signer and read-only verifier.

    The public helper never signs and rejects extra/ambiguous fields.
    """
    if type(receipt) is not dict or set(receipt) != _RECEIPT_FIELDS:
        raise ValueError("invalid_receipt")
    msg = {field: receipt[field] for field in _RECEIPT_FIELDS - {"signature"}}
    return json.dumps(msg, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class TrustedOperatorKey:
    key_id: str
    operator_id: str
    public_key_hex: str  # exactly 32 bytes, configured outside model inputs


class SignedPolicyVerifier:
    """Callable for F2's policy_verifier; closed by default and read-only.

    Keys/revocations/clock must come from a trusted integration, not the AI or
    unsigned mandate. Does not certify runtime key storage, identity proof,
    revocation distribution or clock trust by itself.
    """

    def __init__(self, keys: Iterable[TrustedOperatorKey] = (), *,
                 revoked_approvals: Iterable[str] = (),
                 clock_ms: Callable[[], int] | None = None):
        trusted = {}
        for key in keys:
            if (not isinstance(key, TrustedOperatorKey)
                    or not isinstance(key.key_id, str) or not _TOKEN.fullmatch(key.key_id)
                    or key.operator_id not in ("operator", "system-admin")
                    or not isinstance(key.public_key_hex, str)
                    or not _HEX64.fullmatch(key.public_key_hex)):
                raise ValueError("invalid_trust_anchor")
            if key.key_id in trusted:
                raise ValueError("duplicate_trust_anchor")
            trusted[key.key_id] = key
        self._keys = trusted
        self._revoked = frozenset(revoked_approvals)
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)

    def __call__(self, receipt: dict, policy: object) -> bool:
        try:
            return self._verify(receipt, policy)
        except (Exception,):  # fail-closed: never leak signature/key/provider diagnostics
            return False

    def _verify(self, r: dict, policy: object) -> bool:
        payload = receipt_payload(r)
        if (r["purpose"] != _PURPOSE or r["approved"] is not True
                or r["portfolio_id"] != "brain"
                or type(r["version"]) is not str or not _TOKEN.fullmatch(r["version"])
                or type(r["run_id"]) is not str or not _TOKEN.fullmatch(r["run_id"])
                or type(r["approval_id"]) is not str or not _TOKEN.fullmatch(r["approval_id"])
                or r["approval_id"] in self._revoked):
            return False
        if (type(r["key_id"]) is not str or not _TOKEN.fullmatch(r["key_id"])
                or type(r["signature"]) is not str or not _HEX128.fullmatch(r["signature"])):
            return False
        key = self._keys.get(r["key_id"])
        if key is None or r["approved_by"] != key.operator_id:
            return False
        issued, expires, now = r["issued_at_ms"], r["expires_at_ms"], self._clock_ms()
        if (type(issued) is not int or type(expires) is not int or type(now) is not int
                or issued <= 0 or issued > now or now >= expires
                or expires - issued > _MAX_TTL_MS or expires <= issued):
            return False
        if (r["policy_hash"] != _policy_hash(policy)
                or type(r["policy_sha256"]) is not str
                or not _HEX64.fullmatch(r["policy_sha256"])
                or r["policy_sha256"] != canonical_policy_sha256(policy)):
            return False
        try:
            public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(key.public_key_hex))
            public.verify(bytes.fromhex(r["signature"]), payload)
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False
