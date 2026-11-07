"""Isolated PAPER exit-sidecar prototype (NOT wired into live runner).

One owner of manual closes and stop monitor, independent of the DeepSeek
analysis process. The owner holds a POSIX flock for the *entire* session.
Its heartbeat is a health prerequisite for any future new-open guard.

This module provides no auto-start, no network clients, no live trading, no
side effect on import, and NO means to disable the original runner's exits.
A deployment must first switch both responsibilities atomically in a separately
reviewed wiring change, or the two workers could contend for close requests.

Main guard is intentionally fail-closed: missing/stale/malformed heartbeat,
wrong run, heartbeat errors or unlocked lease mean NOT healthy. The lock and
heartbeat are checked from the same directory as the run's journal.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import secrets
import stat
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from backend.v3.runner.manual_close import ManualCloseReport
from backend.v3.runner.monitor import MonitorReport
from backend.v3.runner.paper_close_fence import PaperCloseFenceBusy, paper_close_fence

LOCK_FILE = ".exit_service.lock"
BEAT_FILE = "exit_heartbeat.json"
SCHEMA_VERSION = 1
MINUTE_MS = 60_000
MAX_BEAT_AGE_MS = 15_000
MAX_MONITOR_AGE_MS = 65_000
_RUN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
_LEASE_RE = re.compile(r"[0-9a-f]{32}\Z")


class ExitServiceBusy(RuntimeError):
    """Another owner holds the exit service lease."""


@dataclass(frozen=True)
class ExitTick:
    state: str  # healthy | degraded
    manual: Optional[ManualCloseReport]
    monitor: Optional[MonitorReport]
    last_error: Optional[str]
    last_monitor_ms: Optional[int]


def _validate_directory(data_dir: Path) -> None:
    if not isinstance(data_dir, Path) or not data_dir.is_dir():
        raise ValueError("invalid_data_dir")


def _active_lease_token(path: Path) -> str | None:
    """Return current owner's token only when a distinct fd owns its flock.

    A token distinguishes a restarted service from a previous healthy owner.
    """
    fd = None
    try:
        flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size != 32:
            return None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.lseek(fd, 0, os.SEEK_SET)
            raw = os.read(fd, 33)
            token = raw.decode("ascii", "strict")
            return token if _LEASE_RE.fullmatch(token) else None
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return None
    except (OSError, UnicodeError):
        return None
    finally:
        if fd is not None:
            os.close(fd)


def exit_service_healthy(*, data_dir: Path, run_id: str, now_ms: int,
                         max_beat_age_ms: int = MAX_BEAT_AGE_MS,
                         max_monitor_age_ms: int = MAX_MONITOR_AGE_MS) -> bool:
    """Pure, no-write fail-closed gate; intended before EACH PAPER OPEN.

    A lease alone is not sufficient: the monitor must have succeeded recently.
    A heartbeat alone is not sufficient: a crashed worker releases its lease.
    """
    if (not isinstance(data_dir, Path) or not data_dir.is_dir()
            or type(run_id) is not str or _RUN_RE.fullmatch(run_id) is None
            or type(now_ms) is not int or now_ms <= 0
            or type(max_beat_age_ms) is not int or not 1 <= max_beat_age_ms <= 60_000
            or type(max_monitor_age_ms) is not int or not 1 <= max_monitor_age_ms <= 120_000):
        return False
    token = _active_lease_token(data_dir / LOCK_FILE)
    if token is None:
        return False
    try:
        beat_path = data_dir / BEAT_FILE
        # Do not follow a symlink or accept a huge/untrusted local JSON file.
        fd = os.open(beat_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            if os.fstat(fd).st_size > 2048:
                return False
            with os.fdopen(fd, "r", encoding="utf-8") as f:
                fd = -1
                beat = json.load(f)
        finally:
            if fd != -1:
                os.close(fd)
    except (OSError, ValueError, UnicodeError, TypeError):
        return False
    if type(beat) is not dict or set(beat) != {
        "schema_version", "run_id", "lease_token", "ts_ms", "state", "last_monitor_ms", "last_commands_ms", "last_error"
    }:
        return False
    if (type(beat["schema_version"]) is not int or beat["schema_version"] != SCHEMA_VERSION
            or beat["run_id"] != run_id or beat["lease_token"] != token
            or beat["state"] != "healthy" or beat["last_error"] is not None):
        return False
    now_fields = (beat["ts_ms"], beat["last_monitor_ms"], beat["last_commands_ms"])
    if any(type(v) is not int or v <= 0 or v > now_ms for v in now_fields):
        return False
    ts, mon, cmd = now_fields
    return (now_ms - ts <= max_beat_age_ms
            and now_ms - mon <= max_monitor_age_ms
            and now_ms - cmd <= max_beat_age_ms
            and mon <= ts and cmd <= ts
            and _active_lease_token(data_dir / LOCK_FILE) == token)


class ExitService:
    """One PAPER exit owner. Instantiate and start explicitly in a separate process.

    The two callbacks must use run_manual_close and run_exit_monitor from the
    *same* portfolio_id='brain' and run_id; wiring is intentionally deferred.
    """

    def __init__(self, *, run_id: str, data_dir: Path,
                 run_commands: Callable[[int], Optional[ManualCloseReport]],
                 run_monitor: Callable[[int], MonitorReport]):
        if type(run_id) is not str or _RUN_RE.fullmatch(run_id) is None:
            raise ValueError("invalid_run_id")
        _validate_directory(data_dir)
        if not callable(run_commands) or not callable(run_monitor):
            raise ValueError("invalid_callbacks")
        self.run_id = run_id
        self.data_dir = data_dir
        self._commands = run_commands
        self._monitor = run_monitor
        self._fd: Optional[int] = None
        self._lease_token: Optional[str] = None
        self._tick_lock = threading.Lock()
        self._last_minute = -1
        self._last_monitor_ms: Optional[int] = None
        self._last_tick_ms: Optional[int] = None

    def start(self) -> "ExitService":
        if self._fd is not None:
            raise ExitServiceBusy("exit_service_already_running")
        flags = (os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
        try:
            fd = os.open(self.data_dir / LOCK_FILE, flags, 0o600)
        except OSError:
            raise ExitServiceBusy("exit_service_lease_unavailable") from None
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                raise ExitServiceBusy("exit_service_lease_unavailable")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ExitServiceBusy("exit_service_already_running") from None
            # New owner gets a new fencing identity. An old healthy heartbeat
            # cannot authorize opens until THIS instance has finished a tick.
            self._lease_token = secrets.token_hex(16)
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, self._lease_token.encode("ascii"))
            os.fsync(fd)
        except BaseException:
            self._lease_token = None
            os.close(fd)
            raise
        self._fd = fd
        self._last_tick_ms = None
        self._last_monitor_ms = None
        self._last_minute = -1
        return self

    def stop(self) -> None:
        # Never relinquish ownership while a tick is still processing a CLOSE.
        with self._tick_lock:
            if self._fd is None:
                return
            fd, self._fd = self._fd, None
            self._lease_token = None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        # Keep the old heartbeat as a forensic record; guard tests lease too.

    def __enter__(self) -> "ExitService":
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    def _write_heartbeat(self, body: dict) -> None:
        temp = None
        try:
            fd, temp = tempfile.mkstemp(dir=self.data_dir, prefix=".exit_heartbeat.", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                fp.write(json.dumps(body, sort_keys=True, allow_nan=False))
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(temp, self.data_dir / BEAT_FILE)
            temp = None
        except OSError:
            # Continue processing stops; openings remain blocked by stale/no heartbeat.
            pass
        finally:
            if temp is not None:
                try:
                    os.unlink(temp)
                except OSError:
                    pass

    def tick(self, now_ms: int) -> ExitTick:
        if not self._tick_lock.acquire(blocking=False):
            raise ExitServiceBusy("exit_service_tick_in_progress")
        try:
            if self._fd is None:
                raise ExitServiceBusy("exit_service_not_started")
            if (type(now_ms) is not int or now_ms <= 0
                    or (self._last_tick_ms is not None and now_ms < self._last_tick_ms)):
                raise ValueError("invalid_now")
            return self._tick_locked(now_ms)
        finally:
            self._tick_lock.release()

    def _tick_locked(self, now_ms: int) -> ExitTick:
        # Every ExitService, even when created programmatically, must share
        # OPEN's journal writer fence. The sidecar can never be healthy while
        # its CLOSE callbacks are unprotected by the coordinating lock.
        try:
            with paper_close_fence(self.data_dir):
                return self._tick_fenced(now_ms)
        except PaperCloseFenceBusy:
            self._last_tick_ms = now_ms
            self._last_monitor_ms = None
            self._write_heartbeat({
                "schema_version": SCHEMA_VERSION, "run_id": self.run_id,
                "lease_token": self._lease_token, "ts_ms": now_ms,
                "state": "degraded", "last_monitor_ms": None,
                "last_commands_ms": None, "last_error": "writer_fence_unavailable",
            })
            return ExitTick("degraded", None, None, "writer_fence_unavailable", None)

    def _tick_fenced(self, now_ms: int) -> ExitTick:
        self._last_tick_ms = now_ms
        errors = []
        manual: Optional[ManualCloseReport] = None
        monitor: Optional[MonitorReport] = None
        try:
            manual = self._commands(now_ms)
            if manual is not None and manual.failed:
                errors.append("commands_reported_failures")
        except Exception:
            errors.append("commands_failed")
        minute = now_ms // MINUTE_MS
        if minute > self._last_minute:
            self._last_minute = minute  # no 5s repeated network flood after one failure
            try:
                monitor = self._monitor(now_ms)
                if type(monitor) is not MonitorReport:
                    errors.append("monitor_invalid_report")
                    self._last_monitor_ms = None
                elif monitor.errors:
                    errors.append("monitor_reported_errors")
                    self._last_monitor_ms = None
                else:
                    self._last_monitor_ms = now_ms
            except Exception:
                errors.append("monitor_failed")
                self._last_monitor_ms = None
        monitor_fresh = (self._last_monitor_ms is not None and
                         0 <= now_ms - self._last_monitor_ms <= MAX_MONITOR_AGE_MS)
        state = "healthy" if not errors and monitor_fresh else "degraded"
        last_error = errors[0] if errors else (None if monitor_fresh else "monitor_stale")
        self._write_heartbeat({
            "schema_version": SCHEMA_VERSION, "run_id": self.run_id,
            "lease_token": self._lease_token, "ts_ms": now_ms,
            "state": state, "last_monitor_ms": self._last_monitor_ms,
            "last_commands_ms": now_ms if "commands_failed" not in errors else None,
            "last_error": last_error,
        })
        return ExitTick(state, manual, monitor, last_error, self._last_monitor_ms)

    def run(self, *, now_fn: Callable[[], int], sleep_fn: Callable[[float], None],
            should_stop: Callable[[], bool], poll_s: float = 5.0) -> None:
        """Blocking loop; must run in a separate process to survive a model hang."""
        if type(poll_s) not in (float, int) or isinstance(poll_s, bool) or not 0.1 <= poll_s <= 60.0:
            raise ValueError("invalid_poll")
        with self:
            while not should_stop():
                self.tick(now_fn())
                sleep_fn(poll_s)
