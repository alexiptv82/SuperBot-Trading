"""Strict web-to-host UNIX socket client: PAPER one-position close ONLY.

No filesystem writes, credentials, model calls or direct exchange access from
the dashboard. The run directories remain read-only inside Docker.
"""
from __future__ import annotations

import json
import os
import socket
from typing import Any

SOCKET_PATH = "/run/superbot-paper-close/close.sock"
MAX_REPLY_BYTES = 4096
MAX_REQUEST_BYTES = 512


class CloseBridgeError(Exception):
    def __init__(self, status: int = 409, message: str = "Servizio PAPER di chiusura non disponibile."):
        self.status = status
        self.message = message
        super().__init__(message)


def send_single_close(wallet: str, value: str) -> dict[str, Any]:
    """A failed socket call is NEVER interpreted as a successfully queued close."""
    if wallet not in ("falco", "toro", "brain") or type(value) is not str or len(value) > 64:
        raise CloseBridgeError(422, "Richiesta di chiusura non valida.")
    # A pinned socket location only, even if a malicious environment asks for
    # another path. Middleware and authenticated routes are mandatory too.
    if os.environ.get("V3_CLOSE_BRIDGE_SOCKET") != SOCKET_PATH:
        raise CloseBridgeError()
    name = "position_id" if wallet == "brain" else "symbol"
    message = json.dumps({"wallet": wallet, name: value}, separators=(",", ":")).encode("ascii")
    if len(message) > MAX_REQUEST_BYTES:
        raise CloseBridgeError(422, "Richiesta troppo lunga.")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.settimeout(3.0)
            channel.connect(SOCKET_PATH)
            channel.sendall(message + b"\n")
            reply = bytearray()
            while len(reply) <= MAX_REPLY_BYTES:
                data = channel.recv(min(1024, MAX_REPLY_BYTES + 1 - len(reply)))
                if not data:
                    break
                reply.extend(data)
                if b"\n" in data:
                    break
        if len(reply) > MAX_REPLY_BYTES or not reply.endswith(b"\n"):
            raise ValueError("invalid_reply")
        envelope = json.loads(reply)
        if (type(envelope) is not dict or set(envelope) != {"status", "payload"}
                or type(envelope["status"]) is not int
                or envelope["status"] not in (200, 400, 404, 409, 422, 423)
                or type(envelope["payload"]) is not dict):
            raise ValueError("invalid_reply")
        status, payload = envelope["status"], envelope["payload"]
        if status == 200 and payload.get("ok") is True:
            return payload
        if status != 200:
            raw = payload.get("message") or payload.get("detail") or ""
            text = raw if isinstance(raw, str) else raw.get("message") if isinstance(raw, dict) else ""
            raise CloseBridgeError(status, str(text)[:160] or "Chiusura PAPER rifiutata.")
        raise ValueError("false_ok")
    except CloseBridgeError:
        raise
    except (OSError, ValueError, UnicodeError, TypeError, json.JSONDecodeError):
        raise CloseBridgeError() from None
