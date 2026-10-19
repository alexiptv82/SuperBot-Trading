#!/usr/bin/env python3
"""Backup ESTERNO cifrato di SuperBot, verso un repository GitHub PRIVATO separato.

Che cosa fa (tutto sul VPS, in sola lettura sui dati veri):
  1. produce copie FRESCHE E VERIFICATE con gli stessi strumenti dei deploy:
       - database dell'app e database del pool (API di backup di SQLite, schema, prova di ripristino);
       - cervello di Hawk e Bull (backup_brain.py nel percorso normale: file irrinunciabili presenti, JSONL
         completi, confine di ciclo VERIFICATO). Se il backup del cervello non riesce, NIENTE parte;
  2. le impacchetta in un archivio .tar.gz con un manifesto interno (SHA-256 di ogni file);
  3. le CIFRA con age (chiave pubblica, cifratura autenticata): sul server c'e' solo la chiave PUBBLICA;
     la chiave privata di recupero sta fuori da GitHub e fuori dal server. Il testo in chiaro viene
     cancellato subito dopo la cifratura;
  4. mette nel repository privato SOLO l'archivio cifrato e un manifesto minimo in chiaro (nome, SHA-256
     dell'archivio cifrato, dimensione, data, origine, versioni del codice, destinatario). Nessun database,
     nessuna memoria dei bot, nessun .env, token o chiave privata viaggia in chiaro;
  5. verifica l'invio: riscarica da GitHub il file appena inviato e ne ricalcola lo SHA-256;
  6. applica la retention (ultimi 14 + uno per settimana per 8 settimane + uno per mese per 6 mesi) togliendo
     i file piu' vecchi dalla punta del ramo (la storia git conserva comunque i blob cifrati);
  7. scrive lo stato in <work>/status.json (ultimo successo, ultimo errore). Mai segreti.

Credenziale di invio: una chiave di deploy SSH con accesso al SOLO repository dei backup (sta sul VPS).
Il push non e' mai forzato. Esce con 1 se qualcosa non torna.

Il ripristino si fa con restore_external_backup.py (serve la chiave privata di recupero).
"""
import argparse
import fcntl
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timedelta, timezone

FORMAT = 1
NAME_RE = re.compile(r"^superbot-backup-(\d{8}T\d{6}Z)\.tar\.gz\.age$")
KEY_RE = re.compile(r"^age1[0-9a-z]{58}$")
AGE_MAGIC = b"age-encryption.org/v1"
INTERNAL_MANIFEST = "INTERNAL-MANIFEST.json"
HERE = os.path.dirname(os.path.abspath(__file__))

LEGGIMI = """# Backup cifrati di SuperBot Trading

Questo repository contiene SOLO archivi gia' cifrati con age (`*.tar.gz.age`) e il loro manifesto
minimo (`*.manifest.json`: nome, SHA-256 dell'archivio cifrato, dimensione, data, origine, versioni del
codice, destinatario). Nessun dato in chiaro, nessun segreto.

- Cifratura: age, chiave pubblica del destinatario (vedi `recipient.txt`). La chiave PRIVATA di recupero
  non e' qui: la custodisce l'utente fuori da GitHub.
- Retention: ultimi 14 archivi + il piu' recente di ogni settimana per 8 settimane + il piu' recente di
  ogni mese per 6 mesi. I file piu' vecchi escono dalla punta del ramo; la storia git li conserva ancora.
- Ripristino: `deploy/scripts/restore_external_backup.py` (repository SuperBot, ramo rule-pool).
- Questo e' una copia ESTERNA aggiuntiva: i backup verificati sul VPS restano necessari.
"""


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def now_utc():
    return datetime.now(timezone.utc)


def stamp(dt):
    return dt.strftime("%Y%m%dT%H%M%SZ")


def parse_stamp(s):
    return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def say(msg):
    print(msg, flush=True)


class Fail(Exception):
    pass


def run(cmd, cwd=None, env=None, timeout=3600, check=True):
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise Fail("comando fallito (%s): %s" % (" ".join(cmd[:3]), (p.stdout + p.stderr).strip()[-600:]))
    return p


# ---- destinatario ------------------------------------------------------------

def read_recipient(path):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if not KEY_RE.match(line):
                        raise Fail("il destinatario in %s non e' una chiave pubblica age valida" % path)
                    return line
    except OSError as e:
        raise Fail("destinatario illeggibile: %s" % e)
    raise Fail("nessuna chiave pubblica age in %s" % path)


# ---- retention ---------------------------------------------------------------

