"""Criteri UNIFORMI di ammissione al training supervisionato.

Il dataset COMPLETO (`examples.jsonl`) conserva tutto: perdite, NO_TRADE, rifiuti, chiusure manuali, posizioni aperte,
duplicati, esempi non verificati. Solo una parte e' `eligible_for_training`: split, sufficienza e qualunque consumatore
devono usare QUESTO campo, mai filtri propri. Ogni riga esclusa riporta i motivi (`ineligible_reasons`).
"""
from __future__ import annotations

REASONS = ("duplicate", "synthetic", "input_not_attested", "provenance_not_anchored", "schema_unverified", "no_features", "label_incomplete",
           "open_censored", "unknown_pnl", "manual_close_not_imitable", "decision_link_untrusted",
           "ambiguous_feature_link", "market_data_unattested", "snapshot_unverified")
_BLOCKING_FLAGS = ("ambiguous_feature_link", "market_data_unattested", "snapshot_unverified")


def reasons(row: dict, attested_inputs: set, untrusted_inputs: frozenset = frozenset()) -> list:
    """`untrusted_inputs`: input con hash coincidenti ma SENZA ancora esterna (`hash_matched_untrusted`): non ammessi."""
    r = []
    p, o = row["provenance"], row["outcome"]
    if p.get("duplicate_of"):
        r.append("duplicate")
    if row["is_synthetic"]:
        r.append("synthetic")
    if p["input_id"] in untrusted_inputs and p["input_id"] not in attested_inputs:
        r.append("provenance_not_anchored")
    elif p["input_id"] not in attested_inputs:
        r.append("input_not_attested")
    if p.get("schema_unverified"):
        r.append("schema_unverified")
    if row["features"] is None:
        r.append("no_features")
    if not row["label_complete"]:
        r.append("label_incomplete")
    if o["status"] == "open_censored":
        r.append("open_censored")
    if o["status"] == "closed_unknown_pnl":
        r.append("unknown_pnl")
    if o.get("is_manual"):
        r.append("manual_close_not_imitable")
    if p.get("link_status") in ("unlinked", "dangling"):
        r.append("decision_link_untrusted")
    for f in _BLOCKING_FLAGS:
        if f in row["quality_flags"]:
            r.append(f)
    return r
