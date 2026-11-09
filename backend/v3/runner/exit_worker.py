"""Isolated PAPER-only entrypoint proposal for the V3 exit-sidecar.

DO NOT deploy or enable while the legacy Brain worker still owns exits.
The default CLI never starts or changes anything; explicit --start-paper is
required. Startup checks the existing journal (read-only) and never calls
``EventJournal.init_schema`` or creates a new run. Network is public market
READ-ONLY when an explicitly started worker executes its callbacks.

The module has no side effects on import. Its systemd unit is a *template* in
this review package; the launcher/wiring on the VPS is NOT yet installed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import stat
import sys
import time
from typing import Callable, Mapping, Optional

from backend.v3.events import EventJournal
from backend.v3.runner.config import RunnerConfig, default_config_path, load_runner_config
from backend.v3.runner.prepared_config_guard import verify_prepared_run_config
from backend.v3.runner.exit_service import ExitService, ExitServiceBusy
from backend.v3.runner.exits import load_default_policy
from backend.v3.runner.feed import CandleStore, last_minute_close, minute_fetcher
from backend.v3.runner.manual_close import run_manual_close
from backend.v3.runner.monitor import run_exit_monitor
from backend.v3.lab_tools.fetch_candles import http_json

_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")

class ExitWorkerConfigurationError(ValueError):
    """Fixed error codes only (do not leak data path or secrets to logs)."""


# Un runner Brain di versione precedente non conosce il lease: lo si riconosce dal suo heartbeat senza
# "exit_mode". Finche' quel heartbeat e' recente l'exit-worker non prende le chiusure (difesa in profondita',
# NON una prova di esclusione: il runner va fermato prima del passaggio).
UNPATCHED_RUNNER_WINDOW_MS = 45 * 60_000
_RUNNER_BEAT_MAX_BYTES = 65_536


class ForeignExitOwner(RuntimeError):
    """Un altro proprietario delle uscite potrebbe essere attivo sulla stessa cartella dati."""


def foreign_exit_owner(data_dir: Path, now_ms: int) -> Optional[str]:
    """Sola lettura. None se nessun runner non aggiornato puo' essere attivo; altrimenti un codice fisso."""
    path = data_dir / "heartbeat.json"
    try:
        if path.is_symlink():
            return "runner_heartbeat_unverifiable"
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        return "runner_heartbeat_unverifiable"
    if len(raw) > _RUNNER_BEAT_MAX_BYTES:
        return "runner_heartbeat_unverifiable"
    try:
        beat = json.loads(raw)
    except (ValueError, UnicodeError):
        return "runner_heartbeat_unverifiable"
    if not isinstance(beat, dict) or type(beat.get("ts_ms")) is not int:
        return "runner_heartbeat_unverifiable"
    mode = beat.get("exit_mode")
    if mode in ("sidecar", "legacy"):
        return None          # runner aggiornato: in legacy detiene il lease per tutta la vita, decide il kernel
    if mode is not None:
        return "runner_heartbeat_unverifiable"
    if now_ms - beat["ts_ms"] < UNPATCHED_RUNNER_WINDOW_MS:
        return "unpatched_runner_recent"
    return None


def check_existing_data(*, data_dir: Path, run_id: str,
                        require_existing_run: bool = True) -> EventJournal:
    """Verify existing V3 PAPER journal and scope, without creating any file.

    Empty run is rejected by default: an accidental run typo must not cause an
    unmonitored new portfolio to be treated as protected.
    """
    if (not isinstance(data_dir, Path) or not data_dir.is_absolute() or data_dir.is_symlink()
            or not data_dir.is_dir() or type(run_id) is not str
            or _RUN.fullmatch(run_id) is None or type(require_existing_run) is not bool):
        raise ExitWorkerConfigurationError('invalid_exit_scope')
    try:
        root = data_dir.resolve(strict=True)
        db = root / 'journal.db'
        mode = db.lstat().st_mode
        if db.is_symlink() or not stat.S_ISREG(mode):
            raise ExitWorkerConfigurationError('journal_not_regular')
        with sqlite3.connect(db.as_uri()+'?mode=ro', uri=True, timeout=2) as conn:
            conn.execute('PRAGMA query_only=ON')
            schema = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='v3_events'").fetchone()
            if schema is None:
                raise ExitWorkerConfigurationError('journal_schema_missing')
            if require_existing_run:
                row = conn.execute("SELECT 1 FROM v3_events WHERE portfolio_id='brain' AND run_id=? LIMIT 1",(run_id,)).fetchone()
                if row is None:
                    raise ExitWorkerConfigurationError('run_not_found')
        journal = EventJournal(db)
        journal.verify_chain()
        return journal
    except ExitWorkerConfigurationError:
        raise
    except (OSError, sqlite3.Error, ValueError, TypeError):
        raise ExitWorkerConfigurationError('journal_validation_failed') from None


