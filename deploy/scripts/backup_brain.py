#!/usr/bin/env python3
"""Backup verificato del "cervello" dei bot (Hawk e Bull), prima di un deploy.

Regola dell'utente: i file del cervello (trade_history.jsonl, lessons.md,
errors.md, learning_log.jsonl) non si cancellano, non si azzerano, non si
modificano. Questo script li SOLO LEGGE e ne fa una copia a parte.

File irrinunciabili (REQUIRED): per ogni portafoglio devono esistere
state_v2.json, trade_history.jsonl, learning_log.jsonl e lessons.md (file
normali, non collegamenti). Una cartella vuota o incompleta NON e' un backup:
il deploy si ferma. L'unica eccezione e' --first-install, esplicita, che il
manifesto e l'output dichiarano. errors.md si salva se esiste ma non e' obbligatorio.

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
  Se non si arriva a una finestra stabile il backup FALLISCE (uscita 1).
  Il percorso normale (quello dei deploy) RICHIEDE il confine di ciclo
  verificato: battito vecchio o senza `cycle_running` = FALLITO subito, non
  "ok ma non verificato". Per un bot davvero fermo esiste una modalita'
  separata ed esplicita, --bot-stopped. Il fermo si DIMOSTRA sul container
  (docker inspect: nessun container del portafoglio in esecuzione) e il
  battito deve essere vecchio o assente; un battito vecchio da solo non basta
  (un processo bloccato ha il battito vecchio ma puo' ancora scrivere).
  Container in esecuzione, docker non utilizzabile o container fermo con
  battito ancora fresco = si rifiuta. Il manifesto dice "bot_fermo" e riporta
  lo stato di ogni container.

Per ogni file dei portafogli:
  - i quattro del cervello crescono soltanto, quindi la copia deve essere
    identica ai primi byte dell'originale e non piu' corta di prima;
  - i file .jsonl devono essere COMPLETI: ogni riga JSON valida e l'ultima
    riga terminata da a capo. Una riga finale troncata e' corruzione;
  - i database SQLite (se ce ne sono) si copiano con l'API di backup;
  - gli altri file si copiano e si confrontano per hash, con qualche
    tentativo se il bot li sta riscrivendo (heartbeat: solo avviso).
Poi una prova di ripristino rilegge tutta la copia dal disco e la confronta
con il manifesto (hash di ogni file, righe dei file del cervello, JSON validi).

Cartelle o portafogli mancanti sono un ERRORE (uscita 1), salvo --first-install.
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
import subprocess
import sys
import time

CRITICAL = ("trade_history.jsonl", "lessons.md", "errors.md", "learning_log.jsonl")
CORE = CRITICAL + ("state_v2.json",)
# Irrinunciabili in ogni portafoglio: senza anche uno solo non c'e' un backup utile.
REQUIRED = ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md")
HB_STALE = 120  # secondi: battito piu' vecchio di cosi' = il bot non sta scrivendo
OK, WAIT, NO = "ok", "attesa", "non_verificabile"
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


def jsonl_problem(path):
    """None se il file JSONL e' completo; altrimenti la descrizione del problema.
    Completo = ogni riga e' JSON valido e (se il file non e' vuoto) l'ultima riga finisce con a capo:
    una riga finale senza a capo e' una scrittura interrotta, cioe' corruzione."""
    with open(path, "rb") as f:
        for n, line in enumerate(f, 1):
            if not line.endswith(b"\n"):        # solo l'ultima riga puo' non finire con a capo
                return "ultima riga incompleta (riga %d senza a capo finale)" % n
            if not line.strip():
                continue
            try:
                json.loads(line)
            except ValueError:
                return "riga %d non e' JSON valido" % n
    return None


def jsonl_ok(path):
    return jsonl_problem(path) is None


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
    """(esito, descrizione): il bot e' tra due cicli?
    OK = confine di ciclo VERIFICATO e finestra buona; WAIT = riprovare tra poco (ciclo in corso, appena
    finito, prossimo imminente, battito illeggibile); NO = il confine di ciclo non e' dimostrabile e aspettare
    non serve (battito vecchio, o bot vecchio senza cycle_running)."""
    hb, mt = read_hb(base)
    if hb is None:
        return WAIT, "battito illeggibile"
    now = time.time()
    if now - mt > HB_STALE:
        return NO, ("battito vecchio di %d s: il bot non sta scrivendo, quindi il confine di ciclo non si puo' "
                    "verificare (se il bot e' davvero fermo: modalita' esplicita --bot-stopped)" % int(now - mt))
    if "cycle_running" not in hb:
        return NO, "nel battito manca cycle_running (bot vecchio): confine di ciclo non verificabile"
    if hb.get("cycle_running") is not False:
        return WAIT, "ciclo in corso"
    end_ms, next_ms = hb.get("last_end_ms"), hb.get("next_cycle_ms")
    if isinstance(end_ms, (int, float)) and now - end_ms / 1000.0 < quiet:
        return WAIT, "ultimo ciclo finito da meno di %g s" % quiet
    # Bot FERMO DAVVERO dal battito: in pausa, senza posizioni, nessun ciclo programmato (next_cycle_ms == 0).
    # Non fa cicli da solo (riparte solo se l'utente preme Avvia) e il battito e' fresco. Qui lo 0 non vuol dire
    # "ciclo imminente": senza questa eccezione il backup aspettava per sempre dopo un reset. Restano obbligatori
    # la quiete dei file centrali (wait_ready) e la ricontrollo prima/dopo la copia.
    idle = (hb.get("mode") == "paused" and hb.get("pause_requested") is True and
            type(hb.get("open_positions")) is int and hb.get("open_positions") == 0 and
            type(next_ms) is int and next_ms == 0)
    if not idle and isinstance(next_ms, (int, float)) and next_ms / 1000.0 - now < margin:
        return WAIT, "il prossimo ciclo parte tra meno di %g s" % margin
    if idle:
        return OK, "in pausa, senza posizioni e senza cicli programmati (cicli fatti %s)" % hb.get("cycles")
    nxt = ("%d s" % int(next_ms / 1000.0 - now)) if isinstance(next_ms, (int, float)) else "?"
    return OK, "tra due cicli (cicli fatti %s, prossimo tra %s)" % (hb.get("cycles"), nxt)


def container_state(docker_bin, name):
    """('running'|'stopped'|'absent'|'unknown', descrizione) letto da docker, mai dedotto dai file."""
    try:
        p = subprocess.run([docker_bin, "inspect", "-f", "{{.State.Running}}", name],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return "unknown", "docker non utilizzabile (%s)" % type(e).__name__
    out = (p.stdout + p.stderr).strip()
    if p.returncode == 0:
        if p.stdout.strip() == "true":
            return "running", "container %s IN ESECUZIONE" % name
        if p.stdout.strip() == "false":
            return "stopped", "container %s fermo (docker inspect)" % name
        return "unknown", "risposta di docker illeggibile per %s" % name
    if "no such" in out.lower():
        return "absent", "container %s assente (nessun processo docker per questo bot)" % name
    return "unknown", "stato del container %s non verificabile: %s" % (name, out[:100])


def default_container(base, prefix="superbot-desk-"):
    return prefix + os.path.basename(base.rstrip(os.sep))


def stopped_state(base, container="", docker_bin="docker"):
    """Modalita' --bot-stopped: ammessa solo se il bot e' DAVVERO fermo, dimostrato sul container (docker) e
    con il battito vecchio o assente. Un battito vecchio da solo non dimostra niente: un processo bloccato
    ha il battito vecchio ma puo' ancora scrivere."""
    if not container:
        return NO, "nome del container sconosciuto: il fermo non e' dimostrabile"
    cs, desc = container_state(docker_bin, container)
    if cs == "running":
        return NO, ("%s: il bot risulta ATTIVO, la modalita' --bot-stopped non e' ammessa; usare il backup "
                    "normale" % desc)
    if cs == "unknown":
        return NO, desc + ": la modalita' --bot-stopped richiede la prova del fermo"
    p = os.path.join(base, "heartbeat.json")
    try:
        age = time.time() - os.stat(p).st_mtime
    except FileNotFoundError:
        return OK, "%s; nessun battito (mai avviato o fermo da tempo)" % desc
    if age <= HB_STALE:
        return WAIT, ("%s ma il battito e' ancora fresco (%d s): aspetto che invecchi; se non succede "
                      "qualcun altro sta scrivendo" % (desc, int(age)))
    return OK, "%s; battito vecchio di %d s" % (desc, int(age))


