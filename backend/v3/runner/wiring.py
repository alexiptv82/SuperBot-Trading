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
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping, Optional

from backend.v3.brain_f2.engine import _policy_hash
from backend.v3.brain_f3.providers import Transport
from backend.v3.brain_market.deepseek_l5 import DeepSeekL5Analyst
from backend.v3.brain_market.classic_peers import read_peers
from backend.v3.brain_market.params import MarketViewParams, load_default_params as load_market_params
from backend.v3.brain_market.view import min_bars, regime_for_context
from backend.v3.brain_view.menu import build_menu, menu_ids
from backend.v3.brain_view.params import load_default_params as load_view_params
from backend.v3.budget import BudgetLedger
from backend.v3.events import EventJournal
from backend.v3.knowledge.library import load_library
from backend.v3.lab_tools.fetch_candles import http_json
from backend.v3.outcomes import extract_outcomes
from backend.v3.risk import RiskPolicy
from backend.v3.runner.alerts import telegram_sender
from backend.v3.runner.config import RunnerConfig, default_config_path, load_runner_config
from backend.v3.runner.prepared_config_guard import verify_prepared_run_config
from backend.v3.runner.contracts import ContractRules
from backend.v3.runner.daily_loss import DailyLossGuard, evaluate_daily_loss, max_daily_loss_between
from backend.v3.runner.cycle import CycleBars, CycleReport, MarketEntryAnalyst, PORTFOLIO_ID, run_brain_cycle
from backend.v3.runner.thesis import ReentryPolicy
from backend.v3.runner.exits import load_default_policy
from backend.v3.runner.feed import CandleStore, fetch_closed_bars, last_minute_close, minute_fetcher
from backend.v3.runner.manual_close import ManualCloseReport, run_manual_close
from backend.v3.runner.metering import BudgetHalt, MeteredTransport
from backend.v3.runner.monitor import MonitorReport, run_exit_monitor
from backend.v3.runner.runner import Runner, TickResult
from backend.v3.runner.open_serial import commit_paper_open
from backend.v3.runner.exit_service import ExitServiceBusy, exit_service_healthy
from backend.v3.runner.legacy_exit_fence import LegacyExitFence
from backend.v3.runner.exit_worker import check_existing_data
from backend.v3.transport import deepseek_transport

PROVIDER = "deepseek"
MANDATE_FILE = "mandate.json"
UNICO_DECISION_AGE_MS = 300_000    # Brain unico: eta' massima di una decisione all'apertura (vedi safety_open_commit)
MINUTE_STORE_BARS = 1_500          # 24 ore di durata massima + margine, a 1 minuto (un test lo lega alla politica di uscita)
FALCO_4H_KEEP = 300                # Falco Evoluto: 50 giorni di 4h (EMA200 4h e trend 1d su giorni completi)
EXTRA_KEEP = 24                    # barre in piu' del minimo, per non stare sempre sul bordo