def plan_retention(entries, keep_recent=14, keep_weeks=8, keep_months=6):
    """entries: elenco di (nome, datetime). Restituisce l'insieme dei nomi DA TOGLIERE.
    Si tengono: i `keep_recent` piu' recenti; il piu' recente di ognuna delle ultime `keep_weeks` settimane
    (ISO) che hanno archivi; il piu' recente di ognuno degli ultimi `keep_months` mesi che hanno archivi."""
    ordered = sorted(entries, key=lambda e: e[1], reverse=True)
    keep = {n for n, _ in ordered[:keep_recent]}
    weeks, months = {}, {}
    for n, dt in ordered:                      # dal piu' recente: il primo di ogni gruppo e' il piu' recente
        iso = dt.isocalendar()
        weeks.setdefault((iso[0], iso[1]), n)
        months.setdefault((dt.year, dt.month), n)
    for key in sorted(weeks, reverse=True)[:keep_weeks]:
        keep.add(weeks[key])
    for key in sorted(months, reverse=True)[:keep_months]:
        keep.add(months[key])
    return {n for n, _ in ordered} - keep


def manifest_name(archive_name):
    return archive_name[: -len(".tar.gz.age")] + ".manifest.json"


def archives_in(repo):
    out = []
    base = os.path.join(repo, "archives")
    for dp, _dn, fn in os.walk(base):
        for f in fn:
            m = NAME_RE.match(f)
            if m:
                out.append((os.path.join(dp, f), parse_stamp(m.group(1))))
    return out


# ---- copie fresche e verificate -------------------------------------------------

def make_staging(a, stage):
    py = [sys.executable, "-I"]
    dbs = os.path.join(stage, "database")
    os.makedirs(dbs, mode=0o700)
    for label, src in (("app", a.app_db), ("pool", a.pool_db)):
        say("copia verificata del database %s ..." % label)
        p = run(py + [os.path.join(a.tools, "backup_app_db.py"), "--src", src, "--dir", dbs,
                      "--prefix", label, "--keep", "5"], check=False)
        say("  " + (p.stdout.strip().splitlines() or ["(nessun output)"])[0])
        if p.returncode != 0:
            raise Fail("backup del database %s non riuscito: %s" % (label, (p.stdout + p.stderr).strip()[-400:]))
    brain = os.path.join(stage, "cervello")
    os.makedirs(brain, mode=0o700)
    last = ""
    for attempt in range(1, a.brain_retries + 2):
        say("copia verificata del cervello (tentativo %d) ..." % attempt)
        cmd = py + [os.path.join(a.tools, "backup_brain.py"), "--root", a.root, "--dir", brain, "--keep", "5",
                    "--tag", "ext"] + a.brain_args
        p = run(cmd, check=False)
        last = (p.stdout + p.stderr).strip()
        if p.returncode == 0:
            break
        lines = last.splitlines()
        say("  non riuscita: " + (lines[-2][:200] if len(lines) > 1 else "(nessun dettaglio)"))
        if attempt <= a.brain_retries:
            time.sleep(a.brain_retry_wait)
    else:
        raise Fail("backup del cervello non riuscito (nessuna finestra di fine ciclo verificata o file mancanti): "
                   + last[-400:])
    # lasciamo nell'archivio solo il contenuto: la copia del cervello e' una cartella bots-*
    return stage


def clean_stage_locks(stage):
    for dp, _dn, fn in os.walk(stage):
        for f in fn:
            if f == ".backup.lock":
                os.unlink(os.path.join(dp, f))


# ---- archivio ------------------------------------------------------------------

def code_versions(a):
    """Versioni: commit delle cartelle git sul server, MA ANCHE quello che gira davvero (le cartelle possono
    differire dai container): immagine di ogni container e versione dichiarata dai bot nel loro battito."""
    out = {}
    for label, path in (("codice_app", a.app_repo), ("codice_bot", a.bots_repo)):
        try:
            p = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30)
            sha = p.stdout.strip()
            out[label] = sha if p.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", sha) else "sconosciuto"
        except (OSError, subprocess.SubprocessError):
            out[label] = "sconosciuto"
    images = {}
    for name in [c for c in a.containers.split(",") if c]:
        try:
            p = subprocess.run([a.docker_bin, "inspect", "-f", "{{.Image}}|{{.Config.Image}}|{{.State.Running}}", name],
                               capture_output=True, text=True, timeout=30)
            parts = p.stdout.strip().split("|")
            if p.returncode == 0 and len(parts) == 3:
                images[name] = {"id_immagine": parts[0], "nome_immagine": parts[1], "in_esecuzione": parts[2] == "true"}
            else:
                images[name] = "sconosciuto"
        except (OSError, subprocess.SubprocessError):
            images[name] = "sconosciuto"
    out["immagini_in_esecuzione"] = images
    declared = {}
    for pf in ("hawk", "bull"):
        try:
            with open(os.path.join(a.root, pf, "heartbeat.json")) as f:
                hb = json.load(f)
            declared[pf] = {"versione": hb.get("version", "sconosciuta"), "avviato_ms": hb.get("started_ms")}
        except (OSError, ValueError, AttributeError):
            declared[pf] = "sconosciuta"
    out["versione_dichiarata_dai_bot"] = declared
    return out


