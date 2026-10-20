"""
live_sync.py — Copia sull'exchange quello che il motore fa, e riallinea motore ed exchange (solo live).

Il motore (engine.py) continua a decidere e a fare i conti come in paper: nessun parametro cambia.
Qui si decide soltanto come trasferire ogni sua azione sull'exchange e cosa fare se i due mondi divergono:

- apertura / DCA / seconda gamba: il motore agisce, poi l'exchange; se l'exchange rifiuta, il motore
  TORNA INDIETRO (come se non fosse successo nulla). Mai esposizione sull'exchange che il motore non ha.
- chiusura / TP parziale decisi da regole o da Claude: prima l'exchange, poi il motore (se l'exchange
  non riesce, la posizione resta com'e').
- uscite del motore sulle candele (stop, take profit, liquidazione): il motore chiude, poi si chiude
  quello che resta sull'exchange; se non riesce, la richiesta resta in `pending_close` e si riprova.
- fine ciclo: si confronta tutto con l'exchange (la verita'). Exchange piatto e motore aperto -> il motore
  chiude ("chiusa su Bitget"). Posizione estranea / lato opposto / quantita' molto diversa / margine non
  isolato / lettura fallita -> BLOCCO delle nuove aperture e avviso; non si tocca nulla di automatico.

Tutte le funzioni sono no-op se il connettore non e' in modalita' live.
"""
from __future__ import annotations

import copy
from typing import Callable, Optional

from desk.live_connector import LiveError, _base


def _noop(*_a, **_k) -> None:
    return None


# ── istantanea / ripristino del conto (per tornare indietro se l'exchange rifiuta) ────────────

def snapshot_position(acc, sym: str):
    """Copia della posizione e della cassa prima di un'azione che potrebbe dover essere annullata."""
    pos = acc.positions.get(sym)
    return None if pos is None else (copy.deepcopy(pos), acc.cash)


def restore_position(acc, sym: str, snap) -> None:
    """Rimette la posizione com'era nell'istantanea. Il cursore delle barre giudicate NON torna mai indietro:
    se l'istantanea precede `on_bar`, la barra e' stata comunque giudicata una volta e non va rigiudicata."""
    if snap is not None:
        pos = snap[0]
        cur = acc.positions.get(sym)
        if cur is not None:
            pos.last_bar_ms = max(pos.last_bar_ms, cur.last_bar_ms)
        acc.positions[sym] = pos
        acc.cash = snap[1]


def rollback_open(acc, pos) -> None:
    """Annulla un'apertura appena fatta nel motore (l'exchange l'ha rifiutata)."""
    acc.positions.pop(pos.symbol, None)
    acc.cash += pos.total_margin + pos.fee_open


# ── azioni del motore da copiare sull'exchange ─────────────────────────────────────────────

def open_on_exchange(live, pos, px: float) -> tuple:
    """Apre sull'exchange quanto il motore ha appena aperto (stessa quantita', stesso stop/TP)."""
    return live.open(pos.symbol, pos.side, pos.qty, pos.leverage, pos.sl, pos.tp, ref_price=px)


def dca_on_exchange(live, acc, sym: str, before, px: float) -> tuple:
    """Dopo acc.add_dca: porta sull'exchange i contratti aggiunti. Se rifiuta, il motore torna com'era."""
    pos = acc.positions.get(sym)
    if pos is None or before is None:
        return False, "posizione non trovata"
    added = pos.qty - before[0].qty
    ok, detail = live.add(sym, pos.side, added, pos.leverage, sl=pos.sl, tp=pos.tp, ref_price=px)
    if not ok:
        restore_position(acc, sym, before)
    return ok, detail


def partial_on_exchange(live, pos, fraction: float) -> tuple:
    """Prima dell'engine.partial_close: riduce la posizione reale della stessa frazione."""
    fraction = max(0.05, min(0.95, fraction))     # stessa tosatura del motore
    return live.reduce(pos.symbol, pos.side, fraction)


def after_bar(live, acc, sym: str, before, result: Optional[dict],
              alert: Callable[[str], None] = _noop, now_ms: int = 0) -> Optional[str]:
    """Dopo acc.on_bar(sym,...): copia sull'exchange quello che il motore ha fatto su quella candela.

    - il motore ha CHIUSO (stop, take profit, liquidazione): si chiude quel che resta sull'exchange;
    - il motore ha eseguito la SECONDA GAMBA: si aggiungono i contratti; se l'exchange rifiuta il motore
      torna indietro e la gamba si ANNULLA (non si ritenta); la barra resta giudicata (cursore invariato).
    Ritorna una nota testuale solo se qualcosa va guardato."""
    if not live._live:
        return None
    if result is not None:
        side = result.get("side")
        ok, detail = live.close(sym, side)
        if live.last_fill:
            result["live"] = dict(live.last_fill)
        if not ok:
            live.pending_close[_base(sym)] = side
            msg = (f"{sym}: il motore ha chiuso ({result.get('why')}) ma su Bitget la chiusura non e' riuscita "
                   f"({detail}). Riprovo; controlla la posizione.")
            alert(msg)
            return msg
        return None
    pos = acc.positions.get(sym)
    if pos is not None and before is not None and pos.qty > before[0].qty * (1 + 1e-9):
        added = pos.qty - before[0].qty
        ok, detail = live.add(sym, pos.side, added, pos.leverage, sl=pos.sl, tp=pos.tp, ref_price=pos.entry)
        if not ok:
            restore_position(acc, sym, before)
            # la gamba rifiutata si annulla (non si ritenta a ogni candela): resta la posizione di prima
            acc.cancel_split(sym, f"rifiutata da Bitget: {str(detail)[:60]}", now_ms)
            return f"{sym}: seconda gamba rifiutata da Bitget ({detail}); annullata"
    return None


