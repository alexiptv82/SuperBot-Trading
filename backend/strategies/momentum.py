from __future__ import annotations

from .base import BaseStrategy, SignalDirection, StrategyContext, StrategyDecision


class MomentumStrategy(BaseStrategy):
    """Short-horizon impulse strategy with multi-timeframe confirmation."""

    strategy_id = "momentum"
    version = "1.0"
    trade_type = "momentum"
    min_strength = 55.0

    def analyze(self, context: StrategyContext) -> StrategyDecision:
        i1 = context.indicators_1m
        i15 = context.indicators_15m

        long_score = 0.0
        short_score = 0.0
        long_reasons: list[str] = []
        short_reasons: list[str] = []

        macd1 = i1.get("macd") or {}
        if bool(macd1.get("bullish_cross")):
            long_score += 30; long_reasons.append("1M_MACD_BULLISH_CROSS")
        if bool(macd1.get("bearish_cross")):
            short_score += 30; short_reasons.append("1M_MACD_BEARISH_CROSS")

        hist1 = self._macd_hist(i1)
        hist15 = self._macd_hist(i15)
        if hist1 > 0:
            long_score += 15; long_reasons.append("1M_MACD_HIST_POSITIVE")
        elif hist1 < 0:
            short_score += 15; short_reasons.append("1M_MACD_HIST_NEGATIVE")

        if hist15 > 0:
            long_score += 15; long_reasons.append("15M_MACD_HIST_POSITIVE")
        elif hist15 < 0:
            short_score += 15; short_reasons.append("15M_MACD_HIST_NEGATIVE")

        trend15 = self._trend(i15)
        if trend15 == "bullish":
            long_score += 15; long_reasons.append("15M_TREND_BULLISH")
        elif trend15 == "bearish":
            short_score += 15; short_reasons.append("15M_TREND_BEARISH")

        volume = i1.get("volume") or {}
        try:
            volume_ratio = float(volume.get("ratio", 1.0))
        except (TypeError, ValueError):
            volume_ratio = 1.0

        if bool(volume.get("high_volume")) or volume_ratio >= 1.5:
            if long_score > short_score:
                long_score += 20; long_reasons.append(f"1M_VOLUME_EXPANSION={volume_ratio:.2f}x")
            elif short_score > long_score:
                short_score += 20; short_reasons.append(f"1M_VOLUME_EXPANSION={volume_ratio:.2f}x")

        rsi = self._float(i1, "rsi", 50.0)
        if 52 <= rsi <= 68 and long_score > 0:
            long_score += 15; long_reasons.append(f"1M_RSI_BULLISH_MOMENTUM={rsi:.1f}")
        elif rsi > 75:
            long_score = max(0.0, long_score - 20); long_reasons.append(f"PENALTY_LONG_RSI_EXHAUSTED={rsi:.1f}")

        if 32 <= rsi <= 48 and short_score > 0:
            short_score += 15; short_reasons.append(f"1M_RSI_BEARISH_MOMENTUM={rsi:.1f}")
        elif rsi < 25:
            short_score = max(0.0, short_score - 20); short_reasons.append(f"PENALTY_SHORT_RSI_EXHAUSTED={rsi:.1f}")

        price = self._float(i1, "price")
        ema9 = self._float(i1, "ema_9")
        ema21 = self._float(i1, "ema_21")
        if price > ema9 > ema21 > 0:
            long_score += 10; long_reasons.append("1M_PRICE_EMA_MOMENTUM_STACK")
        elif 0 < price < ema9 < ema21:
            short_score += 10; short_reasons.append("1M_PRICE_EMA_BEARISH_STACK")

        if long_score == short_score:
            return self.hold(context, "NO_MOMENTUM_EDGE",
                metadata={"long_score": long_score, "short_score": short_score, "volume_ratio": volume_ratio, "rsi": rsi})

        direction = SignalDirection.LONG if long_score > short_score else SignalDirection.SHORT
        strength = max(long_score, short_score)
        reasons = long_reasons if direction == SignalDirection.LONG else short_reasons

        return self.decision(context, direction=direction, strength=strength, reasons=reasons,
            metadata={"long_score": long_score, "short_score": short_score,
                      "volume_ratio": volume_ratio, "rsi": rsi, "trend_15m": trend15, "regime": context.regime})