def build_archive(stage, out_path, created, a):
    """Crea out_path (.tar.gz) con tutto lo staging sotto dati/ e un manifesto interno con gli hash."""
    files = []
    for dp, dn, fn in os.walk(stage):
        dn.sort()
        for f in sorted(fn):
            full = os.path.join(dp, f)
            if os.path.islink(full):
                raise Fail("collegamento simbolico inatteso nello staging: %s" % full)
            rel = os.path.relpath(full, stage)
            files.append({"file": "dati/" + rel.replace(os.sep, "/"), "size": os.path.getsize(full),
                          "sha256": sha256_file(full), "_full": full})
    meta = {"formato": FORMAT, "creato": created, "origine": {"host": socket.gethostname()},
            "versioni": code_versions(a), "file": [{k: v for k, v in x.items() if k != "_full"} for x in files]}
    manifest_bytes = json.dumps(meta, indent=1, sort_keys=True).encode()
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
                ti.size = len(manifest_bytes)
                ti.mtime = int(time.time())
                ti.mode = 0o600
                tar.addfile(ti, io.BytesIO(manifest_bytes))
    os.chmod(out_path, 0o600)
    return meta


def encrypt(plain, out_path, recipient):
    run(["age", "-r", recipient, "-o", out_path, plain])
    os.chmod(out_path, 0o600)
    with open(out_path, "rb") as f:
        head = f.read(len(AGE_MAGIC))
    if head != AGE_MAGIC or os.path.getsize(out_path) < 200:
        raise Fail("il file cifrato non ha il formato age atteso")


# ---- repository privato -----------------------------------------------------------

class Repo:
    def __init__(self, a):
        self.a = a
        self.dir = os.path.join(a.work, "repo")
        self.env = dict(os.environ)
        self.env["GIT_TERMINAL_PROMPT"] = "0"
        if a.ssh_key:
            self.env["GIT_SSH_COMMAND"] = (
                "ssh -i %s -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes "
                "-o UserKnownHostsFile=%s -o ConnectTimeout=30" % (a.ssh_key, a.known_hosts))

    def git(self, *args, check=True, binary=False):
        p = subprocess.run(["git", "-C", self.dir] + list(args), env=self.env, capture_output=True, timeout=600)
        if check and p.returncode != 0:
            raise Fail("git %s fallito: %s" % (args[0], (p.stdout + p.stderr).decode(errors="replace").strip()[-500:]))
        return p if binary else p.stdout.decode(errors="replace").strip()

    def sync(self):
        if not os.path.isdir(os.path.join(self.dir, ".git")):
            os.makedirs(os.path.dirname(self.dir), exist_ok=True)
            run(["git", "clone", "-q", self.a.remote, self.dir], env=self.env)
        self.git("config", "user.name", "SuperBot backup")
        self.git("config", "user.email", "backup@superbot.invalid")
        self.git("fetch", "-q", "origin")
        remote_main = self.git("rev-parse", "--verify", "-q", "refs/remotes/origin/main", check=False)
        if remote_main:
            self.git("checkout", "-q", "-B", "main", "origin/main")
            self.git("reset", "-q", "--hard", "origin/main")
            self.git("clean", "-q", "-fd")
        else:                                        # repository ancora vuoto
            self.git("checkout", "-q", "-B", "main")

    def publish(self, message):
        self.git("add", "-A")
        if not self.git("status", "--porcelain"):
            return False
        self.git("commit", "-q", "-m", message)
        for attempt in (1, 2):
            p = self.git("push", "-q", "origin", "main", check=False, binary=True)
            if p.returncode == 0:
                return True
            if attempt == 2:
                raise Fail("push rifiutato: %s" % (p.stdout + p.stderr).decode(errors="replace").strip()[-400:])
            self.git("fetch", "-q", "origin")
            self.git("rebase", "-q", "origin/main")       # nessun push forzato: ci si rimette in fila
        return True

    def verify_remote(self, relpath, expect_sha):
        """Verifica INDIPENDENTE: un clone nuovo da GitHub in una cartella vuota (nessun oggetto gia' presente
        in locale puo' essere riusato), stessa punta del push, file presente e SHA-256 ricalcolato."""
        tmp = os.path.join(self.a.work, "verifica-%d" % os.getpid())
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            p = subprocess.run(["git", "clone", "-q", "--no-local", "--depth", "1", "--branch", "main",
                                self.a.remote, tmp], env=self.env, capture_output=True, timeout=600)
            if p.returncode != 0:
                raise Fail("verifica: clone nuovo da GitHub non riuscito: %s"
                           % (p.stdout + p.stderr).decode(errors="replace").strip()[-300:])
            fresh = subprocess.run(["git", "-C", tmp, "rev-parse", "HEAD"], capture_output=True, text=True,
                                   timeout=60).stdout.strip()
            head = self.git("rev-parse", "HEAD")
            if fresh != head:
                raise Fail("verifica: la punta scaricata (%s) non e' quella appena inviata (%s)" % (fresh[:10], head[:10]))
            path = os.path.join(tmp, *relpath.split("/"))
            if not os.path.isfile(path):
                raise Fail("verifica: l'archivio non c'e' nel clone nuovo")
            if sha256_file(path) != expect_sha:
                raise Fail("il file riscaricato da GitHub ha uno SHA-256 diverso da quello inviato")
            mpath = os.path.join(os.path.dirname(path), manifest_name(os.path.basename(path)))
            if not os.path.isfile(mpath):
                raise Fail("verifica: manca il manifesto accanto all'archivio nel clone nuovo")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return True


