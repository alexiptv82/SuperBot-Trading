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
        rows = "".join(json.dumps({"i": i, "nota": M_TRADE}) + "\n" for i in range(40))
        old = time.time() - 300
        for name, body in (("trade_history.jsonl", rows), ("learning_log.jsonl", rows), ("errors.md", "# e\n"),
                           ("lessons.md", "# %s\n" % M_LESSONS),
                           ("state_v2.json", json.dumps({"run_no": 3, "cycle": 5, "note": M_STATE,
                                                         "main": {"positions": {}}}))):
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


if __name__ == "__main__":
    unittest.main()
