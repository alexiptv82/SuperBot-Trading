"""Container health: every configured bot's status.json must have been refreshed recently.

Freshness only proves the polling loop is alive; whether cycles are being journaled is in the status
file (last_success_ms) and, later, in the external sentinel. Exit 0 healthy, 1 not.
"""
import json
import os
import sys
import time

STALE_MS = 5 * 60 * 1000


def healthy(root, bots, now_ms):
    for bot in bots:
        try:
            with open(os.path.join(root, bot, "status.json")) as stream:
                status = json.load(stream)
            if now_ms - int(status["ts_ms"]) > STALE_MS:
                return False
        except (OSError, ValueError, KeyError, TypeError):
            return False
    return True


if __name__ == "__main__":
    bots = [b for b in os.environ.get("SIDECAR_BOTS", "hawk,bull").split(",") if b]
    sys.exit(0 if healthy(os.environ.get("SIDECAR_OUT", "/out"), bots, int(time.time() * 1000)) else 1)
