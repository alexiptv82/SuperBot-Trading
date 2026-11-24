"""Strict market-view configuration. Only default_params_path/load_default_params perform I/O."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path

from backend.v3.features.regime import RegimeParams


@dataclass(frozen=True)
class TimeframeSpec:
    name: str
    candle_ms: int
    pct_window: int


@dataclass(frozen=True)
class IndicatorParams:
    ema_fast: int
    ema_slow: int
    atr_n: int
    rsi_n: int
    macd_fast: int
    macd_slow: int
    macd_signal: int
    bb_n: int
    bb_k: Decimal
    donchian_n: int
    adx_n: int


@dataclass(frozen=True)
class MarketViewParams:
    base_timeframe: str
    max_age_candles: int
    timeframes: tuple[TimeframeSpec, ...]
    indicators: IndicatorParams
    regime: RegimeParams


_TIMEFRAMES = {
    "1m": 60000, "5m": 300000, "15m": 900000,
    "1h": 3600000, "4h": 14400000, "1d": 86400000,
}
_TF_KEYS = {"name", "candle_ms", "pct_window"}
_IND_KEYS = set(IndicatorParams.__dataclass_fields__)
_REG_KEYS = set(RegimeParams.__dataclass_fields__)
_MAIN_KEYS = {"schema_version", "base_timeframe", "max_age_candles", "timeframes", "indicators", "regime"}


def _fail() -> None:
    raise ValueError("invalid_params") from None


def _pairs(pairs):
    out = {}
    for name, value in pairs:
        if name in out:
            _fail()
        out[name] = value
    return out


def _reject_constant(_value):
    _fail()


def _positive_int(value, minimum):
    if type(value) is not int or value < minimum:
        _fail()
    return value


def _number_string(value):
    """Check ^[0-9]{1,3}(\\.[0-9]{1,4})?$ without importing regex."""
    if type(value) is not str:
        _fail()
    bits = value.split(".")
    if (len(bits) > 2 or not 1 <= len(bits[0]) <= 3
            or not bits[0].isascii() or not bits[0].isdigit()):
        _fail()
    if len(bits) == 2 and (not 1 <= len(bits[1]) <= 4
                           or not bits[1].isascii() or not bits[1].isdigit()):
        _fail()
    return Decimal(value)


def load_market_view_params(raw: bytes) -> MarketViewParams:
    """Parse only exact bytes, rejecting duplicate keys, constants, wrong shapes and types."""
    if type(raw) is not bytes:
        _fail()
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=_reject_constant)
        if type(data) is not dict or set(data) != _MAIN_KEYS:
            _fail()
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            _fail()
        age = _positive_int(data["max_age_candles"], 1)
        if age > 10:
            _fail()
        specs = data["timeframes"]
        if type(specs) is not list or not 1 <= len(specs) <= 5:
            _fail()
        parsed = []
        seen = set()
        for item in specs:
            if type(item) is not dict or set(item) != _TF_KEYS:
                _fail()
            name = item["name"]
            if type(name) is not str or name not in _TIMEFRAMES or name in seen:
                _fail()
            seen.add(name)
            if type(item["candle_ms"]) is not int or item["candle_ms"] != _TIMEFRAMES[name]:
                _fail()
            parsed.append(TimeframeSpec(name, item["candle_ms"], _positive_int(item["pct_window"], 2)))
        base = data["base_timeframe"]
        if type(base) is not str or base not in seen:
            _fail()
        inds = data["indicators"]
        if type(inds) is not dict or set(inds) != _IND_KEYS:
            _fail()
        ind_vals = {k: _number_string(v) if k == "bb_k" else _positive_int(v, 1)
                    for k, v in inds.items()}
        ind = IndicatorParams(**ind_vals)
        if (ind.ema_fast >= ind.ema_slow or ind.macd_fast >= ind.macd_slow
                or ind.bb_k <= 0):
            _fail()
        reg = data["regime"]
        if type(reg) is not dict or set(reg) != _REG_KEYS:
            _fail()
        rp = RegimeParams(**{name: _number_string(reg[name]) for name in _REG_KEYS})
        if (rp.shock_tr_mult <= 0 or not 0 <= rp.expansion_pct_min <= 100
                or rp.adx_trend_min <= 0 or rp.adx_range_max < 0
                or rp.adx_range_max >= rp.adx_trend_min):
            _fail()
        return MarketViewParams(base, age, tuple(parsed), ind, rp)
    except Exception:
        raise ValueError("invalid_params") from None


def default_params_path() -> Path:
    """I/O boundary helper: resolve the bundled JSON relative to this file."""
    return Path(__file__).with_name("market_view_params.json")


def load_default_params() -> MarketViewParams:
    """Only file-reading entry point: call explicitly at configuration time."""
    return load_market_view_params(default_params_path().read_bytes())
