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
  - lo script di controllo in sola lettura distingue pronto / bloccato e non scrive nulla; bloccano: impronte diverse
    dei tre programmi Python (salvo accettazione esplicita dell'impronta COMPLETA), politica di riavvio automatica dei
    container (salvo 'unless-stopped' accettato per nome e verificato), numero di posizioni sconosciuto (non e' zero),
    worker exit-only senza prova affidabile (processo di systemd, battito fresco e che avanza, nessuna richiesta in
    coda, nessun file cambiato, nessun altro scrittore);
  - lo script di installazione cambia SOLO run.sh, rifiuta file diversi, non sovrascrive mai l'originale salvato,
    non chiama systemd se non per leggere lo stato, e il rollback rimette l'impronta esatta dell'originale.

Se manca age/age-keygen/git le prove integrate si SALTANO e lo dicono; con SUPERBOT_REQUIRE_INTEGRATION=1 invece
FALLISCONO (cosi' un "tutto verde" non puo' nascondere prove non eseguite).
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
REQUIRE_INTEGRATION = os.environ.get("SUPERBOT_REQUIRE_INTEGRATION") == "1"
INSTALL_SH = os.path.join(REPO, "deploy", "extbackup", "install-wrapper.sh")
REAL_SLEEP = shutil.which("sleep") or "/bin/sleep"
REAL_SHA256SUM = shutil.which("sha256sum") or "/usr/bin/sha256sum"
# run.sh scritto dall'azione "setup" del workflow su rule-pool (fed2e3f) PRIMA della correzione
OLD_RUN_SH = (
    "#!/bin/sh\n"
    "exec /usr/bin/python3 -I /opt/superbot-tools/external_backup.py \\\n"
    "  --root /opt/superbot-desk-data --app-db /opt/superbot/data/superbot.db \\\n"
    "  --pool-db /opt/superbot-pool-data/pool.db --tools /opt/superbot-tools --work /opt/superbot-extbackup \\\n"
    "  --remote git@github.com:alexiptv82/superbot-backups.git --recipient-file /opt/superbot-extbackup/recipient.txt \\\n"
    "  --ssh-key /root/.ssh/superbot_backup_ed25519 --known-hosts /opt/superbot-extbackup/known_hosts\n"
)

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
  '{{.State.Running}}|{{.HostConfig.RestartPolicy.Name}}|{{.State.Status}}|{{.State.Restarting}}|{{.State.FinishedAt}}')
    POL=no; [ -f "$D/$NAME.policy" ] && POL="$(cat "$D/$NAME.policy")"
    if [ "$STATE" = true ]; then ST=running; else ST=exited; fi; [ -f "$D/$NAME.status" ] && ST="$(cat "$D/$NAME.status")"
    RS=false; [ -f "$D/$NAME.restarting" ] && RS="$(cat "$D/$NAME.restarting")"
    FIN=2026-11-02T10:00:00.123456789Z; [ -f "$D/$NAME.finished" ] && FIN="$(cat "$D/$NAME.finished")"
    echo "$STATE|$POL|$ST|$RS|$FIN" ;;
  *) echo "sha256:fake|img:fake|$STATE" ;;
esac
"""
FAKE_SYSTEMCTL = r"""#!/bin/sh
echo "$*" >> "$FAKE_SYSTEMD_DIR/calls.log"
case "$1" in
  is-active) f="$FAKE_SYSTEMD_DIR/$2"; if [ -f "$f" ]; then cat "$f"; else echo inactive; fi ;;
  show)
    case "$*" in
      *MainPID*) for a; do U="$a"; done; if [ -f "$FAKE_SYSTEMD_DIR/$U.mainpid" ]; then cat "$FAKE_SYSTEMD_DIR/$U.mainpid"; else echo 0; fi ;;
      *) echo "ActiveState=inactive"; echo "Result=success"; echo "ExecMainStatus=0" ;;
    esac ;;
  *) echo "systemctl finto: comando non permesso nelle prove: $*" >&2; exit 9 ;;
