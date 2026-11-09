#!/usr/bin/env python3
"""Prove OFFLINE della correzione del backup esterno con i bot fermi (deploy/extbackup/run.sh).

Nessun server, nessun segreto, nessuna rete: docker, systemctl e journalctl sono FINTI (cartelle temporanee),
chiavi age e repository "remoto" sono creati al volo. Servono `age`, `age-keygen` e `git`; se mancano le prove
che li usano si SALTANO e lo dicono.

Che cosa dimostrano:
  - run.sh nel repository e' identico al testo dentro il workflow di installazione (nessuna deriva);
  - run.sh sceglie --bot-stopped SOLO se docker dimostra che hawk e bull sono entrambi fermi; in ogni altro caso
    (uno attivo, uno assente, docker rotto o assente) sceglie il percorso normale;
  - con i bot fermi il backup riesce, l'archivio si ripristina, il manifesto interno coincide con i file e dice
    "bot_fermo"; i file del cervello originali restano IDENTICI (hash, inode, istante di modifica);
  - se un container e' attivo il backup viene RIFIUTATO e non parte niente (neanche un byte sul "remoto");
  - se un container parte DOPO la scelta di run.sh, backup_brain.py lo rifiuta lo stesso;
  - un worker exit-only simulato che riscrive il proprio battito ogni 20 ms non disturba il backup;
  - una scrittura sul cervello DURANTE la copia (chiusura manuale simulata) fa scartare la copia e rifare;
  - scritture continue sul cervello = il backup fallisce chiuso, senza caricare nulla;
  - lo script di controllo in sola lettura distingue pronto / bloccato e non scrive nulla.
"""
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
EXT = os.path.join(HERE, "external_backup.py")
RESTORE = os.path.join(HERE, "restore_external_backup.py")
BRAIN = os.path.join(HERE, "backup_brain.py")
RUN_SH = os.path.join(REPO, "deploy", "extbackup", "run.sh")
CHECK_SH = os.path.join(REPO, "deploy", "extbackup", "check-stopped-readonly.sh")
WORKFLOW = os.path.join(REPO, ".github", "workflows", "sg-extbackup.yml")
HAVE_AGE = bool(shutil.which("age") and shutil.which("age-keygen") and shutil.which("git"))
HAVE_SH = bool(shutil.which("sh") and shutil.which("timeout"))

FAKE_DOCKER = r"""#!/bin/sh
# docker FINTO per le prove: solo "docker inspect -f <formato> <nome>".
D="${FAKE_DOCKER_DIR:?}"
[ "$1" = inspect ] || { echo "docker finto: comando non gestito" >&2; exit 1; }
FMT="$3"; NAME="$4"
[ -f "$D/$NAME" ] || { echo "Error: No such object: $NAME" >&2; exit 1; }
STATE="$(cat "$D/$NAME")"
case "$FMT" in
  '{{.State.Running}}')
    N=0; [ -f "$D/$NAME.calls" ] && N="$(cat "$D/$NAME.calls")"; N=$((N + 1)); echo "$N" > "$D/$NAME.calls"
    if [ -f "$D/$NAME.flip" ] && [ "$N" -gt "$(cat "$D/$NAME.flip")" ]; then echo true; else echo "$STATE"; fi ;;
  '{{.State.Running}} {{.HostConfig.RestartPolicy.Name}}') echo "$STATE no" ;;
  *) echo "sha256:fake|img:fake|$STATE" ;;
esac
"""
FAKE_SYSTEMCTL = r"""#!/bin/sh
case "$1" in
  is-active) f="$FAKE_SYSTEMD_DIR/$2"; if [ -f "$f" ]; then cat "$f"; else echo inactive; fi ;;
  show) echo "ActiveState=inactive"; echo "Result=success"; echo "ExecMainStatus=0" ;;
esac
"""
FAKE_JOURNALCTL = "#!/bin/sh\necho 'RISULTATO: OK  archivio finto'\n"


def sh(*cmd, cwd=None, check=True, env=None):
    p = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True, timeout=300, env=env)
    if check and p.returncode != 0:
        raise AssertionError("%s -> %s%s" % (cmd, p.stdout, p.stderr))
    return p


