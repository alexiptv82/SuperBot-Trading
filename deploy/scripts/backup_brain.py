#!/usr/bin/env python3
"""Backup verificato del "cervello" dei bot (Hawk e Bull), prima di un deploy.

Regola dell'utente: i file del cervello (trade_history.jsonl, lessons.md,
errors.md, learning_log.jsonl) non si cancellano, non si azzerano, non si
modificano. Questo script li SOLO LEGGE e ne fa una copia a parte.

Per ogni file dei due portfolio:
  - i quattro file del cervello crescono soltanto, quindi la copia deve
    essere identica ai primi byte dell'originale e non piu' corta di quanto
    era l'originale prima di copiarlo;
  - i database SQLite (se ce ne sono) si copiano con l'API di backup;
  - gli altri file si copiano e si confrontano per hash, con qualche
    tentativo se il bot li sta riscrivendo in quel momento.
Poi una prova di ripristino rilegge tutta la copia dal disco e la confronta
con il manifesto (hash di ogni file, righe dei file del cervello).

Esce con codice 1 se un file del cervello non e' stato copiato bene.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import time

CRITICAL = ("trade_history.jsonl", "lessons.md", "errors.md", "learning_log.jsonl")
SQLITE_EXT = (".db", ".sqlite", ".sqlite3")
SKIP_SUFFIX = ("-wal", "-shm", "-journal", ".part")
BIG = 50 * 1024 * 1024  # file non critici piu' grandi di cosi' non si copiano
PORTFOLIOS = ("hawk", "bull")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_prefix(src, dst):
    """True se dst e' identico ai primi len(dst) byte di src."""
    left = os.path.getsize(dst)
    with open(src, "rb") as a, open(dst, "rb") as b:
        while left > 0:
            n = min(1 << 20, left)
            x, y = a.read(n), b.read(n)
            if not x or x != y:
                return False
            left -= len(x)
    return True


def count_lines(path):
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return n


def jsonl_ok(path):
    """Ogni riga e' JSON valido; l'ultima puo' essere troncata se il file non finisce con a capo."""
    with open(path, "rb") as f:
        lines = f.read().split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
        tail_complete = True
    else:
        tail_complete = False
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except ValueError:
            if i == len(lines) - 1 and not tail_complete:
                continue
            return False
    return True


def copy_critical(src, dst):
    for _ in range(3):
        before = os.path.getsize(src)
        shutil.copyfile(src, dst)
        size = os.path.getsize(dst)
        if size >= before and is_prefix(src, dst):
            return True
        time.sleep(0.5)
    return False


def copy_other(src, dst):
    for _ in range(3):
        shutil.copyfile(src, dst)
        if sha256(src) == sha256(dst):
            return True
        time.sleep(0.5)
    return False


