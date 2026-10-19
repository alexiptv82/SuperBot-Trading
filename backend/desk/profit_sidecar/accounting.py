"""Mirror engine formula on immutable copies; never infer execution fills."""
from .common import Freeze, integer, numeric, sha
from ..profit.liquidable import Leg, PositionView, Costs, evaluate

FUNDING_MODEL = "engine-0b9a2ad-long-qty-entry-elapsed-1"


def identity(run_key, pos):
    integer(pos.get("id"), 1)
    integer(pos.get("open_ms"), 1)
    symbol = pos.get("symbol")
    if not isinstance(symbol, str) or not symbol:
        raise Freeze("position_identity")
    return sha([run_key, pos["id"], pos["open_ms"], symbol])


def matching(row, pos):
    return all(row.get(k) == pos.get(k) for k in ("id", "open_ms", "symbol"))


def closed_records(observation, previous_hashes):
    rows = observation.state["main"]["closed"]
    hashes = [sha(r) for r in rows]
    if hashes[:len(previous_hashes)] != previous_hashes:
        raise Freeze("closed_prefix_changed")
    outcomes = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise Freeze("closed_record_schema")
        key = identity(observation.run_key, row)
        at = integer(row.get("close_ms"), row["open_ms"])
        if row["open_ms"] < observation.state["run_started_ms"] or at > observation.asof_ms:
            raise Freeze("closed_time_inconsistent")
        numeric(row.get("net"))
        if i < len(previous_hashes):
            continue
        all_position = [r for r in rows[:i+1] if matching(r, row)]
        realized = sum(numeric(r["net"]) for r in all_position)
        outcomes.append({"ev": "actual_outcome", "event_id": sha([observation.run_key, i, hashes[i]]),
                         "position_key": key, "closed_index": i, "record_hash": hashes[i],
                         "record": row, "lifecycle_net_usd": realized,
                         "reconciled": True, "partial": row.get("partial") is True})
    return hashes, outcomes


def snapshot(observation, pos, *, previous_cycle_end=None, prudent_spread_bp=4.0, prudent_extra_slip_bp=3.0):
    state, now = observation.state, observation.asof_ms
    key = identity(observation.run_key, pos)
    if pos["open_ms"] < state["run_started_ms"] or pos["open_ms"] > now:
        raise Freeze("position_time_inconsistent")
    side = pos.get("side")
    if side not in (-1, 1) or isinstance(side, bool):
        raise Freeze("position_side")
    qty, entry = numeric(pos.get("qty"), positive=True), numeric(pos.get("entry"), positive=True)
    fee = numeric(pos.get("fee_open"))
    levels = pos.get("dca_levels")
    if not isinstance(levels, list):
        raise Freeze("dca_schema")
    reference = numeric(pos.get("margin"), positive=True) + sum(numeric(d.get("margin"), positive=True) for d in levels)
    limits = state["main"]["limits"]
    rate = numeric(limits.get("funding_bp_8h_long"))
    funding = qty * entry * rate / 10000 * max(0, now-pos["open_ms"]) / 28800000 if side == 1 else 0.0
    partials = [r for r in state["main"]["closed"] if matching(r, pos) and r.get("partial") is True]
    realized = sum(numeric(r.get("net")) for r in partials)
    view = PositionView(side, (Leg(entry, qty, fee),), funding, realized, reference)
    costs = Costs(numeric(limits.get("fee_bp_side"))/10000, 0, numeric(limits.get("slip_bp_side"))/10000)
    prudent = Costs(costs.fee_rate, prudent_spread_bp/10000, costs.slippage_fraction+prudent_extra_slip_bp/10000)
    price = numeric(state.get("last_prices", {}).get(pos["symbol"]), positive=True)
    price_ms = integer(state.get("last_prices_ms"), 1)
    if price_ms > now:
        raise Freeze("future_reference_price")
    lower = previous_cycle_end if previous_cycle_end is not None else observation.heartbeat["last_start_ms"]-1
    dca_in_window = any(integer(d.get("added_ms"), 1) > lower for d in levels)
    partial_in_window = any(r["close_ms"] > lower for r in partials)
    # On first observation we cannot order historical DCA/partials reliably.
    ambiguous = dca_in_window and partial_in_window
    if previous_cycle_end is None and levels and partials:
        ambiguous = True
    fields = {k: pos.get(k) for k in ("id", "symbol", "open_ms", "liq", "leverage", "trade_type", "source", "pending_split", "entry0", "legs", "dca_count", "sl", "tp")}
    snap = {**fields, "position_key": key, "run_key": observation.run_key,
            "asof_ms": now, "cycle": observation.heartbeat["cycles"],
            "aggregate_leg": {"entry": entry, "qty": qty, "open_fee": fee},
            "reference_margin": reference, "current_margin": numeric(pos.get("total_margin"), positive=True),
            "realized_net": realized, "partial_occurrences": len(partials),
            "funding_paid": funding, "funding_model_version": FUNDING_MODEL,
            "funding_source": "modello del motore; non funding reale",
            "price": price, "price_ms": price_ms, "ambiguous_order": ambiguous,
            "price_extrema": {"px_hi": pos.get("px_hi"), "px_lo": pos.get("px_lo"),
                              "label": "limite superiore di prezzo non eseguibile; non inizializza picco PM"},
            "costs": {"fee_rate": costs.fee_rate, "spread_fraction": 0, "slippage_fraction": costs.slippage_fraction},
            "prudent_costs": {"fee_rate": prudent.fee_rate, "spread_fraction": prudent.spread_fraction, "slippage_fraction": prudent.slippage_fraction},
            "prudent_scenario": "ipotesi di sensibilita; non spread misurato"}
    return snap, view, costs, prudent
