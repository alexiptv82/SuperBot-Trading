"""RIPARTENZA PAPER con il Brain unico da 2.000 USDT (24/11/2026): una sola procedura root, con archivio e rollback.

    ripartenza_brain.py --controlla --stage <codice nuovo>   controlli senza modifiche
    ripartenza_brain.py --esegui    --stage <codice nuovo>   pausa -> chiusura e contabilizzazione delle posizioni aperte
                                   di Falco Evoluto e Brain Scalp -> arresto -> archivio integrale delle due run ->
                                   unita' di Brain Scalp sul codice nuovo, unita' di Falco Evoluto disattivate -> run
                                   NUOVA (Brain unico, 2.000, journal nuovo) nello slot di Brain Scalp -> avvio uscite e
                                   runner -> verifica -> attivazione PAPER (80-paper.sh) -> RUNNING
    ripartenza_brain.py --rollback <TIMBRO>                  run precedenti al loro posto (IN PAUSA), unita' e codice
                                   precedenti, Falco Evoluto riattivato; la run nuova scartata resta conservata
    ripartenza_brain.py --nuova-sessione --stage <codice>   NUOVA SESSIONE del Brain unico (Brain Live Evolution, 24/11):
                                   solo con Brain in pausa, zero posizioni aperte e nessuna chiusura o richiesta in
                                   attesa -> arresto -> archivio integrale della sessione (operazioni, decisioni, memoria,
                                   P&L) -> unita' sul codice nuovo -> run nuova da 2.000 con la configurazione V2 e
                                   l'apprendimento delle sessioni archiviate in sola lettura -> avvio -> attivazione.
                                   Nessuna chiusura forzata: con posizioni aperte si ferma prima di cambiare qualcosa.

Si esegue con il codice NUOVO (``cwd`` e ``PYTHONPATH`` = cartella installata da ``30-codice.sh``): la configurazione
schema 3 si legge solo con quel codice. Slot riusato: stessa cartella, stesso run_id e stesse unita' di Brain Scalp,
quindi bridge di chiusura, ``superbot-ops`` e mount della web restano validi senza modifiche. Il vecchio contenuto
delle due run viene SPOSTATO (mai cancellato) in ``<runs>/.archivio/reset-<data>/<run>`` con le impronte di ogni file,
verificate dopo lo spostamento, e ``RISULTATI.json``. Brain RC1 non viene mai toccato (solo verificato in pausa).

Fallimenti: prima dell'archivio -> run vecchie intatte, in pausa, unita' riavviate. Durante unita'/preparazione/avvio ->
rollback automatico. Dopo l'avvio della run nuova -> run nuova lasciata IN PAUSA, rollback disponibile.
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
from typing import Optional

E = os.environ
PARENT = Path(E.get("RIP_PARENT", "/opt/superbot-v3-paper-runs"))
FSD = Path(E.get("RIP_FSD", "/root/falco-scalp-rilascio"))
STATE_DIR = Path(E.get("RIP_STATE", "/opt/superbot-v3-backups/brain-unico-2000"))
UNIT_DIR = Path(E.get("RIP_UNIT_DIR", "/etc/systemd/system"))
SYSTEMCTL = E.get("RIP_SYSTEMCTL", "systemctl")
DOCKER = E.get("RIP_DOCKER", "docker")
TEST = E.get("RIP_TEST_MODE") == "1"
POLL = float(E.get("RIP_POLL_S", "5"))
HERE = Path(__file__).resolve().parent
CONFIG_NAME = "runner_config_brain_unico_2000_paper.json"
CONFIG = Path(E["RIP_CONFIG"]) if TEST and E.get("RIP_CONFIG") else HERE / CONFIG_NAME   # nel pacchetto: accanto
RC1 = PARENT / "brain-v3-unico-paper-rc1"
RC1_EXIT = "superbot-brain-unico-rc1-exit.service"
BRIDGE = "superbot-v3-paper-single-close-bridge.service"
PINNED = {"80-paper.sh": "0fc1e6e1ee74ea50b890dc2c6917238a3d84b87b1bb9429c0e173b079182d0f1",
          "comune.sh": "c639a85c6e37ec03adc748586977817aee633e17848d9457adae1f652a3a66e0",
          "controlli.py": "638c4da73615e11439d4e92f89890b5ca92c031b7df789d358d2d92fe7210afd"}
if TEST and E.get("RIP_PINNED"):
    PINNED = json.loads(E["RIP_PINNED"])
FALCO = {"bot": "falco", "dir": "brain-v3-falco-evoluto-p1", "id": "falco-evoluto-paper-p1",
         "exit": "superbot-falco-evoluto-p1-exit.service", "runner": "superbot-falco-evoluto-p1-runner.service"}
SCALP = {"bot": "scalp", "dir": "brain-v3-brain-scalp-p1", "id": "brain-scalp-paper-p1",
         "exit": "superbot-brain-scalp-p1-exit.service", "runner": "superbot-brain-scalp-p1-runner.service"}
RUNS = (FALCO, SCALP)
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .-]{1,40}$")
ACTIVATION_WAIT_S = float(E.get("RIP_ACTIVATION_WAIT_S", "2400")) if TEST else 2400.0
STAGE_RE = re.compile(r"^/opt/superbot-falco-scalp-[0-9a-f]{12}$")


class Blocco(Exception):
    """Controllo indispensabile fallito: codice breve, mai segreti o importi reali."""


def say(key: str, value: object = "") -> None:
    print(f"RIPARTENZA {key}" + (f"={value}" if value != "" else ""), flush=True)


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


def workdir(unit: str) -> str:
    return sh(SYSTEMCTL, "show", "-p", "WorkingDirectory", "--value", unit).stdout.strip()


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
    """(numero eventi, eventi, riepilogo) da una copia in sola lettura del journal (catena verificata)."""
    from backend.v3.dashboard import build_summary
    from backend.v3.events import EventJournal
    tmp = Path(tempfile.mkdtemp(prefix="rip-ro-"))
    try:
        j = EventJournal(str(ro_copy(run_dir / "journal.db", tmp)))
        count, _head = j.verify_chain()
        return count, j.list_run("brain", run_id), build_summary(j, "brain", run_id)
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


def fsd(*args: str) -> None:
    p = sh("sh", str(FSD / "80-paper.sh"), *args, check=False)
    for line in (p.stdout + p.stderr).splitlines():
        print("   | " + line, flush=True)
    if p.returncode != 0:
        raise Blocco(f"80-paper_{'_'.join(args[:2])}_fallito")


def exits_healthy(stage: Path, r: dict) -> bool:
    p = sh(E.get("RIP_PY", sys.executable), str(FSD / "controlli.py"), str(PARENT / r["dir"]), r["id"], "uscite",
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
def check_config(raw: bytes):
    """La configurazione del Brain unico, letta con il codice nuovo: i valori decisi dal proprietario il 24/11."""
    from backend.v3.runner.config import load_runner_config
    c = load_runner_config(raw)
    p, u = c.risk_policy, c.unico
    ok = (c.initial_equity == Decimal("2000") and c.daily_loss_halt == Decimal("0.25") and u is not None
          and (p.min_leverage, p.max_leverage, p.max_positions, p.leverage_fit) == (15, 50, 10, True)
          and (p.max_loss_fraction, p.max_open_risk_fraction, p.max_total_margin_fraction, p.max_margin)
          == (Decimal("0.043"), Decimal("0.12"), Decimal("0.55"), Decimal("400"))
          and u.partial is not None and u.piggy is not None and c.guardian is not None and c.guardian.tiers is not None
          and c.initial_equity * (1 - c.daily_loss_halt) > p.minimum_equity
          and c.daily_loss_halt < c.guardian.global_drawdown_lock and c.analyst == "deepseek"
          and c.exit_policy is not None and c.exit_policy.max_hold_ms is None and u.claude is not None)
    if not ok:
        raise Blocco("configurazione_brain_unico_inattesa")
    return c


def preflight(stage: Path) -> dict:
    if not TEST and os.geteuid() != 0:
        raise Blocco("serve_root")
    for f, want in PINNED.items():
        p = FSD / f
        if not p.is_file() or p.is_symlink() or sha_file(p) != want:
            raise Blocco(f"pacchetto_installato_modificato:{f}")
    # ogni bot ha UNA cartella del codice (uscite e runner uguali); i due bot possono averne di diverse
    old_by_bot = {}
    for r in RUNS:
        dirs = {workdir(r[k]) for k in ("exit", "runner")}
        if len(dirs) != 1:
            raise Blocco(f"codice_installato_non_univoco:{r['bot']}")
        old_by_bot[r["bot"]] = dirs.pop()
    old = old_by_bot["scalp"]                            # solo lo slot di Brain Scalp passa al codice nuovo
    if not TEST and (not all(STAGE_RE.match(d) for d in old_by_bot.values()) or not STAGE_RE.match(str(stage))):
        raise Blocco("cartelle_del_codice_non_riconosciute")
    if str(stage) == old or not (stage / "backend" / "v3" / "unico.py").is_file():
        raise Blocco("codice_nuovo_assente_o_uguale")
    if Path.cwd().resolve() != stage.resolve():
        raise Blocco("eseguire_dalla_cartella_del_codice_nuovo")
    for bot, d in old_by_bot.items():
        say(f"CODICE_ATTUALE_{bot}", d)
    say("CODICE_NUOVO", stage)
    if not (RC1 / "pause.flag").is_file() or not active(RC1_EXIT):
        raise Blocco("brain_rc1_non_in_pausa_o_uscite_ferme")
    say("BRAIN_RC1", "IN_PAUSA_NON_TOCCATO")
    for u in [BRIDGE] + [r[k] for r in RUNS for k in ("exit", "runner")]:
        if not active(u):
            raise Blocco(f"unita_non_attiva:{u}")
        if not (UNIT_DIR / u).is_file() and u != BRIDGE:
            raise Blocco(f"file_unita_assente:{u}")
    if sh(DOCKER, "inspect", "superbot", "--format", "{{.State.Status}}", check=False).stdout.strip() != "running":
        raise Blocco("web_non_in_esecuzione")
    raw = CONFIG.read_bytes()
    if raw != (stage / "backend" / "v3" / "runner" / CONFIG_NAME).read_bytes():
        raise Blocco("configurazione_diversa_dal_commit")
    cfg = check_config(raw)
    ctx = {"stage": stage, "old": Path(old), "old_by_bot": {b: Path(d) for b, d in old_by_bot.items()},
           "raw": raw, "cfg": cfg, "runs": []}
    for r in RUNS:
        run_dir = PARENT / r["dir"]
        if not run_dir.is_dir() or run_dir.is_symlink() or not (run_dir / "PREPARED_PAUSED_ONLY.json").is_file():
            raise Blocco(f"run_attuale_assente:{r['bot']}")
        if os.stat(run_dir).st_dev != os.stat(PARENT).st_dev:
            raise Blocco(f"run_su_un_altro_disco:{r['bot']}")
        count, _rows, summ = journal_view(run_dir, r["id"])
        say(f"RUN_ATTUALE_{r['bot']}", f"journal {count} eventi catena integra; aperte {len(summ.open_positions)}; "
                                       f"chiuse {len(summ.closed_trades)}")
        ctx["runs"].append({**r, "run_dir": run_dir})
    try:
        m = json.loads((PARENT / SCALP["dir"] / "mandate.json").read_text())
    except (OSError, ValueError):
        raise Blocco("mandato_attuale_illeggibile") from None
    who = m.get("approved_by") if m.get("approved") is True else None
    if not isinstance(who, str) or not NAME_RE.fullmatch(who):
        raise Blocco("nome_di_chi_approva_non_disponibile")
    ctx["who"] = who
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
        self.path = STATE_DIR / f"ripartenza-{stamp}.state"
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
        fsd(r["bot"], "pausa")
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
            if not exits_healthy(ctx["old_by_bot"][r["bot"]], r):      # con il codice di QUEL bot
                raise Blocco(f"uscite_non_sane_per_chiudere:{r['bot']}")
            ts = now_ms()
            fd, tmp = tempfile.mkstemp(dir=r["run_dir"], prefix=".close_request.")
            with os.fdopen(fd, "w") as f:
                json.dump({"ts_ms": ts, "all": True}, f)
            os.chmod(tmp, 0o600)
            os.replace(tmp, r["run_dir"] / "close_request.json")

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
            "realized_pnl": str(realized), "open_positions": 0, "closed_at_ms": now_ms(),
            "motivo": "ripartenza Brain unico PAPER 2000 (24/11/2026)"}
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


def switch_units(ctx: dict, st: State) -> None:
    """Unita' di Brain Scalp sul codice nuovo (unica differenza ammessa: la cartella); Falco Evoluto disattivato."""
    bak = STATE_DIR / f"unita-{st.stamp}"
    bak.mkdir(mode=0o700)
    old, new = str(ctx["old"]), str(ctx["stage"])
    for r in ctx.get("unit_runs", RUNS):                  # nuova sessione: solo le unita' del Brain
        for k in ("exit", "runner"):
            shutil.copy2(UNIT_DIR / r[k], bak / r[k])
    for k in ("exit", "runner"):
        unit = SCALP[k]
        text = (bak / unit).read_text()
        changed = text.replace(old, new)
        if changed == text or changed.replace(new, old) != text:
            raise Blocco(f"unita_non_trasformabile:{unit}")
        tmp = UNIT_DIR / (unit + ".new")
        tmp.write_text(changed)
        os.chmod(tmp, 0o644)
        os.replace(tmp, UNIT_DIR / unit)
    sh(SYSTEMCTL, "daemon-reload")
    for k in ("exit", "runner"):
        if workdir(SCALP[k]) != new:
            raise Blocco(f"unita_non_sul_codice_nuovo:{SCALP[k]}")
        sh(SYSTEMCTL, "disable", FALCO[k], check=False)
    say("UNITA", f"Brain Scalp -> {new}; Falco Evoluto fermo e disattivato (backup unita' in {bak})")


