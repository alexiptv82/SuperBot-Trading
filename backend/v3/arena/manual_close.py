"""Chiusura manuale PAPER di UNA posizione di UNA AI dell'Arena, con motivazione umana facoltativa.

Lato privilegiato (bridge di chiusura o processo con la cartella della run in scrittura). Il web in sola lettura non
scrive mai qui direttamente. Protocollo verso il servizio uscite = quello del Brain (``runner/manual_close.py``):
``close_request.json`` con ``{"ts_ms", "position_ids": [id]}``; il servizio uscite e' l'unico che chiude e scrive
``paper_close`` nel journal.

Garanzie:
* idempotenza per ``request_id``: la stessa richiesta ripetuta non accoda una seconda chiusura; un ``request_id``
  riusato per un'altra posizione e' rifiutato;
* una sola richiesta in volo per run; posizione chiusa o non aperta -> rifiuto; servizio uscite non sano -> rifiuto;
* esito terminale letto dal JOURNAL (``paper_close``), non dal solo file di risultato: ``closed`` (chiusa da questa
  richiesta, motivo ``manual``), ``closed_by_other_exit`` (stop/target arrivati prima), ``failed`` (prezzo mancante o
  errore del motore), ``unconfirmed`` (il servizio uscite non ha mai preso in carico la richiesta);
* motivazione umana solo dopo ``closed``, una per posizione, append-only con catena di hash, mai dedotta dal PnL.

Registri nella cartella della run: ``arena_close_requests.jsonl`` e ``human_close_annotations.jsonl``.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from backend.v3.arena.read_view import _safe_scope
from backend.v3.arena.trial_plan import WalletPlan
from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.runner.exit_service import exit_service_healthy
from backend.v3.runner.manual_close import (
    MAX_AGE_MS,
    REQUEST_FILE,
    RESULT_FILE,
    WORK_FILE,
)

REQUESTS_FILE = "arena_close_requests.jsonl"
ANNOTATIONS_FILE = "human_close_annotations.jsonl"
REASONS = ("profit_protection", "loss_reduction", "trend_change", "other", "unspecified")
REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{16,64}$")
POSITION_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
NOTE_MAX = 280
GRACE_MS = 120_000
GENESIS = "0" * 64


class ArenaCloseError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


# --------------------------------------------------------------------------------------------- registri a catena
def _digest(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_chain(path: Path) -> list[dict]:
    """Righe verificate; una catena rotta o un file alterato e' un errore (fail-closed), mai ignorato."""
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        raise ArenaCloseError(409, "registry_unsafe")
    out, prev = [], GENESIS
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            raise ArenaCloseError(409, "registry_corrupt") from None
        if type(rec) is not dict or rec.get("prev") != prev or rec.get("hash") != _digest(rec):
            raise ArenaCloseError(409, "registry_corrupt")
        out.append(rec)
        prev = rec["hash"]
    return out


