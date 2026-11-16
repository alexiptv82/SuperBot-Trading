#!/usr/bin/env python3
"""One-shot PUBLIC closed-candle catch-up for the isolated Arena research cache.

--selftest: synthetic 25-market recovery and backup/commit, no network.
--preflight EXPECTED_SHA: no network, writes or locks.
--apply EXPECTED_SHA --confirm-public-get=YES: public Bitget V2 GETs ONLY,
  complete fail-closed replay, independent private backup, atomic replacement.
NO automation, production runner, credentials, paid AI APIs, orders or deploy.
"""
from __future__ import annotations

from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory
import fcntl
import json
import os
import re
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.v3.arena.frozen_market import FRAME_MS, freeze_market_batch
from backend.v3.arena.incremental_cache import (
    load_research_cache, save_research_cache,
)
from backend.v3.arena.recovery_gap import (
    MAX_PUBLIC_GETS, recover_gap, recovery_plan,
)

CACHE_DIR = Path("/var/lib/superbot-arena-research")
CACHE = CACHE_DIR / "arena-market-research-cache.json"
LOCK = ".arena-bootstrap.lock"
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
FETCH_MAX_SECONDS = 10 * 60
MAX_RECORD_BYTES = 24 * 1024 * 1024
MAX_BACKUP_COUNT = 12
EXPECTED_MARKETS = 25


def _isolate_directory(directory: Path):
    if (directory != CACHE_DIR and not (
        directory.parent == Path("/tmp")
        and directory.name.startswith("superbot-arena-research-")
        and len(directory.name) <= 90
    )):
        raise ValueError("APPLY_UNAUTHORIZED_RESEARCH_PATH")
    if (not directory.is_dir() or directory.is_symlink()
            or directory.resolve(strict=True) != directory):
        raise ValueError("APPLY_RESEARCH_DIRECTORY_INVALID")
    if directory.stat().st_mode & 0o077:
        raise ValueError("APPLY_RESEARCH_DIRECTORY_NOT_PRIVATE")
    return directory


def _audit_snapshot(path: Path, expected_sha: str):
    if type(expected_sha) is not str or not DIGEST.fullmatch(expected_sha):
        raise ValueError("APPLY_EXPECTED_SHA_REQUIRED")
    if path.is_symlink():
        raise ValueError("APPLY_CACHE_SYMLINK")
    source = load_research_cache(path)
    if source.sha256_hex != expected_sha:
        raise ValueError("APPLY_CACHE_SHA_CHANGED")
    if (len(source.symbols) != EXPECTED_MARKETS
            or not {"XAUUSDT", "XAGUSDT"}.issubset(source.symbols)
            or source.classification != "PROVISIONAL_NOT_TRADE_APPROVED"):
        raise ValueError("APPLY_CACHE_SCOPE_INVALID")
    return source


