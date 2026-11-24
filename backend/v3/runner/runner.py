"""Il "direttore" del Brain PAPER: ogni minuto il monitor delle uscite, a intervalli fissi (15 minuti o un multiplo) un giro del Brain.

``Runner.tick(now_ms)`` decide cosa e' dovuto adesso e lo esegue; ``Runner.run`` lo richiama in ciclo.
Qui non c'e' rete, ne' modello, ne' orologio di sistema: monitor e ciclo arrivano come funzioni (le costruisce
``wiring.py``), l'orologio e il sonno sono iniettati. Tutto e' provabile offline con un orologio finto.

Regole:
* **Monitor ogni minuto** (stop, take-profit, durata massima) SEMPRE, anche in pausa o fermo: la pausa ferma
  solo le NUOVE aperture, le posizioni aperte devono poter chiudere.
* **Comandi dell'utente** (chiusura manuale, ``manual_close.py``) a ogni tick (ogni ~5 s), anche in pausa o fermo,
  PRIMA del monitor: un clic sul pulsante non aspetta il minuto successivo.
* **Giro del Brain una volta per intervallo** (``cycle_ms``: 15 minuti di default, un multiplo di 15 minuti da
  configurazione; oggi 1 ora), a ``cycle_delay_ms`` (20 s) dopo l'inizio dell'intervallo, cosi' la candela appena
  chiusa e' disponibile sul feed. Se il processo parte a meta' intervallo il giro parte subito (la vista accetta dati
  fino a 15 minuti dopo la chiusura dell'ultima candela da 15 minuti). Un giro fallito NON si ripete nella stessa
  candela (niente raffica di chiamate al modello).
* **Pausa**: se esiste ``pause.flag`` nella cartella dati non si fanno giri del Brain (nessuna apertura e nessuna
  spesa per il modello) e lo stato e' ``paused``; togliendo il file il giro riparte subito se la candela non
  e' stata ancora servita. **Fermo** (``halted``): come la pausa ma deciso dal programma (es. tetto di spesa).
* **Battito** ``heartbeat.json`` riscritto a ogni tick in modo atomico: ``ts_ms``, ``cycle`` (giri completati da
  questo processo), ``state`` (running|paused|halted), ``run_id``, ``last_error`` (solo codici brevi, mai
  testi liberi, chiavi o importi) o ``null``. Con il freno di perdita giornaliera (``daily_loss.py``) il battito porta
  anche ``daily_loss_level`` (ok|warn|halt|unknown) e ``daily_loss_pct`` (perdita di oggi in %, una cifra decimale).
* **Perdita giornaliera**: valutata a ogni tick DOPO comandi e monitor (una chiusura appena avvenuta conta subito);
  al livello ``halt`` lo stato e' ``halted`` (``halted:daily_loss``, come il tetto di spesa: niente giri del Brain,
  uscite e comandi proseguono); se la valutazione fallisce, ``halted:daily_loss_check_failed``.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from backend.v3.runner.cycle import CycleReport
from backend.v3.runner.daily_loss import DailyLoss, pct_text
from backend.v3.runner.manual_close import ManualCloseReport
from backend.v3.runner.monitor import MonitorReport

CYCLE_MS = 900_000
MINUTE_MS = 60_000
STATES = ("running", "paused", "halted")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")


@dataclass(frozen=True)
class TickResult:
    state: str
    monitor: Optional[MonitorReport]
    cycle: Optional[CycleReport]
    last_error: Optional[str]
    manual: Optional[ManualCloseReport] = None


def _short(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:,-]", "_", text)[:120]


class Runner:
    def __init__(self, *, run_id: str, data_dir: Path, run_monitor: Callable[[int], MonitorReport],
                 run_cycle: Callable[[int, int], CycleReport], halted: Callable[[], Optional[str]] = lambda: None,
                 cycle_delay_ms: int = 20_000, cycle_ms: int = CYCLE_MS,
                 run_commands: Optional[Callable[[int], Optional[ManualCloseReport]]] = None,
                 daily_loss: Optional[Callable[[int], DailyLoss]] = None):
        if type(run_id) is not str or not _RUN_ID_RE.match(run_id):
            raise ValueError("invalid_run_id")
        if not isinstance(data_dir, Path) or not data_dir.is_dir():
            raise ValueError("invalid_data_dir")
        if type(cycle_ms) is not int or not CYCLE_MS <= cycle_ms <= 86_400_000 or cycle_ms % CYCLE_MS:
            raise ValueError("invalid_cycle_ms")
        if type(cycle_delay_ms) is not int or not 0 <= cycle_delay_ms < cycle_ms:
            raise ValueError("invalid_cycle_delay")
        self.run_id, self.data_dir = run_id, data_dir
        self.pause_path, self.heartbeat_path = data_dir / "pause.flag", data_dir / "heartbeat.json"
        self._monitor, self._cycle, self._halted, self._delay = run_monitor, run_cycle, halted, cycle_delay_ms
        self._commands, self._cycle_ms = run_commands, cycle_ms
        self._daily_loss = daily_loss
        self._last_minute = -1
        self._last_slot = -1
        self.cycles = 0

    def tick(self, now_ms: int) -> TickResult:
        if type(now_ms) is not int or now_ms <= 0:
            raise ValueError("invalid_now")
        errors: list[str] = []
        halt_reason = None
        try:
            halt_reason = self._halted()
        except Exception:
            halt_reason = "halt_check_failed"                  # nel dubbio: niente nuove aperture
        monitor_report = cycle_report = manual_report = None
        if self._commands is not None:
            try:
                manual_report = self._commands(now_ms)
                if manual_report is not None and manual_report.failed:
                    errors.append(_short(f"manual:{manual_report.failed[0][1]}"))
            except Exception:
                errors.append("commands_failed")
        minute = now_ms // MINUTE_MS
        if minute > self._last_minute:
            self._last_minute = minute
            try:
                monitor_report = self._monitor(now_ms)
                if monitor_report.errors:
                    errors.append(_short(f"monitor:{monitor_report.errors[0][1]}"))
            except Exception:
                errors.append("monitor_failed")

        # la perdita di oggi si valuta DOPO comandi e monitor: una chiusura appena avvenuta (stop, chiusura manuale)
        # conta subito e non puo' lasciare aprire una nuova posizione nello stesso tick
        loss_info: Optional[dict] = None
        if self._daily_loss is not None:
            try:
                loss = self._daily_loss(now_ms)
                loss_info = {"daily_loss_level": loss.level, "daily_loss_pct": pct_text(loss.loss_fraction)}
                if loss.level == "halt":
                    halt_reason = halt_reason or "daily_loss"
            except Exception:
                loss_info = {"daily_loss_level": "unknown"}
                halt_reason = halt_reason or "daily_loss_check_failed"   # nel dubbio: niente nuove aperture
        state = "halted" if halt_reason else ("paused" if self.pause_path.exists() else "running")
        if halt_reason:
            errors.insert(0, _short(f"halted:{halt_reason}"))

        slot = now_ms // self._cycle_ms
        if slot > self._last_slot and now_ms - slot * self._cycle_ms >= self._delay and state == "running":
            self._last_slot = slot                              # servita comunque: un guasto non si ripete nella candela
            try:
                cycle_report = self._cycle(now_ms, slot)
                self.cycles += 1
                if cycle_report.errors:
                    errors.append(_short("cycle:" + ",".join(f"{s}:{c}" for s, c in cycle_report.errors[:3])))
            except Exception:
                errors.append("cycle_failed")

        last_error = ";".join(errors)[:200] if errors else None
        self._write_heartbeat(now_ms, state, last_error, loss_info)
        return TickResult(state, monitor_report, cycle_report, last_error, manual_report)

    def _write_heartbeat(self, now_ms: int, state: str, last_error: Optional[str],
                         extra: Optional[dict] = None) -> None:
        beat = {"ts_ms": now_ms, "cycle": self.cycles, "state": state, "run_id": self.run_id,
                "last_error": last_error}
        if extra:
            beat.update(extra)
        body = json.dumps(beat, sort_keys=True)
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(dir=self.data_dir, prefix=".heartbeat.", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
            os.replace(tmp, self.heartbeat_path)
            tmp = None
        except OSError:
            pass                                                # un disco pieno non deve fermare le uscite
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def run(self, *, now_fn: Callable[[], int], sleep_fn: Callable[[float], None],
            should_stop: Callable[[], bool] = lambda: False, poll_s: float = 5.0,
            on_tick: Optional[Callable[[int, TickResult], None]] = None) -> None:
        """Ciclo infinito (finche' ``should_stop`` non e' vero). Un'eccezione inattesa in un tick non lo ferma;
        ``on_tick`` (log) e' best-effort: un suo errore non ferma il ciclo."""
        while not should_stop():
            now = now_fn()
            try:
                result = self.tick(now)
            except Exception:
                self._write_heartbeat(now, "running", "tick_failed")
            else:
                if on_tick is not None:
                    try:
                        on_tick(now, result)
                    except Exception:
                        pass
            sleep_fn(poll_s)
