"""Preparazione e attivazione delle TRE run PAPER dell'Arena (DeepSeek prova, Qwen, MiniMax), mai una alla volta.

Comandi (``python -m backend.v3.arena.trial_setup <comando> ...``):

* ``inspect`` (predefinito, SOLA LETTURA): stato verificabile delle tre run e del T0, con verdetto per codice.
* ``prepare-paused``: crea le tre run IN PAUSA, mandato NON approvato, SENZA T0, in una cartella di staging; le
  sposta al loro posto solo se tutte e tre sono valide. Se una run esiste gia', non tocca nulla. Nessuna chiamata AI.
* ``activate``: SOLO su autorizzazione dell'utente (frase di conferma con il T0). Richiede i tre servizi uscite sani,
  l'istantanea dell'universo coerente con le config, e scrive nell'ordine: T0 comune -> mandati approvati -> rimozione
  delle tre pause. Qualunque errore prima dell'ultimo passo riporta tutto allo stato precedente.

Non avvia servizi systemd, non abilita l'inferenza (``V3_ARENA_ALLOW_INFERENCE`` resta una scelta separata), non tocca
Brain storico, Falco o Toro. Uscita 0 = fatto/coerente, 2 = rifiutato o incompleto.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from decimal import Decimal
from datetime import date
from pathlib import Path
from typing import Callable, Mapping, Optional

from backend.v3.arena import openrouter_transport as ORT
from backend.v3.arena.budget_gate import budget_gate, load_evidence
from backend.v3.arena.prepare import FORBIDDEN_ROOTS, config_path, plan_for, prepare_arena_run, shared_policy_hash
from backend.v3.arena.t0 import T0_FILE, T0_SCHEMA, read_t0
from backend.v3.arena.trial_plan import PROVIDERS, WalletPlan
from backend.v3.brain_f2.engine import _policy_hash
from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.outcomes import extract_outcomes
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.exit_service import exit_service_healthy
from backend.v3.runner.prepare_paper_run import RunPreparationError
from backend.v3.runner.wiring import mandate_template

DEFAULT_ROOT = Path("/opt/superbot-ai-arena-paper")
PREPARE_PHRASE = "PREPARA-TRE-RUN-PAPER-IN-PAUSA"
ACTIVATE_PREFIX = "AVVIA-GARA-PAPER-T0-"
T0_SKEW_MS = 300_000                      # il T0 dichiarato deve essere "adesso" (+/- 5 minuti)


class SetupRefused(Exception):
    """Codice fisso, mai percorsi o segreti."""


def _plans(root: Path, day: date) -> dict[str, WalletPlan]:
    return {p: plan_for(p, day, root) for p in PROVIDERS}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> Optional[dict]:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    return data if type(data) is dict else None


# ------------------------------------------------------------------------------------------------------- posizioni
def open_positions(folder: Path, run_id: str):
    """Numero di posizioni aperte derivato dal journal DI QUESTA RUN, oppure ``"UNKNOWN"`` (fail-closed) se la
    catena non verifica, se il riepilogo e gli esiti non concordano o se compaiono eventi di un'altra run."""
    try:
        journal = EventJournal(folder / "journal.db")
        if not (folder / "journal.db").is_file():
            return "UNKNOWN"
        count, _head = journal.verify_chain()
        if count != len(journal.list_run("brain", run_id)):
            return "UNKNOWN"                                   # eventi estranei nel journal isolato
        summary = build_summary(journal, "brain", run_id)
        report = extract_outcomes(journal, "brain", run_id)
        ids = {p.position_id for p in summary.open_positions}
        if report.skipped or ids != set(report.open_position_ids) or len(ids) != len(summary.open_positions):
            return "UNKNOWN"
        return len(ids)
    except Exception:
        return "UNKNOWN"


