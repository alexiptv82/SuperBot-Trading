#!/usr/bin/env python3
"""Backup verificato del "cervello" dei bot (Hawk e Bull), prima di un deploy.

Regola dell'utente: i file del cervello (trade_history.jsonl, lessons.md,
errors.md, learning_log.jsonl) non si cancellano, non si azzerano, non si
modificano. Questo script li SOLO LEGGE e ne fa una copia a parte.

Coerenza (il bot scrive mentre noi copiamo):
  i file "centrali" (i quattro del cervello + state_v2.json) vengono copiati
  in una FINESTRA STABILE a FINE CICLO. Il battito del bot (heartbeat.json)
  dichiara gia' il confine di ciclo: `cycle_running`, `last_end_ms`,
  `next_cycle_ms`, `cycles`. Si copia solo quando, per ogni portafoglio, il
  bot e' tra due cicli (nessun ciclo in corso, ultimo ciclo finito da almeno N
  secondi, prossimo ciclo ancora lontano) e nessun file centrale e' stato
  scritto negli ultimi N secondi. Si registra l'impronta dei file centrali
  (inode, dimensione, istante di modifica) e il contatore dei cicli, si copia,
  si rileggono: se qualcosa e' cambiato la copia viene scartata e si riprova.
  Se non si arriva a una finestra stabile il backup FALLISCE (uscita 1): una
  copia di cui non si puo' dimostrare la coerenza tra stato e registri non e'
  una barriera affidabile. Se il battito e' vecchio di oltre 2 minuti il bot
  non sta scrivendo (fermo): vale solo il controllo dell'impronta. Se nel
  battito manca `cycle_running` (versione vecchia del bot) il confine di ciclo
  non e' verificabile: lo dice il manifesto.

Per ogni file dei portafogli:
  - i quattro file del cervello crescono soltanto, quindi la copia deve
    essere identica ai primi byte dell'originale e non piu' corta di prima;
  - i database SQLite (se ce ne sono) si copiano con l'API di backup;
  - gli altri file si copiano e si confrontano per hash, con qualche
    tentativo se il bot li sta riscrivendo (heartbeat: solo avviso).
Poi una prova di ripristino rilegge tutta la copia dal disco e la confronta
con il manifesto (hash di ogni file, righe dei file del cervello, JSON validi).

Cartelle o portafogli mancanti sono un ERRORE (uscita 1), salvo --allow-missing.
Un nome di copia esistente non viene mai sovrascritto; due backup insieme non
si pestano (blocco condiviso con backup_app_db.py). Esce con 1 se qualcosa non torna.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import time

CRITICAL = ("trade_history.jsonl", "lessons.md", "errors.md", "learning_log.jsonl")
CORE = CRITICAL + ("state_v2.json",)
SQLITE_EXT = (".db", ".sqlite", ".sqlite3")
SKIP_SUFFIX = ("-wal", "-shm", "-journal", ".part")
BIG = 50 * 1024 * 1024  # file non critici piu' grandi di cosi' non si copiano
DEFAULT_PORTFOLIOS = "hawk,bull"


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


def json_ok(path):
    try:
        with open(path, "rb") as f:
            json.loads(f.read())
        return True
    except (ValueError, OSError):
        return False


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


# ---- coerenza ---------------------------------------------------------------

def core_fp(base):
    """Impronta dei file centrali: inode, dimensione, istante di modifica (ns)."""
    out = []
    for n in CORE:
        try:
            st = os.stat(os.path.join(base, n))
        except FileNotFoundError:
            out.append((n, None))
            continue
        out.append((n, st.st_ino, st.st_size, st.st_mtime_ns))
    return tuple(out)


def read_hb(base):
    """(battito, istante di modifica del file) oppure (None, None)."""
    p = os.path.join(base, "heartbeat.json")
    try:
        with open(p) as f:
            hb = json.load(f)
        return (hb if isinstance(hb, dict) else None), os.stat(p).st_mtime
    except (OSError, ValueError):
        return None, None


def boundary_state(base, quiet, margin=30.0):
    """(pronto, verificato, descrizione): il bot e' tra due cicli?
    pronto=False -> aspettare. verificato=False -> il confine di ciclo non si puo' dimostrare."""
    hb, mt = read_hb(base)
    if hb is None:
        return False, False, "battito illeggibile"
    now = time.time()
    if now - mt > 120:
        return True, False, "battito vecchio di %d s: il bot non sta scrivendo" % int(now - mt)
    if "cycle_running" not in hb:
        return True, False, "nel battito manca cycle_running: confine di ciclo non verificabile"
    if hb.get("cycle_running") is not False:
        return False, True, "ciclo in corso"
    end_ms, next_ms = hb.get("last_end_ms"), hb.get("next_cycle_ms")
    if isinstance(end_ms, (int, float)) and now - end_ms / 1000.0 < quiet:
        return False, True, "ultimo ciclo finito da meno di %g s" % quiet
    if isinstance(next_ms, (int, float)) and next_ms / 1000.0 - now < margin:
        return False, True, "il prossimo ciclo parte tra meno di %g s" % margin
    nxt = ("%d s" % int(next_ms / 1000.0 - now)) if isinstance(next_ms, (int, float)) else "?"
    return True, True, "tra due cicli (cicli fatti %s, prossimo tra %s)" % (hb.get("cycles"), nxt)


