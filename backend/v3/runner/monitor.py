"""Monitor delle posizioni PAPER aperte: applica le uscite di ``exits.py`` con candele da 1 minuto.

A ogni chiamata: per ogni posizione aperta del portafoglio scarica le candele chiuse dal minuto
dell'apertura, le spezza in tratti contigui (una barra mancante non nasconde uno stop colpito nelle altre)
e, alla prima uscita, chiude con ``close_paper`` (motivi ``stop``, ``take_profit``, ``timeout``).
Un errore su una posizione non ferma le altre: finisce nel rapporto. Idempotente: ``close_paper`` rifiuta
una posizione gia' chiusa. Nessuna rete qui: ``fetch_bars`` e' iniettata.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Sequence

from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.executor.paper import ExecutionError
from backend.v3.executor.paper_close import close_paper
from backend.v3.features.indicators import Bar
from backend.v3.runner.exits import ExitPolicy, evaluate_exit
from backend.v3.runner.feed import contiguous_runs

MINUTE_MS = 60_000
FetchBars = Callable[[str, int, int], Sequence[Bar]]     # (symbol, start_ms, end_ms) -> barre da 1 minuto


@dataclass(frozen=True)
class MonitorReport:
    checked: int
    closed: tuple[tuple[str, str], ...]                  # (position_id, motivo)
    errors: tuple[tuple[str, str], ...]                  # (position_id, codice)


def run_exit_monitor(*, journal: EventJournal, portfolio_id: str, run_id: str, fetch_bars: FetchBars,
                     policy: ExitPolicy, fee_bps: Decimal | int, now_ms: int) -> MonitorReport:
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError("invalid_now")
    end = now_ms // MINUTE_MS * MINUTE_MS                # solo minuti chiusi
    summary = build_summary(journal, portfolio_id, run_id)
    closed: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    for pos in summary.open_positions:
        try:
            start = pos.opened_at_ms // MINUTE_MS * MINUTE_MS
            if start >= end:
                continue                                  # aperta nello stesso minuto: nessuna barra chiusa ancora
            bars = list(fetch_bars(pos.symbol, start, end))
            signal = None
            for run in contiguous_runs(bars, MINUTE_MS):
                signal = evaluate_exit(side=pos.side, fill_price=pos.fill_price, stop_price=pos.stop_price,
                                       opened_at_ms=pos.opened_at_ms, bars=run, candle_ms=MINUTE_MS,
                                       policy=policy)
                if signal is not None:
                    break
            if signal is None:
                continue
            close_paper(portfolio_id=portfolio_id, run_id=run_id, position_id=pos.position_id,
                        exit_price=signal.price, reason=signal.reason, fee_bps=fee_bps,
                        journal=journal, now_ms=now_ms)
            closed.append((pos.position_id, signal.reason))
        except ExecutionError as exc:
            errors.append((pos.position_id, str(exc)))
        except ValueError as exc:
            errors.append((pos.position_id, str(exc) or "invalid"))
        except Exception:
            errors.append((pos.position_id, "feed_error"))
    return MonitorReport(len(summary.open_positions), tuple(closed), tuple(errors))
