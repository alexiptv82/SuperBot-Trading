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


# The following optional persistence helpers are only for an isolated shadow
# output directory. They are NEVER imported or called by the operational bot.
import datetime as _dt
import fcntl as _fcntl
from pathlib import Path as _Path


def _shadow_root(root: str) -> _Path:
    path = _Path(root).resolve()
    if path.name != "fix-b-shadow-data":
        raise GuardianError("Fix B writes ONLY to a distinct fix-b-shadow-data directory")
    if any(part in ("superbot-desk-data", "superbot-ai-data", "superbot-sidecar-data") for part in path.parts):
        raise GuardianError("refuse to write in bot or DeepSeek data directories")
    return path


def _append_fsynced(file, row: dict) -> None:
    file.seek(0, 2)
    file.write(json.dumps(row, separators=(",", ":"), sort_keys=True, allow_nan=False) + "\n")
    file.flush()
    __import__("os").fsync(file.fileno())


def append_shadow_record(root: str, event: dict) -> bool:
    """Idempotent append-only evidence for all THREE lanes in one coherent row.

    NEVER publishes an execution command; data directory is separate from bots.
    Corrupt prior JSONL fails closed; this method cannot repair or reset it.
    """
    if event.get("applied") is not False or event.get("executed") is not False:
        raise GuardianError("not a safe shadow event")
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise GuardianError("missing event id")
    directory = _shadow_root(root)
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory/"fix-b-decisions.jsonl", "a+", encoding="utf-8") as file:
        _fcntl.flock(file.fileno(), _fcntl.LOCK_EX)
        file.seek(0)
        for line in file:
            try:
                prev = json.loads(line)
            except ValueError as exc:
                raise GuardianError("shadow log corrupted; refuse append") from exc
            if prev.get("event_id") == event_id:
                return False
        _append_fsynced(file, event)
    return True


def comparison_portfolio_alert(alert: dict, positions: list[dict], *,
                               now_ms: int,
                               operational_by_key: dict | None = None,
                               shadow_by_key: dict | None = None,
                               deepseek_by_symbol: dict | None = None) -> dict:
    """Three-lane comparative ALARM record; no execute and no model calls.

    Future adapters inject model replies. Missing DeepSeek data remain explicitly
    missing; an independent account is never mistaken for Hawk/Bull's position.
    """
    if alert.get("active") is not True or alert.get("applied") is not False:
        raise GuardianError("not a valid shadow portfolio alert")
    from desk.profit_guardian import eligibility as _eligibility
    op = operational_by_key or {}
    sh = shadow_by_key or {}
    ds = deepseek_by_symbol or {}
    rows = []
    for p in positions:
        if _side(p) != -1:
            continue
        key = position_key(p)
        if key not in alert.get("position_keys", []):
            continue
        review = _eligibility(p, now_ms=now_ms, alert=alert)
        rows.append(comparison_event(
            p, now_ms=now_ms, review=review,
            operational_claude=op.get(key), claude_shadow=sh.get(key),
            deepseek_record=ds.get(str(p["symbol"]).upper()),
            alert_id=alert.get("event_id")))
    return {"schema": 1,"event_id": "portfolio:" + str(alert["event_id"]),
            "ts_ms": now_ms,"mode": "ombra","applied": False,"executed": False,
            "status": "ALERT_AND_PROPOSALS_ONLY_NO_EXECUTOR",
            "priority": "MAX","portfolio_alert": alert,
            "position_comparisons": rows,"execution_result": None}


class ShadowBudgetLedger:
    """Durable shared UTC $0.10/day budget for optional FUTURE Claude adapter.

    The SAME root must be mounted to Hawk and Bull to enforce one shared bucket.
    Reservation before a call prevents double admission; failed/crashed calls keep
    their reservation until explicitly settled, never auto-refunded on restart.
    """
    def __init__(self, root: str, cap_usd: float = DAILY_SHARED_BUDGET):
        self.root = _shadow_root(root)
        self.cap = _float(cap_usd, "cap")
        if self.cap <= 0:
            raise GuardianError("budget cap must be positive")

    def _with_lock(self, operation):
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.root/"budget-v1.jsonl", "a+", encoding="utf-8") as file:
            _fcntl.flock(file.fileno(), _fcntl.LOCK_EX)
            file.seek(0)
            rows = []
            for line in file:
                try:
                    row = json.loads(line)
                except ValueError as exc:
                    raise GuardianError("budget journal corrupt; refuse changes") from exc
                if not isinstance(row, dict) or row.get("kind") not in ("reserve", "settle"):
                    raise GuardianError("invalid budget event")
                rows.append(row)
            return operation(file, rows)

    @staticmethod
    def _day(ts_ms: int) -> str:
        if type(ts_ms) is not int or ts_ms <= 0:
            raise GuardianError("invalid UTC budget time")
        return _dt.datetime.fromtimestamp(ts_ms/1000, _dt.timezone.utc).date().isoformat()

    @staticmethod
    def _state(rows: list[dict], day: str) -> tuple[float,float,dict]:
        reservation = {}
        spent = 0.0
        for row in rows:
            if row["day"] != day:
                continue
            ident = row["id"]
            if row["kind"] == "reserve":
                if ident in reservation:
                    raise GuardianError("duplicate reservation in ledger")
                reservation[ident] = {"reserved": float(row["usd"]), "settled": False}
            else:
                if ident not in reservation or reservation[ident]["settled"]:
                    raise GuardianError("orphan or duplicate settlement")
                reservation[ident]["settled"] = True
                spent += float(row["usd"])
        held = sum(x["reserved"] for x in reservation.values() if not x["settled"])
        return spent, held, reservation

    def reserve(self, *, ts_ms: int, event_id: str, worst_usd: float) -> bool:
        day = self._day(ts_ms)
        cost = _float(worst_usd, "worst case cost")
        if not isinstance(event_id,str) or not event_id or cost <= 0:
            raise GuardianError("bad budget reservation")
        def work(file, rows):
            spent, held, entries = self._state(rows, day)
            if event_id in entries:
                return False  # idempotent
            if not budget_admission(spent_usd=spent,reserved_usd=held,
                                    worst_case_call_usd=cost,cap_usd=self.cap):
                return False
            _append_fsynced(file, {"kind":"reserve","day":day,"id":event_id,"usd":cost})
            return True
        return self._with_lock(work)

    def settle(self, *, ts_ms: int, event_id: str, actual_usd: float) -> bool:
        day = self._day(ts_ms)
        actual = _float(actual_usd,"actual cost")
        if actual < 0:
            raise GuardianError("negative actual cost")
        def work(file,rows):
            _, _, entries = self._state(rows,day)
            reservation = entries.get(event_id)
            if reservation is None:
                raise GuardianError("settlement without reservation")
            if reservation["settled"]:
                return False
            if actual > reservation["reserved"] + 1e-9:
                raise GuardianError("actual cost exceeds conservative reservation")
            _append_fsynced(file,{"kind":"settle","day":day,"id":event_id,"usd":actual})
            return True
        return self._with_lock(work)

    def remaining(self, *, ts_ms: int) -> float:
        day=self._day(ts_ms)
        def work(file,rows):
            spent,held,_=self._state(rows,day)
            return max(0.0,round(self.cap-spent-held,8))
        return self._with_lock(work)
