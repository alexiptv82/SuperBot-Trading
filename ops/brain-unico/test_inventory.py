"""Test su fixture sintetiche (nessun dato reale, nessuna rete)."""
import json
import os
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inventory as inv  # noqa: E402


def snapshot(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            st = os.lstat(p)
            out[p] = (st.st_size, st.st_mtime_ns)
    return out


def slurp(path):
    with open(path) as fh:
        return fh.read()


def load(path):
    with open(path) as fh:
        return json.load(fh)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = os.path.join(self.tmp.name, "src")
        self.outdir = os.path.join(self.tmp.name, "out")
        os.makedirs(self.src)
        os.makedirs(self.outdir)
        self.n = 0

    def run_cli(self, *extra):
        self.n += 1
        out = os.path.join(self.outdir, f"m{self.n}.json")
        rc = inv.main(["--root", f"lab={self.src}", "--out", out, *extra])
        return rc, out

    def write(self, name, data, mode="w"):
        p = os.path.join(self.src, name)
        with open(p, mode) as fh:
            fh.write(data)
        return p

    def entry(self, m, suffix):
        return next(e for e in m["entries"] if e["path"].endswith(suffix))


class CoreTest(Base):
    def setUp(self):
        super().setUp()
        self.write("t.jsonl", '{"run_no":1,"portfolio_id":"x"}\n{"run_no":2}\nNOT JSON\n\n')
        self.write(".env", "API_KEY=SUPERSECRETVALUE\n")
        self.write("api_key.txt", "SUPERSECRETVALUE")
        os.symlink("/etc/hostname", os.path.join(self.src, "link"))

    def test_counts_hashes_no_secrets_source_untouched(self):
        before = snapshot(self.src)
        rc, out = self.run_cli()
        self.assertEqual(rc, 0)
        raw = slurp(out)
        self.assertNotIn("SUPERSECRETVALUE", raw)
        m = json.loads(raw)
        self.assertEqual([e["path"] for e in m["entries"]], ["lab/t.jsonl"])
        self.assertEqual((m["excluded_sensitive_count"], m["symlinks_skipped"]), (2, 1))
        j = m["entries"][0]
        self.assertEqual((j["lines"], j["invalid_lines"]), (3, 1))
        self.assertEqual(j["distinct_run_no_count"], 2)
        self.assertTrue(m["complete"])
        self.assertIs(m["certifies_backup"], False)
        self.assertEqual(m["classification"], "PRIVATE_DO_NOT_COMMIT")
        self.assertEqual(before, snapshot(self.src))

    def test_out_mode_0600_and_summary_is_numbers_only(self):
        sm = os.path.join(self.outdir, "summary.json")
        rc, out = self.run_cli("--summary-out", sm)
        self.assertEqual(rc, 0)
        self.assertEqual(stat.S_IMODE(os.stat(out).st_mode), 0o600)
        s = load(sm)
        self.assertEqual(s["classification"], "PUBLIC_SUMMARY_NUMBERS_ONLY")
        self.assertNotIn("entries", s)
        self.assertNotIn("lab/", slurp(sm))

    def test_digest_stable_and_changes(self):
        _, o1 = self.run_cli()
        _, o2 = self.run_cli()
        d1 = load(o1)["manifest_digest"]
        self.assertEqual(d1, load(o2)["manifest_digest"])
        self.write("t.jsonl", '{"run_no":3}\n', "a")
        _, o3 = self.run_cli()
        self.assertNotEqual(d1, load(o3)["manifest_digest"])

    def test_output_collisions(self):
        self.assertEqual(inv.main(["--root", f"lab={self.src}", "--out", os.path.join(self.src, "m.json")]), 2)
        _, out = self.run_cli()
        self.assertEqual(inv.main(["--root", f"lab={self.src}", "--out", out]), 2)
        # summary che collide con out gia' esistente
        sm = os.path.join(self.outdir, "s.json")
        with open(sm, "w"):
            pass
        self.assertEqual(inv.main(["--root", f"lab={self.src}", "--out", os.path.join(self.outdir, "z.json"),
                                   "--summary-out", sm]), 2)
        self.assertFalse(os.path.exists(os.path.join(self.outdir, "z.json")))
        # out dietro un symlink pendente: lexists -> rifiutato
        dang = os.path.join(self.outdir, "dang.json")
        os.symlink(os.path.join(self.outdir, "nowhere"), dang)
        self.assertEqual(inv.main(["--root", f"lab={self.src}", "--out", dang]), 2)

    def test_out_equals_summary_out_refused_before_writing(self):
        same = os.path.join(self.outdir, "same.json")
        self.assertEqual(inv.main(["--root", f"lab={self.src}", "--out", same, "--summary-out", same]), 2)
        self.assertFalse(os.path.exists(same))
        alias = os.path.join(self.outdir, "sub", "..", "same.json")           # stesso file, percorso diverso
        os.makedirs(os.path.join(self.outdir, "sub"))
        self.assertEqual(inv.main(["--root", f"lab={self.src}", "--out", same, "--summary-out", alias]), 2)
        self.assertEqual(os.listdir(self.outdir), ["sub"])

    def test_out_inside_git_worktree_refused(self):
        repo = os.path.join(self.tmp.name, "repo")
        subprocess.run(["git", "init", "-q", repo], check=True)
        out = os.path.join(repo, "manifest.json")
        self.assertEqual(inv.main(["--root", f"lab={self.src}", "--out", out]), 2)
        self.assertFalse(os.path.exists(out))

    def test_git_info(self):
        repo = os.path.join(self.tmp.name, "repo")
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit",
                        "-q", "--allow-empty", "-m", "x"], check=True)
        g = inv.git_info(repo)
        self.assertEqual(len(g["head"]), 40)
        self.assertEqual(g["modified_tracked_count"], 0)


