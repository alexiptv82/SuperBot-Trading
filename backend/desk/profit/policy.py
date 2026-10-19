"""Explicit research configuration. No production defaults."""
from dataclasses import dataclass, asdict
import hashlib
import json
from .liquidable import finite


@dataclass(frozen=True)
class Policy:
    portfolio: str
    version: str
    arm_atr: float
    confirmations: int
    giveback_atr: float
    tight_atr: float
    trend_multiplier: float
    range_multiplier: float
    high_vol_multiplier: float
    no_peak_ms: int
    reversal_threshold: float
    partial_fraction: float = 0.0

    def __post_init__(self):
        values = asdict(self)
        finite(*(v for k,v in values.items() if k not in ("portfolio", "version")))
        if self.portfolio not in ("hawk", "bull") or not self.version or type(self.confirmations) is not int or self.confirmations < 1 or type(self.no_peak_ms) is not int or self.no_peak_ms <= 0:
            raise ValueError("invalid policy")
        if min(self.arm_atr, self.giveback_atr, self.tight_atr, self.trend_multiplier, self.range_multiplier, self.high_vol_multiplier) <= 0 or self.tight_atr > self.giveback_atr or not 0 < self.reversal_threshold <= 1 or not 0 <= self.partial_fraction < 1 or (self.portfolio == "hawk" and self.partial_fraction):
            raise ValueError("invalid policy bounds")

    @property
    def config_hash(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
