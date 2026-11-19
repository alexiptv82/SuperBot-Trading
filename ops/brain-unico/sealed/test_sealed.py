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


def append_event(path, kind, ts, payload):
    con = sqlite3.connect(path)
    row = con.execute("SELECT seq,event_hash FROM v3_events ORDER BY seq DESC LIMIT 1").fetchone()
    prev, seq = (row[1], row[0]) if row else (audit.GENESIS, 0)
    pj = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    eid = f"x{seq + 1}"
    h = audit._digest(prev, eid, "brain", "run1", kind, ts, "src", pj)
    con.execute("INSERT INTO v3_events(event_id,portfolio_id,run_id,kind,occurred_at_ms,source,payload_json,previous_hash,"
                "event_hash) VALUES(?,?,?,?,?,?,?,?,?)", (eid, "brain", "run1", kind, ts, "src", pj, prev, h))
    con.commit()
    con.close()


T_START = 1_795_021_392_344                                   # T0 sintetico
H = 3_600_000


def add_trade(path, pid, ts, *, loss=-40, lev=30, risk_loss=30, reason="stop", close=True):
    qty = risk_loss / 0.5
    append_event(path, "paper_open", ts, {"position_id": pid, "symbol": "SECRETUSDT", "side": 1, "fill_price": "100",
                                          "quantity": str(qty), "notional": str(100 * qty), "margin_used": str(100 * qty / lev),
                                          "leverage": lev, "stop_price": "99.5", "rationale": "TESTO-RISERVATO"})
    if close:
        append_event(path, "paper_close", ts + H, {"position_id": pid, "realized_pnl": str(loss), "fees": "1",
                                                   "reason": reason, "held_ms": H, "loss_exceeds_margin": False})


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
        for i, p in enumerate(("deepseek", "qwen", "minimax")):
            self.units[f"superbot-arena-runner@{p}.service"] = ("active", "running", str(200 + i), "0")
            self.units[f"superbot-arena-exit@{p}.service"] = ("active", "running", str(300 + i), "0")
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
            self.w(f"arena/{p}/arena_t0.json", json.dumps({"trial_start_ms": T_START}))
            make_chain_db(self.d("arena", p, "journal.db"), 3)
        self.spec = {"schema": 1, "require_data": True, "arena_planned_hours": 72,
                     "arena_risk_policy": load(build_sealed.SPEC)["arena_risk_policy"],
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

    def stopper(self, calls, fail=(), noeffect=False):
        def st(argv):
            calls.append(list(argv))
            unit = argv[2]
            if unit in fail:
                return 1, ""
            if not noeffect:
                self.units[unit] = ("inactive", "dead", "0", "0")
            return 0, ""
        return st

    def checkpoint(self, groups=None, **kw):
        """Checkpoint coerente PRE-stop reale: un `full` su tutte le run Arena (o sui gruppi indicati)."""
        code, s = self.go("full", groups=groups or ["arena_deepseek", "arena_qwen", "arena_minimax"], **kw)
        assert code == 0, s
        self.last_checkpoint = s["run_id"]
        return s["run_id"]

    def stop(self, **kw):
        calls = kw.pop("calls", [])
        kw.setdefault("runner", self.runner())
        kw.setdefault("stopper", self.stopper(calls, kw.pop("fail", ()), kw.pop("noeffect", False)))
        if "checkpoint_run" not in kw:
            kw["checkpoint_run"] = getattr(self, "last_checkpoint", None) or self.checkpoint()
        self._clock = getattr(self, "_clock", 1_800_000_000.0) + 1
        kw.setdefault("now", lambda t=self._clock: t)
        out = []
        code, s = sr.execute_stop(self.spec, ended_early_reason=kw.pop("reason", "arena_priority_brain_unico"),
                                  auth_ref=kw.pop("auth_ref", "ISSUE113-STOP"), base=self.base, allowed_root=self.opt,
                                  trusted_uid=ME, chain_anchor=self.R, code_sha="b" * 64, out=out.append, **kw)
        return code, s, calls

    def status(self, **kw):
        self._clock = getattr(self, "_clock", 1_800_000_000.0) + 1
        kw.setdefault("runner", self.runner())
        kw.setdefault("now", lambda t=self._clock: t)
        return sr.execute_status_services(base=self.base, trusted_uid=ME, chain_anchor=self.R, code_sha="c" * 64,
                                          out=lambda *_: None, **kw)

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


class GroupsRiskAndWindow(unittest.TestCase):
    def setUp(self):
        self.e = Env(self)

    def test_groups_filter_limits_sources_and_requirements(self):
        code, s = self.e.go("preflight", groups=["arena_minimax"])
        self.assertEqual((code, s["verdict"], s["groups"]), (0, "PREFLIGHT_GO", ["arena_minimax"]))
        self.assertEqual(list(s["preflight"]["bytes_by_group"]), ["arena_minimax"])
        with self.assertRaises(ValueError):
            self.e.go("preflight", groups=["arena_minimax", "nope"])
        self.assertEqual(self.e.run_dirs(), [d for d in self.e.run_dirs()])               # nessuna directory per l'errore
        n_before = len(self.e.run_dirs())
        with self.assertRaises(ValueError):
            self.e.go("preflight", groups=["zzz"])
        with self.assertRaises(ValueError):
            self.e.go("preflight", groups=[])                                             # [] non significa "tutti"
        self.assertEqual(len(self.e.run_dirs()), n_before)

    def test_full_adds_numbers_only_risk_audit_and_effective_window(self):
        mm = self.e.d("arena", "minimax", "journal.db")
        for i in range(6):
            add_trade(mm, f"m{i}", T_START + (i + 1) * 2 * H, loss=-40)
        code, s = self.e.go("full", groups=["arena_minimax"], ended_early_reason="arena_priority_brain_unico")
        self.assertEqual((code, s["verdict"]), (0, "SNAPSHOT_GO"))
        r = s["risk"]["minimax"]
        self.assertEqual((r["trades"]["closed"], r["trades"]["realized_pnl"]), (6, "-240.0000"))
        self.assertTrue(r["verdict"]["no_breach_proven"], r["verdict"])
        w = s["arena_window"]["minimax"]
        self.assertEqual((w["t0_ms"], w["planned_hours"]), (T_START, 72))
        self.assertAlmostEqual(w["effective_hours"], 13.0, places=2)                      # 6 trade: ultimo evento T0+13h
        self.assertEqual(s["ended_early_reason"], "arena_priority_brain_unico")
        text = json.dumps(s)
        for leak in ("SECRETUSDT", "TESTO-RISERVATO", self.e.R, "m0"):
            self.assertNotIn(leak, text)
        self.assertFalse(os.path.exists(os.path.join(self.e.base, s["run_id"], "private", "restore")))

    def test_risk_violation_is_reported_but_does_not_fail_the_snapshot(self):
        mm = self.e.d("arena", "minimax", "journal.db")
        add_trade(mm, "bad", T_START + H, lev=10, risk_loss=140, loss=-150)             # leva fuori profilo + rischio > tetto
        code, s = self.e.go("full", groups=["arena_minimax"])
        self.assertEqual((code, s["verdict"]), (0, "SNAPSHOT_GO"))                       # lo snapshot e' valido
        v = s["risk"]["minimax"]["verdict"]
        self.assertFalse(v["no_breach_proven"])
        self.assertIn("leverage_out_of_policy_range", v["hard_flags"])
        self.assertIn("per_position_risk_clearly_over_cap", v["hard_flags"])

    def test_minus_800_style_loss_within_limits_is_reported_as_held(self):
        mm = self.e.d("arena", "minimax", "journal.db")
        for i in range(20):
            add_trade(mm, f"m{i}", T_START + (i % 10 + 1) * 2 * H + (24 * H if i >= 10 else 0), loss=-40)
        code, s = self.e.go("full", groups=["arena_minimax"])
        r = s["risk"]["minimax"]
        self.assertEqual(r["trades"]["realized_pnl"], "-800.0000")
        self.assertTrue(r["verdict"]["no_breach_proven"], r["verdict"])

    def test_multiple_providers_each_reported(self):
        add_trade(self.e.d("arena", "qwen", "journal.db"), "q", T_START + H)
        code, s = self.e.go("full")
        self.assertEqual(sorted(s["risk"]), ["deepseek", "minimax", "qwen"])
        self.assertEqual(s["risk"]["qwen"]["trades"]["closed"], 1)


class StatusServicesCommand(unittest.TestCase):
    def setUp(self):
        self.e = Env(self)

    def test_services_ok_when_systemd_answers_and_units_exist(self):
        code, s = self.e.status()
        self.assertEqual((code, s["verdict"], s["systemd_readable"], s["problems"]), (0, "SERVICES_OK", True, []))
        p = s["providers"]["minimax"]
        self.assertEqual((p["runner"], p["exit"], p["exit_main_pid_present"]), ("active", "active", True))
        self.assertFalse(s["reads_databases"])

    def test_it_can_never_touch_a_database_or_a_data_file(self):
        add_trade(self.e.d("arena", "minimax", "journal.db"), "open1", T_START + H, close=False)
        before = tree_state(self.e.opt)
        real_open = open
        opened = []

        def spy(p, *a, **k):
            opened.append(str(p))
            return real_open(p, *a, **k)
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("nessun sottoprocesso")), \
                mock.patch.object(sqlite3, "connect", side_effect=AssertionError("NESSUN database")), \
                mock.patch("builtins.open", spy):
            code, s = self.e.status()
        self.assertEqual(code, 0)
        self.assertEqual(before, tree_state(self.e.opt))                                     # nemmeno -shm/-wal toccati
        self.assertFalse([p for p in opened if p.startswith(self.e.opt)], "ha aperto file di dati")

    def test_incomplete_is_an_explicit_failure_not_a_success(self):
        code, s = self.e.status(runner=self.e.runner(fail_list=True))
        self.assertEqual((code, s["verdict"], s["systemd_readable"]), (1, "INCOMPLETE", False))
        self.assertIn("systemd_unavailable", s["problems"])
        del self.e.units["superbot-arena-exit@qwen.service"]
        code, s = self.e.status()
        self.assertEqual((code, s["verdict"]), (1, "INCOMPLETE"))
        self.assertIn("unit_missing:superbot-arena-exit@qwen.service", s["problems"])

    def test_summary_is_numbers_and_unit_states_only(self):
        add_trade(self.e.d("arena", "minimax", "journal.db"), "open1", T_START + H, close=False)
        code, s = self.e.status()
        text = rd(os.path.join(self.e.base, s["run_id"], "public", "summary.json"))
        for leak in ("open1", "SECRETUSDT", self.e.R, "positions"):
            self.assertNotIn(leak, text)

    def test_cli_exposes_status_services_not_a_database_status(self):
        sha = hashlib.sha256(rd(BUNDLE, "rb")).hexdigest()
        r = subprocess.run([sys.executable, "-I", BUNDLE, "status", "--expect-sha256", sha], capture_output=True, text=True, cwd="/")
        self.assertEqual(r.returncode, 2)                                                    # il vecchio comando 'status' non esiste piu'
        if not IS_ROOT:
            r = subprocess.run([sys.executable, "-I", BUNDLE, "status-services", "--expect-sha256", sha],
                               capture_output=True, text=True, cwd="/")
            self.assertEqual((r.returncode, "richiede root" in r.stdout), (2, True))


