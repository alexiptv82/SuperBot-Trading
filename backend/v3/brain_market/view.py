"""Pure closed-bar market snapshot. No resampling, time lookup, network or I/O.

The caller uses regime_for_context for MarketContext.regime: one label for market,
scoreboard, journal and model. Donchian's current window INCLUDES the last bar
as defined by features.indicators.donchian.
"""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from backend.v3.features.indicators import check_bars, ema, atr, rsi, macd, bollinger, donchian, adx
from backend.v3.features.levels import atr_percentile, vwap_session
from backend.v3.features.regime import regime_labels
from backend.v3.brain_market.params import IndicatorParams, TimeframeSpec, MarketViewParams

_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")
_BP = Decimal("10000")
# Fixed by the S25-S27 cards, not tunable: EMA9 and a VWAP anchored at 00:00 UTC.
# Both are optional fields: None when not computable (e.g. a day with no volume);
# they never change the timeframe status or min_bars.
EMA_EXTRA_N = 9
VWAP_PERIOD_MS = 86_400_000


def min_bars(spec: TimeframeSpec, ind: IndicatorParams) -> int:
    """Cover ATR percentile and every other used indicator's warm-up."""
    if type(spec) is not TimeframeSpec or type(ind) is not IndicatorParams:
        raise ValueError("invalid_params") from None
    return max(spec.pct_window + ind.atr_n - 1, ind.ema_slow, ind.rsi_n + 1,
               ind.macd_slow + ind.macd_signal - 1, ind.bb_n,
               ind.donchian_n, 2 * ind.adx_n - 1)


def _q(value: Decimal, places: Decimal) -> str:
    value = value.quantize(places, rounding=ROUND_HALF_EVEN)
    return str(abs(value) if value == 0 else value)


def _sign(left: Decimal, right: Decimal) -> int:
    return (left > right) - (left < right)


def _one_ok(bars, spec, params):
    ind = params.indicators
    step = spec.candle_ms
    close = bars[-1].close
    closes = [b.close for b in bars]
    e_fast = ema(closes, ind.ema_fast)[-1]
    e_slow = ema(closes, ind.ema_slow)[-1]
    average_range = atr(bars, ind.atr_n, candle_ms=step)[-1]
    pct = atr_percentile(bars, ind.atr_n, spec.pct_window, candle_ms=step)[-1]
    strength = rsi(bars, ind.rsi_n, candle_ms=step)[-1]
    mac = macd(bars, ind.macd_fast, ind.macd_slow, ind.macd_signal, candle_ms=step)
    bb = bollinger(bars, ind.bb_n, ind.bb_k, candle_ms=step)
    dc = donchian(bars, ind.donchian_n, candle_ms=step)
    directional = adx(bars, ind.adx_n, candle_ms=step)
    e9 = ema(closes, EMA_EXTRA_N)[-1]
    day_vwap = vwap_session(bars, VWAP_PERIOD_MS, 0, candle_ms=step)[-1]
    label = regime_labels(bars, ind.atr_n, spec.pct_window, ind.adx_n,
                          params.regime, candle_ms=step)[-1]
    values = (e_fast, e_slow, average_range, pct, strength, mac.line[-1],
              mac.signal[-1], mac.hist[-1], bb.percent_b[-1], bb.bandwidth[-1],
              dc.high[-1], dc.low[-1], directional.plus_di[-1],
              directional.minus_di[-1], directional.adx[-1])
    if any(v is None for v in values):
        return {"tf": spec.name, "status": "insufficient_history"}
    high, low = dc.high[-1], dc.low[-1]
    return {
        "tf": spec.name, "status": "ok", "close": str(close), "regime": label,
        "ema_fast_gap_bp": _q((close - e_fast) / close * _BP, Q2),
        "ema_slow_gap_bp": _q((close - e_slow) / close * _BP, Q2),
        "ema_cross": _sign(e_fast, e_slow),
        "atr_bp": _q(average_range / close * _BP, Q2),
        "atr_pct_rank": _q(pct, Q2),
        "rsi": _q(strength, Q2),
        "macd_hist_bp": _q(mac.hist[-1] / close * _BP, Q2),
        "macd_above_signal": _sign(mac.line[-1], mac.signal[-1]),
        "bb_pct_b": _q(bb.percent_b[-1], Q4),
        "bb_bandwidth": _q(bb.bandwidth[-1], Q4),
        "donchian_pos": _q((close - low) / (high - low), Q4) if high != low else "0.5000",
        "adx": _q(directional.adx[-1], Q2),
        "di_dir": _sign(directional.plus_di[-1], directional.minus_di[-1]),
        "ema9_gap_bp": None if e9 is None else _q((close - e9) / close * _BP, Q2),
        "vwap_gap_bp": None if day_vwap is None else _q((close - day_vwap) / close * _BP, Q2),
    }


def build_market_view(bars_by_tf, *, timestamp_ms, params) -> dict:
    """Build JSON-safe snapshot: validation, closed-only, freshness, warm-up, indicators.

    Validation order: invalid_params > invalid_timestamp > invalid_bars keys/shapes;
    then per configured timeframe: missing, invalid_bars, future_bar, stale,
    insufficient_history, ok. No timeframes are resampled.
    """
    if type(params) is not MarketViewParams:
        raise ValueError("invalid_params") from None
    if type(timestamp_ms) is not int or timestamp_ms <= 0:
        raise ValueError("invalid_timestamp") from None
    if (not isinstance(bars_by_tf, Mapping)
            or not all(type(k) is str and k in {s.name for s in params.timeframes}
                       and type(v) in (list, tuple) for k, v in bars_by_tf.items())):
        raise ValueError("invalid_bars") from None
    entries = []
    try:
        with localcontext(_CTX):
            for spec in params.timeframes:
                bars = bars_by_tf.get(spec.name)
                if not bars:
                    entries.append({"tf": spec.name, "status": "missing"})
                    continue
                try:
                    check_bars(bars, candle_ms=spec.candle_ms)
                except ValueError:
                    raise ValueError("invalid_bars") from None
                end_ms = bars[-1].open_time_ms + spec.candle_ms
                if end_ms > timestamp_ms:
                    raise ValueError("future_bar") from None
                if timestamp_ms - end_ms >= params.max_age_candles * spec.candle_ms:
                    entries.append({"tf": spec.name, "status": "stale"})
                    continue
                if len(bars) < min_bars(spec, params.indicators):
                    entries.append({"tf": spec.name, "status": "insufficient_history"})
                    continue
                try:
                    entries.append(_one_ok(bars, spec, params))
                except ValueError as exc:
                    if str(exc) == "numeric_out_of_range":
                        raise ValueError("numeric_out_of_range") from None
                    raise ValueError("invalid_params") from None
            base = next(e for e in entries if e["tf"] == params.base_timeframe)
            return {
                "base_tf": params.base_timeframe,
                "regime": base["regime"] if base["status"] == "ok" else "UNKNOWN",
                "timeframes": entries,
            }
    except ArithmeticError:
        raise ValueError("numeric_out_of_range") from None


def regime_for_context(bars_by_tf, *, timestamp_ms, params) -> str:
    """One regime source for MarketContext, scoreboard, model and journal."""
    return build_market_view(bars_by_tf, timestamp_ms=timestamp_ms, params=params)["regime"]
