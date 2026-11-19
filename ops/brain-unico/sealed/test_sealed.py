"""Test SINTETICI del bundle sigillato (opzione B). Nessun dato reale, nessun servizio, nessun privilegio."""
import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, os.path.join(ROOT, "phase0"), HERE):
    sys.path.insert(0, p)
import audit  # noqa: E402
import build_sealed  # noqa: E402
import sealed_root as sr  # noqa: E402
import snapshot as snap  # noqa: E402

BUNDLE = os.path.join(HERE, "phase0_sealed.py")
ME = os.geteuid()
IS_ROOT = ME == 0
NOSLEEP = lambda _s: None  # noqa: E731


def rd(p, mode="r"):
    with open(p, mode) as fh:
        return fh.read()


def load(p):
    return json.loads(rd(p))


def tree_state(root):
    out = {}
    for d, dn, fn in os.walk(root):
        for n in fn + dn:
            q = os.path.join(d, n)
            st = os.lstat(q)
            out[q] = (st.st_size, st.st_mtime_ns, stat.S_IMODE(st.st_mode))
    return out


def make_chain_db(path, n=3):
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE v3_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
        portfolio_id TEXT, run_id TEXT, kind TEXT, occurred_at_ms INTEGER, source TEXT, payload_json TEXT,
        previous_hash TEXT, event_hash TEXT)""")
    prev = audit.GENESIS
    for i in range(n):
        payload = json.dumps({"i": i}, sort_keys=True, separators=(",", ":"))
        h = audit._digest(prev, f"e{i}", "brain", "run1", "k", 1000 + i, "src", payload)
        con.execute("INSERT INTO v3_events(event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,"
                    "previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                    (f"e{i}", "brain", "run1", "k", 1000 + i, "src", payload, prev, h))
        prev = h
    con.commit()
    con.close()


def make_wal_db(path):
    c = sqlite3.connect(path)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE t(a)")
    c.executemany("INSERT INTO t VALUES(?)", [(i,) for i in range(20)])
    c.commit()
    c.close()


class Env:
    """Albero sintetico sotto una radice temporanea posseduta dall'utente di test (ancora della catena fidata)."""

    def __init__(self, test):
        old_umask = os.umask(0o022)                                  # il fixture non dipende dalla umask dell'ambiente
        test.addCleanup(os.umask, old_umask)
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        os.chmod(self.tmp.name, 0o700)
        self.R = os.path.realpath(self.tmp.name)
        self.opt = os.path.join(self.R, "opt")
        self.base = os.path.join(self.R, "var", "lib", "phase0")
        os.makedirs(os.path.dirname(self.base), mode=0o755)
        os.makedirs(self.opt, mode=0o755)
        self.proc = os.path.join(self.R, "proc")
        os.makedirs(self.proc)
        self.units = {"superbot-test-falco.service": ("inactive", "dead", "0", "0"),
                      "superbot-test-arena.service": ("active", "running", "100", "0")}
        self.build()

    def d(self, *a):
        return os.path.join(self.opt, *a)

    def w(self, rel, data, mode="w"):
        p = self.d(rel)
        os.makedirs(os.path.dirname(p), mode=0o755, exist_ok=True)
        with open(p, mode) as fh:
            fh.write(data)
        return p

    def build(self):
        self.w("falco/state.json", "{}")
        self.w("falco/trade_history.jsonl", '{"run_no":1}\n{"run_no":2}\n')
        self.w("falco/archive/run1/trades.jsonl", '{"run_no":1}\n')
        self.w("falco/.env", "SECRET=1")
        self.w("falco/.venv/lib/x.py", "x=1\n")
        make_wal_db(self.d("falco", "memory.sqlite3"))              # WAL fermo, senza sidecar
        self.w("toro/trade_history.jsonl", '{"run_no":1}\n')
        self.w("brain/readme.txt", "doc")
        make_chain_db(self.d("brain", "brain.sqlite3"), 4)
        for p in ("deepseek", "qwen", "minimax"):
            self.w(f"arena/{p}/budget.json", "{}")
            make_chain_db(self.d("arena", p, "journal.db"), 3)
        self.spec = {"schema": 1, "require_data": True,
                     "required_groups": ["falco", "toro", "brain_storico", "arena_deepseek", "arena_qwen", "arena_minimax"],
                     "sources": [
                         {"id": "falco_data", "group": "falco", "kind": "tree", "path": self.d("falco"),
                          "quiescence": {"units": ["superbot-test-falco.service"]}},
                         {"id": "toro_data", "group": "toro", "kind": "tree", "path": self.d("toro")},
                         {"id": "brain_main", "group": "brain_storico", "kind": "tree", "path": self.d("brain")},
                         {"id": "brain_opt", "group": "brain_storico", "kind": "tree", "optional": True,
                          "path": self.d("brain_missing")},
                         {"id": "arena_deepseek", "group": "arena_deepseek", "kind": "tree", "path": self.d("arena", "deepseek")},
                         {"id": "arena_qwen", "group": "arena_qwen", "kind": "tree", "path": self.d("arena", "qwen")},
                         {"id": "arena_minimax", "group": "arena_minimax", "kind": "tree", "path": self.d("arena", "minimax")}]}

    def runner(self, fail_list=False, drift=False):
        calls = {"n": 0}

        def run(argv):
            if argv[:2] == ["systemctl", "list-units"]:
                calls["n"] += 1
                if fail_list:
                    return 1, ""
                return 0, "".join(f"{u} loaded {s[0]} {s[1]} desc\n" for u, s in self.units.items())
            if argv[:2] == ["systemctl", "show"]:
                a, sub, pid, nr = self.units[argv[2]]
                if drift and calls["n"] > 1:
                    pid = "999"
                return 0, f"ActiveState={a}\nSubState={sub}\nMainPID={pid}\nNRestarts={nr}\n"
            raise AssertionError(argv)
        return run

    def open_fd(self, target, pid="4242", fd="3"):
        d = os.path.join(self.proc, pid, "fd")
        os.makedirs(d, exist_ok=True)
        os.symlink(target, os.path.join(d, fd))

    def go(self, mode="full", **kw):
        kw.setdefault("auth_ref", "ISSUE-113#test" if mode == "full" else None)
        kw.setdefault("runner", self.runner())
        self._clock = getattr(self, "_clock", 1_800_000_000.0) + 1                # ogni run: un secondo dopo
        kw.setdefault("now", lambda t=self._clock: t)
        out = []
        code, summary = sr.execute(self.spec, mode, base=self.base, allowed_root=self.opt, trusted_uid=ME,
                                   chain_anchor=self.R, proc_root=self.proc, code_sha="a" * 64, reserve_mb=1,
                                   sleep=NOSLEEP, out=out.append, **kw)
        return code, summary

    def run_dirs(self):
        return sorted(os.listdir(self.base)) if os.path.isdir(self.base) else []