esac
"""
FAKE_ID = "#!/bin/sh\ncase \"$1\" in -u) echo \"${FAKE_UID:-0}\" ;; *) exec /usr/bin/id \"$@\" ;; esac\n"
FAKE_SLEEP = "#!/bin/sh\n[ -n \"$SLEEP_HOOK\" ] && eval \"$SLEEP_HOOK\"\nexec %s \"$@\"\n" % REAL_SLEEP
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
        put(os.path.join(self.fakebin, "id"), FAKE_ID, 0o755)
        put(os.path.join(self.fakebin, "sleep"), FAKE_SLEEP, 0o755)
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


INTEGRATION = unittest.skipUnless(HAVE_AGE and HAVE_SH or REQUIRE_INTEGRATION,
                                  "mancano age/age-keygen/git/sh: installare age per eseguire queste prove")


class IntegrationPrerequisiteTests(unittest.TestCase):
    def test_age_and_git_are_present_when_integration_is_required(self):
        if not REQUIRE_INTEGRATION:
            self.skipTest("SUPERBOT_REQUIRE_INTEGRATION non impostato: le prove con age possono essere saltate")
        self.assertTrue(HAVE_AGE, "SUPERBOT_REQUIRE_INTEGRATION=1 ma mancano age/age-keygen/git: prove integrate NON eseguibili")
        self.assertTrue(HAVE_SH)


@INTEGRATION
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


def _kill(proc):
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


UNITS = {"hawk": "superbot-v3-falco-exit.service", "bull": "superbot-v3-toro-exit.service"}
TOOL_NAMES = ("external_backup.py", "backup_brain.py", "backup_app_db.py")
WORKER_OWN_FILES = ("exit_only_heartbeat.json", ".exit_only_writer.lock")


def utc_iso(age_seconds):
    t = time.time() - age_seconds
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".123456789Z"


@unittest.skipUnless(HAVE_SH, "mancano sh/timeout")
class CheckScriptTests(Base):
    """Controllo 'pre' in sola lettura. Il worker exit-only e' SIMULATO con un vero processo (riga di comando con
    'desk.exit_only', blocco di scrittura aperto) piu' un thread che riscrive il battito ogni 50 ms con tmp + rename,
    come fa quello vero; systemd e docker sono finti."""

    def setUp(self):
        super().setUp()
        os.makedirs(self.work, exist_ok=True)
        put(os.path.join(self.work, "run.sh"), OLD_RUN_SH, 0o700)      # il wrapper "attuale", ancora da correggere
        self.procs = []
        self.beaters = {}
        for p in ("hawk", "bull"):
            self.start_worker(p)

    def tearDown(self):
        for ev, th in list(self.beaters.values()):
            ev.set()
            th.join(5)
        for pr in self.procs:
            _kill(pr)
        super().tearDown()

    # ---- worker exit-only simulato ----
    def write_hb(self, p, pid, ready=True, portfolio=None, opt_in=False, ts=None):
        d = os.path.join(self.root, p)
        tmp = os.path.join(d, ".exit-only-hb.%d.tmp" % pid)
        put(tmp, json.dumps({"mode": "paper-exit-only", "portfolio": portfolio or p, "ready": ready,
                             "ts": time.time() if ts is None else ts, "pid": pid, "stop_monitor_opt_in": opt_in,
                             "stop_protection": "off"}))
        os.replace(tmp, os.path.join(d, "exit_only_heartbeat.json"))

    def stop_worker(self, p):
        if p in self.beaters:
            ev, th = self.beaters.pop(p)
            ev.set()
            th.join(5)

    def start_worker(self, p, beat=True, ready=True, hb_portfolio=None, hb_pid=None, marker="desk.exit_only",
                     mainpid=None, opt_in=False):
        self.stop_worker(p)
        lock = os.path.join(self.root, p, ".exit_only_writer.lock")
        code = "import sys, time\nf = open(sys.argv[1], 'a')\ntime.sleep(300)\n"
        proc = subprocess.Popen([sys.executable, "-I", "-c", code, lock, marker])
        self.procs.append(proc)
        for _ in range(100):
            if os.path.exists(lock):
                break
            time.sleep(0.05)
        self.assertTrue(os.path.exists(lock), "il worker finto non e' partito")
        put(os.path.join(self.sysdir, UNITS[p] + ".mainpid"), str(proc.pid if mainpid is None else mainpid))
        hbpid = proc.pid if hb_pid is None else hb_pid
        self.write_hb(p, hbpid, ready=ready, portfolio=hb_portfolio, opt_in=opt_in)
        if beat:
            ev = threading.Event()

            def beater():
                while not ev.is_set():
                    try:
                        self.write_hb(p, hbpid, ready=ready, portfolio=hb_portfolio, opt_in=opt_in)
                    except OSError:
                        pass
                    time.sleep(0.05)

            th = threading.Thread(target=beater, daemon=True)
            th.start()
            self.beaters[p] = (ev, th)
        return proc

    # ---- utilita' ----
    def check(self, mode="pre", *args, settle="0.6", tools=HERE, extra_path=None, **envx):
        e = self.env(SUPERBOT_DATA=self.root, SUPERBOT_EXTB=self.work, SUPERBOT_TOOLS=tools,
                     SUPERBOT_SETTLE=settle, **envx)
        if extra_path:
            e["PATH"] = extra_path + os.pathsep + e["PATH"]
        p = subprocess.run(["sh", CHECK_SH, mode, *args], capture_output=True, text=True, timeout=180, env=e)
        return p.returncode, p.stdout + p.stderr

    def quiet_tree(self):
        out = {}
        for k, v in self.tree_state().items():
            b = os.path.basename(k)
            if b in WORKER_OWN_FILES or b.startswith(".exit-only-hb."):
                continue
            out[k] = v
        return out

    def set_state(self, p, mutate):
        path = os.path.join(self.root, p, "state_v2.json")
        st = json.loads(get(path))
        mutate(st)
        put(path, json.dumps(st))
        os.utime(path, (time.time() - 3600,) * 2)

    def tools_copy(self):
        d = os.path.join(self.td.name, "strumenti-%d" % len(os.listdir(self.td.name)))
        os.makedirs(d)
        for n in TOOL_NAMES:
            shutil.copy(os.path.join(HERE, n), os.path.join(d, n))
        return d

    def set_policy(self, name, policy, finished_age=86400, status=None, restarting=None):
        put(os.path.join(self.dockerdir, name + ".policy"), policy)
        put(os.path.join(self.dockerdir, name + ".finished"), utc_iso(finished_age))
        if status:
            put(os.path.join(self.dockerdir, name + ".status"), status)
        if restarting:
            put(os.path.join(self.dockerdir, name + ".restarting"), restarting)

    # ---- pronto / non pronto: base ----
    def test_ready_when_everything_is_stopped_and_quiet_and_writes_nothing(self):
        before = self.quiet_tree()
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        self.assertIn("ESITO: PRONTO", out)
        self.assertNotIn("BLOCCO     ", out)
        self.assertIn("FIRMA_CERVELLO=", out)
        self.assertIn("posizioni aperte = 0", out)
        self.assertIn("il battito exit-only e' AVANZATO", out)
        self.assertIn("politica di riavvio 'no'", out)
        self.assertIn("eseguito come root", out)
        self.assertEqual(before, self.quiet_tree(), "il controllo in sola lettura ha scritto nei dati dei bot")
        self.assertEqual(sorted(os.listdir(self.work)), ["run.sh"])
        self.assertEqual(get(os.path.join(self.work, "run.sh")).decode(), OLD_RUN_SH)

    def test_blocks_when_the_wrapper_is_missing(self):
        os.unlink(os.path.join(self.work, "run.sh"))
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("BLOCCO     run.sh assente in", out)

    def test_blocks_when_a_container_is_running(self):
        self.set_docker("superbot-desk-hawk", "true")
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("BLOCCO     superbot-desk-hawk NON risulta fermo", out)
        self.assertIn("ESITO: NON PRONTO", out)

    def test_blocks_when_a_container_is_restarting_even_if_running_is_false(self):
        self.set_policy("superbot-desk-bull", "no", restarting="true")
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("BLOCCO     superbot-desk-bull NON risulta fermo", out)

    def test_blocks_when_a_container_is_missing_or_docker_does_not_answer(self):
        os.unlink(os.path.join(self.dockerdir, "superbot-desk-bull"))
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("superbot-desk-bull NON risulta fermo (docker non risponde o container assente)", out)

    def test_blocks_when_a_close_request_is_pending(self):
        put(os.path.join(self.root, "bull", "close_position.flag"), "{}")
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("BLOCCO     bull: richiesta di chiusura/reset in coda (close_position.flag)", out)
        self.assertNotIn("durante l'osservazione e' comparsa", out)      # c'era gia' prima: non e' "comparsa"

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

    def test_blocks_when_capital_v1_needs_a_journal_that_is_missing(self):
        self.set_state("bull", lambda st: st.__setitem__("capital", {"schema_version": 1}))
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("manca capital-v1-journal.jsonl", out)

    def test_wrong_mode_is_refused(self):
        rc, out = self.check("scrivi")
        self.assertEqual(rc, 2, out)

    def test_not_root_blocks(self):
        rc, out = self.check(FAKE_UID="1000")
        self.assertEqual(rc, 1, out)
        self.assertIn("non eseguito come root (uid 1000)", out)

    # ---- punto 1: impronte dei tre programmi Python ----
    def test_old_tools_without_the_options_block(self):
        d = os.path.join(self.td.name, "tools-vecchi")
        os.makedirs(d)
        for n in TOOL_NAMES:
            put(os.path.join(d, n), "# versione vecchia senza le opzioni\n")
        rc, out = self.check(tools=d)
        self.assertEqual(rc, 1, out)
        self.assertIn("non accetta --brain-arg", out)
        self.assertIn("non conosce --bot-stopped", out)
        self.assertIn("DIVERSO dal repository", out)

    def test_a_missing_tool_blocks(self):
        d = self.tools_copy()
        os.unlink(os.path.join(d, "backup_app_db.py"))
        rc, out = self.check(tools=d)
        self.assertEqual(rc, 1, out)
        self.assertIn("backup_app_db.py assente", out)

    def test_a_modified_tool_blocks_and_prints_the_full_hash_without_replacing_anything(self):
        d = self.tools_copy()
        path = os.path.join(d, "backup_brain.py")
        put(path, get(path) + b"\n# modifica locale\n")
        h = sha(path)
        before = {n: sha(os.path.join(d, n)) for n in TOOL_NAMES}
        rc, out = self.check(tools=d)
        self.assertEqual(rc, 1, out)
        self.assertIn("BLOCCO     backup_brain.py DIVERSO dal repository: sha256 %s" % h, out)
        self.assertIn("Non sostituire", out)
        self.assertEqual(before, {n: sha(os.path.join(d, n)) for n in TOOL_NAMES}, "il controllo ha toccato i programmi")

    def test_explicit_acceptance_of_the_full_hash_unblocks_only_that_file(self):
        d = self.tools_copy()
        for n in ("backup_brain.py", "external_backup.py"):
            put(os.path.join(d, n), get(os.path.join(d, n)) + b"\n# modifica locale\n")
        hb = sha(os.path.join(d, "backup_brain.py"))
        rc, out = self.check(tools=d, SUPERBOT_ACCEPT_TOOL_HASHES="backup_brain=%s" % hb)
        self.assertEqual(rc, 1, out)
        self.assertIn("backup_brain.py DIVERSO dal repository ma ACCETTATO ESPLICITAMENTE", out)
        self.assertIn("BLOCCO     external_backup.py DIVERSO dal repository", out)
        he = sha(os.path.join(d, "external_backup.py"))
        rc, out = self.check(tools=d, SUPERBOT_ACCEPT_TOOL_HASHES="backup_brain=%s,external_backup=%s" % (hb, he))
        self.assertEqual(rc, 0, out)
        self.assertIn("ESITO: PRONTO", out)

    def test_acceptance_with_a_short_wrong_or_foreign_hash_does_not_count(self):
        d = self.tools_copy()
        put(os.path.join(d, "backup_brain.py"), get(os.path.join(d, "backup_brain.py")) + b"\n# x\n")
        h = sha(os.path.join(d, "backup_brain.py"))
        for label, value in (("abbreviata", "backup_brain=%s" % h[:16]), ("nome sbagliato", "external_backup=%s" % h),
                             ("altra impronta", "backup_brain=%s" % ("0" * 64)), ("senza nome", h),
                             ("maiuscole", "backup_brain=%s" % h.upper())):
            with self.subTest(label):
                rc, out = self.check(tools=d, SUPERBOT_ACCEPT_TOOL_HASHES=value)
                self.assertEqual(rc, 1, out)
                self.assertIn("BLOCCO     backup_brain.py DIVERSO dal repository", out)

    def test_an_accepted_tool_that_lost_the_required_option_still_blocks(self):
        d = self.tools_copy()
        path = os.path.join(d, "backup_brain.py")
        put(path, "# versione senza l'opzione\n")
        rc, out = self.check(tools=d, SUPERBOT_ACCEPT_TOOL_HASHES="backup_brain=%s" % sha(path))
        self.assertEqual(rc, 1, out)
        self.assertIn("ACCETTATO ESPLICITAMENTE", out)
        self.assertIn("backup_brain.py non conosce --bot-stopped", out)

    def test_an_accepted_tool_that_is_not_valid_python_still_blocks(self):
        d = self.tools_copy()
        path = os.path.join(d, "backup_brain.py")
        put(path, "--bot-stopped\ndef (:\n")
        rc, out = self.check(tools=d, SUPERBOT_ACCEPT_TOOL_HASHES="backup_brain=%s" % sha(path))
        self.assertEqual(rc, 1, out)
        self.assertIn("backup_brain.py non e' un programma Python valido", out)

    def test_a_known_historical_version_is_named_but_still_blocks(self):
        shim = os.path.join(self.td.name, "shim-sha")
        os.makedirs(shim)
        put(os.path.join(shim, "sha256sum"),
            '#!/bin/sh\ncase "$*" in *backup_brain.py) echo "d31aaeca9131070095adc8d1f14b0e261fb1c3f07dafdc30dfcb187a781bd626  $1"; exit 0 ;; esac\nexec %s "$@"\n' % REAL_SHA256SUM,
            0o755)
        rc, out = self.check(extra_path=shim)
        self.assertEqual(rc, 1, out)
        self.assertIn("backup_brain.py DIVERSO dal repository: sha256 d31aaeca9131070095adc8d1f14b0e261fb1c3f07dafdc30dfcb187a781bd626"
                      " - corrisponde a: versione storica del repository: rule-pool@db5f08a", out)

    def test_every_embedded_tool_hash_matches_the_repository_and_has_a_history_label(self):
        text = get(CHECK_SH).decode()
        for n in ("external_backup", "backup_brain", "backup_app_db"):
            h = sha(os.path.join(HERE, n + ".py"))
            self.assertIn(" chk %s %s" % (n, h), text, "impronta attesa di %s non allineata al repository" % n)
            self.assertRegex(text, r"\n\s+%s:%s\) echo \"versione storica" % (n, h), "manca l'etichetta storica di %s" % n)
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        for n in ("external_backup", "backup_brain", "backup_app_db"):
            self.assertIn("OK         %s.py identico alla versione del repository" % n, out)

    # ---- punto 2: politica di riavvio dei container ----
    def test_automatic_restart_policies_block(self):
        for pol in ("always", "on-failure", "on-failure:5", "unless-stopped", ""):
            with self.subTest(politica=pol):
                self.set_policy("superbot-desk-hawk", pol)
                rc, out = self.check()
                self.assertEqual(rc, 1, out)
                self.assertRegex(out, r"BLOCCO     superbot-desk-hawk: politica di riavvio", out)
                self.assertNotIn("BLOCCO     superbot-desk-bull", out)
        self.set_policy("superbot-desk-hawk", "no")
        rc, out = self.check()
        self.assertEqual(rc, 0, out)

    def test_unless_stopped_is_accepted_only_by_name_when_exited_and_stopped_for_over_an_hour(self):
        both = "superbot-desk-hawk=unless-stopped,superbot-desk-bull=unless-stopped"
        for name in ("superbot-desk-hawk", "superbot-desk-bull"):
            self.set_policy(name, "unless-stopped", finished_age=86400)
        rc, out = self.check()
        self.assertEqual(rc, 1, out)                                    # senza accettazione: blocco
        rc, out = self.check(SUPERBOT_ACCEPT_RESTART_POLICY=both)
        self.assertEqual(rc, 0, out)
        self.assertIn("politica 'unless-stopped' ACCETTATA ESPLICITAMENTE", out)
        # accettato solo per uno: l'altro blocca
        rc, out = self.check(SUPERBOT_ACCEPT_RESTART_POLICY="superbot-desk-hawk=unless-stopped")
        self.assertEqual(rc, 1, out)
        self.assertIn("BLOCCO     superbot-desk-bull: politica di riavvio AUTOMATICA 'unless-stopped'", out)
        self.assertNotIn("BLOCCO     superbot-desk-hawk", out)
        # accettazione di un valore diverso da unless-stopped non vale
        rc, out = self.check(SUPERBOT_ACCEPT_RESTART_POLICY="superbot-desk-hawk=always,superbot-desk-bull=always")
        self.assertEqual(rc, 1, out)

    def test_unless_stopped_accepted_but_stopped_only_recently_still_blocks(self):
        self.set_policy("superbot-desk-hawk", "unless-stopped", finished_age=60)
        rc, out = self.check(SUPERBOT_ACCEPT_RESTART_POLICY="superbot-desk-hawk=unless-stopped")
        self.assertEqual(rc, 1, out)
        self.assertIn("BLOCCO     superbot-desk-hawk: politica di riavvio AUTOMATICA 'unless-stopped' non accettata", out)

    def test_unless_stopped_accepted_but_unreadable_stop_time_still_blocks(self):
        self.set_policy("superbot-desk-hawk", "unless-stopped")
        put(os.path.join(self.dockerdir, "superbot-desk-hawk.finished"), "non-una-data")
        rc, out = self.check(SUPERBOT_ACCEPT_RESTART_POLICY="superbot-desk-hawk=unless-stopped")
        self.assertEqual(rc, 1, out)
        self.assertIn("fermo da: -1 s", out)

    def test_unless_stopped_accepted_but_container_not_exited_still_blocks(self):
        self.set_policy("superbot-desk-hawk", "unless-stopped", status="created")
        rc, out = self.check(SUPERBOT_ACCEPT_RESTART_POLICY="superbot-desk-hawk=unless-stopped")
        self.assertEqual(rc, 1, out)

    # ---- punto 3: posizioni e prova sul worker exit-only ----
    def test_unknown_number_of_positions_blocks_and_is_never_treated_as_zero(self):
        variants = {
            "positions assente": lambda st: st["main"].pop("positions"),
            "positions nullo": lambda st: st["main"].__setitem__("positions", None),
            "positions e' una lista": lambda st: st["main"].__setitem__("positions", []),
            "positions e' una stringa": lambda st: st["main"].__setitem__("positions", "3"),
            "main assente": lambda st: st.pop("main"),
            "main non e' un oggetto": lambda st: st.__setitem__("main", [1]),
        }
        for label, mutate in variants.items():
            with self.subTest(label):
                self.make_portfolio("hawk")
                self.set_state("hawk", mutate)
                rc, out = self.check()
                self.assertEqual(rc, 1, out)
                self.assertIn("BLOCCO     hawk: numero di posizioni aperte SCONOSCIUTO", out)
                self.assertIn("non lo considero zero", out)
                self.assertIn("deve essere NOTO e zero (qui e' sconosciuto)", out)

    def test_unknown_positions_also_block_when_the_worker_is_not_active(self):
        self.make_portfolio("hawk")
        self.set_state("hawk", lambda st: st["main"].pop("positions"))
        put(os.path.join(self.sysdir, UNITS["hawk"]), "inactive")
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("BLOCCO     hawk: numero di posizioni aperte SCONOSCIUTO", out)

    def test_open_positions_with_an_active_exit_only_worker_block_with_or_without_the_stop_monitor(self):
        for opt in (False, True):
            with self.subTest(stop_monitor=opt):
                self.make_portfolio("hawk")
                self.set_state("hawk", lambda st: st["main"].__setitem__("positions", {"BTCUSDT": {"qty": 1}}))
                self.start_worker("hawk", opt_in=opt)
                rc, out = self.check()
                self.assertEqual(rc, 1, out)
                self.assertIn("BLOCCO     hawk: 1 posizioni aperte con il worker exit-only attivo", out)
                self.assertNotIn("BTCUSDT", out)                    # mai contenuti dei file

    def test_open_positions_with_the_worker_not_active_are_only_informational(self):
        self.set_state("hawk", lambda st: st["main"].__setitem__("positions", {"BTCUSDT": {"qty": 1}}))
        for u in UNITS.values():
            put(os.path.join(self.sysdir, u), "inactive")
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        self.assertIn("hawk: posizioni aperte nello stato = 1", out)
        self.assertNotIn("BTCUSDT", out)

    def test_exit_only_inactive_or_failed_is_not_a_block(self):
        put(os.path.join(self.sysdir, UNITS["hawk"]), "inactive")
        put(os.path.join(self.sysdir, UNITS["bull"]), "failed")
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        self.assertIn("worker exit-only non attivo", out)

    def test_odd_unit_states_block_instead_of_being_assumed_harmless(self):
        for state in ("activating", "deactivating", "reloading", "", "maintenance"):
            with self.subTest(stato=state):
                put(os.path.join(self.sysdir, UNITS["hawk"]), state)
                rc, out = self.check()
                self.assertEqual(rc, 1, out)
                self.assertIn("BLOCCO     hawk: stato del servizio exit-only non determinabile", out)

    def test_worker_that_stopped_beating_is_not_trusted(self):
        self.start_worker("hawk", beat=False)
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("BLOCCO     hawk: il battito exit-only NON e' avanzato", out)

    def test_stale_worker_heartbeat_blocks(self):
        proc = self.start_worker("hawk", beat=False)
        self.write_hb("hawk", proc.pid, ts=time.time() - 120)
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("BLOCCO     hawk: battito exit-only non fresco", out)

    def test_worker_not_ready_or_for_another_portfolio_or_with_another_pid_blocks(self):
        cases = (("non pronto", dict(ready=False), "NON dichiara ready"),
                 ("altro portafoglio", dict(hb_portfolio="bull"), "il battito dichiara il portafoglio 'bull'"),
                 ("altro pid", dict(hb_pid=999999), "il pid del battito (999999) non coincide con quello di systemd"))
        for label, kw, msg in cases:
            with self.subTest(label):
                self.start_worker("hawk", **kw)
                rc, out = self.check()
                self.assertEqual(rc, 1, out)
                self.assertIn(msg, out)

    def test_systemd_main_process_must_exist_and_be_the_exit_only_program(self):
        done = subprocess.Popen(["true"])
        done.wait()
        cases = (("pid zero", dict(mainpid=0)), ("processo morto", dict(mainpid=done.pid)),
                 ("altro programma", dict(marker="altro-programma")))
        for label, kw in cases:
            with self.subTest(label):
                self.start_worker("hawk", **kw)
                rc, out = self.check()
                self.assertEqual(rc, 1, out)
                self.assertIn("BLOCCO     hawk: il processo principale di systemd", out)
                self.assertIn("non esiste o non e' desk.exit_only: evidenza non affidabile", out)

    def test_unreadable_or_missing_worker_heartbeat_blocks(self):
        self.start_worker("hawk", beat=False)
        put(os.path.join(self.root, "hawk", "exit_only_heartbeat.json"), "{non json")
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("NON dichiara ready (ready=illeggibile)", out)
        os.unlink(os.path.join(self.root, "hawk", "exit_only_heartbeat.json"))
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("NON dichiara ready", out)

    # ---- richieste e scritture DURANTE l'osservazione (il finto 'sleep' le provoca nel punto esatto) ----
    def test_a_request_that_appears_during_the_observation_blocks(self):
        hook = 'touch "%s"' % os.path.join(self.root, "hawk", "close_position.flag")
        rc, out = self.check(SLEEP_HOOK=hook)
        self.assertEqual(rc, 1, out)
        self.assertIn("durante l'osservazione e' comparsa una richiesta (close_position.flag)", out)

    def test_a_brain_write_during_the_observation_blocks(self):
        hook = 'echo riga >> "%s"' % os.path.join(self.root, "hawk", "lessons.md")
        rc, out = self.check(SLEEP_HOOK=hook)
        self.assertEqual(rc, 1, out)
        self.assertIn("i file del cervello sono cambiati durante l'osservazione", out)
        self.assertIn("lessons.md", out)

    def test_any_other_file_change_in_the_data_folder_during_the_observation_blocks(self):
        hook = 'touch "%s"' % os.path.join(self.root, "bull", "file_nuovo.json")
        rc, out = self.check(SLEEP_HOOK=hook)
        self.assertEqual(rc, 1, out)
        self.assertIn("bull: file della cartella dati cambiati/creati/spariti durante l'osservazione (solo nomi)", out)
        self.assertIn("file_nuovo.json", out)

    def test_another_process_with_a_brain_file_open_for_writing_blocks_but_a_reader_does_not(self):
        target = os.path.join(self.root, "hawk", "trade_history.jsonl")
        reader = subprocess.Popen([sys.executable, "-I", "-c", "import sys, time\nf = open(sys.argv[1])\ntime.sleep(60)\n", target])
        self.procs.append(reader)
        time.sleep(0.5)
        rc, out = self.check()
        self.assertEqual(rc, 0, "un processo che solo legge non deve bloccare: " + out)
        writer = subprocess.Popen([sys.executable, "-I", "-c", "import sys, time\nf = open(sys.argv[1], 'a')\ntime.sleep(60)\n", target])
        self.procs.append(writer)
        time.sleep(0.5)
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("scrittore aperto: pid %d" % writer.pid, out)
        self.assertIn("scrive trade_history.jsonl", out)

    def test_blocks_when_a_backup_process_is_really_running_but_not_for_a_shell_that_only_names_it(self):
        fake = os.path.join(self.td.name, "strumenti-finti")
        os.makedirs(fake)
        put(os.path.join(fake, "external_backup.py"), "import time\ntime.sleep(30)\n")
        decoy = subprocess.Popen(["sh", "-c", "sleep 30 # parla di external_backup.py e backup_brain.py"])
        self.procs.append(decoy)
        time.sleep(0.3)
        rc, out = self.check()
        self.assertEqual(rc, 0, "una shell che nomina soltanto lo script non deve bloccare: " + out)
        real = subprocess.Popen([sys.executable, "-I", os.path.join(fake, "external_backup.py")])
        self.procs.append(real)
        time.sleep(0.5)
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("processo di backup in esecuzione", out)

    def test_a_backup_service_already_running_blocks(self):
        put(os.path.join(self.sysdir, "superbot-extbackup.service"), "active")
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("superbot-extbackup.service e' in corso", out)

    def test_pre_never_calls_systemctl_for_anything_but_reading(self):
        self.check()
        calls = get(os.path.join(self.sysdir, "calls.log")).decode().splitlines()
        self.assertTrue(calls)
        for c in calls:
            self.assertTrue(c.startswith(("is-active ", "show ")), "chiamata a systemctl non di sola lettura: " + c)


@INTEGRATION
@unittest.skipUnless(HAVE_SH, "mancano sh/timeout")
class PostCheckTests(Base):
    """Controllo 'post' dopo un VERO backup (run.sh -> external_backup.py -> age -> repository 'remoto' locale)."""

    def setUp(self):
        super().setUp()
        for u in UNITS.values():
            put(os.path.join(self.sysdir, u), "inactive")
        os.makedirs(self.work, exist_ok=True)
        put(os.path.join(self.work, "run.sh"), OLD_RUN_SH, 0o700)      # il wrapper "attuale", prima della correzione

    def check(self, mode, *args):
        e = self.env(SUPERBOT_DATA=self.root, SUPERBOT_EXTB=self.work, SUPERBOT_TOOLS=HERE, SUPERBOT_SETTLE="0")
        p = subprocess.run(["sh", CHECK_SH, mode, *args], capture_output=True, text=True, timeout=180, env=e)
        return p.returncode, p.stdout + p.stderr

    def backup(self):
        rc, out = self.check("pre")
        self.assertEqual(rc, 0, out)
        sig = re.search(r"FIRMA_CERVELLO=([0-9a-f]{16})", out).group(1)
        rc, out = self.run_sh()
        self.assertEqual(rc, 0, out)
        put(os.path.join(self.work, "run.sh"), get(RUN_SH), 0o700)       # il wrapper "installato"
        return sig

    def manifest_path(self):
        found = []
        for dp, _dn, fn in os.walk(os.path.join(self.work, "repo", "archives")):
            found += [os.path.join(dp, f) for f in fn if f.endswith(".manifest.json")]
        self.assertEqual(len(found), 1)
        return found[0]

    def test_after_a_real_backup_the_post_check_passes_and_verifies_the_remote(self):
        sig = self.backup()
        before = {k: v for k, v in self.tree_state().items()}
        work_before = sorted((os.path.join(dp, f), os.stat(os.path.join(dp, f)).st_mtime_ns)
                             for dp, _dn, fn in os.walk(self.work) for f in fn)
        rc, out = self.check("post", sig)
        self.assertEqual(rc, 0, out)
        for frag in ("CONTROLLO SUPERATO", "il cervello e' identico a prima del backup",
                     "verifica remota: la punta di main nel repository privato dei backup",
                     "status.json: nessun errore registrato", "(entro 30 minuti)",
                     "coincide con quello di status.json", "NON in esecuzione",
                     "run.sh e' la versione corretta attesa"):
            self.assertIn(frag, out)
        self.assertEqual(before, self.tree_state(), "il controllo post ha scritto nei dati dei bot")
        self.assertEqual(work_before, sorted((os.path.join(dp, f), os.stat(os.path.join(dp, f)).st_mtime_ns)
                                             for dp, _dn, fn in os.walk(self.work) for f in fn),
                         "il controllo post ha scritto nella cartella del backup")

    def test_post_blocks_when_run_sh_was_overwritten_with_the_old_version(self):
        sig = self.backup()
        put(os.path.join(self.work, "run.sh"), OLD_RUN_SH, 0o700)
        rc, out = self.check("post", sig)
        self.assertEqual(rc, 1, out)
        self.assertIn("run.sh installato NON e' la versione corretta attesa", out)

    def test_post_blocks_when_the_remote_moved_after_the_push(self):
        sig = self.backup()
        c = os.path.join(self.td.name, "altro-clone")
        sh("git", "clone", "-q", self.remote, c)
        sh("git", "-C", c, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
        sh("git", "-C", c, "push", "-q", "origin", "main")
        rc, out = self.check("post", sig)
        self.assertEqual(rc, 1, out)
        self.assertIn("verifica remota: punta locale", out)

    def test_post_blocks_when_the_remote_is_unreachable(self):
        sig = self.backup()
        sh("git", "-C", os.path.join(self.work, "repo"), "remote", "set-url", "origin", os.path.join(self.td.name, "non-esiste.git"))
        rc, out = self.check("post", sig)
        self.assertEqual(rc, 1, out)
        self.assertIn("remoto non raggiungibile", out)

    def test_post_blocks_when_the_last_success_is_not_recent(self):
        sig = self.backup()
        path = os.path.join(self.work, "status.json")
        st = json.loads(get(path))
        st["ultimo_successo"] = "2020-01-01T00:00:00Z"
        put(path, json.dumps(st))
        rc, out = self.check("post", sig)
        self.assertEqual(rc, 1, out)
        self.assertIn("l'ultimo backup riuscito non e' recente", out)

    def test_post_blocks_when_status_records_an_error(self):
        sig = self.backup()
        path = os.path.join(self.work, "status.json")
        st = json.loads(get(path))
        st["ultimo_errore"] = "errore di prova"
        put(path, json.dumps(st))
        rc, out = self.check("post", sig)
        self.assertEqual(rc, 1, out)
        self.assertIn("status.json: ultimo errore registrato o stato illeggibile", out)

    def test_post_blocks_when_the_public_manifest_sha_differs_from_status(self):
        sig = self.backup()
        mp = self.manifest_path()
        m = json.loads(get(mp))
        m["sha256"] = "0" * 64
        put(mp, json.dumps(m))
        rc, out = self.check("post", sig)
        self.assertEqual(rc, 1, out)
        self.assertIn("lo SHA-256 del manifesto pubblico non coincide con status.json", out)

    def test_post_blocks_when_the_manifest_says_a_bot_was_running(self):
        sig = self.backup()
        mp = self.manifest_path()
        m = json.loads(get(mp))
        m["versioni"]["immagini_in_esecuzione"]["superbot-desk-hawk"]["in_esecuzione"] = True
        put(mp, json.dumps(m))
        rc, out = self.check("post", sig)
        self.assertEqual(rc, 1, out)
        self.assertIn("il manifesto non registra entrambi i bot come non in esecuzione", out)

    def test_post_blocks_without_a_local_backup_repository(self):
        sig = self.backup()
        shutil.rmtree(os.path.join(self.work, "repo"))
        rc, out = self.check("post", sig)
        self.assertEqual(rc, 1, out)
        self.assertIn("repository locale dei backup assente", out)

    def test_post_blocks_when_the_brain_changed_during_the_backup(self):
        sig = self.backup()
        put(os.path.join(self.root, "hawk", "lessons.md"), "# cambiata\n")
        os.utime(os.path.join(self.root, "hawk", "lessons.md"), (time.time() - 3600,) * 2)
        rc, out = self.check("post", sig)
        self.assertEqual(rc, 1, out)
        self.assertIn("il cervello e' DIVERSO", out)


@unittest.skipUnless(HAVE_SH, "mancano sh/timeout")
class InstallWrapperTests(Base):
    """install-wrapper.sh su un finto /opt: cambia SOLO run.sh, non chiama systemd se non per leggere."""

    def setUp(self):
        super().setUp()
        t = self.td.name
        self.extb = os.path.join(t, "opt", "superbot-extbackup")
        self.fix = os.path.join(t, "root", "extbackup-fix-20261109")
        self.tools = os.path.join(t, "opt", "superbot-tools")
        for d in (self.extb, self.tools, os.path.join(t, "root"), os.path.join(self.extb, "repo", "archives")):
            os.makedirs(d, exist_ok=True)
        self.target = os.path.join(self.extb, "run.sh")
        put(self.target, OLD_RUN_SH, 0o700)
        for n in TOOL_NAMES:
            shutil.copy(os.path.join(HERE, n), os.path.join(self.tools, n))
        put(os.path.join(self.extb, "recipient.txt"), "age1prova\n", 0o600)
        put(os.path.join(self.extb, "known_hosts"), "github.com ssh-ed25519 AAAA\n", 0o600)
        put(os.path.join(self.extb, "status.json"), json.dumps({"ultimo_successo": "2026-11-02T03:20:00Z"}), 0o644)
        put(os.path.join(self.extb, "repo", "archives", "a.tar.gz.age"), b"cifrato-finto", 0o600)
        put(os.path.join(t, "root", "superbot-extbackup.service"), "[Service]\nExecStart=/opt/superbot-extbackup/run.sh\n")
        self.old_sha = hashlib.sha256(OLD_RUN_SH.encode()).hexdigest()
        self.new_sha = sha(RUN_SH)

    def snapshot(self, with_run_sh=False):
        """Tutto l'albero finto (file: impronta, modo, istante di modifica; cartelle: elenco dei nomi), tranne gli
        stati dei finti docker/systemd, i file del bot e (di norma) run.sh stesso."""
        skip = {self.dockerdir, self.sysdir, self.fakebin}
        out = {}
        for dp, dn, fn in os.walk(self.td.name):
            dn[:] = [d for d in dn if os.path.join(dp, d) not in skip]
            out[dp] = ("dir", tuple(sorted(dn + fn)))
            for f in fn:
                path = os.path.join(dp, f)
                if path == self.target and not with_run_sh:
                    continue
                st = os.stat(path)
                out[path] = (sha(path), st.st_mode, st.st_mtime_ns, st.st_size)
        return out

    def inst(self, *args, extra_path=None, **envx):
        e = self.env(SUPERBOT_EXTB=self.extb, SUPERBOT_FIXDIR=self.fix, **envx)
        if extra_path:
            e["PATH"] = extra_path + os.pathsep + e["PATH"]
        p = subprocess.run(["sh", INSTALL_SH, *args], capture_output=True, text=True, timeout=120, env=e)
        return p.returncode, p.stdout + p.stderr

    def test_embedded_hashes_are_consistent_with_the_repository(self):
        text = get(INSTALL_SH).decode()
        new = re.search(r"^EXPECTED_NEW=([0-9a-f]{64})$", text, re.M).group(1)
        old = re.search(r"^KNOWN_OLD=([0-9a-f]{64})$", text, re.M).group(1)
        self.assertEqual(new, self.new_sha, "l'impronta attesa in install-wrapper.sh non e' quella di run.sh")
        self.assertEqual(old, self.old_sha)
        chk = re.search(r"^EXPECTED_RUN_SH=([0-9a-f]{64})$", get(CHECK_SH).decode(), re.M).group(1)
        self.assertEqual(chk, new, "check-stopped-readonly.sh e install-wrapper.sh attendono run.sh diversi")
        self.assertNotIn("--bot-stopped", OLD_RUN_SH)
        self.assertIn("--bot-stopped", get(RUN_SH).decode())

    def test_dry_run_changes_nothing_not_even_a_directory(self):
        before = self.snapshot(with_run_sh=True)
        rc, out = self.inst("install")
        self.assertEqual(rc, 0, out)
        self.assertIn("ESITO: SIMULAZIONE RIUSCITA - nessuna modifica", out)
        self.assertEqual(before, self.snapshot(with_run_sh=True))
        self.assertFalse(os.path.exists(self.fix))
        rc, out = self.inst("status")
        self.assertEqual(rc, 0, out)
        self.assertEqual(before, self.snapshot(with_run_sh=True))

    def test_install_changes_only_run_sh_and_saves_the_original_once(self):
        before = self.snapshot()
        rc, out = self.inst("install", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("ESITO: INSTALLATO - solo run.sh modificato", out)
        after = self.snapshot()
        diff = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        self.assertEqual(diff, sorted([self.fix, os.path.join(self.td.name, "root"), os.path.join(self.fix, "run.sh.original"),
                                       os.path.join(self.fix, "run.sh.original.sha256")]),
                         "oltre a run.sh e alla cartella di salvataggio e' cambiato altro")
        self.assertEqual(sha(self.target), self.new_sha)
        self.assertEqual(oct(os.stat(self.target).st_mode & 0o777), "0o700")
        self.assertEqual(sha(os.path.join(self.fix, "run.sh.original")), self.old_sha)
        self.assertEqual(get(os.path.join(self.fix, "run.sh.original.sha256")).decode().split()[0], self.old_sha)
        self.assertEqual(sorted(os.listdir(self.extb)), ["known_hosts", "recipient.txt", "repo", "run.sh", "status.json"],
                         "restano file temporanei nella cartella del backup")
        calls = get(os.path.join(self.sysdir, "calls.log")).decode().splitlines()
        self.assertTrue(calls)
        self.assertTrue(all(c.startswith("is-active ") for c in calls), "chiamate a systemctl non di sola lettura: %s" % calls)

    def test_install_is_idempotent_and_never_overwrites_the_saved_original(self):
        self.assertEqual(self.inst("install", "--apply")[0], 0)
        saved = get(os.path.join(self.fix, "run.sh.original"))
        rc, out = self.inst("install", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("ESITO: GIA' INSTALLATO - nessuna modifica", out)
        self.assertEqual(get(os.path.join(self.fix, "run.sh.original")), saved)

    def test_if_the_setup_workflow_puts_the_old_wrapper_back_a_reinstall_works_and_the_original_stays(self):
        self.assertEqual(self.inst("install", "--apply")[0], 0)
        put(self.target, OLD_RUN_SH, 0o700)                         # sovrascrittura da parte del vecchio workflow
        rc, out = self.inst("install", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(sha(self.target), self.new_sha)
        self.assertEqual(sha(os.path.join(self.fix, "run.sh.original")), self.old_sha)

    def test_a_source_that_is_not_the_approved_file_is_refused(self):
        src = os.path.join(self.td.name, "src-diverso.sh")
        put(src, get(RUN_SH) + b"# un byte in piu'\n")
        before = self.snapshot(with_run_sh=True)
        rc, out = self.inst("install", "--apply", "--src", src)
        self.assertEqual(rc, 1, out)
        self.assertIn("file diverso da quello approvato", out)
        self.assertEqual(before, self.snapshot(with_run_sh=True))
        self.assertFalse(os.path.exists(self.fix))

    def test_an_unknown_installed_wrapper_is_not_replaced_blindly(self):
        put(self.target, "#!/bin/sh\necho versione-misteriosa\n", 0o700)
        h = sha(self.target)
        before = self.snapshot(with_run_sh=True)
        for label, env in (("senza accettazione", {}), ("abbreviata", {"SUPERBOT_ACCEPT_ORIGINAL_SHA": h[:16]}),
                           ("altra", {"SUPERBOT_ACCEPT_ORIGINAL_SHA": "0" * 64})):
            with self.subTest(label):
                rc, out = self.inst("install", "--apply", **env)
                self.assertEqual(rc, 1, out)
                self.assertIn("run.sh attuale ha sha256 %s" % h, out)
                self.assertIn("SUPERBOT_ACCEPT_ORIGINAL_SHA=%s" % h, out)
                self.assertEqual(before, self.snapshot(with_run_sh=True))
        rc, out = self.inst("install", "--apply", SUPERBOT_ACCEPT_ORIGINAL_SHA=h)
        self.assertEqual(rc, 0, out)
        self.assertEqual(sha(self.target), self.new_sha)
        self.assertEqual(sha(os.path.join(self.fix, "run.sh.original")), h)

    def test_a_different_saved_original_is_never_overwritten(self):
        os.makedirs(self.fix)
        put(os.path.join(self.fix, "run.sh.original"), "un altro originale\n", 0o700)
        rc, out = self.inst("install", "--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("c'e' gia' un originale salvato DIVERSO", out)
        self.assertEqual(get(os.path.join(self.fix, "run.sh.original")), b"un altro originale\n")
        self.assertEqual(sha(self.target), self.old_sha)

    def test_a_running_backup_service_or_process_blocks_the_install(self):
        for state in ("active", "activating", "reloading", ""):
            with self.subTest(stato=state):
                put(os.path.join(self.sysdir, "superbot-extbackup.service"), state)
                rc, out = self.inst("install", "--apply")
                self.assertEqual(rc, 1, out)
                self.assertIn("superbot-extbackup.service non e' fermo", out)
        os.unlink(os.path.join(self.sysdir, "superbot-extbackup.service"))
        fake = os.path.join(self.td.name, "strumenti-finti")
        os.makedirs(fake)
        put(os.path.join(fake, "backup_brain.py"), "import time\ntime.sleep(30)\n")
        real = subprocess.Popen([sys.executable, "-I", os.path.join(fake, "backup_brain.py")])
        try:
            time.sleep(0.5)
            rc, out = self.inst("install", "--apply")
            self.assertEqual(rc, 1, out)
            self.assertIn("c'e' un processo di backup in esecuzione", out)
        finally:
            _kill(real)
        self.assertEqual(sha(self.target), self.old_sha)

    def test_failed_service_is_not_an_obstacle(self):
        put(os.path.join(self.sysdir, "superbot-extbackup.service"), "failed")
        rc, out = self.inst("install", "--apply")
        self.assertEqual(rc, 0, out)

    def test_not_root_and_symlink_target_are_refused(self):
        rc, out = self.inst("install", "--apply", FAKE_UID="1000")
        self.assertEqual(rc, 1, out)
        self.assertIn("va eseguito come root", out)
        real = os.path.join(self.td.name, "altro-run.sh")
        shutil.move(self.target, real)
        os.symlink(real, self.target)
        rc, out = self.inst("install", "--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("non e' un file normale", out)
        self.assertEqual(sha(real), self.old_sha)

    def test_rollback_restores_the_exact_original_and_keeps_the_saved_copy(self):
        self.assertEqual(self.inst("install", "--apply")[0], 0)
        before = self.snapshot(with_run_sh=True)
        rc, out = self.inst("rollback")
        self.assertEqual(rc, 0, out)
        self.assertIn("SIMULAZIONE RIUSCITA", out)
        self.assertEqual(before, self.snapshot(with_run_sh=True))
        rc, out = self.inst("rollback", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("ESITO: RIPRISTINATO - solo run.sh modificato", out)
        self.assertEqual(sha(self.target), self.old_sha)
        self.assertEqual(oct(os.stat(self.target).st_mode & 0o777), "0o700")
        self.assertTrue(os.path.exists(os.path.join(self.fix, "run.sh.original")), "il rollback non deve cancellare nulla")
        rc, out = self.inst("rollback", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("GIA' RIPRISTINATO", out)
        self.assertEqual(sorted(os.listdir(self.extb)), ["known_hosts", "recipient.txt", "repo", "run.sh", "status.json"])

    def test_rollback_refuses_without_a_saved_original_or_with_a_damaged_copy_or_an_unknown_current_wrapper(self):
        rc, out = self.inst("rollback", "--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("nessun originale salvato", out)
        self.assertEqual(self.inst("install", "--apply")[0], 0)
        saved = os.path.join(self.fix, "run.sh.original")
        good = get(saved)
        put(saved, b"copia danneggiata\n")
        rc, out = self.inst("rollback", "--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("non coincide piu' con la sua impronta registrata", out)
        self.assertEqual(sha(self.target), self.new_sha)
        put(saved, good)
        put(self.target, "#!/bin/sh\necho modificato-da-altri\n", 0o700)
        rc, out = self.inst("rollback", "--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("non e' quello installato da questa procedura", out)

    def test_a_failure_before_the_rename_leaves_run_sh_untouched_and_no_temporary_file(self):
        shim = os.path.join(self.td.name, "shim-chown")
        os.makedirs(shim)
        put(os.path.join(shim, "chown"), "#!/bin/sh\nexit 1\n", 0o755)
        rc, out = self.inst("install", "--apply", extra_path=shim)
        self.assertEqual(rc, 1, out)
        self.assertIn("run.sh NON e' stato modificato", out)
        self.assertEqual(sha(self.target), self.old_sha)
        self.assertEqual(sorted(os.listdir(self.extb)), ["known_hosts", "recipient.txt", "repo", "run.sh", "status.json"])

    def test_a_bad_write_at_the_rename_is_detected_and_the_original_is_put_back_automatically(self):
        shim = os.path.join(self.td.name, "shim-mv")
        os.makedirs(shim)
        mark = os.path.join(self.td.name, "mv-gia-rotto")
        put(os.path.join(shim, "mv"),
            '#!/bin/sh\nfor a; do prev="$last"; last="$a"; done\ncase "$last" in\n  *run.sh) if [ ! -e "%s" ]; then touch "%s"; echo contenuto-sbagliato > "$last"; rm -f "$prev"; exit 0; fi ;;\nesac\nexec %s "$@"\n'
            % (mark, mark, shutil.which("mv")), 0o755)
        rc, out = self.inst("install", "--apply", extra_path=shim)
        self.assertEqual(rc, 1, out)
        self.assertIn("originale rimesso a posto", out)
        self.assertEqual(sha(self.target), self.old_sha)
        self.assertEqual(sorted(os.listdir(self.extb)), ["known_hosts", "recipient.txt", "repo", "run.sh", "status.json"])

    def test_the_setup_workflow_is_the_only_other_writer_of_the_wrapper_and_it_writes_the_same_bytes(self):
        pat = re.compile(r"(>|tee |cp |mv |install |scp )[^#\n]*(\$W|/opt/superbot-extbackup|extbackup)[^#\n]*run\.sh")
        skip = {os.path.basename(__file__), "install-wrapper.sh", "check-stopped-readonly.sh"}
        writers = []
        for base in (".github", "deploy", "ops"):
            for dp, _dn, fn in os.walk(os.path.join(REPO, base)):
                for f in fn:
                    if f in skip or not f.endswith((".yml", ".yaml", ".sh", ".py")):
                        continue
                    path = os.path.join(dp, f)
                    try:
                        text = get(path).decode()
                    except (OSError, UnicodeDecodeError):
                        continue
                    if pat.search(text):
                        writers.append(os.path.relpath(path, REPO))
        self.assertEqual(sorted(writers), [".github/workflows/sg-extbackup.yml"])
        wf = get(WORKFLOW).decode()
        m = re.search(r"cat > \"\$W/run\.sh\" <<'RUNSH'\n(.*?)\n {10}RUNSH\n", wf, re.S)
        inner = "\n".join(l[10:] if l.startswith(" " * 10) else l for l in m.group(1).split("\n")) + "\n"
        self.assertEqual(hashlib.sha256(inner.encode()).hexdigest(), self.new_sha)
        self.assertIn("deploy/sg-extbackup.trigger", wf)             # parte solo da questo file, su rule-pool


if __name__ == "__main__":
    unittest.main(verbosity=2)
