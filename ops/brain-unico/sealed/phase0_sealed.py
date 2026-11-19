#!/usr/bin/env python3
"""SuperBot Brain Unico - bundle SIGILLATO della Fase 0 (opzione B). GENERATO da build_sealed.py: NON modificare.

Uso (selftest: nessun privilegio e nessun dato; preflight/full: solo root, solo da una directory di root):
    python3 -I phase0_sealed.py selftest
    python3 -I phase0_sealed.py preflight --expect-sha256 <HASH>
    python3 -I phase0_sealed.py full --expect-sha256 <HASH> --auth-ref <RIFERIMENTO>
Moduli incorporati (sha256 dei sorgenti):
  inventory    e363261aa42656a8160c7a9e9c9b0b43bb1d28093f0d78cc7014c1f5cc977c19
  snapshot     b60f8aba7b79af47bc5da7b528adf7867c48e40e769fa725c08fb5b07848fb70
  audit        f9ccf2475f267cd4f3fa65a06e81017fbcf624b94606f55534bae5fee5604da8
  sealed_root  e00a7c7ded2b9d81f511e344c4f58f9fd5fa2482f640a136048da855c4d11741
  sources.json 9845b98efc9f37b39117b2026057be17e9d6881e2198da81b84f2b95d25cea44
"""
import hashlib
import json
import os
import sys
import types

_ORDER = ('inventory', 'snapshot', 'audit', 'sealed_root')


def _extract(raw):
    blocks, cur, buf = {}, None, []
    for ln in raw.decode("utf-8").split("\n"):
        if ln.startswith("#@@ BEGIN "):
            cur, buf = ln[len("#@@ BEGIN "):], []
        elif ln.startswith("#@@ END "):
            blocks[cur] = "\n".join(buf) + "\n"
            cur = None
        elif cur is not None:
            if not ln.startswith("#|"):
                raise SystemExit("bundle corrotto")
            buf.append(ln[2:])
    return blocks


def _boot():
    path = os.path.abspath(__file__)
    with open(path, "rb") as fh:
        raw = fh.read()
    blocks = _extract(raw)
    sys._phase0_sealed = True
    for name in _ORDER:
        mod = types.ModuleType(name)
        mod.__file__ = "<sealed:%s>" % name
        sys.modules[name] = mod
        exec(compile(blocks[name], mod.__file__, "exec"), mod.__dict__)
    spec = json.loads(blocks["sources.json"])
    hashes = {n: hashlib.sha256(blocks[n].encode()).hexdigest() for n in _ORDER + ("sources.json",)}
    return sys.modules["sealed_root"].main(sys.argv[1:], data=raw, spec=spec, code_path=path, module_hashes=hashes)


if __name__ == "__main__":
    sys.exit(_boot())