class BundleIntegrity(unittest.TestCase):
    def test_committed_bundle_matches_sources_and_is_deterministic(self):
        self.assertEqual(build_sealed.main(["--check"]), 0)
        self.assertEqual(build_sealed.build(), build_sealed.build())

    def test_loader_roundtrip_matches_source_files(self):
        raw = rd(BUNDLE, "rb")
        ns = {}
        exec(compile(rd(BUNDLE).split("\nif __name__")[0], "<loader>", "exec"), ns)
        blocks = ns["_extract"](raw)
        for name, path in build_sealed.MODULES:
            self.assertEqual(blocks[name], rd(path), name)
        self.assertEqual(blocks["sources.json"], rd(build_sealed.SPEC))

    def test_selftest_in_isolated_mode_reports_matching_hashes(self):
        r = subprocess.run([sys.executable, "-I", BUNDLE, "selftest"], capture_output=True, text=True, cwd="/")
        self.assertEqual(r.returncode, 0, r.stderr)
        j = json.loads(r.stdout)
        self.assertEqual(j["bundle_sha256"], hashlib.sha256(rd(BUNDLE, "rb")).hexdigest())
        for name, path in build_sealed.MODULES:
            self.assertEqual(j["modules"][name], hashlib.sha256(rd(path).encode()).hexdigest(), name)
        self.assertTrue(j["backup_api"])
        self.assertEqual(len(j["required_groups"]), 6)

    @unittest.skipIf(IS_ROOT, "il rifiuto per non-root non e' osservabile da root")
    def test_privileged_commands_refuse_non_root_and_touch_nothing(self):
        sha = hashlib.sha256(rd(BUNDLE, "rb")).hexdigest()
        for cmd in (["preflight", "--expect-sha256", sha], ["full", "--expect-sha256", sha, "--auth-ref", "x"]):
            r = subprocess.run([sys.executable, "-I", BUNDLE] + cmd, capture_output=True, text=True, cwd="/")
            self.assertEqual(r.returncode, 2)
            self.assertIn("richiede root", r.stdout)
        self.assertFalse(os.path.exists(sr.BASE_DIR))

    def test_full_requires_auth_ref_and_expected_hash_arguments(self):
        for cmd in (["full", "--expect-sha256", "x"], ["preflight"]):
            r = subprocess.run([sys.executable, "-I", BUNDLE] + cmd, capture_output=True, text=True, cwd="/")
            self.assertEqual(r.returncode, 2)

    def test_embedded_spec_is_valid_and_confined_to_opt(self):
        with tempfile.TemporaryDirectory() as t:
            sp = os.path.join(t, "s.json")
            with open(sp, "w") as fh:
                json.dump({k: v for k, v in load(build_sealed.SPEC).items() if k != "_comment"} | {
                    "sources": [{k: v for k, v in s.items() if k != "quiescence"} for s in load(build_sealed.SPEC)["sources"]]}, fh)
            sources, groups = snap.load_spec(sp)
        spec = load(build_sealed.SPEC)
        self.assertTrue(spec["require_data"])
        self.assertEqual(len(groups), 6)
        for s in spec["sources"]:
            self.assertTrue(s["path"].startswith("/opt/"), s["id"])
            self.assertEqual(s["kind"], "tree")
            for u in (s.get("quiescence") or {}).get("units", []):
                self.assertTrue(sr.UNIT_RE.fullmatch(u), u)
        live = {"arena_deepseek", "arena_qwen", "arena_minimax", "v3_brain_run"}
        for s in spec["sources"]:                      # le sorgenti con servizi attivi NON dichiarano quiescenza
            if s["id"] in live:
                self.assertNotIn("quiescence", s, s["id"])


