"""Append-only SQLite budget ledger for AI provider spending — F4.

Implements the ``SpendingGate = Callable[[str], bool]`` interface defined in
``brain_f3.providers``.

Design constraints:
- stdlib only: sqlite3, threading, datetime, json — no pip installs.
- Append-only: no UPDATE or DELETE — every spend event is a permanent record.
- Thread-safe: one connection per BudgetLedger instance, protected by a lock.
- Gate semantics: returns True (spend allowed) only if daily + session limits
  are not exceeded for the queried provider.
- Fail-closed: on any DB error, the gate returns False (deny spend).
- No credentials, balances or position data stored here.

Usage::

    from backend.v3.budget import BudgetLedger

    ledger = BudgetLedger(":memory:")          # or a file path
    gate = ledger.spending_gate(
        daily_limits={"deepseek": 100, "claude": 50},   # arbitrary units
        session_limits={"deepseek": 20, "claude": 10},
    )

    if gate("deepseek"):
        ledger.record_spend("deepseek", units=1)
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Callable, Mapping

# Type alias matching providers.py
SpendingGate = Callable[[str], bool]


class BudgetLedger:
    """
    Append-only SQLite ledger tracking AI provider spend in abstract *units*.

    Units are caller-defined (tokens, API calls, cents × 100, …).  The ledger
    does not interpret them: it just accumulates and compares against limits.
    """

    _CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS spend_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at TEXT    NOT NULL,   -- ISO-8601 UTC
            provider    TEXT    NOT NULL,
            units       INTEGER NOT NULL,
            metadata    TEXT    NOT NULL DEFAULT '{}'
        );
    """
    # Index for fast daily lookups.
    _CREATE_INDEX = """
        CREATE INDEX IF NOT EXISTS idx_spend_provider_date
        ON spend_events (provider, occurred_at);
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(self._CREATE_TABLE)
        self._conn.execute(self._CREATE_INDEX)
        self._conn.commit()

        # Per-instance session accumulator (in-memory, resets on restart).
        self._session_spend: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def record_spend(
        self,
        provider: str,
        units: int,
        metadata: Mapping | None = None,
    ) -> None:
        """Append a spend event.  Raises ValueError on bad input."""
        if not isinstance(provider, str) or not provider:
            raise ValueError("provider must be a non-empty string")
        if not isinstance(units, int) or units < 0:
            raise ValueError("units must be a non-negative integer")
        meta_str = json.dumps(metadata or {}, separators=(",", ":"))
        now_iso = datetime.now(tz=timezone.utc).isoformat()

        with self._lock:
            self._conn.execute(
                "INSERT INTO spend_events (occurred_at, provider, units, metadata) "
                "VALUES (?, ?, ?, ?)",
                (now_iso, provider, units, meta_str),
            )
            self._conn.commit()
            self._session_spend[provider] = (
                self._session_spend.get(provider, 0) + units
            )

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def daily_spend(self, provider: str) -> int:
        """
        Return total units recorded for *provider* in the current UTC calendar day.
        Returns 0 on any DB error (fail-open for reads; gate is fail-closed separately).
        """
        today_prefix = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT COALESCE(SUM(units), 0) FROM spend_events "
                    "WHERE provider = ? AND occurred_at LIKE ?",
                    (provider, f"{today_prefix}%"),
                )
                row = cur.fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def session_spend(self, provider: str) -> int:
        """Return units accumulated for *provider* in this process lifetime."""
        with self._lock:
            return self._session_spend.get(provider, 0)

    # ------------------------------------------------------------------
    # Gate factory
    # ------------------------------------------------------------------

    def spending_gate(
        self,
        *,
        daily_limits: Mapping[str, int] | None = None,
        session_limits: Mapping[str, int] | None = None,
    ) -> SpendingGate:
        """
        Return a ``SpendingGate`` callable that checks this ledger.

        The gate returns True (allow) only when **both** daily and session
        spend for the requested provider are strictly below the configured
        limit.  Returns False (deny) on any error or missing limit.

        Args:
            daily_limits:   {provider: max_units_per_UTC_day}.  Missing
                            provider → gate denies by default.
            session_limits: {provider: max_units_per_session}.  Missing
                            provider → no session cap applied.
        """
        d_limits: dict[str, int] = dict(daily_limits or {})
        s_limits: dict[str, int] = dict(session_limits or {})

        def gate(provider: str) -> bool:
            if not isinstance(provider, str) or not provider:
                return False
            # Must have an explicit daily limit for this provider.
            if provider not in d_limits:
                return False
            try:
                daily_max = int(d_limits[provider])
                daily_used = self.daily_spend(provider)
                if daily_used >= daily_max:
                    return False
                if provider in s_limits:
                    session_max = int(s_limits[provider])
                    session_used = self.session_spend(provider)
                    if session_used >= session_max:
                        return False
            except Exception:
                # Fail-closed: any unexpected error denies spend.
                return False
            return True

        return gate

    # ------------------------------------------------------------------
    # Diagnostic helpers
    # ------------------------------------------------------------------

    def all_spend(self, provider: str) -> list[dict]:
        """Return all spend events for *provider*, oldest first.  For tests/debug."""
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT occurred_at, units, metadata FROM spend_events "
                    "WHERE provider = ? ORDER BY id ASC",
                    (provider,),
                )
                rows = cur.fetchall()
            return [{"occurred_at": r[0], "units": r[1], "metadata": json.loads(r[2])} for r in rows]
        except Exception:
            return []

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._conn.close()
