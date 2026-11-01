"""Exact ONE-position manual close contract; no order or wallet write API.

This pure module only validates an operator's intended target against an
authoritative, timestamped account snapshot. It does NOT close any position,
execute an order, enqueue a command or change a trading strategy.

Do not connect to a service until an authenticated command inbox, durable
idempotency ledger and the PAPER wallet owner are audited end to end.
"""
from __future__ import annotations

import math
import re

SCHEMA = "superbot-single-trade-close-v1"
ACCOUNTS = frozenset(("hawk", "bull", "brain"))
INTENTS = frozenset(("profit_sufficient", "trend_changed", "risk_excessive", "other"))
MAX_REQUEST_AGE_MS = 90_000
MAX_WALLET_AGE_MS = 30_000
MAX_CLOCK_SKEW_MS = 5_000
SYMBOL_RE = re.compile(r"[A-Z0-9]{2,24}\Z")
REQUEST_ID_RE = re.compile(r"[a-f0-9]{32}\Z")


class CloseRejected(ValueError):
    """No valid target, no output, and no action."""


def _symbol(value):
    if not isinstance(value, str):
        raise CloseRejected("invalid_symbol")
    value = value.strip().upper()
    if not SYMBOL_RE.fullmatch(value):
        raise CloseRejected("invalid_symbol")
    return value[:-4] if value.endswith("USDT") and len(value) > 4 else value


def _valid_run(value):
    # Classic run_no is int, Brain experiment_id is a non-empty string.
    return (type(value) is int and value > 0) or (
        isinstance(value, str) and not isinstance(value, bool) and
        1 <= len(value) <= 100 and re.fullmatch(r"[A-Za-z0-9-]{1,100}", value))


def _timestamp(value):
    return type(value) is int and value > 0


def validate_request(request, *, now_ms, seen_request_ids=()):
    """Validate a confirmed operator intent; never creates trade permissions."""
    if not isinstance(request, dict) or request.get("schema") != SCHEMA:
        raise CloseRejected("unsupported_request_schema")
    if type(now_ms) is not int or now_ms <= 0:
        raise CloseRejected("invalid_now")
    if request.get("account_id") not in ACCOUNTS:
        raise CloseRejected("invalid_account")
    if not _valid_run(request.get("run_id")):
        raise CloseRejected("invalid_run")
    if request.get("action") != "close_full" or request.get("mode") != "paper":
        raise CloseRejected("unsupported_action_or_mode")
    if request.get("confirmed_by_user") is not True:
        raise CloseRejected("not_user_confirmed")
    if request.get("intent") not in INTENTS:
        raise CloseRejected("invalid_intent")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise CloseRejected("invalid_request_id")
    if request_id in seen_request_ids:
        raise CloseRejected("duplicate_request_id")
    if type(request.get("position_id")) is not int or request["position_id"] <= 0:
        raise CloseRejected("invalid_position_id")
    if request.get("side") not in (-1, 1) or type(request["side"]) is not int:
        raise CloseRejected("invalid_side")
    symbol = _symbol(request.get("symbol"))
    opened = request.get("open_ms")
    created = request.get("created_ms")
    if not (_timestamp(opened) and _timestamp(created) and opened <= created):
        raise CloseRejected("invalid_open_or_request_time")
    if not (-MAX_CLOCK_SKEW_MS <= now_ms-created <= MAX_REQUEST_AGE_MS):
        raise CloseRejected("expired_or_future_request")
    return symbol


