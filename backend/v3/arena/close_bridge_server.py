"""Processo host (root) del canale di chiusura manuale PAPER dell'Arena. Separato dal bridge storico.

Rivalida ogni richiesta: ambiente PAPER, giorno di prova, cartella della run con ``arena_manifest.json`` coerente
(provider, run_id, paper, 2000), poi ``manual_close.dispatch``. Scrive solo ``close_request.json`` e i due registri
append-only nella cartella della AI indicata. Non avvia ne' ferma servizi, non apre posizioni.

Uso (solo su autorizzazione): DESK_MODE=paper TRADING_MODE=paper V3_ARENA_TRIAL_DAY=AAAA-MM-GG \
    V3_ARENA_ALLOW_MANUAL_CLOSE=1 V3_ARENA_CLOSE_SOCKET=/run/superbot-arena-close/arena.sock \
    python -m backend.v3.arena.close_bridge_server
"""
from __future__ import annotations

import json
import os
import socketserver
import stat
import sys
import time
from datetime import date
from pathlib import Path

from backend.v3.arena import manual_close as MC
from backend.v3.arena.close_bridge import (
    MAX_REQUEST_BYTES,
    OPS,
    PROVIDERS,
    SOCKET_PATH,
    arena_manual_close_enabled,
)
from backend.v3.arena.trial_plan import build_trial_plan

ROOT = Path("/opt/superbot-ai-arena-paper")


def _manifest_ok(plan) -> bool:
    path = plan.folder / "arena_manifest.json"
    try:
        if path.is_symlink() or path.stat().st_size > 8192:
            return False
        m = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return False
    return (type(m) is dict and m.get("provider") == plan.provider and m.get("run_id") == plan.run_id
            and m.get("mode") == "paper" and m.get("initial_capital") == "2000"
            and m.get("experiment") == "independent")


def load_plans(environ, root: Path = ROOT) -> dict:
    if not arena_manual_close_enabled(environ):
        raise RuntimeError("arena_bridge_not_paper_only")
    day = date.fromisoformat(environ.get("V3_ARENA_TRIAL_DAY", ""))
    return {p.provider: p for p in build_trial_plan(day, root=root)}


def process(plans: dict, raw: bytes, now_ms: int) -> tuple[int, dict]:
    if not raw.endswith(b"\n") or len(raw) > MAX_REQUEST_BYTES + 1:
        return 422, {"ok": False, "code": "invalid_request"}
    try:
        msg = json.loads(raw)
    except (ValueError, UnicodeError):
        return 422, {"ok": False, "code": "invalid_request"}
    if (type(msg) is not dict or set(msg) != {"op", "provider", "body"} or msg["op"] not in OPS
            or msg["provider"] not in PROVIDERS or type(msg["body"]) is not dict):
        return 422, {"ok": False, "code": "invalid_request"}
    plan = plans.get(msg["provider"])
    if plan is None or not _manifest_ok(plan):
        return 409, {"ok": False, "code": "arena_run_not_available"}
    return MC.dispatch({plan.provider: plan}, msg["op"], plan.provider, msg["body"], now_ms)


def _handler(plans: dict):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            self.connection.settimeout(3)
            try:
                status, payload = process(plans, self.rfile.readline(MAX_REQUEST_BYTES + 2),
                                          int(time.time() * 1000))
            except (OSError, TimeoutError):
                status, payload = 409, {"ok": False, "code": "arena_bridge_unavailable"}
            try:
                self.wfile.write(json.dumps({"status": status, "payload": payload},
                                            separators=(",", ":")).encode() + b"\n")
            except OSError:
                return
    return Handler


class _Server(socketserver.UnixStreamServer):
    allow_reuse_address = False
    request_queue_size = 4


def main() -> int:
    if os.geteuid() != 0:
        raise RuntimeError("bridge_requires_root")
    plans = load_plans(os.environ)
    sock = Path(SOCKET_PATH)
    parent = sock.parent
    if parent.is_symlink() or not parent.is_dir():
        raise RuntimeError("socket_directory_missing")
    pst = parent.stat()
    if pst.st_uid != 0 or stat.S_IMODE(pst.st_mode) != 0o700:
        raise RuntimeError("socket_directory_must_be_private")
    if sock.exists() or sock.is_symlink():
        raise RuntimeError("socket_path_already_occupied")
    try:
        with _Server(str(sock), _handler(plans)) as server:
            os.chmod(sock, 0o600)
            print("ARENA_PAPER_CLOSE_BRIDGE_READY=True", flush=True)
            server.serve_forever(poll_interval=0.5)
    finally:
        try:
            if sock.is_socket():
                sock.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("ARENA_PAPER_CLOSE_BRIDGE_REFUSED=guard_failed", file=sys.stderr)
        sys.exit(2)
