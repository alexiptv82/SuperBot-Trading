"""Brain V3 PAPER: per-asset closed-trade diagnostics from read-only journal.

Research only: NO live bot hooks, no exchange requests, no symbols disabled.
Each trade is linked to its originating brain_decision by event ID when possible.
PnL includes fees already: never subtract reported fees twice.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3

NIL = Decimal("0")


def _dec(payload: dict, key: str) -> Decimal:
    value = payload.get(key)
    if type(value) not in (str, int):
        raise ValueError("invalid_numeric_field_" + key)
    try:
        x = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid_numeric_field_" + key) from exc
    if not x.is_finite():
        raise ValueError("invalid_numeric_field_" + key)
    return x


def _snapshot(path: Path, run_id: str) -> tuple[list[dict], list[dict]]:
    if not path.is_file() or not run_id:
        raise ValueError("missing_journal_or_run_id")
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        rows = con.execute(
            "SELECT event_id,kind,occurred_at_ms,payload_json FROM v3_events "
            "WHERE portfolio_id='brain' AND run_id=? "
            "AND kind IN ('brain_decision','paper_open','paper_close') ORDER BY seq",
            (run_id,),
        ).fetchall()
        con.rollback()
    finally:
        con.close()

    decisions: dict[str, dict] = {}
    opens: dict[str, dict] = {}
    closes: list[dict] = []
    for event_id, kind, ts, raw in rows:
        p = json.loads(raw)
        if type(p) is not dict or type(ts) is not int:
            raise ValueError("invalid_journal_event")
        if kind == "brain_decision":
            decisions[event_id] = p
        elif kind == "paper_open":
            position = p.get("position_id")
            if type(position) is not str or not position or position in opens:
                raise ValueError("invalid_open_event")
            opens[position] = {"ts": ts, "event": p}
        else:
            closes.append({"ts": ts, "event": p})

    finished: list[dict] = []
    closed_ids = set()
    for item in closes:
        c = item["event"]
        pid = c.get("position_id")
        if type(pid) is not str or pid not in opens or pid in closed_ids:
            raise ValueError("invalid_close_link")
        closed_ids.add(pid)
        op = opens[pid]["event"]
        if item["ts"] < opens[pid]["ts"]:
            raise ValueError("close_before_open")
        if (c.get("symbol") != op.get("symbol")
                or c.get("side") != op.get("side")):
            raise ValueError("inconsistent_symbol_or_side")
        if type(c.get("side")) is not int or c["side"] not in (-1, 1):
            raise ValueError("invalid_side")
        link = op.get("decision_event_id", "")
        d = decisions.get(link, {}) if type(link) is str and link else {}
        linked = bool(
            d.get("symbol") == op.get("symbol")
            and d.get("kind") == "OPEN"
            and d.get("status") == "APPROVED"
        )
        entry = _dec(op, "fill_price")
        stop = _dec(op, "stop_price")
        qty = _dec(op, "quantity")
        if entry <= 0 or stop <= 0 or qty <= 0 or entry == stop:
            raise ValueError("invalid_entry_risk")
        pnl = _dec(c, "realized_pnl")
        fees = _dec(c, "fees")
        if fees < 0:
            raise ValueError("invalid_fees")
        risk_usdt = abs(entry - stop) * qty
        finished.append({
            "symbol": op["symbol"], "side": c["side"],
            "position_id": pid, "open_ts_ms": opens[pid]["ts"],
            "close_ts_ms": item["ts"], "pnl": pnl, "fees": fees,
            "risk_usdt": risk_usdt,
            "net_r": pnl / risk_usdt,
            "stop_gap_pct": abs(entry - stop) / entry * Decimal(100),
            "reason": c.get("reason"),
            "regime": d.get("regime", "UNKNOWN") if linked else "UNKNOWN",
            "decision_link_verified": linked,
        })
    pending = [
        {"symbol": p["event"].get("symbol"), "position_id": pid}
        for pid, p in opens.items() if pid not in closed_ids
    ]
    return finished, pending


def _summary(trades: list[dict]) -> dict:
    winners = [t for t in trades if t["pnl"] > 0]
    losers = [t for t in trades if t["pnl"] < 0]
    total = sum((t["pnl"] for t in trades), NIL)
    fees = sum((t["fees"] for t in trades), NIL)
    gross_wins = sum((t["pnl"] for t in winners), NIL)
    gross_losses = -sum((t["pnl"] for t in losers), NIL)
    risk_total = sum((t["risk_usdt"] for t in trades), NIL)
    n = len(trades)
    return {
        "closed": n,
        "wins": len(winners),
        "losses": len(losers),
        "win_rate_pct": round(100 * len(winners) / n, 2) if n else None,
        "net_usdt": str(total.quantize(Decimal("0.01"))),
        "fees_usdt_included_in_net": str(fees.quantize(Decimal("0.01"))),
        "net_r_mean": str(
            (sum((t["net_r"] for t in trades), NIL) / n).quantize(Decimal("0.001"))
        ) if n else None,
        "risk_weighted_net_r": str((total / risk_total).quantize(Decimal("0.001")))
        if risk_total else None,
        "stop_gap_pct_median": str(
            sorted(t["stop_gap_pct"] for t in trades)[n // 2].quantize(Decimal("0.001"))
        ) if n % 2 else str(
            ((sorted(t["stop_gap_pct"] for t in trades)[n // 2 - 1]
              + sorted(t["stop_gap_pct"] for t in trades)[n // 2]) / 2)
            .quantize(Decimal("0.001"))
        ) if n else None,
        "profit_factor": str((gross_wins / gross_losses).quantize(Decimal("0.001")))
        if gross_losses else ("infinite" if gross_wins else None),
        "stop_closes": sum(t["reason"] == "stop" for t in trades),
        "take_profit_closes": sum(t["reason"] == "take_profit" for t in trades),
        "verified_decision_links": sum(t["decision_link_verified"] for t in trades),
        "sample_status": "TOO_SMALL_TO_EXCLUDE" if n < 20 else "REVIEW_WITH_VALIDATION",
    }


def build_report(journal: Path, run_id: str) -> dict:
    trades, pending = _snapshot(journal, run_id)
    buckets: dict[str, list] = defaultdict(list)
    by_regime: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    by_side: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for trade in trades:
        sym = trade["symbol"]
        buckets[sym].append(trade)
        by_regime[sym][trade["regime"]].append(trade)
        by_side[sym]["SHORT" if trade["side"] == -1 else "LONG"].append(trade)
    return {
        "schema": "brain_symbol_risk_research_v1", "run_id": run_id,
        "mode": "PAPER_READ_ONLY", "orders_sent": 0, "symbols_excluded": [],
        "closed_total": len(trades), "open_total": len(pending),
        "overall": _summary(trades),
        "symbols": {
            symbol: {
                "overall": _summary(rows),
                "by_regime": {k: _summary(v) for k, v in sorted(by_regime[symbol].items())},
                "by_side": {k: _summary(v) for k, v in sorted(by_side[symbol].items())},
                "open_positions": sum(p.get("symbol") == symbol for p in pending),
            }
            for symbol, rows in sorted(buckets.items())
        },
        "note": (
            "Fees are included in realized PnL; small samples cannot justify exclusions. "
            "Check regime, stop distance relative to ATR, timing, and fresh holdout outcomes."
        ),
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Read-only Brain PAPER asset research")
    ap.add_argument("--journal", type=Path, required=True)
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args(argv)
    print(json.dumps(build_report(args.journal, args.run_id),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
