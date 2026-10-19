"""Offline JSON snapshot replay. Never connects to a server or engine.

Run: PYTHONPATH=backend python -m desk.profit_replay_v1 input.json new-output.json
Input schema documented in profit/README.md. Output creation is exclusive.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from .profit.features import Bar, extract
from .profit.liquidable import Costs, Leg, PositionView, evaluate
from .profit.machine import State, step
from .profit.policy import Policy
from .profit.reversal import assess
from .profit.ledger import evaluation


def replay(data):
    if data.get("schema") != 1 or data.get("mode") != "paper":
        raise ValueError("schema 1 PAPER input required")
    policy = Policy(**data["policy"])
    expected_run = {"hawk": 3, "bull": 2}[policy.portfolio]
    if data["run_no"] != expected_run:
        raise ValueError("this audit targets Hawk run 3 / Bull run 2")
    costs = Costs(**data["costs"])
    events, summaries = [], []
    seen = set()
    for trade in data["positions"]:
        key = trade["position_key"]
        if key in seen:
            raise ValueError("duplicate position")
        seen.add(key)
        bars = tuple(Bar(**b) for b in trade["bars"])
        state, previous, first_exit = State(), -1, None
        for snap in trade["snapshots"]:
            at = snap["asof_ms"]
            if at <= previous:
                raise ValueError("snapshots must be strictly chronological")
            previous = at
            view = PositionView(legs=tuple(Leg(**x) for x in snap["legs"]), side=trade["side"], funding_paid=snap["funding_paid"], realized_net=snap["realized_net"], reference_margin=trade["reference_margin"])
            f = extract(bars, asof_ms=at, opened_ms=trade["opened_ms"], peak_ms=max(trade["opened_ms"], state.peak_ms), interval_ms=data["interval_ms"], max_age_ms=data["max_age_ms"])
            # No mark means no valuation; do not invent a price from future bars.
            if f.mark <= 0:
                raise ValueError("no known mark at snapshot")
            liq = evaluate(view, f.mark, costs)
            rev = assess(f, view.side)
            d = step(state, features=f, liquidation=liq, qty=sum(x.qty for x in view.legs), reversal=rev, policy=policy)
            event = evaluation(portfolio=policy.portfolio, run_no=data["run_no"], position_key=key, ts_ms=at, code_version=data["code_version"], policy=policy, before=state, decision=d, features=f, liquidation=liq, reversal=rev)
            events.append(event)
            state = d.state
            if d.action == "ESCI" and first_exit is None:
                first_exit = {"signal_ms": at, "net_at_signal_usd": liq.net_usd, "execution_net_usd": None}
        summaries.append({"position_key": key, "first_exit": first_exit, "baseline_net_usd": trade.get("baseline_net_usd"), "final_state": asdict(state)})
    return {"schema": 1, "research_only": True, "config_hash": policy.config_hash, "events": events, "positions": summaries,
            "limitations": ["Decision replay only: signal valuation is not an executable fill or realized return.", "No PM-A or A-D engine counterfactuals in this runner; original prototype runner remains separate.", "Historical snapshots must include contemporaneous residual legs, fees, funding and realized partials; final state is not a substitute.", "No portfolio performance or promotion conclusion without validated source data and execution replay."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    result = replay(json.loads(raw))
    result["input_sha256"] = hashlib.sha256(raw).hexdigest()
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(result, stream, allow_nan=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
