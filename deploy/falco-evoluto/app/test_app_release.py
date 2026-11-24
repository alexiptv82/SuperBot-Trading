"""Rilascio dell'app PAPER: sonda (``app_probe.py``) e aggiornamento della web (``web_app_update.py``), offline.

La sonda gira come nel container candidato: processo separato, router V3 vero, sessione vera (DB di autenticazione
copiato), run preparate col codice vero, archivio del reset come lo scrive ``reset_paper.py``. Nessun docker, nessuna VPS.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from decimal import Decimal as D
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
from backend.tests.test_brain_f7_outcomes import _hand  # noqa: E402
from backend.v3.events import EventJournal  # noqa: E402
from backend.v3.executor.paper import execute_paper  # noqa: E402
from backend.v3.executor.paper_close import close_paper  # noqa: E402
from backend.v3.runner.prepare_paper_run import prepare_new_paper_run  # noqa: E402

RUNNER = REPO / "backend" / "v3" / "runner"
H = 3_600_000
WALLETS = {"falco_evoluto": ("brain-v3-falco-evoluto-p1", "falco-evoluto-paper-p1", "runner_config_falco_evoluto_paper.json", "1000"),
           "brain_scalp": ("brain-v3-brain-scalp-p1", "brain-scalp-paper-p1", "runner_config_brain_scalp_paper.json", "2000")}


def _trade(j, rid, side, entry, stop, exit_price, reason, at):
    pid = execute_paper(_hand(side=side, entry=entry, stop=stop, qty="1", margin="100", lev=20, symbol="BTCUSDT"),
                        portfolio_id="brain", run_id=rid, journal=j, now_ms=at).position_id
    if exit_price:
        close_paper(portfolio_id="brain", run_id=rid, position_id=pid, exit_price=D(exit_price), reason=reason,
                    fee_bps=6, journal=j, now_ms=at + H)


def _world(tmp: Path):
    for mod in ("jwt", "sqlalchemy", "dotenv"):          # autenticazione vera della web: dipendenze dell'immagine
        pytest.importorskip(mod)
    now = int(time.time() * 1000)
    runs = tmp / "runs"
    runs.mkdir()
    env = []
    for name, (folder, rid, cfg, eq) in WALLETS.items():
        root = prepare_new_paper_run(parent=runs, run_name=folder, run_id=rid, config_bytes=(RUNNER / cfg).read_bytes(),
                                     desk_mode="paper", now_ms=now - 30 * H, expected_initial_equity=eq)
        j = EventJournal(root / "journal.db")
        _trade(j, rid, 1, "100", "98", "106", "take_profit", now - 20 * H)
        _trade(j, rid, -1, "100", "102", "101", "manual", now - 10 * H)
        _trade(j, rid, 1, "100", "98", None, None, now - H)
        env.append({"name": name, "label": name.replace("_", " ").title(), "dir": str(root), "run_id": rid})
    arch = runs / ".archivio"
    base = arch / "reset-20261123T203000Z"
    base.mkdir(parents=True)
    for name, (folder, rid, cfg, eq) in WALLETS.items():
        old = prepare_new_paper_run(parent=base, run_name=folder, run_id=rid, config_bytes=(RUNNER / cfg).read_bytes(),
                                    desk_mode="paper", now_ms=now - 60 * H, expected_initial_equity=eq)
        _trade(EventJournal(old / "journal.db"), rid, 1, "100", "98", "97", "stop", now - 50 * H)
        (base / f"{folder}.RISULTATI.json").write_text(json.dumps({"run_id": rid, "closed_at_ms": now - 40 * H}))
    for d in sorted(arch.rglob("*"), reverse=True) + [arch]:     # archivio come nella web: in sola lettura
        if d.is_dir():
            d.chmod(0o555)
    auth = tmp / "auth.db"
    penv = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, (str(REPO), str(REPO / "backend"), os.environ.get("PYTHONPATH")))), PYTHONDONTWRITEBYTECODE="1", DB_PATH=str(auth),
                V3_COMPARE_RUNS=json.dumps(env), V3_PAPER_ARCHIVE_ROOT=str(arch), DESK_MODE="paper", TRADING_MODE="paper",
                HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9")
    subprocess.run([sys.executable, "-c", "import auth, database; database.Base.metadata.create_all(database.engine); auth.init_auth()"],
                   cwd=tmp, env=penv, check=True, capture_output=True, timeout=60)
    return runs, arch, penv


def _probe(tmp, penv, archived="2"):
    p = subprocess.run([sys.executable, "-B", "-", "candidate", archived], input=(HERE / "app_probe.py").read_text(),
                       cwd=tmp, env=penv, capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout + p.stderr


def test_candidate_probe_passes_on_real_runs_and_reports_only_counts(tmp_path):
    runs, _arch, penv = _world(tmp_path)
    before = {p: p.read_bytes() for p in runs.rglob("*") if p.is_file()}
    code, out = _probe(tmp_path, penv)
    assert code == 0, out
    assert "APP_PROBE RESULT=PASS_CANDIDATE" in out
    assert "APP_PROBE falco_evoluto=run falco-evoluto-paper-p1: 2 chiusi, 1 aperti" in out
    assert "APP_PROBE archivio=2 run archiviate leggibili" in out
    assert "Bearer" not in out and "$" not in out
    after = {p: p.read_bytes() for p in runs.rglob("*") if p.is_file()}
    # nessun file creato. Unica eccezione: -wal/-shm del registro di spesa (WAL) delle run ATTIVE, che qui sono cartelle
    # scrivibili senza runner; nella web sono montate in sola lettura e il runner tiene aperto il registro.
    created = sorted(str(p.relative_to(runs)) for p in set(after) ^ set(before))
    assert [c for c in created if not (c.endswith(("budget.db-wal", "budget.db-shm")) and not c.startswith(".archivio"))] == []
    assert [str(p.relative_to(runs)) for p in before if after[p] != before[p]] == []      # nessun file cambiato
    assert "costi AI leggibili" in out


def test_candidate_probe_fails_when_the_archive_is_not_what_the_host_has(tmp_path):
    _runs, _arch, penv = _world(tmp_path)
    code, out = _probe(tmp_path, penv, archived="3")
    assert code == 2 and "FAILED_archive_not_readable_2_of_3" in out
    code, out = _probe(tmp_path, dict(penv, V3_PAPER_ARCHIVE_ROOT="/nonexistent"))
    assert code == 2 and "FAILED_archive_not_readable_0_of_2" in out


def test_candidate_probe_fails_when_compare_and_trades_disagree(tmp_path, monkeypatch):
    runs, _arch, penv = _world(tmp_path)
    # chiusura registrata senza esito leggibile per gli outcomes: i trade non tornano con /compare -> la sonda lo dice
    cfg = json.loads(penv["V3_COMPARE_RUNS"])
    j = EventJournal(Path(cfg[0]["dir"]) / "journal.db")
    from backend.v3.events import Event
    j.append(Event("paper_close.orfano", "brain", cfg[0]["run_id"], "paper_close", int(time.time() * 1000), "t",
                   {"position_id": "inesistente", "symbol": "BTCUSDT", "side": 1, "realized_pnl": "5", "fees": "0.1"}))
    code, out = _probe(tmp_path, penv)
    assert code == 2 and "FAILED_trades_" in out


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def wu():
    return _load("web_app_update")


def _web(env, mounts):
    return {"Image": "sha256:old", "Config": {"Env": [f"{k}={v}" for k, v in env.items()]},
            "Mounts": [{"Type": "bind", "Source": s, "Destination": d, "RW": rw} for s, d, rw in mounts]}


def test_target_env_adds_only_the_archive_root_and_requires_the_falco_scalp_web(wu):
    base = dict(wu.base.REQUIRED_ENV, V3_COMPARE_RUNS=wu.compare_env_value(), OTHER="x")
    assert wu.target_env(base) == dict(base, V3_PAPER_ARCHIVE_ROOT=wu.ARCHIVE)
    assert wu.target_env(dict(base, V3_PAPER_ARCHIVE_ROOT=wu.ARCHIVE)) == dict(base, V3_PAPER_ARCHIVE_ROOT=wu.ARCHIVE)
    for bad in (dict(base, V3_COMPARE_RUNS="[]"), {k: v for k, v in base.items() if k != "V3_COMPARE_RUNS"},
                dict(base, V3_PAPER_ARCHIVE_ROOT="/altro"), dict(base, DESK_MODE="live")):
        with pytest.raises(wu.Refused):
            wu.target_env(bad)


def test_archive_is_mounted_read_only_once_and_never_read_write(wu):
    runs = [(d, d, False) for d in wu.run_dirs()]
    web = _web({}, runs + [("/opt/superbot-desk-data", "/data", True)])
    assert wu.mount_args(web, force_ro=False)[-2:] == ["-v", f"{wu.ARCHIVE}:{wu.ARCHIVE}:ro"]
    assert (wu.ARCHIVE, "bind", False, wu.ARCHIVE) in wu.expected_mounts(web)
    assert "/opt/superbot-desk-data:/data:rw" in wu.mount_args(web, force_ro=False)
    assert "/opt/superbot-desk-data:/data:ro" in wu.mount_args(web, force_ro=True)
    again = _web({}, runs + [(wu.ARCHIVE, wu.ARCHIVE, False)])
    assert wu.mount_args(again, force_ro=False).count(f"{wu.ARCHIVE}:{wu.ARCHIVE}:ro") == 1
    with pytest.raises(wu.Refused):
        wu.needs_archive_mount(_web({}, [(wu.ARCHIVE, wu.ARCHIVE, True)]))
    with pytest.raises(wu.Refused):
        wu.needs_archive_mount(_web({}, [("/tmp/x", wu.ARCHIVE, False)]))


def test_host_archive_count_only_complete_archives(wu, tmp_path):
    base = tmp_path / "reset-20261123T203000Z"
    (base / "brain-v3-falco-evoluto-p1").mkdir(parents=True)
    (base / "brain-v3-brain-scalp-p1").mkdir()
    (base / "brain-v3-falco-evoluto-p1.RISULTATI.json").write_text("{}")
    (tmp_path / "reset-20261123T203000Z-run-nuove-scartate" / "brain-v3-brain-scalp-p1").mkdir(parents=True)
    assert wu.host_archived(tmp_path) == 1


def test_backend_tar_is_verified_and_contains_only_backend(wu, tmp_path):
    import tarfile
    good = tmp_path / "b.tar"
    with tarfile.open(good, "w") as t:
        f = tmp_path / "x.py"
        f.write_text("x")
        t.add(f, arcname="backend/x.py")
    sha = wu.sha256(good)
    assert wu.check_backend_tar(good, sha) is None
    with pytest.raises(wu.Refused):
        wu.check_backend_tar(good, "0" * 64)
    bad = tmp_path / "c.tar"
    with tarfile.open(bad, "w") as t:
        t.add(f, arcname="../etc/x.py")
    with pytest.raises(wu.Refused):
        wu.check_backend_tar(bad, wu.sha256(bad))


# ---------------------------------------------------------------- script unico (aggiorna_app.sh) con servizi finti
def _package(tmp: Path, *, web_rc=0, ui_rc=0, index_ok=True):
    pkg = tmp / "pkg"
    (pkg / "ui").mkdir(parents=True)
    (pkg / "ui" / "index.html").write_text("<html>nuova</html>")
    subprocess.run("sha256sum index.html > SHA256SUMS", shell=True, cwd=pkg / "ui", check=True)
    sha = "a" * 40
    (pkg / "COMMIT").write_text(sha)
    (pkg / f"backend-{sha[:12]}.tar").write_bytes(b"tar")
    log = tmp / "calls.log"
    (pkg / "web_app_update.py").write_text(
        f"import sys\nopen({str(log)!r},'a').write('web '+sys.argv[1]+'\\n')\n"
        f"sys.exit({web_rc} if sys.argv[1] == '--deploy' else 0)\n")
    (pkg / "70-interfaccia.sh").write_text(f"echo \"ui $1\" >> {log}\n[ \"$1\" = --activate ] && exit {ui_rc}\nexit 0\n")
    shutil_copy(HERE / "aggiorna_app.sh", pkg / "aggiorna_app.sh")
    subprocess.run("sha256sum COMMIT backend-*.tar web_app_update.py 70-interfaccia.sh ui/SHA256SUMS > SHA256SUMS",
                   shell=True, cwd=pkg, check=True)
    fake = tmp / "bin"
    fake.mkdir()
    body = "<html>nuova</html>" if index_ok else "<html>vecchia</html>"
    (fake / "curl").write_text(
        "#!/bin/bash\nout=/dev/null\nurl=''\nwhile [ $# -gt 0 ]; do case \"$1\" in -o) out=$2; shift 2;; -w|--max-time|--resolve) shift 2;;"
        " -*) shift;; *) url=$1; shift;; esac; done\n"
        f"case \"$url\" in */) printf '%s' '{body}' > \"$out\"; printf 200;; */api/health) printf 200;; *) printf 401;; esac\n")
    (fake / "curl").chmod(0o755)
    env = dict(os.environ, PATH=f"{fake}:{os.environ['PATH']}", PAPER_APP_TEST_MODE="1", PAPER_APP_STATE=str(tmp / "state"))
    return pkg, log, env


def shutil_copy(a, b):
    b.write_bytes(a.read_bytes())


def _run(pkg, env, *args):
    p = subprocess.run(["bash", str(pkg / "aggiorna_app.sh"), *args], env=env, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


def test_install_success_order_web_then_ui_then_domain_check(tmp_path):
    pkg, log, env = _package(tmp_path)
    rc, out = _run(pkg, env)
    assert rc == 0 and out.strip().endswith("APP_RESULT=APP_PAPER_INSTALLATA_E_VERIFICATA"), out
    assert log.read_text().splitlines() == ["web --deploy", "ui --activate"]
    assert (tmp_path / "state" / "interfaccia-attivata").is_file()
    rc, out = _run(pkg, env, "--rollback")
    assert rc == 0 and "ROLLBACK_COMPLETATO" in out
    assert log.read_text().splitlines()[-2:] == ["ui --rollback", "web --rollback"]
    assert not (tmp_path / "state" / "interfaccia-attivata").exists()


def test_web_refused_means_no_ui_change(tmp_path):
    pkg, log, env = _package(tmp_path, web_rc=2)
    rc, out = _run(pkg, env)
    assert rc == 3 and "WEB_NON_AGGIORNATA" in out
    assert log.read_text().splitlines() == ["web --deploy"]


def test_ui_failure_puts_the_previous_web_back(tmp_path):
    pkg, log, env = _package(tmp_path, ui_rc=2)
    rc, out = _run(pkg, env)
    assert rc == 4 and "INTERFACCIA_FALLITA_TUTTO_RIPRISTINATO" in out
    assert log.read_text().splitlines() == ["web --deploy", "ui --activate", "web --rollback"]
    assert not (tmp_path / "state" / "interfaccia-attivata").exists()


def test_final_check_failure_rolls_back_both(tmp_path):
    pkg, log, env = _package(tmp_path, index_ok=False)
    rc, out = _run(pkg, env)
    assert rc == 4 and "CONTROLLO_FINALE_FALLITO_TUTTO_RIPRISTINATO" in out
    assert log.read_text().splitlines() == ["web --deploy", "ui --activate", "ui --rollback", "web --rollback"]


def test_rollback_without_our_activation_never_touches_the_served_ui(tmp_path):
    pkg, log, env = _package(tmp_path)
    rc, out = _run(pkg, env, "--rollback")
    assert rc == 0 and "nessuna attivazione registrata" in out
    assert log.read_text().splitlines() == ["web --rollback"]


def test_tampered_package_is_refused_before_any_change(tmp_path):
    pkg, log, env = _package(tmp_path)
    (pkg / "web_app_update.py").write_text("print('altro')\n")
    rc, out = _run(pkg, env)
    assert rc == 2 and "RIFIUTATA_IMPRONTE_DEL_PACCHETTO" in out and not log.exists()
    pkg2, log2, env2 = _package(tmp_path / "b")
    (pkg2 / "ui" / "index.html").write_text("manomessa")
    rc, out = _run(pkg2, env2)
    assert rc == 2 and "RIFIUTATA_IMPRONTE_INTERFACCIA" in out and not log2.exists()


# ------------------------------------------------------------------ Brain unico PAPER 2000 (24/11)
def test_target_env_for_the_single_brain_replaces_the_two_runs_and_is_idempotent(wu):
    base = dict(wu.base.REQUIRED_ENV, V3_COMPARE_RUNS=wu.compare_env_value(), OTHER="x")
    with pytest.raises(wu.Refused):                         # senza l'opzione la web a Brain unico non e' accettata
        wu.target_env(dict(base, V3_COMPARE_RUNS=wu.compare_env_value(wu.UNICO_RUNS)))
    wu.UNICO["on"] = True
    try:
        new = wu.target_env(base)
        assert json.loads(new["V3_COMPARE_RUNS"]) == [{"name": "brain_scalp", "label": "Brain",
                                                       "dir": wu.RUN_ROOT + "/brain-v3-brain-scalp-p1",
                                                       "run_id": "brain-scalp-paper-p1"}]
        assert wu.target_env(new) == new and dict(new, V3_COMPARE_RUNS=base["V3_COMPARE_RUNS"]) == dict(
            base, V3_PAPER_ARCHIVE_ROOT=wu.ARCHIVE)
        with pytest.raises(wu.Refused):
            wu.target_env(dict(base, V3_COMPARE_RUNS="[]"))
    finally:
        wu.UNICO["on"] = False


def test_candidate_probe_on_the_single_brain_with_two_legs_counts_closes_and_hides_falco(tmp_path):
    from backend.v3.unico import PartialTakeProfit, split_legs
    runs, _arch, penv = _world(tmp_path)
    unico = runs / "unico"
    unico.mkdir()
    rid = "brain-scalp-paper-p1"
    root = prepare_new_paper_run(parent=unico, run_name="brain-v3-brain-scalp-p1", run_id=rid,
                                 config_bytes=(RUNNER / "runner_config_brain_unico_2000_paper.json").read_bytes(),
                                 desk_mode="paper", now_ms=int(time.time() * 1000) - 5 * H, expected_initial_equity="2000")
    j = EventJournal(root / "journal.db")
    d = _hand(side=1, entry="100", stop="98", qty="10", margin="100", lev=20, symbol="BTCUSDT")
    legs = split_legs(D(10), step=D("0.001"), price=D(100), minimum_notional=D(5), partial=PartialTakeProfit(D("0.35"), D(2)))
    execute_paper(d, portfolio_id="brain", run_id=rid, journal=j, now_ms=int(time.time() * 1000) - 4 * H, legs=legs)
    first = [r.event.payload["position_id"] for r in j.list_run("brain", rid) if r.event.kind == "paper_open"][0]
    close_paper(portfolio_id="brain", run_id=rid, position_id=first, exit_price=D(104), reason="take_profit", fee_bps=6,
                journal=j, now_ms=int(time.time() * 1000) - 3 * H)         # 1a quota a 2R, il residuo resta aperto
    penv["V3_COMPARE_RUNS"] = json.dumps([{"name": "brain_scalp", "label": "Brain", "dir": str(root), "run_id": rid}])
    p = subprocess.run([sys.executable, "-B", "-", "candidate", "2", "unico"], input=(HERE / "app_probe.py").read_text(),
                       cwd=tmp_path, env=penv, capture_output=True, text=True, timeout=120)
    out = p.stdout + p.stderr
    assert p.returncode == 0, out
    assert "APP_PROBE brain_scalp=run brain-scalp-paper-p1: 1 chiusi, 1 aperti" in out and "RESULT=PASS_CANDIDATE" in out


def test_archive_with_a_two_leg_trade_counts_closes_and_keeps_the_loss(tmp_path):
    """Caso del 24/11: la sessione BTC archiviata ha UN trade distinto chiuso in DUE quote (stop): il dettaglio
    dell'archivio ha due righe; la sonda confronta le chiusure (``closes``) e il P&L netto, mai i trade distinti."""
    from backend.v3.unico import PartialTakeProfit, split_legs
    _runs, arch, penv = _world(tmp_path)
    for d in [arch] + sorted(arch.rglob("*")):
        if d.is_dir():
            d.chmod(0o755)
    base = arch / "reset-20261124T205540Z"
    base.mkdir()
    rid, now = "brain-scalp-paper-p1", int(time.time() * 1000)
    root = prepare_new_paper_run(parent=base, run_name="brain-v3-brain-scalp-p1", run_id=rid,
                                 config_bytes=(RUNNER / "runner_config_brain_unico_2000_paper.json").read_bytes(),
                                 desk_mode="paper", now_ms=now - 9 * H, expected_initial_equity="2000")
    j = EventJournal(root / "journal.db")
    d = _hand(side=-1, entry="60200", stop="60800", qty="0.1", margin="200", lev=19, symbol="BTCUSDT",
              link="brain-req-fdd2076ac06e640af59e4634a1689163")              # le due quote: stessa decisione
    legs = split_legs(D("0.1"), step=D("0.001"), price=D(60200), minimum_notional=D(5),
                      partial=PartialTakeProfit(D("0.35"), D(2)))
    execute_paper(d, portfolio_id="brain", run_id=rid, journal=j, now_ms=now - 8 * H, legs=legs)
    for i, r in enumerate([x for x in j.list_run("brain", rid) if x.event.kind == "paper_open"]):
        close_paper(portfolio_id="brain", run_id=rid, position_id=r.event.payload["position_id"],
                    exit_price=D("60262.05"), reason="stop", fee_bps=6, journal=j, now_ms=now - 6 * H + i,
                    stop_kind="brain")
    (base / "brain-v3-brain-scalp-p1.RISULTATI.json").write_text(json.dumps({"run_id": rid, "closed_at_ms": now - 5 * H}))
    for x in sorted(arch.rglob("*"), reverse=True) + [arch]:
        if x.is_dir():
            x.chmod(0o555)
    from backend.v3.compare_view import RunRef, read_run
    v = read_run(RunRef("archivio", "Brain", root, rid), now)
    assert (v["closed"], v["closes"]) == (1, 2) and D(v["net_pnl"]) < 0          # 1 trade, 2 chiusure, in perdita
    code, out = _probe(tmp_path, penv, archived="3")
    assert code == 0, out
    assert "APP_PROBE archivio=3 run archiviate leggibili" in out and "RESULT=PASS_CANDIDATE" in out
    # stesso archivio con il confronto di prima (trade distinti): il controllo falliva come sulla VPS
    old = (HERE / "app_probe.py").read_text().replace('r.get("closes", r.get("closed"))', 'r.get("closed")')
    p = subprocess.run([sys.executable, "-B", "-", "candidate", "3"], input=old, cwd=tmp_path, env=penv,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 2 and "FAILED_archive_detail_mismatch_reset-20261124T205540Z" in p.stdout + p.stderr


@pytest.mark.parametrize("ready,close_code,expect", [(True, 401, "PASS_LIVE"), (False, 401, "FAILED_manual_close_not_ready"),
                                                      (True, 200, "FAILED_manual_close_without_session_not_401")])
def test_live_probe_checks_the_manual_close_without_ever_closing(monkeypatch, capsys, ready, close_code, expect):
    import importlib.util
    import io
    import types
    import urllib.error
    spec = importlib.util.spec_from_file_location("app_probe_live", HERE / "app_probe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.EXPECT = mod.UNICO
    monkeypatch.setattr(mod, "checks", lambda get, post, archived: None)
    monkeypatch.setitem(sys.modules, "backend.auth", types.SimpleNamespace(create_session_token=lambda s: "t"))
    seen = []

    class Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=20):
        seen.append((req.get_method(), req.full_url, req.data))
        if req.full_url.endswith("/api/v3/compare"):
            return Resp(json.dumps({"runs": [{"name": "brain_scalp", "manual_close_allowed": ready}]}).encode())
        if close_code == 200:
            return Resp(b"{}")
        raise urllib.error.HTTPError(req.full_url, close_code, "x", {}, io.BytesIO(b"{}"))
    monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
    with pytest.raises(SystemExit) if expect != "PASS_LIVE" else _nullcontext():
        mod.live(5)
    assert "RESULT=" + expect in capsys.readouterr().out
    posts = [s for s in seen if s[0] == "POST"]
    assert all(p[2] == b"{}" and "position_id" not in p[2].decode() for p in posts)    # mai una chiusura vera


class _nullcontext:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False
