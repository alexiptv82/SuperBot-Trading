#!/usr/bin/env python3
"""Verifica e ripristino di un backup ESTERNO cifrato di SuperBot (prodotto da external_backup.py).

Uso:
  restore_external_backup.py --archive superbot-backup-AAAAMMGGTHHMMSSZ.tar.gz.age \\
      --identity chiave-di-recupero.txt --out /cartella/vuota [--manifest ...manifest.json]

Serve la chiave PRIVATA di recupero (quella che l'utente custodisce fuori da GitHub). Non tocca mai il
server di produzione: scrive soltanto dentro --out, che deve essere vuota o inesistente.

Passi (qualunque difetto = uscita 1, e --out resta per l'esame):
  1. SHA-256 e dimensione dell'archivio cifrato uguali al manifesto in chiaro (se c'e');
  2. decifratura con age (la cifratura e' autenticata: un archivio alterato non si decifra);
  3. estrazione SICURA: solo file normali sotto dati/, niente percorsi assoluti, niente "..", niente link;
  4. manifesto interno: ogni file presente, con la dimensione e lo SHA-256 dichiarati, nessun file in piu';
  5. database: integrity_check "ok" e conteggio righe per tabella;
  6. cervello di Hawk e Bull: file irrinunciabili presenti, JSONL completi, state_v2.json valido, hash e
     righe uguali al manifesto del backup del cervello;
  7. la copia del cervello deve avere il CONFINE DI CICLO VERIFICATO, oppure un'eccezione esplicita e
     ammessa scritta nel suo manifesto (bot fermo, prima installazione), che viene dichiarata nell'esito;
  8. coerenza SEMANTICA per ogni portafoglio: i trade chiusi nello stato coincidono (id, apertura, chiusura,
     risultato) con le righe dello storico della stessa run; nessun id oltre next_id; nessuna chiusura prima
     dell'apertura; nessuna run futura nello storico o nel registro di apprendimento; contabilita': senza
     posizioni aperte cassa = capitale iniziale + somma dei risultati (tolleranza 1 centesimo), con
     posizioni aperte la cassa non puo' superare quella somma.
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
INTERNAL_MANIFEST = "INTERNAL-MANIFEST.json"


def load_brain():
    spec = importlib.util.spec_from_file_location("backup_brain_lib", os.path.join(HERE, "backup_brain.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Problems(list):
    def add(self, msg):
        self.append(msg)
        print("  ERRORE: " + msg)


def safe_extract(tar_path, out, problems):
    """Estrae solo file normali sotto dati/ (e il manifesto interno). Restituisce l'elenco dei file estratti."""
    done = []
    with tarfile.open(tar_path, mode="r:gz") as tar:
        for m in tar:
            name = m.name
            if not m.isreg():
                problems.add("voce non ammessa nell'archivio (non e' un file normale): %s" % name)
                continue
            parts = name.split("/")
            if name.startswith("/") or ".." in parts or "\\" in name:
                problems.add("percorso pericoloso nell'archivio: %s" % name)
                continue
            if name != INTERNAL_MANIFEST and parts[0] != "dati":
                problems.add("file fuori da dati/ nell'archivio: %s" % name)
                continue
            dest = os.path.join(out, *parts)
            if os.path.commonpath([os.path.abspath(dest), os.path.abspath(out)]) != os.path.abspath(out):
                problems.add("percorso fuori dalla cartella di ripristino: %s" % name)
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            src = tar.extractfile(m)
            with open(dest, "wb") as f:
                shutil.copyfileobj(src, f)
            done.append(name)
    return done


