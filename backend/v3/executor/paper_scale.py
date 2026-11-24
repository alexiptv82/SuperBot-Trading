"""Posizione PAPER unica con ingresso progressivo e chiusure parziali (Brain unico, 24/11/2026).

Correzione del proprietario: una nuova apertura e' UNA posizione (un ``paper_open``). Poi:

* ``paper_add``    secondo ingresso FACOLTATIVO a un prezzo diverso e piu' conveniente (short: piu' alto; long: piu' basso),
                   deciso dopo una nuova analisi; stesso stop (mai allargato), prezzo medio aggiornato, margine in piu'
                   alla stessa leva. Al massimo uno per posizione e mai dopo una riduzione.
* ``paper_reduce`` chiusura PARZIALE della posizione esistente: quantita' chiusa, prezzo di uscita, P&L lordo e netto,
                   commissioni (entrata e uscita della sola parte chiusa, al prezzo medio), margine liberato, residuo.

La chiusura finale resta ``paper_close`` (``executor.paper_close``) sulla quantita' residua al prezzo medio. Ogni unita'
paga una volta la commissione d'entrata e una volta quella d'uscita: nessun doppio conteggio. Le posizioni aperte prima
di questa correzione (due quote ``tp1``/``runner``) non hanno mai questi eventi e restano identiche.

``position_state`` e' l'unico calcolo dello stato effettivo; ``expand_scaled`` traduce aumenti e riduzioni in coppie
apertura/chiusura equivalenti per chi valuta l'equity a mercato minuto per minuto (Guardian, perdita giornaliera):
stesso P&L realizzato agli stessi istanti e stesso non realizzato del calcolo sul prezzo medio.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal
from typing import Any, Mapping, Optional

from backend.v3.events import Event, EventConflict, EventJournal
from backend.v3.executor.paper import ExecutionError

ADD_KIND, REDUCE_KIND = "paper_add", "paper_reduce"
SCALE_KINDS = (ADD_KIND, REDUCE_KIND)
REDUCE_REASONS = frozenset({"take_profit", "brain_close", "manual"})
_Q8 = Decimal("0.00000001")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_Q8, rounding=ROUND_DOWN)


def _dec(v) -> Decimal:
    try:
        d = Decimal(str(v))
    except Exception:
        raise ExecutionError("corrupt_position_payload") from None
    if not d.is_finite():
        raise ExecutionError("corrupt_position_payload")
    return d


@dataclass
class PositionState:
    position_id: str
    open_event: Event
    symbol: str
    side: int
    stop: Decimal
    leverage: int
    quantity: Decimal                      # residua
    avg_price: Decimal                     # prezzo medio d'ingresso
    margin: Decimal                        # margine residuo
    adds: int = 0
    reduces: int = 0
    tp_reduced: bool = False               # gia' incassata la presa parziale a take-profit
    realized: Decimal = field(default_factory=lambda: Decimal("0"))
    closed: bool = False


def position_state(events, position_id: str) -> Optional[PositionState]:
    """Stato effettivo dagli eventi del journal (ordine del journal). ``None`` se la posizione non esiste."""
    st: Optional[PositionState] = None
    for ev in events:
        p = ev.payload if isinstance(ev.payload, Mapping) else {}
        if p.get("position_id") != position_id:
            continue
        if ev.kind == "paper_open":
            st = PositionState(position_id, ev, str(p.get("symbol")), int(p.get("side")), _dec(p.get("stop_price")),
                               int(p.get("leverage")), _dec(p.get("quantity")), _dec(p.get("fill_price")),
                               _dec(p.get("margin_used")))
        elif st is None:
            continue
        elif ev.kind == ADD_KIND:
            st.quantity, st.avg_price = _dec(p.get("new_quantity")), _dec(p.get("new_avg_price"))
            st.margin += _dec(p.get("margin_added"))
            st.adds += 1
        elif ev.kind == REDUCE_KIND:
            st.quantity = _dec(p.get("remaining_quantity"))
            st.margin -= _dec(p.get("margin_released"))
            st.realized += _dec(p.get("realized_pnl"))
            st.reduces += 1
            st.tp_reduced = st.tp_reduced or p.get("reason") == "take_profit"
        elif ev.kind == "paper_close":
            st.closed = True
    return st


def expand_scaled(events) -> list:
    """Eventi con aumenti/riduzioni tradotti in aperture/chiusure equivalenti (gli altri restano identici).

    Aumento -> nuovo segmento aperto al suo prezzo (stesso stop). Riduzione -> tutti i segmenti vivi si chiudono
    (P&L realizzato della riduzione sul primo, 0 sugli altri) e il residuo si riapre al prezzo medio. Chiusura finale ->
    tutti i segmenti vivi si chiudono (P&L sul primo)."""
    scaled = {ev.payload.get("position_id") for ev in events
              if ev.kind in SCALE_KINDS and isinstance(ev.payload, Mapping)}
    if not scaled:
        return list(events)
    out, live, n = [], {}, {}
    for ev in events:
        p = ev.payload if isinstance(ev.payload, Mapping) else {}
        pid = p.get("position_id")
        if pid not in scaled or ev.kind not in ("paper_open", "paper_close") + SCALE_KINDS:
            out.append(ev)
            continue
        base = live.setdefault(pid, {"tpl": None, "segs": [], "avg": None})

        def seg_open(fill, qty, ts):
            n[pid] = n.get(pid, 0) + 1
            sid = f"{pid}~{n[pid]}"
            pl = dict(base["tpl"], position_id=sid, fill_price=str(fill), quantity=str(qty))
            out.append(Event(f"paper_open.{sid}", ev.portfolio_id, ev.run_id, "paper_open", ts, ev.source, pl))
            base["segs"].append(sid)

        def close_all(pnl, ts):
            for i, sid in enumerate(base["segs"]):
                pl = {"position_id": sid, "symbol": base["tpl"].get("symbol"), "side": base["tpl"].get("side"),
                      "realized_pnl": str(pnl if i == 0 else Decimal("0"))}
                out.append(Event(f"paper_close.{sid}", ev.portfolio_id, ev.run_id, "paper_close", ts, ev.source, pl))
            base["segs"] = []
        if ev.kind == "paper_open":
            base["tpl"] = dict(p)
            base["avg"] = _dec(p.get("fill_price"))
            seg_open(base["avg"], _dec(p.get("quantity")), ev.occurred_at_ms)
        elif base["tpl"] is None:
            out.append(ev)
        elif ev.kind == ADD_KIND:
            base["avg"] = _dec(p.get("new_avg_price"))
            seg_open(_dec(p.get("fill_price")), _dec(p.get("quantity")), ev.occurred_at_ms)
        elif ev.kind == REDUCE_KIND:
            close_all(_dec(p.get("realized_pnl")), ev.occurred_at_ms)
            seg_open(base["avg"], _dec(p.get("remaining_quantity")), ev.occurred_at_ms)
        else:
            close_all(_dec(p.get("realized_pnl")), ev.occurred_at_ms)
    return out


def _read(journal: EventJournal, portfolio_id: str, run_id: str) -> list:
    try:
        return [se.event for se in journal.list_run(portfolio_id, run_id)]
    except Exception as exc:
        raise ExecutionError("journal_read_failed") from exc


def reduce_paper(*, portfolio_id: str, run_id: str, position_id: str, fraction: Decimal, exit_price: Decimal,
                 reason: str, fee_bps: Decimal | int, journal: EventJournal, quantity_step: Decimal,
                 minimum_notional: Decimal = Decimal("5"), now_ms: Optional[int] = None) -> dict[str, Any]:
    """Chiude ``fraction`` della posizione residua (arrotondata al passo). Se la parte chiusa o il residuo restano
    sotto il nozionale minimo, ``ExecutionError("reduce_too_small")``: il chiamante decide (di solito non riduce)."""
    if reason not in REDUCE_REASONS:
        raise ExecutionError("invalid_reason")
    frac, exit_d, fee_d, step = _dec(fraction), _dec(exit_price), _dec(fee_bps), _dec(quantity_step)
    if not (0 < frac < 1) or exit_d <= 0 or not 0 <= fee_d <= 100 or step <= 0:
        raise ExecutionError("invalid_reduce_input")
    ts = now_ms if now_ms is not None else int(time.time() * 1000)
    st = position_state(_read(journal, portfolio_id, run_id), position_id)
    if st is None:
        raise ExecutionError("position_not_found")
    if st.closed:
        raise ExecutionError("position_already_closed")
    if ts < st.open_event.occurred_at_ms:
        raise ExecutionError("close_before_open")
    qty = (st.quantity * frac / step).to_integral_value(rounding=ROUND_DOWN) * step
    rest = st.quantity - qty
    if qty <= 0 or rest <= 0 or qty * exit_d < minimum_notional or rest * exit_d < minimum_notional:
        raise ExecutionError("reduce_too_small")
    gross = _q(Decimal(st.side) * (exit_d - st.avg_price) * qty)
    n_entry, n_exit = _q(st.avg_price * qty), _q(exit_d * qty)
    fees = _q((n_entry + n_exit) * fee_d / Decimal(10000))
    released = _q(st.margin * qty / st.quantity)
    realized = _q(gross - fees)
    p = st.open_event.payload
    payload = {"position_id": position_id, "symbol": st.symbol, "side": st.side, "entry_price": str(st.avg_price),
               "exit_price": str(exit_d), "quantity": str(qty), "notional_entry": str(n_entry),
               "notional_exit": str(n_exit), "gross_pnl": str(gross), "fees": str(fees),
               "realized_pnl": str(realized), "remaining_quantity": str(rest), "margin_released": str(released),
               "margin_used": str(released), "leverage": st.leverage, "fee_bps": str(fee_d), "reason": reason,
               "opened_at_ms": st.open_event.occurred_at_ms, "held_ms": ts - st.open_event.occurred_at_ms,
               "loss_exceeds_margin": bool(realized < 0 and -realized > released),
               "decision_event_id": p.get("decision_event_id", "")}
    try:
        journal.append(Event(f"{REDUCE_KIND}.{position_id}.{st.reduces + 1}", portfolio_id, run_id, REDUCE_KIND, ts,
                             "executor.paper_scale", payload))
    except EventConflict:
        raise ExecutionError("position_changed") from None
    except Exception as exc:
        raise ExecutionError("journal_write_failed") from exc
    return payload


def add_paper(*, portfolio_id: str, run_id: str, position_id: str, fill_price: Decimal, quantity: Decimal,
              journal: EventJournal, decision_event_id: str = "", now_ms: Optional[int] = None) -> dict[str, Any]:
    """Secondo ingresso gia' validato (prezzo, rischio, margine) dal chiamante: registra soltanto, con i controlli
    strutturali (posizione aperta, nessuna riduzione prima, al massimo un aumento, prezzo piu' conveniente)."""
    fill, q = _dec(fill_price), _dec(quantity)
    if fill <= 0 or q <= 0:
        raise ExecutionError("invalid_add_input")
    ts = now_ms if now_ms is not None else int(time.time() * 1000)
    st = position_state(_read(journal, portfolio_id, run_id), position_id)
    if st is None:
        raise ExecutionError("position_not_found")
    if st.closed or st.reduces or st.adds:
        raise ExecutionError("add_not_allowed")
    if st.side * (st.avg_price - fill) <= 0 or st.side * (fill - st.stop) <= 0:
        raise ExecutionError("add_price_not_better")       # short: piu' alto dell'ingresso e sotto lo stop; long: speculare
    new_qty = st.quantity + q
    new_avg = _q((st.avg_price * st.quantity + fill * q) / new_qty)
    added = _q(fill * q / st.leverage)
    payload = {"position_id": position_id, "symbol": st.symbol, "side": st.side, "fill_price": str(fill),
               "quantity": str(q), "margin_added": str(added), "new_quantity": str(new_qty),
               "new_avg_price": str(new_avg), "stop_price": str(st.stop), "leverage": st.leverage,
               "decision_event_id": decision_event_id}
    try:
        journal.append(Event(f"{ADD_KIND}.{position_id}.1", portfolio_id, run_id, ADD_KIND, ts, "executor.paper_scale",
                             payload))
    except EventConflict:
        raise ExecutionError("position_changed") from None
    except Exception as exc:
        raise ExecutionError("journal_write_failed") from exc
    return payload


# ----------------------------------------------------------------------------- secondo ingresso: dimensione
MIN_ADD_GAP_R = Decimal("0.25")        # il nuovo prezzo deve essere migliore di almeno 0,25 R (e 10 bp)
MIN_ADD_GAP_FRACTION = Decimal("0.001")
MIN_STOP_ROOM_R = Decimal("0.3")       # e ad almeno 0,3 R dallo stop: un prezzo che sfiora lo stop non e' conveniente


def add_price_ok(*, side: int, avg_price: Decimal, initial_risk: Decimal, stop: Decimal, price: Decimal) -> bool:
    """Prezzo realmente piu' conveniente dell'ingresso e non vicino all'invalidazione (stop invariato)."""
    gap = side * (avg_price - price)
    return (initial_risk > 0 and gap >= MIN_ADD_GAP_R * initial_risk and gap >= MIN_ADD_GAP_FRACTION * price
            and side * (price - stop) >= MIN_STOP_ROOM_R * initial_risk)


def add_quantity(*, side: int, quantity: Decimal, avg_price: Decimal, stop: Decimal, price: Decimal,
                 cost_fraction: Decimal, risk_budget: Decimal, open_risk_room: Decimal, side_risk_room: Decimal,
                 margin_room: Decimal, leverage: int, step: Decimal, minimum_notional: Decimal) -> Decimal:
    """Quantita' massima del secondo ingresso (multiplo del passo) o 0.

    Rischio della posizione allo stop dopo l'aumento, con i costi, sul nuovo prezzo medio:
        R(q) = Q*|A - S| + q*|P - S| + c*(A*Q + P*q)       (lineare in q; stesso stop)
    vincoli: R(q) <= ``risk_budget`` (rischio per trade, mai aumentato); R(q) - R(0) <= stanze di rischio aperto
    (totale e stessa direzione); margine P*q/leva <= ``margin_room``."""
    r0 = quantity * abs(avg_price - stop) + cost_fraction * avg_price * quantity
    per_unit = abs(price - stop) + cost_fraction * price
    if per_unit <= 0 or leverage <= 0 or step <= 0:
        return Decimal("0")
    limits = [(risk_budget - r0) / per_unit, open_risk_room / per_unit, side_risk_room / per_unit,
              margin_room * leverage / price]
    q = min(limits)
    if q <= 0:
        return Decimal("0")
    q = (q / step).to_integral_value(rounding=ROUND_DOWN) * step
    return q if q > 0 and q * price >= minimum_notional else Decimal("0")
