"""Preparazione esplicita di una run PAPER dell'Arena per UN provider (in pausa, mandato NON approvato).

Crea soltanto la cartella ``<root>/<provider>/<run_id>`` del piano di prova (trial_plan.py) con journal, budget,
configurazione, mandato non approvato, ``pause.flag``, marcatore PREPARED e ``arena_manifest.json``.
Non avvia nulla, non chiama provider, non tocca il Brain storico, Falco o Toro. Una run esistente non viene mai
sovrascritta. La configurazione deve avere la stessa politica di rischio delle altre due AI.

Uso: DESK_MODE=paper python -m backend.v3.arena.prepare --provider qwen --root /opt/superbot-ai-arena-paper \
         --day 2026-11-18 --trial-start-ms <ms> [--config FILE] --confirm-capital 2000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Mapping, Optional

from backend.v3.arena.trial_plan import PROVIDERS, build_trial_plan, WalletPlan
from backend.v3.brain_f2.engine import _policy_hash
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.prepare_paper_run import RunPreparationError, provision_paused_run

CONFIG_DIR = Path(__file__).with_name("configs")
# Le run dell'Arena non devono mai finire dentro le cartelle dei portafogli esistenti.
FORBIDDEN_ROOTS = (Path("/opt/superbot-v3-paper-runs"), Path("/opt/superbot-desk-data"))


def config_path(provider: str) -> Path:
    if provider not in PROVIDERS:
        raise RunPreparationError("invalid_provider")
    return CONFIG_DIR / f"{provider}.json"


def shared_policy_hash() -> str:
    """Le tre AI devono avere lo stesso mandato di rischio: altrimenti il confronto non vale."""
    hashes = {_policy_hash(load_runner_config(config_path(p).read_bytes()).risk_policy) for p in PROVIDERS}
    if len(hashes) != 1:
        raise RunPreparationError("arena_risk_policy_differs")
    return hashes.pop()


def plan_for(provider: str, day: date, root: Path) -> WalletPlan:
    if provider not in PROVIDERS:
        raise RunPreparationError("invalid_provider")
    return {p.provider: p for p in build_trial_plan(day, root=root)}[provider]


def prepare_arena_run(plan: WalletPlan, *, config_bytes: bytes, desk_mode: str, now_ms: int,
                      trial_start_ms: int, expected_initial_equity: str) -> Path:
    if desk_mode != "paper":
        raise RunPreparationError("paper_only")
    if type(trial_start_ms) is not int or not 0 < trial_start_ms or type(now_ms) is not int or now_ms <= 0:
        raise RunPreparationError("invalid_time")
    config = load_runner_config(config_bytes)
    if config.model != plan.model or config.initial_equity != plan.capital_usdt:
        raise RunPreparationError("config_does_not_match_plan")
    if _policy_hash(config.risk_policy) != shared_policy_hash():
        raise RunPreparationError("arena_risk_policy_differs")
    trial_root, provider_dir = plan.folder.parent.parent, plan.folder.parent
    if any(trial_root == f or f in trial_root.parents or trial_root in f.parents for f in FORBIDDEN_ROOTS):
        raise RunPreparationError("arena_root_forbidden")
    if trial_root.is_symlink() or not trial_root.is_dir():
        raise RunPreparationError("arena_root_missing")
    if provider_dir.is_symlink():
        raise RunPreparationError("arena_provider_dir_unsafe")
    if not provider_dir.exists():
        provider_dir.mkdir(mode=0o700)
    root = provision_paused_run(plan.folder, run_id=plan.run_id, config_bytes=config_bytes, now_ms=now_ms,
                                expected_initial_equity=expected_initial_equity)
    manifest = root / "arena_manifest.json"
    manifest.write_text(json.dumps({
        "schema": "brain_arena_trial_v1", "provider": plan.provider, "run_id": plan.run_id,
        "initial_capital": str(plan.capital_usdt), "mode": "paper", "model": plan.model,
        "experiment": "independent", "trial_start_ms": trial_start_ms,
        "risk_policy_hash": _policy_hash(config.risk_policy),
    }, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.chmod(manifest, 0o600)
    return root


def main(argv: Optional[list] = None, *, env: Optional[Mapping[str, str]] = None,
         now_fn=lambda: int(time.time() * 1000)) -> int:
    ap = argparse.ArgumentParser(description="Prepara una run PAPER dell'Arena (in pausa, mandato non approvato).")
    ap.add_argument("--provider", required=True, choices=PROVIDERS)
    ap.add_argument("--root", required=True)
    ap.add_argument("--day", required=True, help="AAAA-MM-GG, giorno del run_id")
    ap.add_argument("--trial-start-ms", required=True, type=int)
    ap.add_argument("--config")
    ap.add_argument("--confirm-capital", required=True)
    a = ap.parse_args(argv)
    environ = os.environ if env is None else env
    try:
        plan = plan_for(a.provider, date.fromisoformat(a.day), Path(a.root))
        raw = Path(a.config).read_bytes() if a.config else config_path(a.provider).read_bytes()
        root = prepare_arena_run(plan, config_bytes=raw, desk_mode=environ.get("DESK_MODE", ""),
                                 now_ms=now_fn(), trial_start_ms=a.trial_start_ms,
                                 expected_initial_equity=a.confirm_capital)
    except (RunPreparationError, ValueError, OSError) as exc:
        code = str(exc) if isinstance(exc, RunPreparationError) else "preparation_failed"
        print(json.dumps({"ok": False, "code": code}), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "provider": plan.provider, "run_id": plan.run_id, "folder": str(root),
                      "paused": True, "mandate_approved": False}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
