"""Pure, read-only attachment of independently verified human close annotations.

The caller must read annotation records using manual_close.read_annotations,
which verifies the append-only SHA-256 chain. This function validates semantic
linkage to the PAPER close event and outcome; nothing here trains a model.
Free-form private notes stay in the source registry, not in the shared export.
"""
from __future__ import annotations

import re

from backend.v3.arena.manual_close import REASONS

_HASH = re.compile(r"^[0-9a-f]{64}$")
_REQUEST = re.compile(r"^[A-Za-z0-9-]{16,64}$")
_KEYS = frozenset({
    "schema", "provider", "run_id", "position_id", "close_event_id",
    "request_id", "reason", "note", "annotated_ms", "source", "prev", "hash",
})


def attach_verified_human_reasons(
    outcomes: list[dict], close_events: dict[str, dict], annotations: list[dict],
    *, provider: str, run_id: str, trial_start_ms: int, now_ms: int,
) -> dict:
    """Attach only proven manual reasons to closed outcomes, reject any orphan.

    The close event ID, position, timestamp and exit reason must match the
    authoritative journal. Automatic exits must never inherit human labels.
    Do not copy free-form note contents; the source hash enables private review.
    """
    if type(annotations) is not list or type(close_events) is not dict:
        raise ValueError("arena_annotation_invalid_evidence")
    by_position = {}
    for outcome in outcomes:
        if type(outcome) is not dict or type(outcome.get("position_id")) is not str:
            raise ValueError("arena_annotation_invalid_outcome")
        pid = outcome["position_id"]
        if pid in by_position:
            raise ValueError("arena_annotation_duplicate_outcome")
        by_position[pid] = outcome

    seen_ids = set()
    seen_positions = set()
    last_sha = "0" * 64
    for item in annotations:
        if (type(item) is not dict or set(item) != _KEYS
                or item.get("schema") != "human_close_annotation_v1"
                or item.get("provider") != provider
                or item.get("run_id") != run_id
                or item.get("source") != "human_operator"
                or item.get("reason") not in REASONS
                or type(item.get("position_id")) is not str
                or type(item.get("close_event_id")) is not str
                or type(item.get("request_id")) is not str
                or _REQUEST.fullmatch(item["request_id"]) is None
                or type(item.get("annotated_ms")) is not int
                or not trial_start_ms <= item["annotated_ms"] <= now_ms
                or type(item.get("hash")) is not str
                or _HASH.fullmatch(item["hash"]) is None):
            raise ValueError("arena_annotation_invalid_record")

        note = item["note"]
        if note is not None and (type(note) is not str or not note.strip()
                                 or len(note) > 280
                                 or any(ord(ch) < 32 or ord(ch) == 127 for ch in note)):
            raise ValueError("arena_annotation_invalid_note")

        position_id = item["position_id"]
        event_id = item["close_event_id"]
        if position_id in seen_positions or item["request_id"] in seen_ids:
            raise ValueError("arena_annotation_duplicate")
        seen_positions.add(position_id)
        seen_ids.add(item["request_id"])

        outcome = by_position.get(position_id)
        close_event = close_events.get(event_id)
        if (outcome is None or outcome.get("exit_reason") != "manual"
                or outcome.get("originating_ai") != provider
                or not isinstance(close_event, dict)
                or close_event.get("position_id") != position_id
                or close_event.get("reason") != "manual"
                or type(close_event.get("occurred_at_ms")) is not int
                or not trial_start_ms <= close_event["occurred_at_ms"] <= item["annotated_ms"]):
            raise ValueError("arena_annotation_not_linked_to_manual_close")
        outcome["user_reason"] = item["reason"]
        outcome["user_reason_status"] = (
            "HUMAN_ANNOTATED_UNSPECIFIED" if item["reason"] == "unspecified"
            else "VERIFIED_HUMAN_ANNOTATION"
        )
        outcome["user_annotation_sha256"] = item["hash"]
        outcome["user_note_present"] = note is not None
        outcome["eligible_for_automatic_promotion"] = False
        last_sha = item["hash"]

    return {
        "verified_human_annotation_count": len(annotations),
        "annotation_chain_head_sha256": last_sha,
        "annotation_note_policy": "PRIVATE_SOURCE_ONLY_NOT_EXPORTED",
    }
