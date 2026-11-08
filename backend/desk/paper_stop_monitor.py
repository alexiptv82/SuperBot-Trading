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
# Bar timestamp is the candle OPEN. A 1m bar is closed only after 60s.
# Usable closed bars are those whose open is 60–120 seconds old.
BAR_MS = 60_000
QUOTE_CLOCK = "bar_open_ms"
EXECUTION_MODEL = "closed_1m_close_only"
INTRABAR_WICK = "not_a_fill"


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
    common = {"ts": ts, "age_ms": age, "clock": QUOTE_CLOCK,
              "execution": EXECUTION_MODEL, "intrabar_wick": INTRABAR_WICK}
    if age < 0:
        return {"status": "future", "reason": "timestamp_ahead", "price": None, **common}
    if age < BAR_MS:
        # The exchange bar is still forming. Its close is not a finished price.
        return {"status": "incomplete", "reason": "candle_still_forming", "price": None, **common}
    if age > PRICE_MAX_AGE_MS:
        return {"status": "stale", "reason": "older_than_120s", "price": None, **common}
    return {"status": "fresh", "reason": "closed_bar", "price": close, **common}


def select_closed_minute(bars, now_ms: int) -> dict:
    """Use the newest completed 1m bar. A forming bar is not a price."""
    if not isinstance(bars, (list, tuple)) or not bars:
        return {"status": "missing", "reason": "empty_feed", "price": None,
                "execution": EXECUTION_MODEL, "intrabar_wick": INTRABAR_WICK}
    forming = False
    for bar in reversed(list(bars)):
        found = classify_candle(bar, now_ms)
        if found["status"] == "incomplete":
            forming = True
            continue
        return found
    if forming:
        return {"status": "incomplete", "reason": "candle_still_forming", "price": None,
                "execution": EXECUTION_MODEL, "intrabar_wick": INTRABAR_WICK}
    return {"status": "anomalous", "reason": "shape", "price": None,
            "execution": EXECUTION_MODEL, "intrabar_wick": INTRABAR_WICK}


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
        open_ms = item.get("open_ms")
        clean.append({
            "symbol": str(item["symbol"]),
            "id": _id_key(item.get("id")),
            "open_ms": open_ms if type(open_ms) is int else None,
            "run_no": item.get("run_no"),
            "portfolio": item.get("portfolio"),
        })
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


def _is_partial_row(row: dict) -> bool:
    if row.get("partial") is True:
        return True
    why = str(row.get("why") or "").lower()
    return "parzial" in why


def _terminal_match(row: dict, *, symbol: str, pos_id, open_ms: int,
                    close_ms=None, portfolio=None, run_no=None) -> bool:
    """A terminal close of this exact position. Partial fills and other runs do not match."""
    if not isinstance(row, dict) or _is_partial_row(row):
        return False
    if row.get("symbol") != symbol or not _same_id(row.get("id"), pos_id):
        return False
    if type(open_ms) is not int or row.get("open_ms") != open_ms:
        return False
    if close_ms is not None and row.get("close_ms") != close_ms:
        return False
    if run_no is not None and "run_no" in row and row.get("run_no") != run_no:
        return False
    # `account` in the trade record is the paper book name ("main"), not Falco/Toro.
    if portfolio is not None and "portfolio" in row and row.get("portfolio") not in (None, portfolio):
        return False
    why = row.get("why")
    if row.get("ev") == "close":
        return why in PROTECTION_REASONS or why == "chiusura manuale" or why is None
    return why in PROTECTION_REASONS or why == "chiusura manuale"


def _same_number(left, right) -> bool:
    try:
        a, b = float(left), float(right)
    except (TypeError, ValueError):
        return left == right
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    return round(a, 4) == round(b, 4)


def _same_closure_economics(history_row: dict, learning_row: dict) -> bool:
    """The two files must describe one fill, not two closes of one position."""
    if type(history_row.get("close_ms")) is not int or history_row.get("close_ms") != learning_row.get("close_ms"):
        return False
    if history_row.get("why") != learning_row.get("why"):
        return False
    if "net" not in history_row or "net" not in learning_row:
        return False
    if not _same_number(history_row.get("net"), learning_row.get("net")):
        return False
    for field in ("gross", "fees", "exit"):
        in_history, in_learning = field in history_row, field in learning_row
        if in_history != in_learning:
            return False
        if in_history and not _same_number(history_row.get(field), learning_row.get(field)):
            return False
    return True


