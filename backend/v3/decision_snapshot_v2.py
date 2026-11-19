"""Brain Unico decision snapshot v2 -- inert, append-only laboratory adapter.

Captures a small, strictly typed snapshot linked to an existing V3 brain_decision.
This module is NOT wired to a runner; it has no network, model or trading calls.
A snapshot is explicitly *unverified* until independent evidence attests the
capture and upstream market feed. In particular this is not training data yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import re
from typing import Mapping

from backend.v3.events import Event, EventJournal

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_FEATURE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9/_:.-]{0,31}$")
# The journal does not enforce that occurred_at_ms is truthful, so a timestamp alone cannot show that a snapshot was
# written BEFORE the outcome was known. Write ORDER (journal seq) can. Keep WRITE_GRACE_MS equal to the dataset builder's
# `snapshot_link.WRITE_GRACE_MS`: the builder re-checks the same rule on the copied journal.
SNAPSHOT_KIND = "brain_decision_snapshot_v2"
WRITE_GRACE_MS = 120_000
_ALLOWED_RISK = frozenset({
    "equity_usd", "margin_in_use_usd", "open_risk_usd", "daily_loss_fraction",
    "portfolio_exposure_usd", "available_margin_usd",
})


@dataclass(frozen=True)
class DecisionSnapshotV2:
    """Claim about information available at decision time, never a hindsight label.

    captured_at_ms is the snapshot acquisition instant, not its write time;
    unverified timestamps cannot establish provenance by themselves.
    feature_asof_ms is the latest input time used in constructing features.
    features and risk accept Decimal only; no AI rationale or free text.
    """

    decision_event_id: str
    decision_ts_ms: int
    captured_at_ms: int
    feature_asof_ms: int | None = None
    features: Mapping[str, Decimal] = field(default_factory=dict)
    risk: Mapping[str, Decimal] = field(default_factory=dict)


def _finite_num_map(values: Mapping[str, Decimal], *, risk: bool) -> dict[str, str]:
    if not isinstance(values, Mapping) or len(values) > (len(_ALLOWED_RISK) if risk else 64):
        raise ValueError("invalid_snapshot_values")
    output: dict[str, str] = {}
    for name, number in values.items():
        if type(name) is not str or not _FEATURE.fullmatch(name):
            raise ValueError("invalid_snapshot_key")
        if risk and name not in _ALLOWED_RISK:
            raise ValueError("invalid_risk_key")
        if type(number) is not Decimal or not number.is_finite():
            raise ValueError("invalid_snapshot_number")
        if risk and number < 0:
            raise ValueError("invalid_risk_number")
        if number.adjusted() > 16 or number.as_tuple().exponent < -16:
            raise ValueError("snapshot_number_out_of_range")
        output[name] = format(number, "f")
    return dict(sorted(output.items()))


def _safe_source_code(value: object) -> str | None:
    return value if (type(value) is str and _TOKEN.fullmatch(value) and len(value) <= 64) else None


def _require_write_order(run_events, original, snapshot: DecisionSnapshotV2) -> None:
    """Refuse a snapshot the journal can show was NOT written at decision time.

    * ``snapshot_after_open``: a paper_open already exists for this decision (the outcome path has started);
    * ``snapshot_written_late``: some other event written after the decision carries a time beyond
      decision_ts + WRITE_GRACE_MS. Other snapshots are not evidence of time (their timestamps are claims too).
    Necessary, not sufficient: it does not prove the features were computed from the right inputs.
    """
    decision_id = original.event.event_id
    horizon = snapshot.decision_ts_ms + WRITE_GRACE_MS
    for item in run_events:
        ev = item.event
        if ev.kind == "paper_open" and isinstance(ev.payload, Mapping) and ev.payload.get("decision_event_id") == decision_id:
            raise ValueError("snapshot_after_open")
        if item.seq > original.seq and ev.kind != SNAPSHOT_KIND and ev.occurred_at_ms > horizon:
            raise ValueError("snapshot_written_late")


def make_snapshot_event(*, journal: EventJournal, run_id: str,
                        snapshot: DecisionSnapshotV2) -> Event:
    """Validate a journal link, return a deterministic V3 event, without writing."""
    if not isinstance(journal, EventJournal) or type(snapshot) is not DecisionSnapshotV2:
        raise ValueError("invalid_snapshot_request")
    if type(run_id) is not str or not _TOKEN.fullmatch(run_id):
        raise ValueError("invalid_snapshot_run")
    if type(snapshot.decision_event_id) is not str or not _TOKEN.fullmatch(snapshot.decision_event_id):
        raise ValueError("invalid_decision_event_id")
    if (any(type(v) is not int or v <= 0 for v in (snapshot.decision_ts_ms, snapshot.captured_at_ms))
            or snapshot.captured_at_ms > snapshot.decision_ts_ms):
        raise ValueError("snapshot_after_decision")
    at_ms = snapshot.feature_asof_ms
    if at_ms is not None and (type(at_ms) is not int or at_ms <= 0 or at_ms > snapshot.captured_at_ms):
        raise ValueError("feature_from_future")
    if snapshot.features and at_ms is None:
        raise ValueError("missing_feature_asof")

    features = _finite_num_map(snapshot.features, risk=False)
    risk = _finite_num_map(snapshot.risk, risk=True)
    run_events = journal.list_run("brain", run_id)
    records = [item for item in run_events if item.event.event_id == snapshot.decision_event_id]
    if len(records) != 1 or records[0].event.kind != "brain_decision":
        raise ValueError("decision_source_not_found")
    original = records[0]
    event = original.event
    if event.occurred_at_ms != snapshot.decision_ts_ms:
        raise ValueError("decision_timestamp_mismatch")
    payload = event.payload
    if (payload.get("kind") not in ("OPEN", "NO_TRADE", "HOLD")
            or payload.get("status") not in ("APPROVED", "REJECTED", "RISK_REJECTED", "DRAFT")
            # Brain F2 permits APPROVED only for OPEN; reject impossible
            # journal status/action pairs before linking a snapshot.
            or (payload.get("status") == "APPROVED" and payload.get("kind") != "OPEN")
            or not isinstance(payload.get("symbol"), str)
            or not _SYMBOL.fullmatch(payload["symbol"])):
        raise ValueError("source_decision_invalid")

    # Deterministic idempotency key, bound to original decision and immutable hash.
    suffix = hashlib.sha256((run_id + "\0" + event.event_id + "\0" + original.event_hash
                             + "\0snapshot-v2").encode("utf-8")).hexdigest()[:32]
    event_id = "snapshot-v2-" + suffix
    # A re-append of an already stored snapshot is decided by the journal (idempotent or conflict), not re-judged here.
    if not any(item.event.event_id == event_id for item in run_events):
        _require_write_order(run_events, original, snapshot)
    return Event(
        event_id=event_id,
        portfolio_id="brain", run_id=run_id, kind=SNAPSHOT_KIND,
        occurred_at_ms=snapshot.decision_ts_ms, source="brain_snapshot_v2_lab",
        payload={
            "schema_version": 2,
            "decision_event_id": event.event_id,
            "decision_event_hash": original.event_hash,
            "decision_ts_ms": snapshot.decision_ts_ms,
            "snapshot_captured_at_ms": snapshot.captured_at_ms,
            "feature_asof_ms": at_ms,
            "symbol": payload["symbol"],
            "action": payload["kind"],
            "status": payload["status"],
            "regime": _safe_source_code(payload.get("regime")),
            "strategy_id": _safe_source_code(payload.get("strategy_id")),
            "reason_code": _safe_source_code(payload.get("rationale")),
            "features": features,
            "risk": risk,
            "feature_source": "unverified_snapshot" if features else "none",
            "inputs_verified": False,
            "eligible_for_training": False,
        },
    )


def append_snapshot(*, journal: EventJournal, run_id: str,
                    snapshot: DecisionSnapshotV2):
    """Append idempotently; conflicting payload for same decision is rejected.

    This is opt-in and never invoked from the running Brain or an exit service.
    """
    return journal.append(make_snapshot_event(journal=journal, run_id=run_id,
                                              snapshot=snapshot))
