"""Aggiorna i limiti giornalieri di UNA run PAPER (Falco Evoluto o Brain Scalp), con copia di sicurezza e rollback.

Uso (root, solo il proprietario; ``--controlla`` non cambia nulla):
    PYTHONPATH=<codice installato> <python della stage> aggiorna_limiti.py --bot scalp|falco --controlla --nuova <json>
    ... --bot scalp --applica --nuova <json> --approvato-da "<nome>"
    ... --bot scalp --rollback [--copia <cartella di backup>]

Cosa cambia: SOLO ``daily_loss_warn_fraction``, ``daily_loss_halt_fraction`` e ``guardian.session_loss_fraction`` del
``runner_config.json`` della run (contenuti e impronte bloccati qui sotto), e l'impronta ``config_sha256`` del
marcatore ``PREPARED_PAUSED_ONLY.json`` (gli altri sei campi restano identici), perche' runner e servizio uscite
rifiutano di avviarsi se marcatore e configurazione non coincidono. Ogni modifica e' annotata in
``CONFIG_AMENDMENTS.jsonl`` (solo aggiunte) nella cartella della run e nella copia di sicurezza.

Cosa NON tocca mai: journal e budget (mai aperti in scrittura), mandato, pausa, ``daily_loss.json`` (il freno agganciato
non si cancella e, nel rollback, non si ripristina all'indietro), servizio uscite (non riavviato: deve restare lo stesso
processo), codice, strategie, rischio per trade/aperto, leva, margini, floor e protezione dei profitti.

Rifiuta (senza cambiare nulla) se: configurazione in uso diversa da quella attesa; marcatore incoerente; mandato non
approvato o non piu' valido; freno giornaliero agganciato OGGI (qualunque motivo: lo si lascia scadere a 00:00 UTC);
nessuna valutazione del Guardian nella sessione corrente, oppure l'ultima e' bloccata per perdita di sessione (il nuovo
limite toglierebbe un blocco gia' scattato: si attende il cambio di sessione delle 08:00 Europe/Rome).
Dopo l'applicazione riavvia SOLO il runner e controlla battito, motivo e servizio uscite; se un controllo fallisce
ripristina da solo la configurazione precedente.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUNS = {
    "falco": {"dir": "brain-v3-falco-evoluto-p1", "run_id": "falco-evoluto-paper-p1",
              "runner": "superbot-falco-evoluto-p1-runner.service", "exit": "superbot-falco-evoluto-p1-exit.service",
              "old_sha": "65bf6f599964bccd7d10b84a2c913d969d262b0407dd1e774ac2cb128cafc877",
              "new_sha": "98b52a3bb82bb0e7dfe76d42558d7515aff0608371db2301140da208db2839cd"},
    "scalp": {"dir": "brain-v3-brain-scalp-p1", "run_id": "brain-scalp-paper-p1",
              "runner": "superbot-brain-scalp-p1-runner.service", "exit": "superbot-brain-scalp-p1-exit.service",
              "old_sha": "dd0c6907aef744e42b0341a64204d27fc04546307a8e6b6b35809b47006ba5de",
              "new_sha": "a31bedc567dc8753611f34d1ec0c372e6a7b59b5588f757ee933c0c9d7f7ea29"},
}
CHANGED = ("daily_loss_warn", "daily_loss_halt", "guardian.session_loss_fraction")
PARENT = Path(os.environ.get("LIMITI_PARENT", "/opt/superbot-v3-paper-runs"))
BACKUPS = Path(os.environ.get("LIMITI_BACKUPS", "/opt/superbot-v3-backups"))
TEST_MODE = os.environ.get("LIMITI_TEST_MODE") == "1"
SYSTEMCTL = os.environ.get("LIMITI_SYSTEMCTL", "systemctl")
BACKUP_FILES = ("runner_config.json", "PREPARED_PAUSED_ONLY.json", "mandate.json", "daily_loss.json", "heartbeat.json")
RESTORE_FILES = ("runner_config.json", "PREPARED_PAUSED_ONLY.json")      # mai daily_loss.json, mai il mandato
DAY_MS = 86_400_000


class Rifiuto(Exception):
    pass


def say(k: str, v: object = "") -> None:
    print(f"LIMITI_{k}={v}" if v != "" else f"LIMITI_{k}", flush=True)


def now_ms() -> int:
    return int(os.environ.get("LIMITI_NOW_MS") or time.time() * 1000)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write_atomic(path: Path, data: bytes, like: Path) -> None:
    """Scrittura atomica nella stessa cartella, con proprietario e permessi del file ``like``."""
    st = like.stat()
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, st.st_mode & 0o777)
        if not TEST_MODE:
            os.chown(tmp, st.st_uid, st.st_gid)
        os.replace(tmp, path)
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def config_fields_diff(a, b) -> list[str]:
    out = [f.name for f in dataclasses.fields(a) if f.name != "guardian" and getattr(a, f.name) != getattr(b, f.name)]
    if (a.guardian is None) != (b.guardian is None):
        out.append("guardian")
    elif a.guardian is not None:
        out += [f"guardian.{f.name}" for f in dataclasses.fields(a.guardian)
                if getattr(a.guardian, f.name) != getattr(b.guardian, f.name)]
    return sorted(out)


def latest_guardian(run_dir: Path) -> tuple[int, dict] | None:
    """Ultima valutazione del Guardian dal journal, letto in sola lettura (``mode=ro``): mai una scrittura."""
    db = run_dir / "journal.db"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    try:
        row = con.execute("SELECT occurred_at_ms, payload_json FROM v3_events WHERE kind='guardian_state' "
                          "ORDER BY seq DESC LIMIT 1").fetchone()
    finally:
        con.close()
    return None if row is None else (int(row[0]), json.loads(row[1]))


def controlla(bot: str, new_path: Path | None, *, per_applicare: bool) -> dict:
    """Tutti i controlli, senza scrivere nulla. Restituisce il contesto per l'applicazione."""
    from backend.v3.brain_f2.engine import _policy_hash
    from backend.v3.guardian import session_start_ms
    from backend.v3.runner.config import load_runner_config
    from backend.v3.runner.prepared_config_guard import verify_prepared_run_config

    r = RUNS[bot]
    run_dir = PARENT / r["dir"]
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise Rifiuto("run_assente")
    cfg_path, marker_path = run_dir / "runner_config.json", run_dir / "PREPARED_PAUSED_ONLY.json"
    cur_raw = cfg_path.read_bytes()
    cur_sha = sha(cur_raw)
    say("CONFIG_IN_USO_SHA256", cur_sha)
    if cur_sha == r["new_sha"]:
        raise Rifiuto("gia_applicata")
    if cur_sha != r["old_sha"]:
        raise Rifiuto("configurazione_in_uso_inattesa")
    cur = load_runner_config(cur_raw)
    verify_prepared_run_config(data_dir=run_dir, run_id=r["run_id"], config=cur)   # marcatore coerente oggi
    say("MARCATORE", "COERENTE")
    ctx = {"r": r, "run_dir": run_dir, "cur_raw": cur_raw, "cur": cur}
    if new_path is not None:
        new_raw = Path(new_path).read_bytes()
        if sha(new_raw) != r["new_sha"]:
            raise Rifiuto("nuova_configurazione_impronta_errata")
        new = load_runner_config(new_raw)
        diff = config_fields_diff(cur, new)
        if diff != sorted(CHANGED):
            raise Rifiuto("campi_cambiati_inattesi:" + ",".join(diff))
        say("CAMBIA", f"avviso {cur.daily_loss_warn}->{new.daily_loss_warn}; stop {cur.daily_loss_halt}->"
                      f"{new.daily_loss_halt}; sessione {cur.guardian.session_loss_fraction}->"
                      f"{new.guardian.session_loss_fraction}")
        ctx.update(new_raw=new_raw, new=new)
        if _policy_hash(new.risk_policy) != _policy_hash(cur.risk_policy):
            raise Rifiuto("politica_di_rischio_cambiata")
    try:
        mandate = json.loads((run_dir / "mandate.json").read_text())
    except (OSError, ValueError):
        raise Rifiuto("mandato_illeggibile") from None
    if (mandate.get("approved") is not True or mandate.get("run_id") != r["run_id"]
            or mandate.get("policy_hash") != _policy_hash(cur.risk_policy)):
        raise Rifiuto("mandato_non_valido")
    say("MANDATO", "VALIDO_ANCHE_DOPO (legato solo alla politica di rischio, invariata: nessuna nuova approvazione)")
    t = now_ms()
    day = t // DAY_MS * DAY_MS
    try:
        dl = json.loads((run_dir / "daily_loss.json").read_text())
    except (OSError, ValueError):
        dl = None
    latched = isinstance(dl, dict) and dl.get("halt_latched") is True and dl.get("day_start_ms") == day
    say("FRENO_GIORNALIERO", f"AGGANCIATO:{dl.get('latch_reason')}" if latched else "libero")
    g = latest_guardian(run_dir)
    s_start = session_start_ms(t, cur.guardian)
    if g is None or g[0] < s_start:
        g_state = "nessuna_valutazione_nella_sessione"
    else:
        g_state = f"{g[1].get('state')}:{','.join(g[1].get('reasons') or [])}"
    say("GUARDIAN_SESSIONE_CORRENTE", g_state)
    if per_applicare:
        if latched:
            raise Rifiuto("freno_giornaliero_agganciato_oggi: attendere 00:00 UTC, il blocco non si cancella")
        if g is None or g[0] < s_start:
            raise Rifiuto("nessuna_valutazione_del_guardian_nella_sessione: attendere il primo giro dopo le 08:00")
        if "session_loss" in (g[1].get("reasons") or []):
            raise Rifiuto("guardian_bloccato_per_perdita_di_sessione: attendere il cambio di sessione delle 08:00")
    return ctx


