"""Revisore selettivo (Claude) — solo per casi complessi.

Attivato solo quando: confidence bassa, regime change, segnali Falco/Toro in conflitto,
o proposta che supera soglie di rischio.
Nessuna chiamata reale.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .contracts import BrainDecision, DecisionKind, ProposalStatus


class Reviewer(ABC):
    @abstractmethod
    def review(self, decision: BrainDecision, complexity_reason: str) -> BrainDecision:
        """Può approvare, rifiutare o modificare. NO_TRADE resta valido."""


class MockClaudeReviewer(Reviewer):
    def __init__(self, always_approve: bool = False):
        self.always_approve = always_approve

    def review(self, decision: BrainDecision, complexity_reason: str) -> BrainDecision:
        if decision.kind == DecisionKind.NO_TRADE:
            return decision  # non si forza un trade
        if self.always_approve:
            decision.status = ProposalStatus.APPROVED
            decision.rationale += " | Claude: approvato"
            decision.sources.append("claude:mock")
            return decision
        # Default conservativo: rifiuta casi complessi non chiari
        decision.kind = DecisionKind.NO_TRADE
        decision.status = ProposalStatus.REJECTED
        decision.rationale = f"Claude rifiuta per complessità: {complexity_reason}"
        decision.sources.append("claude:mock")
        return decision
