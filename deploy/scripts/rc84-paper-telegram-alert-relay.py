#!/usr/bin/env python3
"""PAPER-only Telegram alert relay for NEW RC84 Falco and Toro.

This process is deliberately OUTSIDE the trading runners: never restarts a
runner, sends an exchange order, writes wallet state, or changes risk/mandate.
It watches atomic on-disk account snapshots and committed trade_history rows,
sending informational Telegram messages with a private durable dedup ledger.
Existing open positions get explicitly labelled "RECUPERO AVVISO".
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import urllib.request
from typing import Mapping

RUN_ROOT = Path("/opt/superbot-v3-paper-runs")
WALLETS = (
    ("FALCO", "🦅", RUN_ROOT / "classic-hawk-paper20261111", "hawk",
     "superbot-v3-paper-falco.service"),
    ("TORO", "🐂", RUN_ROOT / "classic-bull-paper20261111", "bull",
     "superbot-v3-paper-toro.service"),
)
LEDGER_DIR = Path("/opt/superbot-v3-telegram-notifier")
DB_PATH = LEDGER_DIR / "sent.sqlite3"
LOCK_PATH = LEDGER_DIR / "relay.lock"
POLL_SECONDS = 15
MAX_EVENTS_PER_TICK = 12
MIN_RETRY_MS = 90_000
MAX_HISTORY_BYTES = 524_288
KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
SYMBOL_RE = re.compile(r"^[A-Za-z0-9_-]{1,25}$")
TOKEN_RE = re.compile(r"^[0-9]{6,20}:[A-Za-z0-9_-]{25,100}$")
CHAT_RE = re.compile(r"^-?[0-9]{5,25}$")


def clock_ms() -> int:
    return int(time.time() * 1000)


def fail(message: str) -> None:
    raise RuntimeError(message)


def _json_file(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        fail("PAPER_FILE_MISSING_OR_SYMLINK")
    body = json.loads(path.read_text(encoding="utf-8"))
    if type(body) is not dict:
        fail("PAPER_FILE_INVALID")
    return body


def validate_wallets() -> None:
    for label, _, path, pid, _ in WALLETS:
        if path.is_symlink() or not path.is_dir():
            fail("RUN_DIR_UNAVAILABLE")
        marker = _json_file(path / "PREPARED_PAUSED_ONLY.json")
        if marker.get("paper_only") is not True or marker.get("portfolio_id") != pid:
            fail("NOT_AUTHORIZED_PAPER_WALLET")
        # The account may contain open positions; never require it to be
        # empty, paused, stopped or restarted to recover alerts.
        state = _json_file(path / "state_v2.json")
        if type((state.get("main") or {}).get("positions")) is not dict:
            fail("WALLET_ACCOUNT_SHAPE_CHANGED")


def _credentials() -> tuple[str, str]:
    token = os.environ.get(KEYS[0], "")
    chat = os.environ.get(KEYS[1], "")
    if not TOKEN_RE.fullmatch(token) or not CHAT_RE.fullmatch(chat):
        fail("TELEGRAM_CREDENTIALS_MISSING_OR_INVALID")
    return token, chat


def _api_call(token: str, operation: str, data: dict | None) -> bool:
    if operation not in ("getMe", "sendMessage"):
        return False
    url = "https://api.telegram.org/bot" + token + "/" + operation
    try:
        if data is None:
            req = urllib.request.Request(url, method="GET")
        else:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                url, data=body, method="POST",
                headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            if r.status != 200:
                return False
            response = json.loads(r.read(65536).decode("utf-8"))
        return type(response) is dict and response.get("ok") is True
    except Exception:
        # Never print exception! An HTTP error often embeds the secret token
        # in the requested URL.
        return False


def _safe_number(x, places: int = 4) -> str:
    try:
        value = Decimal(str(x))
        if not value.is_finite() or abs(value) > Decimal("1e15"):
            return "n/d"
        return f"{value:,.{places}f}"
    except (InvalidOperation, TypeError, ValueError):
        return "n/d"


def _event_id(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def _open_events(state: dict, *, wallet: str, icon: str, now_ms: int,
                 observer_started_ms: int) -> list[tuple[str, str, str]]:
    positions = (state.get("main") or {}).get("positions") or {}
    run = state.get("run_no", 1)
    if type(positions) is not dict or len(positions) > 100:
        return []
    out = []
    for symbol, item in sorted(positions.items()):
        if type(symbol) is not str or not SYMBOL_RE.fullmatch(symbol) or type(item) is not dict:
            continue
        if item.get("symbol") not in (None, symbol):
            continue
        pid, opened = item.get("id"), item.get("open_ms")
        if (type(opened) is not int or opened <= 0 or opened > now_ms + 120000
                or type(pid) not in (str, int) or not str(pid) or len(str(pid)) > 60):
            continue
        side = item.get("side")
        if side not in (1, -1):
            continue
        kind = "LONG 🟢" if side == 1 else "SHORT 🔴"
        catchup = opened < observer_started_ms
        title = "APERTURA — AVVISO RECUPERATO" if catchup else "TRADE APERTO"
        leverage = item.get("leverage")
        lev = str(leverage) if type(leverage) is int and 1 <= leverage <= 125 else "n/d"
        message = (
            f"{icon} <b>{wallet} · {html.escape(title)} (PAPER)</b>\n"
            f"📊 {html.escape(symbol)} · {kind} · leva {lev}x\n"
            f"💰 Ingresso: {_safe_number(item.get('entry'), 6)} USDT\n"
            f"💵 Margine: {_safe_number(item.get('total_margin', item.get('margin')), 2)} USDT\n"
            f"🛡️ Stop: {_safe_number(item.get('sl'), 6)}\n"
            "🧾 Operazione simulata, non denaro reale.")
        eid = _event_id("open", wallet, run, symbol, pid, opened)
        out.append((eid, wallet, message))
    return out


def _recent_history(path: Path) -> list[dict]:
    if path.is_symlink() or not path.is_file():
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            start = max(size - MAX_HISTORY_BYTES, 0)
            fh.seek(start)
            if start:
                fh.readline()  # drop a possibly truncated line
            lines = fh.readlines()
        if len(lines) > 3000:
            lines = lines[-3000:]
    except OSError:
        return []
    rows = []
    for raw in lines:
        try:
            row = json.loads(raw)
            if type(row) is dict:
                rows.append(row)
        except (UnicodeError, ValueError, TypeError):
            continue
    return rows


def _close_events(path: Path, *, wallet: str, icon: str, since_ms: int,
                  now_ms: int) -> list[tuple[str, str, str]]:
    rows = _recent_history(path / "trade_history.jsonl")
    out = []
    for rec in rows:
        symbol, closed = rec.get("symbol"), rec.get("close_ms")
        if (type(symbol) is not str or not SYMBOL_RE.fullmatch(symbol)
                or type(closed) is not int or not since_ms <= closed <= now_ms + 120000
                or type(rec.get("open_ms")) is not int
                or rec.get("side") not in (1, -1)):
            continue
        # This module reports *committed* closure events only. Existing
        # accounting/learning remains the responsibility of the trading bot.
        partial = bool(rec.get("partial") is True)
        label = "CHIUSURA PARZIALE" if partial else "TRADE CHIUSO"
        net = _safe_number(rec.get("net"), 2)
        message = (f"{icon} <b>{wallet} · {label} (PAPER)</b>\n"
                   f"📊 {html.escape(symbol)}\n"
                   f"💵 P&amp;L netto: {net} USDT\n"
                   "🧾 Esito simulato, non denaro reale.")
        key = _event_id("close", wallet, symbol, rec.get("id"), rec["open_ms"],
                        closed, partial, rec.get("fraction"), rec.get("net"))
        out.append((key, wallet, message))
    return out


def _private_db() -> sqlite3.Connection:
    if (not LEDGER_DIR.is_dir() or LEDGER_DIR.is_symlink()
            or LEDGER_DIR.stat().st_uid != 0
            or stat.S_IMODE(LEDGER_DIR.stat().st_mode) != 0o700):
        fail("PRIVATE_LEDGER_DIRECTORY_REQUIRED")
    if DB_PATH.is_symlink():
        fail("SYMLINK_LEDGER_REFUSED")
    if DB_PATH.exists() and (not DB_PATH.is_file() or DB_PATH.stat().st_mode & 0o077):
        fail("LEDGER_PERMISSIONS_INVALID")
    if not DB_PATH.exists():
        f = os.open(DB_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                    getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.close(f)
    db = sqlite3.connect(DB_PATH, timeout=8, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS meta(
        name TEXT PRIMARY KEY, value TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS notice(
        event_id TEXT PRIMARY KEY, wallet TEXT NOT NULL,
        last_attempt_ms INTEGER NOT NULL DEFAULT 0,
        delivered_ms INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0)""")
    db.execute("INSERT OR IGNORE INTO meta VALUES ('started_ms',?)", (str(clock_ms()),))
    return db


