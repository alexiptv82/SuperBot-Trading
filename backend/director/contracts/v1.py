"""Pure, immutable contracts for SuperBot Director shadow/paper research v1.

No exchange access, no order placement, no environment or network dependencies.
Timestamp fields are UTC Unix milliseconds; prices are positive quote prices.
These structures validate claims and *never* authorize an order.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any, Mapping, Optional

VERSION = 1
SIDES = ("LONG", "SHORT")
REGIMES = ("TREND_UP", "TREND_DOWN", "RANGE", "TRANSITION", "UNKNOWN")
ACTIONS = ("OPEN", "HOLD", "CLOSE", "PARTIAL_CLOSE", "NO_TRADE", "REASSESS")
QUALITY = ("OK", "DEGRADED", "UNAVAILABLE")


def _assert(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def _text(value: Any, label: str) -> None:
    _assert(isinstance(value, str) and bool(value.strip()), f"{label}: nonempty string required")


def _ms(value: Any, label: str, *, allow_zero: bool = False) -> None:
    _assert(type(value) is int and (value >= 0 if allow_zero else value > 0), f"{label}: UTC milliseconds integer required")


def _n(value: Any, label: str, *, min_value: float = 0.0, strictly: bool = False) -> None:
    _assert(type(value) in (float, int) and isfinite(value) and (value > min_value if strictly else value >= min_value),
            f"{label}: finite number out of range")


def _version(value: Any) -> None:
    _assert(type(value) is int and value == VERSION, "unsupported schema_version")


def _symbol(value: Any) -> None:
    _text(value, "symbol")
    _assert(value == value.upper() and "/" not in value and " " not in value, "symbol must be canonical base, e.g. BTC")


@dataclass(frozen=True, kw_only=True)
class DataQuality:
    status: str
    source: str
    gaps: int
    stale_ms: int

    def __post_init__(self) -> None:
        _assert(self.status in QUALITY, "unknown quality status")
        _text(self.source, "data source")
        _ms(self.stale_ms, "stale_ms", allow_zero=True)
        _ms(self.gaps, "gaps", allow_zero=True)
        if self.status == "OK":
            _assert(self.gaps == 0, "OK quality cannot contain gaps")


@dataclass(frozen=True, kw_only=True)
class PriceLevel:
    kind: str
    price: float
    touched: int
    confirmed_at_ms: int
    tolerance_bp: float
    evidence_id: str

    def __post_init__(self) -> None:
        _assert(self.kind in ("SUPPORT", "RESISTANCE"), "invalid price level kind")
        _n(self.price, "price", strictly=True)
        _ms(self.touched, "touched", allow_zero=True)
        _ms(self.confirmed_at_ms, "confirmed_at_ms")
        _n(self.tolerance_bp, "tolerance_bp")
        _text(self.evidence_id, "evidence_id")


@dataclass(frozen=True, kw_only=True)
class MarketFrame:
    frame_id: str
    symbol: str
    market_type: str
    asof_ms: int
    bar_ms: int
    last_closed_open_ms: int
    observed_price: float
    price_asof_ms: int
    regime: str
    quality: DataQuality
    levels: tuple[PriceLevel, ...] = ()
    features: dict[str, Any] = field(default_factory=dict)
    schema_version: int = VERSION

    def __post_init__(self) -> None:
        _version(self.schema_version)
        _text(self.frame_id, "frame_id")
        _symbol(self.symbol)
        _assert(self.market_type in ("USDT_PERPETUAL", "SPOT", "COMMODITY"), "unknown market type")
        for k, v in (("asof_ms", self.asof_ms), ("bar_ms", self.bar_ms),
                     ("last_closed_open_ms", self.last_closed_open_ms), ("price_asof_ms", self.price_asof_ms)):
            _ms(v, k)
        _n(self.observed_price, "observed_price", strictly=True)
        _assert(self.last_closed_open_ms + self.bar_ms <= self.asof_ms, "LOOKAHEAD: last bar must be fully closed")
        _assert(self.price_asof_ms <= self.asof_ms, "LOOKAHEAD: price timestamp is in future")
        _assert(self.regime in REGIMES, "invalid regime")
        _assert(isinstance(self.quality, DataQuality), "quality must be DataQuality")
        _assert(type(self.levels) is tuple and all(isinstance(x, PriceLevel) for x in self.levels), "levels must be PriceLevel tuple")
        for level in self.levels:
            _assert(level.confirmed_at_ms <= self.asof_ms, "LOOKAHEAD: level confirmation in future")
        _assert(type(self.features) is dict, "features must be dict")

    def as_payload(self) -> dict:
        return asdict(self)

    @classmethod
    def from_payload(cls, raw: Mapping[str, Any]) -> "MarketFrame":
        d = dict(raw)
        d["quality"] = DataQuality(**d["quality"])
        d["levels"] = tuple(PriceLevel(**level) for level in d.get("levels", []))
        return cls(**d)


@dataclass(frozen=True, kw_only=True)
class Candidate:
    candidate_id: str
    frame_id: str
    symbol: str
    strategy_id: str
    strategy_version: str
    params_hash: str
    side: str
    signal_bar_open_ms: int
    bar_ms: int
    earliest_entry_ms: int
    proposed_entry: float
    stop: float
    target: Optional[float]
    time_exit_bars: int
    cost_bp_roundtrip: float
    evidence_ids: tuple[str, ...]
    regime_match: bool
    estimated_net_r: Optional[float] = None
    calibrated_win_prob: Optional[float] = None
    calibration_n: int = 0
    schema_version: int = VERSION

    def __post_init__(self) -> None:
        _version(self.schema_version)
        for k in ("candidate_id", "frame_id", "strategy_id", "strategy_version", "params_hash"):
            _text(getattr(self, k), k)
        _symbol(self.symbol)
        _assert(self.side in SIDES, "candidate: invalid side")
        for k in ("signal_bar_open_ms", "bar_ms", "earliest_entry_ms"):
            _ms(getattr(self, k), k)
        _assert(self.earliest_entry_ms >= self.signal_bar_open_ms + self.bar_ms,
                "LOOKAHEAD: entry before signal candle closes")
        for k in ("proposed_entry", "stop"):
            _n(getattr(self, k), k, strictly=True)
        _assert((self.stop < self.proposed_entry if self.side == "LONG" else self.stop > self.proposed_entry),
                "stop on wrong side")
        if self.target is not None:
            _n(self.target, "target", strictly=True)
            _assert((self.target > self.proposed_entry if self.side == "LONG" else self.target < self.proposed_entry),
                    "target on wrong side")
        _ms(self.time_exit_bars, "time_exit_bars")
        _n(self.cost_bp_roundtrip, "cost_bp_roundtrip")
        _assert(type(self.evidence_ids) is tuple and bool(self.evidence_ids)
                and all(isinstance(s, str) and bool(s) for s in self.evidence_ids), "at least one evidence id required")
        _assert(type(self.regime_match) is bool, "regime_match must be bool")
        if self.estimated_net_r is not None:
            _n(self.estimated_net_r, "estimated_net_r", min_value=float("-inf"))
        if self.calibrated_win_prob is not None:
            _n(self.calibrated_win_prob, "calibrated_win_prob")
            _assert(self.calibrated_win_prob <= 1 and self.calibration_n >= 30,
                    "calibrated probability requires n>=30 and range [0,1]")
        _ms(self.calibration_n, "calibration_n", allow_zero=True)

    def as_payload(self) -> dict:
        return asdict(self)

    @classmethod
    def from_payload(cls, raw: Mapping[str, Any]) -> "Candidate":
        d = dict(raw)
        d["evidence_ids"] = tuple(d.get("evidence_ids", []))
        return cls(**d)


@dataclass(frozen=True, kw_only=True)
class PositionView:
    position_key: str
    symbol: str
    side: str
    trade_type: str
    entry_price: float
    stop: float
    margin_usd: float
    open_ms: int

    def __post_init__(self) -> None:
        _text(self.position_key, "position_key")
        _symbol(self.symbol)
        _assert(self.side in SIDES, "position side invalid")
        _assert(self.trade_type in ("scalp", "medio"), "trade_type invalid")
        for k in ("entry_price", "stop", "margin_usd"):
            _n(getattr(self, k), k, strictly=True)
        _ms(self.open_ms, "open_ms")


@dataclass(frozen=True, kw_only=True)
class PortfolioSnapshot:
    portfolio_id: str
    run_key: str
    asof_ms: int
    start_equity_usd: float
    equity_usd: float
    cash_usd: float
    margin_used_usd: float
    max_margin_total_usd: float
    max_margin_trade_usd: float
    max_open: int
    positions: tuple[PositionView, ...] = ()
    halted: bool = False
    schema_version: int = VERSION

    def __post_init__(self) -> None:
        _version(self.schema_version)
        _assert(self.portfolio_id in ("hawk", "bull", "director-hawk", "director-bull", "director-turbo"), "unknown portfolio")
        _text(self.run_key, "run_key")
        _ms(self.asof_ms, "asof_ms")
        for k in ("start_equity_usd", "max_margin_total_usd", "max_margin_trade_usd"):
            _n(getattr(self, k), k, strictly=True)
        _assert(type(self.equity_usd) in (int, float) and isfinite(self.equity_usd), "equity_usd: finite number required")
        for k in ("cash_usd", "margin_used_usd"):
            _n(getattr(self, k), k)
        _ms(self.max_open, "max_open")
        _assert(type(self.positions) is tuple and all(isinstance(p, PositionView) for p in self.positions), "invalid positions")
        _assert(type(self.halted) is bool, "halted must be bool")
        _assert(len({p.symbol for p in self.positions}) == len(self.positions), "same symbol cannot be opened twice in one portfolio")
        _assert(all(p.open_ms <= self.asof_ms for p in self.positions), "LOOKAHEAD: position opened in the future")
        # Do not reject old accounts temporarily over their new limits: observer must still see them.
        # Arbiter blocks new trades separately; this contract is an observation, not an authorization.

    def as_payload(self) -> dict:
        return asdict(self)

    @classmethod
    def from_payload(cls, raw: Mapping[str, Any]) -> "PortfolioSnapshot":
        d = dict(raw)
        d["positions"] = tuple(PositionView(**p) for p in d.get("positions", []))
        return cls(**d)


@dataclass(frozen=True, kw_only=True)
class DirectorAdvice:
    advice_id: str
    frame_id: str
    portfolio_id: str
    asof_ms: int
    provider_id: str
    model_id: str
    prompt_version: str
    action: str
    thesis: str
    counterthesis: str
    invalidate_if: str
    uncertainty_0_1: float
    evaluated_candidate_ids: tuple[str, ...]
    selected_candidate_id: Optional[str] = None
    position_key: Optional[str] = None
    hold_conviction_0_100: Optional[int] = None
    review_after_bars: Optional[int] = None
    review_timeframe_ms: Optional[int] = None
    no_trade_reason: Optional[str] = None
    schema_version: int = VERSION

    def __post_init__(self) -> None:
        _version(self.schema_version)
        for k in ("advice_id", "frame_id", "portfolio_id", "provider_id", "model_id", "prompt_version", "thesis", "counterthesis", "invalidate_if"):
            _text(getattr(self, k), k)
        _ms(self.asof_ms, "asof_ms")
        _assert(self.action in ACTIONS, "invalid action")
        _n(self.uncertainty_0_1, "uncertainty")
        _assert(self.uncertainty_0_1 <= 1, "uncertainty above 1")
        _assert(type(self.evaluated_candidate_ids) is tuple, "evaluated_candidate_ids must be tuple")
        _assert(len(set(self.evaluated_candidate_ids)) == len(self.evaluated_candidate_ids), "duplicate candidate id")
        if self.action == "OPEN":
            _text(self.selected_candidate_id, "selected_candidate_id")
            _assert(self.selected_candidate_id in self.evaluated_candidate_ids, "selected candidate not evaluated")
        elif self.selected_candidate_id is not None:
            _assert(self.selected_candidate_id in self.evaluated_candidate_ids, "selected candidate not evaluated")
        if self.action in ("HOLD", "CLOSE", "PARTIAL_CLOSE", "REASSESS"):
            _text(self.position_key, "position_key")
        if self.action in ("HOLD", "REASSESS"):
            _assert(type(self.hold_conviction_0_100) is int, "HOLD/REASSESS require hold_conviction_0_100")
        if self.hold_conviction_0_100 is not None:
            _assert(type(self.hold_conviction_0_100) is int and 0 <= self.hold_conviction_0_100 <= 100,
                    "hold conviction is a subjective score from 0 to 100, not probability")
        if self.review_after_bars is not None:
            _ms(self.review_after_bars, "review_after_bars")
            _ms(self.review_timeframe_ms, "review_timeframe_ms")
        else:
            _assert(self.review_timeframe_ms is None, "review_timeframe_ms requires review_after_bars")
        if self.action == "NO_TRADE":
            _text(self.no_trade_reason, "no_trade_reason")
        # Advice is never an execution authorization; the independent arbiter decides.

    @property
    def proposed_review_not_before_ms(self) -> Optional[int]:
        return (self.asof_ms + self.review_after_bars * self.review_timeframe_ms
                if self.review_after_bars is not None else None)

    def as_payload(self) -> dict:
        return asdict(self)

    @classmethod
    def from_payload(cls, raw: Mapping[str, Any]) -> "DirectorAdvice":
        d = dict(raw)
        d["evaluated_candidate_ids"] = tuple(d.get("evaluated_candidate_ids", []))
        return cls(**d)
