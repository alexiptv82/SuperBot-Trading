"""70-interfaccia.sh e 00-avvio-completo.sh con strumenti finti (nessun root, systemd, docker, nginx o rete)."""
import hashlib
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


def put(p, text, mode=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    if mode:
        p.chmod(mode)


def ui_env(tmp, active):
    web, bins = tmp / "web", tmp / "bin"
    put(web / "build/index.html", "old")
    put(web / "build/manifest.json", '{"m":1}')
    put(web / "build/service-worker.js", "sw")
    (tmp / "backups").mkdir()
    # systemctl finto: registra OGNI argomento ricevuto; attivi solo i servizi elencati
    put(bins / "systemctl", "#!/bin/sh\nshift\nfor a in \"$@\"; do echo \"$a\" >> %s/calls; done\n"
        "case \" %s \" in *\" $1 \"*) echo active;; *) echo inactive;; esac\n" % (tmp, " ".join(active)), 0o755)
    put(bins / "curl", "#!/bin/sh\nout=''; url=''\nwhile [ $# -gt 0 ]; do case \"$1\" in -o) out=\"$2\"; shift 2;; "
        "-w|--resolve|--max-time) shift 2;; -sS) shift;; *) url=\"$1\"; shift;; esac; done\n"
        "case \"$url\" in */) cp %s/build/index.html \"$out\"; printf 200;; */webauthn/status) echo '{}' > \"$out\"; "
        "printf 200;; */brain/config) printf 401;; *) printf 404;; esac\n" % web, 0o755)
    cand = tmp / "cand"
    put(cand / "index.html", "new")
    put(cand / "static/js/main.js", "'/api/v3/brain/status' '/api/v3/brain/close' 'BRAIN UNICO' '/api/auth/login' "
        "'/api/auth/webauthn/status'")
    files = sorted(p for p in cand.rglob("*") if p.is_file())
    put(cand / "SHA256SUMS", "".join("%s  ./%s\n" % (hashlib.sha256(p.read_bytes()).hexdigest(),
                                                     p.relative_to(cand)) for p in files))
    env = dict(os.environ, PATH="%s:%s" % (bins, os.environ["PATH"]), BRAIN_UI_TEST_MODE="1",
               BRAIN_UI_ROOT=str(web), BRAIN_UI_BACKUPS=str(tmp / "backups"))
    msha = hashlib.sha256((cand / "SHA256SUMS").read_bytes()).hexdigest()
    return env, cand, msha, web


def run_ui(env, cand, msha):
    return subprocess.run(["bash", str(HERE / "70-interfaccia.sh"), "--activate", "--candidate", str(cand),
                           "--manifest-sha", msha], capture_output=True, text=True, env=env, timeout=60)


EXIT, RUNNER = "superbot-brain-unico-rc1-exit.service", "superbot-brain-unico-rc1-runner.service"


def test_ui_release_checks_both_units_separately(tmp_path):
    env, cand, msha, web = ui_env(tmp_path, [EXIT, RUNNER])
    p = run_ui(env, cand, msha)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "RESULT=SUCCESS_UI_BRAIN_UNICO" in p.stdout
    calls = (tmp_path / "calls").read_text().splitlines()
    assert EXIT in calls and RUNNER in calls                     # due argomenti distinti, mai "exit runner" insieme
    assert all(" " not in c for c in calls)
    assert (web / "build/index.html").read_text() == "new"


def test_ui_release_refuses_if_one_unit_is_inactive(tmp_path):
    for active in ([EXIT], [RUNNER]):
        sub = tmp_path / active[0]
        sub.mkdir()
        env, cand, msha, web = ui_env(sub, active)
        p = run_ui(env, cand, msha)
        assert p.returncode == 2 and "REFUSED=BRAIN_UNICO_UNITS_NOT_ACTIVE" in p.stdout, p.stdout
        assert (web / "build/index.html").read_text() == "old"     # nulla pubblicato


def wrapper(tmp, ui_rc, rollback_rc=0):
    """00-avvio-completo.sh con i passi sostituiti da finti che registrano le chiamate."""
    d = tmp / "pc"
    src = (HERE / "00-avvio-completo.sh").read_text()
    for x in ('[ "$(id -u)" = 0 ] || nogo "serve root"',):
        assert x in src
        src = src.replace(x, "")
    put(d / "00.sh", src)
    log = tmp / "log"
    put(d / "comune.sh", "PY=python3\nRUN=%s\nRUN_ID=x\nLAB=/x\nU_EXIT=a\nU_RUN=b\nOLD_EXIT=c\n"
        "nogo() { echo \"NO-GO: $*\"; exit 1; }\n" % tmp)
    put(d / "50-unita.sh", "echo 50 >> %s\n" % log)
    put(d / "70-interfaccia.sh", "echo 70 >> %s\nexit %d\n" % (log, ui_rc))
    put(d / "30-controlli.sh", "exit 0\n")
    put(d / "brain_unico_web_cutover.py", "import sys\nopen(%r,'a').write(sys.argv[1]+'\\n')\n"
        "sys.exit(%d if sys.argv[1] == '--rollback' else 0)\n" % (str(log), rollback_rc))
    put(tmp / "mandate.json", '{"approved": false}')
    put(tmp / "pause.flag", "1")
    bins = tmp / "bin"
    put(bins / "systemctl", "#!/bin/sh\necho 1\n", 0o755)
    put(bins / "docker", "#!/bin/sh\nexit 0\n", 0o755)
    put(bins / "id", "#!/bin/sh\necho 0\n", 0o755)
    env = dict(os.environ, PATH="%s:%s" % (bins, os.environ["PATH"]))
    src2 = (d / "00.sh").read_text().replace("/root/avvio-brain-unico", str(tmp / "snap"))
    put(d / "00.sh", src2)
    p = subprocess.run(["sh", str(d / "00.sh"), "a" * 40, str(tmp), "b" * 64], capture_output=True, text=True,
                       env=env, timeout=60)
    return p, log.read_text().split()


def test_ui_failure_after_backend_cutover_restores_web_and_bridge(tmp_path):
    p, calls = wrapper(tmp_path, ui_rc=2)
    assert p.returncode == 1
    assert calls == ["50", "--deploy", "70", "--rollback"]
    assert "Web e bridge precedenti RIPRISTINATI" in p.stdout
    assert "PRONTO PER L'ATTIVAZIONE" not in p.stdout


def test_ui_failure_with_failed_restore_says_manual_restore_is_needed(tmp_path):
    p, calls = wrapper(tmp_path, ui_rc=2, rollback_rc=2)
    assert p.returncode == 1 and calls[-1] == "--rollback"
    assert "RIPRISTINO MANUALE NECESSARIO: sudo python3" in p.stdout


def test_success_path_does_not_roll_back(tmp_path):
    p, calls = wrapper(tmp_path, ui_rc=0)
    assert calls == ["50", "--deploy", "70"], p.stdout
    assert p.returncode == 0 and "PRONTO PER L'ATTIVAZIONE PAPER" in p.stdout
