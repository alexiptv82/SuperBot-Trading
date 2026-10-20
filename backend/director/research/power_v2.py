"""Power calculation, effective independent unit is a UTC day/block not trade."""
from __future__ import annotations
from math import sqrt, isfinite
from statistics import NormalDist


def minimum_detectable_edge_bp(sd_bp: float, n_effective: float, *,
                                family_k: int = 2, power: float = 0.80) -> float:
    """One-sided Bonferroni alpha=.05, normal approximation.

    MDE = (z_{1-alpha/K}+z_{power}) * SD / sqrt(n_effective).
    n_effective must be derived from correlated blocks, not raw trade count.
    This is a planning bound, NOT the full rule_pool gate / significance test.
    """
    if (not isfinite(sd_bp) or sd_bp <= 0 or not isfinite(n_effective) or
            n_effective <= 1 or type(family_k) is not int or family_k < 1 or
            not 0.5 < power < 1):
        raise ValueError("bad planning parameters")
    z_alpha=NormalDist().inv_cdf(1-0.05/family_k)
    z_power=NormalDist().inv_cdf(power)
    return (z_alpha+z_power)*sd_bp/sqrt(n_effective)
