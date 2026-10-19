#!/usr/bin/env python3
"""Backup verificato di un database SQLite (app o pool) mentre e' in uso.

Cosa fa, nell'ordine:
  0. prende un blocco esclusivo sulla cartella dei backup (due backup insieme
     non si pestano) e sceglie un nome che non esiste ancora: una copia
     esistente non viene MAI sovrascritta;
  1. copia consistente con l'API di backup di SQLite (non un semplice "cp",
     che su un database in uso puo' dare un file incompleto);
  2. controlla l'intestazione del file e `PRAGMA integrity_check`;
  3. confronta lo schema COMPLETO (tabelle, indici, viste, trigger, con il
     loro SQL) e `user_version` della copia con quelli del database vivo;
  4. prova di ripristino: ricopia il backup in una cartella temporanea,
     verifica che sia byte per byte identico, lo riapre e confronta
     integrita', schema e numero di righe di ogni tabella;
  5. tiene solo le ultime N copie con lo stesso prefisso.

Se il database NON esiste (o e' vuoto) e' un ERRORE (uscita 1): un deploy che
dipende da questo backup deve fermarsi. Solo con --allow-missing l'assenza e'
accettata (per esempio il primissimo deploy su un server vuoto).

Non modifica mai il database di origine. Esce con codice 1 se qualcosa non torna.
"""
import argparse
import fcntl
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


def schema(conn):
    """Schema completo: tipo, nome, tabella e SQL di ogni oggetto, piu' user_version."""
    rows = conn.execute(
        "select type, name, tbl_name, coalesce(sql, '') from sqlite_master "
        "where name not like 'sqlite_%' order by type, name"
    ).fetchall()
    return [tuple(r) for r in rows], conn.execute("pragma user_version").fetchone()[0]


def schema_diff(a, b):
    """Descrizione leggibile della differenza tra due schemi, o None se uguali."""
    (ra, va), (rb, vb) = a, b
    if va != vb:
        return "user_version diversa (%s contro %s)" % (va, vb)
    da, db = {(t, n): (tb, s) for t, n, tb, s in ra}, {(t, n): (tb, s) for t, n, tb, s in rb}
    missing = sorted(set(da) - set(db))
    extra = sorted(set(db) - set(da))
    changed = sorted(k for k in set(da) & set(db) if da[k] != db[k])
    if not (missing or extra or changed):
        return None
    parts = []
    if missing:
        parts.append("mancano nella copia: " + ", ".join("%s %s" % k for k in missing))
    if extra:
        parts.append("in piu' nella copia: " + ", ".join("%s %s" % k for k in extra))
    if changed:
        parts.append("definizione diversa: " + ", ".join("%s %s" % k for k in changed))
    return "; ".join(parts)


def fail(msg, partial=None):
    print("ERRORE BACKUP DB: " + msg)
    if partial and os.path.exists(partial):
        try:
            dest = partial + ".FALLITO"
            n = 0
            while os.path.exists(dest):
                n += 1
                dest = "%s.FALLITO.%d" % (partial, n)
            os.replace(partial, dest)
        except OSError:
            pass
    return 1


def take_lock(directory, timeout=300):
    """Blocco esclusivo condiviso con backup_brain.py (stesso file)."""
    fd = os.open(os.path.join(directory, ".backup.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    end = time.time() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except OSError:
            if time.time() > end:
                os.close(fd)
                raise TimeoutError("un altro backup e' in corso da oltre %d secondi" % timeout)
            time.sleep(1)


def free_name(directory, prefix):
    """Nome mai usato prima (ne' come copia ne' come .part ne' come .FALLITO)."""
    for _ in range(6):
        ts = time.strftime("%Y%m%d-%H%M%S")
        final = os.path.join(directory, "%s-%s.db" % (prefix, ts))
        if not any(os.path.exists(final + s) for s in ("", ".part", ".FALLITO")):
            return final
        time.sleep(1.1)
    raise OSError("impossibile trovare un nome libero per la copia")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--keep", type=int, default=10)
    ap.add_argument("--allow-missing", action="store_true",
                    help="se il database non esiste non e' un errore (di norma lo e')")
    a = ap.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.prefix):
        print("ERRORE BACKUP DB: prefisso non valido")
        return 1

    if not os.path.isfile(a.src) or os.path.getsize(a.src) == 0:
        if a.allow_missing:
            print("BACKUP DB: nessun database in %s (accettato con --allow-missing)." % a.src)
            return 0
        print("ERRORE BACKUP DB: il database %s non esiste o e' vuoto. "
              "Senza un database da salvare il deploy non deve proseguire." % a.src)
        return 1

    os.makedirs(a.dir, mode=0o700, exist_ok=True)
    os.chmod(a.dir, 0o700)
    lock_fd = take_lock(a.dir)
    try:
        return run(a)
    finally:
        os.close(lock_fd)


def run(a):
    final = free_name(a.dir, a.prefix)
    part = final + ".part"

    # 1. copia consistente
    try:
        src = sqlite3.connect(a.src, timeout=60)
        dst = sqlite3.connect(part)
        src.backup(dst)
        dst.close()
        live_schema = schema(src)
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
    copy_schema = schema(c)
    copy_counts = counts(c)
    c.close()
    if integrity != "ok":
        return fail("integrity_check della copia: %s" % integrity, part)

    # 3. schema completo uguale a quello vivo
    diff = schema_diff(live_schema, copy_schema)
    if diff:
        return fail("lo schema della copia non coincide con quello del database vivo: " + diff, part)

    # pubblicazione senza sovrascrivere nulla: os.link fallisce se il nome esiste
    try:
        os.link(part, final)
    except FileExistsError:
        return fail("il nome %s esiste gia': nessuna copia sovrascritta" % os.path.basename(final), part)
    os.unlink(part)
    digest = sha256(final)

    # 4. prova di ripristino in una cartella temporanea
    with tempfile.TemporaryDirectory(dir=a.dir) as td:
        restored = os.path.join(td, "ripristino-di-prova.db")
        shutil.copyfile(final, restored)
        if sha256(restored) != digest:
            return fail("il file ripristinato non e' identico al backup", final)
        c = sqlite3.connect("file:%s?mode=ro" % restored, uri=True)
        integrity2 = c.execute("pragma integrity_check").fetchone()[0]
        restored_schema = schema(c)
        restored_counts = counts(c)
        c.close()
        if integrity2 != "ok":
            return fail("integrity_check del file ripristinato: %s" % integrity2, final)
        if schema_diff(copy_schema, restored_schema):
            return fail("lo schema del file ripristinato non coincide col backup", final)
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
    print("  integrity_check: ok | oggetti nello schema: %d | tabelle: %d | righe totali: %d"
          % (len(copy_schema[0]), len(copy_counts), sum(copy_counts.values())))
    print("  schema completo identico al database vivo | prova di ripristino: identico, riaperto, integrita', schema e righe uguali")
    print("  copie con prefisso '%s' conservate: %d (eliminate le piu' vecchie: %d)"
          % (a.prefix, min(len(olds), a.keep), removed))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except (sqlite3.Error, OSError, TimeoutError) as e:
        print("ERRORE BACKUP DB: %s" % e)
        code = 1
    sys.exit(code)
