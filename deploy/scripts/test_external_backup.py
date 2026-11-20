"""Prove del backup esterno cifrato (external_backup.py) e del ripristino (restore_external_backup.py).

Si lanciano con:  python3 -m unittest deploy/scripts/test_external_backup.py -v
Servono i programmi `age`, `age-keygen` e `git` (nessun server, nessun segreto vero: chiavi e repository
"remoto" sono creati in cartelle temporanee). Se `age` manca le prove si SALTANO e lo dicono: installarlo.

Si controlla soprattutto che:
  - il repository dei backup riceva SOLO archivi cifrati (nessun testo in chiaro nei suoi oggetti git);
  - il ripristino completo con la chiave giusta funzioni e con la chiave sbagliata o un file alterato no;
  - se il backup del cervello non e' provabile non venga inviato niente;
  - la retention tolga i vecchi senza mai togliere i recenti;
  - il push non sia mai forzato e si rimetta in fila se il remoto e' avanzato.
"""
import gzip
import hashlib
import io
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(HERE, "external_backup.py")
RESTORE = os.path.join(HERE, "restore_external_backup.py")
HAVE_AGE = bool(shutil.which("age") and shutil.which("age-keygen") and shutil.which("git"))

M_LESSONS, M_TRADE, M_DB, M_STATE = "SEGRETO-LESSONS-7731", "SEGRETO-TRADE-7731", "SEGRETO-DB-7731", "SEGRETO-STATE-7731"
MARKERS = [m.encode() for m in (M_LESSONS, M_TRADE, M_DB, M_STATE)]


def load(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sh(*cmd, cwd=None, check=True, inp=None):
    p = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=inp is None, input=inp, timeout=120)
    if check and p.returncode != 0:
        raise AssertionError("%s -> %s" % (cmd, p.stdout if inp is None else p.stdout))
    return p


def put(path, data):
    with open(path, "wb" if isinstance(data, bytes) else "w") as f:
        f.write(data)


def get(path):
    with open(path, "rb") as f:
        return f.read()


def keygen(path):
    sh("age-keygen", "-o", path)
    os.chmod(path, 0o600)
    return sh("age-keygen", "-y", path).stdout.strip()