#@@ BEGIN inventory
#|#!/usr/bin/env python3
#|"""Inventario SOLA LETTURA per Brain Unico (Issue #113, Fase B) — v2 (revisione PR #114).
#|
#|Produce un manifest PRIVATO con, per ogni file regolare sotto le radici indicate: percorso relativo, byte,
#|mtime, SHA256 e, per i .jsonl, conteggio righe / righe non valide / numero di run_id, run_no, portfolio_id
#|distinti. Con --git-repo aggiunge commit in esecuzione e file tracciati modificati (solo nomi).
#|
#|Garanzie:
#|- non scrive nulla tranne --out (e --summary-out): file nuovi, mai sovrascritti, --out con permessi 0600;
#|- --out e' rifiutato se cade dentro una radice o dentro QUALUNQUE working tree git: il manifest e' privato
#|  (contiene percorsi) e non va incollato nel repository; per condividere si usa --summary-out (solo numeri);
#|- non stampa ne' salva MAI il contenuto dei file; i valori degli ID compaiono solo con --include-ids e solo
#|  se hanno formato sicuro (^[A-Za-z0-9_.:-]{1,64}$); gli altri sono solo contati;
#|- i file dal nome sensibile (.env, chiavi, token, secret, credential...) NON vengono aperti: sono contati;
#|- si guarda solo con lstat: symlink non seguiti; FIFO/socket/device/directory-come-file mai aperti (contati
#|  in special_files); apertura con O_NOFOLLOW|O_NONBLOCK e verifica dev/inode/tipo dopo l'apertura;
#|- DATABASE: file .sqlite/.sqlite3/.db e -wal/-shm/-journal NON vengono letti ne' hashati per default
#|  (skipped=live_db_not_read): un hash di un DB vivo non e' una copia coerente e non certifica nulla.
#|  --include-db li hasha (solo su una COPIA FERMA); --sqlite lo implica e conta le righe, ma salta il SQL se
#|  esiste un -wal non vuoto (sql_skipped=wal_present). Nessun DB viene mai aperto in scrittura;
#|- stabilita': hash e statistiche JSONL escono dalla stessa unica lettura; se dimensione/mtime/inode
#|  cambiano durante la lettura l'entry e' marcata unstable=true;
#|- il manifest dichiara complete=false se ci sono errori di attraversamento/lettura o file instabili.
#|  complete=true NON certifica un backup: certifies_backup e' sempre false;
#|- solo libreria standard, nessuna rete, nessun sudo.
#|"""
#|from __future__ import annotations
#|
#|import argparse
#|import hashlib
#|import json
#|import os
#|import re
#|import sqlite3
#|import stat
#|import subprocess
#|import sys
#|from typing import Any, Callable, Optional
#|
#|SCHEMA = 2
#|SENSITIVE = re.compile(r"(\.env|secret|token|passw|credential|private|\.pem$|\.key$|(^|/)id_(rsa|ed25519|ecdsa)|\.age$|api[_-]?key)", re.I)
#|DB_EXT = (".sqlite", ".sqlite3", ".db")
#|DB_SIDE = ("-wal", "-shm", "-journal")
#|ID_FIELDS = ("run_id", "run_no", "portfolio_id")
#|SAFE_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
#|MAX_TRACK = 1000          # ID distinti tracciati per campo (oltre: capped)
#|MAX_SHOWN = 50            # ID mostrati con --include-ids
#|MAX_LINE = 16 * 1024 * 1024
#|CHUNK = 1 << 20
#|
#|# Solo per i test: chiamato dopo la lettura, prima del controllo di stabilita'.
#|_TEST_HOOK: Optional[Callable[[str], None]] = None
#|
#|
#|class _Jsonl:
#|    def __init__(self) -> None:
#|        self.lines = 0
#|        self.bad = 0
#|        self.ids: dict[str, set] = {k: set() for k in ID_FIELDS}
#|        self.id_unsafe = 0
#|        self.capped: set = set()
#|
#|    def line(self, raw: bytes) -> None:
#|        if not raw.strip():
#|            return
#|        self.lines += 1
#|        if len(raw) > MAX_LINE:
#|            self.bad += 1
#|            return
#|        try:
#|            row = json.loads(raw)
#|        except (ValueError, RecursionError):
#|            self.bad += 1
#|            return
#|        if not isinstance(row, dict):
#|            return
#|        for k in ID_FIELDS:
#|            v = row.get(k)
#|            if v is None:
#|                continue
#|            if isinstance(v, bool) or not isinstance(v, (str, int)):
#|                self.id_unsafe += 1
#|                continue
#|            s = str(v)
#|            if not SAFE_ID.fullmatch(s):
#|                self.id_unsafe += 1
#|            elif len(self.ids[k]) < MAX_TRACK:
#|                self.ids[k].add(s)
#|            elif s not in self.ids[k]:
#|                self.capped.add(k)
#|
#|    def result(self, include_ids: bool) -> dict:
#|        out: dict[str, Any] = {"lines": self.lines, "invalid_lines": self.bad}
#|        for k, s in self.ids.items():
#|            if s:
#|                out[f"distinct_{k}_count"] = len(s)
#|                if include_ids:
#|                    out[f"distinct_{k}"] = sorted(s)[:MAX_SHOWN]
#|        if self.capped:
#|            out["distinct_capped"] = sorted(self.capped)
#|        if self.id_unsafe:
#|            out["id_values_not_exported"] = self.id_unsafe
#|        return out
#|
#|
#|def read_regular(path: str, parse_jsonl: bool = False) -> dict:
#|    """Legge UNA volta un file regolare (hash + eventuale JSONL). Mai segue symlink, mai apre file speciali.
#|    Ritorna {"special": True} se non e' un file regolare, altrimenti sha256/bytes/unstable/(jsonl)."""
#|    pre = os.lstat(path)
#|    if not stat.S_ISREG(pre.st_mode):
#|        return {"special": True}
#|    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
#|    fd = os.open(path, flags)
#|    try:
#|        st = os.fstat(fd)
#|        if not stat.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != (pre.st_dev, pre.st_ino):
#|            return {"special": True}
#|        h = hashlib.sha256()
#|        total = 0
#|        js = _Jsonl() if parse_jsonl else None
#|        buf = b""
#|        discarding = False        # dentro una riga oltre MAX_LINE: si scarta fino al prossimo a-capo
#|        while True:
#|            chunk = os.read(fd, CHUNK)
#|            if not chunk:
#|                break
#|            total += len(chunk)
#|            h.update(chunk)
#|            if js is None:
#|                continue
#|            if discarding:
#|                nl = chunk.find(b"\n")
#|                if nl < 0:
#|                    continue
#|                chunk = chunk[nl + 1:]
#|                discarding = False
#|            buf += chunk
#|            *done, buf = buf.split(b"\n")
#|            for ln in done:
#|                js.line(ln)
#|            if len(buf) > MAX_LINE:       # riga ancora aperta e troppo lunga: contata UNA volta
#|                js.lines += 1
#|                js.bad += 1
#|                buf = b""
#|                discarding = True
#|        if js is not None and buf and not discarding:
#|            js.line(buf)
#|        if _TEST_HOOK is not None:
#|            _TEST_HOOK(path)
#|        post = os.fstat(fd)
#|        try:
#|            post_l = os.lstat(path)
#|            same_path = (post_l.st_dev, post_l.st_ino) == (st.st_dev, st.st_ino)
#|        except OSError:
#|            same_path = False
#|        unstable = not (total == st.st_size == post.st_size and post.st_mtime_ns == st.st_mtime_ns and same_path)
#|        return {"sha256": h.hexdigest(), "bytes_read": total, "size": st.st_size, "mtime": int(st.st_mtime),
#|                "unstable": unstable, "_js": js}
#|    finally:
#|        os.close(fd)
#|
#|
#|def sqlite_stats(path: str) -> dict:
#|    """Conteggi per tabella su una COPIA FERMA. mode=ro + query_only. Gestisce WITHOUT ROWID."""
#|    wal = path + "-wal"
#|    try:
#|        if os.path.getsize(wal) > 0:
#|            return {"sql_skipped": "wal_present"}
#|    except OSError:
#|        pass
#|    if os.path.exists(path + "-journal"):
#|        return {"sql_skipped": "journal_present"}
#|    uri = "file:" + path.replace("%", "%25").replace("?", "%3f").replace("#", "%23") + "?mode=ro"
#|    con = sqlite3.connect(uri, uri=True, timeout=1)
#|    try:
#|        con.execute("PRAGMA query_only=1")
#|        tables = [r[0] for r in con.execute(
#|            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
#|        out = {}
#|        for t in tables:
#|            q = '"' + t.replace('"', '""') + '"'
#|            try:
#|                n, mx = con.execute(f"SELECT COUNT(*), MAX(rowid) FROM {q}").fetchone()
#|            except sqlite3.OperationalError:          # WITHOUT ROWID (o vista/virtuale)
#|                n, mx = con.execute(f"SELECT COUNT(*) FROM {q}").fetchone()[0], None
#|            out[t] = {"rows": n, "max_rowid": mx}
#|        return {"tables": out}
#|    finally:
#|        con.close()
#|
#|
#|def git_info(repo: str) -> dict:
#|    def run(*a):
#|        return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, timeout=30)
#|    try:
#|        head = run("rev-parse", "HEAD")
#|    except (OSError, subprocess.SubprocessError):
#|        return {"error": "git_unavailable"}
#|    if head.returncode != 0:
#|        return {"error": "not_a_git_repo"}
#|    st = run("status", "--porcelain", "--untracked-files=no")
#|    changed = sorted(line[3:] for line in st.stdout.splitlines() if line.strip())
#|    return {"head": head.stdout.strip(), "branch": run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
#|            "modified_tracked_count": len(changed), "modified_tracked_paths": changed[:200]}
#|
#|
#|def inside_git_worktree(path: str) -> bool:
#|    d = os.path.dirname(os.path.realpath(path)) or "."
#|    try:
#|        r = subprocess.run(["git", "-C", d, "rev-parse", "--is-inside-work-tree"],
#|                           capture_output=True, text=True, timeout=15)
#|    except (OSError, subprocess.SubprocessError):
#|        return False
#|    return r.returncode == 0 and r.stdout.strip() == "true"
#|
#|
#|def scan_root(label: str, root: str, o: argparse.Namespace, acc: dict) -> None:
#|    def onerror(exc: OSError) -> None:
#|        rel = os.path.relpath(getattr(exc, "filename", root) or root, root)
#|        acc["traverse_errors"].append({"path": f"{label}/{rel}", "error": type(exc).__name__})
#|
#|    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=onerror):
#|        dirnames.sort()
#|        for name in sorted(filenames):
#|            full = os.path.join(dirpath, name)
#|            rel = f"{label}/{os.path.relpath(full, root)}"
#|            try:
#|                lst = os.lstat(full)
#|            except OSError as exc:
#|                acc["errors"].append({"path": rel, "error": type(exc).__name__})
#|                continue
#|            if stat.S_ISLNK(lst.st_mode):
#|                acc["symlinks_skipped"] += 1
#|                continue
#|            if not stat.S_ISREG(lst.st_mode):
#|                acc["special_files"] += 1
#|                continue
#|            if SENSITIVE.search(rel):
#|                acc["excluded_sensitive_count"] += 1
#|                continue
#|            low = name.lower()
#|            is_db = low.endswith(DB_EXT) or low.endswith(DB_SIDE)
#|            if is_db and not o.include_db:
#|                acc["entries"].append({"path": rel, "bytes": lst.st_size, "mtime": int(lst.st_mtime),
#|                                       "skipped": "live_db_not_read"})
#|                continue
#|            try:
#|                r = read_regular(full, parse_jsonl=low.endswith(".jsonl"))
#|                if r.get("special"):
#|                    acc["special_files"] += 1
#|                    continue
#|                js = r.pop("_js", None)
#|                e: dict[str, Any] = {"path": rel, "bytes": r["size"], "mtime": r["mtime"], "sha256": r["sha256"]}
#|                if r["unstable"]:
#|                    e["unstable"] = True
#|                    acc["unstable_count"] += 1
#|                if js is not None:
#|                    e.update(js.result(o.include_ids))
#|                if o.sqlite and low.endswith(DB_EXT):
#|                    e.update(sqlite_stats(full))
#|                acc["entries"].append(e)
#|            except (OSError, sqlite3.Error) as exc:
#|                acc["errors"].append({"path": rel, "error": type(exc).__name__})
#|
#|
#|def build(roots: list[tuple[str, str]], o: argparse.Namespace) -> dict:
#|    acc: dict[str, Any] = {"entries": [], "errors": [], "traverse_errors": [], "symlinks_skipped": 0,
#|                           "special_files": 0, "excluded_sensitive_count": 0, "unstable_count": 0}
#|    for label, root in roots:
#|        scan_root(label, root, o, acc)
#|    entries = sorted(acc["entries"], key=lambda d: d["path"])
#|    hashed = [e for e in entries if "sha256" in e]
#|    canon = json.dumps([(e["path"], e["bytes"], e["sha256"]) for e in hashed], separators=(",", ":"))
#|    complete = not (acc["errors"] or acc["traverse_errors"] or acc["unstable_count"])
#|    out: dict[str, Any] = {
#|        "schema": SCHEMA, "classification": "PRIVATE_DO_NOT_COMMIT", "certifies_backup": False,
#|        "complete": complete, "files_hashed": len(hashed),
#|        "skipped_live_db": sum(1 for e in entries if e.get("skipped") == "live_db_not_read"),
#|        "special_files": acc["special_files"], "symlinks_skipped": acc["symlinks_skipped"],
#|        "excluded_sensitive_count": acc["excluded_sensitive_count"], "unstable_count": acc["unstable_count"],
#|        "errors": acc["errors"], "traverse_errors": acc["traverse_errors"],
#|        "manifest_digest": hashlib.sha256(canon.encode()).hexdigest(),
#|        "digest_covers": "hashed_entries_only", "entries": entries}
#|    if o.git_repo:
#|        out["git"] = git_info(o.git_repo)
#|    return out
#|
#|
#|def summary_of(m: dict) -> dict:
#|    keys = ("schema", "complete", "files_hashed", "skipped_live_db", "special_files", "symlinks_skipped",
#|            "excluded_sensitive_count", "unstable_count", "manifest_digest", "certifies_backup")
#|    s = {k: m[k] for k in keys}
#|    s.update(classification="PUBLIC_SUMMARY_NUMBERS_ONLY", errors_count=len(m["errors"]),
#|             traverse_errors_count=len(m["traverse_errors"]))
#|    return s
#|
#|
#|def _write_new(path: str, data: dict, mode: int) -> None:
#|    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
#|    with os.fdopen(fd, "w", encoding="utf-8") as fh:
#|        json.dump(data, fh, indent=1, sort_keys=True)
#|
#|
#|def main(argv: list[str] | None = None) -> int:
#|    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
#|    ap.add_argument("--root", action="append", required=True, metavar="LABEL=PATH",
#|                    help="radice da inventariare, con etichetta logica (es. falco=/percorso)")
#|    ap.add_argument("--git-repo")
#|    ap.add_argument("--include-db", action="store_true", help="hasha anche DB/WAL (solo su COPIA FERMA)")
#|    ap.add_argument("--sqlite", action="store_true", help="conta righe dei DB (implica --include-db; copia ferma)")
#|    ap.add_argument("--include-ids", action="store_true", help="mostra i valori degli ID in formato sicuro")
#|    ap.add_argument("--out", required=True, help="manifest PRIVATO (0600, fuori da qualunque repo git)")
#|    ap.add_argument("--summary-out", help="riepilogo con soli numeri, condivisibile")
#|    a = ap.parse_args(argv)
#|    if a.sqlite:
#|        a.include_db = True
#|    roots = []
#|    for spec in a.root:
#|        label, sep, path = spec.partition("=")
#|        if not sep or not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", label) or not os.path.isdir(path):
#|            print(f"radice non valida: {label!r}", file=sys.stderr)
#|            return 2
#|        roots.append((label, os.path.realpath(path)))
#|    # Percorsi di output: NON si risolve l'ultimo componente (un symlink, anche pendente, e' "esistente").
#|    a.out = os.path.abspath(a.out)
#|    a.summary_out = os.path.abspath(a.summary_out) if a.summary_out else None
#|    if a.summary_out and os.path.join(os.path.realpath(os.path.dirname(a.out)), os.path.basename(a.out)) == \
#|            os.path.join(os.path.realpath(os.path.dirname(a.summary_out)), os.path.basename(a.summary_out)):
#|        print("--out e --summary-out devono essere file diversi", file=sys.stderr)
#|        return 2
#|    for p in (a.out, a.summary_out):
#|        if not p:
#|            continue
#|        real = os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))
#|        for _, r in roots:
#|            if real == r or real.startswith(r + os.sep):
#|                print("l'output non puo' stare dentro una radice inventariata", file=sys.stderr)
#|                return 2
#|        if os.path.lexists(p):
#|            print("l'output esiste gia': non sovrascrivo", file=sys.stderr)
#|            return 2
#|    if inside_git_worktree(a.out):
#|        print("--out non puo' stare dentro un working tree git (manifest privato)", file=sys.stderr)
#|        return 2
#|    manifest = build(roots, a)
#|    _write_new(a.out, manifest, 0o600)
#|    if a.summary_out:
#|        _write_new(a.summary_out, summary_of(manifest), 0o644)
#|    print(f"complete={manifest['complete']} hashed={manifest['files_hashed']} "
#|          f"skipped_live_db={manifest['skipped_live_db']} special={manifest['special_files']} "
#|          f"errors={len(manifest['errors']) + len(manifest['traverse_errors'])} "
#|          f"unstable={manifest['unstable_count']} digest={manifest['manifest_digest']}")
#|    return 0
#|
#|
#|if __name__ == "__main__":
#|    sys.exit(main())
#@@ END inventory