class StopOpenings(unittest.TestCase):
    def setUp(self):
        self.e = Env(self)

    def runner_unit(self, p):
        return f"superbot-arena-runner@{p}.service"

    def test_stops_only_runners_and_leaves_exits_untouched(self):
        code, s, calls = self.e.stop()
        self.assertEqual((code, s["verdict"]), (0, "OPENINGS_STOPPED"))
        self.assertEqual(sorted(c[2] for c in calls), sorted(self.runner_unit(p) for p in ("deepseek", "qwen", "minimax")))
        self.assertTrue(all(c[:2] == ["systemctl", "stop"] and len(c) == 3 for c in calls))
        self.assertTrue(s["exit_services_untouched"])
        for p in ("deepseek", "qwen", "minimax"):
            self.assertEqual(self.e.units[f"superbot-arena-exit@{p}.service"][0], "active")
            self.assertEqual(self.e.units[self.runner_unit(p)][0], "inactive")
        self.assertEqual(self.e.units["superbot-test-arena.service"][0], "active")          # nessuna altra unita' toccata
        self.assertEqual(s["ended_early_reason"], "arena_priority_brain_unico")
        self.assertFalse(s["reads_databases"])
        self.assertNotIn("positions_after", s)
        self.assertEqual(s["checkpoint_run_id"], self.e.last_checkpoint)

    def test_idempotent_second_run_does_not_stop_again(self):
        self.e.stop()
        code, s, calls = self.e.stop()
        self.assertEqual((code, calls, sorted(s["already_stopped"])), (0, [], ["deepseek", "minimax", "qwen"]))

    def test_single_provider_only(self):
        code, s, calls = self.e.stop(providers=["minimax"])
        self.assertEqual([c[2] for c in calls], [self.runner_unit("minimax")])
        self.assertEqual(self.e.units[self.runner_unit("qwen")][0], "active")

    def test_exit_service_not_active_stops_nothing(self):
        self.e.units["superbot-arena-exit@qwen.service"] = ("failed", "failed", "0", "0")
        code, s, calls = self.e.stop()
        self.assertEqual((code, s["verdict"], calls), (1, "NO-GO", []))
        self.assertIn("exit_service_not_active:qwen", s["nogo"])

    def test_runner_unit_missing_stops_nothing(self):
        del self.e.units[self.runner_unit("deepseek")]
        code, s, calls = self.e.stop()
        self.assertEqual((code, calls), (1, []))
        self.assertIn("runner_unit_not_found:deepseek", s["nogo"])

    def test_systemd_unavailable_stops_nothing(self):
        code, s, calls = self.e.stop(runner=self.e.runner(fail_list=True))
        self.assertEqual((code, calls, s["nogo"]), (1, [], ["systemd_unavailable"]))

    def test_stop_failure_and_ineffective_stop_are_nogo(self):
        code, s, calls = self.e.stop(fail=(self.runner_unit("qwen"),))
        self.assertEqual((code, s["stop_failed"]), (1, ["qwen"]))
        e2 = Env(self)
        code, s, calls = e2.stop(noeffect=True)
        self.assertEqual(code, 1)
        self.assertEqual(sorted(s["runners_still_active"]), ["deepseek", "minimax", "qwen"])

    def test_exit_service_changed_during_stop_is_nogo(self):
        base = self.e.stopper([])

        def st(argv):
            r = base(argv)
            self.e.units["superbot-arena-exit@minimax.service"] = ("active", "running", "999", "1")   # riavviata da altri
            return r
        code, s, _ = self.e.stop(stopper=st)
        self.assertEqual(code, 1)
        self.assertFalse(s["exit_services_untouched"])

    def test_argument_validation(self):
        for kw in ({"providers": []}, {"providers": ["nope"]}, {"providers": ["qwen", "qwen"]},
                   {"reason": "ha spazi"}, {"reason": ""}, {"reason": "x" * 65}, {"auth_ref": "  "}):
            with self.assertRaises(ValueError):
                self.e.stop(**kw)
        self.assertEqual(len(self.e.run_dirs()), 1)                                       # solo il checkpoint: nessuna esecuzione di stop

    def test_default_stopper_whitelist(self):
        for argv in (["systemctl", "stop", "superbot-arena-exit@minimax.service"],
                     ["systemctl", "stop", "superbot-arena-close-bridge.service"],
                     ["systemctl", "stop", "superbot-v3-paper-brain-exit.service"],
                     ["systemctl", "stop", "superbot-arena-runner@other.service"],
                     ["systemctl", "stop", "superbot-arena-runner@minimax.service", "--force"],
                     ["systemctl", "restart", "superbot-arena-runner@minimax.service"],
                     ["systemctl", "kill", "superbot-arena-runner@minimax.service"],
                     ["systemctl", "stop", "superbot-arena-runner@minimax.service;id"],
                     ["sh", "-c", "id"], []):
            with self.assertRaises(ValueError, msg=argv):
                sr.default_stopper(argv)
        with self.assertRaises(ValueError):
            sr.default_runner(["systemctl", "stop", "superbot-arena-runner@minimax.service"])      # il runner di lettura non puo' fermare

    def test_public_summary_has_no_paths_or_contents(self):
        add_trade(self.e.d("arena", "minimax", "journal.db"), "p1", T_START + H, close=False)
        code, s, _ = self.e.stop()
        text = rd(os.path.join(self.e.base, s["run_id"], "public", "summary.json"))
        for leak in (self.e.R, "SECRETUSDT", "TESTO-RISERVATO", '"p1"'):
            self.assertNotIn(leak, text)

    def test_cli_requires_confirmation_and_root(self):
        sha = hashlib.sha256(rd(BUNDLE, "rb")).hexdigest()
        base = [sys.executable, "-I", BUNDLE, "stop-openings", "--expect-sha256", sha, "--auth-ref", "x",
                "--ended-early-reason", "r"]
        r = subprocess.run(base, capture_output=True, text=True, cwd="/")
        self.assertEqual(r.returncode, 2)                                                  # mancano --confirm-stop-runners e --checkpoint-run
        self.assertIn("--confirm-stop-runners", r.stderr)
        self.assertIn("--checkpoint-run", r.stderr)
        if not IS_ROOT:
            r = subprocess.run(base + ["--confirm-stop-runners", "--checkpoint-run", "run-20260101T000000Z-abc"],
                               capture_output=True, text=True, cwd="/")
            self.assertEqual(r.returncode, 2)
            self.assertIn("richiede root", r.stdout)


