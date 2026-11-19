"""Attestazione di un input: prova che il file letto dal builder e' ESATTAMENTE una copia di Fase 0 riuscita e verificata.

Il flag `verified` scritto a mano in una spec NON vale nulla (fail-closed). Un input e' "attestato" solo se:
1. esiste un'attestazione `phase0_attestation_v1` generata da `build_attestation` (snapshot_log.json completo + report di audit);
2. TUTTI gli item della copia risultano `OK` e l'audit non e' FAIL;
3. lo SHA-256 di OGNI file dell'input coincide con uno SHA-256 attestato.
Limite dichiarato: l'attestazione e' affidabile quanto chi la genera; non e' una firma. Non certifica il backup
(`certifies_backup` resta falso finche' non esiste una copia fuori host con ripristino indipendente).
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

KIND = "phase0_attestation_v1"
OK_AUDIT = ("PASS", "WARN")


def _sha_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def build_attestation(snapshot_log_path: str, audit_report_path: Optional[str] = None) -> dict:
    with open(snapshot_log_path, encoding="utf-8") as fh:
        log = json.load(fh)
    items = log.get("items")
    if not isinstance(items, list) or not items or not log.get("complete"):
        raise ValueError("snapshot_not_complete")
    files = {}
    for it in items:
        if it.get("status") != "OK" or not isinstance(it.get("sha256"), str) or len(it["sha256"]) != 64:
            raise ValueError("snapshot_item_not_ok")
        files[it["sha256"]] = {"status": "OK"}
    verdict = None
    if audit_report_path:
        with open(audit_report_path, encoding="utf-8") as fh:
            verdict = json.load(fh).get("verdict")
    return {"kind": KIND, "snapshot_log_sha256": _sha_file(snapshot_log_path), "files": files, "audit_verdict": verdict,
            "certifies_backup": False}


def check(att: object, file_shas: list) -> tuple:
    """(attestato, motivo). `file_shas` = SHA-256 di tutti i file letti dall'input."""
    if not isinstance(att, dict) or att.get("kind") != KIND:
        return False, "attestation_invalid"
    if att.get("audit_verdict") not in OK_AUDIT:
        return False, "audit_not_passed"
    if not file_shas:
        return False, "input_without_files"
    files = att.get("files")
    if not isinstance(files, dict):
        return False, "attestation_invalid"
    for sha in file_shas:
        if files.get(sha, {}).get("status") != "OK":
            return False, "file_hash_not_attested"
    return True, "attested"
