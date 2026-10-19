#!/usr/bin/env python3
"""Backup verificato di un database SQLite (app o pool) mentre e' in uso.

Cosa fa, nell'ordine:
  1. copia consistente con l'API di backup di SQLite (non un semplice "cp",
     che su un database in uso puo' dare un file incompleto);
  2. controlla l'intestazione del file e `PRAGMA integrity_check`;
  3. confronta lo schema della copia con quello del database vivo;
  4. prova di ripristino: ricopia il backup in una cartella temporanea,
     verifica che sia byte per byte identico, lo riapre e confronta
     integrita' e numero di righe di ogni tabella;
  5. tiene solo le ultime N copie con lo stesso prefisso.

Non modifica mai il database di origine. Esce con codice 1 se qualcosa non
torna: un deploy che dipende da questo backup deve fermarsi.
"""
import argparse
import hashlib
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time

HEADER = b"SQLite format 3\x00"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tables(conn):
    rows = conn.execute(
        "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
    ).fetchall()
    return sorted(r[0] for r in rows)


def counts(conn):
    return {t: conn.execute('select count(*) from "%s"' % t.replace('"', '""')).fetchone()[0]
            for t in tables(conn)}


def fail(msg, partial=None):
    print("ERRORE BACKUP DB: " + msg)
    if partial and os.path.exists(partial):
        try:
            os.replace(partial, partial + ".FALLITO")
        except OSError:
            pass
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--keep", type=int, default=10)
    a = ap.parse_args()

    if not os.path.isfile(a.src) or os.path.getsize(a.src) == 0:
        print("BACKUP DB: nessun database in %s, niente da salvare." % a.src)
        return 0

    os.makedirs(a.dir, mode=0o700, exist_ok=True)
    os.chmod(a.dir, 0o700)
    ts = time.strftime("%Y%m%d-%H%M%S")
    final = os.path.join(a.dir, "%s-%s.db" % (a.prefix, ts))
    part = final + ".part"

    # 1. copia consistente
    try:
        src = sqlite3.connect(a.src, timeout=60)
        dst = sqlite3.connect(part)
        src.backup(dst)
        dst.close()
        live_tables = tables(src)
        src.close()
    except sqlite3.Error as e:
        return fail("copia del database non riuscita: %s" % e, part)
    os.chmod(part, 0o600)

    # 2. intestazione e integrita'
    with open(part, "rb") as f:
        if f.read(16) != HEADER:
            return fail("la copia non ha l'intestazione SQLite", part)
    c = sqlite3.connect(part)
    integrity = c.execute("pragma integrity_check").fetchone()[0]
    copy_tables = tables(c)
    copy_counts = counts(c)
    c.close()
    if integrity != "ok":
        return fail("integrity_check della copia: %s" % integrity, part)

    # 3. schema uguale a quello vivo
    if copy_tables != live_tables:
        return fail("le tabelle della copia non coincidono con quelle del database vivo", part)

    os.replace(part, final)
    digest = sha256(final)

    # 4. prova di ripristino in una cartella temporanea
    with tempfile.TemporaryDirectory(dir=a.dir) as td:
        restored = os.path.join(td, "ripristino-di-prova.db")
        shutil.copyfile(final, restored)
        if sha256(restored) != digest:
            return fail("il file ripristinato non e' identico al backup", final)
        c = sqlite3.connect("file:%s?mode=ro" % restored, uri=True)
        integrity2 = c.execute("pragma integrity_check").fetchone()[0]
        restored_counts = counts(c)
        c.close()
        if integrity2 != "ok":
            return fail("integrity_check del file ripristinato: %s" % integrity2, final)
        if restored_counts != copy_counts:
            return fail("il numero di righe del file ripristinato non coincide col backup", final)

    # 5. conserva solo le ultime N copie con questo prefisso
    pat = re.compile(r"^%s-\d{8}-\d{6}\.db$" % re.escape(a.prefix))
    olds = sorted(n for n in os.listdir(a.dir) if pat.match(n))
    removed = 0
    for n in olds[:-a.keep] if a.keep > 0 else []:
        os.remove(os.path.join(a.dir, n))
        removed += 1

    print("BACKUP DB OK: %s" % os.path.basename(final))
    print("  dimensione %d byte, sha256 %s..." % (os.path.getsize(final), digest[:16]))
    print("  integrity_check: ok | tabelle: %d | righe totali: %d"
          % (len(copy_tables), sum(copy_counts.values())))
    print("  prova di ripristino: identico, riaperto, integrita' e righe uguali")
    print("  copie con prefisso '%s' conservate: %d (eliminate le piu' vecchie: %d)"
          % (a.prefix, min(len(olds), a.keep), removed))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except (sqlite3.Error, OSError) as e:
        print("ERRORE BACKUP DB: %s" % e)
        code = 1
    sys.exit(code)
