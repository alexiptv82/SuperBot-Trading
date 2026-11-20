"""Tesi di trading persistenti (``thesis_id``) e anti-reingresso, ricostruiti dal SOLO journal in modo causale.

Una TESI e' una catena di ingressi sullo stesso simbolo e lato: un nuovo ingresso continua la tesi dell'ingresso
precedente dello stesso (simbolo, lato) se avviene entro ``window_ms`` da quello e nessun ingresso di lato opposto
sullo stesso simbolo sta in mezzo. E' la stessa definizione dello strumento E0 (``ops/brain-unico/guardian``), cosi'
la misura sugli storici e il comportamento del runner parlano della stessa cosa.

* ``thesis_id`` e' deterministico: (run, simbolo, lato, id della DECISIONE del primo ingresso). Lo stesso valore
  si ottiene al momento della decisione e ricalcolandolo dopo dal journal.
* I tempi sono quelli delle DECISIONI (istante di riferimento del giro), non l'ora reale dell'apertura: in modalita'
  sidecar ``paper_open`` porta l'ora di parete e la catena non deve dipendere da quanto ha impiegato il modello.
* ``reentry_index`` = 1 per il primo ingresso della tesi, 2 per il primo reingresso, ...
* ``prev_outcome`` = esito dell'ultimo trade della tesi gia' CHIUSO prima dell'istante valutato (win / loss / flat /
  none): mai un esito futuro.
* Si leggono solo aperture e chiusure da ``now - lookback`` (query SQL filtrata, nessuna lettura completa della run).
  Se la catena arriva al bordo del lookback, ``truncated=True``: l'indice e' un minimo, non un valore esatto.

``ReentryPolicy`` e' un controllo deterministico e puro. Modalita': ``off``, ``observe`` (predefinita: registra che
cosa AVREBBE bloccato, non blocca) ed ``enforce``. Soglie provvisorie in attesa della misura E0 sugli storici
certificati e di una decisione del proprietario: in ``observe`` non cambiano alcun comportamento di trading.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
from typing import Iterable, Mapping, Optional

from backend.v3.events import EventJournal

HOUR_MS = 3_600_000
OUTCOMES = ("none", "win", "loss", "flat")
MODES = ("off", "observe", "enforce")


@dataclass(frozen=True)
class Entry:
    position_id: str
    symbol: str
    side: int
    opened_ms: int                  # istante della decisione d'ingresso
    decision_event_id: str


@dataclass(frozen=True)
class ThesisInfo:
    thesis_id: str
    reentry_index: int
    prev_outcome: str
    last_loss_close_ms: Optional[int]
    truncated: bool


@dataclass(frozen=True)
class ReentryPolicy:
    mode: str = "observe"
    window_ms: int = 12 * HOUR_MS              # come E0 (--reentry-window-h 12)
    max_reentry_index: int = 2                 # E0 H2: si misura l'EV degli ingressi di indice >= 3
    loss_cooldown_ms: int = 0                  # 0 = regola spenta

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError("invalid_reentry_mode")
        if (type(self.window_ms) is not int or self.window_ms <= 0 or type(self.max_reentry_index) is not int
                or self.max_reentry_index < 1 or type(self.loss_cooldown_ms) is not int or self.loss_cooldown_ms < 0):
            raise ValueError("invalid_reentry_policy")


def thesis_id_for(run_id: str, symbol: str, side: int, first_decision_id: str) -> str:
    key = f"{run_id}|{symbol}|{side}|{first_decision_id}"
    return "th-" + hashlib.sha256(key.encode()).hexdigest()[:24]


def _outcome(pnl) -> Optional[str]:
    try:
        x = Decimal(str(pnl))
    except (InvalidOperation, ValueError):
        return None
    if not x.is_finite():
        return None
    return "win" if x > 0 else "loss" if x < 0 else "flat"


class ThesisBook:
    def __init__(self, run_id: str, window_ms: int, since_ms: int, entries: Iterable[Entry] = (),
                 closes: Optional[Mapping[str, tuple[int, str]]] = None):
        self.run_id, self.window_ms, self.since_ms = run_id, window_ms, since_ms
        self.entries: list[Entry] = sorted(entries, key=lambda e: (e.opened_ms, e.position_id))
        self.closes: dict[str, tuple[int, str]] = dict(closes or {})

    @classmethod
    def from_journal(cls, journal: EventJournal, run_id: str, *, now_ms: int, window_ms: int,
                     lookback_ms: int = 30 * 24 * HOUR_MS) -> "ThesisBook":
        since = now_ms - lookback_ms
        entries, closes = [], {}
        for r in journal.list_run_kinds_since("brain", run_id, ("paper_open", "paper_close"), since):
            p = r.event.payload if isinstance(r.event.payload, Mapping) else {}
            pid = p.get("position_id")
            if type(pid) is not str or not pid or r.event.occurred_at_ms > now_ms:
                continue                                   # nulla dal futuro dell'istante valutato
            if r.event.kind == "paper_open":
                side, did = p.get("side"), p.get("decision_event_id")
                if type(p.get("symbol")) is str and side in (1, -1) and type(did) is str and did:
                    dec = journal.get(did)                 # poche aperture: lettura puntuale per id
                    at = dec.event.occurred_at_ms if dec is not None and dec.event.run_id == run_id \
                        else r.event.occurred_at_ms
                    entries.append(Entry(pid, p["symbol"], side, at, did))
            else:
                out = _outcome(p.get("realized_pnl"))
                if out is not None and pid not in closes:
                    closes[pid] = (r.event.occurred_at_ms, out)
        return cls(run_id, window_ms, since, entries, closes)

    def add_open(self, position_id: str, symbol: str, side: int, decision_ms: int, decision_event_id: str) -> None:
        self.entries.append(Entry(position_id, symbol, side, decision_ms, decision_event_id))
        self.entries.sort(key=lambda e: (e.opened_ms, e.position_id))

    def assess(self, symbol: str, side: int, at_ms: int, decision_event_id: str) -> ThesisInfo:
        """La tesi a cui APPARTERREBBE l'ingresso deciso da ``decision_event_id`` all'istante ``at_ms``. Solo dati
        precedenti ad ``at_ms``."""
        if side not in (1, -1):
            raise ValueError("invalid_side")
        chain: list[Entry] = []                            # catena corrente di (symbol, side)
        last_opposite: Optional[int] = None
        for e in self.entries:
            if e.opened_ms >= at_ms or e.symbol != symbol:
                continue
            if e.side == -side:
                last_opposite = e.opened_ms
                continue
            if chain and e.opened_ms - chain[-1].opened_ms <= self.window_ms and not (
                    last_opposite is not None and chain[-1].opened_ms < last_opposite < e.opened_ms):
                chain.append(e)
            else:
                chain = [e]
        continues = bool(chain) and at_ms - chain[-1].opened_ms <= self.window_ms and not (
            last_opposite is not None and chain[-1].opened_ms < last_opposite < at_ms)
        if not continues:
            return ThesisInfo(thesis_id_for(self.run_id, symbol, side, decision_event_id), 1, "none", None, False)
        done = sorted((self.closes[e.position_id] for e in chain
                       if e.position_id in self.closes and self.closes[e.position_id][0] < at_ms))
        prev = done[-1][1] if done else "none"
        losses = [ts for ts, out in done if out == "loss"]
        truncated = chain[0].opened_ms - self.since_ms <= self.window_ms
        return ThesisInfo(thesis_id_for(self.run_id, symbol, side, chain[0].decision_event_id), len(chain) + 1, prev,
                          losses[-1] if losses else None, truncated)


def evaluate(info: ThesisInfo, policy: ReentryPolicy, at_ms: int) -> tuple[bool, Optional[str]]:
    """(bloccherebbe?, regola). Non guarda la modalita': quella la applica chi chiama."""
    if info.reentry_index > policy.max_reentry_index:
        return True, "reentry_limit"
    if (policy.loss_cooldown_ms and info.prev_outcome == "loss" and info.last_loss_close_ms is not None
            and at_ms - info.last_loss_close_ms < policy.loss_cooldown_ms):
        return True, "loss_cooldown"
    return False, None
