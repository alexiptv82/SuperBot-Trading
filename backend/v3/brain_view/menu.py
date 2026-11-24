"""Biblioteca L4: only closed-vocabulary strategy metadata reaches the model.

Pass ``menu_ids(build_menu(library))`` as ``allowed_strategy_ids`` to BrainEngine.
That engine alone decides whether a proposed label can reach the journal.
"""
from __future__ import annotations

from dataclasses import dataclass
from backend.v3.knowledge.library import (
    DATA_CANDLES, FAMILIES, HOLDING_STYLES, REGIMES, Library, testable_now,
)
from backend.v3.strategy_label import AI_PREFIX, is_valid_strategy_id


@dataclass(frozen=True)
class MenuItem:
    strategy_id: str
    family: str
    holding_style: str
    regimes: tuple[str, ...]


def build_menu(library: Library) -> tuple[MenuItem, ...]:
    """Select only currently testable candle-only cards, preserving library order."""
    if type(library) is not Library:
        raise ValueError("invalid_library") from None
    return tuple(MenuItem(s.id, s.family, s.holding_style, s.candidate_regimes)
                 for s in library.strategies if testable_now(s) == DATA_CANDLES)


def menu_ids(menu: tuple[MenuItem, ...]) -> frozenset[str]:
    """Validate menu, return the permitted library ids for BrainEngine."""
    if type(menu) is not tuple:
        raise ValueError("invalid_menu") from None
    found = set()
    for item in menu:
        if (type(item) is not MenuItem
                or not is_valid_strategy_id(item.strategy_id)
                or item.strategy_id.startswith(AI_PREFIX)
                or item.strategy_id in found
                or type(item.family) is not str or item.family not in FAMILIES
                or type(item.holding_style) is not str or item.holding_style not in HOLDING_STYLES
                or type(item.regimes) is not tuple
                or any(type(r) is not str or r not in REGIMES for r in item.regimes)):
            raise ValueError("invalid_menu") from None
        found.add(item.strategy_id)
    return frozenset(found)


def menu_payload(menu: tuple[MenuItem, ...]) -> list[dict]:
    """Return only closed-token columns, never strategy names or hypothesis text."""
    menu_ids(menu)
    return [{"id": x.strategy_id, "family": x.family,
             "style": x.holding_style, "regimes": list(x.regimes)} for x in menu]
