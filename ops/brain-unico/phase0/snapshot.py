#!/usr/bin/env python3
"""Fase 0 — copia consistente PER FILE degli storici, in una directory di laboratorio separata.

NON e' uno snapshot atomico fra sorgenti diverse: ogni file e' catturato in modo coerente al proprio
istante (captured_at_ms) e il log dichiara la finestra totale. Garanzie sulle sorgenti:

- mai scritte, mai bloccate piu' del minimo: nessun chmod/rename/touch sulle sorgenti;
- SQLite: solo `Connection.backup()` da una connessione mode=ro + query_only, a passi di poche pagine
  (rilascia il lock fra un passo e l'altro), busy_timeout breve: se il DB e' occupato si ABBANDONA e si
  riprova, non si resta in coda dietro l'exit service. Mai `cp` di DB/WAL. La copia e' un file standalone
  (journal_mode=DELETE, nessun -wal/-shm accanto), con integrity_check;
- JSONL append-only: si legge esattamente la dimensione vista all'inizio, si taglia all'ultimo a-capo
  completo (la riga parziale in coda NON entra), poi si rilegge il prefisso della sorgente e si confronta
  l'hash: se e' cambiato (file riscritto, sostituito, troncato) l'esito e' un nuovo tentativo, mai "OK";
- file piccoli (state, lessons...): doppia lettura e confronto di hash/size/mtime/inode;
- solo file regolari, nessun symlink seguito, nomi sensibili (.env, chiavi, token...) esclusi;
- preflight: sorgenti leggibili, destinazione nuova e fuori dalle sorgenti, spazio >= fattore x totale + riserva;
- le copie sono 0400 e la directory 0700; il log (snapshot_log.json) e' PRIVATO, non va nel repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
from typing import Any, Callable, Optional
from urllib.parse import quote

if not getattr(sys, "_phase0_sealed", False):          # bundle sigillato: nessuna modifica di sys.path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import inventory as inv  # noqa: E402

SCHEMA = 1
CHUNK = 1 << 20
MAX_ATTEMPTS = 3
RETRY_SLEEP = 2.0
SQLITE_STEP_PAGES = 64
SQLITE_STEP_SLEEP = 0.02
SQLITE_BUSY_S = 1.0
SQLITE_MAX_SECONDS = 600
ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,60}")
KINDS = ("sqlite", "jsonl", "file", "tree")
EXCLUDE_DIRS = frozenset({".venv", "venv", "node_modules", "__pycache__", ".git", "site-packages"})
SIDE = inv.DB_SIDE

# Solo per i test: _HOOK(stage, path) con stage in {"after_copy"}.
_HOOK: Optional[Callable[[str, str], None]] = None


def inside_git(path: str) -> bool:
    """True se `path` (anche non ancora esistente) cadrebbe in un working tree git."""
    p = os.path.abspath(path)
    while not os.path.lexists(p) and os.path.dirname(p) != p:
        p = os.path.dirname(p)
    if os.path.isdir(p) and not os.path.islink(p):
        p = os.path.join(p, "x")
    return inv.inside_git_worktree(p)


def safe_new_dir(path: str) -> str:
    """Crea UNA directory nuova (0700 per costruzione, nessun chmod). Rifiuta: percorso gia' esistente (anche
    symlink, anche pendente), genitore mancante o raggiunto attraverso un symlink. Mai tocca directory preesistenti."""
    p = os.path.abspath(path)
    parent = os.path.dirname(p)
    if not os.path.basename(p) or not os.path.isdir(parent) or os.path.realpath(parent) != parent:
        raise ValueError("parent_missing_or_symlink_in_path")
    if os.path.lexists(p):
        raise FileExistsError("path_exists")
    os.mkdir(p, 0o700)
    return p


def mkdirs_private(root: str, rel_dir: str) -> str:
    """Crea i sotto-livelli di `rel_dir` sotto `root` UNO PER UNO con 0700 (makedirs applica il mode al solo ultimo)."""
    cur = root
    for part in [x for x in rel_dir.split(os.sep) if x]:
        if part in (".", ".."):
            raise ValueError("bad_relative_dir")
        cur = os.path.join(cur, part)
        if not os.path.isdir(cur):
            os.mkdir(cur, 0o700)
    return cur


# --------------------------------------------------------------------------- spec

def load_spec(path: str) -> tuple:
    """Ritorna (sources, required_groups). La spec DEVE dichiarare required_groups: la completezza non si
    deduce dall'esistenza dei percorsi (es. Falco, Toro, Brain storico e ciascuna Arena)."""
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    srcs = spec.get("sources") if isinstance(spec, dict) else None
    if not isinstance(srcs, list) or not srcs:
        raise ValueError("spec_without_sources")
    req = spec.get("required_groups")
    if (not isinstance(req, list) or not req or len(set(req)) != len(req)
            or any(not isinstance(g, str) or not ID_RE.fullmatch(g) or g in (".", "..") for g in req)):
        raise ValueError("spec_without_required_groups")
    seen, out = set(), []
    for s in srcs:
        sid, kind, p = s.get("id"), s.get("kind"), s.get("path")
        if (not isinstance(sid, str) or not ID_RE.fullmatch(sid) or sid in (".", "..") or sid in seen):
            raise ValueError(f"bad_or_duplicate_id:{sid!r}")
        if kind not in KINDS:
            raise ValueError(f"bad_kind:{sid}")
        if not isinstance(p, str) or not os.path.isabs(p) or ".." in p.split(os.sep):
            raise ValueError(f"bad_path:{sid}")
        if inv.SENSITIVE.search(p):
            raise ValueError(f"sensitive_name_source:{sid}")
        np_ = os.path.normpath(p)
        if kind != "tree" and not os.path.basename(np_):
            raise ValueError(f"bad_path:{sid}")
        grp = s.get("group", sid)
        if not isinstance(grp, str) or not ID_RE.fullmatch(grp) or grp in (".", ".."):
            raise ValueError(f"bad_group:{sid}")
        opt = s.get("optional", False)
        ev = s.get("quiescence_evidence")
        if not isinstance(opt, bool) or (ev is not None and (not isinstance(ev, str) or not ev.strip() or len(ev) > 200
                                                             or re.search(r"[\x00-\x1f]", ev))):
            raise ValueError(f"bad_field:{sid}")
        seen.add(sid)
        out.append({"id": sid, "kind": kind, "path": np_, "group": grp, "optional": opt,
                    "quiescence_evidence": ev.strip() if ev else None})
    for g in req:
        if not any(s["group"] == g and not s["optional"] for s in out):
            raise ValueError(f"required_group_without_source:{g}")
    return out, req


