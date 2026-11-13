#!/usr/bin/env bash
# Brain PAPER — verifica prima dell'attivazione (issue #95). Eseguire come root sulla VPS Singapore.
#
# NON modifica: pause.flag, mandate.json, journal.db, budget.db, runner_config.json, unita' systemd, Falco, Toro.
# NON stampa chiavi ne' testo del modello: solo booleani, codici, conteggi, tempi, hash.
# UNICA azione esterna: UNA richiesta reale a DeepSeek, dentro un ciclo Brain completo eseguito su un journal
# TEMPORANEO in /tmp (cancellato alla fine), con candele pubbliche Bitget. NO_TRADE e' un esito valido.
# Costo stimato della richiesta: sotto 0,01 USD; NON registrato nel budget.db della run.
set -uo pipefail
umask 077
RUN_ID=brain-v3-paper20261111
RUN=${PF_RUN:-/opt/superbot-v3-paper-runs/$RUN_ID}
STAGE=${PF_STAGE:-/opt/superbot-v3-rc84-stage}
PY=${PF_PY:-/opt/superbot-v3-rc70-stage/.venv/bin/python3}
ENVF=${PF_ENVF:-/etc/superbot-v3-paper/brain-ai.env}
U_RUN=superbot-v3-paper-brain-runner
U_EXIT=superbot-v3-paper-brain-exit
say(){ echo "BRAIN_PF $*"; }

say "host=$(hostname) utc=$(date -u +%FT%TZ) ntp_sync=$(timedatectl show -p NTPSynchronized --value 2>/dev/null)"
say "stage_sha=$(git -C "$STAGE" rev-parse HEAD 2>/dev/null) stage_dirty=$(git -C "$STAGE" status --porcelain 2>/dev/null | wc -l)"

# 1-2. Unita', processi, stessa run, DESK_MODE
for u in $U_RUN $U_EXIT; do
  pid=$(systemctl show -p MainPID --value "$u" 2>/dev/null)
  say "unit=$u active=$(systemctl is-active "$u" 2>/dev/null) enabled=$(systemctl is-enabled "$u" 2>/dev/null) pid=$pid restarts=$(systemctl show -p NRestarts --value "$u" 2>/dev/null) since=$(systemctl show -p ActiveEnterTimestamp --value "$u" 2>/dev/null | tr ' ' '_')"
  es=$(systemctl show -p ExecStart --value "$u" 2>/dev/null)
  say "unit=$u run_id_ok=$([[ "$es" == *"--run-id $RUN_ID "* ]] && echo 1 || echo 0) data_dir_ok=$([[ "$es" == *"--data-dir $RUN "* ]] && echo 1 || echo 0) config_ok=$([[ "$es" == *"--config $RUN/runner_config.json"* ]] && echo 1 || echo 0) sidecar=$([[ "$es" == *"--exit-mode sidecar"* ]] && echo 1 || echo 0)"
  if [[ -n "$pid" && "$pid" != 0 && -r /proc/$pid/environ ]]; then
    say "unit=$u proc_desk_mode=$(tr '\0' '\n' </proc/$pid/environ | sed -n 's/^DESK_MODE=//p') proc_deepseek_key_present=$(tr '\0' '\n' </proc/$pid/environ | grep -c '^DEEPSEEK_API_KEY=..*') proc_cwd=$(readlink /proc/$pid/cwd)"
  fi
done
say "envfile_exists=$([[ -f $ENVF ]] && echo 1 || echo 0) envfile_mode=$(stat -c %a $ENVF 2>/dev/null) envfile_key_lines=$(grep -c '^[[:space:]]*DEEPSEEK_API_KEY=..*' $ENVF 2>/dev/null)"

