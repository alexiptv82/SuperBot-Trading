#!/usr/bin/env python3
"""Installa (o toglie) SOLO l'estensione del backup esterno per Brain V3. Il backup di Falco/Toro non viene toccato.

  python3 install_brain_v3_extension.py status
  python3 install_brain_v3_extension.py install  [--apply --approve IMPRONTA]
  python3 install_brain_v3_extension.py install  --with-timer --restore-certificate FILE [--apply --approve IMPRONTA]
  python3 install_brain_v3_extension.py rollback [--apply]

Senza --apply e' una SIMULAZIONE: controlla tutto, stampa che cosa farebbe e l'IMPRONTA DI APPROVAZIONE dei file
che installerebbe; non scrive niente (nemmeno cartelle). Con --apply serve --approve con quella impronta.

Che cosa crea (con --apply), e nient'altro:
  - /opt/superbot-tools/brain_v3_snapshot.py e external_backup_brain_v3.py   (file NUOVI, modo 700)
  - /opt/superbot-extbackup-v3/run-v3.sh                                       (cartella NUOVA, modo 700)
  - un registro in /root/extbackup-v3-install/INSTALL-MANIFEST.json, scritto PRIMA di ogni modifica (stato "in_corso")
    e portato a "completo" solo alla fine: dopo un'interruzione brusca il rollback sa che cosa togliere
  - solo con --with-timer: superbot-extbackup-v3.service/.timer (+ timer-gate.json), vedi sotto

IL TIMER SI ATTIVA SOLO CON LA PROVA (cancello):
  1. un backup V3 REALMENTE pubblicato: <work>/v3/status.json con ultimo_successo, archivio, sha256 e verifica remota,
     nessun errore successivo, e nel clone locale il manifesto e l'archivio (o le parti) con lo SHA-256 giusto;
  2. un ripristino INDIPENDENTE: il certificato scritto da restore_brain_v3_backup.py --certificate su un'ALTRA macchina,
     con esito OK, lo stesso SHA-256 dell'archivio pubblicato, le stesse run (eventi e hash di testa) del manifesto e le
     impronte degli strumenti di ripristino uguali a quelle di questo repository.
  Una uscita 3 («niente da proteggere»), un --plan o un'esecuzione mai riuscita NON soddisfano il cancello.
  L'unita' .timer non ha Persistent=true e NON si usa "enable --now": enable, poi start del SOLO timer, e dopo si controlla
  che il servizio non sia partito. Un solo passo di systemd che fallisce, un segnale o un errore: si disattiva e si
  toglie quanto creato da questa esecuzione (mai un timer attivo senza unita' valida).

Non tocca: external_backup.py, backup_brain.py, backup_app_db.py, run.sh, recipient, known_hosts, chiavi, unita'
superbot-extbackup.*, dati o cervello dei bot, container, workflow. Non lancia nessun backup.
Rollback: toglie i file registrati (solo se invariati), ferma e toglie il solo timer V3, e SPOSTA la cartella di lavoro in
<cartella>.removed-<data> (non cancella mai niente che contenga dati o stato).
"""
import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "..", "scripts"))
CLASSIC_EXTERNAL_BACKUP_SHA = "7cad7d8fdc83b76f9cd28e93edcc75aafcca05955bf4214a0058b88e491fa5ab"
CLASSIC_NAMES = ("external_backup.py", "backup_brain.py", "backup_app_db.py")
UNIT_SERVICE, UNIT_TIMER = "superbot-extbackup-v3.service", "superbot-extbackup-v3.timer"
CERT_SCHEMA = "superbot-brain-v3-restore-certificate-v1"


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def out(tag, msg):
    print("%-10s %s" % (tag, msg))