def expand(sources: list[dict]) -> tuple:
    """Espande i 'tree' in file singoli. Ritorna (items, skipped_totali, per_sorgente)."""
    items, total = [], {"sensitive": 0, "side_files": 0, "symlinks": 0, "special": 0, "walk_errors": 0,
                        "excluded_dirs": 0}
    by_source: dict[str, dict] = {}
    for s in sources:
        sk = {"sensitive": 0, "side_files": 0, "symlinks": 0, "special": 0, "walk_errors": 0, "excluded_dirs": 0}
        n0 = len(items)
        missing = s["optional"] and not os.path.lexists(s["path"])          # sorgente opzionale assente: ammessa
        base = {"group": s["group"], "optional": s["optional"], "quiescence_evidence": s["quiescence_evidence"],
                "source_id": s["id"]}
        if missing:
            pass
        elif s["kind"] != "tree":
            items.append({"id": s["id"], "kind": s["kind"], "path": s["path"],
                          "rel": os.path.join(s["id"], os.path.basename(s["path"])), **base})
        elif os.path.islink(s["path"]) or not os.path.isdir(s["path"]):
            sk["walk_errors"] += 1                                      # radice non valida: NO-GO in preflight
        else:
            def onerr(_e: OSError, _sk=sk) -> None:
                _sk["walk_errors"] += 1
            for d, dn, fn in os.walk(s["path"], followlinks=False, onerror=onerr):
                kept = sorted(x for x in dn if x not in EXCLUDE_DIRS)
                sk["excluded_dirs"] += len(dn) - len(kept)
                dn[:] = kept
                for name in sorted(fn):
                    full = os.path.join(d, name)
                    rel = os.path.relpath(full, s["path"])
                    try:
                        st = os.lstat(full)
                    except OSError:
                        sk["walk_errors"] += 1
                        continue
                    if stat.S_ISLNK(st.st_mode):
                        sk["symlinks"] += 1
                    elif not stat.S_ISREG(st.st_mode):
                        sk["special"] += 1
                    elif inv.SENSITIVE.search(rel):
                        sk["sensitive"] += 1
                    elif name.lower().endswith(SIDE):
                        sk["side_files"] += 1
                    else:
                        low = name.lower()
                        kind = "jsonl" if low.endswith(".jsonl") else "sqlite" if low.endswith(inv.DB_EXT) else "file"
                        items.append({"id": f"{s['id']}/{rel}", "kind": kind, "path": full,
                                      "rel": os.path.join(s["id"], rel), **base})
        by_source[s["id"]] = {**sk, "items": len(items) - n0, "optional": s["optional"], "group": s["group"],
                              "missing": bool(missing)}
        for k in sk:
            total[k] += sk[k]
    return items, total, by_source


