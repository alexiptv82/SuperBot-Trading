"""Allowlisted, read-only PAPER *position observations* from Falco and Toro.

A classic position is NOT a recommendation to copy it. Missing, stale, LIVE,
malformed, mixed-portfolio or contradictory snapshots => NO_DATA (None).
No trading flags, no account mutation, no Claude calls, no live exchange requests.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

SYMBOL = re.compile(r"^[A-Z0-9]{2,20}USDT$")
MAX_AGE_MS = 60_000
MAX_FUTURE_MS = 2_000
SOURCE = "classic_paper_positions"
LABELS = {"falco": "hawk", "toro": "bull"}
OBSERVATIONS = {"LONG_POSITION", "SHORT_POSITION", "FLAT"}


def _read(path: Path, limit: int) -> dict | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            return None
        raw = path.read_bytes()
        if len(raw) > limit:
            return None
        data = json.loads(raw.decode("utf-8"))
        return data if type(data) is dict else None
    except (OSError, ValueError, UnicodeError):
        return None


def validate_peer_signal(value: object, portfolio: str, symbol: str, now_ms: int) -> dict | None:
    """Re-sanitize the transport boundary; never pass legacy free text to the model."""
    if (type(value) is not dict or portfolio not in LABELS or type(symbol) is not str
            or SYMBOL.fullmatch(symbol) is None or type(now_ms) is not int or now_ms <= 0):
        return None
    if (value.get("portfolio") != portfolio or value.get("symbol") != symbol
            or value.get("source") != SOURCE or value.get("observation") not in OBSERVATIONS
            or type(value.get("asof_ms")) is not int
            or type(value.get("open_positions")) is not int):
        return None
    timestamp, count = value["asof_ms"], value["open_positions"]
    if (timestamp <= 0 or not -MAX_FUTURE_MS <= now_ms-timestamp <= MAX_AGE_MS
            or not 0 <= count <= 100):
        return None
    # Strict keys: reject instruction injection and unknown future schema.
    if set(value) != {"portfolio","symbol","source","observation","asof_ms","open_positions"}:
        return None
    return dict(value)


def read_peer(data_dir: Path, portfolio: str, symbol: str, now_ms: int) -> dict | None:
    if (portfolio not in LABELS or type(symbol) is not str or SYMBOL.fullmatch(symbol) is None
            or type(now_ms) is not int or now_ms <= 0):
        return None
    base = Path(data_dir)
    if base.is_symlink() or not base.is_dir():
        return None
    hb = _read(base / "heartbeat.json", 128_000)
    state = _read(base / "state_v2.json", 8_000_000)
    if hb is None or state is None:
        return None
    if hb.get("portfolio") != LABELS[portfolio] or hb.get("exec_mode") != "paper":
        return None
    ts = hb.get("ts")
    if type(ts) not in (int, float) or not math.isfinite(ts):
        return None
    ts_ms = int(ts * 1000)
    if not -MAX_FUTURE_MS <= now_ms - ts_ms <= MAX_AGE_MS:
        return None
    main = state.get("main")
    positions = main.get("positions") if type(main) is dict else None
    if type(positions) is not dict or len(positions) > 100:
        return None
    advertised = hb.get("open_positions")
    if type(advertised) is int and advertised != len(positions):
        return None
    candidates = []
    for key, pos in positions.items():
        if type(key) is not str or type(pos) is not dict:
            return None
        raw_symbol = pos.get("symbol") or key
        if type(raw_symbol) is not str:
            return None
        normalized = raw_symbol.upper()
        normalized = normalized if normalized.endswith("USDT") else normalized + "USDT"
        if normalized != symbol:
            continue
        if type(pos.get("side")) is not int or pos["side"] not in (-1,1):
            return None
        candidates.append(pos["side"])
    if len(candidates) > 1:
        return None  # competing positions on same symbol are ambiguous
    observed = ("FLAT" if not candidates else
                "LONG_POSITION" if candidates[0] == 1 else "SHORT_POSITION")
    item = {"portfolio": portfolio, "symbol": symbol, "source": SOURCE,
            "observation": observed, "asof_ms": ts_ms, "open_positions": len(positions)}
    return validate_peer_signal(item, portfolio, symbol, now_ms)


def read_peers(falco_dir: Path, toro_dir: Path, symbol: str, now_ms: int) -> dict:
    """Each peer is independent. A failure on one does not promote the other."""
    out = {}
    for name, path in (("falco", falco_dir), ("toro", toro_dir)):
        result = read_peer(path, name, symbol, now_ms)
        if result is not None:
            out[name] = result
    return out