def make_guardian(*, journal, run_id: str, config, ledger, get_json):
    """Profit Guardian della run: journal della run + chiusure da 1 minuto dal feed (sola lettura, nessuno stato)."""
    from datetime import datetime, timezone
    from backend.v3.guardian import MINUTE_MS, evaluate_guardian, session_start_ms
    policy = config.guardian

    def ai_cost_since(start_ms: int):
        try:
            units = 0
            for r in ledger.all_spend(PROVIDER):
                ts = datetime.fromisoformat(str(r["occurred_at"]).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts.timestamp() * 1000 >= start_ms and type(r["units"]) is int:
                    units += r["units"]
            return Decimal(units) / Decimal(1_000_000)
        except Exception:
            return None                                   # costo non verificabile: mostrato come sconosciuto

    def evaluate(now_ms: int):
        start = session_start_ms(now_ms, policy)
        end = now_ms // MINUTE_MS * MINUTE_MS
        events = [r.event for r in journal.list_run_kinds_since(PORTFOLIO_ID, run_id, ("paper_open", "paper_close"), 0)]
        cache: dict = {}

        def close_at(symbol: str, minute_ms: int):
            if symbol not in cache:
                cache[symbol] = {b.open_time_ms: b.close for b in fetch_closed_bars(
                    symbol, start - MINUTE_MS, end, candle_ms=MINUTE_MS, get_json=get_json)}
            return cache[symbol].get(minute_ms)

        return evaluate_guardian(events=events, initial_equity=config.initial_equity, close_at=close_at,
                                 now_ms=now_ms, policy=policy, max_loss_fraction=config.risk_policy.max_loss_fraction,
                                 fee_bps=config.fee_bps, roundtrip_cost_bp=config.risk_policy.estimated_roundtrip_cost_bp,
                                 ai_cost_session=ai_cost_since(start))
    return evaluate

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
                 view_params: Optional[MarketViewParams] = None,
                 alert_send: Optional[Callable[[str], bool]] = None,
                 exit_mode: str = "legacy", clock_ms: Optional[Callable[[], int]] = None,
                 desk_mode: Optional[str] = None,
                 classic_peer_dirs: Optional[Mapping[str, Path]] = None,
                 claude_inner_transport: Optional[Transport] = None, strategy=None) -> Built:
    """Assembla tutto. ``get_json`` e ``inner_transport`` sono iniettabili (prove offline); ``view_params`` serve solo ai test.
    ``strategy`` (Brain Live Evolution, ``strategy_versions.Effective``): ``config`` resta la BASE della run (verificata
    contro la run preparata); il runner lavora con la configurazione della versione attiva, aggiunge le sue note al
    prompt e registra la sua fotografia su ogni nuova apertura."""
    if type(exit_mode) is not str or exit_mode not in ("legacy", "sidecar"):
        raise ValueError("invalid_exit_mode")
    # Peer observation is opt-in and can only read explicitly provided, isolated dirs.
    peer_reader = None
    if classic_peer_dirs is not None:
        if (type(classic_peer_dirs) is not dict or set(classic_peer_dirs) != {"falco", "toro"}
                or any(not isinstance(p, Path) or not p.is_absolute() for p in classic_peer_dirs.values())
                or any(p.resolve() == data_dir.resolve() for p in classic_peer_dirs.values())
                or classic_peer_dirs["falco"].resolve() == classic_peer_dirs["toro"].resolve()):
            raise ValueError("invalid_peer_directories")
        peer_reader = lambda sym, at_ms: read_peers(
            classic_peer_dirs["falco"], classic_peer_dirs["toro"], sym, at_ms)
    if exit_mode == "sidecar":
        if type(desk_mode) is not str or desk_mode != "paper":
            raise ValueError("paper_mode_required")
        # Never create a fresh run/empty journal in a cutover path.
        journal = check_existing_data(data_dir=data_dir, run_id=run_id)
        verify_prepared_run_config(data_dir=data_dir, run_id=run_id, config=config)     # sempre la BASE
        if not (data_dir / "budget.db").is_file():
            raise ValueError("split_budget_missing")
        if clock_ms is None or not callable(clock_ms):
            raise ValueError("split_fresh_clock_required")
    else:
        journal = EventJournal(str(data_dir / "journal.db"))
        journal.init_schema()
    if strategy is not None:
        config = strategy.config                      # da qui: la versione attiva (rischio e mandato = base, sempre)
    snapshot = strategy.snapshot() if strategy is not None else None
    notes = strategy.notes if strategy is not None else None
    ledger = BudgetLedger(str(data_dir / "budget.db"))
    vp = view_params if view_params is not None else load_market_params()
    menu = build_menu(load_library())
    metered = MeteredTransport(
        inner_transport if inner_transport is not None else deepseek_transport(), ledger, PROVIDER,
        input_usd_per_million=config.input_usd_per_million, output_usd_per_million=config.output_usd_per_million,
        extra_payload=config.model_extra_payload)
    holder = CycleBars()
    gate = ledger.spending_gate(daily_limits={PROVIDER: config.daily_cap_units})
    keep = {s.name: (s.candle_ms, min_bars(s, vp.indicators) + EXTRA_KEEP) for s in vp.timeframes}
    # ------------------------------------------------------------------ Brain unico (schema 3, 24/11)
    unico = config.unico
    last_guardian: dict = {"state": "NORMAL"}

    def reserve_of(summary, at_ms: int) -> Decimal:
        """Salvadanaio: profitti accantonati a mezzanotte, esclusi dal capitale che il Brain usa."""
        from backend.v3.unico import piggy_from_closed
        return piggy_from_closed(summary.closed_trades, initial_equity=config.initial_equity, now_ms=at_ms,
                                 policy=unico.piggy).total

    def portfolio_state() -> dict:
        from backend.v3.dashboard import build_summary, open_groups
        from backend.v3.runner.cycle import snapshot_from_summary
        summ = build_summary(journal, PORTFOLIO_ID, run_id)
        slots = config.risk_policy.max_positions or 0
        snap = snapshot_from_summary(summ, config.initial_equity, config.risk_policy.estimated_roundtrip_cost_bp)
        eq = snap.equity if snap.equity > 0 else Decimal("1")
        return {"guardian_mode": last_guardian["state"], "open_trades": open_groups(summ.open_positions),
                "free_slots": max(0, slots - open_groups(summ.open_positions)),
                "open_risk_pct": str((snap.existing_open_risk / eq * 100).quantize(Decimal("0.01"))),
                "long_risk_pct": str((snap.side_open_risk.get(1, Decimal(0)) / eq * 100).quantize(Decimal("0.01"))),
                "short_risk_pct": str((snap.side_open_risk.get(-1, Decimal(0)) / eq * 100).quantize(Decimal("0.01"))),
                "margin_used": str(snap.margin_used), "equity": str(snap.equity)}

    def market_view_of(sym: str, t: int) -> dict:
        from backend.v3.brain_market.view import build_market_view
        return build_market_view({tf.name: store.refresh(sym, tf.name, t) for tf in vp.timeframes},
                                 timestamp_ms=t, params=vp)

    def funding_of(sym: str):
        body = get_json("https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol=" + sym
                        + "&productType=USDT-FUTURES")
        rate = Decimal(str(body["data"][0]["fundingRate"]))
        return rate if rate.is_finite() and abs(rate) < 1 else None

    consultant = None
    if unico is not None and unico.claude is not None:
        from backend.v3.runner.consult import FALLBACK_BETA, ClaudeConsultant
        from backend.v3.transport import claude_transport
        cp = unico.claude
        claude_metered = MeteredTransport(
            claude_inner_transport if claude_inner_transport is not None else claude_transport(
                timeout_s=cp.timeout_s, betas=(FALLBACK_BETA,)),
            ledger, "claude", input_usd_per_million=cp.input_usd_per_million,
            output_usd_per_million=cp.output_usd_per_million)
        consultant = ClaudeConsultant(
            transport=claude_metered, model=cp.model, effort=cp.effort, max_tokens=cp.max_tokens,
            spending_gate=ledger.spending_gate(daily_limits={"claude": cp.daily_cap_units}),
            max_per_cycle=cp.max_per_cycle, cooldown_ms=cp.cooldown_minutes * 60_000)
    if config.analyst == "falco_evoluto":
        # regole + DeepSeek consulente raro (stesso trasporto metrato, budget proprio della run)
        from backend.v3.falco_evoluto import EMA200_MIN_BARS, FalcoEvolutoAnalyst
        analyst = MarketEntryAnalyst(FalcoEvolutoAnalyst(
            bars_source=holder, max_leverage=config.risk_policy.max_leverage, transport=metered,
            model=config.model, spending_gate=gate, ai_enabled=True, max_tokens=config.max_tokens))
        if "4h" in keep:                    # EMA200 4h solo con storia sufficiente (correzione dell'originale)
            keep["4h"] = (keep["4h"][0], max(keep["4h"][1], FALCO_4H_KEEP))
    elif config.analyst == "deepseek":
        unico_extra = {}
        if unico is not None and unico.guidance:
            from backend.v3.brain_market.deepseek_l5 import UNICO_GUIDANCE
            from backend.v3.unico import parse_reasons
            unico_extra = {"guidance": UNICO_GUIDANCE + (f" Operator strategy notes (version {strategy.version}), "
                                                         f"never above the risk limits: {notes}" if notes else ""),
                           "portfolio_state": portfolio_state,
                           "reasons_parser": parse_reasons}
        ds_analyst = DeepSeekL5Analyst(
            transport=metered, model=config.model,
            outcomes_source=lambda: extract_outcomes(journal, PORTFOLIO_ID, run_id).outcomes,
            bars_source=holder, view_params=load_view_params(), market_params=vp, menu=menu,
            spending_gate=gate, enabled=True, max_tokens=config.max_tokens, **unico_extra)
        if consultant is not None:
            # Brain unico: DeepSeek propone, Claude consulente nei casi importanti, arbitro deterministico
            from backend.v3.runner.consult import CollaborativeAnalyst
            ds_analyst = CollaborativeAnalyst(ds_analyst, consultant, journal=journal, run_id=run_id,
                                              market_view=lambda sym, t: market_view_of(sym, t),
                                              portfolio_state=portfolio_state)
        analyst = MarketEntryAnalyst(ds_analyst)
    else:
        raise ValueError("invalid_analyst")
    store = CandleStore(get_json, keep=keep)
    minutes = CandleStore(get_json, keep={"1m": (60_000, MINUTE_STORE_BARS)})
    rules = ContractRules(get_json, maintenance_fraction=config.maintenance_fraction)
    exit_policy = config.exit_policy if config.exit_policy is not None else load_default_policy()   # schema 2
    mandate = MandateFile(data_dir / MANDATE_FILE, config.risk_policy, run_id)
    budget_halt = BudgetHalt(ledger, PROVIDER, config.daily_cap_units, metered)
    allowed = tuple(sorted(menu_ids(menu)))
    guardian_eval = (make_guardian(journal=journal, run_id=run_id, config=config, ledger=ledger, get_json=get_json)
                     if config.guardian is not None else None)
    if guardian_eval is not None and unico is not None:
        inner_guardian = guardian_eval

        def guardian_eval(at_ms: int):                       # ricorda il modo per il prompt e la revisione
            g = inner_guardian(at_ms)
            last_guardian["state"] = getattr(g, "state", "LOCKED")
            return g
    reviewer = None
    if unico is not None and unico.position_review:
        from backend.v3.brain_market.view import build_market_view
        from backend.v3.runner.position_review import DeepSeekPositionReviewer
        reviewer = DeepSeekPositionReviewer(
            transport=metered, model=config.model, spending_gate=gate, max_tokens=config.max_tokens,
            market_view=lambda sym, t: market_view_of(sym, t))
        from backend.v3.runner.monitor import HISTORY_MS, HISTORY_TF, history_best_from
        review_best = history_best_from(CandleStore(get_json, keep={HISTORY_TF: (HISTORY_MS, 1_500)}))

    def halted() -> Optional[str]:
        return mandate.problem() or budget_halt()

    def safety_add_commit(position_id: str, now_ms: int):
        """Secondo ingresso (posizione unica, 24/11): stesso scrittore serializzato e stessi controlli delle aperture."""
        from backend.v3.runner.open_serial import commit_paper_add
        return commit_paper_add(journal=journal, data_dir=data_dir, run_id=run_id, position_id=position_id,
                                clock_ms=clock_ms, guard_inputs=open_guard_inputs(), desk_mode=desk_mode)

    def safety_open_commit(decision):
        return commit_paper_open(
            journal=journal, data_dir=data_dir, run_id=run_id, decision=decision,
            clock_ms=clock_ms, guard_inputs=open_guard_inputs(),
            slippage_bps=config.slippage_bps, desk_mode=desk_mode,
            partial=None,        # 24/11: una sola posizione all'ingresso (niente quote); il 35 % a 2R e' una riduzione
            strategy=snapshot)   # Brain Live Evolution: versione e regole d'uscita con cui la posizione nasce

    def open_guard_inputs() -> dict:
        # Split mode only. The *real* on-disk exit owner is checked again under
        # the single-writer lock, after the model returns and before append.
        def fresh_market(sym: str, at_ms: int) -> bool:
            candles = {tf.name: store.refresh(sym, tf.name, at_ms) for tf in vp.timeframes}
            return regime_for_context(candles, timestamp_ms=at_ms, params=vp) != "UNKNOWN"

        guard_inputs = {
            "initial_equity": config.initial_equity,
            "risk_policy": config.risk_policy,
            "exit_healthy": lambda t: exit_service_healthy(data_dir=data_dir, run_id=run_id, now_ms=t),
            "mandate_problem": mandate.problem,
            "budget_problem": budget_halt,
            # Unlike the scheduled one-minute cache, this checks CURRENT PnL
            # and durably latches HALT if the limit was crossed during AI wait.
            "daily_loss_halted": lambda t: daily_loss.recheck(t).level == "halt",
            "paused": lambda: (data_dir / "pause.flag").exists(),
            "market_rules": lambda sym: rules(sym),
            "market_price": lambda sym, t: last_minute_close(sym, t, get_json),
            "market_fresh": fresh_market,
        }
        if unico is not None and unico.piggy is not None:
            guard_inputs["equity_reserve"] = reserve_of
        if unico is not None:
            # DeepSeek con ragionamento + eventuale consulto di Claude possono superare i 2 minuti: la decisione resta
            # valida fino a 5 minuti; il prezzo deve comunque essere entro lo 0,5 % (max_entry_divergence invariato)
            guard_inputs["max_decision_age_ms"] = UNICO_DECISION_AGE_MS
        return guard_inputs

    def run_cycle(now_ms: int, slot: int) -> CycleReport:
        rules.load(now_ms)
        # stesso slot che il runner usa per decidere quando girare: un riavvio a meta' slot non ridecide i simboli
        slot_start = slot * config.cycle_ms
        if reviewer is not None:
            # Brain unico: prima si rivedono le posizioni aperte (le uscite deterministiche restano attive)
            from backend.v3.runner.position_review import review_open_positions
            try:
                review_open_positions(journal=journal, run_id=run_id, data_dir=data_dir, now_ms=now_ms,
                                      reviewer=reviewer, mode=last_guardian["state"],
                                      price_of=lambda sym, t: last_minute_close(sym, t, get_json),
                                      consultant=consultant, best_of=review_best, funding_of=funding_of,
                                      market_of=market_view_of,
                                      add_commit=safety_add_commit if exit_mode == "sidecar" else None,
                                      partial_fraction=(unico.partial.fraction if unico.partial is not None
                                                        else Decimal("0.35")))
            except Exception:
                pass                                        # una revisione fallita non ferma il giro delle aperture
        return run_brain_cycle(
            now_ms=now_ms, journal=journal, run_id=run_id, symbols=config.symbols, store=store,
            bars_holder=holder, analyst=analyst, view_params=vp, risk_policy=config.risk_policy,
            mandate=mandate.read(), policy_verifier=make_verifier(mandate, run_id), market_rules=rules,
            initial_equity=config.initial_equity, slippage_bps=config.slippage_bps,
            allowed_strategy_ids=allowed, price_source=lambda sym, now: last_minute_close(sym, now, get_json),
            rotate=slot, require_open_commit=(exit_mode == "sidecar"),
            open_commit=safety_open_commit if exit_mode == "sidecar" else None,
            peer_source=peer_reader, trace="required",
            wall_ms=clock_ms if clock_ms is not None else (lambda: int(time.time() * 1000)),
            # anti-reingresso in sola osservazione: soglie provvisorie finche' E0 e il proprietario non decidono
            reentry_policy=ReentryPolicy(mode="observe"),
            slot_start_ms=slot_start, slot_end_ms=slot_start + config.cycle_ms,
            # Brain unico (27 mercati, un giro dura minuti): ogni simbolo con il PROPRIO istante, altrimenti le decisioni
            # dei simboli analizzati dopo ~2 minuti arrivano "vecchie" al controllo dopo l'AI (decision_stale)
            instant="per_symbol" if unico is not None else "cycle",
            guardian=guardian_eval,
            reserve_of=reserve_of if unico is not None and unico.piggy is not None else None)

    long_hold = {}
    if exit_policy.max_hold_ms is None:                 # Brain unico: nessun limite di tempo (vedi monitor.py)
        from backend.v3.runner.monitor import HISTORY_MS, HISTORY_TF, LONG_HOLD_WINDOW_MS, history_best_from
        long_hold = {"window_ms": LONG_HOLD_WINDOW_MS, "history_best": history_best_from(
            CandleStore(get_json, keep={HISTORY_TF: (HISTORY_MS, 1_500)}))}

    if unico is not None and unico.partial is not None:   # posizione unica: presa parziale come riduzione
        long_hold = dict(long_hold, partial=unico.partial,
                         step_of=lambda sym: Decimal(str(rules(sym)["quantity_step"])))

    def run_monitor(now_ms: int) -> MonitorReport:
        rules.load(now_ms)
        return run_exit_monitor(journal=journal, portfolio_id=PORTFOLIO_ID, run_id=run_id,
                                fetch_bars=minute_fetcher(minutes), policy=exit_policy,
                                fee_bps=config.fee_bps, now_ms=now_ms, **long_hold)

    def run_commands(now_ms: int) -> Optional[ManualCloseReport]:
        return run_manual_close(journal=journal, portfolio_id=PORTFOLIO_ID, run_id=run_id, data_dir=data_dir,
                                price_of=lambda sym, now: last_minute_close(sym, now, get_json),
                                fee_bps=config.fee_bps, now_ms=now_ms)

    daily_loss = DailyLossGuard(
        data_dir=data_dir, send=alert_send, warn_fraction=config.daily_loss_warn, halt_fraction=config.daily_loss_halt,
        evaluate=lambda now_ms: evaluate_daily_loss(
            journal=journal, portfolio_id=PORTFOLIO_ID, run_id=run_id, initial_equity=config.initial_equity,
            now_ms=now_ms, price_of=lambda sym, now: last_minute_close(sym, now, get_json),
            warn_fraction=config.daily_loss_warn, halt_fraction=config.daily_loss_halt),
        audit=lambda from_ms, now_ms: max_daily_loss_between(
            journal=journal, portfolio_id=PORTFOLIO_ID, run_id=run_id, initial_equity=config.initial_equity,
            from_ms=from_ms, now_ms=now_ms,
            closes_of=lambda sym, lo, hi: {b.open_time_ms: b.close for b in fetch_closed_bars(
                sym, lo, hi, candle_ms=60_000, get_json=get_json)}))

    runner = Runner(
        run_id=run_id, data_dir=data_dir,
        run_monitor=run_monitor if exit_mode == "legacy" else None,
        run_cycle=run_cycle, halted=halted, cycle_ms=config.cycle_ms,
        run_commands=run_commands if exit_mode == "legacy" else None, daily_loss=daily_loss,
        exit_mode=exit_mode,
        exit_healthy=(lambda t: exit_service_healthy(data_dir=data_dir, run_id=run_id, now_ms=t))
        if exit_mode == "sidecar" else None,
        fresh_clock_ms=clock_ms if exit_mode == "sidecar" else None)
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
    ap.add_argument("--exit-mode", choices=("legacy", "sidecar"), default="legacy",
                    help="sidecar: richiede journal e budget PAPER esistenti, e servizio uscite sano")
    a = ap.parse_args(argv)
    environ = os.environ if env is None else env
    try:
        base_raw = Path(a.config or default_config_path()).read_bytes()
        config = load_runner_config(base_raw)
    except (OSError, ValueError):
        print("config_invalid", file=sys.stderr)
        return 2
    if a.print_mandate:
        print(json.dumps(mandate_template(config.risk_policy, a.run_id), indent=2, sort_keys=True))
        return 0
    if environ.get("DESK_MODE") != "paper":
        print("refused: DESK_MODE must be 'paper'", file=sys.stderr)
        return 2
    # Explicit opt-in; never infer classic paths from legacy /opt defaults.
    peer_mode = environ.get("V3_BRAIN_PEER_OBSERVATIONS", "disabled")
    if peer_mode not in ("disabled", "paper_readonly"):
        print("peer_mode_invalid", file=sys.stderr)
        return 2
    peer_opts = {}
    if peer_mode == "paper_readonly":
        falco, toro = environ.get("V3_FALCO_DATA_DIR"), environ.get("V3_TORO_DATA_DIR")
        if not falco or not toro:
            print("peer_paths_missing", file=sys.stderr)
            return 2
        peer_opts = {"classic_peer_dirs": {"falco": Path(falco), "toro": Path(toro)}}
    data_dir = Path(a.data_dir)
    if a.exit_mode == "sidecar":
        # A split start must NEVER initialize an empty journal/run implicitly.
        if not data_dir.is_dir():
            print("split_data_missing", file=sys.stderr)
            return 2
        split_opts = {"exit_mode": "sidecar", "desk_mode": "paper", "clock_ms": now_fn}
    else:
        data_dir.mkdir(parents=True, exist_ok=True)
        split_opts = {}
    fence = None
    if a.exit_mode == "legacy":
        # Il runner legacy possiede monitor e chiusure: tiene per TUTTA la vita lo stesso lease kernel
        # dell'exit-worker. Se un altro proprietario lo detiene, non parte (e non chiude nulla).
        try:
            fence = LegacyExitFence(run_id=a.run_id, data_dir=data_dir).start()
        except ExitServiceBusy:
            print("exit_owner_busy", file=sys.stderr)
            return 3
        except ValueError:
            print("setup_invalid", file=sys.stderr)
            return 2
    try:
        return _run_built(a, data_dir, config, environ, get_json, inner_transport, now_fn, sleep_fn,
                          should_stop, split_opts, peer_opts, base_raw=base_raw)
    finally:
        if fence is not None:
            fence.stop()


