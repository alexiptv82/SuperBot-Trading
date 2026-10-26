"""Director contracts 1.1, additive to immutable v1 (never replace v1 files).

JSON wire format retains schema_version=1 (major); contract_version='1.1'.
External numpy scalar normalization belongs at the explicit source boundary.
This layer represents advice, NEVER an exchange action or authorization.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from hashlib import sha256
import json
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping, Optional

from . import v1

CONTRACT_VERSION = "1.1"


def _check_version(version: str) -> None:
    if version != CONTRACT_VERSION:
        raise ValueError("contract_version must be 1.1")


def _freeze_json(data: Any) -> Any:
    """Recursively copy/lock JSON features; reject mutable objects and NaN."""
    if isinstance(data, dict):
        if not all(isinstance(k, str) for k in data):
            raise ValueError("JSON feature map keys must be strings")
        return MappingProxyType({k: _freeze_json(v) for k, v in data.items()})
    if type(data) in (tuple, list):
        return tuple(_freeze_json(v) for v in data)
    if type(data) is float:
        if not isfinite(data):
            raise ValueError("non-finite features are not valid JSON")
        return data
    if type(data) in (str, int, bool) or data is None:
        return data
    raise ValueError("features must contain only standard JSON scalars/maps/lists")


def _thaw_json(data: Any) -> Any:
    if isinstance(data, Mapping):
        return {k: _thaw_json(v) for k, v in data.items()}
    if isinstance(data, tuple):
        return [_thaw_json(v) for v in data]
    if is_dataclass(data):
        return {f.name: _thaw_json(getattr(data, f.name)) for f in fields(data)}
    return data


def normalize_boundary(value: Any) -> Any:
    """Call ONLY on input data boundary, before validating contracts.

    Supports numpy scalar .item() without depending on numpy; never quietly
    converts '42' strings or non-finite floats to numeric values.
    """
    if isinstance(value, dict):
        return {str(k): normalize_boundary(v) for k, v in value.items()}
    if type(value) in (tuple, list):
        return [normalize_boundary(v) for v in value]
    if type(value).__module__.startswith("numpy") and hasattr(value, "item"):
        return normalize_boundary(value.item())
    return value


@dataclass(frozen=True, kw_only=True)
class MarketFrame(v1.MarketFrame):
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        super().__post_init__()
        _check_version(self.contract_version)
        object.__setattr__(self, "features", _freeze_json(self.features))

    def as_payload(self) -> dict:
        return _thaw_json(self)

    def __hash__(self) -> int:
        # Hash uses ALL fields, including nested features; stable across processes.
        payload = json.dumps(self.as_payload(), ensure_ascii=False,
                             sort_keys=True, separators=(",", ":"), allow_nan=False)
        return int.from_bytes(sha256(payload.encode("utf-8")).digest()[:8], "big")


@dataclass(frozen=True, kw_only=True)
class Candidate(v1.Candidate):
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        super().__post_init__()
        _check_version(self.contract_version)


@dataclass(frozen=True, kw_only=True)
class PortfolioSnapshot(v1.PortfolioSnapshot):
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        super().__post_init__()
        _check_version(self.contract_version)


@dataclass(frozen=True, kw_only=True)
class DirectorAdvice(v1.DirectorAdvice):
    contract_version: str = CONTRACT_VERSION
    open_conviction_0_100: Optional[int] = None
    close_fraction: Optional[float] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        _check_version(self.contract_version)
        # An AI does not decide a margin amount. An arbiter, when designed and
        # approved, maps validated evidence + limits to a legal size.
        if self.action == "OPEN":
            if self.position_key is not None:
                raise ValueError("OPEN cannot name an existing position_key")
            if type(self.open_conviction_0_100) is not int or not (0 <= self.open_conviction_0_100 <= 100):
                raise ValueError("OPEN requires open_conviction_0_100 within 0..100")
        elif self.open_conviction_0_100 is not None:
            raise ValueError("open_conviction_0_100 is only valid on OPEN")

        if self.action == "PARTIAL_CLOSE":
            if (type(self.close_fraction) not in (float, int)
                    or not isfinite(self.close_fraction)
                    or not 0.0 < self.close_fraction < 1.0):
                raise ValueError("PARTIAL_CLOSE requires close_fraction strictly between 0 and 1")
        elif self.close_fraction is not None:
            raise ValueError("close_fraction is only valid on PARTIAL_CLOSE")

        if self.action != "OPEN" and self.selected_candidate_id is not None:
            raise ValueError("selected_candidate_id is only valid on OPEN")
        if self.action == "NO_TRADE" and self.position_key is not None:
            raise ValueError("NO_TRADE cannot refer to position_key")
        if self.action == "OPEN" and self.no_trade_reason is not None:
            raise ValueError("OPEN cannot carry no_trade_reason")
        if self.action != "NO_TRADE" and self.no_trade_reason is not None:
            raise ValueError("no_trade_reason is only valid on NO_TRADE")
        if self.action not in ("HOLD", "REASSESS") and self.hold_conviction_0_100 is not None:
            raise ValueError("hold_conviction_0_100 is only for HOLD/REASSESS")
        if self.action not in ("HOLD", "REASSESS") and self.review_after_bars is not None:
            raise ValueError("review_after_bars is only for HOLD/REASSESS")

__all__ = ["CONTRACT_VERSION", "MarketFrame", "Candidate", "DirectorAdvice",
           "PortfolioSnapshot", "normalize_boundary"]
