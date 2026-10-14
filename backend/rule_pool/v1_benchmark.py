"""Termine di paragone: i trade chiusi del bot attuale (V1), letti in SOLA LETTURA.

Il file del database del bot viene COPIATO in una cartella temporanea (con -wal/-shm se ci sono)
e la copia viene letta: il database originale non viene mai aperto in scrittura ne' bloccato.
Il rendimento e' netto sul nozionale (pnl / (prezzo ingresso * quantita)), in bp, cosi' e'
confrontabile con le regole del pool. Solo informativo: non entra nelle decisioni.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from typing import Optional

import numpy as np

from rule_pool import evidence as ev

DEFAULT_PATH = "/app/botdata/superbot.db"


def read_v1(path: str) -> Optional[tuple]:
    """(t_ms_chiusura, net_bp) dei trade chiusi, o None se il file non c'e' / non e' leggibile."""
    if not path or not os.path.exists(path):
        return None
    try:
        with tempfile.TemporaryDirectory() as d:
            dst = os.path.join(d, "copy.db")
            for suf in ("", "-wal", "-shm"):
                if os.path.exists(path + suf):
                    shutil.copyfile(path + suf, dst + suf)
            con = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
            try:
                rows = con.execute(
                    "SELECT entry_price, quantity, pnl, strftime('%s', close_time) FROM trades "
                    "WHERE status = 'closed' AND pnl IS NOT NULL AND close_time IS NOT NULL "
                    "AND entry_price > 0 AND quantity > 0 ORDER BY close_time").fetchall()
            finally:
                con.close()
    except Exception:  # noqa: BLE001
        return None
    if not rows:
        return np.empty(0), np.empty(0)
    t = np.array([int(r[3]) * 1000 for r in rows], dtype=float)
    x = np.array([r[2] / (r[0] * r[1]) * 1e4 for r in rows], dtype=float)
    return t, x


def line(path: str) -> str:
    """Riga di riepilogo per il report."""
    got = read_v1(path)
    if got is None:
        return "- V1 (bot attuale, solo confronto): database non leggibile da qui"
    t, x = got
    s = ev.summarize(t, x)
    if s is None:
        return f"- V1 (bot attuale, solo confronto): {len(x)} trade chiusi, troppo pochi"
    tg = f"{s.t_gate:+.2f}" if s.t_gate == s.t_gate else "n/d"
    return (f"- V1 (bot attuale, solo confronto): {s.n} trade chiusi, netto {s.mean:+.1f} bp "
            f"[{s.ci_low:+.0f},{s.ci_high:+.0f}], t={tg}")
