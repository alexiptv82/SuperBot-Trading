"""Brain V3 F2 — contratti isolati per motore AI PAPER.

Dipende solo dalle interfacce F1 (events.Event, risk.RiskQuote) senza importarle qui
per mantenere isolamento fino a integrazione esplicita.
Nessuna chiamata AI reale, nessun side effect.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Optional


class DecisionKind(str, Enum):
    NO_TRADE = "NO_TRADE"
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    MODIFY_STOP = "MODIFY_STOP"
    HOLD = "HOLD"  # rivalutazione senza azione


class ProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RISK_REJECTED = "RISK_REJECTED"
    EXECUTED_PAPER = "EXECUTED_PAPER"  # solo dopo risk quote OK e journal


@dataclass(frozen=True)
class MarketContext:
    symbol: str
    price: Decimal
    timestamp_ms: int
    regime: str  # es. "TRENDING", "RANGING", "VOLATILE", "UNKNOWN"
    falco_signal: Optional[Mapping[str, Any]] = None
    toro_signal: Optional[Mapping[str, Any]] = None
    source: str = "market_feed"  # tracciabilità


@dataclass(frozen=True)
class OpenProposal:
    symbol: str
    side: int  # +1 / -1
    entry_price: Decimal
    stop_price: Decimal
    leverage: int
    rationale: str
    confidence: float  # 0..1
    originating_ai: str  # "deepseek" | "claude"
    context_hash: str


@dataclass(frozen=True)
class CloseProposal:
    position_id: str
    reason: str
    originating_ai: str
    confidence: float


@dataclass(frozen=True)
class StopModifyProposal:
    position_id: str
    new_stop: Decimal
    reason: str
    originating_ai: str


@dataclass
class BrainDecision:
    kind: DecisionKind
    proposal: Optional[Any] = None  # Open/Close/StopModify
    risk_quote: Optional[Any] = None  # RiskQuote da F1
    rationale: str = ""
    sources: list[str] = field(default_factory=list)
    occurred_at_ms: int = 0
    status: ProposalStatus = ProposalStatus.DRAFT
    journal_event_id: Optional[str] = None


@dataclass(frozen=True)
class MemoryEpisode:
    """Episodio di memoria con provenienza esplicita."""
    episode_id: str
    decision: BrainDecision
    outcome: Optional[Mapping[str, Any]] = None  # PnL, fill, etc. quando disponibile
    provenance: list[str] = field(default_factory=list)  # ["deepseek:analysis", "risk:quote", "falco:signal"]
    stored_event_id: Optional[str] = None