class TraversalAndSpecialFiles(Base):
    def test_unreadable_directory_marks_incomplete(self):
        if os.geteuid() == 0:
            self.skipTest("root ignora i permessi")
        self.write("ok.jsonl", '{"run_id":"a"}\n')
        sub = os.path.join(self.src, "locked")
        os.makedirs(sub)
        self.write("locked/hidden.jsonl", "{}\n")
        os.chmod(sub, 0)
        self.addCleanup(os.chmod, sub, 0o700)
        rc, out = self.run_cli()
        m = load(out)
        self.assertEqual(rc, 0)
        self.assertFalse(m["complete"])
        self.assertEqual([e["path"] for e in m["traverse_errors"]], ["lab/locked"])

    def test_fifo_is_never_opened(self):
        self.write("ok.jsonl", "{}\n")
        os.mkfifo(os.path.join(self.src, "pipe.jsonl"))
        signal.signal(signal.SIGALRM, lambda *_: self.fail("scansione bloccata su FIFO"))
        signal.alarm(10)
        try:
            rc, out = self.run_cli()
        finally:
            signal.alarm(0)
        m = load(out)
        self.assertEqual(m["special_files"], 1)
        self.assertEqual([e["path"] for e in m["entries"]], ["lab/ok.jsonl"])
        self.assertTrue(m["complete"])

    def test_read_regular_rejects_symlink_and_fifo(self):
        t = self.write("real.txt", "x")
        os.symlink(t, os.path.join(self.src, "sl"))
        os.mkfifo(os.path.join(self.src, "ff"))
        self.assertEqual(inv.read_regular(os.path.join(self.src, "sl")), {"special": True})
        self.assertEqual(inv.read_regular(os.path.join(self.src, "ff")), {"special": True})
        self.assertIn("sha256", inv.read_regular(t))


class StabilityTest(Base):
    def tearDown(self):
        inv._TEST_HOOK = None

    def test_file_changing_during_read_is_unstable(self):
        p = self.write("grow.jsonl", '{"run_id":"a"}\n')

        def grow(path):
            with open(path, "a") as fh:
                fh.write('{"run_id":"b"}\n')
        inv._TEST_HOOK = grow
        _, out = self.run_cli()
        m = load(out)
        self.assertFalse(m["complete"])
        self.assertEqual(m["unstable_count"], 1)
        self.assertTrue(self.entry(m, "grow.jsonl")["unstable"])

    def test_file_replaced_during_read_is_unstable(self):
        p = self.write("swap.jsonl", '{"run_id":"a"}\n')

        def swap(path):
            os.rename(path, path + ".old")
            with open(path, "w") as fh:
                fh.write("{}\n")
        inv._TEST_HOOK = swap
        _, out = self.run_cli()
        self.assertTrue(self.entry(load(out), "swap.jsonl")["unstable"])

    def test_stable_file_not_flagged(self):
        self.write("s.jsonl", "{}\n")
        _, out = self.run_cli()
        m = load(out)
        self.assertTrue(m["complete"])
        self.assertNotIn("unstable", self.entry(m, "s.jsonl"))


