#!/bin/bash
# Controllo di Hawk: cosa e' successo al suo conto/flag e, se e' fermo, lo AVVIA con il comando vero dell'app.
# NON stampa mai token o password.
OUT=/tmp/diag_e2e.txt
exec > "$OUT" 2>&1
API=http://127.0.0.1:8002
H=/opt/superbot-desk-data/hawk
echo "=== ORA UTC: $(date -u) ==="

hb() {
  python3 - "$1" <<'PY'
import json, sys, time
try:
    h = json.load(open(f"/opt/superbot-desk-data/{sys.argv[1]}/heartbeat.json"))
    n = h.get("next_cycle_ms") or 0
    print({"mode": h.get("mode"), "pause_requested": h.get("pause_requested"), "open": h.get("open_positions"),
           "cycles": h.get("cycles"), "last_ok": h.get("last_ok"), "last_error": (h.get("last_error") or "")[:80],
           "version": h.get("version"), "age_s": round(time.time() - h["ts"]),
           "next_in_min": round((n / 1000 - time.time()) / 60, 1) if n else None})
except Exception as e:
    print("heartbeat illeggibile:", e)
PY
}

echo "--- file Hawk (data completa):"; ls -la --time-style=full-iso $H | awk '{print $6, $7, $5, $9}' | tail -n +2
echo "--- archivio Hawk:"; ls -la --time-style=full-iso $H/archive 2>&1 | awk '{print $6, $7, $9}' | tail -n +2
echo "--- riepiloghi archiviati:"
for f in $H/archive/*/summary.json; do [ -e "$f" ] && python3 - "$f" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
print({k: s.get(k) for k in ("archive", "run_no", "trades", "pnl", "start_equity", "end_equity", "lessons_cleared")})
PY
done
echo "--- stato Hawk:"
python3 - <<'PY'
import json
s = json.load(open("/opt/superbot-desk-data/hawk/state_v2.json"))
m = s.get("main", {})
print({"run_no": s.get("run_no"), "paused": s.get("paused"), "mode": s.get("mode"), "cash": m.get("cash"),
       "positions": list(m.get("positions", {})), "closed_in_state": len(m.get("closed", [])),
       "last_action": s.get("last_action"), "budget": s.get("budget")})
PY
echo "--- log Hawk (ultimi 14):"; docker logs --tail 14 superbot-desk-hawk 2>&1 | cut -c1-200
echo "--- heartbeat Hawk:"; hb hawk
[ -e $H/pause.flag ] && echo "pause.flag Hawk: PRESENTE" || echo "pause.flag Hawk: assente"

TOKEN=$(docker exec superbot python3 -c "import sys; sys.path.insert(0,'/app/backend'); from auth import create_session_token; print(create_session_token('full'))" 2>/dev/null | tail -1)
if [ -z "$TOKEN" ]; then echo "ERRORE: sessione di prova non creata"; else
  call() { curl -s -m 25 -H "Authorization: Bearer $TOKEN" "$@"; }
  summ() { python3 -c "
import sys, json
d = json.load(sys.stdin)
print({k: d.get(k) for k in sys.argv[1].split(',') if k in d})" "$1"; }
  if [ -e $H/pause.flag ]; then
    echo; echo ">> Hawk e' in pausa: premo AVVIA (POST /api/desk/resume), come farebbe l'app"
    call -X POST $API/api/desk/resume | summ paused,bot_mode,message
    sleep 50
  fi
  echo "--- Hawk dopo l'avvio:"; echo -n "  server: "; call $API/api/desk/status | summ bot_mode,paused,bot_online,equity,cash,margin_used,open_positions,total_closed,run_no,halt,last_action
  echo -n "  posizioni: "; call $API/api/desk/status | python3 -c "
import sys,json
d=json.load(sys.stdin)
print([(p['symbol'],p['side'],p['trade_type'],p['leverage'],p['margin'],p['pnl'],p['price_source']) for p in d.get('positions',[])])"
  echo -n "  bot: "; hb hawk
  docker logs --tail 30 superbot-desk-hawk 2>&1 | grep -E "AVVIO|MODO|candles|readings|OPEN|CLOSE|GUARDRAIL|CAP|SKIP|COOLDOWN|HALT|SLEEP|Claude|Traceback|Error" | cut -c1-170 | tail -14
  [ -e $H/pause.flag ] && echo "pause.flag Hawk: ancora presente" || echo "pause.flag Hawk: assente, Hawk in funzione"
  echo; echo "--- Bull (non toccato):"; echo -n "  server: "; call $API/api/desk/bull/status | summ bot_mode,paused,equity,open_positions,total_closed
fi
echo; echo "FINE"
