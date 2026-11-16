#!/usr/bin/env python3
"""AI Arena: create the FIRST persistent full-history research cache.

Public CoinGecko and Bitget GETs only. No paid AI calls, trading orders,
runner/UI/journal changes, Docker changes, or recurring services.

--selftest: offline cache round-trip with 25 synthetic symbols (no network).
--preflight: read-only checks of disk and target; no network or writes.
--bootstrap: explicit one-time fetch (<=578 public GETs) and atomic save.
A prior 25-market diagnostic was memory-only and CANNOT be reused from SHA.
The resulting cache is still PROVISIONAL_NOT_TRADE_APPROVED.
"""
from __future__ import annotations

from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import fcntl
import json
import os
import re
import stat
import sys
import time
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.v3.arena.frozen_market import FRAME_MS, freeze_market_batch
from backend.v3.arena.incremental_cache import (
    MAX_CACHE_BYTES, load_research_cache, save_research_cache,
)

STORE_ROOT = Path("/var/lib/superbot-arena-research")
STORE_PATH = STORE_ROOT / "arena-market-research-cache.json"
LOCK_FILENAME = ".arena-bootstrap.lock"
MAX_BOOTSTRAP_AGE_MS = 10 * 60_000
MIN_FREE_DISK = 64 * 1024 * 1024
MAX_PUBLIC_GET = 578
AI_LANES = ("deepseek", "qwen", "minimax")


def _full_module():
    path = Path(__file__).with_name("arena-dynamic25-fullhistory-20261116.py")
    spec = spec_from_file_location("arena_full_history_bootstrap", path)
    if spec is None or spec.loader is None or not path.is_file():
        raise ValueError("ARENA_FULL_HISTORY_MODULE_MISSING")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_directory(path: Path, *, allow_missing: bool = False):
    if path != STORE_ROOT and not (
        path.parent == Path("/tmp")
        and path.name.startswith("superbot-arena-research-")
        and len(path.name) <= 90
    ):
        raise ValueError("BOOTSTRAP_NON_RESEARCH_ROOT")
    if not path.exists():
        if allow_missing:
            return False
        raise ValueError("BOOTSTRAP_DIRECTORY_MISSING")
    if path.is_symlink() or path.resolve(strict=True) != path:
        raise ValueError("BOOTSTRAP_DIRECTORY_SYMLINK")
    mode = path.stat().st_mode
    if not stat.S_ISDIR(mode):
        raise ValueError("BOOTSTRAP_NOT_DIRECTORY")
    if mode & 0o077:
        raise ValueError("BOOTSTRAP_DIRECTORY_PERMISSIONS_NOT_PRIVATE")
    return True


def _existing_cache_status(path: Path):
    if path.is_symlink():
        raise ValueError("BOOTSTRAP_CACHE_SYMLINK")
    if path.exists():
        # Never overwrite first-cache data, even if corrupted: explicit audit.
        raise ValueError("BOOTSTRAP_CACHE_ALREADY_EXISTS")


def _free_space(path: Path):
    parent = path if path.is_dir() else path.parent
    statv = os.statvfs(parent)
    free = statv.f_bavail * statv.f_frsize
    if free < MIN_FREE_DISK:
        raise ValueError("BOOTSTRAP_INSUFFICIENT_DISK")
    return free


