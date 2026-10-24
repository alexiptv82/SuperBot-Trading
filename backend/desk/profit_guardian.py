"""Fix B Profit Guardian V1 — SHADOW ONLY.

No connection to engine/cli, exchange, bot state, orders, Claude or DeepSeek API.
Caller passes hypothetical model responses; every event is applied=false.
"""
from __future__ import annotations
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

WATCH_ROI = 12.0
ARM_ROI = 20.0
COOLDOWN_MS = 30 * 60_000
PARTIAL_FRACTION = 0.50
DAILY_SHARED_BUDGET = 0.10
ACTIONS = ("CLOSE_FULL", "TAKE_PARTIAL", "HOLD_TP")


class GuardianError(ValueError):
    pass


def _float(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise GuardianError(label + ": invalid boolean")
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise GuardianError(label + ": invalid number") from exc
    if not math.isfinite(v):
        raise GuardianError(label + ": non-finite")
    return v


def _side(p: dict) -> int:
    if type(p.get("side")) is not int or p["side"] not in (-1, 1):
        raise GuardianError("side must be +1 or -1")
    return p["side"]


def position_key(p: dict) -> str:
    """Stable across same run and unique across runs/resets."""
    if p.get("portfolio") not in ("hawk", "bull"):
        raise GuardianError("unsupported portfolio")
    run_no = _float(p.get("run_no"), "run_no")
    opened = _float(p.get("open_ms"), "open_ms")
    if int(run_no) != run_no or run_no < 1 or int(opened) != opened or opened <= 0:
        raise GuardianError("invalid run identity")
    sym = str(p.get("symbol") or "").upper()
    pos_id = str(p.get("position_id") or "")
    if not sym or not pos_id:
        raise GuardianError("missing position identity")
    return "%s:%d:%s:%s:%d" % (p["portfolio"], int(run_no), sym, pos_id, int(opened))


@dataclass(frozen=True)
class Review:
    eligible: bool
    priority: str
    reason: str
    next_ms: int | None
    observed_peak_roi: float


def eligibility(p: dict, *, now_ms: int, previous: dict | None = None,
                alert: dict | None = None) -> Review:
    """ROI 12% watches, 20% schedules; SHORT portfolio alerts override ROI,
    but NEVER override the approved hard 30-minute per-position interval.
    """
    position_key(p)
    if type(now_ms) is not int or now_ms <= 0:
        raise GuardianError("invalid now_ms")
    roi = _float(p.get("roi_net_pct"), "roi")
    prev = previous or {}
    peak = max(roi, _float(prev.get("peak_roi_net_pct", roi), "prior peak"))
    short_alert = (_side(p) == -1 and bool(alert and alert.get("active") is True and
                   position_key(p) in alert.get("position_keys", [])))
    if short_alert:
        priority, reason = "MAX", "portfolio_reversal"
    elif roi >= ARM_ROI:
        priority, reason = "HIGH", "roi_at_least_20"
    elif peak >= ARM_ROI:
        priority, reason = "HIGH", "post_peak_giveback"
    elif roi >= WATCH_ROI:
        return Review(False, "WATCH", "roi_12_to_20", None, peak)
    else:
        return Review(False, "NONE", "below_watch", None, peak)
    last = prev.get("last_review_ms")
    if last is not None:
        last_ms = int(_float(last, "last_review_ms"))
        if now_ms < last_ms:
            raise GuardianError("time moved backwards")
        next_ms = last_ms + COOLDOWN_MS
        if now_ms < next_ms:
            return Review(False, priority, "cooldown", next_ms, peak)
    return Review(True, priority, reason, None, peak)


def tp_distance_r(p: dict) -> float | None:
    if p.get("tp") is None:
        return None
    last = _float(p.get("price"), "price")
    tp = _float(p["tp"], "tp")
    entry0 = _float(p.get("entry0"), "entry0")
    risk_dist = _float(p.get("r_dist"), "r_dist")
    if min(last, tp, entry0, risk_dist) <= 0:
        raise GuardianError("invalid TP or original risk reference")
    return _side(p) * (tp - last) / (entry0 * risk_dist)


def build_prompt(p: dict, market: dict, review: Review, *, now_ms: int) -> str:
    """Dedicated Fix B Claude prompt, NOT part of the normal entry prompt."""
    if not review.eligible:
        raise GuardianError("no model call due")
    key = position_key(p)
    roi = _float(p.get("roi_net_pct"), "roi")
    mfe = _float(p.get("mfe_price_R_upper_bound"), "mfe bound")
    if mfe < 0 or market.get("valid") is not True or market.get("closed_bars_only") is not True:
        raise GuardianError("invalid or unclosed market bars")
    asof = int(_float(market.get("asof_ms"), "market time"))
    if not 0 <= now_ms - asof <= 15 * 60_000:
        raise GuardianError("stale market")
    for item in ("rsi_15m", "rsi_1h", "ema20_1h", "ema50_1h", "volume_ratio", "atr_pct"):
        _float(market.get(item), item)
    frame = (
        "QUESTA POSIZIONE HA SUPERATO LA SOGLIA DI PROFITTO — "
        "VALUTA SE PROTEGGERE IL GUADAGNO."
        if roi >= ARM_ROI or review.observed_peak_roi >= ARM_ROI else
        "ALERT PORTAFOGLIO: valuta subito questo SHORT anche senza ROI >=20%."
    )
    data = {
        "position_key": key, "portfolio": p["portfolio"], "side": _side(p),
        "roi_net_pct": roi, "observed_peak_roi_net_pct": review.observed_peak_roi,
        "mfe_price_R_upper_bound": mfe,
        "mfe_note": "bar high/low upper bound, NOT proven executable net peak",
        "tp_original": p.get("tp"), "tp_distance_from_current_price_R": tp_distance_r(p),
        "entry": _float(p.get("entry"), "entry"),
        "price": _float(p.get("price"), "price"),
        "stop_loss": _float(p.get("sl"), "sl"),
        "reference_margin": _float(p.get("reference_margin"), "reference margin"),
        "risk_plan_usd": _float(p.get("risk_plan_usd"), "risk"),
        "market": market, "alert_reason": review.reason,
    }
    return (
        "FIX B / CLAUDE PROFIT GUARDIAN / DEDICATED SINGLE-POSITION REVIEW.\n"
        + frame + "\n"
        "You choose ONE: CLOSE_FULL when reversal threatens protected profit, "
        "TAKE_PARTIAL for a fixed 50% realization with protective residual stop, "
        "or HOLD_TP while momentum is strong. These are judgments, not fixed exits.\n"
        "Use net ROI, MFE upper bound, distance to original TP in R, EMA, RSI, "
        "volume, ATR, momentum, and multi-timeframe reversal structure.\n"
        "TAKE_PARTIAL requires new_stop PRICE, stricter than old stop, on correct "
        "side of current price and after conservative costs at net break-even or better. "
        "If protection fails, the WHOLE partial must be rejected; no half-executed pair.\n"
        "No new entries, DCA, leverage changes, loosening SL or exchange orders.\n"
        "Reply ONLY JSON with action, new_stop (number or null), reason.\n"
        "DATA=" + json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    )


def residual_breakeven(p: dict) -> float:
    """Estimated break-even for remaining quantity, conservative execution fees.
    Existing realized partial gains do not subsidize residual contract losses.
    """
    side = _side(p)
    entry, qty = _float(p.get("entry"), "entry"), _float(p.get("qty"), "quantity")
    fee_open = _float(p.get("fee_open_remaining", 0), "open fees")
    funding = _float(p.get("funding_remaining_usd", 0), "funding")
    fee, slip = _float(p.get("fee_rate_side"), "exit fee"), _float(p.get("slip_rate_side"), "slippage")
    if min(entry, qty) <= 0 or min(fee_open, funding, fee, slip) < 0 or max(fee, slip) >= .05:
        raise GuardianError("invalid residual costs")
    cost_per_qty = (fee_open + funding) / qty
    if side == 1:
        return (entry + cost_per_qty) / ((1 - slip) * (1 - fee))
    be = (entry - cost_per_qty) / ((1 + slip) * (1 + fee))
    if be <= 0:
        raise GuardianError("invalid short breakeven")
    return be


def parse_proposal(response: str | dict, p: dict) -> dict:
    """Strict schema + safety validation, returns a PROPOSAL, never an order."""
    if isinstance(response, str):
        raw = response.strip()
        fence = chr(96) * 3
        if raw.startswith(fence):
            raw = raw.split("\n", 1)[-1].rsplit(fence, 1)[0]
        try:
            proposal = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise GuardianError("invalid Claude response JSON") from exc
    else:
        proposal = response
    if not isinstance(proposal, dict) or proposal.get("action") not in ACTIONS:
        raise GuardianError("unrecognized action")
    reason = proposal.get("reason")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 600:
        raise GuardianError("missing/invalid rationale")
    action = proposal["action"]
    stop = proposal.get("new_stop")
    if action != "TAKE_PARTIAL":
        if stop is not None:
            raise GuardianError("stop only permitted on TAKE_PARTIAL")
        return {"action": action, "new_stop": None, "fraction": None, "reason": reason.strip()}
    if _float(proposal.get("partial_close_fraction", .5), "fraction") != .5:
        raise GuardianError("TAKE_PARTIAL requires exactly half")
    if stop is None:
        raise GuardianError("atomic partial requires residual stop")
    stop, old, mark = _float(stop, "new stop"), _float(p.get("sl"), "old stop"), _float(p.get("price"), "price")
    be = residual_breakeven(p)
    if _side(p) == 1:
        safe = old < stop < mark and stop >= be
    else:
        safe = mark < stop < old and stop <= be
    if not safe:
        raise GuardianError("unsafe stop: entire TAKE_PARTIAL rejected")
    return {"action": action, "new_stop": stop, "fraction": .5, "reason": reason.strip()}


def budget_admission(*, spent_usd: float, reserved_usd: float,
                     worst_case_call_usd: float, cap_usd: float = DAILY_SHARED_BUDGET) -> bool:
    """Check only; future caller MUST atomically reserve in a shared durable ledger.
    One daily $0.10 budget for BOTH bots; not the existing Claude trading budget.
    """
    vals = [_float(v, "budget") for v in (spent_usd, reserved_usd, worst_case_call_usd, cap_usd)]
    if min(vals) < 0:
        raise GuardianError("negative budget")
    return vals[0] + vals[1] + vals[2] <= vals[3] + 1e-9


def _claude_lane(p: dict, raw: str | dict | None, lane: str) -> dict:
    if raw is None:
        return {"lane": lane, "present": False, "proposal": None, "valid": False, "reason": "not_collected"}
    try:
        decision = parse_proposal(raw, p)
        return {"lane": lane, "present": True, "proposal": decision, "valid": True, "reason": "validated"}
    except GuardianError as exc:
        return {"lane": lane, "present": True, "proposal": None, "valid": False, "reason": str(exc)[:160]}


def comparison_event(p: dict, *, now_ms: int, review: Review,
                     operational_claude: str | dict | None = None,
                     claude_shadow: str | dict | None = None,
                     deepseek_record: dict | None = None,
                     alert_id: str | None = None) -> dict:
    """3 lanes; DeepSeek is its EXISTING INDEPENDENT shadow output, never queried.
    No claim of comparison if same symbol/time is held in a different portfolio.
    """
    key = position_key(p)
    event_id = hashlib.sha256(("%s:%d:%s" % (key, now_ms, alert_id or "")).encode()).hexdigest()[:24]
    op = _claude_lane(p, operational_claude, "claude_candidate_not_executed")
    sh = _claude_lane(p, claude_shadow, "claude_independent_shadow")
    ds = {"lane": "deepseek_existing_shadow", "present": False,
          "applied": False, "proposal": None, "reason": "not_collected"}
    if deepseek_record is not None:
        same = (str(deepseek_record.get("symbol", "")).upper() == str(p["symbol"]).upper()
                and type(deepseek_record.get("ts_ms")) is int
                and abs(now_ms - deepseek_record["ts_ms"]) <= 15 * 60_000
                and deepseek_record.get("same_position_context") is True)
        ds = {"lane": "deepseek_existing_shadow", "present": bool(same), "applied": False,
              "proposal": deepseek_record.get("action") if same else None,
              "reason": "comparable" if same else "independent_account_not_comparable"}
    agreement = ("agree" if op["valid"] and sh["valid"] and op["proposal"]["action"] == sh["proposal"]["action"]
                 else "diverge" if op["valid"] and sh["valid"] else "unknown")
    return {"schema": 1, "event_id": event_id, "ts_ms": now_ms,
            "position_key": key, "portfolio": p["portfolio"], "symbol": p["symbol"],
            "mode": "ombra", "applied": False, "executed": False,
            "status": "PROPOSAL_ONLY_NO_EXECUTOR", "alert_id": alert_id,
            "review": {"priority": review.priority, "reason": review.reason},
            "roi_net_pct": p.get("roi_net_pct"),
            "mfe_price_R_upper_bound": p.get("mfe_price_R_upper_bound"),
            "claude_operational_candidate": op, "claude_shadow": sh,
            "deepseek_shadow": ds, "claude_self_comparison": agreement,
            "execution_result": None}
