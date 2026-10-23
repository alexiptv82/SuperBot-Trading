"""Capital Management V1 — deterministic PAPER-only accounting primitives.

No I/O, trading orders, balance changes, or Bitget calls. Integration into bot
requires a separate audited change and specific deploy approval.
All values are Decimal; inputs must be finite, nonnegative where specified.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Mapping

CENT = Decimal("0.01")
TARGET = Decimal("1000.00")
DAILY_LOSS_PCT = Decimal("0.20")
KILL_EQUITY = Decimal("450.00")


class CapitalInvariantError(ValueError):
    """A balance, day boundary, or reconciliation is unsafe."""


def dec(value: object) -> Decimal:
    if isinstance(value, bool):
        raise CapitalInvariantError("boolean is not a monetary value")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CapitalInvariantError("invalid monetary value") from exc
    if not result.is_finite():
        raise CapitalInvariantError("non-finite monetary value")
    return result


def cents(value: object) -> Decimal:
    return dec(value).quantize(CENT, rounding=ROUND_DOWN)


def nonnegative(value: object) -> Decimal:
    v = dec(value)
    if v < 0:
        raise CapitalInvariantError("negative amount")
    return v


@dataclass(frozen=True)
class DayReference:
    utc_day: str
    equity_at_boundary: Decimal
    day_budget: Decimal
    net_manual_and_vault_flow: Decimal = Decimal("0")
    stop_latched: bool = False
    revision: int = 0

    def __post_init__(self) -> None:
        if not self.utc_day or len(self.utc_day) != 10:
            raise CapitalInvariantError("invalid UTC day")
        nonnegative(self.day_budget)
        dec(self.equity_at_boundary)
        dec(self.net_manual_and_vault_flow)
        if self.day_budget > TARGET:
            raise CapitalInvariantError("day budget exceeds target")
        if self.revision < 0:
            raise CapitalInvariantError("negative revision")

    def to_dict(self) -> dict:
        return {
            "utc_day": self.utc_day, "equity_at_boundary": str(self.equity_at_boundary),
            "day_budget": str(self.day_budget),
            "net_manual_and_vault_flow": str(self.net_manual_and_vault_flow),
            "stop_latched": self.stop_latched, "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, d: Mapping) -> "DayReference":
        return cls(str(d["utc_day"]), dec(d["equity_at_boundary"]),
                   dec(d["day_budget"]), dec(d.get("net_manual_and_vault_flow", 0)),
                   bool(d.get("stop_latched", False)), int(d.get("revision", 0)))


def start_day(utc_day: str, equity_after_vault: object, *, revision: int = 0) -> DayReference:
    eq = dec(equity_after_vault)
    # Short equity is not a reason to invent cash or release the daily stop.
    budget = min(TARGET, max(Decimal("0"), eq))
    return DayReference(utc_day, eq, budget, revision=revision)


@dataclass(frozen=True)
class RiskView:
    equity: Decimal
    budget: Decimal
    day_pnl: Decimal
    loss_limit: Decimal
    loss_remaining: Decimal
    stop_latched: bool
    reason: str
    def to_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v)
                for k, v in vars(self).items()}


def risk_view(ref: DayReference, equity: object, *, kill_equity: object = KILL_EQUITY) -> RiskView:
    eq = dec(equity)
    pnl = eq - ref.equity_at_boundary - ref.net_manual_and_vault_flow
    limit = DAILY_LOSS_PCT * ref.day_budget
    crossed = pnl <= -limit if ref.day_budget > 0 else True
    latched = ref.stop_latched or crossed
    reason = ("kill_equity" if eq <= dec(kill_equity) else
              "daily_stop" if latched else "")
    return RiskView(eq, ref.day_budget, pnl, limit, limit + pnl, latched, reason)


def latch_risk(ref: DayReference, equity: object) -> DayReference:
    """Latch even if market rebounds; daily-stop clears only on valid UTC rollover."""
    if risk_view(ref, equity).stop_latched and not ref.stop_latched:
        return replace(ref, stop_latched=True, revision=ref.revision + 1)
    return ref


def add_capital_flow(ref: DayReference, amount_into_operating: object) -> DayReference:
    """Accounting-only movement. Never increase the day budget or clear daily stop."""
    amount = dec(amount_into_operating)
    return replace(ref, net_manual_and_vault_flow=ref.net_manual_and_vault_flow + amount,
                   revision=ref.revision + 1)


def eligible_rollover(current: DayReference | None, next_day: str) -> bool:
    """Refuse duplicate and backdated rollover; never silently reset a daily stop."""
    if current is None:
        return True
    if next_day == current.utc_day:
        return False
    if next_day < current.utc_day:
        raise CapitalInvariantError("backward UTC day")
    return True