# 10. Altri scrittori possibili sul journal Brain
say "journal_open_by_pids=$(fuser "$RUN/journal.db" 2>/dev/null | xargs)"
for p in $(fuser "$RUN/journal.db" 2>/dev/null); do say "journal_pid=$p unit=$(grep -o '[^/]*\.service' /proc/$p/cgroup 2>/dev/null | head -1)"; done
say "processi_con_run_id=$(pgrep -fc "$RUN_ID" 2>/dev/null) attesi=2"
say "altre_unita_superbot_attive=$(systemctl list-units --type=service --state=active --no-legend 'superbot*' 2>/dev/null | awk '{print $1}' | xargs)"
say "docker_attivi=$(docker ps --format '{{.Names}}' 2>/dev/null | xargs)"

# 3, 8, 9. File della run, mandato, rischio, heartbeat, budget, journal: SOLA LETTURA
cd "$STAGE" 2>/dev/null || { say "ERRORE stage assente"; exit 2; }
DESK_MODE=paper PYTHONPATH="$STAGE" PYTHONDONTWRITEBYTECODE=1 "$PY" - "$RUN" "$RUN_ID" <<'PY'
import hashlib, json, sqlite3, sys, time
from pathlib import Path
run, run_id = Path(sys.argv[1]), sys.argv[2]
say = lambda *a: print("BRAIN_PF", *a, flush=True)
now = int(time.time() * 1000)
for f in ("pause.flag", "mandate.json", "runner_config.json", "PREPARED_PAUSED_ONLY.json", "journal.db", "budget.db",
          "heartbeat.json", "exit_heartbeat.json", ".exit_service.lock", "close_request.json"):
    p = run / f
    say(f"file={f} exists={int(p.exists())}" + (f" age_s={(now - int(p.stat().st_mtime * 1000)) // 1000}" if p.exists() else ""))
from backend.v3.runner.config import load_runner_config
from backend.v3.brain_f2.engine import _policy_hash
cfg_raw = (run / "runner_config.json").read_bytes()
c = load_runner_config(cfg_raw)
rp = c.risk_policy
tpl = Path("backend/v3/runner/runner_config_brain2000_paper.json")
say(f"config_sha256={hashlib.sha256(cfg_raw).hexdigest()[:16]} uguale_template_2000={int(tpl.exists() and json.loads(tpl.read_bytes()) == json.loads(cfg_raw))}")
say(f"equity={c.initial_equity} floor={rp.minimum_equity} leva={rp.min_leverage}-{rp.max_leverage} rischio_ingresso={rp.max_loss_fraction} "
    f"rischio_aperto={rp.max_open_risk_fraction} margine_pos={rp.max_position_margin_fraction} margine_tot={rp.max_total_margin_fraction} "
    f"perdita_su_margine={rp.max_loss_margin_fraction} costi_bp={rp.estimated_roundtrip_cost_bp} buffer_liq={rp.liquidation_buffer_fraction}")
say(f"modello={c.model} thinking={c.thinking} effort={c.reasoning_effort} max_tokens={c.max_tokens} ciclo_min={c.cycle_minutes} "
    f"cap_usd_giorno={c.daily_cap_usd} perdita_giorno_avviso={c.daily_loss_warn} blocco={c.daily_loss_halt} simboli={len(c.symbols)}")
try:
    m = json.loads((run / "mandate.json").read_text())
    say(f"mandato approved={m.get('approved')} approved_by_presente={int(bool(m.get('approved_by')))} run_id_ok={int(m.get('run_id') == run_id)} "
        f"policy_hash_ok={int(m.get('policy_hash') == _policy_hash(rp))} portfolio={m.get('portfolio_id')}")
except Exception as e:
    say(f"mandato illeggibile {type(e).__name__}")
for f in ("heartbeat.json", "exit_heartbeat.json"):
    try:
        b = json.loads((run / f).read_text())
        keep = {k: b.get(k) for k in ("state", "run_id", "cycle", "last_error", "last_cycle", "daily_loss_level",
                                       "last_monitor_ms", "ts_ms")}
        say(f"{f} " + json.dumps(keep, sort_keys=True) + f" eta_s={(now - int(b.get('ts_ms') or 0)) // 1000}")
    except Exception as e:
        say(f"{f} illeggibile {type(e).__name__}")
