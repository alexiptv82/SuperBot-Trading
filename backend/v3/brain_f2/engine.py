"""Motore Brain F2 — ciclo decisionale offline, rispettoso del risk manager F1.

- DeepSeek analista principale con monitoraggio (simulato via chiamate ripetute).
- Claude solo su casi complessi.
- Nessun fallback automatico a strategie meccaniche.
- NO_TRADE è decisione di prima classe.
- Ogni proposta OPEN passa da quote_paper_risk (import opzionale, iniettato).
- Memoria via EventJournal (portfolio_id="brain").
- Rivalutazione periodica delle posizioni aperte.
- Strategie adattive solo come proposte, mai auto-promosse.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Optional

from .analyst import Analyst
from .contracts import (
    BrainDecision, DecisionKind, MarketContext, ProposalStatus, MemoryEpisode,
)
from .reviewer import Reviewer


class BrainEngine:
    def __init__(
        self,
        analyst: Analyst,
        reviewer: Reviewer,
        risk_quoter: Optional[Callable] = None,  # inietta quote_paper_risk di F1
        journal_append: Optional[Callable] = None,  # inietta EventJournal.append
    ):
        self.analyst = analyst
        self.reviewer = reviewer
        self.risk_quoter = risk_quoter
        self.journal_append = journal_append
        self.open_positions: list[dict] = []
        self.memory: list[MemoryEpisode] = []
        self.cycle = 0

    def step(self, context: MarketContext, complexity_threshold: float = 0.7) -> BrainDecision:
        """Un ciclo di monitoraggio. Può essere chiamato periodicamente o su evento."""
        self.cycle += 1
        decision = self.analyst.analyze(context, self.open_positions)

        # Rivalutazione posizioni esistenti (anche senza nuovi segnali)
        if self.open_positions and decision.kind == DecisionKind.HOLD:
            decision = self._reevaluate_positions(context, decision)

        # Revisore selettivo
        if self._needs_review(decision, complexity_threshold):
            decision = self.reviewer.review(decision, "complex_case")

        # Risk gate deterministico (solo per OPEN)
        if decision.kind == DecisionKind.OPEN and self.risk_quoter:
            quote = self.risk_quoter(decision.proposal)  # adattare alla firma reale
            decision.risk_quote = quote
            if not getattr(quote, "allowed", False):
                decision.kind = DecisionKind.NO_TRADE
                decision.status = ProposalStatus.RISK_REJECTED
                decision.rationale += f" | risk: {getattr(quote, 'reason', 'rejected')}"

        # Persistenza memoria con provenienza
        episode = MemoryEpisode(
            episode_id=f"brain-{self.cycle}-{context.timestamp_ms}",
            decision=decision,
            provenance=decision.sources + [f"cycle:{self.cycle}"],
        )
        self.memory.append(episode)
        if self.journal_append:
            # Costruire Event F1 e append (implementazione in integrazione)
            pass

        return decision

    def _needs_review(self, decision: BrainDecision, threshold: float) -> bool:
        if decision.kind == DecisionKind.NO_TRADE:
            return False
        # Esempio: confidence bassa o regime change
        conf = getattr(decision.proposal, "confidence", 1.0) if decision.proposal else 1.0
        return conf < threshold or "regime_change" in (decision.rationale or "")

    def _reevaluate_positions(self, context: MarketContext, decision: BrainDecision) -> BrainDecision:
        # Placeholder: può generare CLOSE o MODIFY_STOP
        # In implementazione reale confronta stop, PnL, regime
        return decision

    def propose_adaptive_strategy(self, regime: str) -> dict:
        """Proposta di strategia adattiva. NON operativa finché non valutata e approvata."""
        return {
            "type": "adaptive_proposal",
            "regime": regime,
            "status": "requires_evaluation",
            "note": "Non promuovere a operativo senza walk-forward e OK utente",
        }