# --------------------------------------------------------------------------- preflight

def _bytes_by_group(items: list) -> dict:
    out: dict[str, int] = {}
    for it in items:
        try:
            out[it["group"]] = out.get(it["group"], 0) + os.lstat(it["path"]).st_size
        except OSError:
            pass
    return out


def preflight(items: list[dict], skipped: dict, dest: str, space_factor: float, reserve_bytes: int,
              roots: Optional[list[dict]] = None, by_source: Optional[dict] = None,
              required_groups: Optional[list] = None, require_data: bool = False,
              max_total_bytes: Optional[int] = None) -> dict:
    nogo: list[dict] = []
    warn: list[dict] = []
    dest_abs = os.path.abspath(dest)
    parent = os.path.dirname(dest_abs)
    if os.path.lexists(dest_abs):
        nogo.append({"code": "dest_exists"})                            # la destinazione deve essere NUOVA
    if not os.path.isdir(parent) or os.path.realpath(parent) != parent:
        nogo.append({"code": "dest_parent_missing_or_symlink"})
    elif not os.access(parent, os.W_OK):
        nogo.append({"code": "dest_parent_not_writable"})
    real_dest = os.path.join(os.path.realpath(parent), os.path.basename(dest_abs))
    total = 0
    if not items:
        nogo.append({"code": "no_items"})
    for r in (roots if roots is not None else items):          # radici originali, anche per i 'tree'
        rp = os.path.realpath(r["path"])
        if real_dest == rp or real_dest.startswith(rp.rstrip(os.sep) + os.sep) or rp.startswith(real_dest + os.sep):
            nogo.append({"code": "dest_overlaps_source", "id": r["id"]})
    for sid, bs in (by_source or {}).items():
        if bs["items"] == 0 and not bs["optional"]:
            nogo.append({"code": "source_yields_no_items", "id": sid})
        if bs.get("missing"):
            warn.append({"code": "optional_source_missing", "id": sid})
        if bs["symlinks"] or bs["special"]:
            warn.append({"code": "source_has_excluded_symlinks_or_special", "id": sid,
                         "symlinks": bs["symlinks"], "special": bs["special"]})
    if required_groups:
        present = {it["group"] for it in items}
        for g in required_groups:
            if g not in present:
                nogo.append({"code": "required_group_without_items", "group": g})
            elif require_data and not any(it["group"] == g and it["kind"] in ("sqlite", "jsonl") for it in items):
                nogo.append({"code": "required_group_without_data_files", "group": g})   # solo codice/config non e' storico
    for it in items:
        p = it["path"]
        try:
            st = os.lstat(p)
        except FileNotFoundError:
            nogo.append({"code": "source_missing", "id": it["id"]})
            continue
        except PermissionError:
            nogo.append({"code": "source_permission_denied", "id": it["id"]})
            continue
        if stat.S_ISLNK(st.st_mode):
            nogo.append({"code": "source_is_symlink", "id": it["id"]})
        elif not stat.S_ISREG(st.st_mode):
            nogo.append({"code": "source_not_regular_file", "id": it["id"]})
        elif not os.access(p, os.R_OK):
            nogo.append({"code": "source_not_readable", "id": it["id"]})
        else:
            total += st.st_size
            if it["kind"] == "sqlite":
                pr = probe_sqlite(p)
                m = sqlite_method(pr, it.get("quiescence_evidence"))
                if m.startswith("nogo:"):
                    nogo.append({"code": m[5:], "id": it["id"]})
                elif pr.get("wal") and pr["shm_exists"]:
                    warn.append({"code": "live_wal_db_backup_api", "id": it["id"]})
                if pr.get("hot_journal"):
                    warn.append({"code": "hot_journal_present", "id": it["id"]})
    if skipped.get("walk_errors"):
        nogo.append({"code": "tree_walk_errors", "count": skipped["walk_errors"]})
    if max_total_bytes is not None and total > max_total_bytes:
        nogo.append({"code": "total_size_exceeds_limit", "total": total, "limit": max_total_bytes})
    free = None
    if os.path.isdir(parent):
        free = shutil.disk_usage(parent).free
        need = int(total * space_factor) + reserve_bytes
        if free < need:
            nogo.append({"code": "insufficient_space", "free": free, "need": need})
    return {"go": not nogo, "nogo": nogo, "warn": warn, "total_source_bytes": total, "free_bytes": free,
            "items": len(items), "skipped": skipped, "by_source": by_source or {},
            "bytes_by_group": _bytes_by_group(items)}