try:
    from backend.v3.runner.exit_service import exit_service_healthy
    say(f"exit_service_healthy={exit_service_healthy(data_dir=run, run_id=run_id, now_ms=now)}")
except Exception as e:
    say(f"exit_service_healthy errore {type(e).__name__}")
def ro(db):
    return sqlite3.connect((run / db).as_uri() + "?mode=ro", uri=True, timeout=2)
try:
    with ro("journal.db") as j:
        rows = j.execute("SELECT kind, COUNT(*) FROM v3_events WHERE portfolio_id='brain' AND run_id=? GROUP BY kind", (run_id,)).fetchall()
        say("journal_eventi " + json.dumps(dict(rows), sort_keys=True))
        say("journal_integrity=" + j.execute("PRAGMA integrity_check").fetchone()[0])
    from backend.v3.events import EventJournal
    EventJournal(str(run / "journal.db")).verify_chain()
    say("journal_chain=ok")
except Exception as e:
    say(f"journal errore {type(e).__name__}")
try:
    day = time.strftime("%Y-%m-%d", time.gmtime())
    with ro("budget.db") as b:
        tot = b.execute("SELECT COALESCE(SUM(units),0), COUNT(*) FROM spend_events WHERE provider='deepseek' AND occurred_at LIKE ?", (day + "%",)).fetchone()
        alltime = b.execute("SELECT COALESCE(SUM(units),0), COUNT(*) FROM spend_events WHERE provider='deepseek'").fetchone()
    say(f"budget_oggi_usd={tot[0] / 1e6:.4f} chiamate_oggi={tot[1]} totale_usd={alltime[0] / 1e6:.4f} chiamate_totali={alltime[1]} cap_usd={c.daily_cap_usd}")
except Exception as e:
    say(f"budget errore {type(e).__name__}")
