#!/usr/bin/env python3
"""Backup ESTERNO cifrato di Brain V3 (e, a parte, del vecchio database Brain Free), AFFIANCATO a quello di Falco/Toro.

Non sostituisce e non modifica external_backup.py, backup_brain.py, restore_external_backup.py ne' run.sh: li riusa
(cifratura age, controlli del destinatario, stato) e se ne sta in una cartella di lavoro, un ramo git e una famiglia di
archivi TUTTI SEPARATI, cosi' un errore qui non puo' rompere il backup che gia' funziona (e viceversa).

  --mode v3          certifica e copia le cartelle  <runs-root>/brain-v3-*  (journal.db, budget.db, configurazione,
                     marcatore, mandato, pausa, stato giornaliero; heartbeat e richieste di chiusura come "transient");
  --mode brain-free  copia certificata del solo database storico Brain Free (brain.sqlite3), famiglia SEPARATA,
                     da pubblicare solo quando il suo contenuto cambia.

Sempre in SOLA LETTURA sulle sorgenti (vedi brain_v3_snapshot.py). Prima di far uscire dati dalla VPS: ogni verifica
passata, archivio .tar.gz con manifesto interno (SHA-256 di ogni file), cifratura age con la sola chiave PUBBLICA
(la privata di recupero non e' sul server). Nel repository dei backup (ramo dedicato: brain-v3 / brain-free) vanno
SOLO l'archivio cifrato e un manifesto minimo in chiaro. Dopo il push si riscarica da GitHub in una cartella nuova e si
ricalcola lo SHA-256. Il push non e' mai forzato; NIENTE viene cancellato (la rimozione dalla punta del ramo esiste solo
con --prune --confirm-prune, spenta di default).

Se lo stato non e' certificabile, o e' regredito rispetto all'ultimo backup riuscito (ancora: eventi e hash di testa del
journal, righe e hash del budget, run scomparse), NIENTE viene inviato: uscita 1 con il codice del rifiuto.
Se lo stato e' identico all'ultimo archivio pubblicato non si crea un archivio nuovo (INVARIATO, uscita 0).
Uscita 3: non c'e' niente da proteggere (cartella delle run assente o vuota e nessun backup precedente).

  --plan       prova locale completa (copia, verifiche, archivio, cifratura) SENZA rete e SENZA invio: stampa le dimensioni;
  --preflight  controlli sui SOLI METADATI (stat e prima pagina dei database: nessuna apertura SQLite, nessuna scrittura,
               nessun file creato; i processi che tengono aperti i file si leggono da /proc).

Esecuzione pianificata (SUPERBOT_V3_SCHEDULED=1, impostata dall'unita' systemd): rifiutata se manca il file
<work>/timer-gate.json, che l'installatore scrive solo dopo la prova di un backup reale e di un ripristino indipendente.
Segnali SIGTERM/SIGINT: si ripulisce il testo in chiaro prima di uscire; dopo un arresto brusco (SIGKILL) i residui
temporanei (cartella di lavoro 0700, file 0600) vengono rimossi al primo avvio successivo e dall'unita' (ExecStopPost).
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tarfile
import gzip
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
MIB = 1 << 20
FORMAT = 1
SCHEMA = "superbot-brain-v3-backup-v1"
INTERNAL_MANIFEST = "INTERNAL-MANIFEST.json"
FAMILIES = {
    "v3": {"prefix": "superbot-brainv3-", "dir": "brain-v3", "branch": "brain-v3", "label": "Brain V3"},
    "brain-free": {"prefix": "superbot-brainfree-", "dir": "brain-free", "branch": "brain-free",
                   "label": "Brain Free (storico)"},
}
LEGGIMI = """# Backup cifrati di SuperBot - %s

