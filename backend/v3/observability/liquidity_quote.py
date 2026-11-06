"""Read-only order-book quality estimate; never a trade authorization.

Requires independently verified book data in BASE asset quantities and stable
contract multipliers. No Bitget order-book feed adapter is included in V3 yet.
No invented spread/depth means no false "safe" verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext, Overflow
from typing import Sequence


@dataclass(frozen=True)
class BookSample:
    symbol: str
    timestamp_ms: int
    bids: tuple[tuple[Decimal, Decimal], ...]  # price, BASE qty, descending
    asks: tuple[tuple[Decimal, Decimal], ...]  # price, BASE qty, ascending


@dataclass(frozen=True)
class LiquidityQuote:
    status: str      # OBSERVED / UNKNOWN / INSUFFICIENT / INVALID
    reason: str
    spread_bps: Decimal | None = None
    impact_bps: Decimal | None = None
    # All findings are observational. Not approved by risk manager.
    observational_only: bool = True


def _valid_side(levels: Sequence[tuple[Decimal, Decimal]], *, descending: bool) -> bool:
    if type(levels) not in (list, tuple) or not 1 <= len(levels) <= 50:
        return False
    last = None
    for level in levels:
        if type(level) not in (tuple, list) or len(level) != 2:
            return False
        p, qty = level
        if (type(p) is not Decimal or type(qty) is not Decimal or
                not p.is_finite() or not qty.is_finite() or p <= 0 or qty <= 0):
            return False
        if last is not None and ((descending and p >= last) or (not descending and p <= last)):
            return False
        last = p
    return True


def assess_book(*, now_ms: int, book: BookSample | None, side: str,
                requested_notional_usdt: Decimal, max_age_ms: int = 3000) -> LiquidityQuote:
    """Estimate spread and market-order price impact for intended notional.

    Price impact uses VWAP against midpoint; this is a snapshot approximation,
    not a slippage/fill guarantee. If unavailable, never label it liquid.
    """
    if (type(now_ms) is not int or now_ms <= 0 or type(max_age_ms) is not int or
            not 100 <= max_age_ms <= 60000 or side not in ("LONG", "SHORT") or
            type(requested_notional_usdt) is not Decimal or
            not requested_notional_usdt.is_finite() or requested_notional_usdt <= 0):
        raise ValueError("invalid_liquidity_request")
    if book is None:
        return LiquidityQuote("UNKNOWN", "order_book_unavailable")
    if type(book) is not BookSample or type(book.timestamp_ms) is not int:
        return LiquidityQuote("INVALID", "invalid_order_book")
    if book.timestamp_ms > now_ms or now_ms - book.timestamp_ms > max_age_ms:
        return LiquidityQuote("UNKNOWN", "stale_order_book")
    if not _valid_side(book.bids, descending=True) or not _valid_side(book.asks, descending=False):
        return LiquidityQuote("INVALID", "invalid_order_book")
    if book.bids[0][0] >= book.asks[0][0]:
        return LiquidityQuote("INVALID", "crossed_order_book")
    try:
        with localcontext() as ctx:
            ctx.prec = 40
            midpoint = (book.bids[0][0] + book.asks[0][0]) / 2
            spread = (book.asks[0][0] - book.bids[0][0]) * Decimal(10000) / midpoint
            levels = book.asks if side == "LONG" else book.bids
            # Notional is in USDT. Consume quote notional per level.
            remaining = requested_notional_usdt
            base_quantity = Decimal(0)
            spent = Decimal(0)
            for price, qty in levels:
                available_usdt = price * qty
                consumed = min(remaining, available_usdt)
                base_quantity += consumed / price
                spent += consumed
                remaining -= consumed
                if remaining <= Decimal("0.000000000000000000001"):
                    break
            if remaining > Decimal("0.000000000000000000001"):
                return LiquidityQuote("INSUFFICIENT", "insufficient_visible_depth", spread)
            vwap = spent / base_quantity
            impact = abs(vwap / midpoint - 1) * Decimal(10000)
    except (InvalidOperation, Overflow, ArithmeticError, ZeroDivisionError):
        return LiquidityQuote("INVALID", "invalid_book_arithmetic")
    return LiquidityQuote("OBSERVED", "snapshot_only", spread, impact)
