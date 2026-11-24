"""Interfaccia analista principale (DeepSeek) — solo contratti e mock offline.

Nessuna chiamata di rete. Il mock restituisce decisioni controllate per i test.
Il monitor continuo è modellato come callback periodico o event-driven.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Mapping

from .contracts import BrainDecision, DecisionKind, MarketContext, OpenProposal


class Analyst(ABC):
    @abstractmethod
    def analyze(self, context: MarketContext, open_positions: list[Mapping]) -> BrainDecision:
        """Analisi principale. Può restituire NO_TRADE."""


class MockDeepSeekAnalyst(Analyst):
    """Mock deterministico per test offline. Nessun fallback meccanico."""

    def __init__(self, force_no_trade: bool = False):
        self.force_no_trade = force_no_trade
        self.call_count = 0

    def analyze(self, context: MarketContext, open_positions: list[Mapping]) -> BrainDecision:
        self.call_count += 1
        if self.force_no_trade or context.regime == "UNKNOWN":
            return BrainDecision(
                kind=DecisionKind.NO_TRADE,
                rationale="DeepSeek: condizioni non sufficientemente chiare",
                sources=["deepseek:mock"],
                occurred_at_ms=context.timestamp_ms,
            )
        # Esempio controllato di proposta OPEN solo se regime TRENDING e nessun conflitto
        if context.regime == "TRENDING" and not open_positions:
            proposal = OpenProposal(
                symbol=context.symbol,
                side=1,
                entry_price=context.price,
                stop_price=context.price * Decimal("0.98"),
                leverage=2,
                rationale="Mock trend following",
                confidence=0.6,
                originating_ai="deepseek",
                context_hash="mock",
            )
            return BrainDecision(
                kind=DecisionKind.OPEN,
                proposal=proposal,
                rationale="DeepSeek propone ingresso in trend",
                sources=["deepseek:mock"],
                occurred_at_ms=context.timestamp_ms,
            )
        return BrainDecision(
            kind=DecisionKind.HOLD,
            rationale="DeepSeek: mantenere, nessuna nuova azione",
            sources=["deepseek:mock"],
            occurred_at_ms=context.timestamp_ms,
        )