def build_exit_worker(*, data_dir: Path, run_id: str, config: RunnerConfig,
                      get_json: Callable[[str], object] = http_json,
                      require_existing_run: bool = True) -> ExitService:
    """Wire existing PAPER exits without initializing journal or touching model API."""
    if type(config) is not RunnerConfig or not callable(get_json):
        raise ExitWorkerConfigurationError('invalid_exit_config')
    journal = check_existing_data(data_dir=data_dir, run_id=run_id,
                                  require_existing_run=require_existing_run)
    verify_prepared_run_config(data_dir=data_dir, run_id=run_id, config=config)
    # A distinct 1m store belongs only to this exit worker: never share the AI
    # worker's in-memory cache or mutate its portfolio state.
    minutes = CandleStore(get_json, keep={'1m': (60_000, 1_500)})
    policy = load_default_policy()
    def guard(now_ms: int) -> None:
        code = foreign_exit_owner(data_dir, now_ms)
        if code is not None:
            raise ForeignExitOwner(code)     # tick degraded: nessuna chiusura, nuove aperture bloccate
    def commands(now_ms: int):
        # ExitService.tick applies the shared OPEN/CLOSE lock to both callbacks.
        guard(now_ms)
        return run_manual_close(journal=journal, portfolio_id='brain', run_id=run_id,
                                data_dir=data_dir,
                                price_of=lambda s, t: last_minute_close(s, t, get_json),
                                fee_bps=config.fee_bps, now_ms=now_ms)
    def monitor(now_ms: int):
        guard(now_ms)
        return run_exit_monitor(journal=journal, portfolio_id='brain', run_id=run_id,
                                fetch_bars=minute_fetcher(minutes), policy=policy,
                                fee_bps=config.fee_bps, now_ms=now_ms)
    return ExitService(run_id=run_id, data_dir=data_dir,
                       run_commands=commands, run_monitor=monitor)


def acquire_exit_lease(service: ExitService, *, wait_s: float, sleep: Callable[[float], None],
                       monotonic: Callable[[], float] = time.monotonic) -> None:
    """Passaggio di consegne: attende (al massimo wait_s) che il proprietario attuale rilasci il lease."""
    deadline = monotonic() + wait_s
    while True:
        try:
            service.start()
            return
        except ExitServiceBusy as exc:
            if str(exc) != "exit_service_already_running" or monotonic() >= deadline:
                raise
        sleep(0.25)


def serve(*, service: ExitService, clock: Callable[[], int],
          sleep: Callable[[float], None], stop: Callable[[], bool],
          notify: Callable[[str], bool] = lambda _: False, poll_s: float = 5.0,
          acquire_wait_s: float = 0.0) -> None:
    """Foreground loop; supervisable via systemd Type=notify/WatchdogSec.

    No READY or WATCHDOG on degraded tick; an external supervisor can restart
    the process if market feed, manual-close or monitor stops making progress.
    A restart does NOT itself guarantee healthy market data; new opens stay
    rejected until a newly acquired lease and fresh healthy heartbeat exist.
    """
    if (type(service) is not ExitService or not callable(clock) or not callable(sleep)
            or not callable(stop) or not callable(notify)
            or type(poll_s) not in (int,float) or not 0.25 <= poll_s <= 10.0
            or type(acquire_wait_s) not in (int, float) or not 0 <= acquire_wait_s <= 600):
        raise ExitWorkerConfigurationError('invalid_worker_loop')
    ready = False
    acquire_exit_lease(service, wait_s=acquire_wait_s, sleep=sleep)
    try:
        while not stop():
            r = service.tick(clock())
            if r.state == 'healthy':
                if not ready:
                    notify('READY=1')
                    ready = True
                notify('WATCHDOG=1')
            elif ready:
                notify('STATUS=exit_service_degraded')
            sleep(poll_s)
    finally:
        service.stop()
    if ready:
        notify('STOPPING=1')


