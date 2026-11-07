"""Isolated PAPER manual-exit worker for legacy Falco/Toro, NEVER a strategy runner.

The historic desk containers must remain stopped, with restart policies disabled.
This worker may ONLY consume the two authenticated-dashboard close-request flags.
It never processes pause/resume/reset, calls Claude, evaluates symbols, or opens trades.

This is a separate opt-in process. Merely importing this module has no side effects.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Callable, Optional

REQUIRED = ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md")
PENDING = ("reset.flag", "reset.flag.work", "close_position.flag", "close_position.flag.work")
HEARTBEAT = "exit_only_heartbeat.json"
LOCK = ".exit_only_writer.lock"
PRICE_MAX_AGE_MS = 120_000
POLL_SECONDS = 3.0


class ExitOnlyError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def docker_stopped_and_disabled(portfolio: str) -> bool:
    """Both conditions are required; a missing Docker daemon is NOT evidence of stopped trading."""
    if portfolio not in ("hawk", "bull"):
        return False
    name = "superbot-desk-" + portfolio
    try:
        p = subprocess.run(
            ["docker", "inspect", "-f",
             "{{.State.Running}}|{{.HostConfig.RestartPolicy.Name}}", name],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if p.returncode != 0:
        return False
    state, sep, restart = p.stdout.strip().partition("|")
    return bool(sep and state == "false" and restart in ("no", ""))


def _safe_required_files(base: Path) -> None:
    for name in REQUIRED:
        f = base / name
        if f.is_symlink() or not f.is_file() or (name == "state_v2.json" and f.stat().st_size == 0):
            raise ExitOnlyError("required_file_missing_or_invalid:" + name)
    try:
        data = json.loads((base / "state_v2.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ExitOnlyError("state_unreadable") from None
    if not isinstance(data, dict) or not isinstance(data.get("main"), dict):
        raise ExitOnlyError("state_structure_invalid")
    if not isinstance(data["main"].get("positions"), dict):
        raise ExitOnlyError("positions_structure_invalid")


def verify_snapshot(base: Path, backup: Path) -> None:
    """A fresh local backup of all indispensable files, byte-identical at start, is mandatory."""
    if backup.is_symlink() or not backup.is_dir() or backup.resolve() == base.resolve():
        raise ExitOnlyError("snapshot_directory_missing_or_invalid")
    if base.resolve() in backup.resolve().parents or backup.resolve() in base.resolve().parents:
        raise ExitOnlyError("snapshot_must_be_separate")
    for name in REQUIRED:
        original, copy = base / name, backup / name
        if copy.is_symlink() or not copy.is_file() or _sha256(original) != _sha256(copy):
            raise ExitOnlyError("snapshot_missing_or_mismatched:" + name)


def recent_minute_prices(symbols, state, now_ms: int, *, fetch_candles) -> dict:
    """No old candle cache; use public Bitget futures 1m candles no older than 120 seconds."""
    prices = {}
    for symbol in symbols:
        try:
            bars = fetch_candles(symbol, "1m", 3)
        except Exception:
            bars = []  # failed public feed => no PAPER close, never invented price
        if not isinstance(bars, (tuple, list)) or not bars:
            continue
        try:
            last = bars[-1]
            ts, px = float(last[0]), float(last[4])
            if (math.isfinite(ts) and math.isfinite(px) and
                    0 <= now_ms - ts <= PRICE_MAX_AGE_MS and px > 0):
                prices[symbol] = px
        except (TypeError, IndexError, ValueError, OverflowError):
            continue
    return prices


class ExitOnlyWorker:
    """One owner, proof of stopped legacy bots, explicit local snapshot before any PAPER write."""

    def __init__(self, *, base: Path, backup: Path, portfolio: str, legacy,
                 stopped: Callable[[str], bool] = docker_stopped_and_disabled,
                 clock: Callable[[], float] = time.time):
        self.base = Path(base)
        self.backup = Path(backup)
        self.portfolio = portfolio
        self.legacy = legacy
        self.stopped = stopped
        self.clock = clock
        self._fd: Optional[int] = None

    def check_safe(self, *, startup=False):
        if self.portfolio not in ("hawk", "bull"):
            raise ExitOnlyError("unsupported_portfolio")
        if self.base.is_symlink() or not self.base.is_dir():
            raise ExitOnlyError("data_directory_missing_or_symlink")
        if self.legacy.PORTFOLIO.name != self.portfolio:
            raise ExitOnlyError("portfolio_mismatch")
        if Path(self.legacy.DATA_DIR).resolve() != self.base.resolve():
            raise ExitOnlyError("data_directory_mismatch")
        if self.legacy.LIVE._live or os.environ.get("DESK_MODE") != "paper":
            raise ExitOnlyError("paper_mode_required")
        if not (self.base / "pause.flag").is_file():
            raise ExitOnlyError("pause_required")
        if not self.stopped(self.portfolio):
            raise ExitOnlyError("legacy_container_not_proven_stopped_and_disabled")
        _safe_required_files(self.base)
        if startup:
            verify_snapshot(self.base, self.backup)
            if any((self.base / f).exists() for f in PENDING):
                raise ExitOnlyError("existing_close_request_needs_manual_reconciliation")

    def _write_heartbeat(self, ready: bool) -> None:
        payload = {
            "mode": "paper-exit-only", "portfolio": self.portfolio, "ready": ready,
            "ts": self.clock(), "pid": os.getpid(),
        }
        fd, tmp = tempfile.mkstemp(dir=self.base, prefix=".exit-only-hb.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as w:
                json.dump(payload, w, separators=(",", ":"))
                w.flush()
                os.fsync(w.fileno())
            os.replace(tmp, self.base / HEARTBEAT)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def __enter__(self):
        # Verify before even creating the lock file; no auto-start or reset is ever performed.
        self.check_safe(startup=True)
        self._fd = os.open(self.base / LOCK, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self._fd)
            self._fd = None
            raise ExitOnlyError("another_exit_writer_active") from None
        try:
            self.check_safe(startup=True)
            self._write_heartbeat(True)
        except Exception:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._fd is not None:
                self._write_heartbeat(False)
        finally:
            if self._fd is not None:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
                self._fd = None

    def _price_provider(self, symbols, state, now_ms):
        prices = recent_minute_prices(symbols, state, now_ms, fetch_candles=self.legacy.fetch_candles)
        # Recheck BEFORE the existing accounting code is allowed to commit a close.
        self.check_safe()
        return prices

    def tick(self) -> dict:
        if self._fd is None:
            raise ExitOnlyError("worker_not_started")
        try:
            self.check_safe()
            # Do not call legacy.process_flags(), legacy.loop_step(), legacy.iteration(),
            # legacy.run_cycle(), or any strategy/AI function, even in PAPER.
            selected = (self.base / "close_position.flag").is_file()
            all_pending = (self.base / "reset.flag").is_file()
            if selected or all_pending:
                state = self.legacy.load_state(str(self.base / "state_v2.json"))
                if not isinstance(state, dict) or not isinstance((state.get("main") or {}).get("positions"), dict):
                    raise ExitOnlyError("state_became_invalid")
                if selected:
                    self.legacy._check_close_position_flag(state, price_provider=self._price_provider)
                if all_pending:
                    self.legacy._check_close_all_flag(state, price_provider=self._price_provider)
            # The legacy handlers deliberately catch their own errors. Verify
            # ownership AGAIN after them; never publish READY if Docker changed mid-request.
            self.check_safe()
            self._write_heartbeat(True)
            return {"manual_one_requested": selected, "manual_all_requested": all_pending}
        except Exception:
            # No further close commands can be accepted after failed preflight.
            self._write_heartbeat(False)
            raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--portfolio", choices=("hawk", "bull"), required=True)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--snapshot-dir", required=True)
    ap.add_argument("--start-paper-exit-only", action="store_true",
                    help="explicit operator opt-in: never starts regular trading")
    args = ap.parse_args(argv)
    # No import of the full legacy runner until the user explicitly opts in.
    if not args.start_paper_exit_only:
        print("REFUSED: --start-paper-exit-only is required; no worker started", flush=True)
        return 2
    if os.environ.get("DESK_MODE") != "paper" or os.environ.get("DESK_PORTFOLIO") != args.portfolio:
        print("REFUSED: DESK_MODE=paper and DESK_PORTFOLIO must match", flush=True)
        return 2
    if Path(os.environ.get("DESK_DATA_DIR", "")).resolve() != Path(args.data_dir).resolve():
        print("REFUSED: data directory must match the explicit environment", flush=True)
        return 2

    from desk import cli as legacy
    try:
        with ExitOnlyWorker(base=Path(args.data_dir), backup=Path(args.snapshot_dir),
                            portfolio=args.portfolio, legacy=legacy) as service:
            print("EXIT_ONLY_PAPER_READY=1; opens_and_claude_calls=DISABLED", flush=True)
            while True:
                service.tick()
                time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        return 0
    except (ExitOnlyError, OSError, ValueError) as exc:
        print("EXIT_ONLY_REFUSED: " + str(exc)[:150], flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
