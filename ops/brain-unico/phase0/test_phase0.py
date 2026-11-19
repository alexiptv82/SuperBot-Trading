"""Test su fixture SINTETICHE per la Fase 0 (nessun dato reale, nessuna rete, nessun servizio)."""
import builtins
import importlib.util
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import audit  # noqa: E402
import phase0  # noqa: E402
import discover  # noqa: E402
import snapshot as snap  # noqa: E402

NOSLEEP = lambda _s: None  # noqa: E731
ROOT = os.geteuid() == 0


def load(p):
    with open(p) as fh:
        return json.load(fh)


def rd(p, mode="r"):
    with open(p, mode) as fh:
        return fh.read()


def rw(p, text):
    with open(p, "w") as fh:
        fh.write(text)


def poke(p, b=b"X"):
    with open(p, "r+b") as fh:
        fh.write(b)


def tree_state(root):
    out = {}
    for d, dn, fn in os.walk(root):
        for n in fn + dn:
            p = os.path.join(d, n)
            st = os.lstat(p)
            out[p] = (st.st_size, st.st_mtime_ns, stat.S_IMODE(st.st_mode))
    return out


def make_v3_db(path, n=5, tamper=None):
    """journal sintetico con la stessa formula di catena del codice di produzione (ricopiata nei test)."""
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE v3_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
        portfolio_id TEXT, run_id TEXT, kind TEXT, occurred_at_ms INTEGER, source TEXT, payload_json TEXT,
        previous_hash TEXT, event_hash TEXT)""")
    prev = audit.GENESIS
    for i in range(n):
        payload = json.dumps({"i": i}, sort_keys=True, separators=(",", ":"))
        eid = f"e{i}"
        h = audit._digest(prev, eid, "brain", "run1" if i < 3 else "run2", "k", 1000 + i, "src", payload)
        con.execute("INSERT INTO v3_events(event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,"
                    "previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                    (eid, "brain", "run1" if i < 3 else "run2", "k", 1000 + i, "src", payload, prev, h))
        prev = h
    con.commit()
    if tamper == "payload":
        con.execute("UPDATE v3_events SET payload_json='{\"i\":99}' WHERE seq=2")
    elif tamper == "gap":
        con.execute("DELETE FROM v3_events WHERE seq=3")
    con.commit()
    con.close()
    return prev


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.t = self.tmp.name
        self.src = os.path.join(self.t, "src")
        os.makedirs(self.src)
        self.work = os.path.join(self.t, "work")
        os.makedirs(self.work)
        self.n = 0
        for name in ("SQLITE_STEP_PAGES", "SQLITE_STEP_SLEEP"):
            self.addCleanup(setattr, snap, name, getattr(snap, name))
        snap.SQLITE_STEP_PAGES, snap.SQLITE_STEP_SLEEP = 1, 0.002
        self.addCleanup(setattr, snap, "_HOOK", None)

    def p(self, *a):
        return os.path.join(self.src, *a)

    def write(self, rel, data, mode="w"):
        path = self.p(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode) as fh:
            fh.write(data)
        return path

    def spec(self, sources):
        path = os.path.join(self.t, f"spec{self.n}.json")
        self.n += 1
        with open(path, "w") as fh:
            json.dump({"schema": 1, "sources": sources}, fh)
        return path

    def dest(self):
        return os.path.join(self.work, f"snap{self.n}")

    def go(self, sources, **kw):
        d = self.dest()
        self.n += 1
        code, rep = snap.run_snapshot(self.spec(sources), d, kw.pop("auth_ref", "ISSUE-113#test"),
                                      kw.pop("dry_run", False), sleep=NOSLEEP, **kw)
        return code, rep, d


class SnapshotSqlite(Base):
    def test_live_wal_db_with_concurrent_writer(self):
        db = self.p("live.sqlite3")
        w = sqlite3.connect(db, isolation_level=None, timeout=5, check_same_thread=False)
        w.execute("PRAGMA journal_mode=WAL")
        w.execute("CREATE TABLE ev(id INTEGER PRIMARY KEY, b BLOB)")
        w.execute("BEGIN")
        w.executemany("INSERT INTO ev(b) VALUES(?)", [(os.urandom(2000),) for _ in range(300)])
        w.execute("COMMIT")
        stop = threading.Event()
        written = []

        def writer():
            while not stop.is_set():
                w.execute("INSERT INTO ev(b) VALUES(?)", (os.urandom(500),))
                written.append(1)
                time.sleep(0.001)
        th = threading.Thread(target=writer)
        th.start()
        try:
            code, rep, d = self.go([{"id": "brain_db", "kind": "sqlite", "path": db}])
        finally:
            stop.set()
            th.join()
            w.close()
        self.assertEqual(code, 0, rep.get("items"))
        it = rep["items"][0]
        self.assertEqual((it["status"], it["integrity"], it["journal_mode_src"], it["method"]),
                         ("OK", "ok", "wal", "backup_api"))
        self.assertGreaterEqual(it["tables"]["ev"], 300)
        names = os.listdir(os.path.join(d, "brain_db"))
        self.assertEqual(names, ["live.sqlite3"])                       # copia standalone: nessun -wal/-shm
        self.assertGreater(len(written), 0)                              # lo scrittore era davvero attivo

    def test_db_locked_exclusively_aborts_without_waiting(self):
        db = self.p("busy.sqlite3")
        c = sqlite3.connect(db, isolation_level=None)
        c.execute("CREATE TABLE t(a)")
        c.execute("BEGIN EXCLUSIVE")                                     # rollback-journal: blocca i lettori
        try:
            t0 = time.time()
            res = snap.copy_sqlite(db, os.path.join(self.work, "o.sqlite3"), sleep=NOSLEEP)
            self.assertLess(time.time() - t0, 10)
        finally:
            c.execute("ROLLBACK")
            c.close()
        self.assertEqual(res["status"], "FAILED")
        self.assertEqual(res["reason"], "busy_or_locked")
        self.assertEqual(res["attempts"], snap.MAX_ATTEMPTS)
        self.assertEqual(os.listdir(self.work), [])                      # nessun residuo parziale

    def test_source_db_not_modified(self):
        db = self.p("a.sqlite3")
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE t(a)")
        con.executemany("INSERT INTO t VALUES(?)", [(i,) for i in range(50)])
        con.commit()
        con.close()
        before = tree_state(self.src)
        code, rep, _ = self.go([{"id": "a", "kind": "sqlite", "path": db}])
        self.assertEqual(code, 0)
        self.assertEqual(before, tree_state(self.src))

    def make_wal_db(self, name, hold_open=False, rows=50):
        db = self.p(name)
        c = sqlite3.connect(db, isolation_level=None, check_same_thread=False)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE t(a)")
        c.execute("BEGIN")
        c.executemany("INSERT INTO t VALUES(?)", [(i,) for i in range(rows)])
        c.execute("COMMIT")
        if hold_open:
            self.addCleanup(c.close)
            return db, c
        c.close()
        return db, None

    def test_idle_wal_db_is_file_copied_and_source_dir_untouched(self):
        db, _ = self.make_wal_db("idle.sqlite3")
        self.assertEqual(os.listdir(self.src), ["idle.sqlite3"])         # chiusura pulita: nessun -wal/-shm
        before = tree_state(self.src)
        res = snap.copy_sqlite(db, os.path.join(self.work, "o.sqlite3"), sleep=NOSLEEP)
        self.assertEqual((res["status"], res["method"], res["tables"]), ("OK", "file_copy_checkpointed", {"t": 50}))
        self.assertEqual(before, tree_state(self.src))                  # NIENTE -shm/-wal creati nella sorgente
        self.assertEqual(sorted(os.listdir(self.work)), ["o.sqlite3"])  # copia standalone
        self.assertEqual(res["sha256"], snap._sha(os.path.join(self.work, "o.sqlite3")))

    def test_rollback_journal_db_backup_api_source_dir_untouched(self):
        db = self.p("rj.sqlite3")
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE t(a)")
        c.execute("INSERT INTO t VALUES(1)")
        c.commit()
        c.close()
        before = tree_state(self.src)
        res = snap.copy_sqlite(db, os.path.join(self.work, "o.sqlite3"), sleep=NOSLEEP)
        self.assertEqual((res["status"], res["method"]), ("OK", "backup_api"))
        self.assertEqual(before, tree_state(self.src))

    def test_live_wal_uses_backup_api(self):
        db, _c = self.make_wal_db("live2.sqlite3", hold_open=True)
        self.assertTrue(os.path.exists(db + "-shm"))
        res = snap.copy_sqlite(db, os.path.join(self.work, "o.sqlite3"), sleep=NOSLEEP)
        self.assertEqual((res["status"], res["method"]), ("OK", "backup_api"))

    @unittest.skipIf(ROOT, "root ignora i permessi")
    def test_live_wal_with_unwritable_shm_is_nogo(self):
        db, _c = self.make_wal_db("ro.sqlite3", hold_open=True)
        os.chmod(db + "-shm", 0o444)
        self.addCleanup(os.chmod, db + "-shm", 0o644)
        code, rep, _ = self.go([{"id": "ro", "kind": "sqlite", "path": db}], dry_run=True)
        self.assertEqual(code, 1)
        self.assertIn("wal_shm_not_writable_by_snapshot_user", {n["code"] for n in rep["preflight"]["nogo"]})
        res = snap.copy_sqlite(db, os.path.join(self.work, "o.sqlite3"), sleep=NOSLEEP)
        self.assertEqual((res["status"], res["reason"]), ("FAILED", "wal_shm_not_writable_by_snapshot_user"))

    def test_wal_data_without_shm_is_nogo(self):
        db, _c = self.make_wal_db("crash.sqlite3", hold_open=True)
        import shutil
        os.makedirs(self.p("c"))
        shutil.copy(db, self.p("c", "crash.sqlite3"))
        shutil.copy(db + "-wal", self.p("c", "crash.sqlite3-wal"))      # WAL con dati, senza -shm (come dopo un crash)
        self.assertGreater(os.path.getsize(self.p("c", "crash.sqlite3-wal")), 0)
        res = snap.copy_sqlite(self.p("c", "crash.sqlite3"), os.path.join(self.work, "o.sqlite3"), sleep=NOSLEEP)
        self.assertEqual((res["status"], res["reason"]), ("FAILED", "wal_data_without_shm"))
        self.assertFalse(os.path.exists(self.p("c", "crash.sqlite3-shm")))   # la sorgente non e' stata toccata

    def test_probe_header(self):
        db, _ = self.make_wal_db("p.sqlite3")
        self.assertTrue(snap.probe_sqlite(db)["wal"])
        plain = self.p("plain.sqlite3")
        sqlite3.connect(plain).execute("CREATE TABLE t(a)").connection.close()
        self.assertFalse(snap.probe_sqlite(plain)["wal"])
        self.assertIn("error", snap.probe_sqlite(self.p("missing")))


class SnapshotFiles(Base):
    def test_jsonl_appender_prefix_and_partial_tail(self):
        path = self.write("h.jsonl", '{"run_no":1}\n{"run_no":2}\n{"run_no":3')   # coda parziale senza a-capo
        code, rep, d = self.go([{"id": "h", "kind": "jsonl", "path": path}])
        it = rep["items"][0]
        self.assertEqual((code, it["status"], it["lines"], it["invalid_lines"]), (0, "OK", 2, 0))
        self.assertEqual(it["partial_tail_bytes"], len('{"run_no":3'))
        self.assertEqual(rd(os.path.join(d, "h", "h.jsonl"), "rb"), b'{"run_no":1}\n{"run_no":2}\n')

    def test_jsonl_with_live_appender_is_valid_prefix(self):
        path = self.write("live.jsonl", "".join('{"n":%d}\n' % i for i in range(20000)))
        stop = threading.Event()

        def app():
            i = 0
            with open(path, "a") as fh:
                while not stop.is_set():
                    fh.write('{"n":%d}\n' % (100000 + i))
                    fh.flush()
                    i += 1
        th = threading.Thread(target=app)
        th.start()
        try:
            code, rep, d = self.go([{"id": "live", "kind": "jsonl", "path": path}])
        finally:
            stop.set()
            th.join()
        self.assertEqual(code, 0)
        data = rd(os.path.join(d, "live", "live.jsonl"), "rb")
        self.assertTrue(data.endswith(b"\n"))
        self.assertEqual(rep["items"][0]["invalid_lines"], 0)
        self.assertEqual(rd(path, "rb")[:len(data)], data)       # la copia e' un prefisso esatto

    def test_jsonl_prefix_modified_then_retry_ok(self):
        path = self.write("r.jsonl", '{"a":1}\n{"a":2}\n')
        fired = []

        def hook(stage, p):
            if not fired:
                fired.append(1)
                poke(p)                                                  # riscrittura del prefisso
        snap._HOOK = hook
        res = snap.copy_append_only(path, os.path.join(self.work, "o.jsonl"), sleep=NOSLEEP)
        self.assertEqual((res["status"], res["attempts"]), ("OK", 2))

    def test_jsonl_always_modified_fails_and_leaves_nothing(self):
        path = self.write("r.jsonl", '{"a":1}\n{"a":2}\n')
        count = []

        def hook(stage, p):
            count.append(1)
            poke(p, bytes([65 + len(count)]))                              # un byte DIVERSO a ogni tentativo
        snap._HOOK = hook
        res = snap.copy_append_only(path, os.path.join(self.work, "o.jsonl"), sleep=NOSLEEP)
        self.assertEqual((res["status"], res["reason"]), ("FAILED", "prefix_modified"))
        self.assertEqual(os.listdir(self.work), [])

    def test_jsonl_replaced_inode_detected(self):
        path = self.write("r.jsonl", '{"a":1}\n')
        n = []

        def hook(stage, p):
            if not n:
                n.append(1)
                os.rename(p, p + ".old")
                with open(p, "w") as fh:
                    fh.write('{"a":1}\n')                               # stesso contenuto, altro inode
        snap._HOOK = hook
        res = snap.copy_append_only(path, os.path.join(self.work, "o.jsonl"), sleep=NOSLEEP)
        self.assertEqual((res["status"], res["attempts"]), ("OK", 2))

    def test_small_file_changed_during_copy(self):
        path = self.write("s.json", '{"k":1}')
        n = []

        def hook(stage, p):
            if not n:
                n.append(1)
                with open(p, "w") as fh:
                    fh.write('{"k":22}')
        snap._HOOK = hook
        res = snap.copy_small_file(path, os.path.join(self.work, "o.json"), sleep=NOSLEEP)
        self.assertEqual((res["status"], res["attempts"]), ("OK", 2))
        self.assertEqual(rd(os.path.join(self.work, "o.json")), '{"k":22}')

    def test_empty_file_and_no_newline_only(self):
        a = self.write("e.jsonl", "")
        b = self.write("n.jsonl", "abc")
        r1 = snap.copy_append_only(a, os.path.join(self.work, "a"), sleep=NOSLEEP)
        r2 = snap.copy_append_only(b, os.path.join(self.work, "b"), sleep=NOSLEEP)
        self.assertEqual((r1["bytes"], r2["bytes"], r2["partial_tail_bytes"]), (0, 0, 3))

    def test_tree_skips_sensitive_side_symlink_special(self):
        self.write("arch/run1/trade.jsonl", '{"run_no":1}\n')
        self.write("arch/run1/state.json", "{}")
        self.write("arch/.env", "SECRET=1")
        self.write("arch/api_key.txt", "SECRET")
        self.write("arch/x.sqlite3-wal", "w")
        os.symlink("/etc/hostname", self.p("arch", "ln"))
        os.mkfifo(self.p("arch", "ff"))
        code, rep, d = self.go([{"id": "arch", "kind": "tree", "path": self.p("arch")}])
        self.assertEqual(code, 0, rep.get("items"))
        self.assertEqual(sorted(i["dst_rel"] for i in rep["items"]),
                         ["arch/run1/state.json", "arch/run1/trade.jsonl"])
        sk = rep["preflight"]["skipped"]
        self.assertEqual((sk["sensitive"], sk["side_files"], sk["symlinks"], sk["special"]), (2, 1, 1, 1))
        self.assertNotIn("SECRET", json.dumps(rep))


class SnapshotPreflight(Base):
    def setUp(self):
        super().setUp()
        self.f = self.write("a.jsonl", '{"a":1}\n')

    def src_spec(self):
        return [{"id": "a", "kind": "jsonl", "path": self.f}]

    def codes(self, rep):
        return {n["code"] for n in rep["preflight"]["nogo"]}

    def test_dry_run_creates_nothing(self):
        code, rep, d = self.go(self.src_spec(), dry_run=True)
        self.assertEqual((code, rep["verdict"]), (0, "GO"))
        self.assertFalse(os.path.exists(d))

    def test_missing_authorization_reference(self):
        for ref in (None, "", "  "):
            code, rep, d = self.go(self.src_spec(), auth_ref=ref)
            self.assertEqual(code, 1)
            self.assertIn("missing_authorization_reference", self.codes(rep))
            self.assertFalse(os.path.exists(d))

    def test_dest_not_empty_or_overlapping(self):
        d = self.dest()
        os.makedirs(d)
        open(os.path.join(d, "x"), "w").close()
        code, rep = snap.run_snapshot(self.spec(self.src_spec()), d, "ref", True)[0:2]
        self.assertIn("dest_exists_not_empty", self.codes(rep))
        inside = os.path.join(self.src, "dest_inside_src")
        code, rep = snap.run_snapshot(self.spec(self.src_spec()), inside, "ref", True)[0:2]
        self.assertEqual(code, 0)                                         # un file sorgente non contiene la dest
        code, rep = snap.run_snapshot(self.spec([{"id": "t", "kind": "tree", "path": self.src}]), inside, "ref", True)[0:2]
        self.assertIn("dest_overlaps_source", self.codes(rep))

    def test_source_missing_symlink_unreadable(self):
        code, rep, _ = self.go([{"id": "m", "kind": "file", "path": self.p("nope")}], dry_run=True)
        self.assertIn("source_missing", self.codes(rep))
        os.symlink(self.f, self.p("sl.jsonl"))
        code, rep, _ = self.go([{"id": "s", "kind": "jsonl", "path": self.p("sl.jsonl")}], dry_run=True)
        self.assertIn("source_is_symlink", self.codes(rep))
        if not ROOT:
            u = self.write("u.jsonl", "{}\n")
            os.chmod(u, 0)
            code, rep, _ = self.go([{"id": "u", "kind": "jsonl", "path": u}], dry_run=True)
            self.assertIn("source_not_readable", self.codes(rep))

    def test_insufficient_space(self):
        fake = mock.Mock(free=1000)
        with mock.patch.object(snap.shutil, "disk_usage", return_value=fake):
            code, rep, _ = self.go(self.src_spec(), dry_run=True)
        self.assertEqual(code, 1)
        self.assertIn("insufficient_space", self.codes(rep))

    def test_spec_validation(self):
        bad = [[{"id": "a", "kind": "jsonl", "path": "relative.jsonl"}],
               [{"id": "a", "kind": "x", "path": self.f}],
               [{"id": "a b", "kind": "file", "path": self.f}],
               [{"id": "a", "kind": "file", "path": self.f}, {"id": "a", "kind": "file", "path": self.f}],
               [{"id": "a", "kind": "file", "path": "/x/../etc/passwd"}],
               [{"id": "a", "kind": "file", "path": "/opt/app/.env"}]]
        for s in bad:
            with self.assertRaises(ValueError):
                snap.load_spec(self.spec(s))

    def test_outputs_private_and_logged(self):
        code, rep, d = self.go(self.src_spec())
        self.assertEqual(code, 0)
        self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700)
        for f in (os.path.join(d, "a", "a.jsonl"), os.path.join(d, "snapshot_log.json")):
            self.assertEqual(stat.S_IMODE(os.stat(f).st_mode), 0o400)
        log = load(os.path.join(d, "snapshot_log.json"))
        self.assertEqual(log["auth_ref"], "ISSUE-113#test")
        self.assertEqual(log["consistency"], "per_item_not_atomic_across_sources")
        self.assertIn("window_seconds", log)

    def test_cli_refuses_git_worktree_dest(self):
        repo = os.path.join(self.t, "repo")
        subprocess.run(["git", "init", "-q", repo], check=True)
        spec = self.spec(self.src_spec())
        self.assertEqual(snap.main(["--spec", spec, "--dest", os.path.join(repo, "d"), "--dry-run"]), 1)


class AuditRestore(Base):
    def build(self, tamper=None, anchor_count=None):
        head = make_v3_db(self.p("j.sqlite3"), 5, tamper)
        self.write("h.jsonl", '{"run_no":1}\n{"run_no":2}\n')
        self.write("s.json", '{"k":1}')
        self.anchor = {"j": {"count": 5 if anchor_count is None else anchor_count, "head": head}}
        code, rep, d = self.go([{"id": "j", "kind": "sqlite", "path": self.p("j.sqlite3")},
                                {"id": "h", "kind": "jsonl", "path": self.p("h.jsonl")},
                                {"id": "s", "kind": "file", "path": self.p("s.json")}])
        self.assertEqual(code, 0, rep.get("items"))
        return d

    def restore_and_audit(self, d, expect=None):
        rd = os.path.join(self.work, f"restore{self.n}")
        self.n += 1
        res = audit.restore(d, rd)
        self.assertEqual(res["restore_errors"], [])
        return rd, res["log"], audit.audit(rd, res["log"], expect)

    def codes(self, rep, key="fails"):
        return {x["code"] for x in rep[key]}

    def test_clean_roundtrip_pass_with_anchor(self):
        d = self.build()
        rd, log, rep = self.restore_and_audit(d, self.anchor)
        self.assertEqual((rep["verdict"], rep["fails"], rep["warnings"]), ("PASS", [], []))
        ch = rep["checks"]["v3_chains"]["j"]
        self.assertEqual((ch["ok"], ch["count"], ch["per_run"]), (True, 5, {"brain/run1": 3, "brain/run2": 2}))
        self.assertEqual(rep["notes"], ["capture_not_atomic_across_sources"])
        self.assertEqual(audit.summary_of(rep)["v3_chains_ok"], 1)

    def test_without_anchor_warns(self):
        d = self.build()
        _, _, rep = self.restore_and_audit(d)
        self.assertEqual(rep["verdict"], "WARN")
        self.assertIn("v3_chain_no_external_anchor", self.codes(rep, "warnings"))

    def test_tail_truncation_needs_anchor(self):
        d = self.build(anchor_count=6)                                    # l'ancora dice 6, la copia ne ha 5
        _, _, rep = self.restore_and_audit(d, self.anchor)
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertIn("v3_chain_external_anchor_mismatch", self.codes(rep))

    def test_tampered_payload_detected(self):
        d = self.build(tamper="payload")
        _, _, rep = self.restore_and_audit(d, self.anchor)
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertIn("v3_chain_event_hash_mismatch", self.codes(rep))

    def test_deleted_event_detected(self):
        d = self.build(tamper="gap")
        _, _, rep = self.restore_and_audit(d, self.anchor)
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertIn("v3_chain_previous_hash_mismatch", self.codes(rep))

    def test_modified_missing_extra_files(self):
        d = self.build()
        rd, log, _ = self.restore_and_audit(d, self.anchor)
        os.chmod(os.path.join(rd, "s", "s.json"), 0o600)
        with open(os.path.join(rd, "s", "s.json"), "w") as fh:
            fh.write("{}")
        os.remove(os.path.join(rd, "h", "h.jsonl"))
        with open(os.path.join(rd, "extra.txt"), "w") as fh:
            fh.write("x")
        rep = audit.audit(rd, log, self.anchor)
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertTrue({"sha256_mismatch", "missing_file", "extra_file"} <= self.codes(rep))

    def test_corrupted_sqlite_detected(self):
        d = self.build()
        rd, log, _ = self.restore_and_audit(d, self.anchor)
        p = os.path.join(rd, "j", "j.sqlite3")
        os.chmod(p, 0o600)
        with open(p, "r+b") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.truncate(size - 4096)
        rep = audit.audit(rd, log, self.anchor)
        self.assertEqual(rep["verdict"], "FAIL")

    def test_row_count_mismatch_vs_log(self):
        d = self.build()
        rd, log, _ = self.restore_and_audit(d, self.anchor)
        for it in log["items"]:
            if it["kind"] == "sqlite":
                it["tables"]["v3_events"] += 1
        self.assertIn("row_count_mismatch", self.codes(audit.audit(rd, log, self.anchor)))

    def test_failed_snapshot_item_is_fail(self):
        d = self.build()
        log = load(os.path.join(d, "snapshot_log.json"))
        log["items"][0]["status"] = "FAILED"
        log["items"][0]["reason"] = "busy_or_locked"
        rd = os.path.join(self.work, "rr")
        os.makedirs(rd)
        rep = audit.audit(rd, log)
        self.assertIn("snapshot_item_not_ok", self.codes(rep))

    def test_retries_and_partial_tail_are_warnings(self):
        d = self.build()
        rd, log, _ = self.restore_and_audit(d, self.anchor)
        log["items"][1]["attempts"] = 2
        log["items"][1]["partial_tail_bytes"] = 7
        log["window_seconds"] = 5000
        rep = audit.audit(rd, log, self.anchor)
        self.assertEqual(rep["verdict"], "WARN")
        self.assertTrue({"copy_needed_retries", "partial_tail_excluded", "capture_window_long"} <= self.codes(rep, "warnings"))

    def test_restore_refuses_nonempty_and_overlap(self):
        d = self.build()
        ne = os.path.join(self.work, "ne")
        os.makedirs(ne)
        open(os.path.join(ne, "f"), "w").close()
        with self.assertRaises(FileExistsError):
            audit.restore(d, ne)
        with self.assertRaises(ValueError):
            audit.restore(d, os.path.join(d, "sub"))

    def test_cli_end_to_end_and_outputs(self):
        d = self.build()
        anchor = os.path.join(self.t, "anchor.json")
        with open(anchor, "w") as fh:
            json.dump(self.anchor, fh)
        rep_p, sum_p = os.path.join(self.t, "rep.json"), os.path.join(self.t, "sum.json")
        rc = audit.main(["--snapshot", d, "--restore-dir", os.path.join(self.work, "rcli"), "--report", rep_p,
                         "--summary", sum_p, "--expect-v3", anchor])
        self.assertEqual(rc, 0)
        self.assertEqual(stat.S_IMODE(os.stat(rep_p).st_mode), 0o600)
        self.assertNotIn(self.src, rd(sum_p))
        self.assertEqual(load(sum_p)["verdict"], "PASS")
        self.assertEqual(audit.main(["--snapshot", d, "--restore-dir", os.path.join(self.work, "r2"),
                                     "--report", rep_p]), 1)               # report esistente


class V3ChainCrossCheck(unittest.TestCase):
    """Confronto con la vera classe EventJournal (PR #112), scaricata in una directory temporanea."""

    def test_matches_production_verify_chain(self):
        repo = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
        r = subprocess.run(["git", "-C", repo, "show", "pr112:backend/v3/events.py"], capture_output=True, text=True)
        if r.returncode != 0:
            self.skipTest("ref pr112 non disponibile nel clone")
        with tempfile.TemporaryDirectory() as t:
            mp = os.path.join(t, "prod_events.py")
            with open(mp, "w") as fh:
                fh.write(r.stdout)
            spec = importlib.util.spec_from_file_location("prod_events", mp)
            m = importlib.util.module_from_spec(spec)
            sys.modules["prod_events"] = m
            spec.loader.exec_module(m)
            db = os.path.join(t, "j.sqlite3")
            j = m.EventJournal(db)
            j.init_schema()
            for i in range(4):
                j.append(m.Event(f"ev{i}", "brain", "runA", "k", 1000 + i, "src", {"i": i, "z": "à"}))
            count, head = j.verify_chain()
            mine = audit.verify_v3_chain(db)
            self.assertEqual((mine["ok"], mine["count"], mine["head"]), (True, count, head))
            self.assertEqual(mine["per_run"], {"brain/runA": 4})
            con = sqlite3.connect(db)
            con.execute("DROP TRIGGER v3_no_update")
            con.execute("UPDATE v3_events SET payload_json='{\"i\":9,\"z\":\"x\"}' WHERE seq=2")
            con.commit()
            con.close()
            with self.assertRaises(ValueError):
                j.verify_chain()
            self.assertFalse(audit.verify_v3_chain(db)["ok"])


class Discover(unittest.TestCase):
    def test_redact_args(self):
        r = discover.redact_args("/usr/bin/python3 -m backend.v3.arena.runner --api-key sk-abcdef123456 "
                                 "--token=abc --config /opt/x/cfg.json --provider deepseek")
        self.assertNotIn("sk-abcdef", r)
        self.assertNotIn("abc", r.replace("backend", ""))
        self.assertNotIn("deepseek", r)
        self.assertIn("python3", r)
        self.assertIn("--token=<arg>", r)
        self.assertIn("/opt/x/cfg.json", r)
        self.assertEqual(discover.redact_args("x https://u:pw@host/p"), "x <redacted>")
        self.assertEqual(discover.redact_args("run " + "A" * 40), "run <redacted>")
        self.assertEqual(discover.redact_args(""), "")

    def test_parse_ps_filters_and_redacts(self):
        txt = ("  100     1 root     5000 /sbin/init\n"
               "  200     1 svc      120 /opt/v/bin/python3 /opt/superbot/run.py --secret sk-123456789abc\n"
               "  300     1 svc      12 nginx: worker\n")
        rows = discover.parse_ps(txt)
        self.assertEqual([r["pid"] for r in rows], [200])
        self.assertNotIn("sk-", json.dumps(rows))

    def test_parse_show(self):
        txt = ("Id=superbot-x.service\nActiveState=active\nExecStart={ path=/usr/bin/python3 ; "
               "argv[]=/usr/bin/python3 /opt/s/r.py --key abc123 ; ignore_errors=no }\n"
               "EnvironmentFiles=/etc/superbot/x.env (ignore_errors=no)\nEnvironment=API_KEY=hunter2\nMainPID=5\n")
        d = discover.parse_show(txt)
        self.assertEqual(d["EnvironmentFiles"], ["/etc/superbot/x.env"])
        self.assertNotIn("Environment", d)
        self.assertNotIn("hunter2", json.dumps(d))
        self.assertNotIn("abc123", d["ExecStart"])

    def test_discovery_with_fake_runner_and_no_forbidden_reads(self):
        calls = []

        def run(argv):
            calls.append(argv)
            if argv[:2] == ["systemctl", "list-units"]:
                return 0, "superbot-a.service loaded active running A\nother.service loaded active running B\n"
            if argv[:2] == ["systemctl", "show"]:
                return 0, "Id=superbot-a.service\nActiveState=active\nMainPID=7\n"
            if argv[0] == "ps":
                return 0, "  1 0 root 9 /opt/superbot/x.py --k v\n"
            return 0, "1001\n"
        opened = []
        real_open, real_osopen = builtins.open, os.open
        with tempfile.TemporaryDirectory() as t:
            meta_target = os.path.join(t, "data.jsonl")
            with real_open(meta_target, "w") as fh:
                fh.write("secret content\n")
            with mock.patch.object(builtins, "open", lambda p, *a, **k: (opened.append(str(p)), real_open(p, *a, **k))[1]), \
                    mock.patch.object(os, "open", lambda p, *a, **k: (opened.append(str(p)), real_osopen(p, *a, **k))[1]):
                rep = discover.run_discovery([meta_target, os.path.join(t, "missing")], run)
        self.assertEqual(opened, [])                                       # nessun file mai aperto
        self.assertEqual([u["unit"] for u in rep["systemd"]["units"]], ["superbot-a.service"])
        self.assertEqual([p["status"] for p in rep["paths"]], ["ok", "not_found"])
        self.assertNotIn("secret content", json.dumps(rep))
        self.assertFalse(rep["containers"]["readable"])
        for argv in calls:
            self.assertIn(argv[0], discover.ALLOWED)
            self.assertNotIn("cat", argv)
            self.assertNotIn("Environment", argv)

    def test_real_runner_rejects_other_commands(self):
        for argv in (["cat", "/etc/passwd"], ["sudo", "id"], ["docker", "ps"], ["systemctl", "cat", "x"],
                     ["systemctl", "restart", "x"], ["systemctl", "stop", "x"], ["journalctl"]):
            with self.assertRaises(ValueError):
                discover.real_runner(argv)

    def test_path_meta_states(self):
        with tempfile.TemporaryDirectory() as t:
            f = os.path.join(t, "f")
            open(f, "w").close()
            self.assertEqual(discover.path_meta(f)["status"], "ok")
            self.assertEqual(discover.path_meta(os.path.join(t, "no"))["status"], "not_found")
            if not ROOT:
                d = os.path.join(t, "locked")
                os.makedirs(os.path.join(d, "in"))
                os.chmod(d, 0)
                try:
                    self.assertEqual(discover.path_meta(d)["status"], "non_readable")
                    self.assertEqual(discover.path_meta(os.path.join(d, "in"))["status"], "permission_denied")
                finally:
                    os.chmod(d, 0o700)
            os.symlink(f, os.path.join(t, "ln"))
            self.assertEqual(discover.path_meta(os.path.join(t, "ln"))["kind"], "symlink")

    def test_codefp_finds_matching_commit(self):
        with tempfile.TemporaryDirectory() as t:
            repo, dep = os.path.join(t, "repo"), os.path.join(t, "deploy")
            os.makedirs(os.path.join(repo, "backend"))
            g = lambda *a: subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", *a],  # noqa: E731
                                          check=True, capture_output=True)
            subprocess.run(["git", "init", "-q", repo], check=True)
            for name, body in (("a.py", "x=1\n"), ("b.py", "y=2\n")):
                rw(os.path.join(repo, "backend", name), body)
            g("add", "-A")
            g("commit", "-qm", "c1")
            g("tag", "c1")
            rw(os.path.join(repo, "backend", "b.py"), "y=3\n")
            rw(os.path.join(repo, "backend", "c.py"), "z=1\n")
            g("add", "-A")
            g("commit", "-qm", "c2")
            g("tag", "c2")
            os.makedirs(dep)
            rw(os.path.join(dep, "a.py"), "x=1\n")
            rw(os.path.join(dep, "b.py"), "y=2\n")
            rw(os.path.join(dep, ".env"), "SECRET")
            rw(os.path.join(dep, "data.json"), "{}")
            fp = discover.fingerprint_dir(dep)
            self.assertEqual(sorted(fp["files"]), ["a.py", "b.py"])
            rows = discover.match_commits(fp, repo, ["c2", "c1"], subdir="backend")
            self.assertEqual([r["ref"] for r in rows], ["c1", "c2"])
            self.assertTrue(rows[0]["exact_match"])
            self.assertFalse(rows[1]["exact_match"])
            self.assertEqual((rows[1]["different"], rows[1]["only_in_commit"]), (1, 1))

    def test_cli_output_guard(self):
        with tempfile.TemporaryDirectory() as t:
            rep = os.path.join(t, "r.json")
            open(rep, "w").close()
            self.assertEqual(discover.main(["services", "--report", rep]), 1)
            repo = os.path.join(t, "repo")
            subprocess.run(["git", "init", "-q", repo], check=True)
            self.assertEqual(discover.main(["services", "--report", os.path.join(repo, "r.json")]), 1)


