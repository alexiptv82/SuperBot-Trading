"""Prove dell'UPGRADE V1 -> V2 di un Brain V3 gia' installato (installatore: comandi `upgrade` e `upgrade-rollback`).

Si lanciano con:  python3 -m unittest deploy/scripts/test_age_upgrade.py -v
Tutto sintetico: la versione "precedente" e' composta da file finti le cui impronte vengono passate all'installatore con la tabella di
prova (SUPERBOT_INSTALLER_PREVIOUS_TABLE, accettata solo con --allow-nonroot); systemctl e' finto; nessun Secret, nessuna rete, nessuna VPS.
La tabella VERA delle consegne note e' controllata a parte contro i commit pubblicati.
"""
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "deploy", "extbackup", "brain-v3"))
import test_brain_v3_backup as T                                  # noqa: E402
import install_brain_v3_extension as INST                         # noqa: E402

UNITS = ("superbot-extbackup-v3.service", "superbot-extbackup-v3.timer")


def h(text):
    return hashlib.sha256(text.encode()).hexdigest()


def content_state(root):
    """percorso -> (modo, dimensione, sha256) dei file: ignora gli orari (un ripristino li cambia)."""
    out = {}
    for dp, dn, fn in os.walk(root):
        for n in sorted(dn + fn):
            full = os.path.join(dp, n)
            rel = os.path.relpath(full, root)
            if os.path.islink(full):
                out[rel] = ("link", os.readlink(full))
            elif os.path.isdir(full):
                out[rel] = ("dir",)
            else:
                out[rel] = (os.stat(full).st_mode & 0o777, os.path.getsize(full), T.sha(T.slurp(full)))
    return out


@unittest.skipUnless(T.HAVE_AGE, "mancano age/git")
class UpgradeBase(T.InstallerBase):
    profile_args = ()

    def setUp(self):
        super().setUp()
        t = self.td.name
        self.wrap = os.path.join(t, "extbackup-v3")                    # wrapper V1 + dati V1 (restano dove sono)
        self.data = os.path.join(self.v2, "brain")                     # dati V2: cartella SEPARATA
        shutil.copyfile(os.path.join(ROOT, "deploy", "extbackup", "recipient.txt"), os.path.join(self.classic, "recipient.txt"))   # il V1 vero
        self.old = {}
        for lab in ("vA", "vB"):
            self.old[lab] = {
                "brain_v3_snapshot.py": "#!/usr/bin/env python3\n# snapshot precedente %s\n" % lab,
                "external_backup_brain_v3.py": "#!/usr/bin/env python3\n# backup V3 precedente (destinatario V1) %s\n" % lab,
                "run-v3.sh": "#!/bin/sh\n# wrapper precedente (repository V1) %s\n" % lab,
                "superbot-extbackup-v3.service": "[Service]\n# unita' precedente %s\n" % lab,
                "superbot-extbackup-v3.timer": "[Timer]\n# timer precedente %s\n" % lab}
        self.table_path = os.path.join(t, "previous-table.json")
        T.spit(self.table_path, json.dumps({lab: {"descrizione": "versione finta " + lab, "file": {n: h(c) for n, c in files.items()}}
                                            for lab, files in self.old.items()}))

    use_test_table = True

    def env(self, **extra):
        if not self.use_test_table:
            return super().env(**extra)
        return super().env(SUPERBOT_INSTALLER_PREVIOUS_TABLE=self.table_path, **extra)

    def inst_args(self, *args, host="vps-singapore"):
        return [sys.executable, T.INSTALLER, *args, "--profile", "v3", "--tools-dir", self.tools, "--work-dir", self.wrap,
                "--data-dir", self.data, "--proc-dir", self.proc, "--classic-dir", self.classic, "--systemd-dir", self.systemd,
                "--state-dir", self.state, "--v2-dir", self.v2, "--ssh-key", self.key, "--allow-nonroot", "--host-name", host]

    # ---- la situazione di partenza: Brain V3 installato in versione V1, con i suoi dati ----
    def targets(self):
        return {"brain_v3_snapshot.py": os.path.join(self.tools, "brain_v3_snapshot.py"),
                "external_backup_brain_v3.py": os.path.join(self.tools, "external_backup_brain_v3.py"),
                "run-v3.sh": os.path.join(self.wrap, "run-v3.sh"),
                "superbot-extbackup-v3.service": os.path.join(self.systemd, UNITS[0]),
                "superbot-extbackup-v3.timer": os.path.join(self.systemd, UNITS[1])}

    def install_old(self, label="vA", units=False, register=True):
        os.makedirs(self.wrap)
        listed = []
        for n, path in self.targets().items():
            if n in UNITS and not units:
                continue
            content = self.old[label][n]
            with open(path, "wb") as f:
                f.write(content if isinstance(content, bytes) else content.encode())
            os.chmod(path, 0o644 if n in UNITS else 0o700)
            listed.append({"path": path, "sha256": hashlib.sha256(content if isinstance(content, bytes) else content.encode()).hexdigest(),
                           "mode": 0o644 if n in UNITS else 0o700})
        if register:
            os.makedirs(self.state)
            T.spit(os.path.join(self.state, "INSTALL-MANIFEST.json"), json.dumps({
                "creato": "2026-11-10T10:00:00Z", "stato": "completo", "file": listed, "cartella_di_lavoro_creata": True,
                "work_dir": self.wrap}, indent=1))
        # i dati V1 prodotti dai backup gia' fatti: archivi pubblicati verso V1, stato, clone, lock
        for sub in ("v3", "brain-free"):
            os.makedirs(os.path.join(self.wrap, sub, "repo", "brain-v3"))
            T.spit(os.path.join(self.wrap, sub, "status.json"), json.dumps({"ultimo_successo": "2026-11-10T03:50:00Z", "archivio": "a-%s.age" % sub}))
            T.spit(os.path.join(self.wrap, sub, "repo", "brain-v3", "a-%s.age" % sub), "cifrato per V1 " + sub)
            T.spit(os.path.join(self.wrap, sub, ".lock"), "")
        T.spit(os.path.join(self.wrap, "timer-gate.json"), "{}")

    def reset_old(self):
        """Toglie tutto cio' che lascia un'installazione V1 (e un upgrade) ma NON gli strumenti classici di appoggio."""
        for d in (self.wrap, self.systemd, self.state, self.v2):
            shutil.rmtree(d, ignore_errors=True)
        for n in ("brain_v3_snapshot.py", "external_backup_brain_v3.py", "age_recipients.py"):
            if os.path.lexists(os.path.join(self.tools, n)):
                os.unlink(os.path.join(self.tools, n))
        os.makedirs(self.systemd)
        for f in (self.sc_state, self.sc_log):
            if os.path.exists(f):
                os.unlink(f)

    def world(self):
        out = {}
        for name, d in (("tools", self.tools), ("wrap", self.wrap), ("systemd", self.systemd), ("state", self.state),
                        ("v2", self.v2), ("classic", self.classic)):
            if os.path.isdir(d):
                for k, v in T.tree_state(d).items():
                    out[os.path.join(name, k)] = v
        return out

    def content_world(self, skip_upgrades=True):
        out = {}
        for name, d in (("tools", self.tools), ("wrap", self.wrap), ("systemd", self.systemd), ("state", self.state),
                        ("v2", self.v2), ("classic", self.classic)):
            if os.path.isdir(d):
                for k, v in content_state(d).items():
                    if skip_upgrades and k.split(os.sep)[0].startswith("upgrade-") and name == "state":
                        continue
                    out[os.path.join(name, k)] = v
        return out

    def v1_data(self):
        return {k: v for k, v in T.tree_state(self.wrap).items() if k.split(os.sep)[0] in ("v3", "brain-free", "timer-gate.json")}

    def approval_up(self):
        rc, out = self.run_inst("upgrade")
        self.assertEqual(rc, 0, out)
        return [l.split()[-1] for l in out.splitlines() if "IMPRONTA DI APPROVAZIONE" in l][0]

    def do_upgrade(self, *extra, **env):
        return self.run_inst("upgrade", "--apply", "--approve", self.approval_up(), *extra, **env)

    def journals(self):
        return sorted(d for d in os.listdir(self.state) if d.startswith("upgrade-"))

    def hold_lock(self, path):
        code = "import fcntl,sys,time\nf=open(sys.argv[1],'rb')\nfcntl.flock(f,fcntl.LOCK_EX)\nprint('pronto',flush=True)\ntime.sleep(60)\n"
        p = subprocess.Popen([sys.executable, "-c", code, path], stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (p.kill(), p.wait(timeout=30), p.stdout.close()))
        self.assertEqual(p.stdout.readline().strip(), "pronto")

    def fake_process(self, *argv):
        d = os.path.join(self.proc, "4242")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "cmdline"), "wb") as f:
            f.write(b"\0".join(a.encode() for a in argv) + b"\0")


