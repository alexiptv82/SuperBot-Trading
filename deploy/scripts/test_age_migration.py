"""Prove della migrazione age V1 -> V2: destinatari multipli, impronta approvata, wrapper, separazione dagli archivi V1.

Si lanciano con:  python3 -m unittest deploy/scripts/test_age_migration.py -v
Servono `age`, `age-keygen` e `git`. Tutto sintetico: chiavi "V1", "V2" e "personale" sono chiavi di prova create al volo,
repository "privati" sono cartelle temporanee. Nessun Secret, nessuna rete, nessuna VPS.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import age_recipients as AR                                       # noqa: E402
import test_brain_v3_backup as T                                  # noqa: E402
import test_external_backup as CLASSIC                            # noqa: E402
import fake_github_api as FG                                      # noqa: E402

MULTI = os.path.join(HERE, "external_backup_multi.py")
CHECKER = os.path.join(ROOT, "deploy", "extbackup", "v2", "check_recipient_consistency.py")
RECIPIENT_V2 = os.path.join(ROOT, "deploy", "extbackup", "recipient-v2.txt")
HAVE_AGE = T.HAVE_AGE


def gen_pair(path):
    pub = T.keygen(path)
    return pub


def write_recipients(path, *keys):
    T.spit(path, "# prova\n" + "".join(k + "\n" for k in keys))
    return AR.fingerprint(list(keys))


class RecipientsModuleTests(unittest.TestCase):
    A = "age1" + "q" * 58
    B = "age1" + "p" * 58

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.f = os.path.join(self.td.name, "r.txt")

    def tearDown(self):
        self.td.cleanup()

    def test_parse_valid_files_with_comments_and_blank_lines(self):
        T.spit(self.f, "# c\n\n%s\n  # altro\n%s\n" % (self.A, self.B))
        self.assertEqual(AR.read_recipients(self.f), [self.A, self.B])

    def test_rejects_empty_invalid_duplicate_secret_and_too_many(self):
        cases = {"vuoto": "# solo commenti\n", "non_chiave": "age1corta\n", "privata": "AGE-SECRET-KEY-1" + "Q" * 58 + "\n",
                 "duplicata": "%s\n%s\n" % (self.A, self.A), "troppi": "".join("age1%s\n" % (c * 58) for c in "abcde")}
        for name, body in cases.items():
            with self.subTest(caso=name):
                T.spit(self.f, body)
                with self.assertRaises(AR.RecipientError) as cm:
                    AR.read_recipients(self.f)
                self.assertEqual(cm.exception.code, "recipient_invalid")
        with self.assertRaises(AR.RecipientError) as cm:
            AR.read_recipients(os.path.join(self.td.name, "non-esiste"))
        self.assertEqual(cm.exception.code, "recipient_file_unreadable")

    def test_error_messages_never_contain_the_line_content(self):
        T.spit(self.f, "AGE-SECRET-KEY-1" + "Q" * 58 + "\n")
        with self.assertRaises(AR.RecipientError) as cm:
            AR.read_recipients(self.f)
        self.assertNotIn("AGE-SECRET", str(cm.exception))

    def test_fingerprint_is_order_independent_and_changes_with_any_key(self):
        self.assertEqual(AR.fingerprint([self.A, self.B]), AR.fingerprint([self.B, self.A]))
        self.assertNotEqual(AR.fingerprint([self.A]), AR.fingerprint([self.A, self.B]))
        self.assertNotEqual(AR.fingerprint([self.A]), AR.fingerprint([self.B]))
        self.assertRegex(AR.fingerprint([self.A]), r"^[0-9a-f]{64}$")

    def test_expected_fingerprint_is_enforced(self):
        T.spit(self.f, "%s\n" % self.A)
        ok = AR.fingerprint([self.A])
        self.assertEqual(AR.load_checked(self.f, ok).keys, (self.A,))
        for bad in ("", "xyz", AR.fingerprint([self.B]), AR.fingerprint([self.A, self.B])):
            with self.subTest(atteso=bad[:8]):
                with self.assertRaises(AR.RecipientError) as cm:
                    AR.load_checked(self.f, bad)
                self.assertEqual(cm.exception.code, "recipient_mismatch")

    def test_single_recipient_set_behaves_like_the_plain_string(self):
        rs = AR.RecipientSet([self.A])
        self.assertEqual(rs, self.A)
        self.assertEqual("%s" % rs, self.A)
        self.assertEqual(json.dumps({"d": rs}), json.dumps({"d": self.A}))
        self.assertEqual(AR.split_recipients(AR.RecipientSet([self.A, self.B])), [self.A, self.B])
        self.assertEqual(AR.split_recipients([self.A]), [self.A])

    @unittest.skipUnless(HAVE_AGE, "mancano age/age-keygen/git")
    def test_two_recipients_each_identity_decrypts_and_a_third_does_not(self):
        ia, ib, ic = (os.path.join(self.td.name, n) for n in ("a", "b", "c"))
        pa, pb, _pc = gen_pair(ia), gen_pair(ib), gen_pair(ic)
        plain, enc = os.path.join(self.td.name, "p"), os.path.join(self.td.name, "p.age")
        T.spit(plain, b"contenuto di prova " * 50)
        AR.encrypt_to(plain, enc, [pa, pb])
        for ident in (ia, ib):
            out = os.path.join(self.td.name, "o-" + os.path.basename(ident))
            self.assertEqual(subprocess.run(["age", "-d", "-i", ident, "-o", out, enc], capture_output=True).returncode, 0)
            self.assertEqual(T.slurp(out), T.slurp(plain))
        self.assertNotEqual(subprocess.run(["age", "-d", "-i", ic, "-o", os.path.join(self.td.name, "x"), enc],
                                           capture_output=True).returncode, 0)

    @unittest.skipUnless(HAVE_AGE, "mancano age/age-keygen/git")
    def test_encryption_failure_is_reported_with_a_fixed_code(self):
        shim = os.path.join(self.td.name, "bin")
        os.makedirs(shim)
        T.spit(os.path.join(shim, "age"), "#!/bin/sh\necho 'errore simulato' >&2\nexit 1\n")
        os.chmod(os.path.join(shim, "age"), 0o755)
        with self.assertRaises(AR.RecipientError) as cm:
            AR.encrypt_to(self.f, os.path.join(self.td.name, "o"), [self.A], age_bin=os.path.join(shim, "age"))
        self.assertEqual(cm.exception.code, "encryption_failed")


@unittest.skipUnless(HAVE_AGE, "mancano age/age-keygen/git")
class MigrationCase(unittest.TestCase):
    """Un 'V1' reale (archivio classico, V3 e Brain Free cifrati per la chiave V1) e un 'V2' nuovo e separato."""

    def setUp(self):
        self.case = CLASSIC.ExternalBackupTests("test_full_round_trip_backup_then_restore")
        self.case.setUp()
        self.t = self.case.td.name
        self.v1_remote, self.v1_ident, self.v1_pub = self.case.remote, self.case.ident, self.case.pub
        self.v2_remote = os.path.join(self.t, "remote-v2.git")
        T.sh("git", "init", "-q", "--bare", "-b", "main", self.v2_remote)
        self.v2_ident, self.pers_ident = os.path.join(self.t, "v2-id"), os.path.join(self.t, "pers-id")
        self.v2_pub, self.pers_pub = gen_pair(self.v2_ident), gen_pair(self.pers_ident)
        self.rec1, self.rec2 = os.path.join(self.t, "rec-v2-1.txt"), os.path.join(self.t, "rec-v2-2.txt")
        self.fp1 = write_recipients(self.rec1, self.v2_pub)
        self.fp2 = write_recipients(self.rec2, self.v2_pub, self.pers_pub)
        self.runs = os.path.join(self.t, "runs")
        os.makedirs(self.runs)
        r = T.Run(self.runs, "brain-v3-alfa1")
        r.decision(1, T.SECRET)
        r.open("p1")
        r.spend(5)
        self.legacy = os.path.join(self.t, "leg", "brain.sqlite3")
        os.makedirs(os.path.dirname(self.legacy))
        T.make_legacy(self.legacy, 20)

    def tearDown(self):
        self.case.tearDown()

    def multi(self, recfile, fp, remote, work, *extra, expect=True):
        cmd = [sys.executable, "-I", MULTI, "--expect-recipients-sha256", fp, "--root", self.case.root, "--app-db", self.case.app_db,
               "--pool-db", self.case.pool_db, "--tools", HERE, "--work", work, "--remote", remote, "--recipient-file", recipient_arg(recfile),
               "--app-repo", "/nonexistent", "--bots-repo", "/nonexistent", "--brain-retries", "0",
               "--brain-arg=--quiet-secs", "--brain-arg=1", "--brain-arg=--attempts", "--brain-arg=2", "--brain-arg=--wait",
               "--brain-arg=0.1", "--brain-arg=--quiet-timeout", "--brain-arg=2", *extra]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return p.returncode, p.stdout + p.stderr

    def v3pipe(self, mode, recfile, fp, remote, *extra):
        cmd = [sys.executable, "-I", T.PIPE, "--mode", mode, "--runs-root", self.runs, "--legacy-db", self.legacy,
               "--work", os.path.join(self.t, "w3-" + mode + os.path.basename(remote)), "--remote", remote, "--recipient-file", recfile,
               "--expect-recipients-sha256", fp, "--tools", HERE, "--push-wait", "0", "--attempt-wait", "0", *extra]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return p.returncode, p.stdout + p.stderr

    def clone(self, remote, branch):
        dst = os.path.join(self.t, "c-%d" % time.time_ns())
        T.sh("git", "clone", "-q", "--branch", branch, remote, dst)
        return dst

    def archives(self, clone, sub):
        return sorted(os.path.join(dp, f) for dp, _d, fn in os.walk(os.path.join(clone, sub)) for f in fn if f.endswith(".tar.gz.age"))

    def heads(self, remote):
        return subprocess.run(["git", "-C", remote, "for-each-ref", "--format=%(refname) %(objectname)"], capture_output=True, text=True).stdout


def recipient_arg(path):
    return path


class ClassicMultiWrapperTests(MigrationCase):
    def test_classic_code_stays_byte_identical(self):
        for rel, expected in T.CLASSIC_PINS.items():
            self.assertEqual(T.sha(T.slurp(os.path.normpath(os.path.join(HERE, rel)))), expected, rel)

    def test_single_v2_recipient_backup_restores_with_the_classic_restore_script(self):
        rc, out = self.multi(self.rec1, self.fp1, self.v2_remote, os.path.join(self.t, "w2"))
        self.assertEqual(rc, 0, out)
        clone = self.clone(self.v2_remote, "main")
        (arc,) = self.archives(clone, "archives")
        man = T.jload(arc[: -len(".tar.gz.age")] + ".manifest.json")
        self.assertEqual(man["cifratura"]["destinatario"], self.v2_pub)               # stesso formato di external_backup.py
        rc, rout, _ = self.case.restore(arc, self.v2_ident)
        self.assertEqual(rc, 0, rout)
        self.assertIn("RISULTATO: OK", rout)

    def test_two_recipients_either_private_key_restores_and_v1_key_cannot(self):
        rc, out = self.multi(self.rec2, self.fp2, self.v2_remote, os.path.join(self.t, "w2"))
        self.assertEqual(rc, 0, out)
        (arc,) = self.archives(self.clone(self.v2_remote, "main"), "archives")
        man = T.jload(arc[: -len(".tar.gz.age")] + ".manifest.json")
        self.assertEqual(man["cifratura"]["destinatario"].split(","), [self.v2_pub, self.pers_pub])
        for ident in (self.v2_ident, self.pers_ident):
            rc, rout, _ = self.case.restore(arc, ident)
            self.assertEqual(rc, 0, rout)
            self.assertIn("RISULTATO: OK", rout)
        rc, rout, _ = self.case.restore(arc, self.v1_ident)
        self.assertEqual(rc, 1)
        self.assertIn("decifratura non riuscita", rout)

    def test_unapproved_recipients_refuse_and_publish_nothing(self):
        for name, recfile, fp in (("file_v1_con_impronta_v2", self.case.recfile, self.fp1),
                                  ("v2_piu_personale_con_impronta_solo_v2", self.rec2, self.fp1),
                                  ("solo_v2_con_impronta_a_due", self.rec1, self.fp2),
                                  ("impronta_vuota", self.rec1, "")):
            with self.subTest(caso=name):
                rc, out = self.multi(recfile, fp, self.v2_remote, os.path.join(self.t, "w-" + name))
                self.assertEqual(rc, 1, out)
                self.assertTrue("recipient_mismatch" in out or "serve --expect-recipients-sha256" in out, out)
                self.assertEqual(self.heads(self.v2_remote).strip(), "")

    def test_a_replaced_classic_script_is_refused(self):
        tools = os.path.join(self.t, "tools-copia")
        shutil.copytree(HERE, tools, ignore=shutil.ignore_patterns("__pycache__", "fixtures"))
        with open(os.path.join(tools, "external_backup.py"), "a") as f:
            f.write("\n# alterato\n")
        cmd = [sys.executable, "-I", os.path.join(tools, "external_backup_multi.py"), "--expect-recipients-sha256", self.fp1, "--help"]
        p = subprocess.run(cmd, capture_output=True, text=True)
        cmd = [sys.executable, "-I", os.path.join(tools, "external_backup_multi.py"), "--expect-recipients-sha256", self.fp1,
               "--root", self.case.root, "--app-db", self.case.app_db, "--pool-db", self.case.pool_db, "--work", os.path.join(self.t, "wx"),
               "--remote", self.v2_remote, "--recipient-file", self.rec1]
        p = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("non e' la versione rivista", p.stdout)
        self.assertEqual(self.heads(self.v2_remote).strip(), "")


class V3AndBrainFreeMultiRecipientTests(MigrationCase):
    def test_v3_and_brain_free_with_two_recipients_restore_with_each_identity(self):
        for mode, sub in (("v3", "brain-v3"), ("brain-free", "brain-free")):
            rc, out = self.v3pipe(mode, self.rec2, self.fp2, self.v2_remote)
            self.assertEqual(rc, 0, out)
            (arc,) = self.archives(self.clone(self.v2_remote, sub), sub)
            man = T.jload(arc[: -len(".tar.gz.age")] + ".manifest.json")
            self.assertEqual(man["cifratura"]["destinatari"], [self.v2_pub, self.pers_pub])
            self.assertEqual(man["cifratura"]["destinatario"], self.v2_pub)
            self.assertEqual(man["cifratura"]["impronta_destinatari"], self.fp2)
            for ident in (self.v2_ident, self.pers_ident):
                p = subprocess.run([sys.executable, "-I", T.RESTORE, "--archive", arc, "--identity", ident,
                                    "--out", os.path.join(self.t, "r-%s-%d" % (mode, time.time_ns()))], capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_pipeline_refuses_when_the_recipients_file_drifted(self):
        rc, out = self.v3pipe("v3", self.case.recfile, self.fp1, self.v2_remote)            # sul server e' rimasta la chiave V1
        self.assertEqual(rc, 1, out)
        self.assertIn("recipient_mismatch", out)
        self.assertEqual(self.heads(self.v2_remote).strip(), "")
        rc, out = self.v3pipe("v3", self.rec1, "", self.v2_remote)
        self.assertEqual(rc, 1)
        self.assertIn("--expect-recipients-sha256", out)

    def test_pipeline_preflight_reports_the_fingerprint_check(self):
        base = [sys.executable, "-I", T.PIPE, "--mode", "v3", "--runs-root", self.runs, "--work", os.path.join(self.t, "wp"),
                "--recipient-file", self.rec1, "--tools", HERE, "--preflight", "--no-network"]
        p = subprocess.run(base + ["--expect-recipients-sha256", self.fp1], capture_output=True, text=True)
        self.assertIn("impronta dei destinatari uguale a quella approvata", p.stdout)
        p = subprocess.run(base + ["--expect-recipients-sha256", self.fp2], capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("recipient_mismatch", p.stdout)


class V1V2SeparationTests(MigrationCase):
    def test_v2_backups_never_touch_the_v1_repository_or_its_history(self):
        # situazione di partenza: archivi V1 (classico) gia' presenti nel repository V1
        rc, out = self.case.backup()
        self.assertEqual(rc, 0, out)
        for mode in ("v3", "brain-free"):
            self.assertEqual(self.v3pipe(mode, self.case.recfile, self.pin_of(self.case.recfile), self.v1_remote)[0], 0)
        before_heads = self.heads(self.v1_remote)
        before_objects = T.sh("git", "-C", self.v1_remote, "count-objects", "-v").stdout
        v1_tree = T.sh("git", "-C", self.v1_remote, "ls-tree", "-r", "main").stdout
        time.sleep(1.1)
        # migrazione: tre famiglie verso il repository V2 con destinatari V2 + personale
        self.assertEqual(self.multi(self.rec2, self.fp2, self.v2_remote, os.path.join(self.t, "w2"))[0], 0)
        for mode in ("v3", "brain-free"):
            self.assertEqual(self.v3pipe(mode, self.rec2, self.fp2, self.v2_remote)[0], 0)
        self.assertEqual(self.heads(self.v1_remote), before_heads, "i rami V1 sono cambiati")
        self.assertEqual(T.sh("git", "-C", self.v1_remote, "count-objects", "-v").stdout, before_objects)
        self.assertEqual(T.sh("git", "-C", self.v1_remote, "ls-tree", "-r", "main").stdout, v1_tree)
        self.assertEqual(sorted(l.split()[0] for l in self.heads(self.v2_remote).splitlines()),
                         ["refs/heads/brain-free", "refs/heads/brain-v3", "refs/heads/main"])
        # gli archivi V1 restano apribili SOLO con la chiave V1: la V2 e la personale non li aprono
        (old,) = self.archives(self.clone(self.v1_remote, "main"), "archives")
        rc, rout, _ = self.case.restore(old, self.v2_ident)
        self.assertEqual(rc, 1)
        self.assertIn("decifratura non riuscita", rout)
        rc, rout, _ = self.case.restore(old, self.v1_ident)
        self.assertEqual(rc, 0, rout)

    def pin_of(self, recfile):
        return AR.fingerprint(AR.read_recipients(recfile))

    def test_a_v1_archive_cannot_be_migrated_without_the_v1_key_but_fresh_backups_can(self):
        """Fotografia della situazione reale: la V2 non apre il V1; la strada e' un backup nuovo dei dati originali."""
        self.assertEqual(self.case.backup()[0], 0)
        (old,) = self.archives(self.clone(self.v1_remote, "main"), "archives")
        self.assertEqual(self.case.restore(old, self.v2_ident)[0], 1)
        time.sleep(1.1)
        self.assertEqual(self.multi(self.rec1, self.fp1, self.v2_remote, os.path.join(self.t, "w2"))[0], 0)
        (new,) = self.archives(self.clone(self.v2_remote, "main"), "archives")
        rc, rout, _ = self.case.restore(new, self.v2_ident)
        self.assertEqual(rc, 0, rout)


