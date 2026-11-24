"""Parametri del tabellone L4: parsing puro, caricamento esplicito I/O separato.

Solo default_params_path e load_default_params effettuano I/O; il motore deve
passare i parametri in modo esplicito, senza letture implicite.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path


@dataclass(frozen=True)
class ViewParams:
    min_trades: int
    min_days: int
    confidence: Decimal
    n_boot: int
    seed: int
    max_cells: int


def _unique_pairs(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("invalid_params") from None
        data[key] = value
    return data


def _reject_constant(_value):
    raise ValueError("invalid_params") from None


def _valid_confidence(value):
    return (
        type(value) is str and 3 <= len(value) <= 8
        and value.startswith("0.")
        and 1 <= len(value[2:]) <= 6
        and all("0" <= c <= "9" for c in value[2:])
        and any(c != "0" for c in value[2:])
    )


def load_view_params(raw: bytes) -> ViewParams:
    """Parse strict JSON: only bytes; exact keys and types; no duplicate keys."""
    if type(raw) is not bytes:
        raise ValueError("invalid_params") from None
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                          parse_constant=_reject_constant)
        if type(data) is not dict or set(data) != {
            "schema_version", "min_trades", "min_days", "confidence", "n_boot", "seed", "max_cells"
        }:
            raise ValueError("invalid_params")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError("invalid_params")
        if type(data["min_trades"]) is not int or data["min_trades"] < 1:
            raise ValueError("invalid_params")
        if type(data["min_days"]) is not int or data["min_days"] < 2:
            raise ValueError("invalid_params")
        if not _valid_confidence(data["confidence"]):
            raise ValueError("invalid_params")
        if type(data["n_boot"]) is not int or data["n_boot"] < 200:
            raise ValueError("invalid_params")
        if type(data["seed"]) is not int:
            raise ValueError("invalid_params")
        if type(data["max_cells"]) is not int or not 1 <= data["max_cells"] <= 50:
            raise ValueError("invalid_params")
        return ViewParams(
            min_trades=data["min_trades"], min_days=data["min_days"],
            confidence=Decimal(data["confidence"]), n_boot=data["n_boot"],
            seed=data["seed"], max_cells=data["max_cells"],
        )
    except Exception:
        raise ValueError("invalid_params") from None


def default_params_path() -> Path:
    """Locate the bundled JSON independently of the working directory."""
    return Path(__file__).with_name("view_params.json")


def load_default_params() -> ViewParams:
    """Explicit I/O helper, never called by the pure functions or analyst."""
    return load_view_params(default_params_path().read_bytes())
