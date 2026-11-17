"""Prova REALE dei permessi del socket host: processo non-root con e senza il gruppo dedicato.

Richiede root (per creare il socket root:GID e cambiare UID nel figlio); altrimenti saltato. Nessuna rete.
Limite: stesso kernel e stesso namespace utenti; nel container web il GID numerico deve coincidere con quello host
(nessun userns-remap), da verificare sul VPS con lo smoke test della checklist.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from backend.v3.arena import close_bridge as CB
from backend.v3.arena import close_bridge_server as CBS

pytestmark = pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() != 0, reason="serve root")

GID = 54_321
NOBODY = 65_534


CLIENT = """
import json, sys
import close_bridge as CB  # copia del modulo (solo libreria standard), leggibile da nobody
CB.SOCKET_PATH = sys.argv[1]
try:
    out = {"ok": True, "reply": CB.send("status", "qwen", {"request_id": "req-0000000000000001"},
                                        environ={CB.SOCKET_ENV: sys.argv[1]})}
except CB.ArenaBridgeError as exc:
    out = {"ok": False, "status": exc.status, "code": exc.code}
print(json.dumps(out))
"""


def _as_user(groups: list[int], sock: str) -> dict:
    """Il client gira in un processo separato con UID/GID non privilegiati (come il web non-root)."""
    lib = Path(sock).parent.parent / "lib"          # la checkout del repo non e' leggibile da nobody
    if not lib.exists():
        lib.mkdir(mode=0o755)
        shutil.copy(CB.__file__, lib / "close_bridge.py")
        os.chmod(lib / "close_bridge.py", 0o644)
    done = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, %r)\n" % str(lib) + CLIENT, sock],
                          user=NOBODY, group=NOBODY, extra_groups=groups,
                          cwd="/", env={"PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True, timeout=30, check=True)
    return json.loads(done.stdout)


@pytest.fixture
def sockdir():
    base = Path(tempfile.mkdtemp(prefix="arena-sock-", dir="/tmp"))
    os.chmod(base, 0o755)
    d = base / "superbot-arena-close"
    d.mkdir()
    yield d
    shutil.rmtree(base)


def _serve(d: Path, gid):
    os.chown(d, 0, 0 if gid is None else gid)
    os.chmod(d, 0o700 if gid is None else 0o710)
    CBS.validate_socket_directory(d, gid)
    sock = d / "arena.sock"
    plans = {}                                  # nessuna run: ogni richiesta valida riceve 409 arena_run_not_available
    server = CBS._Server(str(sock), CBS._handler(plans))
    CBS.set_socket_permissions(sock, gid)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    return server, str(sock)


def test_web_uid_with_dedicated_group_reaches_the_host_socket(sockdir):
    server, sock = _serve(sockdir, GID)
    try:
        st = os.stat(sock)
        assert (st.st_uid, st.st_gid, st.st_mode & 0o777) == (0, GID, 0o660)
        ok = _as_user([GID], sock)               # il canale risponde: rifiuto applicativo, non di permessi
        assert ok == {"ok": False, "status": 409, "code": "arena_run_not_available"}
        denied = _as_user([], sock)              # senza il gruppo: connessione negata, mai un successo
        assert denied == {"ok": False, "status": 409, "code": "arena_bridge_unavailable"}
        other = _as_user([GID + 1], sock)
        assert other["code"] == "arena_bridge_unavailable"
    finally:
        server.shutdown()
        server.server_close()


def test_default_root_only_socket_refuses_the_web_uid(sockdir):
    server, sock = _serve(sockdir, None)
    try:
        assert os.stat(sock).st_mode & 0o777 == 0o600
        assert _as_user([GID], sock)["code"] == "arena_bridge_unavailable"
    finally:
        server.shutdown()
        server.server_close()