def _dispatch(db: sqlite3.Connection, token: str, chat: str,
              candidates: list[tuple[str, str, str]]) -> int:
    successes = 0
    for event_id, wallet, message in candidates[:MAX_EVENTS_PER_TICK]:
        now = clock_ms()
        db.execute("INSERT OR IGNORE INTO notice(event_id,wallet) VALUES (?,?)",
                   (event_id, wallet))
        row = db.execute(
            "SELECT last_attempt_ms, delivered_ms FROM notice WHERE event_id=?",
            (event_id,)).fetchone()
        if not row or row[1] or now - row[0] < MIN_RETRY_MS:
            continue
        # Reserve attempt BEFORE calling Telegram. Do not pretend success if
        # the request fails; it will be retried at most once per 90 seconds.
        db.execute("UPDATE notice SET last_attempt_ms=?, attempts=attempts+1 WHERE event_id=?",
                   (now, event_id))
        if _api_call(token, "sendMessage", {"chat_id": chat, "text": message,
                                           "parse_mode": "HTML"}):
            db.execute("UPDATE notice SET delivered_ms=? WHERE event_id=?",
                       (clock_ms(), event_id))
            successes += 1
            print("PAPER_TELEGRAM_DELIVERED_" + wallet + "=True", flush=True)
        else:
            print("PAPER_TELEGRAM_RETRY_SCHEDULED_" + wallet + "=True", flush=True)
    return successes


