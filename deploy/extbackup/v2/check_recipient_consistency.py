#!/usr/bin/env python3
"""Verifica di COERENZA dei destinatari age: tutti gli script, i wrapper e le unita' pianificate usano lo stesso destinatario V2.

Sola lettura, nessuna chiave privata, nessuna rete.
  check_recipient_consistency.py                      controlla il REPOSITORIO (wrapper, unita', script, file dei destinatari)
  check_recipient_consistency.py --installed [opzioni] controlla i file INSTALLATI sulla VPS contro quelli del repository

Controlli sul repository:
  - recipient-v2.txt: solo chiavi pubbliche valide; ne ricava l'IMPRONTA approvata;
  - la chiave V1 (recipient.txt) e' diversa e il suo file e' invariato; nessun file V2 la cita;
  - ogni wrapper di backup passa --expect-recipients-sha256 con QUELLA impronta, il file dei destinatari V2, il repository V2
    e la chiave di deploy V2, e lancia lo script a destinatari multipli (external_backup_multi.py / external_backup_brain_v3.py);
  - nessun wrapper, unita' o script V2 contiene riferimenti V1 (repository, chiave di deploy, file dei destinatari, chiave);
  - le unita' pianificate eseguono solo i wrapper V2 e i timer non hanno Persistent=true;
  - external_backup_multi.py fissa l'impronta di external_backup.py realmente presente.
Controlli con --installed: file dei destinatari sulla VPS con l'impronta approvata; wrapper, strumenti e unita' installati identici a
quelli del repository; unita' installate che eseguono solo wrapper V2; file V1 dei destinatari invariato.
Uscita 0 se tutto coincide, 1 altrimenti. Le righe sono OK/NO con frasi fisse.
"""
import argparse
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "deploy", "scripts"))
import age_recipients as ar                                   # noqa: E402

V1_RECIPIENT_FILE_SHA256 = "68a1ecb876bd050406ee487352450814688b04de2401f894b4928a7021621ff8"
V2_DIR = "/opt/superbot-extbackup-v2"
V1_FORBIDDEN = ("/opt/superbot-extbackup/recipient.txt", "superbot-backups.git", "superbot_backup_ed25519", "age142uj5c8x",
                "/opt/superbot-extbackup/run.sh", "/opt/superbot-extbackup/work")
WRAPPERS = {   # percorso nel repository -> (script lanciato, cartella di installazione)
    "deploy/extbackup/v2/run-classic.sh": ("external_backup_multi.py", V2_DIR + "/run-classic.sh"),
    "deploy/extbackup/brain-v3/run-v3.sh": ("external_backup_brain_v3.py", "/opt/superbot-extbackup-v3/run-v3.sh"),
}
UNITS = {      # unita' -> wrapper che puo' eseguire
    "deploy/extbackup/v2/superbot-extbackup-v2.service": V2_DIR + "/run-classic.sh",
    "deploy/extbackup/brain-v3/superbot-extbackup-v3.service": "/opt/superbot-extbackup-v3/run-v3.sh",
}
TIMERS = ("deploy/extbackup/v2/superbot-extbackup-v2.timer", "deploy/extbackup/brain-v3/superbot-extbackup-v3.timer")
TOOLS = ("age_recipients.py", "external_backup_multi.py", "external_backup_brain_v3.py", "brain_v3_snapshot.py")
REQUIRED = ('--recipient-file ' + V2_DIR + '/recipients.txt', "--remote git@github.com:alexiptv82/superbot-backups-v2.git",
            "--ssh-key /root/.ssh/superbot_backup_v2_ed25519")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def code_only(text):
    """Testo senza le righe di commento: i commenti possono spiegare l'origine V1, il codice no."""
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))


class Report:
    def __init__(self):
        self.bad = 0

    def line(self, ok, msg):
        print(("OK  " if ok else "NO  ") + msg)
        if not ok:
            self.bad += 1


