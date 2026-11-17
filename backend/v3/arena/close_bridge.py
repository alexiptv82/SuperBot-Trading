"""Canale web -> host per le chiusure manuali PAPER dell'Arena (separato da quello di Falco/Toro/Brain storico).

Il container web monta le cartelle dell'Arena in sola lettura: non scrive mai file di comando. Le uniche tre
operazioni ammesse passano da un socket UNIX dedicato a un processo host (``close_bridge_server``) che rivalida
tutto: ``close`` (UNA posizione), ``status`` e ``annotate`` (motivazione umana). Nessuna apertura, nessun reset,
nessuna chiusura di massa, nessun accesso all'exchange. Un errore del canale non e' MAI un successo.
"""
from __future__ import annotations

import json
import os
import socket

SOCKET_PATH = "/run/superbot-arena-close/arena.sock"
SOCKET_ENV = "V3_ARENA_CLOSE_SOCKET"
OPS = ("close", "status", "annotate")
PROVIDERS = ("deepseek", "qwen", "minimax")
MAX_REQUEST_BYTES = 1024
MAX_REPLY_BYTES = 4096
CODE_STATUSES = (200, 404, 409, 422, 423)


class ArenaBridgeError(Exception):
    def __init__(self, status: int = 409, code: str = "arena_bridge_unavailable"):
        super().__init__(code)
        self.status, self.code = status, code


def arena_manual_close_enabled(env) -> bool:
    """Opt-in esplicito, solo PAPER, solo con il socket fissato: senza, le rotte non esistono."""
    return (env.get("V3_ARENA_ALLOW_MANUAL_CLOSE") == "1"
            and env.get("DESK_MODE") == "paper" and env.get("TRADING_MODE") == "paper"
            and env.get(SOCKET_ENV) == SOCKET_PATH)


def encode(op: str, provider: str, body: dict) -> bytes:
    if op not in OPS or provider not in PROVIDERS or type(body) is not dict:
        raise ArenaBridgeError(422, "invalid_request")
    raw = json.dumps({"op": op, "provider": provider, "body": body}, ensure_ascii=True,
                     separators=(",", ":")).encode("ascii")
    if len(raw) > MAX_REQUEST_BYTES:
        raise ArenaBridgeError(422, "request_too_large")
    return raw + b"\n"


def decode_reply(reply: bytes) -> dict:
    if len(reply) > MAX_REPLY_BYTES or not reply.endswith(b"\n"):
        raise ArenaBridgeError()
    try:
        env = json.loads(reply)
    except (ValueError, UnicodeError):
        raise ArenaBridgeError() from None
    if (type(env) is not dict or set(env) != {"status", "payload"} or type(env["status"]) is not int
            or env["status"] not in CODE_STATUSES or type(env["payload"]) is not dict):
        raise ArenaBridgeError()
    status, payload = env["status"], env["payload"]
    if status == 200 and payload.get("ok") is True:
        return payload
    code = payload.get("code")
    if status == 200 or type(code) is not str or len(code) > 48:
        raise ArenaBridgeError()
    raise ArenaBridgeError(status, code)


def send(op: str, provider: str, body: dict, *, environ=os.environ) -> dict:
    message = encode(op, provider, body)
    if environ.get(SOCKET_ENV) != SOCKET_PATH:            # mai un percorso scelto dall'ambiente
        raise ArenaBridgeError()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.settimeout(5.0)
            channel.connect(SOCKET_PATH)
            channel.sendall(message)
            reply = bytearray()
            while len(reply) <= MAX_REPLY_BYTES:
                data = channel.recv(min(1024, MAX_REPLY_BYTES + 1 - len(reply)))
                if not data:
                    break
                reply.extend(data)
                if b"\n" in data:
                    break
    except OSError:                                       # timeout compreso: nessun esito presunto
        raise ArenaBridgeError() from None
    return decode_reply(bytes(reply))
