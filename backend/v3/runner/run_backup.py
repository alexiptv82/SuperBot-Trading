"""Backup A CALDO della cartella dati del Brain Unico e PROVA DI RIPRISTINO (la memoria non si cancella, non si riscrive).

* ``journal.db`` e ``budget.db``: API di backup SQLite (copia coerente, include il WAL gia' confermato) con la sorgente
  aperta in SOLA LETTURA; poi ``integrity_check``; per il journal anche la verifica completa della catena di hash.
* file piccoli dello stato (mandato, configurazione, latch della perdita giornaliera, battiti, pausa, risultati di
  chiusura): copiati come sono, se presenti. I lock non si copiano.
* ``backup_manifest.json``: SHA-256 di ogni file, numero di eventi e testa della catena del journal.

``verify_restore`` copia il backup in una cartella NUOVA e verifica: impronte uguali al manifest, catena del journal
uguale (stesso numero di eventi e stessa testa: nessun troncamento), basi SQLite integre, latch leggibile.

Nessuna rete, nessuna scrittura nella sorgente, nessun servizio fermato. Destinazioni sempre NUOVE: mai sovrascrivere.

ATTENZIONE, due fasi distinte: ``backup`` scrive COPIE IN CHIARO dei database e dei file di stato nella cartella di
destinazione (proteggerla: utente dedicato, permessi 0700); solo ``encrypt`` poi cifra in streaming (tar | age) senza
creare ALTRE copie in chiaro. Le copie in chiaro vanno cancellate dopo le verifiche. Per l'esecuzione amministrativa
sui dati reali usare lo script autonomo ``ops/brain-unico/backup/brain_run_backup_root.py`` (lavora in una cartella
0700 e cancella da se' le copie in chiaro).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

from backend.v3.events import EventJournal

SCHEMA = "brain_unico_run_backup_v1"
SQLITE_FILES = ("journal.db", "budget.db")
PLAIN_FILES = ("mandate.json", "runner_config.json", "daily_loss.json", "heartbeat.json", "exit_heartbeat.json",
               "pause.flag", "close_request.json", "close_result.json", "PREPARED_PAUSED_ONLY.json")
MANIFEST = "backup_manifest.json"


class BackupError(Exception):
    pass


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sqlite_copy(src: Path, dst: Path) -> None:
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(dst)
        try:
            source.backup(target)
            ok = target.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            target.close()
    finally:
        source.close()
    if ok != "ok":
        raise BackupError(f"integrity_check_failed:{dst.name}")


def _new_dir(path: Path) -> None:
    if path.exists():
        raise BackupError("destination_exists")
    path.mkdir(parents=True)


def backup(src: Path, dst: Path) -> dict:
    """Backup coerente di ``src`` in ``dst`` (nuova). Restituisce il manifest."""
    src, dst = Path(src), Path(dst)
    if not (src / "journal.db").is_file():
        raise BackupError("journal_missing")
    if dst.resolve() == src.resolve() or src.resolve() in dst.resolve().parents:
        raise BackupError("destination_inside_source")
    _new_dir(dst)
    files = {}
    for name in SQLITE_FILES:
        if (src / name).is_file():
            _sqlite_copy(src / name, dst / name)
            files[name] = _sha(dst / name)
    for name in PLAIN_FILES:
        p = src / name
        if p.is_file() and not p.is_symlink():
            shutil.copy2(p, dst / name)
            files[name] = _sha(dst / name)
    try:
        count, head = EventJournal(dst / "journal.db").verify_chain()
    except ValueError as exc:
        raise BackupError(f"journal_chain_invalid:{exc}") from None
    manifest = {"schema": SCHEMA, "files": dict(sorted(files.items())), "journal_events": count, "journal_head": head}
    (dst / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return manifest


def verify_restore(backup_dir: Path, restore_dir: Path) -> dict:
    """Ripristina in ``restore_dir`` (nuova) e verifica tutto contro il manifest. Restituisce un rapporto."""
    backup_dir, restore_dir = Path(backup_dir), Path(restore_dir)
    try:
        manifest = json.loads((backup_dir / MANIFEST).read_text())
    except (OSError, ValueError):
        raise BackupError("manifest_unreadable") from None
    if manifest.get("schema") != SCHEMA or not isinstance(manifest.get("files"), dict):
        raise BackupError("manifest_invalid")
    _new_dir(restore_dir)
    for name, sha in manifest["files"].items():
        if "/" in name or name not in SQLITE_FILES + PLAIN_FILES:
            raise BackupError("manifest_unexpected_file")
        shutil.copy2(backup_dir / name, restore_dir / name)
        if _sha(restore_dir / name) != sha:
            raise BackupError(f"hash_mismatch:{name}")
    extra = {p.name for p in backup_dir.iterdir()} - set(manifest["files"]) - {MANIFEST}
    if extra:
        raise BackupError("unlisted_files_in_backup")
    try:
        count, head = EventJournal(restore_dir / "journal.db").verify_chain(
            expected_count=manifest["journal_events"], expected_head=manifest["journal_head"])
    except (ValueError, KeyError) as exc:
        raise BackupError(f"journal_restore_mismatch:{exc}") from None
    for name in SQLITE_FILES:
        if (restore_dir / name).is_file():
            con = sqlite3.connect(f"file:{restore_dir / name}?mode=ro", uri=True)
            try:
                if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise BackupError(f"integrity_check_failed:{name}")
            finally:
                con.close()
    if (restore_dir / "daily_loss.json").is_file():
        try:
            json.loads((restore_dir / "daily_loss.json").read_text())
        except ValueError:
            raise BackupError("daily_loss_state_unreadable") from None
    return {"restored": True, "journal_events": count, "journal_head": head,
            "files": len(manifest["files"]), "restore_dir": str(restore_dir)}


def encrypt(backup_dir: Path, out_file: Path, recipient_file: Path) -> str:
    """Archivio tar del backup cifrato con age per i destinatari del file indicato (chiavi PUBBLICHE). Il file in
    chiaro non viene mai scritto: tar | age. Restituisce lo SHA-256 del file cifrato. Nessun trasferimento."""
    import subprocess
    backup_dir, out_file, recipient_file = Path(backup_dir), Path(out_file), Path(recipient_file)
    if not (backup_dir / MANIFEST).is_file():
        raise BackupError("not_a_backup")
    if out_file.exists():
        raise BackupError("destination_exists")
    if not recipient_file.is_file():
        raise BackupError("recipient_missing")
    tar = subprocess.Popen(["tar", "-C", str(backup_dir.parent), "-cf", "-", backup_dir.name], stdout=subprocess.PIPE)
    try:
        age = subprocess.run(["age", "-R", str(recipient_file), "-o", str(out_file)], stdin=tar.stdout,
                             capture_output=True, timeout=600)
    finally:
        tar.stdout.close()
        tar_rc = tar.wait()
    if tar_rc != 0 or age.returncode != 0 or not out_file.is_file():
        if out_file.exists():
            out_file.unlink()
        raise BackupError("encryption_failed")
    return _sha(out_file)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Backup e prova di ripristino della cartella dati del Brain Unico")
    ap.add_argument("--source", required=True)
    ap.add_argument("--dest", required=True, help="cartella NUOVA per il backup")
    ap.add_argument("--restore-test", help="cartella NUOVA dove provare il ripristino")
    ap.add_argument("--encrypt-to", help="file con le chiavi PUBBLICHE age dei destinatari")
    ap.add_argument("--encrypted-out", help="file NUOVO .tar.age")
    a = ap.parse_args(argv)
    try:
        m = backup(Path(a.source), Path(a.dest))
        print(f"BACKUP: eventi={m['journal_events']} testa={m['journal_head'][:16]} file={len(m['files'])}")
        if a.restore_test:
            r = verify_restore(Path(a.dest), Path(a.restore_test))
            print(f"RIPRISTINO VERIFICATO: eventi={r['journal_events']} file={r['files']}")
        if a.encrypt_to and a.encrypted_out:
            print(f"CIFRATO: {a.encrypted_out} sha256={encrypt(Path(a.dest), Path(a.encrypted_out), Path(a.encrypt_to))}")
    except BackupError as exc:
        print(f"NO-GO: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
