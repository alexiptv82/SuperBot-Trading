"""Montaggio del Brain PAPER: assembla feed, analista L5, DeepSeek con tetto, motore, uscite e direttore.

Uso (SOLO su decisione dell'utente, vedi CLAUDE.md: nessun redeploy e nessun avvio senza il suo OK)::

    DESK_MODE=paper python -m backend.v3.runner.wiring --data-dir /percorso/dati --run-id brain-v3-001
    python -m backend.v3.runner.wiring --data-dir ... --run-id ... --print-mandate     # modello del mandato (approved=false)

La cartella dati contiene: ``journal.db`` (journal append-only), ``budget.db`` (registro di spesa), ``heartbeat.json``,
``pause.flag`` (se esiste: nessun nuovo giro del Brain, le uscite proseguono) e ``mandate.json`` (il mandato).
Comando dell'utente: ``close_request.json`` -> chiusura manuale, esito in ``close_result.json`` (``manual_close.py``).

**Mandato.** Il motore apre solo con un mandato di rischio approvato dall'utente e legato all'hash dei limiti. Qui
nessuno approva al posto suo: ``--print-mandate`` stampa un modello con ``approved: false``; l'utente (o chi lui
incarica) lo salva come ``mandate.json`` mettendo ``approved: true`` e ``approved_by``. Finche' il file manca o non
corrisponde (limiti diversi, altra run) il runner resta ``halted`` con il motivo nel battito e NON chiama il
modello (nessuna spesa); il file viene riletto a ogni tick, quindi l'approvazione ha effetto senza riavviare.

**Sicurezza.** Il programma rifiuta di partire se ``DESK_MODE`` non e' ``paper``. Nessuna chiave nel codice: il
trasporto DeepSeek legge ``DEEPSEEK_API_KEY`` dall'ambiente al momento della chiamata. Nessun ordine verso
l'exchange: il feed Bitget e' di sola lettura (dati pubblici) e tutte le esecuzioni sono simulazioni sul journal.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

from backend.v3.brain_f2.engine import _policy_hash
from backend.v3.brain_f3.providers import Transport
from backend.v3.brain_market.deepseek_l5 import DeepSeekL5Analyst
from backend.v3.brain_market.params import MarketViewParams, load_default_params as load_market_params
from backend.v3.brain_market.view import min_bars
from backend.v3.brain_view.menu import build_menu, menu_ids
from backend.v3.brain_view.params import load_default_params as load_view_params
from backend.v3.budget import BudgetLedger
from backend.v3.events import EventJournal
from backend.v3.knowledge.library import load_library
from backend.v3.lab_tools.fetch_candles import http_json
from backend.v3.outcomes import extract_outcomes
from backend.v3.risk import RiskPolicy
from backend.v3.runner.config import RunnerConfig, default_config_path, load_runner_config
from backend.v3.runner.contracts import ContractRules
from backend.v3.runner.cycle import CycleBars, CycleReport, MarketEntryAnalyst, PORTFOLIO_ID, run_brain_cycle
from backend.v3.runner.exits import load_default_policy
from backend.v3.runner.feed import CandleStore, last_minute_close, minute_fetcher
from backend.v3.runner.manual_close import ManualCloseReport, run_manual_close
from backend.v3.runner.metering import BudgetHalt, MeteredTransport
from backend.v3.runner.monitor import MonitorReport, run_exit_monitor
from backend.v3.runner.runner import Runner, TickResult
from backend.v3.transport import deepseek_transport

PROVIDER = "deepseek"
MANDATE_FILE = "mandate.json"
MINUTE_STORE_BARS = 1_500          # 24 ore di durata massima + margine, a 1 minuto (un test lo lega alla politica di uscita)
EXTRA_KEEP = 24                    # barre in piu' del minimo, per non stare sempre sul bordo


def mandate_template(policy: RiskPolicy, run_id: str) -> dict:
    """Modello di mandato NON approvato: serve la firma dell'utente (``approved`` e ``approved_by``)."""
    return {"version": "v1", "approved": False, "approved_by": "", "portfolio_id": PORTFOLIO_ID,
            "run_id": run_id, "policy_hash": _policy_hash(policy)}


