#!/usr/bin/env python3
"""Inventario SOLA LETTURA per Brain Unico (Issue #113, Fase B) — v2 (revisione PR #114).

Produce un manifest PRIVATO con, per ogni file regolare sotto le radici indicate: percorso relativo, byte,
mtime, SHA256 e, per i .jsonl, conteggio righe / righe non valide / numero di run_id, run_no, portfolio_id
distinti. Con --git-repo aggiunge commit in esecuzione e file tracciati modificati (solo nomi).

Garanzie:
- non scrive nulla tranne --out (e --summary-out): file nuovi, mai sovrascritti, --out con permessi 0600;
- --out e' rifiutato se cade dentro una radice o dentro QUALUNQUE working tree git: il manifest e' privato
  (contiene percorsi) e non va incollato nel repository; per condividere si usa --summary-out (solo numeri);
- non stampa ne' salva MAI il contenuto dei file; i valori degli ID compaiono solo con --include-ids e solo
  se hanno formato sicuro (^[A-Za-z0-9_.:-]{1,64}$); gli altri sono solo contati;
- i file dal nome sensibile (.env, chiavi, token, secret, credential...) NON vengono aperti: sono contati;
- si guarda solo con lstat: symlink non seguiti; FIFO/socket/device/directory-come-file mai aperti (contati
  in special_files); apertura con O_NOFOLLOW|O_NONBLOCK e verifica dev/inode/tipo dopo l'apertura;
- DATABASE: file .sqlite/.sqlite3/.db e -wal/-shm/-journal NON vengono letti ne' hashati per default
  (skipped=live_db_not_read): un hash di un DB vivo non e' una copia coerente e non certifica nulla.
  --include-db li hasha (solo su una COPIA FERMA); --sqlite lo implica e conta le righe, ma salta il SQL se
  esiste un -wal non vuoto (sql_skipped=wal_present). Nessun DB viene mai aperto in scrittura;
- stabilita': hash e statistiche JSONL escono dalla stessa unica lettura; se dimensione/mtime/inode
  cambiano durante la lettura l'entry e' marcata unstable=true;
- il manifest dichiara complete=false se ci sono errori di attraversamento/lettura o file instabili.
  complete=true NON certifica un backup: certifies_backup e' sempre false;
- solo libreria standard, nessuna rete, nessun sudo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
from typing import Any, Callable, Optional

SCHEMA = 2
SENSITIVE = re.compile(r"(\.env|secret|token|passw|credential|private|\.pem$|\.key$|(^|/)id_(rsa|ed25519|ecdsa)|\.age$|api[_-]?key)", re.I)
DB_EXT = (".sqlite", ".sqlite3", ".db")
DB_SIDE = ("-wal", "-shm", "-journal")
ID_FIELDS = ("run_id", "run_no", "portfolio_id")
SAFE_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
MAX_TRACK = 1000          # ID distinti tracciati per campo (oltre: capped)
MAX_SHOWN = 50            # ID mostrati con --include-ids
MAX_LINE = 16 * 1024 * 1024
CHUNK = 1 << 20

# Solo per i test: chiamato dopo la lettura, prima del controllo di stabilita'.
_TEST_HOOK: Optional[Callable[[str], None]] = None


class _Jsonl:
    def __init__(self) -> None:
        self.lines = 0
        self.bad = 0
        self.ids: dict[str, set] = {k: set() for k in ID_FIELDS}
        self.id_unsafe = 0
        self.capped: set = set()

    def line(self, raw: bytes) -> None:
        if not raw.strip():
            return
        self.lines += 1
        if len(raw) > MAX_LINE:
            self.bad += 1
            return
        try:
            row = json.loads(raw)
        except (ValueError, RecursionError):
            self.bad += 1
            return
        if not isinstance(row, dict):
            return
        for k in ID_FIELDS:
            v = row.get(k)
            if v is None:
                continue
            if isinstance(v, bool) or not isinstance(v, (str, int)):
                self.id_unsafe += 1
                continue
            s = str(v)
            if not SAFE_ID.fullmatch(s):
                self.id_unsafe += 1
            elif len(self.ids[k]) < MAX_TRACK:
                self.ids[k].add(s)
            elif s not in self.ids[k]:
                self.capped.add(k)

    def result(self, include_ids: bool) -> dict:
        out: dict[str, Any] = {"lines": self.lines, "invalid_lines": self.bad}
        for k, s in self.ids.items():
            if s:
                out[f"distinct_{k}_count"] = len(s)
                if include_ids:
                    out[f"distinct_{k}"] = sorted(s)[:MAX_SHOWN]
        if self.capped:
            out["distinct_capped"] = sorted(self.capped)
        if self.id_unsafe:
            out["id_values_not_exported"] = self.id_unsafe
        return out


def read_regular(path: str, parse_jsonl: bool = False) -> dict:
    """Legge UNA volta un file regolare (hash + eventuale JSONL). Mai segue symlink, mai apre file speciali.
    Ritorna {"special": True} se non e' un file regolare, altrimenti sha256/bytes/unstable/(jsonl)."""
    pre = os.lstat(path)
    if not stat.S_ISREG(pre.st_mode):
        return {"special": True}
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != (pre.st_dev, pre.st_ino):
            return {"special": True}
        h = hashlib.sha256()
        total = 0
        js = _Jsonl() if parse_jsonl else None
        buf = b""
        discarding = False        # dentro una riga oltre MAX_LINE: si scarta fino al prossimo a-capo
        while True:
            chunk = os.read(fd, CHUNK)
            if not chunk:
                break
            total += len(chunk)
            h.update(chunk)
            if js is None:
                continue
            if discarding:
                nl = chunk.find(b"\n")
                if nl < 0:
                    continue
                chunk = chunk[nl + 1:]
                discarding = False
            buf += chunk
            *done, buf = buf.split(b"\n")
            for ln in done:
                js.line(ln)
            if len(buf) > MAX_LINE:       # riga ancora aperta e troppo lunga: contata UNA volta
                js.lines += 1
                js.bad += 1
                buf = b""
                discarding = True
        if js is not None and buf and not discarding:
            js.line(buf)
        if _TEST_HOOK is not None:
            _TEST_HOOK(path)
        post = os.fstat(fd)
        try:
            post_l = os.lstat(path)
            same_path = (post_l.st_dev, post_l.st_ino) == (st.st_dev, st.st_ino)
        except OSError:
            same_path = False
        unstable = not (total == st.st_size == post.st_size and post.st_mtime_ns == st.st_mtime_ns and same_path)
        return {"sha256": h.hexdigest(), "bytes_read": total, "size": st.st_size, "mtime": int(st.st_mtime),
                "unstable": unstable, "_js": js}
    finally:
        os.close(fd)


