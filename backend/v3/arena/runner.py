"""Runner decisionale PAPER di UNA AI dell'Arena (DeepSeek prova, Qwen o MiniMax), isolato dagli altri.

Riusa il Brain V3 (feed, vista L5, motore, rischio, guardia post-AI, esecutore PAPER, journal) in modalita' sidecar:
le uscite le gestisce un servizio uscite separato per la stessa cartella (``backend.v3.runner.exit_worker``).

Isolamento (prova di 14 giorni): ogni AI legge e scrive SOLO la propria cartella ``<root>/<provider>/<run_id>``;
nessuna osservazione di Falco, Toro, del Brain storico o delle altre AI; stesso universo di simboli, stesso mandato
di rischio, stessa guardia, stesse condizioni di NO_TRADE.

Due interruttori indipendenti prima di qualunque spesa: il mandato della run deve essere approvato (altrimenti il runner
resta ``halted`` senza chiamare il modello) e, per Qwen/MiniMax, ``V3_ARENA_ALLOW_INFERENCE=1``. Senza quest'ultimo il
trasporto rifiuta e il motore registra NO_TRADE per AI non disponibile. Nessun ordine verso l'exchange.

Uso: DESK_MODE=paper python -m backend.v3.arena.runner --provider qwen --root /opt/superbot-ai-arena-paper --day 2026-11-18
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import date
from pathlib import Path
from typing import Callable, Mapping, Optional

from backend.v3.arena.inference_trace import TracedTransport
from backend.v3.arena.openrouter_transport import openrouter_transport
from backend.v3.arena.prepare import plan_for, shared_policy_hash
from backend.v3.arena.t0 import read_t0, read_t0_agreed, trial_start
from backend.v3.arena.trial_plan import PROVIDERS, WalletPlan
from backend.v3.brain_f2.engine import _policy_hash
from backend.v3.budget import BudgetLedger
from backend.v3.lab_tools.fetch_candles import http_json
from backend.v3.runner.config import RunnerConfig, load_runner_config
from backend.v3.runner.wiring import Built, build_runner, _log
from backend.v3.transport import deepseek_transport


class ArenaRunnerError(ValueError):
    """Codice fisso, senza percorsi o segreti."""


def check_manifest(plan: WalletPlan, config: RunnerConfig) -> int:
    path = plan.folder / "arena_manifest.json"
    try:
        if path.is_symlink() or path.stat().st_size > 8192:
            raise ArenaRunnerError("arena_manifest_invalid")
        m = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ArenaRunnerError("arena_manifest_invalid") from None
    expected = {"schema": "brain_arena_trial_v1", "provider": plan.provider, "run_id": plan.run_id,
                "initial_capital": "2000", "mode": "paper", "model": plan.model, "experiment": "independent",
                "risk_policy_hash": _policy_hash(config.risk_policy)}
    if type(m) is not dict or any(m.get(k) != v for k, v in expected.items()) or "trial_start_ms" not in m:
        raise ArenaRunnerError("arena_manifest_mismatch")
    if m["risk_policy_hash"] != shared_policy_hash():
        raise ArenaRunnerError("arena_risk_policy_differs")
    if m["trial_start_ms"] is None:                    # run preparata senza T0 nel manifest: serve il T0 comune
        if read_t0(plan.folder, plan.provider, plan.run_id) is None:
            raise ArenaRunnerError("arena_t0_not_assigned")
        agreed = read_t0_agreed(plan.folder, plan.provider, plan.run_id)
        if agreed is None:                             # le tre run non concordano: nessuna partenza
            raise ArenaRunnerError("arena_t0_inconsistent")
        return agreed["trial_start_ms"]
    t0 = trial_start(plan.folder, plan.provider, plan.run_id, m["trial_start_ms"])
    if t0 is None:
        raise ArenaRunnerError("arena_t0_not_assigned")
    return t0


def provider_transport(plan: WalletPlan, config: RunnerConfig, environ: Mapping[str, str]):
    """DeepSeek: chiave DEEPSEEK_API_KEY letta a ogni chiamata. Qwen/MiniMax: OpenRouter, spento per default."""
    if plan.provider == "deepseek":
        return deepseek_transport()
    ledger = BudgetLedger(str(plan.folder / "budget.db"))
    gate = ledger.spending_gate(daily_limits={plan.provider: config.daily_cap_units})
    return openrouter_transport(plan.provider, allow_inference=environ.get("V3_ARENA_ALLOW_INFERENCE") == "1",
                                spending_gate=gate)


def build_arena_runner(plan: WalletPlan, *, environ: Mapping[str, str], clock_ms: Callable[[], int],
                       get_json: Callable[[str], object] = http_json, inner_transport=None,
                       view_params=None) -> Built:
    if environ.get("DESK_MODE") != "paper":
        raise ArenaRunnerError("paper_only")
    try:
        config = load_runner_config((plan.folder / "runner_config.json").read_bytes())
    except (OSError, ValueError):
        raise ArenaRunnerError("config_invalid") from None
    if config.model != plan.model or config.initial_equity != plan.capital_usdt:
        raise ArenaRunnerError("config_does_not_match_plan")
    check_manifest(plan, config)
    transport = inner_transport if inner_transport is not None else provider_transport(plan, config, environ)
    # Traccia per chiamata (parametri di ragionamento inviati, token, latenza): solo misura, nessun effetto.
    transport = TracedTransport(transport, plan.folder / "inference_trace.jsonl", provider=plan.provider)
    kw = {} if view_params is None else {"view_params": view_params}
    try:
        return build_runner(data_dir=plan.folder, run_id=plan.run_id, config=config, get_json=get_json,
                            inner_transport=transport, alert_send=None, exit_mode="sidecar", clock_ms=clock_ms,
                            desk_mode="paper", arena_provider=plan.provider, **kw)
    except ValueError:
        raise ArenaRunnerError("setup_invalid") from None


def main(argv: Optional[list] = None, *, env: Optional[Mapping[str, str]] = None,
         now_fn: Callable[[], int] = lambda: int(time.time() * 1000),
         sleep_fn: Callable[[float], None] = time.sleep, get_json: Callable[[str], object] = http_json,
         inner_transport=None, should_stop: Optional[Callable[[], bool]] = None) -> int:
    ap = argparse.ArgumentParser(description="Runner PAPER di una AI dell'Arena (isolato).")
    ap.add_argument("--provider", required=True, choices=PROVIDERS)
    ap.add_argument("--root", required=True)
    ap.add_argument("--day", required=True)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    environ = os.environ if env is None else env
    try:
        plan = plan_for(a.provider, date.fromisoformat(a.day), Path(a.root))
        built = build_arena_runner(plan, environ=environ, clock_ms=now_fn, get_json=get_json,
                                   inner_transport=inner_transport)
    except (ArenaRunnerError, ValueError) as exc:
        print(json.dumps({"ok": False, "code": str(exc) if isinstance(exc, ArenaRunnerError) else "setup_invalid"}),
              file=sys.stderr)
        return 2
    if a.once:
        r = built.runner.tick(now_fn())
        print(json.dumps({"provider": plan.provider, "state": r.state, "last_error": r.last_error}, sort_keys=True))
        return 0
    stop = {"flag": False}
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, lambda *_: stop.update(flag=True))
        except ValueError:
            pass
    last: dict = {}
    built.runner.run(now_fn=now_fn, sleep_fn=sleep_fn,
                     should_stop=should_stop if should_stop is not None else (lambda: stop["flag"]),
                     on_tick=lambda now, r: _log(now, r, last))
    return 0


if __name__ == "__main__":
    sys.exit(main())