# ── riallineamento con l'exchange (la verita') ──────────────────────────────────────────

def sync(live, acc, prices: dict, now_ms: int, close_engine: bool = True,
         alert: Callable[[str], None] = _noop) -> dict:
    """Confronta motore ed exchange. Ritorna {"closed": [record chiusi nel motore], "interlock": str|None,
    "notes": [...]}. Con close_engine=False non modifica il motore (solo blocco / avvisi: controllo a inizio ciclo).

    Regole (mai azioni alla cieca):
    - lettura fallita -> blocco aperture; niente altro;
    - chiusure richieste e non riuscite -> si ritentano;
    - stop/TP non ancora portati sull'exchange -> si ritenta con i valori ATTUALI del motore;
    - exchange piatto e motore aperto -> il motore chiude ("chiusa su Bitget");
    - tutto il resto che non coincide -> blocco aperture + avviso (non si tocca nulla)."""
    out = {"closed": [], "interlock": None, "notes": []}
    if not live._live:
        return out
    try:
        snap = live.snapshot()
    except LiveError as e:
        reason = f"lettura Bitget fallita ({str(e)[:100]})"
        _set(live, reason, alert)
        out["interlock"] = reason
        return out

    # 1) chiusure da ritentare: il motore le ha chiuse, l'exchange no
    retried = False
    for base, side in list(live.pending_close.items()):
        if base not in snap:
            live.pending_close.pop(base, None)
            continue
        retried = True
        ok, detail = live.close(base, side)
        out["notes"].append(f"{base}: richiusura {'riuscita' if ok else 'FALLITA: ' + str(detail)}")
        if ok:
            live.pending_close.pop(base, None)
    if retried:                      # l'elenco posizioni e' cambiato: si rilegge prima di confrontare
        try:
            snap = live.snapshot()
        except LiveError as e:
            reason = f"lettura Bitget fallita ({str(e)[:100]})"
            _set(live, reason, alert)
            out["interlock"] = reason
            return out
    stuck = sorted(b for b in live.pending_close if b in snap)

    # 2) stop / take profit che non siamo riusciti ad aggiornare: si ritenta con i valori del motore
    for base in list(live.stale_protection):
        pos = next((p for s, p in acc.positions.items() if _base(s) == base), None)
        if pos is None:
            live.stale_protection.pop(base, None)
            continue
        ok, detail = live.set_protection(pos.symbol, pos.side, pos.sl, pos.tp)
        out["notes"].append(f"{base}: stop/TP {'aggiornati' if ok else 'ancora da aggiornare'}")

    # 3) confronto
    cmp_ = live.compare(acc.positions, snap)
    if close_engine:
        for sym in cmp_["flat"]:
            px = prices.get(sym) or acc.positions[sym].entry
            rec = acc.close(sym, px, now_ms, "chiusa su Bitget")
            if rec is not None:
                rec["live"] = {"note": "posizione gia' chiusa sull'exchange (stop/TP/manuale): uscita stimata dal motore"}
                out["closed"].append(rec)
                out["notes"].append(f"{sym}: chiusa su Bitget, il motore si allinea")
    reasons = []
    if stuck:
        reasons.append("chiusura non riuscita su Bitget (il motore ha gia' chiuso): " + ", ".join(stuck))
    if cmp_["foreign"]:
        reasons.append("posizioni su Bitget che il motore non conosce: " + ", ".join(sorted(cmp_["foreign"])))
    for sym, desc in cmp_["mismatch"]:
        reasons.append(f"{sym}: {desc}")
    if not close_engine:
        for sym in cmp_["flat"]:
            reasons.append(f"{sym}: nel motore ma non su Bitget")
    reason = "; ".join(reasons) or None
    _set(live, reason, alert)
    out["interlock"] = reason
    return out


def _set(live, reason: Optional[str], alert: Callable[[str], None]) -> None:
    prev = live.interlock
    live.set_interlock(reason)
    if reason and reason != prev:
        alert(f"Nuove aperture BLOCCATE: {reason}")
    elif prev and not reason:
        alert("Blocco aperture rimosso: motore ed exchange allineati.")
