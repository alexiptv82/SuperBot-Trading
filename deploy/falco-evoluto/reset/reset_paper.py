"""RESET e RIPARTENZA PAPER di Falco Evoluto e Brain Scalp: una sola procedura (root), con backup, verifiche e rollback.

    reset_paper.py --esegui        pausa -> chiusura e contabilizzazione delle posizioni aperte -> arresto ->
                                   archivio integrale -> run nuove (capitale pieno, journal nuovi) -> avvio uscite e
                                   runner -> verifica dashboard -> attivazione PAPER -> verifica finale
    reset_paper.py --rollback      rimette le run archiviate al loro posto (IN PAUSA), conserva le run nuove scartate

Riferimenti invariati: stesse cartelle, stessi run_id, stesse unita' systemd, stessi nomi nel confronto e nel bridge
(il container web e il bridge montano le CARTELLE: se ne sostituisce il contenuto, la cartella resta la stessa).
Quindi niente da cambiare in web, bridge, interfaccia e ``superbot-ops``. Il vecchio contenuto viene SPOSTATO (mai
cancellato) in ``<runs>/.archivio/reset-<data>/<run>`` con l'elenco delle impronte di ogni file, verificato dopo lo spostamento,
piu' ``RISULTATI.json`` (contabilita' finale). Brain RC1 non viene mai toccato (solo verificato in pausa).

Riusa pezzi gia' in produzione, verificati per impronta come fa ``superbot-ops``: ``80-paper.sh`` (pausa, attivazione
con il nome di chi approva, letto dal mandato gia' approvato della run precedente), ``controlli.py`` (uscite sane),
``prepare_paper_run`` del codice installato (run in pausa, mandato approved:false, journal verificato).

Fallimenti: prima dell'archivio -> si ferma, run vecchie intatte e in pausa. Durante archivio/preparazione/avvio ->
rollback automatico alle run vecchie (in pausa). Dopo l'avvio delle run nuove -> run nuove lasciate IN PAUSA e blocco
indicato (il rollback resta disponibile).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from decimal import Decimal
from pathlib import Path

E = os.environ
PARENT = Path(E.get("RESET_PARENT", "/opt/superbot-v3-paper-runs"))
FSD = Path(E.get("RESET_FSD", "/root/falco-scalp-rilascio"))
STATE_DIR = Path(E.get("RESET_STATE", "/opt/superbot-v3-backups/falco-scalp"))
SYSTEMCTL = E.get("RESET_SYSTEMCTL", "systemctl")
DOCKER = E.get("RESET_DOCKER", "docker")
TEST = E.get("RESET_TEST_MODE") == "1"
POLL = float(E.get("RESET_POLL_S", "5"))
HERE = Path(__file__).resolve().parent
RC1 = PARENT / "brain-v3-unico-paper-rc1"
RC1_EXIT = "superbot-brain-unico-rc1-exit.service"
BRIDGE = "superbot-v3-paper-single-close-bridge.service"
PINNED = {"80-paper.sh": "0fc1e6e1ee74ea50b890dc2c6917238a3d84b87b1bb9429c0e173b079182d0f1",
          "comune.sh": "c639a85c6e37ec03adc748586977817aee633e17848d9457adae1f652a3a66e0",
          "controlli.py": "638c4da73615e11439d4e92f89890b5ca92c031b7df789d358d2d92fe7210afd"}
RUNS = (
    {"bot": "falco", "name": "falco_evoluto", "dir": "brain-v3-falco-evoluto-p1", "id": "falco-evoluto-paper-p1",
     "exit": "superbot-falco-evoluto-p1-exit.service", "runner": "superbot-falco-evoluto-p1-runner.service",
     "config": "runner_config_falco_evoluto_paper.json", "equity": "1000", "halt": "0.12", "floor": "800",
     "sha": "98b52a3bb82bb0e7dfe76d42558d7515aff0608371db2301140da208db2839cd"},
    {"bot": "scalp", "name": "brain_scalp", "dir": "brain-v3-brain-scalp-p1", "id": "brain-scalp-paper-p1",
     "exit": "superbot-brain-scalp-p1-exit.service", "runner": "superbot-brain-scalp-p1-runner.service",
     "config": "runner_config_brain_scalp_paper.json", "equity": "2000", "halt": "0.25", "floor": "1400",
     "sha": "7d7100bbc645d3f267ad36c10f1cbfe14c0afd13ef39f516300b14cb9d90f23f"},
)
if TEST and E.get("RESET_PINNED"):                       # solo nelle prove: impronte dei finti 80-paper/controlli
    PINNED = json.loads(E["RESET_PINNED"])
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .-]{1,40}$")


class Blocco(Exception):
    """Controllo indispensabile fallito: codice breve, mai segreti o importi reali."""


def say(key: str, value: object = "") -> None:
    print(f"RESET {key}" + (f"={value}" if value != "" else ""), flush=True)


def now_ms() -> int:
    return int(time.time() * 1000)


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sh(*args: str, check: bool = True, **kw) -> subprocess.CompletedProcess:
    p = subprocess.run(list(args), capture_output=True, text=True, **kw)
    if check and p.returncode != 0:
        raise Blocco(f"comando_fallito:{Path(args[0]).name}:{' '.join(args[1:3])}:{p.returncode}")
    return p


def active(unit: str) -> bool:
    return sh(SYSTEMCTL, "is-active", "--quiet", unit, check=False).returncode == 0


def stage_dir() -> Path:
    dirs = {sh(SYSTEMCTL, "show", "-p", "WorkingDirectory", "--value", r[k]).stdout.strip()
            for r in RUNS for k in ("exit", "runner")}
    if len(dirs) != 1:
        raise Blocco("codice_installato_non_univoco")
    d = Path(dirs.pop())
    if not d.is_absolute() or not (d / "backend" / "v3").is_dir():
        raise Blocco("codice_installato_assente")
    return d


def ro_copy(db: Path, tmp: Path) -> Path:
    dst = tmp / f"{db.parent.name}-{db.name}"
    s = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    d = sqlite3.connect(str(dst))
    with d:
        s.backup(d)
    s.close()
    d.close()
    return dst


def journal_view(run_dir: Path, run_id: str):
    """(numero eventi, catena verificata, riepilogo) da una copia in sola lettura del journal."""
    from backend.v3.dashboard import build_summary
    from backend.v3.events import EventJournal
    tmp = Path(tempfile.mkdtemp(prefix="reset-ro-"))
    try:
        j = EventJournal(str(ro_copy(run_dir / "journal.db", tmp)))
        count, _head = j.verify_chain()
        rows = j.list_run("brain", run_id)
        return count, rows, build_summary(j, "brain", run_id)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def heartbeat(run_dir: Path) -> dict:
    try:
        h = json.loads((run_dir / "heartbeat.json").read_text())
        return h if isinstance(h, dict) else {}
    except (OSError, ValueError):
        return {}


def wait(cond, seconds: float, code: str):
    end = time.time() + seconds
    while True:
        v = cond()
        if v:
            return v
        if time.time() > end:
            raise Blocco(code)
        time.sleep(POLL)


def fsd(script: str, *args: str) -> subprocess.CompletedProcess:
    p = sh("sh", str(FSD / script), *args, check=False)
    for line in (p.stdout + p.stderr).splitlines():
        print("   | " + line, flush=True)
    if p.returncode != 0:
        raise Blocco(f"{script}_{'_'.join(args[:2])}_fallito")
    return p


def exits_healthy(stage: Path, r: dict) -> bool:
    p = sh(E.get("RESET_PY", sys.executable), str(FSD / "controlli.py"), str(PARENT / r["dir"]), r["id"], "uscite",
           check=False, cwd=str(stage), env=dict(E, DESK_MODE="paper", PYTHONPATH=str(stage), PYTHONDONTWRITEBYTECODE="1"))
    return p.returncode == 0


def manifest(root: Path) -> dict:
    out = {}
    for base, _dirs, files in os.walk(root):
        for f in files:
            p = Path(base) / f
            if not p.is_symlink():
                out[str(p.relative_to(root))] = sha_file(p)
    return out


# ------------------------------------------------------------------ controlli preliminari (nessuna modifica)
def preflight() -> dict:
    from backend.v3.runner.config import load_runner_config
    if not TEST and os.geteuid() != 0:
        raise Blocco("serve_root")
    for f, want in PINNED.items():
        p = FSD / f
        if not p.is_file() or p.is_symlink() or sha_file(p) != want:
            raise Blocco(f"pacchetto_installato_modificato:{f}")
    stage = stage_dir()
    say("CODICE_INSTALLATO", stage)
    if not (RC1 / "pause.flag").is_file() or not active(RC1_EXIT):
        raise Blocco("brain_rc1_non_in_pausa_o_uscite_ferme")
    say("BRAIN_RC1", "IN_PAUSA_NON_TOCCATO")
    for u in [BRIDGE] + [r[k] for r in RUNS for k in ("exit", "runner")]:
        if not active(u):
            raise Blocco(f"unita_non_attiva:{u}")
    if sh(DOCKER, "inspect", "superbot", "--format", "{{.State.Status}}", check=False).stdout.strip() != "running":
        raise Blocco("web_non_in_esecuzione")
    ctx = {"stage": stage, "runs": []}
    for r in RUNS:
        cfg_path = HERE / r["config"]
        raw = cfg_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != r["sha"]:
            raise Blocco(f"configurazione_nuova_impronta_errata:{r['bot']}")
        c = load_runner_config(raw)
        if (str(c.initial_equity), str(c.daily_loss_halt), str(c.risk_policy.minimum_equity)) != (
                r["equity"], r["halt"], r["floor"]) or (c.risk_policy.min_leverage, c.risk_policy.max_leverage) != (15, 45) \
                or (str(c.risk_policy.max_loss_fraction), str(c.risk_policy.max_open_risk_fraction)) != ("0.04", "0.10") \
                or c.guardian is None:
            raise Blocco(f"configurazione_nuova_inattesa:{r['bot']}")
        # stop giornaliero effettivamente utilizzabile: sopra floor e blocco globale
        if not (c.initial_equity * (1 - c.daily_loss_halt) > c.risk_policy.minimum_equity
                and c.daily_loss_halt < c.guardian.global_drawdown_lock):
            raise Blocco(f"stop_giornaliero_non_utilizzabile:{r['bot']}")
        run_dir = PARENT / r["dir"]
        if not run_dir.is_dir() or run_dir.is_symlink() or not (run_dir / "PREPARED_PAUSED_ONLY.json").is_file():
            raise Blocco(f"run_attuale_assente:{r['bot']}")
        if os.stat(run_dir).st_dev != os.stat(PARENT).st_dev:
            raise Blocco(f"run_su_un_altro_disco:{r['bot']}")
        count, rows, summ = journal_view(run_dir, r["id"])
        try:
            m = json.loads((run_dir / "mandate.json").read_text())
        except (OSError, ValueError):
            raise Blocco(f"mandato_attuale_illeggibile:{r['bot']}") from None
        who = m.get("approved_by") if m.get("approved") is True else None
        if not isinstance(who, str) or not NAME_RE.fullmatch(who):
            raise Blocco(f"nome_di_chi_approva_non_disponibile:{r['bot']}")
        say(f"RUN_ATTUALE_{r['bot']}", f"journal {count} eventi catena integra; aperte {len(summ.open_positions)}; "
                                       f"chiuse {len(summ.closed_trades)}")
        ctx["runs"].append({**r, "raw": raw, "cfg": c, "who": who, "run_dir": run_dir})
    free = shutil.disk_usage(PARENT).free
    used = sum(f.stat().st_size for r in RUNS for f in (PARENT / r["dir"]).rglob("*") if f.is_file())
    if free < 3 * used + 50_000_000:
        raise Blocco("spazio_disco_insufficiente")
    if not TEST and not Path("/etc/superbot-v3-paper/brain-ai.env").is_file():
        raise Blocco("chiave_ai_assente")
    say("PREFLIGHT", "SUPERATO")
    return ctx


# ------------------------------------------------------------------ passi
class State:
    def __init__(self, stamp: str):
        STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = STATE_DIR / f"reset-{stamp}.state"
        self.stamp = stamp

    def mark(self, step: str) -> None:
        with open(self.path, "a") as f:
            f.write(step + "\n")
            f.flush()
            os.fsync(f.fileno())
        say("PASSO", step)

    def steps(self) -> list[str]:
        return self.path.read_text().split() if self.path.exists() else []


def pause_old(ctx: dict) -> int:
    t = now_ms()
    for r in ctx["runs"]:
        fsd("80-paper.sh", r["bot"], "pausa")
    for r in ctx["runs"]:                               # il giro in corso (anche una chiamata AI) deve essere finito
        hb = wait(lambda r=r: (lambda h: h if h.get("ts_ms", 0) >= t and h.get("state") in ("paused", "halted") else None)(
            heartbeat(r["run_dir"])), 900, f"runner_non_in_pausa:{r['bot']}")
        say(f"PAUSA_{r['bot']}", f"{hb.get('state')} {hb.get('last_error') or '-'}")
    return t


def close_open(ctx: dict, paused_ms: int) -> None:
    for r in ctx["runs"]:
        for attempt in range(4):
            _c, rows, summ = journal_view(r["run_dir"], r["id"])
            if any(x.event.kind == "paper_open" and x.event.occurred_at_ms > paused_ms for x in rows):
                raise Blocco(f"apertura_dopo_la_pausa:{r['bot']}")
            if not summ.open_positions:
                break
            if attempt == 3:
                raise Blocco(f"posizioni_ancora_aperte:{r['bot']}")
            say(f"CHIUSURA_{r['bot']}", f"{len(summ.open_positions)} posizioni aperte, tentativo {attempt + 1}")
            if not exits_healthy(ctx["stage"], r):
                raise Blocco(f"uscite_non_sane_per_chiudere:{r['bot']}")
            ts = now_ms()
            req = r["run_dir"] / "close_request.json"
            fd, tmp = tempfile.mkstemp(dir=r["run_dir"], prefix=".close_request.")
            with os.fdopen(fd, "w") as f:
                json.dump({"ts_ms": ts, "all": True}, f)
            os.chmod(tmp, 0o600)
            os.replace(tmp, req)

            def done(r=r, ts=ts):
                try:
                    res = json.loads((r["run_dir"] / "close_result.json").read_text())
                except (OSError, ValueError):
                    return None
                return res if res.get("request_ts_ms") == ts else None
            res = wait(done, 300, f"chiusura_non_eseguita:{r['bot']}")
            say(f"CHIUSURA_ESITO_{r['bot']}", f"{res.get('status')} chiuse {len(res.get('closed') or [])} "
                                              f"fallite {len(res.get('failed') or [])}")
        _c, _rows, summ = journal_view(r["run_dir"], r["id"])
        if summ.open_positions:
            raise Blocco(f"posizioni_ancora_aperte:{r['bot']}")
        realized = sum((t.realized_pnl for t in summ.closed_trades), Decimal(0))
        r["risultati"] = {"run_id": r["id"], "initial_equity": str(json.loads(
            (r["run_dir"] / "runner_config.json").read_text())["initial_equity"]), "closed_trades": len(summ.closed_trades),
            "realized_pnl": str(realized), "open_positions": 0, "closed_at_ms": now_ms()}
        say(f"CONTABILIZZATA_{r['bot']}", f"chiuse {len(summ.closed_trades)}, aperte 0")


def stop_units(ctx: dict) -> None:
    for r in ctx["runs"]:
        sh(SYSTEMCTL, "stop", r["runner"])
        sh(SYSTEMCTL, "stop", r["exit"])
    for r in ctx["runs"]:
        wait(lambda r=r: not active(r["runner"]) and not active(r["exit"]), 120, f"unita_non_fermate:{r['bot']}")
    say("VECCHI_RUNNER", "FERMATI (nessuna sovrapposizione)")


def archive(ctx: dict, st: State) -> Path:
    base = PARENT / ".archivio" / f"reset-{st.stamp}"
    base.mkdir(parents=True, mode=0o700)
    os.chmod(PARENT / ".archivio", 0o700)
    for r in ctx["runs"]:
        src, dst = r["run_dir"], base / r["dir"]
        dst.mkdir(mode=0o700)
        before = manifest(src)
        (base / f"{r['dir']}.SHA256SUMS").write_text("".join(f"{h}  {p}\n" for p, h in sorted(before.items())))
        for entry in sorted(os.listdir(src)):
            os.rename(src / entry, dst / entry)
        if os.listdir(src):
            raise Blocco(f"cartella_non_svuotata:{r['bot']}")
        if manifest(dst) != before:
            raise Blocco(f"archivio_non_identico:{r['bot']}")
        count, _rows, _s = journal_view(dst, r["id"])
        res = dict(r.get("risultati") or {}, journal_events=count, archived_from=str(src))
        (base / f"{r['dir']}.RISULTATI.json").write_text(json.dumps(res, indent=1, sort_keys=True))
        say(f"ARCHIVIATA_{r['bot']}", f"{dst} ({len(before)} file, impronte verificate, journal {count} eventi integro)")
    for f in base.rglob("*"):
        os.chmod(f, 0o700 if f.is_dir() else (f.stat().st_mode & 0o700))
    return base


def prepare_new(ctx: dict, st: State) -> int:
    from backend.v3.runner.prepare_paper_run import prepare_new_paper_run
    from backend.v3.runner.prepared_config_guard import verify_prepared_run_config
    staging = PARENT / f".reset-{st.stamp}"
    staging.mkdir(mode=0o700)
    t = now_ms()
    for r in ctx["runs"]:
        root = prepare_new_paper_run(parent=staging, run_name=r["dir"], run_id=r["id"], config_bytes=r["raw"],
                                     desk_mode="paper", now_ms=t, expected_initial_equity=r["equity"])
        for entry in sorted(os.listdir(root)):
            os.rename(root / entry, r["run_dir"] / entry)
        root.rmdir()
        verify_prepared_run_config(data_dir=r["run_dir"], run_id=r["id"], config=r["cfg"])
        count, rows, summ = journal_view(r["run_dir"], r["id"])
        m = json.loads((r["run_dir"] / "mandate.json").read_text())
        if (count != 1 or [x.event.kind for x in rows] != ["run_prepared"] or summ.open_positions or summ.closed_trades
                or not (r["run_dir"] / "pause.flag").is_file() or m.get("approved") is not False):
            raise Blocco(f"run_nuova_non_conforme:{r['bot']}")
        say(f"RUN_NUOVA_{r['bot']}", f"{r['id']} capitale {r['equity']}, journal nuovo 1 evento, in pausa, mandato da approvare")
    staging.rmdir()
    return t


def start_units(ctx: dict) -> None:
    for r in ctx["runs"]:
        sh(SYSTEMCTL, "start", r["exit"])
        wait(lambda r=r: exits_healthy(ctx["stage"], r), 180, f"uscite_nuove_non_sane:{r['bot']}")
        t = now_ms()
        sh(SYSTEMCTL, "start", r["runner"])
        hb = wait(lambda r=r, t=t: (lambda h: h if h.get("ts_ms", 0) >= t else None)(heartbeat(r["run_dir"])), 300,
                  f"runner_nuovo_senza_battito:{r['bot']}")
        say(f"AVVIATA_{r['bot']}", f"uscite sane; runner {hb.get('state')} {hb.get('last_error') or '-'}")


def probe(mode: str, reset_ms: int) -> None:
    p = sh(DOCKER, "exec", "-i", "superbot", "python3", "-B", "-", mode, str(reset_ms), check=False,
           input=(HERE / "reset_probe.py").read_text(), timeout=120)
    for line in (p.stdout.splitlines() + [x for x in p.stderr.splitlines() if x.strip()][-5:]):
        print("   | " + line, flush=True)
    if p.returncode != 0 or "RESULT=PASS" not in p.stdout:
        raise Blocco(f"dashboard_{mode}_non_conforme")


def activate(ctx: dict) -> None:
    for r in ctx["runs"]:
        t = now_ms()
        fsd("80-paper.sh", r["bot"], "attiva", r["who"])
        hb = wait(lambda r=r, t=t: (lambda h: h if h.get("ts_ms", 0) >= t and h.get("state") == "running" else None)(
            heartbeat(r["run_dir"])), 300, f"runner_non_running:{r['bot']}")
        say(f"RUNNING_{r['bot']}", f"{r['id']} {hb.get('state')} (mandato approvato da {r['who']})")


def rollback(stamp: str, *, automatic: bool = False) -> None:
    base = PARENT / ".archivio" / f"reset-{stamp}"
    if not base.is_dir():
        raise Blocco("archivio_del_reset_assente")
    scart = PARENT / ".archivio" / f"reset-{stamp}-run-nuove-scartate"
    scart.mkdir(parents=True, exist_ok=True, mode=0o700)
    for r in RUNS:
        run_dir, old = PARENT / r["dir"], base / r["dir"]
        if (run_dir / "pause.flag").parent.is_dir():
            (run_dir / "pause.flag").write_text("pausa del rollback del reset\n")
        sh(SYSTEMCTL, "stop", r["runner"], check=False)
        sh(SYSTEMCTL, "stop", r["exit"], check=False)
        wait(lambda r=r: not active(r["runner"]) and not active(r["exit"]), 120, f"unita_non_fermate:{r['bot']}")
        if not old.is_dir() or not os.listdir(old):
            continue                                     # gia' ripristinata o mai archiviata
        if (base / f"{r['dir']}.RISULTATI.json").is_file():   # archivio completo: nella cartella c'e' la run nuova
            dst = scart / r["dir"]
            dst.mkdir(exist_ok=True, mode=0o700)
            for entry in sorted(os.listdir(run_dir)):
                os.rename(run_dir / entry, dst / entry)
        for entry in sorted(os.listdir(old)):
            if (run_dir / entry).exists():
                raise Blocco(f"rollback_conflitto:{r['bot']}:{entry}")
            os.rename(old / entry, run_dir / entry)
        want = dict(line.split("  ", 1)[::-1] for line in (base / f"{r['dir']}.SHA256SUMS").read_text().splitlines())
        if manifest(run_dir) != want:
            raise Blocco(f"rollback_impronte_diverse:{r['bot']}")
        (run_dir / "pause.flag").exists() or (run_dir / "pause.flag").write_text("pausa del rollback del reset\n")
        sh(SYSTEMCTL, "start", r["exit"], check=False)
        sh(SYSTEMCTL, "start", r["runner"], check=False)
        say(f"RIPRISTINATA_{r['bot']}", "run precedente al suo posto, IN PAUSA (impronte verificate)")
    say("RESULT", "ROLLBACK_AUTOMATICO_RUN_PRECEDENTI_IN_PAUSA" if automatic else "ROLLBACK_RUN_PRECEDENTI_IN_PAUSA")


def esegui() -> int:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ctx = preflight()
    st = State(stamp)
    say("TIMBRO", stamp)
    st.mark("inizio")
    paused_ms = pause_old(ctx)                      # un blocco qui: run vecchie intatte, in pausa
    st.mark("vecchie_in_pausa")
    close_open(ctx, paused_ms)
    st.mark("posizioni_chiuse_e_contabilizzate")
    try:
        stop_units(ctx)
        st.mark("vecchi_runner_fermati")
        base = archive(ctx, st)
        st.mark("archiviate")
        reset_ms = prepare_new(ctx, st)
        st.mark("run_nuove_preparate")
        start_units(ctx)
        st.mark("run_nuove_avviate_in_pausa")
        probe("paused", reset_ms)
        st.mark("dashboard_verificata_in_pausa")
    except Exception as exc:                                  # noqa: BLE001
        say("BLOCCO", exc.args[0] if isinstance(exc, Blocco) else f"{type(exc).__name__}")
        if "archiviate" in st.steps() or (PARENT / ".archivio" / f"reset-{stamp}").is_dir():
            rollback(stamp, automatic=True)
        else:
            for r in RUNS:                                    # niente archiviato: si riavviano le vecchie, in pausa
                sh(SYSTEMCTL, "start", r["exit"], check=False)
                sh(SYSTEMCTL, "start", r["runner"], check=False)
        say("RESULT", "NO_GO_RIPARTENZA_NON_ESEGUITA")
        return 4
    try:
        activate(ctx)
        st.mark("run_nuove_attive")
        probe("active", reset_ms)
        st.mark("dashboard_verificata_attiva")
    except Exception as exc:                                  # noqa: BLE001
        say("BLOCCO", exc.args[0] if isinstance(exc, Blocco) else f"{type(exc).__name__}")
        for r in ctx["runs"]:
            sh("sh", str(FSD / "80-paper.sh"), r["bot"], "pausa", check=False)
        say("RESULT", f"NO_GO_RUN_NUOVE_PRONTE_MA_IN_PAUSA (rollback: --rollback {stamp})")
        return 5
    if not (RC1 / "pause.flag").is_file():
        say("ATTENZIONE", "brain_rc1_non_in_pausa")
        return 6
    say("ARCHIVIO", base)
    say("ROLLBACK", f"--rollback {stamp}")
    say("RESULT", "RIPARTENZA_PAPER_ATTIVA")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="reset e ripartenza PAPER Falco Evoluto / Brain Scalp")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--esegui", action="store_true")
    g.add_argument("--controlla", action="store_true")
    g.add_argument("--rollback", metavar="TIMBRO")
    a = ap.parse_args(argv)
    try:
        if a.controlla:
            preflight()
            say("RESULT", "CONTROLLI_SUPERATI_NESSUNA_MODIFICA")
            return 0
        if a.rollback:
            if not TEST and os.geteuid() != 0:
                raise Blocco("serve_root")
            rollback(a.rollback)
            return 0
        return esegui()
    except Blocco as exc:
        say("BLOCCO", exc.args[0])
        say("RESULT", "NO_GO")
        return 3


if __name__ == "__main__":
    sys.exit(main())