def hb_marker(base):
    hb, _ = read_hb(base)
    if not hb:
        return None
    return (hb.get("cycles"), hb.get("last_start_ms"), hb.get("last_end_ms"), hb.get("cycle_running"))


def wait_ready(bases, quiet, timeout):
    """Aspetta la finestra di fine ciclo: bot tra due cicli e nessun file centrale scritto negli
    ultimi `quiet` secondi. Restituisce (secondi di quiete, descrizioni, tutto_verificato) o None."""
    end = time.time() + timeout
    while True:
        newest = 0.0
        for b in bases:
            for n in CORE:
                try:
                    newest = max(newest, os.stat(os.path.join(b, n)).st_mtime)
                except FileNotFoundError:
                    pass
        age = time.time() - newest
        states = [boundary_state(b, quiet) for b in bases]
        if age >= quiet and all(s[0] for s in states):
            return age, [s[2] for s in states], all(s[1] for s in states)
        if time.time() >= end:
            return None
        time.sleep(min(max(quiet - age, 0) + 0.5, 5))


def take_lock(directory, timeout=300):
    """Blocco esclusivo condiviso con backup_app_db.py (stesso file)."""
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


def free_unique(path):
    """True se nessuna copia, .part o -INCOMPLETO con questo nome esiste."""
    return not any(os.path.exists(path + s) for s in ("", ".part", "-INCOMPLETO"))


def unique_incomplete(path):
    dest = path + "-INCOMPLETO"
    n = 0
    while os.path.exists(dest):
        n += 1
        dest = "%s-INCOMPLETO.%d" % (path, n)
    return dest


# ---- copia ------------------------------------------------------------------

def copy_tree(present, root, out):
    problems, warnings, manifest, skipped = [], [], [], []
    for p in present:
        base = os.path.join(root, p)
        for dp, dn, fn in os.walk(base):
            dn.sort()
            for f in sorted(fn):
                s = os.path.join(dp, f)
                if os.path.islink(s) or f.endswith(SKIP_SUFFIX):
                    continue
                rel = os.path.relpath(s, root)
                d = os.path.join(out, rel)
                os.makedirs(os.path.dirname(d), exist_ok=True)
                critical = f in CRITICAL and dp == base
                try:
                    if f.endswith(SQLITE_EXT):
                        if not copy_sqlite(s, d):
                            problems.append("database %s: integrity_check non ok" % rel)
                    elif critical:
                        if not copy_critical(s, d):
                            problems.append("file del cervello %s: copia incompleta o diversa" % rel)
                    else:
                        if os.path.getsize(s) > BIG:
                            skipped.append(rel)
                            continue
                        if not copy_other(s, d):
                            core = f in CORE and dp == base
                            (problems if core else warnings).append(
                                "%s: cambia di continuo, copia non verificabile" % rel)
                except OSError as e:
                    (problems if critical else warnings).append("%s: %s" % (rel, e))
                if os.path.exists(d):
                    manifest.append({
                        "file": rel,
                        "size": os.path.getsize(d),
                        "sha256": sha256(d),
                        "critical": critical,
                        "righe": count_lines(d) if critical else None,
                    })
    return manifest, problems, warnings, skipped