def _closure_fingerprint(row: dict):
    """Identity of one terminal fill. None means the row cannot be compared safely."""
    if type(row.get("close_ms")) is not int or row.get("why") is None or "net" not in row:
        return None
    if isinstance(row.get("net"), bool):
        return None
    try:
        net = float(row["net"])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(net):
        return None
    extras = []
    for field in ("gross", "fees", "exit"):
        if field not in row:
            extras.append(None)
            continue
        if isinstance(row[field], bool):
            return None
        try:
            number = float(row[field])
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        extras.append(round(number, 4))
    return (row["close_ms"], row.get("why"), round(net, 4), tuple(extras))


def _terminal_rows(base: Path, symbol: str, pos_id, open_ms: int, *, portfolio=None, run_no=None):
    history_rows = []
    for row in _iter_rows(base / "trade_history.jsonl"):
        if _terminal_match(row, symbol=symbol, pos_id=pos_id, open_ms=open_ms,
                           portfolio=portfolio, run_no=run_no):
            history_rows.append(row)
    learning_rows = []
    for row in _iter_rows(base / "learning_log.jsonl"):
        if row.get("ev") != "close":
            continue
        if _terminal_match(row, symbol=symbol, pos_id=pos_id, open_ms=open_ms,
                           portfolio=portfolio, run_no=run_no):
            learning_rows.append(row)
    return history_rows, learning_rows


def terminal_closure_status(base: Path, symbol: str, pos_id, open_ms: int, *,
                            portfolio=None, run_no=None) -> str:
    """unique, discordant, or absent.

    One matching history/learning pair is not enough when either register also
    contains a different terminal close for this same position. Identical
    repeated rows are the same fill and are kept. Partial rows are ignored.
    """
    if type(open_ms) is not int:
        return "discordant"
    history_rows, learning_rows = _terminal_rows(
        base, symbol, pos_id, open_ms, portfolio=portfolio, run_no=run_no)
    if not history_rows and not learning_rows:
        return "absent"
    history_keys = [_closure_fingerprint(row) for row in history_rows]
    learning_keys = [_closure_fingerprint(row) for row in learning_rows]
    if any(key is None for key in history_keys + learning_keys):
        return "discordant"
    history_set, learning_set = set(history_keys), set(learning_keys)
    if len(history_set) > 1 or len(learning_set) > 1 or history_set != learning_set:
        return "discordant"
    if len(history_set) != 1:
        return "absent"
    return "unique"


def find_same_closure(base: Path, symbol: str, pos_id, open_ms: int, *,
                      portfolio=None, run_no=None):
    """Return one history/learning pair only when every terminal row agrees.

    A competing terminal close in either file, even if another pair matches,
    returns None. Nothing is deleted.
    """
    if terminal_closure_status(base, symbol, pos_id, open_ms,
                               portfolio=portfolio, run_no=run_no) != "unique":
        return None
    history_rows, learning_rows = _terminal_rows(
        base, symbol, pos_id, open_ms, portfolio=portfolio, run_no=run_no)
    for history_row in history_rows:
        for learning_row in learning_rows:
            if _same_closure_economics(history_row, learning_row):
                return (history_row, learning_row)
    return None


def _history_has_close(base: Path, symbol: str, pos_id, close_ms=None, *,
                       open_ms: int, portfolio=None, run_no=None) -> bool:
    return find_same_closure(base, symbol, pos_id, open_ms,
                             portfolio=portfolio, run_no=run_no) is not None and (
        close_ms is None or find_same_closure(
            base, symbol, pos_id, open_ms, portfolio=portfolio, run_no=run_no)[0].get("close_ms") == close_ms)


def _learning_has_close(base: Path, symbol: str, pos_id, close_ms, *,
                        open_ms: int, portfolio=None, run_no=None) -> bool:
    pair = find_same_closure(base, symbol, pos_id, open_ms, portfolio=portfolio, run_no=run_no)
    if pair is None:
        return False
    if close_ms is not None and pair[1].get("close_ms") != close_ms:
        return False
    return True


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
    # One file lists every position claimed in the same tick. The group is
    # resolved only when every claim is. A later resolved row must not hide
    # an earlier open, unproven, or mismatched one, nor the reverse.
    verdicts = []
    for claim in claims:
        if type(claim.get("open_ms")) is not int:
            verdicts.append("unproven")
            continue
        pos = acc.positions.get(claim["symbol"])
        still_open = (pos is not None and _same_id(pos.id, claim["id"])
                      and pos.open_ms == claim["open_ms"])
        portfolio = claim.get("portfolio")
        run_no = claim.get("run_no")
        status = terminal_closure_status(
            base, claim["symbol"], claim["id"], claim["open_ms"],
            portfolio=portfolio, run_no=run_no)
        if status == "discordant":
            verdicts.append("mismatch" if still_open else "unproven")
        elif status == "unique":
            verdicts.append("mismatch" if still_open else "resolved")
        elif still_open:
            verdicts.append("open")
        else:
            verdicts.append("unproven")
    if any(item == "mismatch" for item in verdicts):
        return "mismatch"
    if any(item == "open" for item in verdicts):
        return "open"
    if any(item == "unproven" for item in verdicts):
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


