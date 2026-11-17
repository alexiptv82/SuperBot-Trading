"""Pure audit tests: no VPS, model calls or trading."""
from __future__ import annotations

from copy import deepcopy

import pytest

from backend.v3.arena.annotation_evidence import attach_verified_human_reasons

T0 = 1000
NOW = 5000
CLOSE = {
    "paper_close.pos-1": {
        "position_id": "pos-1", "reason": "manual", "occurred_at_ms": 2000,
    }
}
ANNOTATION = {
    "schema": "human_close_annotation_v1",
    "provider": "qwen",
    "run_id": "brain-qwen-paper20261118",
    "position_id": "pos-1",
    "close_event_id": "paper_close.pos-1",
    "request_id": "req-000000000000001",
    "reason": "trend_change",
    "note": "inversione 15m, dato privato",
    "annotated_ms": 2500,
    "source": "human_operator",
    "prev": "0" * 64,
    "hash": "a" * 64,
}
OUTCOME = {
    "position_id": "pos-1",
    "originating_ai": "qwen",
    "exit_reason": "manual",
    "realized_pnl": "-3.20",
    "user_reason": None,
    "user_reason_status": "AWAITING_USER_ANNOTATION",
    "eligible_for_automatic_promotion": False,
}


def collect(annotations, *, close=None, outcome=None):
    records = [deepcopy(OUTCOME if outcome is None else outcome)]
    meta = attach_verified_human_reasons(
        records, deepcopy(CLOSE if close is None else close), deepcopy(annotations),
        provider="qwen", run_id="brain-qwen-paper20261118",
        trial_start_ms=T0, now_ms=NOW,
    )
    return records[0], meta


def test_verified_reason_is_linked_without_promoting_or_copying_private_note():
    outcome, meta = collect([ANNOTATION])
    assert outcome["user_reason"] == "trend_change"
    assert outcome["user_reason_status"] == "VERIFIED_HUMAN_ANNOTATION"
    assert outcome["user_annotation_sha256"] == "a" * 64
    assert outcome["user_note_present"] is True
    assert outcome["realized_pnl"] == "-3.20"
    assert outcome["eligible_for_automatic_promotion"] is False
    assert "inversione" not in str(outcome)
    assert meta["verified_human_annotation_count"] == 1
    assert meta["annotation_note_policy"] == "PRIVATE_SOURCE_ONLY_NOT_EXPORTED"


def test_missing_optional_annotation_does_not_invent_reason():
    outcome, meta = collect([])
    assert outcome["user_reason"] is None
    assert outcome["user_reason_status"] == "AWAITING_USER_ANNOTATION"
    assert meta["annotation_chain_head_sha256"] == "0" * 64


def test_explicit_unspecified_is_not_inferred_from_negative_profit():
    a = dict(ANNOTATION, reason="unspecified", note=None)
    outcome, _ = collect([a])
    assert outcome["user_reason_status"] == "HUMAN_ANNOTATED_UNSPECIFIED"
    assert outcome["user_reason"] == "unspecified"
    assert outcome["user_note_present"] is False


@pytest.mark.parametrize("field,value", [
    ("schema", "unknown"), ("provider", "deepseek"), ("run_id", "another-run"),
    ("source", "model"), ("reason", "not_a_reason"), ("position_id", "pos-2"),
    ("close_event_id", "paper_close.pos-2"), ("request_id", "short"),
    ("annotated_ms", 100), ("annotated_ms", 6000),
    ("note", "bad\ncontrol"), ("note", "x" * 281), ("hash", "not_sha"),
])
def test_invalid_annotation_fails_closed(field, value):
    a = dict(ANNOTATION, **{field: value})
    with pytest.raises(ValueError, match="arena_annotation_"):
        collect([a])


def test_orphan_annotation_fails_closed():
    with pytest.raises(ValueError, match="not_linked"):
        collect([ANNOTATION], close={})


def test_automatic_exit_never_inherits_human_reason():
    with pytest.raises(ValueError, match="not_linked"):
        collect([ANNOTATION], outcome=dict(OUTCOME, exit_reason="take_profit"))


def test_human_reason_timestamp_cannot_precede_verified_close():
    with pytest.raises(ValueError, match="not_linked"):
        collect([dict(ANNOTATION, annotated_ms=1999)])


def test_reused_annotation_is_rejected_even_with_distinct_hash():
    with pytest.raises(ValueError, match="duplicate"):
        collect([ANNOTATION, dict(ANNOTATION, hash="b" * 64)])


def test_unexpected_keys_are_rejected():
    with pytest.raises(ValueError, match="invalid_record"):
        collect([dict(ANNOTATION, extra="leak")])


def test_duplicate_outcome_is_rejected():
    with pytest.raises(ValueError, match="duplicate_outcome"):
        attach_verified_human_reasons(
            [dict(OUTCOME), dict(OUTCOME)], {}, [], provider="qwen",
            run_id="brain-qwen-paper20261118", trial_start_ms=T0, now_ms=NOW,
        )
