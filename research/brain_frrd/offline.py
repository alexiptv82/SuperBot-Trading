"""Read-only, offline FRRD research runner for actual Brain PAPER opens.

Input: exact historical Bitget CSV candles per symbol and SQLite journal
(read-only mode). Outputs a NEW JSONL research file outside the run folder.
No network, no model calls, no bot imports, no trading actions.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import json
from pathlib import Path
import re
import sqlite3

from backend.v3.features.indicators import Bar
from research.brain_frrd.detector import observe

_BAR_HEADER = ("open_time_ms", "open", "high", "low", "close", "volume")
_SYMBOL = re.compile(r"[A-Z0-9]{3,30}\Z")
_REGIMES = {"UNKNOWN", "EXPANSION", "TREND_DOWN", "TREND_UP", "RANGE", "SHOCK", "UNCERTAIN"}


def read_bars(path: Path) -> list[Bar]:
    """Use the exact CSV columns emitted by backend.v3.lab_tools.fetch_candles."""
    if not path.is_file():
        raise ValueError("missing_candle_file")
    result = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != _BAR_HEADER:
                raise ValueError("invalid_candle_header")
            for row in reader:
                if set(row) != set(_BAR_HEADER) or any(row[k] is None for k in _BAR_HEADER):
                    raise ValueError("invalid_candle_row")
                result.append(Bar(
                    int(row["open_time_ms"]), Decimal(row["open"]),
                    Decimal(row["high"]), Decimal(row["low"]),
                    Decimal(row["close"]), Decimal(row["volume"]),
                ))
    except (OSError, ArithmeticError, ValueError, KeyError) as exc:
        raise ValueError("invalid_candle_file") from exc
    return result


def read_brain_opens(journal_path: Path, run_id: str) -> list[dict]:
    """Read one consistent journal snapshot in SQLite mode=ro, never write."""
    if not journal_path.is_file() or not isinstance(run_id, str) or not run_id:
        raise ValueError("invalid_journal_or_run")
    conn = sqlite3.connect(journal_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT event_id, kind, occurred_at_ms, payload_json FROM v3_events "
            "WHERE portfolio_id='brain' AND run_id=? AND kind IN ('paper_open','paper_close') "
            "ORDER BY seq", (run_id,),
        ).fetchall()
        closes = {}
        opens = []
        for event_id, kind, when, body in rows:
            payload = json.loads(body)
            if type(payload) is not dict:
                raise ValueError("invalid_journal_payload")
            position_id = payload.get("position_id")
            if not isinstance(position_id, str) or not position_id:
                raise ValueError("missing_position_id")
            if kind == "paper_close":
                closes[position_id] = {
                    "close_ts_ms": when,
                    "realized_pnl_usdt": str(payload.get("realized_pnl")),
                    "close_reason": payload.get("reason"),
                }
            else:
                symbol = payload.get("symbol")
                side = payload.get("side")
                if (not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol)
                        or side not in (1, -1) or type(when) is not int or when <= 0):
                    raise ValueError("invalid_paper_open")
                opens.append({
                    "decision_event_id": payload.get("decision_event_id"),
                    "open_event_id": event_id,
                    "position_id": position_id,
                    "symbol": symbol,
                    "side": side,
                    "as_of_ms": when,
                    "regime": payload.get("regime")
                    if payload.get("regime") in _REGIMES else "UNKNOWN",
                })
        conn.rollback()  # conclude the read transaction; no write is possible
    finally:
        conn.close()
    for entry in opens:
        entry["outcome_after_entry"] = closes.get(entry["position_id"])
    return opens


def analyze(journal: Path, run_id: str, candles_dir: Path) -> list[dict]:
    """Generate research observations; PnL is attached *after* signal evaluation."""
    opens = read_brain_opens(journal, run_id)
    cached = {}
    out = []
    for row in opens:
        symbol = row["symbol"]
        if symbol not in cached:
            folder = candles_dir / symbol
            try:
                b15 = read_bars(folder / "15m.csv")
                b1h = read_bars(folder / "1h.csv")
                p4 = folder / "4h.csv"
                b4h = read_bars(p4) if p4.is_file() else None
                cached[symbol] = (b15, b1h, b4h, None)
            except ValueError as exc:
                cached[symbol] = (None, None, None, str(exc))
        m15, h1, h4, error = cached[symbol]
        # Outcome is intentionally withheld from the observer.
        observation = observe(
            m15, h1, bars_4h=h4, as_of_ms=row["as_of_ms"],
            regime=row["regime"],
        ).as_dict()
        if error is not None:
            observation["reason"] = "offline_" + error
        out.append({**row, "frrd": observation})
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="FRRD PAPER journal study, offline and read-only")
    ap.add_argument("--journal", type=Path, required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--candles-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    journal = args.journal.resolve(strict=True)
    candles = args.candles_dir.resolve(strict=True)
    target = args.out.resolve()
    # Never produce artefacts inside either source directory/run.
    if target == journal or journal.parent in target.parents or (
        target == candles or candles in target.parents
    ):
        ap.error("output_must_be_outside_journal_and_candles_directories")
    records = analyze(journal, args.run_id, candles)
    # Exclusive creation prevents accidental overwrite.
    with target.open("x", encoding="utf-8") as handle:
        for r in records:
            handle.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {}
    for r in records:
        state = r["frrd"]["state"]
        summary[state] = summary.get(state, 0) + 1
    print(json.dumps({
        "version": "brain_frrd_shadow_v1", "open_events": len(records),
        "states": summary, "journal_modified": False, "orders_sent": 0,
        "output": str(target),
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