def sqlite_stats(path: str) -> dict:
    """Conteggi per tabella su una COPIA FERMA. mode=ro + query_only. Gestisce WITHOUT ROWID."""
    wal = path + "-wal"
    try:
        if os.path.getsize(wal) > 0:
            return {"sql_skipped": "wal_present"}
    except OSError:
        pass
    if os.path.exists(path + "-journal"):
        return {"sql_skipped": "journal_present"}
    uri = "file:" + path.replace("%", "%25").replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=1)
    try:
        con.execute("PRAGMA query_only=1")
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        out = {}
        for t in tables:
            q = '"' + t.replace('"', '""') + '"'
            try:
                n, mx = con.execute(f"SELECT COUNT(*), MAX(rowid) FROM {q}").fetchone()
            except sqlite3.OperationalError:          # WITHOUT ROWID (o vista/virtuale)
                n, mx = con.execute(f"SELECT COUNT(*) FROM {q}").fetchone()[0], None
            out[t] = {"rows": n, "max_rowid": mx}
        return {"tables": out}
    finally:
        con.close()


def git_info(repo: str) -> dict:
    def run(*a):
        return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, timeout=30)
    try:
        head = run("rev-parse", "HEAD")
    except (OSError, subprocess.SubprocessError):
        return {"error": "git_unavailable"}
    if head.returncode != 0:
        return {"error": "not_a_git_repo"}
    st = run("status", "--porcelain", "--untracked-files=no")
    changed = sorted(line[3:] for line in st.stdout.splitlines() if line.strip())
    return {"head": head.stdout.strip(), "branch": run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
            "modified_tracked_count": len(changed), "modified_tracked_paths": changed[:200]}