class DatabaseTest(Base):
    def make_db(self, name="b.sqlite3"):
        p = os.path.join(self.src, name)
        con = sqlite3.connect(p)
        con.execute("create table events(a)")
        con.executemany("insert into events values(?)", [(1,), (2,), (3,)])
        con.execute("create table nr(k text primary key, v) without rowid")
        con.executemany("insert into nr values(?,?)", [("a", 1), ("b", 2)])
        con.commit()
        con.close()
        return p

    def test_db_not_read_nor_hashed_by_default(self):
        self.make_db()
        _, out = self.run_cli()
        m = load(out)
        e = self.entry(m, "b.sqlite3")
        self.assertEqual(e["skipped"], "live_db_not_read")
        self.assertNotIn("sha256", e)
        self.assertEqual((m["skipped_live_db"], m["files_hashed"]), (1, 0))

    def test_include_db_hashes_without_sql(self):
        self.make_db()
        _, out = self.run_cli("--include-db")
        e = self.entry(load(out), "b.sqlite3")
        self.assertIn("sha256", e)
        self.assertNotIn("tables", e)

    def test_sqlite_counts_including_without_rowid(self):
        self.make_db()
        _, out = self.run_cli("--sqlite")
        t = self.entry(load(out), "b.sqlite3")["tables"]
        self.assertEqual(t["events"], {"rows": 3, "max_rowid": 3})
        self.assertEqual(t["nr"], {"rows": 2, "max_rowid": None})

    def test_wal_present_skips_sql_and_sidefiles_not_read(self):
        p = self.make_db("w.sqlite3")
        con = sqlite3.connect(p)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("insert into events values(99)")
        con.commit()                                   # connessione aperta: -wal non vuoto
        self.addCleanup(con.close)
        self.assertGreater(os.path.getsize(p + "-wal"), 0)
        _, out = self.run_cli()
        m = load(out)
        for suf in ("w.sqlite3", "w.sqlite3-wal", "w.sqlite3-shm"):
            self.assertEqual(self.entry(m, suf)["skipped"], "live_db_not_read")
        _, out2 = self.run_cli("--sqlite")
        e = self.entry(load(out2), "w.sqlite3")
        self.assertEqual(e["sql_skipped"], "wal_present")
        self.assertNotIn("tables", e)

    def test_source_db_untouched_by_sqlite_mode(self):
        self.make_db()
        before = snapshot(self.src)
        self.run_cli("--sqlite")
        self.assertEqual(before, snapshot(self.src))


class PrivacyTest(Base):
    def setUp(self):
        super().setUp()
        rows = [{"run_id": "ok_1"}, {"run_id": "../../etc/passwd"}, {"run_id": "a b"},
                {"run_id": "x" * 200}, {"run_id": "line\nbreak"}, {"portfolio_id": "brain"},
                {"run_no": 7}, {"run_id": True}, {"run_id": {"n": 1}}]
        self.write("p.jsonl", "".join(json.dumps(r) + "\n" for r in rows))

    def test_default_exports_no_id_values(self):
        _, out = self.run_cli()
        raw = slurp(out)
        e = self.entry(json.loads(raw), "p.jsonl")
        self.assertEqual(e["distinct_run_id_count"], 1)
        self.assertEqual(e["id_values_not_exported"], 6)
        for leak in ("ok_1", "passwd", "brain", "xxxx", "break"):
            self.assertNotIn(leak, raw)

    def test_include_ids_exports_only_safe_values(self):
        _, out = self.run_cli("--include-ids")
        raw = slurp(out)
        e = self.entry(json.loads(raw), "p.jsonl")
        self.assertEqual(e["distinct_run_id"], ["ok_1"])
        self.assertEqual(e["distinct_portfolio_id"], ["brain"])
        self.assertEqual(e["distinct_run_no"], ["7"])
        for leak in ("passwd", "a b", "xxxx", "break"):
            self.assertNotIn(leak, raw)

    def test_distinct_ids_capped(self):
        self.write("many.jsonl", "".join(json.dumps({"run_id": f"r{i}"}) + "\n" for i in range(inv.MAX_TRACK + 5)))
        _, out = self.run_cli("--include-ids")
        e = self.entry(load(out), "many.jsonl")
        self.assertEqual(e["distinct_run_id_count"], inv.MAX_TRACK)
        self.assertEqual(e["distinct_capped"], ["run_id"])
        self.assertEqual(len(e["distinct_run_id"]), inv.MAX_SHOWN)

    def test_oversized_line_counted_invalid_not_stored(self):
        old = inv.MAX_LINE
        inv.MAX_LINE = 1024
        self.addCleanup(setattr, inv, "MAX_LINE", old)
        self.write("big.jsonl", "A" * 5000 + '\n{"run_id":"z"}\n')
        _, out = self.run_cli()
        e = self.entry(load(out), "big.jsonl")
        self.assertGreaterEqual(e["invalid_lines"], 1)