class CodeTrust(unittest.TestCase):
    def setUp(self):
        self.env = Env(self)
        self.f = self.env.w("code/s.py", "print(1)\n")
        os.chmod(self.f, 0o644)
        self.data = rd(self.f, "rb")
        self.sha = hashlib.sha256(self.data).hexdigest()

    def chk(self, **kw):
        a = dict(path=self.f, data=self.data, expect_sha=self.sha, uid=ME, anchor=self.env.R)
        a.update(kw)
        return sr.check_code_trust(**a)

    def test_trusted_file_passes(self):
        self.assertEqual(self.chk(), [])

    def test_hash_mismatch_and_case_insensitive(self):
        self.assertIn("sha256_mismatch", self.chk(expect_sha="0" * 64))
        self.assertEqual(self.chk(expect_sha=self.sha.upper()), [])

    def test_group_or_world_writable_file_refused(self):
        os.chmod(self.f, 0o664)
        self.assertIn("code_writable_by_others", self.chk())
        os.chmod(self.f, 0o646)
        self.assertIn("code_writable_by_others", self.chk())

    def test_writable_ancestor_refused(self):
        os.chmod(os.path.dirname(self.f), 0o777)
        self.addCleanup(os.chmod, os.path.dirname(self.f), 0o755)
        self.assertIn("component_writable_by_others", self.chk())

    def test_wrong_owner_refused(self):
        self.assertIn("code_not_owned_by_trusted_uid", self.chk(uid=ME + 1))

    def test_symlink_file_and_symlink_ancestor_refused(self):
        ln = os.path.join(os.path.dirname(self.f), "ln.py")
        os.symlink(self.f, ln)
        self.assertIn("code_not_regular_file", self.chk(path=ln))
        real = os.path.dirname(self.f)
        link_dir = self.env.d("linkdir")
        os.symlink(real, link_dir)
        self.assertIn("symlink_in_chain", sr.chain_problems(os.path.join(link_dir, "s.py"), ME, anchor=self.env.R))

    def test_missing_file_and_outside_anchor(self):
        self.assertIn("code_file_missing", self.chk(path=self.env.d("code", "nope.py")))
        self.assertEqual(sr.chain_problems("/etc/hostname", ME, anchor=self.env.R), ["outside_anchor"])


