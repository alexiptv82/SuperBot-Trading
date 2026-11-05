"""Chiusura manuale delle posizioni PAPER del Brain: il comando che l'utente da' dall'app.

Canale: due file nella cartella dati del Brain (stesso schema dei classici, con file al posto di un'API).

* ``close_request.json`` (scritto dall'app): ``{"ts_ms": <int>, "position_ids": ["<id>", ...]}`` oppure
  ``{"ts_ms": <int>, "all": true}``. ``ts_ms`` e' l'istante della richiesta.
* ``close_result.json`` (scritto qui, atomico): ``{"request_ts_ms", "done_ms", "status", "closed", "failed"}``.
  ``status``: ``done`` | ``expired`` | ``invalid_request``. ``closed`` = id chiusi; ``failed`` = coppie
  ``[id, codice]`` (solo codici brevi: ``position_not_open``, ``position_already_closed``, ``price_unavailable``,
  o il codice del motore). Mai testi liberi, chiavi o importi.

Regole:
* La richiesta viene presa in carico con un rinomino atomico (``.close_request.work``): non si esegue due volte,
  anche se l'app la riscrive. Se il processo si ferma a meta', al giro dopo il file ``.work`` viene ripreso
  (la chiusura e' idempotente: una posizione gia' chiusa torna ``position_already_closed``).
* Una richiesta piu' vecchia di 10 minuti scade (``expired``): non si chiude nulla a distanza di ore da un
  clic. Una con ``ts_ms`` nel futuro oltre 10 minuti e' respinta (orologio sbagliato).
* Funziona anche con il Brain in pausa o fermo: chiudere non apre nulla e non costa chiamate al modello.
* Prezzo di uscita = chiusura dell'ultimo minuto chiuso del feed (nessuna slippage, come lo stop). Se il prezzo
  non c'e' la posizione NON viene chiusa e il guasto e' nel risultato: la richiesta e' comunque consumata,
  l'utente la rifa. Motivo registrato: ``manual`` (il Brain lo riconosce e non lo copia alla cieca).
* Nessuna rete qui: ``price_of`` e' iniettata. Nessuna scrittura sul journal oltre a ``close_paper``.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.executor.paper import ExecutionError
from backend.v3.executor.paper_close import close_paper

REQUEST_FILE = "close_request.json"
WORK_FILE = ".close_request.work"
RESULT_FILE = "close_result.json"
MAX_AGE_MS = 600_000
MAX_IDS = 50
_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
PriceOf = Callable[[str, int], Decimal]                  # (simbolo, now_ms) -> ultimo prezzo di mercato


@dataclass(frozen=True)
class ManualCloseReport:
    status: str                                           # done | expired | invalid_request
    closed: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]


def _parse(raw: object, now_ms: int) -> Optional[tuple[int, Optional[tuple[str, ...]]]]:
    """``(ts_ms, ids)`` con ``ids=None`` per «tutte»; ``None`` se la richiesta non e' valida."""
    if not isinstance(raw, dict):
        return None
    ts = raw.get("ts_ms")
    if type(ts) is not int or ts <= 0 or ts > now_ms + MAX_AGE_MS:
        return None
    if raw.get("all") is True:
        return (ts, None) if "position_ids" not in raw else None
    ids = raw.get("position_ids")
    if (type(ids) is not list or not 1 <= len(ids) <= MAX_IDS or "all" in raw
            or any(type(i) is not str or not _ID_RE.match(i) for i in ids)):
        return None
    return ts, tuple(dict.fromkeys(ids))                  # senza doppioni, ordine di arrivo


def _write_result(data_dir: Path, body: dict) -> None:
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=data_dir, prefix=".close_result.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(body, sort_keys=True))
        os.replace(tmp, data_dir / RESULT_FILE)
        tmp = None
    except OSError:
        pass                                              # un disco pieno non deve bloccare il Brain
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def run_manual_close(*, journal: EventJournal, portfolio_id: str, run_id: str, data_dir: Path,
                     price_of: PriceOf, fee_bps: Decimal | int, now_ms: int) -> Optional[ManualCloseReport]:
    """Esegue la richiesta in sospeso, se c'e'. ``None`` = nessuna richiesta (caso comune: un controllo di file)."""
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError("invalid_now")
    request, work = data_dir / REQUEST_FILE, data_dir / WORK_FILE
    try:
        os.replace(request, work)                         # una richiesta nuova sostituisce un .work vecchio
    except FileNotFoundError:
        if not work.is_file():
            return None                                   # niente richiesta e niente da riprendere
    except OSError:
        return None                                       # riprovera' al giro dopo
    try:
        raw = json.loads(work.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = None
    parsed = _parse(raw, now_ms)
    if parsed is None:
        report, req_ts = ManualCloseReport("invalid_request", (), ()), 0
    else:
        req_ts, ids = parsed
        if now_ms - req_ts > MAX_AGE_MS:
            report = ManualCloseReport("expired", (), ())
        else:
            report = _execute(journal, portfolio_id, run_id, ids, price_of, fee_bps, now_ms)
    _write_result(data_dir, {"request_ts_ms": req_ts, "done_ms": now_ms, "status": report.status,
                             "closed": list(report.closed), "failed": [list(f) for f in report.failed]})
    try:
        work.unlink()
    except OSError:
        pass
    return report


def _execute(journal: EventJournal, portfolio_id: str, run_id: str, ids: Optional[tuple[str, ...]],
             price_of: PriceOf, fee_bps: Decimal | int, now_ms: int) -> ManualCloseReport:
    try:
        open_positions = {p.position_id: p for p in build_summary(journal, portfolio_id, run_id).open_positions}
    except Exception:
        return ManualCloseReport("done", (), (("*", "journal_read_failed"),))
    wanted = tuple(open_positions) if ids is None else ids
    closed: list[str] = []
    failed: list[tuple[str, str]] = []
    for pid in wanted:
        pos = open_positions.get(pid)
        if pos is None:
            failed.append((pid, "position_not_open"))
            continue
        try:
            price = price_of(pos.symbol, now_ms)
        except Exception:
            failed.append((pid, "price_unavailable"))
            continue
        try:
            close_paper(portfolio_id=portfolio_id, run_id=run_id, position_id=pid, exit_price=price,
                        reason="manual", fee_bps=fee_bps, journal=journal, now_ms=now_ms)
            closed.append(pid)
        except ExecutionError as exc:
            failed.append((pid, str(exc)[:64] or "invalid"))
        except Exception:
            failed.append((pid, "close_failed"))
    return ManualCloseReport("done", tuple(closed), tuple(failed))
