"""Monitor delle posizioni PAPER aperte: applica le uscite di ``exits.py`` con candele da 1 minuto.

A ogni chiamata: per ogni posizione aperta del portafoglio scarica le candele chiuse dal minuto
dell'apertura, le spezza in tratti contigui (una barra mancante non nasconde uno stop colpito nelle altre)
e, alla prima uscita, chiude con ``close_paper`` (motivi ``stop``, ``take_profit``, ``timeout``).
Un errore su una posizione non ferma le altre: finisce nel rapporto. Idempotente: ``close_paper`` rifiuta
una posizione gia' chiusa. Nessuna rete qui: ``fetch_bars`` e' iniettata.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Callable, Sequence

from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.executor.paper import ExecutionError
from backend.v3.executor.paper_close import close_paper
from backend.v3.features.indicators import Bar
from backend.v3.runner.exits import ExitPolicy, evaluate_exit, favorable_extreme
from backend.v3.runner.feed import contiguous_runs

MINUTE_MS = 60_000
FetchBars = Callable[[str, int, int], Sequence[Bar]]     # (symbol, start_ms, end_ms) -> barre da 1 minuto


@dataclass(frozen=True)
class MonitorReport:
    checked: int
    closed: tuple[tuple[str, str], ...]                  # (position_id, motivo)
    errors: tuple[tuple[str, str], ...]                  # (position_id, codice)
    protected: tuple[tuple[str, str], ...] = ()          # (position_id, break_even|trailing|protect): stop spostato


STOP_MOVE_KIND = "stop_move"


def stop_moves_by_position(journal: EventJournal, portfolio_id: str, run_id: str) -> dict:
    """``{position_id: ((valido_dal_minuto_ms, stop), ...)}`` dagli eventi ``stop_move`` del Brain unico. Uno
    spostamento vale dalla candela che apre DOPO il minuto in cui e' stato registrato (mai retroattivo)."""
    out: dict = {}
    for r in journal.list_run_kinds_since(portfolio_id, run_id, (STOP_MOVE_KIND,), 0):
        p = r.event.payload if isinstance(r.event.payload, dict) else {}
        pid, raw = p.get("position_id"), p.get("stop_price")
        try:
            level = Decimal(str(raw))
        except ArithmeticError:
            continue
        if type(pid) is not str or not level.is_finite() or level <= 0:
            continue
        at = (r.event.occurred_at_ms // MINUTE_MS + 1) * MINUTE_MS
        out.setdefault(pid, []).append((at, level))
    return {k: tuple(v) for k, v in out.items()}


def run_exit_monitor(*, journal: EventJournal, portfolio_id: str, run_id: str, fetch_bars: FetchBars,
                     policy: ExitPolicy, fee_bps: Decimal | int, now_ms: int) -> MonitorReport:
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError("invalid_now")
    end = now_ms // MINUTE_MS * MINUTE_MS                # solo minuti chiusi
    summary = build_summary(journal, portfolio_id, run_id)
    closed: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    protected: list[tuple[str, str]] = []
    try:                 # serve solo al break-even; un valore non valido diventa un errore per posizione, mai un crash
        fee = Decimal(str(fee_bps)) if type(fee_bps) in (int, Decimal) else None
    except ArithmeticError:
        fee = None
    moves = stop_moves_by_position(journal, portfolio_id, run_id)
    for pos in summary.open_positions:
        try:
            # Brain unico: take-profit proprio della quota e stop stretti dall'AI (run storiche: invariato)
            pos_policy = policy if pos.take_profit_r is None else replace(policy, take_profit_r=pos.take_profit_r)
            start = pos.opened_at_ms // MINUTE_MS * MINUTE_MS
            if start >= end:
                continue                                  # aperta nello stesso minuto: nessuna barra chiusa ancora
            bars = list(fetch_bars(pos.symbol, start, end))
            signal = None
            best = None          # miglior prezzo dei tratti precedenti: la protezione non si azzera dopo un buco
            for run in contiguous_runs(bars, MINUTE_MS):
                signal = evaluate_exit(side=pos.side, fill_price=pos.fill_price, stop_price=pos.stop_price,
                                       opened_at_ms=pos.opened_at_ms, bars=run, candle_ms=MINUTE_MS,
                                       policy=pos_policy, fee_bps=fee, best_before=best,
                                       stop_moves=moves.get(pos.position_id, ()))
                if signal is not None:
                    break
                best = favorable_extreme(pos.side, best, run, pos.opened_at_ms)
            if signal is None:
                # Only closed candles whose opens are >= position entry can
                # be evaluated. The opening partial minute is deliberately
                # excluded by evaluate_exit; it must NOT cause false alarms.
                first_eligible = ((pos.opened_at_ms + MINUTE_MS - 1) // MINUTE_MS) * MINUTE_MS
                if first_eligible < end:
                    timestamps = sorted({b.open_time_ms for b in bars
                                         if first_eligible <= b.open_time_ms < end})
                    expected = (end - first_eligible) // MINUTE_MS
                    # Missing, stale, or internally gapped data is not
                    # evidence that the stop was checked: degrade heartbeat
                    # and veto new PAPER opens until the feed recovers.
                    if (len(timestamps) != expected or not timestamps
                            or timestamps[0] != first_eligible
                            or timestamps[-1] != end - MINUTE_MS
                            or any(b - a != MINUTE_MS
                                   for a, b in zip(timestamps, timestamps[1:]))):
                        errors.append((pos.position_id, "exit_feed_incomplete"))
                continue
            close_paper(portfolio_id=portfolio_id, run_id=run_id, position_id=pos.position_id,
                        exit_price=signal.price, reason=signal.reason, fee_bps=fee_bps,
                        journal=journal, now_ms=now_ms,
                        stop_kind=(signal.stop_kind if signal.reason == "stop" and signal.stop_kind != "initial"
                                   else None))
            closed.append((pos.position_id, signal.reason))
            if signal.reason == "stop" and signal.stop_kind != "initial":
                protected.append((pos.position_id, signal.stop_kind))
        except ExecutionError as exc:
            errors.append((pos.position_id, str(exc)))
        except ValueError as exc:
            errors.append((pos.position_id, str(exc) or "invalid"))
        except Exception:
            errors.append((pos.position_id, "feed_error"))
    return MonitorReport(len(summary.open_positions), tuple(closed), tuple(errors), tuple(protected))