#@@ BEGIN snapshot
#|#!/usr/bin/env python3
#|"""Fase 0 — copia consistente PER FILE degli storici, in una directory di laboratorio separata.
#|
#|NON e' uno snapshot atomico fra sorgenti diverse: ogni file e' catturato in modo coerente al proprio
#|istante (captured_at_ms) e il log dichiara la finestra totale. Garanzie sulle sorgenti:
#|
#|- mai scritte, mai bloccate piu' del minimo: nessun chmod/rename/touch sulle sorgenti;
#|- SQLite: solo `Connection.backup()` da una connessione mode=ro + query_only, a passi di poche pagine
#|  (rilascia il lock fra un passo e l'altro), busy_timeout breve: se il DB e' occupato si ABBANDONA e si
#|  riprova, non si resta in coda dietro l'exit service. Mai `cp` di DB/WAL. La copia e' un file standalone
#|  (journal_mode=DELETE, nessun -wal/-shm accanto), con integrity_check;
#|- JSONL append-only: si legge esattamente la dimensione vista all'inizio, si taglia all'ultimo a-capo
#|  completo (la riga parziale in coda NON entra), poi si rilegge il prefisso della sorgente e si confronta
#|  l'hash: se e' cambiato (file riscritto, sostituito, troncato) l'esito e' un nuovo tentativo, mai "OK";
#|- file piccoli (state, lessons...): doppia lettura e confronto di hash/size/mtime/inode;
#|- solo file regolari, nessun symlink seguito, nomi sensibili (.env, chiavi, token...) esclusi;
#|- preflight: sorgenti leggibili, destinazione nuova e fuori dalle sorgenti, spazio >= fattore x totale + riserva;
#|- le copie sono 0400 e la directory 0700; il log (snapshot_log.json) e' PRIVATO, non va nel repository.
#|"""
#|from __future__ import annotations
#|
#|import argparse
#|import hashlib
#|import json
#|import os
#|import re
#|import shutil
#|import sqlite3
#|import stat
#|import subprocess
#|import sys
#|import time
#|from typing import Any, Callable, Optional
#|from urllib.parse import quote
#|
#|if not getattr(sys, "_phase0_sealed", False):          # bundle sigillato: nessuna modifica di sys.path
#|    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#|import inventory as inv  # noqa: E402
#|
#|SCHEMA = 1
#|CHUNK = 1 << 20
#|MAX_ATTEMPTS = 3
#|RETRY_SLEEP = 2.0
#|SQLITE_STEP_PAGES = 64
#|SQLITE_STEP_SLEEP = 0.02
#|SQLITE_BUSY_S = 1.0
#|SQLITE_MAX_SECONDS = 600
#|ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,60}")
#|KINDS = ("sqlite", "jsonl", "file", "tree")
#|EXCLUDE_DIRS = frozenset({".venv", "venv", "node_modules", "__pycache__", ".git", "site-packages"})
#|SIDE = inv.DB_SIDE
#|
#|# Solo per i test: _HOOK(stage, path) con stage in {"after_copy"}.
#|_HOOK: Optional[Callable[[str, str], None]] = None
#|
#|
#|def inside_git(path: str) -> bool:
#|    """True se `path` (anche non ancora esistente) cadrebbe in un working tree git."""
#|    p = os.path.abspath(path)
#|    while not os.path.lexists(p) and os.path.dirname(p) != p:
#|        p = os.path.dirname(p)
#|    if os.path.isdir(p) and not os.path.islink(p):
#|        p = os.path.join(p, "x")
#|    return inv.inside_git_worktree(p)
#|
#|
#|def safe_new_dir(path: str) -> str:
#|    """Crea UNA directory nuova (0700 per costruzione, nessun chmod). Rifiuta: percorso gia' esistente (anche
#|    symlink, anche pendente), genitore mancante o raggiunto attraverso un symlink. Mai tocca directory preesistenti."""
#|    p = os.path.abspath(path)
#|    parent = os.path.dirname(p)
#|    if not os.path.basename(p) or not os.path.isdir(parent) or os.path.realpath(parent) != parent:
#|        raise ValueError("parent_missing_or_symlink_in_path")
#|    if os.path.lexists(p):
#|        raise FileExistsError("path_exists")
#|    os.mkdir(p, 0o700)
#|    return p
#|
#|
#|def mkdirs_private(root: str, rel_dir: str) -> str:
#|    """Crea i sotto-livelli di `rel_dir` sotto `root` UNO PER UNO con 0700 (makedirs applica il mode al solo ultimo)."""
#|    cur = root
#|    for part in [x for x in rel_dir.split(os.sep) if x]:
#|        if part in (".", ".."):
#|            raise ValueError("bad_relative_dir")
#|        cur = os.path.join(cur, part)
#|        if not os.path.isdir(cur):
#|            os.mkdir(cur, 0o700)
#|    return cur
#|
#|
#|# --------------------------------------------------------------------------- spec
#|
#|def load_spec(path: str) -> tuple:
#|    """Ritorna (sources, required_groups). La spec DEVE dichiarare required_groups: la completezza non si
#|    deduce dall'esistenza dei percorsi (es. Falco, Toro, Brain storico e ciascuna Arena)."""
#|    with open(path, encoding="utf-8") as fh:
#|        spec = json.load(fh)
#|    srcs = spec.get("sources") if isinstance(spec, dict) else None
#|    if not isinstance(srcs, list) or not srcs:
#|        raise ValueError("spec_without_sources")
#|    req = spec.get("required_groups")
#|    if (not isinstance(req, list) or not req or len(set(req)) != len(req)
#|            or any(not isinstance(g, str) or not ID_RE.fullmatch(g) or g in (".", "..") for g in req)):
#|        raise ValueError("spec_without_required_groups")
#|    seen, out = set(), []
#|    for s in srcs:
#|        sid, kind, p = s.get("id"), s.get("kind"), s.get("path")
#|        if (not isinstance(sid, str) or not ID_RE.fullmatch(sid) or sid in (".", "..") or sid in seen):
#|            raise ValueError(f"bad_or_duplicate_id:{sid!r}")
#|        if kind not in KINDS:
#|            raise ValueError(f"bad_kind:{sid}")
#|        if not isinstance(p, str) or not os.path.isabs(p) or ".." in p.split(os.sep):
#|            raise ValueError(f"bad_path:{sid}")
#|        if inv.SENSITIVE.search(p):
#|            raise ValueError(f"sensitive_name_source:{sid}")
#|        np_ = os.path.normpath(p)
#|        if kind != "tree" and not os.path.basename(np_):
#|            raise ValueError(f"bad_path:{sid}")
#|        grp = s.get("group", sid)
#|        if not isinstance(grp, str) or not ID_RE.fullmatch(grp) or grp in (".", ".."):
#|            raise ValueError(f"bad_group:{sid}")
#|        opt = s.get("optional", False)
#|        ev = s.get("quiescence_evidence")
#|        if not isinstance(opt, bool) or (ev is not None and (not isinstance(ev, str) or not ev.strip() or len(ev) > 200
#|                                                             or re.search(r"[\x00-\x1f]", ev))):
#|            raise ValueError(f"bad_field:{sid}")
#|        seen.add(sid)
#|        out.append({"id": sid, "kind": kind, "path": np_, "group": grp, "optional": opt,
#|                    "quiescence_evidence": ev.strip() if ev else None})
#|    for g in req:
#|        if not any(s["group"] == g and not s["optional"] for s in out):
#|            raise ValueError(f"required_group_without_source:{g}")
#|    return out, req
#|
#|
#|def expand(sources: list[dict]) -> tuple:
#|    """Espande i 'tree' in file singoli. Ritorna (items, skipped_totali, per_sorgente)."""
#|    items, total = [], {"sensitive": 0, "side_files": 0, "symlinks": 0, "special": 0, "walk_errors": 0,
#|                        "excluded_dirs": 0}
#|    by_source: dict[str, dict] = {}
#|    for s in sources:
#|        sk = {"sensitive": 0, "side_files": 0, "symlinks": 0, "special": 0, "walk_errors": 0, "excluded_dirs": 0}
#|        n0 = len(items)
#|        missing = s["optional"] and not os.path.lexists(s["path"])          # sorgente opzionale assente: ammessa
#|        base = {"group": s["group"], "optional": s["optional"], "quiescence_evidence": s["quiescence_evidence"],
#|                "source_id": s["id"]}
#|        if missing:
#|            pass
#|        elif s["kind"] != "tree":
#|            items.append({"id": s["id"], "kind": s["kind"], "path": s["path"],
#|                          "rel": os.path.join(s["id"], os.path.basename(s["path"])), **base})
#|        elif os.path.islink(s["path"]) or not os.path.isdir(s["path"]):
#|            sk["walk_errors"] += 1                                      # radice non valida: NO-GO in preflight
#|        else:
#|            def onerr(_e: OSError, _sk=sk) -> None:
#|                _sk["walk_errors"] += 1
#|            for d, dn, fn in os.walk(s["path"], followlinks=False, onerror=onerr):
#|                kept = sorted(x for x in dn if x not in EXCLUDE_DIRS)
#|                sk["excluded_dirs"] += len(dn) - len(kept)
#|                dn[:] = kept
#|                for name in sorted(fn):
#|                    full = os.path.join(d, name)
#|                    rel = os.path.relpath(full, s["path"])
#|                    try:
#|                        st = os.lstat(full)
#|                    except OSError:
#|                        sk["walk_errors"] += 1
#|                        continue
#|                    if stat.S_ISLNK(st.st_mode):
#|                        sk["symlinks"] += 1
#|                    elif not stat.S_ISREG(st.st_mode):
#|                        sk["special"] += 1
#|                    elif inv.SENSITIVE.search(rel):
#|                        sk["sensitive"] += 1
#|                    elif name.lower().endswith(SIDE):
#|                        sk["side_files"] += 1
#|                    else:
#|                        low = name.lower()
#|                        kind = "jsonl" if low.endswith(".jsonl") else "sqlite" if low.endswith(inv.DB_EXT) else "file"
#|                        items.append({"id": f"{s['id']}/{rel}", "kind": kind, "path": full,
#|                                      "rel": os.path.join(s["id"], rel), **base})
#|        by_source[s["id"]] = {**sk, "items": len(items) - n0, "optional": s["optional"], "group": s["group"],
#|                              "missing": bool(missing)}
#|        for k in sk:
#|            total[k] += sk[k]
#|    return items, total, by_source
#|
#|
#|# --------------------------------------------------------------------------- preflight
#|
#|def _bytes_by_group(items: list) -> dict:
#|    out: dict[str, int] = {}
#|    for it in items:
#|        try:
#|            out[it["group"]] = out.get(it["group"], 0) + os.lstat(it["path"]).st_size
#|        except OSError:
#|            pass
#|    return out
#|
#|
#|def preflight(items: list[dict], skipped: dict, dest: str, space_factor: float, reserve_bytes: int,
#|              roots: Optional[list[dict]] = None, by_source: Optional[dict] = None,
#|              required_groups: Optional[list] = None, require_data: bool = False,
#|              max_total_bytes: Optional[int] = None) -> dict:
#|    nogo: list[dict] = []
#|    warn: list[dict] = []
#|    dest_abs = os.path.abspath(dest)
#|    parent = os.path.dirname(dest_abs)
#|    if os.path.lexists(dest_abs):
#|        nogo.append({"code": "dest_exists"})                            # la destinazione deve essere NUOVA
#|    if not os.path.isdir(parent) or os.path.realpath(parent) != parent:
#|        nogo.append({"code": "dest_parent_missing_or_symlink"})
#|    elif not os.access(parent, os.W_OK):
#|        nogo.append({"code": "dest_parent_not_writable"})
#|    real_dest = os.path.join(os.path.realpath(parent), os.path.basename(dest_abs))
#|    total = 0
#|    if not items:
#|        nogo.append({"code": "no_items"})
#|    for r in (roots if roots is not None else items):          # radici originali, anche per i 'tree'
#|        rp = os.path.realpath(r["path"])
#|        if real_dest == rp or real_dest.startswith(rp.rstrip(os.sep) + os.sep) or rp.startswith(real_dest + os.sep):
#|            nogo.append({"code": "dest_overlaps_source", "id": r["id"]})
#|    for sid, bs in (by_source or {}).items():
#|        if bs["items"] == 0 and not bs["optional"]:
#|            nogo.append({"code": "source_yields_no_items", "id": sid})
#|        if bs.get("missing"):
#|            warn.append({"code": "optional_source_missing", "id": sid})
#|        if bs["symlinks"] or bs["special"]:
#|            warn.append({"code": "source_has_excluded_symlinks_or_special", "id": sid,
#|                         "symlinks": bs["symlinks"], "special": bs["special"]})
#|    if required_groups:
#|        present = {it["group"] for it in items}
#|        for g in required_groups:
#|            if g not in present:
#|                nogo.append({"code": "required_group_without_items", "group": g})
#|            elif require_data and not any(it["group"] == g and it["kind"] in ("sqlite", "jsonl") for it in items):
#|                nogo.append({"code": "required_group_without_data_files", "group": g})   # solo codice/config non e' storico
#|    for it in items:
#|        p = it["path"]
#|        try:
#|            st = os.lstat(p)
#|        except FileNotFoundError:
#|            nogo.append({"code": "source_missing", "id": it["id"]})
#|            continue
#|        except PermissionError:
#|            nogo.append({"code": "source_permission_denied", "id": it["id"]})
#|            continue
#|        if stat.S_ISLNK(st.st_mode):
#|            nogo.append({"code": "source_is_symlink", "id": it["id"]})
#|        elif not stat.S_ISREG(st.st_mode):
#|            nogo.append({"code": "source_not_regular_file", "id": it["id"]})
#|        elif not os.access(p, os.R_OK):
#|            nogo.append({"code": "source_not_readable", "id": it["id"]})
#|        else:
#|            total += st.st_size
#|            if it["kind"] == "sqlite":
#|                pr = probe_sqlite(p)
#|                m = sqlite_method(pr, it.get("quiescence_evidence"))
#|                if m.startswith("nogo:"):
#|                    nogo.append({"code": m[5:], "id": it["id"]})
#|                elif pr.get("wal") and pr["shm_exists"]:
#|                    warn.append({"code": "live_wal_db_backup_api", "id": it["id"]})
#|                if pr.get("hot_journal"):
#|                    warn.append({"code": "hot_journal_present", "id": it["id"]})
#|    if skipped.get("walk_errors"):
#|        nogo.append({"code": "tree_walk_errors", "count": skipped["walk_errors"]})
#|    if max_total_bytes is not None and total > max_total_bytes:
#|        nogo.append({"code": "total_size_exceeds_limit", "total": total, "limit": max_total_bytes})
#|    free = None
#|    if os.path.isdir(parent):
#|        free = shutil.disk_usage(parent).free
#|        need = int(total * space_factor) + reserve_bytes
#|        if free < need:
#|            nogo.append({"code": "insufficient_space", "free": free, "need": need})
#|    return {"go": not nogo, "nogo": nogo, "warn": warn, "total_source_bytes": total, "free_bytes": free,
#|            "items": len(items), "skipped": skipped, "by_source": by_source or {},
#|            "bytes_by_group": _bytes_by_group(items)}
#|
#|
#|# --------------------------------------------------------------------------- copy primitives
#|
#|def _sha(path: str, upto: Optional[int] = None) -> str:
#|    h = hashlib.sha256()
#|    left = upto
#|    with open(path, "rb") as fh:
#|        while left is None or left > 0:
#|            b = fh.read(CHUNK if left is None else min(CHUNK, left))
#|            if not b:
#|                break
#|            h.update(b)
#|            if left is not None:
#|                left -= len(b)
#|    return h.hexdigest()
#|
#|
#|def _open_src(path: str) -> tuple[int, os.stat_result]:
#|    pre = os.lstat(path)
#|    if not stat.S_ISREG(pre.st_mode):
#|        raise OSError("not_regular")
#|    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
#|                 | getattr(os, "O_CLOEXEC", 0))
#|    st = os.fstat(fd)
#|    if not stat.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != (pre.st_dev, pre.st_ino):
#|        os.close(fd)
#|        raise OSError("changed_while_opening")
#|    return fd, st
#|
#|
#|def _fsync_path(path: str) -> None:
#|    fd = os.open(path, os.O_RDONLY)
#|    try:
#|        os.fsync(fd)
#|    finally:
#|        os.close(fd)
#|
#|
#|def probe_sqlite(path: str) -> dict:
#|    """Solo intestazione (100 byte) + metadati dei file affiancati. Non apre SQLite."""
#|    try:
#|        with open(path, "rb") as fh:
#|            hdr = fh.read(100)
#|    except OSError as exc:
#|        return {"error": type(exc).__name__}
#|    shm, wal = path + "-shm", path + "-wal"
#|    try:
#|        wal_size = os.path.getsize(wal)
#|    except OSError:
#|        wal_size = None
#|    return {"wal": len(hdr) >= 20 and hdr[18] == 2 and hdr[19] == 2,
#|            "shm_exists": os.path.lexists(shm), "shm_writable": os.access(shm, os.W_OK) if os.path.lexists(shm) else None,
#|            "wal_exists": wal_size is not None, "wal_size": wal_size or 0,
#|            "hot_journal": os.path.lexists(path + "-journal")}
#|
#|
#|def sqlite_method(pr: dict, quiescence_evidence: Optional[str] = None) -> str:
#|    """'backup' | 'file_copy' | 'nogo:<codice>'. Regola: la sorgente non deve ricevere file nuovi ne' scritture
#|    di contenuto. Un DB WAL aperto anche solo in lettura crea/usa -shm e -wal (indice wal-index, volatile, mai
#|    dati durevoli): ok solo se gia' esistono e -shm e' scrivibile (servizio vivo).
#|    L'ASSENZA di -wal/-shm NON prova che nessuno stia scrivendo (un servizio puo' aprire il DB un attimo dopo):
#|    senza `quiescence_evidence` (riferimento a una prova ESTERNA, es. unita' verificata inattiva nello step 1)
#|    il metodo e' NO-GO; con l'evidenza si copia il file senza aprirlo e si controlla che nessun sidecar compaia."""
#|    if "error" in pr:
#|        return "nogo:sqlite_probe_" + pr["error"]
#|    if not pr["wal"]:
#|        return "backup"
#|    if pr["shm_exists"]:
#|        return "backup" if pr["shm_writable"] else "nogo:wal_shm_not_writable_by_snapshot_user"
#|    if pr["wal_exists"] and pr["wal_size"] > 0:
#|        return "nogo:wal_data_without_shm"
#|    if not quiescence_evidence:
#|        return "nogo:wal_quiescence_unproven"
#|    return "file_copy"
#|
#|
#|def _finalize_copy(dst: str) -> tuple:
#|    """integrity_check e conteggi sulla COPIA, poi journal_mode=DELETE e rimozione di eventuali -wal/-shm."""
#|    d = sqlite3.connect(dst)
#|    try:
#|        d.execute("PRAGMA journal_mode=DELETE").fetchone()
#|        ic = [r[0] for r in d.execute("PRAGMA integrity_check").fetchall()]
#|        tables = {}
#|        for (t,) in d.execute("SELECT name FROM sqlite_master WHERE type='table' "
#|                              "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
#|            tables[t] = d.execute('SELECT COUNT(*) FROM "%s"' % t.replace('"', '""')).fetchone()[0]
#|    finally:
#|        d.close()
#|    return ic, tables
#|
#|
#|def copy_sqlite(src: str, dst: str, sleep: Callable[[float], None] = time.sleep,
#|                quiescence_evidence: Optional[str] = None) -> dict:
#|    pr = probe_sqlite(src)
#|    method = sqlite_method(pr, quiescence_evidence)
#|    if method.startswith("nogo:"):
#|        return {"status": "FAILED", "reason": method[5:], "attempts": 0}
#|    if method == "file_copy":
#|        res = copy_small_file(src, dst, sleep=sleep)
#|        if res["status"] != "OK":
#|            return res
#|        if os.path.lexists(src + "-wal") or os.path.lexists(src + "-shm"):      # qualcuno ha aperto il DB nel frattempo
#|            os.remove(dst)
#|            return {"status": "FAILED", "reason": "wal_sidecar_appeared_during_copy", "attempts": res["attempts"]}
#|        try:
#|            ic, tables = _finalize_copy(dst)
#|        except sqlite3.Error as exc:
#|            os.remove(dst)
#|            return {"status": "FAILED", "reason": "copy_not_a_valid_db:" + type(exc).__name__, "attempts": res["attempts"]}
#|        left = [x for x in (dst + "-wal", dst + "-shm", dst + "-journal") if os.path.lexists(x)]
#|        if left or ic != ["ok"]:
#|            for x in [dst] + left:
#|                os.remove(x)
#|            return {"status": "FAILED", "reason": "copy_not_standalone" if left else "integrity_check_failed",
#|                    "attempts": res["attempts"]}
#|        res.update({"method": "file_copy_checkpointed", "quiescence_evidence": quiescence_evidence, "integrity": "ok", "tables": tables, "journal_mode_src": "wal",
#|                    "bytes": os.path.getsize(dst), "sha256": _sha(dst)})
#|        _fsync_path(dst)
#|        return res
#|    last = "unknown"
#|    for attempt in range(1, MAX_ATTEMPTS + 1):
#|        for ex in (dst, dst + "-journal", dst + "-wal", dst + "-shm"):
#|            if os.path.lexists(ex):
#|                os.remove(ex)
#|        t0 = time.time()
#|        try:
#|            uri = "file:" + quote(src, safe="/") + "?mode=ro"
#|            s = sqlite3.connect(uri, uri=True, timeout=SQLITE_BUSY_S)
#|            try:
#|                s.execute("PRAGMA query_only=1")
#|                jm = s.execute("PRAGMA journal_mode").fetchone()[0]
#|                d = sqlite3.connect(dst)
#|                try:
#|                    def prog(_status, _remaining, _total):
#|                        if time.time() - t0 > SQLITE_MAX_SECONDS:
#|                            raise TimeoutError("sqlite_backup_timeout")
#|                    s.backup(d, pages=SQLITE_STEP_PAGES, progress=prog, sleep=SQLITE_STEP_SLEEP)
#|                finally:
#|                    d.close()
#|            finally:
#|                s.close()
#|            ic, tables = _finalize_copy(dst)
#|            leftovers = [x for x in (dst + "-wal", dst + "-shm", dst + "-journal") if os.path.lexists(x)]
#|            if leftovers:
#|                return {"status": "FAILED", "reason": "copy_not_standalone", "attempts": attempt}
#|            if ic != ["ok"]:
#|                return {"status": "FAILED", "reason": "integrity_check_failed", "attempts": attempt}
#|            _fsync_path(dst)
#|            return {"status": "OK", "attempts": attempt, "bytes": os.path.getsize(dst), "sha256": _sha(dst),
#|                    "journal_mode_src": jm, "tables": tables, "integrity": "ok", "method": "backup_api"}
#|        except (sqlite3.Error, TimeoutError, OSError) as exc:
#|            msg = str(exc).lower()
#|            last = ("busy_or_locked" if ("locked" in msg or "busy" in msg) else
#|                    "timeout" if isinstance(exc, TimeoutError) else
#|                    "readonly_wal_needs_shm" if "readonly" in msg or "read-only" in msg else
#|                    "open_failed:" + type(exc).__name__)
#|            if attempt < MAX_ATTEMPTS:
#|                sleep(RETRY_SLEEP)
#|    for ex in (dst, dst + "-journal", dst + "-wal", dst + "-shm"):
#|        if os.path.lexists(ex):
#|            os.remove(ex)
#|    return {"status": "FAILED", "reason": last, "attempts": MAX_ATTEMPTS}
#|
#|
#|def copy_append_only(src: str, dst: str, sleep: Callable[[float], None] = time.sleep) -> dict:
#|    last = "unknown"
#|    for attempt in range(1, MAX_ATTEMPTS + 1):
#|        tmp = dst + ".part"
#|        if os.path.lexists(tmp):
#|            os.remove(tmp)
#|        try:
#|            fd, st = _open_src(src)
#|        except OSError as exc:
#|            return {"status": "FAILED", "reason": "open_failed:" + type(exc).__name__, "attempts": attempt}
#|        size0, copied, last_nl = st.st_size, 0, -1
#|        try:
#|            out = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
#|            try:
#|                while copied < size0:
#|                    b = os.read(fd, min(CHUNK, size0 - copied))
#|                    if not b:
#|                        break
#|                    os.write(out, b)
#|                    i = b.rfind(b"\n")
#|                    if i >= 0:
#|                        last_nl = copied + i
#|                    copied += len(b)
#|                if copied < size0:
#|                    last = "source_shrank_during_copy"
#|                    os.close(out)
#|                    out = -1
#|                    sleep(RETRY_SLEEP) if attempt < MAX_ATTEMPTS else None
#|                    continue
#|                cut = last_nl + 1
#|                os.ftruncate(out, cut)
#|                os.fsync(out)
#|            finally:
#|                if out != -1:
#|                    os.close(out)
#|        finally:
#|            os.close(fd)
#|        digest = _sha(tmp)
#|        if _HOOK:
#|            _HOOK("after_copy", src)
#|        try:
#|            fd2, st2 = _open_src(src)
#|        except OSError:
#|            last = "source_replaced_or_missing"
#|            if attempt < MAX_ATTEMPTS:
#|                sleep(RETRY_SLEEP)
#|            continue
#|        os.close(fd2)
#|        if (st2.st_dev, st2.st_ino) != (st.st_dev, st.st_ino):
#|            last = "source_replaced_inode_changed"
#|        elif st2.st_size < cut:
#|            last = "source_truncated"
#|        elif _sha(src, cut) != digest:
#|            last = "prefix_modified"
#|        else:
#|            os.replace(tmp, dst)
#|            _fsync_path(dst)
#|            return {"status": "OK", "attempts": attempt, "bytes": cut, "sha256": digest,
#|                    "source_size_at_start": size0, "partial_tail_bytes": size0 - cut,
#|                    "source_size_after": st2.st_size}
#|        if attempt < MAX_ATTEMPTS:
#|            sleep(RETRY_SLEEP)
#|    if os.path.lexists(dst + ".part"):
#|        os.remove(dst + ".part")
#|    return {"status": "FAILED", "reason": last, "attempts": MAX_ATTEMPTS}
#|
#|
#|def copy_small_file(src: str, dst: str, sleep: Callable[[float], None] = time.sleep) -> dict:
#|    last = "unknown"
#|    for attempt in range(1, MAX_ATTEMPTS + 1):
#|        tmp = dst + ".part"
#|        if os.path.lexists(tmp):
#|            os.remove(tmp)
#|        try:
#|            fd, st = _open_src(src)
#|        except OSError as exc:
#|            return {"status": "FAILED", "reason": "open_failed:" + type(exc).__name__, "attempts": attempt}
#|        try:
#|            h = hashlib.sha256()
#|            out = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
#|            try:
#|                while True:
#|                    b = os.read(fd, CHUNK)
#|                    if not b:
#|                        break
#|                    h.update(b)
#|                    os.write(out, b)
#|                os.fsync(out)
#|            finally:
#|                os.close(out)
#|            if _HOOK:
#|                _HOOK("after_copy", src)
#|            post = os.fstat(fd)
#|        finally:
#|            os.close(fd)
#|        try:
#|            st3 = os.lstat(src)
#|            same = (st3.st_dev, st3.st_ino) == (st.st_dev, st.st_ino)
#|        except OSError:
#|            same = False
#|        if (same and post.st_size == st.st_size == os.path.getsize(tmp) and post.st_mtime_ns == st.st_mtime_ns
#|                and _sha(src) == h.hexdigest()):
#|            os.replace(tmp, dst)
#|            _fsync_path(dst)
#|            return {"status": "OK", "attempts": attempt, "bytes": st.st_size, "sha256": h.hexdigest()}
#|        last = "source_changed_during_copy"
#|        if attempt < MAX_ATTEMPTS:
#|            sleep(RETRY_SLEEP)
#|    if os.path.lexists(dst + ".part"):
#|        os.remove(dst + ".part")
#|    return {"status": "FAILED", "reason": last, "attempts": MAX_ATTEMPTS}
#|
#|
#|COPIERS = {"sqlite": copy_sqlite, "jsonl": copy_append_only, "file": copy_small_file}
#|
#|
#|# --------------------------------------------------------------------------- run
#|
#|def run_snapshot(spec_path: str, dest: str, auth_ref: Optional[str], dry_run: bool,
#|                 space_factor: float = 2.0, reserve_mb: int = 512, sleep: Callable[[float], None] = time.sleep,
#|                 require_data: bool = False, max_total_bytes: Optional[int] = None) -> tuple[int, dict]:
#|    roots, required = load_spec(spec_path)
#|    items, skipped, by_source = expand(roots)
#|    pf = preflight(items, skipped, dest, space_factor, reserve_mb * 1024 * 1024, roots, by_source, required,
#|                   require_data, max_total_bytes)
#|    report: dict[str, Any] = {"schema": SCHEMA, "classification": "PRIVATE_DO_NOT_COMMIT", "preflight": pf,
#|                              "dry_run": dry_run}
#|    if dry_run or not pf["go"]:
#|        report["verdict"] = "GO" if pf["go"] else "NO-GO"
#|        return (0 if pf["go"] else 1), report
#|    if not auth_ref or not auth_ref.strip():
#|        report["verdict"] = "NO-GO"
#|        report["preflight"]["nogo"].append({"code": "missing_authorization_reference"})
#|        return 1, report
#|    dest = safe_new_dir(dest)                       # nuova, 0700 per costruzione; niente chmod su directory esistenti
#|    started = int(time.time() * 1000)
#|    results = []
#|    for it in items:
#|        dst = os.path.join(dest, it["rel"])
#|        mkdirs_private(dest, os.path.dirname(it["rel"]))
#|        t0 = int(time.time() * 1000)
#|        extra = {"quiescence_evidence": it.get("quiescence_evidence")} if it["kind"] == "sqlite" else {}
#|        res = COPIERS[it["kind"]](it["path"], dst, sleep=sleep, **extra)
#|        res.update({"id": it["id"], "kind": it["kind"], "src": it["path"], "dst_rel": it["rel"],
#|                    "captured_at_ms": t0, "finished_at_ms": int(time.time() * 1000)})
#|        if res["status"] == "OK" and it["kind"] == "jsonl":
#|            r = inv.read_regular(dst, parse_jsonl=True)
#|            res.update(r["_js"].result(False))
#|        if res["status"] == "OK":
#|            os.chmod(dst, 0o400)
#|        results.append(res)
#|    ended = int(time.time() * 1000)
#|    ok = bool(results) and len(results) == len(items) and all(r["status"] == "OK" for r in results)
#|    report.update({"auth_ref": auth_ref, "started_ms": started, "ended_ms": ended,
#|                   "window_seconds": round((ended - started) / 1000, 3),
#|                   "consistency": "per_item_not_atomic_across_sources", "items": results, "complete": ok,
#|                   "required_groups": required, "by_source": by_source,
#|                   "verdict": "GO" if ok else "NO-GO"})
#|    log = os.path.join(dest, "snapshot_log.json")
#|    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
#|    with os.fdopen(fd, "w", encoding="utf-8") as fh:
#|        json.dump(report, fh, indent=1, sort_keys=True)
#|    return (0 if ok else 1), report
#|
#|
#|def main(argv: Optional[list[str]] = None) -> int:
#|    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
#|    ap.add_argument("--spec", required=True)
#|    ap.add_argument("--dest", required=True, help="directory NUOVA, fuori dalle sorgenti e da qualunque repo")
#|    ap.add_argument("--auth-ref", help="riferimento all'autorizzazione esplicita (obbligatorio senza --dry-run)")
#|    ap.add_argument("--dry-run", action="store_true", help="solo preflight, nessuna copia")
#|    ap.add_argument("--space-factor", type=float, default=2.0)
#|    ap.add_argument("--reserve-mb", type=int, default=512)
#|    a = ap.parse_args(argv)
#|    if inside_git(a.dest):
#|        print("NO-GO: la destinazione non puo' stare in un working tree git")
#|        return 1
#|    try:
#|        code, rep = run_snapshot(a.spec, a.dest, a.auth_ref, a.dry_run, a.space_factor, a.reserve_mb)
#|    except (ValueError, OSError, json.JSONDecodeError) as exc:
#|        print(f"NO-GO: spec o destinazione non valida ({type(exc).__name__}: {str(exc)[:80]})")
#|        return 1
#|    pf = rep["preflight"]
#|    if code:
#|        print("NO-GO: " + ", ".join(sorted({n["code"] for n in pf["nogo"]}) or
#|                                     [r.get("reason", "?") for r in rep.get("items", []) if r["status"] != "OK"]))
#|    else:
#|        n = len(rep.get("items", [])) or pf["items"]
#|        print(f"GO ({'dry-run' if a.dry_run else 'snapshot completo'}): items={n} bytes={pf['total_source_bytes']} "
#|              f"warn={len(pf['warn'])}")
#|    return code
#|
#|
#|if __name__ == "__main__":
#|    sys.exit(main())
#@@ END snapshot

