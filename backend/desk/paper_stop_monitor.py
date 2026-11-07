"""Dormant PAPER stop / take-profit / liquidation protection for a paused desk.

Importing this module does not start a thread, read the network, or touch a
data directory. Protection runs only when a caller that already holds the
exit-writer lock invokes ``apply_paper_stop_protection`` and the process
environment is exactly ``DESK_PAPER_STOP_MONITOR=1`` with ``DESK_MODE=paper``.

The decision reuses the existing paper engine's priority for a single fresh
price (liquidation, then stop, then take profit) and the existing ``_close``
accounting. It does not open trades, fill a pending second leg, change size
or leverage, call Claude, or talk to an exchange.

A claimed ``paper_stop_protect.work`` file blocks another automatic close.
That is the restart guard: an interrupted claim is reconciled, never replayed.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
from typing import Optional

OPT_IN_ENV = "DESK_PAPER_STOP_MONITOR"
OPT_IN_VALUE = "1"
STOP_WORK_NAME = "paper_stop_protect.work"
MANUAL_WORK = ("close_position.flag.work", "reset.flag.work")
PROTECTION_REASONS = ("liquidazione", "stop loss", "take profit")


class PaperStopRefused(RuntimeError):
    """Fail closed. A refusal never writes a close."""


def monitor_opt_in() -> bool:
    """Read the opt-in. This does not activate anything by itself."""
    return os.environ.get(OPT_IN_ENV) == OPT_IN_VALUE


def _level(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def quote_protection(pos, price) -> Optional[tuple]:
    """Same priority as ``PaperAccount.on_bar`` on a degenerate bar o=h=l=c=price.

    The returned price is the value passed to ``_close`` (slippage is applied
    there). A pending second leg is ignored: filling it would add margin.
    Returns ``(why, fill)`` or None when the fresh price does not cross a level.
    """
    mark = _level(price)
    if mark is None or getattr(pos, "side", None) not in (1, -1):
        return None
    liq, sl, tp = _level(getattr(pos, "liq", None)), _level(getattr(pos, "sl", None)), _level(getattr(pos, "tp", None))
    if pos.side == 1:
        if liq is not None and mark <= liq:
            return ("liquidazione", liq)
        if sl is not None and mark <= sl:
            return ("stop loss", min(sl, mark))
        if tp is not None and mark >= tp:
            return ("take profit", tp)
    else:
        if liq is not None and mark >= liq:
            return ("liquidazione", liq)
        if sl is not None and mark >= sl:
            return ("stop loss", max(sl, mark))
        if tp is not None and mark <= tp:
            return ("take profit", tp)
    return None


def _read_claims(path: Path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    claims = payload.get("claims") if isinstance(payload, dict) else None
    if not isinstance(claims, list) or not claims:
        return None
    clean = []
    for item in claims:
        if not isinstance(item, dict) or not item.get("symbol") or item.get("id") is None:
            return None
        clean.append({"symbol": str(item["symbol"]), "id": item["id"]})
    return clean


def _claim_still_open(acc, claims) -> bool:
    for claim in claims:
        pos = acc.positions.get(claim["symbol"])
        if pos is not None and pos.id == claim["id"]:
            return True
    return False


def _write_claims(base: Path, claims: list) -> None:
    fd, tmp = tempfile.mkstemp(dir=base, prefix=".paper-stop-claim.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"claims": claims}, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, base / STOP_WORK_NAME)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def apply_paper_stop_protection(legacy, prices: dict, now_ms: int, *, lock_held: bool) -> dict:
    """Close PAPER positions already past stop, target or liquidation.

    ``lock_held`` must be true only for the exit writer that owns the
    directory lock. The default environment leaves this function inert.
    """
    if not lock_held:
        raise PaperStopRefused("ownership_lock_required")
    if not monitor_opt_in():
        return {"enabled": False, "closed": [], "kept": [], "blocked": None}
    if os.environ.get("DESK_MODE") != "paper" or legacy.LIVE._live:
        raise PaperStopRefused("paper_only")
    base = Path(legacy.DATA_DIR)
    if base.is_symlink() or not base.is_dir():
        raise PaperStopRefused("data_directory_missing_or_symlink")
    if not (base / "pause.flag").is_file():
        raise PaperStopRefused("pause_required")
    if any((base / name).exists() for name in MANUAL_WORK):
        return {"enabled": True, "closed": [], "kept": [], "blocked": "unreconciled_manual_close"}

    state = legacy.load_state(str(base / "state_v2.json"))
    acc = legacy.make_account(state)
    work = base / STOP_WORK_NAME
    if os.path.lexists(work):
        if work.is_symlink():
            return {"enabled": True, "closed": [], "kept": sorted(acc.positions),
                    "blocked": "unreconciled_stop_protection"}
        claims = _read_claims(work)
        if claims is None or _claim_still_open(acc, claims):
            return {"enabled": True, "closed": [], "kept": sorted(acc.positions),
                    "blocked": "unreconciled_stop_protection"}
        work.unlink()

    planned = []
    for symbol in list(acc.positions):
        pos = acc.positions[symbol]
        if not isinstance(now_ms, int) or now_ms < pos.open_ms:
            continue
        decision = quote_protection(pos, (prices or {}).get(symbol))
        if decision is None:
            continue
        why, fill = decision
        if why not in PROTECTION_REASONS:
            continue
        planned.append((symbol, pos.id, why, fill))
    if not planned:
        return {"enabled": True, "closed": [], "kept": sorted(acc.positions), "blocked": None}

    _write_claims(base, [{"symbol": symbol, "id": pos_id, "why": why} for symbol, pos_id, why, _fill in planned])
    closed = []
    for symbol, _pos_id, why, fill in planned:
        pos = acc.positions.get(symbol)
        if pos is None:
            continue
        record = acc._close(pos, fill, now_ms, why)
        legacy.record_close(state, record)
        closed.append({"symbol": symbol, "id": record["id"], "why": record["why"],
                       "net": record["net"], "exit": record["exit"]})
    legacy.flush_events(state, acc)
    legacy.save_account(acc, state)
    legacy.save_state(state, str(base / "state_v2.json"))
    if work.exists():
        work.unlink()
    return {"enabled": True, "closed": closed, "kept": sorted(acc.positions), "blocked": None}
