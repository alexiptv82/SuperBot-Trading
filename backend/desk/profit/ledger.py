"""Pure event construction/serialization. The caller owns append-only I/O."""
from dataclasses import asdict
from hashlib import sha256
import json
from . import VERSION


def serialize(event):
    return json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def evaluation(*, portfolio, run_no, position_key, ts_ms, code_version, policy, before, decision, features, liquidation, reversal):
    if portfolio != policy.portfolio or type(run_no) is not int or run_no < 1 or not position_key or ts_ms < features.bar_close_ms:
        raise ValueError("invalid event identity/clock")
    event = {"schema": 1, "ev": "pm_eval", "portfolio": portfolio, "run_no": run_no,
             "position_key": position_key, "ts_ms": ts_ms, "bar_close_ms": features.bar_close_ms,
             "code_version": code_version, "algo": {"name": "pm-"+portfolio, "version": VERSION, "config_hash": policy.config_hash},
             "mode": "ombra", "applied": False, "inputs": asdict(features),
             "derived": {"liquidable": asdict(liquidation), "reversal": asdict(reversal)},
             "state": {"from": asdict(before), "to": asdict(decision.state)},
             "decision": {"action": decision.action, "floor_usd": decision.state.floor_usd, "fraction": decision.fraction, "reasons": decision.reasons},
             "alternatives": [{"action": "HOLD", "ev_usd": None}], "p_win": None, "ev_net_usd": None}
    event["event_id"] = sha256(serialize(event).encode()).hexdigest()
    return event


def outcome(event, *, observed_ms, metrics):
    if observed_ms <= event["ts_ms"]:
        raise ValueError("outcome must be observed later")
    result = {"schema": 1, "ev": "pm_outcome", "event_id": event["event_id"], "ts_ms": observed_ms, "metrics": metrics}
    return json.loads(serialize(result))