def _append(path: Path, record: dict, chain: list[dict]) -> dict:
    rec = dict(record, prev=chain[-1]["hash"] if chain else GENESIS)
    rec["hash"] = _digest(rec)
    line = (json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
    return rec


@contextmanager
def _locked(folder: Path):
    """Stesso lucchetto di cartella usato dall'API storica e dal servizio uscite per i file di comando."""
    fd = os.open(folder, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _check(plan: WalletPlan) -> None:
    if not _safe_scope(plan) or not plan.journal.is_file() or plan.journal.is_symlink():
        raise ArenaCloseError(409, "arena_run_not_available")


def _journal_closes(plan: WalletPlan) -> dict:
    out = {}
    for stored in EventJournal(plan.journal).list_run("brain", plan.run_id):
        ev = stored.event
        if ev.kind == "paper_close" and type(ev.payload.get("position_id")) is str:
            out.setdefault(ev.payload["position_id"], (ev.event_id, ev.occurred_at_ms, ev.payload))
    return out


# --------------------------------------------------------------------------------------------- richiesta
def request_close(plan: WalletPlan, *, position_id: object, request_id: object, now_ms: int) -> dict:
    _check(plan)
    if type(request_id) is not str or not REQUEST_ID.fullmatch(request_id):
        raise ArenaCloseError(422, "invalid_request_id")
    if type(position_id) is not str or not POSITION_ID.fullmatch(position_id):
        raise ArenaCloseError(422, "invalid_position_id")
    reg = plan.folder / REQUESTS_FILE
    with _locked(plan.folder):
        chain = read_chain(reg)
        known = next((r for r in chain if r["request_id"] == request_id), None)
        if known is not None:
            if known["position_id"] != position_id:
                raise ArenaCloseError(409, "request_id_reused")
            return _status_from(plan, known, now_ms)            # ripetizione: nessuna nuova richiesta
        if position_id in _journal_closes(plan):
            raise ArenaCloseError(409, "position_already_closed")
        summary = build_summary(EventJournal(plan.journal), "brain", plan.run_id)
        if position_id not in {p.position_id for p in summary.open_positions}:
            raise ArenaCloseError(404, "position_not_open")
        if exit_service_healthy(data_dir=plan.folder, run_id=plan.run_id, now_ms=now_ms) is not True:
            raise ArenaCloseError(409, "exit_service_not_ready")
        if (plan.folder / REQUEST_FILE).exists() or (plan.folder / WORK_FILE).exists():
            raise ArenaCloseError(409, "request_in_progress")
        ts = max(now_ms, (chain[-1]["ts_ms"] + 1) if chain else now_ms)   # ts unico: lega il risultato alla richiesta
        rec = _append(reg, {"schema": "arena_close_request_v1", "provider": plan.provider, "run_id": plan.run_id,
                            "request_id": request_id, "position_id": position_id, "ts_ms": ts}, chain)
        fd, tmp = tempfile.mkstemp(prefix=".close_request.", suffix=".tmp", dir=plan.folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"ts_ms": ts, "position_ids": [position_id]}, fh, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, plan.folder / REQUEST_FILE)
            tmp = None
        finally:
            if tmp is not None:
                os.unlink(tmp)
        return _status_from(plan, rec, now_ms)


# --------------------------------------------------------------------------------------------- stato
def _status_from(plan: WalletPlan, rec: dict, now_ms: int) -> dict:
    base = {"provider": plan.provider, "run_id": plan.run_id, "request_id": rec["request_id"],
            "position_id": rec["position_id"], "requested_ms": rec["ts_ms"]}
    close = _journal_closes(plan).get(rec["position_id"])
    if close is not None:
        event_id, at_ms, p = close
        manual = p.get("reason") == "manual" and at_ms >= rec["ts_ms"]
        return {**base, "status": "closed" if manual else "closed_by_other_exit", "terminal": True,
                "close_event_id": event_id, "closed_ms": at_ms, "exit_reason": p.get("reason"),
                "exit_price": p.get("exit_price"), "realized_pnl": p.get("realized_pnl")}
    result = None
    try:
        raw = json.loads((plan.folder / RESULT_FILE).read_text(encoding="utf-8"))
        if type(raw) is dict and raw.get("request_ts_ms") == rec["ts_ms"]:
            result = raw
    except (OSError, ValueError):
        pass
    if result is not None:
        failed = [f for f in result.get("failed") or [] if type(f) is list and len(f) == 2]
        code = (failed[0][1] if failed else result.get("status")) or "close_failed"
        code = code if type(code) is str and re.fullmatch(r"[a-z0-9_]{1,48}", code) else "close_failed"
        return {**base, "status": "failed", "terminal": True, "code": code}
    if (plan.folder / REQUEST_FILE).exists() or (plan.folder / WORK_FILE).exists():
        if now_ms - rec["ts_ms"] <= MAX_AGE_MS + GRACE_MS:
            return {**base, "status": "pending", "terminal": False}
    if now_ms - rec["ts_ms"] > MAX_AGE_MS + GRACE_MS:
        return {**base, "status": "unconfirmed", "terminal": True, "code": "exit_service_did_not_confirm"}
    return {**base, "status": "pending", "terminal": False}


def close_status(plan: WalletPlan, *, request_id: object, now_ms: int) -> dict:
    _check(plan)
    if type(request_id) is not str or not REQUEST_ID.fullmatch(request_id):
        raise ArenaCloseError(422, "invalid_request_id")
    rec = next((r for r in read_chain(plan.folder / REQUESTS_FILE) if r["request_id"] == request_id), None)
    if rec is None:
        raise ArenaCloseError(404, "request_not_found")
    status = _status_from(plan, rec, now_ms)
    note = next((a for a in read_annotations(plan) if a["position_id"] == rec["position_id"]), None)
    status["annotation"] = None if note is None else {"reason": note["reason"], "note": note.get("note"),
                                                      "annotated_ms": note["annotated_ms"]}
    return status


# --------------------------------------------------------------------------------------------- motivazione umana
def read_annotations(plan: WalletPlan) -> list[dict]:
    return read_chain(plan.folder / ANNOTATIONS_FILE)


def annotate(plan: WalletPlan, *, request_id: object, reason: object, note: object = None, now_ms: int) -> dict:
    _check(plan)
    if type(reason) is not str or reason not in REASONS:
        raise ArenaCloseError(422, "invalid_reason")
    if note is not None:
        if (type(note) is not str or not 0 < len(note.strip()) <= NOTE_MAX
                or any(ord(c) < 32 or ord(c) == 127 for c in note)):
            raise ArenaCloseError(422, "invalid_note")
        note = note.strip()
    with _locked(plan.folder):
        status = close_status(plan, request_id=request_id, now_ms=now_ms)
        if status["status"] != "closed":
            raise ArenaCloseError(409, "close_not_confirmed")    # niente motivo senza chiusura manuale confermata
        path = plan.folder / ANNOTATIONS_FILE
        chain = read_chain(path)
        old = next((a for a in chain if a["position_id"] == status["position_id"]), None)
        if old is not None:
            if old["request_id"] == request_id and old["reason"] == reason and old.get("note") == note:
                return old                                       # ripetizione identica
            raise ArenaCloseError(409, "already_annotated")      # una sola motivazione per posizione
        return _append(path, {"schema": "human_close_annotation_v1", "provider": plan.provider,
                              "run_id": plan.run_id, "position_id": status["position_id"],
                              "close_event_id": status["close_event_id"], "request_id": request_id,
                              "reason": reason, "note": note, "annotated_ms": now_ms,
                              "source": "human_operator"}, chain)


def manual_close_ready(plan: WalletPlan, now_ms: int) -> bool:
    """Per la dashboard: il servizio uscite di QUESTA run e' vivo (vale anche su un mount in sola lettura)."""
    try:
        return _safe_scope(plan) and exit_service_healthy(data_dir=plan.folder, run_id=plan.run_id, now_ms=now_ms)
    except (OSError, ValueError):
        return False


def dispatch(plans: dict, op: str, provider: str, body: dict, now_ms: int) -> tuple[int, dict]:
    """Punto d'ingresso unico per bridge e API: (stato HTTP, corpo). Nessun messaggio libero, solo codici."""
    plan: Optional[WalletPlan] = plans.get(provider) if type(plans) is dict else None
    if plan is None or type(body) is not dict:
        return 422, {"ok": False, "code": "invalid_provider"}
    try:
        if op == "close" and set(body) == {"position_id", "request_id"}:
            return 200, {"ok": True, **request_close(plan, now_ms=now_ms, **body)}
        if op == "status" and set(body) == {"request_id"}:
            return 200, {"ok": True, **close_status(plan, now_ms=now_ms, **body)}
        if op == "annotate" and set(body) in ({"request_id", "reason"}, {"request_id", "reason", "note"}):
            return 200, {"ok": True, "annotation": annotate(plan, now_ms=now_ms, **body)}
        return 422, {"ok": False, "code": "invalid_request"}
    except ArenaCloseError as exc:
        return exc.status, {"ok": False, "code": exc.code}
    except (OSError, ValueError):
        return 409, {"ok": False, "code": "arena_close_unavailable"}