def put(path, data, mode=None):
    with open(path, "wb" if isinstance(data, bytes) else "w") as f:
        f.write(data)
    if mode:
        os.chmod(path, mode)


def get(path):
    with open(path, "rb") as f:
        return f.read()


def sha(path):
    return hashlib.sha256(get(path)).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CORE = ("trade_history.jsonl", "lessons.md", "errors.md", "learning_log.jsonl", "state_v2.json")


class Base(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        t = self.td.name
        self.root = os.path.join(t, "data")
        self.work = os.path.join(t, "work")
        self.remote = os.path.join(t, "remote.git")
        self.ident = os.path.join(t, "id.txt")
        self.recfile = os.path.join(t, "recipient.txt")
        self.fakebin = os.path.join(t, "fakebin")
        self.dockerdir = os.path.join(t, "dockerstate")
        self.sysdir = os.path.join(t, "systemdstate")
        for d in (self.fakebin, self.dockerdir, self.sysdir):
            os.makedirs(d)
        put(os.path.join(self.fakebin, "docker"), FAKE_DOCKER, 0o755)
        put(os.path.join(self.fakebin, "systemctl"), FAKE_SYSTEMCTL, 0o755)
        put(os.path.join(self.fakebin, "journalctl"), FAKE_JOURNALCTL, 0o755)
        for c, state in (("superbot-desk-hawk", "false"), ("superbot-desk-bull", "false")):
            put(os.path.join(self.dockerdir, c), state)
        for u in ("superbot-v3-falco-exit.service", "superbot-v3-toro-exit.service"):
            put(os.path.join(self.sysdir, u), "active")
        for p in ("hawk", "bull"):
            self.make_portfolio(p)
        self.app_db = os.path.join(t, "app.db")
        self.pool_db = os.path.join(t, "pool.db")
        for path in (self.app_db, self.pool_db):
            c = sqlite3.connect(path)
            c.execute("create table users(id integer primary key, name text)")
            c.executemany("insert into users(name) values(?)", [("riga-%d" % i,) for i in range(30)])
            c.commit()
            c.close()
        if HAVE_AGE:
            sh("age-keygen", "-o", self.ident)
            os.chmod(self.ident, 0o600)
            pub = sh("age-keygen", "-y", self.ident).stdout.strip()
            put(self.recfile, "# prova\n%s\n" % pub)
            sh("git", "init", "-q", "--bare", "-b", "main", self.remote)

    def tearDown(self):
        self.td.cleanup()

    # ---- dati finti, stessa forma di quelli veri (nessun importo reale) ----
    def make_portfolio(self, p, age=3600):
        d = os.path.join(self.root, p)
        os.makedirs(d, exist_ok=True)
        t0 = 1760000000000
        trades = [{"id": i + 1, "run_no": 3, "open_ms": t0 + i * 60000, "close_ms": t0 + i * 60000 + 30000,
                   "net": round((i % 5 - 2) * 1.25, 4)} for i in range(40)]
        rows = "".join(json.dumps(t) + "\n" for t in trades)
        learn = "".join(json.dumps({"i": i, "run_no": 3, "portfolio": p}) + "\n" for i in range(40))
        state = {"run_no": 3, "cycle": 5,
                 "main": {"cash": 1000.0 + sum(t["net"] for t in trades), "positions": {}, "closed": trades,
                          "next_id": 41, "limits": {"start_equity": 1000.0}}}
        old = time.time() - age
        for name, body in (("trade_history.jsonl", rows), ("learning_log.jsonl", learn), ("errors.md", "# e\n"),
                           ("lessons.md", "# lezioni\n"), ("state_v2.json", json.dumps(state))):
            path = os.path.join(d, name)
            put(path, body)
            os.utime(path, (old, old))
        # i bot sono FERMI da giorni: battito vecchio di un giorno
        hb = os.path.join(d, "heartbeat.json")
        put(hb, json.dumps({"cycles": 12, "cycle_running": False}))
        os.utime(hb, (time.time() - 86400, time.time() - 86400))
        put(os.path.join(d, "pause.flag"), "")

    def exit_only_heartbeat(self, p, opt_in=False, ready=True):
        put(os.path.join(self.root, p, "exit_only_heartbeat.json"),
            json.dumps({"mode": "paper-exit-only", "ready": ready, "ts": time.time(), "pid": 4242,
                        "stop_monitor_opt_in": opt_in, "stop_protection": "off"}))

    def set_docker(self, name, state):
        put(os.path.join(self.dockerdir, name), state)

    def env(self, **extra):
        e = dict(os.environ)
        e["PATH"] = self.fakebin + os.pathsep + e.get("PATH", "")
        e["FAKE_DOCKER_DIR"] = self.dockerdir
        e["FAKE_SYSTEMD_DIR"] = self.sysdir
        e.update(extra)
        return e

    def core_state(self):
        out = {}
        for p in ("hawk", "bull"):
            for n in CORE:
                path = os.path.join(self.root, p, n)
                st = os.stat(path)
                out[(p, n)] = (sha(path), st.st_ino, st.st_size, st.st_mtime_ns)
        return out

    def tree_state(self):
        out = {}
        for dp, _dn, fn in os.walk(self.root):
            for f in fn:
                path = os.path.join(dp, f)
                st = os.stat(path)
                out[path] = (st.st_size, st.st_mtime_ns)
        return out

    def archives(self):
        clone = os.path.join(self.td.name, "clone-%d" % int(time.time() * 1e6))
        sh("git", "clone", "-q", self.remote, clone)
        out = []
        for dp, _dn, fn in os.walk(os.path.join(clone, "archives")):
            out += [os.path.join(dp, f) for f in fn if f.endswith(".tar.gz.age")]
        return sorted(out)

    def remote_is_empty(self):
        p = subprocess.run(["git", "-C", self.remote, "rev-list", "--all", "--count"], capture_output=True, text=True)
        return p.returncode != 0 or p.stdout.strip() in ("", "0")

    def leftovers(self):
        return [n for n in os.listdir(self.work)
                if n.startswith("staging") or n.endswith(".age") or n.endswith(".tar.gz")] if os.path.isdir(self.work) else []

    # ---- run.sh con i percorsi del server sostituiti da cartelle temporanee ----
    def render_run_sh(self):
        text = get(RUN_SH).decode()
        key = os.path.join(self.td.name, "chiave-finta")
        subs = [("/usr/bin/python3", sys.executable),
                ("/opt/superbot-extbackup/recipient.txt", self.recfile),
                ("/opt/superbot-extbackup/known_hosts", os.path.join(self.td.name, "known_hosts-finto")),
                ("/opt/superbot-extbackup", self.work),
                ("/opt/superbot-tools", HERE),
                ("/opt/superbot-desk-data", self.root),
                ("/opt/superbot/data/superbot.db", self.app_db),
                ("/opt/superbot-pool-data/pool.db", self.pool_db),
                ("git@github.com:alexiptv82/superbot-backups.git", self.remote),
                ("/root/.ssh/superbot_backup_ed25519", key)]
        for a, b in subs:
            self.assertIn(a, text, "run.sh non contiene piu' %s: aggiornare la prova" % a)
            text = text.replace(a, b)
        self.assertNotIn("/opt/", text.replace(HERE, ""), "restano percorsi del server non sostituiti")
        path = os.path.join(self.td.name, "run-provato.sh")
        put(path, text, 0o755)
        return path

    def run_sh(self, *args, env=None):
        p = subprocess.run([shutil.which("sh"), self.render_run_sh(), *args], capture_output=True, text=True,
                           timeout=300, env=env or self.env())
        return p.returncode, p.stdout + p.stderr


@unittest.skipUnless(HAVE_SH, "mancano sh/timeout")
class RunShDecisionTests(Base):
    def mode(self):
        rc, out = self.run_sh("--print-mode")
        self.assertEqual(rc, 0, out)
        return out.strip()

    def test_repo_run_sh_is_identical_to_the_one_the_workflow_installs(self):
        wf = get(WORKFLOW).decode()
        m = re.search(r"cat > \"\$W/run\.sh\" <<'RUNSH'\n(.*?)\n {10}RUNSH\n", wf, re.S)
        self.assertTrue(m, "heredoc RUNSH non trovato nel workflow")
        inner = "\n".join(l[10:] if l.startswith(" " * 10) else l for l in m.group(1).split("\n")) + "\n"
        self.assertEqual(inner, get(RUN_SH).decode(), "run.sh del repository e heredoc del workflow sono diversi")

    def test_workflow_still_installs_the_same_unit_and_triggers_only_on_its_trigger_file(self):
        wf = get(WORKFLOW).decode()
        self.assertIn("ExecStart=/opt/superbot-extbackup/run.sh", wf)      # la unit non cambia
        self.assertIn('paths:\n      - "deploy/sg-extbackup.trigger"', wf)   # nessun nuovo trigger
        self.assertIn("branches: [rule-pool]", wf)

    def test_both_containers_stopped_chooses_bot_stopped(self):
        self.assertEqual(self.mode(), "bot-stopped")

    def test_any_running_container_chooses_normal_mode(self):
        self.set_docker("superbot-desk-hawk", "true")
        self.assertEqual(self.mode(), "normale")
        self.set_docker("superbot-desk-hawk", "false")
        self.set_docker("superbot-desk-bull", "true")
        self.assertEqual(self.mode(), "normale")

    def test_absent_container_chooses_normal_mode_fail_closed(self):
        os.unlink(os.path.join(self.dockerdir, "superbot-desk-bull"))
        self.assertEqual(self.mode(), "normale")

    def test_unreadable_docker_answer_chooses_normal_mode(self):
        self.set_docker("superbot-desk-hawk", "forse")
        self.assertEqual(self.mode(), "normale")

    def test_docker_missing_from_path_chooses_normal_mode(self):
        empty = os.path.join(self.td.name, "solo-timeout")
        os.makedirs(empty)
        os.symlink(shutil.which("timeout"), os.path.join(empty, "timeout"))
        e = dict(os.environ)
        e["PATH"] = empty
        rc, out = self.run_sh("--print-mode", env=e)
        self.assertEqual((rc, out.strip()), (0, "normale"), out)

    def test_unknown_argument_is_refused_and_nothing_runs(self):
        rc, out = self.run_sh("--bot-stopped")
        self.assertEqual(rc, 2, out)
        self.assertIn("uso:", out)
        self.assertFalse(os.path.exists(self.work), "run.sh non deve toccare nulla")

    def test_print_mode_writes_nothing_and_asks_docker_only_to_inspect(self):
        before = self.tree_state()
        self.mode()
        self.assertEqual(before, self.tree_state())
        self.assertFalse(os.path.exists(self.work))


@unittest.skipUnless(HAVE_AGE and HAVE_SH, "mancano age/age-keygen/git/sh: installare age per eseguire queste prove")
class StoppedBackupTests(Base):
    def direct(self, *extra, retries=0):
        """external_backup.py chiamato direttamente (per le prove di rifiuto: tempi corti)."""
        cmd = [sys.executable, "-I", EXT, "--root", self.root, "--app-db", self.app_db, "--pool-db", self.pool_db,
               "--tools", HERE, "--work", self.work, "--remote", self.remote, "--recipient-file", self.recfile,
               "--app-repo", "/nonexistent", "--bots-repo", "/nonexistent", "--brain-retries", str(retries),
               "--brain-retry-wait", "0", "--docker-bin", os.path.join(self.fakebin, "docker"),
               "--brain-arg=--quiet-secs", "--brain-arg=1", "--brain-arg=--attempts", "--brain-arg=2",
               "--brain-arg=--wait", "--brain-arg=0.1", "--brain-arg=--quiet-timeout", "--brain-arg=2", *extra]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=self.env())
        return p.returncode, p.stdout + p.stderr

    def decrypt_tar(self, archive):
        p = subprocess.run(["age", "-d", "-i", self.ident, archive], capture_output=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        return tarfile.open(fileobj=io.BytesIO(p.stdout), mode="r:gz")

    # ---- giro completo con run.sh ----
    def test_run_sh_with_stopped_bots_succeeds_and_manifests_match(self):
        before = self.core_state()
        rc, out = self.run_sh()
        self.assertEqual(rc, 0, out)
        self.assertIn("RISULTATO: OK", out)
        self.assertEqual(before, self.core_state(), "il backup ha toccato i file originali del cervello")
        self.assertEqual(self.leftovers(), [], "restano in chiaro/cifrati nella cartella di lavoro")
        (arc,) = self.archives()
        # manifesto interno: ogni file elencato esiste, stessa dimensione e stesso SHA-256, e non c'e' altro
        with self.decrypt_tar(arc) as tar:
            members = {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}
        internal = json.loads(members.pop("INTERNAL-MANIFEST.json"))
        listed = {f["file"]: f for f in internal["file"]}
        self.assertEqual(sorted(listed), sorted(members))
        for name, data in members.items():
            self.assertEqual(listed[name]["size"], len(data), name)
            self.assertEqual(listed[name]["sha256"], hashlib.sha256(data).hexdigest(), name)
        # manifesto del cervello dentro l'archivio: dichiara il fermo e NON finge un confine di ciclo
        (bm,) = [n for n in members if n.endswith("/MANIFEST.json") and "/cervello/" in n]
        brain = json.loads(members[bm])
        self.assertEqual(brain["coerenza"]["modalita"], "bot_fermo")
        self.assertFalse(brain["coerenza"]["confine_di_ciclo_verificato"])
        self.assertTrue(brain["coerenza"]["consistente"])
        self.assertIn("docker inspect", brain["coerenza"]["metodo"])
        for p in ("hawk", "bull"):
            self.assertIn("fermo (docker inspect)", brain["coerenza"]["stato_del_confine"][p])
        # i file del cervello nell'archivio sono identici agli originali
        for p in ("hawk", "bull"):
            for n in CORE:
                orig = get(os.path.join(self.root, p, n))
                (found,) = [k for k in members if k.endswith("/%s/%s" % (p, n)) and "/cervello/" in k]
                self.assertEqual(members[found], orig, "%s/%s" % (p, n))
        # manifesto pubblico: hash dell'archivio cifrato, immagini NON in esecuzione, nessun dato in chiaro
        pub = json.loads(get(arc[: -len(".tar.gz.age")] + ".manifest.json"))
        self.assertEqual(pub["sha256"], sha(arc))
        self.assertEqual(pub["contenuto"]["file"], len(listed))
        for c in ("superbot-desk-hawk", "superbot-desk-bull"):
            self.assertIs(pub["versioni"]["immagini_in_esecuzione"][c]["in_esecuzione"], False)
        # stato per la sentinella: successo registrato, nessun errore
        st = json.loads(get(os.path.join(self.work, "status.json")))
        self.assertIsNone(st["ultimo_errore"])
        self.assertTrue(st["ultimo_successo"])
        # ripristino vero con il restore: accetta l'eccezione dichiarata e rilegge tutto
        out_dir = os.path.join(self.td.name, "ripristino")
        p = subprocess.run([sys.executable, "-I", RESTORE, "--archive", arc, "--identity", self.ident,
                            "--out", out_dir], capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("RISULTATO: OK", p.stdout)
        self.assertIn("ECCEZIONE AMMESSA", p.stdout)

    def test_run_sh_chooses_stopped_but_a_container_starts_afterwards_is_refused(self):
        # run.sh vede 'fermo' alla prima domanda; da quel momento docker risponde 'attivo'
        put(os.path.join(self.dockerdir, "superbot-desk-hawk.flip"), "1")
        rc, out = self.run_sh()
        self.assertEqual(rc, 1, out)
        self.assertIn("RISULTATO: FALLITO", out)
        self.assertIn("non e' ammessa", out)
        self.assertTrue(self.remote_is_empty(), "il backup rifiutato non deve caricare niente")
        self.assertEqual(self.leftovers(), [])
        st = json.loads(get(os.path.join(self.work, "status.json")))
        self.assertTrue(st["ultimo_errore"])            # la sentinella vedrebbe un errore, non un falso OK
        self.assertNotIn("ultimo_successo", st)

    def test_without_the_fix_stopped_bots_fail_exactly_as_in_production(self):
        """Riproduce il difetto: percorso normale + bot fermi da giorni = nessun confine di ciclo = FALLITO."""
        rc, out = self.direct()                              # come il vecchio run.sh: nessuna modalita' particolare
        self.assertEqual(rc, 1, out)
        self.assertIn("RISULTATO: FALLITO", out)
        self.assertIn("backup del cervello non riuscito", out)
        self.assertTrue(self.remote_is_empty())
        st = json.loads(get(os.path.join(self.work, "status.json")))
        self.assertTrue(st["ultimo_errore"])
        self.assertNotIn("ultimo_successo", st)             # e' il motivo per cui la sentinella suona

    # ---- rifiuto diretto se un container e' attivo ----
    def test_bot_stopped_with_a_running_container_is_refused_and_uploads_nothing(self):
        self.set_docker("superbot-desk-bull", "true")
        before = self.core_state()
        rc, out = self.direct("--brain-arg=--bot-stopped")
        self.assertEqual(rc, 1, out)
        self.assertIn("RISULTATO: FALLITO", out)
        self.assertIn("non e' ammessa", out)
        self.assertTrue(self.remote_is_empty())
        self.assertEqual(self.leftovers(), [])
        self.assertEqual(before, self.core_state())

    def test_bot_stopped_with_docker_unusable_is_refused(self):
        rc, out = self.direct("--brain-arg=--bot-stopped", "--brain-arg=--docker-bin",
                              "--brain-arg=" + os.path.join(self.td.name, "non-esiste"))
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.remote_is_empty())

    def test_bot_stopped_with_a_fresh_heartbeat_is_not_enough_to_pass(self):
        hb = os.path.join(self.root, "hawk", "heartbeat.json")
        os.utime(hb, None)                                  # battito di adesso: qualcuno scrive
        rc, out = self.direct("--brain-arg=--bot-stopped")
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.remote_is_empty())

    # ---- servizi exit-only ----
    def test_exit_only_worker_rewriting_its_heartbeat_does_not_disturb_the_backup(self):
        stop, counter = threading.Event(), {"n": 0}

        def worker():
            while not stop.is_set():
                for p in ("hawk", "bull"):
                    d = os.path.join(self.root, p)
                    fd, tmp = tempfile.mkstemp(dir=d, prefix=".exit-only-hb.", suffix=".tmp")
                    with os.fdopen(fd, "w") as w:
                        json.dump({"mode": "paper-exit-only", "ready": True, "ts": time.time()}, w)
                        w.flush()
                        os.fsync(w.fileno())
                    os.replace(tmp, os.path.join(d, "exit_only_heartbeat.json"))
                    counter["n"] += 1
                time.sleep(0.02)

        th = threading.Thread(target=worker, daemon=True)
        before = self.core_state()
        th.start()
        try:
            rc, out = self.run_sh()
        finally:
            stop.set()
            th.join(5)
        self.assertGreater(counter["n"], 20, "la prova non e' valida: il worker simulato non ha scritto abbastanza")
        self.assertEqual(rc, 0, out)
        self.assertIn("RISULTATO: OK", out)
        self.assertEqual(before, self.core_state())
        (arc,) = self.archives()
        out_dir = os.path.join(self.td.name, "ripristino-exit-only")
        p = subprocess.run([sys.executable, "-I", RESTORE, "--archive", arc, "--identity", self.ident,
                            "--out", out_dir], capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)         # archivio coerente anche con il worker attivo
        self.assertEqual(self.leftovers(), [])

    def test_a_write_to_the_brain_during_the_copy_discards_the_copy_and_retries(self):
        """Chiusura manuale simulata: il worker exit-only scrive sul cervello mentre si copia."""
        bb = load(BRAIN, "backup_brain_prova")
        real_copy_tree = bb.copy_tree
        state = {"calls": 0}

        def copy_then_write(present, root, out):
            res = real_copy_tree(present, root, out)
            state["calls"] += 1
            if state["calls"] == 1:                         # solo durante il primo tentativo
                with open(os.path.join(root, "hawk", "trade_history.jsonl"), "a") as f:
                    f.write(json.dumps({"id": 9999, "run_no": 3, "net": 0.0}) + "\n")
            return res

        bb.copy_tree = copy_then_write
        dest = os.path.join(self.td.name, "copie")
        argv = ["backup_brain.py", "--root", self.root, "--dir", dest, "--tag", "prova", "--bot-stopped",
                "--docker-bin", os.path.join(self.fakebin, "docker"), "--quiet-secs", "1", "--wait", "0.1",
                "--quiet-timeout", "5", "--attempts", "3"]
        old_argv, old_env, buf = sys.argv, dict(os.environ), io.StringIO()
        sys.argv = argv
        os.environ.update(self.env())
        try:
            from contextlib import redirect_stdout
            with redirect_stdout(buf):
                rc = bb.main()
        finally:
            sys.argv = old_argv
            os.environ.clear()
            os.environ.update(old_env)
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("copia scartata, riprovo", out)
        self.assertEqual(state["calls"], 2)
        (snap,) = [d for d in os.listdir(dest) if d.startswith("bots-")]
        self.assertEqual(get(os.path.join(dest, snap, "hawk", "trade_history.jsonl")),
                         get(os.path.join(self.root, "hawk", "trade_history.jsonl")),
                         "la copia tenuta deve contenere anche la riga scritta durante il primo tentativo")

    def test_continuous_writes_to_the_brain_fail_closed_without_uploading(self):
        stop = threading.Event()
        path = os.path.join(self.root, "hawk", "trade_history.jsonl")

        def writer():
            while not stop.is_set():
                with open(path, "a") as f:
                    f.write(json.dumps({"id": 1, "run_no": 3, "net": 0.0}) + "\n")
                time.sleep(0.05)

        th = threading.Thread(target=writer, daemon=True)
        th.start()
        try:
            rc, out = self.direct("--brain-arg=--bot-stopped")
        finally:
            stop.set()
            th.join(5)
        self.assertEqual(rc, 1, out)
        self.assertIn("RISULTATO: FALLITO", out)
        self.assertTrue(self.remote_is_empty(), "con scritture continue non deve partire nessun archivio")
        self.assertEqual(self.leftovers(), [])