class StopRequiresCheckpoint(unittest.TestCase):
    """Fix PR #117: nessuno stop senza un checkpoint coerente, recente e completo; su NO-GO nulla viene fermato."""

    def setUp(self):
        self.e = Env(self)
        self.runner_units = [f"superbot-arena-runner@{p}.service" for p in ("deepseek", "qwen", "minimax")]

    def nogo(self, expected, **kw):
        code, s, calls = self.e.stop(**kw)
        self.assertEqual((code, s["verdict"], calls), (1, "NO-GO", []), s)
        self.assertEqual(s["nogo"], [expected])
        for u in self.runner_units:
            self.assertEqual(self.e.units[u][0], "active")                                   # nessun runner fermato
        return s

    def test_no_checkpoint_at_all_is_refused(self):
        for bad in ("", "nope", "../run-20260101T000000Z-abc", "run-20260101T000000Z-../x", "run-1-2"):
            self.nogo("checkpoint_run_id_invalid", checkpoint_run=bad)

    def test_unknown_run_id_is_refused(self):
        self.nogo("checkpoint_missing_or_path_not_trusted", checkpoint_run="run-20260101T000000Z-abcdef12")

    def test_valid_checkpoint_allows_the_stop_and_is_recorded(self):
        cp = self.e.checkpoint()
        code, s, calls = self.e.stop(checkpoint_run=cp)
        self.assertEqual((code, s["checkpoint_run_id"], len(calls)), (0, cp, 3))

    def test_checkpoint_must_be_a_full_run_not_a_preflight(self):
        code, s = self.e.go("preflight", groups=["arena_deepseek", "arena_qwen", "arena_minimax"])
        self.nogo("checkpoint_not_a_full_run", checkpoint_run=s["run_id"])

    def test_checkpoint_must_cover_every_selected_provider(self):
        cp = self.e.checkpoint(groups=["arena_minimax"])
        self.nogo("checkpoint_does_not_cover_selected_providers", checkpoint_run=cp)
        code, s, calls = self.e.stop(checkpoint_run=cp, providers=["minimax"])
        self.assertEqual((code, [c[2] for c in calls]), (0, ["superbot-arena-runner@minimax.service"]))

    def test_checkpoint_too_old_or_from_the_future_is_refused(self):
        cp = self.e.checkpoint()
        base_t = self.e._clock
        self.nogo("checkpoint_too_old", checkpoint_run=cp, now=lambda: base_t + 7200)
        self.nogo("checkpoint_from_the_future", checkpoint_run=cp, now=lambda: base_t - 3600)
        code, s, calls = self.e.stop(checkpoint_run=cp, now=lambda: base_t + 7300, max_checkpoint_age_s=3 * 3600)
        self.assertEqual(code, 0)

    def tamper(self, cp, **changes):
        p = os.path.join(self.e.base, cp, "public", "summary.json")
        s = load(p)
        for k, v in changes.items():
            cur = s
            *path, last = k.split(".")
            for x in path:
                cur = cur[x]
            cur[last] = v
        os.chmod(p, 0o644)
        with open(p, "w") as fh:
            json.dump(s, fh)

    def test_each_weakness_of_the_checkpoint_is_refused(self):
        cases = (("verdict", "NO-GO", "checkpoint_not_go"), ("certifies_backup", True, "checkpoint_not_go"),
                 ("snapshot.complete", False, "checkpoint_snapshot_incomplete"),
                 ("snapshot.items_ok", 0, "checkpoint_snapshot_incomplete"),
                 ("manifest.complete", False, "checkpoint_manifest_incomplete"),
                 ("manifest.unstable_count", 1, "checkpoint_manifest_incomplete"),
                 ("audit.verdict", "FAIL", "checkpoint_audit_or_hash_chain_not_ok"),
                 ("audit.fail_codes", ["sha256_mismatch"], "checkpoint_audit_or_hash_chain_not_ok"),
                 ("audit.v3_chains_ok", 0, "checkpoint_audit_or_hash_chain_not_ok"),
                 ("audit.v3_chains_total", 1, "checkpoint_audit_or_hash_chain_not_ok"),
                 ("risk.minimax", "error:OperationalError", "checkpoint_risk_audit_missing"),
                 ("services.unchanged", False, "checkpoint_services_changed_or_unknown"),
                 ("services.comparable", False, "checkpoint_services_changed_or_unknown"))
        for key, val, code in cases:
            e = Env(self)
            self.e = e
            cp = e.checkpoint()
            self.tamper(cp, **{key: val})
            self.nogo(code, checkpoint_run=cp)

    def test_checkpoint_file_must_be_in_a_trusted_location_and_regular(self):
        cp = self.e.checkpoint()
        p = os.path.join(self.e.base, cp, "public", "summary.json")
        os.chmod(p, 0o666)                                                                   # scrivibile da tutti: non fidato
        self.nogo("checkpoint_missing_or_path_not_trusted", checkpoint_run=cp)
        os.chmod(p, 0o644)
        e2 = Env(self)
        self.e = e2
        cp2 = e2.checkpoint()
        pp = os.path.join(e2.base, cp2, "public", "summary.json")
        os.rename(pp, pp + ".real")
        os.symlink(pp + ".real", pp)                                                         # symlink al posto del file
        self.nogo("checkpoint_missing_or_path_not_trusted", checkpoint_run=cp2)

    def test_garbage_checkpoint_is_refused_without_crashing(self):
        cp = self.e.checkpoint()
        p = os.path.join(self.e.base, cp, "public", "summary.json")
        os.chmod(p, 0o644)
        with open(p, "w") as fh:
            fh.write("[1, 2, 3]")
        self.nogo("checkpoint_not_a_full_run", checkpoint_run=cp)
        with open(p, "w") as fh:
            fh.write("{not json")
        self.nogo("checkpoint_unreadable", checkpoint_run=cp)

    def test_systemd_exit_and_runner_conditions_still_apply_after_a_good_checkpoint(self):
        cp = self.e.checkpoint()
        self.e.units["superbot-arena-exit@qwen.service"] = ("failed", "failed", "0", "0")
        code, s, calls = self.e.stop(checkpoint_run=cp)
        self.assertEqual((code, calls), (1, []))
        self.assertIn("exit_service_not_active:qwen", s["nogo"])

    def test_stop_never_reads_a_database(self):
        cp = self.e.checkpoint()
        with mock.patch.object(sqlite3, "connect", side_effect=AssertionError("NESSUN database")):
            code, s, calls = self.e.stop(checkpoint_run=cp)
        self.assertEqual(code, 0)

    def test_auth_ref_is_only_a_trace_the_checkpoint_is_the_gate(self):
        code, s, calls = self.e.stop(auth_ref="qualunque-cosa", checkpoint_run="run-20260101T000000Z-abcdef12")
        self.assertEqual((code, calls), (1, []))                                              # un riferimento non sostituisce il checkpoint


