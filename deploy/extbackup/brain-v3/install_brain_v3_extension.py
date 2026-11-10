#!/usr/bin/env python3
"""Installa (o toglie) i soli file del backup esterno cifrato V2 (destinatario age V2): profilo `v3` (Brain V3 e Brain Free) e
profilo `classic` (Falco/Toro). Il backup V1 di Falco/Toro (run.sh, timer 03:20, repository superbot-backups) NON viene toccato.

  python3 install_brain_v3_extension.py [--profile v3|classic] status
  python3 install_brain_v3_extension.py [--profile ...] install  [--apply --approve IMPRONTA]
  python3 install_brain_v3_extension.py [--profile ...] install  --with-timer --restore-certificate FILE [--apply --approve IMPRONTA]
  python3 install_brain_v3_extension.py [--profile ...] rollback [--apply]

Senza --apply e' una SIMULAZIONE: controlla tutto, stampa che cosa farebbe e l'IMPRONTA DI APPROVAZIONE dei file che
installerebbe (la stessa per entrambi i profili); non scrive niente (nemmeno cartelle). Con --apply serve --approve.

Che cosa crea (con --apply), e nient'altro:
  - in /opt/superbot-tools: age_recipients.py (comune), brain_v3_snapshot.py e external_backup_brain_v3.py (profilo v3) oppure
    external_backup_multi.py (profilo classic): file NUOVI, modo 700;
  - /opt/superbot-extbackup-v2/recipients.txt: le chiavi PUBBLICHE approvate (copia di deploy/extbackup/recipient-v2.txt);
  - il wrapper: /opt/superbot-extbackup-v3/run-v3.sh (v3) oppure /opt/superbot-extbackup-v2/run-classic.sh (classic);
  - un registro in /root/extbackup-v3-install, scritto PRIMA di ogni modifica (stato "in_corso", poi "completo");
  - solo con --with-timer: le unita' systemd del profilo (+ timer-gate.json), vedi sotto.
Prima di tutto controlla che nel repository wrapper, unita' e script usino lo stesso destinatario V2 con la stessa impronta
(check_recipient_consistency.py): se no, BLOCCO. I file sul server non cambiano mai se esistono gia' con contenuto diverso.

IL TIMER SI ATTIVA SOLO CON LA PROVA (cancello):
  1. un backup REALMENTE pubblicato dal profilo (status.json con ultimo_successo, archivio, sha256 e verifica remota, nessun
     errore successivo; manifesto e archivio/parti nel clone locale con lo SHA-256 giusto);
  2. un ripristino INDIPENDENTE di quell'archivio, certificato da una delle due strade:
       - restore_brain_v3_backup.py --certificate su un'ALTRA macchina (famiglia v3), oppure
       - la riga CERTIFICATO stampata dal workflow protetto age-v2-recovery-verify (origine github-actions, qualunque famiglia),
         con le impronte del workflow e dello script uguali a quelle di questo repository e il commit degli script fissato.
  Una uscita 3, un --plan o un'esecuzione mai riuscita NON soddisfano il cancello. L'unita' .timer non ha Persistent=true e NON
  si usa "enable --now": enable, poi start del SOLO timer, e dopo si controlla che il servizio non sia partito. Un solo passo di
  systemd che fallisce, un segnale o un errore: si disattiva e si toglie quanto creato da questa esecuzione.

Rollback: toglie i file registrati (solo se invariati; quelli comuni solo se l'altro profilo non li usa), ferma e toglie il solo
timer del profilo e SPOSTA la cartella di lavoro in <cartella>.removed-<data> (non cancella mai dati o stato).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
SCRIPTS = os.path.join(REPO, "deploy", "scripts")
V2SRC = os.path.join(REPO, "deploy", "extbackup", "v2")
RECIPIENTS_SRC = os.path.join(REPO, "deploy", "extbackup", "recipient-v2.txt")
CHECKER = os.path.join(V2SRC, "check_recipient_consistency.py")
WORKFLOW = os.path.join(REPO, ".github", "workflows", "age-v2-recovery-verify.yml")
VERIFY_SCRIPT = os.path.join(REPO, "deploy", "extbackup", "age-v2-recovery", "verify_recovery.py")
CLASSIC_EXTERNAL_BACKUP_SHA = "7cad7d8fdc83b76f9cd28e93edcc75aafcca05955bf4214a0058b88e491fa5ab"
CLASSIC_NAMES = ("external_backup.py", "backup_brain.py", "backup_app_db.py")
CERT_SCHEMA = "superbot-brain-v3-restore-certificate-v1"
SHARED = ("age_recipients.py", "recipients.txt")
ALL_UNITS = (("superbot-extbackup-v3.service", HERE), ("superbot-extbackup-v3.timer", HERE),
             ("superbot-extbackup-v2.service", V2SRC), ("superbot-extbackup-v2.timer", V2SRC))


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


def prof(a):
    """Tutto cio' che cambia da un profilo all'altro."""
    if a.profile == "v3":
        wd = a.work_dir
        return {"name": "v3", "manifest": "INSTALL-MANIFEST.json", "label": "Brain V3 / Brain Free",
                "tools": ("age_recipients.py", "brain_v3_snapshot.py", "external_backup_brain_v3.py"),
                "wrapper": (os.path.join(wd, "run-v3.sh"), os.path.join(HERE, "run-v3.sh")),
                "service": "superbot-extbackup-v3.service", "timer": "superbot-extbackup-v3.timer", "units_src": HERE,
                "gate_file": os.path.join(wd, "timer-gate.json"), "status": os.path.join(wd, "v3", "status.json"),
                "repo": os.path.join(wd, "v3", "repo"), "sub": "brain-v3", "family": "v3",
                "dirs": [a.v2_dir, wd], "aside": wd, "wrapper_name": "run-v3.sh"}
    wd = a.v2_dir
    return {"name": "classic", "manifest": "INSTALL-MANIFEST-classic.json", "label": "Falco/Toro",
            "tools": ("age_recipients.py", "external_backup_multi.py"),
            "wrapper": (os.path.join(wd, "run-classic.sh"), os.path.join(V2SRC, "run-classic.sh")),
            "service": "superbot-extbackup-v2.service", "timer": "superbot-extbackup-v2.timer", "units_src": V2SRC,
            "gate_file": os.path.join(wd, "timer-gate.json"), "status": os.path.join(wd, "work", "status.json"),
            "repo": os.path.join(wd, "work", "repo"), "sub": "archives", "family": "classico",
            "dirs": [wd], "aside": os.path.join(wd, "work"), "wrapper_name": "run-classic.sh"}


def plan(a, with_timer=None):
    """Elenco (destinazione, sorgente, modo) dei file del profilo."""
    p = prof(a)
    wt = a.with_timer if with_timer is None else with_timer
    files = [(os.path.join(a.tools_dir, n), os.path.join(SCRIPTS, n), 0o700) for n in p["tools"]]
    files.append((os.path.join(a.v2_dir, "recipients.txt"), RECIPIENTS_SRC, 0o644))
    files.append((p["wrapper"][0], p["wrapper"][1], 0o700))
    if wt:
        files += [(os.path.join(a.systemd_dir, p["service"]), os.path.join(p["units_src"], p["service"]), 0o644),
                  (os.path.join(a.systemd_dir, p["timer"]), os.path.join(p["units_src"], p["timer"]), 0o644)]
    return files


def approval(a):
    """Impronta unica sui file di ENTRAMBI i profili (un'approvazione sola per tutto il pacchetto V2)."""
    srcs = [(n, os.path.join(SCRIPTS, n)) for n in ("age_recipients.py", "brain_v3_snapshot.py", "external_backup_brain_v3.py",
                                                     "external_backup_multi.py")]
    srcs += [("recipient-v2.txt", RECIPIENTS_SRC), ("run-v3.sh", os.path.join(HERE, "run-v3.sh")),
             ("run-classic.sh", os.path.join(V2SRC, "run-classic.sh"))]
    srcs += [(n, os.path.join(d, n)) for n, d in ALL_UNITS]
    return hashlib.sha256("".join("%s %s\n" % (n, sha(p)) for n, p in srcs).encode()).hexdigest()


def this_host(a):
    return a.host_name or socket.gethostname()


# ---- il cancello del timer ----------------------------------------------------------------------------------------

def published_manifests(p):
    found = []
    for dp, _dn, fn in os.walk(os.path.join(p["repo"], p["sub"])):
        for f in sorted(fn):
            if f.endswith(".manifest.json"):
                try:
                    m = jload(os.path.join(dp, f))
                except (OSError, ValueError):
                    continue
                if isinstance(m, dict) and m.get("famiglia", "classico") == p["family"]:
                    found.append((dp, m))
    return found


def archive_present(folder, m):
    """L'archivio (intero o in parti) e' nel clone con la dimensione e lo SHA-256 del manifesto."""
    if m.get("parti"):
        h = hashlib.sha256()
        for part in m["parti"]:
            path = os.path.join(folder, part["nome"])
            if not os.path.isfile(path) or os.path.getsize(path) != part["dimensione"] or sha(path) != part["sha256"]:
                return False
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        return h.hexdigest() == m["sha256"]
    path = os.path.join(folder, m["archivio"])
    return os.path.isfile(path) and os.path.getsize(path) == m["dimensione"] and sha(path) == m["sha256"]


def load_certificates(path):
    """Certificati da un file: un JSON, oppure righe `CERTIFICATO {json}` copiate dal log del workflow, oppure righe JSON."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        whole = json.loads(text)
        return [whole] if isinstance(whole, dict) else [c for c in whole if isinstance(c, dict)]
    except ValueError:
        pass
    found = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("CERTIFICATO "):
            line = line[len("CERTIFICATO "):]
        if line.startswith("{"):
            try:
                c = json.loads(line)
            except ValueError:
                continue
            if isinstance(c, dict):
                found.append(c)
    return found


def pinned_sha_of_workflow():
    m = re.search(r"PINNED_SHA:\s*([0-9a-f]{40})", open(WORKFLOW, encoding="utf-8").read())
    return m.group(1) if m else ""


def check_certificate(a, p, c, published):
    """Problemi di UN certificato (lista vuota = valido)."""
    bad = []
    origin = c.get("origine", "ripristino-locale")
    if c.get("esito") != "OK":
        bad.append("il certificato non riporta esito OK")
    if origin == "github-actions":
        if not str(c.get("eseguito_su", "")).startswith("github-actions"):
            bad.append("certificato di origine github-actions ma eseguito altrove")
        if c.get("workflow_sha256") != sha(WORKFLOW) or c.get("script_sha256") != sha(VERIFY_SCRIPT):
            bad.append("il certificato non e' stato prodotto dal workflow e dallo script di questo repository (impronte diverse)")
        if c.get("pinned_sha") != pinned_sha_of_workflow():
            bad.append("il certificato usa script di un commit diverso da quello fissato nel workflow")
        if not re.fullmatch(r"\d{5,}", str(c.get("run_id", ""))):
            bad.append("il certificato non indica il numero della run di GitHub Actions")
    else:
        if p["family"] != "v3":
            bad.append("per questa famiglia serve un certificato prodotto dal workflow protetto (origine github-actions)")
        if c.get("eseguito_su") == this_host(a):
            bad.append("il ripristino risulta fatto su QUESTA macchina (%s): serve un ripristino indipendente" % this_host(a))
        want = {"restore_brain_v3_backup.py": sha(os.path.join(SCRIPTS, "restore_brain_v3_backup.py")),
                "brain_v3_snapshot.py": sha(os.path.join(SCRIPTS, "brain_v3_snapshot.py"))}
        if c.get("strumenti") != want:
            bad.append("il certificato non e' stato prodotto con gli strumenti di ripristino di questo repository (impronte diverse)")
    certified = [(d, m) for d, m in published if m.get("sha256") == c.get("archivio_sha256")]
    if not certified:
        bad.append("il certificato riguarda un archivio (sha256 %s...) che non risulta pubblicato" % str(c.get("archivio_sha256"))[:12])
    elif origin != "github-actions" and p["family"] == "v3":
        anchors = certified[0][1].get("ancore") or {}
        runs = {r.get("nome"): r for r in c.get("run") or []}
        if not runs or set(runs) != set(anchors) or any(
                runs[n].get("eventi") != anchors[n].get("eventi") or runs[n].get("testa") != anchors[n].get("testa") for n in anchors):
            bad.append("le run (eventi e hash di testa) del certificato non coincidono con il manifesto dell'archivio pubblicato")
    return bad


def timer_gate(a):
    """(problemi, prova). Nessun problema = backup reale pubblicato e ripristino indipendente certificati."""
    p = prof(a)
    bad, proof = [], {}
    try:
        st = jload(p["status"])
    except (OSError, ValueError):
        return ["nessun status.json del backup %s: nessun backup reale e' mai stato eseguito (un --plan o l'uscita 3 non contano)"
                % p["label"]], proof
    for k in ("ultimo_successo", "archivio", "sha256", "verifica"):
        if not st.get(k):
            bad.append("status.json senza %s: nessun archivio realmente pubblicato e verificato da GitHub" % k)
    if st.get("ultimo_errore"):
        bad.append("l'ultimo tentativo di backup e' fallito: %s" % str(st["ultimo_errore"])[:120])
    if bad:
        return bad, proof
    published = published_manifests(p)
    mine = [(d, m) for d, m in published if m.get("archivio") == st["archivio"] and m.get("sha256") == st["sha256"]]
    if not mine:
        return ["l'archivio indicato in status.json non risulta nel clone locale del repository dei backup"], proof
    if not archive_present(*mine[0]):
        return ["l'archivio pubblicato nel clone locale non ha la dimensione/SHA-256 del suo manifesto"], proof
    proof["archivio_pubblicato"] = st["archivio"]
    if not a.restore_certificate:
        return ["manca --restore-certificate: serve il certificato di un ripristino indipendente (un'ALTRA macchina o il workflow protetto)"], proof
    try:
        certs = load_certificates(a.restore_certificate)
    except (OSError, ValueError):
        return ["certificato di ripristino illeggibile: %s" % a.restore_certificate], proof
    cands = [c for c in certs if c.get("schema") == CERT_SCHEMA and c.get("famiglia") == p["family"]]
    if not cands:
        return ["il certificato non e' un esito OK del ripristino di una famiglia %s" % p["family"]], proof
    best = None
    for c in cands:
        problems = check_certificate(a, p, c, published)
        if not problems:
            proof.update({"certificato_archivio_sha256": c["archivio_sha256"], "origine": c.get("origine", "ripristino-locale"),
                          "ripristino_eseguito_su": c.get("eseguito_su"), "controllo_rc84": c.get("controllo_rc84")})
            return [], proof
        best = best or problems
    return best, proof


# ---- controlli e primitive ----------------------------------------------------------------------------------------

def checks(a):
    bad = []
    p = prof(a)
    if os.getuid() != 0 and not a.allow_nonroot:
        bad.append("va eseguito come root (uid %d)" % os.getuid())
    for tool in ("age", "git"):
        if not shutil.which(tool):
            bad.append("manca il programma %s" % tool)
    if not os.path.isfile(os.path.join(a.classic_dir, "known_hosts")):
        bad.append("manca %s (chiavi di GitHub, in sola lettura)" % os.path.join(a.classic_dir, "known_hosts"))
    if not os.path.isfile(a.ssh_key):
        bad.append("manca la chiave di deploy V2 %s (repository superbot-backups-v2, scrittura)" % a.ssh_key)
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
    cp = subprocess.run([sys.executable, "-I", CHECKER, "--root", REPO], capture_output=True, text=True, timeout=120)
    if cp.returncode != 0:
        bad.append("coerenza dei destinatari nel repository: NO (%s)" % "; ".join(
            l[4:] for l in cp.stdout.splitlines() if l.startswith("NO  "))[:300])
    for dest, src, _mode in plan(a):
        if not os.path.isfile(src):
            bad.append("sorgente mancante: %s" % src)
        elif os.path.lexists(dest) and (os.path.islink(dest) or sha(dest) != sha(src)):
            bad.append("%s esiste gia' con contenuto diverso: non lo sovrascrivo" % dest)
        base = os.path.basename(dest)
        if base in CLASSIC_NAMES or base in ("run.sh", "recipient.txt"):
            bad.append("destinazione %s e' un file del backup V1 di Falco/Toro: BLOCCO" % dest)
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
    return os.path.join(a.state_dir, prof(a)["manifest"])


def write_manifest(a, record):
    os.makedirs(a.state_dir, mode=0o700, exist_ok=True)
    tmp = manifest_path(a) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(record, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, manifest_path(a))


def shared_paths(a):
    return {os.path.join(a.tools_dir, "age_recipients.py"), os.path.join(a.v2_dir, "recipients.txt")}


def other_profile_files(a):
    """Cio' che l'ALTRO profilo (se installato) usa ancora: i file comuni e quelli che ha registrato."""
    other = "INSTALL-MANIFEST-classic.json" if a.profile == "v3" else "INSTALL-MANIFEST.json"
    path = os.path.join(a.state_dir, other)
    if not os.path.isfile(path):
        return set()
    try:
        return shared_paths(a) | {c["path"] for c in jload(path).get("file", [])}
    except (OSError, ValueError, KeyError):
        return shared_paths(a)


def orphan_shared(a, rec):
    """File comuni gia' presenti all'installazione e identici al repository: si tolgono solo se l'ALTRO profilo non c'e' piu'."""
    if other_profile_files(a):
        return []
    pairs = [(os.path.join(a.tools_dir, "age_recipients.py"), os.path.join(SCRIPTS, "age_recipients.py")),
             (os.path.join(a.v2_dir, "recipients.txt"), RECIPIENTS_SRC)]
    listed = {c["path"] for c in rec["file"]}
    return [d for d, src in pairs if d not in listed and os.path.isfile(d) and not os.path.islink(d) and sha(d) == sha(src)]


def stray_temp(paths):
    """File temporanei lasciati da un'installazione interrotta mentre scriveva (.NOME.new.PID)."""
    found = []
    for pth in paths:
        d, base = os.path.dirname(pth), os.path.basename(pth)
        if os.path.isdir(d):
            found += [os.path.join(d, n) for n in os.listdir(d) if n.startswith(".%s.new." % base)]
    return found


def disable_timer(p):
    """Prima si ferma e si disabilita, poi (e solo poi) si possono togliere i file delle unita'."""
    systemctl("stop", p["timer"])
    systemctl("disable", p["timer"])


def undo(a, created, timer_touched):
    """Compensazione: toglie quanto creato da QUESTA esecuzione, mai un timer attivo senza unita'."""
    p = prof(a)
    if timer_touched:
        disable_timer(p)
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
    p = prof(a)
    print("== Fotografia, profilo %s (sola lettura)" % p["name"])
    for dest, src, _m in plan(a, with_timer=True):
        if os.path.lexists(dest):
            out("PRESENTE" if sha(dest) == sha(src) else "DIVERSO", dest)
        else:
            out("ASSENTE", dest)
    eb = os.path.join(a.tools_dir, "external_backup.py")
    out("INFO", "external_backup.py (V1 Falco/Toro): %s" % (sha(eb) if os.path.isfile(eb) else "assente"))
    out("INFO", "superbot-extbackup.service (V1): %s" % systemctl("is-active", "superbot-extbackup.service")[1])
    out("INFO", "%s: %s" % (p["timer"], systemctl("is-enabled", p["timer"])[1] or "non installato"))
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
    p = prof(a)
    print("== Installazione V2, profilo %s (%s%s)" % (p["name"], "APPLICA" if a.apply else "SIMULAZIONE",
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
    timer_done = a.with_timer and os.path.isfile(p["gate_file"]) and not todo
    out("OK", "controlli superati (coerenza dei destinatari compresa); da creare: %s" % (", ".join(d for d, _s, _m in todo) or "(niente: gia' installato)"))
    if a.with_timer:
        out("OK", "cancello del timer soddisfatto: backup pubblicato %s, ripristino indipendente (%s) su %s" % (
            proof.get("archivio_pubblicato"), proof.get("origine"), proof.get("ripristino_eseguito_su")))
        if proof.get("controllo_rc84") != "eseguito" and p["family"] == "v3":
            out("INFO", "il ripristino indipendente NON includeva il confronto con il codice RC84: resta un gate separato")
    out("INFO", "IMPRONTA DI APPROVAZIONE: %s" % appr)
    if not todo and (not a.with_timer or timer_done):
        print("ESITO: GIA' INSTALLATO - nessuna modifica")
        return 0
    if not a.apply:
        print("ESITO: SIMULAZIONE RIUSCITA - nessuna modifica. Per applicare: --profile %s install --apply --approve %s%s"
              % (p["name"], appr, " --with-timer --restore-certificate <FILE>" if a.with_timer else ""))
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
        intended.append({"path": p["gate_file"], "sha256": "", "mode": 0o600})
    new_dirs = [d for d in p["dirs"] if not os.path.isdir(d)]
    record = {"creato": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stato": "in_corso", "file": previous + intended,
              "profilo": p["name"], "cartelle_create": new_dirs, "aside": p["aside"], "timer": bool(a.with_timer),
              "approvazione": appr}
    created, timer_touched = [], False
    old_term, old_int = signal.signal(signal.SIGTERM, _on_signal), signal.signal(signal.SIGINT, _on_signal)
    try:
        write_manifest(a, record)                                   # PRIMA di ogni modifica: l'interruzione resta recuperabile
        for d in new_dirs:
            os.makedirs(d, mode=0o700)
        for dest, src, mode in todo:
            if not atomic_put(src, dest, mode):
                raise OSError("verifica fallita su %s" % dest)
            created.append({"path": dest, "sha256": sha(dest), "mode": mode})
            out("OK", "creato %s" % dest)
        if a.with_timer:
            gate_body = json.dumps({"creato": record["creato"], "prova": proof}, sort_keys=True, indent=1) + "\n"
            tmpg = p["gate_file"] + ".tmp"
            with open(tmpg, "w") as f:
                f.write(gate_body)
            os.chmod(tmpg, 0o600)
            os.replace(tmpg, p["gate_file"])
            created.append({"path": p["gate_file"], "sha256": sha(p["gate_file"]), "mode": 0o600})
            for c in record["file"]:
                if c["path"] == p["gate_file"]:
                    c["sha256"] = sha(p["gate_file"])
            write_manifest(a, record)
            timer_touched = True
            for step in (("daemon-reload",), ("enable", p["timer"]), ("start", p["timer"])):
                rc, msg = systemctl(*step)
                if rc != 0:
                    raise OSError("systemctl %s: %s" % (" ".join(step), msg[-200:]))
            rc, timer_state = systemctl("is-active", p["timer"])
            rc2, enabled = systemctl("is-enabled", p["timer"])
            _rc, service_state = systemctl("is-active", p["service"])
            if timer_state != "active" or enabled != "enabled":
                raise OSError("il timer non risulta attivo e abilitato (%s / %s)" % (timer_state, enabled))
            if service_state in ("active", "activating"):
                raise OSError("il servizio di backup e' partito all'attivazione del timer (%s): non previsto" % service_state)
            out("OK", "timer %s attivo; il servizio NON e' partito (nessun avvio arretrato)" % p["name"])
        record["stato"] = "completo"
        write_manifest(a, record)
    except BaseException as e:                                       # errore di systemd, segnale, qualunque interruzione
        out("BLOCCO", "installazione interrotta: %s" % (e if isinstance(e, Exception) else "segnale %s" % getattr(e, "code", e)))
        undo(a, created, timer_touched)
        for d in reversed(new_dirs):
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
        if previous:
            record["file"], record["stato"] = previous, "completo"
            write_manifest(a, record)
        elif os.path.isfile(manifest_path(a)):
            os.unlink(manifest_path(a))
        print("ESITO: FALLITO - rimosso e disattivato quanto creato da questa esecuzione; "
              "il backup V1 di Falco/Toro non e' stato toccato")
        if isinstance(e, SystemExit):
            raise
        return 1
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)
    print("ESITO: INSTALLATO - solo i file V2 del profilo %s%s. Prossimo passo: %s. Rollback: install_brain_v3_extension.py --profile %s rollback --apply"
          % (p["name"], " con timer" if a.with_timer else " (nessun timer)",
             "controllare il primo giro notturno" if a.with_timer else "%s --preflight/--plan, poi il primo backup reale" % p["wrapper_name"],
             p["name"]))
    return 0


def do_rollback(a):
    p = prof(a)
    print("== Rollback V2, profilo %s (%s)" % (p["name"], "APPLICA" if a.apply else "SIMULAZIONE"))
    if os.getuid() != 0 and not a.allow_nonroot:
        out("BLOCCO", "va eseguito come root")
        return 1
    if not os.path.isfile(manifest_path(a)):
        out("BLOCCO", "nessun registro dell'installazione in %s: niente da annullare" % a.state_dir)
        return 1
    rec = jload(manifest_path(a))
    rc, state = systemctl("is-active", p["service"])
    if state in ("active", "activating"):
        out("BLOCCO", "il servizio %s e' in corso (%s): attendere la fine" % (p["name"], state))
        return 1
    if rec.get("stato") != "completo":
        out("INFO", "registro in stato '%s': installazione interrotta, si toglie quanto risulta presente e invariato" % rec.get("stato"))
    used_elsewhere = other_profile_files(a)
    leave = []
    for extra in orphan_shared(a, rec):
        rec["file"].append({"path": extra, "sha256": sha(extra), "mode": 0})
        out("INFO", "file comune non piu' usato da nessun profilo: %s" % extra)
    for c in rec["file"]:
        path = c["path"]
        if not os.path.lexists(path):
            out("INFO", "gia' assente: %s" % path)
        elif path in used_elsewhere:
            leave.append(path)
            out("INFO", "usato anche dall'altro profilo, lo lascio: %s" % path)
        elif c.get("sha256") and sha(path) != c["sha256"]:
            leave.append(path)
            out("INFO", "MODIFICATO dopo l'installazione, lo lascio: %s" % path)
        else:
            out("OK", "%s %s" % ("toglierei" if not a.apply else "tolgo", path))
    strays = stray_temp([c["path"] for c in rec["file"]])
    for s in strays:
        out("OK", "%s il temporaneo di un'installazione interrotta: %s" % ("toglierei" if not a.apply else "tolgo", s))
    if rec.get("timer"):
        out("OK", "%s il timer %s" % ("fermerei e toglierei" if not a.apply else "fermo e tolgo", p["name"]))
    aside = rec.get("aside") or rec.get("work_dir") or p["aside"]
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    if os.path.isdir(aside):
        out("OK", "%s %s in %s.removed-%s (nessuna cancellazione)" % ("sposterei" if not a.apply else "sposto", aside, aside, stamp))
    if not a.apply:
        print("ESITO: SIMULAZIONE RIUSCITA - nessuna modifica. Per applicare: rollback --apply")
        return 0
    if rec.get("timer"):
        disable_timer(p)
    for c in rec["file"]:
        if c["path"] not in leave and os.path.lexists(c["path"]):
            os.unlink(c["path"])
    for s in strays:
        os.unlink(s)
    if rec.get("timer"):
        systemctl("daemon-reload")
    if os.path.isdir(aside):
        os.rename(aside, "%s.removed-%s" % (aside, stamp))
    os.rename(manifest_path(a), os.path.join(a.state_dir, "%s.rolledback-%s.json" % (p["manifest"][:-len(".json")], stamp)))
    print("ESITO: RIPRISTINATO - rimossi solo i file V2 del profilo %s%s; il backup V1 di Falco/Toro non e' stato toccato"
          % (p["name"], "; file lasciati: %d" % len(leave) if leave else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("status", "install", "rollback"))
    ap.add_argument("--profile", choices=("v3", "classic"), default="v3")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--approve", default="")
    ap.add_argument("--with-timer", action="store_true")
    ap.add_argument("--restore-certificate", default="", help="certificato (file di restore_brain_v3_backup.py o righe CERTIFICATO del workflow)")
    ap.add_argument("--tools-dir", default="/opt/superbot-tools")
    ap.add_argument("--work-dir", default="/opt/superbot-extbackup-v3")
    ap.add_argument("--v2-dir", default="/opt/superbot-extbackup-v2")
    ap.add_argument("--classic-dir", default="/opt/superbot-extbackup", help="solo per il known_hosts di GitHub, in sola lettura")
    ap.add_argument("--systemd-dir", default="/etc/systemd/system")
    ap.add_argument("--state-dir", default="/root/extbackup-v3-install")
    ap.add_argument("--ssh-key", default="/root/.ssh/superbot_backup_v2_ed25519")
    ap.add_argument("--host-name", default="", help="solo per le prove automatiche")
    ap.add_argument("--allow-nonroot", action="store_true", help="solo per le prove automatiche")
    a = ap.parse_args(argv)
    return {"status": do_status, "install": do_install, "rollback": do_rollback}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
