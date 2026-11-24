"""Ripartenza con il Brain unico PAPER 2000: procedura completa in cartelle finte con il codice VERO (run vecchie
preparate dal codice, posizione aperta chiusa dal canale manuale vero, unita' spostate sul codice nuovo, run nuova
preparata e letta dalla dashboard vera, rollback con impronte verificate)."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import threading
import time
from decimal import Decimal as D
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from backend.v3.events import EventJournal  # noqa: E402
from backend.v3.runner.prepare_paper_run import prepare_new_paper_run  # noqa: E402

RUNNER = ROOT / "backend" / "v3" / "runner"
F, S, U = ("runner_config_falco_evoluto_paper.json", "runner_config_brain_scalp_paper.json",
           "runner_config_brain_unico_2000_paper.json")
UNITS = ("superbot-falco-evoluto-p1-exit.service", "superbot-falco-evoluto-p1-runner.service",
         "superbot-brain-scalp-p1-exit.service", "superbot-brain-scalp-p1-runner.service")

FAKE_SYSTEMCTL = r"""#!/bin/sh
cmd="$1"; shift
case "$cmd" in
  show) u="$4"; sed -n 's/^WorkingDirectory=//p' "$FAKE_UNITS/$u" 2>/dev/null ;;
  is-active) shift; [ ! -e "$FAKE_SD/$1.stopped" ] ;;
  stop) touch "$FAKE_SD/$1.stopped"; echo "stop $1" >> "$FAKE_SD/calls" ;;
  daemon-reload|disable|enable) echo "$cmd $*" >> "$FAKE_SD/calls" ;;
  start) rm -f "$FAKE_SD/$1.stopped"; echo "start $1" >> "$FAKE_SD/calls"
    case "$1" in
      *falco-evoluto-p1-runner*) "$FAKE_PY" "$FAKE_SD/beat.py" "$FAKE_RUNS/brain-v3-falco-evoluto-p1" ;;
      *brain-scalp-p1-runner*) "$FAKE_PY" "$FAKE_SD/beat.py" "$FAKE_RUNS/brain-v3-brain-scalp-p1" ;;
    esac ;;
esac
"""
BEAT = r"""import json, os, sys, time
run = sys.argv[1]
m = json.load(open(os.path.join(run, 'mandate.json')))
st = 'halted' if m.get('approved') is not True else ('paused' if os.path.exists(os.path.join(run, 'pause.flag')) else 'running')
if os.path.exists(os.path.join(os.environ['FAKE_SD'], 'runner_fails')): st = 'halted'
json.dump({'ts_ms': int(time.time()*1000) + 2, 'state': st,
           'last_error': None if st != 'halted' else 'halted:mandate_not_approved'}, open(os.path.join(run, 'heartbeat.json'), 'w'))
"""
FAKE_80 = r"""#!/bin/sh
case "$1" in falco) RUN=$FAKE_RUNS/brain-v3-falco-evoluto-p1 ;; scalp) RUN=$FAKE_RUNS/brain-v3-brain-scalp-p1 ;; esac
case "$2" in
  pausa) echo pausa > "$RUN/pause.flag"; "$FAKE_PY" "$FAKE_SD/beat.py" "$RUN"; echo "PAUSA ATTIVA" ;;
  attiva) "$FAKE_PY" -c "import json,sys; p=sys.argv[1]; m=json.load(open(p)); m['approved']=True; m['approved_by']=sys.argv[2]; json.dump(m,open(p,'w'))" "$RUN/mandate.json" "$3"
    rm -f "$RUN/pause.flag"; "$FAKE_PY" "$FAKE_SD/beat.py" "$RUN"; echo "PAPER ATTIVO $3" ;;
