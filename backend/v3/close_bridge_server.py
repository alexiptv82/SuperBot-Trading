"""Dedicated host-side close-only PAPER command bridge.

A UNIX domain socket exposes precisely one authenticated-by-filesystem
operation: queue closure of ONE already-open PAPER position. It cannot start
bots, open trades, reset portfolios, alter the mandate or close all positions.
Browser authentication remains mandatory in the FastAPI API before contacting
this socket. The original state directories remain Docker read-only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socketserver
import stat
import sys
import time

from fastapi import HTTPException

import desk_view as dv
from backend.v3.close_bridge import SOCKET_PATH, MAX_REQUEST_BYTES
from backend.v3_api import V3Paths, _close_request

RUN_ROOT = Path("/opt/superbot-v3-paper-runs")
FALCO = RUN_ROOT / "classic-hawk-paper20261111"
TORO = RUN_ROOT / "classic-bull-paper20261111"
# Run del Brain servita dal bridge: scelta dall'unita' systemd (V3_BRIDGE_BRAIN_RUN_DIR / V3_BRIDGE_BRAIN_RUN_ID), sempre
# sotto RUN_ROOT e con il nome accettato da prepare_paper_run. Senza variabili: la run storica di RC84 (stesso
# comportamento di prima). Valori non validi: nessuna run (il bridge rifiuta di partire, fail-closed).
_RUN_DIR_RE = re.compile(r"brain-v3-[A-Za-z0-9_-]{3,55}")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9_-]{3,64}")


def _brain_from_env(env) -> tuple:
    name = env.get("V3_BRIDGE_BRAIN_RUN_DIR", "brain-v3-paper20261111")
    run_id = env.get("V3_BRIDGE_BRAIN_RUN_ID", "brain-v3-paper20261111")
    if (type(name) is not str or type(run_id) is not str
            or not _RUN_DIR_RE.fullmatch(name) or not _RUN_ID_RE.fullmatch(run_id)):
        return None, None
    return RUN_ROOT / name, run_id


BRAIN, RUN_ID = _brain_from_env(os.environ)
# Portafogli PAPER aggiuntivi (23/11: Falco Evoluto, Brain Scalp), ognuno con la SUA run. Nomi fissi; cartelle e run_id
# dall'unita' systemd, in formato compatto senza virgolette ne' spazi (sicuro in ExecStart):
#   V3_BRIDGE_EXTRA_RUNS=falco_evoluto=brain-v3-<cartella>:<run_id>,brain_scalp=brain-v3-<cartella>:<run_id>
EXTRA_WALLETS = ("falco_evoluto", "brain_scalp")


def _extra_from_env(env) -> dict:
    """{nome: (cartella, run_id)}; valore assente o non valido -> {} (portafogli aggiuntivi rifiutati, RC1 invariato)."""
    raw = env.get("V3_BRIDGE_EXTRA_RUNS")
    if not raw or type(raw) is not str or len(raw) > 400:
        return {}
    out = {}
    for item in raw.split(","):
        name, eq, spec = item.partition("=")
        folder, colon, run_id = spec.partition(":")
        if (not eq or not colon or name not in EXTRA_WALLETS or name in out
                or not _RUN_DIR_RE.fullmatch(folder) or not _RUN_ID_RE.fullmatch(run_id)):
            return {}
        out[name] = (RUN_ROOT / folder, run_id)
    dirs = [d for d, _ in out.values()]
    if len(set(dirs)) != len(dirs) or BRAIN in dirs:
        return {}
    return out


EXTRA = _extra_from_env(os.environ)
SOCKET = Path(SOCKET_PATH)
CLASSIC_SYMBOL = re.compile(r"^[A-Za-z0-9_-]{1,24}$")
BRAIN_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def _reject(status: int = 409, message: str = "Chiusura PAPER non disponibile.") -> tuple[int, dict]:
    return status, {"ok": False, "message": message}


def _assert_paper_env() -> None:
    env = os.environ
    if (env.get("DESK_MODE") != "paper" or env.get("TRADING_MODE") != "paper"
            or env.get("V3_CUTOVER_READONLY") != "1"
            or env.get("V3_ALLOW_BRAIN_SINGLE_CLOSE") != "1"
            or env.get("V3_CLOSE_BRIDGE_ONLY") != "1"
            or env.get("V3_CLOSE_BRIDGE_SOCKET") != SOCKET_PATH):
        raise RuntimeError("bridge_not_paper_only")


def _assert_extra(name: str) -> tuple:
    """Identita' della run aggiuntiva ``name``, ricontrollata a ogni richiesta: cartella reale, marcatore PAPER della
    STESSA run, journal presente. Indipendente da Falco/Toro/RC1."""
    _assert_paper_env()
    if name not in EXTRA:
        raise RuntimeError("extra_run_not_configured")
    root, run_id = EXTRA[name]
    marker = root / "PREPARED_PAUSED_ONLY.json"
    if root.is_symlink() or not root.is_dir() or marker.is_symlink():
        raise RuntimeError("wallet_path_changed")
    try:
        record = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise RuntimeError("paper_marker_missing") from None
    if type(record) is not dict or record.get("paper_only") is not True or record.get("run_id") != run_id:
        raise RuntimeError("extra_run_id_mismatch")
    if not (root / "journal.db").is_file():
        raise RuntimeError("extra_journal_missing")
    return root, run_id


def _assert_paper() -> None:
    env = os.environ
    if (env.get("DESK_MODE") != "paper" or env.get("TRADING_MODE") != "paper"
            or env.get("V3_CUTOVER_READONLY") != "1"
            or env.get("V3_ALLOW_CLASSIC_SINGLE_CLOSE") != "1"
            or env.get("V3_ALLOW_BRAIN_SINGLE_CLOSE") != "1"
            or env.get("V3_CLOSE_BRIDGE_ONLY") != "1"
            or env.get("V3_CLOSE_BRIDGE_SOCKET") != SOCKET_PATH):
        raise RuntimeError("bridge_not_paper_only")
    if BRAIN is None or not RUN_ID:
        raise RuntimeError("brain_run_invalid")
    for path in (FALCO, TORO, BRAIN):
        marker = path / "PREPARED_PAUSED_ONLY.json"
        if path.is_symlink() or not path.is_dir() or marker.is_symlink():
            raise RuntimeError("wallet_path_changed")
        try:
            record = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            raise RuntimeError("paper_marker_missing") from None
        if type(record) is not dict or record.get("paper_only") is not True:
            raise RuntimeError("not_paper_wallet")
    if not (BRAIN / "journal.db").is_file():
        raise RuntimeError("brain_journal_missing")
    marker = json.loads((BRAIN / "PREPARED_PAUSED_ONLY.json").read_text(encoding="utf-8"))
    if marker.get("run_id", RUN_ID) != RUN_ID:
        raise RuntimeError("brain_run_id_mismatch")


def _run_paths(root: Path, run_id: str) -> V3Paths:
    return V3Paths(
        journal_path=str(root / "journal.db"),
        run_id=run_id,
        budget_db_path=str(root / "budget.db"),
        heartbeat_path=str(root / "heartbeat.json"),
        pause_flag_path=str(root / "pause.flag"),
        falco_data_dir=str(FALCO),
        toro_data_dir=str(TORO),
        close_request_path=str(root / "close_request.json"),
        close_result_path=str(root / "close_result.json"),
        brain_config_path=str(root / "runner_config.json"),
    )


def _brain_paths() -> V3Paths:
    return _run_paths(BRAIN, RUN_ID)


def process_single_close(body: object, now_ms: int | None = None) -> tuple[int, dict]:
    """Validate strict request and PAPER identity again inside host authority."""
    if type(body) is not dict:
        return _reject(422, "Richiesta non valida.")
    wallet = body.get("wallet")
    if wallet in ("falco", "toro") and set(body) == {"wallet", "symbol"}:
        symbol = body.get("symbol")
        if type(symbol) is not str or not CLASSIC_SYMBOL.fullmatch(symbol):
            return _reject(422, "Simbolo non valido.")
    elif wallet in ("brain",) + EXTRA_WALLETS and set(body) == {"wallet", "position_id"}:
        position_id = body.get("position_id")
        if type(position_id) is not str or not BRAIN_ID.fullmatch(position_id):
            return _reject(422, "Posizione Brain non valida.")
    else:
        return _reject(423, "Sono permesse solo chiusure singole PAPER.")
    if wallet in EXTRA_WALLETS:
        try:
            root, run_id = _assert_extra(wallet)
        except (RuntimeError, OSError, ValueError, TypeError):
            return _reject()
        return _queue_run_close(_run_paths(root, run_id), position_id, now_ms)
    try:
        _assert_paper()
        if wallet in ("falco", "toro"):
            data_dir, portfolio = (
                (FALCO, "hawk") if wallet == "falco" else (TORO, "bull"))
            ok, status, payload = dv.command_close_position(
                str(data_dir), symbol, portfolio)
            if status == 200 and ok is True:
                return 200, payload
            # Reject missing, duplicated or not-ready requests: NEVER turn into
            # a queued success response just because the socket is reachable.
            return status if status in (400, 404, 409) else 409, payload
        return _queue_run_close(_brain_paths(), position_id, now_ms)
    except (RuntimeError, OSError, ValueError, TypeError):
        return _reject()


def _queue_run_close(paths: V3Paths, position_id: str, now_ms: int | None) -> tuple[int, dict]:
    """Una sola posizione della run indicata: il servizio uscite di QUELLA run la chiude e la registra nel journal."""
    try:
        result = _close_request(paths, {"position_id": position_id}, now_ms or int(time.time() * 1000))
        return (200, result) if result.get("ok") is True else _reject()
    except HTTPException as exc:
        detail = exc.detail
        if type(detail) is dict:
            detail = detail.get("message", "")
        return _reject(
            exc.status_code if exc.status_code in (404, 409, 422, 423) else 409,
            str(detail)[:160] or "Posizione non disponibile.")
    except (RuntimeError, OSError, ValueError, TypeError):
        return _reject()


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.connection.settimeout(3)
        try:
            raw = self.rfile.readline(MAX_REQUEST_BYTES + 2)
            if not raw.endswith(b"\n") or len(raw) > MAX_REQUEST_BYTES + 1:
                status, payload = _reject(422, "Richiesta non valida.")
            else:
                try:
                    body = json.loads(raw)
                except (UnicodeError, ValueError):
                    body = None
                status, payload = process_single_close(body)
        except (OSError, TimeoutError):
            status, payload = _reject(409, "Canale di chiusura non disponibile.")
        try:
            self.wfile.write(json.dumps(
                {"status": status, "payload": payload},
                ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
        except OSError:
            return


class _Server(socketserver.UnixStreamServer):
    allow_reuse_address = False
    request_queue_size = 4


def main() -> int:
    if os.geteuid() != 0:
        raise RuntimeError("bridge_requires_root")
    _assert_paper()
    parent = SOCKET.parent
    if parent.is_symlink() or not parent.is_dir():
        raise RuntimeError("socket_directory_missing")
    pst = parent.stat()
    if pst.st_uid != 0 or stat.S_IMODE(pst.st_mode) != 0o700:
        raise RuntimeError("socket_directory_must_be_private")
    if SOCKET.exists() or SOCKET.is_symlink():
        raise RuntimeError("socket_path_already_occupied")
    try:
        with _Server(str(SOCKET), _Handler) as server:
            os.chmod(SOCKET, 0o600)
            print("RC84_PAPER_SINGLE_CLOSE_BRIDGE_READY=True", flush=True)
            server.serve_forever(poll_interval=0.5)
    finally:
        try:
            if SOCKET.is_socket():
                SOCKET.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("RC84_PAPER_SINGLE_CLOSE_BRIDGE_REFUSED=guard_failed", file=sys.stderr)
        sys.exit(2)
