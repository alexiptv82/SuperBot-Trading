"""Read-only AI Arena universe bridge: 8-symbol Brain baseline vs 25-market research.

This is an inspection and configuration-planning boundary, NOT a trading
permission or a new runner. The current DeepSeek runner remains unchanged.
The Arena selection is provisional until asset identity, contract rules,
market freshness and multi-model execution isolation are independently gated.
No disk/network/model calls, risk mutation, service controls or orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

from backend.v3.arena.comparison_packet import CommonMarketPacket, LANES
from backend.v3.runner.config import RunnerConfig

METALS = frozenset(("XAUUSDT", "XAGUSDT"))
SHA_RE = re.compile(r"[a-f0-9]{64}\Z")
COIN_ID = re.compile(r"[a-z0-9-]{1,100}\Z")
MAX_SNAPSHOT_AGE_MS = 15 * 60_000
CAPITAL = Decimal("2000")
PROVISIONAL = "RESEARCH_ONLY_NOT_TRADE_APPROVED"


@dataclass(frozen=True)
class VerifiedMarketIdentity:
    """Externally reviewed mapping; unverified CoinGecko symbol matches do NOT count.

    Such records can be assessed for consistency, but are NOT independent
    authorization to enable a PAPER runner. This module cannot grant one.
    """
    symbol: str
    category: str                 # "crypto_native" or "metal"
    coingecko_id: str              # crypto only; metals use ""
    market_cap_rank: int | None    # crypto only; metals use None
    bitget_contract_symbol: str
    contract_status: str           # exact "normal" from recent public catalog
    quote_asset: str               # USDT only
    exchange_max_leverage: int
    identity_reviewed: bool        # external independent asset ID review


@dataclass(frozen=True)
class TrialUniverseReview:
    source_packet_sha256: str
    snapshot_asof_ms: int
    legacy_brain_symbols: tuple[str, ...]
    candidates: tuple[str, ...]
    per_ai: tuple[tuple[str, tuple[str, ...]], ...]
    issues: tuple[str, ...]
    classification: str = PROVISIONAL
    executable: bool = False

    @property
    def ready_for_further_integration(self) -> bool:
        # The review may allow subsequent engineering, never enable orders.
        return not self.issues and not self.executable


def review_equal_universe(
    market: CommonMarketPacket, baseline: RunnerConfig, *, now_ms: int,
    identities: tuple[VerifiedMarketIdentity, ...] | None = None,
) -> TrialUniverseReview:
    """Build identical proposed 25-symbol sets for three independent PAPER runs.

    1. Must be exactly the common-market packet already used in Arena research.
    2. Retain the existing Brain config, including risk, model and 8 symbols.
    3. Do NOT assume a symbol matched by name is the right native coin.
    4. Do NOT assert fresh data or approve any position on the strength of a
       historical research snapshot.
    """
    if type(market) is not CommonMarketPacket or type(baseline) is not RunnerConfig:
        raise ValueError("ARENA_UNIVERSE_INVALID_INPUT")
    market.verify()
    if type(now_ms) is not int or now_ms <= 0 or now_ms < market.asof_ms:
        raise ValueError("ARENA_UNIVERSE_INVALID_TIME")
    if (len(market.symbols) != 25 or not METALS.issubset(market.symbols)
            or len(set(market.symbols)) != 25
            or not SHA_RE.fullmatch(market.packet_sha256)):
        raise ValueError("ARENA_UNIVERSE_INVALID_MARKETS")

    issues: list[str] = []
    age = now_ms - market.asof_ms
    if age > MAX_SNAPSHOT_AGE_MS:
        issues.append("STALE_RESEARCH_SNAPSHOT")
    if baseline.initial_equity != CAPITAL:
        issues.append("BASELINE_CAPITAL_MISMATCH")
    if baseline.risk_policy.minimum_equity != Decimal("450"):
        issues.append("BASELINE_EQUITY_FLOOR_MISMATCH")
    if not (baseline.risk_policy.min_leverage >= 20
            and baseline.risk_policy.max_leverage <= 50):
        issues.append("BASELINE_LEVERAGE_POLICY_DIFFERENT")

    if identities is None:
        issues.append("ASSET_IDENTITY_AND_CONTRACTS_NOT_REVIEWED")
    elif type(identities) is not tuple or any(type(x) is not VerifiedMarketIdentity for x in identities):
        raise ValueError("ARENA_UNIVERSE_INVALID_IDENTITY_SET")
    else:
        if (len(identities) != 25 or
                set(x.symbol for x in identities) != set(market.symbols) or
                len(set(x.symbol for x in identities)) != 25):
            issues.append("INCOMPLETE_ASSET_IDENTITY_SET")
        else:
            seen_ids = set()
            seen_ranks = set()
            for entry in identities:
                if (entry.identity_reviewed is not True
                        or entry.bitget_contract_symbol != entry.symbol
                        or entry.contract_status != "normal"
                        or entry.quote_asset != "USDT"
                        or type(entry.exchange_max_leverage) is not int
                        or entry.exchange_max_leverage < baseline.risk_policy.min_leverage):
                    issues.append("UNVERIFIED_OR_UNTRADEABLE_CONTRACT")
                    break
                if entry.symbol in METALS:
                    if (entry.category != "metal" or entry.coingecko_id != ""
                            or entry.market_cap_rank is not None):
                        issues.append("METAL_IDENTITY_MISMATCH")
                        break
                else:
                    if (entry.category != "crypto_native"
                            or not COIN_ID.fullmatch(entry.coingecko_id)
                            or type(entry.market_cap_rank) is not int
                            or entry.market_cap_rank < 1
                            or entry.coingecko_id in seen_ids
                            or entry.market_cap_rank in seen_ranks):
                        issues.append("CRYPTO_IDENTITY_OR_RANK_AMBIGUOUS")
                        break
                    seen_ids.add(entry.coingecko_id)
                    seen_ranks.add(entry.market_cap_rank)

    # Existing Brain runner loops over EVERY configured symbol and may call
    # DeepSeek per symbol. Replacing 8 with 25 blindly would increase spend.
    # Existing config.model also forbids OpenRouter provider/model identifiers.
    # Until the shared single-call candidate selector and per-model risk/journal
    # isolation exist, all proposed sets remain strictly NON-EXECUTABLE.
    per_ai = tuple((p, market.symbols) for p in LANES)
    return TrialUniverseReview(
        source_packet_sha256=market.packet_sha256,
        snapshot_asof_ms=market.asof_ms,
        legacy_brain_symbols=baseline.symbols,
        candidates=market.symbols,
        per_ai=per_ai,
        issues=tuple(issues),
    )
