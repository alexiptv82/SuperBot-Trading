"""Criteri UNIFORMI di ammissione al training supervisionato.

Il dataset COMPLETO (`examples.jsonl`) conserva tutto: perdite, NO_TRADE, rifiuti, chiusure manuali, posizioni aperte,
duplicati, esempi non verificati. Solo una parte e' `eligible_for_training`: split, sufficienza e qualunque consumatore
devono usare QUESTO campo, mai filtri propri. Ogni riga esclusa riporta i motivi (`ineligible_reasons`).
"""
from __future__ import annotations

REASONS = ("duplicate", "synthetic", "input_not_attested", "provenance_not_anchored", "schema_unverified", "no_features", "label_incomplete",
           "open_censored", "unknown_pnl", "manual_close_not_imitable", "decision_link_untrusted",
           "ambiguous_feature_link", "market_data_unattested", "snapshot_unverified", "semantic_not_certified")
# Decisione del proprietario (20/11/2026): gli archivi classici Falco (hawk) e Toro (bull) sono conservati integralmente
# ma NON certificati semanticamente (contabilita' e storico non riconciliati con lo stato, anomalie registrate nel
# ramo diario). Le loro righe restano nel dataset ma non sono mai ammesse al training automatico. Revocabile solo con
# una nuova decisione esplicita del proprietario (modifica di codice revisionata, mai un flag della spec).
SEMANTIC_NOT_CERTIFIED_SOURCES = ("falco", "toro")
_BLOCKING_FLAGS = ("ambiguous_feature_link", "market_data_unattested", "snapshot_unverified")

# Tre stati DISTINTI per ogni riga (tutte le righe restano nel dataset, nessuna viene cancellata):
#   verified    nessun motivo di esclusione: CANDIDATA al training. Non e' un'autorizzazione ad addestrare.
#   unverified  manca soltanto un'attestazione o una provenienza che potrebbe arrivare (Fase 0, ancore, candele).
#   excluded    difetto strutturale che nessuna attestazione risolve (duplicato, sintetico, etichetta incompleta,
#               posizione aperta, PnL ignoto, chiusura manuale, legame decisione o feature non affidabile, archivio
#               classico non certificato semanticamente).
UNVERIFIED_REASONS = ("input_not_attested", "provenance_not_anchored", "schema_unverified", "market_data_unattested",
                      "snapshot_unverified")
EXCLUDED_REASONS = tuple(x for x in REASONS if x not in UNVERIFIED_REASONS)
DATA_STATUSES = ("verified", "unverified", "excluded")


def data_status(reasons_: list) -> str:
    if any(x in EXCLUDED_REASONS for x in reasons_):
        return "excluded"
    return "unverified" if reasons_ else "verified"


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
    if row.get("source_system") in SEMANTIC_NOT_CERTIFIED_SOURCES:
        r.append("semantic_not_certified")
    return r
