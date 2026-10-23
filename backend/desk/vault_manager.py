"""Vault Management V1: PAPER virtual vault, conservative transfers.

Pure transition functions: NEVER place orders, persist trading state, or call an
exchange. Caller is responsible for executing returned cash deltas atomically
with the account through one journal/revision. Pending is *not* protected cash.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from hashlib import sha256
import json

from .capital_manager import TARGET, CapitalInvariantError, dec, nonnegative, cents


@dataclass(frozen=True)
class PendingLot:
    key: str
    utc_day: str
    remaining: Decimal

    def __post_init__(self):
        if not self.key or not self.utc_day:
            raise CapitalInvariantError("missing pending lot identifier")
        nonnegative(self.remaining)

    def to_dict(self):
        return {"key": self.key, "utc_day": self.utc_day, "remaining": str(self.remaining)}


@dataclass(frozen=True)
class VaultState:
    balance: Decimal = Decimal("0")
    pending: tuple[PendingLot, ...] = ()
    revision: int = 0
    last_rollover_day: str = ""
    processed: tuple[tuple[str, str], ...] = ()  # idempotent manual and close commands

    def __post_init__(self):
        nonnegative(self.balance)
        if self.revision < 0:
            raise CapitalInvariantError("negative revision")
        keys = [x.key for x in self.pending]
        if len(keys) != len(set(keys)):
            raise CapitalInvariantError("duplicate pending key")
        ids = [x[0] for x in self.processed]
        if len(ids) != len(set(ids)):
            raise CapitalInvariantError("duplicate event receipt")

    @property
    def pending_total(self) -> Decimal:
        return sum((x.remaining for x in self.pending), Decimal("0"))

    def to_dict(self):
        return {"balance": str(self.balance),
                "pending": [x.to_dict() for x in self.pending],
                "revision": self.revision, "last_rollover_day": self.last_rollover_day,
                "processed": [list(x) for x in self.processed]}

    @classmethod
    def from_dict(cls, d: dict) -> "VaultState":
        return cls(dec(d.get("balance", 0)),
                   tuple(PendingLot(str(x["key"]), str(x["utc_day"]), dec(x["remaining"]))
                         for x in d.get("pending", [])),
                   int(d.get("revision", 0)), str(d.get("last_rollover_day", "")),
                   tuple((str(a), str(b)) for a, b in d.get("processed", [])))


@dataclass(frozen=True)
class VaultTransition:
    state: VaultState
    cash_delta: Decimal
    event_id: str
    reason: str

    def to_dict(self):
        return {"state": self.state.to_dict(), "cash_delta": str(self.cash_delta),
                "event_id": self.event_id, "reason": self.reason}


def _room(equity: object, cash: object, committed_margin: object, unrealized: object,
          reserved_cash: object = Decimal("0"),
          excluded_external_funds: object = Decimal("0")) -> Decimal:
    """Never treat returned principal, margin or unrealized profit as distributable."""
    eq, ca, m, u, reserve, external = [dec(x) for x in
                             (equity, cash, committed_margin, unrealized,
                              reserved_cash, excluded_external_funds)]
    if ca < 0 or m < 0 or reserve < 0 or external < 0:
        raise CapitalInvariantError("invalid cash, margin or reservation")
    # Reconcile: the account must not invent equity relative to its component parts.
    if abs(eq - (ca + m + u)) > Decimal("0.02"):
        raise CapitalInvariantError("equity reconciliation mismatch")
    surplus = max(Decimal("0"), eq - TARGET)
    realized_surplus = max(Decimal("0"), (ca + m) - TARGET - external)
    return max(Decimal("0"), min(surplus, realized_surplus, ca - reserve))


def _reduce_lots(lots: tuple[PendingLot, ...], spent: Decimal) -> tuple[PendingLot, ...]:
    remaining = nonnegative(spent)
    result = []
    for lot in lots:
        take = min(lot.remaining, remaining)
        remaining -= take
        if lot.remaining > take:
            result.append(replace(lot, remaining=lot.remaining - take))
    if remaining:
        raise CapitalInvariantError("paid more than eligible pending lots")
    return tuple(result)


def _trim_lots(lots: tuple[PendingLot, ...], max_pending: Decimal) -> tuple[PendingLot, ...]:
    """Reduce stale paper claims after a loss; no claim is a guaranteed profit."""
    remaining = nonnegative(max_pending)
    result = []
    for lot in lots:
        keep = min(lot.remaining, remaining)
        remaining -= keep
        if keep:
            result.append(replace(lot, remaining=keep))
    return tuple(result)


def rollover(vault: VaultState, *, utc_day: str, equity: object, cash: object,
             committed_margin: object, unrealized: object,
             reserved_cash: object = Decimal("0"),
             excluded_external_funds: object = Decimal("0")) -> VaultTransition:
    if vault.last_rollover_day == utc_day:
        return VaultTransition(vault, Decimal("0"), "rollover:" + utc_day, "already_applied")
    if vault.last_rollover_day and utc_day < vault.last_rollover_day:
        raise CapitalInvariantError("backdated rollover")
    eq = dec(equity)
    eligible = cents(_room(eq, cash, committed_margin, unrealized,
                           reserved_cash, excluded_external_funds))
    t = max(Decimal("0"), eligible)
    surplus_remaining = max(Decimal("0"), cents(eq - t - TARGET - nonnegative(excluded_external_funds)))
    existing = _trim_lots(vault.pending, surplus_remaining)
    covered = sum((x.remaining for x in existing), Decimal("0"))
    new_claim = max(Decimal("0"), surplus_remaining - covered)
    new_lots = existing + ((PendingLot("rollover:" + utc_day, utc_day, new_claim),)
                           if new_claim else ())
    new = replace(vault, balance=vault.balance + t,
                  pending=new_lots, revision=vault.revision + 1,
                  last_rollover_day=utc_day)
    return VaultTransition(new, -t, "rollover:" + utc_day, "rollover_committed")


def settle_pending(vault: VaultState, *, equity: object, cash: object,
                   committed_margin: object, unrealized: object,
                   reserved_cash: object = Decimal("0"), event_id: str,
                   excluded_external_funds: object = Decimal("0")) -> VaultTransition:
    if not event_id:
        raise CapitalInvariantError("missing event identifier")
    prior = dict(vault.processed)
    if event_id in prior:
        if prior[event_id] != "settlement":
            raise CapitalInvariantError("event id reused for different operation")
        return VaultTransition(vault, Decimal("0"), event_id, "already_applied")
    eq = dec(equity)
    claims = _trim_lots(vault.pending, max(Decimal("0"), cents(eq - TARGET - nonnegative(excluded_external_funds))))
    payable = min(sum((x.remaining for x in claims), Decimal("0")),
                  cents(_room(eq, cash, committed_margin, unrealized,
                              reserved_cash, excluded_external_funds)))
    adjusted = _reduce_lots(claims, payable)
    new = replace(vault, balance=vault.balance + payable,
                  pending=adjusted, revision=vault.revision + 1,
                  processed=vault.processed + ((event_id, "settlement"),))
    return VaultTransition(new, -payable, event_id, "pending_reconciled")


def manual_withdraw(vault: VaultState, amount: object, *, event_id: str,
                    expected_revision: int, paper_mode: bool) -> VaultTransition:
    """Only an authenticated app command may reach this method. No bot-initiated call."""
    if not paper_mode:
        raise CapitalInvariantError("vault transfers disabled outside PAPER")
    a = cents(amount)
    if a <= 0 or a != dec(amount):
        raise CapitalInvariantError("amount must be positive and precise to cents")
    if not event_id:
        raise CapitalInvariantError("missing idempotency key")
    previous = dict(vault.processed)
    if event_id in previous:
        if previous[event_id] != str(a):
            raise CapitalInvariantError("event id reused with different amount")
        return VaultTransition(vault, Decimal("0"), event_id, "already_applied")
    if expected_revision != vault.revision:
        raise CapitalInvariantError("stale vault revision")
    if a > vault.balance:
        raise CapitalInvariantError("insufficient vault balance")
    return VaultTransition(replace(vault, balance=vault.balance - a,
                                   revision=vault.revision + 1,
                                   processed=vault.processed + ((event_id, str(a)),)),
                           a, event_id, "manual_withdraw")


def journal_record(transition: VaultTransition, *, bot: str,
                   previous_revision: int, account_cash_before: object) -> dict:
    """Immutable journal payload for caller's fsync/replay transaction protocol."""
    if bot not in ("hawk", "bull"):
        raise CapitalInvariantError("unknown portfolio")
    if transition.state.revision != previous_revision + 1:
        raise CapitalInvariantError("unexpected transition revision")
    before = dec(account_cash_before)
    after = before + transition.cash_delta
    if after < 0:
        raise CapitalInvariantError("cash would become negative")
    body = {"schema": 1, "bot": bot, "event_id": transition.event_id,
            "prev_revision": previous_revision, "next_revision": transition.state.revision,
            "cash_before": str(before), "cash_after": str(after),
            "cash_delta": str(transition.cash_delta), "vault": transition.state.to_dict()}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["sha256"] = sha256(raw.encode()).hexdigest()
    return body
