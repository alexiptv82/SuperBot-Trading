"""Prove del workflow di rilascio dell'app (superbot-sg-deploy.yml) senza server e senza segreti.

Si lanciano con:  python3 -m unittest deploy/scripts/test_deploy_workflow.py -v

Come funziona: lo script che gira sul VPS (il blocco `script:` del passo ssh-action) e il passo che
risolve lo SHA vengono ESTRATTI dal file del workflow e fatti girare davvero, in una cartella
temporanea che fa da finto server (/opt e /etc puntati li'), con docker/git/curl/nginx FINTI che
scrivono un registro. Il backup del database e' invece quello vero (backup_app_db.py su un database
vero). Cosi' si verifica l'ORDINE reale delle operazioni, non solo il testo.

Casi 4 e 5 della revisione di ChatGPT (19/10, terzo giro):
  4. i backup obbligatori vengono PRIMA della promozione del frontend; la build vecchia resta fino al
     controllo finale e il ritorno indietro la ripristina;
  5. lo SHA approvato e' risolto UNA volta e usato per checkout, build, fetch/reset sul VPS e manifesto;
     se main si muove nel frattempo il rilascio non cambia.
"""
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
WORKFLOW = os.path.join(REPO, ".github", "workflows", "superbot-sg-deploy.yml")
BACKUP_APP = os.path.join(HERE, "backup_app_db.py")

SHA = "a" * 40
OTHER = "b" * 40
MOVED = "c" * 40            # dove si sarebbe spostato main nel frattempo
INITIAL = "1" * 40           # lo SHA in uso sul server prima del rilascio


def text():
    with open(WORKFLOW) as f:
        return f.read()


def get_block(src, anchor, key):
    """Testo (senza l'indentazione YAML) del blocco `key: |` che segue la prima riga con `anchor`."""
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


def remote_script():
    return get_block(text(), "uses: appleboy/ssh-action", "script")


def resolve_script():
    return get_block(text(), "id: approved", "run")


STUB_COMMON = r'''#!/bin/sh
# finto "%(name)s": scrive nel registro lo stato visibile in quel momento
SB="%(sb)s"
printf '%%s %%s | build=%%s prev=%%s backups=%%s\n' "%(name)s" "$*" \
  "$(cat "$SB/opt/superbot-web/build/index.html" 2>/dev/null || echo none)" \
  "$(cat "$SB/opt/superbot-web/build.prev/index.html" 2>/dev/null || echo none)" \
  "$(ls "$SB/opt/superbot-backups" 2>/dev/null | grep -c '^superbot-deploy-.*\.db$')" >> "$SB/calls.log"
flag() { [ -e "$SB/flags/$1" ]; }
'''

STUBS = {
    "docker": r'''
case "$1" in
  image)  grep -qx "$3" "$SB/state/images" ;;
  tag)    grep -qx "$2" "$SB/state/images" && echo "$3" >> "$SB/state/images"; exit 0 ;;
  build)  flag fail_build && exit 1; echo superbot >> "$SB/state/images"; exit 0 ;;
  run)    for last; do :; done; echo "$last" > "$SB/state/running"; exit 0 ;;
  inspect) echo "sha256:fakeimage"; exit 0 ;;
  *)      exit 0 ;;
esac
''',
    "curl": r'''
fmt=""; prev=""
for a in "$@"; do [ "$prev" = "-w" ] && fmt="$a"; prev="$a"; done
[ -n "$fmt" ] && printf '%s' "$fmt" | sed 's/%{http_code}/200/g; s/\\n/\n/g'
case "$*" in *8002/api/health*)
  r="$(cat "$SB/state/running")"
  if [ "$r" = "superbot" ] && flag fail_health; then exit 22; fi ;;
esac
exit 0
''',
    "git": r'''
case "$1 $2" in
  "rev-parse --verify"|"rev-parse HEAD") cat "$SB/state/head"; exit 0 ;;
esac
case "$1" in
  fetch)    case "$*" in *"origin $FAKE_SHA"*) flag fail_fetch_sha && exit 1 ;; esac; exit 0 ;;
  cat-file) flag fail_cat_file && exit 1; exit 0 ;;
  reset)    case "$3" in origin/main) echo "%(moved)s" > "$SB/state/head" ;; *) echo "$3" > "$SB/state/head" ;; esac; exit 0 ;;
  *)        exit 0 ;;
esac
''',
    "nginx": "exit 0\n",
    "systemctl": "exit 0\n",
    "apt-get": "exit 0\n",
    "sleep": "exit 0\n",
}


