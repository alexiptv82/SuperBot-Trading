"""Causal delayed-entry adapter for unchanged outcomes.evaluate_path v1.

Candidate.signal_bar_open_ms remains the *original* signal timestamp; a
candidate may wait several bars before entry. Never relabel the signal as a
later bar in the audit record. The existing outcome engine is used unchanged.
"""
from __future__ import annotations

from typing import Sequence

from . import v1_1
from .outcomes import OHLC, Outcome, evaluate_path


def evaluate_candidate_path(candidate: v1_1.Candidate, bars: Sequence[OHLC],
                            *, funding_bp_8h_long: float = 1.0) -> Outcome:
    if not isinstance(candidate, v1_1.Candidate):
        raise TypeError("v1.1 Candidate required")
    expected = candidate.signal_bar_open_ms + candidate.bar_ms
    if bars:
        if bars[0].open_ms != expected:
            raise ValueError("GAP/LOOKAHEAD before candidate entry: first bar must immediately follow signal")
        for prev, curr in zip(bars, bars[1:]):
            if curr.open_ms != prev.open_ms + candidate.bar_ms:
                raise ValueError("GAP: no interpolation or silent skipped bars before/after delayed entry")
    chosen = next((i for i, bar in enumerate(bars)
                   if bar.open_ms >= candidate.earliest_entry_ms), None)
    if chosen is None:
        return evaluate_path(signal_open_ms=candidate.signal_bar_open_ms,
                             bar_ms=candidate.bar_ms, side=candidate.side,
                             stop=candidate.stop, target=candidate.target,
                             bars=[], max_hold_bars=candidate.time_exit_bars,
                             cost_bp_roundtrip=candidate.cost_bp_roundtrip,
                             funding_bp_8h_long=funding_bp_8h_long)
    selected = bars[chosen:]
    # Rebase only the pure path helper, which requires a bar immediately after
    # its supplied offset. The Candidate signal time is NOT rewritten.
    return evaluate_path(signal_open_ms=selected[0].open_ms - candidate.bar_ms,
                         bar_ms=candidate.bar_ms, side=candidate.side,
                         stop=candidate.stop, target=candidate.target,
                         bars=selected, max_hold_bars=candidate.time_exit_bars,
                         cost_bp_roundtrip=candidate.cost_bp_roundtrip,
                         funding_bp_8h_long=funding_bp_8h_long)