def mini_repo(dst):
    """Copia dei soli file che il verificatore di coerenza legge."""
    files = ["deploy/extbackup/recipient.txt", "deploy/extbackup/recipient-v2.txt", "deploy/extbackup/v2/run-classic.sh",
             "deploy/extbackup/v2/superbot-extbackup-v2.service", "deploy/extbackup/v2/superbot-extbackup-v2.timer",
             "deploy/extbackup/brain-v3/run-v3.sh", "deploy/extbackup/brain-v3/superbot-extbackup-v3.service",
             "deploy/extbackup/brain-v3/superbot-extbackup-v3.timer", "deploy/extbackup/v2/check_recipient_consistency.py",
             "deploy/extbackup/v2/set_recipients.py"] + ["deploy/scripts/" + n for n in (
                 "age_recipients.py", "external_backup_multi.py", "external_backup_brain_v3.py", "brain_v3_snapshot.py", "external_backup.py")]
    for rel in files:
        os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), os.path.join(dst, rel))
    return dst


class ConsistencyCheckerTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = mini_repo(os.path.join(self.td.name, "repo"))

    def tearDown(self):
        self.td.cleanup()

    def check(self, *extra, root=None):
        p = subprocess.run([sys.executable, "-I", CHECKER, "--root", root or self.root, *extra], capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout

    def edit(self, rel, fn):
        path = os.path.join(self.root, rel)
        T.spit(path, fn(T.slurp(path).decode()))

    def test_real_repository_is_consistent(self):
        rc, out = self.check(root=ROOT)
        self.assertEqual(rc, 0, out)
        self.assertIn("COERENZA DESTINATARI: OK", out)
        self.assertNotIn("NO  ", out)

    def test_mini_copy_is_consistent_too(self):
        self.assertEqual(self.check()[0], 0)

    def test_wrong_fingerprint_in_a_wrapper_is_caught(self):
        for rel in ("deploy/extbackup/v2/run-classic.sh", "deploy/extbackup/brain-v3/run-v3.sh"):
            with self.subTest(wrapper=rel):
                shutil.rmtree(self.root)
                self.root = mini_repo(os.path.join(self.td.name, "repo"))
                self.edit(rel, lambda t: re.sub(r"--expect-recipients-sha256 [0-9a-f]{64}", "--expect-recipients-sha256 " + "0" * 64, t))
                rc, out = self.check()
                self.assertEqual(rc, 1)
                self.assertIn("NO  %s: impronta dei destinatari approvata" % os.path.basename(rel), out)

    def test_v1_references_in_wrappers_units_or_scripts_are_caught(self):
        cases = [("deploy/extbackup/v2/run-classic.sh", lambda t: t.replace("superbot-backups-v2.git", "superbot-backups.git"), "run-classic.sh"),
                 ("deploy/extbackup/brain-v3/run-v3.sh", lambda t: t.replace("/root/.ssh/superbot_backup_v2_ed25519", "/root/.ssh/superbot_backup_ed25519"), "run-v3.sh"),
                 ("deploy/extbackup/brain-v3/run-v3.sh", lambda t: t.replace("/opt/superbot-extbackup-v2/recipients.txt", "/opt/superbot-extbackup/recipient.txt"), "run-v3.sh"),
                 ("deploy/extbackup/v2/superbot-extbackup-v2.service", lambda t: t + "Environment=X=/opt/superbot-extbackup/work\n", "superbot-extbackup-v2.service"),
                 ("deploy/scripts/external_backup_brain_v3.py", lambda t: t + "\nOLD='age142uj5c8x'\n", "external_backup_brain_v3.py")]
        for rel, fn, label in cases:
            with self.subTest(file=label, caso=rel):
                shutil.rmtree(self.root)
                self.root = mini_repo(os.path.join(self.td.name, "repo"))
                self.edit(rel, fn)
                rc, out = self.check()
                self.assertEqual(rc, 1, out)
                self.assertIn("NO", out)

    def test_wrapper_that_runs_the_classic_script_directly_is_caught(self):
        self.edit("deploy/extbackup/v2/run-classic.sh", lambda t: t.replace("external_backup_multi.py", "external_backup.py"))
        rc, out = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("NO  run-classic.sh: lancia lo script a destinatari multipli", out)

    def test_persistent_timer_and_foreign_exec_are_caught(self):
        self.edit("deploy/extbackup/v2/superbot-extbackup-v2.timer", lambda t: t.replace("[Install]", "Persistent=true\n\n[Install]"))
        self.edit("deploy/extbackup/brain-v3/superbot-extbackup-v3.service", lambda t: t.replace("run-v3.sh --mode v3", "run-v3.sh --mode v3\nExecStart=/bin/true"))
        rc, out = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("NO  superbot-extbackup-v2.timer: nessun Persistent=true", out)
        self.assertIn("NO  superbot-extbackup-v3.service: esegue solo il wrapper V2", out)

    def test_unguarded_cleanup_or_cleanup_outside_the_work_folder_is_caught(self):
        cases = {"deploy/extbackup/brain-v3/superbot-extbackup-v3.service": "superbot-extbackup-v3.service",
                 "deploy/extbackup/v2/superbot-extbackup-v2.service": "superbot-extbackup-v2.service"}
        for rel, label in cases.items():
            with self.subTest(unita=label, caso="senza flock"):
                shutil.rmtree(self.root)
                self.root = mini_repo(os.path.join(self.td.name, "repo"))
                self.edit(rel, lambda t: re.sub(r"(?m)^ExecStopPost=-/usr/bin/flock -n \S+ ", "ExecStopPost=", t))
                rc, out = self.check()
                self.assertEqual(rc, 1, out)
                self.assertIn("NO  %s: la pulizia ExecStopPost prende lo stesso .lock" % label, out)
            with self.subTest(unita=label, caso="lock sbagliato"):
                shutil.rmtree(self.root)
                self.root = mini_repo(os.path.join(self.td.name, "repo"))
                self.edit(rel, lambda t: re.sub(r"(?m)^(ExecStopPost=-/usr/bin/flock -n )\S+", r"\1/tmp/altro.lock", t))
                self.assertEqual(self.check()[0], 1)
            with self.subTest(unita=label, caso="cancella fuori dalla cartella"):
                shutil.rmtree(self.root)
                self.root = mini_repo(os.path.join(self.td.name, "repo"))
                self.edit(rel, lambda t: t.replace("rm -f ", "rm -f /opt/superbot-extbackup-v2/repo/x "))
                rc, out = self.check()
                self.assertEqual(rc, 1, out)
                self.assertIn("NO  %s: la pulizia agisce solo dentro" % label, out)

    def test_brain_v3_wrapper_must_work_in_the_separate_v2_folder(self):
        self.edit("deploy/extbackup/brain-v3/run-v3.sh", lambda t: t.replace("--work /opt/superbot-extbackup-v2/brain", "--work /opt/superbot-extbackup-v3"))
        rc, out = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("NO  run-v3.sh: cartella dati V2 separata", out)

    def test_v1_recipient_in_the_v2_file_or_modified_v1_file_is_caught(self):
        v1 = [l for l in T.slurp(os.path.join(self.root, "deploy/extbackup/recipient.txt")).decode().splitlines() if l.startswith("age1")][0]
        self.edit("deploy/extbackup/recipient-v2.txt", lambda t: t + v1 + "\n")
        rc, out = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("NO  la chiave V1 non e' tra i destinatari V2", out)
        shutil.rmtree(self.root)
        self.root = mini_repo(os.path.join(self.td.name, "repo"))
        self.edit("deploy/extbackup/recipient.txt", lambda t: t + "# toccato\n")
        self.assertIn("NO  file dei destinatari V1 presente e invariato", self.check()[1])

    def test_stale_classic_pin_in_the_multi_wrapper_is_caught(self):
        self.edit("deploy/scripts/external_backup.py", lambda t: t + "\n# cambiato\n")
        rc, out = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("NO  external_backup_multi.py fissa l'impronta", out)

    def installed_tree(self, drift=None):
        v2, v3, tools, sd, v1 = (os.path.join(self.td.name, n) for n in ("v2", "v3", "tools", "sd", "v1"))
        for d in (v2, v3, tools, sd, v1):
            os.makedirs(d, exist_ok=True)
        shutil.copy2(os.path.join(self.root, "deploy/extbackup/recipient-v2.txt"), os.path.join(v2, "recipients.txt"))
        shutil.copy2(os.path.join(self.root, "deploy/extbackup/v2/run-classic.sh"), v2)
        shutil.copy2(os.path.join(self.root, "deploy/extbackup/brain-v3/run-v3.sh"), v3)
        for n in ("age_recipients.py", "external_backup_multi.py", "external_backup_brain_v3.py", "brain_v3_snapshot.py", "external_backup.py"):
            shutil.copy2(os.path.join(self.root, "deploy/scripts", n), tools)
        for rel in ("deploy/extbackup/v2/superbot-extbackup-v2.service", "deploy/extbackup/v2/superbot-extbackup-v2.timer"):
            shutil.copy2(os.path.join(self.root, rel), sd)
        shutil.copy2(os.path.join(self.root, "deploy/extbackup/recipient.txt"), v1)
        if drift:
            drift(v2, v3, tools, sd, v1)
        return ["--installed", "--v2-dir", v2, "--v3-dir", v3, "--tools-dir", tools, "--systemd-dir", sd, "--v1-dir", v1]

    def test_installed_files_matching_the_repository_pass(self):
        rc, out = self.check(*self.installed_tree())
        self.assertEqual(rc, 0, out)
        self.assertIn("destinatari installati", out)

    def test_installed_drift_is_caught(self):
        def v1_key_on_vps(v2, v3, tools, sd, v1):
            shutil.copy2(os.path.join(v1, "recipient.txt"), os.path.join(v2, "recipients.txt"))

        def old_wrapper(v2, v3, tools, sd, v1):
            T.spit(os.path.join(v3, "run-v3.sh"), "#!/bin/sh\nexec /opt/superbot-tools/external_backup.py\n")

        def edited_tool(v2, v3, tools, sd, v1):
            with open(os.path.join(tools, "external_backup_multi.py"), "a") as f:
                f.write("# alterato\n")

        def v1_in_unit(v2, v3, tools, sd, v1):
            with open(os.path.join(sd, "superbot-extbackup-v2.service"), "a") as f:
                f.write("ExecStartPost=/opt/superbot-extbackup/run.sh\n")

        def v1_file_touched(v2, v3, tools, sd, v1):
            with open(os.path.join(v1, "recipient.txt"), "a") as f:
                f.write("# toccato\n")
        expect = {v1_key_on_vps: "NO  destinatari installati", old_wrapper: "NO  installato identico al repository: run-v3.sh",
                  edited_tool: "NO  installato identico al repository: external_backup_multi.py", v1_in_unit: "NO  unita' installata identica",
                  v1_file_touched: "NO  file V1 dei destinatari invariato"}
        for fn, needle in expect.items():
            with self.subTest(deriva=fn.__name__):
                shutil.rmtree(self.td.name + "/v2", ignore_errors=True)
                args = self.installed_tree(drift=fn)
                rc, out = self.check(*args)
                self.assertEqual(rc, 1, out)
                self.assertIn(needle, out)


# ======================================================================================================
# Installatore V2: profilo classico (Falco/Toro), file comuni, cancello del timer con attestazione delle Actions
# ======================================================================================================

WORKFLOW = os.path.join(ROOT, ".github", "workflows", "age-v2-recovery-verify.yml")
VERIFY = os.path.join(ROOT, "deploy", "extbackup", "age-v2-recovery", "verify_recovery.py")


def pinned_sha_of_workflow():
    return re.search(r"PINNED_SHA:\s*([0-9a-f]{40})", T.slurp(WORKFLOW).decode()).group(1)


def actions_cert(family, archive_sha, **override):
    c = {"schema": "superbot-brain-v3-restore-certificate-v1", "esito": "OK", "famiglia": family, "archivio": "x.tar.gz.age",
         "archivio_sha256": archive_sha, "eseguito_su": "github-actions", "origine": "github-actions", "run_id": "42685000001",
         "run_attempt": "1", "commit": "c" * 40, "repository": FG.REPO,
         "workflow_sha256": T.sha(T.slurp(WORKFLOW)), "script_sha256": T.sha(T.slurp(VERIFY)), "pinned_sha": pinned_sha_of_workflow(),
         "controllo_rc84": "non eseguito"}
    c.update(override)
    return c


class InstallerV2Base(T.InstallerBase):
    def setUp(self):
        super().setUp()
        self.cls = CLASSIC.ExternalBackupTests("test_full_round_trip_backup_then_restore")
        self.cls.setUp()
        self.gh = FG.FakeGitHub()                                      # le API pubbliche di GitHub, finte e locali
        self.addCleanup(self.gh.close)

    def tearDown(self):
        self.cls.tearDown()
        super().tearDown()

    def publish_run(self, cert, **kw):
        """Fa risultare a GitHub (finto) una run riuscita che ha emesso proprio questo certificato."""
        self.gh.register_valid(cert, T.slurp(WORKFLOW), T.slurp(VERIFY), **kw)
        return cert

    def run_prof(self, profile, *args, host="vps-singapore", **env):
        p = subprocess.run(self.inst_args(*args, host=host) + ["--profile", profile], capture_output=True, text=True, timeout=180,
                           env=self.env(**env))
        return p.returncode, p.stdout + p.stderr

    def approval_of(self, profile):
        rc, out = self.run_prof(profile, "status")
        return [l.split()[-1] for l in out.splitlines() if "impronta di approvazione" in l][0]

    def classic_v2_backup(self):
        c = self.cls
        cmd = [sys.executable, "-I", MULTI, "--expect-recipients-sha256", self.recpin, "--root", c.root, "--app-db", c.app_db,
               "--pool-db", c.pool_db, "--tools", HERE, "--work", os.path.join(self.v2, "work"), "--remote", self.remote,
               "--recipient-file", self.recfile, "--app-repo", "/nonexistent", "--bots-repo", "/nonexistent", "--brain-retries", "0",
               "--brain-arg=--quiet-secs", "--brain-arg=1", "--brain-arg=--attempts", "--brain-arg=2", "--brain-arg=--wait",
               "--brain-arg=0.1", "--brain-arg=--quiet-timeout", "--brain-arg=2"]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def real_attestation(self, tmp="cert-lines.txt"):
        """Righe CERTIFICATO prodotte dal VERO verify_recovery.py sui rami del repository di prova (chiave V2 di prova)."""
        base = os.path.join(self.td.name, "ver-repos")
        shutil.rmtree(base, ignore_errors=True)
        heads = subprocess.run(["git", "ls-remote", "--heads", self.remote], capture_output=True, text=True).stdout
        for b in ("main", "brain-v3", "brain-free"):
            if "refs/heads/" + b in heads:
                T.sh("git", "clone", "-q", "--branch", b, self.remote, os.path.join(base, b))
        os.makedirs(base, exist_ok=True)
        cmd = [sys.executable, "-I", VERIFY, "--identity", self.ident, "--repos-dir", base, "--pinned", ROOT, "--work",
               os.path.join(self.td.name, "ver-work"), "--run-id", "42685000001", "--workflow-sha256", T.sha(T.slurp(WORKFLOW)),
               "--script-sha256", T.sha(T.slurp(VERIFY)), "--pinned-sha", pinned_sha_of_workflow(),
               "--run-attempt", "1", "--commit", "c" * 40, "--repository", FG.REPO]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        lines = [l for l in p.stdout.splitlines() if l.startswith("CERTIFICATO ")]
        notes = [l[len("::notice title=CERTIFICATO::"):].replace("%0D", "\r").replace("%0A", "\n").replace("%25", "%")
                 for l in p.stdout.splitlines() if l.startswith("::notice title=CERTIFICATO::")]
        self.assertEqual(len(notes), len(lines))
        for l, note in zip(lines, notes):
            self.publish_run(json.loads(l[len("CERTIFICATO "):]), annotations=[{"title": "CERTIFICATO", "message": note}])
        path = os.path.join(self.td.name, tmp)
        T.spit(path, "\n".join(lines) + "\n")
        return path, lines


class InstallerClassicProfileTests(InstallerV2Base):
    def test_classic_profile_creates_only_its_files_and_leaves_v1_alone(self):
        v1_before = {n: T.sha(T.slurp(os.path.join(self.classic, n))) for n in os.listdir(self.classic)}
        before = self.snap()
        rc, out = self.run_prof("classic", "install")
        self.assertEqual(rc, 0, out)
        self.assertIn("coerenza dei destinatari compresa", out)
        self.assertEqual(self.snap(), before)
        ap = self.approval_of("classic")
        rc, out = self.run_prof("classic", "install", "--apply", "--approve", ap)
        self.assertEqual(rc, 0, out)
        self.assertEqual(sorted(os.listdir(self.v2)), ["recipients.txt", "run-classic.sh"])
        self.assertEqual(sorted(n for n in os.listdir(self.tools) if "recipient" in n or "multi" in n or "snapshot" in n or "brain_v3" in n),
                         ["age_recipients.py", "external_backup_multi.py"])
        self.assertEqual(oct(os.stat(os.path.join(self.v2, "run-classic.sh")).st_mode & 0o777), "0o700")
        self.assertEqual(T.slurp(os.path.join(self.v2, "recipients.txt")), T.slurp(RECIPIENT_V2))
        self.assertEqual(T.jload(os.path.join(self.state, "INSTALL-MANIFEST-classic.json"))["stato"], "completo")
        self.assertFalse(os.path.exists(os.path.join(self.state, "INSTALL-MANIFEST.json")))
        self.assertEqual({n: T.sha(T.slurp(os.path.join(self.classic, n))) for n in os.listdir(self.classic)}, v1_before)
        self.assertEqual(os.listdir(self.systemd), [])
        self.assertEqual(self.mutating_calls(), [])
        self.assertIn("GIA' INSTALLATO", self.run_prof("classic", "install", "--apply", "--approve", ap)[1])
        # i file installati si lanciano da soli e il wrapper rifiuta argomenti inattesi
        self.assertEqual(subprocess.run(["sh", os.path.join(self.v2, "run-classic.sh"), "--x"], capture_output=True).returncode, 2)

    def test_the_same_approval_covers_both_profiles(self):
        self.assertEqual(self.approval_of("classic"), self.approval_of("v3"))

    def test_shared_files_survive_the_rollback_of_one_profile_and_go_with_the_last(self):
        ap = self.approval_of("v3")
        self.assertEqual(self.run_prof("v3", "install", "--apply", "--approve", ap)[0], 0)
        self.assertEqual(self.run_prof("classic", "install", "--apply", "--approve", ap)[0], 0)
        rc, out = self.run_prof("v3", "rollback", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("usato anche dall'altro profilo", out)
        self.assertTrue(os.path.isfile(os.path.join(self.v2, "recipients.txt")))
        self.assertTrue(os.path.isfile(os.path.join(self.tools, "age_recipients.py")))
        self.assertFalse(os.path.exists(os.path.join(self.tools, "brain_v3_snapshot.py")))
        self.assertTrue(os.path.isfile(os.path.join(self.v2, "run-classic.sh")), "il rollback V3 ha tolto un file del classico")
        rc, out = self.run_prof("classic", "rollback", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(os.path.join(self.v2, "recipients.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.tools, "age_recipients.py")))
        self.assertFalse(os.path.exists(os.path.join(self.tools, "external_backup_multi.py")))
        self.assertTrue(os.path.isfile(os.path.join(self.tools, "external_backup.py")))           # il classico V1 non si tocca

    def test_a_drifted_recipients_file_on_the_server_blocks_the_installation(self):
        os.makedirs(self.v2)
        T.spit(os.path.join(self.v2, "recipients.txt"), T.slurp(os.path.join(ROOT, "deploy", "extbackup", "recipient.txt")))   # chiave V1
        for prof in ("classic", "v3"):
            rc, out = self.run_prof(prof, "install")
            self.assertEqual(rc, 1, out)
            self.assertIn("non lo sovrascrivo", out)

    def test_a_repository_whose_wrappers_disagree_blocks_everything(self):
        fake = os.path.join(self.td.name, "repo-copia")
        for rel in ("deploy/extbackup", "deploy/scripts", ".github/workflows"):
            shutil.copytree(os.path.join(ROOT, rel), os.path.join(fake, rel), ignore=shutil.ignore_patterns("__pycache__", "fixtures"))
        w = os.path.join(fake, "deploy/extbackup/v2/run-classic.sh")
        T.spit(w, re.sub(r"--expect-recipients-sha256 [0-9a-f]{64}", "--expect-recipients-sha256 " + "0" * 64, T.slurp(w).decode()))
        cmd = [sys.executable, os.path.join(fake, "deploy/extbackup/brain-v3/install_brain_v3_extension.py"), "install",
               "--profile", "classic", "--tools-dir", self.tools, "--work-dir", self.work, "--classic-dir", self.classic,
               "--systemd-dir", self.systemd, "--state-dir", self.state, "--v2-dir", self.v2, "--ssh-key", self.key, "--allow-nonroot"]
        p = subprocess.run(cmd, capture_output=True, text=True, env=self.env())
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("coerenza dei destinatari nel repository: NO", p.stdout)
        self.assertIn("run-classic.sh: impronta dei destinatari approvata", p.stdout)
        self.assertEqual(os.listdir(self.systemd), [])

    def test_the_classic_wrapper_refuses_scheduled_runs_without_the_gate_file(self):
        p = subprocess.run(["sh", os.path.join(ROOT, "deploy/extbackup/v2/run-classic.sh")], capture_output=True, text=True,
                           env=dict(os.environ, SUPERBOT_V2_SCHEDULED="1"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("timer_gate_missing", p.stderr)


class ClassicTimerGateTests(InstallerV2Base):
    def prepare(self):
        self.assertEqual(self.run_prof("classic", "install", "--apply", "--approve", self.approval_of("classic"))[0], 0)
        self.classic_v2_backup()

    def test_no_backup_no_attestation_no_timer(self):
        ap = self.approval_of("classic")
        rc, out = self.run_prof("classic", "install", "--with-timer", "--apply", "--approve", ap)
        self.assertEqual(rc, 1, out)
        self.assertIn("CANCELLO DEL TIMER", out)
        self.assertIn("nessun backup reale", out)
        self.assertEqual(os.listdir(self.systemd), [])
        self.assertEqual(self.mutating_calls(), [])

    def test_a_real_backup_alone_is_not_enough(self):
        self.prepare()
        rc, out = self.run_prof("classic", "install", "--with-timer")
        self.assertEqual(rc, 1)
        self.assertIn("manca --restore-certificate", out)

    def test_a_local_certificate_is_not_accepted_for_the_classic_family(self):
        self.prepare()
        man = T.jload(next(os.path.join(dp, f) for dp, _d, fn in os.walk(os.path.join(self.v2, "work", "repo", "archives"))
                           for f in fn if f.endswith(".manifest.json")))
        c = actions_cert("classico", man["sha256"], origine="ripristino-locale", eseguito_su="altro-pc")
        path = os.path.join(self.td.name, "loc.json")
        T.spit(path, json.dumps(c))
        rc, out = self.run_prof("classic", "install", "--with-timer", "--restore-certificate", path)
        self.assertEqual(rc, 1)
        self.assertIn("serve un certificato prodotto dal workflow protetto", out)

    def test_real_attestation_from_the_verifier_activates_the_timer_without_a_backlog_run(self):
        self.prepare()
        path, lines = self.real_attestation()
        self.assertEqual(len(lines), 1, lines)
        self.assertEqual(json.loads(lines[0][len("CERTIFICATO "):])["famiglia"], "classico")
        ap = self.approval_of("classic")
        rc, out = self.run_prof("classic", "install", "--with-timer", "--restore-certificate", path)
        self.assertEqual(rc, 0, out)
        self.assertIn("cancello del timer soddisfatto", out)
        self.assertEqual(self.mutating_calls(), [])
        rc, out = self.run_prof("classic", "install", "--with-timer", "--restore-certificate", path, "--apply", "--approve", ap)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.mutating_calls(), ["daemon-reload", "enable superbot-extbackup-v2.timer", "start superbot-extbackup-v2.timer"])
        self.assertFalse([l for l in self.log() if "--now" in l or l.endswith("superbot-extbackup-v2.service") and l.startswith(("start", "restart"))])
        timer = T.slurp(os.path.join(self.systemd, "superbot-extbackup-v2.timer")).decode()
        self.assertFalse([l for l in timer.splitlines() if l.strip().startswith("Persistent")])
        self.assertEqual(self.sc(), {"enabled": ["superbot-extbackup-v2.timer"], "active": ["superbot-extbackup-v2.timer"]})
        self.assertTrue(os.path.isfile(os.path.join(self.v2, "timer-gate.json")))
        # il timer V1 di Falco/Toro non e' stato nominato nemmeno una volta
        self.assertFalse([l for l in self.log() if "superbot-extbackup.timer" in l or "superbot-extbackup.service" in l and l.split()[0] != "is-active"])
        # rollback: il timer V2 sparisce, il V1 non e' mai stato toccato
        rc, out = self.run_prof("classic", "rollback", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.sc(), {"enabled": [], "active": []})
        self.assertEqual(os.listdir(self.systemd), [])

    def test_tampered_or_foreign_attestations_are_refused(self):
        self.prepare()
        man = T.jload(next(os.path.join(dp, f) for dp, _d, fn in os.walk(os.path.join(self.v2, "work", "repo", "archives"))
                           for f in fn if f.endswith(".manifest.json")))
        good = self.publish_run(actions_cert("classico", man["sha256"]))
        path0 = os.path.join(self.td.name, "ok.json")
        T.spit(path0, json.dumps(good))
        self.assertEqual(self.run_prof("classic", "install", "--with-timer", "--restore-certificate", path0)[0], 0)
        cases = {"workflow_diverso": {"workflow_sha256": "1" * 64}, "script_diverso": {"script_sha256": "2" * 64},
                 "commit_diverso": {"pinned_sha": "3" * 40}, "run_senza_numero": {"run_id": "abc"},
                 "esito_no": {"esito": "FALLITO"}, "eseguito_altrove": {"eseguito_su": "vps-singapore"},
                 "archivio_ignoto": {"archivio_sha256": "4" * 64}, "famiglia_v3": {"famiglia": "v3"}}
        for name, over in cases.items():
            with self.subTest(caso=name):
                path = os.path.join(self.td.name, "bad-%s.json" % name)
                T.spit(path, json.dumps(dict(good, **over)))
                rc, out = self.run_prof("classic", "install", "--with-timer", "--restore-certificate", path)
                self.assertEqual(rc, 1, out)
                self.assertIn("CANCELLO DEL TIMER", out)
        self.assertEqual(os.listdir(self.systemd), [])

    def test_v3_profile_accepts_the_same_kind_of_attestation_for_its_family(self):
        cert_local, _arc = self.make_proof()                          # backup V3 reale pubblicato (famiglia v3) nella cartella di lavoro V3
        man = T.jload(next(os.path.join(dp, f) for dp, _d, fn in os.walk(os.path.join(self.work, "v3", "repo", "brain-v3"))
                           for f in fn if f.endswith(".manifest.json")))
        path = os.path.join(self.td.name, "actions-v3.txt")
        T.spit(path, "CERTIFICATO " + json.dumps(self.publish_run(actions_cert("v3", man["sha256"], controllo_rc84="eseguito"))) + "\n")
        rc, out = self.run_prof("v3", "install", "--with-timer", "--restore-certificate", path)
        self.assertEqual(rc, 0, out)
        self.assertIn("github-actions", out)
        bad = os.path.join(self.td.name, "actions-v3-bad.txt")
        T.spit(bad, "CERTIFICATO " + json.dumps(actions_cert("v3", man["sha256"], workflow_sha256="9" * 64)) + "\n")
        self.assertEqual(self.run_prof("v3", "install", "--with-timer", "--restore-certificate", bad)[0], 1)


class CertificateAuthenticityTests(InstallerV2Base):
    """Un rapporto non firmato non e' una prova: solo una run di GitHub confermata dalle sue API apre il cancello del timer."""

    def prepare(self):
        self.assertEqual(self.run_prof("classic", "install", "--apply", "--approve", self.approval_of("classic"))[0], 0)
        self.classic_v2_backup()
        man = T.jload(next(os.path.join(dp, f) for dp, _d, fn in os.walk(os.path.join(self.v2, "work", "repo", "archives"))
                           for f in fn if f.endswith(".manifest.json")))
        self.cert = actions_cert("classico", man["sha256"])
        self.cert_path = os.path.join(self.td.name, "c.json")

    def attempt(self, cert=None, **publish):
        cert = cert or self.cert
        self.gh.json_routes.clear()
        self.gh.raw_routes.clear()
        if publish is not None and publish.get("_pubblica", True):
            publish.pop("_pubblica", None)
            self.publish_run(cert, **publish)
        T.spit(self.cert_path, json.dumps(cert))
        return self.run_prof("classic", "install", "--with-timer", "--restore-certificate", self.cert_path)

    def test_a_run_confirmed_by_github_opens_the_gate_and_only_get_requests_without_credentials_are_made(self):
        self.prepare()
        rc, out = self.attempt()
        self.assertEqual(rc, 0, out)
        self.assertIn("autenticita': verificata con le API di GitHub", out)
        self.assertTrue(self.gh.log)
        for r in self.gh.log:
            self.assertEqual(r["metodo"], "GET")
            self.assertTrue(r["percorso"].startswith("/repos/alexiptv82/SuperBot-Trading/"), r)
            self.assertFalse({"authorization", "cookie", "x-github-token"} & set(r["intestazioni"]), r)

    def test_a_certificate_that_github_does_not_confirm_is_refused_in_every_way_it_can_be_forged(self):
        self.prepare()
        wf, sc = T.slurp(WORKFLOW), T.slurp(VERIFY)
        cases = {
            "run inesistente": dict(_pubblica=False),
            "run fallita": dict(run={"conclusion": "failure"}),
            "run non conclusa": dict(run={"status": "in_progress", "conclusion": None}),
            "commit diverso": dict(run={"head_sha": "d" * 40}),
            "tentativo diverso": dict(run={"run_attempt": 2}),
            "ramo non atteso": dict(branch="cursor/un-ramo-qualunque"),
            "evento non ammesso": dict(run={"event": "pull_request"}),
            "altro workflow": dict(run={"path": ".github/workflows/altro.yml"}),
            "repository diverso": dict(run={"repository": {"full_name": "altro/repo"}}),
            "fork": dict(run={"head_repository": {"full_name": "altro/fork"}}),
            "workflow modificato al commit": dict(files={FG.WORKFLOW_PATH: wf + b"\n# modifica"}),
            "script modificato al commit": dict(files={FG.SCRIPT_PATH: sc + b"\n# modifica"}),
            "job fallito": dict(jobs=[{"id": FG.JOB_ID, "conclusion": "failure"}]),
            "nessun job": dict(jobs=[]),
            "nessuna annotazione": dict(annotations=[]),
            "annotazione con altro testo": dict(annotations=[{"title": "CERTIFICATO", "message": json.dumps(dict(self.cert, controllo_rc84="eseguito"))}]),
            "annotazione con altro titolo": dict(annotations=[{"title": "NOTA", "message": json.dumps(self.cert, sort_keys=True, separators=(",", ":"))}]),
        }
        for name, kw in cases.items():
            with self.subTest(caso=name):
                rc, out = self.attempt(**kw)
                self.assertEqual(rc, 1, out)
                self.assertIn("PROVA NON AUTENTICA", out)
                self.assertIn("CANCELLO DEL TIMER", out)
                self.assertEqual(os.listdir(self.systemd), [])
        self.assertEqual(self.mutating_calls(), [])

    def test_old_format_or_incomplete_certificates_have_no_verifiable_proof(self):
        self.prepare()
        for field in ("commit", "run_attempt", "repository"):
            with self.subTest(manca=field):
                cert = {k: v for k, v in self.cert.items() if k != field}
                rc, out = self.attempt(cert, **{"_pubblica": False})
                self.assertEqual(rc, 1, out)
                self.assertIn("PROVA NON AUTENTICA", out)
        rc, out = self.attempt(dict(self.cert, run_id="12"), **{"_pubblica": False})
        self.assertEqual(rc, 1)

    def test_an_unreachable_github_never_means_verified(self):
        self.prepare()
        self.gh.close()
        T.spit(self.cert_path, json.dumps(self.cert))
        rc, out = self.run_prof("classic", "install", "--with-timer", "--restore-certificate", self.cert_path)
        self.assertEqual(rc, 1, out)
        self.assertIn("prova non verificabile", out)

    def test_the_proof_only_talks_https_and_loopback_for_tests(self):
        import github_run_proof as GP
        with self.assertRaises(GP.ProofError):
            GP.http_get("http://api.github.com/x")
        with self.assertRaises(GP.ProofError):
            GP.http_get("http://127.0.0.1:9/x")                      # il loopback in chiaro e' ammesso solo dalle prove
        with self.assertRaises(GP.ProofError):
            GP.http_get("file:///etc/passwd", allow_http=True)
        self.assertNotIn("Authorization", T.slurp(os.path.join(HERE, "github_run_proof.py")).decode().replace("Authorization\"", ""))

    def test_an_unsigned_local_report_needs_an_explicit_choice_and_is_labelled(self):
        cert_local, _arc = self.make_proof()
        self.accept_unsigned = False
        self.addCleanup(setattr, self, "accept_unsigned", True)
        rc, out = self.run_prof("v3", "install", "--with-timer", "--restore-certificate", cert_local)
        self.assertEqual(rc, 1, out)
        self.assertIn("RAPPORTO NON FIRMATO", out)
        self.accept_unsigned = True
        rc, out = self.run_prof("v3", "install", "--with-timer", "--restore-certificate", cert_local)
        self.assertEqual(rc, 0, out)
        self.assertIn("NON FIRMATO (accettato su richiesta esplicita)", out)

    def test_a_certificate_pasted_into_a_text_file_is_not_enough(self):
        """Il vecchio punto debole: righe CERTIFICATO scritte a mano con le impronte giuste. Senza la run su GitHub non vale nulla."""
        self.prepare()
        T.spit(self.cert_path, "CERTIFICATO " + json.dumps(self.cert) + "\n")
        rc, out = self.run_prof("classic", "install", "--with-timer", "--restore-certificate", self.cert_path)
        self.assertEqual(rc, 1, out)
        self.assertIn("PROVA NON AUTENTICA", out)


SETREC = os.path.join(ROOT, "deploy", "extbackup", "v2", "set_recipients.py")


class PersonalKeyIntroductionTests(MigrationCase):
    """Aggiungere la chiave personale: un diff piccolo, impronte riallineate ovunque, entrambe le chiavi aprono tutto."""

    def mini(self):
        root = mini_repo(os.path.join(self.t, "repo"))
        return root

    def run_set(self, root, *extra):
        p = subprocess.run([sys.executable, "-I", os.path.join(root, "deploy/extbackup/v2/set_recipients.py"), "--root", root, *extra],
                           capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout + p.stderr

    def wrapper_pin(self, root, rel):
        return re.search(r"--expect-recipients-sha256 ([0-9a-f]{64})", T.slurp(os.path.join(root, rel)).decode()).group(1)

    def test_adding_the_personal_key_realigns_every_pin_and_keeps_the_v2_key(self):
        root = self.mini()
        shutil.copy2(SETREC, os.path.join(root, "deploy/extbackup/v2/set_recipients.py"))
        before = {r: T.slurp(os.path.join(root, r)) for r in ("deploy/extbackup/recipient-v2.txt", "deploy/extbackup/v2/run-classic.sh",
                                                               "deploy/extbackup/brain-v3/run-v3.sh", "deploy/extbackup/recipient.txt")}
        keys_before = AR.read_recipients(os.path.join(root, "deploy/extbackup/recipient-v2.txt"))
        rc, out = self.run_set(root, "--add", self.pers_pub, "--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertEqual({r: T.slurp(os.path.join(root, r)) for r in before}, before, "la simulazione ha modificato dei file")
        rc, out = self.run_set(root, "--add", self.pers_pub)
        self.assertEqual(rc, 0, out)
        self.assertIn("COERENZA DESTINATARI: OK", out)
        keys = AR.read_recipients(os.path.join(root, "deploy/extbackup/recipient-v2.txt"))
        self.assertEqual(keys, keys_before + [self.pers_pub])                        # la V2 resta
        fp = AR.fingerprint(keys)
        for rel in ("deploy/extbackup/v2/run-classic.sh", "deploy/extbackup/brain-v3/run-v3.sh"):
            self.assertEqual(self.wrapper_pin(root, rel), fp)
        self.assertEqual(T.slurp(os.path.join(root, "deploy/extbackup/recipient.txt")), before["deploy/extbackup/recipient.txt"])   # V1 intatto
        changed = [r for r in before if T.slurp(os.path.join(root, r)) != before[r]]
        self.assertEqual(sorted(changed), ["deploy/extbackup/brain-v3/run-v3.sh", "deploy/extbackup/recipient-v2.txt", "deploy/extbackup/v2/run-classic.sh"])
        self.assertEqual(subprocess.run([sys.executable, "-I", CHECKER, "--root", root], capture_output=True).returncode, 0)

    def test_with_the_updated_recipients_both_keys_open_every_family(self):
        root = self.mini()
        shutil.copy2(SETREC, os.path.join(root, "deploy/extbackup/v2/set_recipients.py"))
        # le chiavi del test: sostituisco la V2 "vera" con la V2 di prova nel file e nei wrapper, poi aggiungo la personale
        T.spit(os.path.join(root, "deploy/extbackup/recipient-v2.txt"), "# v2 di prova\n%s\n" % self.v2_pub)
        for rel in ("deploy/extbackup/v2/run-classic.sh", "deploy/extbackup/brain-v3/run-v3.sh"):
            path = os.path.join(root, rel)
            T.spit(path, re.sub(r"--expect-recipients-sha256 [0-9a-f]{64}", "--expect-recipients-sha256 " + self.fp1, T.slurp(path).decode()))
        self.assertEqual(self.run_set(root, "--add", self.pers_pub)[0], 0)
        rec = os.path.join(root, "deploy/extbackup/recipient-v2.txt")
        fp = self.wrapper_pin(root, "deploy/extbackup/brain-v3/run-v3.sh")
        self.assertEqual(fp, AR.fingerprint(AR.read_recipients(rec)))
        self.assertEqual(self.multi(rec, fp, self.v2_remote, os.path.join(self.t, "w2"))[0], 0)
        for mode in ("v3", "brain-free"):
            self.assertEqual(self.v3pipe(mode, rec, fp, self.v2_remote)[0], 0)
        for ident in (self.v2_ident, self.pers_ident):
            (arc,) = self.archives(self.clone(self.v2_remote, "main"), "archives")
            self.assertEqual(self.case.restore(arc, ident)[0], 0)
            (arc3,) = self.archives(self.clone(self.v2_remote, "brain-v3"), "brain-v3")
            p = subprocess.run([sys.executable, "-I", T.RESTORE, "--archive", arc3, "--identity", ident,
                                "--out", os.path.join(self.t, "rp-%d" % time.time_ns())], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        # e un server rimasto con il vecchio file (solo V2) rifiuta di cifrare con l'impronta nuova
        rc, out = self.multi(self.rec1, fp, self.v2_remote, os.path.join(self.t, "w2b"))
        self.assertEqual(rc, 1)
        self.assertIn("recipient_mismatch", out)

    def test_dangerous_inputs_are_refused_and_change_nothing(self):
        root = self.mini()
        shutil.copy2(SETREC, os.path.join(root, "deploy/extbackup/v2/set_recipients.py"))
        v1 = AR.read_recipients(os.path.join(root, "deploy/extbackup/recipient.txt"))[0]
        v2 = AR.read_recipients(os.path.join(root, "deploy/extbackup/recipient-v2.txt"))[0]
        before = {r: T.slurp(os.path.join(root, r)) for r in ("deploy/extbackup/recipient-v2.txt", "deploy/extbackup/v2/run-classic.sh")}
        for name, key in (("privata", "AGE-SECRET-KEY-1" + "Q" * 58), ("corta", "age1abc"), ("duplicata", v2), ("chiave_v1", v1)):
            with self.subTest(caso=name):
                rc, out = self.run_set(root, "--add", key)
                self.assertEqual(rc, 1, out)
                self.assertIn("RIFIUTATO", out)
                self.assertNotIn("AGE-SECRET-KEY-1" + "Q" * 10, out)
                self.assertEqual({r: T.slurp(os.path.join(root, r)) for r in before}, before)

    def test_removing_a_recipient_realigns_the_pins_and_never_leaves_zero(self):
        root = self.mini()
        shutil.copy2(SETREC, os.path.join(root, "deploy/extbackup/v2/set_recipients.py"))
        keys0 = AR.read_recipients(os.path.join(root, "deploy/extbackup/recipient-v2.txt"))
        self.assertEqual(self.run_set(root, "--add", self.pers_pub)[0], 0)
        before = {r: T.slurp(os.path.join(root, r)) for r in ("deploy/extbackup/recipient-v2.txt", "deploy/extbackup/v2/run-classic.sh")}
        rc, out = self.run_set(root, "--remove", keys0[0], "--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertEqual({r: T.slurp(os.path.join(root, r)) for r in before}, before)
        rc, out = self.run_set(root, "--remove", keys0[0])
        self.assertEqual(rc, 0, out)
        self.assertIn("COERENZA DESTINATARI: OK", out)
        keys = AR.read_recipients(os.path.join(root, "deploy/extbackup/recipient-v2.txt"))
        self.assertEqual(keys, [self.pers_pub])
        for rel in ("deploy/extbackup/v2/run-classic.sh", "deploy/extbackup/brain-v3/run-v3.sh"):
            self.assertEqual(self.wrapper_pin(root, rel), AR.fingerprint(keys))
        # l'ultimo destinatario non si toglie, una chiave estranea nemmeno, una privata nemmeno
        for key, frag in ((self.pers_pub, "unico destinatario"), (keys0[0], "non e' tra i destinatari"), ("AGE-SECRET-KEY-1" + "Q" * 58, "non e' una chiave pubblica")):
            rc, out = self.run_set(root, "--remove", key)
            self.assertEqual(rc, 1, out)
            self.assertIn(frag, out)
        self.assertEqual(AR.read_recipients(os.path.join(root, "deploy/extbackup/recipient-v2.txt")), [self.pers_pub])
        self.assertEqual(self.run_set(root)[0], 1)                                   # ne --add ne --remove
        self.assertEqual(self.run_set(root, "--add", keys0[0], "--remove", keys0[0])[0], 1)


KIT = os.path.join(ROOT, "deploy", "extbackup", "age-v2-migration", "chiave_personale.py")


@unittest.skipUnless(HAVE_AGE, "mancano age/git")
class PersonalKeyKitTests(unittest.TestCase):
    """Il kit per il PC del proprietario: crea e prova la chiave senza mai mostrare la privata ne' usare la rete."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.dir = os.path.join(self.td.name, "chiave")

    def run_kit(self, *args):
        p = subprocess.run([sys.executable, "-I", KIT, *args], capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout + p.stderr

    def make(self):
        rc, out = self.run_kit("crea", "--cartella", self.dir)
        self.assertEqual(rc, 0, out)
        pub = re.search(r"chiave pubblica: (age1[a-z0-9]{58})", out).group(1)
        return pub, out

    def test_create_prints_only_the_public_key_and_writes_the_private_one_with_600(self):
        pub, out = self.make()
        ident = os.path.join(self.dir, "chiave-personale.txt")
        self.assertEqual(oct(os.stat(ident).st_mode & 0o777), "0o600")
        self.assertEqual(oct(os.stat(self.dir).st_mode & 0o777), "0o700")
        secret = [l for l in T.slurp(ident).decode().splitlines() if l.startswith("AGE-SECRET-KEY-")][0]
        self.assertNotIn(secret, out)
        self.assertNotIn("AGE-SECRET-KEY", out)
        self.assertEqual(T.slurp(os.path.join(self.dir, "chiave-personale-pubblica.txt")).decode().splitlines()[-1], pub)
        self.assertIn(hashlib.sha256((pub + "\n").encode()).hexdigest(), out)
        # un nome diverso crea una seconda chiave (es. quella per l'ambiente di GitHub) senza toccare la prima
        rc, out3 = self.run_kit("crea", "--cartella", self.dir, "--nome", "chiave-actions")
        self.assertEqual(rc, 0, out3)
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "chiave-actions.txt")))
        self.assertNotEqual(re.search(r"chiave pubblica: (age1\S+)", out3).group(1), pub)
        rc, out3 = self.run_kit("crea", "--cartella", self.dir, "--nome", "../fuori")
        self.assertEqual(rc, 1)
        # non sovrascrive
        before = T.slurp(ident)
        rc, out2 = self.run_kit("crea", "--cartella", self.dir)
        self.assertEqual(rc, 1)
        self.assertIn("non la sovrascrivo", out2)
        self.assertEqual(T.slurp(ident), before)

    def test_proof_accepts_the_right_pair_and_rejects_everything_else(self):
        pub, _ = self.make()
        ident = os.path.join(self.dir, "chiave-personale.txt")
        rc, out = self.run_kit("prova", "--identita", ident, "--pubblica", pub)
        self.assertEqual(rc, 0, out)
        self.assertIn("ESITO COMPLESSIVO: OK - la chiave funziona", out)
        self.assertNotIn("AGE-SECRET-KEY", out)
        other = T.keygen(os.path.join(self.td.name, "altra"))
        rc, out = self.run_kit("prova", "--identita", ident, "--pubblica", other)
        self.assertEqual(rc, 1, out)
        self.assertIn("corrisponde alla pubblica indicata: NO", out)
        rc, out = self.run_kit("prova", "--identita", ident, "--pubblica", "AGE-SECRET-KEY-1" + "Q" * 58)
        self.assertEqual(rc, 1)
        self.assertIn("chiave PRIVATA", out)
        self.assertNotIn("Q" * 20, out)
        rc, out = self.run_kit("prova", "--identita", os.path.join(self.td.name, "non-esiste"), "--pubblica", pub)
        self.assertEqual(rc, 1)

    def test_the_personal_key_really_opens_a_v2_backup_like_the_installed_flow(self):
        """Un archivio cifrato per V2 + personale (come produce il backup) si apre con la sola chiave personale creata dal kit."""
        pub, _ = self.make()
        ident = os.path.join(self.dir, "chiave-personale.txt")
        v2_pub = T.keygen(os.path.join(self.td.name, "v2"))
        plain, enc = os.path.join(self.td.name, "p"), os.path.join(self.td.name, "p.age")
        T.spit(plain, "dati di prova\n")
        subprocess.run(["age", "-r", v2_pub, "-r", pub, "-o", enc, plain], check=True)
        p = subprocess.run(["age", "-d", "-i", ident, enc], capture_output=True)
        self.assertEqual(p.stdout, b"dati di prova\n")

    def test_it_refuses_to_work_inside_a_git_repository_or_on_the_server(self):
        repo = os.path.join(self.td.name, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        rc, out = self.run_kit("crea", "--cartella", os.path.join(repo, "chiave"))
        self.assertEqual(rc, 1)
        self.assertIn("dentro un repository git", out)
        self.assertFalse(os.path.exists(os.path.join(repo, "chiave", "chiave-personale.txt")))
        import importlib.util
        spec = importlib.util.spec_from_file_location("kit", KIT)
        kit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(kit)
        kit.SERVER_MARKERS = (self.td.name,)                                          # "il server" = una cartella che esiste
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = kit.main(["crea", "--cartella", os.path.join(self.td.name, "x")])
        self.assertEqual(rc, 1)
        self.assertIn("sembra il server", buf.getvalue())
        self.assertFalse(os.path.exists(os.path.join(self.td.name, "x")))

    def test_the_kit_has_no_network_and_no_way_to_send_the_key_anywhere(self):
        text = T.slurp(KIT).decode()
        import ast
        mods = {n.names[0].name.split(".")[0] for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Import)}
        mods |= {n.module.split(".")[0] for n in ast.walk(ast.parse(text)) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(mods - {"argparse", "hashlib", "os", "shutil", "subprocess", "sys", "tempfile"}, set())
        for forbidden in ("socket", "urllib", "http://", "https://", "requests", "ssl", "smtplib", "ftplib", "curl", "git push"):
            self.assertNotIn(forbidden, text, forbidden)
        self.assertEqual(sorted(set(re.findall(r'subprocess\.run\(\[("[a-z-]+")', text))), ['"age"', '"age-keygen"'])


if __name__ == "__main__":
    unittest.main()