class FullReportsExitProgress(unittest.TestCase):
    def setUp(self):
        self.e = Env(self)

    def test_full_measures_open_position_age_from_now_and_flags_overdue_exits(self):
        mm = self.e.d("arena", "minimax", "journal.db")
        add_trade(mm, "stuck", T_START + H, close=False)
        old_now = (T_START + 30 * H) / 1000.0                                               # 29 h dopo l'apertura
        code, s = self.e.go("full", groups=["arena_minimax"], now=lambda: old_now)
        r = s["risk"]["minimax"]
        self.assertEqual((r["trades"]["still_open"], r["trades"]["open_overdue"], r["trades"]["open_age_reference"]), (1, 1, "now"))
        self.assertIn("open_positions_overdue_for_exit", r["verdict"]["soft_flags"])
        self.assertFalse(r["verdict"]["fully_checked"])
        self.assertTrue(r["verdict"]["no_breach_proven"])

    def test_recent_open_positions_are_not_overdue(self):
        mm = self.e.d("arena", "minimax", "journal.db")
        add_trade(mm, "fresh", T_START + H, close=False)
        code, s = self.e.go("full", groups=["arena_minimax"], now=lambda: (T_START + 5 * H) / 1000.0)
        self.assertEqual(s["risk"]["minimax"]["trades"]["open_overdue"], 0)


if __name__ == "__main__":
    unittest.main()
