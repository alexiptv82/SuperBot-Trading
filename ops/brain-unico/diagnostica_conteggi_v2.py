#!/usr/bin/env python3
"""Analisi read-only conteggi Brain V2. Stampa solo aggregati, nessun ID o segreto."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import sys

from backend.v3.events import EventJournal
from backend.v3.dashboard import build_summary
from backend.v3.outcomes import extract_outcomes

RUN = Path("/opt/superbot-v3-paper-runs/brain-v3-brain-scalp-p1")
RUN_ID = "brain-scalp-paper-p1"
PORTFOLIO = "brain"


def metrics(journal: EventJournal):
    summary = build_summary(journal, PORTFOLIO, RUN_ID)
    report = extract_outcomes(journal, PORTFOLIO, RUN_ID)
    events = journal.list_run(PORTFOLIO, RUN_ID)
    kind = Counter(e.event.kind for e in events)
    skip = Counter(s.code for s in report.skipped)
    pnl_events = sum((Decimal(str(e.event.payload.get("realized_pnl", "0")))
                      for e in events if e.event.kind in ("paper_close", "paper_reduce")),
                     Decimal("0"))
    pnl_outcomes = sum((o.realized_pnl for o in report.outcomes), Decimal("0"))
    return {
        "events": len(events),
        "opens": kind["paper_open"],
        "adds": kind["paper_add"],
        "reduces": kind["paper_reduce"],
        "final_closes": kind["paper_close"],
        "summary_closes": len(summary.closed_trades),
        "valid_outcomes": len(report.outcomes),
        "skipped": dict(sorted(skip.items())),
        "open_positions": len(summary.open_positions),
        "report_open_ids": len(report.open_position_ids),
        "journal_pnl": str(pnl_events),
        "outcomes_pnl": str(pnl_outcomes),
    }


def main():
    source = RUN / "journal.db"
    if not source.is_file():
        print("CONTEGGI_ERRORE=JOURNAL_ASSENTE")
        return 2
    with TemporaryDirectory(prefix="brain-counts-", dir="/root") as tmp:
        dst = Path(tmp) / "snapshot.db"
        uri = source.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=20) as original:
            original.execute("PRAGMA query_only=ON")
            with sqlite3.connect(dst) as copy:
                original.backup(copy, pages=200, sleep=0.05)
        snap = EventJournal(dst)
        total, _ = snap.verify_chain()
        print("CONTEGGI_CATENA=OK")
        print(f"CONTEGGI_EVENTI_GLOBALI={total}")
        for key, value in metrics(snap).items():
            print(f"CONTEGGI_{key.upper()}={value}")
    live = EventJournal(source)
    for i in (1, 2):
        try:
            info = metrics(live)
            print(f'CONTEGGI_LIVE_{i}=eventi:{info["events"]},chiusure:{info["summary_closes"]},'
                  f'esiti:{info["valid_outcomes"]},scarti:{sum(info["skipped"].values())}')
        except Exception as exc:
            print(f"CONTEGGI_LIVE_{i}_ERRORE={type(exc).__name__}")
    print("CONTEGGI_FINE=OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"CONTEGGI_ERRORE={type(exc).__name__}")
        sys.exit(1)