class Orchestrator(Base):
    def test_end_to_end_steps(self):
        head = make_v3_db(self.p("journal.sqlite3"), 4)
        self.write("hist.jsonl", '{"run_no":1}\n{"run_no":2}\n')
        self.write("arch/run1/trade.jsonl", '{"run_no":1}\n')
        self.write("arch/.env", "SECRET")
        spec = self.spec([{"id": "journal", "kind": "sqlite", "path": self.p("journal.sqlite3")},
                          {"id": "hist", "kind": "jsonl", "path": self.p("hist.jsonl")},
                          {"id": "arch", "kind": "tree", "path": self.p("arch")}])
        anchor = os.path.join(self.t, "anchor.json")
        with open(anchor, "w") as fh:
            json.dump({"journal": {"count": 4, "head": head}}, fh)
        W = os.path.join(self.t, "ph0")
        before = tree_state(self.src)
        self.assertEqual(phase0.main(["--work", W, "step2-preflight", "--spec", spec]), 0)
        self.assertFalse(os.path.exists(os.path.join(W, "snapshot")))              # il preflight non copia
        self.assertEqual(phase0.main(["--work", W, "step4-manifest"]), 1)           # senza snapshot: NO-GO
        self.assertEqual(phase0.main(["--work", W, "step5-restore-audit"]), 1)
        self.assertEqual(phase0.main(["--work", W, "step3-snapshot", "--spec", spec, "--auth-ref", "ISSUE-113#c"]), 0)
        self.assertEqual(phase0.main(["--work", W, "step3-snapshot", "--spec", spec, "--auth-ref", "x"]), 1)  # dest non vuota
        self.assertEqual(phase0.main(["--work", W, "step4-manifest"]), 0)
        self.assertEqual(phase0.main(["--work", W, "step5-restore-audit", "--expect-v3", anchor]), 0)
        self.assertEqual(before, tree_state(self.src))                              # sorgenti intatte
        R = os.path.join(W, "reports")
        self.assertEqual(sorted(os.listdir(R)), ["step4_manifest.json", "step4_manifest_summary.json",
                                                 "step5_audit.json", "step5_audit_summary.json"])
        for f in ("step4_manifest.json", "step5_audit.json"):
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(R, f)).st_mode), 0o600)
        self.assertEqual(load(os.path.join(R, "step5_audit_summary.json"))["verdict"], "PASS")
        m = load(os.path.join(R, "step4_manifest.json"))
        self.assertTrue(m["complete"])
        self.assertEqual(m["skipped_live_db"], 0)
        self.assertNotIn("SECRET", json.dumps(load(os.path.join(W, "snapshot", "snapshot_log.json"))))
        self.assertEqual(phase0.main(["--work", W, "status"]), 0)

    def test_step3_requires_auth_ref_argument(self):
        spec = self.spec([{"id": "a", "kind": "file", "path": self.write("a.json", "{}")}])
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            phase0.main(["--work", os.path.join(self.t, "w"), "step3-snapshot", "--spec", spec])

    def test_work_dir_in_git_refused(self):
        repo = os.path.join(self.t, "repo")
        subprocess.run(["git", "init", "-q", repo], check=True)
        spec = self.spec([{"id": "a", "kind": "file", "path": self.write("a.json", "{}")}])
        self.assertEqual(phase0.main(["--work", os.path.join(repo, "w", "deep"), "step2-preflight", "--spec", spec]), 1)
        self.assertFalse(os.path.exists(os.path.join(repo, "w")))


if __name__ == "__main__":
    unittest.main()
