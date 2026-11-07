"""Opt-in, read-only market microstructure observations for PAPER/shadow.

This module does NOT fetch from Bitget, assemble order-book deltas, authorize
orders or write to EventJournal. The caller must provide a full, verified book
image with UTA-v3 provenance. Missing or unproven source metadata is UNKNOWN,
never a low-cost/healthy market judgement. No threshold is a trade veto.

IMPORTANT: `mid_markout_after` is an *ex-post* measurement. Never put it in
an entry-time MarketQualitySnapshot or pass it to Brain decision features.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, Overflow, localcontext
import re

from backend.v3.observability.liquidity_quote import BookSample, assess_book

_SYMBOL = re.compile(r"^[A-Z0-9]{2,20}USDT$")
_STREAM = re.compile(r"^[a-zA-Z0-9_.:-]{1,64}$")
_BPS = Decimal("10000")


@dataclass(frozen=True)
class FullBookFrame:
    """A FULL normalized L2 image; this is NOT an incremental delta.

    qty_unit='BASE' means quantities are already converted to base crypto
    units via a validated exchange instrument/contract multiplier. Metadata
    represents an actual collector observation, not values inferred from OHLCV.
    """
    book: BookSample
    symbol: str
    venue: str
    instrument_type: str
    source_version: str
    qty_unit: str
    connection_id: str
    event_ts_ms: int
    received_ts_ms: int
    is_snapshot: bool
    seq: int
    pseq: int | None


@dataclass(frozen=True)
class SequenceCursor:
    connection_id: str
    seq: int
    received_ts_ms: int


@dataclass(frozen=True)
class MarketQualitySnapshot:
    status: str                       # OBSERVED/UNKNOWN/INVALID/INSUFFICIENT
    reason: str
    symbol: str | None = None
    event_ts_ms: int | None = None
    received_ts_ms: int | None = None
    source_version: str | None = None
    spread_bps: Decimal | None = None
    depth_bid_10bps_usdt: Decimal | None = None
    depth_ask_10bps_usdt: Decimal | None = None
    imbalance_top5: Decimal | None = None  # -1 .. +1 (base-side notional)
    microprice_delta_bps: Decimal | None = None
    midpoint: Decimal | None = None
    # Both estimated costs use the SAME book, not future book conditions.
    entry_impact_bps: Decimal | None = None
    exit_impact_bps: Decimal | None = None
    estimated_roundtrip_bps_ex_funding: Decimal | None = None
    observational_only: bool = True


@dataclass(frozen=True)
class MidMarkout:
    """Separate ex-post outcome, deliberately absent from entry-time snapshot."""
    status: str                       # OBSERVED / UNKNOWN / INVALID
    reason: str
    horizon_ms: int
    signed_mid_move_bps: Decimal | None = None


def _finite_nonnegative(d: object) -> bool:
    return type(d) is Decimal and d.is_finite() and d >= 0


def _report(status: str, reason: str, frame: FullBookFrame | None = None) -> tuple[MarketQualitySnapshot, None]:
    symbol = frame.symbol if type(frame) is FullBookFrame and type(frame.symbol) is str else None
    return MarketQualitySnapshot(status, reason, symbol=symbol), None


def _depth_near_mid(levels: tuple[tuple[Decimal, Decimal], ...], mid: Decimal,
                    *, is_bid: bool, threshold_bps: Decimal = Decimal("10")) -> Decimal:
    boundary = mid * (1 - threshold_bps / _BPS) if is_bid else mid * (1 + threshold_bps / _BPS)
    return sum((price * qty for price, qty in levels
                if (price >= boundary if is_bid else price <= boundary)), Decimal(0))


def observe_market_quality(*, now_ms: int, frame: FullBookFrame | None,
                           intended_side: str, notional_usdt: Decimal,
                           fee_roundtrip_bps: Decimal | None = None,
                           previous: SequenceCursor | None = None,
                           max_age_ms: int = 3000,
                           max_transport_lag_ms: int = 2000
                           ) -> tuple[MarketQualitySnapshot, SequenceCursor | None]:
    """Compute shadow-only metrics and (only for a valid frame) sequence cursor.

    A snapshot establishes a new cursor; a subsequent full-book image built
    from deltas needs a matching previous cursor (pseq => seq). The *collector*
    must independently prove it reconstructed the correct full book: this
    calculation cannot validate unseen deltas or reconnect history.
    """
    if (type(now_ms) is not int or now_ms <= 0 or intended_side not in ("LONG", "SHORT")
            or type(notional_usdt) is not Decimal or not notional_usdt.is_finite() or notional_usdt <= 0
            or (fee_roundtrip_bps is not None and not _finite_nonnegative(fee_roundtrip_bps))
            or type(max_age_ms) is not int or not 100 <= max_age_ms <= 60000
            or type(max_transport_lag_ms) is not int or not 0 <= max_transport_lag_ms <= 60000):
        raise ValueError("invalid_market_quality_request")
    if previous is not None and (type(previous) is not SequenceCursor
            or type(previous.connection_id) is not str or not _STREAM.fullmatch(previous.connection_id)
            or type(previous.seq) is not int or previous.seq < 0
            or type(previous.received_ts_ms) is not int or previous.received_ts_ms <= 0):
        return _report("INVALID", "invalid_sequence_cursor")
    if frame is None:
        return _report("UNKNOWN", "book_feed_missing")
    if type(frame) is not FullBookFrame or type(frame.book) is not BookSample:
        return _report("INVALID", "invalid_book_frame")
    if (type(frame.symbol) is not str or not _SYMBOL.fullmatch(frame.symbol)
            or frame.book.symbol != frame.symbol or frame.book.timestamp_ms != frame.event_ts_ms):
        return _report("INVALID", "book_identity_mismatch", frame)
    if (frame.venue != "BITGET" or frame.instrument_type != "USDT_PERPETUAL"
            or frame.source_version != "UTA_V3_L2" or frame.qty_unit != "BASE"):
        return _report("UNKNOWN", "unverified_book_source_or_units", frame)
    if (type(frame.connection_id) is not str or not _STREAM.fullmatch(frame.connection_id)
            or type(frame.is_snapshot) is not bool or type(frame.seq) is not int or frame.seq < 0
            or (frame.pseq is not None and (type(frame.pseq) is not int or frame.pseq < 0))):
        return _report("INVALID", "invalid_sequence_metadata", frame)
    if (type(frame.event_ts_ms) is not int or type(frame.received_ts_ms) is not int
            or frame.event_ts_ms <= 0 or frame.received_ts_ms < frame.event_ts_ms
            or frame.received_ts_ms > now_ms):
        return _report("UNKNOWN", "invalid_or_future_timestamps", frame)
    if now_ms - frame.received_ts_ms > max_age_ms or frame.received_ts_ms - frame.event_ts_ms > max_transport_lag_ms:
        return _report("UNKNOWN", "stale_or_delayed_book", frame)
    if frame.is_snapshot:
        if (type(previous) is SequenceCursor and previous.connection_id == frame.connection_id
                and (frame.seq <= previous.seq or frame.received_ts_ms <= previous.received_ts_ms)):
            return _report("INVALID", "replayed_or_reordered_book", frame)
    else:
        if previous is None or type(previous) is not SequenceCursor:
            return _report("UNKNOWN", "unproven_sequence", frame)
        if frame.connection_id != previous.connection_id:
            return _report("UNKNOWN", "reconnect_requires_snapshot", frame)
        if frame.pseq != previous.seq:
            return _report("UNKNOWN", "sequence_gap", frame)
        if frame.seq <= previous.seq or frame.received_ts_ms <= previous.received_ts_ms:
            return _report("INVALID", "replayed_or_reordered_book", frame)

    entry = assess_book(now_ms=now_ms, book=frame.book, side=intended_side,
                        requested_notional_usdt=notional_usdt, max_age_ms=max_age_ms)
    if entry.status in ("INVALID", "UNKNOWN"):
        return _report(entry.status, entry.reason, frame)
    inverse_side = "SHORT" if intended_side == "LONG" else "LONG"
    exit_q = assess_book(now_ms=now_ms, book=frame.book, side=inverse_side,
                         requested_notional_usdt=notional_usdt, max_age_ms=max_age_ms)
    if exit_q.status in ("INVALID", "UNKNOWN"):
        return _report(exit_q.status, exit_q.reason, frame)

    try:
        with localcontext() as ctx:
            ctx.prec = 40
            bids, asks = frame.book.bids, frame.book.asks
            bid, bid_qty = bids[0]
            ask, ask_qty = asks[0]
            mid = (bid + ask) / 2
            micro = (ask * bid_qty + bid * ask_qty) / (bid_qty + ask_qty)
            micro_delta = (micro - mid) / mid * _BPS
            bid_top = sum((p * q for p, q in bids[:5]), Decimal(0))
            ask_top = sum((p * q for p, q in asks[:5]), Decimal(0))
            imbalance = (bid_top - ask_top) / (bid_top + ask_top)
            bid_depth = _depth_near_mid(bids, mid, is_bid=True)
            ask_depth = _depth_near_mid(asks, mid, is_bid=False)
            total = (entry.impact_bps + exit_q.impact_bps + fee_roundtrip_bps
                     if entry.status == exit_q.status == "OBSERVED" and fee_roundtrip_bps is not None
                     else None)
    except (InvalidOperation, Overflow, ArithmeticError, ZeroDivisionError, TypeError):
        return _report("INVALID", "metric_arithmetic_failed", frame)

    status = "OBSERVED" if entry.status == exit_q.status == "OBSERVED" else "INSUFFICIENT"
    result = MarketQualitySnapshot(
        status=status, reason="shadow_book_estimate" if status == "OBSERVED" else "insufficient_visible_depth",
        symbol=frame.symbol, event_ts_ms=frame.event_ts_ms, received_ts_ms=frame.received_ts_ms,
        source_version=frame.source_version,
        spread_bps=entry.spread_bps, depth_bid_10bps_usdt=bid_depth,
        depth_ask_10bps_usdt=ask_depth, imbalance_top5=imbalance,
        microprice_delta_bps=micro_delta, midpoint=mid,
        entry_impact_bps=entry.impact_bps if entry.status == "OBSERVED" else None,
        exit_impact_bps=exit_q.impact_bps if exit_q.status == "OBSERVED" else None,
        estimated_roundtrip_bps_ex_funding=total,
    )
    return result, SequenceCursor(frame.connection_id, frame.seq, frame.received_ts_ms)


def mid_markout_after(*, at_entry: MarketQualitySnapshot, later: MarketQualitySnapshot,
                      side: str, horizon_ms: int, max_lateness_ms: int = 5000) -> MidMarkout:
    """Ex-post signed midpoint markout; NOT fill PnL and not an entry-time feature.

    Caller must supply a FUTURE book observation, separated from the original
    decision features. Returns UNKNOWN if horizon is missing, early or too late.
    """
    if (side not in ("LONG", "SHORT") or type(horizon_ms) is not int or horizon_ms not in (30000, 60000)
            or type(max_lateness_ms) is not int or not 0 <= max_lateness_ms <= 60000):
        raise ValueError("invalid_markout_request")
    if type(at_entry) is not MarketQualitySnapshot or type(later) is not MarketQualitySnapshot:
        return MidMarkout("INVALID", "invalid_markout_inputs", horizon_ms)
    if (at_entry.status != "OBSERVED" or later.status != "OBSERVED"
            or at_entry.symbol != later.symbol or at_entry.source_version != later.source_version
            or not at_entry.midpoint or not later.midpoint
            or at_entry.event_ts_ms is None or later.event_ts_ms is None):
        return MidMarkout("UNKNOWN", "unusable_observations", horizon_ms)
    difference = later.event_ts_ms - at_entry.event_ts_ms
    if not horizon_ms <= difference <= horizon_ms + max_lateness_ms:
        return MidMarkout("UNKNOWN", "horizon_not_observed", horizon_ms)
    try:
        with localcontext() as ctx:
            ctx.prec = 40
            move = (later.midpoint - at_entry.midpoint) / at_entry.midpoint * _BPS
            signed = move if side == "LONG" else -move
    except (InvalidOperation, Overflow, ArithmeticError, ZeroDivisionError):
        return MidMarkout("INVALID", "markout_arithmetic_failed", horizon_ms)
    return MidMarkout("OBSERVED", "ex_post_midpoint_not_pnl", horizon_ms, signed)
