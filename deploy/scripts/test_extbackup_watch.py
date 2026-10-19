"""Prove della sentinella del backup esterno (extbackup_watch.py e workflow sg-extbackup-watch.yml).

Si lanciano con:  python3 -m unittest deploy/scripts/test_extbackup_watch.py -v
Il passo del workflow viene ESEGUITO davvero con un ssh finto che restituisce lo stato voluto.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
WATCH = os.path.join(HERE, "extbackup_watch.py")
WF = os.path.join(REPO, ".github", "workflows", "sg-extbackup-watch.yml")
NOW = "2026-10-20T04:40:00Z"


def status(**kw):
    base = {"archivio": "superbot-backup-20261020T032100Z.tar.gz.age", "sha256": "a" * 64,
            "ultimo_successo": "2026-10-20T03:21:00Z", "ultimo_tentativo": "2026-10-20T03:21:00Z",
            "ultimo_errore": None}
    base.update(kw)
    return json.dumps(base)


def wf_text():
    with open(WF) as f:
        return f.read()


def get_block(src, anchor, key):
    import re
    lines = src.split("\n")
    i = next(n for n, l in enumerate(lines) if anchor in l)
    j = next(n for n in range(i, len(lines)) if re.match(r"\s*%s: \|\s*$" % re.escape(key), lines[n]))
    base, out = None, []
    for l in lines[j + 1:]:
        if not l.strip():
            out.append("")
            continue
        ind = len(l) - len(l.lstrip(" "))
        if base is None:
            base = ind
        if ind < base:
            break
        out.append(l[base:])
    return "\n".join(out) + "\n"


class WatchTests(unittest.TestCase):
    def run_watch(self, text, now=NOW, *extra):
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, "s.json")
            if text is not None:
                with open(path, "w") as f:
                    f.write(text)
            p = subprocess.run([sys.executable, "-I", WATCH, "--status", path, "--now", now, *extra],
                               capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout.strip()

    def test_recent_success_is_quiet(self):
        rc, out = self.run_watch(status())
        self.assertEqual(rc, 0, out)
        self.assertTrue(out.startswith("OK"))

    def test_first_failure_alerts_and_says_when_last_success_was(self):
        rc, out = self.run_watch(status(ultimo_errore="comando fallito (git clone -q): Permission denied",
                                        ultimo_successo="2026-10-19T11:57:24Z"))
        self.assertEqual(rc, 2, out)
        self.assertIn("FALLITO", out)
        self.assertIn("Permission denied", out)
        self.assertIn("2026-10-19T11:57:24Z", out)

    def test_old_success_alerts_even_without_errors(self):
        rc, out = self.run_watch(status(ultimo_successo="2026-10-18T03:21:00Z"))   # 49 ore prima
        self.assertEqual(rc, 2, out)
        self.assertIn("da 49 ore", out)
        rc, _ = self.run_watch(status(ultimo_successo="2026-10-18T17:00:00Z"))      # 35,7 ore: ancora ok
        self.assertEqual(rc, 0)

    def test_unreachable_or_broken_state_alerts(self):
        for text in (None, "", "{rotto", "[1,2]", status(ultimo_successo=None),
                     status(ultimo_successo="ieri")):
            with self.subTest(text=text):
                rc, out = self.run_watch(text)
                self.assertEqual(rc, 2, out)

    # ---- il passo del workflow, eseguito davvero ----

    def run_step(self, status_text, event="schedule", trigger=None):
        script = get_block(wf_text(), "id: check", "run").replace("${{ github.event_name }}", event)
        with tempfile.TemporaryDirectory() as t:
            bind = os.path.join(t, "bin")
            os.makedirs(bind)
            log = os.path.join(t, "ssh.log")
            src = os.path.join(t, "status.src")
            if status_text is None:
                body = 'echo "ssh $*" >> %s; exit 255' % log           # server spento
            else:
                with open(src, "w") as f:
                    f.write(status_text)
                body = 'echo "ssh $*" >> %s; cat %s' % (log, src)
            with open(os.path.join(bind, "ssh"), "w") as f:
                f.write("#!/bin/sh\n" + body + "\n")
            os.chmod(os.path.join(bind, "ssh"), 0o755)
            os.makedirs(os.path.join(t, "deploy", "scripts"))
            for n in ("extbackup_watch.py",):
                with open(os.path.join(HERE, n)) as a, open(os.path.join(t, "deploy", "scripts", n), "w") as b:
                    b.write(a.read())
            if trigger:
                with open(os.path.join(t, "deploy", "sg-extbackup-watch.trigger"), "w") as f:
                    f.write(trigger)
            out = os.path.join(t, "out")
            p = subprocess.run(["bash", "-e", "-c", script], cwd=t, capture_output=True, text=True, timeout=60,
                               env=dict(os.environ, PATH=bind + ":" + os.environ["PATH"], HOME=t, SG_SSH_KEY="finta",
                                        GITHUB_OUTPUT=out), stdin=subprocess.DEVNULL)
            with open(out) as f:
                outputs = dict(l.split("=", 1) for l in f.read().split())
            with open(log) as f:
                calls = f.read()
        return p.returncode, outputs, calls

    def test_step_is_read_only_and_quiet_when_all_is_well(self):
        # lo stato vero e' di "adesso": uso un successo recente rispetto all'orologio reale
        from datetime import datetime, timezone, timedelta
        recent = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rc, outputs, calls = self.run_step(status(ultimo_successo=recent))
        self.assertEqual(rc, 0)
        self.assertEqual(outputs, {"alert": "0", "prova": "0"})
        self.assertEqual(calls.count("ssh "), 1)
        self.assertIn("cat /opt/superbot-extbackup/status.json", calls)   # l'unica azione sul server e' leggere

    def test_step_alerts_on_failure_and_on_unreachable_server(self):
        rc, outputs, _ = self.run_step(status(ultimo_errore="boom"))
        self.assertEqual((rc, outputs["alert"]), (0, "1"))
        rc, outputs, _ = self.run_step(None)
        self.assertEqual((rc, outputs["alert"]), (0, "1"))

    def test_test_message_only_on_manual_push_with_the_flag(self):
        from datetime import datetime, timezone, timedelta
        recent = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual(self.run_step(status(ultimo_successo=recent), "push", "prova=telegram\n")[1]["prova"], "1")
        self.assertEqual(self.run_step(status(ultimo_successo=recent), "schedule", "prova=telegram\n")[1]["prova"], "0")

    def test_workflow_text_rules(self):
        t = wf_text()
        self.assertIn('cron: "40 4 * * *"', t)                          # dopo il backup delle 03:20 UTC
        self.assertIn("StrictHostKeyChecking=yes", t)
        self.assertNotIn("StrictHostKeyChecking=no", t)
        self.assertEqual(t.count("root@51.79.205.82"), 1)
        self.assertNotIn("51.91.109.45", t)                              # Strasburgo/HI-TV mai contattato
        self.assertIn("permissions:\n  contents: read", t)
        for leak in ('echo "$TELEGRAM_BOT_TOKEN', "echo $TELEGRAM_BOT_TOKEN", "set -x"):
            self.assertNotIn(leak, t)
        self.assertIn("exit 1", get_block(t, "name: Esito", "run"))     # con un avviso il workflow e' rosso


if __name__ == "__main__":
    unittest.main()
