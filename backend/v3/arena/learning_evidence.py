"""Read-only, full-history evidence bundle for a future AI Arena learning review.

There is NO training, model prompt update, side effect, merge of journals, or
trading action. A winner can later be advised by evidence from all three
providers *after* the independent 14-day test, human audit and offline
evaluation. Source journals stay independent, intact and authoritative.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import re

from backend.v3.arena.read_view import read_wallet
from backend.v3.arena.annotation_evidence import attach_verified_human_reasons
from backend.v3.arena.manual_close import read_annotations
from backend.v3.arena.trial_plan import PROVIDERS, WalletPlan
from backend.v3.events import EventJournal
from backend.v3.outcomes import extract_outcomes

_HEX_SHA = re.compile(r"^[a-f0-9]{64}$")


def _safe_reason(value):
    """Return only a short machine-readable reason; never prompt free text."""
    if isinstance(value, str) and len(value) <= 96 and re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
        return value
    return None


def _validate_plans(plans: tuple[WalletPlan, ...]) -> None:
    if (type(plans) is not tuple or len(plans) != 3
            or tuple(p.provider for p in plans) != PROVIDERS
            or len({p.journal for p in plans}) != 3
            or len({p.run_id for p in plans}) != 3
            or any(p.internal_portfolio_id != "brain"
                   or p.journal != p.folder / "journal.db"
                   or p.folder.parent.name != p.provider
                   or p.folder.name != p.run_id
                   for p in plans)):
        raise ValueError("arena_learning_invalid_wallet_scope")


def collect_arena_learning_evidence(
    plans: tuple[WalletPlan, ...], now_ms: int,
) -> dict:
    """Make an auditable snapshot, including ALL decisions and ALL closed outcomes.

    Requires 3 initialized, intact, approved trial journals with a shared T0.
    Missing, stale, mutated, unmatched or incomplete journals FAIL CLOSED.
    The caller must not automatically use this bundle in any live model prompt.
    """
    _validate_plans(plans)
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError("arena_learning_invalid_clock")
    wallets = {p.provider: read_wallet(p, now_ms) for p in plans}
    if any(row.get("data_status") != "VERIFIED"
           or row.get("trial_comparable") is not True
           or not isinstance(row.get("trial_start_ms"), int)
           or row["trial_start_ms"] <= 0
           for row in wallets.values()):
        raise ValueError("arena_learning_wallet_not_verified")
    starts = {row["trial_start_ms"] for row in wallets.values()}
    if len(starts) != 1:
        raise ValueError("arena_learning_t0_mismatch")
    t0 = starts.pop()
    archive = {}
    for plan in plans:
        journal = EventJournal(plan.journal)
        count, head = journal.verify_chain()
        if not _HEX_SHA.fullmatch(head):
            raise ValueError("arena_learning_invalid_head")
        events = journal.list_run("brain", plan.run_id)
        if count != len(events):
            raise ValueError("arena_learning_foreign_events")
        report = extract_outcomes(journal, "brain", plan.run_id)
        # All CLOSED positions must be retained; a skipped outcome is not
        # usable learning evidence, and cannot be silently discarded.
        if report.skipped:
            raise ValueError("arena_learning_skipped_outcomes")
        if report.run_id != plan.run_id or report.portfolio_id != "brain":
            raise ValueError("arena_learning_report_scope_mismatch")
        decisions = []
        close_events = {}
        kinds = Counter()
        for se in events:
            ev = se.event
            kinds[ev.kind] += 1
            if ev.portfolio_id != "brain" or ev.run_id != plan.run_id:
                raise ValueError("arena_learning_foreign_events")
            if ev.kind in ("brain_decision", "paper_open") and ev.payload.get("originating_ai") != plan.provider:
                raise ValueError("arena_learning_origin_mismatch")
            # Existing executor.paper_close writes no originating_ai field.
            # Trust the linked opening outcome for attribution; if the close
            # DOES declare an origin, it must agree with the provider.
            if ev.kind == "paper_close" and ev.payload.get("originating_ai", plan.provider) != plan.provider:
                raise ValueError("arena_learning_origin_mismatch")
            if ev.kind == "paper_close":
                if ev.event_id in close_events:
                    raise ValueError("arena_learning_duplicate_close_event")
                close_events[ev.event_id] = {
                    "position_id": ev.payload.get("position_id"),
                    "reason": ev.payload.get("reason"),
                    "occurred_at_ms": ev.occurred_at_ms,
                }
            if ev.kind == "brain_decision":
                # The decision is evidence even if it says NO_TRADE or
                # RISK_REJECTED. Short reason codes only; no secrets/prompts.
                decisions.append({
                    "decision_event_id": ev.event_id,
                    "occurred_at_ms": ev.occurred_at_ms,
                    "kind": ev.payload.get("kind"),
                    "status": ev.payload.get("status"),
                    "symbol": ev.payload.get("symbol"),
                    "reason_code": _safe_reason(ev.payload.get("reason_code")),
                    "source": ev.source,
                })
        outcomes = []
        for o in report.outcomes:
            if (o.run_id != plan.run_id or o.portfolio_id != "brain"
                    or o.originating_ai != plan.provider
                    or o.link_status != "linked"):
                raise ValueError("arena_learning_outcome_unlinked_or_foreign")
            if o.closed_at_ms < t0:
                raise ValueError("arena_learning_outcome_predates_trial")
            record = o.to_dict()
            # A human close is a verified observation, not a recommendation
            # to imitate. The user's INTENT cannot be inferred from PnL sign.
            record["learning_provenance"] = "human_manual_exit" if o.is_manual else "model_or_risk_exit"
            record["user_reason"] = None
            record["user_reason_status"] = "AWAITING_USER_ANNOTATION" if o.is_manual else "NOT_APPLICABLE"
            record["eligible_for_automatic_promotion"] = False
            outcomes.append(record)
        # Manual reasons are stored in their own hash-chained append-only file.
        # Link every annotation to a verified manual close before exporting any
        # human reason. Private free-text notes are NOT copied to this bundle.
        annotations = read_annotations(plan)
        annotation_meta = attach_verified_human_reasons(
            outcomes, close_events, annotations, provider=plan.provider,
            run_id=plan.run_id, trial_start_ms=t0, now_ms=now_ms,
        )
        if read_annotations(plan) != annotations:
            raise ValueError("arena_learning_annotation_changed_during_read")
        # Re-check the journal after gathering data: fail if a position opened
        # or closed while we were reading, rather than exporting mixed epochs.
        journal.verify_chain(expected_count=count, expected_head=head)
        if len(outcomes) != kinds["paper_close"]:
            raise ValueError("arena_learning_close_count_mismatch")
        archive[plan.provider] = {
            "run_id": plan.run_id,
            "model": plan.model,
            "source_journal": str(plan.journal),
            "chain_head": head,
            "source_event_count": count,
            "event_kind_counts": dict(sorted(kinds.items())),
            "open_position_ids": list(report.open_position_ids),
            "decisions": decisions,
            "closed_outcomes": outcomes,
            "manual_closed_count": sum(o.is_manual for o in report.outcomes),
            **annotation_meta,
        }
    summary = {
        "schema": "arena_learning_evidence_v2",
        "mode": "paper",
        "trial_start_ms": t0,
        "generated_at_ms": now_ms,
        "status": "OFFLINE_RESEARCH_ONLY_NOT_APPLIED_TO_MODELS",
        "provider_order": list(PROVIDERS),
        "providers": archive,
    }
    digest_input = json.dumps(summary, sort_keys=True, ensure_ascii=True,
                              allow_nan=False, separators=(",", ":"))
    summary["evidence_sha256"] = sha256(digest_input.encode("utf-8")).hexdigest()
    return summary
