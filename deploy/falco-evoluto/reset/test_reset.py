"""Reset e ripartenza PAPER: configurazioni nuove e procedura completa in cartelle finte (run vere preparate dal codice,
posizione aperta chiusa dal canale manuale vero, dashboard letta con ``compare_view`` vero)."""
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
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "limiti"))

import analisi_limiti as al  # noqa: E402
from backend.v3.brain_f2.engine import _policy_hash  # noqa: E402
from backend.v3.events import EventJournal  # noqa: E402
from backend.v3.runner.prepare_paper_run import prepare_new_paper_run  # noqa: E402

RUNNER = ROOT / "backend" / "v3" / "runner"
F, S = "runner_config_falco_evoluto_paper.json", "runner_config_brain_scalp_paper.json"


# ------------------------------------------------------------------ configurazioni
def test_new_configs_values_and_daily_stop_really_usable():
    f, s = al.load(HERE / F), al.load(HERE / S)
    assert (f.initial_equity, f.daily_loss_warn, f.daily_loss_halt, f.guardian.session_loss_fraction) == (
        D("1000"), D("0.06"), D("0.12"), D("0.12"))
    assert (s.initial_equity, s.daily_loss_warn, s.daily_loss_halt, s.guardian.session_loss_fraction) == (
        D("2000"), D("0.15"), D("0.25"), D("0.25"))
    assert (f.risk_policy.minimum_equity, f.guardian.global_drawdown_lock) == (D("800"), D("0.20"))
    assert (s.risk_policy.minimum_equity, s.guardian.global_drawdown_lock) == (D("1400"), D("0.30"))   # adeguati
    for c in (f, s):
        p = c.risk_policy
        assert (p.max_loss_fraction, p.max_open_risk_fraction, p.min_leverage, p.max_leverage) == (D("0.04"), D("0.10"), 15, 45)
        assert c.guardian.activation_fraction == D("0.08") and c.guardian.keep_fraction == D("0.75")  # profitti
        assert c.guardian.global_drawdown_half == D("0.10")
    # il primo blocco dal capitale pieno (e dopo profitti) e' lo stop giornaliero richiesto
    for c, e in ((f, D("1000")), (s, D("2000")), (f, D("1200")), (s, D("2400"))):
        assert {x.nome for x in al.primo_blocco(c, e)} == {"freno_giornaliero", "guardian_sessione"}
    assert al.primo_blocco(s, D("2000"))[0].equity == D("1500") and al.primo_blocco(f, D("1000"))[0].equity == D("880")
    # sicurezza: floor e blocco globale restano, sotto lo stop
    assert al.mai_raggiunti(s, D("2000")) == [] and s.risk_policy.minimum_equity < D("1500")
    # nessun'altra differenza rispetto alle configurazioni delle run precedenti
    import aggiorna_limiti as ag
    assert ag.config_fields_diff(al.load(RUNNER / F), f) == sorted(ag.CHANGED)
    assert ag.config_fields_diff(al.load(RUNNER / S), s) == sorted(ag.CHANGED + ("guardian.global_drawdown_lock", "risk_policy"))
    # mandati: Falco stessa politica di rischio; Scalp nuova impronta (floor) -> mandato nuovo, approvato nella run nuova
    assert _policy_hash(f.risk_policy) == _policy_hash(al.load(RUNNER / F).risk_policy)
    assert _policy_hash(s.risk_policy) != _policy_hash(al.load(RUNNER / S).risk_policy)


def test_pinned_hashes_match_the_files():
    rp = importlib.import_module("reset_paper")
    for r in rp.RUNS:
        assert r["sha"] == hashlib.sha256((HERE / r["config"]).read_bytes()).hexdigest()
    sops = (ROOT / "deploy/falco-evoluto/admin/superbot-ops").read_text()
    for f, h in rp.PINNED.items():
        assert f'pinned "$FSD" {f} {h}' in sops                          # stesse impronte che verifica superbot-ops