def systemctl(*args):
    try:
        p = subprocess.run(["systemctl", *args], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return p.returncode, (p.stdout + p.stderr).strip()


def jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def plan(a, with_timer=None):
    """Elenco (destinazione, sorgente, modo) dei file dell'estensione."""
    wt = a.with_timer if with_timer is None else with_timer
    files = [(os.path.join(a.tools_dir, "brain_v3_snapshot.py"), os.path.join(SCRIPTS, "brain_v3_snapshot.py"), 0o700),
             (os.path.join(a.tools_dir, "external_backup_brain_v3.py"), os.path.join(SCRIPTS, "external_backup_brain_v3.py"), 0o700),
             (os.path.join(a.work_dir, "run-v3.sh"), os.path.join(HERE, "run-v3.sh"), 0o700)]
    if wt:
        files += [(os.path.join(a.systemd_dir, UNIT_SERVICE), os.path.join(HERE, UNIT_SERVICE), 0o644),
                  (os.path.join(a.systemd_dir, UNIT_TIMER), os.path.join(HERE, UNIT_TIMER), 0o644)]
    return files


def approval(a):
    lines = []
    for n, src in (("brain_v3_snapshot.py", os.path.join(SCRIPTS, "brain_v3_snapshot.py")),
                   ("external_backup_brain_v3.py", os.path.join(SCRIPTS, "external_backup_brain_v3.py")),
                   ("run-v3.sh", os.path.join(HERE, "run-v3.sh")), (UNIT_SERVICE, os.path.join(HERE, UNIT_SERVICE)),
                   (UNIT_TIMER, os.path.join(HERE, UNIT_TIMER))):
        lines.append("%s %s\n" % (n, sha(src)))
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def this_host(a):
    return a.host_name or socket.gethostname()


# ---- il cancello del timer ----------------------------------------------------------------------------------------

def published_manifests(repo_dir):
    found = []
    base = os.path.join(repo_dir, "brain-v3")
    for dp, _dn, fn in os.walk(base):
        for f in sorted(fn):
            if f.endswith(".manifest.json"):
                try:
                    m = jload(os.path.join(dp, f))
                except (OSError, ValueError):
                    continue
                if isinstance(m, dict) and m.get("famiglia") == "v3":
                    found.append((dp, m))
    return found


def archive_present(folder, m):
    """L'archivio (intero o in parti) e' nel clone con la dimensione e lo SHA-256 del manifesto."""
    if m.get("parti"):
        h = hashlib.sha256()
        for p in m["parti"]:
            path = os.path.join(folder, p["nome"])
            if not os.path.isfile(path) or os.path.getsize(path) != p["dimensione"] or sha(path) != p["sha256"]:
                return False
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        return h.hexdigest() == m["sha256"]
    path = os.path.join(folder, m["archivio"])
    return os.path.isfile(path) and os.path.getsize(path) == m["dimensione"] and sha(path) == m["sha256"]


def timer_gate(a):
    """(problemi, prova). Nessun problema = backup reale pubblicato e ripristino indipendente certificati."""
    bad, proof = [], {}
    v3 = os.path.join(a.work_dir, "v3")
    try:
        st = jload(os.path.join(v3, "status.json"))
    except (OSError, ValueError):
        return ["nessun status.json del backup V3: nessun backup reale e' mai stato eseguito (un --plan o l'uscita 3 non contano)"], proof
    for k in ("ultimo_successo", "archivio", "sha256", "verifica"):
        if not st.get(k):
            bad.append("status.json senza %s: nessun archivio realmente pubblicato e verificato da GitHub" % k)
    if st.get("ultimo_errore"):
        bad.append("l'ultimo tentativo di backup e' fallito: %s" % str(st["ultimo_errore"])[:120])
    if bad:
        return bad, proof
    published = published_manifests(os.path.join(v3, "repo"))
    mine = [(d, m) for d, m in published if m.get("archivio") == st["archivio"] and m.get("sha256") == st["sha256"]]
    if not mine:
        return ["l'archivio indicato in status.json non risulta nel clone locale del repository dei backup"], proof
    if not archive_present(*mine[0]):
        return ["l'archivio pubblicato nel clone locale non ha la dimensione/SHA-256 del suo manifesto"], proof
    proof["archivio_pubblicato"] = st["archivio"]
    cert_path = a.restore_certificate
    if not cert_path:
        return ["manca --restore-certificate: serve il certificato di un ripristino fatto su un'ALTRA macchina"], proof
    try:
        cert = jload(cert_path)
    except (OSError, ValueError):
        return ["certificato di ripristino illeggibile: %s" % cert_path], proof
    if not isinstance(cert, dict) or cert.get("schema") != CERT_SCHEMA or cert.get("esito") != "OK" or cert.get("famiglia") != "v3":
        return ["il certificato non e' un esito OK del ripristino di una famiglia v3"], proof
    if cert.get("eseguito_su") == this_host(a):
        bad.append("il ripristino risulta fatto su QUESTA macchina (%s): serve un ripristino indipendente" % this_host(a))
    certified = [(d, m) for d, m in published if m.get("sha256") == cert.get("archivio_sha256")]
    if not certified:
        bad.append("il certificato riguarda un archivio (sha256 %s...) che non risulta pubblicato" % str(cert.get("archivio_sha256"))[:12])
    else:
        anchors = certified[0][1].get("ancore") or {}
        runs = {r.get("nome"): r for r in cert.get("run") or []}
        if not runs or set(runs) != set(anchors) or any(
                runs[n].get("eventi") != anchors[n].get("eventi") or runs[n].get("testa") != anchors[n].get("testa") for n in anchors):
            bad.append("le run (eventi e hash di testa) del certificato non coincidono con il manifesto dell'archivio pubblicato")
    want = {"restore_brain_v3_backup.py": sha(os.path.join(SCRIPTS, "restore_brain_v3_backup.py")),
            "brain_v3_snapshot.py": sha(os.path.join(SCRIPTS, "brain_v3_snapshot.py"))}
    if cert.get("strumenti") != want:
        bad.append("il certificato non e' stato prodotto con gli strumenti di ripristino di questo repository (impronte diverse)")
    if not bad:
        proof.update({"certificato_archivio_sha256": cert["archivio_sha256"], "ripristino_eseguito_su": cert["eseguito_su"],
                      "controllo_rc84": cert.get("controllo_rc84")})
    return bad, proof


# ---- controlli e primitive ----------------------------------------------------------------------------------------

def checks(a):
    bad = []
    if os.getuid() != 0 and not a.allow_nonroot:
        bad.append("va eseguito come root (uid %d)" % os.getuid())
    for tool in ("age", "git"):
        if not shutil.which(tool):
            bad.append("manca il programma %s" % tool)
    for f in ("recipient.txt", "known_hosts"):
        if not os.path.isfile(os.path.join(a.classic_dir, f)):
            bad.append("manca %s del backup di Falco/Toro" % os.path.join(a.classic_dir, f))
    if not os.path.isfile(a.ssh_key):
        bad.append("manca la chiave di deploy %s" % a.ssh_key)
    eb = os.path.join(a.tools_dir, "external_backup.py")
    if not os.path.isfile(eb):
        bad.append("manca %s" % eb)
    elif sha(eb) != CLASSIC_EXTERNAL_BACKUP_SHA:
        bad.append("external_backup.py installato ha sha256 %s, atteso %s (versione rivista)" % (sha(eb), CLASSIC_EXTERNAL_BACKUP_SHA))
    rc, state = systemctl("is-active", "superbot-extbackup.service")
    if rc == 127 and not a.allow_nonroot:
        bad.append("systemctl non disponibile: non posso escludere un backup di Falco/Toro in corso")
    elif state in ("active", "activating"):
        bad.append("superbot-extbackup.service e' in corso (%s): non installo durante un backup" % state)
    for dest, src, _mode in plan(a):
        if not os.path.isfile(src):
            bad.append("sorgente mancante: %s" % src)
        elif os.path.lexists(dest) and (os.path.islink(dest) or sha(dest) != sha(src)):
            bad.append("%s esiste gia' con contenuto diverso: non lo sovrascrivo" % dest)
        base = os.path.basename(dest)
        if base in CLASSIC_NAMES or base == "run.sh":
            bad.append("destinazione %s e' un file del backup di Falco/Toro: BLOCCO" % dest)
    return bad


def atomic_put(src, dest, mode):
    tmp = os.path.join(os.path.dirname(dest), ".%s.new.%d" % (os.path.basename(dest), os.getpid()))
    try:
        shutil.copyfile(src, tmp)
        os.chmod(tmp, mode)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return sha(dest) == sha(src)


def manifest_path(a):
    return os.path.join(a.state_dir, "INSTALL-MANIFEST.json")


def write_manifest(a, record):
    os.makedirs(a.state_dir, mode=0o700, exist_ok=True)
    tmp = manifest_path(a) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(record, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, manifest_path(a))


def gate_file(a):
    return os.path.join(a.work_dir, "timer-gate.json")


def stray_temp(paths):
    """File temporanei lasciati da un'installazione interrotta mentre scriveva (.NOME.new.PID)."""
    found = []
    for p in paths:
        d, base = os.path.dirname(p), os.path.basename(p)
        if os.path.isdir(d):
            found += [os.path.join(d, n) for n in os.listdir(d) if n.startswith(".%s.new." % base)]
    return found


def disable_timer():
    """Prima si ferma e si disabilita, poi (e solo poi) si possono togliere i file delle unita'."""
    systemctl("stop", UNIT_TIMER)
    systemctl("disable", UNIT_TIMER)


def undo(a, created, timer_touched):
    """Compensazione: toglie quanto creato da QUESTA esecuzione, mai un timer attivo senza unita'."""
    if timer_touched:
        disable_timer()
    for c in reversed(created):
        try:
            if os.path.lexists(c["path"]) and sha(c["path"]) == c["sha256"]:
                os.unlink(c["path"])
        except OSError:
            pass
    if timer_touched:
        systemctl("daemon-reload")


def _on_signal(signum, _frame):
    raise SystemExit(128 + signum)


# ---- comandi ------------------------------------------------------------------------------------------------------

def do_status(a):
    print("== Fotografia (sola lettura)")
    for dest, src, _m in plan(a, with_timer=True):
        if os.path.lexists(dest):
            out("PRESENTE" if sha(dest) == sha(src) else "DIVERSO", dest)
        else:
            out("ASSENTE", dest)
    eb = os.path.join(a.tools_dir, "external_backup.py")
    out("INFO", "external_backup.py (Falco/Toro): %s" % (sha(eb) if os.path.isfile(eb) else "assente"))
    out("INFO", "superbot-extbackup.service: %s" % systemctl("is-active", "superbot-extbackup.service")[1])
    out("INFO", "%s: %s" % (UNIT_TIMER, systemctl("is-enabled", UNIT_TIMER)[1] or "non installato"))
    if os.path.isfile(manifest_path(a)):
        try:
            stato = jload(manifest_path(a)).get("stato")
        except (OSError, ValueError):
            stato = "illeggibile"
        out("ATTENZIONE" if stato != "completo" else "INFO", "registro dell'installazione: %s%s" % (
            stato, " -> installazione interrotta: eseguire rollback --apply" if stato != "completo" else ""))
    else:
        out("INFO", "registro dell'installazione: assente")
    bad, proof = timer_gate(a)
    if bad:
        out("INFO", "cancello del timer: NON soddisfatto (nessun backup reale + ripristino indipendente certificati)")
        for b in bad:
            out("INFO", "  - " + b)
    else:
        out("INFO", "cancello del timer: soddisfatto (%s)" % json.dumps(proof, sort_keys=True))
    out("INFO", "impronta di approvazione dei file di questo repository: %s" % approval(a))
    return 0


def do_install(a):
    print("== Installazione dell'estensione Brain V3 (%s%s)" % ("APPLICA" if a.apply else "SIMULAZIONE",
                                                                 ", con timer" if a.with_timer else ""))
    bad = checks(a)
    proof = {}
    if a.with_timer:
        gate_bad, proof = timer_gate(a)
        bad += ["CANCELLO DEL TIMER: " + b for b in gate_bad]
    if os.path.isfile(manifest_path(a)):
        try:
            stato = jload(manifest_path(a)).get("stato")
        except (OSError, ValueError):
            stato = "illeggibile"
        if stato != "completo":
            bad.append("registro dell'installazione in stato '%s': un'installazione precedente e' stata interrotta; "
                       "eseguire prima rollback --apply" % stato)
    for b in bad:
        out("BLOCCO", b)
    if bad:
        print("ESITO: NESSUNA MODIFICA - %d blocchi" % len(bad))
        return 1
    appr = approval(a)
    todo = [(d, s, m) for d, s, m in plan(a) if not os.path.lexists(d)]
    timer_done = a.with_timer and os.path.isfile(gate_file(a)) and not todo
    out("OK", "controlli superati; da creare: %s" % (", ".join(d for d, _s, _m in todo) or "(niente: gia' installato)"))
    if a.with_timer:
        out("OK", "cancello del timer soddisfatto: backup pubblicato %s, ripristino indipendente su %s" % (
            proof.get("archivio_pubblicato"), proof.get("ripristino_eseguito_su")))
        if proof.get("controllo_rc84") != "eseguito":
            out("INFO", "il ripristino indipendente NON includeva il confronto con il codice RC84 (--v3-src): resta un gate separato")
    out("INFO", "IMPRONTA DI APPROVAZIONE: %s" % appr)
    if not todo and (not a.with_timer or timer_done):
        print("ESITO: GIA' INSTALLATO - nessuna modifica")
        return 0
    if not a.apply:
        print("ESITO: SIMULAZIONE RIUSCITA - nessuna modifica. Per applicare: install --apply --approve %s%s"
              % (appr, " --with-timer --restore-certificate <FILE>" if a.with_timer else ""))
        return 0
    if a.approve != appr:
        out("BLOCCO", "--approve mancante o diverso dall'impronta dei file di questo repository")
        print("ESITO: NESSUNA MODIFICA")
        return 1
    previous = []
    if os.path.isfile(manifest_path(a)):
        previous = jload(manifest_path(a)).get("file", [])
    intended = [{"path": d, "sha256": sha(s), "mode": m} for d, s, m in todo]
    if a.with_timer:
        intended.append({"path": gate_file(a), "sha256": "", "mode": 0o600})
    record = {"creato": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stato": "in_corso", "file": previous + intended,
              "cartella_di_lavoro_creata": not os.path.isdir(a.work_dir), "work_dir": a.work_dir,
              "timer": bool(a.with_timer), "approvazione": appr}
    created, timer_touched, work_new = [], False, record["cartella_di_lavoro_creata"]
    old_term, old_int = signal.signal(signal.SIGTERM, _on_signal), signal.signal(signal.SIGINT, _on_signal)
    try:
        write_manifest(a, record)                                   # PRIMA di ogni modifica: l'interruzione resta recuperabile
        if work_new:
            os.makedirs(a.work_dir, mode=0o700)
        for dest, src, mode in todo:
            if not atomic_put(src, dest, mode):
                raise OSError("verifica fallita su %s" % dest)
            created.append({"path": dest, "sha256": sha(dest), "mode": mode})
            out("OK", "creato %s" % dest)
        if a.with_timer:
            gate_body = json.dumps({"creato": record["creato"], "prova": proof}, sort_keys=True, indent=1) + "\n"
            tmpg = gate_file(a) + ".tmp"
            with open(tmpg, "w") as f:
                f.write(gate_body)
            os.chmod(tmpg, 0o600)
            os.replace(tmpg, gate_file(a))
            created.append({"path": gate_file(a), "sha256": sha(gate_file(a)), "mode": 0o600})
            for c in record["file"]:
                if c["path"] == gate_file(a):
                    c["sha256"] = sha(gate_file(a))
            write_manifest(a, record)
            timer_touched = True
            for step in (("daemon-reload",), ("enable", UNIT_TIMER), ("start", UNIT_TIMER)):
                rc, msg = systemctl(*step)
                if rc != 0:
                    raise OSError("systemctl %s: %s" % (" ".join(step), msg[-200:]))
            rc, timer_state = systemctl("is-active", UNIT_TIMER)
            rc2, enabled = systemctl("is-enabled", UNIT_TIMER)
            _rc, service_state = systemctl("is-active", UNIT_SERVICE)
            if timer_state != "active" or enabled != "enabled":
                raise OSError("il timer non risulta attivo e abilitato (%s / %s)" % (timer_state, enabled))
            if service_state in ("active", "activating"):
                raise OSError("il servizio di backup e' partito all'attivazione del timer (%s): non previsto" % service_state)
            out("OK", "timer V3 attivo; il servizio NON e' partito (nessun avvio arretrato)")
        record["stato"] = "completo"
        write_manifest(a, record)
    except BaseException as e:                                       # errore di systemd, segnale, qualunque interruzione
        out("BLOCCO", "installazione interrotta: %s" % (e if isinstance(e, Exception) else "segnale %s" % getattr(e, "code", e)))
        undo(a, created, timer_touched)
        if work_new and os.path.isdir(a.work_dir) and not os.listdir(a.work_dir):
            os.rmdir(a.work_dir)
        if previous:
            record["file"], record["stato"] = previous, "completo"
            write_manifest(a, record)
        elif os.path.isfile(manifest_path(a)):
            os.unlink(manifest_path(a))
        print("ESITO: FALLITO - rimosso e disattivato quanto creato da questa esecuzione; "
              "il backup di Falco/Toro non e' stato toccato")
        if isinstance(e, SystemExit):
            raise
        return 1
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)
    print("ESITO: INSTALLATO - solo l'estensione V3%s. Prossimo passo: %s. Rollback: install_brain_v3_extension.py rollback --apply"
          % (" con timer" if a.with_timer else " (nessun timer)",
             "controllare il primo giro notturno" if a.with_timer else "run-v3.sh --preflight, --plan, poi il primo backup reale"))
    return 0