def exit_stop_check(root: Path, day: date, provider: str) -> dict:
    """Cancello prima di fermare ``superbot-arena-exit@<provider>``: consentito SOLO con 0 posizioni verificate."""
    if provider not in PROVIDERS:
        raise SetupRefused("invalid_provider")
    plan = _plans(root, day)[provider]
    n = open_positions(plan.folder, plan.run_id) if plan.folder.is_dir() else "UNKNOWN"
    return {"provider": provider, "run_id": plan.run_id, "open_positions": n, "exit_stop_allowed": n == 0}


# ------------------------------------------------------------------------------------------------------- inspect
def inspect(root: Path, day: date, now_ms: int) -> dict:
    """Sola lettura: nessuna scrittura, nessun lock, nessuna rete."""
    plans = _plans(root, day)
    rows, blockers = {}, []
    configs = {}
    for p, plan in plans.items():
        f = plan.folder
        row = {"run_id": plan.run_id, "exists": f.is_dir() and not f.is_symlink()}
        if row["exists"]:
            man = _read_json(f / "arena_manifest.json")
            mandate = _read_json(f / "mandate.json")
            cfg_bytes = None
            try:
                cfg_bytes = (f / "runner_config.json").read_bytes()
                cfg = load_runner_config(cfg_bytes)
                configs[p] = cfg
            except (OSError, ValueError):
                cfg = None
            try:
                count, _head = EventJournal(f / "journal.db").verify_chain() if (f / "journal.db").is_file() else (None, None)
                kinds = sorted({se.event.kind for se in EventJournal(f / "journal.db").list_run("brain", plan.run_id)}) \
                    if count is not None else []
                chain_ok = count is not None
            except Exception:
                count, kinds, chain_ok = None, [], False
            t0 = read_t0(f, p, plan.run_id)
            row.update({
                "manifest_ok": bool(man) and man.get("provider") == p and man.get("run_id") == plan.run_id
                               and man.get("mode") == "paper" and man.get("initial_capital") == "2000",
                "t0_in_manifest": None if not man else man.get("trial_start_ms"),
                "t0_file": None if t0 is None else t0["trial_start_ms"],
                "paused": (f / "pause.flag").is_file(),
                "mandate_approved": bool(mandate) and mandate.get("approved") is True,
                "journal_chain_ok": chain_ok, "journal_events": count, "event_kinds": kinds,
                "budget_db": (f / "budget.db").is_file(),
                "config_sha256": None if cfg_bytes is None else _sha(cfg_bytes),
                "symbols": None if cfg is None else len(cfg.symbols),
                "capital": None if cfg is None else str(cfg.initial_equity),
                "exit_service_healthy": exit_service_healthy(data_dir=f, run_id=plan.run_id, now_ms=now_ms),
                "open_positions": open_positions(f, plan.run_id),
            })
            if not row["manifest_ok"] or not chain_ok or cfg is None:
                blockers.append(f"{p}:RUN_INVALID")
            if row["open_positions"] == "UNKNOWN":
                blockers.append(f"{p}:OPEN_POSITIONS_UNKNOWN")
        rows[p] = row
    existing = [p for p in PROVIDERS if rows[p]["exists"]]
    if not existing:
        stage = "NOT_PREPARED"
    elif len(existing) != 3:
        stage = "PARTIAL_RUNS"
        blockers.append("PARTIAL_RUNS_ONLY_" + "_".join(existing))
    else:
        t0s = {rows[p]["t0_file"] or rows[p]["t0_in_manifest"] for p in PROVIDERS}
        approved = [rows[p]["mandate_approved"] for p in PROVIDERS]
        paused = [rows[p]["paused"] for p in PROVIDERS]
        if t0s == {None} and not any(approved) and all(paused):
            stage = "PREPARED_PAUSED_NO_T0"
        elif len(t0s) == 1 and None not in t0s and all(approved) and not any(paused):
            stage = "ACTIVE"
        else:
            stage = "INCONSISTENT"
            blockers.append("RUNS_NOT_IN_THE_SAME_STATE")
        if len({configs[p].symbols for p in configs}) > 1:
            blockers.append("UNIVERSE_DIFFERS_BETWEEN_RUNS")
        try:
            if len({_policy_hash(c.risk_policy) for c in configs.values()}) != 1:
                blockers.append("RISK_POLICY_DIFFERS_BETWEEN_RUNS")
        except Exception:
            blockers.append("RISK_POLICY_UNREADABLE")
    budget = None
    if len(configs) == 3:
        budget = budget_gate(configs, evidence=load_evidence(), approved_total_usd=None, key_limit_usd=ORT.KEY_LIMIT)
    return {"schema": "arena_trial_inspect_v1", "budget": budget, "root": str(root), "day": day.isoformat(), "stage": stage,
            "providers": rows, "blockers": blockers, "read_only": True}