# ------------------------------------------------------------------ procedura completa
FAKE_SYSTEMCTL = r"""#!/bin/sh
cmd="$1"; shift
case "$cmd" in
  show) echo "$FAKE_STAGE" ;;
  is-active) shift; [ ! -e "$FAKE_SD/$1.stopped" ] ;;
  stop) touch "$FAKE_SD/$1.stopped"; echo "stop $1" >> "$FAKE_SD/calls" ;;
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
FAKE_CONTROLLI = "print('USCITE: SANE')\n"
FAKE_DOCKER = r"""#!/bin/sh
case "$1" in
  inspect) echo running ;;
  exec) cat > /dev/null; "$FAKE_PY" "$FAKE_SD/probe.py" "$7" "$8" ;;
esac
"""
PROBE = r"""import json, os, sys, time
sys.path.insert(0, os.environ['FAKE_RESET_DIR'])
import backend.v3.compare_view as cv
import reset_probe as rp
cv._close_ready = lambda ref, now: True          # salute delle uscite: verificata a parte (controlli.py)
runs = os.environ['FAKE_RUNS']
env = {'V3_COMPARE_RUNS': json.dumps([
    {'name': 'falco_evoluto', 'label': 'Falco Evoluto', 'dir': runs + '/brain-v3-falco-evoluto-p1', 'run_id': 'falco-evoluto-paper-p1'},
    {'name': 'brain_scalp', 'label': 'Brain Scalp', 'dir': runs + '/brain-v3-brain-scalp-p1', 'run_id': 'brain-scalp-paper-p1'}])}