def systemd_notify(payload: str) -> bool:
    """Optional sd_notify protocol; never a required dependency for tests."""
    addr = os.environ.get('NOTIFY_SOCKET')
    if not addr or payload not in ('READY=1','WATCHDOG=1','STOPPING=1','STATUS=exit_service_degraded'):
        return False
    import socket
    if addr.startswith('@'):
        addr = '\0' + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(addr)
            s.sendall(payload.encode('ascii'))
        return True
    except OSError:
        return False


def main(argv: Optional[list[str]] = None, *, env: Optional[Mapping[str, str]] = None,
         get_json: Callable[[str], object] = http_json,
         clock: Callable[[], int] = lambda: int(time.time()*1000),
         sleep: Callable[[float], None] = time.sleep,
         should_stop: Optional[Callable[[], bool]] = None,
         notify: Callable[[str],bool] = systemd_notify) -> int:
    parser = argparse.ArgumentParser(description='Brain V3 PAPER exit worker — explicit start only')
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--config', default=str(default_config_path()))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--validate-only', action='store_true', help='read-only checks, never start')
    mode.add_argument('--start-paper', action='store_true', help='explicit foreground PAPER exit owner')
    parser.add_argument('--legacy-exits-disabled', action='store_true',
                        help='operator assertion only: legacy worker ownership removed (NOT a technical proof)')
    parser.add_argument('--wait-lease-s', type=float, default=0.0,
                        help='handover: attendi fino a N s (max 600) che il runner legacy aggiornato rilasci il lease')
    args = parser.parse_args(argv)
    if args.start_paper and not args.legacy_exits_disabled:
        print('handover_required',file=sys.stderr)
        return 2
    variables = os.environ if env is None else env
    if variables.get('DESK_MODE') != 'paper':
        print('paper_mode_required',file=sys.stderr)
        return 2
    try:
        config = load_runner_config(Path(args.config).read_bytes())
        folder = Path(args.data_dir)
        if args.validate_only:
            check_existing_data(data_dir=folder,run_id=args.run_id)
            verify_prepared_run_config(data_dir=folder, run_id=args.run_id, config=config)
            foreign = foreign_exit_owner(folder, clock())
            if foreign is not None:
                print(f'foreign_exit_owner:{foreign}', file=sys.stderr)
                return 3
            print('validated_existing_brain_run')
            return 0
        svc = build_exit_worker(data_dir=folder,run_id=args.run_id,config=config,get_json=get_json)
        foreign = foreign_exit_owner(folder, clock())
    except (ValueError,OSError):
        print('exit_worker_preflight_failed',file=sys.stderr)
        return 2
    if foreign is not None:
        print(f'foreign_exit_owner:{foreign}', file=sys.stderr)
        return 3
    stopped = {'value': False}
    if should_stop is None:
        for signum in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(signum, lambda *_: stopped.update(value=True))
            except ValueError:
                pass
    try:
        serve(service=svc, clock=clock, sleep=sleep,
              stop=should_stop if should_stop is not None else lambda: stopped['value'],
              notify=notify, acquire_wait_s=args.wait_lease_s)
    except ExitServiceBusy:
        print('exit_owner_busy', file=sys.stderr)   # un altro proprietario detiene il lease: nessuna chiusura
        return 3
    except ExitWorkerConfigurationError:
        print('exit_worker_preflight_failed', file=sys.stderr)
        return 2
    except Exception:
        # Nonzero exit triggers supervisor restart. Never claim continued protection.
        print('exit_worker_stopped_unexpectedly',file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