@contextmanager
def _exclusive_research_lock(directory: Path):
    lock = directory / LOCK_FILENAME
    if lock.is_symlink():
        raise ValueError("BOOTSTRAP_LOCK_SYMLINK")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(lock, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("BOOTSTRAP_LOCK_NOT_FILE")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def _save_verified_initial(snapshot, directory: Path):
    _check_directory(directory)
    path = directory / STORE_PATH.name
    _existing_cache_status(path)
    _free_space(directory)
    if len(snapshot.canonical_bytes) > MAX_CACHE_BYTES // 2:
        raise ValueError("BOOTSTRAP_TOO_LARGE_FOR_CACHE")
    if snapshot.classification != "PROVISIONAL_NOT_TRADE_APPROVED":
        raise ValueError("BOOTSTRAP_UNEXPECTED_TRADING_APPROVAL")
    snapshot.verify()
    save_research_cache(snapshot, path)
    loaded = load_research_cache(path)
    if (loaded.sha256_hex != snapshot.sha256_hex
            or loaded.canonical_bytes != snapshot.canonical_bytes
            or loaded.asof_ms != snapshot.asof_ms
            or loaded.symbols != snapshot.symbols):
        raise ValueError("BOOTSTRAP_READBACK_MISMATCH")
    return path, loaded


def _synthetic_snapshot():
    asof_ms = 1795000000000
    required = {"1m": 60, "15m": 24, "1h": 24, "4h": 24}
    symbols = ("BTCUSDT",) + tuple(f"T{i}USDT" for i in range(1, 23)) + (
        "XAUUSDT", "XAGUSDT",
    )
    assert len(symbols) == 25
    by_symbol = {}
    for symbol in symbols:
        by_symbol[symbol] = {}
        for frame, step in FRAME_MS.items():
            last = asof_ms // step * step - step
            by_symbol[symbol][frame] = [
                [str(last - (required[frame] - 1 - i) * step),
                 "100", "102", "98", "101", "5", "500"]
                for i in range(required[frame])
            ]
    return freeze_market_batch(by_symbol, required, asof_ms=asof_ms,
                               source_id="bitget.v2.synthetic-cache-bootstrap")


def selftest():
    with TemporaryDirectory(prefix="superbot-arena-research-", dir="/tmp") as tmp:
        directory = Path(tmp)
        os.chmod(directory, 0o700)
        original = _synthetic_snapshot()
        with _exclusive_research_lock(directory):
            path, loaded = _save_verified_initial(original, directory)
            assert loaded.sha256_hex == original.sha256_hex
            assert len(loaded.symbols) == 25
            assert path.stat().st_mode & 0o777 == 0o600
            for lane in AI_LANES:
                assert loaded.for_provider(lane) == original.for_provider(lane)
            try:
                _save_verified_initial(original, directory)
            except ValueError as exc:
                assert str(exc) == "BOOTSTRAP_CACHE_ALREADY_EXISTS"
            else:
                raise AssertionError("OVERWRITE_WAS_ALLOWED")
            # An unreadable or corrupted existing cache is never overwritten.
            path.write_text("corrupt")
            try:
                _save_verified_initial(original, directory)
            except ValueError as exc:
                assert str(exc) == "BOOTSTRAP_CACHE_ALREADY_EXISTS"
            else:
                raise AssertionError("CORRUPT_CACHE_WAS_OVERWRITTEN")
        assert path.read_text() == "corrupt"
    print("ARENA_BOOTSTRAP SELFTEST=PASS_OFFLINE")
    print("ARENA_BOOTSTRAP synthetic_markets=25 private_cache_roundtrip=YES")
    print("ARENA_BOOTSTRAP verify_non_overwrite_and_readback=YES")
    print("ARENA_BOOTSTRAP actual_public_GETs=0 paid_AI_calls=0 orders=0")
    return 0


def preflight():
    print("ARENA_BOOTSTRAP mode=READ_ONLY_PREFLIGHT", flush=True)
    if _check_directory(STORE_ROOT, allow_missing=True):
        _existing_cache_status(STORE_PATH)
        free = _free_space(STORE_ROOT)
        print("ARENA_BOOTSTRAP directory=READY_PRIVATE", flush=True)
    else:
        free = _free_space(Path("/var/lib"))
        print("ARENA_BOOTSTRAP directory=NOT_CREATED", flush=True)
    print("ARENA_BOOTSTRAP free_disk_MiB=" + str(free // (1024 * 1024)))
    print("ARENA_BOOTSTRAP max_public_GETs=578 (if explicitly bootstrapped)")
    print("ARENA_BOOTSTRAP paid_AI_calls=0 orders=0 services_changed=0")
    print("ARENA_BOOTSTRAP RESULT=PREFLIGHT_NO_WRITES_NO_NETWORK")
    return 0


def bootstrap():
    """Caller explicitly opts in to bounded public fetch and research disk write."""
    print("ARENA_BOOTSTRAP mode=EXPLICIT_PUBLIC_FIRST_CACHE")
    print("ARENA_BOOTSTRAP max_public_GETs=578 paid_AI_calls=0 orders=0")
    if not STORE_ROOT.exists():
        STORE_ROOT.mkdir(mode=0o700)
    _check_directory(STORE_ROOT)
    with _exclusive_research_lock(STORE_ROOT):
        _existing_cache_status(STORE_PATH)
        _free_space(STORE_ROOT)
        module = _full_module()
        symbols, _listing, asof = module.catalog_snapshot()
        if len(symbols) != 25:
            raise ValueError("BOOTSTRAP_INVALID_UNIVERSE")
        count = 0
        history = module.history_module()

        def public_get(symbol, frame, first, last):
            nonlocal count
            if count >= module.MAX_HISTORY_GETS:
                raise ValueError("BOOTSTRAP_PUBLIC_GET_CAP")
            count += 1
            time.sleep(0.2)
            return history._public_get(symbol, frame, first, last)

        frozen, counts, req = module.collect(
            symbols, asof, public_get,
            on_symbol=lambda symbol, used: print(
                "ARENA_BOOTSTRAP completed=" + symbol
                + " pages=" + str(used)
                + " total_history_GETs=" + str(count), flush=True),
        )
        age_ms = int(time.time() * 1000) - asof
        if age_ms < 0 or age_ms > MAX_BOOTSTRAP_AGE_MS:
            raise ValueError("BOOTSTRAP_EXPIRED_DURING_FETCH")
        if count != 575 or sum(counts.values()) != 575:
            raise ValueError("BOOTSTRAP_UNEXPECTED_PAGE_COUNT")
        if len(frozen.symbols) != 25 or frozen.asof_ms != asof:
            raise ValueError("BOOTSTRAP_UNEXPECTED_SNAPSHOT")
        path, loaded = _save_verified_initial(frozen, STORE_ROOT)
        print("ARENA_BOOTSTRAP requirements=" + str(req), flush=True)
        print("ARENA_BOOTSTRAP history_GETs=" + str(count), flush=True)
        print("ARENA_BOOTSTRAP snapshot_age_seconds=" + str(age_ms // 1000))
        print("ARENA_BOOTSTRAP cache_file=" + str(path))
        print("ARENA_BOOTSTRAP cache_SHA256=" + loaded.sha256_hex)
        for lane in AI_LANES:
            print("ARENA_BOOTSTRAP " + lane.upper()
                  + "_SHA256=" + loaded.for_provider(lane)[1])
        print("ARENA_BOOTSTRAP classification=PROVISIONAL_NOT_TRADE_APPROVED")
        print("ARENA_BOOTSTRAP paid_AI_calls=0 orders=0 services_changed=0")
        print("ARENA_BOOTSTRAP RESULT=FIRST_PRIVATE_CACHE_SAVED_NO_DEPLOY")
    return 0


def main():
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    if sys.argv[1:] == ["--preflight"]:
        return preflight()
    if sys.argv[1:] == ["--bootstrap", "--confirm-public-download=YES"]:
        try:
            return bootstrap()
        except (ValueError, OSError) as exc:
            reason = str(exc)
            if re.fullmatch("[A-Z0-9_]+", reason) is None:
                reason = "UNVERIFIED_OR_UNAVAILABLE"
            print("ARENA_BOOTSTRAP RESULT=NOT_SAVED_" + reason, flush=True)
            return 2
    print("ARENA_BOOTSTRAP RESULT=REQUIRES_SELFTEST_PREFLIGHT_OR_EXPLICIT_BOOTSTRAP")
    return 2


if __name__ == "__main__":
    sys.exit(main())