def inside_git_worktree(path: str) -> bool:
    d = os.path.dirname(os.path.realpath(path)) or "."
    try:
        r = subprocess.run(["git", "-C", d, "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def scan_root(label: str, root: str, o: argparse.Namespace, acc: dict) -> None:
    def onerror(exc: OSError) -> None:
        rel = os.path.relpath(getattr(exc, "filename", root) or root, root)
        acc["traverse_errors"].append({"path": f"{label}/{rel}", "error": type(exc).__name__})

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=onerror):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = f"{label}/{os.path.relpath(full, root)}"
            try:
                lst = os.lstat(full)
            except OSError as exc:
                acc["errors"].append({"path": rel, "error": type(exc).__name__})
                continue
            if stat.S_ISLNK(lst.st_mode):
                acc["symlinks_skipped"] += 1
                continue
            if not stat.S_ISREG(lst.st_mode):
                acc["special_files"] += 1
                continue
            if SENSITIVE.search(rel):
                acc["excluded_sensitive_count"] += 1
                continue
            low = name.lower()
            is_db = low.endswith(DB_EXT) or low.endswith(DB_SIDE)
            if is_db and not o.include_db:
                acc["entries"].append({"path": rel, "bytes": lst.st_size, "mtime": int(lst.st_mtime),
                                       "skipped": "live_db_not_read"})
                continue
            try:
                r = read_regular(full, parse_jsonl=low.endswith(".jsonl"))
                if r.get("special"):
                    acc["special_files"] += 1
                    continue
                js = r.pop("_js", None)
                e: dict[str, Any] = {"path": rel, "bytes": r["size"], "mtime": r["mtime"], "sha256": r["sha256"]}
                if r["unstable"]:
                    e["unstable"] = True
                    acc["unstable_count"] += 1
                if js is not None:
                    e.update(js.result(o.include_ids))
                if o.sqlite and low.endswith(DB_EXT):
                    e.update(sqlite_stats(full))
                acc["entries"].append(e)
            except (OSError, sqlite3.Error) as exc:
                acc["errors"].append({"path": rel, "error": type(exc).__name__})


def build(roots: list[tuple[str, str]], o: argparse.Namespace) -> dict:
    acc: dict[str, Any] = {"entries": [], "errors": [], "traverse_errors": [], "symlinks_skipped": 0,
                           "special_files": 0, "excluded_sensitive_count": 0, "unstable_count": 0}
    for label, root in roots:
        scan_root(label, root, o, acc)
    entries = sorted(acc["entries"], key=lambda d: d["path"])
    hashed = [e for e in entries if "sha256" in e]
    canon = json.dumps([(e["path"], e["bytes"], e["sha256"]) for e in hashed], separators=(",", ":"))
    complete = not (acc["errors"] or acc["traverse_errors"] or acc["unstable_count"])
    out: dict[str, Any] = {
        "schema": SCHEMA, "classification": "PRIVATE_DO_NOT_COMMIT", "certifies_backup": False,
        "complete": complete, "files_hashed": len(hashed),
        "skipped_live_db": sum(1 for e in entries if e.get("skipped") == "live_db_not_read"),
        "special_files": acc["special_files"], "symlinks_skipped": acc["symlinks_skipped"],
        "excluded_sensitive_count": acc["excluded_sensitive_count"], "unstable_count": acc["unstable_count"],
        "errors": acc["errors"], "traverse_errors": acc["traverse_errors"],
        "manifest_digest": hashlib.sha256(canon.encode()).hexdigest(),
        "digest_covers": "hashed_entries_only", "entries": entries}
    if o.git_repo:
        out["git"] = git_info(o.git_repo)
    return out


def summary_of(m: dict) -> dict:
    keys = ("schema", "complete", "files_hashed", "skipped_live_db", "special_files", "symlinks_skipped",
            "excluded_sensitive_count", "unstable_count", "manifest_digest", "certifies_backup")
    s = {k: m[k] for k in keys}
    s.update(classification="PUBLIC_SUMMARY_NUMBERS_ONLY", errors_count=len(m["errors"]),
             traverse_errors_count=len(m["traverse_errors"]))
    return s


def _write_new(path: str, data: dict, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", action="append", required=True, metavar="LABEL=PATH",
                    help="radice da inventariare, con etichetta logica (es. falco=/percorso)")
    ap.add_argument("--git-repo")
    ap.add_argument("--include-db", action="store_true", help="hasha anche DB/WAL (solo su COPIA FERMA)")
    ap.add_argument("--sqlite", action="store_true", help="conta righe dei DB (implica --include-db; copia ferma)")
    ap.add_argument("--include-ids", action="store_true", help="mostra i valori degli ID in formato sicuro")
    ap.add_argument("--out", required=True, help="manifest PRIVATO (0600, fuori da qualunque repo git)")
    ap.add_argument("--summary-out", help="riepilogo con soli numeri, condivisibile")
    a = ap.parse_args(argv)
    if a.sqlite:
        a.include_db = True
    roots = []
    for spec in a.root:
        label, sep, path = spec.partition("=")
        if not sep or not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", label) or not os.path.isdir(path):
            print(f"radice non valida: {label!r}", file=sys.stderr)
            return 2
        roots.append((label, os.path.realpath(path)))
    # Percorsi di output: NON si risolve l'ultimo componente (un symlink, anche pendente, e' "esistente").
    a.out = os.path.abspath(a.out)
    a.summary_out = os.path.abspath(a.summary_out) if a.summary_out else None
    if a.summary_out and os.path.join(os.path.realpath(os.path.dirname(a.out)), os.path.basename(a.out)) == \
            os.path.join(os.path.realpath(os.path.dirname(a.summary_out)), os.path.basename(a.summary_out)):
        print("--out e --summary-out devono essere file diversi", file=sys.stderr)
        return 2
    for p in (a.out, a.summary_out):
        if not p:
            continue
        real = os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))
        for _, r in roots:
            if real == r or real.startswith(r + os.sep):
                print("l'output non puo' stare dentro una radice inventariata", file=sys.stderr)
                return 2
        if os.path.lexists(p):
            print("l'output esiste gia': non sovrascrivo", file=sys.stderr)
            return 2
    if inside_git_worktree(a.out):
        print("--out non puo' stare dentro un working tree git (manifest privato)", file=sys.stderr)
        return 2
    manifest = build(roots, a)
    _write_new(a.out, manifest, 0o600)
    if a.summary_out:
        _write_new(a.summary_out, summary_of(manifest), 0o644)
    print(f"complete={manifest['complete']} hashed={manifest['files_hashed']} "
          f"skipped_live_db={manifest['skipped_live_db']} special={manifest['special_files']} "
          f"errors={len(manifest['errors']) + len(manifest['traverse_errors'])} "
          f"unstable={manifest['unstable_count']} digest={manifest['manifest_digest']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