def main_pid(unit: str) -> str:
    out = subprocess.run([SYSTEMCTL, "show", "-p", "MainPID", "--value", unit], capture_output=True, text=True)
    return out.stdout.strip()


def is_active(unit: str) -> bool:
    return subprocess.run([SYSTEMCTL, "is-active", "--quiet", unit]).returncode == 0


def heartbeat(run_dir: Path) -> dict:
    try:
        h = json.loads((run_dir / "heartbeat.json").read_text())
        return h if isinstance(h, dict) else {}
    except (OSError, ValueError):
        return {}


def riavvia_e_verifica(r: dict, run_dir: Path, exit_pid: str, wait_s: int) -> None:
    t0 = now_ms()
    if subprocess.run([SYSTEMCTL, "restart", r["runner"]]).returncode != 0:
        raise Rifiuto("riavvio_runner_fallito")
    deadline = time.time() + wait_s
    hb = {}
    while time.time() < deadline:
        hb = heartbeat(run_dir)
        if isinstance(hb.get("ts_ms"), int) and hb["ts_ms"] >= t0:
            break
        time.sleep(2)
    else:
        raise Rifiuto("nessun_battito_dopo_il_riavvio")
    err = str(hb.get("last_error") or "")
    say("BATTITO", f"{hb.get('state')} {err or '-'} freno={hb.get('daily_loss_level')}:{hb.get('daily_loss_pct')}")
    if hb.get("state") not in ("running", "paused", "halted") or any(
            x in err for x in ("mandate", "prepared_config", "split_", "exit_service_unhealthy", "daily_loss_check")):
        raise Rifiuto("runner_non_sano_dopo_il_riavvio")
    if not is_active(r["runner"]) or not is_active(r["exit"]):
        raise Rifiuto("unita_non_attive")
    if main_pid(r["exit"]) != exit_pid:
        raise Rifiuto("servizio_uscite_riavviato_inatteso")
    say("USCITE", f"stesso processo {exit_pid}, non riavviato")


