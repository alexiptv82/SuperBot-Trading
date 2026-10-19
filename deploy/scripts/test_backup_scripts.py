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

    def tearDown(self):
        self.td.cleanup()

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
        rc, out = run(BRAIN, "--root", os.path.join(self.td.name, "nulla"), "--dir", self.dir, "--allow-missing")
        self.assertEqual(rc, 0, out)

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

    def test_stopped_bot_old_heartbeat_ok_but_not_verified(self):
        for p in ("hawk", "bull"):
            self.heartbeat(p, age=600, cycle_running=True)
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        (name,) = self.finished()
        man = load_json(os.path.join(self.dir, name, "MANIFEST.json"))
        self.assertFalse(man["coerenza"]["confine_di_ciclo_verificato"])

    def test_old_bot_without_cycle_running_is_flagged_unverified(self):
        for p in ("hawk", "bull"):
            self.heartbeat(p, cycle_running=None)
        rc, out = self.go()
        self.assertEqual(rc, 0, out)
        (name,) = self.finished()
        man = load_json(os.path.join(self.dir, name, "MANIFEST.json"))
        self.assertFalse(man["coerenza"]["confine_di_ciclo_verificato"])

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
