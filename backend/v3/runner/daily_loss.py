"""Freno di perdita giornaliera del Brain PAPER (decisione dell'utente, 5/11: avviso al 35 %, stop al 50 %).

**Definizione (scelta tecnica di Claude, i due numeri sono dell'utente):**
* giorno = giorno UTC (stessa regola del tetto di spesa del modello): riparte a mezzanotte UTC;
* capitale di inizio giornata = capitale iniziale + PnL realizzato delle chiusure PRIMA di mezzanotte;
* perdita di oggi = perdita realizzata oggi + perdita NON realizzata delle posizioni aperte (prezzo dell'ultimo minuto
  chiuso contro il prezzo d'ingresso); un guadagno compensa. Se il prezzo di una posizione non c'e' si conta solo
  il realizzato per quella posizione (lo stop la limita comunque);
* frazione = perdita / capitale di inizio giornata. ``>= warn`` -> ``warn`` (avviso, il Brain continua);
  ``>= halt`` -> ``halt``: nessuna nuova apertura e nessuna chiamata al modello fino a mezzanotte UTC
  (uscite, stop e chiusura manuale proseguono). Lo stop e' **agganciato per il resto del giorno**: anche se
  le posizioni aperte poi recuperano, non si riapre fino al giorno dopo.

``DailyLossGuard`` e' la funzione che il direttore chiama a ogni controllo: valuta al massimo una volta al minuto,
ricorda lo stato nel file ``daily_loss.json`` della cartella dati (cosi' un riavvio non rimanda l'avviso e non
toglie il blocco) e manda l'avviso una sola volta per livello e per giorno. Nessun importo nei file di stato
oltre alle frazioni; nessuna rete se non l'invio dell'avviso (iniettato, best-effort).
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Callable, Optional

from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal

DAY_MS = 86_400_000
MINUTE_MS = 60_000
STATE_FILE = "daily_loss.json"
LEVELS = ("ok", "warn", "halt")


@dataclass(frozen=True)
class DailyLoss:
    level: str                  # ok | warn | halt
    loss_fraction: Decimal      # >= 0
    loss_usd: Decimal           # >= 0, PAPER
    day_start_ms: int


def day_start_ms(now_ms: int) -> int:
    return now_ms // DAY_MS * DAY_MS


def pct_text(fraction: Decimal) -> str:
    """Percentuale con un decimale TRONCATO (mai arrotondata in su: 34,99 % non diventa «35,0» mentre il livello e'
    ancora ``ok``), per battito e messaggi (``Decimal`` finito >= 0)."""
    return str((fraction * 100).quantize(Decimal("0.1"), rounding=ROUND_DOWN))


def _check_fractions(warn: object, halt: object) -> None:
    if (type(warn) is not Decimal or type(halt) is not Decimal or not warn.is_finite() or not halt.is_finite()
            or not Decimal("0") < warn < halt <= Decimal("1")):
        raise ValueError("invalid_daily_loss_fractions")


def evaluate_daily_loss(*, journal: EventJournal, portfolio_id: str, run_id: str, initial_equity: Decimal,
                        now_ms: int, price_of: Callable[[str, int], Decimal], warn_fraction: Decimal,
                        halt_fraction: Decimal) -> DailyLoss:
    """Perdita di oggi e livello. Fail-closed sul capitale: se quello di inizio giornata non e' positivo e' ``halt``."""
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError("invalid_now")
    if type(initial_equity) is not Decimal or not initial_equity.is_finite() or initial_equity <= 0:
        raise ValueError("invalid_initial_equity")
    _check_fractions(warn_fraction, halt_fraction)
    summary = build_summary(journal, portfolio_id, run_id)
    start = day_start_ms(now_ms)
    before = sum((t.realized_pnl for t in summary.closed_trades if t.closed_at_ms < start), Decimal("0"))
    today = sum((t.realized_pnl for t in summary.closed_trades if t.closed_at_ms >= start), Decimal("0"))
    unrealized = Decimal("0")
    for pos in summary.open_positions:
        try:
            price = price_of(pos.symbol, now_ms)
        except Exception:
            continue                                            # prezzo non disponibile: conta solo il realizzato
        if type(price) is not Decimal or not price.is_finite() or price <= 0:
            continue
        unrealized += (price - pos.fill_price) * pos.quantity * pos.side
    start_equity = initial_equity + before
    if start_equity <= 0:
        return DailyLoss("halt", Decimal("1"), max(-(today + unrealized), Decimal("0")), start)
    loss = max(-(today + unrealized), Decimal("0"))
    fraction = loss / start_equity
    level = "halt" if fraction >= halt_fraction else ("warn" if fraction >= warn_fraction else "ok")
    return DailyLoss(level, fraction, loss, start)


class DailyLossGuard:
    """Valuta una volta al minuto, ricorda warn/halt per il giorno e manda un solo avviso per livello."""

    def __init__(self, *, data_dir: Path, evaluate: Callable[[int], DailyLoss],
                 send: Optional[Callable[[str], bool]] = None, warn_fraction: Decimal, halt_fraction: Decimal):
        _check_fractions(warn_fraction, halt_fraction)
        if not isinstance(data_dir, Path) or not data_dir.is_dir():
            raise ValueError("invalid_data_dir")
        self._path = data_dir / STATE_FILE
        self._evaluate, self._send = evaluate, send
        self._warn, self._halt = warn_fraction, halt_fraction
        self._minute = -1
        self._last: Optional[DailyLoss] = None
        self._state = self._load()

    def _load(self) -> dict:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = None
        ok = (isinstance(raw, dict) and set(raw) == {"day_start_ms", "warn_sent", "halt_sent", "halt_latched"}
              and type(raw["day_start_ms"]) is int and all(type(raw[k]) is bool for k in
                                                           ("warn_sent", "halt_sent", "halt_latched")))
        return raw if ok else {"day_start_ms": 0, "warn_sent": False, "halt_sent": False, "halt_latched": False}

    def _save(self) -> None:
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".daily_loss.", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._state, f, sort_keys=True)
            os.replace(tmp, self._path)
            tmp = None
        except OSError:
            pass                                                # lo stato in memoria vale comunque
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def _notify(self, key: str, text: str) -> None:
        if self._send is None or self._state[key]:
            return
        try:
            sent = self._send(text) is True
        except Exception:
            sent = False
        if sent:
            self._state[key] = True                              # se l'invio fallisce si riprova al minuto dopo
            self._save()

    def __call__(self, now_ms: int) -> DailyLoss:
        if type(now_ms) is not int or now_ms <= 0:
            raise ValueError("invalid_now")
        minute = now_ms // MINUTE_MS
        if self._last is not None and minute == self._minute:
            return self._last
        result = self._evaluate(now_ms)                         # se solleva, niente cache: il direttore va in «fermo»
        start = day_start_ms(now_ms)
        if self._state["day_start_ms"] != start:
            self._state = {"day_start_ms": start, "warn_sent": False, "halt_sent": False, "halt_latched": False}
            self._save()
        if result.level == "halt" and not self._state["halt_latched"]:
            self._state["halt_latched"] = True
            self._save()
        if self._state["halt_latched"] and result.level != "halt":
            result = DailyLoss("halt", result.loss_fraction, result.loss_usd, result.day_start_ms)
        if result.level == "warn":                               # se salta dritto a halt, un avviso «si ferma al 50 %» sarebbe falso
            self._notify("warn_sent", (
                f"⚠️ Brain PAPER: perdita di oggi al {pct_text(result.loss_fraction)}% del portafoglio "
                f"(avviso al {pct_text(self._warn)}%). Si ferma da solo al {pct_text(self._halt)}%: "
                f"puoi fermarlo tu prima."))
        if result.level == "halt":
            self._notify("halt_sent", (
                f"🛑 Brain PAPER: raggiunta la perdita massima di oggi ({pct_text(result.loss_fraction)}%). "
                f"Nessuna nuova apertura fino a mezzanotte UTC. Le posizioni aperte restano protette dai loro stop "
                f"e puoi chiuderle a mano."))
        self._minute, self._last = minute, result
        return result