def check_databases(out, problems):
    base = os.path.join(out, "dati", "database")
    found = 0
    if not os.path.isdir(base):
        problems.add("manca la cartella dei database nell'archivio")
        return
    for f in sorted(os.listdir(base)):
        if not f.endswith(".db"):
            continue
        found += 1
        path = os.path.join(base, f)
        try:
            con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
            ok = con.execute("pragma integrity_check").fetchone()[0]
            tables = [r[0] for r in con.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
            rows = sum(con.execute('select count(*) from "%s"' % t.replace('"', '""')).fetchone()[0] for t in tables)
            con.close()
        except sqlite3.Error as e:
            problems.add("database %s illeggibile: %s" % (f, e))
            continue
        if ok != "ok":
            problems.add("database %s: integrity_check = %s" % (f, ok))
        print("  database %s: integrity_check ok | %d tabelle | %d righe" % (f, len(tables), rows))
    if found < 2:
        problems.add("attesi almeno due database (app e pool), trovati %d" % found)


def check_brain(out, problems):
    brain = load_brain()
    root = os.path.join(out, "dati", "cervello")
    snaps = sorted(d for d in os.listdir(root) if d.startswith("bots-")) if os.path.isdir(root) else []
    if len(snaps) != 1:
        problems.add("attesa una sola copia del cervello (bots-*), trovate %d" % len(snaps))
        return
    snap = os.path.join(root, snaps[0])
    try:
        with open(os.path.join(snap, "MANIFEST.json")) as f:
            man = json.load(f)
    except (OSError, ValueError):
        problems.add("manifesto del backup del cervello mancante o illeggibile")
        return
    for p in ("hawk", "bull"):
        if not os.path.isdir(os.path.join(snap, p)):
            problems.add("manca il portafoglio %s" % p)
            continue
    for x in brain.required_missing(snap, [p for p in ("hawk", "bull")]):
        problems.add("file irrinunciabile mancante o vuoto: %s" % x)
    for m in man.get("file", []):
        path = os.path.join(snap, m["file"])
        if not os.path.isfile(path) or sha256_file(path) != m["sha256"]:
            problems.add("cervello: %s non coincide col suo manifesto" % m["file"])
            continue
        base = os.path.basename(m["file"])
        if base in brain.CRITICAL and base.endswith(".jsonl"):
            why = brain.jsonl_problem(path)
            if why:
                problems.add("cervello: %s non e' un JSONL completo (%s)" % (m["file"], why))
        if base == "state_v2.json" and not brain.json_ok(path):
            problems.add("cervello: %s non e' un JSON valido" % m["file"])
    c = man.get("coerenza", {})
    mode = c.get("modalita")
    first = (man.get("prima_installazione") or {}).get("ammessa")
    if c.get("confine_di_ciclo_verificato") and mode == "ciclo_verificato":
        print("  confine di ciclo: VERIFICATO")
    elif mode == "bot_fermo":
        print("  ECCEZIONE AMMESSA dichiarata nel manifesto: copia con i bot FERMI (nessun confine di ciclo)")
    elif first:
        print("  ECCEZIONE AMMESSA dichiarata nel manifesto: PRIMA INSTALLAZIONE")
    else:
        problems.add("la copia del cervello non ha il confine di ciclo verificato ne' un'eccezione ammessa "
                     "(modalita' %s)" % mode)
    print("  cervello: %d file | coerenza %s | confine di ciclo %s | modalita' %s"
          % (len(man.get("file", [])), "dichiarata" if c.get("consistente") else "NON dichiarata",
             "VERIFICATO" if c.get("confine_di_ciclo_verificato") else "non verificato", c.get("modalita")))
    if not c.get("consistente"):
        problems.add("il manifesto del cervello non dichiara la coerenza")
    for p, st in (man.get("stato_copiato") or {}).items():
        print("  stato %s: %s" % (p, st))
    for p in ("hawk", "bull"):
        if os.path.isdir(os.path.join(snap, p)):
            check_semantics(os.path.join(snap, p), p, problems)


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def check_semantics(base, name, problems):
    """Coerenza tra stato, posizioni, storico e contabilita' di un portafoglio (vedi punto 8 in testa)."""
    try:
        with open(os.path.join(base, "state_v2.json")) as f:
            st = json.load(f)
        with open(os.path.join(base, "trade_history.jsonl")) as f:
            hist = [json.loads(line) for line in f if line.strip()]
        with open(os.path.join(base, "learning_log.jsonl")) as f:
            learn = [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError) as e:
        problems.add("%s: stato o registri illeggibili per il controllo di coerenza (%s)" % (name, e))
        return
    m = st.get("main") if isinstance(st, dict) else None
    run = st.get("run_no") if isinstance(st, dict) else None
    if not isinstance(m, dict) or not isinstance(run, int) or not _num(m.get("cash")) \
            or not isinstance(m.get("positions"), dict) or not isinstance(m.get("closed"), list) \
            or not isinstance(m.get("next_id"), int):
        problems.add("%s: stato senza i campi essenziali (run_no, main.cash, main.positions, main.closed, "
                     "main.next_id)" % name)
        return
    before = len(problems)
    closed, positions, next_id = m["closed"], m["positions"], m["next_id"]

    def key(r):
        return (r.get("id"), r.get("open_ms"), r.get("close_ms"), round(float(r.get("net") or 0), 6))

    from collections import Counter
    in_run = [r for r in hist if r.get("run_no") == run]
    a, b = Counter(key(r) for r in in_run), Counter(key(c) for c in closed)
    if a != b:
        problems.add("%s: i trade chiusi nello stato (%d) non coincidono con lo storico della run %d (%d): "
                     "%d solo nello stato, %d solo nello storico"
                     % (name, len(closed), run, len(in_run), sum((b - a).values()), sum((a - b).values())))
    ids = [c.get("id") for c in closed] + [pos.get("id", k) if isinstance(pos, dict) else k
                                           for k, pos in positions.items()]
    bad = [i for i in ids if isinstance(i, int) and i >= next_id]
    if bad:
        problems.add("%s: id %s oltre next_id=%d" % (name, bad[:5], next_id))
    back = [r.get("id") for r in hist if _num(r.get("open_ms")) and _num(r.get("close_ms"))
            and r["close_ms"] < r["open_ms"]]
    if back:
        problems.add("%s: %d trade chiusi prima di essere aperti (id %s)" % (name, len(back), back[:5]))
    fut = sum(1 for r in hist if isinstance(r.get("run_no"), int) and r["run_no"] > run)
    fut += sum(1 for r in learn if isinstance(r.get("run_no"), int) and r["run_no"] > run)
    if fut:
        problems.add("%s: %d righe di storico/apprendimento di una run successiva a quella dello stato (%d)"
                     % (name, fut, run))
    other = sum(1 for r in learn if r.get("portfolio") not in (None, name))
    if other:
        problems.add("%s: %d righe del registro di apprendimento di un altro portafoglio" % (name, other))
    start = (m.get("limits") or {}).get("start_equity")
    if not _num(start):
        starts = {r.get("start_equity") for r in in_run if _num(r.get("start_equity"))}
        start = starts.pop() if len(starts) == 1 else None
    total = sum(float(c.get("net") or 0) for c in closed)
    if start is None:
        problems.add("%s: capitale iniziale della run sconosciuto: contabilita' non verificabile" % name)
        acct = "non verificabile"
    elif not positions:
        diff = m["cash"] - (start + total)
        if abs(diff) > 0.01:
            problems.add("%s: contabilita' incoerente: cassa %.4f, capitale iniziale + risultati %.4f (diff %.4f)"
                         % (name, m["cash"], start + total, diff))
        acct = "cassa = capitale iniziale + risultati (diff %.6f)" % diff
    else:
        if m["cash"] > start + total + 0.01:
            problems.add("%s: con posizioni aperte la cassa (%.4f) supera capitale iniziale + risultati (%.4f)"
                         % (name, m["cash"], start + total))
        acct = "posizioni aperte %d: cassa <= capitale iniziale + risultati" % len(positions)
    print("  coerenza %s: run %d | %d trade chiusi = storico della run | %d posizioni aperte | %s | %s"
          % (name, run, len(closed), len(positions), acct, "OK" if len(problems) == before else "PROBLEMI"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", required=True)
    ap.add_argument("--identity", required=True, help="file con la chiave PRIVATA di recupero (AGE-SECRET-KEY-...)")
    ap.add_argument("--out", required=True, help="cartella vuota o inesistente")
    ap.add_argument("--manifest", default="", help="manifesto in chiaro (default: accanto all'archivio)")
    a = ap.parse_args(argv)

    if os.path.exists(a.out) and os.listdir(a.out):
        print("ERRORE: la cartella di ripristino %s non e' vuota" % a.out)
        return 1
    if not shutil.which("age"):
        print("ERRORE: serve il programma age (apt install age)")
        return 1
    if os.stat(a.identity).st_mode & 0o077:
        print("ATTENZIONE: la chiave privata ha permessi troppo larghi (consigliato chmod 600)")
    problems = Problems()
    print("RIPRISTINO DI PROVA di %s" % os.path.basename(a.archive))

    mpath = a.manifest or (a.archive[: -len(".tar.gz.age")] + ".manifest.json" if a.archive.endswith(".tar.gz.age") else "")
    if mpath and os.path.isfile(mpath):
        with open(mpath) as f:
            pub = json.load(f)
        digest = sha256_file(a.archive)
        if digest != pub.get("sha256") or os.path.getsize(a.archive) != pub.get("dimensione"):
            problems.add("l'archivio cifrato NON coincide col manifesto (SHA-256 o dimensione diversi): alterato o incompleto")
        else:
            print("  archivio cifrato: SHA-256 e dimensione uguali al manifesto")
    else:
        print("  (nessun manifesto in chiaro: salto il controllo dell'hash del cifrato; age controlla comunque l'integrita')")

    os.makedirs(a.out, mode=0o700, exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="restore-")
    try:
        plain = os.path.join(tmpdir, "archivio.tar.gz")
        p = subprocess.run(["age", "-d", "-i", a.identity, "-o", plain, a.archive], capture_output=True, text=True)
        if p.returncode != 0:
            problems.add("decifratura non riuscita (chiave sbagliata o archivio alterato): %s" % p.stderr.strip()[-200:])
            print("RISULTATO: FALLITO")
            return 1
        print("  decifratura riuscita (cifratura autenticata: archivio non alterato)")
        try:
            extracted = safe_extract(plain, a.out, problems)
        except (tarfile.TarError, OSError, EOFError, gzip.BadGzipFile) as e:
            problems.add("archivio non leggibile: %s" % e)
            print("RISULTATO: FALLITO")
            return 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)       # il testo in chiaro temporaneo non resta in giro

    # manifesto interno
    try:
        with open(os.path.join(a.out, INTERNAL_MANIFEST)) as f:
            inner = json.load(f)
    except (OSError, ValueError):
        problems.add("manifesto interno mancante o illeggibile")
        inner = {"file": []}
    declared = {x["file"]: x for x in inner.get("file", [])}
    for name, x in declared.items():
        path = os.path.join(a.out, *name.split("/"))
        if not os.path.isfile(path):
            problems.add("file dichiarato ma assente: %s" % name)
        elif os.path.getsize(path) != x["size"] or sha256_file(path) != x["sha256"]:
            problems.add("file diverso dal manifesto interno: %s" % name)
    for name in extracted:
        if name != INTERNAL_MANIFEST and name not in declared:
            problems.add("file non dichiarato nel manifesto interno: %s" % name)
    print("  manifesto interno: %d file controllati (dimensione e SHA-256)" % len(declared))
    print("  creato %s | origine %s | versioni %s" % (inner.get("creato"), inner.get("origine"), inner.get("versioni")))

    check_databases(a.out, problems)
    check_brain(a.out, problems)

    if problems:
        print("RISULTATO: FALLITO (%d problemi). La cartella %s resta per l'esame." % (len(problems), a.out))
        return 1
    print("RISULTATO: OK  backup decifrato, completo e integro in %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
