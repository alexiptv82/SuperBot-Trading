"""Pacchetto di rilascio Falco Evoluto + Brain Scalp: prove offline (nessun root, Docker, systemd reale o VPS)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "deploy" / "brain-unico" / "avvio"))
sys.path.insert(0, str(HERE))
import falco_scalp_web_cutover as cut  # noqa: E402
from backend.v3 import close_bridge_server as bridge  # noqa: E402
from backend.v3.compare_view import runs_from_env  # noqa: E402

# Unita' del bridge come e' installata oggi sulla VPS (letta con systemctl cat il 23/11/2026).
LIVE_UNIT = """[Service]
ExecStart=/usr/bin/docker run --rm --name superbot-rc84-paper-close-bridge --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --user 0 --pids-limit 64 --memory 256m --tmpfs /tmp:rw,noexec,nosuid,size=8m -v /run/superbot-paper-close:/run/superbot-paper-close:rw -v /opt/superbot-v3-paper-runs/classic-hawk-paper20261111:/opt/superbot-v3-paper-runs/classic-hawk-paper20261111:rw -v /opt/superbot-v3-paper-runs/classic-bull-paper20261111:/opt/superbot-v3-paper-runs/classic-bull-paper20261111:rw -v /opt/superbot-v3-paper-runs/brain-v3-unico-paper-rc1:/opt/superbot-v3-paper-runs/brain-v3-unico-paper-rc1:rw -w /app -e PYTHONPATH=/app:/app/backend -e PYTHONDONTWRITEBYTECODE=1 -e DESK_MODE=paper -e TRADING_MODE=paper -e V3_CUTOVER_READONLY=1 -e V3_ALLOW_CLASSIC_SINGLE_CLOSE=1 -e V3_ALLOW_BRAIN_SINGLE_CLOSE=1 -e V3_CLOSE_BRIDGE_ONLY=1 -e V3_CLOSE_BRIDGE_SOCKET=/run/superbot-paper-close/close.sock -e V3_BRIDGE_BRAIN_RUN_DIR=brain-v3-unico-paper-rc1 -e V3_BRIDGE_BRAIN_RUN_ID=brain-unico-paper-rc1 --entrypoint python3 superbot:brain-unico-web-9b1532780fe6 -m backend.v3.close_bridge_server
ExecStop=/usr/bin/docker stop -t 8 superbot-rc84-paper-close-bridge
"""


def test_bridge_unit_adds_only_the_two_runs_and_their_variable():
    img = cut.bridge_image(LIVE_UNIT)
    assert img == "superbot:brain-unico-web-9b1532780fe6"
    new = cut.bridge_unit_text(LIVE_UNIT, "superbot:falco-scalp-web-abcdef123456", img)
    for keep in ("classic-hawk-paper20261111:rw", "classic-bull-paper20261111:rw", "brain-v3-unico-paper-rc1:rw",
                 "-e V3_BRIDGE_BRAIN_RUN_ID=brain-unico-paper-rc1", "--network none", "--read-only", "--cap-drop ALL"):
        assert keep in new
    for run in ("brain-v3-falco-evoluto-p1", "brain-v3-brain-scalp-p1"):
        assert f"-v /opt/superbot-v3-paper-runs/{run}:/opt/superbot-v3-paper-runs/{run}:rw" in new
    assert "superbot:brain-unico-web-9b1532780fe6" not in new and new.count("superbot:falco-scalp-web-abcdef123456") == 1
    # la variabile che finisce nell'unita' e' esattamente quella che il bridge sa leggere
    value = new.split("-e V3_BRIDGE_EXTRA_RUNS=", 1)[1].split(" ", 1)[0]
    assert '"' not in value and "'" not in value
    got = bridge._extra_from_env({"V3_BRIDGE_EXTRA_RUNS": value})
    assert got == {"falco_evoluto": (bridge.RUN_ROOT / "brain-v3-falco-evoluto-p1", "falco-evoluto-paper-p1"),
                   "brain_scalp": (bridge.RUN_ROOT / "brain-v3-brain-scalp-p1", "brain-scalp-paper-p1")}
    # gia' applicata, immagine diversa o unita' inattesa: rifiuto
    for bad, image in ((new, "superbot:falco-scalp-web-abcdef123456"), (LIVE_UNIT, "superbot:other"),
                       (LIVE_UNIT.replace("V3_BRIDGE_BRAIN_RUN_ID=brain-unico-paper-rc1", "X=1"), img)):
        with pytest.raises(cut.Refused):
            cut.bridge_unit_text(bad, "superbot:falco-scalp-web-1", image)


def _web(mounts, env):
    return {"Mounts": mounts, "Config": {"Env": [f"{k}={v}" for k, v in env.items()]}}


RC1_ENV = {**cut.base.REQUIRED_ENV, **cut.base.new_run_env(), "DB_PATH": "/app/data/superbot.db"}
MOUNTS = [{"Destination": "/app/data", "Type": "bind", "RW": True, "Source": "/opt/superbot/data"},
          {"Destination": cut.RC1_RUN, "Type": "bind", "RW": False, "Source": cut.RC1_RUN}]


def test_web_gets_only_the_compare_variable_and_two_read_only_mounts():
    env = cut.target_env(RC1_ENV)
    assert set(env) - set(RC1_ENV) == {"V3_COMPARE_RUNS"} and all(env[k] == v for k, v in RC1_ENV.items())
    refs = runs_from_env({"V3_COMPARE_RUNS": env["V3_COMPARE_RUNS"]})
    assert [(r.name, r.run_id, str(r.dir)) for r in refs] == [
        ("falco_evoluto", "falco-evoluto-paper-p1", "/opt/superbot-v3-paper-runs/brain-v3-falco-evoluto-p1"),
        ("brain_scalp", "brain-scalp-paper-p1", "/opt/superbot-v3-paper-runs/brain-v3-brain-scalp-p1")]
    for bad in ({**RC1_ENV, "V3_RUN_ID": "other"}, {**RC1_ENV, "V3_COMPARE_RUNS": "[]"},
                {**RC1_ENV, "V3_CUTOVER_READONLY": "0"}):
        with pytest.raises(cut.Refused):
            cut.target_env(bad)
    web = _web(MOUNTS, RC1_ENV)
    added = cut.expected_mounts(web) - cut.base.mount_tuples(web)
    assert added == {(r, "bind", False, r) for r in cut.run_dirs()}
    args = cut.mount_args(web, force_ro=False)
    assert "/opt/superbot/data:/app/data:rw" in args and all(f"{r}:{r}:ro" in args for r in cut.run_dirs())
    assert all(":rw" not in a for a in args if "falco-evoluto" in a or "brain-scalp" in a)
    with pytest.raises(cut.Refused):                          # una run nuova gia' montata in scrittura nella web
        cut.needs_mount(_web([{"Destination": cut.RUN_ROOT, "Type": "bind", "RW": True, "Source": cut.RUN_ROOT}],
                             RC1_ENV), cut.run_dirs()[0])


def test_create_args_reuse_the_rc1_construction_with_this_release_name_and_mounts():
    web = {**_web(MOUNTS, RC1_ENV), "HostConfig": {"SecurityOpt": ["no-new-privileges"]},
           "Config": {"Env": [], "User": "app", "WorkingDir": "/app", "Labels": {"a": "b"}}}
    args = cut.create_args(web, "superbot:falco-scalp-web-x", Path("/run/env"))
    assert args[args.index("--name") + 1] == cut.NEW_TMP and args[-1] == "superbot:falco-scalp-web-x"
    assert args.count("-v") == len(MOUNTS) + 2 and "--security-opt" in args and "--label" in args


# ------------------------------------------------------------------ orchestratore con passi finti
def _package(tmp, fail_at=None, main="00-rilascio.sh"):
    d = tmp / "pkg"
    d.mkdir()
    log = tmp / "log"
    backups = tmp / "backups"
    rc1 = tmp / "rc1"
    rc1.mkdir()
    (rc1 / "pause.flag").write_text("p")
    src = (HERE / "comune.sh").read_text().replace("BACKUPS=/opt/superbot-v3-backups/falco-scalp", f"BACKUPS={backups}")
    src = src.replace("RC1_RUN=$PARENT/brain-v3-unico-paper-rc1", f"RC1_RUN={rc1}")
    (d / "comune.sh").write_text(src)
    for f in (main, "90-rollback.sh"):
        shutil.copy(HERE / f, d / f)
    (tmp / "runs").mkdir(exist_ok=True)
    src2 = (d / "comune.sh").read_text().replace("PARENT=/opt/superbot-v3-paper-runs", f"PARENT={tmp / 'runs'}")
    (d / "comune.sh").write_text(src2)
    for r in ("brain-v3-falco-evoluto-p1", "brain-v3-brain-scalp-p1"):
        (tmp / "runs" / r).mkdir(exist_ok=True)
        (tmp / "runs" / r / "journal.db").write_text("journal")
    for step in ("05-rc1-pausa.sh", "10-preflight.sh", "15-ripresa-preflight.sh", "20-backup.sh", "30-codice.sh",
                 "35-verifica-run.sh", "40-run.sh", "50-unita.sh", "70-interfaccia.sh", "80-paper.sh"):
        code = 1 if step == fail_at else 0
        (d / step).write_text(f"echo {step} \"$@\" >> {log}\nexit {code}\n")
    code = 1 if fail_at == "web" else 0
    (d / "falco_scalp_web_cutover.py").write_text(
        f"import sys\nopen({str(log)!r},'a').write('cutover '+' '.join(sys.argv[1:2])+'\\n')\n"
        f"sys.exit({code} if sys.argv[1] == '--deploy' else 0)\n")
    bins = tmp / "bin"
    bins.mkdir()
    for name, body in (("id", "echo 0"), ("systemctl", f"echo systemctl \"$@\" >> {log}; echo active"),
                       ("curl", "printf 401")):
        (bins / name).write_text(f"#!/bin/sh\n{body}\n")
        (bins / name).chmod(0o755)
    env = dict(os.environ, PATH=f"{bins}:{os.environ['PATH']}")
    p = subprocess.run(["sh", str(d / main), "a" * 40, str(tmp), "b" * 64], capture_output=True, text=True,
                       env=env, timeout=60)
    return p, (log.read_text() if log.exists() else ""), backups


def test_success_path_records_every_step_and_never_rolls_back(tmp_path):
    p, log, backups = _package(tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "ESITO RILASCIO: PRONTO PER IL COLLAUDO PAPER" in p.stdout
    assert "cutover --rollback" not in log and "--rollback" not in log
    assert (backups / "rilascio.state").read_text().split() == ["codice", "run", "unita_avviate", "unita",
                                                               "web_avviato", "web", "ui"]
    assert log.index("05-rc1-pausa.sh") < log.index("10-preflight.sh")        # RC1 in pausa prima di tutto


def test_web_failure_rolls_back_web_and_stops_the_new_units_keeping_runs(tmp_path):
    p, log, backups = _package(tmp_path, fail_at="web")
    assert p.returncode == 1 and "ESITO RILASCIO: NO-GO (web e bridge)" in p.stdout
    assert "cutover --rollback" in log and "70-interfaccia.sh --rollback" not in log   # interfaccia mai cambiata
    for u in ("superbot-falco-evoluto-p1-runner.service", "superbot-brain-scalp-p1-exit.service"):
        assert f"systemctl stop {u}" in log
    assert not (backups / "rilascio.state").exists()                          # stato chiuso (rinominato)


def test_preflight_failure_changes_nothing(tmp_path):
    p, log, backups = _package(tmp_path, fail_at="10-preflight.sh")
    assert p.returncode == 1 and "NO-GO: preflight" in p.stdout
    assert "30-codice.sh" not in log and "cutover" not in log and not (backups / "rilascio.state").exists()


def test_ui_failure_restores_ui_web_and_units(tmp_path):
    p, log, _ = _package(tmp_path, fail_at="70-interfaccia.sh")
    assert p.returncode == 1 and "cutover --rollback" in log
    assert "70-interfaccia.sh --activate" in log and "systemctl stop superbot-falco-evoluto-p1-exit.service" in log


# ------------------------------------------------------------------ 80-paper.sh con il vero controllo del mandato
def test_owner_activation_and_revocation_per_run(tmp_path):
    from backend.v3.runner.prepare_paper_run import prepare_new_paper_run
    runs = tmp_path / "runs"
    runs.mkdir()
    root = prepare_new_paper_run(parent=runs, run_name="brain-v3-falco-evoluto-p1", run_id="falco-evoluto-paper-p1",
                                 config_bytes=(REPO / "backend/v3/runner/runner_config_falco_evoluto_paper.json")
                                 .read_bytes(), desk_mode="paper", now_ms=int(time.time() * 1000),
                                 expected_initial_equity="1000")
    d = tmp_path / "pkg"
    d.mkdir()
    aienv = tmp_path / "ai.env"
    aienv.write_text("DEEPSEEK_API_KEY=x\n")
    src = (HERE / "comune.sh").read_text().replace("PARENT=/opt/superbot-v3-paper-runs", f"PARENT={runs}")
    src = src.replace("PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3", f"PY={sys.executable}")
    src = src.replace("AIENV=/etc/superbot-v3-paper/brain-ai.env", f"AIENV={aienv}")
    (d / "comune.sh").write_text(src)
    shutil.copy(HERE / "80-paper.sh", d / "80-paper.sh")
    (d / "controlli.py").write_text("print('USCITE: SANE')\n")
    bins = tmp_path / "bin"
    bins.mkdir()
    (bins / "id").write_text("#!/bin/sh\necho 0\n")
    (bins / "systemctl").write_text(f"#!/bin/sh\ncase \"$1\" in is-active) echo active;; show) case \"$3\" in "
                                    f"WorkingDirectory) echo {REPO};; *) echo DESK_MODE=paper;; esac;; esac\n")
    for b in bins.iterdir():
        b.chmod(0o755)
    env = dict(os.environ, PATH=f"{bins}:{os.environ['PATH']}")

    def run(*a):
        return subprocess.run(["sh", str(d / "80-paper.sh"), *a], capture_output=True, text=True, env=env, timeout=60)
    p = run("falco", "attiva", "Proprietario")
    assert p.returncode == 0, p.stdout + p.stderr
    m = json.loads((root / "mandate.json").read_text())
    assert m["approved"] is True and m["approved_by"] == "Proprietario" and not (root / "pause.flag").exists()
    assert "mandato: VALIDO" in p.stdout
    p = run("falco", "revoca")
    assert p.returncode == 0 and json.loads((root / "mandate.json").read_text())["approved"] is False
    assert (root / "pause.flag").exists()
    assert run("scalp", "stato").returncode != 0                              # l'altra run non esiste qui: rifiuto
    assert run("falco", "attiva", "").returncode != 0                         # serve un nome


def test_compare_probe_reports_the_application_code_and_checks_the_real_gate(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("compare_probe_t", HERE / "compare_probe.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    assert probe.why(b'{"detail": {"code": "posizione_non_aperta", "message": "x"}}') == "posizione_non_aperta"
    assert probe.why(b'{"ok": false, "message": "Collaudo V3 in sola lettura: comandi trading disattivati"}') == \
        "gate_sola_lettura"
    assert probe.why(b'{"detail": {"code": "<script>"}}') == "sconosciuto" and probe.why(b"nope") == "non_json"
    env = {"V3_CUTOVER_READONLY": "1", "V3_ALLOW_BRAIN_SINGLE_CLOSE": "1", "TRADING_MODE": "paper",
           "DESK_MODE": "paper", "V3_CLOSE_BRIDGE_ONLY": "1",
           "V3_CLOSE_BRIDGE_SOCKET": "/run/superbot-paper-close/close.sock"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    probe.check_gate()                                       # con il gate corretto: nessun errore
    monkeypatch.setenv("V3_ALLOW_BRAIN_SINGLE_CLOSE", "0")   # interruttore spento: il gate blocca -> la sonda fallisce
    with pytest.raises(SystemExit):
        probe.check_gate()


# ------------------------------------------------------------------ ripresa dopo il NO-GO del 23/11
def test_resume_reuses_the_runs_never_prepares_new_ones_and_backs_them_up(tmp_path):
    p, log, backups = _package(tmp_path, main="00-ripresa.sh")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "ESITO RILASCIO: PRONTO PER IL COLLAUDO PAPER" in p.stdout
    assert "40-run.sh" not in log and "10-preflight.sh" not in log
    assert log.index("15-ripresa-preflight.sh") < log.index("30-codice.sh") < log.index("35-verifica-run.sh") \
        < log.index("50-unita.sh")
    copies = list(backups.glob("runs-before-ripresa-*"))
    assert len(copies) == 1 and (copies[0] / "brain-v3-falco-evoluto-p1" / "journal.db").read_text() == "journal"
    assert (backups / "rilascio.state").read_text().split() == ["codice", "unita_avviate", "unita", "web_avviato",
                                                               "web", "ui"]


def test_resume_failure_rolls_back_without_touching_the_runs(tmp_path):
    p, log, backups = _package(tmp_path, fail_at="web", main="00-ripresa.sh")
    assert p.returncode == 1 and "cutover --rollback" in log
    assert (tmp_path / "runs" / "brain-v3-falco-evoluto-p1" / "journal.db").read_text() == "journal"
    p, log, _ = _package(tmp_path / "x" if (tmp_path / "x").mkdir() is None else None,
                         fail_at="35-verifica-run.sh", main="00-ripresa.sh")
    assert p.returncode == 1 and "50-unita.sh" not in log and "verifica delle run riusate" in p.stdout


def _real_runs(tmp_path):
    from backend.v3.runner.prepare_paper_run import prepare_new_paper_run
    runs = tmp_path / "runs"
    runs.mkdir()
    for name, rid, cfg, eq in (("brain-v3-falco-evoluto-p1", "falco-evoluto-paper-p1",
                                "runner_config_falco_evoluto_paper.json", "1000"),
                               ("brain-v3-brain-scalp-p1", "brain-scalp-paper-p1",
                                "runner_config_brain_scalp_paper.json", "2000")):
        prepare_new_paper_run(parent=runs, run_name=name, run_id=rid,
                              config_bytes=(REPO / "backend/v3/runner" / cfg).read_bytes(), desk_mode="paper",
                              now_ms=int(time.time() * 1000), expected_initial_equity=eq)
    return runs


def _real_pkg(tmp_path, runs, stage):
    d = tmp_path / "pkg"
    d.mkdir()
    src = (HERE / "comune.sh").read_text().replace("PARENT=/opt/superbot-v3-paper-runs", f"PARENT={runs}")
    src = src.replace("PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3", f"PY={sys.executable}")
    src = src.replace("LAB=/home/superbot-agent/brain-unico-lab/wt-fe", f"LAB={REPO}")
    src = src.replace('stage_of() { echo "/opt/superbot-falco-scalp-$(printf \'%s\' "$1" | cut -c1-12)"; }',
                      f'stage_of() {{ echo "{stage}"; }}')
    (d / "comune.sh").write_text(src)
    for f in ("15-ripresa-preflight.sh", "35-verifica-run.sh"):
        shutil.copy(HERE / f, d / f)
    bins = tmp_path / "bin"
    bins.mkdir()
    for name, body in (("id", "echo 0"), ("systemctl", "echo active"), ("curl", "printf 200"),
                       ("docker", 'case "$2" in superbot) echo true;; *) exit 1;; esac')):
        (bins / name).write_text(f"#!/bin/sh\n{body}\n")
        (bins / name).chmod(0o755)
    return d, dict(os.environ, PATH=f"{bins}:{os.environ['PATH']}")


def test_resume_preflight_and_journal_check_on_real_runs(tmp_path):
    runs = _real_runs(tmp_path)
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    d, env = _real_pkg(tmp_path, runs, REPO)
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("x")
    (ui / "SHA256SUMS").write_text(subprocess.run(["sha256sum", "./index.html"], cwd=ui, capture_output=True,
                                                  text=True).stdout)
    uisha = subprocess.run(["sha256sum", str(ui / "SHA256SUMS")], capture_output=True, text=True).stdout.split()[0]
    aienv = tmp_path / "ai.env"
    aienv.write_text("DEEPSEEK_API_KEY=x\n")
    (d / "comune.sh").write_text((d / "comune.sh").read_text().replace(
        "AIENV=/etc/superbot-v3-paper/brain-ai.env", f"AIENV={aienv}"))
    src = (d / "15-ripresa-preflight.sh").read_text().replace(
        '[ ! -e "$STAGE" ] || nogo "$STAGE esiste gia\'"', ":").replace(
        "/etc/systemd/system/superbot-v3-paper-single-close-bridge.service", str(tmp_path / "bridge.service")).replace(
        "/etc/systemd/system/", str(tmp_path / "no-units") + "/")             # isolato dalle unita' reali della VPS
    (tmp_path / "bridge.service").write_text("ExecStart=docker run x\n")
    (d / "15-ripresa-preflight.sh").write_text(src)

    def pre():
        return subprocess.run(["sh", str(d / "15-ripresa-preflight.sh"), head, str(ui), uisha], capture_output=True,
                              text=True, env=env, timeout=60)
    p = pre()
    assert p.returncode == 0, p.stdout + p.stderr
    assert p.stdout.count("intatta") == 2
    p = subprocess.run(["sh", str(d / "35-verifica-run.sh"), head], capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0 and "catena integra, aperture/chiusure: 0" in p.stdout, p.stdout + p.stderr
    # mandato approvato, configurazione cambiata, run mancante: rifiuto (nessuna modifica fatta dal preflight)
    f = runs / "brain-v3-falco-evoluto-p1"
    m = json.loads((f / "mandate.json").read_text())
    (f / "mandate.json").write_text(json.dumps({**m, "approved": True}))
    assert pre().returncode == 1
    (f / "mandate.json").write_text(json.dumps(m))
    cfg = (f / "runner_config.json").read_text()
    (f / "runner_config.json").write_text(cfg.replace('"initial_equity": "1000"', '"initial_equity": "1001"'))
    assert pre().returncode == 1
    (f / "runner_config.json").write_text(cfg)
    assert pre().returncode == 0
    shutil.move(str(runs / "brain-v3-brain-scalp-p1"), str(tmp_path / "moved"))
    assert pre().returncode == 1 and "assente" in pre().stdout
    shutil.move(str(tmp_path / "moved"), str(runs / "brain-v3-brain-scalp-p1"))
    # un'apertura registrata nel journal: la run non e' piu' "senza operazioni" -> rifiuto della verifica
    from backend.v3.events import Event, EventJournal
    EventJournal(f / "journal.db").append(Event("paper_open.x", "brain", "falco-evoluto-paper-p1", "paper_open",
                                                int(time.time() * 1000), "test", {"position_id": "x"}))
    p = subprocess.run(["sh", str(d / "35-verifica-run.sh"), head], capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 1 and "NO-GO" in p.stdout


# ------------------------------------------------------------------ aggiornamento mirato del codice (60)
UNIT_NAMES = ("superbot-falco-evoluto-p1-exit.service", "superbot-falco-evoluto-p1-runner.service",
              "superbot-brain-scalp-p1-exit.service", "superbot-brain-scalp-p1-runner.service")


def _update_env(tmp_path, *, fail_on="", contracts_ok=True, unpause=False):
    runs = _real_runs(tmp_path)
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    old = tmp_path / "opt" / "superbot-falco-scalp-aaaaaaaaaaaa"
    (old / "backend").mkdir(parents=True)
    units, bins, log, d = tmp_path / "units", tmp_path / "bin", tmp_path / "log", tmp_path / "pkg"
    for x in (units, bins, d):
        x.mkdir()
    for u in UNIT_NAMES:
        (units / u).write_text(f"[Service]\nWorkingDirectory={old}\nEnvironment=PYTHONPATH={old}\n"
                               f"ExecStart=/usr/bin/env DESK_MODE=paper py -m backend.v3.runner.x --data-dir {runs}/r\n")
    rc1 = tmp_path / "rc1"
    rc1.mkdir()
    (rc1 / "pause.flag").write_text("p")
    if unpause:
        (runs / "brain-v3-brain-scalp-p1" / "pause.flag").unlink()
    src = (HERE / "comune.sh").read_text()
    for a, b in (("PARENT=/opt/superbot-v3-paper-runs", f"PARENT={runs}"),
                 ("PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3", f"PY={sys.executable}"),
                 ("LAB=/home/superbot-agent/brain-unico-lab/wt-fe", f"LAB={REPO}"),
                 ("BACKUPS=/opt/superbot-v3-backups/falco-scalp", f"BACKUPS={tmp_path / 'backups'}"),
                 ("RC1_RUN=$PARENT/brain-v3-unico-paper-rc1", f"RC1_RUN={rc1}"),
                 ('echo "/opt/superbot-falco-scalp-', f'echo "{tmp_path}/opt/superbot-falco-scalp-')):
        assert a in src
        src = src.replace(a, b)
    (d / "comune.sh").write_text(src)
    s60 = (HERE / "60-aggiorna-codice.sh").read_text().replace("/etc/systemd/system", str(units)).replace(
        "^/opt/superbot-falco-scalp-[0-9a-f]{12}$", f"^{tmp_path}/opt/superbot-falco-scalp-[0-9a-f]{{12}}$")
    (d / "60-aggiorna-codice.sh").write_text(s60)
    (d / "30-codice.sh").write_text(f'. "$(dirname "$0")/comune.sh"\nN=$(stage_of "$1"); mkdir -p "$N"; '
                                    f'ln -s {REPO}/backend "$N/backend"; echo 30 >> {log}\n')
    (d / "controlli.py").write_text("print('USCITE: SANE')\n")
    (d / "contratti_check.py").write_text(f"import sys\nprint('regole 8/8')\nsys.exit({0 if contracts_ok else 1})\n")
    (bins / "id").write_text("#!/bin/sh\necho 0\n")
    (bins / "systemctl").write_text(
        f'#!/bin/sh\necho "systemctl $*" >> {log}\n'
        f'case "$1" in is-active) echo active;; show) sed -n "s/^WorkingDirectory=//p" {units}/"$5";; '
        f'*) [ "$*" = "{fail_on}" ] && exit 1; exit 0;; esac\n')
    for b in bins.iterdir():
        b.chmod(0o755)
    env = dict(os.environ, PATH=f"{bins}:{os.environ['PATH']}")
    p = subprocess.run(["sh", str(d / "60-aggiorna-codice.sh"), head], capture_output=True, text=True, env=env,
                       timeout=120)
    return p, (log.read_text() if log.exists() else ""), units, runs, old, tmp_path / "opt" / f"superbot-falco-scalp-{head[:12]}"


def _snapshot(runs):
    return {p.relative_to(runs): p.read_bytes() for p in runs.rglob("*") if p.is_file()}


def test_code_update_changes_only_the_code_folder_and_keeps_runs_paused(tmp_path):
    p, log, units, runs, old, new = _update_env(tmp_path)
    assert p.returncode == 0 and "ESITO AGGIORNAMENTO: OK" in p.stdout, p.stdout + p.stderr
    for u in UNIT_NAMES:
        text = (units / u).read_text()
        assert str(new) in text and str(old) not in text
        assert text.replace(str(new), str(old)) == (tmp_path / "backups").glob("aggiorna-*").__next__().joinpath(u).read_text()
    # ordine sicuro per ogni bot: runner fermo, uscite riavviate e sane, poi runner
    for exit_u, run_u in ((UNIT_NAMES[0], UNIT_NAMES[1]), (UNIT_NAMES[2], UNIT_NAMES[3])):
        assert log.index(f"stop {run_u}") < log.index(f"restart {exit_u}") < log.index(f"start {run_u}")
    rc1_cmds = [l for l in log.splitlines() if "brain-unico-rc1" in l]
    assert rc1_cmds and all(l.startswith("systemctl is-active") for l in rc1_cmds)   # RC1 solo letto, mai toccato
    for r in ("brain-v3-falco-evoluto-p1", "brain-v3-brain-scalp-p1"):
        assert (runs / r / "pause.flag").exists()
        assert json.loads((runs / r / "mandate.json").read_text())["approved"] is False


def test_incomplete_contract_rules_stop_before_touching_the_units(tmp_path):
    p, log, units, runs, old, new = _update_env(tmp_path, contracts_ok=False)
    assert p.returncode == 1 and "regole dei contratti incomplete" in p.stdout
    assert all(str(old) in (units / u).read_text() for u in UNIT_NAMES) and "restart" not in log


def test_a_failed_restart_restores_the_previous_units(tmp_path):
    p, log, units, runs, old, new = _update_env(tmp_path, fail_on="restart superbot-brain-scalp-p1-exit.service")
    assert p.returncode == 1 and "ESITO AGGIORNAMENTO: NO-GO" in p.stdout and "ROLLBACK" in p.stdout
    assert all(str(old) in (units / u).read_text() and str(new) not in (units / u).read_text() for u in UNIT_NAMES)


def test_update_refuses_a_run_that_is_not_paused(tmp_path):
    p, log, units, runs, old, new = _update_env(tmp_path, unpause=True)
    assert p.returncode == 1 and "pausa assente" in p.stdout and "30" not in log