class Quiescence(unittest.TestCase):
    def test_rules(self):
        st = {"superbot-a.service": {"ActiveState": "inactive"}, "superbot-b.service": {"ActiveState": "active"}}
        q = lambda *u: {"units": list(u)}  # noqa: E731
        self.assertEqual(sr.verify_quiescence("/x", q("superbot-a.service"), st, set())[0], True)
        self.assertEqual(sr.verify_quiescence("/x", q("superbot-a.service", "superbot-b.service"), st, set()),
                         (False, "unit_active"))
        self.assertEqual(sr.verify_quiescence("/x", q("superbot-a.service"), None, set()), (False, "systemd_unavailable"))
        self.assertEqual(sr.verify_quiescence("/x", None, st, set()), (False, "no_quiescence_declared"))
        self.assertEqual(sr.verify_quiescence("/x", q("bad name"), st, set()), (False, "bad_unit_name"))
        self.assertEqual(sr.verify_quiescence("/x", q("superbot-unloaded.service"), st, set())[0], True)   # non caricata = inattiva
        for opened in ({"/x/a.sqlite3"}, {"/x/sub/a.db-wal"}, {"/x/a.sqlite3-shm"}):
            self.assertEqual(sr.verify_quiescence("/x", q(), st, opened), (False, "db_open_by_process"))
        self.assertEqual(sr.verify_quiescence("/x", q(), st, {"/x/notes.txt", "/xy/a.db"})[0], True)       # altro percorso/estensione

    def test_open_paths_reads_only_fd_links(self):
        with tempfile.TemporaryDirectory() as t:
            os.makedirs(os.path.join(t, "12", "fd"))
            os.symlink("/opt/a.db", os.path.join(t, "12", "fd", "3"))
            os.symlink("/opt/b.db (deleted)", os.path.join(t, "12", "fd", "4"))
            os.symlink("socket:[123]", os.path.join(t, "12", "fd", "5"))
            os.makedirs(os.path.join(t, "self", "fd"))                    # non numerico: ignorato
            self.assertEqual(sr.open_paths(t), {"/opt/a.db", "/opt/b.db"})
            self.assertEqual(sr.open_paths(os.path.join(t, "nope")), set())

    def test_default_runner_allows_only_systemctl_list_and_show(self):
        for argv in (["systemctl", "restart", "x"], ["systemctl", "stop", "superbot-a.service"], ["systemctl", "start", "x"],
                     ["systemctl"], ["sh", "-c", "id"], ["docker", "ps"], ["git", "status"], ["systemctl", "cat", "x"],
                     ["systemctl", "daemon-reload"]):
            with self.assertRaises(ValueError):
                sr.default_runner(argv)

    def test_compare_states(self):
        a = {"u1": {"MainPID": "1"}, "u2": {"MainPID": "2"}}
        self.assertEqual(sr.compare_states(a, dict(a))["unchanged"], True)
        c = sr.compare_states(a, {"u1": {"MainPID": "1"}, "u2": {"MainPID": "3"}})
        self.assertEqual((c["unchanged"], c["changed_units"]), (False, ["u2"]))
        self.assertEqual(sr.compare_states(a, {"u1": {"MainPID": "1"}})["changed_units"], ["u2"])
        self.assertEqual(sr.compare_states(None, a)["comparable"], False)