#@@ BEGIN audit
#|#!/usr/bin/env python3
#|"""Fase 0 — ripristino su directory VUOTA e audit di quadratura, SOLO su copie di laboratorio.
#|
#|Non legge mai le sorgenti: parte da snapshot_log.json e dai file copiati da snapshot.py.
#|
#|Controlli (ogni esito e' PASS / WARN / FAIL):
#|- file attesi vs presenti (mancanti / extra), SHA256 dei file ripristinati contro il log;
#|- SQLite: integrity_check, conteggi righe per tabella uguali a quelli registrati alla copia;
#|- journal V3 (tabella v3_events): catena SHA-256 ricalcolata con la STESSA formula del codice di produzione
#|  (verificatore indipendente, nessun import da backend/), collegamento previous_hash, buchi di seq,
#|  event_id duplicati, payload non canonico, conteggio per (portfolio_id, run_id), testa della catena;
#|- JSONL: righe e righe non valide uguali a quelle registrate alla copia;
#|- avvertenze: tentativi ripetuti, riga parziale in coda, finestra di cattura lunga, DB con -wal residuo.
#|
#|La catena puo' rilevare manomissioni o troncamenti interni, NON un troncamento di coda senza un'ancora
#|esterna (conteggio/testa attesi): per questo l'audit riporta count e head da confrontare con un riscontro
#|indipendente (--expect-v3 FILE.json: {"<db_id>": {"count": N, "head": "<sha256>"}}).
#|"""
#|from __future__ import annotations
#|
#|import argparse
#|import hashlib
#|import json
#|import os
#|import sqlite3
#|import stat
#|import sys
#|from typing import Any, Optional
#|from urllib.parse import quote
#|
#|if not getattr(sys, "_phase0_sealed", False):          # bundle sigillato: nessuna modifica di sys.path
#|    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#|import inventory as inv  # noqa: E402
#|from snapshot import inside_git, mkdirs_private, safe_new_dir  # noqa: E402
#|
#|GENESIS = "0" * 64
#|MAX_WINDOW_WARN_S = 900
#|
#|
#|def _digest(prev: str, event_id: str, portfolio: str, run: str, kind: str, ts: int, source: str, payload: str) -> str:
#|    # Stessa formula di backend/v3/events.py::_digest (ricopiata, non importata).
#|    fields = [prev, event_id, portfolio, run, kind, str(ts), source, payload]
#|    return hashlib.sha256(json.dumps(fields, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()
#|
#|
#|def ro_connect(path: str) -> sqlite3.Connection:
#|    con = sqlite3.connect("file:" + quote(path, safe="/") + "?mode=ro", uri=True, timeout=2)
#|    con.execute("PRAGMA query_only=1")
#|    return con
#|
#|
#|def verify_v3_chain(path: str) -> dict:
#|    """Ricalcola la catena di v3_events. Ritorna {present, ok, count, head, max_seq, per_run, errors, warnings}."""
#|    con = ro_connect(path)
#|    try:
#|        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='v3_events'").fetchone():
#|            return {"present": False}
#|        errors: list[str] = []
#|        warns: list[str] = []
#|        prev, count, last_seq, ids = GENESIS, 0, None, set()
#|        per_run: dict[str, int] = {}
#|        for (seq, eid, pf, run, kind, ts, src, payload, ph, eh) in con.execute(
#|                "SELECT seq,event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,"
#|                "previous_hash,event_hash FROM v3_events ORDER BY seq"):
#|            if last_seq is not None and seq != last_seq + 1:
#|                warns.append("seq_gap")
#|            if eid in ids:
#|                errors.append("duplicate_event_id")
#|            ids.add(eid)
#|            if ph != prev:
#|                errors.append("previous_hash_mismatch")
#|            elif eh != _digest(prev, eid, pf, run, kind, ts, src, payload):
#|                errors.append("event_hash_mismatch")
#|            try:
#|                if json.dumps(json.loads(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
#|                              allow_nan=False) != payload:
#|                    warns.append("payload_not_canonical")
#|            except ValueError:
#|                errors.append("payload_not_json")
#|            if errors:
#|                break                                       # catena rotta: il resto non e' attendibile
#|            prev, last_seq, count = eh, seq, count + 1
#|            per_run[f"{pf}/{run}"] = per_run.get(f"{pf}/{run}", 0) + 1
#|        return {"present": True, "ok": not errors, "count": count, "head": prev, "max_seq": last_seq,
#|                "per_run": per_run, "errors": sorted(set(errors)), "warnings": sorted(set(warns))}
#|    finally:
#|        con.close()
#|
#|
#|def restore(snapshot_dir: str, restore_dir: str) -> dict:
#|    log_path = os.path.join(snapshot_dir, "snapshot_log.json")
#|    with open(log_path, encoding="utf-8") as fh:
#|        log = json.load(fh)
#|    rd = os.path.abspath(restore_dir)
#|    sd = os.path.realpath(snapshot_dir)
#|    rreal = os.path.join(os.path.realpath(os.path.dirname(rd)), os.path.basename(rd))
#|    if rreal == sd or rreal.startswith(sd + os.sep) or sd.startswith(rreal + os.sep):
#|        raise ValueError("restore_dir_overlaps_snapshot")
#|    rd = safe_new_dir(rd)                           # deve essere NUOVA: mai riusare o toccare directory esistenti
#|    restored, bad = [], []
#|    for it in log["items"]:
#|        if it["status"] != "OK":
#|            continue
#|        src = os.path.join(snapshot_dir, it["dst_rel"])
#|        dst = os.path.join(rd, it["dst_rel"])
#|        mkdirs_private(rd, os.path.dirname(it["dst_rel"]))
#|        try:
#|            with open(src, "rb") as fi, open(dst, "xb") as fo:
#|                while True:
#|                    b = fi.read(inv.CHUNK)
#|                    if not b:
#|                        break
#|                    fo.write(b)
#|        except OSError as exc:
#|            bad.append({"id": it["id"], "error": type(exc).__name__})
#|            continue
#|        restored.append(it["dst_rel"])
#|    return {"restored": restored, "restore_errors": bad, "log": log}
#|
#|
#|def audit(restore_dir: str, log: dict, expect_v3: Optional[dict] = None) -> dict:
#|    fails: list[dict] = []
#|    warns: list[dict] = []
#|    checks: dict[str, Any] = {}
#|
#|    def fail(code: str, **kw):
#|        fails.append({"code": code, **kw})
#|
#|    def warn(code: str, **kw):
#|        warns.append({"code": code, **kw})
#|
#|    expected = {it["dst_rel"]: it for it in log["items"] if it["status"] == "OK"}
#|    for it in log["items"]:
#|        if it["status"] != "OK":
#|            fail("snapshot_item_not_ok", id=it["id"], reason=it.get("reason"))
#|    present = set()
#|    for d, _, fs in os.walk(restore_dir, followlinks=False):
#|        for n in fs:
#|            present.add(os.path.relpath(os.path.join(d, n), restore_dir))
#|    for rel in sorted(set(expected) - present):
#|        fail("missing_file", id=expected[rel]["id"])
#|    for rel in sorted(present - set(expected)):
#|        fail("extra_file", path=rel)
#|
#|    chains = {}
#|    for rel, it in sorted(expected.items()):
#|        p = os.path.join(restore_dir, rel)
#|        if rel not in present:
#|            continue
#|        r = inv.read_regular(p, parse_jsonl=(it["kind"] == "jsonl"))
#|        if r.get("special"):
#|            fail("not_regular_after_restore", id=it["id"])
#|            continue
#|        if r["sha256"] != it["sha256"]:
#|            fail("sha256_mismatch", id=it["id"])
#|        if it.get("attempts", 1) > 1:
#|            warn("copy_needed_retries", id=it["id"], attempts=it["attempts"])
#|        if it.get("partial_tail_bytes"):
#|            warn("partial_tail_excluded", id=it["id"], bytes=it["partial_tail_bytes"])
#|        if it["kind"] == "jsonl":
#|            res = r["_js"].result(False)
#|            for k in ("lines", "invalid_lines"):
#|                if res[k] != it.get(k):
#|                    fail("jsonl_count_mismatch", id=it["id"], field=k)
#|        if it["kind"] == "sqlite":
#|            for suffix in inv.DB_SIDE:
#|                if os.path.lexists(p + suffix):
#|                    warn("wal_or_journal_residue", id=it["id"])
#|            try:
#|                con = ro_connect(p)
#|                try:
#|                    ic = [x[0] for x in con.execute("PRAGMA integrity_check").fetchall()]
#|                    if ic != ["ok"]:
#|                        fail("integrity_check_failed", id=it["id"])
#|                    for t, n in (it.get("tables") or {}).items():
#|                        got = con.execute('SELECT COUNT(*) FROM "%s"' % t.replace('"', '""')).fetchone()[0]
#|                        if got != n:
#|                            fail("row_count_mismatch", id=it["id"], table=t)
#|                finally:
#|                    con.close()
#|                ch = verify_v3_chain(p)
#|                if ch["present"]:
#|                    chains[it["id"]] = ch
#|                    for e in ch["errors"]:
#|                        fail("v3_chain_" + e, id=it["id"])
#|                    for w in ch["warnings"]:
#|                        warn("v3_chain_" + w, id=it["id"])
#|                    ex = (expect_v3 or {}).get(it["id"])
#|                    if ex is not None and (ex.get("count") != ch["count"] or ex.get("head") != ch["head"]):
#|                        fail("v3_chain_external_anchor_mismatch", id=it["id"])
#|                    if ex is None:
#|                        warn("v3_chain_no_external_anchor", id=it["id"])
#|            except sqlite3.Error as exc:
#|                fail("sqlite_open_or_query_failed", id=it["id"], error=type(exc).__name__)
#|    if log.get("window_seconds", 0) > MAX_WINDOW_WARN_S:
#|        warn("capture_window_long", seconds=log["window_seconds"])
#|    checks["v3_chains"] = {k: {kk: v[kk] for kk in ("ok", "count", "head", "max_seq", "per_run")}
#|                           for k, v in chains.items()}
#|    verdict = "FAIL" if fails else ("WARN" if warns else "PASS")
#|    blockers = ["same_host_copy", "capture_not_atomic_across_sources"]
#|    if any(w["code"] == "v3_chain_no_external_anchor" for w in warns):
#|        blockers.append("no_external_anchor")
#|    return {"schema": 1, "certifies_backup": False, "certification_blockers": blockers, "classification": "PRIVATE_DO_NOT_COMMIT", "verdict": verdict, "fails": fails,
#|            "warnings": warns, "notes": ["capture_not_atomic_across_sources"], "checks": checks, "items_expected": len(expected), "files_present": len(present)}
#|
#|
#|def summary_of(rep: dict) -> dict:
#|    return {"schema": 1, "classification": "PUBLIC_SUMMARY_NUMBERS_ONLY", "verdict": rep["verdict"],
#|            "certifies_backup": False, "certification_blockers": rep["certification_blockers"],
#|            "fail_codes": sorted({f["code"] for f in rep["fails"]}),
#|            "warning_codes": sorted({w["code"] for w in rep["warnings"]}),
#|            "items_expected": rep["items_expected"], "files_present": rep["files_present"],
#|            "v3_chains_ok": sum(1 for c in rep["checks"]["v3_chains"].values() if c["ok"]),
#|            "v3_chains_total": len(rep["checks"]["v3_chains"])}
#|
#|
#|def _write_new(path: str, data: dict, mode: int) -> None:
#|    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
#|    with os.fdopen(fd, "w", encoding="utf-8") as fh:
#|        json.dump(data, fh, indent=1, sort_keys=True)
#|
#|
#|def main(argv: Optional[list[str]] = None) -> int:
#|    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
#|    ap.add_argument("--snapshot", required=True, help="directory prodotta da snapshot.py")
#|    ap.add_argument("--restore-dir", required=True, help="directory VUOTA di ripristino")
#|    ap.add_argument("--report", required=True, help="report PRIVATO (nuovo file, 0600, fuori da repo git)")
#|    ap.add_argument("--summary", help="riepilogo con soli codici e numeri")
#|    ap.add_argument("--expect-v3", help="JSON con ancore esterne {db_id: {count, head}}")
#|    a = ap.parse_args(argv)
#|    for p in (a.report, a.summary):
#|        if p and (os.path.lexists(p) or inv.inside_git_worktree(p)):
#|            print("NO-GO: output esistente o dentro un working tree git")
#|            return 1
#|    if inside_git(a.restore_dir):
#|        print("NO-GO: la directory di ripristino non puo' stare in un working tree git")
#|        return 1
#|    try:
#|        res = restore(a.snapshot, a.restore_dir)
#|    except (OSError, ValueError, json.JSONDecodeError) as exc:
#|        print(f"NO-GO: ripristino non eseguibile ({type(exc).__name__}: {str(exc)[:80]})")
#|        return 1
#|    expect = None
#|    if a.expect_v3:
#|        with open(a.expect_v3, encoding="utf-8") as fh:
#|            expect = json.load(fh)
#|    rep = audit(a.restore_dir, res["log"], expect)
#|    for e in res["restore_errors"]:
#|        rep["fails"].append({"code": "restore_copy_failed", **e})
#|    if res["restore_errors"]:
#|        rep["verdict"] = "FAIL"
#|    _write_new(a.report, rep, 0o600)
#|    if a.summary:
#|        _write_new(a.summary, summary_of(rep), 0o644)
#|    print(f"{'GO' if rep['verdict'] != 'FAIL' else 'NO-GO'}: audit={rep['verdict']} "
#|          f"fails={len(rep['fails'])} warnings={len(rep['warnings'])} certifies_backup=False "
#|          f"blockers={','.join(rep['certification_blockers'])}")
#|    return 0 if rep["verdict"] != "FAIL" else 1
#|
#|
#|if __name__ == "__main__":
#|    sys.exit(main())
#@@ END audit