def do_rollback(a):
    print("== Rollback dell'estensione Brain V3 (%s)" % ("APPLICA" if a.apply else "SIMULAZIONE"))
    if os.getuid() != 0 and not a.allow_nonroot:
        out("BLOCCO", "va eseguito come root")
        return 1
    if not os.path.isfile(manifest_path(a)):
        out("BLOCCO", "nessun registro dell'installazione in %s: niente da annullare" % a.state_dir)
        return 1
    rec = jload(manifest_path(a))
    rc, state = systemctl("is-active", UNIT_SERVICE)
    if state in ("active", "activating"):
        out("BLOCCO", "il servizio V3 e' in corso (%s): attendere la fine" % state)
        return 1
    if rec.get("stato") != "completo":
        out("INFO", "registro in stato '%s': installazione interrotta, si toglie quanto risulta presente e invariato" % rec.get("stato"))
    leave = []
    for c in rec["file"]:
        p = c["path"]
        if not os.path.lexists(p):
            out("INFO", "gia' assente: %s" % p)
        elif c.get("sha256") and sha(p) != c["sha256"]:
            leave.append(p)
            out("INFO", "MODIFICATO dopo l'installazione, lo lascio: %s" % p)
        else:
            out("OK", "%s %s" % ("toglierei" if not a.apply else "tolgo", p))
    strays = stray_temp([c["path"] for c in rec["file"]])
    for p in strays:
        out("OK", "%s il temporaneo di un'installazione interrotta: %s" % ("toglierei" if not a.apply else "tolgo", p))
    if rec.get("timer"):
        out("OK", "%s il timer V3" % ("fermerei e toglierei" if not a.apply else "fermo e tolgo"))
    wd = rec.get("work_dir", a.work_dir)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    if os.path.isdir(wd):
        out("OK", "%s %s in %s.removed-%s (nessuna cancellazione)" % ("sposterei" if not a.apply else "sposto", wd, wd, stamp))
    if not a.apply:
        print("ESITO: SIMULAZIONE RIUSCITA - nessuna modifica. Per applicare: rollback --apply")
        return 0
    if rec.get("timer"):
        disable_timer()
    for c in rec["file"]:
        if c["path"] not in leave and os.path.lexists(c["path"]):
            os.unlink(c["path"])
    for p in strays:
        os.unlink(p)
    if rec.get("timer"):
        systemctl("daemon-reload")
    if os.path.isdir(wd):
        os.rename(wd, "%s.removed-%s" % (wd, stamp))
    os.rename(manifest_path(a), os.path.join(a.state_dir, "INSTALL-MANIFEST.rolledback-%s.json" % stamp))
    print("ESITO: RIPRISTINATO - rimossa solo l'estensione V3%s; il backup di Falco/Toro non e' stato toccato"
          % ("; file modificati lasciati: %d" % len(leave) if leave else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("status", "install", "rollback"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--approve", default="")
    ap.add_argument("--with-timer", action="store_true")
    ap.add_argument("--restore-certificate", default="", help="certificato di restore_brain_v3_backup.py --certificate")
    ap.add_argument("--tools-dir", default="/opt/superbot-tools")
    ap.add_argument("--work-dir", default="/opt/superbot-extbackup-v3")
    ap.add_argument("--classic-dir", default="/opt/superbot-extbackup")
    ap.add_argument("--systemd-dir", default="/etc/systemd/system")
    ap.add_argument("--state-dir", default="/root/extbackup-v3-install")
    ap.add_argument("--ssh-key", default="/root/.ssh/superbot_backup_ed25519")
    ap.add_argument("--host-name", default="", help="solo per le prove automatiche")
    ap.add_argument("--allow-nonroot", action="store_true", help="solo per le prove automatiche")
    a = ap.parse_args(argv)
    return {"status": do_status, "install": do_install, "rollback": do_rollback}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