def prepare_new(ctx: dict, st: State) -> int:
    from backend.v3.runner.prepare_paper_run import prepare_new_paper_run
    from backend.v3.runner.prepared_config_guard import verify_prepared_run_config
    staging = PARENT / f".ripartenza-{st.stamp}"
    staging.mkdir(mode=0o700)
    t = now_ms()
    run_dir = PARENT / SCALP["dir"]
    root = prepare_new_paper_run(parent=staging, run_name=SCALP["dir"], run_id=SCALP["id"], config_bytes=ctx["raw"],
                                 desk_mode="paper", now_ms=t, expected_initial_equity="2000")
    for entry in sorted(os.listdir(root)):
        os.rename(root / entry, run_dir / entry)
    root.rmdir()
    staging.rmdir()
    verify_prepared_run_config(data_dir=run_dir, run_id=SCALP["id"], config=ctx["cfg"])
    count, rows, summ = journal_view(run_dir, SCALP["id"])
    m = json.loads((run_dir / "mandate.json").read_text())
    if (count != 1 or [x.event.kind for x in rows] != ["run_prepared"] or summ.open_positions or summ.closed_trades
            or not (run_dir / "pause.flag").is_file() or m.get("approved") is not False):
        raise Blocco("run_nuova_non_conforme")
    say("RUN_NUOVA", f"{SCALP['id']} Brain unico, capitale 2000, journal nuovo 1 evento, in pausa, mandato da approvare")
    return t


