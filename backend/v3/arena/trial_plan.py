"""Pure AI Arena trial plan for three distinct 2,000-USDT PAPER wallets.

A trial plan is NOT a deploy manifest and cannot start or pause any service.
The existing DeepSeek run must be preserved; a new 14-day trial needs an
agreed T0 and a clean, separately approved new run for every AI.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.v3.arena.openrouter_transport import MODELS

PROVIDERS = ("deepseek", "qwen", "minimax")
CAPITAL_USDT = Decimal("2000")
INTERNAL_PORTFOLIO = "brain"  # Existing journal schema uses this inside EACH isolated DB.
DEFAULT_ROOT = Path("/opt/superbot-ai-arena-paper")


@dataclass(frozen=True)
class WalletPlan:
    provider: str
    model: str
    run_id: str
    internal_portfolio_id: str
    capital_usdt: Decimal
    journal: Path
    budget: Path
    heartbeat: Path
    enabled: bool = False
    approved: bool = False

    @property
    def folder(self) -> Path:
        return self.journal.parent


def build_trial_plan(
    day_utc: date, *, root: Path = DEFAULT_ROOT,
) -> tuple[WalletPlan, WalletPlan, WalletPlan]:
    """Return only paths/metadata. Do not touch filesystem or network."""
    if type(day_utc) is not date or type(root) is not Path or not root.is_absolute():
        raise ValueError("arena_plan_invalid")
    if ".." in root.parts or root == Path("/"):
        raise ValueError("arena_root_invalid")
    stamp = day_utc.strftime("%Y%m%d")
    model_ids = {"deepseek": "deepseek-flash", **MODELS}
    result = []
    for provider in PROVIDERS:
        run_id = f"brain-{provider}-paper{stamp}"
        folder = root / provider / run_id
        result.append(WalletPlan(
            provider=provider,
            model=model_ids[provider],
            run_id=run_id,
            internal_portfolio_id=INTERNAL_PORTFOLIO,
            capital_usdt=CAPITAL_USDT,
            journal=folder / "journal.db",
            budget=folder / "budget.db",
            heartbeat=folder / "heartbeat.json",
        ))
    wallets = tuple(result)
    if (len({w.folder for w in wallets}) != len(PROVIDERS)
            or len({w.run_id for w in wallets}) != len(PROVIDERS)):
        raise ValueError("arena_scope_collision")
    return wallets
