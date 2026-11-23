"""Sonda del confronto DOPO il reset. Si esegue DENTRO il container web vero, via stdin: ``python3 -B - <modo> <reset_ms>``.

modo ``paused``: run nuove preparate, in pausa; modo ``active``: run nuove attive. In entrambi:
* ``/api/v3/compare`` senza sessione = 401; con sessione = 200 con esattamente Falco Evoluto e Brain Scalp;
* per ciascuna: run_id atteso, capitale pieno (1000 / 2000), equity contabile = capitale, 0 chiusure, P&L 0, nessuna
  posizione aperta, stop giornaliero della nuova configurazione, leva 15-45, rischio 4 % / 10 %, Guardian attivo,
  NESSUN dato precedente al reset (decisioni e valutazioni del Guardian tutte successive a ``reset_ms``);
* chiusura manuale: «chiudi tutte» rifiutata; chiusura singola di una posizione inesistente -> 404 dal bridge della SUA
  run (mai 200, mai l'altra run).
Non stampa token, password, ambiente o importi reali.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

EXPECT = {"falco_evoluto": ("falco-evoluto-paper-p1", "1000", "12.00"),
          "brain_scalp": ("brain-scalp-paper-p1", "2000", "25.00")}
BASE = "http://127.0.0.1:8001"


def say(k, v):
    print(f"RESET_PROBE {k}={v}", flush=True)


def fail(code):
    say("RESULT", "FAILED_" + code)
    sys.exit(2)


def http(path, headers=None, data=None):
    req = urllib.request.Request(BASE + path, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def check(data, mode, reset_ms):
    if data.get("available") is not True:
        fail("compare_not_available")
    runs = {r.get("name"): r for r in data.get("runs") or []}
    if set(runs) != set(EXPECT):
        fail("compare_runs_unexpected")
    for name, (run_id, equity, stop) in EXPECT.items():
        r = runs[name]
        cfg = r.get("config") or {}
        if r.get("available") is not True or r.get("run_id") != run_id:
            fail("run_unexpected_" + name)
        if (r.get("initial_equity") != equity or r.get("settled_equity") != equity or r.get("closed") != 0
                or r.get("net_pnl") not in ("0", "0.00") or r.get("open_positions") != []):
            fail("not_a_fresh_portfolio_" + name)
        if (cfg.get("daily_stop_pct") != stop or cfg.get("leverage") != [15, 45] or cfg.get("guardian") is not True
                or cfg.get("risk_per_trade_pct") != "4.00" or cfg.get("open_risk_pct") != "10.00"):
            fail("config_unexpected_" + name)
        old = [d for d in r.get("decisions") or [] if not isinstance(d.get("ts_ms"), int) or d["ts_ms"] < reset_ms]
        g = r.get("guardian") or {}
        if old or (g and (not isinstance(g.get("as_of_ms"), int) or g["as_of_ms"] < reset_ms)):
            fail("old_data_visible_" + name)
        if mode == "paused" and r.get("paused") is not True:
            fail("run_not_paused_" + name)
        if mode == "active" and (r.get("paused") is not False or r.get("state") != "running"):
            fail("run_not_running_" + name)
        if r.get("manual_close_allowed") is not True:
            fail("close_not_ready_" + name)
        say(name, f"{run_id} capitale {equity} nuovo, stop {stop} %, {'in pausa' if mode == 'paused' else 'RUNNING'}")


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("paused", "active") or not sys.argv[2].isdigit():
        fail("usage")
    mode, reset_ms = sys.argv[1], int(sys.argv[2])
    from backend.auth import create_session_token
    if http("/api/v3/compare")[0] != 401:
        fail("no_session_not_401")
    hdr = {"Authorization": "Bearer " + create_session_token("full"), "Content-Type": "application/json"}
    status, body = http("/api/v3/compare", hdr)
    if status != 200:
        fail("compare_status_%s" % status)
    check(json.loads(body), mode, reset_ms)
    for name in EXPECT:
        status, _b = http(f"/api/v3/compare/{name}/close", hdr, b'{"all": true}')
        if status not in (422, 423):
            fail(f"close_all_not_refused_{name}_{status}")
        status, _b = http(f"/api/v3/compare/{name}/close", hdr, b'{"position_id": "reset-probe-inesistente"}')
        if status != 404:
            fail(f"single_close_not_routed_{name}_{status}")
        say(name + "_chiusura_singola", "instradata alla sua run (404 su posizione inesistente)")
    say("RESULT", "PASS_" + mode.upper())


if __name__ == "__main__":
    main()
