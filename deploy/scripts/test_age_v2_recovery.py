"""Prove del workflow e dello script di verifica di recupero con la chiave age V2 (nessun Secret, nessuna rete, nessuna VPS).

Si lanciano con:  python3 -m unittest deploy/scripts/test_age_v2_recovery.py -v
Servono `age`, `age-keygen` e `git`. Con SUPERBOT_RC84_SRC (checkout di RC84) si prova anche il confronto con il codice RC84.
Chiavi, repository "privati" e archivi sono creati in cartelle temporanee: la chiave "V2" dei test e' una chiave di prova.
Quello che non si puo' eseguire si SALTA e lo dice (SKIP, mai PASS).
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
import test_brain_v3_backup as T                                  # noqa: E402  (solo il modulo: i suoi test non si duplicano)
import test_external_backup as CLASSIC                            # noqa: E402

WORKFLOW = os.path.join(ROOT, ".github", "workflows", "age-v2-recovery-verify.yml")
VERIFY = os.path.join(ROOT, "deploy", "extbackup", "age-v2-recovery", "verify_recovery.py")
DOC = os.path.join(ROOT, "deploy", "extbackup", "age-v2-recovery", "LEGGIMI.md")
RECIPIENT_V2 = os.path.join(ROOT, "deploy", "extbackup", "recipient-v2.txt")
PINNED_SHA = "7b2aabe900d6ba6b032ab34e7568e4f4dd70d5ec"
RC84_SHA = "0e29a73a36f668643da4088178bacb8616a45ac0"
HAVE_AGE = T.HAVE_AGE
HAVE_RC84 = T.HAVE_RC84
MARKER = "MARCATORE-CHIAVE-SEGRETA-XYZ-4417"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def steps_of(text):
    """Passi del workflow: nome -> testo."""
    parts = re.split(r"(?m)^      - name: ", text)
    return {p.split("\n", 1)[0].strip(): p for p in parts[1:]}


class WorkflowStaticTests(unittest.TestCase):
    """Cosa il workflow puo' e non puo' fare, controllato sul testo."""

    @classmethod
    def setUpClass(cls):
        cls.text = read(WORKFLOW)
        cls.steps = steps_of(cls.text)

    def test_no_third_party_actions_no_artifacts_no_cache(self):
        self.assertNotRegex(self.text, r"(?m)^\s*-?\s*uses:")
        for word in ("upload-artifact", "actions/cache", "download-artifact", "actions/checkout"):
            self.assertNotIn(word, self.text)

    def test_no_server_access_at_all(self):
        for word in ("SINGAPORE", "SSH_PRIVATE_KEY", "51.79.205.82", "51.91.109.45", "root@", "scp ", "docker ", "superbot-desk"):
            self.assertNotIn(word, self.text)
        for line in self.text.splitlines():
            if re.search(r"\bssh\b", line):
                self.assertTrue(line.strip().startswith('SSHCMD="ssh -i'), "ssh inatteso: " + line.strip())

    def test_triggers_are_explicit_and_cannot_fire_from_forks_or_by_schedule(self):
        on = self.text.split("\npermissions:")[0]
        for forbidden in ("pull_request", "pull_request_target", "schedule", "workflow_run", "issue_comment", "repository_dispatch"):
            self.assertNotIn(forbidden, on)
        self.assertIn("workflow_dispatch:", on)
        self.assertIn("branches: [work/age-v2-recovery-run-20261110]", on)
        self.assertNotIn("work/age-v2-recovery-verify-20261110", on)          # il ramo di revisione non e' un ramo di avvio
        self.assertIn('- "deploy/extbackup/age-v2-recovery/RUN.trigger"', on)
        block = on.split("\non:\n")[1]
        self.assertEqual(re.findall(r"(?m)^  ([a-z_]+):", block), ["workflow_dispatch", "push"])   # solo questi due
        self.assertFalse(os.path.exists(os.path.join(ROOT, "deploy", "extbackup", "age-v2-recovery", "RUN.trigger")),
                         "il file di avvio NON deve esistere in questo commit")

    def test_permissions_are_read_only_and_job_is_environment_gated(self):
        self.assertRegex(self.text, r"(?m)^permissions:\n  contents: read\n")
        self.assertNotIn("write", self.text.split("jobs:")[0].split("permissions:")[1].split("concurrency:")[0])
        self.assertNotIn("id-token", self.text)
        self.assertIn("environment: age-recovery", self.text)

    def test_each_secret_is_visible_to_exactly_one_step_and_never_job_wide(self):
        self.assertEqual(sorted(set(re.findall(r"secrets\.([A-Za-z0-9_]+)", self.text))),
                         ["SUPERBOT_AGE_RECOVERY_KEY_V2", "SUPERBOT_BACKUPS_READ_KEY"])
        self.assertNotIn("GITHUB_TOKEN", self.text)
        jobhead = self.text.split("    steps:")[0]
        self.assertNotIn("secrets.", jobhead)
        owners = {}
        for name, body in self.steps.items():
            for s in re.findall(r"secrets\.([A-Za-z0-9_]+)", body):
                owners.setdefault(s, []).append(name)
        self.assertEqual({k: len(v) for k, v in owners.items()}, {"SUPERBOT_AGE_RECOVERY_KEY_V2": 1, "SUPERBOT_BACKUPS_READ_KEY": 1})
        self.assertIn("Chiave di recupero V2", owners["SUPERBOT_AGE_RECOVERY_KEY_V2"][0])
        self.assertIn("SOLA LETTURA", owners["SUPERBOT_BACKUPS_READ_KEY"][0])
        # il passo che esegue il programma non ha nessun Secret ne' in env ne' nel comando
        verify = [b for n, b in self.steps.items() if n.startswith("Confronto")][0]
        self.assertNotIn("secrets.", verify)
        self.assertNotIn("AGE_RECOVERY_KEY_V2", verify)

    def test_secret_values_are_only_tested_for_presence_or_written_to_a_file(self):
        for var in ("AGE_RECOVERY_KEY_V2", "BACKUPS_READ_KEY"):
            for line in self.text.splitlines():
                if "$" + var in line or "${" + var in line:
                    ok = (line.strip().startswith('test -n "$%s"' % var)
                          or re.fullmatch(r"\s*printf '%%s\\n' \"\$%s\" > \"\$(KEY|RUNNER_TEMP/age-v2-identity)\"" % var, line) is not None)
                    self.assertTrue(ok, "uso non ammesso di %s: %s" % (var, line.strip()))
        for bad in ("set -x", "xtrace", "ACTIONS_STEP_DEBUG", "ACTIONS_RUNNER_DEBUG", "env | ", "printenv", "base64", "::add-mask", "echo \"$AGE", "cat \"$RUNNER_TEMP/age"):
            self.assertNotIn(bad, self.text)

    def test_untrusted_input_never_reaches_the_shell_through_an_expression(self):
        exprs = re.findall(r"\$\{\{\s*([^}]+?)\s*\}\}", self.text)
        self.assertEqual(sorted(exprs), ["github.event.inputs.approval", "secrets.SUPERBOT_AGE_RECOVERY_KEY_V2",
                                         "secrets.SUPERBOT_BACKUPS_READ_KEY"])
        for line in self.text.splitlines():
            if "github.event.inputs.approval" in line:
                self.assertTrue(line.strip().startswith("INPUT_APPROVAL:"), line)          # solo come variabile d'ambiente
        self.assertIn('[[ "$WANT" =~ ^[0-9a-f]{64}$ ]]', self.text)

    def test_scripts_and_sources_are_pinned_by_full_commit_and_hash(self):
        self.assertIn("PINNED_SHA: " + PINNED_SHA, self.text)
        self.assertIn("RC84_SHA: " + RC84_SHA, self.text)
        pins = dict((m.group(1), m.group(2)) for m in re.finditer(r"check (deploy/scripts/\S+) ([0-9a-f]{64})", self.text))
        self.assertEqual(sorted(pins), ["deploy/scripts/backup_brain.py", "deploy/scripts/brain_v3_snapshot.py",
                                        "deploy/scripts/restore_brain_v3_backup.py", "deploy/scripts/restore_external_backup.py"])
        if subprocess.run(["git", "-C", ROOT, "cat-file", "-e", PINNED_SHA + "^{commit}"], capture_output=True).returncode != 0:
            self.skipTest("SKIP: il commit fissato %s non e' nella copia locale del repository" % PINNED_SHA[:10])
        for path, expected in pins.items():
            blob = subprocess.run(["git", "-C", ROOT, "show", "%s:%s" % (PINNED_SHA, path)], capture_output=True, check=True).stdout
            self.assertEqual(hashlib.sha256(blob).hexdigest(), expected, path)

    def test_cleanup_always_runs_and_the_approval_gate_precedes_every_secret(self):
        names = list(self.steps)
        self.assertEqual(len(names), 5)
        last = self.steps[names[-1]]
        self.assertIn("if: always()", last)
        for needle in ("age-v2-identity", "backups-read-key", "rm -rf"):
            self.assertIn(needle, last)
        first = self.steps[names[0]]
        self.assertNotIn("secrets.", first)
        self.assertIn("impronta di approvazione", first)
        self.assertLess(first.index("BLOCCO: impronta di approvazione"), len(first))
        self.assertIn("exit 1", first.split("BLOCCO: impronta di approvazione")[1][:400])

    def test_attestation_arguments_come_from_non_secret_variables_and_repository_is_v2(self):
        self.assertIn('--run-id "$GITHUB_RUN_ID"', self.text)
        self.assertIn('{ echo "WF_SHA=$WF"; echo "SC_SHA=$SC"; echo "PINNED_SHA=$PINNED_SHA"; } >> "$GITHUB_ENV"', self.text)
        self.assertIn("git@github.com:alexiptv82/superbot-backups-v2.git", self.text)
        self.assertNotRegex(self.text, r"superbot-backups\.git")                 # il repository V1 non si legge

    def test_approval_formula_is_identical_in_workflow_and_documentation(self):
        formula = "printf '%s\\n%s\\n' \"$WF\" \"$SC\" | sha256sum | cut -d' ' -f1"
        self.assertIn(formula, self.text)
        self.assertIn(formula, read(DOC))

    def test_yaml_is_well_formed_when_pyyaml_is_available(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("SKIP: PyYAML non disponibile, struttura YAML non verificata")
        doc = yaml.safe_load(self.text)
        triggers = doc.get(True, doc.get("on"))
        self.assertEqual(sorted(triggers), ["push", "workflow_dispatch"])
        self.assertEqual(doc["jobs"]["verify"]["environment"], "age-recovery")
        self.assertEqual(len(doc["jobs"]["verify"]["steps"]), 5)


class VerifierStaticTests(unittest.TestCase):
    def test_the_private_key_file_is_never_opened_or_read_by_the_program(self):
        src = read(VERIFY)
        self.assertNotRegex(src, r"open\([^)]*identity")
        self.assertNotRegex(src, r"identity[^\n]*\.read\(")
        self.assertNotIn("os.environ", src)
        self.assertNotIn("getenv", src)
        # l'unico uso della variabile e' passarne il PERCORSO ad age-keygen e agli script di ripristino
        uses = [l.strip() for l in src.splitlines() if "a.identity" in l or "identity," in l or '"--identity"' in l or "age-keygen" in l]
        self.assertTrue(uses)

    def test_program_prints_only_fixed_sentences(self):
        src = read(VERIFY)
        printed = re.findall(r'say\((.*)\)', src) + re.findall(r'out\((.*)\)', src)
        for p in printed:
            self.assertNotRegex(p, r"\bpub\b|\bidentity\b|text\b|\.read\(", "stampa di un valore non ammesso: " + p)

    def test_no_documentation_value_looks_like_a_secret(self):
        for path in (WORKFLOW, VERIFY, DOC):
            self.assertNotRegex(read(path), r"AGE-SECRET-KEY-[A-Z0-9]{10,}|BEGIN OPENSSH PRIVATE KEY")


ALLOWED = re.compile(
    r"^(# .*|## .*|ESITO .*|archivi nel ramo: \d+ \| cifrati per questa chiave: \d+ \| altro destinatario: \d+"
    r"|archivio piu' recente: \S+( \(in \d+ parti\))?"
    r"|- (manifest e SHA-256 dell'archivio cifrato: OK|decifratura age \(cifratura autenticata\): OK"
    r"|manifesto interno, SHA-256 di ogni file: OK|integrita' dei database SQLite: OK"
    r"|coerenza semantica del (primo|secondo) portafoglio classico: OK|catena hash del journal e identita' unica: OK"
    r"|codice RC84 fissato: accetta la run ripristinata|integrita' e misura del database storico: OK"
    r"|ripristino isolato completo: OK|run Brain V3 ripristinate e verificate: \d+"
    r"|nota: copia del cervello con eccezione dichiarata nel manifesto \(bot fermi o prima installazione\)"
    r"|[a-z' /,A-Z0-9()-]+: NON CONFERMATO|ripristino: ERRORE \(dettagli non pubblicati\))"
    r"|Nessun file decifrato e' stato caricato o conservato; nessun dato di portafoglio e' stato stampato\."
    r"|CERTIFICATO \{[^\n]*\})?$")


@unittest.skipUnless(HAVE_AGE, "mancano age/age-keygen/git")
class VerifierRunTests(unittest.TestCase):
    """Esecuzione vera dello script su tre famiglie di archivi cifrati per una chiave di prova."""

    def setUp(self):
        self.case = CLASSIC.ExternalBackupTests("test_full_round_trip_backup_then_restore")
        self.case.setUp()
        c = self.case
        self.t = c.td.name
        rc, out = c.backup()
        self.assertEqual(rc, 0, out)
        self.runs = os.path.join(self.t, "v3runs")
        os.makedirs(self.runs)
        r = T.Run(self.runs, "brain-v3-alfa1")
        r.decision(1, T.SECRET)
        r.open("p1")
        r.spend(10)
        self.legacy = os.path.join(self.t, "legacy", "brain.sqlite3")
        os.makedirs(os.path.dirname(self.legacy))
        T.make_legacy(self.legacy, 25)
        time.sleep(1.1)
        self.v3 = self.pipe("v3")
        self.free = self.pipe("brain-free")
        self.other = os.path.join(self.t, "altra-chiave.txt")
        T.keygen(self.other)
        self.repos = self.clone_all()

    def tearDown(self):
        self.case.tearDown()

    def pipe(self, mode, recipient=None):
        c = self.case
        cmd = [sys.executable, "-I", T.PIPE, "--mode", mode, "--runs-root", self.runs, "--legacy-db", self.legacy,
               "--work", os.path.join(self.t, "w-%s" % mode), "--remote", c.remote, "--recipient-file", recipient or c.recfile,
               "--expect-recipients-sha256", T.pin(recipient or c.recfile),
               "--tools", HERE, "--push-wait", "0", "--attempt-wait", "0"]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout

    def clone_all(self, skip=()):
        base = os.path.join(self.t, "repos-%d" % time.time_ns())
        for b in ("main", "brain-v3", "brain-free"):
            if b not in skip:
                T.sh("git", "clone", "-q", "--branch", b, self.case.remote, os.path.join(base, b))
        return base

    def verify(self, identity=None, repos=None, rc84=None, env=None, pinned=ROOT, extra=()):
        work = os.path.join(self.t, "work-%d" % time.time_ns())
        summary = os.path.join(self.t, "summary.md")
        if os.path.exists(summary):
            os.unlink(summary)
        cmd = [sys.executable, "-I", VERIFY, "--identity", identity or self.case.ident, "--repos-dir", repos or self.repos,
               "--pinned", pinned, "--work", work, "--summary", summary]
        if rc84 is not None:
            cmd += ["--rc84", rc84]
        cmd += list(extra)
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env=env)
        return p, work, (read(summary) if os.path.exists(summary) else "")

    def assert_only_fixed_sentences(self, text):
        for line in text.splitlines():
            self.assertRegex(line, ALLOWED, "riga non ammessa nel log: %r" % line)

    @unittest.skipUnless(HAVE_RC84, "SKIP: serve SUPERBOT_RC84_SRC per il confronto con il codice RC84")
    def test_matching_key_restores_the_three_latest_archives_with_rc84(self):
        before = T.slurp(self.case.ident)
        p, work, summary = self.verify(rc84=T.RC84)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        out = p.stdout
        self.assertIn("ESITO chiave privata leggibile e valida: OK", out)
        self.assertEqual(out.count("ESITO destinatario del piu' recente = questa chiave: OK"), 3)
        self.assertEqual(out.count("- ripristino isolato completo: OK"), 3)
        self.assertEqual(out.count("ESITO ripristino: OK"), 3)
        self.assertIn("- codice RC84 fissato: accetta la run ripristinata", out)
        self.assertIn("- catena hash del journal e identita' unica: OK", out)
        self.assertIn("- integrita' e misura del database storico: OK", out)
        self.assertIn("- coerenza semantica del primo portafoglio classico: OK", out)
        self.assertIn("run Brain V3 ripristinate e verificate: 1", out)
        self.assertRegex(out.split("## Brain Free storico")[1], r"archivio piu' recente: \S+ \(in \d+ parti\)|archivio piu' recente: \S+\n")
        self.assertIn("ESITO COMPLESSIVO: OK", out)
        self.assertEqual(summary.strip(), out.strip().replace("\r", ""))
        self.assert_only_fixed_sentences(out)
        self.assertEqual(os.listdir(work), [], "restano file decifrati o log")
        self.assertEqual(T.slurp(self.case.ident), before)

    def test_attestation_lines_contain_only_names_and_hashes_and_only_for_confirmed_families(self):
        extra = ("--run-id", "42685000001", "--workflow-sha256", "a" * 64, "--script-sha256", "b" * 64, "--pinned-sha", PINNED_SHA)
        p, work, summary = self.verify(rc84=T.RC84 or "", extra=extra)
        certs = [json.loads(l[len("CERTIFICATO "):]) for l in p.stdout.splitlines() if l.startswith("CERTIFICATO ")]
        families = sorted(c["famiglia"] for c in certs)
        self.assertEqual(families, ["brain-free", "classico", "v3"] if T.HAVE_RC84 else ["brain-free", "classico"])
        for c in certs:
            self.assertEqual(sorted(c), ["archivio", "archivio_sha256", "controllo_rc84", "eseguito_su", "esito", "famiglia", "origine",
                                         "pinned_sha", "run_id", "schema", "script_sha256", "workflow_sha256"])
            self.assertEqual((c["esito"], c["origine"], c["eseguito_su"], c["run_id"]), ("OK", "github-actions", "github-actions", "42685000001"))
            self.assertRegex(c["archivio_sha256"], r"^[0-9a-f]{64}$")
        by = {c["famiglia"]: c for c in certs}
        self.assertEqual(by["classico"]["controllo_rc84"], "non eseguito")
        if T.HAVE_RC84:
            self.assertEqual(by["v3"]["controllo_rc84"], "eseguito")
        self.assert_only_fixed_sentences(p.stdout)
        # senza gli argomenti dell'attestazione non si emette nulla
        p, _w, _ = self.verify(rc84=T.RC84 or "")
        self.assertNotIn("CERTIFICATO", p.stdout)

    def test_without_rc84_the_v3_family_is_honestly_not_confirmed(self):
        p, work, _ = self.verify()
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertIn("ESITO COMPLESSIVO: PARZIALE", p.stdout)
        self.assertIn("codice RC84 fissato: NON CONFERMATO", p.stdout)
        self.assertIn("ESITO ripristino: NO", p.stdout)
        self.assertEqual(p.stdout.count("ESITO ripristino: OK"), 2)
        self.assert_only_fixed_sentences(p.stdout)
        self.assertEqual(os.listdir(work), [])

    def test_non_matching_key_decrypts_nothing_and_says_so(self):
        shim = os.path.join(self.t, "shim")
        os.makedirs(shim)
        log = os.path.join(self.t, "age-calls.log")
        real = shutil.which("age")
        T.spit(os.path.join(shim, "age"), '#!/bin/sh\necho "$@" >> %s\nexec %s "$@"\n' % (log, real))
        os.chmod(os.path.join(shim, "age"), 0o755)
        env = dict(os.environ, PATH=shim + os.pathsep + os.environ["PATH"])
        p, work, _ = self.verify(identity=self.other, rc84=T.RC84 or "", env=env)
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertEqual(p.stdout.count("ESITO destinatario del piu' recente = questa chiave: NO"), 3)
        self.assertIn("nessun tentativo", p.stdout)
        self.assertIn("ESITO COMPLESSIVO: NO", p.stdout)
        self.assertFalse(os.path.exists(log), "age e' stato invocato per decifrare con la chiave sbagliata")
        self.assertEqual(os.listdir(work), [])
        self.assert_only_fixed_sentences(p.stdout)

    def test_unreadable_or_invalid_key_is_reported_as_no_without_details(self):
        bad = os.path.join(self.t, "non-una-chiave.txt")
        T.spit(bad, "questo non e' una chiave %s\n" % MARKER)
        p, work, _ = self.verify(identity=bad)
        self.assertEqual(p.returncode, 2)
        self.assertIn("ESITO chiave privata leggibile e valida: NO", p.stdout)
        self.assertNotIn(MARKER, p.stdout + p.stderr)
        p, _w, _ = self.verify(identity=os.path.join(self.t, "non-esiste.txt"))
        self.assertEqual(p.returncode, 2)

    def test_key_material_and_recipient_never_appear_in_any_output_or_leftover_file(self):
        ident = os.path.join(self.t, "chiave-con-commenti.txt")
        body = T.slurp(self.case.ident).decode()
        T.spit(ident, "# %s\n%s" % (MARKER, body))
        secret = [l for l in body.splitlines() if l.startswith("AGE-SECRET-KEY")][0]
        pub = self.case.pub
        p, work, summary = self.verify(identity=ident, rc84=T.RC84 or "")
        for blob in (p.stdout, p.stderr, summary):
            for needle in (MARKER, secret, pub, "AGE-SECRET-KEY", "age1"):
                self.assertNotIn(needle, blob)
        for dp, _dn, fn in os.walk(work):
            for f in fn:
                self.assertNotIn(secret.encode(), T.slurp(os.path.join(dp, f)))

    def test_no_portfolio_numbers_or_names_leak_into_the_log(self):
        p, work, summary = self.verify(rc84=T.RC84 or "")
        text = p.stdout + summary
        for needle in ("hawk", "bull", "cassa", "capitale", "equity", "pnl", "realized", "eventi", "trade", "BTCUSDT",
                       T.SECRET, "saldo", "net"):
            self.assertNotIn(needle, text.lower() if needle.islower() else text)
        self.assertNotRegex(text, r"\d+\.\d+")                       # nessun importo decimale

    def test_latest_archive_for_another_recipient_is_reported_even_if_older_ones_match(self):
        time.sleep(1.1)
        # nuovo archivio V3 cifrato per un ALTRO destinatario: il piu' recente non e' piu' apribile con la chiave di prova
        other_pub = T.sh("age-keygen", "-y", self.other).stdout.strip()
        rec = os.path.join(self.t, "rec-altro.txt")
        T.spit(rec, "# altro\n%s\n" % other_pub)
        cmd = [sys.executable, "-I", T.PIPE, "--mode", "v3", "--runs-root", self.runs, "--work", os.path.join(self.t, "w-v3b"),
               "--remote", self.case.remote, "--recipient-file", rec, "--expect-recipients-sha256", T.pin(rec),
               "--tools", HERE, "--push-wait", "0", "--attempt-wait", "0", "--force"]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        repos = self.clone_all()
        p, work, _ = self.verify(repos=repos, rc84=T.RC84 or "")
        sec = p.stdout.split("## Brain V3")[1].split("## Brain Free")[0]
        self.assertIn("archivi nel ramo: 2 | cifrati per questa chiave: 1 | altro destinatario: 1", sec)
        self.assertIn("ESITO destinatario del piu' recente = questa chiave: NO", sec)
        self.assertIn("ESITO COMPLESSIVO: PARZIALE", p.stdout)

    def test_missing_branch_or_tampered_archive_is_a_no_not_a_crash(self):
        repos = self.clone_all(skip=("brain-free",))
        p, work, _ = self.verify(repos=repos, rc84=T.RC84 or "")
        self.assertIn("ramo non disponibile in questo runner", p.stdout)
        self.assertEqual(p.returncode, 2)
        # archivio piu' recente di Falco/Toro alterato di un bit: il ripristino fallisce senza dettagli
        repos = self.clone_all()
        arc = sorted(os.path.join(dp, f) for dp, _d, fn in os.walk(os.path.join(repos, "main", "archives")) for f in fn if f.endswith(".tar.gz.age"))[-1]
        data = bytearray(T.slurp(arc))
        data[len(data) // 2] ^= 1
        T.spit(arc, bytes(data))
        subprocess.run(["git", "-C", os.path.join(repos, "main"), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "alterato"], check=True)
        p, work, _ = self.verify(repos=repos, rc84=T.RC84 or "")
        sec = p.stdout.split("## Falco/Toro")[1].split("## Brain V3")[0]
        self.assertIn("ESITO ripristino: NO", sec)
        self.assertNotIn("Traceback", p.stdout + p.stderr)
        self.assert_only_fixed_sentences(p.stdout)
        self.assertEqual(os.listdir(work), [])

    def test_restore_output_with_details_is_never_printed_even_on_failure(self):
        repos = self.clone_all()
        arc = sorted(os.path.join(dp, f) for dp, _d, fn in os.walk(os.path.join(repos, "brain-v3")) for f in fn if f.endswith(".tar.gz.age"))[-1]
        T.spit(arc, T.slurp(arc)[:-5])
        subprocess.run(["git", "-C", os.path.join(repos, "brain-v3"), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "troncato"], check=True)
        p, work, _ = self.verify(repos=repos, rc84=T.RC84 or "")
        self.assertNotIn("ERRORE", p.stdout)
        self.assertNotIn("RIPRISTINO DI PROVA", p.stdout)
        self.assert_only_fixed_sentences(p.stdout)


KEYCHECK_WORKFLOW = os.path.join(ROOT, ".github", "workflows", "age-v2-key-check.yml")
KEYCHECK = os.path.join(ROOT, "deploy", "extbackup", "age-v2-recovery", "check_key.py")
DOC_COMMIT = "e51cf721196bdd52bce39b925a3b7521e64e141a"


class KeyCheckWorkflowStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(KEYCHECK_WORKFLOW)
        cls.steps = steps_of(cls.text)

    def test_no_actions_no_server_no_private_repository_no_artifacts(self):
        self.assertNotRegex(self.text, r"(?m)^\s*-?\s*uses:")
        for word in ("upload-artifact", "actions/cache", "SINGAPORE", "SSH_PRIVATE_KEY", "51.79.205.82", "root@", "scp ", "docker ",
                     "superbot-backups", "BACKUPS_READ_KEY", "git@github.com", "ssh "):
            self.assertNotIn(word, self.text)

    def test_triggers_permissions_and_environment(self):
        on = self.text.split("\npermissions:")[0]
        block = on.split("\non:\n")[1]
        self.assertEqual(re.findall(r"(?m)^  ([a-z_]+):", block), ["workflow_dispatch", "push"])
        for forbidden in ("pull_request", "schedule", "workflow_run", "issue_comment", "repository_dispatch"):
            self.assertNotIn(forbidden, on)
        self.assertIn("branches: [work/age-v2-keycheck-run-20261110]", on)
        self.assertRegex(self.text, r"(?m)^permissions:\n  contents: read\n")
        self.assertIn("environment: age-recovery", self.text)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "deploy", "extbackup", "age-v2-recovery", "KEYCHECK.trigger")))

    def test_exactly_one_secret_in_exactly_one_step_and_the_program_step_has_none(self):
        self.assertEqual(sorted(set(re.findall(r"secrets\.([A-Za-z0-9_]+)", self.text))), ["SUPERBOT_AGE_RECOVERY_KEY_V2"])
        self.assertEqual(len(re.findall(r"secrets\.", self.text)), 1)
        self.assertNotIn("secrets.", self.text.split("    steps:")[0])
        prog = [b for n, b in self.steps.items() if n.startswith("Confronto")][0]
        self.assertNotIn("AGE_RECOVERY_KEY_V2", prog)
        for line in self.text.splitlines():
            if "$AGE_RECOVERY_KEY_V2" in line:
                self.assertTrue(line.strip().startswith('test -n "$AGE_RECOVERY_KEY_V2"')
                                or line.strip() == "printf '%s\\n' \"$AGE_RECOVERY_KEY_V2\" > \"$RUNNER_TEMP/age-v2-identity\"", line)
        for bad in ("set -x", "xtrace", "printenv", "base64", "env | ", "cat \"$RUNNER_TEMP/age"):
            self.assertNotIn(bad, self.text)

    def test_documented_recipient_is_pinned_to_the_23_october_commit_and_still_among_the_recipients(self):
        self.assertIn("DOC_SHA: " + DOC_COMMIT, self.text)
        self.assertRegex(self.text, r"DOC_RECIPIENT_SHA256: [0-9a-f]{64}")
        doc_sha = re.search(r"DOC_RECIPIENT_SHA256: ([0-9a-f]{64})", self.text).group(1)
        if subprocess.run(["git", "-C", ROOT, "cat-file", "-e", DOC_COMMIT + "^{commit}"], capture_output=True).returncode != 0:
            self.skipTest("SKIP: il commit del 23/10 non e' nella copia locale del repository")
        blob = subprocess.run(["git", "-C", ROOT, "show", "%s:deploy/extbackup/recipient-v2.txt" % DOC_COMMIT], capture_output=True, check=True).stdout
        self.assertEqual(hashlib.sha256(blob).hexdigest(), doc_sha)
        documented = [l for l in blob.decode().splitlines() if l and not l.startswith("#")]
        current = read(RECIPIENT_V2).splitlines()
        for k in documented:
            self.assertIn(k, current, "il destinatario documentato il 23/10 non e' piu' tra i destinatari V2")

    def test_the_documented_key_guard_in_the_workflow_behaves_as_intended(self):
        guard = ("while read -r K; do\n"
                 "  grep -qxF \"$K\" \"$WF/$R\" || { echo BLOCCO; exit 1; }\n"
                 "done < <(grep -v '^#' \"$DOC/$R\" | grep -v '^$')\n")
        self.assertIn("grep -qxF \"$K\" \"$RUNNER_TEMP/wf/$R\"", self.text)
        self.assertIn("done < <(grep -v '^#' \"$RUNNER_TEMP/doc/$R\" | grep -v '^$')", self.text)
        with tempfile.TemporaryDirectory() as td:
            for d in ("wf", "doc"):
                os.makedirs(os.path.join(td, d))
            doc, wf = "# documentato\nage1" + "a" * 58 + "\n", "# documentato\nage1" + "a" * 58 + "\n# personale\nage1" + "b" * 58 + "\n"
            T.spit(os.path.join(td, "doc", "r.txt"), doc)
            env = dict(os.environ, WF=os.path.join(td, "wf"), DOC=os.path.join(td, "doc"), R="r.txt")
            T.spit(os.path.join(td, "wf", "r.txt"), wf)
            self.assertEqual(subprocess.run(["bash", "-c", guard], env=env, capture_output=True).returncode, 0)        # V2 + personale: ok
            T.spit(os.path.join(td, "wf", "r.txt"), "age1" + "b" * 58 + "\n")
            self.assertEqual(subprocess.run(["bash", "-c", guard], env=env, capture_output=True).returncode, 1)        # V2 tolta: blocco

    def test_approval_precedes_the_secret_and_formula_matches_documentation(self):
        names = list(self.steps)
        self.assertEqual(len(names), 4)
        self.assertNotIn("secrets.", self.steps[names[0]])
        self.assertIn("BLOCCO: impronta di approvazione", self.steps[names[0]])
        self.assertIn("if: always()", self.steps[names[-1]])
        self.assertIn("printf '%s\\n%s\\n' \"$WF\" \"$SC\" | sha256sum | cut -d' ' -f1", self.text)
        self.assertEqual(sorted(re.findall(r"\$\{\{\s*([^}]+?)\s*\}\}", self.text)),
                         ["github.event.inputs.approval", "secrets.SUPERBOT_AGE_RECOVERY_KEY_V2"])


KC_ALLOWED = re.compile(r"^(# .*|ESITO [^\n]*: (OK|NO)( \(non eseguita: la chiave non coincide\))?|ESITO COMPLESSIVO: (OK|NO)"
                        r"|La chiave V2 nel Secret appartiene alla coppia documentata: puo' decifrare gli archivi cifrati per quel destinatario\.)?$")


@unittest.skipUnless(HAVE_AGE, "mancano age/age-keygen/git")
class KeyCheckRunTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        t = self.td.name
        self.good, self.other = os.path.join(t, "good"), os.path.join(t, "other")
        self.pub_good, self.pub_other = T.keygen(self.good), T.keygen(self.other)
        self.rec = os.path.join(t, "doc-recipient.txt")
        T.spit(self.rec, "# destinatario documentato (prova)\n%s\n" % self.pub_good)

    def tearDown(self):
        self.td.cleanup()

    def run_check(self, identity, rec=None, env=None):
        work = os.path.join(self.td.name, "work")
        summary = os.path.join(self.td.name, "summary.md")
        p = subprocess.run([sys.executable, "-I", KEYCHECK, "--identity", identity, "--recipients", rec or self.rec, "--work", work,
                            "--summary", summary], capture_output=True, text=True, timeout=120, env=env)
        return p, work, (read(summary) if os.path.exists(summary) else "")

    def test_matching_pair_is_confirmed_and_proved_by_a_real_roundtrip(self):
        before = T.slurp(self.good)
        p, work, summary = self.run_check(self.good)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        for line in ("ESITO chiave privata leggibile e valida: OK",
                     "ESITO la chiave pubblica derivata coincide con il destinatario V2 documentato il 23 ottobre: OK",
                     "ESITO prova di cifratura e decifratura con la coppia: OK", "ESITO COMPLESSIVO: OK"):
            self.assertIn(line, p.stdout)
        self.assertEqual(summary.strip(), p.stdout.strip())
        for l in p.stdout.splitlines():
            self.assertRegex(l, KC_ALLOWED)
        self.assertFalse(os.path.exists(work), "restano file di prova")
        self.assertEqual(T.slurp(self.good), before)

    def test_a_different_pair_is_rejected_without_running_the_roundtrip(self):
        shim = os.path.join(self.td.name, "shim")
        os.makedirs(shim)
        log = os.path.join(self.td.name, "age.log")
        T.spit(os.path.join(shim, "age"), '#!/bin/sh\necho "$@" >> %s\nexec %s "$@"\n' % (log, shutil.which("age")))
        os.chmod(os.path.join(shim, "age"), 0o755)
        p, work, _ = self.run_check(self.other, env=dict(os.environ, PATH=shim + os.pathsep + os.environ["PATH"]))
        self.assertEqual(p.returncode, 2)
        self.assertIn("coincide con il destinatario V2 documentato il 23 ottobre: NO", p.stdout)
        self.assertIn("non eseguita", p.stdout)
        self.assertIn("ESITO COMPLESSIVO: NO", p.stdout)
        self.assertFalse(os.path.exists(log), "age e' stato invocato nonostante la chiave non coincida")
        for l in p.stdout.splitlines():
            self.assertRegex(l, KC_ALLOWED)

    def test_invalid_or_missing_key_is_a_no(self):
        bad = os.path.join(self.td.name, "bad")
        T.spit(bad, "non e' una chiave %s\n" % MARKER)
        for ident in (bad, os.path.join(self.td.name, "non-esiste")):
            p, _w, _s = self.run_check(ident)
            self.assertEqual(p.returncode, 2)
            self.assertIn("ESITO chiave privata leggibile e valida: NO", p.stdout)
            self.assertNotIn(MARKER, p.stdout + p.stderr)

    def test_nothing_secret_or_public_is_ever_printed(self):
        ident = os.path.join(self.td.name, "con-commenti")
        body = T.slurp(self.good).decode()
        T.spit(ident, "# %s\n%s" % (MARKER, body))
        secret = [l for l in body.splitlines() if l.startswith("AGE-SECRET-KEY")][0]
        p, work, summary = self.run_check(ident)
        for blob in (p.stdout, p.stderr, summary):
            for needle in (MARKER, secret, self.pub_good, self.pub_other, "age1", "AGE-SECRET-KEY"):
                self.assertNotIn(needle, blob)

    def test_the_program_never_opens_the_private_key_file(self):
        src = read(KEYCHECK)
        self.assertNotRegex(src, r"open\([^)]*identity")
        self.assertNotIn("os.environ", src)
        self.assertNotIn("getenv", src)

    def test_documented_recipient_file_with_several_keys_matches_any_of_them(self):
        T.spit(self.rec, "%s\n%s\n" % (self.pub_other, self.pub_good))
        self.assertEqual(self.run_check(self.good)[0].returncode, 0)

    def test_the_real_documented_recipient_is_a_valid_public_key_file(self):
        keys = [l for l in read(RECIPIENT_V2).splitlines() if l and not l.startswith("#")]
        self.assertEqual(len(keys), 1)
        self.assertRegex(keys[0], r"^age1[0-9a-z]{58}$")


if __name__ == "__main__":
    unittest.main()
