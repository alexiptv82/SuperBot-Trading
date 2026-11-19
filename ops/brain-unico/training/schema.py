"""Schema versionato del Training Dataset di Brain Unico (solo libreria standard, nessuna rete).

Un esempio = UNA decisione (eseguita o no), con:
- identita' e provenienza (sistema, run, riga sorgente, hash dell'input);
- feature note AL MOMENTO della decisione e la loro origine dichiarata;
- esito reale (se eseguita) con costi, MFE/MAE, motivo di uscita, flag `manual`;
- etichette forward da candele chiuse (anche per NO_TRADE e rifiuti: "come sarebbe andata").

Regole non negoziabili (verificate dai test):
1. Nessun look-ahead: le feature usano solo candele chiuse prima della decisione.
2. Mai interpolare: se manca una candela l'etichetta e' `complete=false`, non un numero.
3. Perdite, NO_TRADE, rifiuti e chiusure manuali RESTANO nel dataset (non si filtrano per "pulirlo").
4. Un trade sintetico non e' mai un esempio reale: `is_synthetic` deve essere sempre false nei dati veri.
5. Nessun testo libero dei modelli o dell'utente nel dataset: solo codici brevi e numeri.
"""
from __future__ import annotations

import hashlib
import math
import time
from typing import Any

SCHEMA_VERSION = 2
BUILDER_VERSION = "0.3.0"
SOURCES = ("falco", "toro", "brain_storico", "arena_deepseek", "arena_qwen", "arena_minimax")
RECORD_KINDS = ("executed", "candidate_rejected", "no_trade")
ACTIONS = ("LONG", "SHORT", "NO_TRADE", "OPEN_REJECTED")
OUTCOME_STATUS = ("closed", "closed_unknown_pnl", "open_censored", "not_executed")
LABEL_ORIGINS = ("realized_outcome", "counterfactual_simulation", "censored", "unknown_pnl")
FEATURE_SOURCES = ("logged_at_decision", "reconstructed_from_candles", "none")
MFE_SOURCES = ("logged", "approximate_candles", "none")
KNOWN_EXIT = frozenset({"stop", "take_profit", "timeout", "manual", "liquidation", "brain_close", "tp", "sl",
                        "ai_close", "trailing", "unknown"})

REQUIRED = ("schema_version", "example_id", "source_system", "source_run", "source_kind", "record_kind",
            "decision_ts_ms", "decision_day", "symbol", "action", "side", "executed", "features", "feature_source",
            "proposal", "outcome", "labels", "label_complete", "horizons_complete", "label_origin", "quality_flags",
            "eligible_for_training", "ineligible_reasons", "is_synthetic", "provenance")


def example_id(source_system: str, source_run: str, record_kind: str, source_key: str) -> str:
    raw = "|".join((source_system, source_run, record_kind, source_key)).encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def utc_day(ms: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))


def short_code(text: Any, limit: int = 40) -> str:
    """Riduce un motivo testuale a un codice breve [a-z0-9_:-] (niente testo libero nel dataset)."""
    s = str(text or "").lower().split(":")[0].strip()
    out = "".join(c if c.isalnum() or c in "_-" else "_" for c in s)[:limit].strip("_")
    return out or "unknown"


def _finite(x: Any) -> bool:
    return x is None or (isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x))


def _scan(obj: Any, path: str, errs: list) -> None:
    if isinstance(obj, float) and not math.isfinite(obj):
        errs.append(f"non_finite:{path}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _scan(v, f"{path}.{k}", errs)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _scan(v, f"{path}[{i}]", errs)


def validate_row(r: dict) -> list:
    """Elenco di errori (vuoto = valida). Controlla struttura, enumerazioni e coerenze logiche."""
    e: list[str] = []
    for k in REQUIRED:
        if k not in r:
            e.append(f"missing:{k}")
    if e:
        return e
    if r["schema_version"] != SCHEMA_VERSION:
        e.append("schema_version")
    if r["source_system"] not in SOURCES:
        e.append("source_system")
    if r["record_kind"] not in RECORD_KINDS:
        e.append("record_kind")
    if r["action"] not in ACTIONS:
        e.append("action")
    if type(r["decision_ts_ms"]) is not int or r["decision_ts_ms"] <= 0:
        e.append("decision_ts_ms")
    elif r["decision_day"] != utc_day(r["decision_ts_ms"]):
        e.append("decision_day")
    if r["side"] not in (-1, 0, 1) or (r["action"] == "LONG") != (r["side"] == 1) or (r["action"] == "SHORT") != (r["side"] == -1):
        e.append("side_action_mismatch")
    if r["feature_source"] not in FEATURE_SOURCES:
        e.append("feature_source")
    if (r["features"] is None) != (r["feature_source"] == "none"):
        e.append("features_vs_source")
    o = r["outcome"]
    if not isinstance(o, dict) or o.get("status") not in OUTCOME_STATUS:
        e.append("outcome_status")
    else:
        if r["executed"] != (o["status"] != "not_executed"):
            e.append("executed_vs_outcome")
        if o["status"] == "closed" and (o.get("net_pnl") is None or o.get("closed_ms") is None):
            e.append("closed_without_result")
        if o["status"] != "closed" and o.get("net_pnl") is not None:
            e.append("result_without_close")
        if o.get("mfe_mae_source") not in MFE_SOURCES:
            e.append("mfe_mae_source")
        if o["status"] != "not_executed" and r["record_kind"] != "executed":
            e.append("kind_vs_outcome")
    if r["record_kind"] == "executed" and not r["executed"]:
        e.append("executed_kind_not_executed")
    if r["is_synthetic"] is not False:
        e.append("synthetic_example")
    if not isinstance(r["label_complete"], bool) or not isinstance(r["horizons_complete"], bool):
        e.append("label_complete")
    if r["label_origin"] not in LABEL_ORIGINS:
        e.append("label_origin")
    if not isinstance(r["quality_flags"], list) or any(not isinstance(x, str) for x in r["quality_flags"]):
        e.append("quality_flags")
    if (not isinstance(r["eligible_for_training"], bool) or not isinstance(r["ineligible_reasons"], list)
            or r["eligible_for_training"] != (not r["ineligible_reasons"])):
        e.append("eligibility_inconsistent")
    for k in ("proposal", "labels", "provenance"):
        if not isinstance(r[k], dict):
            e.append(k)
    _scan(r, "row", e)
    return e
