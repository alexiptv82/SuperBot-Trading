"""PAPER position sizing under a day-frozen portfolio budget.

Position cap includes main leg, filled DCA and committed second leg.
Pure function shared by AI/rules/split/DCA adapters; no trade execution.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from .capital_manager import CapitalInvariantError, dec, nonnegative, cents

CAP_PCT = {"hawk": Decimal("0.10"), "bull": Decimal("0.25")}
SLOTS = {"hawk": 10, "bull": 6}


@dataclass(frozen=True)
class SizeDecision:
    approved: bool
    amount: Decimal
    position_cap: Decimal
    total_budget: Decimal
    reason: str

    def to_dict(self):
        return {"approved": self.approved, "amount": str(self.amount),
                "position_cap": str(self.position_cap),
                "total_budget": str(self.total_budget), "reason": self.reason}


def cap_for(bot: str, day_budget: object) -> Decimal:
    if bot not in CAP_PCT:
        raise CapitalInvariantError("unknown portfolio")
    budget = nonnegative(day_budget)
    if budget > 1000:
        raise CapitalInvariantError("day budget above maximum")
    return cents(budget * CAP_PCT[bot])


def size_request(*, bot: str, day_budget: object,
                 already_in_position: object, pending_same_position: object,
                 total_committed_margin: object, available_cash: object,
                 reserved_cash: object, request: object,
                 minimum_executable: object, fee_fraction: object,
                 n_open: int, is_new: bool, risk_reason: str = "",
                 allow_reduction: bool = True) -> SizeDecision:
    """Compute a conservative cap, including position and aggregate reservations.

    total_committed_margin includes filled positions + ALL reserved split legs.
    already_in_position includes filled margin on the targeted symbol.
    pending_same_position is the symbol's reserved split margin (not in filled).
    For a *new* request, n_open must be strictly below slot cap.
    """
    cap = cap_for(bot, day_budget)
    budget = nonnegative(day_budget)
    if risk_reason:
        return SizeDecision(False, Decimal("0"), cap, budget, "risk_blocked")
    if is_new and n_open >= SLOTS[bot]:
        return SizeDecision(False, Decimal("0"), cap, budget, "slots_full")
    vals = [nonnegative(x) for x in
            (already_in_position, pending_same_position, total_committed_margin,
             available_cash, reserved_cash, request, minimum_executable,
             fee_fraction)]
    filled, pending, committed, cash, reserved, asked, minimum, fee = vals
    if fee >= 1:
        raise CapitalInvariantError("invalid fee fraction")
    if asked <= 0:
        return SizeDecision(False, Decimal("0"), cap, budget, "zero_request")
    if filled + pending > committed:
        raise CapitalInvariantError("position commitment larger than total")
    free_cash = max(Decimal("0"), cash - reserved)
    free_pos = max(Decimal("0"), cap - filled - pending)
    free_total = max(Decimal("0"), budget - committed)
    # Preserve existing cash buffer rule (95% of cash), plus any reserved cost.
    free_cash_after_costs = cents(free_cash * Decimal("0.95") / (1 + fee))
    available = max(Decimal("0"), min(free_pos, free_total, free_cash_after_costs))
    if available < minimum:
        return SizeDecision(False, Decimal("0"), cap, budget, "below_minimum")
    if asked > available and not allow_reduction:
        return SizeDecision(False, Decimal("0"), cap, budget, "exceeds_cap")
    granted = cents(min(asked, available))
    if granted < minimum:
        return SizeDecision(False, Decimal("0"), cap, budget, "below_minimum")
    return SizeDecision(True, granted, cap, budget,
                        "reduced" if granted < asked else "accepted")


def can_fill_split_or_dca(**kwargs) -> SizeDecision:
    """Always recheck commitments and daily cap at fill time; fail closed."""
    return size_request(**kwargs)