@unittest.skipUnless(HAVE_AGE, "mancano age/age-keygen/git: installare age per eseguire queste prove")
class ExternalBackupTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        t = self.td.name
        self.root = os.path.join(t, "data")
        self.work = os.path.join(t, "work")
        self.remote = os.path.join(t, "remote.git")
        self.ident = os.path.join(t, "id.txt")
        self.recfile = os.path.join(t, "recipient.txt")
        for p in ("hawk", "bull"):
            self.make_portfolio(p)
        self.app_db = os.path.join(t, "app.db")
        self.pool_db = os.path.join(t, "pool.db")
        for path in (self.app_db, self.pool_db):
            c = sqlite3.connect(path)
            c.execute("create table users(id integer primary key, name text)")
            c.executemany("insert into users(name) values(?)", [("%s-%d" % (M_DB, i),) for i in range(30)])
            c.commit()
            c.close()
        self.pub = keygen(self.ident)
        with open(self.recfile, "w") as f:
            f.write("# prova\n%s\n" % self.pub)
        sh("git", "init", "-q", "--bare", "-b", "main", self.remote)

    def tearDown(self):
        self.td.cleanup()

    def make_portfolio(self, p):
        d = os.path.join(self.root, p)
        os.makedirs(d, exist_ok=True)
        # forma reale (19/10): i trade chiusi della run stanno sia nello stato (main.closed) sia nello storico;
        # cassa = capitale iniziale + somma dei risultati quando non ci sono posizioni aperte
        t0 = 1760000000000
        trades = [{"id": i + 1, "run_no": 3, "open_ms": t0 + i * 60000, "close_ms": t0 + i * 60000 + 30000,
                   "net": round((i % 5 - 2) * 1.25, 4), "margin": 10.0, "leverage": 10, "entry": 100.0,
                   "exit": 100.0 + (i % 5 - 2), "fees": 0.12, "nota": M_TRADE} for i in range(40)]
        rows = "".join(json.dumps(t) + "\n" for t in trades)
        learn = "".join(json.dumps({"i": i, "run_no": 3, "portfolio": p, "nota": M_TRADE}) + "\n" for i in range(40))
        state = {"run_no": 3, "cycle": 5, "note": M_STATE,
                 "main": {"cash": 1000.0 + sum(t["net"] for t in trades), "positions": {}, "closed": trades,
                          "next_id": 41, "limits": {"start_equity": 1000.0}}}
        old = time.time() - 300
        for name, body in (("trade_history.jsonl", rows), ("learning_log.jsonl", learn), ("errors.md", "# e\n"),
                           ("lessons.md", "# %s\n" % M_LESSONS),
                           ("state_v2.json", json.dumps(state))):
            path = os.path.join(d, name)
            with open(path, "w") as f:
                f.write(body)
            os.utime(path, (old, old))
        self.heartbeat(p)

    def heartbeat(self, p, age=0, **over):
        now = time.time()
        hb = {"cycles": 12, "cycle_running": False, "last_start_ms": int((now - 90) * 1000),
              "last_end_ms": int((now - 60) * 1000), "next_cycle_ms": int((now + 1500) * 1000)}
        hb.update(over)
        path = os.path.join(self.root, p, "heartbeat.json")
        with open(path, "w") as f:
            json.dump(hb, f)
        os.utime(path, (now - age, now - age))

    def args(self, *extra):
        return [sys.executable, "-I", EXT, "--root", self.root, "--app-db", self.app_db, "--pool-db", self.pool_db,
                "--tools", HERE, "--work", self.work, "--remote", self.remote, "--recipient-file", self.recfile,
                "--app-repo", "/nonexistent", "--bots-repo", "/nonexistent", "--brain-retries", "0",
                "--brain-arg=--quiet-secs", "--brain-arg=1", "--brain-arg=--attempts", "--brain-arg=2",
                "--brain-arg=--wait", "--brain-arg=0.1", "--brain-arg=--quiet-timeout", "--brain-arg=2", *extra]

    def backup(self, *extra):
        p = subprocess.run(self.args(*extra), capture_output=True, text=True, timeout=300)
        return p.returncode, p.stdout + p.stderr

    def clone_remote(self):
        dst = os.path.join(self.td.name, "clone-%d" % int(time.time() * 1000))
        sh("git", "clone", "-q", self.remote, dst)
        return dst

    def archives(self, clone):
        out = []
        for dp, _dn, fn in os.walk(os.path.join(clone, "archives")):
            out += [os.path.join(dp, f) for f in fn if f.endswith(".tar.gz.age")]
        return sorted(out)

    def restore(self, archive, ident=None, out=None, *extra):
        out = out or os.path.join(self.td.name, "ripristino-%d" % int(time.time() * 1000))
        p = subprocess.run([sys.executable, "-I", RESTORE, "--archive", archive, "--identity", ident or self.ident,
                            "--out", out, *extra], capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout + p.stderr, out

    # ---- giro completo ----

    def test_full_round_trip_backup_then_restore(self):
        rc, out = self.backup()
        self.assertEqual(rc, 0, out)
        clone = self.clone_remote()
        (arc,) = self.archives(clone)
        rc, rout, dest = self.restore(arc)
        self.assertEqual(rc, 0, rout)
        self.assertIn("RISULTATO: OK", rout)
        self.assertIn("confine di ciclo VERIFICATO", rout)
        # i dati ripristinati sono quelli di partenza
        (snap,) = [d for d in os.listdir(os.path.join(dest, "dati", "cervello")) if d.startswith("bots-")]
        for p in ("hawk", "bull"):
            for n in ("trade_history.jsonl", "learning_log.jsonl", "lessons.md", "state_v2.json"):
                with open(os.path.join(self.root, p, n), "rb") as a, \
                        open(os.path.join(dest, "dati", "cervello", snap, p, n), "rb") as b:
                    self.assertEqual(hashlib.sha256(a.read()).hexdigest(), hashlib.sha256(b.read()).hexdigest())
        dbs = sorted(os.listdir(os.path.join(dest, "dati", "database")))
        self.assertEqual(len([d for d in dbs if d.startswith("app-")]), 1)
        self.assertEqual(len([d for d in dbs if d.startswith("pool-")]), 1)
        c = sqlite3.connect(os.path.join(dest, "dati", "database", [d for d in dbs if d.startswith("app-")][0]))
        self.assertEqual(c.execute("select count(*) from users").fetchone()[0], 30)

    def test_round_trip_includes_run_histories(self):
        run = os.path.join(self.td.name, "arena", "deepseek", "brain-deepseek-paper20261118")
        os.makedirs(os.path.join(run, "sub"))
        make_v3_journal(os.path.join(run, "journal.db"), 7).close()
        put(os.path.join(run, "sub", "trace.jsonl"), M_STATE)
        put(os.path.join(run, ".exit_service.lock"), "")
        rc, out = self.backup("--required-run-dir", run)
        self.assertEqual(rc, 0, out)
        clone = self.clone_remote()
        for dp, _dn, fn in os.walk(clone):                       # nel repository nessun dato in chiaro
            if ".git" in dp:
                continue
            for f in fn:
                self.assertFalse(any(m in get(os.path.join(dp, f)) for m in MARKERS), f)
        (arc,) = self.archives(clone)
        rc, rout, dest = self.restore(arc)
        self.assertEqual(rc, 0, rout)
        self.assertIn("journal V3 dati/runs/deepseek__brain-deepseek-paper20261118/journal.db: 7 eventi", rout)
        r = os.path.join(dest, "dati", "runs", "deepseek__brain-deepseek-paper20261118")
        self.assertEqual(sorted(os.listdir(r)), ["journal.db", "sub"])

    def test_restore_exit_codes_separate_semantic_from_technical(self):
        """Solo anomalie semantiche: uscita 3 (integro, NON certificato). Con un difetto tecnico: uscita 1."""
        path = os.path.join(self.root, "bull", "state_v2.json")
        with open(path) as f:
            st = json.load(f)
        st["main"]["cash"] += 5
        put(path, json.dumps(st).encode())
        old = time.time() - 300
        os.utime(path, (old, old))
        rc, out = self.backup()
        self.assertEqual(rc, 0, out)                                     # il backup conserva comunque tutto
        (arc,) = self.archives(self.clone_remote())
        rc, rout, _ = self.restore(arc)
        self.assertEqual(rc, 3, rout)
        self.assertIn("RISULTATO: INTEGRO MA NON CERTIFICATO", rout)
        self.assertIn("ANOMALIA SEMANTICA: bull: contabilita' incoerente", rout)
        self.assertNotIn("RISULTATO: OK", rout)
        bad = os.path.join(self.td.name, "manifesto-sbagliato.json")
        put(bad, json.dumps({"sha256": "0" * 64, "dimensione": 1}))
        rc, rout, _ = self.restore(arc, None, None, "--manifest", bad)
        self.assertEqual(rc, 1, rout)                                    # il tecnico prevale
        self.assertIn("RISULTATO: FALLITO (1 problemi tecnici, 1 anomalie semantiche)", rout)

    def test_an_unreadable_run_dir_sends_nothing(self):
        rc, out = self.backup("--required-run-dir", os.path.join(self.td.name, "manca"))
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.archives(self.clone_remote()), [])

    def _wrapper(self, drop=None, empty_journal=None, docker="true true", old_heartbeats=False):
        """prova_storici.sh con i percorsi /opt sostituiti da cartelle di prova e senza il controllo di root."""
        t = self.td.name
        o = os.path.join(t, "finto")
        runs = ["v3/brain-v3-paper20261111", "v3/brain-v3-rc20261106", "arena/deepseek/brain-deepseek-paper20261118",
                "arena/qwen/brain-qwen-paper20261118", "arena/minimax/brain-minimax-paper20261118"]
        for rel in runs:
            if rel == drop:
                continue
            os.makedirs(os.path.join(o, rel))
            if empty_journal and os.path.join(o, rel) == empty_journal:
                put(os.path.join(o, rel, "heartbeat.json"), "{}")       # run Arena senza journal
                continue
            make_v3_journal(os.path.join(o, rel, "journal.db"), 3).close()
        os.makedirs(os.path.join(o, "adaptive", "hawk"))
        c = sqlite3.connect(os.path.join(o, "adaptive", "hawk", "brain.sqlite3"))
        c.execute("create table t(x)"); c.execute("insert into t values(?)", (M_DB,)); c.commit(); c.close()
        os.makedirs(os.path.join(self.root, "brain"), exist_ok=True)
        put(os.path.join(self.root, "brain", "state.json"), '{"a":1}')
        src = open(os.path.join(HERE, "..", "extbackup", "prova_storici.sh")).read()
        subs = [('[ "$(id -u)" = 0 ] || { echo "NO-GO: serve root"; exit 2; }', ""),
                ("BASE=/root/extbackup-prova-storici", "BASE=%s/base" % t),
                ("df --output=avail -B1 /root", "df --output=avail -B1 %s" % t),
                ("DESK=/opt/superbot-desk-data", "DESK=%s" % self.root),
                ("/opt/superbot-v3-paper-runs", o + "/v3"), ("/opt/superbot-ai-arena-paper", o + "/arena"),
                ("/opt/superbot-brain-free/", o + "/free/"), ("/opt/superbot-brain-adaptive/", o + "/adaptive/"),
                ("/opt/superbot-ai-data/", o + "/aidata/"),
                ("/opt/superbot/data/superbot.db", self.app_db), ("/opt/superbot-pool-data/pool.db", self.pool_db),
                ("--app-repo /opt/superbot --bots-repo /opt/superbot-desk",
                 "--app-repo /nonexistent --bots-repo /nonexistent --brain-retries 0 --brain-arg=--quiet-secs "
                 "--brain-arg=1 --brain-arg=--attempts --brain-arg=2 --brain-arg=--wait --brain-arg=0.1 "
                 "--brain-arg=--quiet-timeout --brain-arg=2")]
        for x, y in subs:
            self.assertIn(x, src)
            src = src.replace(x, y)
        self.assertNotIn("/opt/", src)                                     # nessun percorso reale nel test
        script = os.path.join(t, "prova.sh")
        put(script, src)
        # finto docker: stato dei container classici (hawk, bull) per la scelta della modalita' del cervello
        fb = os.path.join(t, "fakebin")
        os.makedirs(fb, exist_ok=True)
        h, b = docker.split()
        put(os.path.join(fb, "docker"), "#!/bin/sh\ncase \"$*\" in *hawk*) s=%s;; *bull*) s=%s;; *) s=x;; esac\n"
            "[ \"$s\" = x ] && { echo 'Error: No such object' >&2; exit 1; }\necho $s\n" % (h, b))
        os.chmod(os.path.join(fb, "docker"), 0o755)
        if old_heartbeats:
            old = time.time() - 7 * 86400
            for p in ("hawk", "bull"):
                os.utime(os.path.join(self.root, p, "heartbeat.json"), (old, old))
        env = dict(os.environ, PATH=fb + os.pathsep + os.environ["PATH"])
        return subprocess.run(["sh", script, HERE], capture_output=True, text=True, timeout=300, env=env)

    def test_admin_wrapper_end_to_end_without_root(self):
        p = self._wrapper()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        for x in ("ESITO PROVA: OK", "RISULTATO: OK", "== spazio:", "(obbligatorio)", "sottocartelle"):
            self.assertIn(x, p.stdout)
        self.assertEqual(p.stdout.count("ripristinata"), 7, p.stdout)       # 5 run + Brain storico + adattivo
        self.assertEqual(p.stdout.count(": 3 eventi, catena verificata"), 5, p.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.td.name, "base")))  # tutto cancellato
        self.assertFalse(any(m.decode() in p.stdout for m in MARKERS))        # nessun contenuto stampato

    def test_admin_wrapper_uses_bot_stopped_when_both_classics_are_stopped(self):
        p = self._wrapper(docker="false false", old_heartbeats=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("entrambi fermi -> --bot-stopped", p.stdout)
        self.assertIn("ESITO PROVA: OK", p.stdout)

    def test_admin_wrapper_refuses_mixed_or_unverifiable_classic_states(self):
        for state in ("true false", "false true", "x x"):
            p = self._wrapper(docker=state)
            self.assertNotEqual(p.returncode, 0, state)
            self.assertIn("NO-GO: stato di Falco/Toro misto o non verificabile", p.stdout)
            self.assertFalse(os.path.exists(os.path.join(self.td.name, "base")))
            shutil.rmtree(os.path.join(self.td.name, "finto"), ignore_errors=True)

    def test_bot_stopped_still_refuses_a_fresh_heartbeat(self):
        """docker dice fermo ma il battito e' fresco: backup_brain.py non accetta la copia (controllo non indebolito)."""
        p = self._wrapper(docker="false false", old_heartbeats=False)
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertIn("NO-GO: backup", p.stdout)

    def test_admin_wrapper_passes_on_the_real_bot_shape(self):
        self.bot_shape("hawk", vault=37.5)
        self.bot_shape("bull", vault=12.25)
        p = self._wrapper()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("ESITO PROVA: OK", p.stdout)

    def test_admin_wrapper_reports_semantic_anomalies_as_not_certified_and_keeps_only_the_text_logs(self):
        self.edit_state("bull", lambda st: st["main"].__setitem__("cash", st["main"]["cash"] + 5))
        self.edit_state("hawk", lambda st: st["main"]["closed"].pop())
        p = self._wrapper()
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)                    # non e' un successo
        self.assertIn("ANOMALIA SEMANTICA: bull: contabilita' incoerente", p.stdout)
        self.assertIn("ANOMALIA SEMANTICA: hawk: i trade chiusi nello stato (39)", p.stdout)
        self.assertIn("RISULTATO: INTEGRO MA NON CERTIFICATO", p.stdout)
        self.assertIn("ESITO PROVA: INTEGRITA' TECNICA OK, SEMANTICA DI FALCO/TORO NON CERTIFICATA", p.stdout)
        self.assertNotIn("ESITO PROVA: OK", p.stdout)
        self.assertEqual(p.stdout.count(": 3 eventi, catena verificata"), 5, p.stdout)   # V3 comunque verificati
        self.assertNotIn("resta per l'esame", p.stdout)
        t = self.td.name
        self.assertFalse(os.path.exists(os.path.join(t, "base")))                 # dati in chiaro cancellati
        logs = [f for f in os.listdir(t) if f.startswith("base-") and f.endswith(".log")]
        self.assertEqual(len(logs), 1, os.listdir(t))
        path = os.path.join(t, logs[0])
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode) & 0o077, 0)          # solo il proprietario
        body = open(path, "rb").read()
        self.assertIn(b"ANOMALIA SEMANTICA: bull", body)
        self.assertFalse(any(m in body for m in MARKERS))                         # nessun contenuto
        self.assertNotIn(b"AGE-SECRET-KEY", body)                                 # nessuna chiave
        self.assertIn(logs[0], p.stdout)

    def test_admin_wrapper_refuses_when_an_arena_run_has_no_journal(self):
        t = self.td.name
        p0 = os.path.join(t, "finto", "arena", "minimax", "brain-minimax-paper20261118")
        p = self._wrapper(empty_journal=p0)
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertIn("NO-GO: backup", p.stdout)
        self.assertFalse(os.path.exists(os.path.join(t, "base")))

    def test_admin_wrapper_refuses_when_a_required_archive_is_missing(self):
        p = self._wrapper(drop="arena/qwen/brain-qwen-paper20261118")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("NO-GO: archivio obbligatorio mancante", p.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.td.name, "base")))

    def test_repository_contains_only_encrypted_archives_and_minimal_manifest(self):
        self.assertEqual(self.backup()[0], 0)
        clone = self.clone_remote()
        names = []
        for dp, dn, fn in os.walk(clone):
            dn[:] = [d for d in dn if d != ".git"]
            names += [os.path.relpath(os.path.join(dp, f), clone) for f in fn]
        for n in names:
            self.assertTrue(n in ("LEGGIMI.md", "recipient.txt") or n.endswith(".tar.gz.age")
                            or n.endswith(".manifest.json"), "file inatteso nel repository: " + n)
        # nessun testo in chiaro in NESSUN oggetto git (storia compresa)
        self.assertEqual(self.plaintext_hits(self.remote), [])
        # il manifesto pubblico dice come verificare, senza segreti
        (arc,) = self.archives(clone)
        with open(arc[: -len(".tar.gz.age")] + ".manifest.json") as f:
            man = json.load(f)
        self.assertEqual(man["sha256"], hashlib.sha256(get(arc)).hexdigest())
        self.assertEqual(man["cifratura"]["destinatario"], self.pub)
        self.assertNotIn("AGE-SECRET-KEY", json.dumps(man))
        with open(self.ident) as f:
            secret = [l.strip() for l in f if l.startswith("AGE-SECRET-KEY")][0]
        for n in names:
            with open(os.path.join(clone, n), "rb") as f:
                self.assertNotIn(secret.encode(), f.read())

    def plaintext_hits(self, gitdir):
        hits = []
        objs = sh("git", "-C", gitdir, "cat-file", "--batch-all-objects", "--batch-check").stdout.split("\n")
        for line in objs:
            if not line.strip():
                continue
            oid, typ = line.split()[:2]
            if typ != "blob":
                continue
            data = subprocess.run(["git", "-C", gitdir, "cat-file", "blob", oid], capture_output=True).stdout
            for cand in (data, self._gunzip(data)):
                for m in MARKERS:
                    if m in cand:
                        hits.append((oid, m))
        return hits

    @staticmethod
    def _gunzip(data):
        try:
            return gzip.decompress(data)
        except (OSError, EOFError):
            return b""

    def test_plaintext_scanner_is_not_vacuous(self):
        # controprova: se nel repository finisse del testo in chiaro (o compresso) lo scanner lo vedrebbe
        bare = os.path.join(self.td.name, "control.git")
        sh("git", "init", "-q", "--bare", "-b", "main", bare)
        wc = os.path.join(self.td.name, "control")
        sh("git", "clone", "-q", bare, wc)
        with open(os.path.join(wc, "chiaro.txt"), "w") as f:
            f.write(M_LESSONS)
        with open(os.path.join(wc, "compresso.gz"), "wb") as f:
            f.write(gzip.compress(M_DB.encode()))
        sh("git", "-C", wc, "add", "-A")
        sh("git", "-C", wc, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x")
        sh("git", "-C", wc, "push", "-q", "origin", "main")
        self.assertEqual(len(self.plaintext_hits(bare)), 2)

    def test_work_folder_keeps_no_plaintext_after_success(self):
        self.assertEqual(self.backup()[0], 0)
        left = os.listdir(self.work)
        self.assertFalse([n for n in left if n.startswith("staging")], left)
        self.assertFalse([n for n in left if n.endswith(".tar.gz") or n.endswith(".age")], left)
        with open(os.path.join(self.work, "status.json")) as f:
            st = json.load(f)
        self.assertIsNone(st["ultimo_errore"])
        self.assertTrue(st["archivio"].endswith(".tar.gz.age"))

    # ---- sicurezza del ripristino ----

    def test_wrong_key_cannot_restore(self):
        self.assertEqual(self.backup()[0], 0)
        (arc,) = self.archives(self.clone_remote())
        other = os.path.join(self.td.name, "altra.txt")
        keygen(other)
        rc, out, _ = self.restore(arc, ident=other)
        self.assertEqual(rc, 1, out)
        self.assertIn("decifratura non riuscita", out)

    def test_tampered_archive_is_rejected_by_hash_and_by_age(self):
        self.assertEqual(self.backup()[0], 0)
        (arc,) = self.archives(self.clone_remote())
        bad = os.path.join(self.td.name, "alterato.tar.gz.age")
        data = bytearray(get(arc))
        data[len(data) // 2] ^= 0xFF
        with open(bad, "wb") as f:
            f.write(data)
        shutil.copy(arc[: -len(".tar.gz.age")] + ".manifest.json", bad[: -len(".tar.gz.age")] + ".manifest.json")
        rc, out, _ = self.restore(bad)
        self.assertEqual(rc, 1, out)
        self.assertIn("NON coincide col manifesto", out)
        # senza manifesto, e' la cifratura autenticata di age a fermarlo
        os.unlink(bad[: -len(".tar.gz.age")] + ".manifest.json")
        rc, out, _ = self.restore(bad)
        self.assertEqual(rc, 1, out)
        self.assertIn("decifratura non riuscita", out)

    def encrypted_tar(self, builder, name="x.tar.gz.age"):
        plain = os.path.join(self.td.name, "x.tar.gz")
        with gzip.open(plain, "wb") as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                builder(tar)
        out = os.path.join(self.td.name, name)
        sh("age", "-r", self.pub, "-o", out, plain)
        return out

    def test_restore_refuses_path_traversal_and_links(self):
        def evil(tar):
            data = b"x"
            ti = tarfile.TarInfo("dati/../../fuori.txt")
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))
            ln = tarfile.TarInfo("dati/link")
            ln.type = tarfile.SYMTYPE
            ln.linkname = "/etc/passwd"
            tar.addfile(ln)
        arc = self.encrypted_tar(evil)
        out = os.path.join(self.td.name, "fuori-test", "ripristino")
        rc, rout, _ = self.restore(arc, out=out)
        self.assertEqual(rc, 1, rout)
        self.assertIn("pericoloso", rout)
        self.assertFalse(os.path.exists(os.path.join(self.td.name, "fuori-test", "fuori.txt")))
        self.assertFalse(os.path.exists(os.path.join(out, "dati", "link")))

    def test_restore_detects_content_different_from_internal_manifest(self):
        def build(tar):
            body = b"contenuto"
            ti = tarfile.TarInfo("dati/database/app-1.db")
            ti.size = len(body)
            tar.addfile(ti, io.BytesIO(body))
            man = json.dumps({"formato": 1, "file": [{"file": "dati/database/app-1.db", "size": len(body),
                                                      "sha256": "0" * 64}]}).encode()
            mi = tarfile.TarInfo("INTERNAL-MANIFEST.json")
            mi.size = len(man)
            tar.addfile(mi, io.BytesIO(man))
        rc, out, _ = self.restore(self.encrypted_tar(build))
        self.assertEqual(rc, 1, out)
        self.assertIn("diverso dal manifesto interno", out)

    def test_restore_refuses_non_empty_output_folder(self):
        self.assertEqual(self.backup()[0], 0)
        (arc,) = self.archives(self.clone_remote())
        full = os.path.join(self.td.name, "piena")
        os.makedirs(full)
        put(os.path.join(full, "x"), "")
        rc, out, _ = self.restore(arc, out=full)
        self.assertEqual(rc, 1, out)

    def test_restore_detects_incomplete_jsonl_inside_a_valid_archive(self):
        # un archivio cifrato bene ma con un registro troncato: il ripristino deve segnalarlo
        with open(os.path.join(self.root, "hawk", "trade_history.jsonl"), "ab") as f:
            f.write(b'{"i": 99, "nota"')
        old = time.time() - 300
        os.utime(os.path.join(self.root, "hawk", "trade_history.jsonl"), (old, old))
        rc, out = self.backup()
        self.assertEqual(rc, 1, out)                       # gia' il backup del cervello si rifiuta
        self.assertEqual(self.archives(self.clone_remote()), [])

    # ---- non si invia niente se il cervello non e' provabile ----

    def test_unverifiable_brain_uploads_nothing_and_leaves_no_plaintext(self):
        self.heartbeat("hawk", age=600)                    # battito vecchio: confine di ciclo non verificabile
        rc, out = self.backup()
        self.assertEqual(rc, 1, out)
        self.assertIn("RISULTATO: FALLITO", out)
        self.assertEqual(self.archives(self.clone_remote()), [])
        left = os.listdir(self.work)
        self.assertFalse([n for n in left if n.startswith("staging") or n.endswith(".age")], left)
        with open(os.path.join(self.work, "status.json")) as f:
            self.assertIn("cervello", json.load(f)["ultimo_errore"])

    def test_missing_required_file_uploads_nothing(self):
        os.remove(os.path.join(self.root, "bull", "lessons.md"))
        self.assertEqual(self.backup()[0], 1)
        self.assertEqual(self.archives(self.clone_remote()), [])

    def test_missing_database_uploads_nothing(self):
        os.remove(self.pool_db)
        self.assertEqual(self.backup()[0], 1)
        self.assertEqual(self.archives(self.clone_remote()), [])

    def test_invalid_recipient_fails_before_anything(self):
        with open(self.recfile, "w") as f:
            f.write("non-una-chiave\n")
        rc, out = self.backup()
        self.assertEqual(rc, 1, out)
        self.assertIn("non e' una chiave pubblica age valida", out)
        self.assertFalse(os.path.isdir(os.path.join(self.work, "staging")))

    def test_second_run_while_first_is_running_is_refused(self):
        import fcntl
        os.makedirs(self.work, exist_ok=True)
        fd = os.open(os.path.join(self.work, ".lock"), os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            rc, out = self.backup()
        finally:
            os.close(fd)
        self.assertEqual(rc, 1, out)
        self.assertIn("gia' in corso", out)

    def test_ssh_key_requires_known_hosts(self):
        rc, out = self.backup("--ssh-key", "/nonexistent")
        self.assertEqual(rc, 1, out)
        self.assertIn("known-hosts", out)

    # ---- repository: push, retention ----

    def test_two_runs_add_two_archives_and_never_rewrite_history(self):
        self.assertEqual(self.backup()[0], 0)
        time.sleep(1.1)                                    # il nome contiene l'ora al secondo
        self.assertEqual(self.backup()[0], 0)
        clone = self.clone_remote()
        self.assertEqual(len(self.archives(clone)), 2)
        log = sh("git", "-C", clone, "log", "--format=%s").stdout.strip().split("\n")
        self.assertEqual(len(log), 2)

    def test_push_is_never_forced(self):
        with open(EXT) as f:
            src = f.read()
        self.assertNotIn("--force", src)
        self.assertNotIn("push\", \"-f", src)
        self.assertNotRegex(src, r"\"\+refs|\+main")

    def test_push_rejected_because_remote_advanced_is_rebased_not_forced(self):
        ext = load(EXT, "ext_mod")

        class A:                                           # argomenti minimi per Repo
            work, remote, ssh_key, known_hosts = self.work, self.remote, "", ""

        os.makedirs(self.work)
        # remoto con un primo commit
        seed = os.path.join(self.td.name, "seed")
        sh("git", "clone", "-q", self.remote, seed)
        put(os.path.join(seed, "a.txt"), "a")
        sh("git", "-C", seed, "add", "-A")
        sh("git", "-C", seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "a")
        sh("git", "-C", seed, "push", "-q", "origin", "main")
        repo = ext.Repo(A)
        repo.sync()
        # nel frattempo qualcun altro spinge un commit sul remoto
        put(os.path.join(seed, "b.txt"), "b")
        sh("git", "-C", seed, "add", "-A")
        sh("git", "-C", seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "b")
        sh("git", "-C", seed, "push", "-q", "origin", "main")
        put(os.path.join(repo.dir, "c.txt"), "c")
        self.assertTrue(repo.publish("c"))
        clone = self.clone_remote()
        self.assertEqual(sorted(n for n in os.listdir(clone) if n.endswith(".txt")), ["a.txt", "b.txt", "c.txt"])

    # ---- casi 3 e 4 di ChatGPT (19/10 pomeriggio) ----

    def test_remote_verification_uses_a_fresh_clone_not_local_objects(self):
        """Se GitHub NON avesse davvero l'archivio, la verifica deve accorgersene anche se in locale c'e'."""
        self.assertEqual(self.backup()[0], 0)
        ext = load(EXT, "ext_mod_verify")

        class A:
            work, remote, ssh_key, known_hosts = self.work, self.remote, "", ""

        repo = ext.Repo(A)
        clone = self.clone_remote()
        (arc,) = self.archives(clone)
        rel = os.path.relpath(arc, clone).replace(os.sep, "/")
        digest = hashlib.sha256(get(arc)).hexdigest()
        self.assertTrue(repo.verify_remote(rel, digest))               # caso buono
        blob = sh("git", "-C", repo.dir, "rev-parse", "HEAD:" + rel).stdout.strip()
        loose = os.path.join(self.remote, "objects", blob[:2], blob[2:])
        self.assertTrue(os.path.exists(loose))
        os.remove(loose)                                               # il "server" perde l'archivio
        # il vecchio metodo (oggetti locali) direbbe ancora di si'...
        sh("git", "-C", repo.dir, "fetch", "-q", "origin")
        self.assertEqual(hashlib.sha256(subprocess.run(["git", "-C", repo.dir, "show", "origin/main:" + rel],
                                                       capture_output=True).stdout).hexdigest(), digest)
        # ...la verifica con clone nuovo no
        with self.assertRaises(ext.Fail):
            repo.verify_remote(rel, digest)
        self.assertFalse([d for d in os.listdir(self.work) if d.startswith("verifica-")])   # niente avanzi

    def test_manifest_records_running_images_and_declared_bot_versions_and_status_has_size(self):
        for pf in ("hawk", "bull"):
            self.heartbeat(pf, version="abc1234-" + pf)
        fake = os.path.join(self.td.name, "docker")
        put(fake, "#!/bin/sh\necho \"sha256:img-$4|superbot-desk:singapore|true\"\n")
        os.chmod(fake, 0o755)
        rc, out = self.backup("--docker-bin", fake)
        self.assertEqual(rc, 0, out)
        clone = self.clone_remote()
        (arc,) = self.archives(clone)
        with open(arc[: -len(".tar.gz.age")] + ".manifest.json") as f:
            v = json.load(f)["versioni"]
        self.assertEqual(v["versione_dichiarata_dai_bot"]["hawk"]["versione"], "abc1234-hawk")
        self.assertEqual(v["versione_dichiarata_dai_bot"]["bull"]["versione"], "abc1234-bull")
        imgs = v["immagini_in_esecuzione"]
        self.assertEqual(sorted(imgs), ["superbot", "superbot-desk-bull", "superbot-desk-hawk", "superbot-pool"])
        self.assertEqual(imgs["superbot-desk-hawk"]["id_immagine"], "sha256:img-superbot-desk-hawk")
        self.assertTrue(imgs["superbot-desk-hawk"]["in_esecuzione"])
        with open(os.path.join(self.work, "status.json")) as f:
            st = json.load(f)
        self.assertGreater(st["repo_git_byte"], 0)
        self.assertEqual(st["archivi_visibili"], 1)
        self.assertEqual(st["verifica"], "clone nuovo e indipendente da GitHub")

    # ---- caso 5 di ChatGPT: confine di ciclo obbligatorio e coerenza semantica nel ripristino ----

    def brain_snapshot(self):
        """Una copia vera del cervello fatta da backup_brain.py, in una cartella come quella del ripristino."""
        out = os.path.join(self.td.name, "rip")
        cerv = os.path.join(out, "dati", "cervello")
        os.makedirs(cerv)
        p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "backup_brain.py"), "--root", self.root,
                            "--dir", cerv, "--quiet-secs", "1", "--attempts", "2", "--wait", "0.1",
                            "--quiet-timeout", "2"], capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        (snap,) = [d for d in os.listdir(cerv) if d.startswith("bots-")]
        return out, os.path.join(cerv, snap)

    def check(self, out):
        mod = load(RESTORE, "restore_mod_%d" % int(time.time() * 1e6))
        probs = mod.Problems()
        buf = io.StringIO()
        old, sys.stdout = sys.stdout, buf
        try:
            mod.check_brain(out, probs)
        finally:
            sys.stdout = old
        self.last_technical, self.last_semantic = list(probs), list(probs.semantic)
        return list(probs) + list(probs.semantic), buf.getvalue()

    def edit_state(self, p, fn):
        path = os.path.join(self.root, p, "state_v2.json")
        with open(path) as f:
            st = json.load(f)
        fn(st)
        put(path, json.dumps(st).encode())
        old = time.time() - 300
        os.utime(path, (old, old))

    def test_semantic_check_passes_on_coherent_data(self):
        out, _ = self.brain_snapshot()
        probs, text = self.check(out)
        self.assertEqual(probs, [], text)
        self.assertIn("coerenza hawk: run 3 | 40 trade chiusi | 0 posizioni aperte", text)

    def test_restore_requires_verified_boundary_or_declared_exception(self):
        out, snap = self.brain_snapshot()
        mpath = os.path.join(snap, "MANIFEST.json")
        with open(mpath) as f:
            man = json.load(f)
        man["coerenza"]["confine_di_ciclo_verificato"] = False
        man["coerenza"]["modalita"] = "sconosciuta"
        put(mpath, json.dumps(man).encode())
        probs, _ = self.check(out)
        self.assertTrue(any("confine di ciclo verificato" in x for x in probs), probs)
        man["coerenza"]["modalita"] = "bot_fermo"                      # eccezione ammessa: passa e lo dice
        put(mpath, json.dumps(man).encode())
        probs, text = self.check(out)
        self.assertEqual(probs, [], text)
        self.assertIn("ECCEZIONE AMMESSA", text)

    def bot_shape(self, p, vault=0.0, tag=None):
        """Forma prodotta dal bot reale: righe dello storico SENZA run_no (engine.py non le etichetta, cli.py
        archivia lo storico a ogni nuova run) e, con il salvadanaio, denaro spostato dalla cassa al vault."""
        path = os.path.join(self.root, p, "trade_history.jsonl")
        with open(path) as f:
            rows = [json.loads(x) for x in f if x.strip()]
        for r in rows:
            r.pop("run_no", None)
            if tag is not None:
                r["run_no"] = tag
        put(path, "".join(json.dumps(r) + "\n" for r in rows).encode())
        old = time.time() - 300
        os.utime(path, (old, old))

        def move(st):
            for c in st["main"]["closed"]:
                c.pop("run_no", None)
            st["main"]["cash"] -= vault
            st["capital"] = {"schema_version": 1, "policy": "salvadanaio-only-v1",
                             "vault": {"balance": "%.2f" % vault, "pending": [], "revision": 3}}
        self.edit_state(p, move)
        jp = os.path.join(self.root, p, "salvadanaio-journal.jsonl")    # richiesto da backup_brain.py
        put(jp, (json.dumps({"schema": 1, "bot": p, "cash_delta": "%.2f" % -vault}) + "\n").encode())
        os.utime(jp, (old, old))

    def test_semantic_check_accepts_the_real_bot_shape(self):
        """Riproduce il NO-GO della prova reale: storico senza run_no e salvadanaio facevano fallire due controlli
        per portafoglio (4 problemi) su dati coerenti."""
        self.bot_shape("hawk", vault=37.5)
        self.bot_shape("bull", vault=12.25)
        out, _ = self.brain_snapshot()
        probs, text = self.check(out)
        self.assertEqual(probs, [], text)
        self.assertIn("coerenza hawk: run 3 | 40 trade chiusi | 0 posizioni aperte", text)
        self.assertIn("cassa + salvadanaio + posizioni aperte = capitale iniziale + variazioni di cassa", text)

    def test_semantic_check_still_catches_wrong_accounting_with_the_vault(self):
        self.bot_shape("hawk", vault=37.5)
        self.edit_state("hawk", lambda st: st["capital"]["vault"].__setitem__("balance", "40.00"))
        out, _ = self.brain_snapshot()
        probs, _ = self.check(out)
        self.assertTrue(any("hawk: contabilita' incoerente" in x for x in probs), probs)

    def test_semantic_check_refuses_an_unreadable_or_negative_vault(self):
        for bad in ("-1", "abc", None):
            self.bot_shape("bull", vault=5.0)
            self.edit_state("bull", lambda st: st["capital"].__setitem__("vault", {"balance": bad}))
            out, _ = self.brain_snapshot()
            probs, _ = self.check(out)
            self.assertTrue(any("bull: contabilita' non verificabile: saldo del salvadanaio illeggibile" in x
                                for x in probs), (bad, probs))
            shutil.rmtree(out)

    def test_semantic_check_catches_an_untagged_history_row_missing_from_the_state(self):
        self.bot_shape("hawk")
        self.edit_state("hawk", lambda st: st["main"]["closed"].pop())
        out, _ = self.brain_snapshot()
        probs, _ = self.check(out)
        self.assertTrue(any("hawk: i trade chiusi nello stato (39)" in x and "1 solo nello storico" in x
                            for x in probs), probs)

    def test_semantic_check_still_flags_history_of_a_later_run(self):
        self.bot_shape("bull", tag=4)                                    # stato run 3, storico run 4
        out, _ = self.brain_snapshot()
        probs, _ = self.check(out)
        self.assertTrue(any("bull:" in x and "run successiva" in x for x in probs), probs)

    def _absorbed_loss(self, st):
        """Un trade perso oltre il margine senza liquidazione: net -14.12, ma la cassa perde solo 10 + 0.06."""
        c = st["main"]["closed"][0]
        old_net = c["net"]
        c.update(net=-14.12, exit=86.0, fees=0.0516 + 0.06)                      # fee_close 0.0516, fee_open 0.06
        st["main"]["cash"] += -(10.0 + 0.06) - old_net

    def test_engine_accounting_absorbs_a_loss_beyond_the_margin(self):
        self.edit_state("hawk", self._absorbed_loss)
        path = os.path.join(self.root, "hawk", "trade_history.jsonl")          # stesso record nello storico
        with open(path) as f:
            rows = [json.loads(x) for x in f if x.strip()]
        rows[0].update(net=-14.12, exit=86.0, fees=0.0516 + 0.06)
        put(path, "".join(json.dumps(r) + "\n" for r in rows).encode())
        old = time.time() - 300
        os.utime(path, (old, old))
        out, _ = self.brain_snapshot()
        probs, text = self.check(out)
        self.assertEqual(probs, [], text)
        self.assertIn("perdite oltre il margine assorbite: 1 trade, 4.0600", text)    # 14.12 - (10 + 0.06)

    def test_engine_accounting_counts_open_positions_exactly(self):
        def opened(st):
            st["main"]["positions"] = {"BTCUSDT": {"id": 41, "total_margin": 20.0, "fee_open": 0.12}}
            st["main"]["next_id"] = 42
            st["main"]["cash"] -= 20.12
        self.edit_state("bull", opened)
        out, _ = self.brain_snapshot()
        probs, text = self.check(out)
        self.assertEqual(probs, [], text)
        self.edit_state("bull", lambda st: st["main"].__setitem__("cash", st["main"]["cash"] - 3))   # 3 spariti
        shutil.rmtree(out)
        out, _ = self.brain_snapshot()
        probs, _ = self.check(out)
        self.assertTrue(any("bull: contabilita' incoerente" in x and "(diff -3.0000)" in x for x in probs), probs)

    def test_semantic_anomalies_are_classified_apart_from_technical_defects(self):
        self.edit_state("bull", lambda st: st["main"].__setitem__("cash", st["main"]["cash"] + 5))
        out, _ = self.brain_snapshot()
        self.check(out)
        self.assertEqual(self.last_technical, [])
        self.assertTrue(any("bull: contabilita' incoerente" in x for x in self.last_semantic))

    def test_a_record_without_cash_fields_is_not_verifiable(self):
        self.edit_state("hawk", lambda st: st["main"]["closed"][3].pop("entry"))
        out, _ = self.brain_snapshot()
        probs, _ = self.check(out)
        self.assertTrue(any("hawk: contabilita' non verificabile: record di chiusura" in x for x in probs), probs)

    def test_read_only_diagnostic_explains_accounting_and_extra_history(self):
        diag = os.path.join(HERE, "..", "extbackup", "diagnosi_classici.py")
        self.bot_shape("hawk", vault=37.5)
        self.edit_state("hawk", self._absorbed_loss)
        path = os.path.join(self.root, "hawk", "trade_history.jsonl")
        with open(path) as f:
            rows = [json.loads(x) for x in f if x.strip()]
        rows[0].update(net=-14.12, exit=86.0, fees=0.0516 + 0.06)
        old_rows = [dict(r, id=r["id"], open_ms=r["open_ms"] - 10 ** 9, close_ms=r["close_ms"] - 10 ** 9)
                    for r in rows[:3]]                                   # 3 trade di una run precedente
        put(path, "".join(json.dumps(r) + "\n" for r in old_rows + rows).encode())
        os.makedirs(os.path.join(self.root, "hawk", "archive", "20261001-000000"))
        put(os.path.join(self.root, "hawk", "archive", "20261001-000000", "trade_history.jsonl"),
            "".join(json.dumps(r) + "\n" for r in old_rows))
        put(os.path.join(self.root, "hawk", "archive", "20261001-000000", "state_v2.json"), '{"run_no": 2}')
        self.edit_state("hawk", lambda st: st.__setitem__("run_started_ms", 1760000000000 - 1))

        def snapshot():
            out = {}
            for dp, _dn, fn in os.walk(self.root):
                for f in fn:
                    q = os.path.join(dp, f)
                    out[q] = (os.stat(q).st_mtime_ns, open(q, "rb").read())
            return out
        before = snapshot()
        p = subprocess.run([sys.executable, "-I", diag, HERE, self.root], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(snapshot(), before)                             # nulla scritto, nulla toccato
        o = p.stdout
        self.assertIn("perdite oltre il margine assorbite dal motore: 1 trade, 4.0600", o)
        self.assertIn("con la regola del motore 0.0000", o)
        self.assertIn("differenza con la regola semplice (net) 4.0600", o)
        self.assertIn("solo nello storico 3", o)
        self.assertIn("aperti prima dell'inizio della run corrente", o)
        self.assertIn("di cui 'solo nello storico' attuale 3", o)
        self.assertIn("salvadanaio: policy salvadanaio-only-v1", o)
        self.assertFalse(any(m.decode() in o for m in MARKERS))          # nessun contenuto

    def test_semantic_check_catches_state_and_history_out_of_sync(self):
        self.edit_state("hawk", lambda st: st["main"]["closed"].pop())        # un trade sparito dallo stato
        out, _ = self.brain_snapshot()
        probs, _ = self.check(out)
        self.assertTrue(any("hawk: i trade chiusi nello stato (39)" in x for x in probs), probs)

    def test_semantic_check_catches_wrong_accounting(self):
        self.edit_state("bull", lambda st: st["main"].__setitem__("cash", st["main"]["cash"] + 5))
        out, _ = self.brain_snapshot()
        probs, _ = self.check(out)
        self.assertTrue(any("bull: contabilita' incoerente" in x for x in probs), probs)

    def test_semantic_check_catches_ids_beyond_next_id_and_future_runs(self):
        self.edit_state("hawk", lambda st: st["main"].__setitem__("next_id", 10))
        self.edit_state("bull", lambda st: st.__setitem__("run_no", 2))      # storico della run 3 = "futura"
        out, _ = self.brain_snapshot()
        probs, _ = self.check(out)
        self.assertTrue(any("hawk: id" in x and "oltre next_id=10" in x for x in probs), probs)
        self.assertTrue(any("bull:" in x and "run successiva" in x for x in probs), probs)

    def test_retention_policy_unit(self):
        ext = load(EXT, "ext_mod2")
        base = datetime(2026, 10, 19, 3, 0, tzinfo=timezone.utc)
        daily = [("n%d" % i, base - timedelta(days=i)) for i in range(120)]       # un archivio al giorno, 4 mesi
        drop = ext.plan_retention(daily)
        keep = {n for n, _ in daily} - drop
        newest14 = {"n%d" % i for i in range(14)}
        self.assertTrue(newest14 <= keep)                                         # gli ultimi 14 mai tolti
        self.assertIn("n0", keep)
        self.assertLess(len(keep), 14 + 8 + 6 + 1)
        weekly_old = [n for n in keep - newest14]
        self.assertTrue(weekly_old)                                               # ci sono settimanali/mensili
        self.assertTrue(drop)
        self.assertEqual(ext.plan_retention([]), set())
        few = [("a", base), ("b", base - timedelta(days=1))]
        self.assertEqual(ext.plan_retention(few), set())                          # pochi archivi: non si toglie niente
        self.assertEqual(ext.plan_retention(daily, keep_recent=0, keep_weeks=0, keep_months=0), {n for n, _ in daily})

    def test_retention_removes_old_archives_from_tip_but_history_keeps_them(self):
        seed = os.path.join(self.td.name, "seed2")
        sh("git", "clone", "-q", self.remote, seed)
        old_names = []
        start = datetime(2026, 6, 1, 3, 0, tzinfo=timezone.utc)
        for i in range(40):
            dt = start + timedelta(days=i)
            name = "superbot-backup-%s.tar.gz.age" % dt.strftime("%Y%m%dT%H%M%SZ")
            d = os.path.join(seed, "archives", dt.strftime("%Y"), dt.strftime("%m"))
            os.makedirs(d, exist_ok=True)
            put(os.path.join(d, name), b"age-encryption.org/v1\n" + b"0" * 300)
            put(os.path.join(d, name[: -len(".tar.gz.age")] + ".manifest.json"), "{}")
            old_names.append(name)
        sh("git", "-C", seed, "add", "-A")
        sh("git", "-C", seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "vecchi")
        sh("git", "-C", seed, "push", "-q", "origin", "main")
        rc, out = self.backup()
        self.assertEqual(rc, 0, out)
        self.assertIn("tolti dalla punta del ramo", out)
        clone = self.clone_remote()
        tip = [os.path.basename(a) for a in self.archives(clone)]
        self.assertEqual(len(tip), len(set(tip)))
        self.assertLess(len(tip), 41)                                             # qualcuno e' stato tolto
        newest = sorted(old_names)[-13:]
        for n in newest:
            self.assertIn(n, tip)                                                 # i 13 piu' recenti vecchi + il nuovo
        removed = [n for n in old_names if n not in tip]
        self.assertTrue(removed)
        for n in removed:                                                         # tolto anche il manifesto
            self.assertFalse([f for dp, _d, fn in os.walk(clone) for f in fn
                              if f == n[: -len(".tar.gz.age")] + ".manifest.json"])
        # la storia git li conserva ancora
        hist = sh("git", "-C", clone, "log", "--all", "--name-only", "--format=").stdout
        self.assertIn(removed[0], hist)


GOLDEN = ["1b2a7566a936c3791d431621f8bb2e606a574706a2c2e859b4e54df81e08c7fc",
          "aaee5f8c6ee6f67f578377a416391cbca75f1e010ccd4370cb93fbd7c5a08abd",
          "6d2dbc9035424abb61d69eaa38b8c6e09deb0dc19b5ae6f4da4607fe94dc350f"]


def make_v3_journal(path, n=3):
    """Journal V3 con la stessa regola di hash del progetto (verificata dai vettori GOLDEN)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ext_golden", EXT)
    ext = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ext)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE v3_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT, portfolio_id TEXT,"
                " run_id TEXT, kind TEXT, occurred_at_ms INTEGER, source TEXT, payload_json TEXT, previous_hash TEXT,"
                " event_hash TEXT)")
    prev = ext.GENESIS
    for i in range(n):
        row = (i + 1, "e%d" % i, "brain", "r1", "brain_decision", 1700000000000 + i, "s",
               json.dumps({"k": i, "t": "\u00e8"}, separators=(",", ":"), sort_keys=True))
        h = ext.chain_digest(prev, row)
        con.execute("INSERT INTO v3_events(event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,"
                    "previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?,?)", row[1:] + (prev, h))
        prev = h
    con.commit()
    return con


class RunDirTests(unittest.TestCase):
    """Storici delle run nell'archivio dell'extbackup: copia ricorsiva coerente, esclusioni, catena dei journal V3."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ext = load(EXT, "ext_rundir")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_run(self, rel, n=3):
        d = os.path.join(self.tmp, rel)
        os.makedirs(os.path.join(d, "hawk"))
        con = make_v3_journal(os.path.join(d, "journal.db"), n)       # WAL aperto: la copia deve includerlo
        put(os.path.join(d, "heartbeat.json"), '{"state":"running"}')
        put(os.path.join(d, ".exit_service.lock"), "")
        put(os.path.join(d, "writer.lock"), "")
        put(os.path.join(d, "api_token.txt"), "segreto")
        put(os.path.join(d, ".env"), "KEY=x")
        os.symlink("/etc/hostname", os.path.join(d, "link.txt"))
        c2 = sqlite3.connect(os.path.join(d, "hawk", "brain.sqlite3"))
        c2.execute("CREATE TABLE t(x)")
        c2.execute("INSERT INTO t VALUES(1)")
        c2.commit()
        c2.close()
        return d, con

    def test_golden_vectors_match_the_project_journal_rule(self):
        con = make_v3_journal(os.path.join(self.tmp, "g.db"))
        self.assertEqual([r[0] for r in con.execute("select event_hash from v3_events order by seq")], GOLDEN)

    def test_recursive_copy_with_exclusions_and_journal_chain(self):
        d, con = self.make_run("arena/deepseek/brain-deepseek-paper20261118", n=5)
        runs = os.path.join(self.tmp, "stage", "runs")
        self.ext.copy_run_dir(d, runs, required=True)
        out = os.path.join(runs, "deepseek__brain-deepseek-paper20261118")
        got = sorted(os.path.relpath(os.path.join(dp, f), out) for dp, _d, fn in os.walk(out) for f in fn)
        self.assertEqual(got, ["hawk/brain.sqlite3", "heartbeat.json", "journal.db"])   # niente lock/segreti/link
        with open(os.path.join(runs, self.ext.JOURNAL_INDEX)) as f:
            (j,) = json.load(f)
        self.assertEqual(j["events"], 5)
        self.assertEqual(j["file"], "dati/runs/deepseek__brain-deepseek-paper20261118/journal.db")
        con.close()

    def test_a_broken_source_chain_refuses(self):
        d, con = self.make_run("v3/brain-v3-x")
        con.execute("UPDATE v3_events SET payload_json='{}' WHERE seq=2")
        con.commit()
        with self.assertRaises(self.ext.Fail):
            self.ext.copy_run_dir(d, os.path.join(self.tmp, "s"))
        con.close()

    def test_missing_required_relative_or_empty_refuses(self):
        with self.assertRaisesRegex(self.ext.Fail, "OBBLIGATORIO"):
            self.ext.copy_run_dir(os.path.join(self.tmp, "nope"), os.path.join(self.tmp, "s1"), required=True)
        with self.assertRaises(self.ext.Fail):
            self.ext.copy_run_dir("relative/dir", os.path.join(self.tmp, "s1"))
        os.makedirs(os.path.join(self.tmp, "empty"))
        with self.assertRaises(self.ext.Fail):
            self.ext.copy_run_dir(os.path.join(self.tmp, "empty"), os.path.join(self.tmp, "s2"))

    def _restored_tree(self, n=4):
        out = os.path.join(self.tmp, "restore")
        run = os.path.join(out, "dati", "runs", "a__b")
        os.makedirs(run)
        make_v3_journal(os.path.join(run, "journal.db"), n).close()
        ch = self.ext.journal_chain(os.path.join(run, "journal.db"))
        put(os.path.join(out, "dati", "runs", "_journal_v3.json"),
            json.dumps([{"file": "dati/runs/a__b/journal.db", "events": ch[0], "head": ch[1]}]))
        return out, os.path.join(run, "journal.db")

    def _problems(self, out):
        rest = load(RESTORE, "restore_mod")
        class P(list):
            def add(self, m):
                self.append(m)
        p = P()
        rest.check_v3_journals(out, p)
        return p

    def test_restore_accepts_an_intact_journal(self):
        out, _ = self._restored_tree()
        self.assertEqual(self._problems(out), [])

    def test_restore_detects_a_truncated_journal(self):
        out, db = self._restored_tree()
        c = sqlite3.connect(db)
        c.execute("DELETE FROM v3_events WHERE seq=(SELECT MAX(seq) FROM v3_events)")
        c.commit(); c.close()
        self.assertTrue(any("diverso dall'originale" in m for m in self._problems(out)))

    def test_restore_detects_a_tampered_chain(self):
        out, db = self._restored_tree()
        c = sqlite3.connect(db)
        c.execute("UPDATE v3_events SET payload_json='{}' WHERE seq=2")
        c.commit(); c.close()
        self.assertTrue(any("catena non valida" in m for m in self._problems(out)))

    def test_restore_detects_a_missing_journal(self):
        out, db = self._restored_tree()
        os.remove(db)
        self.assertTrue(any("mancante" in m for m in self._problems(out)))

    def test_a_rewritten_original_is_not_accepted_as_prefix(self):
        a = os.path.join(self.tmp, "a.db")
        make_v3_journal(a, 3).close()
        ch = self.ext.journal_chain(a)
        self.assertTrue(self.ext.source_has_prefix(a, *ch))
        self.assertTrue(self.ext.source_has_prefix(a, 2, self.ext.journal_chain(a)[1]) is False)  # testa sbagliata
        self.assertFalse(self.ext.source_has_prefix(a, 5, ch[1]))                                 # originale piu' corto

    # ---- run obbligatorie con EventJournal V3 (Brain V3 attivo, Arena) ----
    def _v3(self, d):
        return self.ext.copy_run_dir(d, os.path.join(self.tmp, "sv3"), required=True, v3=True)

    def test_required_v3_run_registers_its_journal_as_required(self):
        d, con = self.make_run("arena/qwen/brain-qwen-paper20261118")
        self._v3(d)
        with open(os.path.join(self.tmp, "sv3", self.ext.JOURNAL_INDEX)) as f:
            entries = json.load(f)
        self.assertEqual([e["required"] for e in entries if e["file"].endswith("/journal.db")], [True])
        con.close()

    def test_required_v3_run_without_journal_db_refuses(self):
        d = os.path.join(self.tmp, "v3", "nojournal")
        os.makedirs(d)
        put(os.path.join(d, "heartbeat.json"), "{}")
        with self.assertRaisesRegex(self.ext.Fail, "senza EventJournal"):
            self._v3(d)

    def test_required_v3_run_whose_journal_has_no_v3_events_refuses(self):
        d = os.path.join(self.tmp, "v3", "wrongtable")
        os.makedirs(d)
        c = sqlite3.connect(os.path.join(d, "journal.db"))
        c.execute("create table altro(x)"); c.commit(); c.close()
        with self.assertRaisesRegex(self.ext.Fail, "senza EventJournal"):
            self._v3(d)

    def test_required_v3_run_with_broken_chain_refuses(self):
        d, con = self.make_run("v3/brokenchain")
        con.execute("UPDATE v3_events SET event_hash='%s' WHERE seq=1" % ("0" * 64))
        con.commit(); con.close()
        with self.assertRaisesRegex(self.ext.Fail, "catena del journal non valida"):
            self._v3(d)

    def test_required_v3_run_with_journal_only_in_a_subfolder_refuses(self):
        d = os.path.join(self.tmp, "v3", "nested")
        os.makedirs(os.path.join(d, "sub"))
        make_v3_journal(os.path.join(d, "sub", "journal.db")).close()
        with self.assertRaisesRegex(self.ext.Fail, "senza EventJournal"):
            self._v3(d)

    def test_non_v3_archives_are_not_forced_into_the_v3_format(self):
        d = os.path.join(self.tmp, "storico", "brain")
        os.makedirs(d)
        put(os.path.join(d, "trade_history.jsonl"), "{}\n")
        self.ext.copy_run_dir(d, os.path.join(self.tmp, "snv3"), required=True)
        with open(os.path.join(self.tmp, "snv3", self.ext.JOURNAL_INDEX)) as f:
            self.assertEqual(json.load(f), [])                      # indice scritto comunque, vuoto

    def test_restore_fails_when_the_index_is_missing(self):
        out, _ = self._restored_tree()
        os.remove(os.path.join(out, "dati", "runs", "_journal_v3.json"))
        self.assertTrue(any("indice dei journal V3 mancante" in m for m in self._problems(out)))

    def test_restore_fails_when_a_required_journal_is_missing(self):
        out, db = self._restored_tree()
        idx = os.path.join(out, "dati", "runs", "_journal_v3.json")
        with open(idx) as f:
            entries = json.load(f)
        entries[0]["required"] = True
        put(idx, json.dumps(entries))
        os.remove(db)
        self.assertTrue(any("mancante" in m for m in self._problems(out)))

    def test_same_label_twice_refuses(self):
        a, c1 = self.make_run("x/p/run1")
        b, c2 = self.make_run("y/p/run1")
        runs = os.path.join(self.tmp, "s3")
        self.ext.copy_run_dir(a, runs)
        with self.assertRaises(self.ext.Fail):
            self.ext.copy_run_dir(b, runs)
        c1.close(); c2.close()


if __name__ == "__main__":
    unittest.main()