def start_new(ctx: dict) -> None:
    run_dir = PARENT / SCALP["dir"]
    sh(SYSTEMCTL, "start", SCALP["exit"])
    wait(lambda: exits_healthy(ctx["stage"], SCALP), 180, "uscite_nuove_non_sane")
    t = now_ms()
    sh(SYSTEMCTL, "start", SCALP["runner"])
    hb = wait(lambda: (lambda h: h if h.get("ts_ms", 0) >= t else None)(heartbeat(run_dir)), 300,
              "runner_nuovo_senza_battito")
    say("AVVIATA", f"uscite sane; runner {hb.get('state')} {hb.get('last_error') or '-'} (codice nuovo, in pausa)")


def check_view(fresh: bool = True) -> None:
    """La dashboard nuova legge la run (stesso codice della web): Brain unico disponibile, 2.000; run appena creata:
    nessun trade e salvadanaio vuoto (``fresh``)."""
    from backend.v3.compare_view import RunRef, read_run
    out = read_run(RunRef("brain_scalp", "Brain", PARENT / SCALP["dir"], SCALP["id"]), now_ms())
    if (out.get("available") is not True or out.get("initial_equity") != "2000"
            or not (out.get("config") or {}).get("unico") or out.get("piggy") is None
            or (fresh and (out.get("closed") != 0 or out["piggy"].get("total") != "0"))):
        raise Blocco("vista_della_run_nuova_non_conforme")
    say("VISTA", "run nuova leggibile dalla dashboard: 2000, 0 trade, salvadanaio 0, Brain unico")


