"""PAPER close executor (F5b) for SuperBot V3.

Chiude una posizione PAPER aperta da ``execute_paper`` scrivendo un evento
``paper_close`` nel journal append-only. Offline: nessuna API di exchange.

Perche' esiste
--------------
``execute_paper`` gestisce solo OPEN. Senza una chiusura non esiste un esito
(PnL, costi, durata) da cui il cervello possa imparare (F7).

Scelte di progetto
------------------
* Nessun valore di mercato o di costo e' hardcoded: ``exit_price`` e
  ``fee_bps`` (per lato) sono argomenti espliciti del chiamante. Questo modulo
  non decide soglie, stop o limiti di rischio.
* Fail-closed: ogni anomalia solleva ``ExecutionError`` con un codice
  snake_case e NON scrive nulla. Una posizione non si chiude due volte.
* ``reason`` e' un insieme chiuso. ``manual`` resta distinguibile da
  ``brain_close`` e ``stop``: una chiusura manuale conta come trade vero, ma il
  Brain deve poterla riconoscere per imparare senza copiarla alla cieca.
* La perdita NON viene troncata al margine: il valore registrato e' il calcolo
  puro; ``loss_exceeds_margin`` lo segnala. Decidere se/come simulare la
  liquidazione e' una scelta di modello che spetta all'utente.
* Concorrenza e idempotenza: l'unicita' di ``event_id = paper_close.<position_id>``
  (vincolo UNIQUE del journal, scrittura sotto ``BEGIN IMMEDIATE``) garantisce
  che per ogni posizione esista AL PIU' UN ``paper_close``. Verificato con
  thread veri (vedi ``TestConcurrency``). Casi:
    - chiusura gia' scritta quando la richiesta legge il journal: fallisce con
      ``position_already_closed`` (anche un retry identico DOPO la chiusura);
    - due richieste che si sovrappongono (entrambe leggono prima che una scriva):
      se sono IDENTICHE (stesso prezzo, costi, ragione e timestamp) il journal
      ignora il duplicato e ENTRAMBE possono ricevere la stessa ricevuta; se
      sono DIVERSE vince la prima scrittura e le altre falliscono con
      ``position_already_closed``.
  Per questo chi somma i PnL deve leggere gli eventi ``paper_close`` dal
  journal, non sommare le ricevute restituite ai chiamanti.
* ``decision_event_id`` e' copiato dal ``paper_open`` (scritto da ``execute_paper``
  dal passo P2: id dell'evento ``brain_decision`` che ha generato la posizione;
  "" = posizione senza decisione collegata). Deve essere una stringa breve:
  altrimenti ``corrupt_position_payload``.

Contratto dell'evento ``paper_close`` (letto da ``backend/v3/dashboard.py``)::

    position_id, symbol, side, entry_price, exit_price, quantity, notional_entry,
    notional_exit, gross_pnl, fees, realized_pnl, margin_used, leverage,
    fee_bps, reason, opened_at_ms, held_ms, loss_exceeds_margin, decision_event_id
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any, Mapping

from backend.v3.events import Event, EventConflict, EventJournal
from backend.v3.executor.paper import ExecutionError

# Insieme chiuso delle ragioni di chiusura.
# take_profit e timeout: uscite meccaniche del runner (backend/v3/runner/exits.py).
CLOSE_REASONS = frozenset({"stop", "brain_close", "manual", "liquidation", "take_profit", "timeout"})

_QUANT = Decimal("0.00000001")
_MAX_FEE_BPS = Decimal("100")  # 1% per lato: oltre e' quasi certamente un errore di unita'


@dataclass(frozen=True)
class CloseReceipt:
    """Record immutabile di una chiusura PAPER completata."""
    position_id: str
    portfolio_id: str
    run_id: str
    symbol: str
    side: int
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    gross_pnl: Decimal
    fees: Decimal
    realized_pnl: Decimal
    reason: str
    held_ms: int
    timestamp_ms: int
    journal_seq: int
    journal_event_id: str


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ExecutionError(code)


def _dec(value: Any, code: str) -> Decimal:
    """Decimal finito o ExecutionError(code). Rifiuta bool, NaN e infiniti."""
    _require(not isinstance(value, bool), code)
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ExecutionError(code) from None
    _require(d.is_finite(), code)
    return d


def _num_input(value: Any, code: str) -> Decimal:
    """Numero passato dal chiamante: solo Decimal o int (mai float, bool o stringhe).

    Un float e' una approssimazione binaria: per importi e prezzi si rifiuta
    invece di convertirlo in silenzio.
    """
    _require(type(value) in (Decimal, int), code)
    return _dec(value, code)


def _q(value: Decimal) -> Decimal:
    return value.quantize(_QUANT, rounding=ROUND_HALF_EVEN)


def _find_position(journal: EventJournal, portfolio_id: str, run_id: str,
                   position_id: str) -> Event:
    """Ritorna l'evento paper_open della posizione, ancora aperta, o solleva."""
    try:
        stored = journal.list_run(portfolio_id, run_id)
    except Exception as exc:
        raise ExecutionError("journal_read_failed") from exc
    opened: Event | None = None
    already_closed = False
    for se in stored:
        ev = se.event
        payload = ev.payload if isinstance(ev.payload, Mapping) else {}
        if payload.get("position_id") != position_id:
            continue
        if ev.kind == "paper_open":
            opened = ev
        elif ev.kind == "paper_close":
            already_closed = True
    _require(opened is not None, "position_not_found")
    _require(not already_closed, "position_already_closed")
    return opened  # type: ignore[return-value]


