"""Backup A CALDO delle tre run dell'Arena e verifica del ripristino (memoria: mai cancellata, mai riscritta).

* ``journal.db`` e ``budget.db``: API di backup SQLite (copia coerente che include il contenuto WAL gia' confermato),
  sorgente aperta in sola lettura; poi ``integrity_check`` e, per il journal, verifica della catena di hash.
* registri JSONL append-only (richieste di chiusura, motivi umani, traccia inferenze): copia + verifica della catena;
  se l'ultima riga era a meta' di una scrittura si riprova, mai si "ripara".
* file piccoli (manifest, config, mandato, T0, flag): copiati come sono.
* ``backup_manifest.json``: SHA-256 di ogni file, conteggio e testa della catena del journal.

Nessuna rete, nessuna scrittura nella sorgente, nessun servizio fermato. La cifratura e la copia fuori dal VPS sono
passi separati (vedi matrice d'installazione).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path
from typing import Optional

from backend.v3.arena import manual_close as MC
from backend.v3.arena.prepare import plan_for
from backend.v3.arena.trial_plan import PROVIDERS, WalletPlan
from backend.v3.events import EventJournal

SCHEMA = "arena_run_backup_v1"
SQLITE_FILES = ("journal.db", "budget.db")
CHAINED_JSONL = (MC.REQUESTS_FILE, MC.ANNOTATIONS_FILE)
PLAIN_FILES = ("arena_manifest.json", "runner_config.json", "mandate.json", "arena_t0.json", "pause.flag",
               "PREPARED_PAUSED_ONLY.json", "inference_trace.jsonl", "close_result.json")


class BackupError(Exception):
    pass


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sqlite_copy(src: Path, dst: Path) -> None:
    source = sqlite3.connect(src.as_uri() + "?mode=ro", uri=True, timeout=30)
    target = sqlite3.connect(dst)
    try:
        source.backup(target)                      # pagine coerenti, WAL confermato incluso
        target.execute("PRAGMA journal_mode=DELETE")  # la copia e' un file unico, senza -wal/-shm
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BackupError("sqlite_integrity_failed")
    finally:
        target.close()
        source.close()


def _chained_copy(src: Path, dst: Path, attempts: int = 5) -> int:
    for _ in range(attempts):
        shutil.copyfile(src, dst)
        try:
            return len(MC.read_chain(dst))
        except MC.ArenaCloseError:
            time.sleep(0.05)                       # scrittura in corso: riprova sulla sorgente, non toccarla
    raise BackupError("registry_unreadable")


def snapshot_run(plan: WalletPlan, dest: Path) -> dict:
    src = plan.folder
    if src.is_symlink() or not src.is_dir():
        raise BackupError("run_missing")
    dest.mkdir(parents=True, mode=0o700)
    files = {}
    for name in SQLITE_FILES:
        if (src / name).is_file():
            _sqlite_copy(src / name, dest / name)
    count, head = EventJournal(dest / "journal.db").verify_chain()
    chained = {}
    for name in CHAINED_JSONL:
        if (src / name).is_file():
            chained[name] = _chained_copy(src / name, dest / name)
    for name in PLAIN_FILES:
        p = src / name
        if p.is_file() and not p.is_symlink():
            shutil.copyfile(p, dest / name)
    for p in sorted(dest.iterdir()):
        os.chmod(p, 0o600)
        files[p.name] = _sha(p)
    manifest = {"schema": SCHEMA, "provider": plan.provider, "run_id": plan.run_id, "journal_events": count,
                "journal_head": head, "chained_records": chained, "files_sha256": files,
                "captured_at_ms": int(time.time() * 1000)}
    (dest / "backup_manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=1), encoding="utf-8")
    os.chmod(dest / "backup_manifest.json", 0o600)
    return manifest


def verify_run_backup(dest: Path) -> dict:
    """Verifica indipendente di una copia (anche dopo il trasferimento): hash, integrita', catene."""
    m = json.loads((dest / "backup_manifest.json").read_text(encoding="utf-8"))
    if m.get("schema") != SCHEMA:
        raise BackupError("manifest_invalid")
    present = {p.name for p in dest.iterdir()} - {"backup_manifest.json"}
    if present != set(m["files_sha256"]):
        raise BackupError("file_set_changed")
    for name, digest in m["files_sha256"].items():
        if _sha(dest / name) != digest:
            raise BackupError("hash_mismatch:" + name)
    for name in SQLITE_FILES:
        if (dest / name).is_file():
            con = sqlite3.connect((dest / name).as_uri() + "?mode=ro", uri=True)
            try:
                if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise BackupError("sqlite_integrity_failed:" + name)
            finally:
                con.close()
    EventJournal(dest / "journal.db").verify_chain(expected_count=m["journal_events"], expected_head=m["journal_head"])
    for name, n in m["chained_records"].items():
        if len(MC.read_chain(dest / name)) != n:
            raise BackupError("registry_count_mismatch:" + name)
    return m


def snapshot_all(root: Path, day: date, dest_root: Path) -> dict:
    """Le tre run in una cartella nuova (mai sovrascritta). Restituisce i tre manifest verificati."""
    if dest_root.exists():
        raise BackupError("destination_exists")
    dest_root.mkdir(parents=True, mode=0o700)
    out = {}
    for p in PROVIDERS:
        plan = plan_for(p, day, root)
        target = dest_root / p / plan.run_id
        target.parent.mkdir(mode=0o700)
        snapshot_run(plan, target)
        out[p] = verify_run_backup(target)
    return out


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Backup a caldo / verifica delle tre run PAPER dell'Arena.")
    ap.add_argument("command", choices=("snapshot", "verify"))
    ap.add_argument("--root", default="/opt/superbot-ai-arena-paper")
    ap.add_argument("--day")
    ap.add_argument("--dest", required=True)
    a = ap.parse_args(argv)
    try:
        if a.command == "snapshot":
            res = snapshot_all(Path(a.root), date.fromisoformat(a.day), Path(a.dest))
        else:
            res = {p.name: verify_run_backup(next(p.iterdir())) for p in sorted(Path(a.dest).iterdir()) if p.is_dir()}
    except (BackupError, MC.ArenaCloseError, ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"ok": False, "code": str(exc)[:80] or "backup_failed"}))
        return 2
    print(json.dumps({"ok": True, "runs": {k: {"events": v["journal_events"], "head": v["journal_head"]}
                                           for k, v in res.items()}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