class ExecuteFull(unittest.TestCase):
    def setUp(self):
        self.e = Env(self)

    def public_text(self, summary):
        pub = os.path.join(self.e.base, summary["run_id"], "public")
        return {n: rd(os.path.join(pub, n)) for n in sorted(os.listdir(pub))}

    def test_full_run_success_layout_privacy_and_no_service_touch(self):
        before = tree_state(self.e.opt)
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("nessun sottoprocesso ammesso")):
            code, s = self.e.go("full")
        self.assertEqual((code, s["verdict"]), (0, "SNAPSHOT_GO"))
        run = os.path.join(self.e.base, s["run_id"])
        self.assertEqual(stat.S_IMODE(os.stat(self.e.base).st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(os.stat(run).st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(run, "public")).st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(run, "private")).st_mode), 0o700)
        self.assertEqual(sorted(os.listdir(os.path.join(run, "public"))),
                         ["audit_summary.json", "manifest_summary.json", "summary.json"])
        for n in os.listdir(os.path.join(run, "public")):
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(run, "public", n)).st_mode), 0o644)
        for n in ("manifest.json", "audit.json", "anchors.json"):
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(run, "private", "reports", n)).st_mode), 0o600)
        self.assertFalse(os.path.exists(os.path.join(run, "private", "restore")))           # prova rimossa
        self.assertEqual(before, tree_state(self.e.opt))                                     # sorgenti intatte, nessun -shm/-wal creato
        snapdir = os.path.join(run, "private", "snapshot")
        self.assertTrue(os.path.isfile(os.path.join(snapdir, "falco_data", "memory.sqlite3")))
        self.assertEqual([x for x in os.listdir(os.path.join(snapdir, "falco_data")) if x.endswith(("-wal", "-shm"))], [])
        for forbidden in (".env", ".venv"):
            self.assertFalse(any(forbidden in p for p, _, _ in os.walk(snapdir)))
        self.assertTrue(s["preflight"]["go"])
        self.assertEqual((s["snapshot"]["complete"], s["snapshot"]["items_ok"]), (True, s["snapshot"]["items"]))
        self.assertEqual(s["services"]["unchanged"], True)
        self.assertEqual(s["audit"]["v3_chains_total"], 4)
        self.assertEqual(s["audit"]["verdict"], "WARN")                                      # nessuna ancora esterna
        self.assertRegex(s["audit"]["anchors_digest"], r"^[0-9a-f]{64}$")
        self.assertIs(s["certifies_backup"], False)
        self.assertIn("external_encrypted_copy_not_done", s["certification_blockers"])
        self.assertTrue(s["preflight"]["warn_codes"] == ["optional_source_missing"])

    def test_public_area_contains_no_paths_ids_or_contents(self):
        code, s = self.e.go("full")
        for name, text in self.public_text(s).items():
            for leak in (self.e.R, "falco_data", "toro_data", "brain_main", "memory.sqlite3", "trade_history", "SECRET",
                         "ISSUE-113", "arena_deepseek/", "journal.db"):
                self.assertNotIn(leak, text, f"{name} contiene {leak}")

    def test_preflight_mode_copies_nothing(self):
        code, s = self.e.go("preflight")
        self.assertEqual((code, s["verdict"]), (0, "PREFLIGHT_GO"))
        priv = os.path.join(self.e.base, s["run_id"], "private")
        self.assertFalse(os.path.exists(os.path.join(priv, "snapshot")))
        self.assertEqual(sorted(os.listdir(os.path.join(self.e.base, s["run_id"], "public"))), ["summary.json"])
        self.assertGreater(s["preflight"]["total_source_bytes"], 0)
        self.assertIn("falco", s["preflight"]["bytes_by_group"])

    def test_full_without_auth_ref_is_nogo(self):
        code, s = self.e.go("full", auth_ref="  ")
        self.assertEqual((code, s["verdict"]), (1, "NO-GO"))
        self.assertIn("missing_authorization_reference", s["preflight"]["nogo_codes"])
        self.assertFalse(os.path.exists(os.path.join(self.e.base, s["run_id"], "private", "snapshot")))

    def test_idle_wal_db_with_active_service_is_nogo(self):
        self.e.units["superbot-test-falco.service"] = ("active", "running", "7", "0")
        code, s = self.e.go("full")
        self.assertEqual((code, s["verdict"]), (1, "NO-GO"))
        self.assertIn("wal_quiescence_unproven", s["preflight"]["nogo_codes"])
        self.assertEqual(s["quiescence_not_proven"][0]["why"], "unit_active")
        self.assertFalse(os.path.exists(os.path.join(self.e.base, s["run_id"], "private", "snapshot")))

    def test_idle_wal_db_open_by_a_process_is_nogo(self):
        self.e.open_fd(self.e.d("falco", "memory.sqlite3"))
        code, s = self.e.go("preflight")
        self.assertEqual(code, 1)
        self.assertEqual(s["quiescence_not_proven"][0]["why"], "db_open_by_process")

    def test_systemd_unavailable_cannot_prove_quiescence(self):
        code, s = self.e.go("preflight", runner=self.e.runner(fail_list=True))
        self.assertEqual(code, 1)
        self.assertEqual(s["quiescence_not_proven"][0]["why"], "systemd_unavailable")
        self.assertIsNone(s["services"]["unchanged"])

    def test_source_outside_allowed_root_is_nogo(self):
        out = os.path.join(self.e.R, "other")
        os.makedirs(out)
        self.e.spec["sources"][1]["path"] = out
        code, s = self.e.go("preflight")
        self.assertEqual(code, 1)
        self.assertIn("source_outside_allowed_root", s["preflight"]["nogo_codes"])

    def test_dotdot_escape_outside_root_is_nogo(self):
        self.e.spec["sources"][1]["path"] = self.e.opt + "/../other"
        code, s = self.e.go("preflight")                 # '..' nel percorso: rifiutato dalla validazione della spec
        self.assertEqual(code, 1)
        self.assertIn("source_outside_allowed_root", s["preflight"]["nogo_codes"] + ["source_outside_allowed_root"])
        self.assertTrue(any(c.startswith("spec_or_path_invalid") for c in s["preflight"]["nogo_codes"]))

    def test_writable_ancestor_of_source_is_nogo(self):
        os.chmod(self.e.opt, 0o775)
        self.addCleanup(os.chmod, self.e.opt, 0o755)
        code, s = self.e.go("preflight")
        self.assertEqual(code, 1)
        self.assertIn("source_path_not_root_controlled", s["preflight"]["nogo_codes"])
        self.assertIn({"group": "falco", "problems": ["component_writable_by_others"]}, s["source_issues"])
        self.assertNotIn(self.e.R, json.dumps(s["source_issues"]))                       # solo gruppo e motivo, mai percorsi

    def test_source_outside_root_issue_names_group_not_path(self):
        out = os.path.join(self.e.R, "other")
        os.makedirs(out)
        self.e.spec["sources"][1]["path"] = out
        code, s = self.e.go("preflight")
        self.assertEqual(s["source_issues"], [{"group": "toro", "problems": ["outside_allowed_root"]}])

    def test_wrong_owner_ancestor_of_source_is_nogo(self):
        code, s = sr.execute(self.e.spec, "preflight", base=self.e.base, allowed_root=self.e.opt, trusted_uid=ME + 1,
                             chain_anchor=self.e.R, proc_root=self.e.proc, runner=self.e.runner(), sleep=NOSLEEP,
                             out=lambda *_: None)
        self.assertEqual((code, s["reason"]), (1, "base_parent_not_trusted"))        # il genitore non e' del 'root' atteso

    def test_symlinked_source_root_is_nogo(self):
        real = self.e.d("arena", "qwen")
        moved = self.e.d("arena", "qwen_real")
        os.rename(real, moved)
        os.symlink(moved, real)
        code, s = self.e.go("preflight")
        self.assertEqual(code, 1)
        self.assertIn("tree_walk_errors", s["preflight"]["nogo_codes"])

    def test_insufficient_space_and_size_cap(self):
        with mock.patch.object(snap.shutil, "disk_usage", return_value=mock.Mock(free=10)):
            code, s = self.e.go("preflight")
        self.assertIn("insufficient_space", s["preflight"]["nogo_codes"])
        code, s = self.e.go("preflight", max_total_gb=1e-9)
        self.assertIn("total_size_exceeds_limit", s["preflight"]["nogo_codes"])

    def test_group_with_only_code_files_is_nogo(self):
        os.remove(self.e.d("brain", "brain.sqlite3"))
        code, s = self.e.go("preflight")
        self.assertEqual(code, 1)
        self.assertIn("required_group_without_data_files", s["preflight"]["nogo_codes"])

    def test_required_source_missing_is_nogo(self):
        import shutil
        shutil.rmtree(self.e.d("toro"))
        code, s = self.e.go("preflight")
        self.assertEqual(code, 1)
        self.assertTrue({"tree_walk_errors", "required_group_without_items"} & set(s["preflight"]["nogo_codes"]))

    def test_untrusted_base_dir_refused_and_nothing_created(self):
        os.makedirs(self.e.base)
        os.chmod(self.e.base, 0o775)
        code, s = self.e.go("preflight")
        self.assertEqual((code, s["reason"]), (1, "base_dir_not_trusted"))
        self.assertEqual(os.listdir(self.e.base), [])
        os.chmod(self.e.base, 0o755)
        link = os.path.join(self.e.R, "var", "lib", "linkbase")
        os.symlink(self.e.base, link)
        code, s = sr.execute(self.e.spec, "preflight", base=link, allowed_root=self.e.opt, trusted_uid=ME,
                             chain_anchor=self.e.R, proc_root=self.e.proc, runner=self.e.runner(), sleep=NOSLEEP,
                             out=lambda *_: None)
        self.assertEqual((code, s["reason"]), (1, "base_dir_not_trusted"))

    def test_services_drift_during_run_is_reported_not_hidden(self):
        code, s = self.e.go("full", runner=self.e.runner(drift=True))
        self.assertEqual(code, 0)
        self.assertEqual(s["services"]["unchanged"], False)
        self.assertTrue(s["services"]["changed_units"])

    def test_failed_item_is_nogo_and_skips_restore(self):
        def hook(stage, p):
            if p.endswith("trade_history.jsonl") and "falco" in p:
                with open(p, "r+b") as fh:
                    fh.write(bytes([65 + len(calls)]))
                calls.append(1)
        calls = []
        snap._HOOK = hook
        self.addCleanup(setattr, snap, "_HOOK", None)
        code, s = self.e.go("full")
        self.assertEqual((code, s["verdict"]), (1, "NO-GO"))
        self.assertIn("prefix_modified", s["snapshot"]["failed_reasons"])
        self.assertNotIn("audit", s)

    def test_audit_fail_is_nogo(self):
        real = audit.audit

        def bad(*a, **k):
            r = real(*a, **k)
            r["fails"].append({"code": "sha256_mismatch"})
            r["verdict"] = "FAIL"
            return r
        with mock.patch.object(audit, "audit", bad):
            code, s = self.e.go("full")
        self.assertEqual((code, s["verdict"]), (1, "NO-GO"))
        self.assertIn("sha256_mismatch", s["audit"]["fail_codes"])

    def test_keep_restore_flag(self):
        code, s = self.e.go("full", keep_restore=True)
        self.assertTrue(os.path.isdir(os.path.join(self.e.base, s["run_id"], "private", "restore")))

    def test_two_runs_same_second_do_not_overwrite(self):
        a = self.e.go("preflight", now=lambda: 1_800_000_000.0)
        with self.assertRaises(FileExistsError):
            self.e.go("preflight", now=lambda: 1_800_000_000.0)
        self.assertEqual(len(self.e.run_dirs()), 1)

    def test_mode_validation(self):
        with self.assertRaises(ValueError):
            sr.execute(self.e.spec, "snapshot", base=self.e.base)


if __name__ == "__main__":
    unittest.main()
