"""Arbitro — bridge from DirectorAdvice (contracts v1.1) to executable orders.

The AI shadow produces a DirectorAdvice via contracts.v1_1. The Arbitro
checks legality (portfolio state, risk limits, conviction threshold) and —
only for OPEN — computes the allowed margin via size_position.

Design rules (C1-C5 from CONVENTIONS_V1_1.md):
  - The AI selects a Candidate and declares conviction; the Arbitro decides size.
  - No automatic conviction→margin mapping. Rejection is always preferred
    over silently increasing risk.
  - MOVE_STOP is not in contracts v1/v1.1: the AI cannot request it.
  - Monotone risk: no advice can widen a stop or increase position size.
  - This module never connects to any exchange or reads env secrets.

Imports from backend.director.contracts (work/director-chatgpt) resolve
after the two branches are merged into work/director-v1-unified.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# NOTE: contracts live in work/director-chatgpt; resolve after merge.
from backend.director.contracts import v1_1 as c
from backend.director.ai_shadow.decisions import size_position


# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class ArbitroConfig:
    risk_pct: float = 1.0            # % of equity risked per trade at stop
    max_margin_trade: float = 300.0  # USD hard cap per single position
    max_open: int = 4                # max concurrent positions in portfolio
    min_conviction: int = 55         # open_conviction_0_100 minimum to open
    min_sl_pct: float = 0.3          # stop must be at least 0.3% away from entry
    max_sl_pct: float = 8.0          # stop must be at most 8% away from entry
    min_rr: float = 1.5              # minimum risk-reward ratio (|tp-entry|/|sl-entry|)
    tier_cap: int = 20               # exchange leverage tier cap for this asset
    slip_bp: float = 5.0             # estimated fill slippage in basis points
    maint_rate: float = 0.01         # maintenance margin rate
    sl_liq_frac: float = 0.7         # fraction of dist-to-liquidation at stop level


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class ArbitroResult:
    """Outcome of one arbitrate() call. One advice → exactly one result."""
    advice_id: str
    portfolio_id: str
    action: str
    accepted: bool
    reason: str
    order: Optional[dict] = None         # plan_cycle-compatible dict if accepted
    margin_usd: Optional[float] = None   # computed margin for OPEN orders
    leverage: Optional[int] = None       # computed leverage for OPEN orders
    planned_risk_usd: Optional[float] = None  # expected loss if stop hit


# ── Arbitro ───────────────────────────────────────────────────────────────────

class Arbitro:
    """Validate one DirectorAdvice and return an ArbitroResult.

    Stateless between calls. Instantiate once per portfolio; call arbitrate()
    once per bar with fresh portfolio snapshot, candidates and prices.

    Usage:
        arb = Arbitro(ArbitroConfig())
        result = arb.arbitrate(advice, portfolio, candidates, px, bar_t)
        if result.accepted and result.order:
            paper_account.execute(result.order)
    """

    def __init__(self, cfg: ArbitroConfig) -> None:
        self.cfg = cfg

    def arbitrate(
        self,
        advice: c.DirectorAdvice,
        portfolio: c.PortfolioSnapshot,
        candidates: dict[str, c.Candidate],
        px: dict[str, float],
        bar_t: int,
    ) -> ArbitroResult:
        """Validate advice and return result. Never raises; rejection reasons are explicit."""

        def rej(reason: str) -> ArbitroResult:
            return ArbitroResult(
                advice_id=advice.advice_id,
                portfolio_id=advice.portfolio_id,
                action=advice.action,
                accepted=False,
                reason=reason,
            )

        def ok(order: Optional[dict] = None, **extra) -> ArbitroResult:
            return ArbitroResult(
                advice_id=advice.advice_id,
                portfolio_id=advice.portfolio_id,
                action=advice.action,
                accepted=True,
                reason="ok",
                order=order,
                **extra,
            )

        # ── Portfolio-level guards ────────────────────────────────────────────
        if advice.portfolio_id != portfolio.portfolio_id:
            return rej("portfolio_id_mismatch")
        if portfolio.halted:
            return rej("portfolio_halted")

        action = advice.action

        # ── NO_TRADE ──────────────────────────────────────────────────────────
        if action == "NO_TRADE":
            return ArbitroResult(
                advice_id=advice.advice_id,
                portfolio_id=advice.portfolio_id,
                action=action, accepted=True, reason="no_trade",
            )

        # ── HOLD / REASSESS ───────────────────────────────────────────────────
        if action in ("HOLD", "REASSESS"):
            pos = _find_position(portfolio, advice.position_key)
            if pos is None:
                return rej("position_not_found")
            return ok(order={
                "kind": "hold", "symbol": pos.symbol,
                "action": action,
                "thesis": advice.thesis, "bar_t": bar_t,
            })

        # ── CLOSE ─────────────────────────────────────────────────────────────
        if action == "CLOSE":
            pos = _find_position(portfolio, advice.position_key)
            if pos is None:
                return rej("position_not_found")
            return ok(order={
                "kind": "close", "symbol": pos.symbol,
                "thesis": advice.thesis, "bar_t": bar_t,
            })

        # ── PARTIAL_CLOSE ─────────────────────────────────────────────────────
        if action == "PARTIAL_CLOSE":
            pos = _find_position(portfolio, advice.position_key)
            if pos is None:
                return rej("position_not_found")
            f = advice.close_fraction
            # v1_1 already enforces 0 < f < 1; we add operational minimum 10%
            if f is None or not (0.1 <= f <= 0.9):
                return rej("frazione_non_valida")
            return ok(order={
                "kind": "partial", "symbol": pos.symbol, "fraction": f,
                "thesis": advice.thesis, "bar_t": bar_t,
            })

        # ── OPEN ──────────────────────────────────────────────────────────────
        if action == "OPEN":
            if advice.selected_candidate_id is None:
                return rej("no_candidate_selected")
            cand = candidates.get(advice.selected_candidate_id)
            if cand is None:
                return rej("candidate_not_found")

            # Conviction gate (subjective score, not probability)
            conv = advice.open_conviction_0_100
            if conv is None or conv < self.cfg.min_conviction:
                return rej("convinzione_bassa")

            sym = cand.symbol
            last = px.get(sym)
            if last is None:
                return rej("senza_dati")

            # Slot check
            open_syms = {p.symbol for p in portfolio.positions}
            if sym in open_syms:
                return rej("posizione_gia_aperta")
            if len(portfolio.positions) >= self.cfg.max_open:
                return rej("slot_pieni")

            # Structural checks from Candidate (already validated at construction)
            sl = cand.stop
            tp = cand.target
            if tp is None:
                return rej("tp_mancante")
            side = 1 if cand.side == "LONG" else -1
            if (side == 1 and not (sl < last < tp)) or (side == -1 and not (tp < last < sl)):
                return rej("livelli_dal_lato_sbagliato")

            sl_pct = abs(last - sl) / last * 100.0
            if sl_pct < self.cfg.min_sl_pct:
                return rej("stop_troppo_vicino")
            if sl_pct > self.cfg.max_sl_pct:
                return rej("stop_troppo_lontano")
            if abs(tp - last) / abs(last - sl) < self.cfg.min_rr:
                return rej("rr_basso")

            # Size: Arbitro decides margin; AI never does (CONVENTIONS C2)
            margin, lev_or_reason, planned_risk = size_position(
                self.cfg,
                portfolio.equity_usd,
                side,
                last,
                sl,
                self.cfg.tier_cap,
                self.cfg.slip_bp,
                self.cfg.maint_rate,
                self.cfg.sl_liq_frac,
            )
            if margin is None:
                return rej(f"sizing:{lev_or_reason}")

            return ok(
                order={
                    "kind": "open",
                    "symbol": sym,
                    "side": side,
                    "sl": sl,
                    "tp": tp,
                    "conviction": conv,
                    "horizon_bars": int(cand.time_exit_bars),
                    "thesis": advice.thesis,
                    "invalidate_if": advice.invalidate_if,
                    "ref_px": last,
                    "bar_t": bar_t,
                    "margin_usd": margin,
                    "leverage": lev_or_reason,
                },
                margin_usd=margin,
                leverage=lev_or_reason,
                planned_risk_usd=planned_risk,
            )

        return rej(f"azione_sconosciuta:{action}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_position(
    portfolio: c.PortfolioSnapshot, position_key: Optional[str]
) -> Optional[c.PositionView]:
    if position_key is None:
        return None
    for p in portfolio.positions:
        if p.position_key == position_key:
            return p
    return None
