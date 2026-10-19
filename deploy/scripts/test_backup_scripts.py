"""Prove degli script di backup (nessun server, nessun segreto, solo cartelle temporanee).

Si lanciano con:  python3 -m unittest deploy/scripts/test_backup_scripts.py -v
Ogni prova importante ha anche il suo caso che DEVE fallire: un controllo che non
puo' fallire non verifica niente.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "backup_app_db.py")
BRAIN = os.path.join(HERE, "backup_brain.py")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FAKE_DOCKER = """#!/usr/bin/env python3
import os, sys
D = %r
a = sys.argv[1:]
if a[:3] != ["inspect", "-f", "{{.State.Running}}"]:
    sys.exit(2)
path = os.path.join(D, a[3])
if not os.path.exists(path):
    print("Error: No such object: " + a[3], file=sys.stderr)
    sys.exit(1)
calls = D + ".calls"
n = int(open(calls).read()) + 1 if os.path.exists(calls) else 1
open(calls, "w").write(str(n))
if os.path.exists(D + ".flip") and n > int(open(D + ".flip").read()):
    print("true")                      # il container "riparte" dopo N chiamate
else:
    print(open(path).read().strip())
"""


def run(script, *args):
    p = subprocess.run([sys.executable, "-I", script, *args], capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout + p.stderr


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_json(path):
    with open(path) as f:
        return json.load(f)


class AppDbTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.td.name, "bk")
        self.db = os.path.join(self.td.name, "app.db")

    def tearDown(self):
        self.td.cleanup()

    def make_db(self, wal=False):
        c = sqlite3.connect(self.db)
        if wal:
            c.execute("pragma journal_mode=wal")
        c.execute("create table users(id integer primary key, name text not null)")
        c.execute("create index ix_users_name on users(name)")
        c.executemany("insert into users(name) values(?)", [("a%d" % i,) for i in range(200)])
        c.commit()
        c.close()

    def go(self, *extra):
        return run(APP, "--src", self.db, "--dir", self.dir, "--prefix", "t", *extra)

    def test_ok_and_copy_identical_to_live_content(self):
        self.make_db()
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        files = [n for n in os.listdir(self.dir) if n.endswith(".db")]
        self.assertEqual(len(files), 1)
        c = sqlite3.connect(os.path.join(self.dir, files[0]))
        self.assertEqual(c.execute("select count(*) from users").fetchone()[0], 200)

    def test_missing_db_is_an_error(self):  # punto 1 di ChatGPT
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("non esiste", out)

    def test_missing_db_ok_only_with_flag(self):
        rc, out = self.go("--allow-missing")
        self.assertEqual(rc, 0, out)

    def test_empty_db_is_an_error(self):
        open(self.db, "wb").close()
        rc, _ = self.go()
        self.assertEqual(rc, 1)

    def test_garbage_db_fails_and_leaves_no_good_copy(self):
        with open(self.db, "wb") as f:
            f.write(b"questo non e' un database sqlite" * 50)
        rc, _ = self.go()
        self.assertEqual(rc, 1)
        self.assertEqual([n for n in os.listdir(self.dir) if n.endswith(".db")], [])

    def test_two_backups_never_overwrite(self):  # punto 2 di ChatGPT
        self.make_db()
        for _ in range(2):
            rc, out = self.go()
            self.assertEqual(rc, 0, out)
        self.assertEqual(len([n for n in os.listdir(self.dir) if n.endswith(".db")]), 2)

    def test_free_name_skips_existing_name(self):
        mod = load(APP, "bk_app")
        os.makedirs(self.dir)
        first = mod.free_name(self.dir, "t")
        open(first, "wb").close()
        second = mod.free_name(self.dir, "t")
        self.assertNotEqual(first, second)

    def test_lock_is_exclusive(self):
        mod = load(APP, "bk_app2")
        os.makedirs(self.dir)
        fd = mod.take_lock(self.dir, timeout=2)
        try:
            with self.assertRaises(TimeoutError):
                mod.take_lock(self.dir, timeout=1)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def test_schema_diff_sees_index_column_and_version(self):  # punto 3 di ChatGPT
        mod = load(APP, "bk_app3")
        a = os.path.join(self.td.name, "a.db")
        for p, extra in ((a, True), (a + "2", False)):
            c = sqlite3.connect(p)
            c.execute("create table t(id integer primary key, v text)")
            if extra:
                c.execute("create index ix on t(v)")
            c.commit()
            c.close()
        sa = mod.schema(sqlite3.connect(a))
        sb = mod.schema(sqlite3.connect(a + "2"))
        self.assertIsNone(mod.schema_diff(sa, sa))
        self.assertIn("ix", mod.schema_diff(sa, sb))          # indice mancante
        c = sqlite3.connect(a + "3")
        c.execute("create table t(id integer primary key, v integer)")  # stesso nome, colonna diversa
        c.execute("create index ix on t(v)")
        c.commit()
        self.assertIn("definizione diversa", mod.schema_diff(sa, mod.schema(c)))
        c.execute("pragma user_version=7")
        self.assertIn("user_version", mod.schema_diff(sb, mod.schema(c)))

    def test_backup_while_app_is_writing(self):
        self.make_db(wal=True)
        stop = threading.Event()

        def writer():
            c = sqlite3.connect(self.db, timeout=30)
            i = 0
            while not stop.is_set():
                c.execute("insert into users(name) values(?)", ("w%d" % i,))
                c.commit()
                i += 1

        t = threading.Thread(target=writer)
        t.start()
        try:
            rc, out = self.go()
        finally:
            stop.set()
            t.join()
        self.assertEqual(rc, 0, out)


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.td.name, "data")
        self.dir = os.path.join(self.td.name, "bk")
        for p in ("hawk", "bull"):
            self.make_portfolio(p)
        self.cdir = os.path.join(self.td.name, "containers")
        os.makedirs(self.cdir)
        self.docker = os.path.join(self.td.name, "docker")
        with open(self.docker, "w") as f:
            f.write(FAKE_DOCKER % self.cdir)
        os.chmod(self.docker, 0o755)

    def tearDown(self):
        self.td.cleanup()

    def container(self, portfolio, running):
        """Stato del finto container superbot-desk-<portafoglio>: True/False, None = assente."""
        path = os.path.join(self.cdir, "superbot-desk-" + portfolio)
        if running is None:
            if os.path.exists(path):
                os.remove(path)
            return
        with open(path, "w") as f:
            f.write("true" if running else "false")

    def stopped(self, *extra):
        return self.go("--bot-stopped", "--docker-bin", self.docker, *extra)

    def make_portfolio(self, p, big=0):
        d = os.path.join(self.root, p)
        os.makedirs(d, exist_ok=True)
        rows = "".join(json.dumps({"i": i, "net": i % 5 - 2}) + "\n" for i in range(50))
        old = time.time() - 300
        for name, body in (("trade_history.jsonl", rows), ("learning_log.jsonl", rows * (1 + big)),
                           ("lessons.md", "# lezioni\n"), ("errors.md", "# errori\n"),
                           ("state_v2.json", json.dumps({"run_no": 3, "cycle": 5, "main": {"positions": {}}}))):
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
        for k in [k for k, v in hb.items() if v is None]:
            del hb[k]
        path = os.path.join(self.root, p, "heartbeat.json")
        with open(path, "w") as f:
            json.dump(hb, f)
        os.utime(path, (now - age, now - age))

    def go(self, *extra):
        return run(BRAIN, "--root", self.root, "--dir", self.dir, "--quiet-secs", "1", "--attempts", "2",
                   "--wait", "0.1", "--quiet-timeout", "2", *extra)

    def finished(self):
        if not os.path.isdir(self.dir):
            return []
        return [n for n in os.listdir(self.dir) if n.startswith("bots-") and not n.endswith(".part")]

    def snapshot(self):
        out = {}
        for p in ("hawk", "bull"):
            for n in os.listdir(os.path.join(self.root, p)):
                if n != "heartbeat.json":
                    out[(p, n)] = sha(os.path.join(self.root, p, n))
        return out

    def test_ok_copy_identical_originals_untouched_and_manifest(self):
        before = self.snapshot()
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        self.assertEqual(before, self.snapshot())                 # gli originali non cambiano
        (name,) = self.finished()
        for (p, n), h in before.items():
            self.assertEqual(sha(os.path.join(self.dir, name, p, n)), h)
        man = load_json(os.path.join(self.dir, name, "MANIFEST.json"))
        self.assertTrue(man["coerenza"]["consistente"])
        self.assertTrue(man["coerenza"]["confine_di_ciclo_verificato"])
        self.assertEqual(man["stato_copiato"]["hawk"]["run_no"], 3)

    def test_missing_root_or_portfolio_is_an_error(self):  # punto 1 di ChatGPT
        rc, out = run(BRAIN, "--root", os.path.join(self.td.name, "nulla"), "--dir", self.dir)
        self.assertEqual(rc, 1, out)
        import shutil
        shutil.rmtree(os.path.join(self.root, "bull"))
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("bull", out)
        self.assertEqual(self.finished(), [])

    def test_missing_allowed_only_with_flag(self):
        rc, out = run(BRAIN, "--root", os.path.join(self.td.name, "nulla"), "--dir", self.dir, "--first-install")
        self.assertEqual(rc, 0, out)
        # la vecchia opzione generica non esiste piu': un comando vecchio fallisce invece di passare
        rc, _ = run(BRAIN, "--root", os.path.join(self.td.name, "nulla"), "--dir", self.dir, "--allow-missing")
        self.assertNotEqual(rc, 0)

    # ---- caso 1 di ChatGPT (19/10, terzo giro): file irrinunciabili obbligatori ----

    def test_every_required_file_is_mandatory(self):
        mod = load(BRAIN, "bk_brain_req")
        self.assertEqual(set(mod.REQUIRED),
                         {"state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md"})
        for p in ("hawk", "bull"):
            for name in mod.REQUIRED:
                with self.subTest(portfolio=p, file=name):
                    self.tearDown()
                    self.setUp()                                   # cartelle nuove per ogni caso
                    os.remove(os.path.join(self.root, p, name))
                    rc, out = self.go()
                    self.assertEqual(rc, 1, out)
                    self.assertIn("%s/%s" % (p, name), out)
                    self.assertEqual(self.finished(), [])          # nessuna copia "buona" rimasta

    def test_empty_portfolio_folder_fails(self):
        for n in os.listdir(os.path.join(self.root, "bull")):
            if n != "heartbeat.json":
                os.remove(os.path.join(self.root, "bull", n))      # cartella con solo il battito
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("irrinunciabili", out)
        self.assertEqual(self.finished(), [])

    def test_required_state_cannot_be_empty_or_a_symlink(self):
        path = os.path.join(self.root, "hawk", "state_v2.json")
        open(path, "w").close()
        self.assertEqual(self.go()[0], 1)
        os.remove(path)
        os.symlink(os.path.join(self.root, "bull", "state_v2.json"), path)   # la copia non segue i collegamenti
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("hawk/state_v2.json", out)

    def test_errors_md_is_optional(self):                          # sul server di oggi non esiste
        for p in ("hawk", "bull"):
            os.remove(os.path.join(self.root, p, "errors.md"))
        rc, out = self.go()
        self.assertEqual(rc, 0, out)

    def test_first_install_is_an_explicit_and_recorded_exception(self):
        for n in os.listdir(os.path.join(self.root, "bull")):
            if n != "heartbeat.json":
                os.remove(os.path.join(self.root, "bull", n))
        self.assertEqual(self.go()[0], 1)                          # senza opzione: errore
        rc, out = self.go("--first-install")
        self.assertEqual(rc, 0, out)
        self.assertIn("PRIMA INSTALLAZIONE", out)
        (name,) = self.finished()
        man = load_json(os.path.join(self.dir, name, "MANIFEST.json"))
        self.assertTrue(man["prima_installazione"]["ammessa"])
        self.assertIn("bull/state_v2.json", man["prima_installazione"]["file_irrinunciabili_assenti"])

    def test_normal_backup_records_that_no_exception_was_used(self):
        self.assertEqual(self.go()[0], 0)
        (name,) = self.finished()
        man = load_json(os.path.join(self.dir, name, "MANIFEST.json"))
        self.assertFalse(man["prima_installazione"]["ammessa"])
        self.assertEqual(man["prima_installazione"]["file_irrinunciabili_assenti"], [])

    def test_cycle_running_blocks_the_backup(self):  # punto 4: confine di ciclo
        self.heartbeat("hawk", cycle_running=True)
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.finished(), [])

    def test_cycle_just_ended_or_next_cycle_imminent_blocks(self):
        self.heartbeat("bull", last_end_ms=int(time.time() * 1000))
        self.assertEqual(self.go("--quiet-secs", "30")[0], 1)   # appena finito: si aspetta, e qui non basta il tempo
        self.heartbeat("bull", next_cycle_ms=int((time.time() + 5) * 1000))
        self.assertEqual(self.go()[0], 1)
        self.assertEqual(self.finished(), [])

    def test_writes_during_copy_are_detected_and_copy_discarded(self):  # punto 4: coerenza
        self.make_portfolio("hawk", big=20000)                        # file grande: finestra di copia piu' lunga
        stop = threading.Event()
        path = os.path.join(self.root, "hawk", "learning_log.jsonl")

        def writer():
            with open(path, "ab", buffering=0) as f:
                while not stop.is_set():
                    f.write(b'{"i": 1, "net": 0}\n')

        t = threading.Thread(target=writer)
        t.start()
        try:
            rc, out = run(BRAIN, "--root", self.root, "--dir", self.dir, "--quiet-secs", "0", "--attempts", "3",
                          "--wait", "0.05", "--quiet-timeout", "1")
        finally:
            stop.set()
            t.join()
        self.assertEqual(rc, 1, out)
        self.assertIn("non e' dimostrabile", out)
        self.assertEqual(self.finished(), [])                         # nessuna copia incoerente rimasta

    # ---- caso 3 di ChatGPT: nel percorso di deploy il confine di ciclo VERIFICATO e' obbligatorio ----

    def test_stale_heartbeat_fails_in_the_deploy_path(self):
        for p in ("hawk", "bull"):
            self.heartbeat(p, age=600, cycle_running=True)
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("--bot-stopped", out)                        # dice come procedere se e' davvero fermo
        self.assertEqual(self.finished(), [])

    def test_missing_cycle_running_fails_in_the_deploy_path(self):
        for p in ("hawk", "bull"):
            self.heartbeat(p, cycle_running=None)
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("cycle_running", out)
        self.assertEqual(self.finished(), [])

    def test_one_unverifiable_bot_is_enough_to_fail(self):
        self.heartbeat("bull", age=600)
        self.assertEqual(self.go()[0], 1)
        self.assertEqual(self.finished(), [])

    def test_unverifiable_fails_fast_without_retrying(self):
        for p in ("hawk", "bull"):
            self.heartbeat(p, age=600)
        t = time.time()
        rc, out = run(BRAIN, "--root", self.root, "--dir", self.dir, "--quiet-secs", "1", "--attempts", "5",
                      "--wait", "5", "--quiet-timeout", "60")
        self.assertEqual(rc, 1, out)
        self.assertLess(time.time() - t, 10)                       # non aspetta minuti per qualcosa che non cambiera'
        self.assertNotIn("tentativo 2", out)

    def test_default_manifest_always_says_verified(self):
        self.assertEqual(self.go()[0], 0)
        (name,) = self.finished()
        c = load_json(os.path.join(self.dir, name, "MANIFEST.json"))["coerenza"]
        self.assertTrue(c["confine_di_ciclo_verificato"])
        self.assertEqual(c["modalita"], "ciclo_verificato")

    def test_boundary_state_classification(self):
        mod = load(BRAIN, "bk_brain_bs")
        base = os.path.join(self.root, "hawk")
        self.assertEqual(mod.boundary_state(base, 1)[0], mod.OK)
        self.heartbeat("hawk", age=600)
        self.assertEqual(mod.boundary_state(base, 1)[0], mod.NO)
        self.heartbeat("hawk", cycle_running=None)
        self.assertEqual(mod.boundary_state(base, 1)[0], mod.NO)
        self.heartbeat("hawk", cycle_running=True)
        self.assertEqual(mod.boundary_state(base, 1)[0], mod.WAIT)

    # modalita' separata ed esplicita per un bot davvero fermo: il fermo si DIMOSTRA sul container

    def test_bot_stopped_mode_works_only_for_a_really_stopped_bot_and_says_so(self):
        for p in ("hawk", "bull"):
            self.heartbeat(p, age=600, cycle_running=True)
            self.container(p, False)
        rc, out = self.stopped()
        self.assertEqual(rc, 0, out)
        self.assertIn("BOT FERMO", out)
        (name,) = self.finished()
        c = load_json(os.path.join(self.dir, name, "MANIFEST.json"))["coerenza"]
        self.assertEqual(c["modalita"], "bot_fermo")
        self.assertFalse(c["confine_di_ciclo_verificato"])         # non spaccia la copia per verificata
        self.assertIn("docker inspect", c["metodo"])
        for p in ("hawk", "bull"):                                  # il manifesto riporta la prova, container per container
            self.assertIn("superbot-desk-%s fermo" % p, c["stato_del_confine"][p])

    def test_stale_heartbeat_alone_does_not_prove_a_bot_is_stopped(self):
        """Caso 2 di ChatGPT: un processo bloccato ha il battito vecchio ma puo' ancora scrivere."""
        for p in ("hawk", "bull"):
            self.heartbeat(p, age=600)
            self.container(p, True)                                 # container ancora in esecuzione
        rc, out = self.stopped()
        self.assertEqual(rc, 1, out)
        self.assertIn("IN ESECUZIONE", out)
        self.assertIn("ATTIVO", out)
        self.assertEqual(self.finished(), [])

    def test_bot_stopped_mode_is_refused_when_one_bot_is_alive(self):
        for p in ("hawk", "bull"):
            self.heartbeat(p, age=600)
            self.container(p, False)
        self.container("bull", True)                                # uno fermo, uno vivo
        rc, out = self.stopped()
        self.assertEqual(rc, 1, out)
        self.assertIn("superbot-desk-bull IN ESECUZIONE", out)
        self.assertEqual(self.finished(), [])

    def test_bot_stopped_mode_is_refused_when_docker_cannot_prove_it(self):
        for p in ("hawk", "bull"):
            self.heartbeat(p, age=600)
        rc, out = self.go("--bot-stopped", "--docker-bin", os.path.join(self.td.name, "non-esiste"))
        self.assertEqual(rc, 1, out)
        self.assertIn("richiede la prova del fermo", out)
        self.assertEqual(self.finished(), [])

    def test_stopped_container_with_a_fresh_heartbeat_is_a_contradiction_not_a_pass(self):
        for p in ("hawk", "bull"):
            self.container(p, False)                                # fermi, ma il battito e' di adesso
        rc, out = self.stopped()
        self.assertEqual(rc, 1, out)
        self.assertIn("ancora fresco", out)
        self.assertEqual(self.finished(), [])

    def test_absent_container_with_old_heartbeat_is_accepted_and_reported(self):
        for p in ("hawk", "bull"):
            self.heartbeat(p, age=600)
        rc, out = self.stopped()
        self.assertEqual(rc, 0, out)
        (name,) = self.finished()
        c = load_json(os.path.join(self.dir, name, "MANIFEST.json"))["coerenza"]
        self.assertIn("assente", c["stato_del_confine"]["hawk"])

    def test_bot_stopped_mode_still_needs_quiet_files_and_required_files(self):
        for p in ("hawk", "bull"):
            self.heartbeat(p, age=600)
            self.container(p, False)
        os.utime(os.path.join(self.root, "hawk", "state_v2.json"))          # scritto adesso
        self.assertEqual(self.stopped("--quiet-secs", "30")[0], 1)
        old = time.time() - 300
        os.utime(os.path.join(self.root, "hawk", "state_v2.json"), (old, old))
        os.remove(os.path.join(self.root, "bull", "lessons.md"))
        rc, out = self.stopped()
        self.assertEqual(rc, 1, out)
        self.assertIn("bull/lessons.md", out)

    def test_a_bot_that_restarts_during_the_copy_discards_the_backup(self):
        for p in ("hawk", "bull"):
            self.heartbeat(p, age=600)
            self.container(p, False)
        with open(self.cdir + ".flip", "w") as f:
            f.write("2")                       # le prime 2 chiamate (una per bot) dicono "fermo", poi "in esecuzione"
        rc, out = self.stopped()
        self.assertEqual(rc, 1, out)
        self.assertIn("ripartito", out)
        self.assertEqual(self.finished(), [])

    def test_normal_mode_never_calls_docker(self):
        rc, out = self.go("--docker-bin", os.path.join(self.td.name, "non-esiste"))
        self.assertEqual(rc, 0, out)                                # il percorso normale non dipende da docker

    # ---- caso 2 di ChatGPT: riga finale troncata = corruzione ----

    def write_jsonl(self, p, name, body):
        path = os.path.join(self.root, p, name)
        with open(path, "wb") as f:
            f.write(body)
        old = time.time() - 300
        os.utime(path, (old, old))
        return path

    def test_truncated_last_line_without_newline_blocks_deploy(self):
        rows = b'{"i": 1}\n{"i": 2}\n'
        for name in ("trade_history.jsonl", "learning_log.jsonl"):
            with self.subTest(file=name):
                self.tearDown()
                self.setUp()
                self.write_jsonl("bull", name, rows + b'{"i": 3, "net"')          # scrittura interrotta
                rc, out = self.go()
                self.assertEqual(rc, 1, out)
                self.assertIn("incompleta", out)
                self.assertEqual([n for n in self.finished() if "INCOMPLETO" not in n], [])
                self.assertTrue(any("INCOMPLETO" in n for n in os.listdir(self.dir)))

    def test_complete_json_without_final_newline_is_also_incomplete(self):
        self.write_jsonl("hawk", "trade_history.jsonl", b'{"i": 1}\n{"i": 2}')     # riga valida ma senza a capo
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertIn("senza a capo", out)

    def test_jsonl_problem_cases(self):
        mod = load(BRAIN, "bk_brain_jl")
        path = os.path.join(self.td.name, "x.jsonl")
        cases = [
            (b"", None),                                           # vuoto: nessuna riga, nessun problema
            (b'{"a":1}\n', None),
            (b'{"a":1}\n\n{"b":2}\n', None),                      # riga vuota in mezzo non e' corruzione
            (b'{"a":1}\n{"b":2}', "incompleta"),                    # manca l'a capo finale
            (b'{"a":1}\n{"b":', "incompleta"),
            (b'{"a":1}\n{rotto\n{"b":2}\n', "riga 2"),             # corruzione in mezzo
            (b'{"a":1}\n\xff\xfe\n', "riga 2"),                   # byte non UTF-8
        ]
        for body, expect in cases:
            with self.subTest(body=body):
                with open(path, "wb") as f:
                    f.write(body)
                got = mod.jsonl_problem(path)
                if expect is None:
                    self.assertIsNone(got)
                else:
                    self.assertIn(expect, got)
                self.assertEqual(mod.jsonl_ok(path), expect is None)

    def test_corrupted_jsonl_or_state_fails_and_is_marked_incomplete(self):
        path = os.path.join(self.root, "bull", "trade_history.jsonl")
        with open(path) as f:
            text = f.read().split("\n")
        text[10] = "{rotto"
        with open(path, "w") as f:
            f.write("\n".join(text))
        old = time.time() - 300
        os.utime(path, (old, old))
        rc, out = self.go()
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.finished(), [n for n in self.finished() if n.endswith("INCOMPLETO") or "INCOMPLETO" in n])
        self.assertTrue(any("INCOMPLETO" in n for n in os.listdir(self.dir)))

    def test_invalid_tag_rejected(self):
        self.assertEqual(self.go("--tag", "../x")[0], 1)

    def test_rotation_keeps_last_n(self):
        for _ in range(3):
            self.assertEqual(self.go("--keep", "2")[0], 0)
        self.assertEqual(len(self.finished()), 2)

    def test_free_unique_sees_part_and_incomplete(self):
        mod = load(BRAIN, "bk_brain")
        base = os.path.join(self.td.name, "bots-x")
        self.assertTrue(mod.free_unique(base))
        os.makedirs(base + ".part")
        self.assertFalse(mod.free_unique(base))


if __name__ == "__main__":
    unittest.main()
