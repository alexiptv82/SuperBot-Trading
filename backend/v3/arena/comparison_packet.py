"""Pure three-model AI Arena *comparison-only* common evidence contract.

One identical verified 25-market payload and identical human-readable system
instruction for DeepSeek, Qwen and MiniMax. Models may use different provider-
specific JSON response_format transports; their MARKET INPUT never differs.

This module cannot import secrets, perform network I/O, write journals, price
orders, or grant trading authority. A CANDIDATE here is NOT an OPEN.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re

from backend.v3.arena.compact_market import CompactMarketEvidence

SCHEMA = "arena_three_ai_common_candidate_v1"
CLASSIFICATION = "RESEARCH_ONLY_NOT_TRADE_APPROVED"
LANES = ("deepseek", "qwen", "minimax")
METALS = frozenset(("XAUUSDT", "XAGUSDT"))

# Model output is an observation, not an order or a trading contract.
# Do not copy execution geometry out of the AI's response.
COMMON_SYSTEM = (
    "You are comparing market opportunities for a PAPER-ONLY research audit. "
    "The user message is a time-frozen snapshot of the exact same 25 markets "
    "that other models receive. Use ONLY that snapshot; do not add news, "
    "outside prices, hindsight or candles after asof_ms. "
    "Select at most ONE best-supported candidate across all 25 markets, "
    "or select NO_TRADE. There is no obligation to trade. "
    "Never output an order, leverage, stop, take profit or position sizing. "
    "Return ONLY one JSON object with EXACTLY these five keys: "
    "action, symbol, side, confidence, reason_code. "
    "For a candidate use action=CANDIDATE, symbol=<one listed symbol>, "
    "side=LONG or SHORT, confidence=<number 0..1>, "
    "reason_code=<UPPERCASE_UNDERSCORE_IDENTIFIER>. "
    "For NO_TRADE use action=NO_TRADE, symbol='', side=NONE, "
    "confidence=0, reason_code=<UPPERCASE_UNDERSCORE_IDENTIFIER>. "
    "The response is comparison evidence only; it never authorizes trading."
)


@dataclass(frozen=True)
class CommonMarketPacket:
    compact_sha256: str
    canonical_market_bytes: bytes
    symbols: tuple[str, ...]
    asof_ms: int
    policy_sha256: str
    classification: str = CLASSIFICATION

    def verify(self) -> None:
        if (type(self.canonical_market_bytes) is not bytes
                or sha256(self.canonical_market_bytes).hexdigest()
                != self.compact_sha256
                or sha256(COMMON_SYSTEM.encode("utf-8")).hexdigest()
                != self.policy_sha256
                or type(self.symbols) is not tuple
                or len(self.symbols) != 25
                or len(set(self.symbols)) != 25
                or not METALS.issubset(self.symbols)
                or type(self.asof_ms) is not int
                or self.asof_ms <= 0
                or self.classification != CLASSIFICATION):
            raise ValueError("ARENA_COMMON_PACKET_INTEGRITY")
        try:
            doc = json.loads(self.canonical_market_bytes)
        except (ValueError, UnicodeError):
            raise ValueError("ARENA_COMMON_PACKET_JSON") from None
        if (type(doc) is not dict
                or doc.get("classification") != "PROVISIONAL_NOT_TRADE_APPROVED"
                or doc.get("contains_trading_authorization") is not False
                or doc.get("contains_raw_candles") is not False
                or doc.get("asof_ms") != self.asof_ms
                or type(doc.get("markets")) is not list
                or tuple(x.get("symbol") for x in doc["markets"]
                         if type(x) is dict) != self.symbols):
            raise ValueError("ARENA_COMMON_PACKET_SCOPE")

    def identical_messages(self, provider: str) -> tuple[dict, dict]:
        if provider not in LANES:
            raise ValueError("ARENA_COMMON_PROVIDER_UNKNOWN")
        self.verify()
        return (
            {"role": "system", "content": COMMON_SYSTEM},
            {"role": "user", "content": self.canonical_market_bytes.decode("utf-8")},
        )


def build_common_packet(compact: CompactMarketEvidence) -> CommonMarketPacket:
    if type(compact) is not CompactMarketEvidence:
        raise ValueError("ARENA_COMMON_WRONG_EVIDENCE")
    compact.verify()
    doc = json.loads(compact.canonical_bytes)
    markets = doc.get("markets")
    if (type(markets) is not list or len(markets) != 25
            or any(type(x) is not dict or type(x.get("symbol")) is not str
                   for x in markets)):
        raise ValueError("ARENA_COMMON_EXPECTED_25_MARKETS")
    symbols = tuple(x["symbol"] for x in markets)
    if (len(set(symbols)) != 25 or not METALS.issubset(symbols)
            or any(type(x.get("market")) is not dict
                   or x["market"].get("regime") in ("UNKNOWN", None)
                   or type(x["market"].get("timeframes")) is not list
                   or len(x["market"]["timeframes"]) != 3
                   or any(t.get("status") != "ok"
                          for t in x["market"]["timeframes"]
                          if type(t) is dict)
                   for x in markets)):
        raise ValueError("ARENA_COMMON_MARKETS_NOT_READY")
    packet = CommonMarketPacket(
        compact_sha256=compact.sha256_hex,
        canonical_market_bytes=compact.canonical_bytes,
        symbols=symbols,
        asof_ms=compact.asof_ms,
        policy_sha256=sha256(COMMON_SYSTEM.encode("utf-8")).hexdigest(),
    )
    packet.verify()
    messages = [packet.identical_messages(lane) for lane in LANES]
    if messages[0] != messages[1] or messages[1] != messages[2]:
        raise ValueError("ARENA_COMMON_MARKET_DIFFERENCE")
    return packet


@dataclass(frozen=True)
class ResearchChoice:
    action: str
    symbol: str
    side: str
    confidence: Decimal
    reason_code: str
    classification: str = CLASSIFICATION


def parse_research_choice(packet: CommonMarketPacket, raw: object) -> ResearchChoice:
    """Strict model JSON parser; never translates a candidate to an order."""
    packet.verify()
    if type(raw) is bytes:
        if len(raw) > 4096:
            raise ValueError("ARENA_CHOICE_TOO_LARGE")
        raw = raw.decode("utf-8")
    if type(raw) is str:
        if len(raw) > 4096:
            raise ValueError("ARENA_CHOICE_TOO_LARGE")
        try:
            raw = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ValueError("ARENA_CHOICE_INVALID_JSON") from None
    if (type(raw) is not dict
            or set(raw) != {"action", "symbol", "side",
                            "confidence", "reason_code"}
            or type(raw["action"]) is not str
            or type(raw["symbol"]) is not str
            or type(raw["side"]) is not str
            or type(raw["reason_code"]) is not str
            or re.fullmatch(r"[A-Z][A-Z0-9_]{2,47}",
                            raw["reason_code"]) is None
            or type(raw["confidence"]) not in (int, float)):
        raise ValueError("ARENA_CHOICE_INVALID_FIELDS")
    try:
        confidence = Decimal(str(raw["confidence"]))
    except (ValueError, InvalidOperation):
        raise ValueError("ARENA_CHOICE_INVALID_CONFIDENCE") from None
    if not confidence.is_finite() or confidence < 0 or confidence > 1:
        raise ValueError("ARENA_CHOICE_INVALID_CONFIDENCE")
    if raw["action"] == "NO_TRADE":
        if raw["symbol"] != "" or raw["side"] != "NONE" or confidence != 0:
            raise ValueError("ARENA_CHOICE_MALFORMED_NO_TRADE")
    elif raw["action"] == "CANDIDATE":
        if (raw["symbol"] not in packet.symbols
                or raw["side"] not in ("LONG", "SHORT")
                or confidence <= 0):
            raise ValueError("ARENA_CHOICE_INVALID_CANDIDATE")
    else:
        raise ValueError("ARENA_CHOICE_ACTION_NOT_ALLOWED")
    return ResearchChoice(
        action=raw["action"], symbol=raw["symbol"], side=raw["side"],
        confidence=confidence, reason_code=raw["reason_code"],
    )
