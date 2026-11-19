#!/usr/bin/env python3
"""Inventario SOLA LETTURA per Brain Unico (Issue #113, Fase B).

Produce un manifest JSON con, per ogni file sotto le radici indicate: percorso relativo, byte, mtime,
SHA256 e, per i .jsonl, conteggio righe / righe non valide / valori distinti di run_id, run_no, portfolio_id.
Con --git-repo aggiunge commit in esecuzione e file locali modificati (solo nomi).

Garanzie:
- non scrive nulla tranne il file --out (rifiutato se cade dentro una radice);
- non stampa ne' salva MAI il contenuto dei file (solo numeri e hash);
- i file dal nome sensibile (.env, chiavi, token, secret, credential...) NON vengono aperti: sono contati;
- i link simbolici non vengono seguiti;
- i database SQLite NON si aprono per default. Con --sqlite si aprono con mode=ro + query_only e si contano
  solo righe per tabella e max(rowid): usare su una COPIA ferma (un DB WAL aperto in sola lettura puo'
  comunque richiedere il file -shm);
- solo libreria standard, nessuna rete, nessun sudo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from typing import Any

SCHEMA = 1
SENSITIVE = re.compile(r"(\.env|secret|token|passw|credential|private|\.pem$|\.key$|(^|/)id_(rsa|ed25519|ecdsa)|\.age$|api[_-]?key)", re.I)
SQLITE_EXT = (".sqlite", ".sqlite3", ".db")
ID_FIELDS = ("run_id", "run_no", "portfolio_id")
MAX_DISTINCT = 50


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jsonl_stats(path: str) -> dict:
    lines = bad = 0
    seen: dict[str, set] = {k: set() for k in ID_FIELDS}
    with open(path, "rb") as fh:
        for raw in fh:
            if not raw.strip():
                continue
            lines += 1
            try:
                row = json.loads(raw)
            except ValueError:
                bad += 1
                continue
            if isinstance(row, dict):
                for k in ID_FIELDS:
                    v = row.get(k)
                    if isinstance(v, (str, int)) and len(seen[k]) <= MAX_DISTINCT:
                        seen[k].add(str(v)[:64])
    out: dict[str, Any] = {"lines": lines, "invalid_lines": bad}
    for k, s in seen.items():
        if s:
            out[f"distinct_{k}"] = sorted(s)[:MAX_DISTINCT]
    return out


def sqlite_stats(path: str) -> dict:
    uri = "file:" + path.replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=1)
    try:
        con.execute("PRAGMA query_only=1")
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        out = {}
        for t in tables:
            q = '"' + t.replace('"', '""') + '"'
            n, mx = con.execute(f"SELECT COUNT(*), MAX(rowid) FROM {q}").fetchone()
            out[t] = {"rows": n, "max_rowid": mx}
        return {"tables": out}
    finally:
        con.close()


def git_info(repo: str) -> dict:
    def run(*a):
        return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, timeout=30)
    head = run("rev-parse", "HEAD")
    if head.returncode != 0:
        return {"error": "not_a_git_repo"}
    st = run("status", "--porcelain", "--untracked-files=no")
    changed = sorted(line[3:] for line in st.stdout.splitlines() if line.strip())
    return {"head": head.stdout.strip(), "branch": run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
            "modified_tracked_count": len(changed), "modified_tracked_paths": changed[:200]}


def scan_root(label: str, root: str, with_sqlite: bool) -> tuple[list, int, list]:
    entries, excluded, errors = [], 0, []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = f"{label}/{os.path.relpath(full, root)}"
            if os.path.islink(full):
                continue
            if SENSITIVE.search(rel):
                excluded += 1
                continue
            try:
                st = os.stat(full)
                e: dict[str, Any] = {"path": rel, "bytes": st.st_size, "mtime": int(st.st_mtime),
                                     "sha256": sha256_file(full)}
                low = name.lower()
                if low.endswith(".jsonl"):
                    e.update(jsonl_stats(full))
                elif with_sqlite and low.endswith(SQLITE_EXT):
                    e.update(sqlite_stats(full))
                entries.append(e)
            except (OSError, sqlite3.Error) as exc:
                errors.append({"path": rel, "error": type(exc).__name__})
    return entries, excluded, errors


def build(roots: list[tuple[str, str]], git_repo: str | None, with_sqlite: bool) -> dict:
    entries, excluded, errors = [], 0, []
    for label, root in roots:
        e, x, err = scan_root(label, root, with_sqlite)
        entries += e
        excluded += x
        errors += err
    entries.sort(key=lambda d: d["path"])
    canon = json.dumps([(e["path"], e["bytes"], e["sha256"]) for e in entries], separators=(",", ":"))
    out: dict[str, Any] = {"schema": SCHEMA, "files": len(entries), "excluded_sensitive_count": excluded,
                           "errors": errors, "manifest_digest": hashlib.sha256(canon.encode()).hexdigest(),
                           "entries": entries}
    if git_repo:
        out["git"] = git_info(git_repo)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", action="append", required=True, metavar="LABEL=PATH",
                    help="radice da inventariare, con etichetta logica (es. falco=/percorso)")
    ap.add_argument("--git-repo")
    ap.add_argument("--sqlite", action="store_true", help="conta righe dei DB SQLite (su copia ferma)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    roots = []
    for spec in a.root:
        label, sep, path = spec.partition("=")
        if not sep or not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", label) or not os.path.isdir(path):
            print(f"radice non valida: {label!r}", file=sys.stderr)
            return 2
        roots.append((label, os.path.realpath(path)))
    out_abs = os.path.realpath(a.out)
    for _, r in roots:
        if out_abs == r or out_abs.startswith(r + os.sep):
            print("--out non puo' stare dentro una radice inventariata", file=sys.stderr)
            return 2
    if os.path.exists(out_abs):
        print("--out esiste gia': non sovrascrivo", file=sys.stderr)
        return 2
    manifest = build(roots, a.git_repo, a.sqlite)
    with open(out_abs, "x", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)
    print(f"files={manifest['files']} excluded_sensitive={manifest['excluded_sensitive_count']} "
          f"errors={len(manifest['errors'])} digest={manifest['manifest_digest']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
