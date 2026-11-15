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
                ts = int(row["open_time_ms"])
                o, h, l, c, v = (
                    Decimal(row[k]) for k in ("open", "high", "low", "close", "volume")
                )
                if (ts < 0 or not all(x.is_finite() for x in (o, h, l, c, v))
                        or min(o, h, l, c) <= 0 or v < 0
                        or not (l <= o <= h and l <= c <= h)):
                    raise ValueError("invalid_candle_row")
                result.append(Bar(ts, o, h, l, c, v))
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
            "WHERE portfolio_id='brain' AND run_id=? AND kind IN ('brain_decision','paper_open','paper_close') "
            "ORDER BY seq", (run_id,),
        ).fetchall()
        closes = {}
        decisions = {}
        opens = []
        for event_id, kind, when, body in rows:
            payload = json.loads(body)
            if type(payload) is not dict:
                raise ValueError("invalid_journal_payload")
            if kind == "brain_decision":
                decisions[event_id] = {
                    "ts_ms": when, "symbol": payload.get("symbol"),
                    "kind": payload.get("kind"), "status": payload.get("status"),
                    "regime": payload.get("regime"),
                }
                continue
            position_id = payload.get("position_id")
            if not isinstance(position_id, str) or not position_id:
                raise ValueError("missing_position_id")
            if kind == "paper_close":
                closes[position_id] = {
                    "close_ts_ms": when,
                    "realized_pnl_usdt": (
                        str(payload["realized_pnl"])
                        if payload.get("realized_pnl") is not None else None
                    ),
                    "close_reason": payload.get("reason"),
                }
            else:
                symbol = payload.get("symbol")
                side = payload.get("side")
                if (not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol)
                        or type(side) is not int or side not in (1, -1)
                        or type(when) is not int or when <= 0):
                    raise ValueError("invalid_paper_open")
                opens.append({
                    "decision_event_id": payload.get("decision_event_id"),
                    "open_event_id": event_id,
                    "position_id": position_id,
                    "symbol": symbol,
                    "side": side,
                    "as_of_ms": when,
                    "regime": "UNKNOWN",  # real paper_open has no regime: join decision
                })
        conn.rollback()  # conclude the read transaction; no write is possible
    finally:
        conn.close()
    for entry in opens:
        link = entry["decision_event_id"]
        linked = decisions.get(link) if type(link) is str and link else None
        if (linked is not None and linked["symbol"] == entry["symbol"]
                and linked["kind"] == "OPEN" and linked["status"] == "APPROVED"
                and type(linked["ts_ms"]) is int
                and 0 < linked["ts_ms"] <= entry["as_of_ms"]):
            entry["decision_link"] = "verified"
            entry["decision_ts_ms"] = linked["ts_ms"]
            r = linked["regime"]
            entry["regime"] = r if type(r) is str and r in _REGIMES else "UNKNOWN"
        else:
            entry["decision_link"] = "missing_or_inconsistent" if link else "unlinked"
            entry["decision_ts_ms"] = None
        close = closes.get(entry["position_id"])
        entry["outcome_after_entry"] = (
            close if close is not None and type(close["close_ts_ms"]) is int
            and close["close_ts_ms"] >= entry["as_of_ms"] else None
        )
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
        # A linked Brain decision precedes execution and is the correct
        # conservative "what could the model have known?" timestamp.
        # A missing link falls back to open time, explicitly labelled.
        signal_ts = (
            row["decision_ts_ms"] if row["decision_link"] == "verified"
            else row["as_of_ms"]
        )
        # Outcome is intentionally withheld from the observer.
        observation = observe(
            m15, h1, bars_4h=h4, as_of_ms=signal_ts,
            regime=row["regime"],
        ).as_dict()
        if error is not None:
            observation["reason"] = "offline_" + error
        out.append({
            **row,
            "signal_ts_ms": signal_ts,
            "observation_time_basis": (
                "linked_brain_decision" if row["decision_link"] == "verified"
                else "paper_open_fallback"
            ),
            "frrd": observation,
        })
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