data = json.loads(json.dumps(cv.compare(env, int(time.time() * 1000)), default=str))
rp.check(data, sys.argv[1], int(sys.argv[2]))
print('RESET_PROBE RESULT=PASS_' + sys.argv[1].upper())
"""


def _old_run(parent: Path, name: str, run_id: str, cfg: str, equity: str, with_position: bool):
    from backend.tests.test_v3_runner_feed_monitor import _hand
    from backend.v3.executor.paper import execute_paper
    root = prepare_new_paper_run(parent=parent, run_name=name, run_id=run_id, config_bytes=(RUNNER / cfg).read_bytes(),
                                 desk_mode="paper", now_ms=int(time.time() * 1000) - 7_200_000,
                                 expected_initial_equity=equity)
    m = json.loads((root / "mandate.json").read_text())
    (root / "mandate.json").write_text(json.dumps(dict(m, approved=True, approved_by="Proprietario Test")))
    (root / "pause.flag").unlink()
    if with_position:
        j = EventJournal(str(root / "journal.db"))
        d = _hand(side=1, entry="30000", stop="29000", symbol="BTCUSDT")
        execute_paper(d, portfolio_id="brain", run_id=run_id, journal=j, now_ms=int(time.time() * 1000) - 3_600_000)
    (root / "daily_loss.json").write_text('{"latch": "vecchio"}')
    return root


@pytest.fixture
def rig(tmp_path, monkeypatch):
    runs, sd, fsd, state = tmp_path / "runs", tmp_path / "sd", tmp_path / "fsd", tmp_path / "state"
    for d in (runs, sd, fsd):
        d.mkdir()
    (runs / "brain-v3-unico-paper-rc1").mkdir()
    (runs / "brain-v3-unico-paper-rc1" / "pause.flag").write_text("rc1")
    falco = _old_run(runs, "brain-v3-falco-evoluto-p1", "falco-evoluto-paper-p1", F, "1000", False)
    scalp = _old_run(runs, "brain-v3-brain-scalp-p1", "brain-scalp-paper-p1", S, "2000", True)
    for name, text in (("systemctl", FAKE_SYSTEMCTL), ("docker", FAKE_DOCKER)):
        (sd / name).write_text(text)
        (sd / name).chmod(0o755)
    (sd / "beat.py").write_text(BEAT)
    (sd / "probe.py").write_text(PROBE)
    (fsd / "80-paper.sh").write_text(FAKE_80)
    (fsd / "comune.sh").write_text("# finto\n")
    (fsd / "controlli.py").write_text(FAKE_CONTROLLI)
    pinned = {f: hashlib.sha256((fsd / f).read_bytes()).hexdigest() for f in ("80-paper.sh", "comune.sh", "controlli.py")}
    env = dict(RESET_TEST_MODE="1", RESET_PARENT=str(runs), RESET_FSD=str(fsd), RESET_STATE=str(state),
               RESET_SYSTEMCTL=str(sd / "systemctl"), RESET_DOCKER=str(sd / "docker"), RESET_POLL_S="0.05",
               RESET_PINNED=json.dumps(pinned), FAKE_STAGE=str(ROOT), FAKE_SD=str(sd), FAKE_RUNS=str(runs),
               FAKE_PY=sys.executable, FAKE_RESET_DIR=str(HERE), PYTHONPATH=str(ROOT))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    rp = importlib.reload(importlib.import_module("reset_paper"))

    # il servizio uscite (finto processo): esegue le richieste di chiusura con il codice vero
    stop = threading.Event()

    def exit_service():
        from backend.v3.runner.manual_close import run_manual_close
        while not stop.is_set():
            for run, rid in ((runs / "brain-v3-falco-evoluto-p1", "falco-evoluto-paper-p1"),
                             (runs / "brain-v3-brain-scalp-p1", "brain-scalp-paper-p1")):
                if (run / "close_request.json").exists() and (run / "journal.db").exists():
                    run_manual_close(journal=EventJournal(str(run / "journal.db")), portfolio_id="brain", run_id=rid,
                                     data_dir=run, price_of=lambda s, n: D("29500"), fee_bps=6,
                                     now_ms=int(time.time() * 1000))
            time.sleep(0.02)
    t = threading.Thread(target=exit_service, daemon=True)
    t.start()
    yield SimpleRig(rp, runs, sd, state, falco, scalp)
    stop.set()
    t.join(2)


class SimpleRig:
    def __init__(self, rp, runs, sd, state, falco, scalp):
        self.rp, self.runs, self.sd, self.state, self.falco, self.scalp = rp, runs, sd, state, falco, scalp


def _events(run: Path, rid: str):
    return [x.event for x in EventJournal(str(run / "journal.db")).list_run("brain", rid)]


def test_full_reset_and_restart(rig, capsys):
    rp = rig.rp
    old_scalp_journal = (rig.scalp / "journal.db").read_bytes()
    assert rp.main(["--controlla"]) == 0
    assert rp.main(["--esegui"]) == 0
    out = capsys.readouterr().out
    assert "RESET RESULT=RIPARTENZA_PAPER_ATTIVA" in out, out
    # posizione aperta chiusa e contabilizzata PRIMA dell'archivio
    assert "CONTABILIZZATA_scalp=chiuse 1, aperte 0" in out
    base = next((rig.runs / ".archivio").iterdir())
    arch = base / "brain-v3-brain-scalp-p1"
    kinds = [e.kind for e in _events(arch, "brain-scalp-paper-p1")]
    assert kinds.count("paper_open") == 1 and kinds.count("paper_close") == 1
    res = json.loads((base / "brain-v3-brain-scalp-p1.RISULTATI.json").read_text())
    assert res["closed_trades"] == 1 and res["open_positions"] == 0 and res["realized_pnl"] != "0"
    # archivio integrale e verificato: ogni file con la sua impronta, latch e mandato vecchi conservati
    sums = (base / "brain-v3-brain-scalp-p1.SHA256SUMS").read_text()
    for f in ("journal.db", "budget.db", "mandate.json", "runner_config.json", "daily_loss.json", "PREPARED_PAUSED_ONLY.json"):
        assert f"  {f}\n" in sums and (arch / f).is_file()
    assert (arch / "daily_loss.json").read_text() == '{"latch": "vecchio"}'
    assert len(old_scalp_journal) > 0
    # run nuove: stessa cartella, journal nuovo con la sola preparazione, configurazione nuova, mandato approvato
    for run, rid, cfg in ((rig.falco, "falco-evoluto-paper-p1", F), (rig.scalp, "brain-scalp-paper-p1", S)):
        ev = _events(run, rid)
        assert [e.kind for e in ev] == ["run_prepared"]
        assert (run / "runner_config.json").read_bytes() == (HERE / cfg).read_bytes()
        m = json.loads((run / "mandate.json").read_text())
        assert m["approved"] is True and m["approved_by"] == "Proprietario Test"
        assert m["policy_hash"] == _policy_hash(al.load(HERE / cfg).risk_policy)
        assert not (run / "pause.flag").exists() and not (run / "daily_loss.json").exists()
        assert json.loads((run / "heartbeat.json").read_text())["state"] == "running"
    # nessuna sovrapposizione: i vecchi runner fermati prima di avviare i nuovi; RC1 mai toccato
    calls = (rig.sd / "calls").read_text().splitlines()
    last_stop = max(i for i, c in enumerate(calls) if c.startswith("stop"))
    first_start = min(i for i, c in enumerate(calls) if c.startswith("start"))
    assert last_stop < first_start and not any("rc1" in c for c in calls)
    assert (rig.runs / "brain-v3-unico-paper-rc1" / "pause.flag").read_text() == "rc1"

    # rollback: le run precedenti tornano al loro posto, IN PAUSA, identiche; le nuove conservate
    assert rp.main(["--rollback", base.name.replace("reset-", "")]) == 0
    kinds = [e.kind for e in _events(rig.scalp, "brain-scalp-paper-p1")]
    assert kinds.count("paper_close") == 1 and (rig.scalp / "pause.flag").exists()
    scart = base.parent / f"{base.name}-run-nuove-scartate" / "brain-v3-brain-scalp-p1"
    assert [e.kind for e in _events(scart, "brain-scalp-paper-p1")] == ["run_prepared"]


def test_block_before_archive_leaves_old_runs_intact_and_paused(rig, capsys):
    (rig.runs / "brain-v3-unico-paper-rc1" / "pause.flag").unlink()          # RC1 non in pausa: preflight
    before = (rig.scalp / "journal.db").read_bytes()
    assert rig.rp.main(["--esegui"]) == 3
    assert "brain_rc1_non_in_pausa" in capsys.readouterr().out
    assert (rig.scalp / "journal.db").read_bytes() == before and not (rig.runs / ".archivio").exists()


def test_failure_after_archive_rolls_back_automatically(rig, capsys, monkeypatch):
    def broken(*a, **k):
        raise rig.rp.Blocco("preparazione_simulata_fallita")
    monkeypatch.setattr(rig.rp, "prepare_new", broken)
    assert rig.rp.main(["--esegui"]) == 4
    out = capsys.readouterr().out
    assert "ROLLBACK_AUTOMATICO_RUN_PRECEDENTI_IN_PAUSA" in out and "NO_GO_RIPARTENZA_NON_ESEGUITA" in out
    kinds = [e.kind for e in _events(rig.scalp, "brain-scalp-paper-p1")]
    assert kinds.count("paper_open") == 1 and kinds.count("paper_close") == 1       # storia intatta, chiusura inclusa
    assert (rig.scalp / "pause.flag").exists() and (rig.falco / "pause.flag").exists()


def test_activation_failure_leaves_new_runs_paused_and_says_so(rig, capsys):
    (rig.sd / "runner_fails").write_text("x")
    rig.rp.POLL = 0.01
    orig = rig.rp.wait
    rig.rp.wait = lambda cond, seconds, code: orig(cond, min(seconds, 1), code)
    try:
        assert rig.rp.main(["--esegui"]) in (4, 5)
    finally:
        rig.rp.wait = orig
    out = capsys.readouterr().out
    assert "RIPARTENZA_PAPER_ATTIVA" not in out and "NO_GO" in out
