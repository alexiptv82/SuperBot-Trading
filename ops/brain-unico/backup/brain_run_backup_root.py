#!/usr/bin/env python3
"""Backup cifrato della cartella dati di UNA run Brain, pensato per un'unica esecuzione amministrativa.

Autonomo: solo libreria standard + i comandi `tar`, `age`, `age-keygen`. NON importa codice del repository.
Nessuna rete, nessun servizio fermato, la sorgente si apre SOLO in lettura. Nessun permesso viene cambiato.

Fasi (distinte):
  1. COPIE IN CHIARO TEMPORANEE: dentro una cartella di lavoro nuova con permessi 0700 (umask 077): backup SQLite
     coerente (sorgente `mode=ro`) di journal.db/budget.db, `PRAGMA integrity_check`, copia dei soli file di stato
     ammessi (mai lock), manifest SHA-256 con numero di eventi e testa della catena del journal (ricalcolata).
  2. PROVA DI RIPRISTINO IN CHIARO: copia in una sottocartella nuova, impronte = manifest, catena ricontata = manifest,
     integrity_check.
  3. CIFRATURA IN STREAMING: `tar | age` verso la chiave PUBBLICA approvata (file destinatari) + una chiave di PROVA
     effimera generata nella cartella di lavoro; nessun chiaro aggiuntivo su disco.
  4. PROVA DEL FILE CIFRATO: decifrato con la chiave effimera in una sottocartella nuova -> impronte e catena = manifest.
  5. PULIZIA: cancellata l'intera cartella di lavoro (copie in chiaro e chiave effimera). Restano solo
     `<nome>.tar.age` e `<nome>.manifest.json` (nomi di file, impronte, conteggi: nessun contenuto, nessun segreto).
Nota: la cancellazione e' quella del filesystem (nessuna sovrascrittura sicura garantita).

Modalita' di verifica (sul PC del proprietario, con la SUA chiave privata):
  python3 brain_run_backup_root.py verify --input X.tar.age --manifest X.manifest.json --identity chiave.txt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCHEMA = "brain_run_encrypted_backup_v1"
SQLITE_FILES = ("journal.db", "budget.db")
STATE_FILES = ("mandate.json", "runner_config.json", "daily_loss.json", "heartbeat.json", "exit_heartbeat.json",
               "pause.flag", "close_request.json", "close_result.json", "PREPARED_PAUSED_ONLY.json")
GENESIS = "0" * 64


class Fail(Exception):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(previous: str, row: tuple) -> str:
    """Stessa regola di backend/v3/events.py::_digest (verificata da un test del repository)."""
    _seq, event_id, portfolio_id, run_id, kind, occurred_at_ms, source, payload_json = row[:8]
    fields = [previous, event_id, portfolio_id, run_id, kind, str(occurred_at_ms), source, payload_json]
    return hashlib.sha256(json.dumps(fields, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def chain(db_path: Path) -> tuple:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        prev, count = GENESIS, 0
        for row in con.execute("SELECT seq,event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,"
                               "previous_hash,event_hash FROM v3_events ORDER BY seq"):
            if row[8] != prev or row[9] != digest(prev, row):
                raise Fail("journal_hash_chain_invalid")
            prev, count = row[9], count + 1
        return count, prev
    finally:
        con.close()


def integrity(db_path: Path) -> None:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise Fail(f"integrity_check_failed:{db_path.name}")
    finally:
        con.close()


def check_copy(folder: Path, manifest: dict) -> None:
    for name, sha in manifest["files"].items():
        if sha256(folder / name) != sha:
            raise Fail(f"hash_mismatch:{name}")
    if chain(folder / "journal.db") != (manifest["journal_events"], manifest["journal_head"]):
        raise Fail("journal_does_not_match_manifest")
    for name in SQLITE_FILES:
        if (folder / name).is_file():
            integrity(folder / name)


def recipients_ok(path: Path) -> None:
    lines = [l.strip() for l in path.read_text().splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines or any(not l.startswith("age1") or " " in l for l in lines):
        raise Fail("recipient_file_must_contain_only_age_public_keys")


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, timeout=1800, **kw)
    if r.returncode != 0:
        raise Fail(f"command_failed:{cmd[0]}")
    return r


def backup(source: Path, out_dir: Path, recipient_file: Path, name: str) -> dict:
    source, out_dir, recipient_file = Path(source), Path(out_dir), Path(recipient_file)
    if not (source / "journal.db").is_file():
        raise Fail("source_has_no_journal")
    if not out_dir.is_dir():
        raise Fail("out_dir_missing")
    if source.resolve() == out_dir.resolve() or source.resolve() in out_dir.resolve().parents:
        raise Fail("out_dir_inside_source")
    recipients_ok(recipient_file)
    out, out_manifest = out_dir / f"{name}.tar.age", out_dir / f"{name}.manifest.json"
    if out.exists() or out_manifest.exists():
        raise Fail("destination_exists")
    os.umask(0o077)
    work = Path(tempfile.mkdtemp(prefix=f".{name}.work-", dir=out_dir))           # 0700
    try:
        snap = work / name
        snap.mkdir()
        files = {}
        for fname in SQLITE_FILES:                                                 # fase 1
            if (source / fname).is_file():
                src = sqlite3.connect(f"file:{source / fname}?mode=ro", uri=True)
                dst = sqlite3.connect(snap / fname)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
                    src.close()
                integrity(snap / fname)
                files[fname] = sha256(snap / fname)
        for fname in STATE_FILES:
            p = source / fname
            if p.is_file() and not p.is_symlink():
                shutil.copy2(p, snap / fname)
                files[fname] = sha256(snap / fname)
        count, head = chain(snap / "journal.db")
        manifest = {"schema": SCHEMA, "name": name, "files": dict(sorted(files.items())),
                    "journal_events": count, "journal_head": head}
        (snap / "backup_manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
        restore = work / "restore"                                                 # fase 2
        shutil.copytree(snap, restore)
        check_copy(restore, manifest)
        eph = work / "ephemeral.key"                                               # fase 3
        run(["age-keygen", "-o", str(eph)])
        eph_pub = run(["age-keygen", "-y", str(eph)], text=True).stdout.strip()
        tar = subprocess.Popen(["tar", "-C", str(work), "-cf", "-", name], stdout=subprocess.PIPE)
        try:
            enc = subprocess.run(["age", "-R", str(recipient_file), "-r", eph_pub, "-o", str(out)],
                                 stdin=tar.stdout, capture_output=True, timeout=1800)
        finally:
            tar.stdout.close()
            tar_rc = tar.wait()
        if tar_rc != 0 or enc.returncode != 0:
            raise Fail("encryption_failed")
        check = work / "check"                                                     # fase 4
        check.mkdir()
        dec = subprocess.Popen(["age", "-d", "-i", str(eph), str(out)], stdout=subprocess.PIPE)
        try:
            untar = subprocess.run(["tar", "-C", str(check), "-xf", "-"], stdin=dec.stdout, capture_output=True,
                                   timeout=1800)
        finally:
            dec.stdout.close()
            dec_rc = dec.wait()
        if dec_rc != 0 or untar.returncode != 0:
            raise Fail("encrypted_file_not_decryptable")
        check_copy(check / name, manifest)
        summary = {**manifest, "encrypted_file": out.name, "encrypted_sha256": sha256(out),
                   "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "verified": ["sqlite_integrity", "journal_chain", "manifest_hashes", "plain_restore",
                                "encrypted_round_trip_ephemeral_key"]}
        out_manifest.write_text(json.dumps(summary, indent=1, sort_keys=True))
        return summary
    except BaseException:
        if out.exists():
            out.unlink()
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)                                    # fase 5: nessun chiaro resta


def verify(encrypted: Path, manifest_file: Path, identity: Path) -> dict:
    manifest = json.loads(Path(manifest_file).read_text())
    if sha256(encrypted) != manifest["encrypted_sha256"]:
        raise Fail("encrypted_file_changed")
    with tempfile.TemporaryDirectory() as tmp:
        os.chmod(tmp, 0o700)
        dec = subprocess.Popen(["age", "-d", "-i", str(identity), str(encrypted)], stdout=subprocess.PIPE)
        try:
            untar = subprocess.run(["tar", "-C", tmp, "-xf", "-"], stdin=dec.stdout, capture_output=True, timeout=1800)
        finally:
            dec.stdout.close()
            dec_rc = dec.wait()
        if dec_rc != 0 or untar.returncode != 0:
            raise Fail("decryption_failed")
        check_copy(Path(tmp) / manifest["name"], manifest)
    return {"verified": True, "journal_events": manifest["journal_events"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--source", required=True)
    b.add_argument("--out-dir", required=True)
    b.add_argument("--recipient-file", required=True)
    b.add_argument("--name", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--input", required=True)
    v.add_argument("--manifest", required=True)
    v.add_argument("--identity", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "backup":
            s = backup(Path(a.source), Path(a.out_dir), Path(a.recipient_file), a.name)
            print(f"OK eventi={s['journal_events']} testa={s['journal_head'][:16]} file={len(s['files'])} "
                  f"cifrato={s['encrypted_file']} sha256={s['encrypted_sha256']}")
        else:
            r = verify(Path(a.input), Path(a.manifest), Path(a.identity))
            print(f"RIPRISTINO DAL FILE CIFRATO VERIFICATO eventi={r['journal_events']}")
    except (Fail, OSError, KeyError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"NO-GO: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
