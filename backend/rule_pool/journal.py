"""Giornale del pool: SQLite SEPARATO dal database del bot (file proprio).

Un trade chiuso e' immutabile: se un nuovo calcolo lo contraddice si solleva
ImmutableTradeError (segnala un errore nel sistema, non va ignorato).
"""
from __future__ import annotations

import sqlite3
import time
from typing import Optional

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
    rule_id TEXT NOT NULL, version INTEGER NOT NULL, params_hash TEXT NOT NULL,
    kind TEXT NOT NULL, created_ms INTEGER NOT NULL,
    PRIMARY KEY (rule_id, version)
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id TEXT NOT NULL, version INTEGER NOT NULL, venue TEXT NOT NULL,
    symbol TEXT NOT NULL, side INTEGER NOT NULL, entry_t INTEGER NOT NULL, exit_t INTEGER,
    entry_px REAL NOT NULL, exit_px REAL, why TEXT, hold_h REAL,
    gross_bp REAL, cost_bp REAL, funding_bp REAL, net_bp REAL, mae_bp REAL, mfe_bp REAL,
    status TEXT NOT NULL,
    UNIQUE (rule_id, version, venue, symbol, entry_t)
);
CREATE INDEX IF NOT EXISTS ix_trades_rule ON trades (rule_id, version, venue, status);
CREATE TABLE IF NOT EXISTS rule_state (
    rule_id TEXT NOT NULL, version INTEGER NOT NULL, state TEXT NOT NULL,
    since_ms INTEGER NOT NULL, reasons TEXT,
    PRIMARY KEY (rule_id, version)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts_ms INTEGER NOT NULL,
    rule_id TEXT, event TEXT NOT NULL, detail TEXT
);
"""

_FIELDS = ("entry_px", "exit_t", "exit_px", "why", "hold_h", "gross_bp", "cost_bp", "funding_bp",
           "net_bp", "mae_bp", "mfe_bp", "status")


class ImmutableTradeError(RuntimeError):
    pass


class ParamsChangedError(RuntimeError):
    pass


def _same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is b
        return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(a)))
    return a == b


class Journal:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ---- regole
    def register_rule(self, rule) -> None:
        """Registra la regola; rifiuta lo stesso id/versione con parametri diversi."""
        h = rule.params_hash()
        row = self.db.execute("SELECT params_hash FROM rules WHERE rule_id=? AND version=?",
                              (rule.rule_id, rule.version)).fetchone()
        if row is None:
            self.db.execute("INSERT INTO rules VALUES (?,?,?,?,?)",
                            (rule.rule_id, rule.version, h, rule.kind, int(time.time() * 1000)))
            self.db.commit()
        elif row["params_hash"] != h:
            raise ParamsChangedError(
                f"{rule.rule_id} v{rule.version}: parametri cambiati senza alzare la versione")

    # ---- trade
    def upsert_trade(self, t: dict) -> str:
        """Inserisce o aggiorna un trade. Ritorna 'inserted' | 'updated' | 'unchanged'."""
        key = (t["rule_id"], t["version"], t["venue"], t["symbol"], t["entry_t"])
        row = self.db.execute(
            "SELECT * FROM trades WHERE rule_id=? AND version=? AND venue=? AND symbol=? AND entry_t=?",
            key).fetchone()
        vals = [t.get(f) for f in _FIELDS]
        if row is None:
            self.db.execute(
                "INSERT INTO trades (rule_id,version,venue,symbol,side,entry_t,%s) VALUES (?,?,?,?,?,?,%s)"
                % (",".join(_FIELDS), ",".join("?" * len(_FIELDS))),
                (*key[:4], t["side"], t["entry_t"], *vals))
            self.db.commit()
            return "inserted"
        if row["side"] != t["side"]:
            raise ImmutableTradeError(f"lato diverso per {key}")
        if row["status"] == "closed":
            for f, v in zip(_FIELDS, vals):
                if not _same(row[f], v):
                    raise ImmutableTradeError(f"trade chiuso modificato ({f}): {key}")
            return "unchanged"
        self.db.execute(
            "UPDATE trades SET %s WHERE id=?" % ",".join(f"{f}=?" for f in _FIELDS), (*vals, row["id"]))
        self.db.commit()
        return "updated"

    def closed_arrays(self, rule_id: str, version: int, venue: str):
        """(tempi_ingresso, netto_bp) dei trade chiusi, in ordine cronologico."""
        rows = self.db.execute(
            "SELECT entry_t, net_bp FROM trades WHERE rule_id=? AND version=? AND venue=? "
            "AND status='closed' ORDER BY entry_t, id", (rule_id, version, venue)).fetchall()
        return (np.array([r["entry_t"] for r in rows], dtype=np.int64),
                np.array([r["net_bp"] for r in rows], dtype=float))

    def all_trades(self, rule_id: str, version: int, venue: str) -> list:
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM trades WHERE rule_id=? AND version=? AND venue=? ORDER BY entry_t, id",
            (rule_id, version, venue)).fetchall()]

    # ---- stati
    def set_state(self, rule_id: str, version: int, state: str, reasons: Optional[list] = None) -> bool:
        """Salva lo stato; ritorna True se e' cambiato (e registra un evento)."""
        cur = self.get_state(rule_id, version)
        if cur == state:
            return False
        now = int(time.time() * 1000)
        self.db.execute("INSERT OR REPLACE INTO rule_state VALUES (?,?,?,?,?)",
                        (rule_id, version, state, now, "; ".join(reasons or [])))
        self.db.execute("INSERT INTO events (ts_ms, rule_id, event, detail) VALUES (?,?,?,?)",
                        (now, rule_id, "state", f"{cur} -> {state}: {'; '.join(reasons or [])}"))
        self.db.commit()
        return True

    def get_state(self, rule_id: str, version: int) -> Optional[str]:
        row = self.db.execute("SELECT state FROM rule_state WHERE rule_id=? AND version=?",
                              (rule_id, version)).fetchone()
        return row["state"] if row else None

    def events(self) -> list:
        return [dict(r) for r in self.db.execute("SELECT * FROM events ORDER BY id").fetchall()]
