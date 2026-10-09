"""Macchina a stati delle regole. Funzioni pure: ricevono evidenze, ritornano decisioni.

CANDIDATA  -> IDONEA        se supera la soglia (evidence.check_gate)
CANDIDATA  -> RITIRATA      se futile (t chiaramente negativo dopo abbastanza trade)
IDONEA     -> CANDIDATA     se non supera piu' la soglia
IDONEA     -> LIVE_PICCOLO  solo con live_enabled=True, senza allarme dei controlli,
                            entro max_live regole, per t decrescente
LIVE_PICCOLO -> RETROCESSA  se in live il t scende sotto demote_t dopo demote_n trade
ALLARME dei controlli (un controllo casuale con vantaggio enorme = errore di sistema):
                            nessuna transizione, nessuna promozione; il chiamante deve
                            sospendere i nuovi ingressi live finche' l'allarme dura.
RETROCESSA / RITIRATA sono terminali per quella versione: per riprovare serve una
nuova versione della regola (contatori azzerati).

Stato predefinito: CANDIDATA. Il live e' spento finche' non lo si abilita esplicitamente.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from rule_pool import evidence as ev


class State(str, Enum):
    CANDIDATA = "CANDIDATA"
    IDONEA = "IDONEA"
    LIVE_PICCOLO = "LIVE_PICCOLO"
    RETROCESSA = "RETROCESSA"
    RITIRATA = "RITIRATA"


TERMINAL = (State.RETROCESSA, State.RITIRATA)


@dataclass(frozen=True)
class RuleEvidence:
    summary: Optional[ev.Summary]          # trade paper/replay chiusi
    halves_ok: bool
    excess: Optional[float]                # media netta regola - media netta controllo
    live: Optional[ev.Summary] = None      # trade live chiusi (per la retrocessione)


def decide(states: dict, evidences: dict, k: int, gate: ev.Gate, live_enabled: bool = False,
           alarm: bool = False) -> dict:
    """Ritorna {rule_id: (nuovo_stato, [motivi])} per ogni regola in `states`."""
    out: dict = {}
    for rid, st in states.items():
        e = evidences.get(rid)
        s = e.summary if e else None
        if st in TERMINAL:
            out[rid] = (st, ["stato terminale: serve una nuova versione"])
        elif alarm:
            # Allarme dei controlli = possibile errore di sistema: si congela tutto, senza
            # promuovere ne' retrocedere nessuno. Il chiamante sospende i nuovi ingressi live.
            out[rid] = (st, ["allarme controlli: decisioni congelate"])
        elif st == State.LIVE_PICCOLO:
            lv = e.live if e else None
            if (lv is not None and lv.n >= gate.demote_n and math.isfinite(lv.t_gate)
                    and lv.t_gate <= gate.demote_t):
                out[rid] = (State.RETROCESSA, [f"live: t={lv.t_gate:.2f} <= {gate.demote_t} dopo {lv.n} trade"])
            else:
                out[rid] = (st, [])
        elif ev.futility(s, gate):
            out[rid] = (State.RITIRATA, [f"futile: t={s.t_gate:.2f} dopo {s.n} trade"])
        else:
            g = ev.check_gate(s, k, gate, e.halves_ok if e else False, e.excess if e else None)
            if g["pass"]:
                out[rid] = (State.IDONEA, [])
            else:
                why = [name for name, ok in g["checks"].items() if not ok]
                out[rid] = (State.CANDIDATA, ["non passa: " + ", ".join(why)])
    if live_enabled and not alarm:
        live_now = [r for r, (st, _) in out.items() if st == State.LIVE_PICCOLO]
        room = max(0, gate.max_live - len(live_now))
        ranked = sorted(
            (r for r, (st, _) in out.items() if st == State.IDONEA),
            key=lambda r: evidences[r].summary.t_gate, reverse=True)
        for r in ranked[:room]:
            out[r] = (State.LIVE_PICCOLO, ["promossa: idonea e posto libero"])
    return out