#@@ BEGIN sealed_root
#|"""Runner PRIVILEGIATO della Fase 0 (opzione B): eseguito UNA volta dall'operatore, da un bundle sigillato.
#|
#|Principi (ognuno e' un controllo automatico con test sintetici):
#|1. Codice solo da bundle revisionato e fissato per hash: il file deve coincidere con --expect-sha256 e vivere in
#|   una directory di root (nessun antenato scrivibile da altri, nessun symlink); mai codice da cartelle
#|   modificabili dall'agente.
#|2. Nessun input dell'agente: la spec delle fonti e' INCORPORATA nel bundle (coperta dall'hash); i percorsi devono
#|   stare sotto /opt e ogni antenato deve essere di root e non scrivibile da altri (altrimenti un symlink/rinomina
#|   potrebbe far leggere a root file diversi da quelli revisionati).
#|3. Preflight prima di ogni copia: spazio, tetto di dimensione, leggibilita', gruppi obbligatori con FILE DI DATI
#|   (non solo codice), stato dei DB WAL, quiescenza verificata a RUNTIME (unita' inattive + nessun processo con il
#|   DB aperto), non la fiducia in una stringa.
#|4. Nessun servizio fermato o riavviato: si leggono stati con `systemctl list-units|show` (nient'altro), prima e
#|   dopo, e si dichiara se sono cambiati. Priorita' di CPU abbassata; lettura a passi brevi, abbandono se occupato.
#|5. Dati originali e copie PRIVATI: tutto cio' che contiene dati sta in `private/` (0700, root). L'agente puo'
#|   leggere solo `public/`: numeri, codici e hash, mai percorsi, ID o contenuti.
#|6. Ripristino provato: restore su directory vuota + audit di quadratura; la copia di ripristino viene poi rimossa.
#|7. Nessuna copia esterna qui: fase successiva, con cifratura (vedi runbook). `certifies_backup` e' SEMPRE false.
#|"""
#|from __future__ import annotations
#|
#|import argparse
#|import hashlib
#|import json
#|import os
#|import re
#|import shutil
#|import sqlite3
#|import stat
#|import subprocess
#|import sys
#|import time
#|from typing import Any, Callable, Optional
#|
#|import audit
#|import inventory as inv
#|import snapshot as snap
#|
#|SCHEMA = 1
#|BASE_DIR = "/var/lib/superbot-phase0"
#|ALLOWED_SRC_ROOT = "/opt"
#|UNIT_RE = re.compile(r"superbot-[A-Za-z0-9@:._-]{1,100}\.service")
#|STATE_PROPS = ("ActiveState", "SubState", "MainPID", "NRestarts")
#|ACTIVE_STATES = frozenset({"active", "activating", "reloading", "deactivating", "refreshing"})
#|MAX_TOTAL_GB = 10
#|Runner = Callable[[list], tuple]
#|
#|
#|# --------------------------------------------------------------------------- fiducia nel codice e nei percorsi
#|
#|def chain_problems(path: str, uid: int, include_leaf: bool = False, anchor: str = "/") -> list:
#|    """Antenati di `path` (e opzionalmente la foglia): directory vere, del proprietario atteso, non scrivibili da
#|    gruppo/altri. `anchor`: primo componente controllato (in produzione "/": TUTTA la catena; i test usano la
#|    propria radice temporanea). Ritorna l'elenco dei problemi (vuoto = fidato)."""
#|    p = os.path.abspath(path)
#|    parts = [x for x in p.split(os.sep) if x]
#|    probs = []
#|    chain = [os.sep] + [os.path.join(os.sep, *parts[:i + 1]) for i in range(len(parts) - (0 if include_leaf else 1))]
#|    if anchor != os.sep:
#|        a = os.path.abspath(anchor)
#|        if not (p == a or p.startswith(a + os.sep)):
#|            return ["outside_anchor"]
#|        chain = [c for c in chain if c == a or c.startswith(a + os.sep)]
#|    for c in chain:
#|        try:
#|            st = os.lstat(c)
#|        except OSError:
#|            probs.append("component_missing")
#|            break
#|        if stat.S_ISLNK(st.st_mode):
#|            probs.append("symlink_in_chain")
#|        elif not stat.S_ISDIR(st.st_mode) and c != p:
#|            probs.append("component_not_dir")
#|        if st.st_uid != uid:
#|            probs.append("component_not_owned_by_trusted_uid")
#|        if st.st_mode & 0o022:
#|            probs.append("component_writable_by_others")
#|    return sorted(set(probs))
#|
#|
#|def check_code_trust(path: str, data: bytes, expect_sha: str, uid: int = 0, anchor: str = "/") -> list:
#|    probs = []
#|    if hashlib.sha256(data).hexdigest() != (expect_sha or "").lower():
#|        probs.append("sha256_mismatch")
#|    try:
#|        st = os.lstat(path)
#|    except OSError:
#|        return probs + ["code_file_missing"]
#|    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
#|        probs.append("code_not_regular_file")
#|    if st.st_uid != uid:
#|        probs.append("code_not_owned_by_trusted_uid")
#|    if st.st_mode & 0o022:
#|        probs.append("code_writable_by_others")
#|    return sorted(set(probs + chain_problems(path, uid, anchor=anchor)))
#|
#|
#|# --------------------------------------------------------------------------- servizi (sola lettura)
#|
#|def default_runner(argv: list) -> tuple:
#|    """Unici comandi ammessi: systemctl list-units / show. Mai start/stop/restart, mai shell."""
#|    if len(argv) < 2 or argv[0] != "systemctl" or argv[1] not in ("list-units", "show"):
#|        raise ValueError("command_not_allowed")
#|    exe = next((p for p in ("/usr/bin/systemctl", "/bin/systemctl") if os.path.exists(p)), None)
#|    if exe is None:
#|        return 127, ""
#|    try:
#|        r = subprocess.run([exe] + argv[1:], capture_output=True, text=True, timeout=30,
#|                           env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
#|    except (OSError, subprocess.SubprocessError):
#|        return 127, ""
#|    return r.returncode, r.stdout
#|
#|
#|def unit_states(run: Runner) -> Optional[dict]:
#|    rc, out = run(["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--plain", "--no-pager"])
#|    if rc != 0:
#|        return None
#|    names = sorted({t for line in out.splitlines() for t in line.split()[:1] if UNIT_RE.fullmatch(t)})
#|    states = {}
#|    for n in names:
#|        rc2, o2 = run(["systemctl", "show", n, "--no-pager"] + [x for p in STATE_PROPS for x in ("-p", p)])
#|        d = {}
#|        for line in o2.splitlines():
#|            k, eq, v = line.partition("=")
#|            if eq and k in STATE_PROPS:
#|                d[k] = v
#|        states[n] = d if rc2 == 0 else {"error": "show_failed"}
#|    return states
#|
#|
#|def compare_states(before: Optional[dict], after: Optional[dict]) -> dict:
#|    if before is None or after is None:
#|        return {"comparable": False, "unchanged": None, "changed_units": []}
#|    changed = sorted(u for u in set(before) | set(after) if before.get(u) != after.get(u))
#|    return {"comparable": True, "unchanged": not changed, "changed_units": changed, "units": len(before)}
#|
#|
#|def open_paths(proc_root: str = "/proc") -> set:
#|    """Percorsi aperti da QUALUNQUE processo (richiede root). Nessun contenuto, solo i link in /proc/*/fd."""
#|    out = set()
#|    try:
#|        pids = [d for d in os.listdir(proc_root) if d.isdigit()]
#|    except OSError:
#|        return out
#|    for pid in pids:
#|        fd_dir = os.path.join(proc_root, pid, "fd")
#|        try:
#|            for fd in os.listdir(fd_dir):
#|                try:
#|                    t = os.readlink(os.path.join(fd_dir, fd))
#|                except OSError:
#|                    continue
#|                if t.startswith("/"):
#|                    out.add(t.removesuffix(" (deleted)"))
#|        except OSError:
#|            continue
#|    return out
#|
#|
#|def verify_quiescence(src: str, q: Optional[dict], states: Optional[dict], opened: set) -> tuple:
#|    """(ok, dettaglio). Quiescente = unita' dichiarate NON attive (se systemctl non risponde: non provato) E nessun
#|    processo ha aperto un DB (o i suoi -wal/-shm/-journal) sotto `src`."""
#|    if not q or not isinstance(q.get("units"), list):
#|        return False, "no_quiescence_declared"
#|    if states is None:
#|        return False, "systemd_unavailable"
#|    for u in q["units"]:
#|        if not UNIT_RE.fullmatch(u):
#|            return False, "bad_unit_name"
#|        if states.get(u, {}).get("ActiveState") in ACTIVE_STATES:
#|            return False, "unit_active"
#|    base = os.path.abspath(src)
#|    for p in opened:
#|        if (p == base or p.startswith(base + os.sep)) and p.lower().endswith(inv.DB_EXT + inv.DB_SIDE):
#|            return False, "db_open_by_process"
#|    return True, "units_inactive_and_no_open_db_fds"
#|
#|
#|# --------------------------------------------------------------------------- esecuzione
#|
#|def _write_json_new(path: str, obj: Any, mode: int) -> None:
#|    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
#|    with os.fdopen(fd, "w", encoding="utf-8") as fh:
#|        json.dump(obj, fh, indent=1, sort_keys=True)
#|    os.chmod(path, mode)                                   # file NUOVO: mode esplicito a prescindere dalla umask
#|
#|
#|def _mkdir_new(path: str, mode: int) -> None:
#|    os.mkdir(path)
#|    os.chmod(path, mode)                                   # directory NUOVA creata da noi
#|
#|
#|def _codes(items: list) -> list:
#|    return sorted({x["code"] for x in items})
#|
#|
#|def execute(spec: dict, mode: str, *, base: str = BASE_DIR, allowed_root: str = ALLOWED_SRC_ROOT, trusted_uid: int = 0,
#|            chain_anchor: str = "/", runner: Runner = default_runner, proc_root: str = "/proc", auth_ref: Optional[str] = None,
#|            code_sha: str = "", space_factor: float = 2.0, reserve_mb: int = 512, max_total_gb: float = MAX_TOTAL_GB,
#|            keep_restore: bool = False, sleep: Callable[[float], None] = time.sleep, now: Callable[[], float] = time.time,
#|            out: Callable[[str], None] = print) -> tuple:
#|    if mode not in ("preflight", "full"):
#|        raise ValueError("bad_mode")
#|    # ---- directory base e di esecuzione
#|    bp = os.path.abspath(base)
#|    if not os.path.lexists(bp):
#|        if chain_problems(bp, trusted_uid, anchor=chain_anchor):
#|            return 1, {"verdict": "NO-GO", "reason": "base_parent_not_trusted"}
#|        _mkdir_new(bp, 0o755)
#|    bst = os.lstat(bp)
#|    if (stat.S_ISLNK(bst.st_mode) or not stat.S_ISDIR(bst.st_mode) or bst.st_uid != trusted_uid
#|            or bst.st_mode & 0o022 or chain_problems(bp, trusted_uid, anchor=chain_anchor)):
#|        return 1, {"verdict": "NO-GO", "reason": "base_dir_not_trusted"}
#|    t0 = now()
#|    run_id = time.strftime("run-%Y%m%dT%H%M%SZ", time.gmtime(t0)) + "-" + (code_sha[:8] or "nohash")
#|    run_dir = os.path.join(bp, run_id)
#|    _mkdir_new(run_dir, 0o755)
#|    pub, priv = os.path.join(run_dir, "public"), os.path.join(run_dir, "private")
#|    _mkdir_new(pub, 0o755)
#|    _mkdir_new(priv, 0o700)
#|    _mkdir_new(os.path.join(priv, "reports"), 0o700)
#|    snapdir, restdir = os.path.join(priv, "snapshot"), os.path.join(priv, "restore")
#|
#|    summary: dict[str, Any] = {"schema": SCHEMA, "run_id": run_id, "mode": mode, "code_sha256": code_sha,
#|                               "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
#|                               "certifies_backup": False,
#|                               "certification_blockers": ["same_host_copy", "capture_not_atomic_across_sources",
#|                                                          "external_encrypted_copy_not_done"]}
#|
#|    def finish(verdict: str, code: int) -> tuple:
#|        summary["verdict"] = verdict
#|        _write_json_new(os.path.join(pub, "summary.json"), summary, 0o644)
#|        out(f"{verdict}: vedi {os.path.join(pub, 'summary.json')}")
#|        return code, summary
#|
#|    # ---- stato iniziale dei servizi (sola lettura) e file aperti
#|    before = unit_states(runner)
#|    opened = open_paths(proc_root)
#|
#|    # ---- spec incorporata -> spec risolta (evidenza di quiescenza VERIFICATA a runtime)
#|    pre_nogo: list[dict] = []
#|    issues: list[dict] = []                      # gruppo + motivo (mai percorsi) per capire subito cosa correggere
#|    resolved = []
#|    for s in spec["sources"]:
#|        sid, path = s["id"], s["path"]
#|        q = s.get("quiescence")
#|        item = {k: v for k, v in s.items() if k != "quiescence"}
#|        real_exists = os.path.lexists(path)
#|        if not (os.path.abspath(path) + os.sep).startswith(os.path.abspath(allowed_root).rstrip(os.sep) + os.sep):
#|            pre_nogo.append({"code": "source_outside_allowed_root", "id": sid})
#|            issues.append({"group": s["group"], "problems": ["outside_allowed_root"]})
#|        elif real_exists:
#|            probs = chain_problems(path, trusted_uid, anchor=chain_anchor)
#|            if probs:
#|                pre_nogo.append({"code": "source_path_not_root_controlled", "id": sid, "detail": probs})
#|                issues.append({"group": s["group"], "problems": probs})
#|        if q is not None:
#|            ok, detail = verify_quiescence(path, q, before, opened)
#|            if ok:
#|                item["quiescence_evidence"] = f"runtime:{detail}:t={int(t0)}"
#|            else:
#|                summary.setdefault("quiescence_not_proven", []).append({"id_hash": hashlib.sha256(sid.encode()).hexdigest()[:8],
#|                                                                         "why": detail})
#|        resolved.append(item)
#|    spec_path = os.path.join(priv, "spec.resolved.json")
#|    _write_json_new(spec_path, {"schema": 1, "required_groups": spec["required_groups"], "sources": resolved}, 0o600)
#|
#|    maxb = int(max_total_gb * 1024 ** 3)
#|    kw = dict(space_factor=space_factor, reserve_mb=reserve_mb, sleep=sleep, require_data=spec.get("require_data", True),
#|              max_total_bytes=maxb)
#|    try:
#|        pf_code, pf = snap.run_snapshot(spec_path, snapdir, "preflight", True, **kw)
#|    except (ValueError, OSError) as exc:
#|        summary["preflight"] = {"go": False, "nogo_codes": ["spec_or_path_invalid:" + type(exc).__name__]}
#|        return finish("NO-GO", 1)
#|    pfs = pf["preflight"]
#|    nogo = list(pfs["nogo"]) + pre_nogo
#|    summary["preflight"] = {"go": not nogo, "nogo_codes": _codes(nogo), "warn_codes": _codes(pfs["warn"]),
#|                            "items": pfs["items"], "total_source_bytes": pfs["total_source_bytes"],
#|                            "free_bytes": pfs["free_bytes"], "bytes_by_group": pfs.get("bytes_by_group", {}),
#|                            "excluded": pfs["skipped"], "max_total_bytes": maxb}
#|    after = unit_states(runner)
#|    summary["services"] = compare_states(before, after)
#|    summary["source_issues"] = sorted(issues, key=lambda x: (x["group"], x["problems"]))
#|    if nogo:
#|        return finish("NO-GO", 1)
#|    if mode == "preflight":
#|        return finish("PREFLIGHT_GO", 0)
#|    if not auth_ref or not auth_ref.strip():
#|        summary["preflight"]["nogo_codes"].append("missing_authorization_reference")
#|        return finish("NO-GO", 1)
#|
#|    # ---- snapshot reale (copie coerenti per file, in private/)
#|    code, rep = snap.run_snapshot(spec_path, snapdir, auth_ref, False, **kw)
#|    items = rep.get("items", [])
#|    summary["snapshot"] = {"complete": bool(rep.get("complete")), "items": len(items),
#|                           "items_ok": sum(1 for i in items if i["status"] == "OK"),
#|                           "failed_reasons": sorted({i.get("reason", "?") for i in items if i["status"] != "OK"}),
#|                           "retried_items": sum(1 for i in items if i.get("attempts", 1) > 1),
#|                           "partial_tail_items": sum(1 for i in items if i.get("partial_tail_bytes")),
#|                           "window_seconds": rep.get("window_seconds"), "consistency": rep.get("consistency")}
#|    if code != 0:
#|        summary["services"] = compare_states(before, unit_states(runner))
#|        return finish("NO-GO", 1)
#|
#|    # ---- manifest SHA256 sulla copia (privato) + riepilogo numerico (pubblico)
#|    ns = argparse.Namespace(include_db=True, sqlite=True, include_ids=False, git_repo=None)
#|    manifest = inv.build([("snapshot", snapdir)], ns)
#|    _write_json_new(os.path.join(priv, "reports", "manifest.json"), manifest, 0o600)
#|    msum = inv.summary_of(manifest)
#|    _write_json_new(os.path.join(pub, "manifest_summary.json"), msum, 0o644)
#|    summary["manifest"] = {k: msum[k] for k in ("complete", "files_hashed", "unstable_count", "manifest_digest")}
#|
#|    # ---- ripristino su directory vuota + audit
#|    res = audit.restore(snapdir, restdir)
#|    rep_a = audit.audit(restdir, res["log"], None)
#|    for e in res["restore_errors"]:
#|        rep_a["fails"].append({"code": "restore_copy_failed", **e})
#|    if res["restore_errors"]:
#|        rep_a["verdict"] = "FAIL"
#|    _write_json_new(os.path.join(priv, "reports", "audit.json"), rep_a, 0o600)
#|    asum = audit.summary_of(rep_a)
#|    _write_json_new(os.path.join(pub, "audit_summary.json"), asum, 0o644)
#|    chains = rep_a["checks"]["v3_chains"]
#|    anchors = {k: {"count": v["count"], "head": v["head"]} for k, v in chains.items()}
#|    _write_json_new(os.path.join(priv, "reports", "anchors.json"), anchors, 0o600)
#|    digest = hashlib.sha256(json.dumps(sorted((k, v["count"], v["head"]) for k, v in anchors.items()),
#|                                       separators=(",", ":")).encode()).hexdigest()
#|    summary["audit"] = {"verdict": asum["verdict"], "fail_codes": asum["fail_codes"],
#|                        "warning_codes": asum["warning_codes"], "v3_chains_ok": asum["v3_chains_ok"],
#|                        "v3_chains_total": asum["v3_chains_total"], "anchors_digest": digest}
#|    summary["certification_blockers"] = asum["certification_blockers"] + [
#|        b for b in summary["certification_blockers"] if b not in asum["certification_blockers"]]
#|    if not keep_restore:
#|        shutil.rmtree(restdir)                              # la copia di ripristino e' solo una prova: si rimuove
#|    summary["services"] = compare_states(before, unit_states(runner))
#|    if rep_a["verdict"] == "FAIL" or not manifest["complete"]:
#|        return finish("NO-GO", 1)
#|    return finish("SNAPSHOT_GO", 0)
#|
#|
#|# --------------------------------------------------------------------------- CLI
#|
#|def main(argv: list, *, data: bytes, spec: dict, code_path: str, module_hashes: Optional[dict] = None) -> int:
#|    ap = argparse.ArgumentParser(prog="phase0_sealed.py", description=__doc__.split("\n")[0])
#|    sub = ap.add_subparsers(dest="cmd", required=True)
#|    sub.add_parser("selftest", help="nessun privilegio, nessun dato: versioni e hash dei moduli incorporati")
#|    for name, hlp in (("preflight", "SOLA LETTURA di metadati: nessuna copia"),
#|                      ("full", "preflight + snapshot + manifest + ripristino + audit")):
#|        p = sub.add_parser(name, help=hlp)
#|        p.add_argument("--expect-sha256", required=True, help="hash atteso di QUESTO file (dal messaggio dell'operatore)")
#|        p.add_argument("--auth-ref", required=(name == "full"))
#|        p.add_argument("--max-total-gb", type=float, default=MAX_TOTAL_GB)
#|        p.add_argument("--keep-restore", action="store_true")
#|    a = ap.parse_args(argv)
#|    sha = hashlib.sha256(data).hexdigest()
#|    if a.cmd == "selftest":
#|        ok = sys.version_info >= (3, 8) and hasattr(sqlite3.Connection, "backup")
#|        print(json.dumps({"bundle_sha256": sha, "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
#|                          "backup_api": hasattr(sqlite3.Connection, "backup"), "modules": module_hashes or {},
#|                          "sources": len(spec["sources"]), "required_groups": spec["required_groups"],
#|                          "euid": os.geteuid()}, indent=1, sort_keys=True))
#|        return 0 if ok else 1
#|    if os.geteuid() != 0:
#|        print("NO-GO: richiede root (opzione B: esecuzione dell'operatore); nessuna azione eseguita")
#|        return 2
#|    probs = check_code_trust(code_path, data, a.expect_sha256, 0)
#|    if probs:
#|        print("NO-GO: codice non fidato (" + ", ".join(probs) + "); nessuna azione eseguita")
#|        return 2
#|    try:
#|        os.nice(19)
#|    except OSError:
#|        pass
#|    code, _ = execute(spec, a.cmd, auth_ref=getattr(a, "auth_ref", None), code_sha=sha,
#|                      max_total_gb=a.max_total_gb, keep_restore=getattr(a, "keep_restore", False))
#|    return code
#@@ END sealed_root