@unittest.skipUnless(HAVE_SH, "mancano sh/timeout")
class CheckScriptTests(Base):
    def setUp(self):
        super().setUp()
        for p in ("hawk", "bull"):
            self.exit_only_heartbeat(p)
        os.makedirs(self.work, exist_ok=True)

    def check(self, mode="pre", *args):
        e = self.env(SUPERBOT_DATA=self.root, SUPERBOT_EXTB=self.work, SUPERBOT_TOOLS=HERE, SUPERBOT_SETTLE="0")
        p = subprocess.run(["sh", CHECK_SH, mode, *args], capture_output=True, text=True, timeout=120, env=e)
        return p.returncode, p.stdout + p.stderr

    def test_ready_when_everything_is_stopped_and_quiet_and_writes_nothing(self):
        before = self.tree_state()
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        self.assertIn("ESITO: PRONTO", out)
        self.assertNotIn("BLOCCO     ", out)
        self.assertIn("FIRMA_CERVELLO=", out)
        self.assertIn("nessuna posizione aperta", out)
        self.assertEqual(before, self.tree_state(), "il controllo in sola lettura ha scritto nei dati dei bot")
        self.assertEqual(sorted(os.listdir(self.work)), [])

    def test_blocks_when_a_container_is_running(self):
        self.set_docker("superbot-desk-hawk", "true")
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("BLOCCO     superbot-desk-hawk NON risulta fermo", out)
        self.assertIn("ESITO: NON PRONTO", out)

    def test_blocks_when_a_close_request_is_pending(self):
        put(os.path.join(self.root, "bull", "close_position.flag"), "{}")
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("richiesta in coda (close_position.flag)", out)

    def test_blocks_when_the_brain_was_written_in_the_last_five_minutes(self):
        os.utime(os.path.join(self.root, "hawk", "lessons.md"), None)
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("e' stato scritto", out)

    def test_blocks_when_a_legacy_heartbeat_is_fresh(self):
        os.utime(os.path.join(self.root, "bull", "heartbeat.json"), None)
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("heartbeat.json vecchio di soli", out)

    def test_blocks_when_positions_are_open_and_the_stop_monitor_is_on(self):
        path = os.path.join(self.root, "hawk", "state_v2.json")
        st = json.loads(get(path))
        st["main"]["positions"] = {"BTCUSDT": {"qty": 1}}
        put(path, json.dumps(st))
        os.utime(path, (time.time() - 3600,) * 2)
        self.exit_only_heartbeat("hawk", opt_in=True)
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("monitor stop attivo", out)
        self.assertNotIn("BTCUSDT", out)                    # mai contenuti dei file

    def test_open_positions_without_stop_monitor_is_only_a_warning(self):
        path = os.path.join(self.root, "hawk", "state_v2.json")
        st = json.loads(get(path))
        st["main"]["positions"] = {"BTCUSDT": {"qty": 1}}
        put(path, json.dumps(st))
        os.utime(path, (time.time() - 3600,) * 2)
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        self.assertIn("ATTENZIONE hawk: 1 posizioni aperte", out)

    def test_blocks_when_capital_v1_needs_a_journal_that_is_missing(self):
        path = os.path.join(self.root, "bull", "state_v2.json")
        st = json.loads(get(path))
        st["capital"] = {"schema_version": 1}
        put(path, json.dumps(st))
        os.utime(path, (time.time() - 3600,) * 2)
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("manca capital-v1-journal.jsonl", out)

    def test_blocks_when_installed_tools_are_too_old(self):
        tools = os.path.join(self.td.name, "tools-vecchi")
        os.makedirs(tools)
        for n in ("external_backup.py", "backup_brain.py", "backup_app_db.py"):
            put(os.path.join(tools, n), "# versione vecchia senza le opzioni\n")
        e = self.env(SUPERBOT_DATA=self.root, SUPERBOT_EXTB=self.work, SUPERBOT_TOOLS=tools, SUPERBOT_SETTLE="0")
        p = subprocess.run(["sh", CHECK_SH, "pre"], capture_output=True, text=True, timeout=120, env=e)
        out = p.stdout + p.stderr
        self.assertEqual(p.returncode, 1, out)
        self.assertIn("non accetta --brain-arg", out)
        self.assertIn("non conosce --bot-stopped", out)

    def test_blocks_when_a_backup_process_is_really_running_but_not_for_a_shell_that_only_names_it(self):
        fake = os.path.join(self.td.name, "strumenti-finti")
        os.makedirs(fake)
        put(os.path.join(fake, "external_backup.py"), "import time\ntime.sleep(30)\n")
        decoy = subprocess.Popen(["sh", "-c", "sleep 30 # parla di external_backup.py e backup_brain.py"])
        try:
            time.sleep(0.3)
            rc, out = self.check()
            self.assertEqual(rc, 0, "una shell che nomina soltanto lo script non deve bloccare: " + out)
            real = subprocess.Popen([sys.executable, "-I", os.path.join(fake, "external_backup.py")])
            try:
                time.sleep(0.5)
                rc, out = self.check()
                self.assertEqual(rc, 1, out)
                self.assertIn("processo di backup in esecuzione", out)
            finally:
                real.kill()
                real.wait()
        finally:
            decoy.kill()
            decoy.wait()

    def test_exit_only_inactive_is_not_a_block(self):
        put(os.path.join(self.sysdir, "superbot-v3-falco-exit.service"), "inactive")
        rc, out = self.check()
        self.assertEqual(rc, 0, out)

    def test_embedded_tool_hashes_match_the_repository_versions(self):
        """Se cambia uno strumento, il controllo deve conoscere la nuova impronta attesa."""
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        for n in ("external_backup", "backup_brain", "backup_app_db"):
            self.assertIn("OK         %s.py identico alla versione del repository" % n, out)

    def test_post_mode_confirms_unchanged_brain_with_the_signature_and_reports_the_outcome(self):
        rc, out = self.check("pre")
        sig = re.search(r"FIRMA_CERVELLO=([0-9a-f]{16})", out).group(1)
        rc, out = self.check("post", sig)
        self.assertEqual(rc, 0, out)
        self.assertIn("il cervello e' identico a prima del backup", out)
        self.assertIn("CONTROLLO SUPERATO", out)
        # firma diversa (qualcuno ha scritto) = blocco
        put(os.path.join(self.root, "hawk", "lessons.md"), "# cambiata\n")
        os.utime(os.path.join(self.root, "hawk", "lessons.md"), (time.time() - 3600,) * 2)
        rc, out = self.check("post", sig)
        self.assertEqual(rc, 1, out)
        self.assertIn("il cervello e' DIVERSO", out)

    def test_wrong_mode_is_refused(self):
        rc, out = self.check("scrivi")
        self.assertEqual(rc, 2, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