def _strategy_of(data_dir: Path, run_id: str, base_raw: Optional[bytes]):
    """Versione attiva dal journal (Brain Live Evolution). Solo Brain unico (schema 3) con journal esistente."""
    if base_raw is None or not (data_dir / "journal.db").is_file():
        return None
    from backend.v3.strategy_versions import effective, read_registry
    return effective(base_raw, read_registry(EventJournal(str(data_dir / "journal.db")), run_id))


def _run_built(a, data_dir, config, environ, get_json, inner_transport, now_fn, sleep_fn,
               should_stop, split_opts, peer_opts, base_raw: Optional[bytes] = None) -> int:
    base_raw = base_raw if config.unico is not None else None
    try:
        strategy = _strategy_of(data_dir, a.run_id, base_raw)
        built = build_runner(data_dir=data_dir, run_id=a.run_id, config=config, get_json=get_json,
                             inner_transport=inner_transport, alert_send=telegram_sender(environ),
                             strategy=strategy, **split_opts, **peer_opts)
    except ValueError:
        print("setup_invalid", file=sys.stderr)
        return 2
    if (config.unico is not None and not a.once and environ.get("TELEGRAM_BOT_TOKEN")
            and environ.get("TELEGRAM_CHAT_ID")):
        # Brain unico: notifiche Telegram solo informative, dal journal, in un thread proprio (mai bloccanti)
        from backend.v3.runner.telegram_feed import JournalNotifier, start_thread
        start_thread(lambda: JournalNotifier(
            journal=EventJournal(str(data_dir / "journal.db")), run_id=a.run_id, data_dir=data_dir,
            send=telegram_sender(environ), initial_equity=config.initial_equity, piggy_policy=config.unico.piggy,
            default_tp_r=None if config.exit_policy is None else config.exit_policy.take_profit_r), now_fn)
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
    outer_stop = should_stop if should_stop is not None else (lambda: stop["flag"])
    while True:
        switch = {"to": None, "checked": 0}

        def stop_or_switch() -> bool:
            # Fra un tick e l'altro (mai a meta' giro): richiesta approvata dall'operatore -> eventi nel journal;
            # versione attiva cambiata -> si esce dal ciclo e si ricostruisce il runner con la nuova versione.
            if outer_stop():
                return True
            if base_raw is None:
                return False
            now = now_fn()
            try:
                from backend.v3.strategy_versions import REQUEST_FILE, apply_request, read_registry
                applied = None
                if (data_dir / REQUEST_FILE).is_file():
                    applied = apply_request(journal=built.journal, data_dir=data_dir, run_id=a.run_id,
                                            base_bytes=base_raw, now_ms=now)
                    print(json.dumps({"strategy_request": applied}, sort_keys=True), flush=True)
                if applied is not None or now - switch["checked"] >= 60_000:
                    switch["checked"] = now
                    active = read_registry(built.journal, a.run_id).active
                    if strategy is not None and active != strategy.version:
                        switch["to"] = active
                        return True
            except Exception:
                return False                              # un guasto qui non ferma mai il Brain
            return False

        built.runner.run(now_fn=now_fn, sleep_fn=sleep_fn, should_stop=stop_or_switch,
                         on_tick=lambda now, r: _log(now, r, last))
        if switch["to"] is None:
            return 0
        served = built.runner._last_slot * built.runner._cycle_ms if built.runner._last_slot >= 0 else None
        try:
            strategy = _strategy_of(data_dir, a.run_id, base_raw)
            built = build_runner(data_dir=data_dir, run_id=a.run_id, config=config, get_json=get_json,
                                 inner_transport=inner_transport, alert_send=telegram_sender(environ),
                                 strategy=strategy, **split_opts, **peer_opts)
        except ValueError:
            print("strategy_switch_setup_invalid", file=sys.stderr)
            return 2                                      # systemd (on-failure) riparte con la stessa versione attiva
        if served is not None:                            # il giro gia' servito non si ripete con la nuova frequenza
            built.runner._last_slot = served // built.runner._cycle_ms
        print(json.dumps({"strategy_switch": strategy.version}, sort_keys=True), flush=True)


if __name__ == "__main__":
    sys.exit(main())
