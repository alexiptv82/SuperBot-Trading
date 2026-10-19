"""Uncalibrated evidence score, NOT a probability of reversal."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Reversal:
    score: float
    families: tuple[str, ...]
    evidence: tuple[str, ...]


def assess(features, side):
    if side not in (-1, 1):
        raise ValueError("invalid side")
    if not features.valid:
        return Reversal(0, (), ())
    families, evidence = [], []
    if side * features.ema_slope < 0 and side * (features.rsi-50) < 0:
        families.append("momentum")
        evidence.append("EMA and RSI oppose position (one family)")
    if features.lower_break if side == 1 else features.upper_break:
        families.append("structure")
        evidence.append("close breaks previous range against position")
    return Reversal(len(families)/2, tuple(families), tuple(evidence))