def hb_marker(base):
    hb, _ = read_hb(base)
    if not hb:
        return None
    return (hb.get("cycles"), hb.get("last_start_ms"), hb.get("last_end_ms"), hb.get("cycle_running"))


def wait_ready(bases, quiet, timeout, stopped=False, docker_bin="docker", container_for=default_container):
    """Aspetta la finestra buona: bot tra due cicli (o, con stopped, davvero fermo) e nessun file centrale
    scritto negli ultimi `quiet` secondi. Restituisce (esito, secondi di quiete, descrizioni) con esito
    'ok', 'attesa_scaduta' oppure 'non_verificabile' (inutile aspettare: si ferma subito)."""
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
        states = [(stopped_state(b, container_for(b), docker_bin) if stopped else boundary_state(b, quiet))
                  for b in bases]
        descs = [s[1] for s in states]
        if any(s[0] == NO for s in states):
            return "non_verificabile", None, descs
        if age >= quiet and all(s[0] == OK for s in states):
            return "ok", age, descs
        if time.time() >= end:
            return "attesa_scaduta", None, descs
        time.sleep(min(max(quiet - age, 0) + 0.5, 5))


def required_missing(root, portfolios):
    """File irrinunciabili assenti o inutilizzabili (una cartella vuota li ha tutti assenti).
    Un collegamento simbolico non conta: la copia non lo segue."""
    out = []
    for p in portfolios:
        for n in REQUIRED:
            path = os.path.join(root, p, n)
            if os.path.islink(path) or not os.path.isfile(path):
                out.append("%s/%s" % (p, n))
            elif n == "state_v2.json" and os.path.getsize(path) == 0:
                out.append("%s/%s (vuoto)" % (p, n))
    return out


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
    ap.add_argument("--first-install", action="store_true",
                    help="ECCEZIONE esplicita: cartelle o file irrinunciabili ancora assenti perche' i bot non "
                         "hanno mai girato (di norma sono un errore e il deploy si ferma)")
    ap.add_argument("--bot-stopped", action="store_true",
                    help="modalita' separata per un bot DAVVERO fermo: salta il confine di ciclo ma richiede la "
                         "prova del fermo sul container (docker inspect) e rifiuta se un container e' in "
                         "esecuzione")
    ap.add_argument("--docker-bin", default="docker", help="programma docker (cambia solo nelle prove)")
    ap.add_argument("--container-prefix", default="superbot-desk-",
                    help="prefisso del nome dei container: <prefisso><portafoglio>")
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
    if missing and not a.first_install:
        print("ERRORE BACKUP CERVELLO: mancano le cartelle dati di %s in %s. "
              "Senza il cervello da salvare il deploy non deve proseguire." % (", ".join(missing), a.root))
        print("RISULTATO: FALLITO. Non si deve sostituire nessun container.")
        return 1
    if not present:
        print("BACKUP CERVELLO: nessuna cartella dati in %s (accettato con --first-install)." % a.root)
        return 0
    absent = required_missing(a.root, present)
    if absent and not a.first_install:
        print("ERRORE BACKUP CERVELLO: file irrinunciabili assenti o inutilizzabili: %s. "
              "Una cartella vuota o incompleta non e' un backup del cervello: il deploy non deve proseguire "
              "(solo alla prima installazione, con --first-install esplicito)." % ", ".join(absent))
        print("RISULTATO: FALLITO. Non si deve sostituire nessun container.")
        return 1

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
    absent_ok = []
    for attempt in range(1, a.attempts + 1):
        used = attempt
        outcome, quiet_age, boundary_info = wait_ready(
            bases, a.quiet_secs, a.quiet_timeout, a.bot_stopped, a.docker_bin,
            lambda b: default_container(b, a.container_prefix))
        if outcome == "non_verificabile":
            for p, info in zip(present, boundary_info):
                print("  %s: %s" % (p, info))
            print("ERRORE BACKUP CERVELLO: %s."
                  % ("la modalita' --bot-stopped non e' ammessa: almeno un bot risulta attivo" if a.bot_stopped
                     else "il confine di ciclo non e' verificabile e il deploy lo richiede"))
            print("RISULTATO: FALLITO. Non si deve sostituire nessun container.")
            return 1
        if outcome != "ok":
            print("  tentativo %d: nessuna finestra di fine ciclo entro %g s (ciclo in corso o file "
                  "scritti di continuo), riprovo" % (attempt, a.quiet_timeout))
            for pp, info in zip(present, boundary_info):
                print("    %s: %s" % (pp, info))
            time.sleep(a.wait)
            continue
        verified = not a.bot_stopped
        # i file irrinunciabili devono esserci anche adesso (non spariti dopo il primo controllo)
        absent_ok = required_missing(a.root, present)
        if absent_ok and not a.first_install:
            print("ERRORE BACKUP CERVELLO: file irrinunciabili assenti o inutilizzabili: %s." % ", ".join(absent_ok))
            print("RISULTATO: FALLITO. Non si deve sostituire nessun container.")
            return 1
        before = ([core_fp(b) for b in bases], [hb_marker(b) for b in bases])
        os.makedirs(part, mode=0o700)
        manifest, problems, warnings, skipped = copy_tree(present, a.root, part)
        after = ([core_fp(b) for b in bases], [hb_marker(b) for b in bases])
        if a.bot_stopped:
            # il fermo deve valere ANCHE a copia finita: se un container e' ripartito durante la copia, si scarta
            again = [stopped_state(b, default_container(b, a.container_prefix), a.docker_bin) for b in bases]
            if any(st[0] == NO for st in again):
                shutil.rmtree(part, ignore_errors=True)
                for pp, st in zip(present, again):
                    print("  %s: %s" % (pp, st[1]))
                print("ERRORE BACKUP CERVELLO: un bot e' ripartito (o il suo stato non e' piu' verificabile) "
                      "durante la copia: copia scartata.")
                print("RISULTATO: FALLITO. Non si deve sostituire nessun container.")
                return 1
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

    # i file irrinunciabili devono esserci nella copia (salvo quelli gia' assenti all'origine con --first-install),
    # e i file del cervello presenti all'origine devono esserci nella copia
    for x in required_missing(part, present):
        if x not in absent_ok:
            problems.append("file irrinunciabile mancante o vuoto nella copia: %s" % x)
    for p in present:
        for c in CRITICAL:
            if os.path.isfile(os.path.join(a.root, p, c)) and \
                    not os.path.isfile(os.path.join(part, p, c)):
                problems.append("file del cervello mancante nella copia: %s/%s" % (p, c))
    # barriera finale: nel percorso normale la copia vale solo con il confine di ciclo verificato
    if not a.bot_stopped and not verified:
        problems.append("confine di ciclo non verificato: il deploy richiede confine_di_ciclo_verificato=true")

    coerenza = {
        "consistente": True,
        "modalita": "bot_fermo" if a.bot_stopped else "ciclo_verificato",
        "metodo": ("finestra di fine ciclo (battito del bot) + nessuna scrittura sui file centrali negli "
                   "ultimi %g s + nessuna modifica (inode, dimensione, istante) ne' variazione del "
                   "contatore dei cicli durante la copia" % a.quiet_secs) if not a.bot_stopped else
                  ("bot fermo (prova sul container con docker inspect + battito vecchio o assente) + nessuna "
                   "scrittura sui file centrali negli ultimi %g s + nessuna modifica (inode, dimensione, "
                   "istante) durante la copia, con il fermo ricontrollato a copia finita" % a.quiet_secs),
        "tentativi": used,
        "quiete_osservata_s": round(quiet_age, 1) if quiet_age is not None else None,
        "file_centrali": list(CORE),
        "file_irrinunciabili": list(REQUIRED),
        "confine_di_ciclo_verificato": bool(verified),
        "stato_del_confine": dict(zip(present, boundary_info)),
    }
    stato = {p: state_summary(os.path.join(part, p, "state_v2.json")) for p in present}
    with open(os.path.join(part, "MANIFEST.json"), "w") as f:
        json.dump({"creato": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "coerenza": coerenza, "stato_copiato": stato,
                   "prima_installazione": {"ammessa": bool(a.first_install),
                                           "cartelle_assenti": list(missing),
                                           "file_irrinunciabili_assenti": list(absent_ok)},
                   "file": manifest, "non_copiati_troppo_grandi": skipped}, f, indent=1)
    os.chmod(os.path.join(part, "MANIFEST.json"), 0o600)

    # prova di ripristino: rilegge dal disco la copia e la confronta col manifesto
    for m in manifest:
        path = os.path.join(part, m["file"])
        if not os.path.isfile(path) or sha256(path) != m["sha256"]:
            problems.append("prova di ripristino: %s non coincide col manifesto" % m["file"])
        elif m["file"].endswith(".jsonl") and os.path.basename(m["file"]) in CRITICAL \
                and jsonl_problem(path):
            problems.append("prova di ripristino: %s non e' un JSONL completo (%s)"
                            % (m["file"], jsonl_problem(path)))
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
    if a.first_install:
        print("  ATTENZIONE: PRIMA INSTALLAZIONE ammessa (--first-install). Cartelle assenti: %s. "
              "File irrinunciabili assenti: %s." % (", ".join(missing) or "nessuna", ", ".join(absent_ok) or "nessuno"))
    if a.bot_stopped:
        print("  MODALITA' BOT FERMO (--bot-stopped): copia fatta con i bot fermi, senza confine di ciclo.")
    for mm in missing:
        print("  ATTENZIONE: cartella assente (accettata con --first-install): %s" % mm)
    for s in skipped:
        print("  non copiato (oltre %d MB, non e' del cervello): %s" % (BIG // (1 << 20), s))
    for w in warnings:
        print("  ATTENZIONE: " + w)
    for p, info in zip(present, boundary_info):
        print("  %s: %s" % (p, info))
    print("  coerenza: finestra stabile al tentativo %d (quiete di %.1f s, nessuna modifica ai file centrali "
          "ne' ai cicli durante la copia); confine di ciclo %s"
          % (used, quiet_age or 0.0, "VERIFICATO" if verified else "non applicabile (bot fermo)"))

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