PY
say "errori_runner_24h=$(journalctl -u $U_RUN --since -24h --no-pager -o cat 2>/dev/null | grep -o '"last_error": "[^"]*"' | sort | uniq -c | sort -rn | head -5 | xargs)"
say "errori_exit_24h=$(journalctl -u $U_EXIT --since -24h --no-pager -o cat 2>/dev/null | grep -ciE 'error|traceback|refused')"
J0=$(sha256sum "$RUN/journal.db" 2>/dev/null | cut -c1-16); B0=$(sha256sum "$RUN/budget.db" 2>/dev/null | cut -c1-16)

# 4-7. UNA richiesta reale a DeepSeek dentro un ciclo Brain completo, su journal TEMPORANEO
TMP=$(mktemp -d /tmp/brain-pf-XXXXXX)
( set -a; . "$ENVF" 2>/dev/null; set +a
  DESK_MODE=paper PYTHONPATH="$STAGE" PYTHONDONTWRITEBYTECODE=1 "$PY" - "$RUN" "$TMP" <<'PY'
import dataclasses, json, ssl, sys, time, os, urllib.request, urllib.error
from pathlib import Path
from decimal import Decimal
say = lambda *a: print("BRAIN_PF", *a, flush=True)
run, tmp = Path(sys.argv[1]), Path(sys.argv[2])
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.wiring import build_runner, mandate_template
from backend.v3.brain_f3.providers import TransportResponse, ProviderUnavailable
from backend.v3 import transport as T
say(f"deepseek_key_caricata={int(bool(os.environ.get('DEEPSEEK_API_KEY', '').strip()))}")
full = load_runner_config((run / "runner_config.json").read_bytes())
from backend.v3.lab_tools.fetch_candles import http_json
from backend.v3.runner.contracts import ContractRules
rules = ContractRules(http_json, maintenance_fraction=full.maintenance_fraction)
rules.load(int(time.time() * 1000))
ok = [s for s in full.symbols if rules(s) is not None]
say(f"regole_contratti_ok={len(ok)}/{len(full.symbols)} mancanti={[s for s in full.symbols if s not in ok]}")
cfg = dataclasses.replace(full, symbols=(ok[0] if ok else "BTCUSDT",))
seen = {}
def probe(payload):
    """Stessa URL, intestazioni e richiesta della produzione; attesa massima 120 s per MISURARE il tempo
    (la produzione rinuncia dopo T._TIMEOUT_SECONDS). Non stampa testo, ragionamento o chiave."""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        seen["errore"] = "chiave_assente"; raise ProviderUnavailable("provider_unavailable")
    seen["payload_extra"] = {k: payload[k] for k in ("thinking", "reasoning_effort", "max_tokens", "model", "response_format") if k in payload}
    req = urllib.request.Request(T._DEEPSEEK_URL, data=json.dumps(payload).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
    key = ""
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=120, context=T._make_ssl_context()) as r:
            status, raw = r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        seen.update(http=e.code, secondi=round(time.monotonic() - t0, 1))
        try:
            err = json.loads(e.read()).get("error", {})
            seen["errore"] = {"type": err.get("type"), "code": err.get("code")}
        except Exception:
            seen["errore"] = "non_json"
        raise ProviderUnavailable("provider_unavailable") from None
    except Exception as e:
        seen.update(errore=type(e).__name__, secondi=round(time.monotonic() - t0, 1))
        raise ProviderUnavailable("provider_unavailable") from None
    seen.update(http=status, secondi=round(time.monotonic() - t0, 1))
    body = json.loads(raw)
    ch = (body.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    seen.update(modello_risposta=body.get("model"), finish_reason=ch.get("finish_reason"), usage=body.get("usage"),
                ragionamento_presente=int(bool(msg.get("reasoning_content"))),
                ragionamento_caratteri=len(msg.get("reasoning_content") or ""))
    try:
        obj = json.loads(msg.get("content") or "")
        seen["json_valido"] = 1
        seen["decisione"] = {k: obj.get(k) for k in ("kind", "side", "leverage", "confidence", "strategy_id", "strategy_origin")}
        if obj.get("kind") == "OPEN":
            e, s = Decimal(str(obj["entry_price"])), Decimal(str(obj["stop_price"]))
            seen["decisione"]["stop_pct"] = float(round(abs(e - s) / e * 100, 3))
    except Exception:
        seen["json_valido"] = 0
    return TransportResponse(status, body)
built = build_runner(data_dir=tmp, run_id="brain-pf-isolato", config=cfg, inner_transport=probe)
m = mandate_template(cfg.risk_policy, "brain-pf-isolato")
m.update(approved=True, approved_by="preflight-isolato")
(tmp / "mandate.json").write_text(json.dumps(m))
t = built.runner.tick(int(time.time() * 1000))
say("deepseek " + json.dumps(seen, sort_keys=True, default=str))
say(f"timeout_produzione_s={T._TIMEOUT_SECONDS} entro_timeout={int(seen.get('secondi', 999) < T._TIMEOUT_SECONDS)}")
cyc = t.cycle
say(f"ciclo_isolato state={t.state} last_error={t.last_error} decisioni={list(cyc.decisions) if cyc else None} "
    f"aperture_isolate={len(cyc.opened) if cyc else None} errori={list(cyc.errors) if cyc else None}")
for r in built.journal.list_run("brain", "brain-pf-isolato"):
    p = r.event.payload
    say("evento_isolato " + json.dumps({"kind": r.event.kind, **{k: p.get(k) for k in ("kind", "status", "reason", "code", "symbol", "side", "leverage", "sources") if k in p}}, default=str))
PY
)
rm -rf "$TMP"
say "journal_run_invariato=$([[ "$J0" == "$(sha256sum "$RUN/journal.db" 2>/dev/null | cut -c1-16)" ]] && echo 1 || echo 0) budget_run_invariato=$([[ "$B0" == "$(sha256sum "$RUN/budget.db" 2>/dev/null | cut -c1-16)" ]] && echo 1 || echo 0)"
say "pause_flag_ancora_presente=$([[ -f $RUN/pause.flag ]] && echo 1 || echo 0) fine"