def repo_size(repo_dir):
    """(byte occupati da .git, numero di archivi visibili): la retention limita i file visibili, NON lo spazio
    ne' la durata della storia git (che conserva anche gli archivi tolti). Va misurata nel tempo."""
    total = 0
    for dp, _dn, fn in os.walk(os.path.join(repo_dir, ".git")):
        for f in fn:
            try:
                total += os.lstat(os.path.join(dp, f)).st_size
            except OSError:
                pass
    return total, len(archives_in(repo_dir))


def prune(repo, keep_recent, keep_weeks, keep_months):
    removed = []
    entries = [(os.path.relpath(p, repo.dir), dt) for p, dt in archives_in(repo.dir)]
    names = {os.path.basename(rel): rel for rel, _ in entries}
    for name in plan_retention([(os.path.basename(rel), dt) for rel, dt in entries],
                               keep_recent, keep_weeks, keep_months):
        rel = names[name]
        for target in (rel, os.path.join(os.path.dirname(rel), manifest_name(name))):
            if os.path.exists(os.path.join(repo.dir, target)):
                repo.git("rm", "-q", "--", target)
        removed.append(name)
    return sorted(removed)


# ---- principale -----------------------------------------------------------------

def take_lock(work):
    fd = os.open(os.path.join(work, ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise Fail("un altro backup esterno e' gia' in corso")
    return fd


def write_status(work, **fields):
    path = os.path.join(work, "status.json")
    cur = {}
    try:
        with open(path) as f:
            cur = json.load(f)
    except (OSError, ValueError):
        pass
    cur.update(fields)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cur, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def execute(a):
    recipient = read_recipient(a.recipient_file)
    created_dt = now_utc()
    created = created_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    name = "superbot-backup-%s.tar.gz.age" % stamp(created_dt)
    stage = os.path.join(a.work, "staging")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage, mode=0o700)
    plain = os.path.join(a.work, "staging.tar.gz")
    cipher = os.path.join(a.work, name)
    try:
        make_staging(a, stage)
        clean_stage_locks(stage)
        say("creo l'archivio e lo cifro con age ...")
        meta = build_archive(stage, plain, created, a)
        encrypt(plain, cipher, recipient)
    finally:
        # il testo in chiaro non resta sul disco piu' del necessario
        for p in (plain,):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass
        shutil.rmtree(stage, ignore_errors=True)
    try:
        digest, size = sha256_file(cipher), os.path.getsize(cipher)
        rel_dir = os.path.join("archives", created_dt.strftime("%Y"), created_dt.strftime("%m"))
        repo = Repo(a)
        repo.sync()
        os.makedirs(os.path.join(repo.dir, rel_dir), exist_ok=True)
        shutil.copyfile(cipher, os.path.join(repo.dir, rel_dir, name))
        public = {"formato": FORMAT, "archivio": name, "sha256": digest, "dimensione": size, "creato": created,
                  "origine": meta["origine"], "versioni": meta["versioni"],
                  "cifratura": {"strumento": "age", "destinatario": recipient},
                  "contenuto": {"file": len(meta["file"])}}
        with open(os.path.join(repo.dir, rel_dir, manifest_name(name)), "w") as f:
            json.dump(public, f, indent=1, sort_keys=True)
        with open(os.path.join(repo.dir, "recipient.txt"), "w") as f:
            f.write("# chiave PUBBLICA age dei backup (la privata di recupero non e' in questo repository)\n%s\n" % recipient)
        with open(os.path.join(repo.dir, "LEGGIMI.md"), "w") as f:
            f.write(LEGGIMI)
        removed = prune(repo, a.keep_recent, a.keep_weeks, a.keep_months)
        repo.publish("backup cifrato %s%s" % (name, (" (tolti %d vecchi)" % len(removed)) if removed else ""))
        repo.verify_remote((rel_dir + "/" + name).replace(os.sep, "/"), digest)
        git_bytes, n_archives = repo_size(repo.dir)
    finally:
        try:
            os.unlink(cipher)
        except FileNotFoundError:
            pass
    say("RISULTATO: OK  archivio %s  %d byte  sha256 %s" % (name, size, digest))
    if removed:
        say("  tolti dalla punta del ramo per la retention: %s" % ", ".join(removed))
    say("  repository dei backup: %d archivi visibili, storia git %.1f MB (la retention non riduce la storia)"
        % (n_archives, git_bytes / 1e6))
    write_status(a.work, ultimo_successo=created, archivio=name, sha256=digest, dimensione=size,
                 ultimo_errore=None, repo_git_byte=git_bytes, archivi_visibili=n_archives,
                 verifica="clone nuovo e indipendente da GitHub")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="cartella che contiene hawk/ e bull/")
    ap.add_argument("--app-db", required=True)
    ap.add_argument("--pool-db", required=True)
    ap.add_argument("--tools", default=HERE, help="cartella con backup_app_db.py e backup_brain.py")
    ap.add_argument("--work", required=True, help="cartella di lavoro (clone, stato)")
    ap.add_argument("--remote", required=True, help="repository dei backup (SSH o percorso)")
    ap.add_argument("--recipient-file", required=True)
    ap.add_argument("--ssh-key", default="", help="chiave di deploy (solo per remote SSH)")
    ap.add_argument("--known-hosts", default="", help="known_hosts con la chiave di GitHub (solo per remote SSH)")
    ap.add_argument("--app-repo", default="/opt/superbot")
    ap.add_argument("--bots-repo", default="/opt/superbot-desk")
    ap.add_argument("--docker-bin", default="docker")
    ap.add_argument("--containers", default="superbot,superbot-desk-hawk,superbot-desk-bull,superbot-pool",
                    help="container di cui registrare l'immagine in esecuzione")
    ap.add_argument("--keep-recent", type=int, default=14)
    ap.add_argument("--keep-weeks", type=int, default=8)
    ap.add_argument("--keep-months", type=int, default=6)
    ap.add_argument("--brain-retries", type=int, default=2, help="nuovi tentativi se manca la finestra di fine ciclo")
    ap.add_argument("--brain-retry-wait", type=float, default=300.0)
    ap.add_argument("--brain-arg", action="append", default=[], dest="brain_args",
                    help="argomento in piu' per backup_brain.py (solo per le prove)")
    a = ap.parse_args(argv)
    if a.ssh_key and not a.known_hosts:
        print("ERRORE: con --ssh-key serve anche --known-hosts (la chiave di GitHub va verificata)")
        return 1
    os.makedirs(a.work, mode=0o700, exist_ok=True)
    os.chmod(a.work, 0o700)
    try:
        lock = take_lock(a.work)
    except Fail as e:
        print("ERRORE BACKUP ESTERNO: %s" % e)
        return 1
    try:
        write_status(a.work, ultimo_tentativo=now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"))
        return execute(a)
    except (Fail, OSError, subprocess.SubprocessError, tarfile.TarError) as e:
        msg = str(e)[:700]
        print("ERRORE BACKUP ESTERNO: %s" % msg)
        print("RISULTATO: FALLITO. Nessun archivio e' stato considerato inviato.")
        write_status(a.work, ultimo_errore=msg)
        return 1
    finally:
        os.close(lock)


if __name__ == "__main__":
    sys.exit(main())