def repo_checks(root, rep):
    rec_path = os.path.join(root, "deploy", "extbackup", "recipient-v2.txt")
    try:
        keys = ar.read_recipients(rec_path)
    except ar.RecipientError as e:
        rep.line(False, "recipient-v2.txt non valido: %s" % e.code)
        return None
    fp = ar.fingerprint(keys)
    rep.line(True, "recipient-v2.txt: %d chiave/i pubblica/he valida/e, impronta approvata ricavata" % len(keys))
    v1 = os.path.join(root, "deploy", "extbackup", "recipient.txt")
    rep.line(os.path.isfile(v1) and sha(v1) == V1_RECIPIENT_FILE_SHA256, "file dei destinatari V1 presente e invariato")
    try:
        rep.line(not (set(ar.read_recipients(v1)) & set(keys)), "la chiave V1 non e' tra i destinatari V2")
    except ar.RecipientError:
        rep.line(False, "file V1 illeggibile")
    for rel, (script, _dest) in WRAPPERS.items():
        text = code_only(read(os.path.join(root, rel)))
        rep.line("--expect-recipients-sha256 " + fp in text, "%s: impronta dei destinatari approvata" % os.path.basename(rel))
        rep.line(all(r in text for r in REQUIRED), "%s: destinatari, repository e chiave di deploy V2" % os.path.basename(rel))
        rep.line(("/opt/superbot-tools/" + script) in text, "%s: lancia lo script a destinatari multipli (%s)" % (os.path.basename(rel), script))
        rep.line("/opt/superbot-tools/external_backup.py" not in text, "%s: non lancia il backup classico direttamente" % os.path.basename(rel))
        rep.line(not [x for x in V1_FORBIDDEN if x in text], "%s: nessun riferimento V1" % os.path.basename(rel))
    for rel, wrapper in UNITS.items():
        text = code_only(read(os.path.join(root, rel)))
        exec_lines = re.findall(r"(?m)^ExecStart=(\S+)", text)
        rep.line(exec_lines == [wrapper], "%s: esegue solo il wrapper V2" % os.path.basename(rel))
        rep.line(not [x for x in V1_FORBIDDEN if x in text], "%s: nessun riferimento V1" % os.path.basename(rel))
    for rel in TIMERS:
        text = read(os.path.join(root, rel))
        rep.line(not re.search(r"(?m)^\s*Persistent\s*=\s*true", text, re.I), "%s: nessun Persistent=true" % os.path.basename(rel))
    for name in TOOLS:
        text = read(os.path.join(root, "deploy", "scripts", name))
        rep.line(not [x for x in V1_FORBIDDEN if x in text], "%s: nessun riferimento V1" % name)
    multi = read(os.path.join(root, "deploy", "scripts", "external_backup_multi.py"))
    real = sha(os.path.join(root, "deploy", "scripts", "external_backup.py"))
    rep.line(('CLASSIC_SHA256 = "%s"' % real) in multi, "external_backup_multi.py fissa l'impronta di external_backup.py presente")
    return fp


def installed_checks(root, fp, a, rep):
    pairs = [(os.path.join(root, "deploy/extbackup/v2/run-classic.sh"), os.path.join(a.v2_dir, "run-classic.sh")),
             (os.path.join(root, "deploy/extbackup/brain-v3/run-v3.sh"), os.path.join(a.v3_dir, "run-v3.sh"))]
    pairs += [(os.path.join(root, "deploy", "scripts", n), os.path.join(a.tools_dir, n)) for n in TOOLS]
    rec = os.path.join(a.v2_dir, "recipients.txt")
    anything = any(os.path.exists(dst) for _src, dst in pairs)
    if os.path.exists(rec) or anything:
        try:
            keys = ar.read_recipients(rec)
            rep.line(ar.fingerprint(keys) == fp, "destinatari installati (%s): impronta approvata" % rec)
        except ar.RecipientError as e:
            rep.line(False, "destinatari installati: %s" % e.code)
    else:
        print("--  nulla di V2 installato su questo server: niente da confrontare")
    for src, dst in pairs:
        if not os.path.lexists(dst):
            print("--  non installato (profilo non in uso?): %s" % os.path.basename(dst))
            continue
        rep.line(not os.path.islink(dst) and sha(dst) == sha(src), "installato identico al repository: %s" % os.path.basename(dst))
    classic = os.path.join(a.tools_dir, "external_backup.py")
    if os.path.isfile(classic):
        rep.line(sha(classic) == sha(os.path.join(root, "deploy/scripts/external_backup.py")), "external_backup.py installato = versione rivista")
    for rel in list(UNITS) + list(TIMERS):
        dst = os.path.join(a.systemd_dir, os.path.basename(rel))
        if os.path.exists(dst):
            rep.line(sha(dst) == sha(os.path.join(root, rel)), "unita' installata identica al repository: %s" % os.path.basename(dst))
    for unit in sorted(os.listdir(a.systemd_dir)) if os.path.isdir(a.systemd_dir) else []:
        if unit.startswith("superbot-extbackup") and unit.endswith(".service") and unit != "superbot-extbackup.service":
            text = code_only(read(os.path.join(a.systemd_dir, unit)))
            rep.line(not [x for x in V1_FORBIDDEN if x in text], "%s: nessun riferimento V1" % unit)
    v1 = os.path.join(a.v1_dir, "recipient.txt")
    if os.path.exists(v1):
        rep.line(sha(v1) == V1_RECIPIENT_FILE_SHA256, "file V1 dei destinatari invariato (non modificato dalla migrazione)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=ROOT, help="radice del repository")
    ap.add_argument("--installed", action="store_true")
    ap.add_argument("--v2-dir", default=V2_DIR)
    ap.add_argument("--v3-dir", default="/opt/superbot-extbackup-v3")
    ap.add_argument("--v1-dir", default="/opt/superbot-extbackup")
    ap.add_argument("--tools-dir", default="/opt/superbot-tools")
    ap.add_argument("--systemd-dir", default="/etc/systemd/system")
    a = ap.parse_args(argv)
    rep = Report()
    fp = repo_checks(a.root, rep)
    if a.installed and fp:
        installed_checks(a.root, fp, a, rep)
    print("COERENZA DESTINATARI: %s" % ("OK" if rep.bad == 0 else "NO (%d)" % rep.bad))
    return 0 if rep.bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