Questo ramo contiene SOLO archivi gia' cifrati con age (`*.tar.gz.age`, eventualmente spezzati in `*.partNNN`) e il loro
manifesto minimo (`*.manifest.json`: nome, SHA-256, dimensione, data, origine, destinatario, ancore di integrita').
Nessun dato in chiaro, nessun segreto. La chiave PRIVATA di recupero non e' qui: la custodisce l'utente.

Ripristino: `deploy/scripts/restore_brain_v3_backup.py` (ramo work/extbackup-brain-v3-*). Nessun archivio viene
cancellato automaticamente. Questa e' una copia ESTERNA aggiuntiva: i backup verificati sul VPS restano necessari.
"""


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def say(msg):
    print(msg, flush=True)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fam_name_re(fam):
    return re.compile(r"^%s(\d{8}T\d{6}Z)\.tar\.gz\.age$" % re.escape(FAMILIES[fam]["prefix"]))


# ---- archivio ---------------------------------------------------------------------------------------------------

def build_archive(stage, out_path, internal):
    """tar.gz deterministico: tutto lo staging sotto dati/ + manifesto interno con SHA-256 di ogni file."""
    files = []
    for dp, dn, fn in os.walk(stage):
        dn.sort()
        for f in sorted(fn):
            full = os.path.join(dp, f)
            if os.path.islink(full):
                raise RuntimeError("collegamento simbolico inatteso nello staging")
            rel = os.path.relpath(full, stage).replace(os.sep, "/")
            files.append({"file": "dati/" + rel, "size": os.path.getsize(full), "sha256": sha256_file(full),
                          "_full": full})
    internal = dict(internal)
    internal["file"] = [{k: v for k, v in x.items() if k != "_full"} for x in files]
    blob = json.dumps(internal, indent=1, sort_keys=True).encode()
    with open(out_path, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                for x in files:
                    ti = tar.gettarinfo(x["_full"], arcname=x["file"])
                    ti.uid = ti.gid = 0
                    ti.uname = ti.gname = "root"
                    ti.mode = 0o600
                    with open(x["_full"], "rb") as fh:
                        tar.addfile(ti, fh)
                ti = tarfile.TarInfo(INTERNAL_MANIFEST)
                ti.size = len(blob)
                ti.mtime = int(time.time())
                ti.mode = 0o600
                tar.addfile(ti, io.BytesIO(blob))
    os.chmod(out_path, 0o600)
    return internal


def split_file(path, part_bytes):
    parts = []
    with open(path, "rb") as src:
        n = 0
        while True:
            chunk = src.read(part_bytes)
            if not chunk:
                break
            n += 1
            p = "%s.part%03d" % (path, n)
            with open(p, "wb") as dst:
                dst.write(chunk)
            os.chmod(p, 0o600)
            parts.append(p)
    return parts


# ---- repository privato (un ramo per famiglia) -----------------------------------------------------------------

class BranchRepo:
    def __init__(self, a, classic, wd):
        self.a, self.c = a, classic
        self.dir = os.path.join(wd, "repo")
        self.branch = a.branch
        self.env = dict(os.environ)
        self.env["GIT_TERMINAL_PROMPT"] = "0"
        if a.ssh_key:
            self.env["GIT_SSH_COMMAND"] = (
                "ssh -i %s -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes "
                "-o UserKnownHostsFile=%s -o ConnectTimeout=30" % (a.ssh_key, a.known_hosts))

    def git(self, *args, check=True):
        p = subprocess.run(["git", "-C", self.dir] + list(args), env=self.env, capture_output=True, timeout=900)
        out = (p.stdout + p.stderr).decode(errors="replace").strip()
        if check and p.returncode != 0:
            raise self.c.Fail("git %s fallito: %s" % (args[0], out[-500:]))
        return p.returncode, p.stdout.decode(errors="replace").strip()

    def sync(self):
        """Allinea la copia locale (solo una cache) al ramo remoto; ramo assente = si parte da un ramo vuoto."""
        ls = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", self.a.remote,
                             "refs/heads/" + self.branch], env=self.env, capture_output=True, timeout=300)
        if ls.returncode not in (0, 2):
            raise self.c.Fail("repository dei backup non raggiungibile: %s"
                              % (ls.stdout + ls.stderr).decode(errors="replace").strip()[-300:])
        have = os.path.isdir(os.path.join(self.dir, ".git"))
        if ls.returncode == 2 or not have:
            shutil.rmtree(self.dir, ignore_errors=True)
            os.makedirs(self.dir, mode=0o700)
            self.git("init", "-q")
            self.git("remote", "add", "origin", self.a.remote)
        else:
            self.git("remote", "set-url", "origin", self.a.remote)
        self.git("config", "user.name", "SuperBot backup")
        self.git("config", "user.email", "backup@superbot.invalid")
        if ls.returncode == 0:
            self.git("fetch", "-q", "origin", "+refs/heads/%s:refs/remotes/origin/%s" % (self.branch, self.branch))
            self.git("checkout", "-q", "-f", "-B", self.branch, "origin/" + self.branch)
            self.git("reset", "-q", "--hard", "origin/" + self.branch)
            self.git("clean", "-q", "-fd")
            return True
        self.git("symbolic-ref", "HEAD", "refs/heads/" + self.branch)
        return False

    def publish(self, message):
        self.git("add", "-A")
        if not self.git("status", "--porcelain")[1]:
            return False
        self.git("commit", "-q", "-m", message)
        for attempt in (1, 2):
            rc, out = self.git("push", "-q", "origin", "HEAD:refs/heads/" + self.branch, check=False)
            if rc == 0:
                return True
            if attempt == 2:
                raise self.c.Fail("push rifiutato o non riuscito: %s" % out[-300:])
            time.sleep(self.a.push_wait)
        return True

    def verify_remote(self, expect):
        """Clone NUOVO e indipendente del solo ramo: stessa punta, ogni file atteso presente con lo SHA-256 giusto."""
        tmp = os.path.join(os.path.dirname(self.dir), "verifica-%d" % os.getpid())
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            p = subprocess.run(["git", "clone", "-q", "--no-local", "--depth", "1", "--single-branch", "--branch",
                                self.branch, self.a.remote, tmp], env=self.env, capture_output=True, timeout=1800)
            if p.returncode != 0:
                raise self.c.Fail("verifica: clone nuovo non riuscito: %s"
                                  % (p.stdout + p.stderr).decode(errors="replace").strip()[-300:])
            fresh = subprocess.run(["git", "-C", tmp, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
            if fresh != self.git("rev-parse", "HEAD")[1]:
                raise self.c.Fail("verifica: la punta scaricata non e' quella appena inviata")
            for rel, digest in expect:
                path = os.path.join(tmp, *rel.split("/"))
                if not os.path.isfile(path):
                    raise self.c.Fail("verifica: file assente nel clone nuovo: " + rel)
                if sha256_file(path) != digest:
                    raise self.c.Fail("il file riscaricato da GitHub ha uno SHA-256 diverso da quello inviato: " + rel)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def family_manifests(self, fam):
        base = os.path.join(self.dir, FAMILIES[fam]["dir"])
        rx = fam_name_re(fam)
        found = []
        for dp, _dn, fn in os.walk(base):
            for f in fn:
                if f.endswith(".manifest.json") and rx.match(f[: -len(".manifest.json")] + ".tar.gz.age"):
                    found.append(os.path.join(dp, f))
        return sorted(found, key=os.path.basename)

    def last_manifest(self, fam):
        found = self.family_manifests(fam)
        if not found:
            return None
        with open(found[-1]) as f:
            return json.load(f)

    def size_bytes(self):
        total = 0
        for dp, _dn, fn in os.walk(self.dir):
            for f in fn:
                try:
                    total += os.lstat(os.path.join(dp, f)).st_size
                except OSError:
                    pass
        return total


def manifest_name(name):
    return name[: -len(".tar.gz.age")] + ".manifest.json"


# ---- controlli di sola lettura ----------------------------------------------------------------------------------

def preflight(a, classic):
    """Solo metadati: nessuna apertura SQLite (un WAL rimasto dopo un arresto brusco verrebbe ricostruito da SQLite anche
    in sola lettura), nessuna scrittura, nessun file creato."""
    snap = load_module(os.path.join(a.tools, "brain_v3_snapshot.py"), "brain_v3_snapshot")
    ar = load_module(os.path.join(a.tools, "age_recipients.py"), "age_recipients")
    res = []

    def add(ok, msg):
        res.append((ok, msg))
        say(("OK     " if ok else "BLOCCO ") + msg)

    def info(msg):
        say("INFO   " + msg)

    def describe(label, path):
        d = snap.describe_source(path)
        state = d["stato"]
        bad = state in ("assente", "non_sicuro", "sqlite_not_a_database", "wal_collaterali_anomali", "collaterali_anomali")
        add(not bad, "%s: %s (%s MiB)%s" % (label, state, d.get("byte", 0) // MIB,
                                             " | cattura: " + d["cattura"] if "cattura" in d else ""))
        if d.get("collaterali"):
            info("%s: file collaterali %s" % (label, ", ".join("%s=%d byte" % kv for kv in sorted(d["collaterali"].items()))))
        if "processi" in d:
            if d["processi"]:
                info("%s: aperto da processi %s (scrittore o lettore ATTIVO)" % (label, d["processi"]))
            elif d["processi_verificati_tutti"]:
                info("%s: nessun processo lo tiene aperto" % label)
            else:
                info("%s: processi non tutti ispezionabili (servono permessi di root): stato attivo/residuo NON determinabile" % label)
        if state == "journal_presente":
            info("%s: file -journal non vuoto (scrittura in corso o residuo): se e' un residuo il backup si ferma con hot_journal" % label)
        return d, bad
    for tool in ("age", "git"):
        add(bool(shutil.which(tool)), "programma %s disponibile" % tool)
    try:
        keys = ar.read_recipients(a.recipient_file)
        add(True, "destinatari age (solo chiavi pubbliche): %d" % len(keys))
        if a.expect_recipients_sha256:
            ar.check_expected(keys, a.expect_recipients_sha256)
            add(True, "impronta dei destinatari uguale a quella approvata")
        else:
            add(False, "manca --expect-recipients-sha256 (impronta dei destinatari approvati)")
    except ar.RecipientError as e:
        add(False, str(e))
    if a.ssh_key:
        ok = os.path.isfile(a.ssh_key) and (os.stat(a.ssh_key).st_mode & 0o077) == 0
        add(ok, "chiave di deploy presente con permessi stretti")
        add(os.path.isfile(a.known_hosts or ""), "known_hosts presente")
    need = 0
    if a.mode == "v3":
        try:
            runs, ignored = snap.discover_runs(a.runs_root)
        except snap.Refused as e:
            add(False, "cartella delle run: %s" % e.code)
            runs, ignored = [], []
        add(os.path.isdir(a.runs_root), "cartella delle run %s (%d run, %d voci ignorate)" % (a.runs_root, len(runs), len(ignored)))
        for n in runs:
            d = os.path.join(a.runs_root, n)
            missing = [f for f in snap.DURABLE_REQUIRED if not os.path.isfile(os.path.join(d, f)) or os.path.islink(os.path.join(d, f))]
            add(not missing, "run %s: file irrinunciabili %s" % (n, "presenti" if not missing else "MANCANTI " + ",".join(missing)))
            for dbn in ("journal.db", "budget.db"):
                p = os.path.join(d, dbn)
                if os.path.isfile(p):
                    need += os.path.getsize(p) + (os.path.getsize(p + "-wal") if os.path.isfile(p + "-wal") else 0)
                    describe("run %s: %s" % (n, dbn), p)
            info("run %s: %s" % (n, "IN PAUSA" if os.path.exists(os.path.join(d, "pause.flag")) else "non in pausa"))
    else:
        p = a.legacy_db
        if os.path.isfile(p):
            need += os.path.getsize(p) * 2 + (os.path.getsize(p + "-wal") if os.path.isfile(p + "-wal") else 0)
        describe("database storico", p)
    probe = a.work
    while probe and not os.path.exists(probe):
        probe = os.path.dirname(probe)
    free = shutil.disk_usage(probe or "/").free
    add(free > need * 3 + 64 * MIB, "spazio libero %d MiB, stimato necessario %d MiB" % (free // MIB, (need * 3 + 64 * MIB) // MIB))
    add(os.path.basename(os.path.realpath(a.work).rstrip("/")) != "superbot-extbackup",
        "la cartella di lavoro non e' quella del backup di Falco/Toro")
    if a.remote and not a.no_network:
        r = subprocess.run(["git", "ls-remote", "--heads", a.remote], capture_output=True, timeout=120,
                           env=dict(os.environ, GIT_TERMINAL_PROMPT="0", **(
                               {"GIT_SSH_COMMAND": "ssh -i %s -o IdentitiesOnly=yes -o BatchMode=yes "
                                "-o StrictHostKeyChecking=yes -o UserKnownHostsFile=%s -o ConnectTimeout=30"
                                % (a.ssh_key, a.known_hosts)} if a.ssh_key else {})))
        add(r.returncode == 0, "repository dei backup raggiungibile (ls-remote, sola lettura)")
    bad = [m for ok, m in res if not ok]
    say("PREFLIGHT: %s" % ("BLOCCATO (%d)" % len(bad) if bad else "OK (solo metadati: nessuna apertura SQLite, nessuna scrittura)"))
    return 1 if bad else 0


# ---- esecuzione -------------------------------------------------------------------------------------------------

def tools_hashes(a):
    out = {}
    for n in ("brain_v3_snapshot.py", "external_backup_brain_v3.py", "restore_brain_v3_backup.py"):
        p = os.path.join(a.tools, n)
        out[n] = sha256_file(p) if os.path.isfile(p) else "assente"
    return out


def execute(a, classic, snap):
    fam = FAMILIES[a.mode]
    wd = os.path.join(a.work, a.mode)
    os.makedirs(wd, mode=0o700, exist_ok=True)
    ar = load_module(os.path.join(a.tools, "age_recipients.py"), "age_recipients")
    try:
        recipient = ar.load_checked(a.recipient_file, a.expect_recipients_sha256)
    except ar.RecipientError as e:
        raise classic.Fail(str(e))
    stage = os.path.join(wd, "staging")
    plain = os.path.join(wd, "staging.tar.gz")
    cipher = None
    parts = []
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage, mode=0o700)
    repo = None
    try:
        prev = None
        if not a.plan:
            repo = BranchRepo(a, classic, wd)
            repo.sync()
            prev = repo.last_manifest(a.mode)
        now_ms = int(time.time() * 1000)
        created = classic.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
        if a.mode == "v3":
            prev_anchors = (prev or {}).get("ancore") or {}
            facts, ignored = snap.build_runs_snapshot(a.runs_root, stage, now_ms, tuple(a.run), prev_anchors,
                                                      a.attempts, a.attempt_wait)
            legacy = None
            if not facts:
                say("RISULTATO: NIENTE DA PROTEGGERE  nessuna cartella brain-v3-* in %s. NESSUN BACKUP E' STATO ESEGUITO "
                    "e questo esito non certifica niente" % a.runs_root)
                classic.write_status(wd, ultimo_controllo=created, stato="nessuna_run")
                return 3
            body = {"runs": facts, "ignorati": ignored}
            anchors = dict(prev_anchors) if a.run else {}        # con --run le ancore delle altre run restano quelle precedenti
            anchors.update(snap.anchors_from_facts(facts))
            content = {"run": len(facts)}
        else:
            prev_legacy = (prev or {}).get("ancora_legacy")
            legacy = snap.capture_legacy(a.legacy_db, os.path.join(stage, "legacy"), a.attempts, a.attempt_wait,
                                         prev=prev_legacy)
            facts, body, anchors = [], {"legacy": legacy}, None
            content = {"database_storico": 1}
        fp = snap.state_fingerprint(facts, legacy)
        if prev and prev.get("impronta_stato") == fp and not a.force and not a.plan:
            say("RISULTATO: INVARIATO  stato identico all'ultimo archivio pubblicato (%s): nessun archivio nuovo"
                % prev.get("archivio"))
            classic.write_status(wd, ultima_verifica_ok=created, ultimo_errore=None, impronta_stato=fp,
                                 archivio_corrente=prev.get("archivio"))
            return 0
        created_dt = classic.now_utc()
        name = "%s%s.tar.gz.age" % (fam["prefix"], classic.stamp(created_dt))
        while repo is not None and any(os.path.basename(m) == manifest_name(name) for m in repo.family_manifests(a.mode)):
            time.sleep(1.0)                                  # mai due archivi con lo stesso nome: niente si sovrascrive
            created_dt = classic.now_utc()
            name = "%s%s.tar.gz.age" % (fam["prefix"], classic.stamp(created_dt))
        created = created_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        cipher = os.path.join(wd, name)
        internal = {"formato": FORMAT, "schema": SCHEMA, "famiglia": a.mode, "creato": created,
                    "origine": {"host": socket.gethostname()}, "impronta_stato": fp,
                    "codice": tools_hashes(a), "sorgente": {"runs_root": a.runs_root if a.mode == "v3" else None,
                                                            "database_storico": a.legacy_db if a.mode != "v3" else None}}
        internal.update(body)
        say("creo l'archivio e lo cifro con age ...")
        internal = build_archive(stage, plain, internal)
        try:
            ar.encrypt_to(plain, cipher, recipient.keys)
        except ar.RecipientError as e:
            raise classic.Fail(str(e))
        size, digest = os.path.getsize(cipher), sha256_file(cipher)
        if size > a.max_archive_mib * MIB:
            raise classic.Fail("archivio cifrato di %d MiB oltre il limite di %d MiB (--max-archive-mib): nessun invio"
                               % (size // MIB, a.max_archive_mib))
        public = {"formato": FORMAT, "famiglia": a.mode, "archivio": name, "sha256": digest, "dimensione": size,
                  "creato": created, "origine": internal["origine"], "impronta_stato": fp,
                  "cifratura": {"strumento": "age", "destinatario": recipient.keys[0], "destinatari": list(recipient.keys),
                                "impronta_destinatari": ar.fingerprint(recipient.keys)},
                  "contenuto": dict(content, file=len(internal["file"]))}
        if anchors is not None:
            public["ancore"] = anchors
        if legacy:
            public["ancora_legacy"] = {k: legacy[k] for k in ("eventi", "seq_max", "events_sha256", "state_sha256")}
        if size > a.max_file_mib * MIB:
            parts = split_file(cipher, a.max_file_mib * MIB)
            public["parti"] = [{"nome": os.path.basename(p), "dimensione": os.path.getsize(p),
                                "sha256": sha256_file(p)} for p in parts]
        if a.plan:
            say("PIANO (nessun invio, nessuna rete): archivio cifrato %s  %d byte (%.2f MiB)  sha256 %s  parti %d"
                % (name, size, size / MIB, digest, len(parts) or 1))
            say("RISULTATO: PIANO OK  file nell'archivio %d, impronta di stato %s" % (len(internal["file"]), fp))
            return 0
        rel_dir = "/".join((fam["dir"], created_dt.strftime("%Y"), created_dt.strftime("%m")))
        git_bytes = repo.size_bytes()
        if git_bytes + size > a.max_repo_mib * MIB:
            raise classic.Fail("repository dei backup: %d MiB + %d MiB oltre il limite di %d MiB (--max-repo-mib). "
                               "Serve una decisione sulla rotazione prima di continuare: nessun invio"
                               % (git_bytes // MIB, size // MIB, a.max_repo_mib))
        dest = os.path.join(repo.dir, *rel_dir.split("/"))
        os.makedirs(dest, exist_ok=True)
        expect = []
        if parts:
            for p in parts:
                shutil.copyfile(p, os.path.join(dest, os.path.basename(p)))
                expect.append((rel_dir + "/" + os.path.basename(p), sha256_file(p)))
        else:
            shutil.copyfile(cipher, os.path.join(dest, name))
            expect.append((rel_dir + "/" + name, digest))
        with open(os.path.join(dest, manifest_name(name)), "w") as f:
            json.dump(public, f, indent=1, sort_keys=True)
        expect.append((rel_dir + "/" + manifest_name(name), sha256_file(os.path.join(dest, manifest_name(name)))))
        with open(os.path.join(repo.dir, "recipient.txt"), "w") as f:
            f.write("# chiavi PUBBLICHE age dei backup (le private di recupero non sono in questo repository)\n%s\n"
                    % "\n".join(recipient.keys))
        with open(os.path.join(repo.dir, "LEGGIMI.md"), "w") as f:
            f.write(LEGGIMI % fam["label"])
        removed = prune(a, classic, repo, fam) if (a.prune and a.confirm_prune) else []
        repo.publish("backup cifrato %s%s" % (name, (" (tolti dalla punta %d vecchi)" % len(removed)) if removed else ""))
        repo.verify_remote(expect)
        classic.write_status(wd, ultimo_successo=created, ultima_verifica_ok=created, archivio=name, sha256=digest,
                             dimensione=size, ultimo_errore=None, impronta_stato=fp, archivio_corrente=name,
                             repo_byte=git_bytes + size, famiglia=a.mode,
                             run=[f["run_name"] for f in facts], verifica="clone nuovo e indipendente da GitHub")
        say("RISULTATO: OK  archivio %s  %d byte  sha256 %s  parti %d" % (name, size, digest, len(parts) or 1))
        if removed:
            say("  tolti dalla punta del ramo (retention esplicita): %s" % ", ".join(removed))
        return 0
    finally:
        for p in [plain, cipher] + parts:
            try:
                if p:
                    os.unlink(p)
            except FileNotFoundError:
                pass
        shutil.rmtree(stage, ignore_errors=True)


def prune(a, classic, repo, fam):
    removed = []
    base = os.path.join(repo.dir, fam["dir"])
    rx = fam_name_re(a.mode)
    entries = []
    for dp, _dn, fn in os.walk(base):
        for f in fn:
            m = rx.match(f)
            if m:
                entries.append((os.path.relpath(os.path.join(dp, f), repo.dir), classic.parse_stamp(m.group(1))))
    names = {os.path.basename(rel): rel for rel, _ in entries}
    for name in classic.plan_retention([(os.path.basename(r), dt) for r, dt in entries],
                                       a.keep_recent, a.keep_weeks, a.keep_months):
        rel = names[name]
        stem = os.path.join(os.path.dirname(rel), name)
        for fn in sorted(os.listdir(os.path.join(repo.dir, os.path.dirname(rel)))):
            full = os.path.join(os.path.dirname(rel), fn)
            if full == stem or full.startswith(stem + ".part") or fn == manifest_name(name):
                repo.git("rm", "-q", "--", full)
        removed.append(name)
    return sorted(removed)


def sweep_stale(wd):
    """Dopo un arresto brusco restano solo file temporanei NOSTRI nella cartella di lavoro (0700): li toglie."""
    gone = []
    for n in sorted(os.listdir(wd)):
        full = os.path.join(wd, n)
        if n in ("staging", "scratch") or n.startswith("verifica-"):
            shutil.rmtree(full, ignore_errors=True)
            gone.append(n)
        elif n == "staging.tar.gz" or re.match(r"^superbot-(brainv3|brainfree)-\d{8}T\d{6}Z\.tar\.gz\.age(\.part\d{3})?$", n):
            os.unlink(full)
            gone.append(n)
    return gone


def _on_signal(signum, _frame):
    raise SystemExit(128 + signum)


def main(argv=None):
    os.umask(0o077)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", required=True, choices=sorted(FAMILIES))
    ap.add_argument("--runs-root", default="/opt/superbot-v3-paper-runs")
    ap.add_argument("--run", action="append", default=[], help="solo queste run (nome cartella); default: tutte")
    ap.add_argument("--legacy-db", default="/opt/superbot-brain-free/brain.sqlite3")
    ap.add_argument("--work", required=True, help="cartella di lavoro PROPRIA (mai quella del backup di Falco/Toro)")
    ap.add_argument("--remote", default="", help="repository dei backup (SSH o percorso)")
    ap.add_argument("--branch", default="")
    ap.add_argument("--recipient-file", required=True, help="file con una o piu' chiavi PUBBLICHE age")
    ap.add_argument("--expect-recipients-sha256", default="",
                    help="impronta dei destinatari approvati (obbligatoria per l'invio): se il file e' diverso, rifiuto")
    ap.add_argument("--ssh-key", default="")
    ap.add_argument("--known-hosts", default="")
    ap.add_argument("--tools", default=HERE, help="cartella con external_backup.py e brain_v3_snapshot.py")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--attempt-wait", type=float, default=2.0)
    ap.add_argument("--max-file-mib", type=int, default=45, help="oltre questa dimensione l'archivio si spezza in parti")
    ap.add_argument("--max-archive-mib", type=int, default=400)
    ap.add_argument("--max-repo-mib", type=int, default=1500)
    ap.add_argument("--force", action="store_true", help="pubblica anche se lo stato e' identico")
    ap.add_argument("--plan", action="store_true", help="prova locale completa, senza rete e senza invio")
    ap.add_argument("--preflight", action="store_true", help="controlli di sola lettura")
    ap.add_argument("--no-network", action="store_true")
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--confirm-prune", action="store_true")
    ap.add_argument("--keep-recent", type=int, default=14)
    ap.add_argument("--keep-weeks", type=int, default=8)
    ap.add_argument("--keep-months", type=int, default=6)
    ap.add_argument("--push-wait", type=float, default=5.0, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    a.branch = a.branch or FAMILIES[a.mode]["branch"]
    if not (a.plan or a.preflight) and not a.remote:
        print("ERRORE: serve --remote (oppure --plan / --preflight)")
        return 1
    if not a.preflight and not a.expect_recipients_sha256:
        print("ERRORE: serve --expect-recipients-sha256 (impronta dei destinatari approvati): senza, un file di destinatari "
              "sostituito produrrebbe archivi che nessuno sa piu' aprire")
        return 1
    if a.ssh_key and not a.known_hosts:
        print("ERRORE: con --ssh-key serve anche --known-hosts (la chiave di GitHub va verificata)")
        return 1
    if a.prune and not a.confirm_prune:
        print("ERRORE: --prune richiede anche --confirm-prune (nessuna rimozione senza conferma esplicita)")
        return 1
    if os.path.basename(os.path.realpath(a.work).rstrip("/")) == "superbot-extbackup":
        print("ERRORE: --work non puo' essere la cartella del backup di Falco/Toro")
        return 1
    classic = load_module(os.path.join(a.tools, "external_backup.py"), "external_backup")
    snap = load_module(os.path.join(a.tools, "brain_v3_snapshot.py"), "brain_v3_snapshot")
    if a.preflight:
        return preflight(a, classic)
    wd = os.path.join(a.work, a.mode)
    if os.environ.get("SUPERBOT_V3_SCHEDULED") == "1" and a.mode == "v3" and not a.plan:
        if not os.path.isfile(os.path.join(a.work, "timer-gate.json")):
            print("RIFIUTATO (timer_gate_missing): esecuzione pianificata senza la prova di un backup reale e di un "
                  "ripristino indipendente (timer-gate.json). Niente e' stato fatto.")
            return 1
    os.makedirs(wd, mode=0o700, exist_ok=True)
    os.chmod(a.work, 0o700)
    try:
        lock = classic.take_lock(wd)
    except classic.Fail as e:
        print("ERRORE BACKUP BRAIN V3: %s" % e)
        return 1
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    snap.SCRATCH_ROOT = os.path.join(wd, "scratch")
    try:
        gone = sweep_stale(wd)
        if gone:
            say("ripulito il residuo temporaneo di un'esecuzione interrotta: %s" % ", ".join(gone))
        if not a.plan:
            classic.write_status(wd, ultimo_tentativo=classic.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"))
        return execute(a, classic, snap)
    except snap.Refused as e:
        msg = str(e)[:700]
        print("RIFIUTATO (%s): %s" % (e.code, msg))
        print("RISULTATO: FALLITO. Nessun archivio e' stato considerato inviato; nessun dato ne' archivio e' stato cancellato.")
        if not a.plan:
            classic.write_status(wd, ultimo_errore=msg, codice_rifiuto=e.code)
        return 1
    except (classic.Fail, OSError, subprocess.SubprocessError, tarfile.TarError, sqlite3.Error) as e:
        msg = str(e)[:700]
        print("ERRORE BACKUP BRAIN V3: %s" % msg)
        print("RISULTATO: FALLITO. Nessun archivio e' stato considerato inviato; nessun dato ne' archivio e' stato cancellato.")
        if not a.plan:
            classic.write_status(wd, ultimo_errore=msg)
        return 1
    except SystemExit as e:
        print("RISULTATO: INTERROTTO da un segnale. Nessun archivio e' stato considerato inviato; testo in chiaro rimosso.")
        if not a.plan:
            classic.write_status(wd, ultimo_errore="interrotto da un segnale (%s)" % e.code)
        raise
    finally:
        try:
            os.rmdir(snap.SCRATCH_ROOT)                       # cartella di lavoro dei WAL: se e' vuota non resta
        except OSError:
            pass
        os.close(lock)


if __name__ == "__main__":
    sys.exit(main())
