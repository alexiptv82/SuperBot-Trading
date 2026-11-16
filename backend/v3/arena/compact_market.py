"""AI Arena: derive identical compact indicators using the REAL Brain market view.

Pure deterministic transformation of a previously validated FrozenMarketBatch.
Does NOT fetch candles, call AI, spend credits, write files, change services,
run risk, or place PAPER/LIVE orders. PROVISIONAL means NOT trade approved.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from hashlib import sha256
import json

from backend.v3.arena.frozen_market import (
    AI_LANES, FRAME_MS, FrozenMarketBatch, _closed_rows,
)
from backend.v3.brain_market.params import MarketViewParams
from backend.v3.brain_market.view import build_market_view, min_bars
from backend.v3.features.indicators import Bar

SCHEMA = "arena_compact_brain_market_v1"
CLASSIFICATION = "PROVISIONAL_NOT_TRADE_APPROVED"


@dataclass(frozen=True)
class CompactMarketEvidence:
    asof_ms: int
    source_sha256: str
    params_sha256: str
    sha256_hex: str
    canonical_bytes: bytes
    classification: str = CLASSIFICATION

    def verify(self) -> None:
        if (type(self.canonical_bytes) is not bytes or not self.canonical_bytes
                or sha256(self.canonical_bytes).hexdigest() != self.sha256_hex):
            raise ValueError("COMPACT_INTEGRITY_FAILURE")
        try:
            doc = json.loads(self.canonical_bytes)
        except (UnicodeDecodeError, ValueError):
            raise ValueError("COMPACT_DOCUMENT_INVALID") from None
        if (type(doc) is not dict or doc.get("schema") != SCHEMA
                or doc.get("asof_ms") != self.asof_ms
                or doc.get("source_snapshot_sha256") != self.source_sha256
                or doc.get("params_sha256") != self.params_sha256
                or doc.get("classification") != CLASSIFICATION
                or self.classification != CLASSIFICATION):
            raise ValueError("COMPACT_SCOPE_MISMATCH")

    def for_provider(self, provider: str) -> tuple[bytes, str]:
        if provider not in AI_LANES:
            raise ValueError("UNTRUSTED_ARENA_PROVIDER")
        self.verify()
        return self.canonical_bytes, self.sha256_hex


def _canonical(obj: object) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _params_as_json(params: MarketViewParams) -> dict:
    # Decimal is JSON-unsafe, so serialize it without floating point.
    raw = asdict(params)
    def normalize(value):
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError("INVALID_CONFIG_NUMBER")
            return str(value)
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [normalize(v) for v in value]
        if type(value) in (str, int, bool):
            return value
        raise ValueError("UNSUPPORTED_CONFIG_FIELD")
    return normalize(raw)


def build_compact_market(frozen: FrozenMarketBatch,
                         params: MarketViewParams) -> CompactMarketEvidence:
    """Build real Brain indicators for every frozen symbol.

    Deliberately keeps outcome scoreboard, strategy menus, risk, order and
    model-specific memory OUTSIDE this common market-evidence contract.
    """
    if type(frozen) is not FrozenMarketBatch or type(params) is not MarketViewParams:
        raise ValueError("INVALID_COMPACT_INPUT")
    frozen.verify()
    doc = json.loads(frozen.canonical_bytes)
    required = doc.get("required")
    symbols = doc.get("symbols")
    payload = doc.get("candles")
    asof = frozen.asof_ms
    if (doc.get("classification") != CLASSIFICATION
            or type(required) is not dict or set(required) != set(FRAME_MS)
            or type(symbols) is not list or tuple(symbols) != frozen.symbols
            or type(payload) is not dict or set(payload) != set(symbols)):
        raise ValueError("INCONSISTENT_FROZEN_MARKET_DOCUMENT")
    if (set(spec.name for spec in params.timeframes) != {"15m", "1h", "4h"}
            or params.base_timeframe != "15m"
            or required["1m"] < 60):
        raise ValueError("UNSUPPORTED_BRAIN_TIMEFRAMES")
    specs = {spec.name: spec for spec in params.timeframes}
    if any(type(n) is not int or n < 1 for n in required.values()):
        raise ValueError("INVALID_HISTORY_REQUIREMENTS")
    if any(required[tf] < min_bars(specs[tf], params.indicators)
           for tf in specs):
        raise ValueError("BRAIN_HISTORY_TOO_SHORT")

    entries = []
    for symbol in frozen.symbols:
        by_tf = payload[symbol]
        if type(by_tf) is not dict or set(by_tf) != set(FRAME_MS):
            raise ValueError("FROZEN_TIMEFRAME_MISSING")
        # Validate even the 1m context, although the installed Brain
        # market-view indicator config currently uses 15m/1h/4h only.
        canonical_1m = _closed_rows(by_tf["1m"], "1m", required["1m"], asof)
        if len(canonical_1m) < required["1m"]:
            raise ValueError("FROZEN_1M_DATA_INVALID")
        bars_by_tf = {}
        for tf in ("15m", "1h", "4h"):
            checked = _closed_rows(by_tf[tf], tf, required[tf], asof)
            bars_by_tf[tf] = tuple(Bar(
                open_time_ms=row[0],
                open=Decimal(row[1]),
                high=Decimal(row[2]),
                low=Decimal(row[3]),
                close=Decimal(row[4]),
                volume=Decimal(row[5]),
            ) for row in checked)
        view = build_market_view(
            bars_by_tf, timestamp_ms=asof, params=params)
        if (view.get("base_tf") != "15m"
                or type(view.get("regime")) is not str
                or view["regime"] == "UNKNOWN"
                or len(view.get("timeframes", ())) != 3
                or any(item.get("status") != "ok"
                       for item in view["timeframes"])):
            raise ValueError("BRAIN_MARKET_INDICATORS_NOT_READY")
        base = next(item for item in view["timeframes"] if item["tf"] == "15m")
        entries.append({
            "symbol": symbol,
            "price_at_closed_15m": base["close"],
            "market": view,
        })

    normalized_params = _params_as_json(params)
    params_hash = sha256(_canonical(normalized_params)).hexdigest()
    small_doc = {
        "schema": SCHEMA,
        "classification": CLASSIFICATION,
        "asof_ms": asof,
        "source_snapshot_sha256": frozen.sha256_hex,
        "params_sha256": params_hash,
        "markets": entries,
        "common_input_lanes": AI_LANES,
        "contains_raw_candles": False,
        "contains_trading_authorization": False,
    }
    body = _canonical(small_doc)
    result = CompactMarketEvidence(
        asof_ms=asof,
        source_sha256=frozen.sha256_hex,
        params_sha256=params_hash,
        sha256_hex=sha256(body).hexdigest(),
        canonical_bytes=body,
    )
    result.verify()
    return result