def close_paper(
    *,
    portfolio_id: str,
    run_id: str,
    position_id: str,
    exit_price: Decimal,
    reason: str,
    fee_bps: Decimal | int,
    journal: EventJournal,
    now_ms: int | None = None,
) -> CloseReceipt:
    """Chiude una posizione PAPER aperta e ne registra l'esito nel journal.

    Parameters
    ----------
    exit_price:
        Prezzo di uscita deciso dal chiamante (feed, stop colpito, chiusura manuale).
    fee_bps:
        Costo per lato in basis points, applicato a entrata e uscita (round-trip).
    reason:
        Uno di ``CLOSE_REASONS``.
    now_ms:
        Timestamp deterministico per i test; se None usa l'orologio.

    Raises
    ------
    ExecutionError
        Con codice snake_case, senza scrivere nel journal.
    """
    # --- validazione degli argomenti (prima di qualsiasi lettura/scrittura) ---
    _require(isinstance(portfolio_id, str) and bool(portfolio_id), "invalid_portfolio_id")
    _require(isinstance(run_id, str) and bool(run_id), "invalid_run_id")
    _require(isinstance(position_id, str) and bool(position_id), "invalid_position_id")
    _require(isinstance(journal, EventJournal), "invalid_journal_type")
    _require(isinstance(reason, str) and reason in CLOSE_REASONS, "invalid_reason")
    exit_d = _num_input(exit_price, "invalid_exit_price")
    _require(exit_d > 0, "invalid_exit_price")
    fee_d = _num_input(fee_bps, "invalid_fee_bps")
    _require(0 <= fee_d <= _MAX_FEE_BPS, "invalid_fee_bps")

    timestamp_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    _require(type(timestamp_ms) is int and timestamp_ms > 0, "invalid_timestamp")

    # --- la posizione deve esistere ed essere ancora aperta ---
    opened = _find_position(journal, portfolio_id, run_id, position_id)
    p = opened.payload
    side = p.get("side")
    _require(type(side) is int and side in (-1, 1), "corrupt_position_payload")
    entry = _dec(p.get("fill_price"), "corrupt_position_payload")
    qty = _dec(p.get("quantity"), "corrupt_position_payload")
    margin = _dec(p.get("margin_used"), "corrupt_position_payload")
    _require(entry > 0 and qty > 0 and margin > 0, "corrupt_position_payload")
    leverage = p.get("leverage")
    _require(type(leverage) is int and 1 <= leverage <= 125, "corrupt_position_payload")
    symbol = p.get("symbol")
    _require(isinstance(symbol, str) and bool(symbol), "corrupt_position_payload")
    decision_event_id = p.get("decision_event_id", "")
    _require(isinstance(decision_event_id, str) and len(decision_event_id) <= 128,
             "corrupt_position_payload")
    _require(timestamp_ms >= opened.occurred_at_ms, "close_before_open")

    # --- calcolo (Decimal puro; ordine delle operazioni fissato) ---
    # Valori finiti ma estremi (esponenti enormi, troppe cifre) fanno sollevare
    # decimal.InvalidOperation/Overflow: li convertiamo nel codice d'errore del
    # contratto invece di lasciarli uscire come eccezioni non tipizzate.
    try:
        gross = _q(Decimal(side) * (exit_d - entry) * qty)
        notional_entry = _q(entry * qty)
        notional_exit = _q(exit_d * qty)
        fees = _q((notional_entry + notional_exit) * fee_d / Decimal(10000))
        realized = _q(gross - fees)
        loss_exceeds_margin = bool(realized < 0 and -realized > margin)
    except ArithmeticError:  # decimal.DecimalException e' sottoclasse di ArithmeticError
        raise ExecutionError("numeric_out_of_range") from None
    held_ms = timestamp_ms - opened.occurred_at_ms

    payload: dict[str, Any] = {
        "position_id": position_id,
        "symbol": symbol,
        "side": side,
        "entry_price": str(entry),
        "exit_price": str(exit_d),
        "quantity": str(qty),
        "notional_entry": str(notional_entry),
        "notional_exit": str(notional_exit),
        "gross_pnl": str(gross),
        "fees": str(fees),
        "realized_pnl": str(realized),
        "margin_used": str(margin),
        "leverage": leverage,
        "fee_bps": str(fee_d),
        "reason": reason,
        "opened_at_ms": opened.occurred_at_ms,
        "held_ms": held_ms,
        "loss_exceeds_margin": loss_exceeds_margin,
        "decision_event_id": decision_event_id,
    }
    event = Event(
        event_id=f"paper_close.{position_id}",
        portfolio_id=portfolio_id,
        run_id=run_id,
        kind="paper_close",
        occurred_at_ms=timestamp_ms,
        source="executor.paper_close",
        payload=payload,
    )
    try:
        stored = journal.append(event)
    except EventConflict:
        # Stesso event_id (paper_close.<position_id>) con contenuto diverso: un'altra
        # chiusura e' stata scritta fra la nostra lettura e la nostra scrittura.
        # Non e' un guasto del journal: la posizione risulta gia' chiusa.
        raise ExecutionError("position_already_closed") from None
    except Exception as exc:
        raise ExecutionError("journal_write_failed") from exc

    return CloseReceipt(
        position_id=position_id, portfolio_id=portfolio_id, run_id=run_id,
        symbol=symbol, side=side, entry_price=entry, exit_price=exit_d,
        quantity=qty, gross_pnl=gross, fees=fees, realized_pnl=realized,
        reason=reason, held_ms=held_ms, timestamp_ms=timestamp_ms,
        journal_seq=stored.seq, journal_event_id=stored.event.event_id,
    )