class LongLineTest(Base):
    """Righe oltre MAX_LINE e oltre CHUNK: contate UNA volta, la coda non diventa una riga nuova."""

    def setUp(self):
        super().setUp()
        for name, val in (("MAX_LINE", 100), ("CHUNK", 64)):
            old = getattr(inv, name)
            setattr(inv, name, val)
            self.addCleanup(setattr, inv, name, old)

    def stats(self, content):
        self.write("l.jsonl", content)
        _, out = self.run_cli("--include-ids")
        return self.entry(load(out), "l.jsonl")

    def test_single_line_over_max_and_chunk_counted_once(self):
        e = self.stats('{"run_id":"a"}\n' + "A" * 1000 + '\n{"run_id":"b"}\n')
        self.assertEqual((e["lines"], e["invalid_lines"]), (3, 1))
        self.assertEqual(e["distinct_run_id"], ["a", "b"])

    def test_tail_of_long_line_is_not_a_new_line(self):
        # la coda assomiglia a una riga JSON valida ma appartiene alla riga lunga
        e = self.stats("A" * 500 + '{"run_id":"tail"}\n{"run_id":"b"}\n')
        self.assertEqual((e["lines"], e["invalid_lines"]), (2, 1))
        self.assertEqual(e["distinct_run_id"], ["b"])

    def test_long_line_at_eof_without_newline(self):
        e = self.stats('{"run_id":"a"}\n' + "A" * 700)
        self.assertEqual((e["lines"], e["invalid_lines"]), (2, 1))

    def test_long_line_ending_exactly_on_chunk_boundary(self):
        e = self.stats("A" * 127 + "\n" + '{"run_id":"b"}\n')      # 127 + a-capo = 2 chunk da 64
        self.assertEqual((e["lines"], e["invalid_lines"]), (2, 1))
        self.assertEqual(e["distinct_run_id"], ["b"])

    def test_valid_line_spanning_chunks_still_parsed(self):
        row = json.dumps({"run_id": "multi", "pad": "x" * 55})
        self.assertTrue(inv.CHUNK < len(row) <= inv.MAX_LINE, len(row))   # >1 chunk ma entro il limite
        e = self.stats(row + "\n")
        self.assertEqual((e["lines"], e["invalid_lines"]), (1, 0))
        self.assertEqual(e["distinct_run_id"], ["multi"])

    def test_complete_long_line_inside_one_chunk_is_invalid(self):
        inv.CHUNK = 1 << 20
        e = self.stats('{"run_id":"' + "z" * 300 + '"}\n{"run_id":"b"}\n')
        self.assertEqual((e["lines"], e["invalid_lines"]), (2, 1))
        self.assertEqual(e["distinct_run_id"], ["b"])

    def test_hash_unaffected_by_discarding(self):
        content = "A" * 1000 + "\n"
        p = self.write("h.jsonl", content)
        import hashlib
        _, out = self.run_cli()
        self.assertEqual(self.entry(load(out), "h.jsonl")["sha256"],
                         hashlib.sha256(content.encode()).hexdigest())


if __name__ == "__main__":
    unittest.main()
