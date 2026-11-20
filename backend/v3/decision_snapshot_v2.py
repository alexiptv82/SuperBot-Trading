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


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_TF = re.compile(r"^[0-9]{1,3}[mhd]$")
_THESIS_ID = re.compile(r"^th-[0-9a-f]{24}$")
_THESIS_KEYS = {"thesis_id", "reentry_index", "prev_outcome", "truncated"}
_REENTRY_KEYS = {"mode", "would_block", "rule", "window_ms", "max_reentry_index", "loss_cooldown_ms"}


def _thesis_ok(t) -> bool:
    return (isinstance(t, Mapping) and set(t) == _THESIS_KEYS and type(t["thesis_id"]) is str
            and bool(_THESIS_ID.fullmatch(t["thesis_id"])) and type(t["reentry_index"]) is int
            and 1 <= t["reentry_index"] <= 100_000 and t["prev_outcome"] in ("none", "win", "loss", "flat")
            and type(t["truncated"]) is bool)


def _reentry_ok(a) -> bool:
    return (isinstance(a, Mapping) and set(a) == _REENTRY_KEYS and a["mode"] in ("observe", "enforce")
            and type(a["would_block"]) is bool and a["rule"] in (None, "reentry_limit", "loss_cooldown")
            and (a["rule"] is None) == (not a["would_block"])
            and all(type(a[k]) is int and a[k] >= 0 for k in ("window_ms", "max_reentry_index", "loss_cooldown_ms")))
CAPTURE_PHASES = frozenset({"pre_model"})


@dataclass(frozen=True)
class DecisionSnapshotV2:
    """Claim about information available at decision time, never a hindsight label.

    Four distinct instants, never to be confused:

    * ``decision_ts_ms`` -- the MARKET reference instant of the decision (the cycle instant). Not when the model answered.
    * ``feature_asof_ms`` -- close time of the latest candle used by the features (data reference instant).
    * ``captured_at_ms`` -- the input CUT-OFF: data admitted up to this instant (<= decision_ts_ms). It is not a
      wall-clock reading and not the write time.
    * ``capture_wall_ms`` / ``write_wall_ms`` -- self-reported wall clock when the features were computed and when
      the snapshot was handed to the journal. Claims only: the journal cannot verify them.

    The only verifiable time evidence is write ORDER (journal seq), assessed by ``assess_link``. ``capture_phase``
    ``pre_model`` states that features were computed from the same bars before the model was called;
    ``inputs_digest`` (sha256 of the candles used) lets an independent validator recompute the features from
    attested candle copies. features and risk accept Decimal only; no AI rationale or free text.
    """

    decision_event_id: str
    decision_ts_ms: int
    captured_at_ms: int
    feature_asof_ms: int | None = None
    features: Mapping[str, Decimal] = field(default_factory=dict)
    risk: Mapping[str, Decimal] = field(default_factory=dict)
    inputs_digest: str | None = None
    capture_phase: str | None = None
    capture_wall_ms: int | None = None
    write_wall_ms: int | None = None
    feature_set: str | None = None
    # timeframe -> (open time of the first candle used, number of candles): the exact window to recompute from
    inputs_window: Mapping[str, tuple[int, int]] = field(default_factory=dict)
    # approved OPEN only: thesis of the entry and anti-reentry verdict (see backend/v3/runner/thesis.py)
    thesis: Mapping | None = None
    anti_reentry: Mapping | None = None


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