def copy_sqlite(src, dst):
    s = sqlite3.connect(src, timeout=60)
    d = sqlite3.connect(dst)
    s.backup(d)
    d.close()
    s.close()
    c = sqlite3.connect(dst)
    ok = c.execute("pragma integrity_check").fetchone()[0] == "ok"
    c.close()
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="cartella che contiene hawk/ e bull/")
    ap.add_argument("--dir", required=True, help="cartella dei backup")
    ap.add_argument("--keep", type=int, default=10)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()

    present = [p for p in PORTFOLIOS if os.path.isdir(os.path.join(a.root, p))]
    if not present:
        print("BACKUP CERVELLO: nessuna cartella dati in %s, niente da salvare." % a.root)
        return 0

    os.makedirs(a.dir, mode=0o700, exist_ok=True)
    os.chmod(a.dir, 0o700)
    name = "bots-" + time.strftime("%Y%m%d-%H%M%S") + (("-" + a.tag) if a.tag else "")
    out = os.path.join(a.dir, name)
    os.makedirs(out, mode=0o700)

    problems, warnings, manifest, skipped = [], [], [], []

    for p in present:
        base = os.path.join(a.root, p)
        for dp, dn, fn in os.walk(base):
            dn.sort()
            for f in sorted(fn):
                s = os.path.join(dp, f)
                if os.path.islink(s) or f.endswith(SKIP_SUFFIX):
                    continue
                rel = os.path.relpath(s, a.root)
                d = os.path.join(out, rel)
                os.makedirs(os.path.dirname(d), exist_ok=True)
                critical = f in CRITICAL and dp == base
                try:
                    if f.endswith(SQLITE_EXT):
                        ok = copy_sqlite(s, d)
                        if not ok:
                            problems.append("database %s: integrity_check non ok" % rel)
                    elif critical:
                        ok = copy_critical(s, d)
                        if not ok:
                            problems.append("file del cervello %s: copia incompleta o diversa" % rel)
                    else:
                        if os.path.getsize(s) > BIG:
                            skipped.append(rel)
                            continue
                        ok = copy_other(s, d)
                        if not ok:
                            warnings.append("%s: cambia di continuo, copia non verificabile" % rel)
                except OSError as e:
                    ok = False
                    (problems if critical else warnings).append("%s: %s" % (rel, e))
                if os.path.exists(d):
                    manifest.append({
                        "file": rel,
                        "size": os.path.getsize(d),
                        "sha256": sha256(d),
                        "critical": critical,
                        "righe": count_lines(d) if critical else None,
                    })

    # i file del cervello che esistono nell'origine devono esistere nella copia
    for p in present:
        for c in CRITICAL:
            if os.path.isfile(os.path.join(a.root, p, c)) and \
                    not os.path.isfile(os.path.join(out, p, c)):
                problems.append("file del cervello mancante nella copia: %s/%s" % (p, c))

    with open(os.path.join(out, "MANIFEST.json"), "w") as f:
        json.dump({"creato": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "file": manifest, "non_copiati_troppo_grandi": skipped}, f, indent=1)
    os.chmod(os.path.join(out, "MANIFEST.json"), 0o600)

    # prova di ripristino: rilegge dal disco la copia e la confronta col manifesto
    for m in manifest:
        path = os.path.join(out, m["file"])
        if not os.path.isfile(path) or sha256(path) != m["sha256"]:
            problems.append("prova di ripristino: %s non coincide col manifesto" % m["file"])
        elif m["critical"] and m["file"].endswith(".jsonl") and not jsonl_ok(path):
            problems.append("prova di ripristino: %s contiene righe JSON non valide" % m["file"])

    print("BACKUP CERVELLO: %s" % name)
    for p in present:
        parts = []
        for m in manifest:
            if m["critical"] and m["file"].startswith(p + os.sep):
                parts.append("%s %d righe" % (os.path.basename(m["file"]), m["righe"]))
        n = sum(1 for m in manifest if m["file"].startswith(p + os.sep))
        print("  %s: %d file | %s" % (p, n, ", ".join(parts) if parts else "nessun file del cervello"))
    for s in skipped:
        print("  non copiato (oltre %d MB, non e' del cervello): %s" % (BIG // (1 << 20), s))
    for w in warnings:
        print("  ATTENZIONE: " + w)

    if problems:
        for pr in problems:
            print("  ERRORE: " + pr)
        os.replace(out, out + "-INCOMPLETO")
        print("RISULTATO: FALLITO. Non si deve sostituire nessun container.")
        return 1

    pat = re.compile(r"^bots-\d{8}-\d{6}(-[A-Za-z0-9_]+)?$")
    olds = sorted(n for n in os.listdir(a.dir) if pat.match(n)
                  and os.path.isdir(os.path.join(a.dir, n)))
    removed = 0
    for n in olds[:-a.keep] if a.keep > 0 else []:
        shutil.rmtree(os.path.join(a.dir, n))
        removed += 1
    print("  prova di ripristino: ogni file riletto, hash e righe uguali al manifesto")
    print("  copie dei bot conservate: %d (eliminate le piu' vecchie: %d)"
          % (min(len(olds), a.keep), removed))
    print("RISULTATO: OK")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except (sqlite3.Error, OSError) as e:
        print("ERRORE BACKUP CERVELLO: %s" % e)
        print("RISULTATO: FALLITO. Non si deve sostituire nessun container.")
        code = 1
    sys.exit(code)