def _prove_writer_lock(fd, base: Path) -> None:
    """Path match is not ownership. Relocking this fd must succeed.

    An fd opened on the lock file but not flocked fails here when another
    holder already has LOCK_EX. The call never unlocks a lock it did not take.
    """
    if not _fd_is_writer_lock(fd, base):
        raise PaperStopRefused("ownership_lock_required")
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        raise PaperStopRefused("ownership_lock_required") from exc


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
    portfolio = getattr(legacy.PORTFOLIO, "name", None)
    run_no = state.get("run_no")
    if not _history_has_close(base, record["symbol"], record["id"], record["close_ms"],
                              open_ms=record["open_ms"], portfolio=portfolio, run_no=run_no):
        raise PaperStopRefused("history_not_durable")
    if not _learning_has_close(base, record["symbol"], record["id"], record["close_ms"],
                               open_ms=record["open_ms"], portfolio=portfolio, run_no=run_no):
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
    else:
        _prove_writer_lock(lock_fd, base)
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
        telemetry_ok = _note_transition(base, now_ms, health["coverage"], health["positions"])
        if not telemetry_ok:
            return {"enabled": True, "closed": [], "kept": sorted(acc.positions), "blocked": None,
                    "stop_protection": "telemetry_failed", "telemetry_ok": False,
                    "positions": health["positions"]}

        portfolio = getattr(legacy.PORTFOLIO, "name", None)
        run_no = state.get("run_no")
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
            planned.append((symbol, _id_key(pos.id), pos.open_ms, why, fill))
        if not planned:
            return {"enabled": True, "closed": [], "kept": sorted(acc.positions), "blocked": None,
                    "stop_protection": health["coverage"], "telemetry_ok": True,
                    "positions": health["positions"],
                    "execution": EXECUTION_MODEL, "intrabar_wick": INTRABAR_WICK}

        if not legacy_stopped():
            raise PaperStopRefused("legacy_container_not_proven_stopped_and_disabled")
        _write_claims(base, [{"symbol": symbol, "id": pos_id, "open_ms": open_ms, "why": why,
                              "run_no": run_no, "portfolio": portfolio}
                             for symbol, pos_id, open_ms, why, _fill in planned])
        closed = []
        for symbol, pos_id, open_ms, why, fill in planned:
            pos = acc.positions.get(symbol)
            if pos is None or not _same_id(pos.id, pos_id) or pos.open_ms != open_ms:
                continue
            if terminal_closure_status(base, symbol, pos_id, open_ms,
                                       portfolio=portfolio, run_no=run_no) in ("unique", "discordant"):
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
                "stop_protection": health["coverage"], "telemetry_ok": True,
                "positions": health["positions"],
                "execution": EXECUTION_MODEL, "intrabar_wick": INTRABAR_WICK,
                "stop_certified": False}
    finally:
        if owned_lock:
            _release_writer_lock(lock_fd)


def _note_transition(base: Path, now_ms: int, coverage: str, rows: list, kind: Optional[str] = None) -> bool:
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
        return True
    except OSError:
        return False


def protection_alarm(heartbeat, now=None) -> dict:
    """Fail-visible reading of the exit heartbeat. `ready` is not stop coverage.

    The dashboard is intentionally not changed here. Callers that only look at
    `ready` still get an explicit alarm from this function.
    """
    reasons = []
    if not isinstance(heartbeat, dict):
        return {"alarm": True, "reasons": ["missing"]}
    try:
        timestamp = float(heartbeat.get("ts"))
    except (TypeError, ValueError):
        timestamp = None
    moment = time.time() if now is None else now
    if timestamp is None or not math.isfinite(timestamp) or not (-2 <= moment - timestamp < 12):
        reasons.append("heartbeat_stale")
    status = heartbeat.get("stop_protection")
    if heartbeat.get("ready") is True and status not in ("covered", "idle", "off"):
        reasons.append("ready_is_not_stop_coverage")
    if status in ("blind", "partial", "blocked", "telemetry_failed", "unverified"):
        reasons.append(status)
    if heartbeat.get("telemetry_ok") is False:
        reasons.append("telemetry_failed")
    if heartbeat.get("stop_certified") is not False:
        reasons.append("stop_certified_must_stay_false")
    if heartbeat.get("intrabar_wick") == INTRABAR_WICK:
        reasons.append("intrabar_wick_not_a_fill")
    return {"alarm": bool(reasons), "reasons": reasons}


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
