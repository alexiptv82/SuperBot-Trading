from __future__ import annotations

from .base import BaseStrategy, SignalDirection, StrategyContext, StrategyDecision


class MeanReversionStrategy(BaseStrategy):
    """Range/overextension strategy using RSI + Bollinger positioning."""

    strategy_id = "mean_reversion"
    version = "1.0"
    trade_type = "mean_reversion"
    min_strength = 55.0

    def analyze(self, context: StrategyContext) -> StrategyDecision:
        i1 = context.indicators_1m
        i15 = context.indicators_15m

        long_score = 0.0
        short_score = 0.0
        long_reasons: list[str] = []
        short_reasons: list[str] = []

        rsi = self._float(i1, "rsi", 50.0)
        bb = i1.get("bollinger") or {}
        try:
            bb_pos = float(bb.get("price_position", 0.5))
        except (TypeError, ValueError):
            bb_pos = 0.5

        if rsi <= 30:
            long_score += 35
            long_reasons.append(f"1M_RSI_DEEPLY_OVERSOLD={rsi:.1f}")
        elif rsi < 35:
            long_score += 25
            long_reasons.append(f"1M_RSI_OVERSOLD={rsi:.1f}")

        if rsi >= 70:
            short_score += 35
            short_reasons.append(f"1M_RSI_DEEPLY_OVERBOUGHT={rsi:.1f}")
        elif rsi > 65:
            short_score += 25
            short_reasons.append(f"1M_RSI_OVERBOUGHT={rsi:.1f}")

        if bb_pos <= 0.05:
            long_score += 40
            long_reasons.append(f"1M_BELOW_LOWER_BB_POSITION={bb_pos:.3f}")
        elif bb_pos < 0.15:
            long_score += 30
            long_reasons.append(f"1M_NEAR_LOWER_BB_POSITION={bb_pos:.3f}")

        if bb_pos >= 0.95:
            short_score += 40
            short_reasons.append(f"1M_ABOVE_UPPER_BB_POSITION={bb_pos:.3f}")
        elif bb_pos > 0.85:
            short_score += 30
            short_reasons.append(f"1M_NEAR_UPPER_BB_POSITION={bb_pos:.3f}")

        # VWAP come seconda ancora di prezzo, indipendente dalle Bollinger
        # Band: uno z-score ampio rispetto al VWAP mobile e' un altro
        # segnale di overextension, pesato di piu' delle BB (40 vs 25)
        # solo nel caso estremo perche' incorpora anche il volume, non solo
        # il prezzo (vedi trovato Qwen).
        vwap = i1.get("vwap") or {}
        try:
            vwap_z = float(vwap.get("zscore", 0.0))
        except (TypeError, ValueError):
            vwap_z = 0.0

        if vwap_z <= -1.5:
            long_score += 25
            long_reasons.append(f"1M_VWAP_DEEP_BELOW_ZSCORE={vwap_z:.2f}")
        elif vwap_z <= -1.0:
            long_score += 15
            long_reasons.append(f"1M_VWAP_BELOW_ZSCORE={vwap_z:.2f}")

        if vwap_z >= 1.5:
            short_score += 25
            short_reasons.append(f"1M_VWAP_DEEP_ABOVE_ZSCORE={vwap_z:.2f}")
        elif vwap_z >= 1.0:
            short_score += 15
            short_reasons.append(f"1M_VWAP_ABOVE_ZSCORE={vwap_z:.2f}")

        trend_15m = self._trend(i15)
        if trend_15m == "sideways":
            long_score += 15; short_score += 15
            long_reasons.append("15M_RANGE_CONTEXT"); short_reasons.append("15M_RANGE_CONTEXT")
        elif trend_15m == "bearish":
            long_score = max(0.0, long_score - 20); short_score += 5
            long_reasons.append("PENALTY_15M_BEARISH_TREND")
        elif trend_15m == "bullish":
            short_score = max(0.0, short_score - 20); long_score += 5
            short_reasons.append("PENALTY_15M_BULLISH_TREND")

        macd_hist = self._macd_hist(i1)
        if macd_hist > 0 and long_score > 0:
            long_score += 10; long_reasons.append("1M_MACD_RECOVERY_CONFIRMATION")
        elif macd_hist < 0 and short_score > 0:
            short_score += 10; short_reasons.append("1M_MACD_FADE_CONFIRMATION")

        if bool(bb.get("squeeze")):
            long_score = max(0.0, long_score - 10); short_score = max(0.0, short_score - 10)
            long_reasons.append("PENALTY_BB_SQUEEZE"); short_reasons.append("PENALTY_BB_SQUEEZE")

        if long_score == short_score:
            return self.hold(context, "NO_MEAN_REVERSION_EDGE",
                metadata={"long_score": long_score, "short_score": short_score, "rsi": rsi, "bb_position": bb_pos})

        direction = SignalDirection.LONG if long_score > short_score else SignalDirection.SHORT
        strength = max(long_score, short_score)
        reasons = long_reasons if direction == SignalDirection.LONG else short_reasons

        return self.decision(context, direction=direction, strength=strength, reasons=reasons,
            metadata={"long_score": long_score, "short_score": short_score,
                      "rsi": rsi, "bb_position": bb_pos, "vwap_zscore": vwap_z,
                      "trend_15m": trend_15m, "regime": context.regime})