def _scan(db: sqlite3.Connection, token: str, chat: str) -> int:
    since = int(db.execute("SELECT value FROM meta WHERE name='started_ms'").fetchone()[0])
    now = clock_ms()
    found = []
    for wallet, icon, path, _, _ in WALLETS:
        state = _json_file(path / "state_v2.json")
        found += _open_events(state, wallet=wallet, icon=icon, now_ms=now,
                              observer_started_ms=since)
        found += _close_events(path, wallet=wallet, icon=icon,
                               since_ms=since - 60_000, now_ms=now)
    # Stable ordering: open notices ahead of closes; one event ID at a time.
    uniq = {event_id: (event_id, wallet, msg) for event_id, wallet, msg in found}
    return _dispatch(db, token, chat, list(uniq.values()))


def main() -> None:
    parser = argparse.ArgumentParser()
    gate = parser.add_mutually_exclusive_group(required=True)
    gate.add_argument("--check", action="store_true")
    gate.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        fail("ROOT_REQUIRED")
    validate_wallets()
    token, chat = _credentials()
    if not _api_call(token, "getMe", None):
        fail("TELEGRAM_GETME_NOT_AUTHORIZED")
    if args.check:
        print("RC84_PAPER_TELEGRAM_BOT_API_AUTHENTICATED=PASS", flush=True)
        print("RC84_PAPER_TELEGRAM_WALLETS_VALID_NO_WRITES=PASS", flush=True)
        return
    db = _private_db()
    try:
        with LOCK_PATH.open("a+b") as lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            print("RC84_TELEGRAM_RELAY_RUNNING_PAPER_ONLY=True", flush=True)
            while True:
                try:
                    _scan(db, token, chat)
                except (OSError, ValueError, RuntimeError, sqlite3.Error):
                    # No provider secrets or messages in logs.
                    print("RC84_TELEGRAM_RELAY_TICK_DEGRADED=True", flush=True)
                time.sleep(POLL_SECONDS)
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("RC84_TELEGRAM_RELAY_REFUSED=guard_failed", flush=True)
        raise SystemExit(2)