def validate_target(request, wallet, *, now_ms, seen_request_ids=()):
    """Validate exact position identity and report an observation-only ticket.

    Snapshot format:
      account_id: hawk | bull | brain
      run_id: native run_no or native Brain experiment_id
      as_of_ms: authoritative snapshot time
      positions: native {symbol: {id, side, open_ms, ...}}

    The return value is NOT a broker order or an executable wallet command.
    """
    desired = validate_request(request, now_ms=now_ms,
                               seen_request_ids=seen_request_ids)
    if not isinstance(wallet, dict) or wallet.get("account_id") != request["account_id"]:
        raise CloseRejected("wallet_account_mismatch")
    if type(wallet.get("run_id")) is not type(request["run_id"]) or (
        wallet["run_id"] != request["run_id"]
    ):
        raise CloseRejected("wallet_run_mismatch")
    stamp = wallet.get("as_of_ms")
    if not _timestamp(stamp) or not (-MAX_CLOCK_SKEW_MS <= now_ms-stamp <= MAX_WALLET_AGE_MS):
        raise CloseRejected("wallet_stale_or_future")
    positions = wallet.get("positions")
    if not isinstance(positions, dict):
        raise CloseRejected("missing_wallet_positions")
    matches = []
    for key, p in positions.items():
        if _symbol(key) != desired:
            continue
        if not isinstance(p, dict):
            raise CloseRejected("malformed_position")
        matches.append((key, p))
    if len(matches) == 0:
        raise CloseRejected("target_position_not_open")
    if len(matches) != 1:
        raise CloseRejected("ambiguous_symbol_positions")
    key, p = matches[0]
    if (type(p.get("id")) is not int or p["id"] != request["position_id"] or
            type(p.get("side")) is not int or p["side"] != request["side"] or
            type(p.get("open_ms")) is not int or p["open_ms"] != request["open_ms"]):
        raise CloseRejected("position_identity_changed")
    if p.get("symbol") is not None and _symbol(p["symbol"]) != desired:
        raise CloseRejected("position_symbol_mismatch")
    qty = p.get("qty")
    if type(qty) not in (float, int) or not math.isfinite(qty) or qty <= 0:
        raise CloseRejected("position_not_active")
    return {
        "schema": "superbot-single-trade-close-observation-v1",
        "request_id": request["request_id"],
        "account_id": request["account_id"], "run_id": request["run_id"],
        "position_id": request["position_id"], "symbol": key, "side": p["side"],
        "open_ms": p["open_ms"], "intent": request["intent"],
        "other_open_position_count": len(positions)-1,
        "position_count_before": len(positions),
        "may_execute_orders": False, "may_change_wallet": False,
        "needs_wallet_owner_recheck": True,
        "status": "TARGET_MATCHED_RESEARCH_ONLY",
    }


def verified_close_lesson(request, *, receipt, before_wallet, after_wallet, now_ms):
    """Create a draft lesson only AFTER a wallet owner attests persisted close.

    A click, queued request or disappearing exchange position is NOT a closure.
    This only returns a record; no persistence or AI policy update occurs.
    """
    if not isinstance(receipt, dict) or receipt.get("persisted") is not True or (
        receipt.get("kind") != "trade_closed" or
        receipt.get("source") != "manual_user" or
        receipt.get("request_id") != request.get("request_id") or
        receipt.get("account_id") != request.get("account_id") or
        receipt.get("run_id") != request.get("run_id") or
        receipt.get("position_id") != request.get("position_id")
    ):
        raise CloseRejected("unattested_manual_close")
    if type(receipt.get("close_ms")) is not int or receipt["close_ms"] < request["created_ms"]:
        raise CloseRejected("invalid_close_receipt_time")
    if receipt["close_ms"] > now_ms+MAX_CLOCK_SKEW_MS:
        raise CloseRejected("future_close")
    if not isinstance(after_wallet, dict) or after_wallet.get("account_id") != request.get("account_id") or (
        type(after_wallet.get("run_id")) is not type(request.get("run_id")) or
        after_wallet.get("run_id") != request.get("run_id")
    ):
        raise CloseRejected("post_close_wallet_identity_mismatch")
    positions = after_wallet.get("positions")
    if not isinstance(positions, dict):
        raise CloseRejected("post_close_wallet_missing")
    if not isinstance(before_wallet, dict) or before_wallet.get("account_id") != request["account_id"] or (
        before_wallet.get("run_id") != request["run_id"] or
        not isinstance(before_wallet.get("positions"), dict)
    ):
        raise CloseRejected("before_wallet_identity_mismatch")
    # A manual one-trade closure is attestable only when every other position
    # survives with the same unique ID and opening time. Concurrent legitimate
    # protective closes may cause a false negative, never a false 'all safe'.
    previous = before_wallet["positions"]
    for old_key, old_position in previous.items():
        old_sym = _symbol(old_key)
        if old_sym == _symbol(request["symbol"]):
            continue
        matching = [v for k,v in positions.items() if _symbol(k) == old_sym]
        if len(matching) != 1 or not isinstance(matching[0],dict) or not isinstance(old_position,dict) or (
            matching[0].get("id") != old_position.get("id") or
            matching[0].get("open_ms") != old_position.get("open_ms")
        ):
            raise CloseRejected("other_position_changed_or_closed")
    wanted = _symbol(request.get("symbol"))
    if any(_symbol(k) == wanted and isinstance(p, dict) and
           p.get("id") == request["position_id"] for k, p in positions.items()):
        raise CloseRejected("target_not_yet_closed")
    net = receipt.get("net_usd")
    margin = receipt.get("margin_usd")
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (net, margin)) or margin <= 0:
        raise CloseRejected("invalid_net_or_margin")
    return {
        "schema": "superbot-manual-exit-learning-draft-v1",
        "request_id": request["request_id"], "account_id": request["account_id"],
        "run_id": request["run_id"], "position_id": request["position_id"],
        "symbol": request["symbol"], "intent": request["intent"],
        "net_usd": float(net), "roi_net_on_margin_pct": round(100*net/margin, 4),
        "close_ms": receipt["close_ms"], "user_confirmation_required": True,
        "changes_strategy": False, "may_execute_orders": False,
    }
