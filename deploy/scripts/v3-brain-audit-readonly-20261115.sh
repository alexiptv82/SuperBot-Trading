#!/usr/bin/env bash
# Brain PAPER — audit in SOLA LETTURA (15/11/2026). Eseguire come root sulla VPS Singapore.
#
# Parte A: perche' «Chiudi trade» Brain non funziona (stato del bridge, del servizio uscite e del valore
#          "chiusura consentita" calcolato DENTRO il container web, dove la run e' montata read-only).
# Parte B: prestazioni reali di Brain dal journal (decisioni, LONG/SHORT, PnL, costi, rifiuti, regimi).
#
# NON modifica nulla: nessun file scritto nelle cartelle delle run, nessun comando di chiusura, nessun riavvio.
# NON stampa chiavi, token o testo del modello. Unica rete: prezzi pubblici Bitget per il PnL flottante.
set -uo pipefail
umask 077
RUN_ID=brain-v3-paper20261111
RUN=/opt/superbot-v3-paper-runs/$RUN_ID
STAGE=/opt/superbot-v3-rc84-stage
PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3
say(){ echo "BRAIN_AUDIT $*"; }

say "utc=$(date -u +%FT%TZ) stage_sha=$(git -C "$STAGE" rev-parse --short HEAD 2>/dev/null) stage_file_modificati=$(git -C "$STAGE" status --porcelain 2>/dev/null | wc -l)"

# ---------------------------------------------------------------- Parte A: chiusura manuale
for u in superbot-v3-paper-brain-exit superbot-v3-paper-brain-runner superbot-v3-paper-single-close-bridge; do
  say "unit=$u active=$(systemctl is-active "$u" 2>/dev/null) restarts=$(systemctl show -p NRestarts --value "$u" 2>/dev/null)"
done
say "socket_bridge=$([[ -S /run/superbot-paper-close/close.sock ]] && echo presente || echo assente)"
say "container=$(docker ps --format '{{.Names}}={{.Image}}' 2>/dev/null | xargs)"
say "web_mount_run=$(docker inspect superbot --format '{{range .Mounts}}{{if eq .Source "'"$RUN"'"}}rw={{.RW}}{{end}}{{end}}' 2>/dev/null)"
say "web_gate=$(docker inspect superbot --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep -E '^(V3_CUTOVER_READONLY|V3_ALLOW_BRAIN_SINGLE_CLOSE|V3_CLOSE_BRIDGE_ONLY|DESK_MODE|TRADING_MODE)=' | xargs)"
docker exec -i superbot python3 - <<'PY' 2>&1 | sed 's/^/BRAIN_AUDIT web: /'
import errno, fcntl, os, sys, time
from pathlib import Path
sys.path[:0] = ["/app", "/app/backend"]
try:
    from backend import v3_api as A
    from backend.v3.runner.exit_service import exit_service_healthy
except Exception as e:
    print("import_fallito", type(e).__name__); raise SystemExit
import inspect
env = os.environ
root = Path(env.get("V3_JOURNAL_PATH", "/x")).parent
now = int(time.time() * 1000)
print("run_id_ok=%d cartella=%s" % (env.get("V3_RUN_ID") == "brain-v3-paper20261111", root.name))
for flag, name in ((os.O_RDWR, "O_RDWR"), (os.O_RDONLY, "O_RDONLY")):
    try:
        fd = os.open(root / ".exit_service.lock", flag)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); fcntl.flock(fd, fcntl.LOCK_UN); held = 0
        except BlockingIOError:
            held = 1
        os.close(fd)
        print("lock_%s=apribile lease_tenuto_dal_servizio=%d" % (name, held))
    except OSError as e:
        print("lock_%s=ERRORE_%s" % (name, errno.errorcode.get(e.errno, e.errno)))
print("uscite_sane_viste_dal_web=%s" % exit_service_healthy(data_dir=root, run_id=env.get("V3_RUN_ID", ""), now_ms=now))
paths = A.V3Paths.from_env("/nonexistent", "/nonexistent")
print("chiusura_brain_consentita_vista_dal_web=%s   <- se False la dashboard disattiva «Chiudi»" % A._brain_single_close_ready(paths, now))
print("correzione_RO_presente=%d" % ("O_RDONLY" in inspect.getsource(__import__("backend.v3.runner.exit_service", fromlist=["x"])._active_lease_token)))
PY
say "web_post_chiusura_24h=$(docker logs --since 24h superbot 2>&1 | grep -o 'POST /api/v3/brain/close[^"]*" [0-9]*' | awk '{print $NF}' | sort | uniq -c | xargs)"
say "richiesta_in_coda=$([[ -e $RUN/close_request.json || -e $RUN/.close_request.work ]] && echo SI || echo no) ultimo_risultato_eta_s=$([[ -f $RUN/close_result.json ]] && echo $(( $(date +%s) - $(stat -c %Y $RUN/close_result.json) )) || echo nessuno)"