esac
"""
FAKE_DOCKER = "#!/bin/sh\necho running\n"


def _old_run(parent: Path, name: str, run_id: str, cfg: str, equity: str, with_position: bool):
    from backend.tests.test_brain_f7_outcomes import _hand
    from backend.v3.executor.paper import execute_paper
    root = prepare_new_paper_run(parent=parent, run_name=name, run_id=run_id, config_bytes=(RUNNER / cfg).read_bytes(),
                                 desk_mode="paper", now_ms=int(time.time() * 1000) - 7_200_000,
                                 expected_initial_equity=equity)
    m = json.loads((root / "mandate.json").read_text())
    (root / "mandate.json").write_text(json.dumps(dict(m, approved=True, approved_by="Proprietario Test")))
    (root / "pause.flag").unlink()
    if with_position:
        j = EventJournal(str(root / "journal.db"))
        execute_paper(_hand(side=1, entry="30000", stop="29000", symbol="BTCUSDT"), portfolio_id="brain",
                      run_id=run_id, journal=j, now_ms=int(time.time() * 1000) - 3_600_000)
    (root / "daily_loss.json").write_text('{"latch": "vecchio"}')
    return root


class Rig:
    pass


@pytest.fixture
def rig(tmp_path, monkeypatch):
    r = Rig()
    r.runs, r.sd, fsd, r.state, r.units, r.old = (tmp_path / n for n in ("runs", "sd", "fsd", "state", "units", "old"))
    for d in (r.runs, r.sd, fsd, r.units, r.old):
        d.mkdir()
    (r.runs / "brain-v3-unico-paper-rc1").mkdir()
    (r.runs / "brain-v3-unico-paper-rc1" / "pause.flag").write_text("rc1")
    r.falco = _old_run(r.runs, "brain-v3-falco-evoluto-p1", "falco-evoluto-paper-p1", F, "1000", False)
    r.scalp = _old_run(r.runs, "brain-v3-brain-scalp-p1", "brain-scalp-paper-p1", S, "2000", True)
    for u in UNITS:
        (r.units / u).write_text(f"[Service]\nWorkingDirectory={r.old}\nEnvironment=PYTHONPATH={r.old}\n"
                                 f"ExecStart=/usr/bin/env python -m x --data-dir y\n")
    for name, text in (("systemctl", FAKE_SYSTEMCTL), ("docker", FAKE_DOCKER)):
        (r.sd / name).write_text(text)
        (r.sd / name).chmod(0o755)
    (r.sd / "beat.py").write_text(BEAT)
    (fsd / "80-paper.sh").write_text(FAKE_80)
    (fsd / "comune.sh").write_text("# finto\n")
    (fsd / "controlli.py").write_text("print('USCITE: SANE')\n")
    pinned = {f: hashlib.sha256((fsd / f).read_bytes()).hexdigest() for f in ("80-paper.sh", "comune.sh", "controlli.py")}
    env = dict(RIP_TEST_MODE="1", RIP_PARENT=str(r.runs), RIP_FSD=str(fsd), RIP_STATE=str(r.state),
               RIP_UNIT_DIR=str(r.units), RIP_SYSTEMCTL=str(r.sd / "systemctl"), RIP_DOCKER=str(r.sd / "docker"),
               RIP_POLL_S="0.05", RIP_PINNED=json.dumps(pinned), FAKE_UNITS=str(r.units), FAKE_SD=str(r.sd),
               FAKE_RUNS=str(r.runs), FAKE_PY=sys.executable, PYTHONPATH=str(ROOT), RIP_CONFIG=str(RUNNER / U))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.chdir(ROOT)                              # si esegue dalla cartella del codice nuovo
    r.rp = importlib.reload(importlib.import_module("ripartenza_brain"))
    stop = threading.Event()

    def exit_service():                                  # finto processo delle uscite, chiusure con il codice vero
        from backend.v3.runner.manual_close import run_manual_close
        while not stop.is_set():
            for run, rid in ((r.falco, "falco-evoluto-paper-p1"), (r.scalp, "brain-scalp-paper-p1")):
                if (run / "close_request.json").exists() and (run / "journal.db").exists():
                    run_manual_close(journal=EventJournal(str(run / "journal.db")), portfolio_id="brain", run_id=rid,
                                     data_dir=run, price_of=lambda s, n: D("29500"), fee_bps=6,
                                     now_ms=int(time.time() * 1000))
            time.sleep(0.02)
    t = threading.Thread(target=exit_service, daemon=True)
    t.start()
    yield r
    stop.set()
    t.join(2)


def _events(run: Path, rid: str):
    return [x.event for x in EventJournal(str(run / "journal.db")).list_run("brain", rid)]


def test_pinned_activation_scripts_are_those_checked_by_superbot_ops():
    rp = importlib.import_module("ripartenza_brain")
    sops = (ROOT / "deploy/falco-evoluto/admin/superbot-ops").read_text()
    for f, h in {"80-paper.sh": "0fc1e6e1ee74ea50b890dc2c6917238a3d84b87b1bb9429c0e173b079182d0f1",
                 "comune.sh": "c639a85c6e37ec03adc748586977817aee633e17848d9457adae1f652a3a66e0",
                 "controlli.py": "638c4da73615e11439d4e92f89890b5ca92c031b7df789d358d2d92fe7210afd"}.items():
        assert f'pinned "$FSD" {f} {h}' in sops and rp.PINNED.get(f, h) == h


def test_full_restart_with_the_single_brain_and_rollback(rig, capsys):
    rp = rig.rp
    assert rp.main(["--controlla", "--stage", str(ROOT)]) == 0
    assert rp.main(["--esegui", "--stage", str(ROOT)]) == 0
    out = capsys.readouterr().out
    assert "RIPARTENZA RESULT=BRAIN_UNICO_PAPER_RUNNING" in out, out
    assert "CONTABILIZZATA_scalp=chiuse 1, aperte 0" in out and "VISTA=run nuova leggibile" in out
    base = next(p for p in (rig.runs / ".archivio").iterdir() if p.is_dir())
    for d, rid in (("brain-v3-brain-scalp-p1", "brain-scalp-paper-p1"), ("brain-v3-falco-evoluto-p1",
                                                                         "falco-evoluto-paper-p1")):
        res = json.loads((base / f"{d}.RISULTATI.json").read_text())
        assert res["open_positions"] == 0 and "ripartenza Brain unico" in res["motivo"]
        assert (base / d / "journal.db").is_file() and (base / d / "daily_loss.json").read_text() == '{"latch": "vecchio"}'
    kinds = [e.kind for e in _events(base / "brain-v3-brain-scalp-p1", "brain-scalp-paper-p1")]
    assert kinds.count("paper_open") == 1 and kinds.count("paper_close") == 1
    # run nuova: slot di Brain Scalp, journal nuovo, configurazione del Brain unico, mandato approvato, RUNNING
    assert [e.kind for e in _events(rig.scalp, "brain-scalp-paper-p1")] == ["run_prepared"]
    assert (rig.scalp / "runner_config.json").read_bytes() == (RUNNER / U).read_bytes()
    m = json.loads((rig.scalp / "mandate.json").read_text())
    assert m["approved"] is True and m["approved_by"] == "Proprietario Test"
    assert json.loads((rig.scalp / "heartbeat.json").read_text())["state"] == "running"
    assert not list(rig.falco.iterdir())                 # Falco Evoluto solo in Archivio
    # unita': Brain Scalp sul codice nuovo (unica differenza la cartella), Falco Evoluto fermo e disattivato
    for u in UNITS[2:]:
        text = (rig.units / u).read_text()
        assert f"WorkingDirectory={ROOT}" in text and str(rig.old) not in text
    for u in UNITS[:2]:
        assert f"WorkingDirectory={rig.old}" in (rig.units / u).read_text()
    calls = (rig.sd / "calls").read_text().splitlines()
    assert "disable superbot-falco-evoluto-p1-runner.service" in calls
    assert not any(c.startswith("start superbot-falco") for c in calls)
    last_stop = max(i for i, c in enumerate(calls) if c.startswith("stop"))
    assert last_stop < min(i for i, c in enumerate(calls) if c.startswith("start")) and not any("rc1" in c for c in calls)

    # rollback: run precedenti al loro posto, in pausa, impronte verificate; unita' e Falco ripristinati
    assert rp.main(["--rollback", base.name.replace("reset-", "")]) == 0
    assert [e.kind for e in _events(rig.scalp, "brain-scalp-paper-p1")].count("paper_close") == 1
    assert (rig.scalp / "pause.flag").exists() and (rig.falco / "pause.flag").exists()
    for u in UNITS:
        assert f"WorkingDirectory={rig.old}" in (rig.units / u).read_text()
    scart = base.parent / f"{base.name}-run-nuova-scartata" / "brain-v3-brain-scalp-p1"
    assert [e.kind for e in _events(scart, "brain-scalp-paper-p1")] == ["run_prepared"]


def test_block_before_archive_leaves_everything_intact(rig, capsys):
    (rig.runs / "brain-v3-unico-paper-rc1" / "pause.flag").unlink()
    before = (rig.scalp / "journal.db").read_bytes()
    assert rig.rp.main(["--esegui", "--stage", str(ROOT)]) == 3
    assert "brain_rc1_non_in_pausa" in capsys.readouterr().out
    assert (rig.scalp / "journal.db").read_bytes() == before and not (rig.runs / ".archivio").exists()


def test_failure_after_archive_rolls_back_runs_and_units(rig, capsys, monkeypatch):
    def broken(*a, **k):
        raise rig.rp.Blocco("preparazione_simulata_fallita")
    monkeypatch.setattr(rig.rp, "prepare_new", broken)
    assert rig.rp.main(["--esegui", "--stage", str(ROOT)]) == 4
    out = capsys.readouterr().out
    assert "ROLLBACK_AUTOMATICO_RUN_PRECEDENTI_IN_PAUSA" in out and "NO_GO_RIPARTENZA_NON_ESEGUITA" in out
    kinds = [e.kind for e in _events(rig.scalp, "brain-scalp-paper-p1")]
    assert kinds.count("paper_open") == 1 and kinds.count("paper_close") == 1
    assert (rig.scalp / "pause.flag").exists() and (rig.falco / "pause.flag").exists()
    for u in UNITS:
        assert f"WorkingDirectory={rig.old}" in (rig.units / u).read_text()


def test_wrong_config_is_refused_before_any_change(rig, capsys, tmp_path, monkeypatch):
    raw = json.loads((RUNNER / U).read_bytes())
    raw["initial_equity"] = "2500"
    raw["brain_unico"]["piggy_bank"]["reference_equity"] = "2500"
    (tmp_path / U).write_text(json.dumps(raw))
    monkeypatch.setattr(rig.rp, "CONFIG", tmp_path / U)
    assert rig.rp.main(["--esegui", "--stage", str(ROOT)]) == 3
    assert "configurazione_diversa_dal_commit" in capsys.readouterr().out
    assert not (rig.runs / ".archivio").exists() and not (rig.scalp / "pause.flag").exists()


# ------------------------------------------------------------------ ripartenza.sh: Claude verificato PRIMA delle run
def _package(tmp: Path, env_text: str) -> tuple[Path, dict]:
    import shutil
    import subprocess
    pkg = tmp / "pkg"
    (pkg / "ui").mkdir(parents=True)
    shutil.copy(HERE / "ripartenza.sh", pkg / "ripartenza.sh")
    shutil.copy(RUNNER / U, pkg / U)
    (pkg / "ui" / "index.html").write_text("<html></html>")
    (pkg / "COMMIT").write_text("a" * 40)
    (pkg / ("backend-" + "a" * 12 + ".tar")).write_text("tar finto")
    marker = tmp / "ripartenza_brain_eseguito"
    (pkg / "ripartenza_brain.py").write_text(f"open({str(marker)!r}, 'w').write('x')\n")
    (pkg / "30-codice.sh").write_text(f'ln -s {ROOT} "$NEW_STAGE"\n')
    (pkg / "contratti_check.py").write_text("print('regole contratti: 27/27')\n")
    env = tmp / "brain-ai.env"
    env.write_text(env_text)
    comune = tmp / "comune.sh"
    comune.write_text(f'LAB={ROOT}\nPY={sys.executable}\nAIENV={env}\nnogo() {{ echo "NO-GO: $*"; exit 1; }}\n'
                      f'stage_of() {{ echo "{tmp}/stage"; }}\n')
    subprocess.run("cd ui && sha256sum index.html > SHA256SUMS && cd .. && sha256sum COMMIT *.tar *.sh *.py *.json "
                   "ui/SHA256SUMS > SHA256SUMS", shell=True, cwd=pkg, check=True)
    return pkg, {"marker": marker, "env": dict(os.environ, RIPARTENZA_TEST_MODE="1", RIPARTENZA_TEST_COMUNE=str(comune),
                                                NEW_STAGE=str(tmp / "stage"), HTTPS_PROXY="http://127.0.0.1:9",
                                                HTTP_PROXY="http://127.0.0.1:9", PYTHONDONTWRITEBYTECODE="1")}


def test_restart_stops_before_touching_any_run_when_claude_is_not_usable(tmp_path):
    import subprocess
    for text in ("DEEPSEEK_API_KEY=ds-segreta\n", "DEEPSEEK_API_KEY=ds\nANTHROPIC_API_KEY=sk-ant-NONVALIDA\n"):
        pkg, ctx = _package(tmp_path / str(len(text)), text)
        p = subprocess.run(["bash", str(pkg / "ripartenza.sh")], cwd=tmp_path, env=ctx["env"], capture_output=True,
                           text=True, timeout=180)
        out = p.stdout + p.stderr
        assert p.returncode == 2, out
        assert "RIPARTENZA_RESULT=RIFIUTATA_CLAUDE_NON_UTILIZZABILE_NESSUNA_RUN_TOCCATA" in out
        assert "CLAUDE_API=CHIAVE_ASSENTE" in out or "CLAUDE_API=HTTP_O_RETE" in out
        assert "ANTHROPIC_API_KEY=<la chiave" in out                       # come rimediare da Termius
        assert not ctx["marker"].exists()                                  # la ripartenza non e' mai partita
        assert "segreta" not in out and "NONVALIDA" not in out             # nessuna chiave stampata
