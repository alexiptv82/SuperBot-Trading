from __future__ import annotations

from .base import BaseStrategy, SignalDirection, StrategyContext, StrategyDecision


class TrendFollowingStrategy(BaseStrategy):
    """Multi-timeframe trend continuation strategy."""

    strategy_id = "trend_following"
    version = "1.0"
    trade_type = "trend"
    min_strength = 55.0

    def analyze(self, context: StrategyContext) -> StrategyDecision:
        i1 = context.indicators_1m
        i15 = context.indicators_15m
        i60 = context.indicators_1h

        long_score = 0.0
        short_score = 0.0
        long_reasons: list[str] = []
        short_reasons: list[str] = []

        trend_1h = self._trend(i60)
        trend_15m = self._trend(i15)

        if trend_1h == "bullish":
            long_score += 35
            long_reasons.append("1H_TREND_BULLISH")
        elif trend_1h == "bearish":
            short_score += 35
            short_reasons.append("1H_TREND_BEARISH")

        if trend_15m == "bullish":
            long_score += 20
            long_reasons.append("15M_TREND_BULLISH")
        elif trend_15m == "bearish":
            short_score += 20
            short_reasons.append("15M_TREND_BEARISH")

        e9 = self._float(i15, "ema_9")
        e21 = self._float(i15, "ema_21")
        e50 = self._float(i15, "ema_50")
        if e9 > e21 > e50 > 0:
            long_score += 20
            long_reasons.append("15M_EMA_STACK_BULLISH")
        elif 0 < e9 < e21 < e50:
            short_score += 20
            short_reasons.append("15M_EMA_STACK_BEARISH")

        macd_1h = self._macd_hist(i60)
        if macd_1h > 0:
            long_score += 15
            long_reasons.append("1H_MACD_POSITIVE")
        elif macd_1h < 0:
            short_score += 15
            short_reasons.append("1H_MACD_NEGATIVE")

        price_1m = self._float(i1, "price")
        ema21_1m = self._float(i1, "ema_21")
        if price_1m > ema21_1m > 0:
            long_score += 10
            long_reasons.append("1M_PRICE_ABOVE_EMA21")
        elif 0 < price_1m < ema21_1m:
            short_score += 10
            short_reasons.append("1M_PRICE_BELOW_EMA21")

        volume = i1.get("volume") or {}
        if bool(volume.get("high_volume")):
            if long_score > short_score:
                long_score += 5
                long_reasons.append("1M_HIGH_VOLUME_CONFIRMATION")
            elif short_score > long_score:
                short_score += 5
                short_reasons.append("1M_HIGH_VOLUME_CONFIRMATION")

        if trend_1h == "bullish" and trend_15m == "bearish":
            return self.hold(context, "TIMEFRAME_CONFLICT_1H_BULL_15M_BEAR",
                metadata={"long_score": long_score, "short_score": short_score})
        if trend_1h == "bearish" and trend_15m == "bullish":
            return self.hold(context, "TIMEFRAME_CONFLICT_1H_BEAR_15M_BULL",
                metadata={"long_score": long_score, "short_score": short_score})

        if long_score == short_score:
            return self.hold(context, "NO_DIRECTIONAL_ADVANTAGE",
                metadata={"long_score": long_score, "short_score": short_score, "regime": context.regime})

        direction = SignalDirection.LONG if long_score > short_score else SignalDirection.SHORT
        strength = max(long_score, short_score)
        reasons = long_reasons if direction == SignalDirection.LONG else short_reasons

        return self.decision(context, direction=direction, strength=strength, reasons=reasons,
            metadata={"long_score": long_score, "short_score": short_score,
                      "regime": context.regime, "trend_1h": trend_1h, "trend_15m": trend_15m})