def _require_before_open(later_events, decision_id: str) -> None:
    """Refuse a snapshot once a paper_open exists for its decision: the outcome path has started.

    Lateness is NOT refused here: it is assessed from the journal by ``assess_link`` (the same rule as the dataset
    builder) and makes the snapshot inadmissible for training. Refusing it would turn a data-quality fact into a
    missing record and, in the runner, block the open.
    """
    for item in later_events:
        ev = item.event
        if ev.kind == "paper_open" and isinstance(ev.payload, Mapping) and ev.payload.get("decision_event_id") == decision_id:
            raise ValueError("snapshot_after_open")


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

    if snapshot.inputs_digest is not None and (type(snapshot.inputs_digest) is not str
                                               or not _HEX64.fullmatch(snapshot.inputs_digest)):
        raise ValueError("invalid_inputs_digest")
    if snapshot.capture_phase is not None and snapshot.capture_phase not in CAPTURE_PHASES:
        raise ValueError("invalid_capture_phase")
    walls = (snapshot.capture_wall_ms, snapshot.write_wall_ms)
    if any(w is not None and (type(w) is not int or w <= 0) for w in walls):
        raise ValueError("invalid_wall_clock")
    if None not in walls and walls[0] > walls[1]:
        raise ValueError("capture_after_write")
    if snapshot.feature_set is not None and _safe_source_code(snapshot.feature_set) is None:
        raise ValueError("invalid_feature_set")
    window = snapshot.inputs_window
    if (not isinstance(window, Mapping) or len(window) > 8
            or any(type(k) is not str or not _TF.fullmatch(k) or type(v) is not tuple or len(v) != 2
                   or any(type(x) is not int or x <= 0 for x in v) for k, v in window.items())):
        raise ValueError("invalid_inputs_window")

    if (snapshot.thesis is not None and not _thesis_ok(snapshot.thesis)) or (
            snapshot.anti_reentry is not None and (snapshot.thesis is None or not _reentry_ok(snapshot.anti_reentry))):
        raise ValueError("invalid_thesis")

    features = _finite_num_map(snapshot.features, risk=False)
    risk = _finite_num_map(snapshot.risk, risk=True)
    original = journal.get(snapshot.decision_event_id)          # indexed: no full read of the run per decision
    if (original is None or original.event.kind != "brain_decision" or original.event.portfolio_id != "brain"
            or original.event.run_id != run_id):
        raise ValueError("decision_source_not_found")
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
    if snapshot.thesis is not None and (payload.get("kind") != "OPEN" or payload.get("status") != "APPROVED"):
        raise ValueError("thesis_without_open")

    # Deterministic idempotency key, bound to original decision and immutable hash.
    suffix = hashlib.sha256((run_id + "\0" + event.event_id + "\0" + original.event_hash
                             + "\0snapshot-v2").encode("utf-8")).hexdigest()[:32]
    event_id = "snapshot-v2-" + suffix
    # A re-append of an already stored snapshot is decided by the journal (idempotent or conflict), not re-judged here.
    if journal.get(event_id) is None:
        _require_before_open(journal.list_run_after("brain", run_id, original.seq), event.event_id)
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
            "feature_set": snapshot.feature_set,
            "inputs_window": {k: list(v) for k, v in sorted(snapshot.inputs_window.items())},
            "inputs_digest": snapshot.inputs_digest,
            "thesis": dict(snapshot.thesis) if snapshot.thesis is not None else None,
            "anti_reentry": dict(snapshot.anti_reentry) if snapshot.anti_reentry is not None else None,
            "capture_phase": snapshot.capture_phase,
            "capture_wall_ms": snapshot.capture_wall_ms,
            "write_wall_ms": snapshot.write_wall_ms,
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


# --------------------------------------------------------------------------------------------- canonical link rule
_NUMBER = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")


def assess_link(decision, snapshots, open_seqs, first_seq_stamped_after) -> str:
    """Verdict on the link decision -> snapshot, from journal records only. Same rule as the dataset builder's
    ``snapshot_link.admit`` (cross-checked by tests), plus two stricter checks on the payload's own claims.

    ``decision``: StoredEvent of the brain_decision; ``snapshots``: StoredEvents of SNAPSHOT_KIND naming it;
    ``open_seqs``: seqs of paper_open naming it; ``first_seq_stamped_after(threshold_ms)``: first seq of a
    non-snapshot event of the run stamped beyond threshold. Returns "valid", "missing" or a rejection reason.
    A "valid" link is still NOT verified training data: that needs independent recomputation of the features.
    """
    if not snapshots:
        return "missing"
    if len(snapshots) != 1:
        return "snapshot_conflict"
    snap, dec = snapshots[0], decision.event
    p = snap.event.payload
    if not isinstance(p, Mapping) or snap.event.run_id != dec.run_id or snap.event.portfolio_id != dec.portfolio_id:
        return "snapshot_run_mismatch"
    if p.get("schema_version") != 2 or type(p.get("schema_version")) is not int:
        return "snapshot_schema"
    if p.get("decision_event_id") != dec.event_id or p.get("decision_event_hash") != decision.event_hash:
        return "snapshot_hash_mismatch"
    if type(p.get("decision_ts_ms")) is not int or p.get("decision_ts_ms") != dec.occurred_at_ms:
        return "snapshot_ts_mismatch"
    dp = dec.payload if isinstance(dec.payload, Mapping) else {}
    if not isinstance(dp.get("symbol"), str) or p.get("symbol") != dp.get("symbol"):
        return "snapshot_symbol_mismatch"
    if p.get("action") != dp.get("kind") or p.get("status") != dp.get("status"):
        return "snapshot_decision_mismatch"
    cap, asof, feats = p.get("snapshot_captured_at_ms"), p.get("feature_asof_ms"), p.get("features")
    if (type(cap) is not int or cap > dec.occurred_at_ms or (asof is not None and (type(asof) is not int or asof > cap))
            or (feats and asof is None)):
        return "snapshot_time_order"
    if snap.seq <= decision.seq:
        return "snapshot_before_decision"
    if any(snap.seq >= o for o in open_seqs):
        return "snapshot_after_open"
    later = first_seq_stamped_after(dec.occurred_at_ms + WRITE_GRACE_MS)
    if later is not None and later < decision.seq:
        return "decision_written_late"                    # the decision itself was written after the window
    if later is not None and snap.seq >= later:
        return "snapshot_written_late"
    values = list((feats or {}).items()) + list((p.get("risk") or {}).items())
    if (not isinstance(feats or {}, Mapping) or not isinstance(p.get("risk") or {}, Mapping)
            or any(type(k) is not str or not _FEATURE.fullmatch(k) or type(v) is not str or not _NUMBER.fullmatch(v)
                   for k, v in values)):
        return "snapshot_features_invalid"
    if p.get("inputs_verified") is not False or p.get("eligible_for_training") is not False:
        return "snapshot_self_attested"                   # only an independent validator may verify
    return "valid"
