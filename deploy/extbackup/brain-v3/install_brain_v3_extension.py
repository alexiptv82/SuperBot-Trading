#!/usr/bin/env python3
"""Installa (o toglie) SOLO l'estensione del backup esterno per Brain V3. Il backup di Falco/Toro non viene toccato.

  python3 install_brain_v3_extension.py status
  python3 install_brain_v3_extension.py install  [--with-timer] [--apply --approve IMPRONTA]
  python3 install_brain_v3_extension.py rollback [--apply]

Senza --apply e' una SIMULAZIONE: controlla tutto, stampa che cosa farebbe e l'IMPRONTA DI APPROVAZIONE dei file
che installerebbe; non scrive niente (nemmeno cartelle). Con --apply serve --approve con quella impronta: chi approva
ha visto quei file e non altri.

Che cosa crea (con --apply), e nient'altro:
  - /opt/superbot-tools/brain_v3_snapshot.py e external_backup_brain_v3.py   (file NUOVI, modo 700)
  - /opt/superbot-extbackup-v3/run-v3.sh                                       (cartella NUOVA, modo 700)
  - solo con --with-timer: superbot-extbackup-v3.service e .timer in /etc/systemd/system (+ daemon-reload, enable --now
    del solo timer; il servizio NON viene avviato)
  - un registro dell'installazione in /root/extbackup-v3-install/INSTALL-MANIFEST.json (per il rollback)
Non tocca: external_backup.py, backup_brain.py, backup_app_db.py, run.sh, recipient, known_hosts, chiavi, unita'
superbot-extbackup.*, dati o cervello dei bot, container, workflow. Non lancia nessun backup.

Rifiuta di procedere se: non e' root; mancano age o git; le cartelle del backup di Falco/Toro non sono come attese;
external_backup.py installato non ha l'impronta rivista; il servizio di Falco/Toro e' in corso; un file di destinazione
esiste gia' con contenuto diverso (mai sovrascritto).
Rollback: toglie i file registrati (solo se invariati), ferma e toglie il solo timer V3, e SPOSTA la cartella di lavoro in
<cartella>.removed-<data> (non cancella mai niente che contenga dati o stato).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "..", "scripts"))
CLASSIC_EXTERNAL_BACKUP_SHA = "7cad7d8fdc83b76f9cd28e93edcc75aafcca05955bf4214a0058b88e491fa5ab"
CLASSIC_NAMES = ("external_backup.py", "backup_brain.py", "backup_app_db.py")
UNIT_SERVICE, UNIT_TIMER = "superbot-extbackup-v3.service", "superbot-extbackup-v3.timer"


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
        p = subprocess.run(["systemctl", *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return p.returncode, (p.stdout + p.stderr).strip()


def plan(a):
    """Elenco (destinazione, sorgente, modo, chiave) dei file dell'estensione."""
    files = [(os.path.join(a.tools_dir, "brain_v3_snapshot.py"), os.path.join(SCRIPTS, "brain_v3_snapshot.py"), 0o700),
             (os.path.join(a.tools_dir, "external_backup_brain_v3.py"), os.path.join(SCRIPTS, "external_backup_brain_v3.py"), 0o700),
             (os.path.join(a.work_dir, "run-v3.sh"), os.path.join(HERE, "run-v3.sh"), 0o700)]
    if a.with_timer:
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


def checks(a):
    """Controlli bloccanti. Restituisce l'elenco dei blocchi (vuoto = si puo' procedere)."""
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


def do_status(a):
    print("== Fotografia (sola lettura)")
    for dest, src, _m in plan(argparse.Namespace(**dict(vars(a), with_timer=True))):
        if os.path.lexists(dest):
            out("PRESENTE" if sha(dest) == sha(src) else "DIVERSO", dest)
        else:
            out("ASSENTE", dest)
    eb = os.path.join(a.tools_dir, "external_backup.py")
    out("INFO", "external_backup.py (Falco/Toro): %s" % (sha(eb) if os.path.isfile(eb) else "assente"))
    out("INFO", "superbot-extbackup.service: %s" % systemctl("is-active", "superbot-extbackup.service")[1])
    out("INFO", "%s: %s" % (UNIT_TIMER, systemctl("is-enabled", UNIT_TIMER)[1] or "non installato"))
    out("INFO", "registro dell'installazione: %s" % ("presente" if os.path.isfile(manifest_path(a)) else "assente"))
    out("INFO", "impronta di approvazione dei file di questo repository: %s" % approval(a))
    return 0