class UpgradeTests(UpgradeBase):
    # ---- simulazione e approvazione ----
    def test_simulation_changes_nothing_and_prints_the_approval(self):
        self.install_old()
        before = self.world()
        rc, out = self.run_inst("upgrade")
        self.assertEqual(rc, 0, out)
        self.assertIn("SIMULAZIONE RIUSCITA", out)
        self.assertIn("versione precedente riconosciuta: versione finta vA", out)
        self.assertIn("IMPRONTA DI APPROVAZIONE", out)
        self.assertEqual(self.world(), before)
        self.assertEqual(self.mutating_calls(), [])

    def test_apply_needs_the_exact_approval(self):
        self.install_old()
        before = self.world()
        for args in (("--apply",), ("--apply", "--approve", "0" * 64)):
            rc, out = self.run_inst("upgrade", *args)
            self.assertEqual(rc, 1, out)
        self.assertEqual(self.world(), before)

    # ---- l'upgrade riuscito ----
    def test_upgrade_replaces_only_what_it_must_and_keeps_every_v1_datum(self):
        self.install_old()
        T.spit(os.path.join(self.wrap, "appunti-dell-utente.txt"), "non toccare")
        v1, classic_before, before_files = self.v1_data(), self.classic_state(), {k: v for k, v in self.world().items() if "appunti" in k}
        old_reg = T.slurp(os.path.join(self.state, "INSTALL-MANIFEST.json"))
        old_files = {n: T.slurp(p) for n, p in self.targets().items() if os.path.exists(p)}
        rc, out = self.do_upgrade()
        self.assertEqual(rc, 0, out)
        self.assertIn("AGGIORNATO", out)
        # i file ora sono quelli del repository, con i permessi giusti
        for dest, src, mode in INST.plan(self.args_ns()):
            self.assertEqual(T.slurp(dest), T.slurp(src), dest)
            self.assertEqual(oct(os.stat(dest).st_mode & 0o777), oct(mode))
        # dati, archivi e stati V1: identici anche negli orari
        self.assertEqual(self.v1_data(), v1)
        self.assertEqual({k: v for k, v in self.world().items() if "appunti" in k}, before_files)
        self.assertEqual(self.classic_state(), classic_before)
        # copie verificate e registro precedente conservati
        (jd,) = self.journals()
        for n, content in old_files.items():
            self.assertEqual(T.slurp(os.path.join(self.state, jd, "old", n)), content)
        self.assertEqual(T.slurp(os.path.join(self.state, jd, "old", "INSTALL-MANIFEST.json")), old_reg)
        j = T.jload(os.path.join(self.state, jd, "UPGRADE.json"))
        self.assertEqual(j["stato"], "completo")
        self.assertEqual(j["da"], "vA")
        # nuovo registro nel formato V2, con il rimando all'upgrade
        reg = T.jload(os.path.join(self.state, "INSTALL-MANIFEST.json"))
        self.assertEqual((reg["stato"], reg["profilo"], reg["upgrade"]["da"]), ("completo", "v3", "vA"))
        self.assertEqual(reg["aside"], self.data)
        self.assertTrue(all(INST.sha(c["path"]) == c["sha256"] for c in reg["file"]))
        # niente di attivato, nessuna dato V2 creato, nessun residuo
        self.assertEqual(self.mutating_calls(), [])
        self.assertEqual(self.sc(), {"enabled": [], "active": []})
        self.assertFalse(os.path.exists(self.data))
        self.assertEqual([n for d in (self.tools, self.wrap, self.v2) for n in os.listdir(d) if ".new." in n], [])
        # secondo giro: niente da fare
        rc, out = self.run_inst("upgrade")
        self.assertEqual(rc, 0, out)
        self.assertIn("GIA' AGGIORNATO", out)
        self.assertEqual(len(self.journals()), 1)

    def args_ns(self):
        class A:
            pass
        a = A()
        a.profile, a.work_dir, a.data_dir, a.v2_dir, a.tools_dir, a.systemd_dir, a.with_timer = (
            "v3", self.wrap, self.data, self.v2, self.tools, self.systemd, False)
        return a

    def test_each_known_version_is_recognised_and_units_are_replaced_without_touching_systemd(self):
        for label in ("vA", "vB"):
            with self.subTest(versione=label):
                self.reset_old()
                self.install_old(label, units=True)
                rc, out = self.do_upgrade()
                self.assertEqual(rc, 0, out)
                for n in UNITS:
                    self.assertEqual(T.slurp(os.path.join(self.systemd, n)), T.slurp(os.path.join(ROOT, "deploy", "extbackup", "brain-v3", n)))
                self.assertEqual(self.mutating_calls(), [])
                self.assertEqual(self.sc(), {"enabled": [], "active": []})
                jd = self.journals()[-1]
                self.assertEqual(T.jload(os.path.join(self.state, jd, "UPGRADE.json"))["da"], label)

    def test_after_the_upgrade_the_v1_status_cannot_satisfy_the_timer_gate(self):
        self.install_old()
        self.assertEqual(self.do_upgrade()[0], 0)
        rc, out = self.run_inst("status")
        self.assertIn("cancello del timer: NON soddisfatto", out)
        self.assertIn("nessun status.json", out)
        self.assertIn("versione di Brain V3 installata: V2", out)

    # ---- versioni sconosciute, file imprevisti ----
    def test_unknown_or_modified_or_mixed_versions_block_and_change_nothing(self):
        cases = {
            "file modificato": lambda: T.spit(self.targets()["run-v3.sh"], "#!/bin/sh\necho modificato\n"),
            "script diverso": lambda: T.spit(self.targets()["external_backup_brain_v3.py"], "# ignoto\n"),
            "versioni miste": lambda: T.spit(self.targets()["brain_v3_snapshot.py"], self.old["vB"]["brain_v3_snapshot.py"]),
            "file mancante": lambda: os.unlink(self.targets()["brain_v3_snapshot.py"]),
            "collegamento": lambda: (os.unlink(self.targets()["run-v3.sh"]), os.symlink("/bin/sh", self.targets()["run-v3.sh"])),
        }
        for name, mutate in cases.items():
            with self.subTest(caso=name):
                self.reset_old()
                self.install_old("vA")
                mutate()
                before = self.world()
                rc, out = self.run_inst("upgrade", "--apply", "--approve", "0" * 64)
                self.assertEqual(rc, 1, out)
                self.assertIn("VERSIONE SCONOSCIUTA", out)
                self.assertEqual(self.world(), before)
                rc, out = self.run_inst("status")
                self.assertIn("SCONOSCIUTA", out)

    def test_register_problems_block(self):
        cases = {
            "registro assente": lambda reg: os.unlink(reg),
            "installazione interrotta": lambda reg: self.patch_register(reg, stato="in_corso"),
            "file imprevisto elencato": lambda reg: self.patch_register(reg, extra={"path": "/etc/passwd", "sha256": "0" * 64, "mode": 420}),
            "impronta diversa": lambda reg: self.patch_register(reg, bad_sha=True),
            "gia' formato V2": lambda reg: self.patch_register(reg, profilo="v3"),
        }
        for name, mutate in cases.items():
            with self.subTest(caso=name):
                self.reset_old()
                self.install_old("vA")
                mutate(os.path.join(self.state, "INSTALL-MANIFEST.json"))
                before = self.world()
                rc, out = self.run_inst("upgrade", "--apply", "--approve", "0" * 64)
                self.assertEqual(rc, 1, out)
                self.assertEqual(self.world(), before)
                self.assertIn("BLOCCO", out)

    def patch_register(self, reg, stato=None, extra=None, bad_sha=False, profilo=None):
        r = T.jload(reg)
        if stato:
            r["stato"] = stato
        if extra:
            r["file"].append(extra)
        if bad_sha:
            r["file"][0]["sha256"] = "1" * 64
        if profilo:
            r["profilo"] = profilo
        T.spit(reg, json.dumps(r))

    def test_nothing_to_upgrade_without_a_previous_installation(self):
        rc, out = self.run_inst("upgrade")
        self.assertEqual(rc, 1)
        self.assertIn("nessuna installazione precedente", out)

    def test_plain_install_points_to_upgrade_instead_of_overwriting(self):
        self.install_old()
        before = self.world()
        rc, out = self.run_inst("install", "--apply", "--approve", self.approval())
        self.assertEqual(rc, 1, out)
        self.assertIn("usare il comando upgrade", out)
        self.assertEqual(self.world(), before)

    def test_new_files_that_already_exist_with_other_content_block(self):
        self.install_old()
        os.makedirs(self.v2)
        T.spit(os.path.join(self.v2, "recipients.txt"), "age1" + "z" * 58 + "\n")
        before = self.world()
        rc, out = self.run_inst("upgrade")
        self.assertEqual(rc, 1, out)
        self.assertIn("non lo sovrascrivo", out)
        self.assertEqual(self.world(), before)

    def test_missing_v2_prerequisites_block_before_any_change(self):
        self.install_old()
        os.unlink(self.key)
        before = self.world()
        rc, out = self.run_inst("upgrade")
        self.assertEqual(rc, 1, out)
        self.assertIn("chiave di deploy V2", out)
        self.assertEqual(self.world(), before)

    def test_only_the_v3_profile_can_be_upgraded(self):
        p = subprocess.run(self.inst_args("upgrade") + ["--profile", "classic"], capture_output=True, text=True, env=self.env())
        self.assertEqual(p.returncode, 1)
        self.assertIn("solo il profilo v3", p.stdout)

    # ---- backup in corso, timer attivo ----
    def test_a_running_backup_blocks_upgrade_and_rollback(self):
        self.install_old()
        before = self.world()
        scenarios = {
            "servizio V1 di Falco/Toro": dict(env={"FAKE_SC_CLASSIC": "active"}),
            "servizio Brain V3": dict(env={"FAKE_SC_V3_SERVICE": "active"}),
            "lock del dato V1": dict(lock=os.path.join(self.wrap, "v3", ".lock")),
            "lock di Brain Free V1": dict(lock=os.path.join(self.wrap, "brain-free", ".lock")),
            "processo di backup": dict(proc=("/usr/bin/python3", "-I", "/opt/superbot-tools/external_backup_brain_v3.py", "--mode", "v3")),
            "wrapper in esecuzione": dict(proc=("/bin/sh", "/opt/superbot-extbackup-v3/run-v3.sh", "--mode", "brain-free")),
            "backup classico": dict(proc=("/bin/sh", "/opt/superbot-extbackup/run.sh")),
        }
        for name, sc in scenarios.items():
            with self.subTest(scenario=name):
                if os.path.isdir(self.proc):
                    shutil.rmtree(self.proc)
                os.makedirs(self.proc)
                if "lock" in sc:
                    self.hold_lock(sc["lock"])
                if "proc" in sc:
                    self.fake_process(*sc["proc"])
                before = self.world()
                rc, out = self.run_inst("upgrade", "--apply", "--approve", "0" * 64, **sc.get("env", {}))
                self.assertEqual(rc, 1, out)
                self.assertRegex(out, "in corso|in esecuzione")
                self.assertEqual(self.world(), before, out)
                self.assertEqual(self.journals(), [])
        os.makedirs(self.proc, exist_ok=True)

    def test_an_unrelated_process_does_not_block(self):
        self.install_old()
        self.fake_process("/usr/bin/python3", "-m", "unittest", "test_external_backup.py")   # nome simile, programma diverso
        rc, out = self.run_inst("upgrade")
        self.assertEqual(rc, 0, out)

    def test_an_active_or_enabled_timer_blocks(self):
        for state in ({"enabled": [UNITS[1]], "active": []}, {"enabled": [], "active": [UNITS[1]]}):
            with self.subTest(stato=state):
                self.reset_old()
                self.install_old(units=True)
                T.spit(self.sc_state, json.dumps(state))
                before = self.world()
                rc, out = self.run_inst("upgrade")
                self.assertEqual(rc, 1, out)
                self.assertIn("disattivarlo prima", out)
                self.assertEqual(self.world(), before)

    def test_the_locks_are_held_during_the_upgrade(self):
        self.install_old()
        proc = subprocess.Popen(self.inst_args("upgrade", "--apply", "--approve", self.approval_up()), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, env=self.env(SUPERBOT_INSTALLER_FAULT="put1:sleep"))
        self.addCleanup(lambda: (proc.kill(), proc.wait(timeout=30), proc.stdout.close()))
        end = time.time() + 60
        while time.time() < end and not (os.path.isfile(self.targets()["brain_v3_snapshot.py"])
                                         and T.slurp(self.targets()["brain_v3_snapshot.py"]) == T.slurp(os.path.join(HERE, "brain_v3_snapshot.py"))):
            time.sleep(0.05)
        import fcntl
        for lock in (os.path.join(self.wrap, "v3", ".lock"), os.path.join(self.wrap, "brain-free", ".lock")):
            fd = os.open(lock, os.O_RDONLY)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)      # un backup manuale che parte adesso si rifiuta
            finally:
                os.close(fd)
        proc.terminate()
        proc.communicate(timeout=60)

    # ---- interruzioni ----
    def test_a_failure_at_any_step_restores_the_previous_version_by_itself(self):
        for point in ("put1", "put2", "put3", "create1", "create2", "before-register", "before-complete"):
            with self.subTest(punto=point):
                self.reset_old()
                self.install_old()
                before, v1 = self.content_world(), self.v1_data()
                rc, out = self.do_upgrade(SUPERBOT_INSTALLER_FAULT=point + ":raise")
                self.assertEqual(rc, 1, out)
                self.assertIn("upgrade interrotto", out)
                self.assertIn("versione precedente ripristinata e verificata", out)
                self.assertEqual(self.content_world(), before)
                self.assertEqual(self.v1_data(), v1)
                (jd,) = self.journals()
                self.assertEqual(T.jload(os.path.join(self.state, jd, "UPGRADE.json"))["stato"], "annullato")
                self.assertEqual(self.mutating_calls(), [])
                shutil.rmtree(os.path.join(self.state, jd))
                self.assertEqual(self.run_inst("upgrade")[0], 0)            # e si puo' riprovare

    def test_sigkill_at_any_step_is_recovered_by_upgrade_rollback(self):
        for point in ("put1", "put2", "put3", "create1", "before-register", "before-complete"):
            with self.subTest(punto=point):
                self.reset_old()
                self.install_old()
                before, v1 = self.content_world(), self.v1_data()
                p = subprocess.run(self.inst_args("upgrade", "--apply", "--approve", self.approval_up()), capture_output=True, text=True,
                                   env=self.env(SUPERBOT_INSTALLER_FAULT=point + ":kill"))
                self.assertEqual(p.returncode, -9)
                (jd,) = self.journals()
                self.assertEqual(T.jload(os.path.join(self.state, jd, "UPGRADE.json"))["stato"], "in_corso")
                rc, out = self.run_inst("status")
                self.assertIn("interrotto: eseguire upgrade-rollback --apply", out)
                rc, out = self.run_inst("upgrade")
                self.assertEqual(rc, 1, out)
                self.assertIn("eseguire prima upgrade-rollback", out)
                rc, out = self.run_inst("upgrade-rollback")
                self.assertEqual(rc, 0, out)
                self.assertIn("SIMULAZIONE", out)
                rc, out = self.run_inst("upgrade-rollback", "--apply")
                self.assertEqual(rc, 0, out)
                self.assertIn("VERSIONE PRECEDENTE RIPRISTINATA", out)
                self.assertEqual(self.content_world(), before)
                self.assertEqual(self.v1_data(), v1)
                self.assertEqual(T.jload(os.path.join(self.state, jd, "UPGRADE.json"))["stato"], "annullato")
                self.assertEqual(self.mutating_calls(), [])

    def test_sigterm_restores_by_itself(self):
        self.install_old()
        before = self.content_world()
        proc = subprocess.Popen(self.inst_args("upgrade", "--apply", "--approve", self.approval_up()), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, env=self.env(SUPERBOT_INSTALLER_FAULT="put2:sleep"))
        self.addCleanup(lambda: (proc.kill(), proc.wait(timeout=30), proc.stdout.close()))
        end = time.time() + 60
        while time.time() < end and T.slurp(self.targets()["external_backup_brain_v3.py"]) != T.slurp(os.path.join(HERE, "external_backup_brain_v3.py")):
            time.sleep(0.05)
        proc.terminate()
        out, _ = proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, 143, out)
        self.assertIn("ESITO: FALLITO", out)
        self.assertEqual(self.content_world(), before)

    def test_rollback_also_removes_temp_files_left_by_an_interrupted_write(self):
        self.install_old()
        before = self.content_world()
        p = subprocess.run(self.inst_args("upgrade", "--apply", "--approve", self.approval_up()), capture_output=True, text=True,
                           env=self.env(SUPERBOT_INSTALLER_FAULT="put2:kill"))
        self.assertEqual(p.returncode, -9)
        T.spit(os.path.join(self.wrap, ".run-v3.sh.new.999"), "residuo")
        self.assertEqual(self.run_inst("upgrade-rollback", "--apply")[0], 0)
        self.assertEqual(self.content_world(), before)

    # ---- rollback dopo un upgrade riuscito ----
    def test_rollback_after_a_completed_upgrade_returns_exactly_to_the_previous_state(self):
        self.install_old(units=True)
        before, v1 = self.content_world(), self.v1_data()
        self.assertEqual(self.do_upgrade()[0], 0)
        self.assertNotEqual(self.content_world(), before)
        rc, out = self.run_inst("upgrade-rollback", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.content_world(), before)
        self.assertEqual(self.v1_data(), v1)
        self.assertFalse(os.path.exists(self.v2))
        self.assertEqual(self.mutating_calls(), [])
        rc, out = self.run_inst("upgrade-rollback", "--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("nessun upgrade da annullare", out)
        # e si puo' ripetere l'upgrade
        self.assertEqual(self.do_upgrade()[0], 0)

    def test_rollback_never_overwrites_a_file_changed_after_the_upgrade(self):
        self.install_old()
        self.assertEqual(self.do_upgrade()[0], 0)
        run = self.targets()["run-v3.sh"]
        T.spit(run, "#!/bin/sh\n# modificato a mano dopo l'upgrade\n")
        rc, out = self.run_inst("upgrade-rollback", "--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("contenuto imprevisto", out)
        self.assertIn("modificato a mano", T.slurp(run).decode())
        self.assertEqual(T.slurp(self.targets()["external_backup_brain_v3.py"]).decode(), self.old["vA"]["external_backup_brain_v3.py"])

    def test_rollback_refuses_a_corrupted_backup_copy(self):
        self.install_old()
        self.assertEqual(self.do_upgrade()[0], 0)
        (jd,) = self.journals()
        T.spit(os.path.join(self.state, jd, "old", "run-v3.sh"), "copia danneggiata")
        new_wrapper = T.slurp(self.targets()["run-v3.sh"])
        rc, out = self.run_inst("upgrade-rollback", "--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("copia verificata di run-v3.sh non e' integra", out)
        self.assertEqual(T.slurp(self.targets()["run-v3.sh"]), new_wrapper)

    def test_rollback_is_blocked_by_a_running_backup_or_active_timer(self):
        self.install_old(units=True)
        self.assertEqual(self.do_upgrade()[0], 0)
        before = self.content_world()
        rc, out = self.run_inst("upgrade-rollback", "--apply", FAKE_SC_V3_SERVICE="active")
        self.assertEqual(rc, 1, out)
        T.spit(self.sc_state, json.dumps({"enabled": [UNITS[1]], "active": []}))
        rc, out = self.run_inst("upgrade-rollback", "--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("disattivarlo prima", out)
        self.assertEqual(self.content_world(), before)

    def test_the_ordinary_rollback_refuses_old_and_upgraded_registers(self):
        self.install_old()
        rc, out = self.run_inst("rollback", "--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("formato V1", out)
        self.assertEqual(self.do_upgrade()[0], 0)
        before = self.content_world()
        rc, out = self.run_inst("rollback", "--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("upgrade-rollback", out)
        self.assertEqual(self.content_world(), before)

    def test_after_the_upgrade_the_normal_installation_flow_continues_to_work(self):
        self.install_old()
        self.assertEqual(self.do_upgrade()[0], 0)
        rc, out = self.run_inst("install", "--apply", "--approve", self.approval())
        self.assertEqual(rc, 0, out)
        self.assertIn("GIA' INSTALLATO", out)

    # ---- la tabella vera ----
    def test_the_real_table_matches_the_published_commits(self):
        names = {"brain_v3_snapshot.py": "deploy/scripts/brain_v3_snapshot.py", "external_backup_brain_v3.py": "deploy/scripts/external_backup_brain_v3.py",
                 "run-v3.sh": "deploy/extbackup/brain-v3/run-v3.sh", "superbot-extbackup-v3.service": "deploy/extbackup/brain-v3/superbot-extbackup-v3.service",
                 "superbot-extbackup-v3.timer": "deploy/extbackup/brain-v3/superbot-extbackup-v3.timer"}
        self.assertEqual(sorted(INST.PREVIOUS_VERSIONS), ["7b2aabe", "e2b84b0"])
        checked = 0
        for label, v in INST.PREVIOUS_VERSIONS.items():
            self.assertEqual(sorted(v["file"]), sorted(names))
            for n, digest in v["file"].items():
                self.assertRegex(digest, r"^[0-9a-f]{64}$")
                r = subprocess.run(["git", "-C", ROOT, "show", "%s:%s" % (label, names[n])], capture_output=True)
                if r.returncode == 0:                                  # con la cronologia completa si controlla davvero
                    self.assertEqual(hashlib.sha256(r.stdout).hexdigest(), digest, "%s @ %s" % (n, label))
                    checked += 1
        self.assertIn(checked, (0, 10))                                # o tutte le righe verificabili o nessuna (clone parziale)
        self.assertNotIn("v1_old", INST.PREVIOUS_VERSIONS)
        # la versione nuova NON e' tra le precedenti: nessuna ambiguita'
        for v in INST.PREVIOUS_VERSIONS.values():
            self.assertNotEqual(v["file"]["external_backup_brain_v3.py"], INST.sha(os.path.join(HERE, "external_backup_brain_v3.py")))
            self.assertNotEqual(v["file"]["run-v3.sh"], INST.sha(os.path.join(ROOT, "deploy/extbackup/brain-v3/run-v3.sh")))

    def test_the_test_table_seam_is_ignored_without_the_test_flag(self):
        self.install_old()
        cmd = [a for a in self.inst_args("upgrade") if a != "--allow-nonroot"]
        p = subprocess.run(cmd, capture_output=True, text=True, env=self.env())
        self.assertEqual(p.returncode, 1)
        self.assertNotIn("versione finta", p.stdout)


class RealHistoryUpgradeTests(UpgradeBase):
    """Nessuna tabella di prova: i file V1 veri, presi dai commit pubblicati, sono riconosciuti e aggiornati con la tabella VERA."""
    use_test_table = False
    PATHS = {"brain_v3_snapshot.py": "deploy/scripts/brain_v3_snapshot.py", "external_backup_brain_v3.py": "deploy/scripts/external_backup_brain_v3.py",
             "run-v3.sh": "deploy/extbackup/brain-v3/run-v3.sh", "superbot-extbackup-v3.service": "deploy/extbackup/brain-v3/superbot-extbackup-v3.service",
             "superbot-extbackup-v3.timer": "deploy/extbackup/brain-v3/superbot-extbackup-v3.timer"}

    def setUp(self):
        super().setUp()
        self.real = {}
        for label in ("e2b84b0", "7b2aabe"):
            files = {}
            for n, path in self.PATHS.items():
                r = subprocess.run(["git", "-C", ROOT, "show", "%s:%s" % (label, path)], capture_output=True)
                if r.returncode != 0:
                    files = None
                    break
                files[n] = r.stdout
            if files:
                self.real[label] = files
        self.old = self.real

    def test_the_real_published_versions_are_recognised_and_upgraded(self):
        # con la cronologia completa si provano entrambe le consegne vere; in un clone parziale la prova riguarda quel che c'e'
        # (e si dichiara quante sono: un clone senza cronologia non puo' contare come prova)
        self.assertIn(len(self.real), (0, 2), "cronologia parziale: %s" % sorted(self.real))
        for label in self.real:
            with self.subTest(consegna=label):
                self.reset_old()
                self.install_old(label, units=True)
                rc, out = self.run_inst("status")
                self.assertIn("PRECEDENTE V1", out)
                before_v1 = self.v1_data()
                rc, out = self.do_upgrade()
                self.assertEqual(rc, 0, out)
                self.assertEqual(self.v1_data(), before_v1)
                self.assertEqual(self.mutating_calls(), [])
                for n, path in self.targets().items():
                    self.assertEqual(T.slurp(path), T.slurp(os.path.join(ROOT, self.PATHS[n])), n)
                self.assertEqual(self.run_inst("upgrade-rollback", "--apply")[0], 0)
                for n, path in self.targets().items():
                    self.assertEqual(T.slurp(path), self.real[label][n], n)

    def test_a_single_changed_byte_in_a_real_file_blocks(self):
        for label in self.real:
            with self.subTest(consegna=label):
                self.reset_old()
                self.install_old(label)
                path = self.targets()["external_backup_brain_v3.py"]
                T.spit(path, T.slurp(path).decode() + "\n")
                before = self.world()
                rc, out = self.run_inst("upgrade")
                self.assertEqual(rc, 1, out)
                self.assertIn("VERSIONE SCONOSCIUTA", out)
                self.assertEqual(self.world(), before)


class ExecStopPostTests(unittest.TestCase):
    """La pulizia dopo un arresto brusco non deve toccare i file temporanei di un backup MANUALE concorrente."""
    UNITS = {"brain-v3": ("deploy/extbackup/brain-v3/superbot-extbackup-v3.service", "brain/v3",
                         ("staging", "scratch", "staging.tar.gz", "superbot-brainv3-1.tar.gz.age", "superbot-brainv3-1.tar.gz.age.part1")),
             "classico": ("deploy/extbackup/v2/superbot-extbackup-v2.service", "work",
                          ("staging", "staging.tar.gz", "superbot-backup-1.tar.gz.age"))}

    def setUp(self):
        self.td = __import__("tempfile").TemporaryDirectory()
        self.addCleanup(self.td.cleanup)

    def command(self, unit):
        text = T.slurp(os.path.join(ROOT, self.UNITS[unit][0])).decode()
        (line,) = [l for l in text.splitlines() if l.startswith("ExecStopPost=")]
        self.assertTrue(line.startswith("ExecStopPost=-/usr/bin/flock -n "), line)
        return line[len("ExecStopPost=-"):].replace("/opt/superbot-extbackup-v2", self.td.name).replace("/usr/bin/flock", shutil.which("flock"))

    def populate(self, unit):
        base = os.path.join(self.td.name, self.UNITS[unit][1])
        os.makedirs(base)
        for n in self.UNITS[unit][2]:
            if n in ("staging", "scratch"):
                os.makedirs(os.path.join(base, n))
                T.spit(os.path.join(base, n, "dato.txt"), "testo in chiaro del backup manuale")
            else:
                T.spit(os.path.join(base, n), "temporaneo")
        for keep in ("status.json", "repo/archivio.age"):
            os.makedirs(os.path.dirname(os.path.join(base, keep)), exist_ok=True)
            T.spit(os.path.join(base, keep), "da non toccare")
        return base

    def test_cleanup_removes_only_our_temp_files_when_no_backup_holds_the_lock(self):
        for unit in self.UNITS:
            with self.subTest(unita=unit):
                shutil.rmtree(self.td.name + "/brain", ignore_errors=True)
                shutil.rmtree(self.td.name + "/work", ignore_errors=True)
                base = self.populate(unit)
                p = subprocess.run(["sh", "-c", self.command(unit)], capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(sorted(n for n in os.listdir(base) if n not in (".lock",)), ["repo", "status.json"])
                self.assertEqual(T.slurp(os.path.join(base, "repo", "archivio.age")), b"da non toccare")

    def test_cleanup_does_nothing_while_a_manual_backup_holds_the_lock(self):
        for unit in self.UNITS:
            with self.subTest(unita=unit):
                shutil.rmtree(self.td.name + "/brain", ignore_errors=True)
                shutil.rmtree(self.td.name + "/work", ignore_errors=True)
                base = self.populate(unit)
                before = content_state(base)
                lock = os.path.join(base, ".lock")
                code = "import fcntl,sys,time\nf=open(sys.argv[1],'a+')\nfcntl.flock(f,fcntl.LOCK_EX)\nprint('pronto',flush=True)\ntime.sleep(60)\n"
                holder = subprocess.Popen([sys.executable, "-c", code, lock], stdout=subprocess.PIPE, text=True)
                try:
                    self.assertEqual(holder.stdout.readline().strip(), "pronto")
                    before = content_state(base)
                    p = subprocess.run(["sh", "-c", self.command(unit)], capture_output=True, text=True)
                    self.assertNotEqual(p.returncode, 0)               # flock -n non ottiene il lock: la pulizia non parte
                    self.assertEqual(content_state(base), before)      # nessun file del backup manuale e' stato toccato
                finally:
                    holder.kill()
                    holder.wait(timeout=30)
                    holder.stdout.close()

    def test_cleanup_with_a_missing_folder_is_harmless_and_a_missing_flock_cannot_delete_anything(self):
        for unit in self.UNITS:
            p = subprocess.run(["sh", "-c", self.command(unit)], capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)                        # niente cartella: nulla da pulire (systemd ignora l'esito per il "-")
        base = self.populate("brain-v3")
        before = content_state(base)
        cmd = self.command("brain-v3").replace(shutil.which("flock"), "/nonexistent/flock")
        subprocess.run(["sh", "-c", cmd], capture_output=True, text=True)
        self.assertEqual(content_state(base), before)

    def test_the_units_have_no_unguarded_cleanup(self):
        for rel, _b, _n in self.UNITS.values():
            text = T.slurp(os.path.join(ROOT, rel)).decode()
            for l in text.splitlines():
                if l.startswith("ExecStopPost="):
                    self.assertIn("flock -n", l)
                    self.assertNotIn("ExecStopPost=/bin/sh", l)


class SecretsPlanDocsTests(unittest.TestCase):
    """Il piano dei Secrets distingue le cose e non dichiara protetto cio' che non lo e'."""
    DOC = os.path.join(ROOT, "deploy", "extbackup", "age-v2-migration", "SEGRETI-E-PROTEZIONI.md")

    def text(self, rel):
        """Testo con gli a-capo dei commenti ('# ') e dei paragrafi ridotti a spazi: le frasi non dipendono da dove vanno a capo."""
        import re
        return re.sub(r"\s*\n(#|\s)*\s*", " ", T.slurp(os.path.join(ROOT, rel)).decode()) if rel.endswith((".yml", ".md")) else T.slurp(os.path.join(ROOT, rel)).decode()

    def test_the_plan_separates_repository_secrets_environment_secrets_reviewers_and_branch_protection(self):
        t = self.text("deploy/extbackup/age-v2-migration/SEGRETI-E-PROTEZIONI.md")
        self.assertIn("NON è protetto dall'ambiente", t)
        for term in ("Secret di repository", "Secret di ambiente", "Required reviewers", "Deployment branches",
                     "Protezione dei rami", "workflow_dispatch", "sul ramo predefinito", "Non sposto i workflow sensibili su `main`",
                     "si **sostituisce**", "cancella", "non si può leggere", "Prevent self-review"):
            self.assertIn(term, t, term)
        self.assertNotRegex(t, r"(?i)(?<!non )\b(e'|è|risulta|sara') protetto dall'ambiente")
        self.assertNotIn("AGE-SECRET-KEY-1", t)

    def test_every_document_that_mentions_the_environment_warns_about_repository_secrets(self):
        for rel in (".github/workflows/age-v2-key-check.yml", ".github/workflows/age-v2-recovery-verify.yml"):
            t = self.text(rel)
            self.assertIn("Secret di REPOSITORY", t, rel)
            self.assertIn("SEGRETI-E-PROTEZIONI.md", t, rel)
            self.assertIn("workflow_dispatch funziona solo se questo file e' sul ramo predefinito", t, rel)
        for rel in ("deploy/extbackup/age-v2-migration/LEGGIMI.md", "deploy/extbackup/age-v2-recovery/LEGGIMI.md"):
            self.assertIn("SEGRETI-E-PROTEZIONI.md", self.text(rel), rel)

    def test_sensitive_workflows_were_not_moved_to_the_default_branch_or_given_new_triggers(self):
        for rel in (".github/workflows/age-v2-key-check.yml", ".github/workflows/age-v2-recovery-verify.yml"):
            on = T.slurp(os.path.join(ROOT, rel)).decode().split("\npermissions:")[0].split("\non:\n")[1]
            self.assertEqual(sorted(__import__("re").findall(r"(?m)^  ([a-z_]+):", on)), ["push", "workflow_dispatch"], rel)
            self.assertNotIn("main", on, rel)
        for rel in ("deploy/extbackup/age-v2-recovery/RUN.trigger", "deploy/extbackup/age-v2-recovery/KEYCHECK.trigger"):
            self.assertFalse(os.path.exists(os.path.join(ROOT, rel)), "un file trigger avvierebbe un job che legge Secrets: " + rel)

    def test_no_private_key_material_in_the_deliverables(self):
        import re
        pat = re.compile(r"AGE-SECRET-KEY-1[0-9A-Z]{40,}")
        for base in ("deploy/extbackup", ".github/workflows"):
            for dp, _dn, fn in os.walk(os.path.join(ROOT, base)):
                for f in fn:
                    if f.endswith((".md", ".py", ".sh", ".yml", ".txt", ".service", ".timer")):
                        self.assertIsNone(pat.search(T.slurp(os.path.join(dp, f)).decode("utf-8", "replace")), os.path.join(dp, f))


if __name__ == "__main__":
    unittest.main()
