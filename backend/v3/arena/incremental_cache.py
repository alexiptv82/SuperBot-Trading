"""Offline, fail-closed incremental cache for verified Arena frozen candles.

Pure plan/merge functions; isolated optional atomic disk persistence. Does not
fetch market data, call models, place orders, or touch production services.
The caller supplies strictly closed public candles for each missing interval.
"""
from __future__ import annotations

from base64 import b64decode, b64encode
from binascii import Error as Base64Error
from pathlib import Path
from collections.abc import Mapping
import json
import os
import stat
import tempfile

from backend.v3.arena.frozen_market import (
    FRAME_MS, FrozenMarketBatch, freeze_market_batch,
)

CACHE_FORMAT = "arena_research_cache_v1"
MAX_CACHE_BYTES = 24 * 1024 * 1024
MAX_ELAPSED_MS = 30 * 60 * 1000
MAX_DELTA_BARS_PER_FRAME = 60
RESEARCH_DISK_ROOT = Path("/var/lib/superbot-arena-research")


def delta_plan(previous: FrozenMarketBatch, target_asof_ms: int) -> dict:
    """Determine exact missing closed-candle ranges; no provider requests."""
    if type(previous) is not FrozenMarketBatch or type(target_asof_ms) is not int:
        raise ValueError("CACHE_INVALID_INPUT")
    previous.verify()
    elapsed = target_asof_ms - previous.asof_ms
    if elapsed <= 0:
        raise ValueError("CACHE_NONMONOTONIC_TIME")
    if elapsed > MAX_ELAPSED_MS:
        raise ValueError("CACHE_TOO_OLD_REBOOTSTRAP_REQUIRED")
    doc = json.loads(previous.canonical_bytes)
    if (doc.get("classification") != "PROVISIONAL_NOT_TRADE_APPROVED"
            or type(doc.get("required")) is not dict
            or set(doc["required"]) != set(FRAME_MS)
            or type(doc.get("candles")) is not dict
            or set(doc["candles"]) != set(previous.symbols)):
        raise ValueError("CACHE_SCOPE_CORRUPT")
    if (any(type(n) is not int or not 1 <= n <= 6000
            for n in doc["required"].values())
            or type(doc.get("source_id")) is not str):
        raise ValueError("CACHE_BAD_REQUIREMENTS")
    result = {}
    for symbol in previous.symbols:
        missing = {}
        for frame, step in FRAME_MS.items():
            prev_last = previous.asof_ms // step * step - step
            next_last = target_asof_ms // step * step - step
            if next_last > prev_last:
                first = prev_last + step
                quantity = (next_last - first) // step + 1
                if quantity > MAX_DELTA_BARS_PER_FRAME:
                    raise ValueError("CACHE_DELTA_TOO_LARGE")
                missing[frame] = (first, next_last)
        if missing:
            result[symbol] = missing
    return result


def merge_delta(previous: FrozenMarketBatch, target_asof_ms: int,
                received: Mapping[str, Mapping[str, list]]) -> FrozenMarketBatch:
    """Apply a complete delta atomically IN MEMORY; fail whole snapshot on gap.

    received[symbol][frame] must contain *exactly* the newly closed candles
    in the window reported by delta_plan, no forming, duplicate or extra rows.
    """
    need = delta_plan(previous, target_asof_ms)
    if not isinstance(received, Mapping) or set(received) != set(need):
        raise ValueError("CACHE_INCOMPLETE_DELTA_MARKETS")
    doc = json.loads(previous.canonical_bytes)
    required = doc["required"]
    output = {}
    for symbol in previous.symbols:
        by_frame = doc["candles"][symbol]
        if set(by_frame) != set(FRAME_MS):
            raise ValueError("CACHE_MISSING_FRAME")
        incoming = received.get(symbol, {})
        if not isinstance(incoming, Mapping) or set(incoming) != set(need.get(symbol, {})):
            raise ValueError("CACHE_INCOMPLETE_DELTA_FRAMES")
        output[symbol] = {}
        for frame in FRAME_MS:
            old = by_frame[frame]
            new = incoming.get(frame, [])
            if type(new) is not list:
                raise ValueError("CACHE_INVALID_DELTA_TYPE")
            if frame in need.get(symbol, {}):
                first, last = need[symbol][frame]
                step = FRAME_MS[frame]
                expected = list(range(first, last + step, step))
                timestamps = []
                for row in new:
                    if type(row) is not list or len(row) < 7 or type(row[0]) not in (int, str):
                        raise ValueError("CACHE_MALFORMED_DELTA")
                    try:
                        timestamps.append(int(row[0]))
                    except ValueError:
                        raise ValueError("CACHE_INVALID_DELTA_TIMESTAMP") from None
                if sorted(timestamps) != expected:
                    raise ValueError("CACHE_MISSING_EXTRA_OR_DUPLICATE_BARS")
            elif new:
                raise ValueError("CACHE_UNEXPECTED_NEW_BARS")
            # Previously verified bars need not be re-fetched; existing data
            # remain immutable in previous. freeze_market_batch revalidates ALL.
            output[symbol][frame] = (old + new)[-required[frame]:]
    result = freeze_market_batch(
        output, required, asof_ms=target_asof_ms,
        source_id=doc["source_id"],
    )
    if result.symbols != previous.symbols or result.classification != previous.classification:
        raise ValueError("CACHE_UNIVERSE_CHANGED_UNEXPECTEDLY")
    return result


