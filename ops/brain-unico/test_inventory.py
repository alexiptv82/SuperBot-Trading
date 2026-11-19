"""Test su fixture sintetiche (nessun dato reale)."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import inventory as inv  # noqa: E402


def snapshot(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            st = os.stat(p)
            out[p] = (st.st_size, st.st_mtime_ns)
    return out


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = os.path.join(self.tmp.name, "src")
        self.outdir = os.path.join(self.tmp.name, "out")
        os.makedirs(self.src)
        os.makedirs(self.outdir)
        with open(os.path.join(self.src, "t.jsonl"), "w") as fh:
            fh.write('{"run_no":1,"portfolio_id":"x"}\n{"run_no":2}\nNOT JSON\n\n')
        with open(os.path.join(self.src, ".env"), "w") as fh:
            fh.write("API_KEY=SUPERSECRETVALUE\n")
        with open(os.path.join(self.src, "api_key.txt"), "w") as fh:
            fh.write("SUPERSECRETVALUE")
        con = sqlite3.connect(os.path.join(self.src, "b.sqlite3"))
        con.execute("create table events(a)")
        con.executemany("insert into events values(?)", [(1,), (2,), (3,)])
        con.commit()
        con.close()
        os.symlink("/etc/hostname", os.path.join(self.src, "link"))

    def run_cli(self, *extra):
        out = os.path.join(self.outdir, "m.json")
        rc = inv.main(["--root", f"lab={self.src}", "--out", out, *extra])
        return rc, out

    def test_counts_hashes_and_no_secrets(self):
        before = snapshot(self.src)
        rc, out = self.run_cli("--sqlite")
        self.assertEqual(rc, 0)
        raw = open(out).read()
        self.assertNotIn("SUPERSECRETVALUE", raw)
        m = json.loads(raw)
        paths = {e["path"] for e in m["entries"]}
        self.assertEqual(paths, {"lab/t.jsonl", "lab/b.sqlite3"})
        self.assertEqual(m["excluded_sensitive_count"], 2)
        j = next(e for e in m["entries"] if e["path"] == "lab/t.jsonl")
        self.assertEqual((j["lines"], j["invalid_lines"]), (3, 1))
        self.assertEqual(j["distinct_run_no"], ["1", "2"])
        s = next(e for e in m["entries"] if e["path"] == "lab/b.sqlite3")
        self.assertEqual(s["tables"]["events"]["rows"], 3)
        self.assertEqual(before, snapshot(self.src))   # sorgente invariata

    def test_sqlite_not_opened_by_default(self):
        _, out = self.run_cli()
        s = next(e for e in json.load(open(out))["entries"] if e["path"].endswith(".sqlite3"))
        self.assertNotIn("tables", s)

    def test_digest_stable_and_changes(self):
        _, o1 = self.run_cli()
        d1 = json.load(open(o1))["manifest_digest"]
        os.remove(o1)
        _, o2 = self.run_cli()
        self.assertEqual(d1, json.load(open(o2))["manifest_digest"])
        os.remove(o2)
        with open(os.path.join(self.src, "t.jsonl"), "a") as fh:
            fh.write('{"run_no":3}\n')
        _, o3 = self.run_cli()
        self.assertNotEqual(d1, json.load(open(o3))["manifest_digest"])

    def test_refuses_out_inside_root_and_overwrite(self):
        self.assertEqual(inv.main(["--root", f"lab={self.src}", "--out", os.path.join(self.src, "m.json")]), 2)
        _, out = self.run_cli()
        self.assertEqual(inv.main(["--root", f"lab={self.src}", "--out", out]), 2)

    def test_git_info(self):
        subprocess.run(["git", "init", "-q", self.src], check=True)
        subprocess.run(["git", "-C", self.src, "-c", "user.name=t", "-c", "user.email=t@t", "commit",
                        "-q", "--allow-empty", "-m", "x"], check=True)
        g = inv.git_info(self.src)
        self.assertEqual(len(g["head"]), 40)
        self.assertEqual(g["modified_tracked_count"], 0)


if __name__ == "__main__":
    unittest.main()