@contextmanager
def _exclusive_lock(directory: Path):
    lock = directory / LOCK
    if lock.is_symlink():
        raise ValueError("APPLY_LOCK_SYMLINK")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("APPLY_LOCK_NOT_REGULAR")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def _backup_file_bytes(path: Path, old_sha: str):
    """An independent 0600 copy; never delete or overwrite an older backup."""
    directory = _isolate_directory(path.parent)
    existing = list(directory.glob(".arena-backup-*.json"))
    if len(existing) >= MAX_BACKUP_COUNT:
        raise ValueError("APPLY_BACKUP_RETENTION_LIMIT_REVIEW")
    backup = directory / (".arena-backup-" + old_sha + ".json")
    if backup.exists() or backup.is_symlink():
        raise ValueError("APPLY_BACKUP_NAME_ALREADY_EXISTS")
    body = path.read_bytes()
    if len(body) > MAX_RECORD_BYTES:
        raise ValueError("APPLY_CACHE_FILE_OVERSIZED")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(backup, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        if backup.read_bytes() != body:
            raise ValueError("APPLY_BACKUP_VERIFY_FAILED")
        return backup
    except BaseException:
        backup.unlink(missing_ok=True)
        raise


def _commit(previous, updated, cache_path: Path, expected_sha: str):
    # Lock must already be held. Re-read the file just before writing.
    current = _audit_snapshot(cache_path, expected_sha)
    if (current.sha256_hex != previous.sha256_hex
            or current.canonical_bytes != previous.canonical_bytes):
        raise ValueError("APPLY_SOURCE_CHANGED_DURING_FETCH")
    if (updated.classification != previous.classification
            or updated.symbols != previous.symbols
            or updated.asof_ms <= previous.asof_ms):
        raise ValueError("APPLY_RESULT_SCOPE_INVALID")
    updated.verify()
    # Historical cache is retained before the atomic os.replace from saver.
    backup = _backup_file_bytes(cache_path, previous.sha256_hex)
    save_research_cache(updated, cache_path)
    replay = load_research_cache(cache_path)
    if (replay.sha256_hex != updated.sha256_hex
            or replay.canonical_bytes != updated.canonical_bytes
            or replay.asof_ms != updated.asof_ms):
        raise ValueError("APPLY_ATOMIC_READBACK_FAILED_CHECK_BACKUP")
    return backup, replay


def _history_getter():
    module = Path(__file__).with_name("arena-historical-warmup-20261116.py")
    spec = spec_from_file_location("arena_public_history_apply_v1", module)
    if spec is None or spec.loader is None:
        raise ValueError("APPLY_PUBLIC_HISTORY_UNAVAILABLE")
    instance = module_from_spec(spec)
    spec.loader.exec_module(instance)
    return instance._public_get


def _test_snapshot():
    asof = (1795000000000 // FRAME_MS["4h"]) * FRAME_MS["4h"] - 300_000
    required = {"1m": 60, "15m": 300, "1h": 100, "4h": 50}
    symbols = ("BTCUSDT",) + tuple("A" + str(i) + "USDT" for i in range(1, 23)) + (
        "XAUUSDT", "XAGUSDT",
    )
    data = {}
    for symbol in symbols:
        data[symbol] = {}
        for frame, step in FRAME_MS.items():
            last = asof // step * step - step
            data[symbol][frame] = [
                [str(last - (required[frame] - 1 - i) * step),
                 "100", "102", "98", "101", "10", "1000"]
                for i in range(required[frame])
            ]
    snapshot = freeze_market_batch(
        data, required, asof_ms=asof,
        source_id="bitget.v2.synthetic-recovery-apply",
    )
    return snapshot


def selftest():
    initial = _test_snapshot()
    target = initial.asof_ms + 90 * 60_000
    count = 0
    def fake_public_get(symbol, frame, first, last):
        nonlocal count
        count += 1
        step = FRAME_MS[frame]
        return [
            [str(i), "100", "102", "98", "101", "10", "1000"]
            for i in range(last + step, first - step - 1, -step)
        ]
    changed, plan = recover_gap(initial, target, fake_public_get)
    assert count == len(plan.pages)
    assert count <= MAX_PUBLIC_GETS
    assert len(plan.rebased) == 25
    with TemporaryDirectory(prefix="superbot-arena-research-", dir="/tmp") as name:
        folder = Path(name)
        os.chmod(folder, 0o700)
        path = folder / CACHE.name
        save_research_cache(initial, path)
        with _exclusive_lock(folder):
            backup, replay = _commit(initial, changed, path, initial.sha256_hex)
            assert replay.sha256_hex == changed.sha256_hex
            assert backup.is_file()
            assert stat.S_IMODE(backup.stat().st_mode) == 0o600
            # The backup contains an old cache independently loadable by
            # expected base filename in a second isolated temp folder.
            saved = backup.read_bytes()
            assert saved != path.read_bytes()
            try:
                _commit(initial, changed, path, initial.sha256_hex)
            except ValueError as exc:
                assert str(exc) == "APPLY_CACHE_SHA_CHANGED"
            else:
                raise AssertionError("STALE_SHA_WAS_ACCEPTED")
            assert backup.read_bytes() == saved
    print("ARENA_APPLY SELFTEST=PASS_OFFLINE")
    print("ARENA_APPLY synthetic_markets=25 simulated_public_GETs=" + str(count))
    print("ARENA_APPLY backup_atomic_replace_readback_verified=YES")
    print("ARENA_APPLY actual_public_GETs=0 paid_AI_calls=0 orders=0")
    return 0


def preflight(expected_sha: str):
    _isolate_directory(CACHE_DIR)
    source = _audit_snapshot(CACHE, expected_sha)
    plan = recovery_plan(source, int(time.time() * 1000))
    print("ARENA_APPLY mode=READ_ONLY_PREFLIGHT")
    print("ARENA_APPLY source_SHA256=" + source.sha256_hex)
    print("ARENA_APPLY markets=" + str(len(source.symbols)))
    print("ARENA_APPLY planned_public_GETs=" + str(len(plan.pages)))
    print("ARENA_APPLY rebase_frames=" + str(len(plan.rebased)))
    print("ARENA_APPLY max_public_GETs=" + str(MAX_PUBLIC_GETS))
    print("ARENA_APPLY paid_AI_calls=0 public_GETs=0 orders=0 files_written=0")
    print("ARENA_APPLY RESULT=PREFLIGHT_NO_CHANGES")
    return 0


def apply(expected_sha: str):
    _isolate_directory(CACHE_DIR)
    with _exclusive_lock(CACHE_DIR):
        old = _audit_snapshot(CACHE, expected_sha)
        target = int(time.time() * 1000)
        plan = recovery_plan(old, target)
        if not plan.pages:
            raise ValueError("APPLY_NO_NEW_CLOSED_CANDLES")
        # Avoid lengthy public traffic when backup capacity is exhausted.
        if len(list(CACHE_DIR.glob(".arena-backup-*.json"))) >= MAX_BACKUP_COUNT:
            raise ValueError("APPLY_BACKUP_RETENTION_LIMIT_REVIEW")
        print("ARENA_APPLY mode=ONE_SHOT_PUBLIC_RESEARCH_UPDATE", flush=True)
        print("ARENA_APPLY source_SHA256=" + old.sha256_hex, flush=True)
        print("ARENA_APPLY planned_public_GETs=" + str(len(plan.pages)), flush=True)
        print("ARENA_APPLY rebase_frames=" + str(len(plan.rebased)), flush=True)
        public_get = _history_getter()
        used = 0
        started = time.monotonic()
        def bounded_get(symbol, frame, first, last):
            nonlocal used
            if used >= MAX_PUBLIC_GETS:
                raise ValueError("APPLY_GET_LIMIT")
            if time.monotonic() - started > FETCH_MAX_SECONDS:
                raise ValueError("APPLY_FETCH_TIMEOUT")
            used += 1
            time.sleep(0.18)
            return public_get(symbol, frame, first, last)
        updated, result_plan = recover_gap(old, target, bounded_get)
        if result_plan != plan or used != len(plan.pages):
            raise ValueError("APPLY_PLAN_CHANGED")
        if time.monotonic() - started > FETCH_MAX_SECONDS:
            raise ValueError("APPLY_FETCH_TIMEOUT")
        if int(time.time() * 1000) - target > FETCH_MAX_SECONDS * 1000:
            raise ValueError("APPLY_RESULT_EXPIRED_DURING_FETCH")
        backup, replay = _commit(old, updated, CACHE, expected_sha)
        print("ARENA_APPLY public_GETs=" + str(used))
        print("ARENA_APPLY backup_file=" + str(backup))
        print("ARENA_APPLY source_SHA256=" + old.sha256_hex)
        print("ARENA_APPLY updated_SHA256=" + replay.sha256_hex)
        print("ARENA_APPLY updated_asof_ms=" + str(replay.asof_ms))
        print("ARENA_APPLY rebase_frames=" + str(len(plan.rebased)))
        print("ARENA_APPLY classification=PROVISIONAL_NOT_TRADE_APPROVED")
        print("ARENA_APPLY paid_AI_calls=0 orders=0 services_changed=0")
        print("ARENA_APPLY RESULT=PRIVATE_CACHE_UPDATED_WITH_BACKUP_NO_DEPLOY")
    return 0


def main():
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    if len(sys.argv) == 3 and sys.argv[1] == "--preflight":
        try:
            return preflight(sys.argv[2])
        except (ValueError, OSError, TypeError) as exc:
            print("ARENA_APPLY RESULT=NOT_READY_" + _public_reason(exc))
            return 2
    if len(sys.argv) == 4 and sys.argv[1] == "--apply" and sys.argv[3] == "--confirm-public-get=YES":
        try:
            return apply(sys.argv[2])
        except (ValueError, OSError, TypeError, BlockingIOError) as exc:
            print("ARENA_APPLY RESULT=NOT_UPDATED_" + _public_reason(exc))
            return 2
    print("ARENA_APPLY RESULT=REQUIRES_SELFTEST_PREFLIGHT_OR_EXPLICIT_APPLY")
    return 2


def _public_reason(exc):
    reason = str(exc)
    return reason if re.fullmatch(r"[A-Z0-9_]+", reason) else "PUBLIC_DATA_OR_STORAGE_FAILURE"


if __name__ == "__main__":
    sys.exit(main())