# --------------------------------------------------------------------------- copy primitives

def _sha(path: str, upto: Optional[int] = None) -> str:
    h = hashlib.sha256()
    left = upto
    with open(path, "rb") as fh:
        while left is None or left > 0:
            b = fh.read(CHUNK if left is None else min(CHUNK, left))
            if not b:
                break
            h.update(b)
            if left is not None:
                left -= len(b)
    return h.hexdigest()


def _open_src(path: str) -> tuple[int, os.stat_result]:
    pre = os.lstat(path)
    if not stat.S_ISREG(pre.st_mode):
        raise OSError("not_regular")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                 | getattr(os, "O_CLOEXEC", 0))
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != (pre.st_dev, pre.st_ino):
        os.close(fd)
        raise OSError("changed_while_opening")
    return fd, st


def _fsync_path(path: str) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def probe_sqlite(path: str) -> dict:
    """Solo intestazione (100 byte) + metadati dei file affiancati. Non apre SQLite."""
    try:
        with open(path, "rb") as fh:
            hdr = fh.read(100)
    except OSError as exc:
        return {"error": type(exc).__name__}
    shm, wal = path + "-shm", path + "-wal"
    try:
        wal_size = os.path.getsize(wal)
    except OSError:
        wal_size = None
    return {"wal": len(hdr) >= 20 and hdr[18] == 2 and hdr[19] == 2,
            "shm_exists": os.path.lexists(shm), "shm_writable": os.access(shm, os.W_OK) if os.path.lexists(shm) else None,
            "wal_exists": wal_size is not None, "wal_size": wal_size or 0,
            "hot_journal": os.path.lexists(path + "-journal")}


def sqlite_method(pr: dict, quiescence_evidence: Optional[str] = None) -> str:
    """'backup' | 'file_copy' | 'nogo:<codice>'. Regola: la sorgente non deve ricevere file nuovi ne' scritture
    di contenuto. Un DB WAL aperto anche solo in lettura crea/usa -shm e -wal (indice wal-index, volatile, mai
    dati durevoli): ok solo se gia' esistono e -shm e' scrivibile (servizio vivo).
    L'ASSENZA di -wal/-shm NON prova che nessuno stia scrivendo (un servizio puo' aprire il DB un attimo dopo):
    senza `quiescence_evidence` (riferimento a una prova ESTERNA, es. unita' verificata inattiva nello step 1)
    il metodo e' NO-GO; con l'evidenza si copia il file senza aprirlo e si controlla che nessun sidecar compaia."""
    if "error" in pr:
        return "nogo:sqlite_probe_" + pr["error"]
    if not pr["wal"]:
        return "backup"
    if pr["shm_exists"]:
        return "backup" if pr["shm_writable"] else "nogo:wal_shm_not_writable_by_snapshot_user"
    if pr["wal_exists"] and pr["wal_size"] > 0:
        return "nogo:wal_data_without_shm"
    if not quiescence_evidence:
        return "nogo:wal_quiescence_unproven"
    return "file_copy"


