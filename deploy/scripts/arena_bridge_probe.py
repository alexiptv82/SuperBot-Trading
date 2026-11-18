"""Sonda in SOLA LETTURA del canale app -> bridge di chiusura Arena. Solo libreria standard: si esegue DENTRO il
container web (``docker exec -i <web> python3 - [socket] < arena_bridge_probe.py``), cioe' con l'UID/GID reali
dell'app. Invia UNA richiesta ``status`` per un request_id inesistente: il bridge risponde 404 ``request_not_found``
senza scrivere nulla. Nessuna chiusura, nessuna scrittura, nessun segreto stampato."""
import json
import os
import socket
import stat
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/run/superbot-arena-close/arena.sock"
out = {"uid": os.getuid(), "gid": os.getgid(), "groups": sorted(os.getgroups()), "socket": path}
out["flags"] = {k: os.environ.get(k) for k in ("DESK_MODE", "TRADING_MODE", "V3_ARENA_ALLOW_MANUAL_CLOSE",
                                               "V3_ARENA_CLOSE_SOCKET", "V3_ARENA_READONLY_ENABLED",
                                               "V3_ARENA_TRIAL_DAY", "V3_CUTOVER_READONLY")}
try:
    st = os.stat(path)
    out["socket_stat"] = {"is_socket": stat.S_ISSOCK(st.st_mode), "mode": oct(stat.S_IMODE(st.st_mode)),
                          "uid": st.st_uid, "gid": st.st_gid}
    d = os.stat(os.path.dirname(path))
    out["dir_stat"] = {"mode": oct(stat.S_IMODE(d.st_mode)), "uid": d.st_uid, "gid": d.st_gid}
except FileNotFoundError:
    out["result"] = "SOCKET_MISSING_NOT_MOUNTED_OR_BRIDGE_DOWN"
except PermissionError:
    out["result"] = "PERMISSION_DENIED_ON_DIRECTORY"
if "result" not in out:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
            c.settimeout(5)
            c.connect(path)
            c.sendall(json.dumps({"op": "status", "provider": "qwen", "body": {"request_id": "req-0000000000000000"}},
                                 separators=(",", ":")).encode() + b"\n")
            raw = c.recv(4096)
        reply = json.loads(raw)
        code = (reply.get("payload") or {}).get("code")
        out["reply"] = {"status": reply.get("status"), "code": code}
        out["result"] = ("CHANNEL_OK" if (reply.get("status"), code) in ((404, "request_not_found"),
                                                                        (409, "arena_run_not_available"))
                         else "CHANNEL_REPLIED_UNEXPECTED")
    except PermissionError:
        out["result"] = "PERMISSION_DENIED_ON_SOCKET_NEEDS_DEDICATED_GROUP"
    except (ConnectionRefusedError, FileNotFoundError):
        out["result"] = "BRIDGE_NOT_LISTENING"
    except Exception as exc:                         # timeout o risposta non valida: mai presumere che funzioni
        out["result"] = "NO_VALID_ANSWER_" + type(exc).__name__
print("ARENA_BRIDGE_PROBE " + json.dumps(out, sort_keys=True))
sys.exit(0 if out.get("result") == "CHANNEL_OK" else 3)