def _isolated_path(filename: Path) -> Path:
    """Explicit scratch or dedicated research directory; reject bot paths."""
    path = Path(filename)
    if not path.is_absolute() or path.name != "arena-market-research-cache.json":
        raise ValueError("CACHE_PATH_NOT_ISOLATED")
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("CACHE_DIRECTORY_MUST_EXIST_AND_BE_REAL")
    # Refuse symlinks at every level of the supplied directory.
    if parent.resolve(strict=True) != parent:
        raise ValueError("CACHE_DIRECTORY_SYMLINK_CHAIN")
    if not (
        parent == RESEARCH_DISK_ROOT
        or (parent.parent == Path("/tmp")
            and parent.name.startswith("superbot-arena-research-")
            and len(parent.name) <= 90)
    ):
        raise ValueError("CACHE_PATH_OUTSIDE_RESEARCH_ROOT")
    if path.is_symlink():
        raise ValueError("CACHE_SYMLINK_REJECTED")
    return path


def save_research_cache(snapshot: FrozenMarketBatch, filename: Path) -> None:
    """Atomic replacement in caller-owned research path, NEVER a bot path."""
    if type(snapshot) is not FrozenMarketBatch:
        raise ValueError("CACHE_INVALID_INPUT")
    snapshot.verify()
    if len(snapshot.canonical_bytes) > MAX_CACHE_BYTES // 2:
        raise ValueError("CACHE_PAYLOAD_OVERSIZED")
    path = _isolated_path(filename)
    directory = path.parent
    envelope = {
        "schema": CACHE_FORMAT,
        "asof_ms": snapshot.asof_ms,
        "symbols": list(snapshot.symbols),
        "sha256_hex": snapshot.sha256_hex,
        "payload_b64": b64encode(snapshot.canonical_bytes).decode("ascii"),
    }
    encoded = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("ascii")
    if len(encoded) > MAX_CACHE_BYTES:
        raise ValueError("CACHE_FILE_OVERSIZED")
    fd, tmp = tempfile.mkstemp(prefix=".arena-snapshot-", dir=directory)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        # ensure directory entry survives an unexpected restart.
        dir_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_research_cache(filename: Path) -> FrozenMarketBatch:
    path = _isolated_path(filename)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CACHE_BYTES:
        raise ValueError("CACHE_NOT_REGULAR_OR_TOO_LARGE")
    try:
        content = json.loads(path.read_bytes())
        if (type(content) is not dict or content.get("schema") != CACHE_FORMAT
                or type(content.get("symbols")) is not list
                or type(content.get("asof_ms")) is not int
                or type(content.get("sha256_hex")) is not str
                or type(content.get("payload_b64")) is not str):
            raise ValueError("CACHE_METADATA_INVALID")
        raw = b64decode(content["payload_b64"], validate=True)
        snapshot = FrozenMarketBatch(
            asof_ms=content["asof_ms"],
            symbols=tuple(content["symbols"]),
            sha256_hex=content["sha256_hex"],
            canonical_bytes=raw,
        )
        snapshot.verify()
        return snapshot
    except (UnicodeDecodeError, json.JSONDecodeError, Base64Error, ValueError, TypeError) as exc:
        raise ValueError("CACHE_CORRUPT_OR_UNVERIFIED") from exc