# ---------------------------------------------------------------- Parte B: prestazioni dal journal
cd "$STAGE" 2>/dev/null || { say "ERRORE stage assente"; exit 2; }
PYTHONPATH="$STAGE" PYTHONDONTWRITEBYTECODE=1 "$PY" - "$RUN" "$RUN_ID" <<'PY'
import collections, json, sqlite3, sys, time, urllib.request
from pathlib import Path
run, run_id = Path(sys.argv[1]), sys.argv[2]
say = lambda *a: print("BRAIN_AUDIT", *a, flush=True)
now = int(time.time() * 1000)
iso = lambda ms: time.strftime("%m-%d %H:%M", time.gmtime(ms / 1000))
con = sqlite3.connect((run / "journal.db").as_uri() + "?mode=ro", uri=True, timeout=3)
rows = con.execute("SELECT event_id, kind, occurred_at_ms, payload_json FROM v3_events WHERE portfolio_id='brain' AND run_id=? ORDER BY seq", (run_id,)).fetchall()
ev = [(i, k, t, json.loads(p)) for i, k, t, p in rows]
say(f"eventi={len(ev)} dal={iso(ev[0][2]) if ev else None} al={iso(ev[-1][2]) if ev else None} tipi={dict(collections.Counter(k for _, k, _, _ in ev))}")
dec = {i: p for i, k, t, p in ev if k == "brain_decision"}
dts = {i: t for i, k, t, p in ev if k == "brain_decision"}
say("decisioni_per_esito=" + json.dumps(dict(collections.Counter(f"{p.get('kind')}/{p.get('status')}/{p.get('rationale')}" for p in dec.values())), sort_keys=True))
say("decisioni_per_regime=" + json.dumps(dict(collections.Counter(f"{p.get('regime')}:{p.get('kind')}/{p.get('status')}" for p in dec.values())), sort_keys=True))
say("decisioni_per_simbolo=" + json.dumps(dict(collections.Counter(f"{p.get('symbol')}:{p.get('status')}" for p in dec.values())), sort_keys=True))
say("leva_ridotta_dal_rischio=%d peer_osservati=%d" % (sum("risk:leverage_adjusted" in (p.get("sources") or []) for p in dec.values()),
                                                     sum(any("paper_position_observation" in s for s in (p.get("sources") or [])) for p in dec.values())))
days = collections.Counter(time.strftime("%m-%d", time.gmtime(t / 1000)) for t in dts.values())
say("decisioni_per_giorno=" + json.dumps(dict(sorted(days.items()))))
opens = {p["position_id"]: (t, p) for i, k, t, p in ev if k == "paper_open"}
closes = [(t, p) for i, k, t, p in ev if k == "paper_close"]
closed_ids = {p["position_id"] for _, p in closes}
F = float
def regime_of(p):
    d = dec.get(p.get("decision_event_id")) or {}
    return d.get("regime") or "?", d.get("strategy_id") or "?"
say("aperture=%d long=%d short=%d leve=%s" % (len(opens), sum(p["side"] == 1 for _, p in opens.values()), sum(p["side"] == -1 for _, p in opens.values()),
                                              dict(collections.Counter(p["leverage"] for _, p in opens.values()))))