def state_summary(path):
    try:
        with open(path) as f:
            st = json.load(f)
        main_acc = st.get("main") or {}
        return {"run_no": st.get("run_no"), "cycle": st.get("cycle"),
                "posizioni_aperte": len(main_acc.get("positions") or {})}
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="cartella che contiene hawk/ e bull/")
    ap.add_argument("--dir", required=True, help="cartella dei backup")
    ap.add_argument("--keep", type=int, default=10)
    ap.add_argument("--tag", default="")
    ap.add_argument("--portfolios", default=DEFAULT_PORTFOLIOS,
                    help="portafogli obbligatori, separati da virgola (default hawk,bull)")
    ap.add_argument("--allow-missing", action="store_true",
                    help="cartelle mancanti non sono un errore (di norma lo sono)")
    ap.add_argument("--attempts", type=int, default=5, help="tentativi di finestra stabile")
    ap.add_argument("--wait", type=float, default=10.0, help="secondi tra un tentativo e l'altro")
    ap.add_argument("--quiet-secs", type=float, default=10.0,
                    help="secondi senza scritture sui file centrali prima di copiare")
    ap.add_argument("--quiet-timeout", type=float, default=90.0,
                    help="massimo d'attesa per ottenere la quiete, per tentativo")
    a = ap.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_]*", a.tag):
        print("ERRORE BACKUP CERVELLO: tag non valido (solo lettere, numeri, _)")
        return 1
    wanted = [p for p in a.portfolios.split(",") if p]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", "".join(wanted) or "x"):
        print("ERRORE BACKUP CERVELLO: nomi dei portafogli non validi")
        return 1
    present = [p for p in wanted if os.path.isdir(os.path.join(a.root, p))]
    missing = [p for p in wanted if p not in present]
    if missing and not a.allow_missing:
        print("ERRORE BACKUP CERVELLO: mancano le cartelle dati di %s in %s. "
              "Senza il cervello da salvare il deploy non deve proseguire." % (", ".join(missing), a.root))
        print("RISULTATO: FALLITO. Non si deve sostituire nessun container.")
        return 1
    if not present:
        print("BACKUP CERVELLO: nessuna cartella dati in %s (accettato con --allow-missing)." % a.root)
        return 0

    os.makedirs(a.dir, mode=0o700, exist_ok=True)
    os.chmod(a.dir, 0o700)
    lock_fd = take_lock(a.dir)
    try:
        return run(a, present, missing)
    finally:
        os.close(lock_fd)


