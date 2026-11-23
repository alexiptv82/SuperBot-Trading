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
def _package(tmp, fail_at=None):
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
    for f in ("00-rilascio.sh", "90-rollback.sh"):
        shutil.copy(HERE / f, d / f)
    for step in ("05-rc1-pausa.sh", "10-preflight.sh", "20-backup.sh", "30-codice.sh", "40-run.sh", "50-unita.sh",
                 "70-interfaccia.sh", "80-paper.sh"):
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
    p = subprocess.run(["sh", str(d / "00-rilascio.sh"), "a" * 40, str(tmp), "b" * 64], capture_output=True, text=True,
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