# ------------------------------------------------------------------------------------------------------- prepare
def prepare_paused(root: Path, day: date, *, now_ms: int, desk_mode: str, confirm: str,
                   config_loader: Callable[[str], bytes] = lambda p: config_path(p).read_bytes()) -> dict:
    if confirm != PREPARE_PHRASE:
        raise SetupRefused("confirmation_required")
    if desk_mode != "paper":
        raise SetupRefused("paper_only")
    if not isinstance(root, Path) or not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise SetupRefused("arena_root_missing")
    if any(root == f or f in root.parents or root in f.parents for f in FORBIDDEN_ROOTS):
        raise SetupRefused("arena_root_forbidden")
    plans = _plans(root, day)
    if any(p.folder.exists() or p.folder.is_symlink() for p in plans.values()):
        raise SetupRefused("run_already_exists")                   # mai sovrascrivere, mai completare a meta'
    configs = {p: config_loader(p) for p in PROVIDERS}
    parsed = {p: load_runner_config(b) for p, b in configs.items()}
    if len({c.symbols for c in parsed.values()}) != 1:
        raise SetupRefused("universe_differs_between_configs")
    if len({_policy_hash(c.risk_policy) for c in parsed.values()}) != 1:
        raise SetupRefused("risk_policy_differs_between_configs")
    stage = root / f".staging-{now_ms}-{os.getpid()}"
    stage.mkdir(mode=0o700)
    moved: list[tuple[Path, Path]] = []
    try:
        for p in PROVIDERS:
            (stage / p).mkdir(mode=0o700)
            sp = plan_for(p, day, stage)
            prepare_arena_run(sp, config_bytes=configs[p], desk_mode="paper", now_ms=now_ms,
                              trial_start_ms=None, expected_initial_equity="2000")
        pre = inspect(stage, day, now_ms)                            # validazione completa PRIMA di spostare
        if pre["stage"] != "PREPARED_PAUSED_NO_T0" or pre["blockers"]:
            raise SetupRefused("staging_check_failed")
        for p in PROVIDERS:                                         # tutte valide: ora si spostano
            dst = plans[p].folder
            dst.parent.mkdir(mode=0o700, exist_ok=True)
            if dst.parent.is_symlink() or dst.exists() or dst.is_symlink():
                raise SetupRefused("run_already_exists")
            src = plan_for(p, day, stage).folder
            os.rename(src, dst)
            moved.append((dst, src))
        report = inspect(root, day, now_ms)                         # controllo finale sulle posizioni definitive
        if report["stage"] != "PREPARED_PAUSED_NO_T0" or report["blockers"]:
            raise SetupRefused("post_check_failed")
    except BaseException:
        # Riporta in staging SOLO le run spostate da questa esecuzione (mai run preesistenti), poi elimina lo staging.
        for dst, src in reversed(moved):
            try:
                os.rename(dst, src)
            except OSError:
                pass
        shutil.rmtree(stage, ignore_errors=True)
        raise
    shutil.rmtree(stage, ignore_errors=True)
    return report


