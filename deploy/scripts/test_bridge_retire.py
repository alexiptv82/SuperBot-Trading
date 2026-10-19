"""Prove di bridge_retire.py (ritiro del ponte superbot-desk-api e della chiave del tunnel).

Si lanciano con:  python3 -m unittest deploy/scripts/test_bridge_retire.py -v
Niente server: docker, curl e ss sono FINTI (scrivono lo stato in una cartella temporanea e un registro dei
comandi); authorized_keys e' un file temporaneo con chiavi vere generate sul momento (blob in formato OpenSSH reale, senza bisogno di ssh-keygen).
Si controlla che il ritiro tocchi SOLO quello che deve, che si fermi se qualcosa non torna, che il controllo
finale sappia fallire e che il ripristino rimetta tutto com'era.
"""
import base64
import hashlib
import json
import os
import stat
import struct
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "bridge_retire.py")

FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, sys
S = os.environ["FAKE_STATE"]
D = os.path.join(S, "containers")
with open(os.path.join(S, "docker.log"), "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
def path(n): return os.path.join(D, n + ".json")
def load(n):
    with open(path(n)) as f: return json.load(f)
def save(n, c):
    with open(path(n), "w") as f: json.dump(c, f)
a = sys.argv[1:]
if a[0] == "inspect":
    if not os.path.exists(path(a[1])): print("Error: No such object: " + a[1]); sys.exit(1)
    print(json.dumps([load(a[1])]))
elif a[:2] == ["ps", "-a"]:
    print("\n".join(sorted(f[:-5] for f in os.listdir(D))))
elif a[0] == "update":
    n = a[2]; c = load(n); c["HostConfig"]["RestartPolicy"]["Name"] = a[1].split("=", 1)[1]; save(n, c)
elif a[0] == "stop":
    n = a[-1]; c = load(n); c["State"]["Running"] = False; save(n, c)
    if os.path.exists(os.path.join(S, "break_app_on_stop")): open(os.path.join(S, "app_down"), "w").close()
    if os.path.exists(os.path.join(S, "restart_hawk_on_stop")):
        h = load("superbot-desk-hawk"); h["RestartCount"] += 1; save("superbot-desk-hawk", h)
elif a[0] == "rename":
    c = load(a[1]); c["Name"] = "/" + a[2]; os.remove(path(a[1])); save(a[2], c)
elif a[0] == "start":
    c = load(a[1]); c["State"]["Running"] = True; save(a[1], c)
elif a[0] == "rm":
    n = a[-1]; os.remove(path(n))
else:
    sys.exit(0)
'''
FAKE_CURL = r'''#!/bin/sh
[ -e "$FAKE_STATE/app_down" ] && exit 22
exit 0
'''
FAKE_SS = r'''#!/usr/bin/env python3
import json, os
S = os.environ["FAKE_STATE"]
p = os.path.join(S, "containers", "superbot-desk-api.json")
print("State  Recv-Q Send-Q Local Address:Port Peer Address:Port")
print("LISTEN 0 4096 0.0.0.0:22 0.0.0.0:*")
if os.path.exists(p) and json.load(open(p))["State"]["Running"]:
    print("LISTEN 0 4096 127.0.0.1:18002 0.0.0.0:*")
'''


def container(name, running=True, policy="unless-stopped"):
    return {"Id": "id-" + name, "Name": "/" + name, "RestartCount": 0,
            "State": {"Running": running, "StartedAt": "2026-10-19T04:09:59Z", "Health": {"Status": "healthy"}},
            "HostConfig": {"RestartPolicy": {"Name": policy}}, "Config": {"Image": "img-" + name},
            "NetworkSettings": {"Ports": {"8001/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18002"}]}},
            "Mounts": [{"Source": "/opt/superbot-desk-data/hawk", "Destination": "/opt/superbot-desk-data/hawk", "RW": True}]}


def keygen(comment):
    """Riga pubblica ssh-ed25519 con un blob nel formato di OpenSSH (tipo + 32 byte casuali)."""
    blob = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + os.urandom(32)
    return "ssh-ed25519 %s %s" % (base64.b64encode(blob).decode(), comment)


def fp_of(pub_line):
    raw = base64.b64decode(pub_line.split()[1])
    return "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")


class BridgeRetireTests(unittest.TestCase):
    TUNNEL_OPTS = ('from="51.91.109.45",restrict,port-forwarding,permitopen="127.0.0.1:18002",'
                   'permitlisten="127.0.0.1:18002",command="/bin/false"')

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        t = self.td.name
        self.state = os.path.join(t, "state")
        os.makedirs(os.path.join(self.state, "containers"))
        for n in ("superbot", "superbot-desk-hawk", "superbot-desk-bull", "superbot-pool", "superbot-desk-api"):
            self.put_container(container(n, policy="always" if n == "superbot" else "unless-stopped"))
        self.put_container(container("superbot-desk-api-retained-r39119231791a1", running=False, policy="no"))
        bind = os.path.join(t, "bin")
        os.makedirs(bind)
        for name, body in (("docker", FAKE_DOCKER), ("curl", FAKE_CURL), ("ss", FAKE_SS)):
            p = os.path.join(bind, name)
            with open(p, "w") as f:
                f.write(body)
            os.chmod(p, 0o755)
        self.env = dict(os.environ, PATH=bind + ":" + os.environ["PATH"], FAKE_STATE=self.state)
        # authorized_keys con chiavi vere: amministratore, tunnel, una riga "quasi" tunnel (altra porta)
        self.admin = keygen("admin-sg")
        self.tunnel = keygen("superbot-app-link-tunnel")
        self.decoy = keygen("altra-chiave-limitata")
        self.auth = os.path.join(t, "authorized_keys")
        self.write_auth([self.admin, self.TUNNEL_OPTS + " " + self.tunnel,
                         'from="1.2.3.4",restrict,permitopen="127.0.0.1:9999",command="/bin/false" ' + self.decoy])
        os.chmod(self.auth, 0o600)
        self.root_auth = os.path.join(t, "root_authorized_keys")
        with open(self.root_auth, "w") as f:
            f.write(self.admin + "\n")
        self.ext = os.path.join(t, "status.json")
        self.set_ext(True)
        self.bk = os.path.join(t, "backups")
        os.makedirs(self.bk)
        self.tfp = fp_of(self.tunnel)
        self.dfp = fp_of(self.decoy)

    def tearDown(self):
        self.td.cleanup()

    def write_auth(self, lines):
        with open(self.auth, "w") as f:
            f.write("\n".join(lines) + "\n")

    def put_container(self, c):
        with open(os.path.join(self.state, "containers", c["Name"][1:] + ".json"), "w") as f:
            json.dump(c, f)

    def get_container(self, name):
        p = os.path.join(self.state, "containers", name + ".json")
        if not os.path.exists(p):
            return None
        with open(p) as f:
            return json.load(f)

    def set_ext(self, good=True, age_h=1.0, error=None):
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - age_h * 3600))
        body = {"ultimo_successo": ts, "archivio": "superbot-backup-x.tar.gz.age", "sha256": "a" * 64,
                "ultimo_errore": error} if good else {"ultimo_errore": "boom"}
        with open(self.ext, "w") as f:
            json.dump(body, f)

    def run_cmd(self, cmd, *extra):
        p = subprocess.run([sys.executable, "-I", SCRIPT, cmd, "--auth", self.auth, "--root-auth", self.root_auth,
                            "--ext-status", self.ext, "--backup-root", self.bk, *extra],
                           capture_output=True, text=True, env=self.env, timeout=120)
        return p.returncode, p.stdout + p.stderr

    def retire(self, fp=None):
        return self.run_cmd("retire", "--fingerprint", fp or self.tfp)

    def docker_log(self):
        with open(os.path.join(self.state, "docker.log")) as f:
            return f.read()

    def auth_text(self):
        with open(self.auth) as f:
            return f.read()

    # ---- controllo iniziale ----

    def test_check_finds_exactly_the_tunnel_line_and_is_read_only(self):
        before = self.auth_text()
        rc, out = self.run_cmd("check")
        self.assertEqual(rc, 0, out)
        self.assertIn("righe che sembrano la chiave del tunnel: 1 -> impronta " + self.tfp, out)
        self.assertIn("pronto per il ritiro", out)
        lines = {l.split("|")[0].strip(): l for l in out.splitlines() if l.startswith("  riga ")}
        self.assertNotIn("TUNNEL", lines["riga 1"])
        self.assertIn("TUNNEL", lines["riga 2"])
        self.assertNotIn("TUNNEL", lines["riga 3"])             # la "quasi-tunnel" (altra porta) non e' marcata
        self.assertEqual(self.auth_text(), before)
        verbs = {l.split()[0] for l in self.docker_log().splitlines()}
        self.assertTrue(verbs <= {"inspect", "ps"}, verbs)       # sola lettura: nessun stop/rename/update/start/rm
        self.assertTrue(self.get_container("superbot-desk-api")["State"]["Running"])
        self.assertEqual(os.listdir(self.bk), [])

    def test_fingerprint_matches_openssh_known_vector(self):
        sys.path.insert(0, HERE)
        try:
            import importlib
            mod = importlib.import_module("bridge_retire")
        finally:
            sys.path.pop(0)
        # chiave host ed25519 pubblica di github.com e la sua impronta ufficiale
        blob = "AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
        self.assertEqual(mod.fingerprint("ssh-ed25519", blob), "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU")
        self.assertEqual(mod.fingerprint("ssh-ed25519", "non base64 !!"), "?")

    def test_check_says_not_ready_without_external_backup(self):
        self.set_ext(False)
        rc, out = self.run_cmd("check")
        self.assertEqual(rc, 0, out)
        self.assertIn("NON ancora pronto", out)

    def test_check_does_not_leak_comments_or_addresses_of_other_keys(self):
        self.write_auth([self.admin.replace("admin-sg", "mario.rossi@example.com"),
                         self.TUNNEL_OPTS + " " + self.tunnel,
                         'from="203.0.113.77",command="/usr/local/bin/backup.sh --segreto",no-pty ' + self.decoy])
        rc, out = self.run_cmd("check")
        self.assertEqual(rc, 0, out)
        for leak in ("mario.rossi", "example.com", "203.0.113.77", "backup.sh", "--segreto"):
            self.assertNotIn(leak, out)
        self.assertIn("from,command,no-pty", out)                # il nome delle opzioni si', i valori no
        self.assertIn('permitopen="127.0.0.1:18002"', out)       # la riga del tunnel e' nostra: si mostra intera

    def test_check_never_prints_private_material_or_env(self):
        rc, out = self.run_cmd("check")
        self.assertNotIn("PRIVATE KEY", out)
        self.assertNotIn("Env", out)
        self.assertNotIn(self.tunnel.split()[1], out)          # il blob della chiave non viene stampato

    # ---- ritiro: percorso felice ----

    def test_retire_removes_only_the_tunnel_key_and_retires_the_container_reversibly(self):
        before = self.auth_text().split("\n")
        mode = stat.S_IMODE(os.stat(self.auth).st_mode)
        rc, out = self.retire()
        self.assertEqual(rc, 0, out)
        self.assertIn("RISULTATO: OK", out)
        after = self.auth_text().split("\n")
        self.assertEqual(after, [l for l in before if self.tunnel.split()[1] not in l])       # tolta solo quella riga
        self.assertIn(self.admin, self.auth_text())
        self.assertIn(self.decoy, self.auth_text())                                          # la quasi-tunnel resta
        self.assertEqual(stat.S_IMODE(os.stat(self.auth).st_mode), mode)
        # container: fermo, senza riavvio automatico, rinominato (non cancellato), nessun "docker rm"
        self.assertIsNone(self.get_container("superbot-desk-api"))
        (ret,) = [f[:-5] for f in os.listdir(os.path.join(self.state, "containers")) if "-retired-" in f]
        c = self.get_container(ret)
        self.assertFalse(c["State"]["Running"])
        self.assertEqual(c["HostConfig"]["RestartPolicy"]["Name"], "no")
        self.assertNotIn("rm", {l.split()[0] for l in self.docker_log().splitlines()})
        # il container di rollback non e' stato nemmeno nominato nei comandi
        self.assertNotIn("retained", self.docker_log())
        self.assertEqual(self.get_container("superbot-desk-api-retained-r39119231791a1")["State"]["Running"], False)
        # copia di sicurezza
        (d,) = os.listdir(self.bk)
        with open(os.path.join(self.bk, d, "authorized_keys.before")) as f:
            self.assertEqual(f.read().split("\n"), before)
        with open(os.path.join(self.bk, d, "removed-line.txt")) as f:
            self.assertIn(self.tunnel.split()[1], f.read())
        # bot e app non toccati
        for n in ("superbot", "superbot-desk-hawk", "superbot-desk-bull", "superbot-pool"):
            self.assertEqual(self.get_container(n)["RestartCount"], 0)
            self.assertTrue(self.get_container(n)["State"]["Running"])
            self.assertNotIn("stop %s" % n, self.docker_log())

    def test_nothing_in_the_script_can_delete_data_or_touch_hitv(self):
        with open(SCRIPT) as f:
            src = f.read()
        for bad in ("rmtree", "os.remove", "os.unlink", "unlink(", '"rm"', '"rmi"', '"prune"', "hitv", "hi-tv\""):
            self.assertNotIn(bad, src.lower() if bad.islower() else src)

    # ---- ritiro: rifiuti ----

    def test_retire_refuses_without_a_verified_recent_external_backup(self):
        before = self.auth_text()
        for case in ("missing", "failed", "old", "error"):
            with self.subTest(case=case):
                if case == "missing":
                    os.remove(self.ext)
                elif case == "failed":
                    self.set_ext(False)
                elif case == "old":
                    self.set_ext(True, age_h=100)
                else:
                    self.set_ext(True, error="push rifiutato")
                rc, out = self.retire()
                self.assertEqual(rc, 1, out)
                self.assertIn("backup esterno", out)
                self.assertEqual(self.auth_text(), before)
                self.assertTrue(self.get_container("superbot-desk-api")["State"]["Running"])
                self.assertEqual(os.listdir(self.bk), [])

    def test_retire_refuses_wrong_or_malformed_fingerprint_and_touches_nothing(self):
        before = self.auth_text()
        for fp in (self.dfp, "SHA256:" + "A" * 43, "SHA256:corta", "", "abc"):
            with self.subTest(fp=fp):
                rc, out = self.run_cmd("retire", "--fingerprint", fp)
                self.assertEqual(rc, 1, out)
                self.assertEqual(self.auth_text(), before)
                self.assertTrue(self.get_container("superbot-desk-api")["State"]["Running"])

    def test_retire_refuses_if_two_lines_match(self):
        self.write_auth([self.admin, self.TUNNEL_OPTS + " " + self.tunnel, self.TUNNEL_OPTS + " " + self.tunnel])
        before = self.auth_text()
        rc, out = self.retire()
        self.assertEqual(rc, 1, out)
        self.assertIn("trovate 2", out)
        self.assertEqual(self.auth_text(), before)

    def test_retire_refuses_if_app_is_already_down_or_container_missing(self):
        open(os.path.join(self.state, "app_down"), "w").close()
        self.assertEqual(self.retire()[0], 1)
        os.remove(os.path.join(self.state, "app_down"))
        os.remove(os.path.join(self.state, "containers", "superbot-desk-api.json"))
        rc, out = self.retire()
        self.assertEqual(rc, 1, out)
        self.assertIn("non esiste", out)

    # ---- il controllo finale sa fallire ----

    def assert_bridge_back(self, auth_before):
        """Dopo un ritiro fallito il ponte e' tornato com'era: container col nome e la politica originali, riga al suo posto."""
        c = self.get_container("superbot-desk-api")
        self.assertTrue(c["State"]["Running"])
        self.assertEqual(c["HostConfig"]["RestartPolicy"]["Name"], "unless-stopped")
        self.assertEqual(sorted(l for l in self.auth_text().split("\n") if l), sorted(l for l in auth_before.split("\n") if l))

    def test_final_check_fails_if_the_app_goes_down(self):
        before = self.auth_text()
        open(os.path.join(self.state, "break_app_on_stop"), "w").close()
        rc, out = self.retire()
        self.assertEqual(rc, 1, out)
        self.assertIn("l'app NON risponde", out)
        self.assertIn("RISULTATO: FALLITO", out)
        self.assert_bridge_back(before)

    def test_final_check_fails_if_a_bot_restarts(self):
        before = self.auth_text()
        open(os.path.join(self.state, "restart_hawk_on_stop"), "w").close()
        rc, out = self.retire()
        self.assertEqual(rc, 1, out)
        self.assertIn("superbot-desk-hawk e' cambiato", out)
        self.assert_bridge_back(before)

    # ---- ripristino ----

    def test_restore_puts_everything_back_and_is_idempotent(self):
        original = self.auth_text().split("\n")
        self.assertEqual(self.retire()[0], 0)
        rc, out = self.run_cmd("restore")
        self.assertEqual(rc, 0, out)
        self.assertIn("RISULTATO: OK", out)
        back = self.auth_text()
        self.assertIn(self.tunnel.split()[1], back)
        self.assertEqual(sorted(l for l in back.split("\n") if l), sorted(l for l in original if l))
        c = self.get_container("superbot-desk-api")
        self.assertTrue(c["State"]["Running"])
        self.assertEqual(c["HostConfig"]["RestartPolicy"]["Name"], "unless-stopped")
        rc, out = self.run_cmd("restore")
        self.assertEqual(rc, 0, out)
        self.assertIn("gia' in authorized_keys", out)
        self.assertEqual(back.count(self.tunnel.split()[1]), 1)

    def test_split_line_handles_options_with_spaces_and_commas(self):
        sys.path.insert(0, HERE)
        try:
            import importlib
            mod = importlib.import_module("bridge_retire")
        finally:
            sys.path.pop(0)
        opts, typ, blob, comment = mod.split_line('command="echo a b, c",restrict ssh-ed25519 AAAAC3Nza abc def\n')
        self.assertEqual((opts, typ, blob, comment), ('command="echo a b, c",restrict', "ssh-ed25519", "AAAAC3Nza", "abc def"))
        self.assertIsNone(mod.split_line("# commento\n"))
        self.assertIsNone(mod.split_line("   \n"))
        self.assertEqual(mod.split_line("ssh-ed25519 AAAA\n")[0], "")


if __name__ == "__main__":
    unittest.main()