def annota(run_dir: Path, backup: Path, voce: dict) -> None:
    line = (json.dumps(voce, sort_keys=True) + "\n").encode()
    for d in (run_dir, backup):
        p = d / "CONFIG_AMENDMENTS.jsonl"
        fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)


def ripristina(ctx_dir: Path, backup: Path) -> None:
    sums = dict(line.split("  ", 1)[::-1] for line in (backup / "SHA256SUMS").read_text().splitlines())
    for f in RESTORE_FILES:
        data = (backup / f).read_bytes()
        if sha(data) != sums.get(f):
            raise Rifiuto(f"copia_di_sicurezza_alterata:{f}")
    for f in RESTORE_FILES:                                 # prima la configurazione, poi il marcatore
        write_atomic(ctx_dir / f, (backup / f).read_bytes(), ctx_dir / f)


def applica(bot: str, new_path: Path, approvato_da: str, wait_s: int) -> None:
    from backend.v3.runner.config import load_runner_config
    from backend.v3.runner.prepared_config_guard import verify_prepared_run_config
    if not approvato_da.strip():
        raise Rifiuto("approvato_da_mancante")
    ctx = controlla(bot, new_path, per_applicare=True)
    r, run_dir = ctx["r"], ctx["run_dir"]
    exit_pid = main_pid(r["exit"])
    if not exit_pid or exit_pid == "0" or not is_active(r["exit"]) or not is_active(r["runner"]):
        raise Rifiuto("unita_non_attive_prima")
    stamp = dt.datetime.fromtimestamp(now_ms() / 1000, dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUPS / f"limiti-{bot}-{stamp}"
    backup.mkdir(parents=True, mode=0o700)
    lines = []
    for f in BACKUP_FILES:
        if (run_dir / f).is_file():
            shutil.copy2(run_dir / f, backup / f)
            if sha((backup / f).read_bytes()) != sha((run_dir / f).read_bytes()) and f in RESTORE_FILES:
                raise Rifiuto(f"copia_non_verificata:{f}")
            lines.append(f"{sha((backup / f).read_bytes())}  {f}")
    (backup / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    say("COPIA_DI_SICUREZZA", backup)
    # nel marcatore cambia SOLO l'impronta (stessi byte per tutto il resto)
    marker_old = (run_dir / "PREPARED_PAUSED_ONLY.json").read_bytes()
    if marker_old.count(r["old_sha"].encode()) != 1:
        raise Rifiuto("marcatore_impronta_non_unica")
    marker_raw = marker_old.replace(r["old_sha"].encode(), sha(ctx["new_raw"]).encode())
    write_atomic(run_dir / "runner_config.json", ctx["new_raw"], run_dir / "runner_config.json")
    write_atomic(run_dir / "PREPARED_PAUSED_ONLY.json", marker_raw, run_dir / "PREPARED_PAUSED_ONLY.json")
    voce = {"at_ms": now_ms(), "action": "amend", "from_sha256": ctx["r"]["old_sha"], "to_sha256": sha(ctx["new_raw"]),
            "changed": {"daily_loss_warn_fraction": str(ctx["new"].daily_loss_warn),
                        "daily_loss_halt_fraction": str(ctx["new"].daily_loss_halt),
                        "guardian.session_loss_fraction": str(ctx["new"].guardian.session_loss_fraction)},
            "approved_by": approvato_da.strip(), "backup": str(backup)}
    annota(run_dir, backup, voce)
    restarted = False
    try:
        verify_prepared_run_config(data_dir=run_dir, run_id=r["run_id"],
                                   config=load_runner_config((run_dir / "runner_config.json").read_bytes()))
        say("MARCATORE", "COERENTE_CON_LA_NUOVA_CONFIGURAZIONE")
        restarted = True
        riavvia_e_verifica(r, run_dir, exit_pid, wait_s)
    except Exception as exc:                                       # noqa: BLE001
        say("CONTROLLO_FALLITO", (getattr(exc, "args", None) or [type(exc).__name__])[0])
        ripristina(run_dir, backup)
        annota(run_dir, backup, {"at_ms": now_ms(), "action": "auto_rollback", "backup": str(backup)})
        if restarted:                                  # il runner riparte con la configurazione precedente
            subprocess.run([SYSTEMCTL, "restart", r["runner"]])
        say("RESULT", "AUTO_ROLLBACK_CONFIGURAZIONE_PRECEDENTE")
        raise SystemExit(4)
    say("ROLLBACK_PRONTO", backup)
    say("RESULT", "LIMITI_AGGIORNATI")


def rollback(bot: str, copia: Path | None, wait_s: int) -> None:
    r = RUNS[bot]
    run_dir = PARENT / r["dir"]
    if copia is None:
        cands = sorted(BACKUPS.glob(f"limiti-{bot}-*"))
        if not cands:
            raise Rifiuto("nessuna_copia_di_sicurezza")
        copia = cands[-1]
    if sha((run_dir / "runner_config.json").read_bytes()) != r["new_sha"]:
        raise Rifiuto("configurazione_in_uso_non_e_quella_aggiornata")
    if sha((copia / "runner_config.json").read_bytes()) != r["old_sha"]:
        raise Rifiuto("copia_non_contiene_la_configurazione_precedente")
    exit_pid = main_pid(r["exit"])
    ripristina(run_dir, copia)
    annota(run_dir, copia, {"at_ms": now_ms(), "action": "rollback", "backup": str(copia)})
    say("RIPRISTINATI", ",".join(RESTORE_FILES) + " (daily_loss.json e mandato non toccati)")
    riavvia_e_verifica(r, run_dir, exit_pid, wait_s)
    say("RESULT", "LIMITI_PRECEDENTI_RIPRISTINATI")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bot", required=True, choices=sorted(RUNS))
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--controlla", action="store_true")
    mode.add_argument("--applica", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    ap.add_argument("--nuova", type=Path)
    ap.add_argument("--approvato-da", default="")
    ap.add_argument("--copia", type=Path)
    ap.add_argument("--attesa", type=int, default=180)
    a = ap.parse_args(argv)
    if not TEST_MODE and os.geteuid() != 0:
        print("serve root (le run sono 0700)", file=sys.stderr)
        return 2
    try:
        if a.controlla:
            controlla(a.bot, a.nuova, per_applicare=True)
            say("RESULT", "CONTROLLI_SUPERATI_NESSUNA_MODIFICA")
        elif a.applica:
            if a.nuova is None:
                raise Rifiuto("nuova_configurazione_mancante")
            applica(a.bot, a.nuova, a.approvato_da, a.attesa)
        else:
            rollback(a.bot, a.copia, a.attesa)
    except Rifiuto as exc:
        say("RIFIUTO", exc.args[0])
        say("RESULT", "NESSUNA_MODIFICA" if not a.rollback else "ROLLBACK_NON_ESEGUITO")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