def do_install(a):
    print("== Installazione dell'estensione Brain V3 (%s)" % ("APPLICA" if a.apply else "SIMULAZIONE"))
    bad = checks(a)
    for b in bad:
        out("BLOCCO", b)
    if bad:
        print("ESITO: NESSUNA MODIFICA - %d blocchi" % len(bad))
        return 1
    appr = approval(a)
    todo = [(d, s, m) for d, s, m in plan(a) if not os.path.lexists(d)]
    out("OK", "controlli superati; da creare: %s" % (", ".join(d for d, _s, _m in todo) or "(niente: gia' installato)"))
    out("INFO", "IMPRONTA DI APPROVAZIONE: %s" % appr)
    if not todo:
        print("ESITO: GIA' INSTALLATO - nessuna modifica")
        return 0
    if not a.apply:
        print("ESITO: SIMULAZIONE RIUSCITA - nessuna modifica. Per applicare: install --apply --approve %s%s"
              % (appr, " --with-timer" if a.with_timer else ""))
        return 0
    if a.approve != appr:
        out("BLOCCO", "--approve mancante o diverso dall'impronta dei file di questo repository")
        print("ESITO: NESSUNA MODIFICA")
        return 1
    created = []
    work_new = not os.path.isdir(a.work_dir)
    try:
        if work_new:
            os.makedirs(a.work_dir, mode=0o700)
        os.makedirs(a.state_dir, mode=0o700, exist_ok=True)
        for dest, src, mode in todo:
            if not atomic_put(src, dest, mode):
                raise OSError("verifica fallita su %s" % dest)
            created.append({"path": dest, "sha256": sha(dest), "mode": mode})
            out("OK", "creato %s" % dest)
        previous = []
        if os.path.isfile(manifest_path(a)):
            with open(manifest_path(a)) as f:
                previous = json.load(f).get("file", [])
        record = {"creato": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "file": previous + created,
                  "cartella_di_lavoro_creata": work_new, "work_dir": a.work_dir, "timer": bool(a.with_timer),
                  "approvazione": appr}
        with open(manifest_path(a), "w") as f:
            json.dump(record, f, indent=1, sort_keys=True)
        if a.with_timer:
            for step in (("daemon-reload",), ("enable", "--now", UNIT_TIMER)):
                rc, msg = systemctl(*step)
                if rc != 0:
                    raise OSError("systemctl %s: %s" % (" ".join(step), msg[-200:]))
            out("OK", "timer V3 attivato (il servizio non e' stato avviato)")
    except OSError as e:
        out("BLOCCO", "installazione interrotta: %s" % e)
        for c in created:
            try:
                os.unlink(c["path"])
            except OSError:
                pass
        print("ESITO: FALLITO - rimosso quanto creato da questa esecuzione; il backup di Falco/Toro non e' stato toccato")
        return 1
    print("ESITO: INSTALLATO - solo l'estensione V3. Prossimo passo: run-v3.sh --preflight, poi --plan. "
          "Rollback: install_brain_v3_extension.py rollback --apply")
    return 0


def do_rollback(a):
    print("== Rollback dell'estensione Brain V3 (%s)" % ("APPLICA" if a.apply else "SIMULAZIONE"))
    if os.getuid() != 0 and not a.allow_nonroot:
        out("BLOCCO", "va eseguito come root")
        return 1
    if not os.path.isfile(manifest_path(a)):
        out("BLOCCO", "nessun registro dell'installazione in %s: niente da annullare" % a.state_dir)
        return 1
    with open(manifest_path(a)) as f:
        rec = json.load(f)
    rc, state = systemctl("is-active", "superbot-extbackup-v3.service")
    if state in ("active", "activating"):
        out("BLOCCO", "il servizio V3 e' in corso (%s): attendere la fine" % state)
        return 1
    leave = []
    for c in rec["file"]:
        p = c["path"]
        if not os.path.lexists(p):
            out("INFO", "gia' assente: %s" % p)
        elif sha(p) != c["sha256"]:
            leave.append(p)
            out("INFO", "MODIFICATO dopo l'installazione, lo lascio: %s" % p)
        else:
            out("OK", "%s %s" % ("toglierei" if not a.apply else "tolgo", p))
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
        systemctl("disable", "--now", UNIT_TIMER)
    for c in rec["file"]:
        if c["path"] not in leave and os.path.lexists(c["path"]):
            os.unlink(c["path"])
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
    ap.add_argument("--tools-dir", default="/opt/superbot-tools")
    ap.add_argument("--work-dir", default="/opt/superbot-extbackup-v3")
    ap.add_argument("--classic-dir", default="/opt/superbot-extbackup")
    ap.add_argument("--systemd-dir", default="/etc/systemd/system")
    ap.add_argument("--state-dir", default="/root/extbackup-v3-install")
    ap.add_argument("--ssh-key", default="/root/.ssh/superbot_backup_ed25519")
    ap.add_argument("--allow-nonroot", action="store_true", help="solo per le prove automatiche")
    a = ap.parse_args(argv)
    return {"status": do_status, "install": do_install, "rollback": do_rollback}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
