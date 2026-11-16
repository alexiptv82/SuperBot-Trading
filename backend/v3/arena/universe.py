"""Pure Top-23 crypto + Gold/Silver universe for the future Brain AI Arena.

No HTTP, no API keys, no journal writes, no position management. The 25 slots
are 23 highest-ranked *eligible and tradeable* non-stablecoin crypto assets
and two fixed metal contracts (XAUUSDT, XAGUSDT). Meta sources must supply
independently vetted category labels and current Bitget USDT-futures contracts.

FAIL CLOSED: missing rank, stale rankings, unknown classification, unavailable
contract, bad price feed or weak market depth never become PAPER candidates.
The existing eight-symbol V3 Brain configuration is deliberately untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
import re

CRYPTO_SLOTS = 23
METAL_SYMBOLS = ("XAUUSDT", "XAGUSDT")
UNIVERSE_SLOTS = CRYPTO_SLOTS + len(METAL_SYMBOLS)
DEFAULT_AI_SHORTLIST = 8

CAP_MAX_AGE_MS = 26 * 60 * 60 * 1000
CONTRACT_MAX_AGE_MS = 2 * 60 * 60 * 1000
BAR_MAX_AGE_MS = 60 * 60 * 1000

# Exclusions are metadata categories, not a manually maintained fixed-coin list.
# Provider classification must be independently verified before automated use.
AssetClass = Literal["native", "stablecoin", "wrapped", "tokenized_metal", "unknown"]
Direction = Literal["LONG", "SHORT", "NO_TRADE"]
SYMBOL = re.compile(r"[A-Z0-9]{2,20}USDT\Z")
COIN = re.compile(r"[A-Z0-9]{2,20}\Z")


@dataclass(frozen=True)
class RankedAsset:
    asset_id: str
    ticker: str
    market_cap_rank: int
    market_cap_usd: Decimal
    classification: AssetClass
    observed_ms: int


@dataclass(frozen=True)
class FuturesContract:
    symbol: str
    product_type: str
    contract_type: str
    status: str
    quote_volume_24h_usdt: Decimal
    spread_bps: Decimal
    min_leverage: int
    max_leverage: int
    closed_bars_verified: bool
    observed_ms: int


@dataclass(frozen=True)
class SelectedMarket:
    symbol: str
    kind: Literal["crypto", "metal"]
    tradeable: bool
    reason: str
    crypto_rank: int | None = None
    asset_id: str | None = None


@dataclass(frozen=True)
class UniverseSnapshot:
    asof_ms: int
    markets: tuple[SelectedMarket, ...]
    crypto_count: int
    metal_count: int
    complete: bool
    mode: str = "PAPER_OFFLINE_READONLY"

    @property
    def tradeable_symbols(self) -> tuple[str, ...]:
        return tuple(x.symbol for x in self.markets if x.tradeable)


@dataclass(frozen=True)
class SignalScreen:
    symbol: str
    side: Direction
    quality: Decimal
    market_data_timestamp_ms: int
    closed_bars_only: bool
    contract_liquid: bool


@dataclass(frozen=True)
class ScanResult:
    watched_symbols: tuple[str, ...]
    ai_shortlist: tuple[str, ...]
    bullish_candidates: tuple[str, ...]
    bearish_candidates: tuple[str, ...]
    mode: str = "PAPER_OFFLINE_READONLY"


def _money(v: object) -> bool:
    return type(v) is Decimal and v.is_finite() and v >= 0


def _contract_ok(
    contract: FuturesContract | None, *,
    symbol: str,
    now_ms: int,
    min_volume_usdt: Decimal,
    max_spread_bps: Decimal,
    requested_leverage: int,
) -> tuple[bool, str]:
    if type(contract) is not FuturesContract or contract.symbol != symbol:
        return False, "BITGET_CONTRACT_UNAVAILABLE"
    if (contract.product_type != "USDT-FUTURES"
            or contract.contract_type != "perpetual"
            or contract.status != "normal"):
        return False, "CONTRACT_NOT_OPEN"
    if (type(contract.observed_ms) is not int
            or not 0 <= now_ms - contract.observed_ms <= CONTRACT_MAX_AGE_MS
            or type(contract.closed_bars_verified) is not bool
            or contract.closed_bars_verified is not True):
        return False, "STALE_CONTRACT_OR_FEED"
    if (not _money(contract.quote_volume_24h_usdt)
            or not _money(contract.spread_bps)
            or contract.quote_volume_24h_usdt < min_volume_usdt
            or contract.spread_bps > max_spread_bps):
        return False, "LIQUIDITY_OR_SPREAD_FILTER"
    if (type(contract.min_leverage) is not int
            or type(contract.max_leverage) is not int
            or not 1 <= contract.min_leverage <= requested_leverage <= contract.max_leverage):
        return False, "UNSUPPORTED_LEVERAGE"
    return True, "ELIGIBLE"


def build_universe(
    assets: tuple[RankedAsset, ...],
    contracts: dict[str, FuturesContract],
    *,
    now_ms: int,
    requested_leverage: int = 20,
    min_volume_usdt: Decimal = Decimal("1000000"),
    max_spread_bps: Decimal = Decimal("30"),
) -> UniverseSnapshot:
    """Rank by capitalisation, but require actual Bitget tradability.

    Rank source (e.g. CoinGecko /coins/markets) and stablecoin/wrapped/metal
    metadata classification must be obtained and audited by a separate data
    source. All snapshot timestamps are checked. The optional 1m USD 24h
    volume / 30bp spread limits are provisional PAPER research parameters.
    They must be calibrated before any deployment.
    """
    if (type(assets) is not tuple or type(contracts) is not dict
            or type(now_ms) is not int or now_ms <= 0
            or type(requested_leverage) is not int
            or not 1 <= requested_leverage <= 125
            or not _money(min_volume_usdt) or not _money(max_spread_bps)):
        raise ValueError("invalid_universe_inputs")
    seen_id: set[str] = set()
    seen_ticker: set[str] = set()
    rows: list[RankedAsset] = []
    # Reject entire untrusted ranking batch with inconsistent timestamps.
    for asset in assets:
        if (type(asset) is not RankedAsset
                or type(asset.asset_id) is not str or not asset.asset_id
                or type(asset.ticker) is not str
                or COIN.fullmatch(asset.ticker) is None
                or type(asset.market_cap_rank) is not int
                or asset.market_cap_rank < 1
                or not _money(asset.market_cap_usd)
                or asset.market_cap_usd <= 0
                or asset.classification not in (
                    "native", "stablecoin", "wrapped", "tokenized_metal", "unknown")
                or type(asset.observed_ms) is not int
                or not 0 <= now_ms - asset.observed_ms <= CAP_MAX_AGE_MS):
            raise ValueError("untrusted_ranked_asset")
        if asset.asset_id in seen_id:
            raise ValueError("duplicate_asset_id")
        seen_id.add(asset.asset_id)
        rows.append(asset)
    if len({a.market_cap_rank for a in rows}) != len(rows):
        raise ValueError("duplicate_market_cap_rank")
    rows.sort(key=lambda x: (x.market_cap_rank, -x.market_cap_usd, x.asset_id))
    chosen: list[SelectedMarket] = []
    for asset in rows:
        if len(chosen) == CRYPTO_SLOTS:
            break
        if asset.classification != "native":
            continue
        symbol = asset.ticker + "USDT"
        if symbol in METAL_SYMBOLS or symbol in seen_ticker:
            continue
        seen_ticker.add(symbol)
        valid, _ = _contract_ok(
            contracts.get(symbol), symbol=symbol, now_ms=now_ms,
            min_volume_usdt=min_volume_usdt,
            max_spread_bps=max_spread_bps,
            requested_leverage=requested_leverage,
        )
        if not valid:
            # Move to the next ranked, independently vetted asset.
            continue
        chosen.append(SelectedMarket(
            symbol=symbol, kind="crypto", tradeable=True, reason="CAP_RANK_AND_BITGET_OK",
            crypto_rank=asset.market_cap_rank, asset_id=asset.asset_id,
        ))
    for symbol in METAL_SYMBOLS:
        valid, reason = _contract_ok(
            contracts.get(symbol), symbol=symbol, now_ms=now_ms,
            min_volume_usdt=min_volume_usdt,
            max_spread_bps=max_spread_bps,
            requested_leverage=requested_leverage,
        )
        # Metals have reserved slots even when Bitget reports unavailable:
        # never silently substitute a 24th crypto or duplicate PAXG/XAUT.
        chosen.append(SelectedMarket(
            symbol=symbol, kind="metal", tradeable=valid, reason=reason,
        ))
    if len({x.symbol for x in chosen}) != len(chosen):
        raise ValueError("universe_symbol_collision")
    return UniverseSnapshot(
        asof_ms=now_ms, markets=tuple(chosen),
        crypto_count=len(chosen) - len(METAL_SYMBOLS),
        metal_count=len(METAL_SYMBOLS),
        complete=len(chosen) == UNIVERSE_SLOTS and all(x.tradeable for x in chosen),
    )


def pick_ai_shortlist(
    universe: UniverseSnapshot,
    signals: tuple[SignalScreen, ...],
    *,
    now_ms: int,
    slots: int = DEFAULT_AI_SHORTLIST,
) -> ScanResult:
    """One deterministic shortlist, shared by all three AI runners.

    All 25 may be observed using non-AI market data first. The eight-or-fewer
    strongest timely signals then receive deeper AI attention. Balanced
    LONG/SHORT quota prevents an all-SHORT shortlist solely due to ranking,
    but does NOT force either side to trade. Final execution remains risk-gated.
    """
    if (type(universe) is not UniverseSnapshot
            or type(signals) is not tuple
            or type(now_ms) is not int or now_ms <= 0
            or type(slots) is not int or not 1 <= slots <= UNIVERSE_SLOTS
            or universe.mode != "PAPER_OFFLINE_READONLY"
            or not 0 <= now_ms - universe.asof_ms <= CONTRACT_MAX_AGE_MS):
        raise ValueError("invalid_scan_request")
    candidates = set(universe.tradeable_symbols)
    found: dict[str, SignalScreen] = {}
    for signal in signals:
        if (type(signal) is not SignalScreen
                or signal.symbol not in candidates
                or signal.symbol in found
                or signal.side not in ("LONG", "SHORT", "NO_TRADE")
                or type(signal.quality) is not Decimal
                or not signal.quality.is_finite()
                or not Decimal("0") <= signal.quality <= Decimal("1")
                or type(signal.market_data_timestamp_ms) is not int
                or type(signal.closed_bars_only) is not bool
                or type(signal.contract_liquid) is not bool):
            raise ValueError("invalid_signal_batch")
        found[signal.symbol] = signal
    usable = [
        s for s in found.values()
        if (s.side in ("LONG", "SHORT")
            and s.closed_bars_only and s.contract_liquid
            and 0 <= now_ms - s.market_data_timestamp_ms <= BAR_MAX_AGE_MS)
    ]
    sorter = lambda s: (-s.quality, s.symbol)
    bullish = sorted((s for s in usable if s.side == "LONG"), key=sorter)
    bearish = sorted((s for s in usable if s.side == "SHORT"), key=sorter)
    # Reserve half of each shortlist for each side WHEN candidates exist.
    half = slots // 2
    selected = bullish[:half] + bearish[:half]
    remaining = [s for s in sorted(usable, key=sorter) if s not in selected]
    selected += remaining[:slots - len(selected)]
    # Rank chosen opportunities by score to avoid hidden position-order bias.
    selected.sort(key=sorter)
    if len({s.symbol for s in selected}) != len(selected):
        raise ValueError("duplicate_selected_signal")
    return ScanResult(
        watched_symbols=tuple(x.symbol for x in universe.markets),
        ai_shortlist=tuple(s.symbol for s in selected),
        bullish_candidates=tuple(s.symbol for s in selected if s.side == "LONG"),
        bearish_candidates=tuple(s.symbol for s in selected if s.side == "SHORT"),
    )
