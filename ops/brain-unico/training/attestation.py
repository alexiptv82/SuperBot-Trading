"""Attestazione di un input: prova che i file letti dal builder sono ESATTAMENTE copie di una run Fase 0 sigillata riuscita.

Il flag `verified` della spec NON vale nulla (fail-closed). Un'attestazione (`phase0_attestation_v2`) si costruisce SOLO
da una directory di run del bundle sigillato (`full`, verdetto `SNAPSHOT_GO`) e lega fra loro, ricalcolandoli, quattro file:

  public/summary.json                  run_id = nome della directory, mode=full, snapshot/manifest completi, audit PASS/WARN
  private/snapshot/snapshot_log.json   snapshot completo, ogni item OK con SHA-256, conteggi = summary
  private/reports/manifest.json        digest RICALCOLATO dalle entry = manifest_digest = summary; ogni item vi compare
  private/reports/audit.json           verdetto = summary; digest delle teste di catena RICALCOLATO = summary.anchors_digest

`check` ricostruisce l'attestazione dalla directory della run (un JSON modificato a mano non basta) e confronta gli
SHA-256 dei file dell'input. Esiti (stato, motivo):

  attested                 hash coincidenti E `summary.json` coincide con un'ANCORA ESTERNA {run_id: sha256} registrata
                           dall'operatore al momento della run (non dalla spec ne' dall'agente che costruisce il dataset)
  hash_matched_untrusted   tutto coerente ma senza ancora esterna: NON ammesso al training
  not_certified            qualunque altro caso (motivo specifico)

Limite dichiarato: l'ancora vale quanto la sua registrazione; non e' una firma. Non certifica il backup
(`certifies_backup` resta falso finche' non esiste una copia fuori host con ripristino indipendente).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Optional

KIND = "phase0_attestation_v2"
LEGACY_KINDS = ("phase0_attestation_v1",)
OK_AUDIT = ("PASS", "WARN")
RUN_ID_RE = re.compile(r"run-[0-9]{8}T[0-9]{6}Z-[A-Za-z0-9]{1,16}")
SHA_RE = re.compile(r"[0-9a-f]{64}")
PATHS = {"summary": ("public", "summary.json"), "snapshot_log": ("private", "snapshot", "snapshot_log.json"),
         "manifest": ("private", "reports", "manifest.json"), "audit": ("private", "reports", "audit.json")}
ATTESTED, UNTRUSTED, NOT_CERTIFIED = "attested", "hash_matched_untrusted", "not_certified"


class AttestationError(ValueError):
    pass


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _load(run_dir: str, key: str) -> tuple:
    path = os.path.join(run_dir, *PATHS[key])
    try:
        if os.path.islink(path) or not os.path.isfile(path):
            raise AttestationError(f"{key}_missing")
        with open(path, "rb") as fh:
            raw = fh.read()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        if isinstance(exc, AttestationError):
            raise
        raise AttestationError(f"{key}_unreadable") from None
    if not isinstance(data, dict):
        raise AttestationError(f"{key}_invalid")
    return data, _sha_bytes(raw)


def manifest_digest(entries: list) -> str:
    """Stessa formula di `inventory.build` (solo entry con sha256, ordinate per path)."""
    hashed = sorted((e for e in entries if isinstance(e, dict) and "sha256" in e), key=lambda d: d["path"])
    canon = json.dumps([(e["path"], e["bytes"], e["sha256"]) for e in hashed], separators=(",", ":"))
    return _sha_bytes(canon.encode())


def anchors_digest(v3_chains: dict) -> str:
    """Stessa formula di `sealed_root.execute` (teste delle catene v3 dall'audit)."""
    return _sha_bytes(json.dumps(sorted((k, v["count"], v["head"]) for k, v in v3_chains.items()),
                                 separators=(",", ":")).encode())


def build_attestation(run_dir: str) -> dict:
    """Solleva AttestationError (motivo nel messaggio) se la run non e' una `full` riuscita e coerente."""
    run_dir = os.path.abspath(run_dir)
    run_id = os.path.basename(run_dir)
    if not RUN_ID_RE.fullmatch(run_id):
        raise AttestationError("run_id_invalid")
    summ, summ_sha = _load(run_dir, "summary")
    log, log_sha = _load(run_dir, "snapshot_log")
    man, man_sha = _load(run_dir, "manifest")
    aud, aud_sha = _load(run_dir, "audit")
    if summ.get("run_id") != run_id:
        raise AttestationError("summary_run_id_mismatch")
    if summ.get("mode") != "full" or summ.get("verdict") != "SNAPSHOT_GO":
        raise AttestationError("run_not_a_successful_full")
    if summ.get("certifies_backup") is not False:
        raise AttestationError("summary_invalid")
    s_snap, s_man, s_aud = summ.get("snapshot") or {}, summ.get("manifest") or {}, summ.get("audit") or {}
    items = log.get("items")
    if not isinstance(items, list) or not items or log.get("complete") is not True or s_snap.get("complete") is not True:
        raise AttestationError("snapshot_not_complete")
    files = {}
    for it in items:
        if not isinstance(it, dict) or it.get("status") != "OK" or not SHA_RE.fullmatch(str(it.get("sha256", ""))):
            raise AttestationError("snapshot_item_not_ok")
        files[it["sha256"]] = {"status": "OK"}
    if s_snap.get("items") != len(items) or s_snap.get("items_ok") != len(items):
        raise AttestationError("snapshot_counts_mismatch")
    entries = man.get("entries")
    if not isinstance(entries, list) or man.get("complete") is not True or man.get("unstable_count") != 0:
        raise AttestationError("manifest_not_complete")
    if s_man.get("complete") is not True or s_man.get("unstable_count") != 0:
        raise AttestationError("manifest_not_complete")
    try:
        md = manifest_digest(entries)
    except (KeyError, TypeError):
        raise AttestationError("manifest_invalid") from None
    if not (md == man.get("manifest_digest") == s_man.get("manifest_digest")):
        raise AttestationError("manifest_digest_mismatch")
    man_shas = {e.get("sha256") for e in entries if isinstance(e, dict)}
    if not set(files) <= man_shas:
        raise AttestationError("snapshot_items_not_in_manifest")
    verdict = aud.get("verdict")
    if verdict not in OK_AUDIT or s_aud.get("verdict") != verdict:
        raise AttestationError("audit_not_passed_or_mismatch")
    try:
        chains = aud["checks"]["v3_chains"]
        ad = anchors_digest(chains)
    except (KeyError, TypeError, AttributeError):
        raise AttestationError("audit_invalid") from None
    if ad != s_aud.get("anchors_digest") or s_aud.get("v3_chains_ok") != s_aud.get("v3_chains_total") \
            or not all(isinstance(v, dict) and v.get("ok") for v in chains.values()):
        raise AttestationError("audit_chain_mismatch")
    return {"kind": KIND, "run_id": run_id, "run_dir": run_dir, "code_sha256": summ.get("code_sha256"),
            "summary_sha256": summ_sha, "snapshot_log_sha256": log_sha, "manifest_sha256": man_sha, "audit_sha256": aud_sha,
            "audit_verdict": verdict, "files": files, "certifies_backup": False}


def load_anchors(path: Optional[str]) -> dict:
    """Ancore esterne {run_id: sha256 di public/summary.json}. Formato rigoroso: altrimenti ValueError."""
    if not path:
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not all(RUN_ID_RE.fullmatch(str(k)) and SHA_RE.fullmatch(str(v)) for k, v in data.items()):
        raise ValueError("anchors_invalid")
    return dict(data)


def check(att: object, file_shas: list, anchors: Optional[dict] = None) -> tuple:
    """(stato, motivo). `file_shas` = SHA-256 di tutti i file letti dall'input; `anchors` = ancore esterne."""
    if isinstance(att, dict) and att.get("kind") in LEGACY_KINDS:
        return NOT_CERTIFIED, "attestation_legacy_unbound"
    if not isinstance(att, dict) or att.get("kind") != KIND or not isinstance(att.get("run_dir"), str):
        return NOT_CERTIFIED, "attestation_invalid"
    if not file_shas:
        return NOT_CERTIFIED, "input_without_files"
    try:
        fresh = build_attestation(att["run_dir"])                 # mai fidarsi del contenuto del JSON: si ricalcola
    except AttestationError as exc:
        return NOT_CERTIFIED, "run_" + str(exc)
    if fresh != att:
        return NOT_CERTIFIED, "attestation_stale_or_tampered"
    for sha in file_shas:
        if fresh["files"].get(sha, {}).get("status") != "OK":
            return NOT_CERTIFIED, "file_hash_not_attested"
    if (anchors or {}).get(fresh["run_id"]) != fresh["summary_sha256"]:
        return UNTRUSTED, "no_external_anchor" if fresh["run_id"] not in (anchors or {}) else "external_anchor_mismatch"
    return ATTESTED, "attested"


def main(argv: Optional[list] = None) -> int:
    """python3 attestation.py RUN_DIR --out ATTESTAZIONE.json (file nuovo, 0600). Stampa run_id e sha256 di summary.json:
    l'operatore li confronta con quelli registrati al momento della run (ancora esterna) prima di usarli in `--anchors`."""
    import argparse
    ap = argparse.ArgumentParser(description="attestazione phase0_attestation_v2 da una run sigillata `full`")
    ap.add_argument("run_dir")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        att = build_attestation(a.run_dir)
        fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except (AttestationError, OSError) as exc:
        print(f"NO-GO: {type(exc).__name__}: {str(exc)[:80]}")
        return 1
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(att, fh, indent=1, sort_keys=True)
    print(f"OK: run_id={att['run_id']} summary_sha256={att['summary_sha256']} files={len(att['files'])} "
          f"(NON attestato finche' l'ancora esterna non coincide)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