def run(a, present, missing):
    # copie incomplete lasciate da un'esecuzione interrotta: sono nostre, si tolgono
    for n in os.listdir(a.dir):
        if re.fullmatch(r"bots-\d{8}-\d{6}(-[A-Za-z0-9_]+)?\.part", n):
            shutil.rmtree(os.path.join(a.dir, n), ignore_errors=True)

    for _ in range(6):
        name = "bots-" + time.strftime("%Y%m%d-%H%M%S") + (("-" + a.tag) if a.tag else "")
        final = os.path.join(a.dir, name)
        if free_unique(final):
            break
        time.sleep(1.1)
    else:
        print("ERRORE BACKUP CERVELLO: nessun nome libero per la copia")
        print("RISULTATO: FALLITO. Non si deve sostituire nessun container.")
        return 1
    part = final + ".part"
    bases = [os.path.join(a.root, p) for p in present]

    consistent, used, quiet_age = False, 0, None
    verified, boundary_info = False, []
    manifest, problems, warnings, skipped = [], [], [], []
    for attempt in range(1, a.attempts + 1):
        used = attempt
        ready = wait_ready(bases, a.quiet_secs, a.quiet_timeout)
        if ready is None:
            print("  tentativo %d: nessuna finestra di fine ciclo entro %g s (ciclo in corso o file "
                  "scritti di continuo), riprovo" % (attempt, a.quiet_timeout))
            time.sleep(a.wait)
            continue
        quiet_age, boundary_info, verified = ready
        before = ([core_fp(b) for b in bases], [hb_marker(b) for b in bases])
        os.makedirs(part, mode=0o700)
        manifest, problems, warnings, skipped = copy_tree(present, a.root, part)
        after = ([core_fp(b) for b in bases], [hb_marker(b) for b in bases])
        if before == after:
            consistent = True
            break
        shutil.rmtree(part, ignore_errors=True)
        print("  tentativo %d: i file centrali o il contatore dei cicli sono cambiati durante la copia; "
              "copia scartata, riprovo" % attempt)
        time.sleep(a.wait)

    if not consistent:
        print("ERRORE BACKUP CERVELLO: dopo %d tentativi non c'e' stata una finestra di fine ciclo in cui i file "
              "centrali (%s) non venissero scritti: la coerenza tra stato e registri non e' dimostrabile."
              % (used, ", ".join(CORE)))
        print("RISULTATO: FALLITO. Non si deve sostituire nessun container.")
        return 1

    # file centrali mancanti nell'origine ma richiesti: i quattro del cervello se esistono devono esserci nella copia
    for p in present:
        for c in CRITICAL:
            if os.path.isfile(os.path.join(a.root, p, c)) and \
                    not os.path.isfile(os.path.join(part, p, c)):
                problems.append("file del cervello mancante nella copia: %s/%s" % (p, c))

    coerenza = {
        "consistente": True,
        "metodo": ("finestra di fine ciclo (battito del bot) + nessuna scrittura sui file centrali negli "
                   "ultimi %g s + nessuna modifica (inode, dimensione, istante) ne' variazione del "
                   "contatore dei cicli durante la copia" % a.quiet_secs),
        "tentativi": used,
        "quiete_osservata_s": round(quiet_age, 1) if quiet_age is not None else None,
        "file_centrali": list(CORE),
        "confine_di_ciclo_verificato": bool(verified),
        "stato_del_confine": dict(zip(present, boundary_info)),
    }
    stato = {p: state_summary(os.path.join(part, p, "state_v2.json")) for p in present}
    with open(os.path.join(part, "MANIFEST.json"), "w") as f:
        json.dump({"creato": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "coerenza": coerenza, "stato_copiato": stato,
                   "file": manifest, "non_copiati_troppo_grandi": skipped}, f, indent=1)
    os.chmod(os.path.join(part, "MANIFEST.json"), 0o600)

    # prova di ripristino: rilegge dal disco la copia e la confronta col manifesto
    for m in manifest:
        path = os.path.join(part, m["file"])
        if not os.path.isfile(path) or sha256(path) != m["sha256"]:
            problems.append("prova di ripristino: %s non coincide col manifesto" % m["file"])
        elif m["critical"] and m["file"].endswith(".jsonl") and not jsonl_ok(path):
            problems.append("prova di ripristino: %s contiene righe JSON non valide" % m["file"])
        elif os.path.basename(m["file"]) == "state_v2.json" and not json_ok(path):
            problems.append("prova di ripristino: %s non e' un JSON valido" % m["file"])

    print("BACKUP CERVELLO: %s" % name)
    for p in present:
        parts = []
        for m in manifest:
            if m["critical"] and m["file"].startswith(p + os.sep):
                parts.append("%s %d righe" % (os.path.basename(m["file"]), m["righe"]))
        n = sum(1 for m in manifest if m["file"].startswith(p + os.sep))
        print("  %s: %d file | %s" % (p, n, ", ".join(parts) if parts else "nessun file del cervello"))
    for mm in missing:
        print("  ATTENZIONE: cartella assente (accettata con --allow-missing): %s" % mm)
    for s in skipped:
        print("  non copiato (oltre %d MB, non e' del cervello): %s" % (BIG // (1 << 20), s))
    for w in warnings:
        print("  ATTENZIONE: " + w)
    for p, info in zip(present, boundary_info):
        print("  %s: %s" % (p, info))
    print("  coerenza: finestra stabile al tentativo %d (quiete di %.1f s, nessuna modifica ai file centrali "
          "ne' ai cicli durante la copia); confine di ciclo %s"
          % (used, quiet_age or 0.0, "VERIFICATO" if verified else "NON verificabile (vedi sopra)"))

    if problems:
        for pr in problems:
            print("  ERRORE: " + pr)
        os.replace(part, unique_incomplete(final))
        print("RISULTATO: FALLITO. Non si deve sostituire nessun container.")
        return 1

    os.rename(part, final)

    pat = re.compile(r"^bots-\d{8}-\d{6}(-[A-Za-z0-9_]+)?$")
    olds = sorted(n for n in os.listdir(a.dir) if pat.match(n)
                  and os.path.isdir(os.path.join(a.dir, n)))
    removed = 0
    for n in olds[:-a.keep] if a.keep > 0 else []:
        shutil.rmtree(os.path.join(a.dir, n))
        removed += 1
    print("  prova di ripristino: ogni file riletto, hash, righe e JSON uguali al manifesto")
    print("  copie dei bot conservate: %d (eliminate le piu' vecchie: %d)"
          % (min(len(olds), a.keep), removed))
    print("RISULTATO: OK")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except (sqlite3.Error, OSError, TimeoutError) as e:
        print("ERRORE BACKUP CERVELLO: %s" % e)
        print("RISULTATO: FALLITO. Non si deve sostituire nessun container.")
        code = 1
    sys.exit(code)
