"""Additive candidates and bounded PAPER scalp management; no I/O or orders."""
from __future__ import annotations

import math
from .position_card import metrics

VERSION = "classics-additive-scalp-v1"
DAY_MS = 86_400_000
OPEN_ACTIONS = {"open_long", "open_short", "open_long_split", "open_short_split"}


def combine(rule_decisions, ai_decisions, open_symbols, ai_source="deepseek", vetoes=()):
    """An explicit proposal/veto owns only its symbol, never the whole universe.

    A rejected AI entry is NOT replaced with a larger rule entry. A hold on an
    existing position overrides its rule management. A hold on a flat symbol
    is not a veto: skip is the explicit, documented entry-veto operation.
    """
    selected = {}
    blocked = set(vetoes)
    for d in ai_decisions:
        symbol, action = d.get("symbol"), d.get("action")
        if not symbol:
            continue
        if action == "skip" and symbol not in open_symbols:
            blocked.add(symbol)
        if action in OPEN_ACTIONS or symbol in open_symbols:
            selected[symbol] = dict(d, _decision_source=ai_source)
    out = [dict(d, _decision_source="rules") for d in rule_decisions
           if d["symbol"] not in blocked and d["symbol"] not in selected]
    out.extend(d for symbol, d in selected.items()
               if symbol not in blocked or d["action"] not in OPEN_ACTIONS)
    return out, {"version": VERSION, "rule_proposals": len(rule_decisions),
                 "ai_decisions": len(ai_decisions), "explicit_vetoes": sorted(blocked),
                 "ai_choices": [{"symbol": d.get("symbol"), "action": d.get("action"),
                                 "confidence": d.get("confidence"),
                                 "reason": str(d.get("reason", ""))[:200]}
                                for d in ai_decisions],
                 "rule_candidates": [{k: d.get(k) for k in
                     ("symbol", "action", "confidence", "margin_usd", "leverage",
                      "stop_loss_pct", "take_profit_pct")} for d in rule_decisions],
                 "selected": [{"symbol": d["symbol"], "action": d["action"],
                               "source": d["_decision_source"]} for d in out]}


def stop_for_lifecycle_net(pos, net_target, now_ms, closed, limits):
    """Invert the same fee/slippage/funding cashflows used by position_card.

    Includes already realized partials; no bar-extreme peak is treated as an
    executable net profit. Stop fills remain subject to gaps, as in the engine.
    """
    realized = sum(r["net"] for r in closed
                   if r.get("id") == pos.id and r.get("symbol") == pos.symbol
                   and r.get("open_ms") == pos.open_ms and r.get("partial") is True)
    funding = (pos.qty * pos.entry * limits.funding_bp_8h_long / 10000
               * max(0, now_ms - pos.open_ms) / 28_800_000 if pos.side == 1 else 0.)
    coefficient = pos.qty * (pos.side - limits.fee_bp_side / 10000)
    constant = realized - pos.side * pos.entry * pos.qty - pos.fee_open - funding
    return ((net_target - constant) / coefficient
            / (1 - pos.side * limits.slip_bp_side / 10000))


def manage(account, prices, readings, decisions, state, now_ms, tier_threshold):
    """24h time budget, one justified extension up to 48h, observed-net lock.

    A position arms after reaching +1 initial R net at an observed quote. Half
    that observed peak is protected by a tighter stop. A profitable position
    with a weakening setup and an indecisive adviser is closed. These are
    lifecycle protections: old low-margin/low-leverage positions remain valid.
    """
    memory = state.setdefault("classic_scalp", {"version": VERSION, "positions": {}})
    tracked = memory.setdefault("positions", {})
    by_symbol = {d["symbol"]: d for d in decisions}
    forced = {}
    events = []
    for symbol, pos in account.positions.items():
        price = prices.get(symbol)
        if price is None or not math.isfinite(price) or price <= 0:
            continue  # No invented fill; the ordinary protection path remains active.
        key = f"{symbol}:{pos.id}:{pos.open_ms}"
        record = tracked.setdefault(key, {"deadline_ms": pos.open_ms + DAY_MS,
                                           "extended": False, "peak_net": 0.})
        card = metrics(pos, price, now_ms, account.closed, account.limits)
        roi = card["roi_net_pct"]
        reference = card["reference_margin"]
        if roi is None or reference <= 0:
            continue
        net = roi * reference / 100
        record["peak_net"] = max(float(record.get("peak_net", 0)), net)
        own = readings.get(symbol)
        own_score = (getattr(own, "long_score", 0) if pos.side == 1
                     else getattr(own, "short_score", 0))
        opposite = (getattr(own, "short_score", 0) if pos.side == 1
                    else getattr(own, "long_score", 0))
        choice = by_symbol.get(symbol, {})
        action = choice.get("action")
        reason = ""
        if now_ms >= record["deadline_ms"]:
            extension = choice.get("hold_extension_hours", 0)
            justified = (action == "hold" and choice.get("_decision_source") in ("deepseek", "claude")
                         and isinstance(extension, (int, float)) and math.isfinite(extension)
                         and 0 < extension <= 24 and len(choice.get("reason", "")) >= 20
                         and own_score >= tier_threshold(symbol) and opposite < 60 and net > 0)
            if not record["extended"] and justified and now_ms < pos.open_ms + 2 * DAY_MS:
                record.update(extended=True, deadline_ms=min(pos.open_ms + 2 * DAY_MS,
                              record["deadline_ms"] + int(extension * 3_600_000)))
                events.append({"ev": "scalp_extension", "symbol": symbol, "id": pos.id,
                               "deadline_ms": record["deadline_ms"]})
            if now_ms >= record["deadline_ms"] or now_ms >= pos.open_ms + 2 * DAY_MS:
                reason = "scalp: tempo massimo raggiunto, libera slot"
        armed = pos.risk_plan_usd > 0 and record["peak_net"] >= pos.risk_plan_usd
        if not reason and armed and net > 0 and action in (None, "hold", "skip"):
            if own is not None and (own_score < tier_threshold(symbol) or opposite >= 60):
                reason = "salva profitto netto: setup indebolito, libera slot"
        if not reason and armed and action not in ("close", "partial_close", "dca"):
            target = record["peak_net"] * .5
            # If price is already beyond the intended net lock, exit at the
            # observed price instead of installing a stop on the wrong side.
            if net <= target:
                reason = "salva profitto: ritracciamento del netto osservato"
            else:
                proposed = stop_for_lifecycle_net(pos, target, now_ms, account.closed, account.limits)
                tight = max(pos.sl, proposed) if pos.side == 1 else min(pos.sl, proposed)
                if math.isfinite(tight) and tight > 0 and pos.side * (price - tight) > 0:
                    if tight != pos.sl:
                        pos.sl = tight
                        events.append({"ev": "profit_lock", "symbol": symbol, "id": pos.id,
                                       "stop": tight, "net_lock_estimate": target,
                                       "peak_net_observed": record["peak_net"]})
                        account.cancel_split(symbol, "salva profitto attivo", now_ms)
        if reason:
            forced[symbol] = {"symbol": symbol, "action": "close", "reason": reason,
                              "close_why": reason, "_decision_source": "rules"}
    # Completed positions disappear only from this new lifecycle cache; never
    # from trade/learning history or the portfolio account.
    active = {f"{s}:{p.id}:{p.open_ms}" for s, p in account.positions.items()}
    memory["positions"] = {k: v for k, v in tracked.items() if k in active}
    return ([d for d in decisions if d["symbol"] not in forced] + list(forced.values())), events
