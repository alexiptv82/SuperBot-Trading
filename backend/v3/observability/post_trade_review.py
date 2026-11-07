"""RC79: deterministic, read-only post-trade review for normalized PAPER records.

This module never loads wallets, touches the network, writes journal entries, or
changes trading decisions. Caller supplies a VERIFIED run_id for every portfolio;
a source-specific adapter must normalize Brain events before use.

Partial closes are aggregated per (portfolio, run_id, symbol, id, open_ms).
An exit result is not evidence that a stop was crossed at any particular time.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping


class ReviewDataError(ValueError):
    """Input is ambiguous; refusing to produce an invented conclusion."""


def _number(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ReviewDataError("missing_or_invalid:" + field)
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ReviewDataError("missing_or_invalid:" + field) from None
    if not value.is_finite():
        raise ReviewDataError("missing_or_invalid:" + field)
    return value


def _opt_number(row: Mapping, key: str) -> Decimal | None:
    if row.get(key) is None:
        return None
    return _number(row[key], key)


def _identity(row: Mapping, portfolio: str, run_id: str) -> tuple:
    if not portfolio or not run_id or not isinstance(row, Mapping):
        raise ReviewDataError("portfolio_run_and_mapping_required")
    symbol = row.get("symbol")
    pid = row.get("id", row.get("position_id"))
    opened = row.get("open_ms")
    if not isinstance(symbol, str) or not symbol.strip() or pid is None or opened is None:
        raise ReviewDataError("missing_position_identity")
    if not isinstance(pid, (str, int)) or isinstance(pid, bool):
        raise ReviewDataError("invalid_position_id")
    return (portfolio, run_id, symbol.upper(), str(pid), int(_number(opened, "open_ms")))


def aggregate_fills(closes: Iterable[Mapping], *, portfolio: str, run_id: str) -> list[dict]:
    """Group *fills*, not lines, into logical positions without guessing run IDs.

    Only explicit `fill_id` can deduplicate entries. Identical-looking partial
    fills without such an ID are intentionally kept: they might be real.
    """
    groups: dict[tuple, dict] = {}
    seen_fill_ids: set[tuple] = set()
    for row in closes:
        key = _identity(row, portfolio, run_id)
        side = row.get("side")
        if side not in (1, -1) or isinstance(side, bool):
            raise ReviewDataError("side_must_be_long_or_short")
        close_ms = int(_number(row.get("close_ms"), "close_ms"))
        if close_ms < key[4]:
            raise ReviewDataError("close_before_open")
        fill_id = row.get("fill_id")
        if fill_id is not None:
            dedup_key = (key, str(fill_id))
            if dedup_key in seen_fill_ids:
                continue
            seen_fill_ids.add(dedup_key)
        net = _number(row.get("net"), "net")
        gross = _opt_number(row, "gross")
        fees = _opt_number(row, "fees")
        funding = _opt_number(row, "funding")
        margin = _opt_number(row, "margin")
        if key not in groups:
            groups[key] = {
                "portfolio": key[0], "run_id": key[1], "symbol": key[2],
                "id": key[3], "open_ms": key[4], "close_ms": close_ms,
                "side": side, "source": row.get("source"), "reason": row.get("reason"),
                "leverage": row.get("leverage"), "entry": row.get("entry"),
                "last_exit": row.get("exit"), "last_why": row.get("why"),
                "closed_by": row.get("closed_by"),
                "net": Decimal(0), "gross": Decimal(0), "fees": Decimal(0),
                "funding": Decimal(0), "margin": Decimal(0), "fills": 0,
                "unknown_financial_fields": set(), "partial_fills": 0,
                "data_quality_flags": set(),
            }
        g = groups[key]
        if g["side"] != side:
            raise ReviewDataError("inconsistent_position_records")
        # A DCA can change the recorded weighted entry for the same position.
        # Do not mistake it for a separate trade or pretend the later average
        # was the initial entry. Preserve ambiguity for downstream reviewers.
        if (g["entry"] is not None and row.get("entry") is not None
            and _number(g["entry"], "entry") != _number(row["entry"], "entry")):
            g["entry"] = None
            g["data_quality_flags"].add("entry_changed_across_fills")
        g["fills"] += 1
        g["net"] += net
        if row.get("partial") is True:
            g["partial_fills"] += 1
        for field, value in (("gross", gross), ("fees", fees), ("funding", funding), ("margin", margin)):
            if value is None:
                g["unknown_financial_fields"].add(field)
            else:
                g[field] += value
        if close_ms >= g["close_ms"]:
            g["close_ms"], g["last_exit"], g["last_why"] = close_ms, row.get("exit"), row.get("why")
            g["closed_by"] = row.get("closed_by", g["closed_by"])
    output = []
    for g in sorted(groups.values(), key=lambda x: (x["open_ms"], x["portfolio"], x["symbol"], x["id"])):
        unknown = g.pop("unknown_financial_fields")
        g["unknown_financial_fields"] = sorted(unknown)
        g["data_quality_flags"] = sorted(g["data_quality_flags"])
        for field in ("net", "gross", "fees", "funding", "margin"):
            g[field] = None if field in unknown else float(g[field])
        output.append(g)
    return output


def review_positions(positions: Iterable[Mapping], *,
                     entry_stop_evidence: Mapping[tuple, Mapping] | None = None,
                     monitoring_evidence: Mapping[tuple, Mapping] | None = None,
                     coeval_ms: int = 60_000) -> list[dict]:
    """Report factual anomalies; verdict remains insufficient unless proof is supplied.

    Evidence must have explicit `verified=True` + `source_ref` to be used.
    For full proof of a management failure, independently verified monitoring
    outage and independently verified stop crossing are both needed. Gap
    slippage remains a competing explanation and is not silently excluded.
    """
    positions = list(positions)
    out = []
    for g in positions:
        identity = (g["portfolio"], g["run_id"], g["symbol"], g["id"], g["open_ms"])
        flags: list[str] = []
        proof: list[str] = []
        if g["net"] is not None and g["margin"] and g["net"] < -g["margin"]:
            flags.append("net_loss_exceeds_reported_margin")
        peers = [p for p in positions if p is not g and p["symbol"] == g["symbol"]
                 and abs(p["open_ms"] - g["open_ms"]) <= coeval_ms
                 and p["side"] == g["side"] and p["portfolio"] != g["portfolio"]]
        if peers:
            flags.append("same_symbol_same_direction_cross_portfolio")
        stop = (entry_stop_evidence or {}).get(identity, {})
        monitor = (monitoring_evidence or {}).get(identity, {})
        good_stop = (stop.get("verified") is True and isinstance(stop.get("source_ref"), str)
                     and bool(stop["source_ref"]) and stop.get("initial_stop") is not None)
        if good_stop and g.get("last_exit") is not None and g.get("entry") is not None:
            sl = _number(stop["initial_stop"], "initial_stop")
            exit_price = _number(g["last_exit"], "last_exit")
            entry = _number(g["entry"], "entry")
            beyond = ((g["side"] == -1 and exit_price > sl > entry)
                      or (g["side"] == 1 and exit_price < sl < entry))
            if beyond:
                flags.append("exit_beyond_verified_initial_stop")
                proof.append(stop["source_ref"])
        elif not good_stop:
            flags.append("original_stop_not_verified")
        verified_monitor = monitor.get("verified") is True and bool(monitor.get("source_ref"))
        if verified_monitor and monitor.get("coverage") == "disabled":
            flags.append("monitoring_disabled_during_position")
            proof.append(monitor["source_ref"])
        verdict = "evidenza_insufficiente"
        # Even an offline monitor plus an adverse exit cannot prove the trade's
        # theoretical stop fill: need a trusted, timestamped path and gap audit.
        if (verified_monitor and monitor.get("coverage") == "disabled"
            and monitor.get("stop_crossing_verified") is True
            and monitor.get("continuous_price_path_verified") is True
            and "exit_beyond_verified_initial_stop" in flags):
            verdict = "problema_gestione"
            proof.append(monitor["source_ref"])
        out.append({
            "identity": identity, "net": g["net"], "fills": g["fills"],
            "loss_pct_of_reported_margin": round(g["net"] * 100 / g["margin"], 2)
                if g["net"] is not None and g["margin"] and g["margin"] > 0 else None,
            "flags": sorted(set(flags)), "peer_positions": [
                (p["portfolio"], p["run_id"], p["id"]) for p in peers],
            "verdict": verdict, "source_refs": sorted(set(proof)),
            "can_autolearn": False, "can_trade": False,
        })
    return out