def activate(ctx: dict) -> None:
    run_dir = PARENT / SCALP["dir"]
    t = now_ms()
    fsd("scalp", "attiva", ctx["who"])
    # il primo battito "running" arriva a fine giro: con 27 mercati (e i consulti) un giro dura molti minuti
    hb = wait(lambda: (lambda h: h if h.get("ts_ms", 0) >= t and h.get("state") == "running" else None)(
        heartbeat(run_dir)), ACTIVATION_WAIT_S, "runner_non_running")
    cycle = ctx["cfg"].cycle_ms
    nxt = (now_ms() // cycle + 1) * cycle
    say("RUNNING", f"{SCALP['id']} {hb.get('state')} (mandato approvato da {ctx['who']}); primo giro entro le "
                   f"{dt.datetime.fromtimestamp(nxt / 1000, dt.timezone.utc):%H:%M} UTC")


def rollback(stamp: str, *, automatic: bool = False) -> None:
    base = PARENT / ".archivio" / f"reset-{stamp}"
    bak = STATE_DIR / f"unita-{stamp}"
    # nuova sessione: solo il Brain (Falco Evoluto non e' stato toccato e non va riattivato); altrimenti come sempre
    RUNS = [SCALP] if (STATE_DIR / f"nuova-sessione-{stamp}").is_file() else globals()["RUNS"]
    for r in RUNS:                                       # fermo tutto e rimetto le unita' com'erano
        run_dir = PARENT / r["dir"]
        if run_dir.is_dir() and os.listdir(run_dir):
            (run_dir / "pause.flag").write_text("pausa del rollback della ripartenza\n")
        sh(SYSTEMCTL, "stop", r["runner"], check=False)
        sh(SYSTEMCTL, "stop", r["exit"], check=False)
    for r in RUNS:
        wait(lambda r=r: not active(r["runner"]) and not active(r["exit"]), 120, f"unita_non_fermate:{r['bot']}")
    if bak.is_dir():
        for r in RUNS:
            for k in ("exit", "runner"):
                if (bak / r[k]).is_file():
                    shutil.copy2(bak / r[k], UNIT_DIR / r[k])
        sh(SYSTEMCTL, "daemon-reload")
        for r in RUNS:
            for k in ("exit", "runner"):
                sh(SYSTEMCTL, "enable", r[k], check=False)
        say("UNITA", "ripristinate (codice precedente), Falco Evoluto riattivato")
    if base.is_dir():
        scart = PARENT / ".archivio" / f"reset-{stamp}-run-nuova-scartata"
        scart.mkdir(parents=True, exist_ok=True, mode=0o700)
        for r in RUNS:
            run_dir, old = PARENT / r["dir"], base / r["dir"]
            if not old.is_dir() or not os.listdir(old):
                continue
            if os.listdir(run_dir):                      # nella cartella c'e' la run nuova: la conservo a parte
                dst = scart / r["dir"]
                dst.mkdir(exist_ok=True, mode=0o700)
                for entry in sorted(os.listdir(run_dir)):
                    os.rename(run_dir / entry, dst / entry)
            for entry in sorted(os.listdir(old)):
                os.rename(old / entry, run_dir / entry)
            want = dict(line.split("  ", 1)[::-1] for line in (base / f"{r['dir']}.SHA256SUMS").read_text().splitlines())
            if manifest(run_dir) != want:
                raise Blocco(f"rollback_impronte_diverse:{r['bot']}")
            (run_dir / "pause.flag").exists() or (run_dir / "pause.flag").write_text("pausa del rollback\n")
            say(f"RIPRISTINATA_{r['bot']}", "run precedente al suo posto, IN PAUSA (impronte verificate)")
    for r in RUNS:
        sh(SYSTEMCTL, "start", r["exit"], check=False)
        sh(SYSTEMCTL, "start", r["runner"], check=False)
    say("RESULT", "ROLLBACK_AUTOMATICO_RUN_PRECEDENTI_IN_PAUSA" if automatic else "ROLLBACK_RUN_PRECEDENTI_IN_PAUSA")


# ------------------------------------------------------------------ ripresa (run nuova gia' creata da un tentativo precedente)
def previous_restart() -> Optional[str]:
    """Timbro di una ripartenza precedente arrivata ad avviare la run nuova, se lo stato delle cartelle lo conferma:
    Falco Evoluto gia' archiviato (cartella vuota), slot di Brain Scalp con la configurazione del Brain unico, archivio
    completo delle due run. Altrimenti ``None`` (procedura normale)."""
    falco, scalp = PARENT / FALCO["dir"], PARENT / SCALP["dir"]
    try:
        if not falco.is_dir() or os.listdir(falco) or (scalp / "runner_config.json").read_bytes() != CONFIG.read_bytes():
            return None
    except OSError:
        return None
    for f in sorted(STATE_DIR.glob("ripartenza-*.state"), reverse=True):
        stamp = f.name[len("ripartenza-"):-len(".state")]
        base = PARENT / ".archivio" / f"reset-{stamp}"
        if ("run_nuova_avviata_in_pausa" in f.read_text().split()
                and all((base / f"{r['dir']}.RISULTATI.json").is_file() for r in RUNS)):
            return stamp
    return None


def resume_preflight(stage: Path, stamp: str) -> dict:
    if not TEST and os.geteuid() != 0:
        raise Blocco("serve_root")
    for f, want in PINNED.items():
        p = FSD / f
        if not p.is_file() or p.is_symlink() or sha_file(p) != want:
            raise Blocco(f"pacchetto_installato_modificato:{f}")
    dirs = {workdir(SCALP[k]) for k in ("exit", "runner")}
    if len(dirs) != 1:
        raise Blocco("codice_installato_non_univoco:scalp")
    old = dirs.pop()
    if not TEST and (not STAGE_RE.match(old) or not STAGE_RE.match(str(stage))):
        raise Blocco("cartelle_del_codice_non_riconosciute")
    if not (stage / "backend" / "v3" / "unico.py").is_file() or Path.cwd().resolve() != stage.resolve():
        raise Blocco("eseguire_dalla_cartella_del_codice_nuovo")
    if not (RC1 / "pause.flag").is_file() or not active(RC1_EXIT):
        raise Blocco("brain_rc1_non_in_pausa_o_uscite_ferme")
    for u in (BRIDGE, SCALP["exit"], SCALP["runner"]):
        if not active(u):
            raise Blocco(f"unita_non_attiva:{u}")
    if any(active(FALCO[k]) for k in ("exit", "runner")):
        raise Blocco("falco_evoluto_ancora_attivo")
    if sh(DOCKER, "inspect", "superbot", "--format", "{{.State.Status}}", check=False).stdout.strip() != "running":
        raise Blocco("web_non_in_esecuzione")
    raw = CONFIG.read_bytes()
    if raw != (stage / "backend" / "v3" / "runner" / CONFIG_NAME).read_bytes():
        raise Blocco("configurazione_diversa_dal_commit")
    cfg = check_config(raw)
    run_dir = PARENT / SCALP["dir"]
    count, _rows, summ = journal_view(run_dir, SCALP["id"])
    base = PARENT / ".archivio" / f"reset-{stamp}"
    try:                                                 # chi approva: dal mandato della run Scalp ARCHIVIATA
        m = json.loads((base / SCALP["dir"] / "mandate.json").read_text())
    except (OSError, ValueError):
        raise Blocco("mandato_archiviato_illeggibile") from None
    who = m.get("approved_by") if m.get("approved") is True else None
    if not isinstance(who, str) or not NAME_RE.fullmatch(who):
        raise Blocco("nome_di_chi_approva_non_disponibile")
    say("RIPRESA", f"run Brain unico gia' creata dalla ripartenza {stamp}: journal {count} eventi, aperte "
                   f"{len(summ.open_positions)}; Falco Evoluto gia' archiviato; codice attuale {old}")
    say("PREFLIGHT", "SUPERATO")
    return {"stage": stage, "old": Path(old), "raw": raw, "cfg": cfg, "who": who, "runs": []}


def move_scalp_units(ctx: dict, bak: Path) -> None:
    """Solo le unita' di Brain Scalp: dalla cartella attuale a quella nuova (unica differenza ammessa)."""
    bak.mkdir(mode=0o700)
    old, new = str(ctx["old"]), str(ctx["stage"])
    for k in ("exit", "runner"):
        unit = SCALP[k]
        shutil.copy2(UNIT_DIR / unit, bak / unit)
        text = (bak / unit).read_text()
        changed = text.replace(old, new)
        if changed == text or changed.replace(new, old) != text:
            raise Blocco(f"unita_non_trasformabile:{unit}")
        tmp = UNIT_DIR / (unit + ".new")
        tmp.write_text(changed)
        os.chmod(tmp, 0o644)
        os.replace(tmp, UNIT_DIR / unit)
    sh(SYSTEMCTL, "daemon-reload")
    for k in ("exit", "runner"):
        if workdir(SCALP[k]) != new:
            raise Blocco(f"unita_non_sul_codice_nuovo:{SCALP[k]}")


def riprendi(stage: Path, prev: str) -> int:
    ctx = resume_preflight(stage, prev)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    st = State("ripresa-" + stamp)
    st.mark("inizio")
    run_dir = PARENT / SCALP["dir"]
    t = now_ms()
    fsd("scalp", "pausa")
    wait(lambda: (lambda h: h if h.get("ts_ms", 0) >= t and h.get("state") in ("paused", "halted") else None)(
        heartbeat(run_dir)), 2400, "runner_non_in_pausa:scalp")
    st.mark("in_pausa")
    bak = STATE_DIR / f"unita-ripresa-{stamp}"
    try:
        if ctx["old"] != ctx["stage"]:
            sh(SYSTEMCTL, "stop", SCALP["runner"])
            wait(lambda: not active(SCALP["runner"]), 120, "runner_non_fermato")
            move_scalp_units(ctx, bak)
            st.mark("unita_sul_codice_nuovo")
            sh(SYSTEMCTL, "restart", SCALP["exit"])
            wait(lambda: exits_healthy(ctx["stage"], SCALP), 180, "uscite_nuove_non_sane")
            t = now_ms()
            sh(SYSTEMCTL, "start", SCALP["runner"])
            wait(lambda: (lambda h: h if h.get("ts_ms", 0) >= t else None)(heartbeat(run_dir)), 300,
                 "runner_nuovo_senza_battito")
            say("AVVIATA", f"uscite sane e runner sul codice {ctx['stage']} (in pausa)")
        check_view(fresh=False)
        st.mark("vista_verificata")
    except Exception as exc:                                  # noqa: BLE001
        say("BLOCCO", exc.args[0] if isinstance(exc, Blocco) else type(exc).__name__)
        if bak.is_dir():                                      # unita' come prima della ripresa, run in pausa
            for k in ("exit", "runner"):
                if (bak / SCALP[k]).is_file():
                    shutil.copy2(bak / SCALP[k], UNIT_DIR / SCALP[k])
            sh(SYSTEMCTL, "daemon-reload", check=False)
            sh(SYSTEMCTL, "restart", SCALP["exit"], check=False)
            sh(SYSTEMCTL, "restart", SCALP["runner"], check=False)
        say("RESULT", "NO_GO_RIPRESA_NON_ESEGUITA_RUN_IN_PAUSA")
        return 4
    try:
        activate(ctx)
        st.mark("brain_unico_attivo")
    except Exception as exc:                                  # noqa: BLE001
        say("BLOCCO", exc.args[0] if isinstance(exc, Blocco) else type(exc).__name__)
        sh("sh", str(FSD / "80-paper.sh"), "scalp", "pausa", check=False)
        say("RESULT", f"NO_GO_RUN_NUOVA_PRONTA_MA_IN_PAUSA (rollback completo: --rollback {prev})")
        return 5
    say("ARCHIVIO", PARENT / ".archivio" / f"reset-{prev}")
    say("ROLLBACK", f"--rollback {prev}")
    say("RESULT", "BRAIN_UNICO_PAPER_RUNNING")
    return 0


def esegui(stage: Path) -> int:
    prev = previous_restart()
    if prev is not None:
        say("TIMBRO", prev)
        return riprendi(stage, prev)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ctx = preflight(stage)
    st = State(stamp)
    say("TIMBRO", stamp)
    st.mark("inizio")
    paused_ms = pause_old(ctx)
    st.mark("vecchie_in_pausa")
    close_open(ctx, paused_ms)
    st.mark("posizioni_chiuse_e_contabilizzate")
    try:
        stop_units(ctx)
        st.mark("vecchi_runner_fermati")
        archive(ctx, st)
        st.mark("archiviate")
        switch_units(ctx, st)
        st.mark("unita_sul_codice_nuovo")
        prepare_new(ctx, st)
        st.mark("run_nuova_preparata")
        start_new(ctx)
        st.mark("run_nuova_avviata_in_pausa")
        check_view()
        st.mark("vista_verificata")
    except Exception as exc:                                  # noqa: BLE001
        say("BLOCCO", exc.args[0] if isinstance(exc, Blocco) else type(exc).__name__)
        if "vecchi_runner_fermati" in st.steps():
            rollback(stamp, automatic=True)
        say("RESULT", "NO_GO_RIPARTENZA_NON_ESEGUITA")
        return 4
    try:
        activate(ctx)
        st.mark("brain_unico_attivo")
    except Exception as exc:                                  # noqa: BLE001
        say("BLOCCO", exc.args[0] if isinstance(exc, Blocco) else type(exc).__name__)
        sh("sh", str(FSD / "80-paper.sh"), "scalp", "pausa", check=False)
        say("RESULT", f"NO_GO_RUN_NUOVA_PRONTA_MA_IN_PAUSA (rollback: --rollback {stamp})")
        return 5
    if not (RC1 / "pause.flag").is_file():
        say("ATTENZIONE", "brain_rc1_non_in_pausa")
        return 6
    say("ARCHIVIO", PARENT / ".archivio" / f"reset-{stamp}")
    say("ROLLBACK", f"--rollback {stamp}")
    say("RESULT", "BRAIN_UNICO_PAPER_RUNNING")
    return 0


# ------------------------------------------------------------------ nuova sessione (Brain Live Evolution, 24/11)
PENDING = ("close_request.json", "brain_close_request.json", "strategy_request.json")


def session_preflight(stage: Path) -> dict:
    """Controlli della nuova sessione: niente cambia se uno solo fallisce."""
    if not TEST and os.geteuid() != 0:
        raise Blocco("serve_root")
    for f, want in PINNED.items():
        p = FSD / f
        if not p.is_file() or p.is_symlink() or sha_file(p) != want:
            raise Blocco(f"pacchetto_installato_modificato:{f}")
    dirs = {workdir(SCALP[k]) for k in ("exit", "runner")}
    if len(dirs) != 1:
        raise Blocco("codice_installato_non_univoco:scalp")
    old = dirs.pop()
    if not TEST and (not STAGE_RE.match(old) or not STAGE_RE.match(str(stage))):
        raise Blocco("cartelle_del_codice_non_riconosciute")
    if str(stage) == old or not (stage / "backend" / "v3" / "strategy_versions.py").is_file():
        raise Blocco("codice_nuovo_assente_o_uguale")
    if Path.cwd().resolve() != stage.resolve():
        raise Blocco("eseguire_dalla_cartella_del_codice_nuovo")
    say("CODICE_ATTUALE_scalp", old)
    say("CODICE_NUOVO", stage)
    if not (RC1 / "pause.flag").is_file() or not active(RC1_EXIT):
        raise Blocco("brain_rc1_non_in_pausa_o_uscite_ferme")
    if any(active(FALCO[k]) for k in ("exit", "runner")):
        raise Blocco("falco_evoluto_ancora_attivo")
    for u in (BRIDGE, SCALP["exit"], SCALP["runner"]):
        if not active(u):
            raise Blocco(f"unita_non_attiva:{u}")
    if sh(DOCKER, "inspect", "superbot", "--format", "{{.State.Status}}", check=False).stdout.strip() != "running":
        raise Blocco("web_non_in_esecuzione")
    raw = CONFIG.read_bytes()
    if raw != (stage / "backend" / "v3" / "runner" / CONFIG_NAME).read_bytes():
        raise Blocco("configurazione_diversa_dal_commit")
    cfg = check_config(raw)
    if cfg.unico is None or cfg.unico.entry is None:
        raise Blocco("configurazione_senza_politica_d_ingresso")
    run_dir = PARENT / SCALP["dir"]
    if not run_dir.is_dir() or run_dir.is_symlink() or not (run_dir / "PREPARED_PAUSED_ONLY.json").is_file():
        raise Blocco("run_attuale_assente:scalp")
    if not (run_dir / "pause.flag").is_file():
        raise Blocco("brain_non_in_pausa")
    pending = [f for f in PENDING if (run_dir / f).exists()]
    if pending:
        raise Blocco("richiesta_in_attesa:" + ",".join(pending))
    count, rows, summ = journal_view(run_dir, SCALP["id"])
    if summ.open_positions:
        raise Blocco(f"posizioni_aperte:{len(summ.open_positions)}")      # nessuna chiusura forzata
    say("RUN_ATTUALE_scalp", f"journal {count} eventi catena integra; aperte 0; chiuse {len(summ.closed_trades)}")
    try:
        m = json.loads((run_dir / "mandate.json").read_text())
    except (OSError, ValueError):
        raise Blocco("mandato_attuale_illeggibile") from None
    who = m.get("approved_by") if m.get("approved") is True else None
    if not isinstance(who, str) or not NAME_RE.fullmatch(who):
        raise Blocco("nome_di_chi_approva_non_disponibile")
    used = sum(f.stat().st_size for f in run_dir.rglob("*") if f.is_file())
    if shutil.disk_usage(PARENT).free < 3 * used + 50_000_000:
        raise Blocco("spazio_disco_insufficiente")
    if not TEST and not Path("/etc/superbot-v3-paper/brain-ai.env").is_file():
        raise Blocco("chiave_ai_assente")
    realized = sum((t.realized_pnl for t in summ.closed_trades), Decimal(0))
    old_cfg = json.loads((run_dir / "runner_config.json").read_text())
    risultati = {"run_id": SCALP["id"], "initial_equity": str(old_cfg["initial_equity"]),
                 "closed_trades": len(summ.closed_trades), "realized_pnl": str(realized), "open_positions": 0,
                 "closed_at_ms": now_ms(), "journal_head_count": count,
                 "motivo": "nuova sessione Brain unico PAPER 2000 con Brain Live Evolution (24/11/2026)"}
    say("PREFLIGHT", "SUPERATO")
    return {"stage": stage, "old": Path(old), "old_by_bot": {"scalp": Path(old)}, "raw": raw, "cfg": cfg, "who": who,
            "runs": [{**SCALP, "run_dir": run_dir, "risultati": risultati}], "unit_runs": [SCALP]}


def learning_sources() -> list[dict]:
    """Sessioni archiviate del Brain unico nello slot del Brain (journal in sola lettura): l'apprendimento continua."""
    out = []
    for res in sorted((PARENT / ".archivio").glob(f"reset-*/{SCALP['dir']}.RISULTATI.json")):
        j = res.parent / SCALP["dir"] / "journal.db"
        try:
            cfg = json.loads((res.parent / SCALP["dir"] / "runner_config.json").read_text())
            run_id = json.loads(res.read_text())["run_id"]
        except (OSError, ValueError, KeyError):
            continue
        if j.is_file() and cfg.get("analyst") == "deepseek":
            out.append({"journal": str(j), "run_id": run_id, "archive": res.parent.name})
    return out


def nuova_sessione(stage: Path) -> int:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ctx = session_preflight(stage)
    st = State(stamp)
    (STATE_DIR / f"nuova-sessione-{stamp}").write_text("nuova sessione del Brain unico: il rollback tocca solo il Brain\n")
    say("TIMBRO", stamp)
    st.mark("inizio_nuova_sessione")
    try:
        stop_units(ctx)
        st.mark("vecchi_runner_fermati")
        archive(ctx, st)
        st.mark("archiviate")
        switch_units(ctx, st)
        st.mark("unita_sul_codice_nuovo")
        prepare_new(ctx, st)
        src = learning_sources()
        run_dir = PARENT / SCALP["dir"]
        (run_dir / "learning_sources.json").write_text(json.dumps({"sources": src}, indent=1))
        say("APPRENDIMENTO", f"{len(src)} sessioni archiviate collegate in sola lettura (memoria degli esiti)")
        st.mark("run_nuova_preparata")
        start_new(ctx)
        st.mark("run_nuova_avviata_in_pausa")
        check_view()
        st.mark("vista_verificata")
    except Exception as exc:                                  # noqa: BLE001
        say("BLOCCO", exc.args[0] if isinstance(exc, Blocco) else type(exc).__name__)
        if "vecchi_runner_fermati" in st.steps():
            rollback(stamp, automatic=True)
        say("RESULT", "NO_GO_NUOVA_SESSIONE_NON_ESEGUITA")
        return 4
    try:
        activate(ctx)
        st.mark("brain_unico_attivo")
    except Exception as exc:                                  # noqa: BLE001
        say("BLOCCO", exc.args[0] if isinstance(exc, Blocco) else type(exc).__name__)
        sh("sh", str(FSD / "80-paper.sh"), "scalp", "pausa", check=False)
        say("RESULT", f"NO_GO_RUN_NUOVA_PRONTA_MA_IN_PAUSA (rollback: --rollback {stamp})")
        return 5
    say("ARCHIVIO", PARENT / ".archivio" / f"reset-{stamp}")
    say("ROLLBACK", f"--rollback {stamp}")
    say("RESULT", "BRAIN_UNICO_PAPER_RUNNING")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ripartenza PAPER con il Brain unico da 2000 USDT")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--esegui", action="store_true")
    g.add_argument("--nuova-sessione", action="store_true")
    g.add_argument("--controlla", action="store_true")
    g.add_argument("--rollback", metavar="TIMBRO")
    ap.add_argument("--stage")
    a = ap.parse_args(argv)
    try:
        if a.rollback:
            if not TEST and os.geteuid() != 0:
                raise Blocco("serve_root")
            if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", a.rollback):
                raise Blocco("timbro_non_valido")
            rollback(a.rollback)
            return 0
        if not a.stage:
            raise Blocco("serve_--stage")
        stage = Path(a.stage).resolve()
        if a.nuova_sessione:
            return nuova_sessione(stage)
        if a.controlla:
            prev = previous_restart()
            resume_preflight(stage, prev) if prev is not None else preflight(stage)
            say("RESULT", "CONTROLLI_SUPERATI_NESSUNA_MODIFICA")
            return 0
        return esegui(stage)
    except Blocco as exc:
        say("BLOCCO", exc.args[0])
        say("RESULT", "NO_GO")
        return 3


if __name__ == "__main__":
    sys.exit(main())