class MandateFile:
    """Il mandato letto da ``mandate.json`` (riletto a ogni uso) e il controllo preliminare prima di spendere."""

    def __init__(self, path: Path, policy: RiskPolicy, run_id: str):
        self.path, self._policy, self._run_id = path, policy, run_id

    def read(self) -> Optional[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def problem(self) -> Optional[str]:
        """Perche' il Brain non puo' aprire adesso (``None`` = mandato valido). L'ultima parola resta al motore."""
        if not self.path.is_file():
            return "no_mandate"
        m = self.read()
        if m is None:
            return "mandate_invalid"
        if m.get("approved") is not True:
            return "mandate_not_approved"
        if (not isinstance(m.get("version"), str) or not m["version"]
                or not isinstance(m.get("approved_by"), str) or not m["approved_by"]
                or m.get("portfolio_id") != PORTFOLIO_ID or m.get("run_id") != self._run_id
                or m.get("policy_hash") != _policy_hash(self._policy)):
            return "mandate_mismatch"
        return None


def make_verifier(mandate: MandateFile, run_id: str) -> Callable[[Mapping, RiskPolicy], bool]:
    """Verificatore esterno richiesto dal motore: ri-controlla il file AL MOMENTO dell'apertura (non si fida
    del dizionario passato) e che il mandato sia quello di questa run."""
    def verifier(m: Mapping, policy: RiskPolicy) -> bool:
        return mandate.problem() is None and isinstance(m, Mapping) and m.get("run_id") == run_id
    return verifier


@dataclass(frozen=True)
class Built:
    runner: Runner
    journal: EventJournal
    ledger: BudgetLedger
    metered: MeteredTransport
    mandate: MandateFile


def build_runner(*, data_dir: Path, run_id: str, config: RunnerConfig,
                 get_json: Callable[[str], object] = http_json,
                 inner_transport: Optional[Transport] = None,
                 view_params: Optional[MarketViewParams] = None) -> Built:
    """Assembla tutto. ``get_json`` e ``inner_transport`` sono iniettabili (prove offline); ``view_params`` serve solo ai test."""
    journal = EventJournal(str(data_dir / "journal.db"))
    journal.init_schema()
    ledger = BudgetLedger(str(data_dir / "budget.db"))
    vp = view_params if view_params is not None else load_market_params()
    menu = build_menu(load_library())
    metered = MeteredTransport(
        inner_transport if inner_transport is not None else deepseek_transport(), ledger, PROVIDER,
        input_usd_per_million=config.input_usd_per_million, output_usd_per_million=config.output_usd_per_million,
        extra_payload=config.model_extra_payload)
    holder = CycleBars()
    analyst = MarketEntryAnalyst(DeepSeekL5Analyst(
        transport=metered, model=config.model,
        outcomes_source=lambda: extract_outcomes(journal, PORTFOLIO_ID, run_id).outcomes,
        bars_source=holder, view_params=load_view_params(), market_params=vp, menu=menu,
        spending_gate=ledger.spending_gate(daily_limits={PROVIDER: config.daily_cap_units}), enabled=True,
        max_tokens=config.max_tokens))
    store = CandleStore(get_json, keep={s.name: (s.candle_ms, min_bars(s, vp.indicators) + EXTRA_KEEP)
                                        for s in vp.timeframes})
    minutes = CandleStore(get_json, keep={"1m": (60_000, MINUTE_STORE_BARS)})
    rules = ContractRules(get_json, maintenance_fraction=config.maintenance_fraction)
    exit_policy = load_default_policy()
    mandate = MandateFile(data_dir / MANDATE_FILE, config.risk_policy, run_id)
    budget_halt = BudgetHalt(ledger, PROVIDER, config.daily_cap_units, metered)
    allowed = tuple(sorted(menu_ids(menu)))

    def halted() -> Optional[str]:
        return mandate.problem() or budget_halt()

    def run_cycle(now_ms: int, slot: int) -> CycleReport:
        rules.load(now_ms)
        return run_brain_cycle(
            now_ms=now_ms, journal=journal, run_id=run_id, symbols=config.symbols, store=store,
            bars_holder=holder, analyst=analyst, view_params=vp, risk_policy=config.risk_policy,
            mandate=mandate.read(), policy_verifier=make_verifier(mandate, run_id), market_rules=rules,
            initial_equity=config.initial_equity, slippage_bps=config.slippage_bps,
            allowed_strategy_ids=allowed, price_source=lambda sym, now: last_minute_close(sym, now, get_json),
            rotate=slot)

    def run_monitor(now_ms: int) -> MonitorReport:
        return run_exit_monitor(journal=journal, portfolio_id=PORTFOLIO_ID, run_id=run_id,
                                fetch_bars=minute_fetcher(minutes), policy=exit_policy,
                                fee_bps=config.fee_bps, now_ms=now_ms)

    def run_commands(now_ms: int) -> Optional[ManualCloseReport]:
        return run_manual_close(journal=journal, portfolio_id=PORTFOLIO_ID, run_id=run_id, data_dir=data_dir,
                                price_of=lambda sym, now: last_minute_close(sym, now, get_json),
                                fee_bps=config.fee_bps, now_ms=now_ms)

    runner = Runner(run_id=run_id, data_dir=data_dir, run_monitor=run_monitor, run_cycle=run_cycle, halted=halted,
                    cycle_ms=config.cycle_ms, run_commands=run_commands)
    return Built(runner, journal, ledger, metered, mandate)


def _log(now_ms: int, r: TickResult, last: dict) -> None:
    """Una riga per evento che conta (giro fatto, posizione chiusa, errore nuovo): solo codici e conteggi."""
    closed = (len(r.monitor.closed) if r.monitor is not None else 0) + (len(r.manual.closed) if r.manual is not None else 0)
    if r.cycle is None and not closed and r.manual is None and r.last_error == last.get("err"):
        return
    last["err"] = r.last_error
    print(json.dumps({"ts_ms": now_ms, "state": r.state,
                      "cycle_opened": len(r.cycle.opened) if r.cycle is not None else None,
                      "cycle_decisions": len(r.cycle.decisions) if r.cycle is not None else None,
                      "closed": closed, "last_error": r.last_error}, sort_keys=True), flush=True)


def main(argv: Optional[list] = None, *, env: Optional[Mapping[str, str]] = None,
         now_fn: Callable[[], int] = lambda: int(time.time() * 1000),
         sleep_fn: Callable[[float], None] = time.sleep, get_json: Callable[[str], object] = http_json,
         inner_transport: Optional[Transport] = None, should_stop: Optional[Callable[[], bool]] = None) -> int:
    ap = argparse.ArgumentParser(description="Brain V3 PAPER (solo simulazione).")
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--config", default=None, help="default: runner_config.json (valori proposti)")
    ap.add_argument("--print-mandate", action="store_true", help="stampa il modello di mandato (non approvato) ed esce")
    ap.add_argument("--once", action="store_true", help="un solo tick (prova) e poi esce")
    a = ap.parse_args(argv)
    environ = os.environ if env is None else env
    try:
        config = load_runner_config(Path(a.config or default_config_path()).read_bytes())
    except (OSError, ValueError):
        print("config_invalid", file=sys.stderr)
        return 2
    if a.print_mandate:
        print(json.dumps(mandate_template(config.risk_policy, a.run_id), indent=2, sort_keys=True))
        return 0
    if environ.get("DESK_MODE") != "paper":
        print("refused: DESK_MODE must be 'paper'", file=sys.stderr)
        return 2
    data_dir = Path(a.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        built = build_runner(data_dir=data_dir, run_id=a.run_id, config=config, get_json=get_json,
                             inner_transport=inner_transport)
    except ValueError:
        print("setup_invalid", file=sys.stderr)
        return 2
    if a.once:
        result = built.runner.tick(now_fn())
        print(json.dumps({"state": result.state, "last_error": result.last_error}, sort_keys=True))
        return 0
    stop = {"flag": False}
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, lambda *_: stop.update(flag=True))
        except ValueError:                                   # non nel thread principale (test)
            pass
    last: dict = {}
    built.runner.run(now_fn=now_fn, sleep_fn=sleep_fn,
                     should_stop=should_stop if should_stop is not None else (lambda: stop["flag"]),
                     on_tick=lambda now, r: _log(now, r, last))
    return 0


if __name__ == "__main__":
    sys.exit(main())
