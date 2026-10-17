"""Read-only adapter for saved Hawk/Bull PAPER state.

This module never imports desk.cli, never opens network connections and never
writes files. The caller must supply an independently copied state_v2.json.
A saved last_price is NOT a live mark or a historical tick.
"""
import json
import math
from pathlib import Path

try:
    from .profit_manager_replay import Snapshot
except ImportError:
    from profit_manager_replay import Snapshot


def snapshots_from_state(state, *, bot, max_price_age_ms=120000):
    if bot not in ("hawk", "bull"):
        raise ValueError("Bot must be hawk or bull")
    if not isinstance(state, dict):
        raise ValueError("Expected state object")
    main = state.get("main")
    if not isinstance(main, dict) or not isinstance(main.get("positions"), dict):
        raise ValueError("Missing paper account positions")
    prices = state.get("last_prices") or {}
    price_ts = state.get("last_prices_ms")
    if not isinstance(prices, dict) or not isinstance(price_ts, int) or price_ts <= 0:
        raise ValueError("Missing timestamped observed prices")
    results, exclusions = [], []
    for symbol, p in main["positions"].items():
        label = str(symbol)
        if not isinstance(p, dict):
            exclusions.append({"symbol": label, "reason": "invalid_position"})
            continue
        try:
            if p.get("symbol") != symbol:
                raise ValueError("symbol_mismatch")
            # Partial exits cannot be reconstructed from a single state snapshot.
            # DCA and split legs change cost basis: reject until ledger verified.
            if p.get("dca_count", 0) or p.get("dca_levels") or p.get("legs", 1) != 1:
                raise ValueError("multi_leg_or_dca")
            if p.get("pending_split") is not None:
                raise ValueError("pending_split")
            mark = float(prices[symbol])
            ts = int(price_ts)
            opened = int(p["open_ms"])
            if ts < opened or ts - opened < 0:
                raise ValueError("timestamp_before_open")
            # Freshness relative to the state file must be checked by the
            # collection process; this parameter only enforces a valid bound.
            if max_price_age_ms <= 0:
                raise ValueError("invalid_freshness_limit")
            entry, qty, margin = float(p["entry"]), float(p["qty"]), float(p["total_margin"])
            if not all(math.isfinite(v) and v > 0 for v in (mark, entry, qty, margin)):
                raise ValueError("invalid_price_or_position")
            fee = float(p.get("fee_open", 0))
            if not math.isfinite(fee) or fee < 0:
                raise ValueError("invalid_open_fee")
            results.append(Snapshot(
                trade_id=f"{bot}:paper:{p['id']}:{opened}:{symbol}",
                timestamp_ms=ts, open_ms=opened, side=int(p["side"]),
                entry=entry, mark=mark, qty=qty, allocated_margin=margin,
                open_fee_usdt=fee,
            ))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            exclusions.append({"symbol": label, "reason": str(exc)})
    return results, exclusions


def read_state_file(path, *, bot):
    with Path(path).open("r", encoding="utf-8") as stream:
        state = json.load(stream)
    return snapshots_from_state(state, bot=bot)
