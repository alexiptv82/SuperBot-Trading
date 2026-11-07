"""Dormant PAPER stop / take-profit / liquidation protection for a paused desk.

Importing this module does not start a thread, read the network, or touch a
data directory. Protection runs only when ``apply_paper_stop_protection`` is
called with the exit-writer lock, ``DESK_PAPER_STOP_MONITOR=1`` and
``DESK_MODE=paper``, and only after the legacy container is proven stopped.

A fresh quote is a finished numeric 1m bar whose close sits inside its own
high/low and whose open timestamp is not in the future and not older than
120 seconds. Anything else leaves that position uncovered. The monitor must
not report coverage it does not have, and it must not invent a price.

The economic close is still ``PaperAccount._close``. This module does not
change liquidation cash, leverage, size or strategy.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Optional

OPT_IN_ENV = "DESK_PAPER_STOP_MONITOR"
OPT_IN_VALUE = "1"
STOP_WORK_NAME = "paper_stop_protect.work"
HEALTH_NAME = "paper_stop_health.json"
DIAG_NAME = "paper_stop_diagnostics.jsonl"
WRITER_LOCK = ".exit_only_writer.lock"
MANUAL_WORK = ("close_position.flag.work", "reset.flag.work")
PROTECTION_REASONS = ("liquidazione", "stop loss", "take profit")
PRICE_MAX_AGE_MS = 120_000
# Bar timestamp is the candle OPEN, not the exchange match time.
QUOTE_CLOCK = "bar_open_ms"


class PaperStopRefused(RuntimeError):
    """Fail closed. A refusal never saves a new portfolio state."""


def monitor_opt_in() -> bool:
    """Read the opt-in. This does not activate anything by itself."""
    return os.environ.get(OPT_IN_ENV) == OPT_IN_VALUE


def _number(value) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _level(value) -> Optional[float]:
    number = _number(value)
    if number is None or number <= 0:
        return None
    return number


def _id_key(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return None


def _same_id(left, right) -> bool:
    a, b = _id_key(left), _id_key(right)
    return a is not None and a == b


def classify_candle(bar, now_ms: int) -> dict:
    """Classify one OHLCV bar. Never returns a price unless the bar is fresh."""
    if isinstance(now_ms, bool) or type(now_ms) is not int or now_ms <= 0:
        return {"status": "anomalous", "reason": "clock", "price": None}
    if not isinstance(bar, (list, tuple)) or len(bar) < 5:
        return {"status": "anomalous", "reason": "shape", "price": None}
    ts = _number(bar[0])
    open_, high, low, close = (_number(bar[i]) for i in range(1, 5))
    if ts is None or any(x is None for x in (open_, high, low, close)):
        return {"status": "anomalous", "reason": "type", "price": None}
    if min(open_, high, low, close) <= 0 or high < low or not (low <= open_ <= high and low <= close <= high):
        return {"status": "anomalous", "reason": "ohlc", "price": None}
    age = now_ms - ts
    if age < 0:
        return {"status": "future", "reason": "timestamp_ahead", "price": None, "ts": ts, "age_ms": age}
    if age > PRICE_MAX_AGE_MS:
        return {"status": "stale", "reason": "older_than_120s", "price": None, "ts": ts, "age_ms": age}
    return {"status": "fresh", "reason": "ok", "price": close, "ts": ts, "age_ms": age,
            "clock": QUOTE_CLOCK}


def quote_protection(pos, price) -> Optional[tuple]:
    """Same priority as ``PaperAccount.on_bar`` on a degenerate bar o=h=l=c=price.

    The returned price is what ``_close`` receives. Slippage stays inside
    ``_close``. A pending second leg is not filled.
    """
    mark = _level(price)
    if mark is None or getattr(pos, "side", None) not in (1, -1):
        return None
    liq = _level(getattr(pos, "liq", None))
    sl = _level(getattr(pos, "sl", None))
    tp = _level(getattr(pos, "tp", None))
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
        if path.is_symlink():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    claims = payload.get("claims") if isinstance(payload, dict) else None
    if not isinstance(claims, list) or not claims:
        return None
    clean = []
    for item in claims:
        if not isinstance(item, dict) or not item.get("symbol") or _id_key(item.get("id")) is None:
            return None
        clean.append({"symbol": str(item["symbol"]), "id": _id_key(item.get("id"))})
    return clean


def _iter_rows(path: Path):
    if not path.is_file() or path.is_symlink():
        return
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def _history_has_close(base: Path, symbol: str, pos_id, close_ms=None) -> bool:
    for row in _iter_rows(base / "trade_history.jsonl"):
        if row.get("symbol") != symbol or not _same_id(row.get("id"), pos_id):
            continue
        if close_ms is not None and row.get("close_ms") != close_ms:
            continue
        if row.get("why") in PROTECTION_REASONS or row.get("why") == "chiusura manuale":
            return True
    return False


def _learning_has_close(base: Path, symbol: str, pos_id, close_ms) -> bool:
    for row in _iter_rows(base / "learning_log.jsonl"):
        if row.get("ev") != "close":
            continue
        if row.get("symbol") == symbol and _same_id(row.get("id"), pos_id) and row.get("close_ms") == close_ms:
            return True
    return False


def _fsync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def inspect_claims(base: Path, acc) -> str:
    """Classify an existing claim file without changing the portfolio."""
    path = base / STOP_WORK_NAME
    if not os.path.lexists(path):
        return "absent"
    if path.is_symlink():
        return "malformed"
    claims = _read_claims(path)
    if not claims:
        return "malformed"
    for claim in claims:
        pos = acc.positions.get(claim["symbol"])
        still_open = pos is not None and _same_id(pos.id, claim["id"])
        recorded = _history_has_close(base, claim["symbol"], claim["id"])
        if still_open and recorded:
            return "mismatch"
        if still_open:
            return "open"
        if not recorded:
            return "unproven"
    return "resolved"


def _archive_claim(base: Path) -> str:
    source = base / STOP_WORK_NAME
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dest = base / ("paper_stop_protect.reconciled-" + stamp + ".json")
    n = 1
    while dest.exists():
        dest = base / ("paper_stop_protect.reconciled-" + stamp + "-" + str(n) + ".json")
        n += 1
    os.replace(source, dest)
    _fsync(dest)
    return dest.name


def _append_diag(base: Path, row: dict) -> None:
    path = base / DIAG_NAME
    line = json.dumps(row, separators=(",", ":"), default=str) + "\n"
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def _load_health(base: Path) -> dict:
    path = base / HEALTH_NAME
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_health(base: Path, payload: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=base, prefix=".paper-stop-health.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"), default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, base / HEALTH_NAME)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    _fsync(base / HEALTH_NAME)


def _coverage(symbols, quotes: dict) -> dict:
    rows = []
    for symbol in symbols:
        quote = quotes.get(symbol) or {"status": "missing", "reason": "no_quote", "price": None}
        status = quote.get("status")
        if status == "fresh" and _level(quote.get("price")) is not None:
            rows.append({"symbol": symbol, "coverage": "covered", "status": "fresh",
                         "reason": "ok", "ts": quote.get("ts"), "age_ms": quote.get("age_ms")})
        else:
            rows.append({"symbol": symbol, "coverage": "uncovered",
                         "status": status or "missing", "reason": quote.get("reason") or "no_quote"})
    if not symbols:
        overall = "idle"
    elif all(row["coverage"] == "covered" for row in rows):
        overall = "covered"
    elif any(row["coverage"] == "covered" for row in rows):
        overall = "partial"
    else:
        overall = "blind"
    return {"coverage": overall, "positions": rows}


def _transitions(previous: dict, current_rows: list) -> list:
    old = previous.get("symbols") if isinstance(previous.get("symbols"), dict) else {}
    events = []
    for row in current_rows:
        before = old.get(row["symbol"])
        now = row["status"]
        if before in (None, "absent"):
            kind = "baseline"
        elif before == "fresh" and now != "fresh":
            kind = "feed_lost"
        elif before != "fresh" and now == "fresh":
            kind = "feed_recovered"
        else:
            continue
        events.append({"symbol": row["symbol"], "kind": kind, "status": now, "reason": row["reason"]})
    return events


def _hold_writer_lock(base: Path):
    fd = os.open(base / WRITER_LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise PaperStopRefused("ownership_lock_required") from None
    return fd


def _release_writer_lock(fd: int) -> None:
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _fd_is_writer_lock(fd, base: Path) -> bool:
    try:
        target = os.path.realpath(os.readlink("/proc/self/fd/" + str(fd)))
    except OSError:
        return False
    return target == os.path.realpath(base / WRITER_LOCK)


def _quotes_from_prices(prices: dict) -> dict:
    """Tests pass a synthetic fresh mark. Absence is not a price."""
    quotes = {}
    for symbol, price in (prices or {}).items():
        level = _level(price)
        if level is None:
            quotes[symbol] = {"status": "anomalous", "reason": "price", "price": None}
        else:
            quotes[symbol] = {"status": "fresh", "reason": "synthetic", "price": level}
    return quotes


def _durable_record(legacy, base: Path, state: dict, record: dict) -> None:
    legacy.record_close(state, record)
    history = base / "trade_history.jsonl"
    learning = base / "learning_log.jsonl"
    for path in (history, learning):
        if path.is_file():
            _fsync(path)
    if not _history_has_close(base, record["symbol"], record["id"], record["close_ms"]):
        raise PaperStopRefused("history_not_durable")
    if not _learning_has_close(base, record["symbol"], record["id"], record["close_ms"]):
        raise PaperStopRefused("learning_not_durable")


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
    _fsync(base / STOP_WORK_NAME)


def apply_paper_stop_protection(legacy, prices: dict, now_ms: int, *, lock_held: bool,
                                legacy_stopped, quotes: Optional[dict] = None,
                                lock_fd: Optional[int] = None) -> dict:
    """Close PAPER positions already past stop, target or liquidation.

    ``lock_held`` must be true and this call re-checks the writer lock.
    ``legacy_stopped`` must return true both before and after the durable
    history write. Missing or bad quotes never become a close.
    """
    if lock_held is not True or not callable(legacy_stopped):
        raise PaperStopRefused("ownership_lock_required")
    if not monitor_opt_in():
        return {"enabled": False, "closed": [], "kept": [], "blocked": None,
                "stop_protection": "off", "positions": []}
    if os.environ.get("DESK_MODE") != "paper" or legacy.LIVE._live:
        raise PaperStopRefused("paper_only")
    if isinstance(now_ms, bool) or type(now_ms) is not int:
        raise PaperStopRefused("clock")
    base = Path(legacy.DATA_DIR)
    if base.is_symlink() or not base.is_dir():
        raise PaperStopRefused("data_directory_missing_or_symlink")
    if not (base / "pause.flag").is_file():
        raise PaperStopRefused("pause_required")
    if not legacy_stopped():
        raise PaperStopRefused("legacy_container_not_proven_stopped_and_disabled")

    owned_lock = False
    if lock_fd is None:
        lock_fd = _hold_writer_lock(base)
        owned_lock = True
    elif not _fd_is_writer_lock(lock_fd, base):
        raise PaperStopRefused("ownership_lock_required")
    try:
        if any((base / name).exists() for name in MANUAL_WORK):
            return {"enabled": True, "closed": [], "kept": [], "blocked": "unreconciled_manual_close",
                    "stop_protection": "blocked", "positions": []}
        state = legacy.load_state(str(base / "state_v2.json"))
        acc = legacy.make_account(state)
        verdict = inspect_claims(base, acc)
        if verdict == "resolved":
            _archive_claim(base)
            _append_diag(base, {"ts": now_ms, "kind": "claim_reconciled"})
        elif verdict not in ("absent",):
            _note_transition(base, now_ms, "blocked", [], kind=verdict)
            return {"enabled": True, "closed": [], "kept": sorted(acc.positions),
                    "blocked": verdict, "stop_protection": "blocked", "positions": []}

        quote_map = quotes if quotes is not None else _quotes_from_prices(prices)
        symbols = list(acc.positions)
        health = _coverage(symbols, quote_map)
        fresh = {}
        for row in health["positions"]:
            if row["coverage"] != "covered":
                continue
            fresh[row["symbol"]] = quote_map[row["symbol"]]["price"]
        _note_transition(base, now_ms, health["coverage"], health["positions"])

        planned = []
        for symbol in symbols:
            pos = acc.positions[symbol]
            if now_ms < pos.open_ms:
                continue
            if symbol not in fresh:
                continue
            decision = quote_protection(pos, fresh[symbol])
            if decision is None:
                continue
            why, fill = decision
            if why not in PROTECTION_REASONS:
                continue
            planned.append((symbol, _id_key(pos.id), why, fill))
        if not planned:
            return {"enabled": True, "closed": [], "kept": sorted(acc.positions), "blocked": None,
                    "stop_protection": health["coverage"], "positions": health["positions"]}

        if not legacy_stopped():
            raise PaperStopRefused("legacy_container_not_proven_stopped_and_disabled")
        _write_claims(base, [{"symbol": symbol, "id": pos_id, "why": why}
                             for symbol, pos_id, why, _fill in planned])
        closed = []
        for symbol, pos_id, why, fill in planned:
            pos = acc.positions.get(symbol)
            if pos is None or not _same_id(pos.id, pos_id):
                continue
            if _history_has_close(base, symbol, pos_id):
                raise PaperStopRefused("state_history_mismatch")
            record = acc._close(pos, fill, now_ms, why)
            _durable_record(legacy, base, state, record)
            closed.append({"symbol": symbol, "id": record["id"], "why": record["why"],
                           "net": record["net"], "exit": record["exit"]})
        if not legacy_stopped():
            raise PaperStopRefused("legacy_container_not_proven_stopped_and_disabled")
        legacy.flush_events(state, acc)
        legacy.save_account(acc, state)
        legacy.save_state(state, str(base / "state_v2.json"))
        _fsync(base / "state_v2.json")
        try:
            if (base / STOP_WORK_NAME).is_file() and not (base / STOP_WORK_NAME).is_symlink():
                (base / STOP_WORK_NAME).unlink()
        except OSError:
            pass
        return {"enabled": True, "closed": closed, "kept": sorted(acc.positions), "blocked": None,
                "stop_protection": health["coverage"], "positions": health["positions"]}
    finally:
        if owned_lock:
            _release_writer_lock(lock_fd)


def _note_transition(base: Path, now_ms: int, coverage: str, rows: list, kind: Optional[str] = None) -> None:
    previous = _load_health(base)
    events = _transitions(previous, rows) if rows else []
    if kind and previous.get("blocked") != kind:
        events.append({"symbol": "*", "kind": kind, "status": "blocked", "reason": kind})
    payload = {
        "ts": now_ms,
        "coverage": coverage,
        "blocked": kind,
        "symbols": {row["symbol"]: row["status"] for row in rows},
    }
    try:
        _save_health(base, payload)
        for event in events:
            if event["kind"] == "baseline" and previous:
                continue
            _append_diag(base, {"ts": now_ms, "coverage": coverage, **event})
    except OSError:
        return


def reconcile_stop_claim(legacy) -> str:
    """Startup helper. Archives a claim already present in history and state.

    An open, mismatched, unproven or malformed claim is left in place and the
    caller must refuse to start. This never closes a position.
    """
    base = Path(legacy.DATA_DIR)
    if not os.path.lexists(base / STOP_WORK_NAME):
        return "absent"
    state = legacy.load_state(str(base / "state_v2.json"))
    acc = legacy.make_account(state)
    verdict = inspect_claims(base, acc)
    if verdict == "resolved":
        _archive_claim(base)
        _append_diag(base, {"ts": int(time.time() * 1000), "kind": "startup_claim_reconciled"})
        return "resolved"
    return verdict
