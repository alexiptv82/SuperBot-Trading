from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class SignalDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    HOLD = "hold"


@dataclass(frozen=True)
class StrategyContext:
    """Normalized market context shared by every strategy."""

    symbol: str
    indicators_1m: Mapping[str, Any]
    indicators_15m: Mapping[str, Any]
    indicators_1h: Mapping[str, Any]
    regime: str = "unknown"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_ohlcv(
        cls,
        *,
        symbol: str,
        ohlcv_1m: Sequence[Sequence[float]],
        ohlcv_15m: Sequence[Sequence[float]],
        ohlcv_1h: Sequence[Sequence[float]],
        regime: str = "unknown",
        metadata: Mapping[str, Any] | None = None,
    ) -> "StrategyContext":
        try:
            from indicators import TechnicalIndicators
        except ImportError:
            from backend.indicators import TechnicalIndicators

        return cls(
            symbol=symbol.upper(),
            indicators_1m=TechnicalIndicators(list(ohlcv_1m)).compute_all(),
            indicators_15m=TechnicalIndicators(list(ohlcv_15m)).compute_all(),
            indicators_1h=TechnicalIndicators(list(ohlcv_1h)).compute_all(),
            regime=regime,
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True)
class StrategyDecision:
    strategy_id: str
    strategy_version: str
    symbol: str
    direction: SignalDirection
    strength: float
    confidence: float
    trade_type: str
    reasons: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def normalized(self) -> "StrategyDecision":
        direction = (
            self.direction
            if isinstance(self.direction, SignalDirection)
            else SignalDirection(str(self.direction).lower())
        )
        return StrategyDecision(
            strategy_id=str(self.strategy_id).strip(),
            strategy_version=str(self.strategy_version).strip(),
            symbol=str(self.symbol).strip().upper(),
            direction=direction,
            strength=max(0.0, min(100.0, float(self.strength))),
            confidence=max(0.0, min(1.0, float(self.confidence))),
            trade_type=str(self.trade_type).strip(),
            reasons=tuple(str(r) for r in self.reasons),
            metadata=dict(self.metadata),
        )

    @property
    def is_actionable(self) -> bool:
        d = self.normalized()
        return d.direction != SignalDirection.HOLD and d.strength > 0.0

    def to_dict(self) -> dict[str, Any]:
        d = self.normalized()
        payload = asdict(d)
        payload["direction"] = d.direction.value
        payload["reasons"] = list(d.reasons)
        payload["metadata"] = dict(d.metadata)
        return payload


class BaseStrategy(ABC):
    """Common contract for every SuperBot trading strategy."""

    strategy_id: str
    version: str = "1.0"
    trade_type: str
    min_strength: float = 55.0

    @abstractmethod
    def analyze(self, context: StrategyContext) -> StrategyDecision:
        raise NotImplementedError

    def hold(
        self,
        context: StrategyContext,
        *reasons: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> StrategyDecision:
        return StrategyDecision(
            strategy_id=self.strategy_id,
            strategy_version=self.version,
            symbol=context.symbol,
            direction=SignalDirection.HOLD,
            strength=0.0,
            confidence=0.0,
            trade_type=self.trade_type,
            reasons=tuple(reasons) or ("NO_EDGE",),
            metadata=dict(metadata or {}),
        )

    def decision(
        self,
        context: StrategyContext,
        *,
        direction: SignalDirection,
        strength: float,
        reasons: list[str] | tuple[str, ...],
        metadata: Mapping[str, Any] | None = None,
    ) -> StrategyDecision:
        strength = max(0.0, min(100.0, float(strength)))
        if direction == SignalDirection.HOLD or strength < self.min_strength:
            return self.hold(
                context,
                *(tuple(reasons) + (f"STRENGTH_BELOW_{self.min_strength:g}",)),
                metadata=metadata,
            )

        confidence = 0.50 + 0.50 * (
            (strength - self.min_strength)
            / max(1.0, 100.0 - self.min_strength)
        )
        return StrategyDecision(
            strategy_id=self.strategy_id,
            strategy_version=self.version,
            symbol=context.symbol,
            direction=direction,
            strength=strength,
            confidence=max(0.0, min(1.0, confidence)),
            trade_type=self.trade_type,
            reasons=tuple(reasons),
            metadata=dict(metadata or {}),
        ).normalized()

    @staticmethod
    def _macd_hist(indicators: Mapping[str, Any]) -> float:
        macd = indicators.get("macd") or {}
        try:
            return float(macd.get("histogram", 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _trend(indicators: Mapping[str, Any]) -> str:
        return str(indicators.get("trend", "sideways")).lower()

    @staticmethod
    def _float(
        indicators: Mapping[str, Any],
        key: str,
        default: float = 0.0,
    ) -> float:
        try:
            return float(indicators.get(key, default))
        except (TypeError, ValueError):
            return float(default)