stops = [abs(F(p["fill_price"]) - F(p["stop_price"])) / F(p["fill_price"]) * 100 for _, p in opens.values()]
if stops:
    stops.sort()
    say("distanza_stop_pct min=%.2f mediana=%.2f max=%.2f" % (stops[0], stops[len(stops) // 2], stops[-1]))
def block(name, sel):
    if not sel:
        say(f"{name}: n=0"); return
    net = [F(p["realized_pnl"]) for _, p in sel]
    w, l = sum(x for x in net if x > 0), -sum(x for x in net if x < 0)
    fees = sum(F(p.get("fees", 0)) for _, p in sel)
    fund = sum(F(p["notional_entry"]) * 1e-4 * F(p["held_ms"]) / 28_800_000 for _, p in sel if p["side"] == 1)
    hold = sorted(F(p["held_ms"]) / 3_600_000 for _, p in sel)
    bp = [F(p["realized_pnl"]) / F(p["notional_entry"]) * 1e4 for _, p in sel]
    say(f"{name}: n={len(net)} vincenti={sum(x > 0 for x in net) / len(net):.2f} pnl={sum(net):+.2f} media={sum(net) / len(net):+.2f} "
        f"pf={(w / l if l else float('inf')):.2f} media_bp_nozionale={sum(bp) / len(bp):+.1f} commissioni={fees:.2f} "
        f"funding_long_stimato_non_contabilizzato={fund:.2f} durata_h_mediana={hold[len(hold) // 2]:.1f} max={hold[-1]:.1f}")
block("CHIUSE_TUTTE", closes)
block("CHIUSE_LONG", [c for c in closes if c[1]["side"] == 1])
block("CHIUSE_SHORT", [c for c in closes if c[1]["side"] == -1])
for reason in sorted({p.get("reason") for _, p in closes}):
    block(f"USCITA_{reason}", [c for c in closes if c[1].get("reason") == reason])
for sym in sorted({p["symbol"] for _, p in closes}):
    for side, lab in ((1, "L"), (-1, "S")):
        sel = [c for c in closes if c[1]["symbol"] == sym and c[1]["side"] == side]
        if sel:
            block(f"SIMBOLO_{sym}_{lab}", sel)
for reg in sorted({regime_of(p)[0] for _, p in closes}):
    for side, lab in ((1, "L"), (-1, "S")):
        sel = [c for c in closes if regime_of(c[1])[0] == reg and c[1]["side"] == side]
        if sel:
            block(f"REGIME_{reg}_{lab}", sel)
for sid in sorted({regime_of(p)[1] for _, p in closes}):
    block(f"STRATEGIA_{sid}", [c for c in closes if regime_of(c[1])[1] == sid])
eq, peak, dd = 0.0, 0.0, 0.0
for t, p in sorted(closes, key=lambda c: c[0]):
    eq += F(p["realized_pnl"]); peak = max(peak, eq); dd = max(dd, peak - eq)
say(f"pnl_realizzato={eq:+.2f} drawdown_massimo_realizzato={dd:.2f}")
def price(sym):
    try:
        with urllib.request.urlopen(f"https://api.bitget.com/api/v2/mix/market/ticker?symbol={sym}&productType=USDT-FUTURES", timeout=8) as r:
            return F(json.loads(r.read())["data"][0]["lastPr"])
    except Exception:
        return None
flo = 0.0
for pid, (t, p) in opens.items():
    if pid in closed_ids:
        continue
    px = price(p["symbol"])
    u = None if px is None else p["side"] * (px - F(p["fill_price"])) * F(p["quantity"])
    flo += u or 0.0
    say(f"APERTA {p['symbol']} {'LONG' if p['side'] == 1 else 'SHORT'} {p['leverage']}x margine={F(p['margin_used']):.0f} eta_h={(now - t) / 3_600_000:.1f} "
        f"stop_pct={abs(F(p['fill_price']) - F(p['stop_price'])) / F(p['fill_price']) * 100:.2f} flottante={'n/d' if u is None else f'{u:+.2f}'} id={pid[:10]}")
say(f"pnl_flottante_totale={flo:+.2f} (stima su ultimo prezzo pubblico; nessuna somma con snapshot precedenti)")
try:
    b = sqlite3.connect((run / "budget.db").as_uri() + "?mode=ro", uri=True, timeout=3)
    per = b.execute("SELECT substr(occurred_at,1,10), COUNT(*), SUM(units) FROM spend_events WHERE provider='deepseek' GROUP BY 1 ORDER BY 1").fetchall()
    say("ai_per_giorno=" + json.dumps({d: [n, round(u / 1e6, 3)] for d, n, u in per}))
except Exception as e:
    say(f"budget errore {type(e).__name__}")
for f in ("heartbeat.json", "exit_heartbeat.json"):
    try:
        h = json.loads((run / f).read_text())
        say(f + " " + json.dumps({k: h.get(k) for k in ("state", "last_error", "last_cycle", "daily_loss_level", "daily_loss_pct")}, sort_keys=True) + f" eta_s={(now - int(h.get('ts_ms') or 0)) // 1000}")
    except Exception as e:
        say(f"{f} illeggibile {type(e).__name__}")
say("NOTA: le proposte rifiutate dal rischio sono registrate senza lato, leva, stop e motivo specifico: i LONG scartati non sono ricostruibili dal journal.")
PY
say "errori_runner_48h=$(journalctl -u superbot-v3-paper-brain-runner --since -48h --no-pager -o cat 2>/dev/null | grep -o '"last_error": "[^"]*"' | sort | uniq -c | sort -rn | head -6 | xargs)"
say fine