class Sandbox:
    """Un finto server in una cartella temporanea."""

    def __init__(self):
        self.td = tempfile.TemporaryDirectory()
        self.sb = self.td.name
        for d in ("opt/superbot/data", "opt/superbot/backend", "opt/superbot/.git", "opt/superbot-tools",
                  "opt/superbot-web/build", "opt/superbot-web/build.new", "etc/nginx/sites-available",
                  "etc/nginx/sites-enabled", "bin", "state", "flags"):
            os.makedirs(os.path.join(self.sb, d), exist_ok=True)
        c = sqlite3.connect(os.path.join(self.sb, "opt/superbot/data/superbot.db"))
        c.execute("create table utenti(id integer primary key, nome text)")
        c.execute("insert into utenti(nome) values('a')")
        c.commit()
        c.close()
        shutil.copy(BACKUP_APP, os.path.join(self.sb, "opt/superbot-tools/backup_app_db.py"))
        self.write("opt/superbot-web/build/index.html", "OLD")
        self.write("opt/superbot-web/build.new/index.html", "NEW")
        self.write("opt/superbot-web/build.new.sha", SHA)
        self.write("state/images", "superbot\n")
        self.write("state/running", "iniziale\n")
        self.write("state/head", INITIAL + "\n")
        for name, body in STUBS.items():
            head = STUB_COMMON % {"name": name, "sb": self.sb}
            body = body % {"moved": MOVED} if "%(moved)s" in body else body
            path = os.path.join(self.sb, "bin", name)
            with open(path, "w") as f:
                f.write(head + body.replace("%%", "%").replace("$FAKE_SHA", SHA))
            os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)

    def write(self, rel, body):
        with open(os.path.join(self.sb, rel), "w") as f:
            f.write(body)

    def read(self, rel, default=None):
        try:
            with open(os.path.join(self.sb, rel)) as f:
                return f.read().strip()
        except FileNotFoundError:
            return default

    def flag(self, name):
        self.write("flags/" + name, "1")

    def log(self):
        return (self.read("calls.log", "") or "").split("\n")

    def run(self, shell="bash", env_over=None):
        script = remote_script().replace("/opt/", self.sb + "/opt/").replace("/etc/", self.sb + "/etc/")
        path = os.path.join(self.sb, "script.sh")
        with open(path, "w") as f:
            f.write(script)
        env = {"PATH": os.path.join(self.sb, "bin") + ":/usr/bin:/bin", "APPROVED_SHA": SHA, "DEPLOY_RUN": "42",
               "DASHBOARD_PASSWORD": "prova", "TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "c",
               "SG_DOMAIN": "prova.example"}
        env.update(env_over or {})
        p = subprocess.run([shell, path], env=env, capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout + p.stderr

    def cleanup(self):
        self.td.cleanup()


def shells():
    out = ["bash"]
    if shutil.which("dash"):
        out.append("dash")           # se la shell remota fosse piu' rigida di bash
    return out


class RemoteScriptTests(unittest.TestCase):
    def setUp(self):
        self.s = Sandbox()

    def tearDown(self):
        self.s.cleanup()

    def entries(self, cmd):
        return [l for l in self.s.log() if l.startswith(cmd + " ")]

    # ---- caso 4: ordine backup -> promozione, build vecchia conservata ----

    def test_success_backups_first_then_promotion_old_build_kept(self):
        for shell in shells():
            with self.subTest(shell=shell):
                self.tearDown()
                self.setUp()
                rc, out = self.s.run(shell)
                self.assertEqual(rc, 0, out)
                log = [l for l in self.s.log() if l]
                first_new = next(i for i, l in enumerate(log) if "build=NEW" in l)
                first_git = next(i for i, l in enumerate(log) if l.startswith("git "))
                # appena si comincia a toccare il codice il backup c'e' gia' e il sito in uso e' ancora il vecchio
                self.assertLess(first_git, first_new)
                self.assertIn("build=OLD", log[first_git])
                self.assertIn("backups=1", log[first_git])
                # nessun momento in cui il sito nuovo e' in uso senza backup
                self.assertTrue(all("backups=1" in l for l in log if "build=NEW" in l))
                self.assertTrue(any("backups=0" in l for l in log[:first_git]))      # prima del backup si era a zero
                # dopo: build nuova in uso, quella vecchia conservata
                self.assertEqual(self.s.read("opt/superbot-web/build/index.html"), "NEW")
                self.assertEqual(self.s.read("opt/superbot-web/build.prev/index.html"), "OLD")
                self.assertIsNone(self.s.read("opt/superbot-web/build.new.sha"))
                self.assertEqual(self.s.read("state/running"), "superbot")

    def test_backup_failure_stops_everything_and_touches_nothing(self):
        os.remove(os.path.join(self.s.sb, "opt/superbot/data/superbot.db"))     # backup impossibile
        rc, out = self.s.run()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(self.s.read("opt/superbot-web/build/index.html"), "OLD")        # sito in uso intatto
        self.assertEqual(self.s.read("opt/superbot-web/build.new/index.html"), "NEW")    # niente promosso
        self.assertIsNone(self.s.read("opt/superbot-web/build.prev/index.html"))
        self.assertEqual(self.entries("git") + self.entries("docker"), [])               # nessun codice, nessun container
        self.assertEqual(self.s.read("state/running"), "iniziale")
        self.assertIn("Nessuna modifica", out)

    def test_promotion_only_after_backup_even_if_frontend_marker_is_wrong(self):
        self.s.write("opt/superbot-web/build.new.sha", OTHER)        # frontend costruito da un altro SHA
        rc, out = self.s.run()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(self.s.read("opt/superbot-web/build/index.html"), "OLD")
        self.assertEqual(self.entries("git"), [])                    # si ferma prima di toccare il codice
        self.assertIn("SHA approvato", out)

    def test_health_failure_rolls_back_frontend_and_container(self):
        self.s.flag("fail_health")
        rc, out = self.s.run()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(self.s.read("opt/superbot-web/build/index.html"), "OLD")        # frontend tornato
        self.assertEqual(self.s.read("opt/superbot-web/build.failed/index.html"), "NEW")  # quella scartata, conservata
        self.assertEqual(self.s.read("state/running"), "superbot:prev")                  # container tornato
        self.assertTrue(any(l.startswith("docker run") and l.split("|")[0].rstrip().endswith("superbot:prev")
                            for l in self.s.log()))
        self.assertFalse(os.path.exists(os.path.join(self.s.sb, "opt/superbot-deploys/app-last.json")))
        self.assertIn("RITORNO INDIETRO", out)
        self.assertIn("RISPONDE", out)                                                    # e dopo il ritorno l'app risponde

    def test_image_build_failure_restores_frontend_and_keeps_running_container(self):
        self.s.flag("fail_build")
        rc, out = self.s.run()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(self.s.read("opt/superbot-web/build/index.html"), "OLD")
        self.assertEqual(self.entries("docker stop"), [])            # il container in uso non e' stato fermato
        self.assertEqual(self.s.read("state/running"), "iniziale")

    def test_old_build_is_kept_until_final_check_not_deleted_earlier(self):
        # la build vecchia non viene mai cancellata durante il rilascio: al momento del controllo finale c'e' ancora
        rc, out = self.s.run()
        self.assertEqual(rc, 0, out)
        health_lines = [l for l in self.s.log() if l.startswith("curl") and "8002/api/health" in l]
        self.assertTrue(health_lines)
        self.assertTrue(all("prev=OLD" in l for l in health_lines), health_lines)

    # ---- caso 5: un solo SHA ----

    def test_exact_sha_is_fetched_and_reset_and_main_is_never_followed(self):
        for shell in shells():
            with self.subTest(shell=shell):
                self.tearDown()
                self.setUp()
                rc, out = self.s.run(shell)
                self.assertEqual(rc, 0, out)
                calls = " || ".join(self.s.log())
                self.assertIn("git fetch --no-tags origin %s" % SHA, calls)
                self.assertIn("git reset --hard %s" % SHA, calls)
                self.assertNotIn("origin main", calls)
                self.assertNotIn("reset --hard origin/main", calls)
                self.assertEqual(self.s.read("state/head"), SHA)     # anche se origin/main fosse altrove

    def test_if_origin_main_moved_meanwhile_the_release_does_not_change(self):
        # la finta git porta origin/main a MOVED: chi seguisse main finirebbe su MOVED
        rc, out = self.s.run()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.s.read("state/head"), SHA)
        self.assertNotEqual(self.s.read("state/head"), MOVED)

    def test_direct_sha_fetch_failure_falls_back_to_branch_but_still_resets_to_the_sha(self):
        self.s.flag("fail_fetch_sha")
        rc, out = self.s.run()
        self.assertEqual(rc, 0, out)
        calls = " || ".join(self.s.log())
        self.assertIn("refs/heads/main:refs/remotes/origin/main", calls)
        self.assertIn("git reset --hard %s" % SHA, calls)
        self.assertEqual(self.s.read("state/head"), SHA)

    def test_sha_missing_from_fetched_history_stops_before_promotion(self):
        self.s.flag("fail_fetch_sha")
        self.s.flag("fail_cat_file")
        rc, out = self.s.run()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(self.s.read("opt/superbot-web/build/index.html"), "OLD")
        self.assertEqual(self.entries("docker"), [])

    def test_missing_or_malformed_sha_is_refused_before_anything(self):
        for bad in ("", "abc", "g" * 40, SHA[:-1], SHA + "0"):
            with self.subTest(sha=bad):
                self.tearDown()
                self.setUp()
                rc, out = self.s.run(env_over={"APPROVED_SHA": bad})
                self.assertNotEqual(rc, 0, out)
                self.assertEqual(self.s.read("opt/superbot-web/build/index.html"), "OLD")
                self.assertEqual(self.s.read("calls.log", ""), "")

    def test_manifest_and_image_label_carry_the_same_sha(self):
        rc, out = self.s.run()
        self.assertEqual(rc, 0, out)
        man = json.loads(self.s.read("opt/superbot-deploys/app-last.json"))
        self.assertEqual(man["sha_approvato"], SHA)
        self.assertEqual(man["sha_sul_server"], SHA)
        self.assertEqual(man["sha_frontend"], SHA)
        self.assertEqual(man["sha_precedente"], INITIAL)
        self.assertEqual(man["run_github"], "42")
        self.assertTrue(man["backup_database"].endswith(".db"))
        (build,) = self.entries("docker build")
        self.assertIn("--label superbot.sha=%s" % SHA, build)

    def test_server_sha_different_from_approved_is_refused(self):
        self.s.write("state/head", INITIAL + "\n")
        # una finta git che dopo il reset risponde con uno SHA diverso: il rilascio deve fermarsi
        path = os.path.join(self.s.sb, "bin", "git")
        with open(path) as f:
            body = f.read()
        body = body.replace('*) echo "$3" > "$SB/state/head" ;; esac', '*) echo "%s" > "$SB/state/head" ;; esac' % MOVED)
        with open(path, "w") as f:
            f.write(body)
        rc, out = self.s.run()
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(self.s.read("opt/superbot-web/build/index.html"), "OLD")