#@@ BEGIN sources.json
#|{
#|  "schema": 1,
#|  "_comment": "Spec INCORPORATA nel bundle sigillato (coperta dall'hash). Percorsi pubblici dichiarati nel repository e confermati in parte dallo STEP 1: la verifica reale e' il preflight (NO-GO se mancano). 'quiescence.units' = unita' che devono risultare NON attive e senza DB aperti per ammettere la copia di un DB WAL senza -wal/-shm; le sorgenti con servizi attivi NON dichiarano quiescenza. 'optional' = ammessa se assente, ma ogni gruppo obbligatorio richiede almeno una sorgente non opzionale e almeno un FILE DI DATI (sqlite/jsonl).",
#|  "require_data": true,
#|  "required_groups": ["falco", "toro", "brain_storico", "arena_deepseek", "arena_qwen", "arena_minimax"],
#|  "sources": [
#|    {"id": "falco_data", "group": "falco", "kind": "tree", "path": "/opt/superbot-desk-data/hawk",
#|     "quiescence": {"units": ["superbot-v3-paper-falco.service", "superbot-v3-falco-exit.service"]}},
#|    {"id": "v3_falco_run", "group": "falco", "kind": "tree", "optional": true,
#|     "path": "/opt/superbot-v3-paper-runs/classic-hawk-paper20261111",
#|     "quiescence": {"units": ["superbot-v3-paper-falco.service", "superbot-v3-falco-exit.service"]}},
#|    {"id": "toro_data", "group": "toro", "kind": "tree", "path": "/opt/superbot-desk-data/bull",
#|     "quiescence": {"units": ["superbot-v3-paper-toro.service", "superbot-v3-toro-exit.service"]}},
#|    {"id": "v3_toro_run", "group": "toro", "kind": "tree", "optional": true,
#|     "path": "/opt/superbot-v3-paper-runs/classic-bull-paper20261111",
#|     "quiescence": {"units": ["superbot-v3-paper-toro.service", "superbot-v3-toro-exit.service"]}},
#|    {"id": "brain_free", "group": "brain_storico", "kind": "tree", "path": "/opt/superbot-brain-free",
#|     "quiescence": {"units": ["superbot-v3-paper-brain-runner.service", "superbot-brain-worker.service",
#|                              "superbot-v3-paper-brain.service"]}},
#|    {"id": "v3_brain_run", "group": "brain_storico", "kind": "tree", "optional": true,
#|     "path": "/opt/superbot-v3-paper-runs/brain-v3-paper20261111"},
#|    {"id": "arena_deepseek", "group": "arena_deepseek", "kind": "tree", "path": "/opt/superbot-ai-arena-paper/deepseek"},
#|    {"id": "arena_qwen", "group": "arena_qwen", "kind": "tree", "path": "/opt/superbot-ai-arena-paper/qwen"},
#|    {"id": "arena_minimax", "group": "arena_minimax", "kind": "tree", "path": "/opt/superbot-ai-arena-paper/minimax"}
#|  ]
#|}
#@@ END sources.json