# ------------------------------------------------------------------------------------------------------- activate
def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name("." + path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def activate(root: Path, day: date, *, t0_ms: int, now_ms: int, desk_mode: str, confirm: str, approved_by: str,
             universe_snapshot: Path, approved_total_budget_usd: Optional[str]) -> dict:
    """Avvio simultaneo della gara (NON eseguire senza autorizzazione esplicita). I runner si avviano dopo, a parte."""
    if confirm != f"{ACTIVATE_PREFIX}{t0_ms}":
        raise SetupRefused("confirmation_required")
    if desk_mode != "paper":
        raise SetupRefused("paper_only")
    if type(t0_ms) is not int or abs(now_ms - t0_ms) > T0_SKEW_MS:
        raise SetupRefused("t0_must_be_now")
    if type(approved_by) is not str or not 2 <= len(approved_by.strip()) <= 64:
        raise SetupRefused("approved_by_required")
    report = inspect(root, day, now_ms)
    if report["stage"] != "PREPARED_PAUSED_NO_T0" or report["blockers"]:
        raise SetupRefused("runs_not_prepared_paused")
    plans = _plans(root, day)
    for p, plan in plans.items():
        if not report["providers"][p]["exit_service_healthy"]:
            raise SetupRefused(f"exit_service_not_healthy:{p}")
        kinds = set(report["providers"][p]["event_kinds"])
        if kinds - {"run_prepared"}:
            raise SetupRefused(f"journal_not_fresh:{p}")
    snap = _read_json(universe_snapshot)
    cfgs = {p: load_runner_config((plans[p].folder / "runner_config.json").read_bytes()) for p in PROVIDERS}
    symbols = list(cfgs["qwen"].symbols)
    if (not snap or snap.get("schema") != "arena_universe_snapshot_v1" or snap.get("symbols") != symbols
            or snap.get("crypto_target_met") is not True
            or type(snap.get("as_of_ms")) is not int or not 0 <= now_ms - snap["as_of_ms"] <= 6 * 3_600_000):
        raise SetupRefused("universe_snapshot_not_fresh_or_different")   # va rifatta entro 6 ore dal T0
    try:
        approved = None if approved_total_budget_usd is None else Decimal(approved_total_budget_usd)
    except ArithmeticError:
        raise SetupRefused("approved_budget_invalid") from None
    gate = budget_gate(cfgs, evidence=load_evidence(), approved_total_usd=approved,
                       key_limit_usd=ORT.KEY_LIMIT)
    if gate["blockers"]:
        raise SetupRefused("budget_gate:" + ",".join(gate["blockers"]))
    policy = shared_policy_hash()
    record = {"schema": T0_SCHEMA, "trial_start_ms": t0_ms,
              "run_ids": {p: plans[p].run_id for p in PROVIDERS},
              "symbols_sha256": _sha(",".join(symbols).encode()), "risk_policy_hash": policy,
              "universe_snapshot_sha256": _sha(universe_snapshot.read_bytes()),
              "assigned_at_ms": now_ms, "assigned_by": approved_by.strip()}
    body = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    saved = {p: (plans[p].folder / "mandate.json").read_bytes() for p in PROVIDERS}
    written_t0: list[Path] = []
    try:
        for p in PROVIDERS:                                             # 1) T0 identico nelle tre run
            _atomic_write(plans[p].folder / T0_FILE, body)
            written_t0.append(plans[p].folder / T0_FILE)
        for p in PROVIDERS:                                             # 2) mandati approvati (stessa firma)
            m = mandate_template(cfgs[p].risk_policy, plans[p].run_id)
            m.update(approved=True, approved_by=approved_by.strip())
            _atomic_write(plans[p].folder / "mandate.json", json.dumps(m, sort_keys=True).encode())
        for p in PROVIDERS:                                             # 3) ultime: le tre pause
            _remove_pause(plans[p].folder / "pause.flag")
        after = inspect(root, day, now_ms)                              # 4) controllo finale
        if after["stage"] != "ACTIVE" or after["blockers"]:
            raise SetupRefused("post_check_failed")
    except BaseException:
        _compensate(plans, saved, written_t0)
        raise
    return after


def _remove_pause(path: Path) -> None:
    path.unlink()


def _compensate(plans: dict, saved: dict, written_t0: list) -> None:
    """Ritorno allo stato preparato: PRIMA le tre pause (blocco immediato delle aperture), poi mandati originali,
    poi rimozione dei T0 scritti da questa esecuzione. Ogni passo prosegue anche se uno precedente fallisce."""
    for plan in plans.values():
        flag = plan.folder / "pause.flag"
        try:
            if not flag.exists():
                flag.write_text("activation_rolled_back\n", encoding="ascii")
                os.chmod(flag, 0o600)
        except OSError:
            pass
    for p, raw in saved.items():
        try:
            _atomic_write(plans[p].folder / "mandate.json", raw)
        except OSError:
            pass
    for path in written_t0:
        try:
            path.unlink()
        except OSError:
            pass


# ------------------------------------------------------------------------------------------------------- sostituzione
SUPERSEDE_PREFIX = "ARCHIVIA-TRE-RUN-PREPARATE-"


def supersede_prepared(root: Path, day: date, *, archive_parent: Path, now_ms: int, confirm: str,
                       archive_basename: Optional[str] = None) -> dict:
    """Sposta (mai modifica, mai cancella) le tre run PREPARATE, mai avviate, in un archivio verificabile, per
    prepararne tre nuove con la config aggiornata. Solo con: stadio PREPARED_PAUSED_NO_T0, journal con il solo
    ``run_prepared``, 0 posizioni verificate, servizi uscite delle tre run FERMI (fermati dall'operatore con
    ``can-stop-exit``), archivio sullo stesso filesystem. Errore a meta' = run gia' spostate rimesse al loro posto."""
    if confirm != f"{SUPERSEDE_PREFIX}{day.isoformat()}":
        raise SetupRefused("confirmation_required")
    report = inspect(root, day, now_ms)
    if report["stage"] != "PREPARED_PAUSED_NO_T0" or report["blockers"]:
        raise SetupRefused("runs_not_prepared_paused")
    for p, row in report["providers"].items():
        if row["event_kinds"] != ["run_prepared"]:
            raise SetupRefused(f"journal_not_fresh:{p}")
        if row["open_positions"] != 0:
            raise SetupRefused(f"open_positions:{p}")
        if row["exit_service_healthy"]:
            raise SetupRefused(f"exit_service_still_running:{p}")
    if not archive_parent.is_dir() or archive_parent.is_symlink():
        raise SetupRefused("archive_parent_missing")
    if archive_parent.stat().st_dev != root.stat().st_dev:
        raise SetupRefused("archive_on_other_filesystem")            # rename non atomico: rifiuto prima
    if archive_basename is not None:
        # The wrapper provides the exact name BEFORE stopping exits or moving any files.
        # This lets its EXIT/HUP trap recover even if SSH drops during the archive call.
        if (type(archive_basename) is not str or
                re.fullmatch(rf"arena-superseded-{day.isoformat()}-[0-9]{{13}}-[0-9a-f]{{8}}",
                             archive_basename) is None):
            raise SetupRefused("archive_name_invalid")
    else:
        archive_basename = f"arena-superseded-{day.isoformat()}-{now_ms}"
    archive = archive_parent / archive_basename
    if archive.exists() or archive.is_symlink():
        raise SetupRefused("archive_already_exists")
    archive.mkdir(mode=0o700)
    plans = _plans(root, day)
    record = {"schema": "arena_superseded_runs_v1", "archived_at_ms": now_ms, "day": day.isoformat(), "runs": {}}
    for p, plan in plans.items():
        count, head = EventJournal(plan.folder / "journal.db").verify_chain()
        record["runs"][p] = {"run_id": plan.run_id, "journal_events": count, "journal_head": head,
                             "config_sha256": report["providers"][p]["config_sha256"],
                             "files_sha256": {f.name: _sha(f.read_bytes()) for f in sorted(plan.folder.iterdir())
                                              if f.is_file() and not f.is_symlink()
                                              and not f.name.endswith(("-shm", "-wal"))}}
    moved: list[tuple[Path, Path]] = []
    try:
        for p, plan in plans.items():
            dst = archive / p / plan.run_id
            dst.parent.mkdir(mode=0o700)
            os.rename(plan.folder, dst)
            moved.append((plan.folder, dst))
        _atomic_write(archive / "SUPERSEDED.json", json.dumps(record, sort_keys=True, indent=1).encode())
    except BaseException:
        for src, dst in reversed(moved):
            try:
                os.rename(dst, src)
            except OSError:
                pass
        raise
    after = inspect(root, day, now_ms)
    return {"archive": str(archive), "stage_after": after["stage"], "archived": record["runs"]}


# ------------------------------------------------------------------------------------------------------- CLI
def main(argv: Optional[list] = None, *, env: Optional[Mapping[str, str]] = None,
         now_fn: Callable[[], int] = lambda: int(time.time() * 1000)) -> int:
    ap = argparse.ArgumentParser(description="Tre run PAPER dell'Arena: ispezione, preparazione in pausa, attivazione.")
    ap.add_argument("command", nargs="?", default="inspect", choices=("inspect", "prepare-paused", "activate",
                                                                   "can-stop-exit", "supersede-prepared"))
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--day", required=True, help="AAAA-MM-GG del run_id")
    ap.add_argument("--confirm", default="")
    ap.add_argument("--t0-ms", type=int)
    ap.add_argument("--approved-by", default="")
    ap.add_argument("--universe-snapshot")
    ap.add_argument("--provider", choices=PROVIDERS)
    ap.add_argument("--archive-parent", default="/opt/superbot-v3-backups")
    ap.add_argument("--archive-basename", default=None, help="nome immutabile preassegnato dal wrapper")
    ap.add_argument("--approved-total-budget-usd", help="budget totale della gara approvato dall'utente")
    a = ap.parse_args(argv)
    environ = os.environ if env is None else env
    root, now = Path(a.root), now_fn()
    try:
        day = date.fromisoformat(a.day)
        if a.command == "inspect":
            out = inspect(root, day, now)
        elif a.command == "can-stop-exit":
            if a.provider is None:
                raise SetupRefused("provider_required")
            out = exit_stop_check(root, day, a.provider)
            print(json.dumps({"ok": True, "command": a.command, **out}, sort_keys=True))
            return 0 if out["exit_stop_allowed"] else 2
        elif a.command == "supersede-prepared":
            out = supersede_prepared(root, day, archive_parent=Path(a.archive_parent), now_ms=now,
                                     confirm=a.confirm, archive_basename=a.archive_basename)
        elif a.command == "prepare-paused":
            out = prepare_paused(root, day, now_ms=now, desk_mode=environ.get("DESK_MODE", ""), confirm=a.confirm)
        else:
            if a.t0_ms is None or not a.universe_snapshot:
                raise SetupRefused("t0_and_snapshot_required")
            out = activate(root, day, t0_ms=a.t0_ms, now_ms=now, desk_mode=environ.get("DESK_MODE", ""),
                           confirm=a.confirm, approved_by=a.approved_by, universe_snapshot=Path(a.universe_snapshot),
                           approved_total_budget_usd=a.approved_total_budget_usd)
    except (SetupRefused, RunPreparationError, ValueError, OSError) as exc:
        code = str(exc) if isinstance(exc, (SetupRefused, RunPreparationError)) else "setup_failed"
        print(json.dumps({"ok": False, "command": a.command, "code": code}))
        return 2
    print(json.dumps({"ok": True, "command": a.command, **out}, indent=1, sort_keys=True, default=str))
    return 0 if not out.get("blockers") else 2


if __name__ == "__main__":
    sys.exit(main())