class ResolveStepTests(unittest.TestCase):
    """Il passo che decide lo SHA, con un finto `gh`."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        bindir = os.path.join(self.td.name, "bin")
        os.makedirs(bindir)
        self.calls = os.path.join(self.td.name, "gh.calls")
        self.out = os.path.join(self.td.name, "github_output")
        gh = os.path.join(bindir, "gh")
        with open(gh, "w") as f:
            f.write('''#!/bin/sh
echo "$*" >> "%s"
case "$*" in
  *contents/deploy/superbot-sg-deploy.trigger*) cat "%s/trigger.txt"; [ -e "%s/fail_trigger" ] && exit 1; exit 0 ;;
  *commits/main*) echo "%s" ;;
  *compare/main...*) cat "%s/status.txt" ;;
esac
''' % (self.calls, self.td.name, self.td.name, MOVED, self.td.name))
        os.chmod(gh, 0o755)
        self.bindir = bindir

    def tearDown(self):
        self.td.cleanup()

    def go(self, trigger, status="behind", fail_trigger=False):
        with open(os.path.join(self.td.name, "trigger.txt"), "w") as f:
            f.write(trigger)
        with open(os.path.join(self.td.name, "status.txt"), "w") as f:
            f.write(status + "\n")
        if fail_trigger:
            open(os.path.join(self.td.name, "fail_trigger"), "w").close()
        env = {"PATH": self.bindir + ":/usr/bin:/bin", "GH_TOKEN": "x", "GITHUB_REPOSITORY": "o/r",
               "TRIGGER_COMMIT": "d" * 40, "GITHUB_OUTPUT": self.out}
        p = subprocess.run(["bash", "-c", resolve_script()], env=env, capture_output=True, text=True, timeout=60)
        outv = calls = ""
        if os.path.exists(self.out):
            with open(self.out) as f:
                outv = f.read()
        if os.path.exists(self.calls):
            with open(self.calls) as f:
                calls = f.read()
        return p.returncode, p.stdout + p.stderr, outv, calls

    def test_without_sha_in_trigger_main_tip_is_resolved_exactly_once(self):
        rc, out, outv, calls = self.go("2026-10-19 rilascio\n", status="identical")
        self.assertEqual(rc, 0, out)
        self.assertEqual(outv.strip(), "sha=" + MOVED)
        self.assertEqual(calls.count("commits/main"), 1)

    def test_sha_in_trigger_is_used_and_main_tip_is_not_read(self):
        rc, out, outv, calls = self.go("rilascio\nsha=%s\n" % SHA, status="behind")
        self.assertEqual(rc, 0, out)
        self.assertEqual(outv.strip(), "sha=" + SHA)
        self.assertNotIn("commits/main", calls)

    def test_sha_outside_main_history_is_refused(self):
        for status in ("ahead", "diverged"):
            with self.subTest(status=status):
                rc, out, outv, _ = self.go("sha=%s\n" % SHA, status=status)
                self.assertNotEqual(rc, 0, out)
                self.assertEqual(outv, "")

    def test_malformed_sha_line_is_an_error_not_a_silent_fallback_to_main(self):
        for bad in ("sha=abc\n", "sha=%s\n" % ("G" * 40), "sha=\n", "sha=%s0\n" % SHA):
            with self.subTest(line=bad):
                rc, out, outv, calls = self.go(bad)
                self.assertNotEqual(rc, 0, out)
                self.assertEqual(outv, "")
                self.assertNotIn("commits/main", calls)

    def test_unreadable_trigger_does_not_fall_back_to_main(self):
        rc, out, outv, calls = self.go("sha=%s\n" % SHA, fail_trigger=True)
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(outv, "")


class WorkflowTextTests(unittest.TestCase):
    def test_everything_uses_the_one_resolved_sha(self):
        t = text()
        self.assertEqual(t.count("commits/main"), 1)                      # main si legge in un posto solo
        self.assertNotIn("ref: main", t)
        self.assertNotRegex(t, r"reset --hard origin")
        self.assertNotRegex(t, r"git fetch origin main")
        self.assertIn("ref: ${{ steps.approved.outputs.sha }}", t)
        self.assertLess(t.index("id: approved"), t.index("uses: actions/checkout"))   # risolto prima del checkout
        self.assertIn("APPROVED_SHA:        ${{ steps.approved.outputs.sha }}", t)       # arriva al server
        self.assertRegex(t, r"envs: APPROVED_SHA,")

    def test_runner_copy_step_does_not_promote_the_frontend(self):
        step = get_block(text(), "Copia frontend (in build.new)", "run")
        self.assertIn("build.new", step)
        self.assertNotRegex(step, r"mv .*build\.new")
        self.assertNotIn("rm -rf /opt/superbot-web/build.old", step)

    def test_promotion_comes_after_backup_in_the_remote_script(self):
        s = remote_script()
        self.assertLess(s.index("backup_app_db.py"), s.index('mv "$WEB/build.new" "$WEB/build"'))
        self.assertLess(s.index('mv "$WEB/build.new" "$WEB/build"'), s.index("docker build"))
        # build.prev non viene mai cancellata dopo la promozione (solo all'inizio della promozione successiva)
        self.assertEqual(s.count('rm -rf "$WEB/build.prev"'), 1)
        self.assertLess(s.index('rm -rf "$WEB/build.prev"'), s.index('mv "$WEB/build.new" "$WEB/build"'))

    def test_desk_deploy_has_explicit_bot_stopped_switch_off_by_default(self):
        with open(os.path.join(REPO, ".github", "workflows", "desk-deploy.yml")) as f:
            d = f.read()
        self.assertIn("--bot-stopped", d)
        self.assertNotRegex(d, r"backup_brain\.py[^\n]*--bot-stopped")   # mai fisso nella riga di comando


class ExtBackupWorkflowTests(unittest.TestCase):
    """sg-extbackup.yml: niente segreti stampati, chiavi dei server verificate, azioni ammesse solo tre."""

    def wf(self):
        with open(os.path.join(REPO, ".github", "workflows", "sg-extbackup.yml")) as f:
            return f.read()

    def test_private_deploy_key_is_never_printed_and_hosts_are_verified(self):
        t = self.wf()
        for m in re.finditer(r"cat[^\n]*superbot_backup_ed25519([^\n]*)", t):
            self.assertTrue(m.group(0).split("superbot_backup_ed25519")[1].startswith(".pub")
                            or "$KEY.pub" in m.group(0), m.group(0))
        self.assertIn('cat "$KEY.pub"', t)
        self.assertNotRegex(t, r"cat \"?\$KEY\"?\s*$")
        self.assertNotIn("StrictHostKeyChecking=no", t)
        self.assertNotIn("accept-new", t)
        self.assertIn("StrictHostKeyChecking=yes", t)
        self.assertIn("UserKnownHostsFile=$HOME/.ssh/known_hosts_sg", t)
        self.assertIn("gh api meta", t)                  # le chiavi di GitHub vengono da GitHub, non da ssh-keyscan
        self.assertNotIn("ssh-keyscan", t)

    def test_only_three_actions_are_accepted(self):
        t = self.wf()
        self.assertIn("setup|run|status) ;;", t)
        self.assertIn("*) echo \"ERRORE: nel file trigger serve una riga azione=setup|run|status\"; exit 1 ;;", t)

    def test_service_uses_the_dedicated_key_and_the_private_repo_only(self):
        t = self.wf()
        self.assertEqual(t.count("git@github.com:alexiptv82/superbot-backups.git"), 1)
        self.assertIn("--ssh-key /root/.ssh/superbot_backup_ed25519 --known-hosts /opt/superbot-extbackup/known_hosts", t)
        self.assertIn("--recipient-file /opt/superbot-extbackup/recipient.txt", t)
        self.assertIn("OnCalendar=*-*-* 03:20:00 UTC", t)
        self.assertIn("Persistent=true", t)

    def run_step(self, action):
        """Esegue davvero il passo del workflow con ssh/scp/gh FINTI che registrano le chiamate."""
        script = get_block(self.wf(), "id: act", "run")
        with tempfile.TemporaryDirectory() as t:
            log = os.path.join(t, "log")
            bind = os.path.join(t, "bin")
            os.makedirs(bind)
            for name, body in (("ssh", 'echo "ssh $*" >> %s; cat >/dev/null; exit 0' % log),
                               ("scp", 'echo "scp $*" >> %s; exit 0' % log),
                               ("gh", 'echo "gh $*" >> %s; echo "ssh-ed25519 AAAA"' % log)):
                with open(os.path.join(bind, name), "w") as f:
                    f.write("#!/bin/sh\n" + body + "\n")
                os.chmod(os.path.join(bind, name), 0o755)
            os.makedirs(os.path.join(t, "deploy"))
            with open(os.path.join(t, "deploy", "sg-extbackup.trigger"), "w") as f:
                f.write("prova\nazione=%s\n" % action)
            env = dict(os.environ, PATH=bind + ":" + os.environ["PATH"], HOME=t, SG_SSH_KEY="finta",
                       GITHUB_OUTPUT=os.path.join(t, "out"), GH_TOKEN="x")
            p = subprocess.run(["bash", "-e", "-c", script], cwd=t, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                               timeout=60)
            calls = open(log).read() if os.path.exists(log) else ""
        for leftover in ("/tmp/extbackup_remote.txt", "/tmp/known_hosts_github"):   # file del runner GitHub
            if os.path.exists(leftover):
                os.remove(leftover)
        return p.returncode, calls

    def test_status_writes_nothing_on_the_server(self):
        """Caso 1 di ChatGPT (19/10 pomeriggio): un controllo di stato deve solo leggere."""
        rc, calls = self.run_step("status")
        self.assertEqual(rc, 0, calls)
        self.assertNotIn("scp ", calls)
        self.assertNotIn("mkdir", calls)
        self.assertNotIn("gh api", calls)
        self.assertEqual(calls.count("ssh "), 1)                 # una sola connessione: quella che legge

    def test_setup_and_run_install_the_tools(self):
        for action in ("setup", "run"):
            with self.subTest(action=action):
                rc, calls = self.run_step(action)
                self.assertEqual(rc, 0, calls)
                self.assertEqual(calls.count("scp "), 3)
                self.assertIn("mkdir -p /opt/superbot-tools", calls)

    def test_no_secret_goes_to_the_repository_by_name(self):
        for dp, dn, fn in os.walk(os.path.join(REPO, "deploy")):
            for f in fn:
                path = os.path.join(dp, f)
                with open(path, "rb") as fh:
                    # una vera chiave privata age: prefisso + 58 caratteri bech32 (le semplici citazioni del nome non contano)
                    found = re.search(rb"AGE-SECRET-KEY-1[QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L]{58}", fh.read())
                    self.assertIsNone(found, "chiave privata in " + path)
        with open(os.path.join(REPO, "deploy", "extbackup", "recipient.txt")) as f:
            body = f.read()
        self.assertRegex(body, r"(?m)^age1[0-9a-z]{58}$")


class BridgeWorkflowTests(unittest.TestCase):
    """sg-bridge.yml: tre azioni, impronta validata prima di arrivare al server, host verificato, niente cancellazioni."""

    def wf(self):
        with open(os.path.join(REPO, ".github", "workflows", "sg-bridge.yml")) as f:
            return f.read()

    def test_only_three_actions_and_fingerprint_is_validated_before_use(self):
        t = self.wf()
        for a in ("controllo) CMD=check", "ritira) CMD=retire", "ripristina) CMD=restore"):
            self.assertIn(a, t)
        self.assertIn("azione=controllo|ripristina|ritira".replace("ripristina|ritira", "ritira|ripristina"), t)
        self.assertIn("grep -Eq '^SHA256:[A-Za-z0-9+/]{43}$'", t)
        # fuori da "ritira" l'impronta viene azzerata: non arriva mai al server
        self.assertIn('else\n            FP=""', t)
        self.assertIn("${FP:+--fingerprint $FP}", t)

    def test_runs_only_on_its_trigger_and_is_serialized_with_app_deploys(self):
        t = self.wf()
        self.assertRegex(t, r'paths:\s*\n\s*- "deploy/sg-bridge.trigger"')
        self.assertIn("group: superbot-app-singapore", t)
        self.assertIn("cancel-in-progress: false", t)

    def test_server_identity_is_verified_and_the_ssh_key_is_removed(self):
        t = self.wf()
        self.assertIn("StrictHostKeyChecking=yes", t)
        self.assertNotIn("StrictHostKeyChecking=no", t)
        self.assertNotIn("accept-new", t)
        self.assertIn("rm -f ~/.ssh/id_sg", t)
        self.assertIn("/usr/bin/python3 -I /opt/superbot-tools/bridge_retire.py", t)

    def test_the_workflow_itself_never_deletes_or_touches_other_things(self):
        # solo le righe eseguibili: nei commenti si puo' spiegare cosa fa lo strumento
        t = "\n".join(l for l in self.wf().splitlines() if not l.strip().startswith("#"))
        for bad in ("docker rm", "docker system", "docker volume", "rm -rf", "hitv", "authorized_keys"):
            self.assertNotIn(bad, t.lower() if bad.islower() else t)
        self.assertEqual(t.count("root@51.79.205.82"), 3)       # mkdir, scp, esecuzione: nient'altro
        self.assertNotIn("51.91.109.45", t)                      # Strasburgo (HI-TV) non viene mai contattato


if __name__ == "__main__":
    unittest.main()
