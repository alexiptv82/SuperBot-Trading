"""PAPER vault only: no percentage sizing, reinvestment or risk policy.

Pure transitions. CLI persists whole snapshots with its single-writer journal.
Balances come from account cash/margin, already including recorded trading costs.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from .capital_manager import CapitalInvariantError, dec, cents
from .capital_runtime import account_components, boundary_prices
from .vault_manager import VaultState, rollover, settle_pending

POLICY = "salvadanaio-only-v1"
TARGET = Decimal("1000")
DAY_MS = 86_400_000


def utc_day(now_ms):
    return datetime.fromtimestamp(now_ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def activate(state, now_ms):
    """Add policy metadata, never synthesize past profit or reset an account."""
    cap = state.get("capital")
    if cap and cap.get("policy") == POLICY:
        VaultState.from_dict(cap["vault"])
        return False
    if cap and cap.get("schema_version") != 1:
        raise CapitalInvariantError("unsupported prior capital state")
    cap = deepcopy(cap or {})
    vault = VaultState.from_dict(cap.get("vault") or {})
    cash = dec(state["main"]["cash"])
    if cash < 0:
        raise CapitalInvariantError("negative account cash")
    # Keep every old capital key, vault lot, receipt, trade and position.
    cap.update(schema_version=1, policy=POLICY, status="READY",
               revision=cap.get("revision", 0), vault=vault.to_dict(),
               day={"utc_day": utc_day(now_ms)},
               activated_ms=now_ms, deposits=cap.get("deposits", []))
    cap["valuation"] = {"fresh": False, "unrealized": "0"}
    state["capital"] = cap
    return True


def _record(cap, now_ms, source_day, amount, kind, net_realized=None):
    cap.setdefault("deposits", []).append({
        "utc_day": utc_day(now_ms), "source_day": source_day,
        "ts_ms": now_ms, "kind": kind, "amount": str(cents(amount)),
        "balance_after": str(cap["vault"]["balance"]),
        "net_realized": str(cents(net_realized)) if net_realized is not None else None,
    })


def rollover_today(state, now_ms, candles, **_unused):
    cap = state["capital"]
    if cap.get("policy") != POLICY:
        raise CapitalInvariantError("vault policy missing")
    today = utc_day(now_ms)
    old_day = cap["day"]["utc_day"]
    if old_day == today and cap.get("status") == "READY":
        return False
    old = datetime.strptime(old_day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    new = datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if new - old != timedelta(days=1):
        cap["status"] = "RECONCILIATION_REQUIRED"
        return True
    boundary_ms = int(new.timestamp() * 1000)
    acc = state["main"]
    positions = acc.get("positions") or {}
    signature = sorted([s, p.get("id"), str(p.get("qty")), str(p.get("entry")),
                        str(p.get("total_margin"))] for s, p in positions.items())
    previous = cap.get("boundary_pending_signature")
    if previous is not None and previous != signature:
        cap["status"] = "RECONCILIATION_REQUIRED"
        return True
    try:
        px = boundary_prices(candles, positions, boundary_ms)
        cash, margin, unrealized, equity = account_components(acc, px)
        reserved = sum((dec((p.get("pending_split") or {}).get("margin", 0)) *
                        (1 + dec(p.get("leverage", 1)) * dec((acc.get("limits") or {}).get("fee_bp_side", 6)) / 10000)
                        for p in positions.values()), Decimal(0))
        transfer = rollover(VaultState.from_dict(cap["vault"]), utc_day=today,
                            equity=equity, cash=cash, committed_margin=margin,
                            unrealized=unrealized, reserved_cash=reserved,
                            excluded_external_funds=cap.get("excluded_external_funds", 0))
    except (CapitalInvariantError, KeyError, TypeError, ValueError):
        cap.setdefault("boundary_pending_signature", signature)
        cap["status"] = "ROLLOVER_PENDING"
        return True
    acc["cash"] = float(cash + transfer.cash_delta)
    # A transfer is not a trading loss. Daily 12% stop stays in the engine.
    acc["day"] = today
    acc["day_start_equity"] = float(equity + transfer.cash_delta)
    cap["vault"] = transfer.state.to_dict()
    cap["day"] = {"utc_day": today}
    cap["status"] = "READY"
    cap.pop("boundary_pending_signature", None)
    cap["valuation"] = {"fresh": True, "unrealized": str(unrealized),
                        "valuation_ms": boundary_ms}
    net_realized = sum((dec(t.get("net", 0)) for t in acc.get("closed", [])
                        if boundary_ms - DAY_MS < int(t.get("close_ms", 0)) <= boundary_ms), Decimal(0))
    _record(cap, now_ms, old_day, -transfer.cash_delta, "rollover", net_realized)
    return True


def update_market_risk(state, prices, *, now_ms):
    """Compatibility name: valuation only; never apply the V1 20% loss stop."""
    cap = state["capital"]
    try:
        _, _, unrealized, _ = account_components(state["main"], prices)
    except (CapitalInvariantError, KeyError, ValueError, TypeError):
        cap["valuation"] = {"fresh": False, "unrealized": "0"}
    else:
        cap["valuation"] = {"fresh": True, "unrealized": str(unrealized), "valuation_ms": now_ms}
    return True


def settle_after_close(state, prices, *, event_id):
    cap = state["capital"]
    if cap.get("status") != "READY":
        return False
    vault = VaultState.from_dict(cap["vault"])
    if vault.pending_total <= 0:
        return False
    acc = state["main"]
    cash, margin, unrealized, equity = account_components(acc, prices)
    reserved = sum((dec((p.get("pending_split") or {}).get("margin", 0)) *
                    (1 + dec(p.get("leverage", 1)) * dec((acc.get("limits") or {}).get("fee_bp_side", 6)) / 10000)
                    for p in (acc.get("positions") or {}).values()), Decimal(0))
    transfer = settle_pending(vault, equity=equity, cash=cash, committed_margin=margin,
                              unrealized=unrealized, reserved_cash=reserved, event_id=event_id,
                              excluded_external_funds=cap.get("excluded_external_funds", 0))
    if transfer.reason == "already_applied":
        return False
    acc["cash"] = float(cash + transfer.cash_delta)
    acc["day_start_equity"] = float(dec(acc["day_start_equity"]) + transfer.cash_delta)
    cap["vault"] = transfer.state.to_dict()
    if transfer.cash_delta:
        stamp = int(event_id.rsplit(":", 1)[-1])
        _record(cap, stamp, None, -transfer.cash_delta, "pending_settled")
    return True