def _finalize_copy(dst: str) -> tuple:
    """integrity_check e conteggi sulla COPIA, poi journal_mode=DELETE e rimozione di eventuali -wal/-shm."""
    d = sqlite3.connect(dst)
    try:
        d.execute("PRAGMA journal_mode=DELETE").fetchone()
        ic = [r[0] for r in d.execute("PRAGMA integrity_check").fetchall()]
        tables = {}
        for (t,) in d.execute("SELECT name FROM sqlite_master WHERE type='table' "
                              "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
            tables[t] = d.execute('SELECT COUNT(*) FROM "%s"' % t.replace('"', '""')).fetchone()[0]
    finally:
        d.close()
    return ic, tables


def copy_sqlite(src: str, dst: str, sleep: Callable[[float], None] = time.sleep,
                quiescence_evidence: Optional[str] = None) -> dict:
    pr = probe_sqlite(src)
    method = sqlite_method(pr, quiescence_evidence)
    if method.startswith("nogo:"):
        return {"status": "FAILED", "reason": method[5:], "attempts": 0}
    if method == "file_copy":
        res = copy_small_file(src, dst, sleep=sleep)
        if res["status"] != "OK":
            return res
        if os.path.lexists(src + "-wal") or os.path.lexists(src + "-shm"):      # qualcuno ha aperto il DB nel frattempo
            os.remove(dst)
            return {"status": "FAILED", "reason": "wal_sidecar_appeared_during_copy", "attempts": res["attempts"]}
        try:
            ic, tables = _finalize_copy(dst)
        except sqlite3.Error as exc:
            os.remove(dst)
            return {"status": "FAILED", "reason": "copy_not_a_valid_db:" + type(exc).__name__, "attempts": res["attempts"]}
        left = [x for x in (dst + "-wal", dst + "-shm", dst + "-journal") if os.path.lexists(x)]
        if left or ic != ["ok"]:
            for x in [dst] + left:
                os.remove(x)
            return {"status": "FAILED", "reason": "copy_not_standalone" if left else "integrity_check_failed",
                    "attempts": res["attempts"]}
        res.update({"method": "file_copy_checkpointed", "quiescence_evidence": quiescence_evidence, "integrity": "ok", "tables": tables, "journal_mode_src": "wal",
                    "bytes": os.path.getsize(dst), "sha256": _sha(dst)})
        _fsync_path(dst)
        return res
    last = "unknown"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        for ex in (dst, dst + "-journal", dst + "-wal", dst + "-shm"):
            if os.path.lexists(ex):
                os.remove(ex)
        t0 = time.time()
        try:
            uri = "file:" + quote(src, safe="/") + "?mode=ro"
            s = sqlite3.connect(uri, uri=True, timeout=SQLITE_BUSY_S)
            try:
                s.execute("PRAGMA query_only=1")
                jm = s.execute("PRAGMA journal_mode").fetchone()[0]
                d = sqlite3.connect(dst)
                try:
                    def prog(_status, _remaining, _total):
                        if time.time() - t0 > SQLITE_MAX_SECONDS:
                            raise TimeoutError("sqlite_backup_timeout")
                    s.backup(d, pages=SQLITE_STEP_PAGES, progress=prog, sleep=SQLITE_STEP_SLEEP)
                finally:
                    d.close()
            finally:
                s.close()
            ic, tables = _finalize_copy(dst)
            leftovers = [x for x in (dst + "-wal", dst + "-shm", dst + "-journal") if os.path.lexists(x)]
            if leftovers:
                return {"status": "FAILED", "reason": "copy_not_standalone", "attempts": attempt}
            if ic != ["ok"]:
                return {"status": "FAILED", "reason": "integrity_check_failed", "attempts": attempt}
            _fsync_path(dst)
            return {"status": "OK", "attempts": attempt, "bytes": os.path.getsize(dst), "sha256": _sha(dst),
                    "journal_mode_src": jm, "tables": tables, "integrity": "ok", "method": "backup_api"}
        except (sqlite3.Error, TimeoutError, OSError) as exc:
            msg = str(exc).lower()
            last = ("busy_or_locked" if ("locked" in msg or "busy" in msg) else
                    "timeout" if isinstance(exc, TimeoutError) else
                    "readonly_wal_needs_shm" if "readonly" in msg or "read-only" in msg else
                    "open_failed:" + type(exc).__name__)
            if attempt < MAX_ATTEMPTS:
                sleep(RETRY_SLEEP)
    for ex in (dst, dst + "-journal", dst + "-wal", dst + "-shm"):
        if os.path.lexists(ex):
            os.remove(ex)
    return {"status": "FAILED", "reason": last, "attempts": MAX_ATTEMPTS}


def copy_append_only(src: str, dst: str, sleep: Callable[[float], None] = time.sleep) -> dict:
    last = "unknown"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        tmp = dst + ".part"
        if os.path.lexists(tmp):
            os.remove(tmp)
        try:
            fd, st = _open_src(src)
        except OSError as exc:
            return {"status": "FAILED", "reason": "open_failed:" + type(exc).__name__, "attempts": attempt}
        size0, copied, last_nl = st.st_size, 0, -1
        try:
            out = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                while copied < size0:
                    b = os.read(fd, min(CHUNK, size0 - copied))
                    if not b:
                        break
                    os.write(out, b)
                    i = b.rfind(b"\n")
                    if i >= 0:
                        last_nl = copied + i
                    copied += len(b)
                if copied < size0:
                    last = "source_shrank_during_copy"
                    os.close(out)
                    out = -1
                    sleep(RETRY_SLEEP) if attempt < MAX_ATTEMPTS else None
                    continue
                cut = last_nl + 1
                os.ftruncate(out, cut)
                os.fsync(out)
            finally:
                if out != -1:
                    os.close(out)
        finally:
            os.close(fd)
        digest = _sha(tmp)
        if _HOOK:
            _HOOK("after_copy", src)
        try:
            fd2, st2 = _open_src(src)
        except OSError:
            last = "source_replaced_or_missing"
            if attempt < MAX_ATTEMPTS:
                sleep(RETRY_SLEEP)
            continue
        os.close(fd2)
        if (st2.st_dev, st2.st_ino) != (st.st_dev, st.st_ino):
            last = "source_replaced_inode_changed"
        elif st2.st_size < cut:
            last = "source_truncated"
        elif _sha(src, cut) != digest:
            last = "prefix_modified"
        else:
            os.replace(tmp, dst)
            _fsync_path(dst)
            return {"status": "OK", "attempts": attempt, "bytes": cut, "sha256": digest,
                    "source_size_at_start": size0, "partial_tail_bytes": size0 - cut,
                    "source_size_after": st2.st_size}
        if attempt < MAX_ATTEMPTS:
            sleep(RETRY_SLEEP)
    if os.path.lexists(dst + ".part"):
        os.remove(dst + ".part")
    return {"status": "FAILED", "reason": last, "attempts": MAX_ATTEMPTS}


def copy_small_file(src: str, dst: str, sleep: Callable[[float], None] = time.sleep) -> dict:
    last = "unknown"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        tmp = dst + ".part"
        if os.path.lexists(tmp):
            os.remove(tmp)
        try:
            fd, st = _open_src(src)
        except OSError as exc:
            return {"status": "FAILED", "reason": "open_failed:" + type(exc).__name__, "attempts": attempt}
        try:
            h = hashlib.sha256()
            out = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                while True:
                    b = os.read(fd, CHUNK)
                    if not b:
                        break
                    h.update(b)
                    os.write(out, b)
                os.fsync(out)
            finally:
                os.close(out)
            if _HOOK:
                _HOOK("after_copy", src)
            post = os.fstat(fd)
        finally:
            os.close(fd)
        try:
            st3 = os.lstat(src)
            same = (st3.st_dev, st3.st_ino) == (st.st_dev, st.st_ino)
        except OSError:
            same = False
        if (same and post.st_size == st.st_size == os.path.getsize(tmp) and post.st_mtime_ns == st.st_mtime_ns
                and _sha(src) == h.hexdigest()):
            os.replace(tmp, dst)
            _fsync_path(dst)
            return {"status": "OK", "attempts": attempt, "bytes": st.st_size, "sha256": h.hexdigest()}
        last = "source_changed_during_copy"
        if attempt < MAX_ATTEMPTS:
            sleep(RETRY_SLEEP)
    if os.path.lexists(dst + ".part"):
        os.remove(dst + ".part")
    return {"status": "FAILED", "reason": last, "attempts": MAX_ATTEMPTS}


COPIERS = {"sqlite": copy_sqlite, "jsonl": copy_append_only, "file": copy_small_file}


# --------------------------------------------------------------------------- run

def run_snapshot(spec_path: str, dest: str, auth_ref: Optional[str], dry_run: bool,
                 space_factor: float = 2.0, reserve_mb: int = 512, sleep: Callable[[float], None] = time.sleep,
                 require_data: bool = False, max_total_bytes: Optional[int] = None) -> tuple[int, dict]:
    roots, required = load_spec(spec_path)
    items, skipped, by_source = expand(roots)
    pf = preflight(items, skipped, dest, space_factor, reserve_mb * 1024 * 1024, roots, by_source, required,
                   require_data, max_total_bytes)
    report: dict[str, Any] = {"schema": SCHEMA, "classification": "PRIVATE_DO_NOT_COMMIT", "preflight": pf,
                              "dry_run": dry_run}
    if dry_run or not pf["go"]:
        report["verdict"] = "GO" if pf["go"] else "NO-GO"
        return (0 if pf["go"] else 1), report
    if not auth_ref or not auth_ref.strip():
        report["verdict"] = "NO-GO"
        report["preflight"]["nogo"].append({"code": "missing_authorization_reference"})
        return 1, report
    dest = safe_new_dir(dest)                       # nuova, 0700 per costruzione; niente chmod su directory esistenti
    started = int(time.time() * 1000)
    results = []
    for it in items:
        dst = os.path.join(dest, it["rel"])
        mkdirs_private(dest, os.path.dirname(it["rel"]))
        t0 = int(time.time() * 1000)
        extra = {"quiescence_evidence": it.get("quiescence_evidence")} if it["kind"] == "sqlite" else {}
        res = COPIERS[it["kind"]](it["path"], dst, sleep=sleep, **extra)
        res.update({"id": it["id"], "kind": it["kind"], "src": it["path"], "dst_rel": it["rel"],
                    "captured_at_ms": t0, "finished_at_ms": int(time.time() * 1000)})
        if res["status"] == "OK" and it["kind"] == "jsonl":
            r = inv.read_regular(dst, parse_jsonl=True)
            res.update(r["_js"].result(False))
        if res["status"] == "OK":
            os.chmod(dst, 0o400)
        results.append(res)
    ended = int(time.time() * 1000)
    ok = bool(results) and len(results) == len(items) and all(r["status"] == "OK" for r in results)
    report.update({"auth_ref": auth_ref, "started_ms": started, "ended_ms": ended,
                   "window_seconds": round((ended - started) / 1000, 3),
                   "consistency": "per_item_not_atomic_across_sources", "items": results, "complete": ok,
                   "required_groups": required, "by_source": by_source,
                   "verdict": "GO" if ok else "NO-GO"})
    log = os.path.join(dest, "snapshot_log.json")
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    return (0 if ok else 1), report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec", required=True)
    ap.add_argument("--dest", required=True, help="directory NUOVA, fuori dalle sorgenti e da qualunque repo")
    ap.add_argument("--auth-ref", help="riferimento all'autorizzazione esplicita (obbligatorio senza --dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="solo preflight, nessuna copia")
    ap.add_argument("--space-factor", type=float, default=2.0)
    ap.add_argument("--reserve-mb", type=int, default=512)
    a = ap.parse_args(argv)
    if inside_git(a.dest):
        print("NO-GO: la destinazione non puo' stare in un working tree git")
        return 1
    try:
        code, rep = run_snapshot(a.spec, a.dest, a.auth_ref, a.dry_run, a.space_factor, a.reserve_mb)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"NO-GO: spec o destinazione non valida ({type(exc).__name__}: {str(exc)[:80]})")
        return 1
    pf = rep["preflight"]
    if code:
        print("NO-GO: " + ", ".join(sorted({n["code"] for n in pf["nogo"]}) or
                                     [r.get("reason", "?") for r in rep.get("items", []) if r["status"] != "OK"]))
    else:
        n = len(rep.get("items", [])) or pf["items"]
        print(f"GO ({'dry-run' if a.dry_run else 'snapshot completo'}): items={n} bytes={pf['total_source_bytes']} "
              f"warn={len(pf['warn'])}")
    return code


if __name__ == "__main__":
    sys.exit(main())
